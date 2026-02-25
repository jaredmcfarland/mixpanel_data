"""Tests for the context workflow tool.

These tests verify the context tool correctly aggregates project landscape
for the Operational Analytics Loop workflow.
"""

from unittest.mock import MagicMock


class TestContextToolRegistration:
    """Tests for context tool registration."""

    def test_tool_registered(self, registered_tool_names: list[str]) -> None:
        """Context tool should be registered."""
        assert "context" in registered_tool_names


class TestContextToolBasic:
    """Tests for basic context tool functionality."""

    def test_context_returns_required_fields(self, mock_context: MagicMock) -> None:
        """Context should return all required fields."""
        from mp_mcp.tools.workflows.context import context

        result = context(mock_context)  # type: ignore[operator]

        assert "project" in result
        assert "events" in result
        assert "properties" in result
        assert "funnels" in result
        assert "cohorts" in result
        assert "bookmarks" in result
        assert "date_range" in result

    def test_context_project_structure(self, mock_context: MagicMock) -> None:
        """Context should return valid project structure."""
        from mp_mcp.tools.workflows.context import context

        result = context(mock_context)  # type: ignore[operator]

        assert isinstance(result["project"], dict)
        assert "project_id" in result["project"] or "id" in result["project"]

    def test_context_events_summary(self, mock_context: MagicMock) -> None:
        """Context should return events summary with total and top_events."""
        from mp_mcp.tools.workflows.context import context

        result = context(mock_context)  # type: ignore[operator]

        assert "total" in result["events"]
        assert "top_events" in result["events"]
        assert isinstance(result["events"]["top_events"], list)

    def test_context_funnels_list(self, mock_context: MagicMock) -> None:
        """Context should return list of funnel summaries."""
        from mp_mcp.tools.workflows.context import context

        result = context(mock_context)  # type: ignore[operator]

        assert isinstance(result["funnels"], list)

    def test_context_cohorts_list(self, mock_context: MagicMock) -> None:
        """Context should return list of cohort summaries."""
        from mp_mcp.tools.workflows.context import context

        result = context(mock_context)  # type: ignore[operator]

        assert isinstance(result["cohorts"], list)

    def test_context_bookmarks_summary(self, mock_context: MagicMock) -> None:
        """Context should return bookmarks summary."""
        from mp_mcp.tools.workflows.context import context

        result = context(mock_context)  # type: ignore[operator]

        assert "total" in result["bookmarks"]


class TestContextWithSchemas:
    """Tests for context tool with schemas option."""

    def test_context_without_schemas(self, mock_context: MagicMock) -> None:
        """Context should not include schemas by default."""
        from mp_mcp.tools.workflows.context import context

        result = context(mock_context)  # type: ignore[operator]

        assert result.get("schemas") is None

    def test_context_with_schemas(self, mock_context: MagicMock) -> None:
        """Context should include schemas when requested."""
        from mp_mcp.tools.workflows.context import context

        result = context(mock_context, include_schemas=True)  # type: ignore[operator]

        assert "schemas" in result
        assert result["schemas"] is not None


class TestContextErrorHandling:
    """Tests for context tool error handling."""

    def test_context_handles_events_error(self, mock_context: MagicMock) -> None:
        """Context should handle errors from events() gracefully."""
        from mp_mcp.tools.workflows.context import context

        # Make events() raise an exception
        mock_context.lifespan_context["workspace"].events.side_effect = Exception(
            "API error"
        )

        result = context(mock_context)  # type: ignore[operator]

        # Should still return valid structure
        assert "events" in result
        # Events should have fallback values
        assert result["events"]["total"] == 0
        assert result["events"]["top_events"] == []

    def test_context_handles_funnels_error(self, mock_context: MagicMock) -> None:
        """Context should handle errors from funnels() gracefully."""
        from mp_mcp.tools.workflows.context import context

        mock_context.lifespan_context["workspace"].funnels.side_effect = Exception(
            "API error"
        )

        result = context(mock_context)  # type: ignore[operator]

        # Should still return valid structure with empty funnels
        assert "funnels" in result
        assert result["funnels"] == []

    def test_context_handles_cohorts_error(self, mock_context: MagicMock) -> None:
        """Context should handle errors from cohorts() gracefully."""
        from mp_mcp.tools.workflows.context import context

        mock_context.lifespan_context["workspace"].cohorts.side_effect = Exception(
            "API error"
        )

        result = context(mock_context)  # type: ignore[operator]

        # Should still return valid structure with empty cohorts
        assert "cohorts" in result
        assert result["cohorts"] == []

    def test_context_handles_partial_failures(self, mock_context: MagicMock) -> None:
        """Context should return partial data when some calls fail."""
        from mp_mcp.tools.workflows.context import context

        # Make cohorts and bookmarks fail
        mock_context.lifespan_context["workspace"].cohorts.side_effect = Exception(
            "API error"
        )
        mock_context.lifespan_context[
            "workspace"
        ].list_bookmarks.side_effect = Exception("API error")

        result = context(mock_context)  # type: ignore[operator]

        # Should still have events and funnels
        assert "events" in result
        assert result["events"]["total"] > 0
        assert "funnels" in result
        # Cohorts and bookmarks should have fallback values
        assert result["cohorts"] == []
        assert result["bookmarks"]["total"] == 0


class TestContextHelpers:
    """Tests for context tool helper functions."""

    def test_gather_events(self, mock_context: MagicMock) -> None:
        """_gather_events should return EventsSummary."""
        from mp_mcp.tools.workflows.context import _gather_events

        result = _gather_events(mock_context)

        assert result.total >= 0
        assert isinstance(result.top_events, list)

    def test_gather_funnels(self, mock_context: MagicMock) -> None:
        """_gather_funnels_cohorts should return funnel and cohort summaries."""
        from mp_mcp.tools.workflows.context import _gather_funnels_cohorts

        funnels, cohorts = _gather_funnels_cohorts(mock_context)

        assert isinstance(funnels, list)
        assert isinstance(cohorts, list)

    def test_gather_bookmarks(self, mock_context: MagicMock) -> None:
        """_gather_bookmarks should return BookmarksSummary."""
        from mp_mcp.tools.workflows.context import _gather_bookmarks

        result = _gather_bookmarks(mock_context)

        assert result.total >= 0
        assert isinstance(result.by_type, dict)
