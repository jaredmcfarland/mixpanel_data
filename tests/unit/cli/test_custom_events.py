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
    def test_update_by_id_with_hidden_returns_json(
        self, mock_get_ws: MagicMock
    ) -> None:
        """--id update with --hidden returns JSON and skips lookup."""
        mock_ws = MagicMock()
        mock_ws.update_custom_event.return_value = MagicMock(
            model_dump=lambda: {"name": "Activated", "hidden": True}
        )
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(
            app,
            ["custom-events", "update", "--id", "2044168", "--hidden"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["hidden"] is True
        # Verify the resolved id was passed through, no lookup attempted
        mock_ws.list_custom_events.assert_not_called()
        called_id, called_params = mock_ws.update_custom_event.call_args[0]
        assert called_id == 2044168
        assert called_params.hidden is True

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_update_by_id_with_description(self, mock_get_ws: MagicMock) -> None:
        """--description passes through to the params."""
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
                "--id",
                "2044168",
                "--description",
                "User activated",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["description"] == "User activated"

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_update_by_id_with_dropped(self, mock_get_ws: MagicMock) -> None:
        """--dropped flag passes dropped=True."""
        mock_ws = MagicMock()
        mock_ws.update_custom_event.return_value = MagicMock(
            model_dump=lambda: {"name": "OldEvent", "dropped": True}
        )
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(
            app,
            ["custom-events", "update", "--id", "123", "--dropped"],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["dropped"] is True

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_update_by_name_resolves_to_id(self, mock_get_ws: MagicMock) -> None:
        """--name resolves to the unique custom_event_id and passes it through."""
        from mixpanel_data.types import EventDefinition

        mock_ws = MagicMock()
        mock_ws.list_custom_events.return_value = [
            # An orphan with same name (customEventId=0) — must be filtered out
            EventDefinition(id=999, name="Activated", custom_event_id=0),
            # The real custom event
            EventDefinition(id=0, name="Activated", custom_event_id=2044168),
        ]
        mock_ws.update_custom_event.return_value = MagicMock(
            model_dump=lambda: {"name": "Activated", "verified": True}
        )
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(
            app,
            ["custom-events", "update", "--name", "Activated", "--verified"],
        )
        assert result.exit_code == 0
        called_id, called_params = mock_ws.update_custom_event.call_args[0]
        assert called_id == 2044168
        assert called_params.verified is True

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_update_errors_when_name_not_found(self, mock_get_ws: MagicMock) -> None:
        """--name with no matching custom event errors out."""
        mock_ws = MagicMock()
        mock_ws.list_custom_events.return_value = []
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(
            app,
            ["custom-events", "update", "--name", "Nonexistent", "--hidden"],
        )
        assert result.exit_code != 0

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_update_errors_when_name_is_ambiguous(self, mock_get_ws: MagicMock) -> None:
        """--name matching multiple real custom events errors out."""
        from mixpanel_data.types import EventDefinition

        mock_ws = MagicMock()
        mock_ws.list_custom_events.return_value = [
            EventDefinition(id=0, name="Duplicate", custom_event_id=111),
            EventDefinition(id=0, name="Duplicate", custom_event_id=222),
        ]
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(
            app,
            ["custom-events", "update", "--name", "Duplicate", "--hidden"],
        )
        assert result.exit_code != 0

    def test_update_errors_when_neither_id_nor_name(self) -> None:
        """Update without --id and without --name errors out."""
        result = runner.invoke(app, ["custom-events", "update", "--hidden"])
        assert result.exit_code != 0

    def test_update_errors_when_both_id_and_name(self) -> None:
        """Update with both --id and --name errors out."""
        result = runner.invoke(
            app,
            [
                "custom-events",
                "update",
                "--id",
                "123",
                "--name",
                "X",
                "--hidden",
            ],
        )
        assert result.exit_code != 0


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


class TestCustomEventsCreate:
    """Tests for mp custom-events create."""

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_create_with_single_alternative_returns_json(
        self, mock_get_ws: MagicMock
    ) -> None:
        """Successful create returns JSON with the new custom event."""
        from mixpanel_data.types import CustomEvent, CustomEventAlternative

        mock_ws = MagicMock()
        mock_ws.create_custom_event.return_value = CustomEvent(
            id=42,
            name="Metric Tree Opened",
            alternatives=[CustomEventAlternative(event="Enter room")],
        )
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(
            app,
            [
                "custom-events",
                "create",
                "--name",
                "Metric Tree Opened",
                "--alternative",
                "Enter room",
            ],
        )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == 42
        assert data["name"] == "Metric Tree Opened"

        called_params = mock_ws.create_custom_event.call_args[0][0]
        assert called_params.name == "Metric Tree Opened"
        assert called_params.alternatives == ["Enter room"]

    @patch("mixpanel_data.cli.commands.custom_events.get_workspace")
    def test_create_with_multiple_alternatives_preserves_order(
        self, mock_get_ws: MagicMock
    ) -> None:
        """--alternative is repeatable and preserves order."""
        from mixpanel_data.types import CustomEvent

        mock_ws = MagicMock()
        mock_ws.create_custom_event.return_value = CustomEvent(
            id=1, name="Page View", alternatives=[]
        )
        mock_get_ws.return_value = mock_ws

        result = runner.invoke(
            app,
            [
                "custom-events",
                "create",
                "--name",
                "Page View",
                "--alternative",
                "Home",
                "--alternative",
                "Product",
                "--alternative",
                "Checkout",
            ],
        )

        assert result.exit_code == 0
        called_params = mock_ws.create_custom_event.call_args[0][0]
        assert called_params.alternatives == ["Home", "Product", "Checkout"]

    def test_create_missing_name_errors(self) -> None:
        """Omitting --name causes typer to exit non-zero."""
        result = runner.invoke(app, ["custom-events", "create", "--alternative", "X"])
        assert result.exit_code != 0

    def test_create_missing_alternative_errors(self) -> None:
        """Omitting --alternative causes a non-zero exit (Pydantic validation error)."""
        result = runner.invoke(app, ["custom-events", "create", "--name", "X"])
        assert result.exit_code != 0
