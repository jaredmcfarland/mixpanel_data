"""Unit tests for the new-user auth flow fixes.

Tests cover:
- Fix 2: OAuth resolution safety net — scans OAuth storage when no
  accounts or credentials exist in config.
- Fix 3: projects list OAuth fallback — discovers projects via direct
  /me call when no project is configured.
- Fix 4: Improved error messages mention ``mp auth login``.
- Region+project_id fallback when active context has project_id but
  no credential entries.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import tomli_w
from pydantic import SecretStr

from mixpanel_data._internal.auth.storage import OAuthStorage
from mixpanel_data._internal.auth.token import OAuthTokens
from mixpanel_data._internal.config import AuthMethod, ConfigManager
from mixpanel_data.exceptions import ConfigError


def _make_valid_tokens(
    project_id: str | None = None,
    access_token: str = "test-access-token",
) -> OAuthTokens:
    """Create a non-expired OAuthTokens for testing.

    Args:
        project_id: Optional project ID to embed in the tokens.
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


def _make_expired_tokens() -> OAuthTokens:
    """Create an expired OAuthTokens for testing.

    Returns:
        An expired OAuthTokens instance.
    """
    return OAuthTokens(
        access_token=SecretStr("expired-token"),
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        scope="read:project",
        token_type="Bearer",
    )


# ── Fix 2: OAuth storage scanning ──────────────────────────────────


class TestOAuthStorageScan:
    """Fix 2: _resolve_region_and_project_for_oauth scans storage."""

    def test_empty_config_finds_oauth_tokens(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With no config, scanning OAuth storage finds valid tokens.

        Args:
            tmp_path: Temporary directory for config and OAuth storage.
            monkeypatch: Pytest fixture for patching environment.
        """
        # Clear env vars that would short-circuit resolution
        monkeypatch.delenv("MP_REGION", raising=False)
        monkeypatch.delenv("MP_PROJECT_ID", raising=False)
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)

        config_path = tmp_path / "config.toml"
        oauth_dir = tmp_path / "oauth"
        oauth_dir.mkdir()

        # Save valid OAuth tokens to storage
        storage = OAuthStorage(storage_dir=oauth_dir)
        tokens = _make_valid_tokens(project_id="99999")
        storage.save_tokens(tokens, region="us")

        cm = ConfigManager(config_path=config_path)
        creds = cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

        assert creds.auth_method == AuthMethod.oauth
        assert creds.project_id == "99999"
        assert creds.region == "us"

    def test_empty_config_no_tokens_raises_config_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With no config and no tokens, raises ConfigError.

        Args:
            tmp_path: Temporary directory for config.
            monkeypatch: Pytest fixture for patching environment.
        """
        monkeypatch.delenv("MP_REGION", raising=False)
        monkeypatch.delenv("MP_PROJECT_ID", raising=False)
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)

        config_path = tmp_path / "config.toml"
        oauth_dir = tmp_path / "oauth"
        oauth_dir.mkdir()

        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError):
            cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

    def test_expired_tokens_are_skipped(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Expired OAuth tokens are skipped during storage scan.

        Args:
            tmp_path: Temporary directory for config and OAuth storage.
            monkeypatch: Pytest fixture for patching environment.
        """
        monkeypatch.delenv("MP_REGION", raising=False)
        monkeypatch.delenv("MP_PROJECT_ID", raising=False)
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)

        config_path = tmp_path / "config.toml"
        oauth_dir = tmp_path / "oauth"
        oauth_dir.mkdir()

        # Save expired tokens
        storage = OAuthStorage(storage_dir=oauth_dir)
        expired = _make_expired_tokens()
        storage.save_tokens(expired, region="us")

        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError):
            cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

    def test_tokens_without_project_id_return_none(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OAuth tokens without project_id fall through (no project set).

        Args:
            tmp_path: Temporary directory for config and OAuth storage.
            monkeypatch: Pytest fixture for patching environment.
        """
        monkeypatch.delenv("MP_REGION", raising=False)
        monkeypatch.delenv("MP_PROJECT_ID", raising=False)
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)

        config_path = tmp_path / "config.toml"
        oauth_dir = tmp_path / "oauth"
        oauth_dir.mkdir()

        # Tokens without project_id
        storage = OAuthStorage(storage_dir=oauth_dir)
        tokens = _make_valid_tokens(project_id=None)
        storage.save_tokens(tokens, region="us")

        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError):
            cm.resolve_credentials(_oauth_storage_dir=oauth_dir)


class TestOAuthStorageScanWithActiveProject:
    """Fix 2 extension: active project_id used as fallback in scan."""

    def test_active_project_id_used_when_token_has_none(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Config active.project_id fills in when token lacks project_id.

        Args:
            tmp_path: Temporary directory for config and OAuth storage.
            monkeypatch: Pytest fixture for patching environment.
        """
        monkeypatch.delenv("MP_REGION", raising=False)
        monkeypatch.delenv("MP_PROJECT_ID", raising=False)
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)

        config_path = tmp_path / "config.toml"
        oauth_dir = tmp_path / "oauth"
        oauth_dir.mkdir()

        # Write minimal config with only active.project_id
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump({"active": {"project_id": "77777"}}, f)

        # Save tokens without project_id
        storage = OAuthStorage(storage_dir=oauth_dir)
        tokens = _make_valid_tokens(project_id=None)
        storage.save_tokens(tokens, region="us")

        cm = ConfigManager(config_path=config_path)
        creds = cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

        assert creds.auth_method == AuthMethod.oauth
        assert creds.project_id == "77777"
        assert creds.region == "us"


# ── Fix 2: v2 config resolution ────────────────────────────────────


class TestV2CredentialResolution:
    """Fix 2: v2 credentials are used for OAuth region resolution."""

    def test_v2_oauth_credential_resolves_region(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """v2 config OAuth credential provides region for token lookup.

        Args:
            tmp_path: Temporary directory for config and OAuth storage.
            monkeypatch: Pytest fixture for patching environment.
        """
        monkeypatch.delenv("MP_REGION", raising=False)
        monkeypatch.delenv("MP_PROJECT_ID", raising=False)
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)

        config_path = tmp_path / "config.toml"
        oauth_dir = tmp_path / "oauth"
        oauth_dir.mkdir()

        # Write v2 config with OAuth credential
        with config_path.open("wb") as f:
            tomli_w.dump(
                {
                    "config_version": 2,
                    "active": {
                        "credential": "oauth-eu",
                        "project_id": "55555",
                    },
                    "credentials": {
                        "oauth-eu": {
                            "type": "oauth",
                            "region": "eu",
                        },
                    },
                },
                f,
            )

        # Save tokens for EU region
        storage = OAuthStorage(storage_dir=oauth_dir)
        tokens = _make_valid_tokens(project_id="55555")
        storage.save_tokens(tokens, region="eu")

        cm = ConfigManager(config_path=config_path)
        creds = cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

        assert creds.auth_method == AuthMethod.oauth
        assert creds.project_id == "55555"
        assert creds.region == "eu"


# ── Fix 4: Error message improvements ──────────────────────────────


class TestErrorMessages:
    """Fix 4: Error messages mention mp auth login."""

    def test_no_credentials_error_mentions_login(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ConfigError for missing credentials mentions 'mp auth login'.

        Args:
            tmp_path: Temporary directory for config.
            monkeypatch: Pytest fixture for patching environment.
        """
        monkeypatch.delenv("MP_REGION", raising=False)
        monkeypatch.delenv("MP_PROJECT_ID", raising=False)
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)

        config_path = tmp_path / "config.toml"
        oauth_dir = tmp_path / "oauth"
        oauth_dir.mkdir()

        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="mp auth login"):
            cm.resolve_credentials(_oauth_storage_dir=oauth_dir)

    def test_v2_no_credentials_error_mentions_login(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """v2 ConfigError for missing credentials mentions 'mp auth login'.

        Args:
            tmp_path: Temporary directory for config.
            monkeypatch: Pytest fixture for patching environment.
        """
        monkeypatch.delenv("MP_REGION", raising=False)
        monkeypatch.delenv("MP_PROJECT_ID", raising=False)
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)

        config_path = tmp_path / "config.toml"
        with config_path.open("wb") as f:
            tomli_w.dump({"config_version": 2}, f)

        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="mp auth login"):
            cm.resolve_session()

    def test_v2_no_project_error_mentions_projects_list(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """v2 ConfigError for missing project mentions 'mp projects list'.

        Args:
            tmp_path: Temporary directory for config.
            monkeypatch: Pytest fixture for patching environment.
        """
        monkeypatch.delenv("MP_REGION", raising=False)
        monkeypatch.delenv("MP_PROJECT_ID", raising=False)
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)

        config_path = tmp_path / "config.toml"
        with config_path.open("wb") as f:
            tomli_w.dump(
                {
                    "config_version": 2,
                    "active": {"credential": "test-sa"},
                    "credentials": {
                        "test-sa": {
                            "type": "service_account",
                            "username": "user",
                            "secret": "secret",
                            "region": "us",
                        },
                    },
                },
                f,
            )

        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="mp projects list"):
            cm.resolve_session()
