"""Integration tests for Workspace.query() end-to-end with mocked HTTP.

Tests the full flow: query() -> validate -> build params -> API call -> transform -> QueryResult.
Uses MagicMock for API client to simulate Mixpanel responses.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from mixpanel_data import Workspace
from mixpanel_data._internal.api_client import MixpanelAPIClient
from mixpanel_data.exceptions import QueryError
from mixpanel_data.types import QueryResult

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_api_client() -> MagicMock:
    """Create mock API client for testing."""
    client = MagicMock(spec=MixpanelAPIClient)
    client.close = MagicMock()
    return client


@pytest.fixture
def ws(mock_config_manager: MagicMock, mock_api_client: MagicMock) -> Workspace:
    """Create Workspace with mocked API client for integration testing."""
    workspace = Workspace(_config_manager=mock_config_manager)
    workspace._api_client = mock_api_client
    return workspace


TIMESERIES_RESPONSE: dict[str, Any] = {
    "computed_at": "2024-01-31T12:00:00+00:00",
    "date_range": {
        "from_date": "2024-01-01T00:00:00-07:00",
        "to_date": "2024-01-31T23:59:59.999000-07:00",
    },
    "headers": ["$metric"],
    "series": {
        "Login [Total Events]": {
            "2024-01-01T00:00:00-07:00": 100,
            "2024-01-02T00:00:00-07:00": 200,
            "2024-01-03T00:00:00-07:00": 150,
        },
    },
    "meta": {
        "min_sampling_factor": 1.0,
        "is_segmentation_limit_hit": False,
        "sub_query_count": 1,
    },
}

TOTAL_RESPONSE: dict[str, Any] = {
    "computed_at": "2024-01-31T12:00:00+00:00",
    "date_range": {
        "from_date": "2024-01-01T00:00:00-07:00",
        "to_date": "2024-01-31T23:59:59.999000-07:00",
    },
    "headers": ["$metric"],
    "series": {
        "Login [Unique Users]": {"all": 3551},
    },
    "meta": {
        "min_sampling_factor": 1.0,
        "is_segmentation_limit_hit": False,
    },
}

EMPTY_RESPONSE: dict[str, Any] = {
    "computed_at": "2024-01-31T12:00:00+00:00",
    "date_range": {
        "from_date": "2024-01-01T00:00:00-07:00",
        "to_date": "2024-01-31T23:59:59.999000-07:00",
    },
    "headers": ["$metric"],
    "series": {},
    "meta": {},
}


# =============================================================================
# T009: End-to-end query with mocked HTTP response (timeseries)
# =============================================================================


class TestQueryTimeseries:
    """Integration tests for timeseries query mode."""

    def test_basic_query_returns_query_result(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """query("Login") returns a QueryResult."""
        mock_api_client.insights_query.return_value = TIMESERIES_RESPONSE
        result = ws.query("Login")
        assert isinstance(result, QueryResult)

    def test_basic_query_computed_at(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """QueryResult has computed_at from response."""
        mock_api_client.insights_query.return_value = TIMESERIES_RESPONSE
        result = ws.query("Login")
        assert result.computed_at == "2024-01-31T12:00:00+00:00"

    def test_basic_query_date_range(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """QueryResult extracts nested date_range fields."""
        mock_api_client.insights_query.return_value = TIMESERIES_RESPONSE
        result = ws.query("Login")
        assert "2024-01-01" in result.from_date
        assert "2024-01-31" in result.to_date

    def test_basic_query_series(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """QueryResult contains the series data."""
        mock_api_client.insights_query.return_value = TIMESERIES_RESPONSE
        result = ws.query("Login")
        assert "Login [Total Events]" in result.series

    def test_basic_query_df_shape(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """Timeseries DataFrame has 3 rows and date/event/count columns."""
        mock_api_client.insights_query.return_value = TIMESERIES_RESPONSE
        result = ws.query("Login")
        df = result.df
        assert len(df) == 3
        assert list(df.columns) == ["date", "event", "count"]

    def test_query_passes_bookmark_params(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """insights_query is called with correct body structure."""
        mock_api_client.insights_query.return_value = TIMESERIES_RESPONSE
        ws.query("Login")
        call_args = mock_api_client.insights_query.call_args
        body = call_args[1]["body"] if "body" in call_args[1] else call_args[0][0]
        assert "bookmark" in body
        assert "project_id" in body
        assert body["project_id"] == 12345
        assert "queryLimits" in body

    def test_result_params_populated(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """QueryResult.params contains the bookmark dict."""
        mock_api_client.insights_query.return_value = TIMESERIES_RESPONSE
        result = ws.query("Login")
        assert isinstance(result.params, dict)
        assert "sections" in result.params

    def test_result_meta_populated(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """QueryResult.meta contains response metadata."""
        mock_api_client.insights_query.return_value = TIMESERIES_RESPONSE
        result = ws.query("Login")
        assert "min_sampling_factor" in result.meta


# =============================================================================
# T009b: Query with non-existent event (empty response)
# =============================================================================


class TestQueryNonExistentEvent:
    """Tests for query with non-existent event name."""

    def test_empty_response_no_exception(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """Query with non-existent event returns empty DataFrame, no exception."""
        mock_api_client.insights_query.return_value = EMPTY_RESPONSE
        result = ws.query("NonExistentEvent")
        assert isinstance(result, QueryResult)
        assert len(result.df) == 0

    def test_empty_response_has_metadata(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """Empty result still has computed_at and date range."""
        mock_api_client.insights_query.return_value = EMPTY_RESPONSE
        result = ws.query("NonExistentEvent")
        assert result.computed_at == "2024-01-31T12:00:00+00:00"


# =============================================================================
# T033: Multi-event integration (US4)
# =============================================================================


MULTI_EVENT_RESPONSE: dict[str, Any] = {
    "computed_at": "2024-01-31T12:00:00+00:00",
    "date_range": {
        "from_date": "2024-01-01T00:00:00-07:00",
        "to_date": "2024-01-31T23:59:59.999000-07:00",
    },
    "headers": ["$metric"],
    "series": {
        "Signup [Unique Users]": {"2024-01-01": 50},
        "Login [Unique Users]": {"2024-01-01": 200},
        "Purchase [Unique Users]": {"2024-01-01": 30},
    },
    "meta": {},
}


class TestMultiEventIntegration:
    """Integration tests for multi-event queries."""

    def test_multi_event_df_has_all_metrics(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """Multi-event query returns DataFrame with all metrics."""
        mock_api_client.insights_query.return_value = MULTI_EVENT_RESPONSE
        result = ws.query(["Signup", "Login", "Purchase"], math="unique")
        assert len(result.df) == 3
        events = set(result.df["event"])
        assert len(events) == 3


# =============================================================================
# T037: Formula integration (US5)
# =============================================================================


FORMULA_RESPONSE: dict[str, Any] = {
    "computed_at": "2024-01-31T12:00:00+00:00",
    "date_range": {
        "from_date": "2024-01-01T00:00:00-07:00",
        "to_date": "2024-01-07T23:59:59.999000-07:00",
    },
    "headers": ["$metric"],
    "series": {
        "Conversion Rate": {"2024-01-01": 15.5, "2024-01-02": 18.2},
    },
    "meta": {},
}


class TestFormulaIntegration:
    """Integration tests for formula queries."""

    def test_formula_query_result(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """Formula query returns result with formula series."""
        from mixpanel_data import Metric

        mock_api_client.insights_query.return_value = FORMULA_RESPONSE
        result = ws.query(
            [Metric("Signup", math="unique"), Metric("Purchase", math="unique")],
            formula="(B / A) * 100",
            formula_label="Conversion Rate",
        )
        assert "Conversion Rate" in result.series
        assert len(result.df) == 2


# =============================================================================
# T046: Total mode integration (US7)
# =============================================================================


class TestTotalModeIntegration:
    """Integration tests for total mode queries."""

    def test_total_mode_single_row(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """Total mode returns single row per metric."""
        mock_api_client.insights_query.return_value = TOTAL_RESPONSE
        result = ws.query("Login", math="unique", mode="total")
        df = result.df
        assert len(df) == 1
        assert list(df.columns) == ["event", "count"]
        assert df.iloc[0]["count"] == 3551


# =============================================================================
# T050: Query result persistence (US8)
# =============================================================================


class TestQueryPersistence:
    """Tests for query result debugging and persistence."""

    def test_result_params_can_create_bookmark(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """result.params contains the bookmark dict suitable for create_bookmark."""
        mock_api_client.insights_query.return_value = TIMESERIES_RESPONSE
        result = ws.query("Login", math="unique", last=7)
        # Params should have sections and displayOptions
        assert "sections" in result.params
        assert "displayOptions" in result.params
        assert "show" in result.params["sections"]


# =============================================================================
# Response validation in _transform_query_result
# =============================================================================


class TestTransformQueryResultValidation:
    """Tests for error handling in _transform_query_result."""

    def test_error_as_200_raises_query_error(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """API returning error in 200 response raises QueryError."""
        error_response: dict[str, Any] = {
            "error": "invalid query",
            "status": "fail",
        }
        mock_api_client.insights_query.return_value = error_response
        with pytest.raises(QueryError, match="Insights query failed: invalid query"):
            ws.query("Login")

    def test_missing_series_raises_query_error(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """Response missing 'series' key raises QueryError."""
        malformed_response: dict[str, Any] = {
            "computed_at": "2024-01-31T12:00:00+00:00",
            "date_range": {"from_date": "2024-01-01", "to_date": "2024-01-31"},
            "headers": [],
            "meta": {},
        }
        mock_api_client.insights_query.return_value = malformed_response
        with pytest.raises(QueryError, match="missing 'series' key"):
            ws.query("Login")

    def test_valid_response_no_error(
        self, ws: Workspace, mock_api_client: MagicMock
    ) -> None:
        """Valid response with series key succeeds."""
        mock_api_client.insights_query.return_value = TIMESERIES_RESPONSE
        result = ws.query("Login")
        assert isinstance(result, QueryResult)
        assert "Login [Total Events]" in result.series
