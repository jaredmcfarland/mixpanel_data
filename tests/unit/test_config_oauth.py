"""Unit tests for AuthMethod enum and extended credential resolution (T010).

Tests the AuthMethod enum added to config.py and ensures existing Basic Auth
credential resolution behavior remains unchanged (regression tests).

Verifies:
- AuthMethod enum has 'basic' and 'oauth' values
- Existing Basic Auth resolution is unchanged
- auth_header() returns correct Authorization header for each method
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from mixpanel_data._internal.config import (
    AuthMethod,
    ConfigManager,
    Credentials,
)
from mixpanel_data.exceptions import (
    ConfigError,
)


class TestAuthMethodEnum:
    """Tests for the AuthMethod enum values and behavior."""

    def test_basic_value(self) -> None:
        """Verify AuthMethod.basic has the string value 'basic'.

        This value identifies service account (username/secret) authentication.
        """
        assert AuthMethod.basic == "basic"
        assert AuthMethod.basic.value == "basic"

    def test_oauth_value(self) -> None:
        """Verify AuthMethod.oauth has the string value 'oauth'.

        This value identifies OAuth 2.0 Bearer token authentication.
        """
        assert AuthMethod.oauth == "oauth"
        assert AuthMethod.oauth.value == "oauth"

    def test_enum_members(self) -> None:
        """Verify AuthMethod has exactly two members: basic and oauth."""
        members = list(AuthMethod)
        assert len(members) == 2
        assert AuthMethod.basic in members
        assert AuthMethod.oauth in members

    def test_enum_from_string(self) -> None:
        """Verify AuthMethod can be constructed from string values.

        Example:
            ```python
            method = AuthMethod("basic")
            assert method == AuthMethod.basic
            ```
        """
        assert AuthMethod("basic") == AuthMethod.basic
        assert AuthMethod("oauth") == AuthMethod.oauth

    def test_enum_invalid_value_raises(self) -> None:
        """Verify that invalid string values raise ValueError."""
        with pytest.raises(ValueError):
            AuthMethod("invalid")


class TestCredentialsAuthHeader:
    """Tests for the auth_header() method on Credentials."""

    def test_basic_auth_header_format(self) -> None:
        """Verify auth_header() returns a Basic auth header for basic credentials.

        The header should be 'Basic <base64(username:secret)>' format,
        matching the standard HTTP Basic Authentication scheme.
        """
        import base64

        creds = Credentials(
            username="sa_test_user",
            secret=SecretStr("test_secret"),
            project_id="12345",
            region="us",
        )

        header = creds.auth_header()

        # Verify it starts with "Basic "
        assert header.startswith("Basic ")

        # Decode and verify the payload
        encoded = header.split(" ", 1)[1]
        decoded = base64.b64decode(encoded).decode("utf-8")
        assert decoded == "sa_test_user:test_secret"

    def test_basic_auth_header_is_default(self) -> None:
        """Verify that the default auth method produces a Basic auth header.

        Existing Credentials without explicit auth_method should default
        to Basic authentication to preserve backward compatibility.
        """
        creds = Credentials(
            username="user",
            secret=SecretStr("secret"),
            project_id="123",
            region="us",
        )

        header = creds.auth_header()
        assert header.startswith("Basic ")


class TestCredentialsBasicAuthRegression:
    """Regression tests ensuring existing Basic Auth behavior is unchanged.

    These tests verify that the introduction of AuthMethod and auth_header()
    does not alter existing credential creation, validation, or resolution.
    """

    def test_credentials_still_require_username(self) -> None:
        """Verify that username is still required and validated."""
        with pytest.raises(ValueError, match="cannot be empty"):
            Credentials(
                username="",
                secret=SecretStr("secret"),
                project_id="123",
                region="us",
            )

    def test_credentials_still_require_project_id(self) -> None:
        """Verify that project_id is still required and validated."""
        with pytest.raises(ValueError, match="cannot be empty"):
            Credentials(
                username="user",
                secret=SecretStr("secret"),
                project_id="",
                region="us",
            )

    def test_credentials_still_validate_region(self) -> None:
        """Verify that region validation is unchanged."""
        with pytest.raises(ValueError, match="Region must be one of"):
            Credentials(
                username="user",
                secret=SecretStr("secret"),
                project_id="123",
                region="invalid",
            )

    def test_credentials_still_frozen(self) -> None:
        """Verify that Credentials is still immutable."""
        creds = Credentials(
            username="user",
            secret=SecretStr("secret"),
            project_id="123",
            region="us",
        )
        with pytest.raises(ValidationError):
            creds.username = "other"  # type: ignore[misc]

    def test_credentials_still_redact_secret(self) -> None:
        """Verify that secret is still redacted in repr/str."""
        creds = Credentials(
            username="user",
            secret=SecretStr("my_secret_value"),
            project_id="123",
            region="us",
        )
        assert "my_secret_value" not in repr(creds)
        assert "my_secret_value" not in str(creds)

    def test_region_normalization_unchanged(self) -> None:
        """Verify that region is still normalized to lowercase."""
        creds = Credentials(
            username="user",
            secret=SecretStr("secret"),
            project_id="123",
            region="EU",
        )
        assert creds.region == "eu"


class TestCredentialResolutionRegression:
    """Regression tests for credential resolution with ConfigManager.

    Ensures that the addition of OAuth support doesn't break existing
    environment variable and config file credential resolution.
    """

    def test_env_var_resolution_unchanged(
        self,
        config_manager: ConfigManager,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify that environment variable credential resolution still works.

        The priority order must remain: env vars > named account > default.
        """
        monkeypatch.setenv("MP_USERNAME", "env_user")
        monkeypatch.setenv("MP_SECRET", "env_secret")
        monkeypatch.setenv("MP_PROJECT_ID", "env_project")
        monkeypatch.setenv("MP_REGION", "us")

        creds = config_manager.resolve_credentials()

        assert creds.username == "env_user"
        assert creds.secret.get_secret_value() == "env_secret"
        assert creds.project_id == "env_project"
        assert creds.region == "us"

    def test_config_file_resolution_unchanged(
        self,
        config_manager: ConfigManager,
    ) -> None:
        """Verify that config file credential resolution still works."""
        config_manager.add_account(
            name="test",
            username="file_user",
            secret="file_secret",
            project_id="file_123",
            region="eu",
        )

        creds = config_manager.resolve_credentials()

        assert creds.username == "file_user"
        assert creds.project_id == "file_123"
        assert creds.region == "eu"

    def test_named_account_resolution_unchanged(
        self,
        config_manager: ConfigManager,
    ) -> None:
        """Verify that named account resolution still works."""
        config_manager.add_account(
            name="prod",
            username="prod_user",
            secret="prod_secret",
            project_id="prod_123",
            region="us",
        )
        config_manager.add_account(
            name="staging",
            username="staging_user",
            secret="staging_secret",
            project_id="staging_456",
            region="eu",
        )

        creds = config_manager.resolve_credentials(account="staging")

        assert creds.username == "staging_user"
        assert creds.region == "eu"

    def test_no_credentials_still_raises(
        self,
        config_manager: ConfigManager,
    ) -> None:
        """Verify that missing credentials still raises ConfigError."""
        with pytest.raises(ConfigError, match="No credentials configured"):
            config_manager.resolve_credentials()

    def test_invalid_env_region_still_raises(
        self,
        config_manager: ConfigManager,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify that invalid MP_REGION still raises ConfigError."""
        monkeypatch.setenv("MP_USERNAME", "user")
        monkeypatch.setenv("MP_SECRET", "secret")
        monkeypatch.setenv("MP_PROJECT_ID", "123")
        monkeypatch.setenv("MP_REGION", "invalid")

        with pytest.raises(ConfigError, match="Invalid MP_REGION"):
            config_manager.resolve_credentials()
