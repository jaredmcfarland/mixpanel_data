"""Unit tests for auth bridge module (Cowork credential bridge).

Tests the AuthBridgeFile model, Cowork detection, bridge file discovery,
credential conversion, custom header application, and token refresh.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr, ValidationError

from mixpanel_data._internal.auth.bridge import (
    AuthBridgeFile,
    BridgeCustomHeader,
    BridgeOAuth,
    BridgeServiceAccount,
    apply_bridge_custom_header,
    bridge_to_credentials,
    bridge_to_resolved_session,
    detect_cowork,
    find_bridge_file,
    load_bridge_file,
    refresh_bridge_token,
    write_bridge_file,
)
from mixpanel_data._internal.auth_credential import CredentialType
from mixpanel_data._internal.config import AuthMethod


def _utcnow() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def _make_oauth_bridge(
    *,
    expired: bool = False,
    with_custom_header: bool = False,
    workspace_id: int | None = 67890,
) -> AuthBridgeFile:
    """Create an OAuth AuthBridgeFile for testing.

    Args:
        expired: If True, set token expiry in the past.
        with_custom_header: If True, include a custom header.
        workspace_id: Optional workspace ID.

    Returns:
        Configured AuthBridgeFile instance.
    """
    if expired:
        expires_at = _utcnow() - timedelta(hours=1)
    else:
        expires_at = _utcnow() + timedelta(hours=1)

    custom_header = None
    if with_custom_header:
        custom_header = BridgeCustomHeader(
            name="X-Test-Header",
            value=SecretStr("test-header-value"),
        )

    return AuthBridgeFile(
        version=1,
        auth_method="oauth",
        region="us",
        project_id="12345",
        workspace_id=workspace_id,
        custom_header=custom_header,
        oauth=BridgeOAuth(
            access_token=SecretStr("access_abc123"),
            refresh_token=SecretStr("refresh_xyz789"),
            expires_at=expires_at,
            scope="projects analysis events",
            token_type="Bearer",
            client_id="client_123",
        ),
    )


def _make_sa_bridge(
    *,
    with_custom_header: bool = False,
) -> AuthBridgeFile:
    """Create a service account AuthBridgeFile for testing.

    Args:
        with_custom_header: If True, include a custom header.

    Returns:
        Configured AuthBridgeFile instance.
    """
    custom_header = None
    if with_custom_header:
        custom_header = BridgeCustomHeader(
            name="X-Test-Header",
            value=SecretStr("test-header-value"),
        )

    return AuthBridgeFile(
        version=1,
        auth_method="service_account",
        region="eu",
        project_id="67890",
        workspace_id=None,
        custom_header=custom_header,
        service_account=BridgeServiceAccount(
            username="sa-user.abc.mp-service-account",
            secret=SecretStr("sa-secret-value"),
        ),
    )


def _bridge_to_dict(bridge: AuthBridgeFile) -> dict[str, Any]:
    """Serialize an AuthBridgeFile to a JSON-compatible dict.

    Args:
        bridge: The bridge file to serialize.

    Returns:
        JSON-serializable dictionary.
    """
    d: dict[str, Any] = {
        "version": bridge.version,
        "auth_method": bridge.auth_method,
        "region": bridge.region,
        "project_id": bridge.project_id,
        "workspace_id": bridge.workspace_id,
        "custom_header": None,
        "oauth": None,
        "service_account": None,
    }
    if bridge.custom_header is not None:
        d["custom_header"] = {
            "name": bridge.custom_header.name,
            "value": bridge.custom_header.value.get_secret_value(),
        }
    if bridge.oauth is not None:
        d["oauth"] = {
            "access_token": bridge.oauth.access_token.get_secret_value(),
            "refresh_token": bridge.oauth.refresh_token.get_secret_value()
            if bridge.oauth.refresh_token
            else None,
            "expires_at": bridge.oauth.expires_at.isoformat(),
            "scope": bridge.oauth.scope,
            "token_type": bridge.oauth.token_type,
            "client_id": bridge.oauth.client_id,
        }
    if bridge.service_account is not None:
        d["service_account"] = {
            "username": bridge.service_account.username,
            "secret": bridge.service_account.secret.get_secret_value(),
        }
    return d


class TestAuthBridgeFileModel:
    """Tests for AuthBridgeFile Pydantic model validation."""

    def test_valid_oauth_bridge(self) -> None:
        """Test creating a valid OAuth bridge file."""
        bridge = _make_oauth_bridge()
        assert bridge.auth_method == "oauth"
        assert bridge.region == "us"
        assert bridge.project_id == "12345"
        assert bridge.workspace_id == 67890
        assert bridge.oauth is not None
        assert bridge.service_account is None

    def test_valid_sa_bridge(self) -> None:
        """Test creating a valid service account bridge file."""
        bridge = _make_sa_bridge()
        assert bridge.auth_method == "service_account"
        assert bridge.region == "eu"
        assert bridge.project_id == "67890"
        assert bridge.service_account is not None
        assert bridge.oauth is None

    def test_with_custom_header(self) -> None:
        """Test bridge file with custom header."""
        bridge = _make_oauth_bridge(with_custom_header=True)
        assert bridge.custom_header is not None
        assert bridge.custom_header.name == "X-Test-Header"
        assert bridge.custom_header.value.get_secret_value() == "test-header-value"

    def test_without_workspace_id(self) -> None:
        """Test bridge file without workspace_id."""
        bridge = _make_oauth_bridge(workspace_id=None)
        assert bridge.workspace_id is None

    def test_invalid_region(self) -> None:
        """Test that invalid region is rejected."""
        with pytest.raises((ValueError, ValidationError)):
            AuthBridgeFile(
                version=1,
                auth_method="oauth",
                region="invalid",
                project_id="123",
                oauth=BridgeOAuth(
                    access_token=SecretStr("token"),
                    refresh_token=None,
                    expires_at=_utcnow() + timedelta(hours=1),
                    scope="projects",
                    token_type="Bearer",
                    client_id="client_1",
                ),
            )

    def test_invalid_auth_method(self) -> None:
        """Test that invalid auth_method is rejected."""
        with pytest.raises((ValueError, ValidationError)):
            AuthBridgeFile(
                version=1,
                auth_method="invalid",
                region="us",
                project_id="123",
            )

    def test_version_must_be_1(self) -> None:
        """Test that version must be 1."""
        with pytest.raises((ValueError, ValidationError)):
            _bridge = AuthBridgeFile(
                version=2,
                auth_method="oauth",
                region="us",
                project_id="123",
                oauth=BridgeOAuth(
                    access_token=SecretStr("token"),
                    refresh_token=None,
                    expires_at=_utcnow() + timedelta(hours=1),
                    scope="projects",
                    token_type="Bearer",
                    client_id="client_1",
                ),
            )


class TestDetectCowork:
    """Tests for detect_cowork() function."""

    def test_detects_cowork_via_sessions_dir(self, tmp_path: Path) -> None:
        """Test detection via /sessions/ directory."""
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        with patch(
            "mixpanel_data._internal.auth.bridge._COWORK_SESSIONS_PATH",
            sessions_dir,
        ):
            assert detect_cowork() is True

    def test_detects_cowork_via_env_var(self) -> None:
        """Test detection via CLAUDE_COWORK env var."""
        with patch.dict(os.environ, {"CLAUDE_COWORK": "1"}):
            assert detect_cowork() is True

    def test_not_cowork_when_neither(self) -> None:
        """Test returns False when not in Cowork."""
        with (
            patch(
                "mixpanel_data._internal.auth.bridge._COWORK_SESSIONS_PATH",
                Path("/nonexistent/sessions"),
            ),
            patch.dict(os.environ, {}, clear=True),
        ):
            # Remove CLAUDE_COWORK if present
            os.environ.pop("CLAUDE_COWORK", None)
            assert detect_cowork() is False


class TestFindBridgeFile:
    """Tests for find_bridge_file() function."""

    def test_explicit_mp_auth_file_env_var(self, tmp_path: Path) -> None:
        """Test MP_AUTH_FILE env var takes highest priority."""
        auth_file = tmp_path / "custom_auth.json"
        auth_file.write_text("{}")
        with patch.dict(os.environ, {"MP_AUTH_FILE": str(auth_file)}):
            result = find_bridge_file()
            assert result == auth_file

    def test_mp_auth_file_missing_returns_none(self, tmp_path: Path) -> None:
        """Test MP_AUTH_FILE pointing to nonexistent file returns None."""
        with patch.dict(os.environ, {"MP_AUTH_FILE": str(tmp_path / "nope.json")}):
            result = find_bridge_file()
            assert result is None

    def test_default_claude_dir(self, tmp_path: Path) -> None:
        """Test finding bridge file at ~/.claude/mixpanel/auth.json."""
        bridge_dir = tmp_path / ".claude" / "mixpanel"
        bridge_dir.mkdir(parents=True)
        auth_file = bridge_dir / "auth.json"
        auth_file.write_text("{}")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "mixpanel_data._internal.auth.bridge._default_bridge_path",
                return_value=auth_file,
            ),
        ):
            os.environ.pop("MP_AUTH_FILE", None)
            result = find_bridge_file()
            assert result == auth_file

    def test_cowork_mount_path(self, tmp_path: Path) -> None:
        """Test finding bridge file at ~/mnt/{folder}/mixpanel_auth.json."""
        # Simulate Cowork mount: ~/mnt/workspace/mixpanel_auth.json
        workspace_dir = tmp_path / "mnt" / "my-project"
        workspace_dir.mkdir(parents=True)
        auth_file = workspace_dir / "mixpanel_auth.json"
        auth_file.write_text("{}")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "mixpanel_data._internal.auth.bridge._default_bridge_path",
                return_value=tmp_path / "nonexistent" / "auth.json",
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("pathlib.Path.cwd", return_value=tmp_path / "fakecwd"),
        ):
            os.environ.pop("MP_AUTH_FILE", None)
            result = find_bridge_file()
            assert result == auth_file

    def test_no_bridge_file_returns_none(self, tmp_path: Path) -> None:
        """Test returns None when no bridge file exists."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "mixpanel_data._internal.auth.bridge._default_bridge_path",
                return_value=tmp_path / "nonexistent" / "auth.json",
            ),
            patch("pathlib.Path.home", return_value=tmp_path / "fakehome"),
            patch("pathlib.Path.cwd", return_value=tmp_path / "fakecwd"),
        ):
            os.environ.pop("MP_AUTH_FILE", None)
            result = find_bridge_file()
            assert result is None


class TestLoadBridgeFile:
    """Tests for load_bridge_file() function."""

    def test_load_valid_oauth_bridge(self, tmp_path: Path) -> None:
        """Test loading a valid OAuth bridge file."""
        bridge = _make_oauth_bridge()
        bridge_file = tmp_path / "auth.json"
        bridge_file.write_text(json.dumps(_bridge_to_dict(bridge)))

        loaded = load_bridge_file(bridge_file)
        assert loaded is not None
        assert loaded.auth_method == "oauth"
        assert loaded.project_id == "12345"
        assert loaded.oauth is not None
        assert loaded.oauth.access_token.get_secret_value() == "access_abc123"

    def test_load_valid_sa_bridge(self, tmp_path: Path) -> None:
        """Test loading a valid service account bridge file."""
        bridge = _make_sa_bridge()
        bridge_file = tmp_path / "auth.json"
        bridge_file.write_text(json.dumps(_bridge_to_dict(bridge)))

        loaded = load_bridge_file(bridge_file)
        assert loaded is not None
        assert loaded.auth_method == "service_account"
        assert loaded.service_account is not None
        assert loaded.service_account.username == "sa-user.abc.mp-service-account"

    def test_load_with_custom_header(self, tmp_path: Path) -> None:
        """Test loading bridge file with custom header."""
        bridge = _make_oauth_bridge(with_custom_header=True)
        bridge_file = tmp_path / "auth.json"
        bridge_file.write_text(json.dumps(_bridge_to_dict(bridge)))

        loaded = load_bridge_file(bridge_file)
        assert loaded is not None
        assert loaded.custom_header is not None
        assert loaded.custom_header.name == "X-Test-Header"

    def test_load_nonexistent_returns_none(self) -> None:
        """Test loading nonexistent file returns None."""
        result = load_bridge_file(Path("/nonexistent/auth.json"))
        assert result is None

    def test_load_none_path_returns_none(self, tmp_path: Path) -> None:
        """Test loading with None path and no bridge file returns None."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "mixpanel_data._internal.auth.bridge._default_bridge_path",
                return_value=tmp_path / "nonexistent" / "auth.json",
            ),
            patch("pathlib.Path.home", return_value=tmp_path),
        ):
            result = load_bridge_file(None)
            assert result is None

    def test_load_invalid_json_returns_none(self, tmp_path: Path) -> None:
        """Test loading invalid JSON returns None."""
        bridge_file = tmp_path / "auth.json"
        bridge_file.write_text("not json")

        result = load_bridge_file(bridge_file)
        assert result is None

    def test_load_invalid_schema_returns_none(self, tmp_path: Path) -> None:
        """Test loading valid JSON with invalid schema returns None."""
        bridge_file = tmp_path / "auth.json"
        bridge_file.write_text(json.dumps({"version": 1, "bad": "data"}))

        result = load_bridge_file(bridge_file)
        assert result is None


class TestWriteBridgeFile:
    """Tests for write_bridge_file() function."""

    def test_write_creates_file(self, tmp_path: Path) -> None:
        """Test writing a bridge file creates the file."""
        bridge = _make_oauth_bridge()
        bridge_file = tmp_path / "mixpanel" / "auth.json"

        write_bridge_file(bridge, bridge_file)

        assert bridge_file.exists()
        loaded = json.loads(bridge_file.read_text())
        assert loaded["auth_method"] == "oauth"
        assert loaded["project_id"] == "12345"

    def test_write_sets_directory_permissions(self, tmp_path: Path) -> None:
        """Test that directory permissions are set to 0o700."""
        bridge = _make_oauth_bridge()
        bridge_dir = tmp_path / "mixpanel"
        bridge_file = bridge_dir / "auth.json"

        write_bridge_file(bridge, bridge_file)

        dir_mode = bridge_dir.stat().st_mode & 0o777
        assert dir_mode == 0o700

    def test_write_sets_file_permissions(self, tmp_path: Path) -> None:
        """Test that file permissions are set to 0o600."""
        bridge = _make_oauth_bridge()
        bridge_file = tmp_path / "auth.json"

        write_bridge_file(bridge, bridge_file)

        file_mode = bridge_file.stat().st_mode & 0o777
        assert file_mode == 0o600

    def test_write_overwrites_existing(self, tmp_path: Path) -> None:
        """Test writing overwrites an existing bridge file."""
        bridge_file = tmp_path / "auth.json"
        bridge_file.write_text('{"old": "data"}')

        bridge = _make_sa_bridge()
        write_bridge_file(bridge, bridge_file)

        loaded = json.loads(bridge_file.read_text())
        assert loaded["auth_method"] == "service_account"


class TestBridgeToCredentials:
    """Tests for bridge_to_credentials() conversion."""

    def test_oauth_bridge_to_credentials(self) -> None:
        """Test converting OAuth bridge to Credentials."""
        bridge = _make_oauth_bridge()
        creds = bridge_to_credentials(bridge)

        assert creds.auth_method == AuthMethod.oauth
        assert creds.project_id == "12345"
        assert creds.region == "us"
        assert creds.oauth_access_token is not None
        assert creds.oauth_access_token.get_secret_value() == "access_abc123"

    def test_sa_bridge_to_credentials(self) -> None:
        """Test converting service account bridge to Credentials."""
        bridge = _make_sa_bridge()
        creds = bridge_to_credentials(bridge)

        assert creds.auth_method == AuthMethod.basic
        assert creds.project_id == "67890"
        assert creds.region == "eu"
        assert creds.username == "sa-user.abc.mp-service-account"
        assert creds.secret.get_secret_value() == "sa-secret-value"

    def test_oauth_credentials_auth_header(self) -> None:
        """Test that OAuth credentials produce correct auth header."""
        bridge = _make_oauth_bridge()
        creds = bridge_to_credentials(bridge)

        assert creds.auth_header() == "Bearer access_abc123"

    def test_sa_credentials_auth_header(self) -> None:
        """Test that SA credentials produce correct auth header."""
        bridge = _make_sa_bridge()
        creds = bridge_to_credentials(bridge)

        assert creds.auth_header().startswith("Basic ")


class TestBridgeToResolvedSession:
    """Tests for bridge_to_resolved_session() conversion."""

    def test_oauth_with_workspace(self) -> None:
        """Test converting OAuth bridge with workspace to ResolvedSession."""
        bridge = _make_oauth_bridge(workspace_id=67890)
        session = bridge_to_resolved_session(bridge)

        assert session.project_id == "12345"
        assert session.region == "us"
        assert session.workspace_id == 67890
        assert session.auth.type == CredentialType.oauth

    def test_sa_without_workspace(self) -> None:
        """Test converting SA bridge without workspace to ResolvedSession."""
        bridge = _make_sa_bridge()
        session = bridge_to_resolved_session(bridge)

        assert session.project_id == "67890"
        assert session.region == "eu"
        assert session.workspace_id is None
        assert session.auth.type == CredentialType.service_account

    def test_session_auth_header(self) -> None:
        """Test that session produces correct auth header."""
        bridge = _make_oauth_bridge()
        session = bridge_to_resolved_session(bridge)

        assert session.auth_header() == "Bearer access_abc123"


class TestApplyBridgeCustomHeader:
    """Tests for apply_bridge_custom_header() function."""

    def test_sets_env_vars_when_header_present(self) -> None:
        """Test that custom header sets MP_CUSTOM_HEADER_* env vars."""
        bridge = _make_oauth_bridge(with_custom_header=True)

        with patch.dict(os.environ, {}, clear=True):
            apply_bridge_custom_header(bridge)
            assert os.environ.get("MP_CUSTOM_HEADER_NAME") == "X-Test-Header"
            assert os.environ.get("MP_CUSTOM_HEADER_VALUE") == "test-header-value"

    def test_does_not_override_existing_env_vars(self) -> None:
        """Test that existing env vars are not overridden."""
        bridge = _make_oauth_bridge(with_custom_header=True)

        with patch.dict(
            os.environ,
            {
                "MP_CUSTOM_HEADER_NAME": "X-Existing",
                "MP_CUSTOM_HEADER_VALUE": "existing-value",
            },
        ):
            apply_bridge_custom_header(bridge)
            assert os.environ["MP_CUSTOM_HEADER_NAME"] == "X-Existing"
            assert os.environ["MP_CUSTOM_HEADER_VALUE"] == "existing-value"

    def test_noop_when_no_custom_header(self) -> None:
        """Test that nothing happens when no custom header in bridge."""
        bridge = _make_oauth_bridge(with_custom_header=False)

        with patch.dict(os.environ, {}, clear=True):
            apply_bridge_custom_header(bridge)
            assert "MP_CUSTOM_HEADER_NAME" not in os.environ
            assert "MP_CUSTOM_HEADER_VALUE" not in os.environ


class TestRefreshBridgeToken:
    """Tests for refresh_bridge_token() function."""

    def test_returns_same_bridge_if_not_expired(self) -> None:
        """Test that non-expired bridge is returned unchanged."""
        bridge = _make_oauth_bridge(expired=False)

        result = refresh_bridge_token(bridge, Path("/dummy"))
        assert result is bridge  # Same object, no refresh needed

    def test_refreshes_expired_token(self) -> None:
        """Test that expired OAuth token is refreshed."""
        bridge = _make_oauth_bridge(expired=True)
        new_expires = _utcnow() + timedelta(hours=1)

        mock_tokens = MagicMock()
        mock_tokens.access_token = SecretStr("new_access_token")
        mock_tokens.refresh_token = SecretStr("new_refresh_token")
        mock_tokens.expires_at = new_expires
        mock_tokens.scope = "projects analysis events"
        mock_tokens.token_type = "Bearer"

        with patch("mixpanel_data._internal.auth.bridge.OAuthFlow") as mock_flow_cls:
            mock_flow = mock_flow_cls.return_value
            mock_flow.refresh_tokens.return_value = mock_tokens

            result = refresh_bridge_token(bridge, Path("/dummy"))

            assert result is not bridge
            assert result.oauth is not None
            assert result.oauth.access_token.get_secret_value() == "new_access_token"
            mock_flow.refresh_tokens.assert_called_once()

    def test_refresh_writes_back_if_writable(self, tmp_path: Path) -> None:
        """Test that refreshed token is written back to bridge file."""
        bridge = _make_oauth_bridge(expired=True)
        bridge_file = tmp_path / "auth.json"
        bridge_file.write_text(json.dumps(_bridge_to_dict(bridge)))

        new_expires = _utcnow() + timedelta(hours=1)
        mock_tokens = MagicMock()
        mock_tokens.access_token = SecretStr("new_access")
        mock_tokens.refresh_token = SecretStr("new_refresh")
        mock_tokens.expires_at = new_expires
        mock_tokens.scope = "projects"
        mock_tokens.token_type = "Bearer"

        with patch("mixpanel_data._internal.auth.bridge.OAuthFlow") as mock_flow_cls:
            mock_flow = mock_flow_cls.return_value
            mock_flow.refresh_tokens.return_value = mock_tokens

            refresh_bridge_token(bridge, bridge_file)

        # Verify the file was updated
        updated = json.loads(bridge_file.read_text())
        assert updated["oauth"]["access_token"] == "new_access"

    def test_refresh_ignores_write_errors(self) -> None:
        """Test that write errors during refresh are silently ignored."""
        bridge = _make_oauth_bridge(expired=True)

        mock_tokens = MagicMock()
        mock_tokens.access_token = SecretStr("new_access")
        mock_tokens.refresh_token = SecretStr("new_refresh")
        mock_tokens.expires_at = _utcnow() + timedelta(hours=1)
        mock_tokens.scope = "projects"
        mock_tokens.token_type = "Bearer"

        with patch("mixpanel_data._internal.auth.bridge.OAuthFlow") as mock_flow_cls:
            mock_flow = mock_flow_cls.return_value
            mock_flow.refresh_tokens.return_value = mock_tokens

            # Pass a read-only path — should not raise
            result = refresh_bridge_token(bridge, Path("/read-only/auth.json"))
            assert result.oauth is not None
            assert result.oauth.access_token.get_secret_value() == "new_access"

    def test_returns_original_on_refresh_failure(self) -> None:
        """Test that original bridge is returned if refresh fails."""
        bridge = _make_oauth_bridge(expired=True)

        with patch("mixpanel_data._internal.auth.bridge.OAuthFlow") as mock_flow_cls:
            mock_flow = mock_flow_cls.return_value
            mock_flow.refresh_tokens.side_effect = Exception("refresh failed")

            with pytest.raises(Exception, match="refresh failed"):
                refresh_bridge_token(bridge, Path("/dummy"))

    def test_sa_bridge_returns_unchanged(self) -> None:
        """Test that SA bridge is returned unchanged (no refresh needed)."""
        bridge = _make_sa_bridge()

        result = refresh_bridge_token(bridge, Path("/dummy"))
        assert result is bridge
