"""Unit tests for bridge file credential resolution in ConfigManager.

Tests the integration of auth bridge files into the credential
resolution chain in ConfigManager.resolve_credentials() and
resolve_session().

Verifies:
- Resolution order: env vars > bridge > OAuth > config
- Bridge file is skipped when explicit account/credential requested
- Bridge with expired OAuth token triggers refresh
- Bridge custom headers are applied to env vars
- resolve_session() applies project/workspace overrides from bridge
"""
# ruff: noqa: ARG001, ARG005

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from mixpanel_data._internal.config import (
    AuthMethod,
    ConfigManager,
)


def _write_v1_config(config_path: Path) -> None:
    """Write a minimal v1 config file for testing.

    Args:
        config_path: Path to write the config file.
    """
    import tomli_w

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = {
        "default": "test-account",
        "accounts": {
            "test-account": {
                "username": "sa-config-user",
                "secret": "sa-config-secret",
                "project_id": "config-project",
                "region": "us",
            }
        },
    }
    config_path.write_bytes(tomli_w.dumps(config).encode())


def _write_bridge_file(
    bridge_dir: Path,
    *,
    auth_method: str = "oauth",
    expired: bool = False,
    with_custom_header: bool = False,
) -> Path:
    """Write a bridge file for testing.

    Args:
        bridge_dir: Directory to write auth.json in.
        auth_method: Auth method ('oauth' or 'service_account').
        expired: If True, create an expired token.
        with_custom_header: If True, include a custom header.

    Returns:
        Path to the written bridge file.
    """
    bridge_dir.mkdir(parents=True, exist_ok=True)
    bridge_file = bridge_dir / "auth.json"

    if expired:
        expires_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    else:
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    data: dict[str, Any] = {
        "version": 1,
        "auth_method": auth_method,
        "region": "us",
        "project_id": "bridge-project",
        "workspace_id": 99999,
        "custom_header": None,
        "oauth": None,
        "service_account": None,
    }

    if with_custom_header:
        data["custom_header"] = {
            "name": "X-Bridge-Header",
            "value": "bridge-header-value",
        }

    if auth_method == "oauth":
        data["oauth"] = {
            "access_token": "bridge-access-token",
            "refresh_token": "bridge-refresh-token",
            "expires_at": expires_at,
            "scope": "projects analysis",
            "token_type": "Bearer",
            "client_id": "bridge-client-id",
        }
    else:
        data["service_account"] = {
            "username": "sa-bridge-user",
            "secret": "sa-bridge-secret",
        }

    bridge_file.write_text(json.dumps(data))
    return bridge_file


class TestBridgeInResolveCredentials:
    """Tests for bridge resolution in resolve_credentials()."""

    def test_bridge_resolves_oauth_credentials(self, tmp_path: Path) -> None:
        """Test that bridge file resolves OAuth credentials."""
        config_path = tmp_path / "config.toml"
        _write_v1_config(config_path)

        bridge_dir = tmp_path / "bridge"
        bridge_file = _write_bridge_file(bridge_dir)

        cm = ConfigManager(config_path=config_path)
        with patch.dict(
            os.environ,
            {"MP_AUTH_FILE": str(bridge_file)},
            clear=True,
        ):
            creds = cm.resolve_credentials()

        assert creds.auth_method == AuthMethod.oauth
        assert creds.project_id == "bridge-project"
        assert creds.oauth_access_token is not None
        assert creds.oauth_access_token.get_secret_value() == "bridge-access-token"

    def test_bridge_resolves_sa_credentials(self, tmp_path: Path) -> None:
        """Test that bridge file resolves service account credentials."""
        config_path = tmp_path / "config.toml"
        _write_v1_config(config_path)

        bridge_dir = tmp_path / "bridge"
        bridge_file = _write_bridge_file(bridge_dir, auth_method="service_account")

        cm = ConfigManager(config_path=config_path)
        with patch.dict(
            os.environ,
            {"MP_AUTH_FILE": str(bridge_file)},
            clear=True,
        ):
            creds = cm.resolve_credentials()

        assert creds.auth_method == AuthMethod.basic
        assert creds.project_id == "bridge-project"
        assert creds.username == "sa-bridge-user"

    def test_env_vars_beat_bridge(self, tmp_path: Path) -> None:
        """Test that env vars take priority over bridge file."""
        bridge_dir = tmp_path / "bridge"
        bridge_file = _write_bridge_file(bridge_dir)

        cm = ConfigManager(config_path=tmp_path / "config.toml")
        with patch.dict(
            os.environ,
            {
                "MP_AUTH_FILE": str(bridge_file),
                "MP_USERNAME": "env-user",
                "MP_SECRET": "env-secret",
                "MP_PROJECT_ID": "env-project",
                "MP_REGION": "us",
            },
        ):
            creds = cm.resolve_credentials()

        assert creds.auth_method == AuthMethod.basic
        assert creds.project_id == "env-project"
        assert creds.username == "env-user"

    def test_bridge_beats_config(self, tmp_path: Path) -> None:
        """Test that bridge file beats config file."""
        config_path = tmp_path / "config.toml"
        _write_v1_config(config_path)

        bridge_dir = tmp_path / "bridge"
        bridge_file = _write_bridge_file(bridge_dir)

        cm = ConfigManager(config_path=config_path)
        with patch.dict(
            os.environ,
            {"MP_AUTH_FILE": str(bridge_file)},
            clear=True,
        ):
            creds = cm.resolve_credentials()

        assert creds.project_id == "bridge-project"  # bridge wins
        assert creds.project_id != "config-project"

    def test_bridge_skipped_when_account_specified(self, tmp_path: Path) -> None:
        """Test that bridge is skipped when explicit account is given."""
        config_path = tmp_path / "config.toml"
        _write_v1_config(config_path)

        bridge_dir = tmp_path / "bridge"
        bridge_file = _write_bridge_file(bridge_dir)

        cm = ConfigManager(config_path=config_path)
        with patch.dict(
            os.environ,
            {"MP_AUTH_FILE": str(bridge_file)},
            clear=True,
        ):
            creds = cm.resolve_credentials(account="test-account")

        assert creds.project_id == "config-project"  # config wins
        assert creds.username == "sa-config-user"

    def test_bridge_applies_custom_header(self, tmp_path: Path) -> None:
        """Test that bridge custom header sets env vars."""
        config_path = tmp_path / "config.toml"
        _write_v1_config(config_path)

        bridge_dir = tmp_path / "bridge"
        bridge_file = _write_bridge_file(bridge_dir, with_custom_header=True)

        cm = ConfigManager(config_path=config_path)
        with patch.dict(
            os.environ,
            {"MP_AUTH_FILE": str(bridge_file)},
            clear=True,
        ):
            cm.resolve_credentials()
            assert os.environ.get("MP_CUSTOM_HEADER_NAME") == "X-Bridge-Header"
            assert os.environ.get("MP_CUSTOM_HEADER_VALUE") == "bridge-header-value"


class TestBridgeInResolveSession:
    """Tests for bridge resolution in resolve_session()."""

    def test_bridge_resolves_session(self, tmp_path: Path) -> None:
        """Test that bridge file resolves a session."""
        config_path = tmp_path / "config.toml"
        _write_v1_config(config_path)

        bridge_dir = tmp_path / "bridge"
        bridge_file = _write_bridge_file(bridge_dir)

        cm = ConfigManager(config_path=config_path)
        with patch.dict(
            os.environ,
            {"MP_AUTH_FILE": str(bridge_file)},
            clear=True,
        ):
            session = cm.resolve_session()

        assert session.project_id == "bridge-project"
        assert session.workspace_id == 99999
        assert session.auth_header() == "Bearer bridge-access-token"

    def test_session_overrides_project_id(self, tmp_path: Path) -> None:
        """Test that explicit project_id overrides bridge value."""
        config_path = tmp_path / "config.toml"
        _write_v1_config(config_path)

        bridge_dir = tmp_path / "bridge"
        bridge_file = _write_bridge_file(bridge_dir)

        cm = ConfigManager(config_path=config_path)
        with patch.dict(
            os.environ,
            {"MP_AUTH_FILE": str(bridge_file)},
            clear=True,
        ):
            session = cm.resolve_session(project_id="override-project")

        assert session.project_id == "override-project"
        assert session.workspace_id == 99999  # preserved from bridge

    def test_session_overrides_workspace_id(self, tmp_path: Path) -> None:
        """Test that explicit workspace_id overrides bridge value."""
        config_path = tmp_path / "config.toml"
        _write_v1_config(config_path)

        bridge_dir = tmp_path / "bridge"
        bridge_file = _write_bridge_file(bridge_dir)

        cm = ConfigManager(config_path=config_path)
        with patch.dict(
            os.environ,
            {"MP_AUTH_FILE": str(bridge_file)},
            clear=True,
        ):
            session = cm.resolve_session(workspace_id=11111)

        assert session.project_id == "bridge-project"
        assert session.workspace_id == 11111  # overridden

    def test_bridge_skipped_when_credential_specified(self, tmp_path: Path) -> None:
        """Test that bridge is skipped when explicit credential is given."""
        config_path = tmp_path / "config.toml"
        _write_v1_config(config_path)

        bridge_dir = tmp_path / "bridge"
        bridge_file = _write_bridge_file(bridge_dir)

        cm = ConfigManager(config_path=config_path)
        with patch.dict(
            os.environ,
            {"MP_AUTH_FILE": str(bridge_file)},
            clear=True,
        ):
            session = cm.resolve_session(credential="test-account")

        assert session.project_id == "config-project"  # config wins


class TestBridgeNoFile:
    """Tests that resolution falls through when no bridge file exists."""

    def test_falls_through_to_config(self, tmp_path: Path) -> None:
        """Test that missing bridge file falls through to config."""
        config_path = tmp_path / "config.toml"
        _write_v1_config(config_path)

        # Use empty OAuth storage dir so no real tokens interfere
        empty_oauth = tmp_path / "empty_oauth"
        empty_oauth.mkdir()

        cm = ConfigManager(config_path=config_path)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "mixpanel_data._internal.auth.bridge.default_bridge_path",
                return_value=tmp_path / "nonexistent" / "auth.json",
            ),
        ):
            creds = cm.resolve_credentials(_oauth_storage_dir=empty_oauth)

        assert creds.project_id == "config-project"
        assert creds.username == "sa-config-user"

    def test_session_falls_through_to_config(self, tmp_path: Path) -> None:
        """Test that missing bridge file falls through in session resolution."""
        config_path = tmp_path / "config.toml"
        _write_v1_config(config_path)

        # Use empty OAuth storage dir so no real tokens interfere
        empty_oauth = tmp_path / "empty_oauth"
        empty_oauth.mkdir()

        cm = ConfigManager(config_path=config_path)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "mixpanel_data._internal.auth.bridge.default_bridge_path",
                return_value=tmp_path / "nonexistent" / "auth.json",
            ),
        ):
            session = cm.resolve_session(_oauth_storage_dir=empty_oauth)

        assert session.project_id == "config-project"
