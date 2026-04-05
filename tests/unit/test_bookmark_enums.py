"""Tests for bookmark enum constants completeness.

Verifies that the hardcoded enum constants in bookmark_enums.py are
supersets of the Literal types exposed in the public API, and that
each frozenset has the expected cardinality.
"""

from __future__ import annotations

from typing import get_args

from mixpanel_data._internal.bookmark_enums import (
    MATH_NO_PER_USER,
    MATH_PROPERTY_OPTIONAL,
    MATH_REQUIRING_PROPERTY,
    VALID_ANALYSIS_TYPES,
    VALID_CHART_TYPES,
    VALID_FILTER_OPERATORS,
    VALID_FILTERS_DETERMINER,
    VALID_MATH_FUNNELS,
    VALID_MATH_INSIGHTS,
    VALID_MATH_RETENTION,
    VALID_MATH_TYPES,
    VALID_METRIC_TYPES,
    VALID_PER_USER_AGGREGATIONS,
    VALID_PROPERTY_TYPES,
    VALID_QUERY_TIME_UNITS,
    VALID_RESOURCE_TYPES,
    VALID_TIME_UNITS,
)
from mixpanel_data.types import (
    FilterPropertyType,
    MathType,
    PerUserAggregation,
)


class TestMathTypeCompleteness:
    """Verify math type enum coverage."""

    # User-facing math aliases that map to different bookmark values.
    # "percentile" -> "custom_percentile" in bookmark JSON.
    USER_FACING_ALIASES: frozenset[str] = frozenset({"percentile"})

    def test_math_type_literal_subset_of_insights(self) -> None:
        """Every MathType Literal value (excluding aliases) is in VALID_MATH_INSIGHTS."""
        literal_values = set(get_args(MathType)) - self.USER_FACING_ALIASES
        assert literal_values <= VALID_MATH_INSIGHTS, (
            f"MathType values not in VALID_MATH_INSIGHTS: "
            f"{literal_values - VALID_MATH_INSIGHTS}"
        )

    def test_math_type_literal_subset_of_all(self) -> None:
        """Every MathType Literal value (excluding aliases) is in VALID_MATH_TYPES."""
        literal_values = set(get_args(MathType)) - self.USER_FACING_ALIASES
        assert literal_values <= VALID_MATH_TYPES

    def test_insights_subset_of_all(self) -> None:
        """VALID_MATH_INSIGHTS is a subset of VALID_MATH_TYPES."""
        assert VALID_MATH_INSIGHTS <= VALID_MATH_TYPES

    def test_funnels_subset_of_all(self) -> None:
        """VALID_MATH_FUNNELS is a subset of VALID_MATH_TYPES."""
        assert VALID_MATH_FUNNELS <= VALID_MATH_TYPES

    def test_retention_subset_of_all(self) -> None:
        """VALID_MATH_RETENTION is a subset of VALID_MATH_TYPES."""
        assert VALID_MATH_RETENTION <= VALID_MATH_TYPES

    def test_requiring_property_subset_of_insights(self) -> None:
        """MATH_REQUIRING_PROPERTY (excluding aliases) is a subset of VALID_MATH_INSIGHTS."""
        assert (
            MATH_REQUIRING_PROPERTY - self.USER_FACING_ALIASES
        ) <= VALID_MATH_INSIGHTS

    def test_property_optional_subset_of_insights(self) -> None:
        """MATH_PROPERTY_OPTIONAL is a subset of VALID_MATH_INSIGHTS."""
        assert MATH_PROPERTY_OPTIONAL <= VALID_MATH_INSIGHTS

    def test_no_per_user_subset_of_insights(self) -> None:
        """MATH_NO_PER_USER is a subset of VALID_MATH_INSIGHTS."""
        assert MATH_NO_PER_USER <= VALID_MATH_INSIGHTS

    def test_no_overlap_requiring_and_optional(self) -> None:
        """MATH_REQUIRING_PROPERTY and MATH_PROPERTY_OPTIONAL don't overlap."""
        assert set() == MATH_REQUIRING_PROPERTY & MATH_PROPERTY_OPTIONAL


class TestPerUserAggregationCompleteness:
    """Verify per-user aggregation enum coverage."""

    def test_literal_subset_of_valid(self) -> None:
        """Every PerUserAggregation Literal value is in VALID_PER_USER_AGGREGATIONS."""
        literal_values = set(get_args(PerUserAggregation))
        assert literal_values <= VALID_PER_USER_AGGREGATIONS


class TestPropertyTypeCompleteness:
    """Verify property type enum coverage."""

    def test_filter_property_type_subset(self) -> None:
        """Every FilterPropertyType Literal is in VALID_PROPERTY_TYPES."""
        literal_values = set(get_args(FilterPropertyType))
        assert literal_values <= VALID_PROPERTY_TYPES


class TestEnumCardinality:
    """Verify each enum set has expected minimum size (catches accidental deletions)."""

    def test_valid_math_types_size(self) -> None:
        """VALID_MATH_TYPES has at least 20 values."""
        assert len(VALID_MATH_TYPES) >= 20

    def test_valid_math_insights_size(self) -> None:
        """VALID_MATH_INSIGHTS has at least 15 values."""
        assert len(VALID_MATH_INSIGHTS) >= 15

    def test_valid_per_user_size(self) -> None:
        """VALID_PER_USER_AGGREGATIONS has at least 5 values."""
        assert len(VALID_PER_USER_AGGREGATIONS) >= 5

    def test_valid_property_types_size(self) -> None:
        """VALID_PROPERTY_TYPES has at least 6 values."""
        assert len(VALID_PROPERTY_TYPES) >= 6

    def test_valid_time_units_size(self) -> None:
        """VALID_TIME_UNITS has at least 7 values."""
        assert len(VALID_TIME_UNITS) >= 7

    def test_valid_query_time_units_size(self) -> None:
        """VALID_QUERY_TIME_UNITS superset of VALID_TIME_UNITS."""
        assert VALID_TIME_UNITS <= VALID_QUERY_TIME_UNITS

    def test_valid_resource_types_size(self) -> None:
        """VALID_RESOURCE_TYPES has at least 6 values."""
        assert len(VALID_RESOURCE_TYPES) >= 6

    def test_valid_metric_types_size(self) -> None:
        """VALID_METRIC_TYPES has at least 8 values."""
        assert len(VALID_METRIC_TYPES) >= 8

    def test_valid_chart_types_size(self) -> None:
        """VALID_CHART_TYPES has at least 8 values."""
        assert len(VALID_CHART_TYPES) >= 8

    def test_valid_filter_operators_size(self) -> None:
        """VALID_FILTER_OPERATORS has at least 20 values."""
        assert len(VALID_FILTER_OPERATORS) >= 20

    def test_valid_filters_determiner_values(self) -> None:
        """VALID_FILTERS_DETERMINER contains exactly 'any' and 'all'."""
        assert {"any", "all"} == VALID_FILTERS_DETERMINER

    def test_valid_analysis_types_values(self) -> None:
        """VALID_ANALYSIS_TYPES contains the 4 known analysis types."""
        assert {
            "linear",
            "logarithmic",
            "rolling",
            "cumulative",
        } == VALID_ANALYSIS_TYPES
