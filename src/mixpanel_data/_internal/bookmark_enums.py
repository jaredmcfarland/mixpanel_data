"""Authoritative Mixpanel bookmark enum constants.

All values are sourced from the server-side validation at
``analytics/bookmark_parser/insights/validate.py`` and
``analytics/bookmark_parser/common/schema/property_selectors/operator_expr.json``.

These constants define every valid value the Mixpanel insights query API
accepts for each bookmark field. Used by the validation engine to catch
invalid values client-side before they reach the server.

Organized by domain for clarity. Each constant is a ``frozenset[str]``
for O(1) membership checks and immutability.
"""

from __future__ import annotations

# =============================================================================
# Math / Aggregation Types
# =============================================================================

VALID_MATH_TYPES: frozenset[str] = frozenset(
    {
        # Core counting
        "total",
        "unique",
        "cumulative_unique",
        "sessions",
        # Active users
        "dau",
        "wau",
        "mau",
        # Property aggregation
        "average",
        "median",
        "min",
        "max",
        # Percentiles
        "p25",
        "p75",
        "p90",
        "p99",
        "custom_percentile",
        # Advanced
        "histogram",
        "unique_values",
        "most_frequent",
        "first_value",
        "multi_attribution",
        "numeric_summary",
        # Legacy / context-specific
        "general",
        "session",
        # Conversion (funnel/retention context)
        "conversion_rate",
        "conversion_rate_unique",
        "conversion_rate_total",
        "conversion_rate_session",
        "retention_rate",
    }
)
"""All valid math/aggregation operators across all contexts (insights, funnels, retention)."""

VALID_MATH_INSIGHTS: frozenset[str] = frozenset(
    {
        "total",
        "unique",
        "cumulative_unique",
        "sessions",
        "dau",
        "wau",
        "mau",
        "average",
        "median",
        "min",
        "max",
        "p25",
        "p75",
        "p90",
        "p99",
        "custom_percentile",
        "histogram",
        "unique_values",
        "most_frequent",
        "first_value",
        "multi_attribution",
        "numeric_summary",
    }
)
"""Valid math types for insights context (excludes funnel/retention-specific)."""

VALID_MATH_FUNNELS: frozenset[str] = frozenset(
    {
        "general",
        "unique",
        "session",
        "total",
        "conversion_rate",
        "conversion_rate_unique",
        "conversion_rate_total",
        "conversion_rate_session",
    }
)
"""Valid math types for funnel context."""

VALID_MATH_RETENTION: frozenset[str] = frozenset(
    {
        "unique",
        "retention_rate",
        "total",
        "average",
    }
)
"""Valid math types for retention context."""

MATH_REQUIRING_PROPERTY: frozenset[str] = frozenset(
    {
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
)
"""Math types that require a measurement property to be specified."""

MATH_PROPERTY_OPTIONAL: frozenset[str] = frozenset({"total"})
"""Math types that optionally accept a property.

``"total"`` without a property counts events; with a property it sums
the property's numeric values.
"""

MATH_NO_PER_USER: frozenset[str] = frozenset({"dau", "wau", "mau", "unique"})
"""Math types incompatible with per-user aggregation."""

# =============================================================================
# Per-User Aggregation
# =============================================================================

VALID_PER_USER_AGGREGATIONS: frozenset[str] = frozenset(
    {
        "average",
        "max",
        "min",
        "session_replay_id_value",
        "total",
        "unique_values",
    }
)
"""Valid per-user aggregation types (maps to ``perUserAggregation`` in bookmark)."""

# =============================================================================
# Property Types
# =============================================================================

VALID_PROPERTY_TYPES: frozenset[str] = frozenset(
    {
        "string",
        "number",
        "datetime",
        "boolean",
        "list",
        "object",
        "undefined",
    }
)
"""Valid property data types for filter and group-by clauses."""

# =============================================================================
# Time Units
# =============================================================================

VALID_TIME_UNITS: frozenset[str] = frozenset(
    {
        "minute",
        "hour",
        "day",
        "week",
        "month",
        "year",
        "quarter",
    }
)
"""Valid time units for time section aggregation."""

VALID_QUERY_TIME_UNITS: frozenset[str] = frozenset(
    {
        "minute",
        "hour",
        "day",
        "week",
        "month",
        "year",
        "quarter",
        "day_of_week",
        "hour_of_day",
    }
)
"""Valid time units for query contexts (includes special grouping units)."""

# =============================================================================
# Resource Types
# =============================================================================

VALID_RESOURCE_TYPES: frozenset[str] = frozenset(
    {
        "events",
        "people",
        "cohorts",
        "other",
        # Legacy aliases (still accepted by server)
        "event",
        "user",
        "cohort",
    }
)
"""Valid resource types for filters, groups, and show clauses."""

# =============================================================================
# Metric / Behavior Types
# =============================================================================

VALID_METRIC_TYPES: frozenset[str] = frozenset(
    {
        "event",
        "simple",
        "custom-event",
        "cohort",
        "people",
        "funnel",
        "retention",
        "addiction",
        "formula",
        "metric",
    }
)
"""Valid behavior/metric types in show clause behavior blocks."""

# =============================================================================
# Chart Types
# =============================================================================

VALID_CHART_TYPES: frozenset[str] = frozenset(
    {
        "line",
        "bar",
        "pie",
        "table",
        "insights-metric",
        "column",
        "funnel-steps",
        "funnel-top-paths",
        "retention-curve",
        "frequency-curve",
    }
)
"""Valid chart types for displayOptions.chartType."""

# =============================================================================
# Filter Operators
# =============================================================================

VALID_FILTER_OPERATORS: frozenset[str] = frozenset(
    {
        # String operators
        "contains",
        "does not contain",
        "equals",
        "does not equal",
        "is equal to",
        # Existence operators
        "is set",
        "is not set",
        # Numeric comparison operators
        "is at least",
        "is at most",
        "is between",
        "between",
        "not between",
        "is greater than",
        "is less than",
        "is greater than or equal to",
        "is less than or equal to",
        # Boolean operators
        "true",
        "false",
        # Date operators
        "on",
        "not on",
        "in the last",
        "not in the last",
        "before the last",
        "before",
        "in the next",
        "since",
    }
)
"""Valid filter operators from the canonical operator expression schema."""

# =============================================================================
# Filters Determiner
# =============================================================================

VALID_FILTERS_DETERMINER: frozenset[str] = frozenset({"any", "all"})
"""Valid values for filtersDeterminer (AND/OR logic for multiple filters)."""

# =============================================================================
# Analysis Types
# =============================================================================

VALID_ANALYSIS_TYPES: frozenset[str] = frozenset(
    {
        "linear",
        "logarithmic",
        "rolling",
        "cumulative",
    }
)
"""Valid analysis types for displayOptions."""

# =============================================================================
# Date Range Types
# =============================================================================

VALID_DATE_RANGE_TYPES: frozenset[str] = frozenset(
    {
        "in the last",
        "between",
        "since",
        "on",
        "relative_after",
    }
)
"""Valid date range types for time section clauses."""
