"""Unit tests for OAuth credential resolution in ConfigManager (T033).

Tests the extended credential resolution path that integrates OAuth tokens
from OAuthStorage into ConfigManager.resolve_credentials().

Verifies:
- Resolution order: env vars > OAuth tokens > named account > default
- OAuth tokens are correctly loaded and converted to Credentials
- Auth method selection: env vars produce basic, stored tokens produce oauth
- Partial env var mode (MP_PROJECT_ID + MP_REGION without username/secret)
- Backward compatibility: all existing Basic Auth behavior unchanged
"""
# ruff: noqa: ARG001, ARG005

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import SecretStr

from mixpanel_data._internal.auth.storage import OAuthStorage
from mixpanel_data._internal.auth.token import OAuthTokens
from mixpanel_data._internal.config import (
    AuthMethod,
    ConfigManager,
)
from mixpanel_data.exceptions import ConfigError


def _make_valid_tokens(
    project_id: str = "12345",
    access_token: str = "test-access-token",
) -> OAuthTokens:
    """Create a non-expired OAuthTokens for testing.

    Args:
        project_id: Project ID to embed in the tokens.
        access_token: The access token value.

    Returns:
        A valid, non-expired OAuthTokens instance.
    """
    return OAuthTokens(
        access_token=SecretStr(access_token),
        refresh_token=SecretStr("test-refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scope="read:project",
        token_type="Bearer",
        project_id=project_id,
    )


def _make_expired_tokens(
    project_id: str = "12345",
) -> OAuthTokens:
    """Create an expired OAuthTokens for testing.

    Args:
        project_id: Project ID to embed in the tokens.

    Returns:
        An expired OAuthTokens instance.
    """
    return OAuthTokens(
        access_token=SecretStr("expired-token"),
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        scope="read:project",
        token_type="Bearer",
        project_id=project_id,
    )


class TestEnvVarsStillResolveToBaiscAuth:
    """Regression: env vars always produce Basic Auth credentials."""

    def test_env_vars_produce_basic_auth(
        self,
        config_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        temp_dir: Path,
    ) -> None:
        """When all env vars are set, resolve_credentials returns Basic Auth.

        Even if OAuth tokens are stored, env vars always win.
        """
        monkeypatch.setenv("MP_USERNAME", "env_user")
        monkeypatch.setenv("MP_SECRET", "env_secret")
        monkeypatch.setenv("MP_PROJECT_ID", "99999")
        monkeypatch.setenv("MP_REGION", "us")

        # Store OAuth tokens to verify they are NOT used
        oauth_dir = temp_dir / "oauth"
        storage = OAuthStorage(storage_dir=oauth_dir)
        storage.save_tokens(_make_valid_tokens(project_id="99999"), region="us")

        cm = ConfigManager(config_path=config_path)
        creds = cm.resolve_credentials()

        assert creds.auth_method == AuthMethod.basic
        assert creds.username == "env_user"
        assert creds.secret.get_secret_value() == "env_secret"
        assert creds.oauth_access_token is None

    def test_env_vars_take_precedence_over_oauth_and_config(
        self,
        config_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        temp_dir: Path,
    ) -> None:
        """Env vars > OAuth tokens > config file accounts."""
        monkeypatch.setenv("MP_USERNAME", "env_user")
        monkeypatch.setenv("MP_SECRET", "env_secret")
        monkeypatch.setenv("MP_PROJECT_ID", "99999")
        monkeypatch.setenv("MP_REGION", "eu")

        # Store OAuth tokens and config account
        oauth_dir = temp_dir / "oauth"
        storage = OAuthStorage(storage_dir=oauth_dir)
        storage.save_tokens(_make_valid_tokens(project_id="99999"), region="eu")

        cm = ConfigManager(config_path=config_path)
        cm.add_account(
            name="fallback",
            username="file_user",
            secret="file_secret",
            project_id="file_123",
            region="eu",
        )

        creds = cm.resolve_credentials()
        assert creds.auth_method == AuthMethod.basic
        assert creds.username == "env_user"


class TestOAuthTokenResolution:
    """Tests for OAuth token resolution in ConfigManager."""

    def test_oauth_tokens_resolve_when_no_env_vars(
        self,
        config_path: Path,
        temp_dir: Path,
    ) -> None:
        """When no env vars, stored OAuth tokens should resolve to oauth Credentials."""
        oauth_dir = temp_dir / "oauth"
        storage = OAuthStorage(storage_dir=oauth_dir)
        tokens = _make_valid_tokens(project_id="12345")
        storage.save_tokens(tokens, region="us")

        # Config must have an account to get project_id and region
        cm = ConfigManager(config_path=config_path)
        cm.add_account(
            name="default",
            username="sa_user",
            secret="sa_secret",
            project_id="12345",
            region="us",
        )

        creds = cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

        assert creds.auth_method == AuthMethod.oauth
        assert creds.oauth_access_token is not None
        assert creds.oauth_access_token.get_secret_value() == "test-access-token"
        assert creds.project_id == "12345"
        assert creds.region == "us"

    def test_oauth_tokens_use_project_id_from_token(
        self,
        config_path: Path,
        temp_dir: Path,
    ) -> None:
        """OAuth tokens with project_id should use that project_id."""
        oauth_dir = temp_dir / "oauth"
        storage = OAuthStorage(storage_dir=oauth_dir)
        tokens = _make_valid_tokens(project_id="token-pid")
        storage.save_tokens(tokens, region="us")

        cm = ConfigManager(config_path=config_path)
        cm.add_account(
            name="default",
            username="sa_user",
            secret="sa_secret",
            project_id="config-pid",
            region="us",
        )

        creds = cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

        assert creds.auth_method == AuthMethod.oauth
        assert creds.project_id == "token-pid"

    def test_expired_oauth_tokens_skip_to_config(
        self,
        config_path: Path,
        temp_dir: Path,
    ) -> None:
        """Expired OAuth tokens should be skipped; fall through to config."""
        oauth_dir = temp_dir / "oauth"
        storage = OAuthStorage(storage_dir=oauth_dir)
        storage.save_tokens(_make_expired_tokens(project_id="12345"), region="us")

        cm = ConfigManager(config_path=config_path)
        cm.add_account(
            name="default",
            username="config_user",
            secret="config_secret",
            project_id="12345",
            region="us",
        )

        creds = cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

        assert creds.auth_method == AuthMethod.basic
        assert creds.username == "config_user"

    def test_no_oauth_tokens_falls_through_to_config(
        self,
        config_path: Path,
        temp_dir: Path,
    ) -> None:
        """When no OAuth tokens stored, resolution falls through to config file."""
        oauth_dir = temp_dir / "oauth_empty"  # empty dir, no tokens

        cm = ConfigManager(config_path=config_path)
        cm.add_account(
            name="default",
            username="config_user",
            secret="config_secret",
            project_id="12345",
            region="us",
        )

        creds = cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

        assert creds.auth_method == AuthMethod.basic
        assert creds.username == "config_user"

    def test_oauth_with_partial_env_vars(
        self,
        config_path: Path,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """MP_PROJECT_ID and MP_REGION set without username/secret uses those for OAuth lookup."""
        oauth_dir = temp_dir / "oauth"
        storage = OAuthStorage(storage_dir=oauth_dir)
        tokens = _make_valid_tokens(project_id="env-pid")
        storage.save_tokens(tokens, region="eu")

        monkeypatch.setenv("MP_PROJECT_ID", "env-pid")
        monkeypatch.setenv("MP_REGION", "eu")
        # MP_USERNAME and MP_SECRET NOT set

        cm = ConfigManager(config_path=config_path)
        creds = cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

        assert creds.auth_method == AuthMethod.oauth
        assert creds.project_id == "env-pid"
        assert creds.region == "eu"

    def test_no_oauth_no_config_still_raises(
        self,
        config_path: Path,
        temp_dir: Path,
    ) -> None:
        """No env vars, no OAuth, no config should still raise ConfigError."""
        oauth_dir = temp_dir / "oauth_empty"

        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="No credentials configured"):
            cm.resolve_credentials(_oauth_storage_dir=oauth_dir)


class TestResolutionOrder:
    """Tests for the full resolution priority chain."""

    def test_resolution_order_env_over_oauth(
        self,
        config_path: Path,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Env vars > OAuth tokens."""
        monkeypatch.setenv("MP_USERNAME", "env_user")
        monkeypatch.setenv("MP_SECRET", "env_secret")
        monkeypatch.setenv("MP_PROJECT_ID", "12345")
        monkeypatch.setenv("MP_REGION", "us")

        oauth_dir = temp_dir / "oauth"
        storage = OAuthStorage(storage_dir=oauth_dir)
        storage.save_tokens(_make_valid_tokens(), region="us")

        cm = ConfigManager(config_path=config_path)
        creds = cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

        assert creds.auth_method == AuthMethod.basic
        assert creds.username == "env_user"

    def test_resolution_order_oauth_over_config(
        self,
        config_path: Path,
        temp_dir: Path,
    ) -> None:
        """OAuth tokens > named/default account from config."""
        oauth_dir = temp_dir / "oauth"
        storage = OAuthStorage(storage_dir=oauth_dir)
        storage.save_tokens(_make_valid_tokens(project_id="12345"), region="us")

        cm = ConfigManager(config_path=config_path)
        cm.add_account(
            name="default",
            username="config_user",
            secret="config_secret",
            project_id="12345",
            region="us",
        )

        creds = cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

        assert creds.auth_method == AuthMethod.oauth
        assert creds.oauth_access_token is not None

    def test_named_account_bypasses_oauth(
        self,
        config_path: Path,
        temp_dir: Path,
    ) -> None:
        """When an explicit named account is requested, OAuth is NOT checked."""
        oauth_dir = temp_dir / "oauth"
        storage = OAuthStorage(storage_dir=oauth_dir)
        storage.save_tokens(_make_valid_tokens(project_id="12345"), region="us")

        cm = ConfigManager(config_path=config_path)
        cm.add_account(
            name="prod",
            username="prod_user",
            secret="prod_secret",
            project_id="12345",
            region="us",
        )

        creds = cm.resolve_credentials(account="prod", _oauth_storage_dir=oauth_dir)

        # Named account requested explicitly → should get basic auth
        assert creds.auth_method == AuthMethod.basic
        assert creds.username == "prod_user"
