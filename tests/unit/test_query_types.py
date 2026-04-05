"""Unit tests for Query API types: Metric, Formula, QueryResult.

Tests Metric dataclass construction, defaults, immutability (T006),
Formula dataclass, and QueryResult.df behavior per mode (T045, T049).
"""

from __future__ import annotations

from typing import Any

import pytest

from mixpanel_data.types import (
    NO_PER_USER_MATH_TYPES,
    PROPERTY_MATH_TYPES,
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

    def test_property_math_types_contents(self) -> None:
        """PROPERTY_MATH_TYPES contains all property-based aggregations."""
        expected = {
            "average",
            "median",
            "min",
            "max",
            "p25",
            "p75",
            "p90",
            "p99",
        }
        assert expected == PROPERTY_MATH_TYPES

    def test_property_optional_math_types_contents(self) -> None:
        """PROPERTY_OPTIONAL_MATH_TYPES contains types that optionally accept property."""
        from mixpanel_data.types import PROPERTY_OPTIONAL_MATH_TYPES

        assert {"total"} == PROPERTY_OPTIONAL_MATH_TYPES

    def test_no_per_user_math_types_contents(self) -> None:
        """NO_PER_USER_MATH_TYPES contains DAU/WAU/MAU/unique."""
        assert {"dau", "wau", "mau", "unique"} == NO_PER_USER_MATH_TYPES

    def test_property_math_types_immutable(self) -> None:
        """PROPERTY_MATH_TYPES is a frozenset."""
        assert isinstance(PROPERTY_MATH_TYPES, frozenset)

    def test_no_per_user_math_types_immutable(self) -> None:
        """NO_PER_USER_MATH_TYPES is a frozenset."""
        assert isinstance(NO_PER_USER_MATH_TYPES, frozenset)


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
