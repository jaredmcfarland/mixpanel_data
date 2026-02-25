"""Tests for the health workflow tool.

These tests verify the health tool correctly generates KPI dashboards
with period comparison for the Operational Analytics Loop workflow.
"""

from unittest.mock import MagicMock


class TestHealthToolRegistration:
    """Tests for health tool registration."""

    def test_tool_registered(self, registered_tool_names: list[str]) -> None:
        """Health tool should be registered."""
        assert "health" in registered_tool_names


class TestHealthToolBasic:
    """Tests for basic health tool functionality."""

    def test_health_returns_required_fields(self, mock_context: MagicMock) -> None:
        """Health should return all required fields."""
        from mp_mcp.tools.workflows.health import health

        result = health(mock_context)  # type: ignore[operator]

        assert "period" in result
        assert "comparison_period" in result
        assert "metrics" in result
        assert "highlights" in result
        assert "concerns" in result

    def test_health_period_structure(self, mock_context: MagicMock) -> None:
        """Health should return valid period structure."""
        from mp_mcp.tools.workflows.health import health

        result = health(mock_context)  # type: ignore[operator]

        assert "from_date" in result["period"]
        assert "to_date" in result["period"]
        assert result["period"]["from_date"] < result["period"]["to_date"]

    def test_health_metrics_structure(self, mock_context: MagicMock) -> None:
        """Health should return metrics with required fields."""
        from mp_mcp.tools.workflows.health import health

        result = health(mock_context)  # type: ignore[operator]

        assert isinstance(result["metrics"], list)
        # At least one metric should be present
        if result["metrics"]:
            metric = result["metrics"][0]
            assert "name" in metric
            assert "current" in metric
            assert "previous" in metric
            assert "trend" in metric


class TestHealthWithEvents:
    """Tests for health tool with custom events."""

    def test_health_with_custom_acquisition_event(
        self, mock_context: MagicMock
    ) -> None:
        """Health should use custom acquisition event."""
        from mp_mcp.tools.workflows.health import health

        result = health(  # type: ignore[operator]
            mock_context,
            acquisition_event="register",
        )

        assert "metrics" in result

    def test_health_with_multiple_events(self, mock_context: MagicMock) -> None:
        """Health should track multiple events."""
        from mp_mcp.tools.workflows.health import health

        result = health(  # type: ignore[operator]
            mock_context,
            acquisition_event="signup",
            activation_event="first_purchase",
        )

        assert "metrics" in result


class TestHealthWithDateRange:
    """Tests for health tool with custom date ranges."""

    def test_health_with_custom_dates(self, mock_context: MagicMock) -> None:
        """Health should accept custom date ranges."""
        from mp_mcp.tools.workflows.health import health

        result = health(  # type: ignore[operator]
            mock_context,
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["period"]["from_date"] == "2024-01-01"
        assert result["period"]["to_date"] == "2024-01-31"


class TestHealthErrorHandling:
    """Tests for health tool error handling."""

    def test_health_handles_segmentation_error(self, mock_context: MagicMock) -> None:
        """Health should handle errors from segmentation() gracefully."""
        from mp_mcp.tools.workflows.health import health

        mock_context.lifespan_context["workspace"].segmentation.side_effect = Exception(
            "API error"
        )

        result = health(mock_context)  # type: ignore[operator]

        # Should still return valid structure
        assert "metrics" in result
        assert "period" in result

    def test_health_handles_retention_error(self, mock_context: MagicMock) -> None:
        """Health should handle errors from retention() gracefully."""
        from mp_mcp.tools.workflows.health import health

        mock_context.lifespan_context["workspace"].retention.side_effect = Exception(
            "API error"
        )

        result = health(mock_context)  # type: ignore[operator]

        # Should still return valid structure
        assert "metrics" in result


class TestHealthHelpers:
    """Tests for health tool helper functions."""

    def test_compute_metric(self, mock_context: MagicMock) -> None:
        """_compute_metric should return Metric with proper values."""
        from mp_mcp.tools.workflows.health import _compute_metric

        # Set up mock to return different values for current vs previous
        call_count = 0

        def mock_segmentation(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return MagicMock(to_dict=lambda: {"total": 1000})
            return MagicMock(to_dict=lambda: {"total": 800})

        mock_context.lifespan_context[
            "workspace"
        ].segmentation.side_effect = mock_segmentation

        result = _compute_metric(
            mock_context,
            name="signups",
            display_name="Signups",
            event="signup",
            from_date="2024-01-01",
            to_date="2024-01-31",
            comparison_from="2023-12-01",
            comparison_to="2023-12-31",
        )

        assert result.name == "signups"
        assert result.display_name == "Signups"
        assert result.current == 1000.0
        assert result.previous == 800.0
        assert result.change_percent == 25.0
        assert result.trend == "up"

    def test_determine_trend(self) -> None:
        """_determine_trend should correctly classify trends."""
        from mp_mcp.tools.workflows.health import _determine_trend

        assert _determine_trend(100, 50) == "up"
        assert _determine_trend(50, 100) == "down"
        assert _determine_trend(100, 98) == "flat"
        assert _determine_trend(100, 102) == "flat"

    def test_compute_change_percent(self) -> None:
        """_compute_change_percent should calculate percentage correctly."""
        from mp_mcp.tools.workflows.health import _compute_change_percent

        assert _compute_change_percent(150, 100) == 50.0
        assert _compute_change_percent(50, 100) == -50.0
        assert _compute_change_percent(100, 100) == 0.0
        assert _compute_change_percent(100, 0) == 100.0  # Division by zero case
