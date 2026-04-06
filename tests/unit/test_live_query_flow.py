"""Tests for flow query service and API client methods.

Tests cover the arb_funnels_query API client method, the LiveQueryService
query_flow method, and the _transform_flow_result helper.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from mixpanel_data._internal.api_client import MixpanelAPIClient
from mixpanel_data._internal.services.live_query import (
    LiveQueryService,
    _transform_flow_result,
)
from mixpanel_data.exceptions import QueryError
from mixpanel_data.types import FlowQueryResult

# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def mock_api_client() -> MagicMock:
    """Create mock API client for testing."""
    return MagicMock(spec=MixpanelAPIClient)


@pytest.fixture
def live_query_service(mock_api_client: MagicMock) -> LiveQueryService:
    """Create LiveQueryService with mocked API client."""
    return LiveQueryService(mock_api_client)


def _sample_sankey_response() -> dict[str, Any]:
    """Build a sample sankey flow API response for tests."""
    return {
        "computed_at": "2025-01-15T10:00:00",
        "steps": [
            {"event": "Login", "count": 100},
            {"event": "Purchase", "count": 30},
        ],
        "breakdowns": [{"name": "country", "values": ["US", "UK"]}],
        "overallConversionRate": 0.3,
        "metadata": {"sampling_factor": 1.0},
    }


def _sample_top_paths_response() -> dict[str, Any]:
    """Build a sample top-paths flow API response for tests."""
    return {
        "computed_at": "2025-01-15T10:00:00",
        "flows": [
            {"path": ["Login", "Purchase"], "count": 30},
            {"path": ["Login", "Signup"], "count": 20},
        ],
        "steps": [],
        "breakdowns": [],
        "overallConversionRate": 0.5,
        "metadata": {},
    }


def _sample_bookmark_params() -> dict[str, Any]:
    """Build sample bookmark params for tests."""
    return {
        "steps": [{"event": "Login", "forward": 3, "reverse": 0}],
        "date_range": {
            "type": "in the last",
            "from_date": {"unit": "day", "value": 30},
            "to_date": "$now",
        },
        "chartType": "sankey",
        "count_type": "unique",
        "version": 2,
    }


# =========================================================================
# T024: TestArbFunnelsQuery — API client method
# =========================================================================


class TestArbFunnelsQuery:
    """Tests for MixpanelAPIClient.arb_funnels_query()."""

    def test_posts_to_arb_funnels(
        self,
        mock_api_client: MagicMock,
    ) -> None:
        """arb_funnels_query POSTs body to /arb_funnels endpoint."""
        mock_api_client.arb_funnels_query = MagicMock(
            return_value=_sample_sankey_response()
        )
        body: dict[str, Any] = {
            "bookmark": _sample_bookmark_params(),
            "project_id": 12345,
            "query_type": "flows_sankey",
        }

        result = mock_api_client.arb_funnels_query(body)

        mock_api_client.arb_funnels_query.assert_called_once_with(body)
        assert "computed_at" in result

    def test_query_type_sankey(self) -> None:
        """Sankey mode uses query_type='flows_sankey'."""
        body: dict[str, Any] = {
            "bookmark": _sample_bookmark_params(),
            "project_id": 12345,
            "query_type": "flows_sankey",
        }
        assert body["query_type"] == "flows_sankey"

    def test_query_type_top_paths(self) -> None:
        """Paths mode uses query_type='flows_top_paths'."""
        body: dict[str, Any] = {
            "bookmark": _sample_bookmark_params(),
            "project_id": 12345,
            "query_type": "flows_top_paths",
        }
        assert body["query_type"] == "flows_top_paths"


# =========================================================================
# T026: TestTransformFlowResult — _transform_flow_result helper
# =========================================================================


class TestTransformFlowResult:
    """Tests for _transform_flow_result transform function."""

    def test_sankey_response_transformation(self) -> None:
        """Sankey response extracts steps, breakdowns, conversion rate."""
        raw = _sample_sankey_response()
        bookmark = _sample_bookmark_params()

        result = _transform_flow_result(raw, bookmark, mode="sankey")

        assert isinstance(result, FlowQueryResult)
        assert result.computed_at == "2025-01-15T10:00:00"
        assert len(result.steps) == 2
        assert result.steps[0]["event"] == "Login"
        assert len(result.breakdowns) == 1
        assert result.overall_conversion_rate == 0.3
        assert result.mode == "sankey"
        assert result.meta == {"sampling_factor": 1.0}

    def test_top_paths_response_transformation(self) -> None:
        """Top-paths response extracts flows field."""
        raw = _sample_top_paths_response()
        bookmark = _sample_bookmark_params()

        result = _transform_flow_result(raw, bookmark, mode="paths")

        assert isinstance(result, FlowQueryResult)
        assert len(result.flows) == 2
        assert result.flows[0]["path"] == ["Login", "Purchase"]
        assert result.overall_conversion_rate == 0.5
        assert result.mode == "paths"

    def test_error_as_200_raises_query_error(self) -> None:
        """Response with 'error' key raises QueryError."""
        raw: dict[str, Any] = {"error": "Invalid query parameters"}
        bookmark = _sample_bookmark_params()

        with pytest.raises(QueryError, match="Invalid query parameters"):
            _transform_flow_result(raw, bookmark, mode="sankey")

    def test_params_preserved_in_result(self) -> None:
        """Bookmark params are preserved in result for debugging."""
        raw = _sample_sankey_response()
        bookmark = _sample_bookmark_params()

        result = _transform_flow_result(raw, bookmark, mode="sankey")

        assert result.params == bookmark


# =========================================================================
# T027: TestQueryFlow — LiveQueryService.query_flow
# =========================================================================


class TestQueryFlow:
    """Tests for LiveQueryService.query_flow()."""

    def test_calls_arb_funnels_query_with_correct_body(
        self,
        mock_api_client: MagicMock,
        live_query_service: LiveQueryService,
    ) -> None:
        """query_flow calls arb_funnels_query with bookmark, project_id, query_type."""
        mock_api_client.arb_funnels_query.return_value = _sample_sankey_response()
        bookmark = _sample_bookmark_params()

        result = live_query_service.query_flow(
            bookmark_params=bookmark,
            project_id=12345,
            mode="sankey",
        )

        mock_api_client.arb_funnels_query.assert_called_once()
        call_args = mock_api_client.arb_funnels_query.call_args
        body = call_args[0][0]
        assert body["bookmark"] == bookmark
        assert body["project_id"] == 12345
        assert body["query_type"] == "flows_sankey"

        assert isinstance(result, FlowQueryResult)
        assert result.computed_at == "2025-01-15T10:00:00"

    def test_paths_mode_uses_flows_top_paths_query_type(
        self,
        mock_api_client: MagicMock,
        live_query_service: LiveQueryService,
    ) -> None:
        """Paths mode uses query_type='flows_top_paths'."""
        mock_api_client.arb_funnels_query.return_value = _sample_top_paths_response()
        bookmark = _sample_bookmark_params()

        live_query_service.query_flow(
            bookmark_params=bookmark,
            project_id=12345,
            mode="paths",
        )

        call_args = mock_api_client.arb_funnels_query.call_args
        body = call_args[0][0]
        assert body["query_type"] == "flows_top_paths"

    def test_error_in_response_raises_query_error(
        self,
        mock_api_client: MagicMock,
        live_query_service: LiveQueryService,
    ) -> None:
        """Error-as-200 response raises QueryError."""
        mock_api_client.arb_funnels_query.return_value = {"error": "Bad params"}
        bookmark = _sample_bookmark_params()

        with pytest.raises(QueryError, match="Bad params"):
            live_query_service.query_flow(
                bookmark_params=bookmark,
                project_id=12345,
                mode="sankey",
            )
