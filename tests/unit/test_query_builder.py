"""Tests for the insights query builder.

Pure-function tests — no mocks, no API calls. Validates that typed
arguments produce correct bookmark params JSON.
"""

from __future__ import annotations

# Import will exist after implementation
from mixpanel_data._internal.query_builder import (
    build_insights_params,
)
from mixpanel_data.types import (
    Breakdown,
    BreakdownBucket,
    Filter,
    Formula,
    Metric,
)


class TestBuildInsightsParamsMinimal:
    """Test minimal/simple query param generation."""

    def test_single_event_string_last_30(self) -> None:
        """Simplest case: one metric, last 30 days."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )

        # Top-level structure
        assert "displayOptions" in params
        assert "sections" in params
        assert params["displayOptions"]["chartType"] == "line"

        # Show section
        show = params["sections"]["show"]
        assert len(show) == 1
        clause = show[0]
        assert clause["type"] == "metric"
        assert clause["behavior"]["type"] == "event"
        assert clause["behavior"]["name"] == "Login"
        assert clause["behavior"]["resourceType"] == "events"
        assert clause["measurement"]["math"] == "total"

        # Time section
        time = params["sections"]["time"]
        assert len(time) == 1
        assert time[0]["unit"] == "day"
        # Should use "in the last" date range type
        assert time[0]["dateRangeType"] == "in the last"
        assert time[0]["window"]["value"] == 30
        assert time[0]["window"]["unit"] == "day"

        # Empty sections
        assert params["sections"]["filter"] == []
        assert params["sections"]["group"] == []

    def test_absolute_date_range(self) -> None:
        """Explicit from_date and to_date produce 'between' range."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=None,
            from_date="2025-01-01",
            to_date="2025-03-31",
            chart_type="line",
        )

        time = params["sections"]["time"]
        assert len(time) == 1
        assert time[0]["dateRangeType"] == "between"
        assert time[0]["unit"] == "day"
        assert time[0]["value"] == ["2025-01-01", "2025-03-31"]


class TestBuildShowClause:
    """Test show clause generation for different metric configurations."""

    def test_unique_math(self) -> None:
        """math='unique' sets measurement correctly."""
        params = build_insights_params(
            metrics=[Metric(event="Login", math="unique")],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        assert params["sections"]["show"][0]["measurement"]["math"] == "unique"

    def test_property_aggregation(self) -> None:
        """Property aggregation sets measurement.property."""
        params = build_insights_params(
            metrics=[Metric(event="Purchase", math="average", property="Amount")],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="bar",
        )
        clause = params["sections"]["show"][0]
        assert clause["measurement"]["math"] == "average"
        prop = clause["measurement"]["property"]
        assert prop["name"] == "Amount"
        assert prop["resourceType"] == "events"

    def test_per_user_aggregation(self) -> None:
        """per_user sets measurement.perUserAggregation."""
        params = build_insights_params(
            metrics=[Metric(event="Purchase", math="average", per_user="total")],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="bar",
        )
        clause = params["sections"]["show"][0]
        assert clause["measurement"]["perUserAggregation"] == "total"

    def test_per_metric_filters(self) -> None:
        """Per-metric filters appear in behavior.filters."""
        params = build_insights_params(
            metrics=[
                Metric(
                    event="Purchase",
                    filters=[
                        Filter(
                            property="$browser",
                            operator="equals",
                            value=["Chrome"],
                        )
                    ],
                )
            ],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        behavior = params["sections"]["show"][0]["behavior"]
        assert len(behavior["filters"]) == 1
        f = behavior["filters"][0]
        assert f["value"] == "$browser"
        assert f["filterOperator"] == "equals"
        assert f["filterValue"] == ["Chrome"]

    def test_hidden_metric(self) -> None:
        """hidden=True sets isHidden on the show clause."""
        params = build_insights_params(
            metrics=[Metric(event="Login", hidden=True)],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        assert params["sections"]["show"][0]["isHidden"] is True

    def test_multiple_metrics(self) -> None:
        """Multiple metrics produce multiple show clauses."""
        params = build_insights_params(
            metrics=[
                Metric(event="Sign Up", math="unique"),
                Metric(event="Purchase", math="unique"),
            ],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="week",
            last=90,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        assert len(params["sections"]["show"]) == 2
        assert params["sections"]["show"][0]["behavior"]["name"] == "Sign Up"
        assert params["sections"]["show"][1]["behavior"]["name"] == "Purchase"


class TestBuildFormulaClause:
    """Test formula show clause generation."""

    def test_formula_clause(self) -> None:
        """Formula produces a formula-type show clause."""
        params = build_insights_params(
            metrics=[
                Metric(event="Sign Up"),
                Metric(event="Purchase"),
            ],
            formulas=[Formula(expression="(B / A) * 100", name="Conversion %")],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        # Metrics + formula
        show = params["sections"]["show"]
        assert len(show) == 3
        formula_clause = show[2]
        assert formula_clause["type"] == "formula"
        assert formula_clause["definition"] == "(B / A) * 100"
        assert formula_clause["name"] == "Conversion %"

    def test_formula_without_name(self) -> None:
        """Formula without name uses expression as name."""
        params = build_insights_params(
            metrics=[Metric(event="A"), Metric(event="B")],
            formulas=[Formula(expression="A + B")],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        formula_clause = params["sections"]["show"][2]
        assert formula_clause["name"] == "A + B"


class TestBuildFilterClause:
    """Test filter section generation."""

    def test_string_equals_filter(self) -> None:
        """String equals filter maps correctly."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[Filter(property="$browser", operator="equals", value=["Chrome"])],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        filters = params["sections"]["filter"]
        assert len(filters) == 1
        f = filters[0]
        assert f["value"] == "$browser"
        assert f["filterOperator"] == "equals"
        assert f["filterValue"] == ["Chrome"]
        assert f["resourceType"] == "events"
        assert f["filterType"] == "string"
        assert f["defaultType"] == "string"

    def test_number_filter(self) -> None:
        """Number filter uses correct types."""
        params = build_insights_params(
            metrics=[Metric(event="Purchase")],
            formulas=[],
            where=[
                Filter(
                    property="amount",
                    operator="is greater than",
                    value=100,
                    property_type="number",
                )
            ],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        f = params["sections"]["filter"][0]
        assert f["filterType"] == "number"
        assert f["filterOperator"] == "is greater than"
        assert f["filterValue"] == 100

    def test_is_set_filter(self) -> None:
        """'is set' filter has null value."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[Filter(property="email", operator="is set")],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        f = params["sections"]["filter"][0]
        assert f["filterOperator"] == "is set"
        assert f["filterValue"] is None

    def test_people_filter(self) -> None:
        """User profile filter uses resource_type='people'."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[
                Filter(
                    property="plan",
                    operator="equals",
                    value=["premium"],
                    resource_type="people",
                )
            ],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        f = params["sections"]["filter"][0]
        assert f["resourceType"] == "people"

    def test_multiple_filters(self) -> None:
        """Multiple filters produce multiple filter entries."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[
                Filter(property="$browser", operator="equals", value=["Chrome"]),
                Filter(property="$country_code", operator="equals", value=["US"]),
            ],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        assert len(params["sections"]["filter"]) == 2


class TestBuildGroupClause:
    """Test group (breakdown) section generation."""

    def test_string_breakdown(self) -> None:
        """String property breakdown maps correctly."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[],
            group_by=[Breakdown(property="$browser")],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        groups = params["sections"]["group"]
        assert len(groups) == 1
        g = groups[0]
        assert g["value"] == "$browser"
        assert g["propertyName"] == "$browser"
        assert g["resourceType"] == "events"
        assert g["propertyType"] == "string"
        assert g["propertyDefaultType"] == "string"

    def test_numeric_breakdown_with_bucket(self) -> None:
        """Numeric breakdown with bucketing config."""
        params = build_insights_params(
            metrics=[Metric(event="Purchase")],
            formulas=[],
            where=[],
            group_by=[
                Breakdown(
                    property="amount",
                    property_type="number",
                    bucket=BreakdownBucket(size=10, min=0, max=100),
                )
            ],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="bar",
        )
        g = params["sections"]["group"][0]
        assert g["propertyType"] == "number"
        assert g["customBucket"]["bucketSize"] == 10
        assert g["customBucket"]["min"] == 0
        assert g["customBucket"]["max"] == 100

    def test_people_breakdown(self) -> None:
        """User property breakdown uses resource_type='people'."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[],
            group_by=[Breakdown(property="plan", resource_type="people")],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        g = params["sections"]["group"][0]
        assert g["resourceType"] == "people"

    def test_multiple_breakdowns(self) -> None:
        """Multiple breakdowns produce multiple group entries."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[],
            group_by=[
                Breakdown(property="$browser"),
                Breakdown(property="$os"),
            ],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        assert len(params["sections"]["group"]) == 2


class TestBuildTimeClause:
    """Test time section generation."""

    def test_relative_time_day(self) -> None:
        """last=30, time_unit='day' produces correct time clause."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        t = params["sections"]["time"][0]
        assert t["dateRangeType"] == "in the last"
        assert t["unit"] == "day"
        assert t["window"]["unit"] == "day"
        assert t["window"]["value"] == 30

    def test_relative_time_week(self) -> None:
        """last=12, time_unit='week' produces weekly granularity."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="week",
            last=12,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        t = params["sections"]["time"][0]
        assert t["unit"] == "week"
        assert t["window"]["value"] == 12

    def test_absolute_date_range(self) -> None:
        """Explicit dates produce 'between' date range type."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="month",
            last=None,
            from_date="2024-06-01",
            to_date="2024-12-31",
            chart_type="line",
        )
        t = params["sections"]["time"][0]
        assert t["dateRangeType"] == "between"
        assert t["unit"] == "month"
        assert t["value"] == ["2024-06-01", "2024-12-31"]


class TestChartType:
    """Test chart type configuration."""

    def test_bar_chart(self) -> None:
        """bar chart type is set correctly."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="bar",
        )
        assert params["displayOptions"]["chartType"] == "bar"

    def test_table_chart(self) -> None:
        """table chart type is set correctly."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="table",
        )
        assert params["displayOptions"]["chartType"] == "table"


class TestComplexQueries:
    """Test complex multi-metric, multi-filter, multi-breakdown queries."""

    def test_full_query(self) -> None:
        """Complex query with metrics, filters, breakdowns, and formula."""
        params = build_insights_params(
            metrics=[
                Metric(
                    event="Purchase",
                    math="average",
                    property="revenue",
                    filters=[
                        Filter(
                            property="$browser",
                            operator="equals",
                            value=["Chrome", "Safari"],
                        )
                    ],
                ),
                Metric(event="Sign Up", math="unique"),
            ],
            formulas=[Formula(expression="A / B", name="Revenue per Signup")],
            where=[
                Filter(
                    property="plan_type",
                    operator="equals",
                    value=["premium"],
                )
            ],
            group_by=[
                Breakdown(property="$os"),
                Breakdown(property="plan_tier"),
            ],
            time_unit="month",
            last=None,
            from_date="2025-01-01",
            to_date="2025-03-31",
            chart_type="bar",
        )

        # Verify structure
        assert params["displayOptions"]["chartType"] == "bar"

        show = params["sections"]["show"]
        assert len(show) == 3  # 2 metrics + 1 formula

        # First metric
        assert show[0]["behavior"]["name"] == "Purchase"
        assert show[0]["measurement"]["math"] == "average"
        assert show[0]["measurement"]["property"]["name"] == "revenue"
        assert len(show[0]["behavior"]["filters"]) == 1

        # Second metric
        assert show[1]["behavior"]["name"] == "Sign Up"
        assert show[1]["measurement"]["math"] == "unique"

        # Formula
        assert show[2]["type"] == "formula"
        assert show[2]["definition"] == "A / B"

        # Global filters
        assert len(params["sections"]["filter"]) == 1
        assert params["sections"]["filter"][0]["filterValue"] == ["premium"]

        # Breakdowns
        assert len(params["sections"]["group"]) == 2
        assert params["sections"]["group"][0]["value"] == "$os"
        assert params["sections"]["group"][1]["value"] == "plan_tier"

        # Time
        t = params["sections"]["time"][0]
        assert t["dateRangeType"] == "between"
        assert t["value"] == ["2025-01-01", "2025-03-31"]


class TestEdgeCases:
    """Test edge cases and validation."""

    def test_empty_filters_and_groups(self) -> None:
        """Empty where/group_by produce empty arrays."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        assert params["sections"]["filter"] == []
        assert params["sections"]["group"] == []

    def test_filters_combinator_any(self) -> None:
        """filters_combinator='any' sets filtersDeterminer."""
        params = build_insights_params(
            metrics=[
                Metric(
                    event="Login",
                    filters=[
                        Filter(property="a", operator="equals", value=["1"]),
                    ],
                    filters_combinator="any",
                )
            ],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        behavior = params["sections"]["show"][0]["behavior"]
        assert behavior["filtersDeterminer"] == "any"

    def test_display_options_defaults(self) -> None:
        """Display options include standard defaults."""
        params = build_insights_params(
            metrics=[Metric(event="Login")],
            formulas=[],
            where=[],
            group_by=[],
            time_unit="day",
            last=30,
            from_date=None,
            to_date=None,
            chart_type="line",
        )
        display = params["displayOptions"]
        assert display["chartType"] == "line"
        assert display["plotStyle"] == "standard"
        assert display["analysis"] == "linear"
        assert display["value"] == "absolute"
