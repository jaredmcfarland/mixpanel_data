"""Tests for the report workflow tool.

These tests verify the report tool correctly synthesizes findings
into actionable reports for the Operational Analytics Loop workflow.
"""

from unittest.mock import MagicMock


class TestReportToolRegistration:
    """Tests for report tool registration."""

    def test_tool_registered(self, registered_tool_names: list[str]) -> None:
        """Report tool should be registered."""
        assert "report" in registered_tool_names


class TestReportToolBasic:
    """Tests for basic report tool functionality."""

    def test_report_returns_required_fields(self, mock_context: MagicMock) -> None:
        """Report should return all required fields."""
        from mp_mcp.tools.workflows.report import report

        result = report(  # type: ignore[operator]
            mock_context,
            event="signup",
            anomaly_type="drop",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert "title" in result
        assert "summary" in result
        assert "key_findings" in result
        assert "recommendations" in result
        assert "markdown" in result

    def test_report_title_structure(self, mock_context: MagicMock) -> None:
        """Report should return a valid title."""
        from mp_mcp.tools.workflows.report import report

        result = report(  # type: ignore[operator]
            mock_context,
            event="signup",
            anomaly_type="drop",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert isinstance(result["title"], str)
        assert len(result["title"]) > 0

    def test_report_markdown_format(self, mock_context: MagicMock) -> None:
        """Report should return markdown content."""
        from mp_mcp.tools.workflows.report import report

        result = report(  # type: ignore[operator]
            mock_context,
            event="signup",
            anomaly_type="drop",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert isinstance(result["markdown"], str)
        # Should contain markdown headers
        assert "#" in result["markdown"]


class TestReportWithParams:
    """Tests for report tool with various parameters."""

    def test_report_with_format_slack(self, mock_context: MagicMock) -> None:
        """Report should accept format parameter for Slack."""
        from mp_mcp.tools.workflows.report import report

        result = report(  # type: ignore[operator]
            mock_context,
            event="signup",
            anomaly_type="drop",
            from_date="2024-01-01",
            to_date="2024-01-31",
            include_slack_blocks=True,
        )

        assert "slack_blocks" in result

    def test_report_from_investigation(self, mock_context: MagicMock) -> None:
        """Report should generate from investigation data."""
        from mp_mcp.tools.workflows.report import report

        # Pass investigation summary data
        result = report(  # type: ignore[operator]
            mock_context,
            event="signup",
            anomaly_type="drop",
            from_date="2024-01-01",
            to_date="2024-01-31",
            root_cause="iOS Safari compatibility issue",
        )

        assert "summary" in result


class TestReportErrorHandling:
    """Tests for report tool error handling."""

    def test_report_handles_api_error(self, mock_context: MagicMock) -> None:
        """Report should handle API errors gracefully."""
        from mp_mcp.tools.workflows.report import report

        mock_context.lifespan_context["workspace"].segmentation.side_effect = Exception(
            "API error"
        )

        result = report(  # type: ignore[operator]
            mock_context,
            event="signup",
            anomaly_type="drop",
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        # Should still return valid structure
        assert "title" in result
        assert "markdown" in result


class TestReportHelpers:
    """Tests for report tool helper functions."""

    def test_generate_markdown(self) -> None:
        """_generate_markdown should produce formatted output."""
        from mp_mcp.tools.workflows.report import _generate_markdown
        from mp_mcp.types import DateRange, Report

        # Create a minimal Report
        report_obj = Report(
            title="Test Report",
            generated_at="2024-01-31T12:00:00Z",
            period_analyzed=DateRange(from_date="2024-01-01", to_date="2024-01-31"),
            summary="Test summary.",
            key_findings=["Finding 1", "Finding 2"],
        )

        result = _generate_markdown(report_obj)

        assert isinstance(result, str)
        assert "Test Report" in result
        assert "Finding 1" in result

    def test_generate_recommendations(self) -> None:
        """_generate_recommendations should create actionable items."""
        from mp_mcp.tools.workflows.report import _generate_recommendations

        factors = [
            {"dimension": "$browser", "value": "Safari", "impact": -25.0},
            {"dimension": "$os", "value": "iOS", "impact": -20.0},
        ]

        result = _generate_recommendations(
            factors=factors,
            anomaly_type="drop",
        )

        assert isinstance(result, list)
