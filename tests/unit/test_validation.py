"""Unit tests for the bookmark validation engine.

Tests both Layer 1 (validate_query_args) and Layer 2 (validate_bookmark)
validation functions, plus the error types and fuzzy matching.
"""

from __future__ import annotations

from typing import Any

import pytest

from mixpanel_data._internal.validation import (
    _suggest,
    validate_bookmark,
    validate_query_args,
)
from mixpanel_data.exceptions import BookmarkValidationError, ValidationError
from mixpanel_data.types import GroupBy, Metric

# =============================================================================
# Helpers
# =============================================================================


def _valid_args(**overrides: Any) -> dict[str, Any]:
    """Return valid query args with optional overrides."""
    defaults: dict[str, Any] = {
        "events": ["Login"],
        "math": "total",
        "math_property": None,
        "per_user": None,
        "from_date": None,
        "to_date": None,
        "last": 30,
        "has_formula": False,
        "rolling": None,
        "cumulative": False,
        "group_by": None,
    }
    defaults.update(overrides)
    return defaults


def _minimal_bookmark(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid bookmark params dict with optional overrides."""
    bookmark: dict[str, Any] = {
        "sections": {
            "show": [
                {
                    "behavior": {
                        "type": "event",
                        "resourceType": "events",
                        "value": {"name": "Login"},
                    },
                    "measurement": {
                        "math": "total",
                    },
                }
            ],
            "time": [{"unit": "day", "dateRangeType": "in the last", "value": 30}],
            "filter": [],
            "group": [],
        },
        "displayOptions": {
            "chartType": "line",
            "analysis": "linear",
        },
    }
    bookmark.update(overrides)
    return bookmark


# =============================================================================
# ValidationError tests
# =============================================================================


class TestValidationError:
    """Tests for the ValidationError dataclass."""

    def test_to_dict_basic(self) -> None:
        """to_dict returns expected structure."""
        err = ValidationError(path="math", message="bad", code="V1")
        d = err.to_dict()
        assert d["path"] == "math"
        assert d["message"] == "bad"
        assert d["code"] == "V1"
        assert d["severity"] == "error"
        assert "suggestion" not in d
        assert "fix" not in d

    def test_to_dict_with_suggestion(self) -> None:
        """to_dict includes suggestion when present."""
        err = ValidationError(path="p", message="m", suggestion=("total", "unique"))
        d = err.to_dict()
        assert d["suggestion"] == ["total", "unique"]

    def test_to_dict_with_fix(self) -> None:
        """to_dict includes fix when present."""
        err = ValidationError(path="p", message="m", fix={"math": "total"})
        d = err.to_dict()
        assert d["fix"] == {"math": "total"}

    def test_str_error(self) -> None:
        """str() shows [ERROR] prefix."""
        err = ValidationError(path="math", message="bad math")
        assert "[ERROR]" in str(err)
        assert "math" in str(err)

    def test_str_warning(self) -> None:
        """str() shows [WARNING] prefix for warnings."""
        err = ValidationError(path="x", message="warn", severity="warning")
        assert "[WARNING]" in str(err)

    def test_str_with_suggestion(self) -> None:
        """str() includes 'Did you mean' when suggestion present."""
        err = ValidationError(path="p", message="bad", suggestion=("good",))
        assert "Did you mean 'good'?" in str(err)

    def test_frozen(self) -> None:
        """ValidationError is frozen (immutable)."""
        err = ValidationError(path="p", message="m")
        with pytest.raises(AttributeError):
            err.path = "new"  # type: ignore[misc]


class TestBookmarkValidationError:
    """Tests for the BookmarkValidationError exception."""

    def test_inherits_from_base(self) -> None:
        """BookmarkValidationError is a MixpanelDataError."""
        from mixpanel_data.exceptions import MixpanelDataError

        err = BookmarkValidationError([ValidationError(path="p", message="m")])
        assert isinstance(err, MixpanelDataError)

    def test_error_count(self) -> None:
        """error_count counts severity='error' items."""
        err = BookmarkValidationError(
            [
                ValidationError(path="a", message="m1"),
                ValidationError(path="b", message="m2", severity="warning"),
                ValidationError(path="c", message="m3"),
            ]
        )
        assert err.error_count == 2
        assert err.warning_count == 1

    def test_errors_tuple(self) -> None:
        """errors property returns tuple."""
        items = [ValidationError(path="p", message="m")]
        err = BookmarkValidationError(items)
        assert isinstance(err.errors, tuple)
        assert len(err.errors) == 1

    def test_to_dict(self) -> None:
        """to_dict serializes all errors."""
        err = BookmarkValidationError(
            [ValidationError(path="p", message="m", code="V1")]
        )
        d = err.to_dict()
        assert d["code"] == "BOOKMARK_VALIDATION_ERROR"
        assert d["details"]["error_count"] == 1
        assert len(d["details"]["errors"]) == 1
        assert d["details"]["errors"][0]["code"] == "V1"

    def test_message_contains_errors(self) -> None:
        """String message lists the error details."""
        err = BookmarkValidationError(
            [ValidationError(path="math", message="bad math")]
        )
        assert "bad math" in str(err)
        assert "1 error(s)" in str(err)


# =============================================================================
# Fuzzy matching tests
# =============================================================================


class TestFuzzyMatching:
    """Tests for the _suggest helper."""

    def test_close_match(self) -> None:
        """Finds close match for typo."""
        result = _suggest("totl", frozenset({"total", "unique", "average"}))
        assert result is not None
        assert "total" in result

    def test_no_match(self) -> None:
        """Returns None for completely different value."""
        result = _suggest("zzzzz", frozenset({"total", "unique"}))
        assert result is None

    def test_returns_tuple(self) -> None:
        """Result is a tuple of strings."""
        result = _suggest("averge", frozenset({"average", "median"}))
        assert result is not None
        assert isinstance(result, tuple)


# =============================================================================
# Layer 1: validate_query_args tests
# =============================================================================


class TestValidateQueryArgsLayer1:
    """Tests for Layer 1 argument validation."""

    def test_valid_args_no_errors(self) -> None:
        """Valid arguments produce empty error list."""
        errors = validate_query_args(**_valid_args())
        assert errors == []

    def test_v0_no_events(self) -> None:
        """V0: Empty events list produces error."""
        errors = validate_query_args(**_valid_args(events=[]))
        assert any(e.code == "V0_NO_EVENTS" for e in errors)

    def test_v1_math_requires_property(self) -> None:
        """V1: Property math without property produces error."""
        errors = validate_query_args(**_valid_args(math="average"))
        assert any(e.code == "V1_MATH_REQUIRES_PROPERTY" for e in errors)

    def test_v1_valid_with_property(self) -> None:
        """V1: Property math with property is valid."""
        errors = validate_query_args(
            **_valid_args(math="average", math_property="amount")
        )
        assert not any(e.code == "V1_MATH_REQUIRES_PROPERTY" for e in errors)

    def test_v2_rejects_property(self) -> None:
        """V2: Non-property math with property produces error."""
        errors = validate_query_args(
            **_valid_args(math="unique", math_property="amount")
        )
        assert any(e.code == "V2_MATH_REJECTS_PROPERTY" for e in errors)

    def test_v2_total_allows_property(self) -> None:
        """V2: 'total' math allows property (optional)."""
        errors = validate_query_args(
            **_valid_args(math="total", math_property="amount")
        )
        assert not any(e.code == "V2_MATH_REJECTS_PROPERTY" for e in errors)

    def test_v3_per_user_incompatible(self) -> None:
        """V3: per_user with DAU produces error."""
        errors = validate_query_args(**_valid_args(math="dau", per_user="average"))
        assert any(e.code == "V3_PER_USER_INCOMPATIBLE" for e in errors)

    def test_v3b_per_user_requires_property(self) -> None:
        """V3b: per_user without property produces error."""
        errors = validate_query_args(**_valid_args(math="total", per_user="average"))
        assert any(e.code == "V3B_PER_USER_REQUIRES_PROPERTY" for e in errors)

    def test_v4_formula_min_events(self) -> None:
        """V4: Formula with 1 event produces error."""
        errors = validate_query_args(**_valid_args(has_formula=True, events=["Login"]))
        assert any(e.code == "V4_FORMULA_MIN_EVENTS" for e in errors)

    def test_v4_formula_with_two_events(self) -> None:
        """V4: Formula with 2 events is valid."""
        errors = validate_query_args(
            **_valid_args(has_formula=True, events=["Login", "Signup"])
        )
        assert not any(e.code == "V4_FORMULA_MIN_EVENTS" for e in errors)

    def test_v5_rolling_cumulative_exclusive(self) -> None:
        """V5: Rolling and cumulative together produces error."""
        errors = validate_query_args(**_valid_args(rolling=7, cumulative=True))
        assert any(e.code == "V5_ROLLING_CUMULATIVE_EXCLUSIVE" for e in errors)

    def test_v6_rolling_positive(self) -> None:
        """V6: Non-positive rolling produces error."""
        errors = validate_query_args(**_valid_args(rolling=0))
        assert any(e.code == "V6_ROLLING_POSITIVE" for e in errors)

    def test_v7_last_positive(self) -> None:
        """V7: Non-positive last produces error."""
        errors = validate_query_args(**_valid_args(last=0))
        assert any(e.code == "V7_LAST_POSITIVE" for e in errors)

    def test_v8_from_date_format(self) -> None:
        """V8: Bad from_date format produces error."""
        errors = validate_query_args(**_valid_args(from_date="01/01/2024"))
        assert any(e.code == "V8_DATE_FORMAT" for e in errors)

    def test_v8_valid_date(self) -> None:
        """V8: Valid YYYY-MM-DD format passes."""
        errors = validate_query_args(
            **_valid_args(from_date="2024-01-01", to_date="2024-01-31")
        )
        assert not any(e.code == "V8_DATE_FORMAT" for e in errors)

    def test_v9_to_requires_from(self) -> None:
        """V9: to_date without from_date produces error."""
        errors = validate_query_args(**_valid_args(to_date="2024-01-31"))
        assert any(e.code == "V9_TO_REQUIRES_FROM" for e in errors)

    def test_v10_date_last_exclusive(self) -> None:
        """V10: from_date with non-default last produces error."""
        errors = validate_query_args(**_valid_args(from_date="2024-01-01", last=7))
        assert any(e.code == "V10_DATE_LAST_EXCLUSIVE" for e in errors)

    def test_v10_default_last_with_dates_ok(self) -> None:
        """V10: Default last (30) with dates is OK."""
        errors = validate_query_args(
            **_valid_args(from_date="2024-01-01", to_date="2024-01-31")
        )
        assert not any(e.code == "V10_DATE_LAST_EXCLUSIVE" for e in errors)

    def test_v11_bucket_requires_size(self) -> None:
        """V11: bucket_min without bucket_size produces error."""
        errors = validate_query_args(
            **_valid_args(
                group_by=GroupBy(
                    property="revenue",
                    property_type="number",
                    bucket_min=0,
                )
            )
        )
        assert any(e.code == "V11_BUCKET_REQUIRES_SIZE" for e in errors)

    def test_v12_bucket_size_positive(self) -> None:
        """V12: Non-positive bucket_size produces error."""
        errors = validate_query_args(
            **_valid_args(
                group_by=GroupBy(
                    property="revenue",
                    property_type="number",
                    bucket_size=0,
                    bucket_min=0,
                    bucket_max=100,
                )
            )
        )
        assert any(e.code == "V12_BUCKET_SIZE_POSITIVE" for e in errors)

    def test_v12b_bucket_requires_number(self) -> None:
        """V12b: bucket_size with non-number type produces error."""
        errors = validate_query_args(
            **_valid_args(
                group_by=GroupBy(
                    property="country",
                    property_type="string",
                    bucket_size=10,
                    bucket_min=0,
                    bucket_max=100,
                )
            )
        )
        assert any(e.code == "V12B_BUCKET_REQUIRES_NUMBER" for e in errors)

    def test_v13_metric_math_property(self) -> None:
        """V13: Metric with property math and no property produces error."""
        errors = validate_query_args(
            **_valid_args(events=[Metric("Purchase", math="average")])
        )
        assert any(e.code == "V13_METRIC_MATH_PROPERTY" for e in errors)

    def test_v13_valid_metric(self) -> None:
        """V13: Metric with property math and property is valid."""
        errors = validate_query_args(
            **_valid_args(
                events=[Metric("Purchase", math="average", property="amount")]
            )
        )
        assert not any(e.code == "V13_METRIC_MATH_PROPERTY" for e in errors)

    def test_collects_all_errors(self) -> None:
        """Multiple violations produce multiple errors."""
        errors = validate_query_args(
            **_valid_args(
                events=[],
                math="average",
                last=-1,
            )
        )
        codes = {e.code for e in errors}
        assert "V0_NO_EVENTS" in codes
        assert "V1_MATH_REQUIRES_PROPERTY" in codes
        assert "V7_LAST_POSITIVE" in codes


# =============================================================================
# Layer 2: validate_bookmark tests
# =============================================================================


class TestValidateBookmarkLayer2:
    """Tests for Layer 2 bookmark structure validation."""

    def test_valid_bookmark_no_errors(self) -> None:
        """Valid bookmark produces empty error list."""
        errors = validate_bookmark(_minimal_bookmark())
        assert errors == []

    def test_b1_missing_sections(self) -> None:
        """B1: Missing sections produces error."""
        errors = validate_bookmark({"displayOptions": {"chartType": "line"}})
        assert any(e.code == "B1_MISSING_SECTIONS" for e in errors)

    def test_b2_missing_display_options(self) -> None:
        """B2: Missing displayOptions produces error."""
        errors = validate_bookmark(
            {"sections": {"show": [{"behavior": {"type": "event"}}]}}
        )
        assert any(e.code == "B2_MISSING_DISPLAY_OPTIONS" for e in errors)

    def test_b3_missing_show(self) -> None:
        """B3: Missing show produces error."""
        errors = validate_bookmark(
            {
                "sections": {"time": [], "filter": []},
                "displayOptions": {"chartType": "line"},
            }
        )
        assert any(e.code == "B3_MISSING_SHOW" for e in errors)

    def test_b4_show_empty(self) -> None:
        """B4: Empty show list produces error."""
        errors = validate_bookmark(
            {
                "sections": {"show": []},
                "displayOptions": {"chartType": "line"},
            }
        )
        assert any(e.code == "B4_SHOW_EMPTY" for e in errors)

    def test_b5_invalid_chart_type(self) -> None:
        """B5: Invalid chartType produces error with suggestions."""
        bm = _minimal_bookmark()
        bm["displayOptions"]["chartType"] = "barchart"
        errors = validate_bookmark(bm)
        chart_errors = [e for e in errors if e.code == "B5_INVALID_CHART_TYPE"]
        assert len(chart_errors) == 1
        assert chart_errors[0].suggestion is not None
        assert "bar" in chart_errors[0].suggestion

    def test_b5_missing_chart_type(self) -> None:
        """B5: Missing chartType produces error."""
        bm = _minimal_bookmark()
        del bm["displayOptions"]["chartType"]
        errors = validate_bookmark(bm)
        assert any(e.code == "B5_INVALID_CHART_TYPE" for e in errors)

    def test_b6_missing_behavior(self) -> None:
        """B6: Show clause without behavior produces error."""
        bm = _minimal_bookmark()
        bm["sections"]["show"] = [{"measurement": {"math": "total"}}]
        errors = validate_bookmark(bm)
        assert any(e.code == "B6_MISSING_BEHAVIOR" for e in errors)

    def test_b9_invalid_math(self) -> None:
        """B9: Invalid math type produces error with suggestions."""
        bm = _minimal_bookmark()
        bm["sections"]["show"][0]["measurement"]["math"] = "totl"
        errors = validate_bookmark(bm)
        math_errors = [e for e in errors if e.code == "B9_INVALID_MATH"]
        assert len(math_errors) == 1
        assert math_errors[0].suggestion is not None
        assert "total" in math_errors[0].suggestion

    def test_b10_math_missing_property(self) -> None:
        """B10: Property math without property produces warning."""
        bm = _minimal_bookmark()
        bm["sections"]["show"][0]["measurement"]["math"] = "average"
        errors = validate_bookmark(bm)
        prop_errors = [e for e in errors if e.code == "B10_MATH_MISSING_PROPERTY"]
        assert len(prop_errors) == 1
        assert prop_errors[0].severity == "warning"
        assert prop_errors[0].fix is not None

    def test_b12_invalid_time_unit(self) -> None:
        """B12: Invalid time unit produces error."""
        bm = _minimal_bookmark()
        bm["sections"]["time"] = [{"unit": "fortnite"}]
        errors = validate_bookmark(bm)
        assert any(e.code == "B12_INVALID_TIME_UNIT" for e in errors)

    def test_b14_invalid_filter_type(self) -> None:
        """B14: Invalid filterType produces error."""
        bm = _minimal_bookmark()
        bm["sections"]["filter"] = [
            {
                "filterType": "nope",
                "filterOperator": "equals",
                "value": "country",
                "filterValue": ["US"],
            }
        ]
        errors = validate_bookmark(bm)
        assert any(e.code == "B14_INVALID_FILTER_TYPE" for e in errors)

    def test_b15_invalid_filter_operator_warning(self) -> None:
        """B15: Invalid filterOperator produces warning."""
        bm = _minimal_bookmark()
        bm["sections"]["filter"] = [
            {
                "filterType": "string",
                "filterOperator": "approximately",
                "value": "country",
                "filterValue": ["US"],
            }
        ]
        errors = validate_bookmark(bm)
        op_errors = [e for e in errors if e.code == "B15_INVALID_FILTER_OPERATOR"]
        assert len(op_errors) == 1
        assert op_errors[0].severity == "warning"

    def test_b15_insights_date_operators_valid(self) -> None:
        """B15: InsightsDateRangeType operators pass validation."""
        insights_date_ops = [
            "was on",
            "was not on",
            "was in the",
            "was not in the",
            "was between",
            "was not between",
            "was less than",
            "was before",
            "was since",
            "was in the next",
        ]
        for op in insights_date_ops:
            bm = _minimal_bookmark()
            bm["sections"]["filter"] = [
                {
                    "filterType": "datetime",
                    "filterOperator": op,
                    "value": "created",
                    "filterValue": "2024-01-01",
                }
            ]
            errors = validate_bookmark(bm)
            op_errors = [e for e in errors if e.code == "B15_INVALID_FILTER_OPERATOR"]
            assert len(op_errors) == 0, (
                f"Operator {op!r} should be valid but got B15 warning"
            )

    def test_b18_missing_filter_property(self) -> None:
        """B18: Filter without property identifier produces error."""
        bm = _minimal_bookmark()
        bm["sections"]["filter"] = [
            {
                "filterType": "string",
                "filterOperator": "equals",
                "filterValue": ["US"],
            }
        ]
        errors = validate_bookmark(bm)
        assert any(e.code == "B18_MISSING_FILTER_PROPERTY" for e in errors)

    def test_formula_show_clause_valid(self) -> None:
        """Formula show clauses are accepted."""
        bm = _minimal_bookmark()
        bm["sections"]["show"].append(
            {"formula": {"definition": "(A/B)*100", "name": "Rate"}}
        )
        errors = validate_bookmark(bm)
        assert not any(e.code == "B6_MISSING_BEHAVIOR" for e in errors)

    def test_valid_filter_passes(self) -> None:
        """Valid filter clause produces no errors."""
        bm = _minimal_bookmark()
        bm["sections"]["filter"] = [
            {
                "filterType": "string",
                "filterOperator": "equals",
                "value": "country",
                "filterValue": ["US"],
                "resourceType": "events",
            }
        ]
        errors = validate_bookmark(bm)
        filter_errors = [
            e
            for e in errors
            if e.code.startswith("B14")
            or e.code.startswith("B15")
            or e.code.startswith("B18")
        ]
        assert filter_errors == []

    def test_valid_group_passes(self) -> None:
        """Valid group clause produces no errors."""
        bm = _minimal_bookmark()
        bm["sections"]["group"] = [
            {
                "propertyName": "platform",
                "propertyType": "string",
                "resourceType": "events",
            }
        ]
        errors = validate_bookmark(bm)
        group_errors = [e for e in errors if e.code.startswith("B17")]
        assert group_errors == []
