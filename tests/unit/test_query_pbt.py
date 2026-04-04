"""Property-based tests for Query API type invariants.

Uses Hypothesis to verify:
- Valid Metric → valid params (no exception from _build_query_params)
- Valid Filter → correct filterValue format
- Validation exhaustiveness (no invalid combination passes through)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from pydantic import SecretStr

from mixpanel_data import Workspace
from mixpanel_data._internal.config import ConfigManager, Credentials
from mixpanel_data.types import (
    PROPERTY_MATH_TYPES,
    Filter,
    QueryResult,
)

# =============================================================================
# Strategies
# =============================================================================

event_names = st.text(
    min_size=1, max_size=50, alphabet=st.characters(categories=("L", "N", "P"))
)
non_property_math = st.sampled_from(["total", "unique", "dau", "wau", "mau"])
property_math = st.sampled_from(
    ["average", "median", "min", "max", "sum", "p25", "p75", "p90", "p99"]
)
all_math = st.sampled_from(
    [
        "total",
        "unique",
        "dau",
        "wau",
        "mau",
        "average",
        "median",
        "min",
        "max",
        "sum",
        "p25",
        "p75",
        "p90",
        "p99",
    ]
)
per_user_agg = st.sampled_from(["average", "total", "min", "max"])
units = st.sampled_from(["hour", "day", "week", "month", "quarter"])
modes = st.sampled_from(["timeseries", "total", "table"])
positive_ints = st.integers(min_value=1, max_value=365)


# =============================================================================
# Helpers
# =============================================================================


def _make_ws() -> Workspace:
    """Create Workspace with mocked config for PBT (inline, not fixture)."""
    creds = Credentials(
        username="test",
        secret=SecretStr("secret"),
        project_id="12345",
        region="us",
    )
    mgr = MagicMock(spec=ConfigManager)
    mgr.resolve_credentials.return_value = creds
    return Workspace(_config_manager=mgr)


# =============================================================================
# T053: Property-based tests
# =============================================================================


class TestMetricParamsInvariant:
    """Valid Metric always produces valid bookmark params."""

    @given(
        event=event_names,
        math=non_property_math,
        unit=units,
        last=positive_ints,
        mode=modes,
    )
    def test_non_property_metric_produces_valid_params(
        self,
        event: str,
        math: str,
        unit: str,
        last: int,
        mode: str,
    ) -> None:
        """Any non-property math Metric produces valid params without exception."""
        ws = _make_ws()
        assume(math not in PROPERTY_MATH_TYPES)
        params = ws._build_query_params(
            events=[event],
            math=math,  # type: ignore[arg-type]
            math_property=None,
            per_user=None,
            from_date=None,
            to_date=None,
            last=last,
            unit=unit,
            group_by=None,
            where=None,
            formula=None,
            formula_label=None,
            rolling=None,
            cumulative=False,
            mode=mode,
        )
        assert "sections" in params
        assert "displayOptions" in params
        assert len(params["sections"]["show"]) == 1

    @given(
        event=event_names,
        math=property_math,
        prop=event_names,
    )
    def test_property_metric_produces_valid_params(
        self,
        event: str,
        math: str,
        prop: str,
    ) -> None:
        """Any property math with property produces valid params."""
        ws = _make_ws()
        params = ws._build_query_params(
            events=[event],
            math=math,  # type: ignore[arg-type]
            math_property=prop,
            per_user=None,
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
            group_by=None,
            where=None,
            formula=None,
            formula_label=None,
            rolling=None,
            cumulative=False,
            mode="timeseries",
        )
        m = params["sections"]["show"][0]["measurement"]
        assert m["property"]["name"] == prop


class TestFilterInvariant:
    """Valid Filter always produces correct filterValue format."""

    @given(prop=event_names, value=st.text(min_size=1, max_size=20))
    def test_equals_always_produces_list(self, prop: str, value: str) -> None:
        """Filter.equals always wraps single string in a list."""
        f = Filter.equals(prop, value)
        assert isinstance(f._value, list)
        assert len(f._value) == 1

    @given(prop=event_names, value=st.integers(min_value=-1000, max_value=1000))
    def test_greater_than_always_produces_scalar(self, prop: str, value: int) -> None:
        """Filter.greater_than always produces scalar numeric value."""
        f = Filter.greater_than(prop, value)
        assert isinstance(f._value, (int, float))

    @given(
        prop=event_names,
        min_val=st.integers(min_value=-100, max_value=100),
        max_val=st.integers(min_value=-100, max_value=100),
    )
    def test_between_always_produces_two_element_list(
        self,
        prop: str,
        min_val: int,
        max_val: int,
    ) -> None:
        """Filter.between always produces [min, max] list."""
        f = Filter.between(prop, min_val, max_val)
        assert isinstance(f._value, list)
        assert len(f._value) == 2


class TestValidationExhaustiveness:
    """Validation rules catch all invalid combinations."""

    @given(math=property_math)
    def test_property_math_without_property_always_fails(
        self,
        math: str,
    ) -> None:
        """Any property math without math_property always raises ValueError."""
        ws = _make_ws()
        with pytest.raises(ValueError, match="requires math_property"):
            ws._validate_query_args(
                events=["E"],
                math=math,  # type: ignore[arg-type]
                math_property=None,
                per_user=None,
                from_date=None,
                to_date=None,
                last=30,
                formula=None,
                rolling=None,
                cumulative=False,
                group_by=None,
            )

    @given(math=st.sampled_from(["dau", "wau", "mau"]), per_user=per_user_agg)
    def test_per_user_with_dau_wau_mau_always_fails(
        self,
        math: str,
        per_user: str,
    ) -> None:
        """per_user with DAU/WAU/MAU always raises ValueError."""
        ws = _make_ws()
        with pytest.raises(ValueError, match="per_user is incompatible"):
            ws._validate_query_args(
                events=["E"],
                math=math,  # type: ignore[arg-type]
                math_property=None,
                per_user=per_user,  # type: ignore[arg-type]
                from_date=None,
                to_date=None,
                last=30,
                formula=None,
                rolling=None,
                cumulative=False,
                group_by=None,
            )


class TestQueryResultDfInvariant:
    """QueryResult.df always returns a DataFrame for valid responses."""

    @given(
        n_metrics=st.integers(min_value=1, max_value=5),
        n_dates=st.integers(min_value=1, max_value=10),
    )
    def test_timeseries_df_always_valid(self, n_metrics: int, n_dates: int) -> None:
        """Timeseries QueryResult.df always returns valid DataFrame."""
        series: dict[str, dict[str, int]] = {}
        for i in range(n_metrics):
            dates = {f"2024-01-{d + 1:02d}": d * 10 + i for d in range(n_dates)}
            series[f"Metric {i}"] = dates

        qr = QueryResult(
            computed_at="",
            from_date="",
            to_date="",
            series=series,
            params={},
            meta={},
        )
        df = qr.df
        assert len(df) == n_metrics * n_dates
        assert list(df.columns) == ["date", "event", "count"]
