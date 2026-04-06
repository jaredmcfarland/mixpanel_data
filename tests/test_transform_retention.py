"""Unit tests for _transform_retention_result()."""

from __future__ import annotations

from typing import Any

import pytest

from mixpanel_data._internal.services.live_query import _transform_retention_result
from mixpanel_data.exceptions import QueryError
from mixpanel_data.types import RetentionQueryResult

# =============================================================================
# Shared fixtures
# =============================================================================

_BOOKMARK_PARAMS: dict[str, Any] = {"sections": {}, "displayOptions": {}}


def _mock_response(**overrides: Any) -> dict[str, Any]:
    """Build a mock retention API response with sensible defaults.

    Args:
        **overrides: Keys to override in the default response dict.

    Returns:
        A dict mimicking the retention query response shape.
    """
    defaults: dict[str, Any] = {
        "computed_at": "2025-01-15T12:00:00",
        "date_range": {"from_date": "2025-01-01", "to_date": "2025-01-31"},
        "series": {
            "Signup and then Login": {
                "2025-01-01": {
                    "first": 100,
                    "counts": [100, 50, 25],
                    "rates": [1.0, 0.5, 0.25],
                },
                "2025-01-02": {
                    "first": 80,
                    "counts": [80, 40],
                    "rates": [1.0, 0.5],
                },
                "$average": {
                    "first": 90,
                    "counts": [90, 45, 22],
                    "rates": [1.0, 0.5, 0.244],
                },
            }
        },
        "meta": {"sampling_factor": 1.0},
    }
    defaults.update(overrides)
    return defaults


# =============================================================================
# TestTransformRetentionBasic (T017)
# =============================================================================


class TestTransformRetentionBasic:
    """Tests for _transform_retention_result basic response parsing."""

    def test_returns_retention_query_result(self) -> None:
        """Return type is RetentionQueryResult."""
        result = _transform_retention_result(_mock_response(), _BOOKMARK_PARAMS)

        assert isinstance(result, RetentionQueryResult)

    def test_computed_at_extracted(self) -> None:
        """computed_at is extracted from the raw response."""
        result = _transform_retention_result(_mock_response(), _BOOKMARK_PARAMS)

        assert result.computed_at == "2025-01-15T12:00:00"

    def test_from_date_extracted(self) -> None:
        """from_date is extracted from raw['date_range']."""
        result = _transform_retention_result(_mock_response(), _BOOKMARK_PARAMS)

        assert result.from_date == "2025-01-01"

    def test_to_date_extracted(self) -> None:
        """to_date is extracted from raw['date_range']."""
        result = _transform_retention_result(_mock_response(), _BOOKMARK_PARAMS)

        assert result.to_date == "2025-01-31"

    def test_cohorts_extracted_from_series(self) -> None:
        """Cohorts are extracted from series, excluding $average."""
        result = _transform_retention_result(_mock_response(), _BOOKMARK_PARAMS)

        assert "2025-01-01" in result.cohorts
        assert "2025-01-02" in result.cohorts
        assert len(result.cohorts) == 2

    def test_cohort_data_structure(self) -> None:
        """Each cohort entry contains first, counts, and rates."""
        result = _transform_retention_result(_mock_response(), _BOOKMARK_PARAMS)

        cohort = result.cohorts["2025-01-01"]
        assert cohort["first"] == 100
        assert cohort["counts"] == [100, 50, 25]
        assert cohort["rates"] == [1.0, 0.5, 0.25]

    def test_average_extracted_from_series(self) -> None:
        """Average is extracted from series['$average']."""
        result = _transform_retention_result(_mock_response(), _BOOKMARK_PARAMS)

        assert result.average["first"] == 90
        assert result.average["counts"] == [90, 45, 22]
        assert result.average["rates"] == [1.0, 0.5, 0.244]

    def test_average_excluded_from_cohorts(self) -> None:
        """$average key does not appear in cohorts dict."""
        result = _transform_retention_result(_mock_response(), _BOOKMARK_PARAMS)

        assert "$average" not in result.cohorts

    def test_params_preserved(self) -> None:
        """params field preserves the bookmark_params argument."""
        result = _transform_retention_result(_mock_response(), _BOOKMARK_PARAMS)

        assert result.params == _BOOKMARK_PARAMS

    def test_meta_extracted(self) -> None:
        """meta is extracted from raw['meta']."""
        result = _transform_retention_result(_mock_response(), _BOOKMARK_PARAMS)

        assert result.meta == {"sampling_factor": 1.0}


# =============================================================================
# TestTransformRetentionErrors (T018)
# =============================================================================


class TestTransformRetentionErrors:
    """Tests for _transform_retention_result error handling."""

    def test_error_response_raises_query_error(self) -> None:
        """Response containing 'error' key raises QueryError with message."""
        error_response: dict[str, Any] = {"error": "invalid query"}

        with pytest.raises(QueryError, match="invalid query"):
            _transform_retention_result(error_response, _BOOKMARK_PARAMS)

    def test_error_response_includes_status_code(self) -> None:
        """QueryError from error response has status_code=200 (leaked HTTP 200 error)."""
        error_response: dict[str, Any] = {"error": "bad params"}

        with pytest.raises(QueryError) as exc_info:
            _transform_retention_result(error_response, _BOOKMARK_PARAMS)

        assert exc_info.value.status_code == 200

    def test_error_response_includes_response_body(self) -> None:
        """QueryError from error response includes the raw response as response_body."""
        error_response: dict[str, Any] = {"error": "timeout"}

        with pytest.raises(QueryError) as exc_info:
            _transform_retention_result(error_response, _BOOKMARK_PARAMS)

        assert exc_info.value.response_body == error_response

    def test_error_response_includes_request_body(self) -> None:
        """QueryError from error response includes bookmark_params as request_body."""
        error_response: dict[str, Any] = {"error": "bad filter"}
        params: dict[str, Any] = {"sections": {"filters": "invalid"}}

        with pytest.raises(QueryError) as exc_info:
            _transform_retention_result(error_response, params)

        assert exc_info.value.request_body == params

    def test_missing_series_raises_query_error(self) -> None:
        """Missing series key raises QueryError."""
        raw: dict[str, Any] = {
            "computed_at": "2025-01-15T12:00:00",
            "date_range": {"from_date": "2025-01-01", "to_date": "2025-01-31"},
            "meta": {},
        }

        with pytest.raises(QueryError, match="missing 'series' key"):
            _transform_retention_result(raw, _BOOKMARK_PARAMS)

    def test_empty_series_produces_empty_cohorts(self) -> None:
        """Empty series produces empty cohorts dict."""
        raw = _mock_response(series={})

        result = _transform_retention_result(raw, _BOOKMARK_PARAMS)

        assert result.cohorts == {}
        assert result.average == {}


# =============================================================================
# TestTransformRetentionFormatVariations (T054)
# =============================================================================


class TestTransformRetentionFormatVariations:
    """Tests for response format variations (T054)."""

    def test_direct_cohort_dict(self) -> None:
        """Direct cohort dict format (no wrapper) is parsed correctly."""
        raw = _mock_response()
        result = _transform_retention_result(raw, _BOOKMARK_PARAMS)
        assert len(result.cohorts) == 2

    def test_missing_date_range_uses_defaults(self) -> None:
        """Missing date_range produces empty from_date/to_date."""
        raw = _mock_response()
        del raw["date_range"]
        result = _transform_retention_result(raw, _BOOKMARK_PARAMS)
        assert result.from_date == ""
        assert result.to_date == ""

    def test_missing_meta_uses_empty_dict(self) -> None:
        """Missing meta produces empty dict."""
        raw = _mock_response()
        del raw["meta"]
        result = _transform_retention_result(raw, _BOOKMARK_PARAMS)
        assert result.meta == {}

    def test_missing_computed_at_uses_empty_string(self) -> None:
        """Missing computed_at produces empty string."""
        raw = _mock_response()
        del raw["computed_at"]
        result = _transform_retention_result(raw, _BOOKMARK_PARAMS)
        assert result.computed_at == ""

    def test_series_without_average(self) -> None:
        """Series without $average produces empty average dict."""
        raw = _mock_response(
            series={
                "Signup and then Login": {
                    "2025-01-01": {
                        "first": 100,
                        "counts": [100, 50],
                        "rates": [1.0, 0.5],
                    },
                }
            }
        )
        result = _transform_retention_result(raw, _BOOKMARK_PARAMS)
        assert result.average == {}
        assert len(result.cohorts) == 1

    def test_single_cohort_response(self) -> None:
        """Single cohort date in series is handled correctly."""
        raw = _mock_response(
            series={
                "Signup and then Login": {
                    "2025-01-01": {
                        "first": 50,
                        "counts": [50, 25],
                        "rates": [1.0, 0.5],
                    },
                    "$average": {
                        "first": 50,
                        "counts": [50, 25],
                        "rates": [1.0, 0.5],
                    },
                }
            }
        )
        result = _transform_retention_result(raw, _BOOKMARK_PARAMS)
        assert len(result.cohorts) == 1
        assert "2025-01-01" in result.cohorts

    def test_empty_metric_wrapper(self) -> None:
        """Empty dict inside metric wrapper produces empty cohorts."""
        raw = _mock_response(series={"Signup and then Login": {}})
        result = _transform_retention_result(raw, _BOOKMARK_PARAMS)
        assert result.cohorts == {}
        assert result.average == {}
