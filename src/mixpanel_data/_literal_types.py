"""Shared Literal type aliases for parameter validation.

These types are exported from the public API and can be used by
library consumers for their own type hints.

Example:
    from mixpanel_data import TimeUnit, Workspace

    def my_query(ws: Workspace, unit: TimeUnit) -> None:
        result = ws.segmentation(
            "event", from_date="2024-01-01", to_date="2024-01-31", unit=unit
        )
"""

from __future__ import annotations

from typing import Literal

# Time units for segmentation, retention, event_counts, property_counts, frequency
TimeUnit = Literal["day", "week", "month"]

# Time units for numeric aggregations (segmentation_numeric, sum, average)
HourDayUnit = Literal["hour", "day"]

# Count/aggregation methods
CountType = Literal["general", "unique", "average"]

# =========================================================================
# INSIGHTS QUERY TYPES
# =========================================================================

# Aggregation math for insights metrics (SELECT clause)
MeasurementMath = Literal[
    # Counting
    "total",
    "unique",
    "sessions",
    # Active users
    "dau",
    "wau",
    "mau",
    # Property aggregation (requires measurement.property)
    "average",
    "median",
    "min",
    "max",
    "p25",
    "p75",
    "p90",
    "p99",
    # Other
    "unique_values",
    "histogram",
]

# Filter operators for insights WHERE clauses
FilterOperator = Literal[
    # String operators
    "equals",
    "does not equal",
    "contains",
    "does not contain",
    "is set",
    "is not set",
    # Number operators
    "is equal to",
    "is not equal to",
    "is greater than",
    "is less than",
    "is at least",
    "is at most",
    "is between",
    # Boolean operators
    "true",
    "false",
    # Datetime operators
    "was on",
    "was before",
    "was since",
]

# Property data types
PropertyType = Literal["string", "number", "boolean", "datetime", "list"]

# Resource types for filters and breakdowns
ResourceType = Literal["events", "people"]

# Per-user aggregation methods
PerUserAggregation = Literal["total", "average", "min", "max", "unique_values"]

# Chart types for insights display
ChartType = Literal[
    "line",
    "bar",
    "column",
    "pie",
    "table",
    "insights-metric",
    "bar-stacked",
    "stacked-line",
    "stacked-column",
]

# Time units for insights queries
InsightsTimeUnit = Literal["hour", "day", "week", "month", "quarter"]

# Filter value types
FilterValue = list[str] | str | int | float | list[int | float] | bool | None

__all__ = [
    "TimeUnit",
    "HourDayUnit",
    "CountType",
    # Insights query types
    "MeasurementMath",
    "FilterOperator",
    "PropertyType",
    "ResourceType",
    "PerUserAggregation",
    "ChartType",
    "InsightsTimeUnit",
    "FilterValue",
]
