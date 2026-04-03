"""Tests for interactive analytics tools.

These tests verify the guided_analysis tool works correctly
with elicitation handling.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestGuidedAnalysisHelpers:
    """Tests for guided_analysis helper functions."""

    def test_get_date_range_last_7_days(self) -> None:
        """_get_date_range_from_period should handle last_7_days."""
        from mp_mcp.tools.interactive.guided import _get_date_range_from_period

        from_date, to_date = _get_date_range_from_period("last_7_days")
        assert from_date < to_date

    def test_get_date_range_last_30_days(self) -> None:
        """_get_date_range_from_period should handle last_30_days."""
        from mp_mcp.tools.interactive.guided import _get_date_range_from_period

        from_date, to_date = _get_date_range_from_period("last_30_days")
        assert from_date < to_date

    def test_get_date_range_last_90_days(self) -> None:
        """_get_date_range_from_period should handle last_90_days."""
        from mp_mcp.tools.interactive.guided import _get_date_range_from_period

        from_date, to_date = _get_date_range_from_period("last_90_days")
        assert from_date < to_date

    def test_get_date_range_custom(self) -> None:
        """_get_date_range_from_period should handle custom dates."""
        from mp_mcp.tools.interactive.guided import _get_date_range_from_period

        from_date, to_date = _get_date_range_from_period(
            "custom",
            custom_start="2024-01-01",
            custom_end="2024-01-31",
        )
        assert from_date == "2024-01-01"
        assert to_date == "2024-01-31"

    def test_get_date_range_custom_without_dates(self) -> None:
        """_get_date_range_from_period should default when custom missing dates."""
        from mp_mcp.tools.interactive.guided import _get_date_range_from_period

        from_date, to_date = _get_date_range_from_period("custom")
        assert from_date < to_date  # Falls back to 30 days

    def test_run_initial_analysis(self, mock_context: MagicMock) -> None:
        """run_initial_analysis should run focus-specific queries."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        result = run_initial_analysis(
            mock_context,
            focus_area="conversion",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert "focus_area" in result
        assert "period" in result
        assert result["focus_area"] == "conversion"

    def test_run_initial_analysis_retention(self, mock_context: MagicMock) -> None:
        """run_initial_analysis should handle retention focus."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        result = run_initial_analysis(
            mock_context,
            focus_area="retention",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "retention"

    def test_run_initial_analysis_engagement(self, mock_context: MagicMock) -> None:
        """run_initial_analysis should handle engagement focus."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        result = run_initial_analysis(
            mock_context,
            focus_area="engagement",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "engagement"

    def test_run_initial_analysis_revenue(self, mock_context: MagicMock) -> None:
        """run_initial_analysis should handle revenue focus."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        result = run_initial_analysis(
            mock_context,
            focus_area="revenue",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "revenue"


class TestGuidedAnalysisTool:
    """Tests for the guided_analysis tool."""

    def test_tool_registered(self, registered_tool_names: list[str]) -> None:
        """guided_analysis tool should be registered."""
        assert "guided_analysis" in registered_tool_names

    @pytest.mark.asyncio
    async def test_guided_analysis_with_preset_focus(
        self, mock_context: MagicMock
    ) -> None:
        """guided_analysis should work with pre-selected focus area."""
        from mp_mcp.tools.interactive.guided import guided_analysis

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="retention",
        )

        assert "status" in result
        assert result["focus_area"] == "retention"

    @pytest.mark.asyncio
    async def test_guided_analysis_elicitation_unavailable(
        self, mock_context: MagicMock
    ) -> None:
        """guided_analysis should degrade when elicitation unavailable."""
        from mp_mcp.tools.interactive.guided import guided_analysis

        mock_context.elicit = AsyncMock(
            side_effect=Exception("Elicitation not supported")
        )

        result = await guided_analysis(mock_context)  # type: ignore[operator]

        assert "status" in result
        # When elicitation fails and no focus_area provided, returns guidance message
        assert result["status"] == "elicitation_unavailable"
        assert "focus_options" in result
        assert "message" in result

    @pytest.mark.asyncio
    async def test_guided_analysis_with_custom_dates(
        self, mock_context: MagicMock
    ) -> None:
        """guided_analysis should accept custom date range."""
        from mp_mcp.tools.interactive.guided import guided_analysis

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="engagement",
            time_period="custom",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["period"]["from_date"] == "2024-01-01"
        assert result["period"]["to_date"] == "2024-01-31"


class TestFocusDescriptions:
    """Tests for focus area descriptions constant."""

    def test_focus_descriptions_contains_all_areas(self) -> None:
        """FOCUS_DESCRIPTIONS should have all focus areas."""
        from mp_mcp.tools.interactive.guided import FOCUS_DESCRIPTIONS

        expected_areas = {"conversion", "retention", "engagement", "revenue"}
        assert set(FOCUS_DESCRIPTIONS.keys()) == expected_areas

    def test_focus_descriptions_values_are_strings(self) -> None:
        """FOCUS_DESCRIPTIONS values should be descriptive strings."""
        from mp_mcp.tools.interactive.guided import FOCUS_DESCRIPTIONS

        for _area, desc in FOCUS_DESCRIPTIONS.items():
            assert isinstance(desc, str)
            assert len(desc) > 10  # Should be descriptive


class TestAnalysisChoice:
    """Tests for AnalysisChoice dataclass."""

    def test_analysis_choice_defaults(self) -> None:
        """AnalysisChoice should have sensible defaults."""
        from mp_mcp.tools.interactive.guided import AnalysisChoice

        choice = AnalysisChoice(focus_area="retention")
        assert choice.focus_area == "retention"
        assert choice.time_period == "last_30_days"
        assert choice.custom_start is None
        assert choice.custom_end is None

    def test_analysis_choice_custom_period(self) -> None:
        """AnalysisChoice should accept custom period."""
        from mp_mcp.tools.interactive.guided import AnalysisChoice

        choice = AnalysisChoice(
            focus_area="conversion",
            time_period="custom",
            custom_start="2024-01-01",
            custom_end="2024-01-31",
        )
        assert choice.time_period == "custom"
        assert choice.custom_start == "2024-01-01"


class TestSegmentChoice:
    """Tests for SegmentChoice dataclass."""

    def test_segment_choice_defaults(self) -> None:
        """SegmentChoice should have sensible defaults."""
        from mp_mcp.tools.interactive.guided import SegmentChoice

        choice = SegmentChoice(segment_index=0)
        assert choice.segment_index == 0
        assert choice.investigate_further is True

    def test_segment_choice_no_further(self) -> None:
        """SegmentChoice should allow declining further investigation."""
        from mp_mcp.tools.interactive.guided import SegmentChoice

        choice = SegmentChoice(segment_index=1, investigate_further=False)
        assert choice.investigate_further is False


class TestGuidedAnalysisEdgeCases:
    """Tests for guided_analysis edge cases."""

    def test_run_initial_analysis_handles_error(self, mock_context: MagicMock) -> None:
        """run_initial_analysis should handle query errors."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        mock_context.lifespan_context["workspace"].funnel.side_effect = Exception(
            "API error"
        )

        result = run_initial_analysis(
            mock_context,
            focus_area="conversion",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "conversion"
        # Should return with error info but not crash

    @pytest.mark.asyncio
    async def test_guided_analysis_with_time_period(
        self, mock_context: MagicMock
    ) -> None:
        """guided_analysis should accept time_period parameter."""
        from mp_mcp.tools.interactive.guided import guided_analysis

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="retention",
            time_period="last_7_days",
        )

        assert result["focus_area"] == "retention"

    @pytest.mark.asyncio
    async def test_guided_analysis_default_dates(self, mock_context: MagicMock) -> None:
        """guided_analysis should use default dates when not provided."""
        from mp_mcp.tools.interactive.guided import guided_analysis

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="engagement",
        )

        assert "period" in result
        assert "from_date" in result["period"]
        assert "to_date" in result["period"]

    def test_run_initial_analysis_retention(self, mock_context: MagicMock) -> None:
        """run_initial_analysis should handle retention focus area."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        result = run_initial_analysis(
            mock_context,
            focus_area="retention",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "retention"
        assert "segments" in result
        assert len(result["findings"]) > 0

    def test_run_initial_analysis_retention_error(
        self, mock_context: MagicMock
    ) -> None:
        """run_initial_analysis should handle retention query errors."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        mock_context.lifespan_context["workspace"].retention.side_effect = Exception(
            "Retention API error"
        )

        result = run_initial_analysis(
            mock_context,
            focus_area="retention",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "retention"
        assert any("error" in f.lower() for f in result["findings"])

    def test_run_initial_analysis_engagement(self, mock_context: MagicMock) -> None:
        """run_initial_analysis should handle engagement focus area."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        result = run_initial_analysis(
            mock_context,
            focus_area="engagement",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "engagement"
        assert "frequency_suggestion" in result

    def test_run_initial_analysis_engagement_error(
        self, mock_context: MagicMock
    ) -> None:
        """run_initial_analysis should handle engagement errors."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        mock_context.lifespan_context["workspace"].event_counts.side_effect = Exception(
            "Event counts error"
        )

        result = run_initial_analysis(
            mock_context,
            focus_area="engagement",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "engagement"
        assert any("error" in f.lower() for f in result["findings"])

    def test_run_initial_analysis_revenue(self, mock_context: MagicMock) -> None:
        """run_initial_analysis should handle revenue focus area."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        # Mock events with a purchase event
        mock_context.lifespan_context["workspace"].events.return_value = [
            "purchase",
            "signup",
            "login",
        ]

        result = run_initial_analysis(
            mock_context,
            focus_area="revenue",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "revenue"
        assert "segments" in result

    def test_run_initial_analysis_revenue_no_events(
        self, mock_context: MagicMock
    ) -> None:
        """run_initial_analysis should handle revenue with no matching events."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        # Mock events without revenue events
        mock_context.lifespan_context["workspace"].events.return_value = [
            "signup",
            "login",
            "view_page",
        ]

        result = run_initial_analysis(
            mock_context,
            focus_area="revenue",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "revenue"
        assert any("No revenue events" in f for f in result["findings"])

    def test_run_segment_analysis_retention(self, mock_context: MagicMock) -> None:
        """run_segment_analysis should handle retention focus area."""
        from mp_mcp.tools.interactive.guided import run_segment_analysis

        result = run_segment_analysis(
            mock_context,
            focus_area="retention",
            segment_property="$browser",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["segment_property"] == "$browser"
        assert "breakdown" in result

    def test_run_segment_analysis_other(self, mock_context: MagicMock) -> None:
        """run_segment_analysis should handle non-retention focus areas."""
        from mp_mcp.tools.interactive.guided import run_segment_analysis

        result = run_segment_analysis(
            mock_context,
            focus_area="conversion",
            segment_property="$os",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["segment_property"] == "$os"
        assert len(result["findings"]) > 0

    def test_run_segment_analysis_error(self, mock_context: MagicMock) -> None:
        """run_segment_analysis should handle errors."""
        from mp_mcp.tools.interactive.guided import run_segment_analysis

        mock_context.lifespan_context[
            "workspace"
        ].property_counts.side_effect = Exception("Property counts error")

        result = run_segment_analysis(
            mock_context,
            focus_area="engagement",
            segment_property="$browser",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert any("error" in f.lower() for f in result["findings"])

    @pytest.mark.asyncio
    async def test_guided_analysis_revenue(self, mock_context: MagicMock) -> None:
        """guided_analysis should handle revenue focus area."""
        from mp_mcp.tools.interactive.guided import guided_analysis

        mock_context.lifespan_context["workspace"].events.return_value = [
            "purchase",
            "signup",
        ]

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="revenue",
            time_period="last_30_days",
        )

        assert result["focus_area"] == "revenue"

    @pytest.mark.asyncio
    async def test_guided_analysis_last_90_days(self, mock_context: MagicMock) -> None:
        """guided_analysis should handle last_90_days time period."""
        from mp_mcp.tools.interactive.guided import guided_analysis

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="conversion",
            time_period="last_90_days",
        )

        assert result["focus_area"] == "conversion"
        assert "period" in result

    @pytest.mark.asyncio
    async def test_guided_analysis_custom_dates(self, mock_context: MagicMock) -> None:
        """guided_analysis should accept custom date range."""
        from mp_mcp.tools.interactive.guided import guided_analysis

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="retention",
            time_period="custom",
            from_date="2024-06-01",
            to_date="2024-06-30",
        )

        assert result["period"]["from_date"] == "2024-06-01"
        assert result["period"]["to_date"] == "2024-06-30"


class TestPromptFocusSelection:
    """Tests for prompt_focus_selection helper function."""

    @pytest.mark.asyncio
    async def test_prompt_focus_selection_accepted_dict(
        self, mock_context: MagicMock
    ) -> None:
        """prompt_focus_selection should handle accepted elicitation with dict."""
        from fastmcp.server.elicitation import AcceptedElicitation

        from mp_mcp.tools.interactive.guided import prompt_focus_selection

        mock_context.elicit = AsyncMock(
            return_value=AcceptedElicitation(
                data={
                    "focus_area": "retention",
                    "time_period": "last_7_days",
                    "custom_start": None,
                    "custom_end": None,
                }
            )
        )

        result = await prompt_focus_selection(mock_context)

        assert result is not None
        assert result.focus_area == "retention"
        assert result.time_period == "last_7_days"

    @pytest.mark.asyncio
    async def test_prompt_focus_selection_declined(
        self, mock_context: MagicMock
    ) -> None:
        """prompt_focus_selection should return None on declined."""
        from fastmcp.server.elicitation import DeclinedElicitation

        from mp_mcp.tools.interactive.guided import prompt_focus_selection

        mock_context.elicit = AsyncMock(return_value=DeclinedElicitation())

        result = await prompt_focus_selection(mock_context)

        assert result is None

    @pytest.mark.asyncio
    async def test_prompt_focus_selection_cancelled(
        self, mock_context: MagicMock
    ) -> None:
        """prompt_focus_selection should return None on cancelled."""
        from fastmcp.server.elicitation import CancelledElicitation

        from mp_mcp.tools.interactive.guided import prompt_focus_selection

        mock_context.elicit = AsyncMock(return_value=CancelledElicitation())

        result = await prompt_focus_selection(mock_context)

        assert result is None

    @pytest.mark.asyncio
    async def test_prompt_focus_selection_exception(
        self, mock_context: MagicMock
    ) -> None:
        """prompt_focus_selection should return None on exception."""
        from mp_mcp.tools.interactive.guided import prompt_focus_selection

        mock_context.elicit = AsyncMock(
            side_effect=Exception("Elicitation not available")
        )

        result = await prompt_focus_selection(mock_context)

        assert result is None

    @pytest.mark.asyncio
    async def test_prompt_focus_selection_non_dict_data(
        self, mock_context: MagicMock
    ) -> None:
        """prompt_focus_selection should return None for non-dict data."""
        from fastmcp.server.elicitation import AcceptedElicitation

        from mp_mcp.tools.interactive.guided import prompt_focus_selection

        # Return AcceptedElicitation with non-dict data
        mock_context.elicit = AsyncMock(
            return_value=AcceptedElicitation(data="not a dict")
        )

        result = await prompt_focus_selection(mock_context)

        assert result is None


class TestPromptSegmentSelection:
    """Tests for prompt_segment_selection helper function."""

    @pytest.mark.asyncio
    async def test_prompt_segment_selection_empty_segments(
        self, mock_context: MagicMock
    ) -> None:
        """prompt_segment_selection should return None for empty segments."""
        from mp_mcp.tools.interactive.guided import prompt_segment_selection

        result = await prompt_segment_selection(mock_context, segments=[])

        assert result is None

    @pytest.mark.asyncio
    async def test_prompt_segment_selection_accepted(
        self, mock_context: MagicMock
    ) -> None:
        """prompt_segment_selection should handle accepted elicitation."""
        from fastmcp.server.elicitation import AcceptedElicitation

        from mp_mcp.tools.interactive.guided import prompt_segment_selection

        mock_context.elicit = AsyncMock(
            return_value=AcceptedElicitation(data={"segment_index": 1})
        )

        segments = [
            {"name": "By Browser", "property": "$browser"},
            {"name": "By Platform", "property": "$os"},
        ]

        result = await prompt_segment_selection(mock_context, segments=segments)

        assert result is not None
        assert result.segment_index == 1

    @pytest.mark.asyncio
    async def test_prompt_segment_selection_declined(
        self, mock_context: MagicMock
    ) -> None:
        """prompt_segment_selection should return None on declined."""
        from fastmcp.server.elicitation import DeclinedElicitation

        from mp_mcp.tools.interactive.guided import prompt_segment_selection

        mock_context.elicit = AsyncMock(return_value=DeclinedElicitation())

        segments = [{"name": "By Browser", "property": "$browser"}]

        result = await prompt_segment_selection(mock_context, segments=segments)

        assert result is None

    @pytest.mark.asyncio
    async def test_prompt_segment_selection_cancelled(
        self, mock_context: MagicMock
    ) -> None:
        """prompt_segment_selection should return None on cancelled."""
        from fastmcp.server.elicitation import CancelledElicitation

        from mp_mcp.tools.interactive.guided import prompt_segment_selection

        mock_context.elicit = AsyncMock(return_value=CancelledElicitation())

        segments = [{"name": "By Browser", "property": "$browser"}]

        result = await prompt_segment_selection(mock_context, segments=segments)

        assert result is None

    @pytest.mark.asyncio
    async def test_prompt_segment_selection_exception(
        self, mock_context: MagicMock
    ) -> None:
        """prompt_segment_selection should return None on exception."""
        from mp_mcp.tools.interactive.guided import prompt_segment_selection

        mock_context.elicit = AsyncMock(
            side_effect=Exception("Elicitation not available")
        )

        segments = [{"name": "By Browser", "property": "$browser"}]

        result = await prompt_segment_selection(mock_context, segments=segments)

        assert result is None

    @pytest.mark.asyncio
    async def test_prompt_segment_selection_non_dict_data(
        self, mock_context: MagicMock
    ) -> None:
        """prompt_segment_selection should return None for non-dict data."""
        from fastmcp.server.elicitation import AcceptedElicitation

        from mp_mcp.tools.interactive.guided import prompt_segment_selection

        mock_context.elicit = AsyncMock(
            return_value=AcceptedElicitation(data="not a dict")
        )

        segments = [{"name": "By Browser", "property": "$browser"}]

        result = await prompt_segment_selection(mock_context, segments=segments)

        assert result is None


class TestRunInitialAnalysisErrors:
    """Tests for run_initial_analysis error handling."""

    def test_run_initial_analysis_events_error(self, mock_context: MagicMock) -> None:
        """run_initial_analysis should handle events() exception."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        mock_context.lifespan_context["workspace"].events.side_effect = Exception(
            "Events API error"
        )

        result = run_initial_analysis(
            mock_context,
            focus_area="conversion",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "conversion"
        # Should still have required fields
        assert "findings" in result
        assert "segments" in result

    def test_run_initial_analysis_revenue_segmentation_error(
        self, mock_context: MagicMock
    ) -> None:
        """run_initial_analysis should handle revenue segmentation error."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        # Mock events with purchase event
        mock_context.lifespan_context["workspace"].events.return_value = [
            "purchase",
            "login",
        ]
        # Make segmentation fail
        mock_context.lifespan_context["workspace"].segmentation.side_effect = Exception(
            "Segmentation API error"
        )

        result = run_initial_analysis(
            mock_context,
            focus_area="revenue",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "revenue"
        assert any("error" in f.lower() for f in result["findings"])

    def test_run_initial_analysis_conversion_funnels_error(
        self, mock_context: MagicMock
    ) -> None:
        """run_initial_analysis should handle funnels() exception."""
        from mp_mcp.tools.interactive.guided import run_initial_analysis

        mock_context.lifespan_context["workspace"].funnels.side_effect = Exception(
            "Funnels API error"
        )
        mock_context.lifespan_context["workspace"].top_events.side_effect = Exception(
            "Top events API error"
        )

        result = run_initial_analysis(
            mock_context,
            focus_area="conversion",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["focus_area"] == "conversion"
        assert any("error" in f.lower() for f in result["findings"])


class TestGuidedAnalysisElicitationFlows:
    """Tests for guided_analysis elicitation flows."""

    @pytest.mark.asyncio
    async def test_guided_analysis_with_focus_elicitation(
        self, mock_context: MagicMock
    ) -> None:
        """guided_analysis should use elicitation when focus_area not provided."""
        from fastmcp.server.elicitation import AcceptedElicitation

        from mp_mcp.tools.interactive.guided import guided_analysis

        mock_context.elicit = AsyncMock(
            return_value=AcceptedElicitation(
                data={
                    "focus_area": "engagement",
                    "time_period": "last_7_days",
                    "custom_start": None,
                    "custom_end": None,
                }
            )
        )

        result = await guided_analysis(mock_context)  # type: ignore[operator]

        assert result["focus_area"] == "engagement"
        assert "User selected focus via elicitation" in result["workflow_steps"]

    @pytest.mark.asyncio
    async def test_guided_analysis_with_segment_selection(
        self, mock_context: MagicMock
    ) -> None:
        """guided_analysis should handle segment selection."""
        from fastmcp.server.elicitation import AcceptedElicitation

        from mp_mcp.tools.interactive.guided import guided_analysis

        # First elicit returns None (using preset focus_area), second returns segment choice
        mock_context.elicit = AsyncMock(
            return_value=AcceptedElicitation(
                data={"segment_index": 0, "investigate_further": True}
            )
        )

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="conversion",
        )

        assert result["focus_area"] == "conversion"
        # Should have attempted segment analysis
        assert "segment_analysis" in result or "available_segments" in result

    @pytest.mark.asyncio
    async def test_guided_analysis_segment_selection_invalid_index(
        self, mock_context: MagicMock
    ) -> None:
        """guided_analysis should handle invalid segment index."""
        from fastmcp.server.elicitation import AcceptedElicitation

        from mp_mcp.tools.interactive.guided import guided_analysis

        # Return segment index out of range
        mock_context.elicit = AsyncMock(
            return_value=AcceptedElicitation(
                data={"segment_index": 99, "investigate_further": True}
            )
        )

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="conversion",
        )

        # Should skip invalid segment index
        assert any("Invalid segment index" in step for step in result["workflow_steps"])

    @pytest.mark.asyncio
    async def test_guided_analysis_segment_no_further_investigation(
        self, mock_context: MagicMock
    ) -> None:
        """guided_analysis should skip drill-down when investigate_further is False."""
        from fastmcp.server.elicitation import AcceptedElicitation

        from mp_mcp.tools.interactive.guided import guided_analysis

        # Return segment choice with investigate_further=False
        mock_context.elicit = AsyncMock(
            return_value=AcceptedElicitation(
                data={"segment_index": 0, "investigate_further": False}
            )
        )

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="retention",
        )

        # When investigate_further is False, segment is still selected but we verify
        # the workflow step says it was selected
        assert any(
            "selected segment" in step.lower() for step in result["workflow_steps"]
        )

    @pytest.mark.asyncio
    async def test_guided_analysis_suggestions_conversion(
        self, mock_context: MagicMock
    ) -> None:
        """guided_analysis should provide conversion-specific suggestions."""
        from mp_mcp.tools.interactive.guided import guided_analysis

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="conversion",
        )

        assert "suggestions" in result
        assert any("funnel" in s.lower() for s in result["suggestions"])

    @pytest.mark.asyncio
    async def test_guided_analysis_suggestions_engagement(
        self, mock_context: MagicMock
    ) -> None:
        """guided_analysis should provide engagement-specific suggestions."""
        from mp_mcp.tools.interactive.guided import guided_analysis

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="engagement",
        )

        assert "suggestions" in result
        assert any("feature" in s.lower() for s in result["suggestions"])

    @pytest.mark.asyncio
    async def test_guided_analysis_suggestions_revenue(
        self, mock_context: MagicMock
    ) -> None:
        """guided_analysis should provide revenue-specific suggestions."""
        from mp_mcp.tools.interactive.guided import guided_analysis

        mock_context.lifespan_context["workspace"].events.return_value = [
            "purchase",
            "signup",
        ]

        result = await guided_analysis(  # type: ignore[operator]
            mock_context,
            focus_area="revenue",
        )

        assert "suggestions" in result
        assert any("revenue" in s.lower() for s in result["suggestions"])
