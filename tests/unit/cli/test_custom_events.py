# ruff: noqa: ARG001, ARG005
"""Tests for custom-events CLI commands.

Tests cover all custom-events subcommands:
- list: List all custom events
- update: Update a custom event definition
- delete: Delete a custom event
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import typer.testing

from mixpanel_data.cli.main import app

runner = typer.testing.CliRunner()


class TestCustomEventsList:
    """Tests for mp custom-events list."""

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_returns_json_list(self, mock_get_ws: MagicMock) -> None:
        """Successful list returns JSON list of custom events."""
        mock_ws = MagicMock()
        mock_ws.list_custom_events.return_value = [
            MagicMock(model_dump=lambda: {"name": "Activated", "hidden": False}),
            MagicMock(model_dump=lambda: {"name": "Churned", "hidden": False}),
        ]
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(app, ["custom-events", "list"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["name"] == "Activated"

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_empty_list(self, mock_get_ws: MagicMock) -> None:
        """Empty list returns empty JSON array."""
        mock_ws = MagicMock()
        mock_ws.list_custom_events.return_value = []
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(app, ["custom-events", "list"])
        assert result.exit_code == 0
        assert json.loads(result.stdout) == []


class TestCustomEventsUpdate:
    """Tests for mp custom-events update."""

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_update_with_hidden_returns_json(self, mock_get_ws: MagicMock) -> None:
        """Successful update with --hidden returns JSON."""
        mock_ws = MagicMock()
        mock_ws.update_custom_event.return_value = MagicMock(
            model_dump=lambda: {"name": "Activated", "hidden": True}
        )
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(
            app,
            ["custom-events", "update", "--name", "Activated", "--hidden"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["hidden"] is True

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_update_with_description(self, mock_get_ws: MagicMock) -> None:
        """Update with --description passes it through."""
        mock_ws = MagicMock()
        mock_ws.update_custom_event.return_value = MagicMock(
            model_dump=lambda: {"name": "Activated", "description": "User activated"}
        )
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(
            app,
            [
                "custom-events",
                "update",
                "--name",
                "Activated",
                "--description",
                "User activated",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["description"] == "User activated"

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_update_with_dropped(self, mock_get_ws: MagicMock) -> None:
        """Update with --dropped flag passes dropped=True."""
        mock_ws = MagicMock()
        mock_ws.update_custom_event.return_value = MagicMock(
            model_dump=lambda: {"name": "OldEvent", "dropped": True}
        )
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(
            app,
            ["custom-events", "update", "--name", "OldEvent", "--dropped"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["dropped"] is True


class TestCustomEventsDelete:
    """Tests for mp custom-events delete."""

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_delete_succeeds(self, mock_get_ws: MagicMock) -> None:
        """Successful delete exits with code 0."""
        mock_ws = MagicMock()
        mock_ws.delete_custom_event.return_value = None
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(app, ["custom-events", "delete", "--name", "OldEvent"])
        assert result.exit_code == 0
        mock_ws.delete_custom_event.assert_called_once_with("OldEvent")

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_delete_calls_workspace(self, mock_get_ws: MagicMock) -> None:
        """Delete command invokes workspace.delete_custom_event with the name."""
        mock_ws = MagicMock()
        mock_ws.delete_custom_event.return_value = None
        mock_get_ws.return_value = mock_ws

        runner.invoke(app, ["custom-events", "delete", "--name", "TestEvent"])
        mock_ws.delete_custom_event.assert_called_once_with("TestEvent")
