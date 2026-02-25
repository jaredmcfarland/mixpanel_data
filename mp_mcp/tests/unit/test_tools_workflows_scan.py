"""Tests for the scan workflow tool.

These tests verify the scan tool correctly detects anomalies
using statistical methods for the Operational Analytics Loop workflow.
"""

from unittest.mock import MagicMock


class TestScanToolRegistration:
    """Tests for scan tool registration."""

    def test_tool_registered(self, registered_tool_names: list[str]) -> None:
        """Scan tool should be registered."""
        assert "scan" in registered_tool_names


class TestScanToolBasic:
    """Tests for basic scan tool functionality."""

    def test_scan_returns_required_fields(self, mock_context: MagicMock) -> None:
        """Scan should return all required fields."""
        from mp_mcp.tools.workflows.scan import scan

        result = scan(mock_context)  # type: ignore[operator]

        assert "period" in result
        assert "anomalies" in result
        assert "scan_coverage" in result

    def test_scan_period_structure(self, mock_context: MagicMock) -> None:
        """Scan should return valid period structure."""
        from mp_mcp.tools.workflows.scan import scan

        result = scan(mock_context)  # type: ignore[operator]

        assert "from_date" in result["period"]
        assert "to_date" in result["period"]

    def test_scan_anomalies_structure(self, mock_context: MagicMock) -> None:
        """Scan should return anomalies with required fields."""
        from mp_mcp.tools.workflows.scan import scan

        # Set up mock with data that should trigger anomaly detection
        mock_context.lifespan_context[
            "workspace"
        ].segmentation.return_value = MagicMock(
            to_dict=lambda: {
                "total": 100,
                "series": {
                    "signup": {
                        "2024-01-01": 100,
                        "2024-01-02": 110,
                        "2024-01-03": 105,
                        "2024-01-04": 95,
                        "2024-01-05": 50,  # Anomalous drop
                    }
                },
            }
        )

        result = scan(mock_context)  # type: ignore[operator]

        assert isinstance(result["anomalies"], list)
        # If anomalies found, check structure
        if result["anomalies"]:
            anomaly = result["anomalies"][0]
            assert "id" in anomaly
            assert "type" in anomaly
            assert "severity" in anomaly
            assert "event" in anomaly
            assert "summary" in anomaly


class TestScanWithEvents:
    """Tests for scan tool with custom events."""

    def test_scan_with_custom_events(self, mock_context: MagicMock) -> None:
        """Scan should analyze specified events."""
        from mp_mcp.tools.workflows.scan import scan

        result = scan(  # type: ignore[operator]
            mock_context,
            events=["login", "purchase"],
        )

        assert "anomalies" in result
        assert "scan_coverage" in result

    def test_scan_with_single_event(self, mock_context: MagicMock) -> None:
        """Scan should analyze a single event."""
        from mp_mcp.tools.workflows.scan import scan

        result = scan(  # type: ignore[operator]
            mock_context,
            events=["signup"],
        )

        assert "anomalies" in result


class TestScanWithDateRange:
    """Tests for scan tool with custom date ranges."""

    def test_scan_with_custom_dates(self, mock_context: MagicMock) -> None:
        """Scan should accept custom date ranges."""
        from mp_mcp.tools.workflows.scan import scan

        result = scan(  # type: ignore[operator]
            mock_context,
            from_date="2024-01-01",
            to_date="2024-01-31",
        )

        assert result["period"]["from_date"] == "2024-01-01"
        assert result["period"]["to_date"] == "2024-01-31"


class TestScanErrorHandling:
    """Tests for scan tool error handling."""

    def test_scan_handles_segmentation_error(self, mock_context: MagicMock) -> None:
        """Scan should handle errors from segmentation() gracefully."""
        from mp_mcp.tools.workflows.scan import scan

        mock_context.lifespan_context["workspace"].segmentation.side_effect = Exception(
            "API error"
        )

        result = scan(mock_context)  # type: ignore[operator]

        # Should still return valid structure
        assert "anomalies" in result
        assert "period" in result


class TestScanHelpers:
    """Tests for scan tool helper functions."""

    def test_detect_drops(self) -> None:
        """_detect_drops should identify significant drops in time series."""
        from mp_mcp.tools.workflows.scan import _detect_drops

        # Normal data with a drop
        data = {
            "2024-01-01": 100.0,
            "2024-01-02": 110.0,
            "2024-01-03": 105.0,
            "2024-01-04": 95.0,
            "2024-01-05": 50.0,  # 47% drop from previous
        }

        drops = _detect_drops(data, threshold=0.3)

        assert len(drops) > 0
        # The drop should be on 2024-01-05
        drop_dates = [d["date"] for d in drops]
        assert "2024-01-05" in drop_dates

    def test_detect_spikes(self) -> None:
        """_detect_spikes should identify significant spikes in time series."""
        from mp_mcp.tools.workflows.scan import _detect_spikes

        # Normal data with a spike
        data = {
            "2024-01-01": 100.0,
            "2024-01-02": 110.0,
            "2024-01-03": 105.0,
            "2024-01-04": 95.0,
            "2024-01-05": 200.0,  # Big spike
        }

        spikes = _detect_spikes(data, threshold=0.5)

        assert len(spikes) > 0
        spike_dates = [s["date"] for s in spikes]
        assert "2024-01-05" in spike_dates

    def test_compute_severity(self) -> None:
        """_compute_severity should classify severity correctly."""
        from mp_mcp.tools.workflows.scan import _compute_severity

        assert _compute_severity(0.5) == "critical"
        assert _compute_severity(0.35) == "high"
        assert _compute_severity(0.20) == "medium"
        assert _compute_severity(0.10) == "low"

    def test_generate_anomaly_id(self) -> None:
        """generate_anomaly_id should create deterministic IDs."""
        from mp_mcp.tools.workflows.helpers import generate_anomaly_id

        id1 = generate_anomaly_id("signup", "drop", "2024-01-05")
        id2 = generate_anomaly_id("signup", "drop", "2024-01-05")

        assert id1 == id2  # Same inputs = same ID
        assert "signup" in id1
        assert "drop" in id1
        assert "2024-01-05" in id1

    def test_generate_anomaly_id_with_dimension(self) -> None:
        """generate_anomaly_id should include dimension info."""
        from mp_mcp.tools.workflows.helpers import generate_anomaly_id

        id_with_dim = generate_anomaly_id(
            "signup", "drop", "2024-01-05", dimension="platform", dimension_value="iOS"
        )

        assert "platform" in id_with_dim
        assert "iOS" in id_with_dim
