"""Unit tests for bookmark params generation.

Tests _build_query_params() in Workspace for US1 (basic params),
US2 (aggregation), US3 (filters/groups), US4 (multi-event),
US5 (formula), US6 (analysis mode), US7 (result mode).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mixpanel_data import Formula, Workspace

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def ws(mock_config_manager: MagicMock) -> Workspace:
    """Create Workspace with mocked dependencies for params testing."""
    return Workspace(_config_manager=mock_config_manager)


# =============================================================================
# T008: Basic bookmark params generation (US1)
# =============================================================================


class TestBasicParams:
    """Tests for basic bookmark params generation (single event, time range)."""

    def test_single_event_default_params(self, ws: Workspace) -> None:
        """Single event string produces correct sections.show entry."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        # Verify sections.show has one entry
        show = params["sections"]["show"]
        assert len(show) == 1
        assert show[0]["behavior"]["name"] == "Login"

    def test_relative_time_last_n(self, ws: Workspace) -> None:
        """last=N produces dateRange with 'in the last N days' format."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=7,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        time_section = params["sections"]["time"][0]
        assert time_section["dateRangeType"] == "in the last"
        assert time_section["window"]["value"] == 7
        assert time_section["unit"] == "day"

    def test_absolute_time_range(self, ws: Workspace) -> None:
        """from_date/to_date produces dateRange with explicit dates."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date="2024-01-01",
            to_date="2024-01-31",
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        time_section = params["sections"]["time"][0]
        assert time_section["dateRangeType"] == "between"
        assert time_section["value"] == ["2024-01-01", "2024-01-31"]

    def test_from_date_only(self, ws: Workspace) -> None:
        """from_date without to_date uses 'since' range type."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date="2024-01-01",
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        time_section = params["sections"]["time"][0]
        assert time_section["dateRangeType"] == "between"
        assert time_section["value"][0] == "2024-01-01"
        assert len(time_section["value"]) == 2

    def test_unit_mapping(self, ws: Workspace) -> None:
        """Unit parameter maps correctly to time section."""
        for unit in ("hour", "day", "week", "month", "quarter"):
            params = ws._build_query_params(
                events=["Login"],
                math="total",
                math_property=None,
                per_user=None,
                from_date=None,
                to_date=None,
                last=30,
                unit=unit,
                group_by=None,
                where=None,
                formulas=[],
                rolling=None,
                cumulative=False,
                mode="timeseries",
            )
            assert params["sections"]["time"][0]["unit"] == unit

    def test_default_display_options(self, ws: Workspace) -> None:
        """Default mode='timeseries' produces chartType='line' and analysis='linear'."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        display = params["displayOptions"]
        assert display["chartType"] == "line"
        assert display["analysis"] == "linear"

    def test_show_entry_measurement_defaults(self, ws: Workspace) -> None:
        """Default measurement is total event count."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        show_entry = params["sections"]["show"][0]
        assert show_entry["type"] == "metric"
        assert show_entry["measurement"]["math"] == "total"


# =============================================================================
# T017: Aggregation params (US2)
# =============================================================================


class TestAggregationParams:
    """Tests for aggregation params generation."""

    def test_math_unique(self, ws: Workspace) -> None:
        """math='unique' maps to event_type='unique'."""
        params = ws._build_query_params(
            events=["Login"],
            math="unique",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert params["sections"]["show"][0]["measurement"]["math"] == "unique"

    def test_math_dau(self, ws: Workspace) -> None:
        """math='dau' maps to event_type='dau'."""
        params = ws._build_query_params(
            events=["Login"],
            math="dau",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert params["sections"]["show"][0]["measurement"]["math"] == "dau"

    def test_math_property_mapping(self, ws: Workspace) -> None:
        """math_property maps to measurement.property."""
        params = ws._build_query_params(
            events=["Purchase"],
            math="average",
            math_property="amount",
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        m = params["sections"]["show"][0]["measurement"]
        assert m["math"] == "average"
        assert m["property"]["name"] == "amount"

    def test_per_user_mapping(self, ws: Workspace) -> None:
        """per_user maps to measurement.perUserAggregation."""
        params = ws._build_query_params(
            events=["Purchase"],
            math="total",
            math_property="revenue",
            per_user="average",
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        m = params["sections"]["show"][0]["measurement"]
        assert m["perUserAggregation"] == "average"

    def test_metric_overrides_top_level(self, ws: Workspace) -> None:
        """Metric objects override top-level math/property/per_user."""
        from mixpanel_data import Metric

        params = ws._build_query_params(
            events=[Metric("Purchase", math="average", property="revenue")],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        m = params["sections"]["show"][0]["measurement"]
        assert m["math"] == "average"
        assert m["property"]["name"] == "revenue"


# =============================================================================
# T024-T025: Filter and Group params (US3)
# =============================================================================


class TestFilterParams:
    """Tests for filter params generation."""

    def test_string_filter_format(self, ws: Workspace) -> None:
        """Filter.equals produces correct filter entry."""
        from mixpanel_data import Filter

        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=[Filter.equals("country", "US")],
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        f = params["sections"]["filter"][0]
        assert f["value"] == "country"
        assert f["filterOperator"] == "equals"
        assert f["filterValue"] == ["US"]
        assert f["filterType"] == "string"

    def test_numeric_filter_scalar_value(self, ws: Workspace) -> None:
        """Filter.greater_than produces scalar filterValue."""
        from mixpanel_data import Filter

        params = ws._build_query_params(
            events=["Purchase"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=[Filter.greater_than("age", 18)],
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        f = params["sections"]["filter"][0]
        assert f["filterValue"] == 18
        assert f["filterType"] == "number"

    def test_contains_filter_plain_string(self, ws: Workspace) -> None:
        """Filter.contains produces plain string filterValue."""
        from mixpanel_data import Filter

        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=[Filter.contains("browser", "Chrome")],
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        f = params["sections"]["filter"][0]
        assert f["filterValue"] == "Chrome"

    def test_multiple_filters(self, ws: Workspace) -> None:
        """Multiple filters produce multiple entries."""
        from mixpanel_data import Filter

        params = ws._build_query_params(
            events=["Purchase"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=[Filter.equals("country", "US"), Filter.greater_than("amount", 10)],
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert len(params["sections"]["filter"]) == 2

    def test_empty_filter_section_when_none(self, ws: Workspace) -> None:
        """Empty filter section when where=None."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert params["sections"]["filter"] == []


class TestGroupParams:
    """Tests for group params generation."""

    def test_string_shorthand(self, ws: Workspace) -> None:
        """String group_by produces correct group entry."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by="platform",
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        g = params["sections"]["group"][0]
        assert g["value"] == "platform"
        assert g["propertyType"] == "string"

    def test_typed_groupby(self, ws: Workspace) -> None:
        """GroupBy object produces correct group entry."""
        from mixpanel_data import GroupBy

        params = ws._build_query_params(
            events=["Purchase"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=GroupBy("amount", property_type="number"),
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        g = params["sections"]["group"][0]
        assert g["value"] == "amount"
        assert g["propertyType"] == "number"

    def test_numeric_bucketing(self, ws: Workspace) -> None:
        """GroupBy with bucket_size produces customBucket."""
        from mixpanel_data import GroupBy

        params = ws._build_query_params(
            events=["Purchase"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=GroupBy(
                "revenue",
                property_type="number",
                bucket_size=50,
                bucket_min=0,
                bucket_max=500,
            ),
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        g = params["sections"]["group"][0]
        assert g["customBucket"]["bucketSize"] == 50
        assert g["customBucket"]["min"] == 0
        assert g["customBucket"]["max"] == 500

    def test_multiple_breakdowns(self, ws: Workspace) -> None:
        """List of group_by produces multiple entries."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=["platform", "country"],
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert len(params["sections"]["group"]) == 2


# =============================================================================
# T032: Multi-event params (US4)
# =============================================================================


class TestMultiEventParams:
    """Tests for multi-event params generation."""

    def test_list_of_strings(self, ws: Workspace) -> None:
        """List of event strings produces multiple show entries."""
        params = ws._build_query_params(
            events=["Signup", "Login", "Purchase"],
            math="unique",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert len(params["sections"]["show"]) == 3
        events = [e["behavior"]["name"] for e in params["sections"]["show"]]
        assert events == ["Signup", "Login", "Purchase"]

    def test_list_of_metrics(self, ws: Workspace) -> None:
        """List of Metric objects produces show entries with per-event math."""
        from mixpanel_data import Metric

        params = ws._build_query_params(
            events=[Metric("Signup", math="unique"), Metric("Purchase", math="total")],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert params["sections"]["show"][0]["measurement"]["math"] == "unique"
        assert params["sections"]["show"][1]["measurement"]["math"] == "total"

    def test_mixed_strings_and_metrics(self, ws: Workspace) -> None:
        """Mixed strings and Metrics: strings inherit top-level math."""
        from mixpanel_data import Metric

        params = ws._build_query_params(
            events=["Login", Metric("Purchase", math="total", property="amount")],
            math="unique",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert params["sections"]["show"][0]["measurement"]["math"] == "unique"
        assert params["sections"]["show"][1]["measurement"]["math"] == "total"


# =============================================================================
# T036: Formula params (US5)
# =============================================================================


class TestFormulaParams:
    """Tests for formula params generation."""

    def test_formula_appended_to_show(self, ws: Workspace) -> None:
        """Formula entry appended to sections.show[]."""
        from mixpanel_data import Metric

        params = ws._build_query_params(
            events=[Metric("Signup", math="unique"), Metric("Purchase", math="unique")],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[Formula("(B / A) * 100", label="Conversion Rate")],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        # 2 metrics + 1 formula = 3 show entries
        assert len(params["sections"]["show"]) == 3
        formula_entry = params["sections"]["show"][2]
        assert formula_entry["type"] == "formula"
        assert formula_entry["definition"] == "(B / A) * 100"
        assert formula_entry["name"] == "Conversion Rate"

    def test_formula_hides_input_metrics(self, ws: Workspace) -> None:
        """Input metrics are marked isHidden when formula is present."""
        from mixpanel_data import Metric

        params = ws._build_query_params(
            events=[Metric("A", math="unique"), Metric("B", math="unique")],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[Formula("B / A")],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert params["sections"]["show"][0]["isHidden"] is True
        assert params["sections"]["show"][1]["isHidden"] is True

    def test_no_formula_no_hidden(self, ws: Workspace) -> None:
        """Without formula, metrics are not hidden."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert params["sections"]["show"][0].get("isHidden") is not True


# =============================================================================
# T041: Analysis mode params (US6)
# =============================================================================


class TestAnalysisModeParams:
    """Tests for analysis mode params generation."""

    def test_rolling_mode(self, ws: Workspace) -> None:
        """rolling=7 produces analysis='rolling' + rollingWindowSize=7."""
        params = ws._build_query_params(
            events=["Signup"],
            math="unique",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=7,
            cumulative=False,
            mode="timeseries",
        )
        d = params["displayOptions"]
        assert d["analysis"] == "rolling"
        assert d["rollingWindowSize"] == 7

    def test_cumulative_mode(self, ws: Workspace) -> None:
        """cumulative=True produces analysis='cumulative'."""
        params = ws._build_query_params(
            events=["Signup"],
            math="unique",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=True,
            mode="timeseries",
        )
        assert params["displayOptions"]["analysis"] == "cumulative"

    def test_default_linear_mode(self, ws: Workspace) -> None:
        """Neither rolling nor cumulative produces analysis='linear'."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert params["displayOptions"]["analysis"] == "linear"


# =============================================================================
# T044: Mode→chartType mapping (US7)
# =============================================================================


class TestModeParams:
    """Tests for mode parameter mapping."""

    def test_timeseries_to_line(self, ws: Workspace) -> None:
        """mode='timeseries' maps to chartType='line'."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert params["displayOptions"]["chartType"] == "line"

    def test_total_to_bar(self, ws: Workspace) -> None:
        """mode='total' maps to chartType='bar'."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="total",
        )
        assert params["displayOptions"]["chartType"] == "bar"

    def test_table_to_table(self, ws: Workspace) -> None:
        """mode='table' maps to chartType='table'."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="table",
        )
        assert params["displayOptions"]["chartType"] == "table"


# =============================================================================
# Per-metric filters in params generation
# =============================================================================


class TestPerMetricFilters:
    """Tests for per-metric filters in _build_query_params."""

    def test_per_metric_filter_in_behavior(self, ws: Workspace) -> None:
        """Metric.filters appear in behavior.filters, not sections.filter."""
        from mixpanel_data import Filter, Metric

        params = ws._build_query_params(
            events=[Metric("Purchase", filters=[Filter.equals("country", "US")])],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        show = params["sections"]["show"]
        assert len(show) == 1
        behavior = show[0]["behavior"]
        assert "filters" in behavior
        assert len(behavior["filters"]) == 1
        f = behavior["filters"][0]
        assert f["value"] == "country"
        assert f["filterValue"] == ["US"]
        assert f["filterOperator"] == "equals"

    def test_per_metric_filter_separate_from_global(self, ws: Workspace) -> None:
        """Per-metric filters and global where are in different locations."""
        from mixpanel_data import Filter, Metric

        params = ws._build_query_params(
            events=[Metric("Purchase", filters=[Filter.equals("country", "US")])],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=Filter.greater_than("age", 18),
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        # Global filter in sections.filter
        global_filters = params["sections"]["filter"]
        assert len(global_filters) == 1
        assert global_filters[0]["value"] == "age"

        # Per-metric filter in show[0].behavior.filters
        per_metric_filters = params["sections"]["show"][0]["behavior"]["filters"]
        assert len(per_metric_filters) == 1
        assert per_metric_filters[0]["value"] == "country"


# =============================================================================
# group_by type validation in params building
# =============================================================================


class TestGroupByTypeError:
    """Tests for group_by element type validation."""

    def test_invalid_group_by_type_raises(self, ws: Workspace) -> None:
        """Non-str, non-GroupBy group_by element raises TypeError."""
        with pytest.raises(TypeError, match="group_by elements must be str or GroupBy"):
            ws._build_query_params(
                events=["Login"],
                math="total",
                math_property=None,
                per_user=None,
                from_date=None,
                to_date=None,
                last=30,
                unit="day",
                group_by=[42],  # type: ignore[list-item]
                where=None,
                formulas=[],
                rolling=None,
                cumulative=False,
                mode="timeseries",
            )


# =============================================================================
# filters_combinator in params building
# =============================================================================


class TestFiltersCombinatorParams:
    """Tests for Metric.filters_combinator in _build_query_params."""

    def test_default_combinator_is_all(self, ws: Workspace) -> None:
        """Default filters_combinator='all' emits filtersDeterminer='all'."""
        from mixpanel_data import Metric

        params = ws._build_query_params(
            events=[Metric("Login")],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        behavior = params["sections"]["show"][0]["behavior"]
        assert behavior["filtersDeterminer"] == "all"

    def test_any_combinator(self, ws: Workspace) -> None:
        """filters_combinator='any' emits filtersDeterminer='any'."""
        from mixpanel_data import Filter, Metric

        params = ws._build_query_params(
            events=[
                Metric(
                    "Login",
                    filters=[Filter.equals("$browser", "Chrome")],
                    filters_combinator="any",
                )
            ],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        behavior = params["sections"]["show"][0]["behavior"]
        assert behavior["filtersDeterminer"] == "any"

    def test_string_event_uses_all(self, ws: Workspace) -> None:
        """Plain string events always use filtersDeterminer='all'."""
        params = ws._build_query_params(
            events=["Login"],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        behavior = params["sections"]["show"][0]["behavior"]
        assert behavior["filtersDeterminer"] == "all"


# =============================================================================
# Formula objects in _build_query_params
# =============================================================================


class TestFormulaObjectParams:
    """Tests for Formula objects passed via formulas parameter."""

    def test_single_formula_object(self, ws: Workspace) -> None:
        """A Formula object produces a formula show clause."""
        from mixpanel_data import Metric

        params = ws._build_query_params(
            events=[Metric("Signup", math="unique"), Metric("Purchase", math="unique")],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[Formula("(B / A) * 100", label="Conv %")],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        show = params["sections"]["show"]
        assert len(show) == 3
        assert show[2]["type"] == "formula"
        assert show[2]["definition"] == "(B / A) * 100"
        assert show[2]["name"] == "Conv %"

    def test_formula_without_label(self, ws: Workspace) -> None:
        """Formula without label omits name from show clause."""
        from mixpanel_data import Metric

        params = ws._build_query_params(
            events=[Metric("A"), Metric("B")],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[Formula("A + B")],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        formula_clause = params["sections"]["show"][2]
        assert formula_clause["type"] == "formula"
        assert "name" not in formula_clause

    def test_multiple_formulas(self, ws: Workspace) -> None:
        """Multiple Formula objects produce multiple formula show clauses."""
        from mixpanel_data import Metric

        params = ws._build_query_params(
            events=[Metric("A"), Metric("B")],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[
                Formula("A + B", label="Sum"),
                Formula("A / B", label="Ratio"),
            ],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        show = params["sections"]["show"]
        assert len(show) == 4  # 2 metrics + 2 formulas
        assert show[2]["definition"] == "A + B"
        assert show[3]["definition"] == "A / B"

    def test_formula_hides_metrics(self, ws: Workspace) -> None:
        """Metrics are hidden when formulas are present."""
        from mixpanel_data import Metric

        params = ws._build_query_params(
            events=[Metric("A"), Metric("B")],
            math="total",
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formulas=[Formula("A / B")],
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        assert params["sections"]["show"][0]["isHidden"] is True
        assert params["sections"]["show"][1]["isHidden"] is True
