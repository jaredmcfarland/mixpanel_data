"""Integration tests for jq filter functionality across CLI commands.

These tests verify end-to-end jq filtering behavior through the CLI,
including command invocation, output formatting, and error handling.

Tests cover:
- T068-T071: Integration tests for jq filter with various commands
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mixpanel_data.cli.main import app
from mixpanel_data.types import SQLResult


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a CLI runner for testing commands.

    Returns:
        CliRunner instance for invoking CLI commands.
    """
    return CliRunner()


@pytest.fixture
def mock_workspace() -> MagicMock:
    """Create a mock Workspace for testing.

    Returns:
        MagicMock configured to act as a Workspace.
    """
    return MagicMock()


class TestInspectEventsWithJq:
    """Integration tests for inspect events with --jq option (T069)."""

    def test_inspect_events_with_jq_filter(
        self, cli_runner: CliRunner, mock_workspace: MagicMock
    ) -> None:
        """Test that inspect events applies jq filter to output.

        Verifies end-to-end flow: command -> workspace call -> jq filter -> output.

        Args:
            cli_runner: CLI runner for invoking commands.
            mock_workspace: Mock workspace to provide test data.
        """
        # Setup mock - inspect events returns a list of event names
        mock_workspace.events.return_value = ["Sign Up", "Login", "Purchase"]

        with patch(
            "mixpanel_data.cli.commands.inspect.get_workspace",
            return_value=mock_workspace,
        ):
            result = cli_runner.invoke(
                app,
                ["inspect", "events", "--format", "json", "--jq", ".[0]"],
            )

        assert result.exit_code == 0
        # Should extract just the first event name
        output = result.stdout.strip()
        assert output == '"Sign Up"'

    def test_inspect_events_jq_extracts_all(
        self, cli_runner: CliRunner, mock_workspace: MagicMock
    ) -> None:
        """Test extracting all event names with jq.

        Args:
            cli_runner: CLI runner for invoking commands.
            mock_workspace: Mock workspace to provide test data.
        """
        mock_workspace.events.return_value = ["Event A", "Event B", "Event C"]

        with patch(
            "mixpanel_data.cli.commands.inspect.get_workspace",
            return_value=mock_workspace,
        ):
            result = cli_runner.invoke(
                app,
                ["inspect", "events", "--format", "json", "--jq", ".[]"],
            )

        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed == ["Event A", "Event B", "Event C"]

    def test_inspect_events_jq_length_filter(
        self, cli_runner: CliRunner, mock_workspace: MagicMock
    ) -> None:
        """Test counting events with jq length.

        Args:
            cli_runner: CLI runner for invoking commands.
            mock_workspace: Mock workspace to provide test data.
        """
        mock_workspace.events.return_value = ["A", "B", "C", "D", "E"]

        with patch(
            "mixpanel_data.cli.commands.inspect.get_workspace",
            return_value=mock_workspace,
        ):
            result = cli_runner.invoke(
                app,
                ["inspect", "events", "--format", "json", "--jq", "length"],
            )

        assert result.exit_code == 0
        assert result.stdout.strip() == "5"


class TestQuerySqlWithJq:
    """Integration tests for query sql with --jq option (T070)."""

    def test_query_sql_with_jq_filter(
        self, cli_runner: CliRunner, mock_workspace: MagicMock
    ) -> None:
        """Test that query sql applies jq filter to output.

        Args:
            cli_runner: CLI runner for invoking commands.
            mock_workspace: Mock workspace to provide test data.
        """
        # Mock SQL query result using SQLResult like existing tests
        mock_workspace.sql_rows.return_value = SQLResult(
            columns=["user_id", "email"],
            rows=[
                (1, "user1@example.com"),
                (2, "user2@example.com"),
                (3, "user3@example.com"),
            ],
        )

        with patch(
            "mixpanel_data.cli.commands.query.get_workspace",
            return_value=mock_workspace,
        ):
            result = cli_runner.invoke(
                app,
                [
                    "query",
                    "sql",
                    "SELECT * FROM users",
                    "--format",
                    "json",
                    "--jq",
                    ".[].email",
                ],
            )

        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed == [
            "user1@example.com",
            "user2@example.com",
            "user3@example.com",
        ]

    def test_query_sql_jq_length(
        self, cli_runner: CliRunner, mock_workspace: MagicMock
    ) -> None:
        """Test using jq length filter on query results.

        Args:
            cli_runner: CLI runner for invoking commands.
            mock_workspace: Mock workspace to provide test data.
        """
        mock_workspace.sql_rows.return_value = SQLResult(
            columns=["id"],
            rows=[(1,), (2,), (3,), (4,), (5,)],
        )

        with patch(
            "mixpanel_data.cli.commands.query.get_workspace",
            return_value=mock_workspace,
        ):
            result = cli_runner.invoke(
                app,
                [
                    "query",
                    "sql",
                    "SELECT id FROM events",
                    "--format",
                    "json",
                    "--jq",
                    "length",
                ],
            )

        assert result.exit_code == 0
        assert result.stdout.strip() == "5"


class TestJqWithIncompatibleFormat:
    """Integration tests for --jq with incompatible formats (T071)."""

    def test_jq_with_table_format_fails(
        self, cli_runner: CliRunner, mock_workspace: MagicMock
    ) -> None:
        """Test that --jq with --format table produces error.

        Args:
            cli_runner: CLI runner for invoking commands.
            mock_workspace: Mock workspace to provide test data.
        """
        mock_workspace.events.return_value = ["Test"]

        with patch(
            "mixpanel_data.cli.commands.inspect.get_workspace",
            return_value=mock_workspace,
        ):
            result = cli_runner.invoke(
                app,
                ["inspect", "events", "--format", "table", "--jq", "."],
            )

        # Should fail with exit code 3 (INVALID_ARGS)
        assert result.exit_code == 3
        # Error should mention json/jsonl requirement
        combined = result.stdout + (result.stderr or "")
        assert "json" in combined.lower()

    def test_jq_with_csv_format_fails(
        self, cli_runner: CliRunner, mock_workspace: MagicMock
    ) -> None:
        """Test that --jq with --format csv produces error.

        Args:
            cli_runner: CLI runner for invoking commands.
            mock_workspace: Mock workspace to provide test data.
        """
        mock_workspace.events.return_value = ["Test"]

        with patch(
            "mixpanel_data.cli.commands.inspect.get_workspace",
            return_value=mock_workspace,
        ):
            result = cli_runner.invoke(
                app,
                ["inspect", "events", "--format", "csv", "--jq", "."],
            )

        assert result.exit_code == 3

    def test_jq_with_plain_format_fails(
        self, cli_runner: CliRunner, mock_workspace: MagicMock
    ) -> None:
        """Test that --jq with --format plain produces error.

        Args:
            cli_runner: CLI runner for invoking commands.
            mock_workspace: Mock workspace to provide test data.
        """
        mock_workspace.events.return_value = ["Test"]

        with patch(
            "mixpanel_data.cli.commands.inspect.get_workspace",
            return_value=mock_workspace,
        ):
            result = cli_runner.invoke(
                app,
                ["inspect", "events", "--format", "plain", "--jq", "."],
            )

        assert result.exit_code == 3


class TestJqSyntaxErrorsIntegration:
    """Integration tests for jq syntax error handling."""

    def test_invalid_jq_syntax_fails(
        self, cli_runner: CliRunner, mock_workspace: MagicMock
    ) -> None:
        """Test that invalid jq syntax produces clear error.

        Args:
            cli_runner: CLI runner for invoking commands.
            mock_workspace: Mock workspace to provide test data.
        """
        mock_workspace.events.return_value = ["Test"]

        with patch(
            "mixpanel_data.cli.commands.inspect.get_workspace",
            return_value=mock_workspace,
        ):
            result = cli_runner.invoke(
                app,
                ["inspect", "events", "--format", "json", "--jq", ".name |"],
            )

        assert result.exit_code == 3
        # Error output should mention jq
        combined_output = result.stdout + (result.stderr or "")
        assert "jq" in combined_output.lower()

    def test_unknown_jq_function_fails(
        self, cli_runner: CliRunner, mock_workspace: MagicMock
    ) -> None:
        """Test that unknown jq function produces error.

        Args:
            cli_runner: CLI runner for invoking commands.
            mock_workspace: Mock workspace to provide test data.
        """
        mock_workspace.events.return_value = ["Test"]

        with patch(
            "mixpanel_data.cli.commands.inspect.get_workspace",
            return_value=mock_workspace,
        ):
            result = cli_runner.invoke(
                app,
                ["inspect", "events", "--format", "json", "--jq", "nonexistent_func"],
            )

        assert result.exit_code == 3


class TestJqWithJsonlFormat:
    """Integration tests for --jq with jsonl format."""

    def test_jq_with_jsonl_format(
        self, cli_runner: CliRunner, mock_workspace: MagicMock
    ) -> None:
        """Test that --jq works with jsonl format.

        Args:
            cli_runner: CLI runner for invoking commands.
            mock_workspace: Mock workspace to provide test data.
        """
        mock_workspace.events.return_value = ["Event A", "Event B"]

        with patch(
            "mixpanel_data.cli.commands.inspect.get_workspace",
            return_value=mock_workspace,
        ):
            result = cli_runner.invoke(
                app,
                ["inspect", "events", "--format", "jsonl", "--jq", ".[0]"],
            )

        assert result.exit_code == 0
        parsed = json.loads(result.stdout.strip())
        assert parsed == "Event A"


class TestJqEmptyResultsIntegration:
    """Integration tests for jq filter with empty results."""

    def test_jq_select_no_matches(
        self, cli_runner: CliRunner, mock_workspace: MagicMock
    ) -> None:
        """Test that jq select with no matches returns empty array.

        Args:
            cli_runner: CLI runner for invoking commands.
            mock_workspace: Mock workspace to provide test data.
        """
        mock_workspace.events.return_value = ["A", "B"]

        with patch(
            "mixpanel_data.cli.commands.inspect.get_workspace",
            return_value=mock_workspace,
        ):
            result = cli_runner.invoke(
                app,
                [
                    "inspect",
                    "events",
                    "--format",
                    "json",
                    "--jq",
                    '.[] | select(. == "Z")',
                ],
            )

        assert result.exit_code == 0
        assert result.stdout.strip() == "[]"
