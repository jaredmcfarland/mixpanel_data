"""Integration tests for cowork auth bridge CLI commands."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr
from typer.testing import CliRunner

from mixpanel_data._internal.auth.bridge import (
    AuthBridgeFile,
    BridgeOAuth,
    BridgeServiceAccount,
)
from mixpanel_data._internal.auth.token import OAuthClientInfo, OAuthTokens
from mixpanel_data._internal.config import AuthMethod, Credentials
from mixpanel_data.cli.main import app

# Patch targets — lazy imports inside function bodies resolve from source module
_BRIDGE_MOD = "mixpanel_data._internal.auth.bridge"
_AUTH_CMD_MOD = "mixpanel_data.cli.commands.auth"


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a CLI runner for testing commands."""
    return CliRunner()


@pytest.fixture
def mock_config_manager() -> MagicMock:
    """Create a mock ConfigManager for testing cowork commands.

    Returns:
        MagicMock configured as a v1 ConfigManager with no custom header.
    """
    config = MagicMock()
    config.config_version.return_value = 1
    config.get_custom_header.return_value = None
    return config


@pytest.fixture
def sa_credentials() -> Credentials:
    """Create service account credentials for testing.

    Returns:
        Credentials configured with basic auth method.
    """
    return Credentials(
        username="sa-user",
        secret=SecretStr("sa-secret"),
        project_id="12345",
        region="us",
        auth_method=AuthMethod.basic,
    )


@pytest.fixture
def oauth_credentials() -> Credentials:
    """Create OAuth credentials for testing.

    Returns:
        Credentials configured with OAuth auth method.
    """
    return Credentials(
        username="",
        secret=SecretStr(""),
        project_id="12345",
        region="us",
        auth_method=AuthMethod.oauth,
        oauth_access_token=SecretStr("test-access-token"),
    )


@pytest.fixture
def mock_oauth_tokens() -> OAuthTokens:
    """Create mock OAuth tokens for testing.

    Returns:
        OAuthTokens with a future expiration time.
    """
    return OAuthTokens(
        access_token=SecretStr("test-access-token"),
        refresh_token=SecretStr("test-refresh-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scope="read:project write:project",
        token_type="Bearer",
        project_id="12345",
    )


@pytest.fixture
def mock_client_info() -> OAuthClientInfo:
    """Create mock OAuth client info for testing.

    Returns:
        OAuthClientInfo with a test client ID.
    """
    return OAuthClientInfo(
        client_id="test-client-id",
        region="us",
        redirect_uri="http://localhost:8080/callback",
        scope="read:project write:project",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def bridge_path(tmp_path: Path) -> Path:
    """Create a temporary bridge file path for testing.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        Path to a temporary bridge file location.
    """
    return tmp_path / ".claude" / "mixpanel" / "auth.json"


class TestCoworkSetup:
    """Tests for mp auth cowork-setup command."""

    def test_setup_service_account(
        self,
        cli_runner: CliRunner,
        mock_config_manager: MagicMock,
        sa_credentials: Credentials,
        bridge_path: Path,
    ) -> None:
        """Test cowork-setup with service account credentials."""
        mock_config_manager.resolve_credentials.return_value = sa_credentials

        with (
            patch(
                f"{_AUTH_CMD_MOD}.get_config",
                return_value=mock_config_manager,
            ),
            patch(
                f"{_BRIDGE_MOD}.default_bridge_path",
                return_value=bridge_path,
            ),
            patch(
                "mixpanel_data.workspace.Workspace.test_credentials",
                return_value={"success": True},
            ),
        ):
            result = cli_runner.invoke(app, ["auth", "cowork-setup"])

        assert result.exit_code == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["status"] == "cowork_setup_complete"
        assert data["auth_method"] == "service_account"
        assert data["region"] == "us"
        assert data["project_id"] == "12345"
        assert data["credentials_valid"] is True
        assert bridge_path.exists()

    def test_setup_oauth(
        self,
        cli_runner: CliRunner,
        mock_config_manager: MagicMock,
        oauth_credentials: Credentials,
        mock_oauth_tokens: OAuthTokens,
        mock_client_info: OAuthClientInfo,
        bridge_path: Path,
    ) -> None:
        """Test cowork-setup with OAuth credentials."""
        mock_config_manager.resolve_credentials.return_value = oauth_credentials

        mock_storage = MagicMock()
        mock_storage.load_tokens.return_value = mock_oauth_tokens
        mock_storage.load_client_info.return_value = mock_client_info

        with (
            patch(
                f"{_AUTH_CMD_MOD}.get_config",
                return_value=mock_config_manager,
            ),
            patch(
                f"{_BRIDGE_MOD}.default_bridge_path",
                return_value=bridge_path,
            ),
            patch(
                "mixpanel_data._internal.auth.storage.OAuthStorage",
                return_value=mock_storage,
            ),
            patch(
                "mixpanel_data.workspace.Workspace.test_credentials",
                return_value={"success": True},
            ),
        ):
            result = cli_runner.invoke(app, ["auth", "cowork-setup"])

        assert result.exit_code == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["status"] == "cowork_setup_complete"
        assert data["auth_method"] == "oauth"
        assert data["region"] == "us"
        assert data["project_id"] == "12345"
        assert bridge_path.exists()

    def test_setup_with_project_id_override(
        self,
        cli_runner: CliRunner,
        mock_config_manager: MagicMock,
        sa_credentials: Credentials,
        bridge_path: Path,
    ) -> None:
        """Test cowork-setup with explicit --project-id override."""
        mock_config_manager.resolve_credentials.return_value = sa_credentials

        with (
            patch(
                f"{_AUTH_CMD_MOD}.get_config",
                return_value=mock_config_manager,
            ),
            patch(
                f"{_BRIDGE_MOD}.default_bridge_path",
                return_value=bridge_path,
            ),
            patch(
                "mixpanel_data.workspace.Workspace.test_credentials",
                return_value={"success": True},
            ),
        ):
            result = cli_runner.invoke(
                app, ["auth", "cowork-setup", "--project-id", "99999"]
            )

        assert result.exit_code == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["project_id"] == "99999"

    def test_setup_with_workspace_id(
        self,
        cli_runner: CliRunner,
        mock_config_manager: MagicMock,
        sa_credentials: Credentials,
        bridge_path: Path,
    ) -> None:
        """Test cowork-setup with explicit --workspace-id."""
        mock_config_manager.resolve_credentials.return_value = sa_credentials

        with (
            patch(
                f"{_AUTH_CMD_MOD}.get_config",
                return_value=mock_config_manager,
            ),
            patch(
                f"{_BRIDGE_MOD}.default_bridge_path",
                return_value=bridge_path,
            ),
            patch(
                "mixpanel_data.workspace.Workspace.test_credentials",
                return_value={"success": True},
            ),
        ):
            result = cli_runner.invoke(
                app, ["auth", "cowork-setup", "--workspace-id", "3448413"]
            )

        assert result.exit_code == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["workspace_id"] == 3448413

    def test_setup_with_custom_header_from_env(
        self,
        cli_runner: CliRunner,
        mock_config_manager: MagicMock,
        sa_credentials: Credentials,
        bridge_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test cowork-setup picks up custom headers from env vars."""
        mock_config_manager.resolve_credentials.return_value = sa_credentials
        monkeypatch.setenv("MP_CUSTOM_HEADER_NAME", "X-Custom")
        monkeypatch.setenv("MP_CUSTOM_HEADER_VALUE", "secret-value")

        with (
            patch(
                f"{_AUTH_CMD_MOD}.get_config",
                return_value=mock_config_manager,
            ),
            patch(
                f"{_BRIDGE_MOD}.default_bridge_path",
                return_value=bridge_path,
            ),
            patch(
                "mixpanel_data.workspace.Workspace.test_credentials",
                return_value={"success": True},
            ),
        ):
            result = cli_runner.invoke(app, ["auth", "cowork-setup"])

        assert result.exit_code == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["has_custom_header"] is True

    def test_setup_with_custom_header_from_config(
        self,
        cli_runner: CliRunner,
        mock_config_manager: MagicMock,
        sa_credentials: Credentials,
        bridge_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test cowork-setup picks up custom headers from config [settings]."""
        mock_config_manager.resolve_credentials.return_value = sa_credentials
        mock_config_manager.get_custom_header.return_value = ("X-Config", "config-val")
        monkeypatch.delenv("MP_CUSTOM_HEADER_NAME", raising=False)
        monkeypatch.delenv("MP_CUSTOM_HEADER_VALUE", raising=False)

        with (
            patch(
                f"{_AUTH_CMD_MOD}.get_config",
                return_value=mock_config_manager,
            ),
            patch(
                f"{_BRIDGE_MOD}.default_bridge_path",
                return_value=bridge_path,
            ),
            patch(
                "mixpanel_data.workspace.Workspace.test_credentials",
                return_value={"success": True},
            ),
        ):
            result = cli_runner.invoke(app, ["auth", "cowork-setup"])

        assert result.exit_code == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["has_custom_header"] is True

    def test_setup_oauth_no_tokens_fails(
        self,
        cli_runner: CliRunner,
        mock_config_manager: MagicMock,
        oauth_credentials: Credentials,
        bridge_path: Path,
    ) -> None:
        """Test cowork-setup fails when OAuth tokens are not in storage."""
        mock_config_manager.resolve_credentials.return_value = oauth_credentials

        mock_storage = MagicMock()
        mock_storage.load_tokens.return_value = None

        with (
            patch(
                f"{_AUTH_CMD_MOD}.get_config",
                return_value=mock_config_manager,
            ),
            patch(
                f"{_BRIDGE_MOD}.default_bridge_path",
                return_value=bridge_path,
            ),
            patch(
                "mixpanel_data._internal.auth.storage.OAuthStorage",
                return_value=mock_storage,
            ),
        ):
            result = cli_runner.invoke(app, ["auth", "cowork-setup"])

        assert result.exit_code == 1
        assert "OAuth tokens not found" in result.stderr

    def test_setup_credentials_test_failure_still_succeeds(
        self,
        cli_runner: CliRunner,
        mock_config_manager: MagicMock,
        sa_credentials: Credentials,
        bridge_path: Path,
    ) -> None:
        """Test cowork-setup succeeds even when credential test fails."""
        mock_config_manager.resolve_credentials.return_value = sa_credentials

        with (
            patch(
                f"{_AUTH_CMD_MOD}.get_config",
                return_value=mock_config_manager,
            ),
            patch(
                f"{_BRIDGE_MOD}.default_bridge_path",
                return_value=bridge_path,
            ),
            patch(
                "mixpanel_data.workspace.Workspace.test_credentials",
                side_effect=Exception("network error"),
            ),
        ):
            result = cli_runner.invoke(app, ["auth", "cowork-setup"])

        assert result.exit_code == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["credentials_valid"] is False
        assert bridge_path.exists()

    def test_setup_with_named_credential(
        self,
        cli_runner: CliRunner,
        mock_config_manager: MagicMock,
        sa_credentials: Credentials,
        bridge_path: Path,
    ) -> None:
        """Test cowork-setup passes credential name to resolve_credentials."""
        mock_config_manager.resolve_credentials.return_value = sa_credentials

        with (
            patch(
                f"{_AUTH_CMD_MOD}.get_config",
                return_value=mock_config_manager,
            ),
            patch(
                f"{_BRIDGE_MOD}.default_bridge_path",
                return_value=bridge_path,
            ),
            patch(
                "mixpanel_data.workspace.Workspace.test_credentials",
                return_value={"success": True},
            ),
        ):
            result = cli_runner.invoke(
                app, ["auth", "cowork-setup", "--credential", "demo-sa"]
            )

        assert result.exit_code == 0, f"stderr: {result.stderr}"
        mock_config_manager.resolve_credentials.assert_called_once_with(
            account="demo-sa"
        )


class TestCoworkTeardown:
    """Tests for mp auth cowork-teardown command."""

    def test_teardown_removes_existing_file(
        self,
        cli_runner: CliRunner,
        bridge_path: Path,
    ) -> None:
        """Test cowork-teardown deletes an existing bridge file."""
        # Create the bridge file
        bridge_path.parent.mkdir(parents=True, exist_ok=True)
        bridge_path.write_text('{"version": 1}', encoding="utf-8")
        assert bridge_path.exists()

        with patch(
            f"{_BRIDGE_MOD}.default_bridge_path",
            return_value=bridge_path,
        ):
            result = cli_runner.invoke(app, ["auth", "cowork-teardown"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "cowork_teardown_complete"
        assert data["removed"] is True
        assert not bridge_path.exists()

    def test_teardown_no_file_exists(
        self,
        cli_runner: CliRunner,
        bridge_path: Path,
    ) -> None:
        """Test cowork-teardown when no bridge file exists."""
        assert not bridge_path.exists()

        with patch(
            f"{_BRIDGE_MOD}.default_bridge_path",
            return_value=bridge_path,
        ):
            result = cli_runner.invoke(app, ["auth", "cowork-teardown"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "cowork_teardown_complete"
        assert data["removed"] is False
        assert "did not exist" in data["message"]


class TestCoworkStatus:
    """Tests for mp auth cowork-status command."""

    def test_status_no_bridge_file(
        self,
        cli_runner: CliRunner,
        bridge_path: Path,
    ) -> None:
        """Test cowork-status when no bridge file exists."""
        assert not bridge_path.exists()

        with patch(
            f"{_BRIDGE_MOD}.default_bridge_path",
            return_value=bridge_path,
        ):
            result = cli_runner.invoke(app, ["auth", "cowork-status"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["exists"] is False
        assert "cowork-setup" in data["message"]

    def test_status_valid_sa_bridge(
        self,
        cli_runner: CliRunner,
        bridge_path: Path,
    ) -> None:
        """Test cowork-status with a valid service account bridge file."""
        sa_bridge = AuthBridgeFile(
            version=1,
            auth_method="service_account",
            region="us",
            project_id="12345",
            workspace_id=100,
            service_account=BridgeServiceAccount(
                username="sa-user",
                secret=SecretStr("sa-secret"),
            ),
        )

        # Create the file so is_file() passes
        bridge_path.parent.mkdir(parents=True, exist_ok=True)
        bridge_path.write_text("{}", encoding="utf-8")

        with (
            patch(
                f"{_BRIDGE_MOD}.default_bridge_path",
                return_value=bridge_path,
            ),
            patch(
                f"{_BRIDGE_MOD}.load_bridge_file",
                return_value=sa_bridge,
            ),
        ):
            result = cli_runner.invoke(app, ["auth", "cowork-status"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["exists"] is True
        assert data["valid"] is True
        assert data["auth_method"] == "service_account"
        assert data["region"] == "us"
        assert data["project_id"] == "12345"
        assert data["workspace_id"] == 100
        assert data["sa_username"] == "sa-user"
        assert data["has_custom_header"] is False

    def test_status_valid_oauth_bridge(
        self,
        cli_runner: CliRunner,
        bridge_path: Path,
    ) -> None:
        """Test cowork-status with a valid OAuth bridge file."""
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        oauth_bridge = AuthBridgeFile(
            version=1,
            auth_method="oauth",
            region="eu",
            project_id="67890",
            oauth=BridgeOAuth(
                access_token=SecretStr("access-tok"),
                refresh_token=SecretStr("refresh-tok"),
                expires_at=expires,
                scope="read:project",
                token_type="Bearer",
                client_id="cid-123",
            ),
        )

        bridge_path.parent.mkdir(parents=True, exist_ok=True)
        bridge_path.write_text("{}", encoding="utf-8")

        with (
            patch(
                f"{_BRIDGE_MOD}.default_bridge_path",
                return_value=bridge_path,
            ),
            patch(
                f"{_BRIDGE_MOD}.load_bridge_file",
                return_value=oauth_bridge,
            ),
        ):
            result = cli_runner.invoke(app, ["auth", "cowork-status"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["exists"] is True
        assert data["valid"] is True
        assert data["auth_method"] == "oauth"
        assert data["region"] == "eu"
        assert data["project_id"] == "67890"
        assert data["oauth_is_expired"] is False
        assert data["oauth_scope"] == "read:project"
        assert "oauth_expires_at" in data

    def test_status_invalid_bridge_file(
        self,
        cli_runner: CliRunner,
        bridge_path: Path,
    ) -> None:
        """Test cowork-status with an invalid bridge file."""
        bridge_path.parent.mkdir(parents=True, exist_ok=True)
        bridge_path.write_text("not valid json", encoding="utf-8")

        with (
            patch(
                f"{_BRIDGE_MOD}.default_bridge_path",
                return_value=bridge_path,
            ),
            patch(
                f"{_BRIDGE_MOD}.load_bridge_file",
                return_value=None,
            ),
        ):
            result = cli_runner.invoke(app, ["auth", "cowork-status"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["exists"] is True
        assert data["valid"] is False
        assert "invalid" in data["message"].lower()
