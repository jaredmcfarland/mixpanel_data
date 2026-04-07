"""Unit tests for CLI context commands (show, switch).

Tests cover:
- T101: mp context show
- T101: mp context switch
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mixpanel_data._internal.config import ActiveContext, ProjectAlias
from mixpanel_data.cli.main import app
from mixpanel_data.cli.utils import ExitCode


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a CLI runner for testing commands."""
    return CliRunner()


class TestContextShow:
    """T101: Tests for mp context show."""

    @patch("mixpanel_data.cli.commands.context.get_config")
    def test_show_displays_active_context(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp context show outputs current credential/project/workspace."""
        mock_cm = MagicMock()
        mock_cm.get_active_context.return_value = ActiveContext(
            credential="demo-sa",
            project_id="3713224",
            workspace_id=3448413,
        )
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["context", "show"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["credential"] == "demo-sa"
        assert data["project_id"] == "3713224"
        assert data["workspace_id"] == 3448413

    @patch("mixpanel_data.cli.commands.context.get_config")
    def test_show_empty_context(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp context show with no active context."""
        mock_cm = MagicMock()
        mock_cm.get_active_context.return_value = ActiveContext()
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["context", "show"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["credential"] is None
        assert data["project_id"] is None
        assert data["workspace_id"] is None

    @patch("mixpanel_data.cli.commands.context.get_config")
    def test_show_table_format(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp context show --format table produces output."""
        mock_cm = MagicMock()
        mock_cm.get_active_context.return_value = ActiveContext(
            credential="demo-sa",
            project_id="3713224",
        )
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["context", "show", "--format", "table"])

        assert result.exit_code == 0
        assert "demo-sa" in result.stdout


class TestContextSwitch:
    """T101: Tests for mp context switch."""

    @patch("mixpanel_data.cli.commands.context.get_config")
    def test_switch_to_alias(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp context switch activates a project alias."""
        mock_cm = MagicMock()
        mock_cm.list_project_aliases.return_value = [
            ProjectAlias(
                name="ecom",
                project_id="3018488",
                credential="demo-sa",
                workspace_id=9999,
            ),
        ]
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["context", "switch", "ecom"])

        assert result.exit_code == 0
        mock_cm.set_active_credential.assert_called_once_with("demo-sa")
        mock_cm.set_active_project.assert_called_once_with("3018488", workspace_id=9999)
        data = json.loads(result.stdout)
        assert data["alias"] == "ecom"
        assert data["project_id"] == "3018488"
        assert data["credential"] == "demo-sa"
        assert data["workspace_id"] == 9999

    @patch("mixpanel_data.cli.commands.context.get_config")
    def test_switch_alias_no_credential(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp context switch with alias that has no credential binding."""
        mock_cm = MagicMock()
        mock_cm.list_project_aliases.return_value = [
            ProjectAlias(
                name="staging",
                project_id="5555",
                credential=None,
                workspace_id=None,
            ),
        ]
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["context", "switch", "staging"])

        assert result.exit_code == 0
        mock_cm.set_active_credential.assert_not_called()
        mock_cm.set_active_project.assert_called_once_with("5555", workspace_id=None)

    @patch("mixpanel_data.cli.commands.context.get_config")
    def test_switch_unknown_alias_exits_with_error(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp context switch with unknown alias exits with error."""
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

        result = cli_runner.invoke(app, ["context", "switch", "nonexistent"])

        assert result.exit_code == ExitCode.GENERAL_ERROR

    @patch("mixpanel_data.cli.commands.context.get_config")
    def test_switch_no_aliases_exits_with_error(
        self, mock_get_cfg: MagicMock, cli_runner: CliRunner
    ) -> None:
        """Test mp context switch with no aliases configured."""
        mock_cm = MagicMock()
        mock_cm.list_project_aliases.return_value = []
        mock_get_cfg.return_value = mock_cm

        result = cli_runner.invoke(app, ["context", "switch", "anything"])

        assert result.exit_code == ExitCode.GENERAL_ERROR
