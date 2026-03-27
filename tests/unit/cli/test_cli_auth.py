"""Unit tests for CLI auth OAuth commands (login, logout, status, token).

Tests cover:
- T038: OAuth CLI commands (login, logout, status, token)
- T039: --workspace-id global option and MP_WORKSPACE_ID env var
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import typer
from pydantic import SecretStr
from typer.testing import CliRunner

from mixpanel_data._internal.auth.token import OAuthTokens
from mixpanel_data.cli.main import app
from mixpanel_data.cli.utils import ExitCode


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a CLI runner for testing commands."""
    return CliRunner()


@pytest.fixture
def mock_tokens() -> OAuthTokens:
    """Create mock OAuth tokens for testing."""
    return OAuthTokens(
        access_token=SecretStr("test-access-token-abc123"),
        refresh_token=SecretStr("test-refresh-token-def456"),
        expires_at=datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        scope="projects analysis events",
        token_type="Bearer",
        project_id="12345",
    )


@pytest.fixture
def expired_tokens() -> OAuthTokens:
    """Create expired OAuth tokens for testing."""
    return OAuthTokens(
        access_token=SecretStr("expired-access-token"),
        refresh_token=SecretStr("expired-refresh-token"),
        expires_at=datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        scope="projects analysis events",
        token_type="Bearer",
        project_id="12345",
    )


class TestAuthLogin:
    """Tests for mp auth login command."""

    @patch("mixpanel_data.cli.commands.auth.OAuthFlow")
    def test_login_triggers_oauth_flow(
        self, mock_flow_cls: MagicMock, cli_runner: CliRunner, mock_tokens: OAuthTokens
    ) -> None:
        """Test that mp auth login triggers the OAuth flow."""
        mock_flow = MagicMock()
        mock_flow.login.return_value = mock_tokens
        mock_flow_cls.return_value = mock_flow

        result = cli_runner.invoke(app, ["auth", "login"])

        assert result.exit_code == 0
        mock_flow_cls.assert_called_once()
        mock_flow.login.assert_called_once()

    @patch("mixpanel_data.cli.commands.auth.OAuthFlow")
    def test_login_with_region(
        self, mock_flow_cls: MagicMock, cli_runner: CliRunner, mock_tokens: OAuthTokens
    ) -> None:
        """Test that mp auth login --region eu passes region to OAuthFlow."""
        mock_flow = MagicMock()
        mock_flow.login.return_value = mock_tokens
        mock_flow_cls.return_value = mock_flow

        result = cli_runner.invoke(app, ["auth", "login", "--region", "eu"])

        assert result.exit_code == 0
        mock_flow_cls.assert_called_once_with(region="eu")

    @patch("mixpanel_data.cli.commands.auth.OAuthFlow")
    def test_login_success_outputs_json(
        self, mock_flow_cls: MagicMock, cli_runner: CliRunner, mock_tokens: OAuthTokens
    ) -> None:
        """Test that successful login outputs JSON confirmation."""
        mock_flow = MagicMock()
        mock_flow.login.return_value = mock_tokens
        mock_flow_cls.return_value = mock_flow

        result = cli_runner.invoke(app, ["auth", "login"])

        assert result.exit_code == 0
        assert "login" in result.stdout.lower() or "success" in result.stdout.lower()

    @patch("mixpanel_data.cli.commands.auth.OAuthFlow")
    def test_login_oauth_error_exits_2(
        self, mock_flow_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that OAuthError during login results in exit code 2."""
        from mixpanel_data.exceptions import OAuthError

        mock_flow = MagicMock()
        mock_flow.login.side_effect = OAuthError(
            "Login failed", code="OAUTH_TOKEN_ERROR"
        )
        mock_flow_cls.return_value = mock_flow

        result = cli_runner.invoke(app, ["auth", "login"])

        assert result.exit_code == ExitCode.AUTH_ERROR


class TestAuthLogout:
    """Tests for mp auth logout command."""

    @patch("mixpanel_data.cli.commands.auth.OAuthStorage")
    def test_logout_with_region(
        self, mock_storage_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that mp auth logout --region us deletes tokens for that region."""
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        result = cli_runner.invoke(app, ["auth", "logout", "--region", "us"])

        assert result.exit_code == 0
        mock_storage.delete_tokens.assert_called_once_with("us")

    @patch("mixpanel_data.cli.commands.auth.OAuthStorage")
    def test_logout_without_region_deletes_all(
        self, mock_storage_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that mp auth logout without region deletes all tokens."""
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        result = cli_runner.invoke(app, ["auth", "logout"])

        assert result.exit_code == 0
        mock_storage.delete_all.assert_called_once()

    @patch("mixpanel_data.cli.commands.auth.OAuthStorage")
    def test_logout_outputs_confirmation(
        self, mock_storage_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that logout outputs JSON confirmation."""
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        result = cli_runner.invoke(app, ["auth", "logout"])

        assert result.exit_code == 0
        assert "logout" in result.stdout.lower() or "removed" in result.stdout.lower()


class TestAuthStatus:
    """Tests for mp auth status command."""

    @patch("mixpanel_data.cli.commands.auth.OAuthStorage")
    def test_status_authenticated(
        self,
        mock_storage_cls: MagicMock,
        cli_runner: CliRunner,
        mock_tokens: OAuthTokens,
    ) -> None:
        """Test that status shows authenticated when tokens exist."""
        mock_storage = MagicMock()
        mock_storage.load_tokens.return_value = mock_tokens
        mock_storage_cls.return_value = mock_storage

        result = cli_runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "authenticated" in result.stdout.lower() or "Bearer" in result.stdout

    @patch("mixpanel_data.cli.commands.auth.OAuthStorage")
    def test_status_not_authenticated(
        self, mock_storage_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that status shows not authenticated when no tokens exist."""
        mock_storage = MagicMock()
        mock_storage.load_tokens.return_value = None
        mock_storage_cls.return_value = mock_storage

        result = cli_runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "false" in result.stdout.lower() or "null" in result.stdout.lower()

    @patch("mixpanel_data.cli.commands.auth.OAuthStorage")
    def test_status_shows_expiry(
        self,
        mock_storage_cls: MagicMock,
        cli_runner: CliRunner,
        mock_tokens: OAuthTokens,
    ) -> None:
        """Test that status shows token expiry information."""
        mock_storage = MagicMock()
        mock_storage.load_tokens.return_value = mock_tokens
        mock_storage_cls.return_value = mock_storage

        result = cli_runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        # Should include expiry info
        assert "expires" in result.stdout.lower() or "2099" in result.stdout

    @patch("mixpanel_data.cli.commands.auth.OAuthStorage")
    def test_status_shows_expired_flag(
        self,
        mock_storage_cls: MagicMock,
        cli_runner: CliRunner,
        expired_tokens: OAuthTokens,
    ) -> None:
        """Test that status indicates when tokens are expired."""
        mock_storage = MagicMock()
        mock_storage.load_tokens.return_value = expired_tokens
        mock_storage_cls.return_value = mock_storage

        result = cli_runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "expired" in result.stdout.lower() or "true" in result.stdout.lower()


class TestAuthToken:
    """Tests for mp auth token command."""

    @patch("mixpanel_data.cli.commands.auth.OAuthFlow")
    def test_token_outputs_raw_token(
        self, mock_flow_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that mp auth token outputs raw access token to stdout."""
        mock_flow = MagicMock()
        mock_flow.get_valid_token.return_value = "raw-access-token-value"
        mock_flow_cls.return_value = mock_flow

        result = cli_runner.invoke(app, ["auth", "token"])

        assert result.exit_code == 0
        assert "raw-access-token-value" in result.stdout.strip()

    @patch("mixpanel_data.cli.commands.auth.OAuthFlow")
    def test_token_with_region(
        self, mock_flow_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that mp auth token --region eu passes region correctly."""
        mock_flow = MagicMock()
        mock_flow.get_valid_token.return_value = "eu-token-value"
        mock_flow_cls.return_value = mock_flow

        result = cli_runner.invoke(app, ["auth", "token", "--region", "eu"])

        assert result.exit_code == 0
        mock_flow.get_valid_token.assert_called_once_with(region="eu")

    @patch("mixpanel_data.cli.commands.auth.OAuthFlow")
    def test_token_no_token_exits_2(
        self, mock_flow_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that missing token results in exit code 2."""
        from mixpanel_data.exceptions import OAuthError

        mock_flow = MagicMock()
        mock_flow.get_valid_token.side_effect = OAuthError(
            "No OAuth tokens found.", code="OAUTH_TOKEN_ERROR"
        )
        mock_flow_cls.return_value = mock_flow

        result = cli_runner.invoke(app, ["auth", "token"])

        assert result.exit_code == ExitCode.AUTH_ERROR


class TestWorkspaceIdOption:
    """Tests for --workspace-id global option."""

    def test_workspace_id_option_available(self, cli_runner: CliRunner) -> None:
        """Test that --workspace-id is available as a global option."""
        result = cli_runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "workspace-id" in result.stdout

    @patch("mixpanel_data.cli.commands.auth.OAuthStorage")
    def test_workspace_id_stored_in_context(
        self, mock_storage_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that --workspace-id value is passed through context."""
        mock_storage = MagicMock()
        mock_storage.load_tokens.return_value = None
        mock_storage_cls.return_value = mock_storage

        # Using auth status as a simple command that doesn't need workspace
        result = cli_runner.invoke(app, ["--workspace-id", "999", "auth", "status"])

        assert result.exit_code == 0

    @patch("mixpanel_data.cli.commands.auth.OAuthStorage")
    def test_workspace_id_env_var(
        self, mock_storage_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that MP_WORKSPACE_ID env var works."""
        mock_storage = MagicMock()
        mock_storage.load_tokens.return_value = None
        mock_storage_cls.return_value = mock_storage

        result = cli_runner.invoke(
            app,
            ["auth", "status"],
            env={"MP_WORKSPACE_ID": "888"},
        )

        assert result.exit_code == 0

    @patch("mixpanel_data.workspace.Workspace")
    def test_workspace_id_passed_to_workspace_constructor(
        self, mock_ws_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that workspace_id is passed to Workspace constructor."""
        from pathlib import Path

        from mixpanel_data.types import WorkspaceInfo

        mock_ws = MagicMock()
        mock_ws.events.return_value = ["Event1"]
        mock_ws.info.return_value = WorkspaceInfo(
            path=Path("/tmp/test.db"),
            account="default",
            project_id="12345",
            region="us",
            tables=[],
            size_mb=0.0,
            created_at=None,
        )
        mock_ws_cls.return_value = mock_ws

        # Patch at the point where get_workspace imports Workspace
        with patch("mixpanel_data.cli.utils.Workspace", mock_ws_cls, create=True):
            # Patch the local import inside get_workspace
            import mixpanel_data.cli.utils as utils_mod

            def patched_get_workspace(
                ctx: typer.Context,
                *,
                read_only: bool = False,  # noqa: ARG001
            ) -> MagicMock:
                """Patched get_workspace that captures constructor args."""
                if "workspace" not in ctx.obj or ctx.obj["workspace"] is None:
                    account = ctx.obj.get("account")
                    workspace_id_val: int | None = ctx.obj.get("workspace_id")
                    ctx.obj["workspace"] = mock_ws_cls(
                        account=account,
                        read_only=read_only,
                        workspace_id=workspace_id_val,
                    )
                result: MagicMock = ctx.obj["workspace"]
                return result

            with patch.object(utils_mod, "get_workspace", patched_get_workspace):
                cli_runner.invoke(app, ["--workspace-id", "777", "inspect", "info"])

        # Verify workspace_id was passed
        mock_ws_cls.assert_called_once()
        call_kwargs = mock_ws_cls.call_args
        assert call_kwargs.kwargs.get("workspace_id") == 777


class TestHandleErrorsOAuth:
    """Tests for OAuthError and WorkspaceScopeError handling in handle_errors."""

    def test_oauth_error_exits_2(self) -> None:
        """Test that OAuthError maps to exit code 2."""
        import click.exceptions

        from mixpanel_data.cli.utils import handle_errors
        from mixpanel_data.exceptions import OAuthError

        @handle_errors
        def failing_func() -> None:
            """Raise OAuthError."""
            raise OAuthError("Token expired", code="OAUTH_TOKEN_ERROR")

        with pytest.raises(click.exceptions.Exit) as exc_info:
            failing_func()

        assert exc_info.value.exit_code == ExitCode.AUTH_ERROR

    def test_workspace_scope_error_exits_1(self) -> None:
        """Test that WorkspaceScopeError maps to exit code 1."""
        import click.exceptions

        from mixpanel_data.cli.utils import handle_errors
        from mixpanel_data.exceptions import WorkspaceScopeError

        @handle_errors
        def failing_func() -> None:
            """Raise WorkspaceScopeError."""
            raise WorkspaceScopeError(
                "Multiple workspaces found", code="AMBIGUOUS_WORKSPACE"
            )

        with pytest.raises(click.exceptions.Exit) as exc_info:
            failing_func()

        assert exc_info.value.exit_code == ExitCode.GENERAL_ERROR


class TestCliAuthSmoke:
    """Smoke tests verifying help output for all auth subcommands."""

    def test_auth_help(self, cli_runner: CliRunner) -> None:
        """Verify mp auth --help exits 0 and lists login/logout subcommands."""
        result = cli_runner.invoke(app, ["auth", "--help"])
        assert result.exit_code == 0
        assert "login" in result.stdout
        assert "logout" in result.stdout

    def test_auth_login_help(self, cli_runner: CliRunner) -> None:
        """Verify mp auth login --help exits 0 and shows --region option."""
        result = cli_runner.invoke(app, ["auth", "login", "--help"])
        assert result.exit_code == 0
        assert "--region" in result.stdout

    def test_auth_logout_help(self, cli_runner: CliRunner) -> None:
        """Verify mp auth logout --help exits 0."""
        result = cli_runner.invoke(app, ["auth", "logout", "--help"])
        assert result.exit_code == 0

    def test_auth_status_help(self, cli_runner: CliRunner) -> None:
        """Verify mp auth status --help exits 0."""
        result = cli_runner.invoke(app, ["auth", "status", "--help"])
        assert result.exit_code == 0

    def test_auth_token_help(self, cli_runner: CliRunner) -> None:
        """Verify mp auth token --help exits 0."""
        result = cli_runner.invoke(app, ["auth", "token", "--help"])
        assert result.exit_code == 0

    def test_workspace_id_in_main_help(self, cli_runner: CliRunner) -> None:
        """Verify --workspace-id appears in the main mp --help output."""
        result = cli_runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "workspace-id" in result.stdout


class TestCliAuthExtended:
    """Extended CLI tests for auth token and logout region behaviour."""

    @patch("mixpanel_data.cli.commands.auth.OAuthFlow")
    def test_auth_token_only_raw_token(
        self, mock_flow_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Verify mp auth token outputs only the raw token string, no JSON wrapper."""
        mock_flow = MagicMock()
        mock_flow.get_valid_token.return_value = "my_raw_token_value"
        mock_flow_cls.return_value = mock_flow

        result = cli_runner.invoke(app, ["auth", "token"])

        assert result.exit_code == 0
        assert result.stdout.strip() == "my_raw_token_value"

    @patch("mixpanel_data.cli.commands.auth.OAuthStorage")
    def test_auth_logout_region_preserves_others(
        self, mock_storage_cls: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Verify mp auth logout --region us calls delete_tokens, not delete_all."""
        mock_storage = MagicMock()
        mock_storage_cls.return_value = mock_storage

        result = cli_runner.invoke(app, ["auth", "logout", "--region", "us"])

        assert result.exit_code == 0
        mock_storage.delete_tokens.assert_called_once_with("us")
        mock_storage.delete_all.assert_not_called()
