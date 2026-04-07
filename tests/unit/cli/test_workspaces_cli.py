"""Unit tests for CLI workspaces commands (list, switch, show).

Tests cover:
- T069: mp workspaces list
- T069: mp workspaces switch
- T069: mp workspaces show
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mixpanel_data._internal.config import ActiveContext
from mixpanel_data._internal.me import MeWorkspaceInfo
from mixpanel_data.cli.main import app
from mixpanel_data.cli.utils import ExitCode
from mixpanel_data.exceptions import ConfigError


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a CLI runner for testing commands."""
    return CliRunner()


def _make_mock_workspace() -> MagicMock:
    """Create a mock Workspace with discover_workspaces().

    Returns:
        MagicMock configured with workspace discovery data.
    """
    ws = MagicMock()
    ws.discover_workspaces.return_value = [
        MeWorkspaceInfo(
            id=3448413,
            name="Default",
            project_id=3713224,
            is_default=True,
        ),
        MeWorkspaceInfo(
            id=3448414,
            name="Staging",
            project_id=3713224,
            is_default=False,
        ),
    ]
    return ws


class TestWorkspacesList:
    """T069: Tests for mp workspaces list."""

    @patch("mixpanel_data.cli.commands.workspaces_cmd.get_workspace")
    def test_list_outputs_json(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp workspaces list outputs JSON with workspace data."""
        mock_get_ws.return_value = _make_mock_workspace()

        result = cli_runner.invoke(app, ["workspaces", "list"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["id"] == 3448413
        assert data[0]["name"] == "Default"
        assert data[0]["is_default"] is True

    @patch("mixpanel_data.cli.commands.workspaces_cmd.get_workspace")
    def test_list_with_project_filter(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp workspaces list --project passes project_id."""
        mock_ws = _make_mock_workspace()
        mock_get_ws.return_value = mock_ws

        result = cli_runner.invoke(app, ["workspaces", "list", "--project", "3713224"])

        assert result.exit_code == 0
        mock_ws.discover_workspaces.assert_called_once_with(project_id="3713224")

    @patch("mixpanel_data.cli.commands.workspaces_cmd.get_workspace")
    def test_list_default_no_project(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp workspaces list without --project passes None."""
        mock_ws = _make_mock_workspace()
        mock_get_ws.return_value = mock_ws

        result = cli_runner.invoke(app, ["workspaces", "list"])

        assert result.exit_code == 0
        mock_ws.discover_workspaces.assert_called_once_with(project_id=None)

    @patch("mixpanel_data.cli.commands.workspaces_cmd.get_workspace")
    def test_list_table_format(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp workspaces list --format table produces output."""
        mock_get_ws.return_value = _make_mock_workspace()

        result = cli_runner.invoke(app, ["workspaces", "list", "--format", "table"])

        assert result.exit_code == 0
        assert "Default" in result.stdout

    @patch("mixpanel_data.cli.commands.workspaces_cmd.get_workspace")
    def test_list_config_error(
        self, mock_get_ws: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp workspaces list handles ConfigError."""
        mock_get_ws.side_effect = ConfigError("No credentials")

        result = cli_runner.invoke(app, ["workspaces", "list"])

        assert result.exit_code == ExitCode.GENERAL_ERROR


class TestWorkspacesSwitch:
    """T069: Tests for mp workspaces switch."""

    @patch("mixpanel_data.cli.commands.workspaces_cmd.get_config")
    def test_switch_sets_workspace(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp workspaces switch sets the workspace ID."""
        mock_cm = MagicMock()
        mock_cm.get_active_context.return_value = ActiveContext(
            credential="demo-sa",
            project_id="3713224",
            workspace_id=None,
        )
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["workspaces", "switch", "3448413"])

        assert result.exit_code == 0
        mock_cm.set_active_project.assert_called_once_with(
            "3713224", workspace_id=3448413
        )

    @patch("mixpanel_data.cli.commands.workspaces_cmd.get_config")
    def test_switch_outputs_confirmation(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp workspaces switch outputs confirmation JSON."""
        mock_cm = MagicMock()
        mock_cm.get_active_context.return_value = ActiveContext(
            credential="demo-sa",
            project_id="3713224",
            workspace_id=None,
        )
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["workspaces", "switch", "3448413"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "ok"
        assert data["active_workspace_id"] == 3448413
        assert data["active_project_id"] == "3713224"

    @patch("mixpanel_data.cli.commands.workspaces_cmd.get_config")
    def test_switch_no_active_project(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp workspaces switch with no active project uses empty string."""
        mock_cm = MagicMock()
        mock_cm.get_active_context.return_value = ActiveContext()
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["workspaces", "switch", "3448413"])

        assert result.exit_code == 0
        mock_cm.set_active_project.assert_called_once_with("", workspace_id=3448413)


class TestWorkspacesShow:
    """T069: Tests for mp workspaces show."""

    @patch("mixpanel_data.cli.commands.workspaces_cmd.get_config")
    def test_show_outputs_context(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp workspaces show displays workspace context."""
        mock_cm = MagicMock()
        mock_cm.get_active_context.return_value = ActiveContext(
            credential="demo-sa",
            project_id="3713224",
            workspace_id=3448413,
        )
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["workspaces", "show"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["project_id"] == "3713224"
        assert data["workspace_id"] == 3448413

    @patch("mixpanel_data.cli.commands.workspaces_cmd.get_config")
    def test_show_empty_context(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp workspaces show with no active context."""
        mock_cm = MagicMock()
        mock_cm.get_active_context.return_value = ActiveContext()
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["workspaces", "show"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["project_id"] is None
        assert data["workspace_id"] is None
