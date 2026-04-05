"""Unit tests for Query API types: Metric, Formula, QueryResult.

Tests Metric dataclass construction, defaults, immutability (T006),
Formula dataclass, and QueryResult.df behavior per mode (T045, T049).
"""

from __future__ import annotations

from typing import Any

import pytest

from mixpanel_data._internal.bookmark_enums import (
    MATH_NO_PER_USER,
    MATH_PROPERTY_OPTIONAL,
    MATH_REQUIRING_PROPERTY,
)
from mixpanel_data.types import (
    Filter,
    Formula,
    Metric,
    QueryResult,
)

# =============================================================================
# T006: Metric dataclass tests
# =============================================================================


class TestMetricConstruction:
    """Tests for Metric frozen dataclass construction and defaults."""

    def test_event_only_uses_defaults(self) -> None:
        """Metric("Login") uses default math="total" and None for optional fields."""
        m = Metric("Login")
        assert m.event == "Login"
        assert m.math == "total"
        assert m.property is None
        assert m.per_user is None
        assert m.filters is None

    def test_all_fields_set(self) -> None:
        """Metric with all fields explicitly set."""
        m = Metric(
            "Purchase",
            math="average",
            property="amount",
            per_user="total",
            filters=[],
        )
        assert m.event == "Purchase"
        assert m.math == "average"
        assert m.property == "amount"
        assert m.per_user == "total"
        assert m.filters == []

    def test_keyword_construction(self) -> None:
        """Metric can be constructed with keyword arguments."""
        m = Metric(event="Login", math="unique")
        assert m.event == "Login"
        assert m.math == "unique"

    def test_immutability(self) -> None:
        """Metric is frozen and cannot be modified after construction."""
        m = Metric("Login")
        with pytest.raises(AttributeError):
            m.event = "Signup"  # type: ignore[misc]

    def test_equality_same_fields(self) -> None:
        """Two Metrics with identical fields are equal."""
        m1 = Metric("Login", math="unique")
        m2 = Metric("Login", math="unique")
        assert m1 == m2

    def test_inequality_different_event(self) -> None:
        """Metrics with different events are not equal."""
        assert Metric("Login") != Metric("Signup")

    def test_inequality_different_math(self) -> None:
        """Metrics with different math are not equal."""
        assert Metric("Login", math="total") != Metric("Login", math="unique")


class TestTypeConstants:
    """Tests for query type aliases and constants."""

    def test_math_requiring_property_contents(self) -> None:
        """MATH_REQUIRING_PROPERTY contains all property-based aggregations."""
        expected = {
            "average",
            "median",
            "min",
            "max",
            "p25",
            "p75",
            "p90",
            "p99",
            "custom_percentile",
            "percentile",
            "histogram",
        }
        assert expected == MATH_REQUIRING_PROPERTY

    def test_math_property_optional_contents(self) -> None:
        """MATH_PROPERTY_OPTIONAL contains types that optionally accept property."""
        assert {"total"} == MATH_PROPERTY_OPTIONAL

    def test_math_no_per_user_contents(self) -> None:
        """MATH_NO_PER_USER contains DAU/WAU/MAU/unique."""
        assert {"dau", "wau", "mau", "unique"} == MATH_NO_PER_USER

    def test_math_requiring_property_immutable(self) -> None:
        """MATH_REQUIRING_PROPERTY is a frozenset."""
        assert isinstance(MATH_REQUIRING_PROPERTY, frozenset)

    def test_math_no_per_user_immutable(self) -> None:
        """MATH_NO_PER_USER is a frozenset."""
        assert isinstance(MATH_NO_PER_USER, frozenset)


# =============================================================================
# QueryResult tests
# =============================================================================


class TestQueryResultConstruction:
    """Tests for QueryResult dataclass construction."""

    def test_basic_construction(self) -> None:
        """QueryResult with all required fields."""
        qr = QueryResult(
            computed_at="2024-01-01T00:00:00Z",
            from_date="2024-01-01",
            to_date="2024-01-31",
            headers=["$metric"],
            series={"Login [Total Events]": {"2024-01-01": 100}},
            params={"test": True},
            meta={"min_sampling_factor": 1.0},
        )
        assert qr.computed_at == "2024-01-01T00:00:00Z"
        assert qr.from_date == "2024-01-01"
        assert qr.to_date == "2024-01-31"

    def test_immutability(self) -> None:
        """QueryResult is frozen."""
        qr = QueryResult(
            computed_at="",
            from_date="",
            to_date="",
            params={},
            meta={},
        )
        with pytest.raises(AttributeError):
            qr.computed_at = "changed"  # type: ignore[misc]

    def test_params_preserved(self) -> None:
        """QueryResult.params contains the bookmark dict sent to API."""
        params: dict[str, Any] = {"sections": {"show": []}, "displayOptions": {}}
        qr = QueryResult(
            computed_at="",
            from_date="",
            to_date="",
            params=params,
            meta={},
        )
        assert qr.params is params

    def test_meta_preserved(self) -> None:
        """QueryResult.meta contains response metadata."""
        meta: dict[str, Any] = {
            "min_sampling_factor": 1.0,
            "is_segmentation_limit_hit": False,
        }
        qr = QueryResult(
            computed_at="",
            from_date="",
            to_date="",
            params={},
            meta=meta,
        )
        assert qr.meta is meta


class TestQueryResultDataFrame:
    """Tests for QueryResult.df property."""

    def test_timeseries_columns(self) -> None:
        """Timeseries mode produces date, event, count columns."""
        qr = QueryResult(
            computed_at="",
            from_date="",
            to_date="",
            series={
                "Login [Total Events]": {
                    "2024-01-01": 100,
                    "2024-01-02": 200,
                },
            },
            params={},
            meta={},
        )
        df = qr.df
        assert list(df.columns) == ["date", "event", "count"]
        assert len(df) == 2

    def test_timeseries_values(self) -> None:
        """Timeseries DataFrame has correct values."""
        qr = QueryResult(
            computed_at="",
            from_date="",
            to_date="",
            series={
                "Login [Total Events]": {
                    "2024-01-01": 100,
                    "2024-01-02": 200,
                },
            },
            params={},
            meta={},
        )
        df = qr.df
        row0 = df.iloc[0]
        assert row0["date"] == "2024-01-01"
        assert row0["event"] == "Login [Total Events]"
        assert row0["count"] == 100

    def test_hourly_timestamps_preserved(self) -> None:
        """Hourly timestamp keys are preserved (not truncated to date)."""
        qr = QueryResult(
            computed_at="",
            from_date="",
            to_date="",
            series={
                "Login [Total Events]": {
                    "2024-01-01T00:00:00": 100,
                    "2024-01-01T01:00:00": 110,
                    "2024-01-01T02:00:00": 120,
                },
            },
            params={},
            meta={},
        )
        df = qr.df
        assert len(df) == 3
        dates = list(df["date"])
        assert dates[0] == "2024-01-01T00:00:00"
        assert dates[1] == "2024-01-01T01:00:00"
        assert dates[2] == "2024-01-01T02:00:00"

    def test_total_mode_columns(self) -> None:
        """Total mode produces event, count columns (no date)."""
        qr = QueryResult(
            computed_at="",
            from_date="",
            to_date="",
            series={"Login [Unique Users]": {"all": 500}},
            params={},
            meta={},
        )
        df = qr.df
        assert list(df.columns) == ["event", "count"]
        assert len(df) == 1
        assert df.iloc[0]["count"] == 500

    def test_empty_series(self) -> None:
        """Empty series returns empty DataFrame with expected columns."""
        qr = QueryResult(
            computed_at="",
            from_date="",
            to_date="",
            series={},
            params={},
            meta={},
        )
        df = qr.df
        assert len(df) == 0
        assert "date" in df.columns

    def test_multi_metric_timeseries(self) -> None:
        """Multiple metrics in timeseries produce rows for each."""
        qr = QueryResult(
            computed_at="",
            from_date="",
            to_date="",
            series={
                "Login [Total]": {"2024-01-01": 100},
                "Signup [Total]": {"2024-01-01": 50},
            },
            params={},
            meta={},
        )
        df = qr.df
        assert len(df) == 2
        events = set(df["event"])
        assert events == {"Login [Total]", "Signup [Total]"}

    def test_df_caching(self) -> None:
        """DataFrame is cached on first access."""
        qr = QueryResult(
            computed_at="",
            from_date="",
            to_date="",
            series={"A": {"2024-01-01": 1}},
            params={},
            meta={},
        )
        df1 = qr.df
        df2 = qr.df
        assert df1 is df2


class TestQueryResultToDict:
    """Tests for QueryResult.to_dict() serialization."""

    def test_to_dict_contains_all_fields(self) -> None:
        """to_dict() returns all QueryResult fields."""
        qr = QueryResult(
            computed_at="ts",
            from_date="f",
            to_date="t",
            headers=["h"],
            series={"s": {}},
            params={"p": 1},
            meta={"m": 2},
        )
        d = qr.to_dict()
        assert d["computed_at"] == "ts"
        assert d["from_date"] == "f"
        assert d["to_date"] == "t"
        assert d["headers"] == ["h"]
        assert d["series"] == {"s": {}}
        assert d["params"] == {"p": 1}
        assert d["meta"] == {"m": 2}


# =============================================================================
# T022: Filter class method tests (US3)
# =============================================================================


class TestFilterConstruction:
    """Tests for Filter class method construction."""

    def test_equals_string(self) -> None:
        """Filter.equals creates correct filter."""
        from mixpanel_data.types import Filter

        f = Filter.equals("country", "US")
        assert f._property == "country"
        assert f._operator == "equals"
        assert f._value == ["US"]
        assert f._property_type == "string"

    def test_equals_list(self) -> None:
        """Filter.equals with list preserves list."""
        from mixpanel_data.types import Filter

        f = Filter.equals("country", ["US", "CA"])
        assert f._value == ["US", "CA"]

    def test_not_equals(self) -> None:
        """Filter.not_equals creates correct filter."""
        from mixpanel_data.types import Filter

        f = Filter.not_equals("browser", "IE")
        assert f._operator == "does not equal"

    def test_contains(self) -> None:
        """Filter.contains uses plain string value."""
        from mixpanel_data.types import Filter

        f = Filter.contains("browser", "Chrome")
        assert f._operator == "contains"
        assert f._value == "Chrome"

    def test_not_contains(self) -> None:
        """Filter.not_contains creates correct filter."""
        from mixpanel_data.types import Filter

        f = Filter.not_contains("url", "test")
        assert f._operator == "does not contain"

    def test_greater_than(self) -> None:
        """Filter.greater_than creates numeric filter."""
        from mixpanel_data.types import Filter

        f = Filter.greater_than("age", 18)
        assert f._operator == "is greater than"
        assert f._value == 18
        assert f._property_type == "number"

    def test_less_than(self) -> None:
        """Filter.less_than creates numeric filter."""
        from mixpanel_data.types import Filter

        f = Filter.less_than("amount", 100)
        assert f._operator == "is less than"
        assert f._value == 100

    def test_between(self) -> None:
        """Filter.between creates range filter."""
        from mixpanel_data.types import Filter

        f = Filter.between("age", 18, 65)
        assert f._operator == "is between"
        assert f._value == [18, 65]

    def test_is_set(self) -> None:
        """Filter.is_set creates existence filter."""
        from mixpanel_data.types import Filter

        f = Filter.is_set("email")
        assert f._operator == "is set"
        assert f._value is None

    def test_is_not_set(self) -> None:
        """Filter.is_not_set creates non-existence filter."""
        from mixpanel_data.types import Filter

        f = Filter.is_not_set("phone")
        assert f._operator == "is not set"

    def test_is_true(self) -> None:
        """Filter.is_true creates boolean filter."""
        from mixpanel_data.types import Filter

        f = Filter.is_true("verified")
        assert f._operator == "true"
        assert f._property_type == "boolean"

    def test_is_false(self) -> None:
        """Filter.is_false creates boolean filter."""
        from mixpanel_data.types import Filter

        f = Filter.is_false("opted_out")
        assert f._operator == "false"

    def test_immutability(self) -> None:
        """Filter is frozen."""
        from mixpanel_data.types import Filter

        f = Filter.equals("country", "US")
        with pytest.raises(AttributeError):
            f._property = "browser"  # type: ignore[misc]

    def test_resource_type_default(self) -> None:
        """Default resource_type is 'events'."""
        from mixpanel_data.types import Filter

        f = Filter.equals("country", "US")
        assert f._resource_type == "events"

    def test_resource_type_people(self) -> None:
        """resource_type='people' is supported."""
        from mixpanel_data.types import Filter

        f = Filter.equals("city", "SF", resource_type="people")
        assert f._resource_type == "people"


# =============================================================================
# T023: GroupBy construction tests (US3)
# =============================================================================


class TestGroupByConstruction:
    """Tests for GroupBy frozen dataclass construction."""

    def test_string_property_defaults(self) -> None:
        """GroupBy with property only uses string type default."""
        from mixpanel_data.types import GroupBy

        g = GroupBy("country")
        assert g.property == "country"
        assert g.property_type == "string"
        assert g.bucket_size is None

    def test_numeric_with_buckets(self) -> None:
        """GroupBy with full numeric bucketing."""
        from mixpanel_data.types import GroupBy

        g = GroupBy(
            "revenue",
            property_type="number",
            bucket_size=50,
            bucket_min=0,
            bucket_max=500,
        )
        assert g.property_type == "number"
        assert g.bucket_size == 50
        assert g.bucket_min == 0
        assert g.bucket_max == 500

    def test_immutability(self) -> None:
        """GroupBy is frozen."""
        from mixpanel_data.types import GroupBy

        g = GroupBy("country")
        with pytest.raises(AttributeError):
            g.property = "city"  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two GroupBys with same fields are equal."""
        from mixpanel_data.types import GroupBy

        g1 = GroupBy("country")
        g2 = GroupBy("country")
        assert g1 == g2


# =============================================================================
# Metric.filters_combinator tests
# =============================================================================


class TestMetricFiltersCombinator:
    """Tests for Metric.filters_combinator field."""

    def test_default_is_all(self) -> None:
        """filters_combinator defaults to 'all'."""
        m = Metric("Login")
        assert m.filters_combinator == "all"

    def test_set_to_any(self) -> None:
        """filters_combinator can be set to 'any'."""
        m = Metric("Login", filters_combinator="any")
        assert m.filters_combinator == "any"

    def test_equality_includes_combinator(self) -> None:
        """Metrics with different filters_combinator are not equal."""
        m1 = Metric("Login", filters_combinator="all")
        m2 = Metric("Login", filters_combinator="any")
        assert m1 != m2


# =============================================================================
# Formula dataclass tests
# =============================================================================


class TestFormulaConstruction:
    """Tests for Formula frozen dataclass construction and defaults."""

    def test_expression_only(self) -> None:
        """Formula with expression only uses None label."""
        f = Formula("(B / A) * 100")
        assert f.expression == "(B / A) * 100"
        assert f.label is None

    def test_expression_with_label(self) -> None:
        """Formula with expression and label."""
        f = Formula("(B / A) * 100", label="Conversion %")
        assert f.expression == "(B / A) * 100"
        assert f.label == "Conversion %"

    def test_immutability(self) -> None:
        """Formula is frozen."""
        f = Formula("A + B")
        with pytest.raises(AttributeError):
            f.expression = "C + D"  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two Formulas with same fields are equal."""
        f1 = Formula("A + B", label="Sum")
        f2 = Formula("A + B", label="Sum")
        assert f1 == f2

    def test_inequality(self) -> None:
        """Formulas with different expressions are not equal."""
        assert Formula("A + B") != Formula("A - B")


# =============================================================================
# T055: Date filter factory methods
# =============================================================================


class TestDateFilterConstruction:
    """T055: Date filter factory methods on Filter class."""

    def test_on_creates_datetime_filter(self) -> None:
        """Filter.on() creates absolute date equality filter."""
        f = Filter.on("created", "2024-06-15")
        assert f._property == "created"
        assert f._operator == "was on"
        assert f._value == "2024-06-15"
        assert f._property_type == "datetime"
        assert f._date_unit is None

    def test_not_on(self) -> None:
        """Filter.not_on() creates date inequality filter."""
        f = Filter.not_on("created", "2024-06-15")
        assert f._operator == "was not on"
        assert f._value == "2024-06-15"
        assert f._property_type == "datetime"

    def test_before(self) -> None:
        """Filter.before() creates date before filter."""
        f = Filter.before("created", "2024-01-01")
        assert f._operator == "was before"
        assert f._value == "2024-01-01"
        assert f._property_type == "datetime"
        assert f._date_unit is None

    def test_since(self) -> None:
        """Filter.since() creates date since filter."""
        f = Filter.since("created", "2024-01-01")
        assert f._operator == "was since"
        assert f._value == "2024-01-01"
        assert f._property_type == "datetime"

    def test_in_the_last(self) -> None:
        """Filter.in_the_last() creates relative date filter with date_unit."""
        f = Filter.in_the_last("created", 7, "day")
        assert f._operator == "was in the"
        assert f._value == 7
        assert f._date_unit == "day"
        assert f._property_type == "datetime"

    def test_not_in_the_last(self) -> None:
        """Filter.not_in_the_last() creates relative negation filter."""
        f = Filter.not_in_the_last("created", 30, "day")
        assert f._operator == "was not in the"
        assert f._value == 30
        assert f._date_unit == "day"
        assert f._property_type == "datetime"

    def test_date_between(self) -> None:
        """Filter.date_between() creates date range filter."""
        f = Filter.date_between("created", "2024-01-01", "2024-06-30")
        assert f._operator == "was between"
        assert f._value == ["2024-01-01", "2024-06-30"]
        assert f._property_type == "datetime"
        assert f._date_unit is None

    def test_in_the_last_hour_unit(self) -> None:
        """Filter.in_the_last() supports hour unit."""
        f = Filter.in_the_last("ts", 24, "hour")
        assert f._date_unit == "hour"

    def test_in_the_last_month_unit(self) -> None:
        """Filter.in_the_last() supports month unit."""
        f = Filter.in_the_last("ts", 3, "month")
        assert f._date_unit == "month"

    def test_in_the_last_week_unit(self) -> None:
        """Filter.in_the_last() supports week unit."""
        f = Filter.in_the_last("ts", 2, "week")
        assert f._date_unit == "week"

    def test_immutability_date_filter(self) -> None:
        """Date filter is frozen."""
        f = Filter.on("created", "2024-01-01")
        with pytest.raises(AttributeError):
            f._date_unit = "day"  # type: ignore[misc]

    def test_resource_type_on_date_filter(self) -> None:
        """Date filters support resource_type parameter."""
        f = Filter.on("$created", "2024-01-01", resource_type="people")
        assert f._resource_type == "people"


# =============================================================================
# T056: Date filter input validation
# =============================================================================


class TestDateFilterValidation:
    """T056: Date filter factory method input validation."""

    def test_on_rejects_invalid_date_format(self) -> None:
        """Filter.on() rejects non-YYYY-MM-DD date string."""
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            Filter.on("created", "06/15/2024")

    def test_on_rejects_invalid_calendar_date(self) -> None:
        """Filter.on() rejects impossible calendar date."""
        with pytest.raises(ValueError, match="valid calendar date"):
            Filter.on("created", "2024-02-30")

    def test_before_rejects_invalid_date(self) -> None:
        """Filter.before() rejects invalid date string."""
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            Filter.before("created", "bad-date")

    def test_since_rejects_invalid_date(self) -> None:
        """Filter.since() rejects invalid date string."""
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            Filter.since("created", "2024/01/01")

    def test_date_between_rejects_invalid_from(self) -> None:
        """Filter.date_between() rejects invalid from_date."""
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            Filter.date_between("created", "bad", "2024-06-30")

    def test_date_between_rejects_invalid_to(self) -> None:
        """Filter.date_between() rejects invalid to_date."""
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            Filter.date_between("created", "2024-01-01", "bad")

    def test_date_between_rejects_reversed_dates(self) -> None:
        """Filter.date_between() rejects from > to."""
        with pytest.raises(ValueError, match="must be before"):
            Filter.date_between("created", "2024-12-31", "2024-01-01")

    def test_in_the_last_rejects_zero(self) -> None:
        """Filter.in_the_last() rejects non-positive quantity."""
        with pytest.raises(ValueError, match="positive"):
            Filter.in_the_last("created", 0, "day")

    def test_in_the_last_rejects_negative(self) -> None:
        """Filter.in_the_last() rejects negative quantity."""
        with pytest.raises(ValueError, match="positive"):
            Filter.in_the_last("created", -5, "day")

    def test_not_in_the_last_rejects_zero(self) -> None:
        """Filter.not_in_the_last() rejects non-positive quantity."""
        with pytest.raises(ValueError, match="positive"):
            Filter.not_in_the_last("created", 0, "week")


# =============================================================================
# T063: Custom percentile type support
# =============================================================================


class TestPercentileType:
    """T063: Custom percentile support."""

    def test_math_type_accepts_percentile(self) -> None:
        """MathType literal accepts 'percentile'."""
        m = Metric("Login", math="percentile", property="duration", percentile_value=95)
        assert m.math == "percentile"

    def test_percentile_value_default_none(self) -> None:
        """Metric.percentile_value defaults to None."""
        assert Metric("Login").percentile_value is None

    def test_percentile_value_int(self) -> None:
        """Metric.percentile_value accepts int."""
        m = Metric("Login", math="percentile", property="duration", percentile_value=95)
        assert m.percentile_value == 95

    def test_percentile_value_float(self) -> None:
        """Metric.percentile_value accepts float."""
        m = Metric("X", math="percentile", property="d", percentile_value=99.9)
        assert m.percentile_value == 99.9

    def test_percentile_immutable(self) -> None:
        """percentile_value is frozen."""
        m = Metric("Login", math="percentile", property="d", percentile_value=95)
        with pytest.raises(AttributeError):
            m.percentile_value = 50  # type: ignore[misc]


# =============================================================================
# T067: Histogram math type
# =============================================================================


class TestHistogramType:
    """T067: Histogram math type."""

    def test_math_type_accepts_histogram(self) -> None:
        """MathType literal accepts 'histogram'."""
        m = Metric("Purchase", math="histogram", property="amount")
        assert m.math == "histogram"

    def test_histogram_in_requiring_property(self) -> None:
        """'histogram' is in MATH_REQUIRING_PROPERTY."""
        assert "histogram" in MATH_REQUIRING_PROPERTY
