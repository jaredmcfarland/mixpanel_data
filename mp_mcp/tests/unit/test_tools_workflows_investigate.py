"""Tests for the investigate workflow tool.

These tests verify the investigate tool correctly performs root cause
analysis for anomalies in the Operational Analytics Loop workflow.
"""

from unittest.mock import MagicMock


class TestInvestigateToolRegistration:
    """Tests for investigate tool registration."""

    def test_tool_registered(self, registered_tool_names: list[str]) -> None:
        """Investigate tool should be registered."""
        assert "investigate" in registered_tool_names


class TestInvestigateToolBasic:
    """Tests for basic investigate tool functionality."""

    def test_investigate_returns_required_fields(self, mock_context: MagicMock) -> None:
        """Investigate should return all required fields."""
        from mp_mcp.tools.workflows.investigate import investigate

        result = investigate(  # type: ignore[operator]
            mock_context,
            event="signup",
            date="2024-01-15",
            anomaly_type="drop",
        )

        assert "anomaly" in result
        assert "contributing_factors" in result
        assert "confidence" in result

    def test_investigate_anomaly_structure(self, mock_context: MagicMock) -> None:
        """Investigate should return valid anomaly structure."""
        from mp_mcp.tools.workflows.investigate import investigate

        result = investigate(  # type: ignore[operator]
            mock_context,
            event="signup",
            date="2024-01-15",
            anomaly_type="drop",
        )

        assert "id" in result["anomaly"]
        assert "event" in result["anomaly"]
        assert "type" in result["anomaly"]


class TestInvestigateWithParams:
    """Tests for investigate tool with various parameters."""

    def test_investigate_with_dimensions(self, mock_context: MagicMock) -> None:
        """Investigate should accept dimensions parameter."""
        from mp_mcp.tools.workflows.investigate import investigate

        result = investigate(  # type: ignore[operator]
            mock_context,
            event="signup",
            date="2024-01-15",
            anomaly_type="drop",
            dimensions=["platform", "$browser"],
        )

        assert "anomaly" in result

    def test_investigate_with_anomaly_id(self, mock_context: MagicMock) -> None:
        """Investigate should accept anomaly_id parameter."""
        from mp_mcp.tools.workflows.investigate import investigate

        result = investigate(  # type: ignore[operator]
            mock_context,
            anomaly_id="signup_drop_2024-01-15_a3f2b1c9",
        )

        assert "anomaly" in result


class TestInvestigateErrorHandling:
    """Tests for investigate tool error handling."""

    def test_investigate_handles_segmentation_error(
        self, mock_context: MagicMock
    ) -> None:
        """Investigate should handle errors from segmentation() gracefully."""
        from mp_mcp.tools.workflows.investigate import investigate

        mock_context.lifespan_context["workspace"].segmentation.side_effect = Exception(
            "API error"
        )

        result = investigate(  # type: ignore[operator]
            mock_context,
            event="signup",
            date="2024-01-15",
            anomaly_type="drop",
        )

        # Should still return valid structure
        assert "anomaly" in result
        assert "confidence" in result


class TestInvestigateHelpers:
    """Tests for investigate tool helper functions."""

    def test_dimensional_decomposition(self, mock_context: MagicMock) -> None:
        """_dimensional_decomposition should segment by dimensions."""
        from mp_mcp.tools.workflows.investigate import _dimensional_decomposition

        result = _dimensional_decomposition(
            mock_context,
            event="signup",
            from_date="2024-01-01",
            to_date="2024-01-31",
            anomaly_date="2024-01-15",
            dimensions=["$browser", "$os"],
        )

        assert isinstance(result, list)
