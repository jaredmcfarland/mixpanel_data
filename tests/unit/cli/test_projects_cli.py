"""Unit tests for CLI projects commands (list, refresh, switch, show).

Tests cover:
- T044: mp projects list
- T045: mp projects refresh
- T059: mp projects switch / show
- T062: Global --credential and --project options
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mixpanel_data._internal.config import ActiveContext
from mixpanel_data._internal.me import MeProjectInfo
from mixpanel_data.cli.main import app
from mixpanel_data.cli.utils import ExitCode
from mixpanel_data.exceptions import ConfigError


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a CLI runner for testing commands."""
    return CliRunner()


def _make_mock_workspace() -> MagicMock:
    """Create a mock Workspace with discover_projects() and me()."""
    ws = MagicMock()
    ws.discover_projects.return_value = [
        (
            "3713224",
            MeProjectInfo(
                name="AI Demo",
                organization_id=100,
                timezone="US/Pacific",
                has_workspaces=True,
            ),
        ),
        (
            "3018488",
            MeProjectInfo(
                name="E-Commerce",
                organization_id=100,
                timezone="US/Eastern",
                has_workspaces=False,
            ),
        ),
    ]
    ws.me.return_value = MagicMock()
    return ws


class TestProjectsList:
    """T044: Tests for mp projects list."""

    @patch("mixpanel_data.cli.commands.projects.get_workspace")
    def test_list_outputs_json(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects list outputs JSON with project data."""
        mock_get_ws.return_value = _make_mock_workspace()

        result = cli_runner.invoke(app, ["projects", "list"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["project_id"] == "3713224"
        assert data[0]["name"] == "AI Demo"

    @patch("mixpanel_data.cli.commands.projects.get_workspace")
    def test_list_with_refresh(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects list --refresh calls me(force_refresh=True)."""
        mock_ws = _make_mock_workspace()
        mock_get_ws.return_value = mock_ws

        result = cli_runner.invoke(app, ["projects", "list", "--refresh"])

        assert result.exit_code == 0
        mock_ws.me.assert_called_once_with(force_refresh=True)

    @patch("mixpanel_data.cli.commands.projects.get_workspace")
    def test_list_table_format(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects list --format table produces output."""
        mock_get_ws.return_value = _make_mock_workspace()

        result = cli_runner.invoke(app, ["projects", "list", "--format", "table"])

        assert result.exit_code == 0
        # Table format should contain project names
        assert "AI Demo" in result.stdout

    @patch("mixpanel_data.cli.commands.projects._discover_projects_via_oauth")
    @patch("mixpanel_data.cli.commands.projects.get_workspace")
    def test_list_config_error(
        self,
        mock_get_ws: MagicMock,
        mock_oauth_fallback: MagicMock,
        cli_runner: CliRunner,
    ) -> None:
        """Test mp projects list handles ConfigError when no OAuth fallback."""
        mock_get_ws.side_effect = ConfigError("No credentials")
        mock_oauth_fallback.return_value = None

        result = cli_runner.invoke(app, ["projects", "list"])

        assert result.exit_code != 0


class TestProjectsRefresh:
    """T045: Tests for mp projects refresh."""

    @patch("mixpanel_data.cli.commands.projects.get_workspace")
    def test_refresh_forces_api_call(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects refresh calls me(force_refresh=True)."""
        mock_ws = _make_mock_workspace()
        mock_get_ws.return_value = mock_ws

        result = cli_runner.invoke(app, ["projects", "refresh"])

        assert result.exit_code == 0
        mock_ws.me.assert_called_once_with(force_refresh=True)

    @patch("mixpanel_data.cli.commands.projects.get_workspace")
    def test_refresh_outputs_json(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects refresh outputs project data as JSON."""
        mock_get_ws.return_value = _make_mock_workspace()

        result = cli_runner.invoke(app, ["projects", "refresh"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 2


class TestProjectsSwitch:
    """T059: Tests for mp projects switch."""

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_switch_sets_active_project(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects switch sets the active project."""
        mock_cm = MagicMock()
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["projects", "switch", "3713224"])

        assert result.exit_code == 0
        mock_cm.set_active_project.assert_called_once_with("3713224", workspace_id=None)

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_switch_with_workspace(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects switch with --workspace-id."""
        mock_cm = MagicMock()
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(
            app,
            ["projects", "switch", "3713224", "--workspace-id", "3448413"],
        )

        assert result.exit_code == 0
        mock_cm.set_active_project.assert_called_once_with(
            "3713224", workspace_id=3448413
        )

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_switch_outputs_confirmation(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects switch outputs confirmation JSON."""
        mock_cm = MagicMock()
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["projects", "switch", "3713224"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "ok"
        assert data["active_project_id"] == "3713224"


class TestProjectsShow:
    """T059: Tests for mp projects show."""

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_show_outputs_active_context(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects show displays current active context."""
        mock_cm = MagicMock()
        mock_cm.get_active_context.return_value = ActiveContext(
            credential="demo-sa",
            project_id="3713224",
            workspace_id=3448413,
        )
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["projects", "show"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["credential"] == "demo-sa"
        assert data["project_id"] == "3713224"
        assert data["workspace_id"] == 3448413

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_show_empty_context(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects show with no active context."""
        mock_cm = MagicMock()
        mock_cm.get_active_context.return_value = ActiveContext()
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["projects", "show"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["credential"] is None
        assert data["project_id"] is None
        assert data["workspace_id"] is None


class TestGlobalOptions:
    """T062: Tests for global --credential and --project options."""

    @patch("mixpanel_data.cli.commands.projects.get_workspace")
    def test_credential_option_stored_in_context(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that --credential is stored in ctx.obj."""
        mock_get_ws.return_value = _make_mock_workspace()

        result = cli_runner.invoke(
            app,
            ["--credential", "demo-sa", "projects", "list"],
        )

        assert result.exit_code == 0
        # Verify the context was set by checking get_workspace was called
        mock_get_ws.assert_called_once()

    @patch("mixpanel_data.cli.commands.projects.get_workspace")
    def test_project_option_stored_in_context(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test that --project is stored in ctx.obj."""
        mock_get_ws.return_value = _make_mock_workspace()

        result = cli_runner.invoke(
            app,
            ["--project", "3713224", "projects", "list"],
        )

        assert result.exit_code == 0
        mock_get_ws.assert_called_once()

    @patch("mixpanel_data.cli.commands.projects.get_workspace")
    def test_credential_and_project_combined(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test --credential + --project both stored."""
        mock_get_ws.return_value = _make_mock_workspace()

        result = cli_runner.invoke(
            app,
            [
                "--credential",
                "demo-sa",
                "--project",
                "3713224",
                "projects",
                "list",
            ],
        )

        assert result.exit_code == 0

    def test_get_workspace_v2_path(self) -> None:
        """Test get_workspace uses v2 path when --credential is set."""
        import typer

        from mixpanel_data.cli.utils import get_workspace

        ctx = typer.Context(typer.main.get_command(app))
        ctx.ensure_object(dict)
        ctx.obj["account"] = None
        ctx.obj["credential"] = "demo-sa"
        ctx.obj["project"] = "3713224"
        ctx.obj["workspace_id"] = None
        ctx.obj["workspace"] = None

        with patch("mixpanel_data.workspace.Workspace") as mock_ws_cls:
            mock_ws_cls.return_value = MagicMock()
            get_workspace(ctx)
            mock_ws_cls.assert_called_once_with(
                credential="demo-sa",
                project_id="3713224",
                workspace_id=None,
            )

    def test_get_workspace_legacy_path(self) -> None:
        """Test get_workspace uses legacy path when no --credential."""
        import typer

        from mixpanel_data.cli.utils import get_workspace

        ctx = typer.Context(typer.main.get_command(app))
        ctx.ensure_object(dict)
        ctx.obj["account"] = "staging"
        ctx.obj["credential"] = None
        ctx.obj["project"] = None
        ctx.obj["workspace_id"] = None
        ctx.obj["workspace"] = None

        with patch("mixpanel_data.workspace.Workspace") as mock_ws_cls:
            mock_ws_cls.return_value = MagicMock()
            get_workspace(ctx)
            mock_ws_cls.assert_called_once_with(
                account="staging",
                project_id=None,
                workspace_id=None,
            )

    def test_get_workspace_project_only_uses_legacy(self) -> None:
        """Test --project without --credential uses legacy path."""
        import typer

        from mixpanel_data.cli.utils import get_workspace

        ctx = typer.Context(typer.main.get_command(app))
        ctx.ensure_object(dict)
        ctx.obj["account"] = None
        ctx.obj["credential"] = None
        ctx.obj["project"] = "3713224"
        ctx.obj["workspace_id"] = None
        ctx.obj["workspace"] = None

        with patch("mixpanel_data.workspace.Workspace") as mock_ws_cls:
            mock_ws_cls.return_value = MagicMock()
            get_workspace(ctx)
            mock_ws_cls.assert_called_once_with(
                account=None,
                project_id="3713224",
                workspace_id=None,
            )


# =============================================================================
# T098-T099: Project Alias CLI Tests
# =============================================================================


class TestProjectAliasAdd:
    """T098: Tests for mp projects alias add."""

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_alias_add_basic(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects alias add creates an alias."""
        mock_cm = MagicMock()
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(
            app,
            ["projects", "alias", "add", "ecom", "--project", "3018488"],
        )

        assert result.exit_code == 0
        mock_cm.add_project_alias.assert_called_once_with(
            "ecom", "3018488", credential=None, workspace_id=None
        )
        data = json.loads(result.stdout)
        assert data["alias"] == "ecom"
        assert data["project_id"] == "3018488"

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_alias_add_with_credential_and_workspace(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects alias add with --credential and --workspace."""
        mock_cm = MagicMock()
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(
            app,
            [
                "projects",
                "alias",
                "add",
                "ai-demo",
                "--project",
                "3713224",
                "--credential",
                "demo-sa",
                "--workspace",
                "3448413",
            ],
        )

        assert result.exit_code == 0
        mock_cm.add_project_alias.assert_called_once_with(
            "ai-demo", "3713224", credential="demo-sa", workspace_id=3448413
        )
        data = json.loads(result.stdout)
        assert data["credential"] == "demo-sa"
        assert data["workspace_id"] == 3448413

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_alias_add_duplicate_raises(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects alias add with duplicate name exits with error."""
        mock_cm = MagicMock()
        mock_cm.add_project_alias.side_effect = ConfigError(
            "Project alias 'ecom' already exists."
        )
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(
            app,
            ["projects", "alias", "add", "ecom", "--project", "3018488"],
        )

        assert result.exit_code == ExitCode.GENERAL_ERROR


class TestProjectAliasRemove:
    """T098: Tests for mp projects alias remove."""

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_alias_remove(self, mock_get_cfg: MagicMock, cli_runner: CliRunner) -> None:
        """Test mp projects alias remove deletes an alias."""
        mock_cm = MagicMock()
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(
            app,
            ["projects", "alias", "remove", "ecom"],
        )

        assert result.exit_code == 0
        mock_cm.remove_project_alias.assert_called_once_with("ecom")
        data = json.loads(result.stdout)
        assert data["removed"] == "ecom"

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_alias_remove_not_found(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects alias remove with unknown name exits with error."""
        mock_cm = MagicMock()
        mock_cm.remove_project_alias.side_effect = ConfigError(
            "Project alias 'nonexistent' not found."
        )
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(
            app,
            ["projects", "alias", "remove", "nonexistent"],
        )

        assert result.exit_code == ExitCode.GENERAL_ERROR


class TestProjectAliasList:
    """T098: Tests for mp projects alias list."""

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_alias_list_outputs_json(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects alias list outputs aliases as JSON."""
        from mixpanel_data._internal.config import ProjectAlias

        mock_cm = MagicMock()
        mock_cm.list_project_aliases.return_value = [
            ProjectAlias(
                name="ecom",
                project_id="3018488",
                credential="demo-sa",
                workspace_id=None,
            ),
            ProjectAlias(
                name="ai-demo",
                project_id="3713224",
                credential="demo-sa",
                workspace_id=3448413,
            ),
        ]
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(
            app,
            ["projects", "alias", "list"],
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["name"] == "ecom"
        assert data[0]["project_id"] == "3018488"
        assert data[1]["workspace_id"] == 3448413

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_alias_list_empty(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects alias list with no aliases."""
        mock_cm = MagicMock()
        mock_cm.list_project_aliases.return_value = []
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(
            app,
            ["projects", "alias", "list"],
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data == []

    @patch("mixpanel_data.cli.commands.projects.get_config")
    def test_alias_list_table_format(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp projects alias list --format table produces output."""
        from mixpanel_data._internal.config import ProjectAlias

        mock_cm = MagicMock()
        mock_cm.list_project_aliases.return_value = [
            ProjectAlias(
                name="ecom",
                project_id="3018488",
                credential=None,
                workspace_id=None,
            ),
        ]
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(
            app,
            ["projects", "alias", "list", "--format", "table"],
        )

        assert result.exit_code == 0
        assert "ecom" in result.stdout
