"""Result types for mixpanel_data operations.

All result types are immutable frozen dataclasses with:
- Lazy DataFrame conversion via the `df` property (computed once, then cached)
- JSON serialization via the `to_dict()` method (all values JSON-serializable)
- Full type hints for IDE/mypy support

Immutability: These dataclasses are frozen, meaning their attributes cannot be
modified after construction. This ensures data integrity and thread-safety.
If you need to modify a result, create a new instance with the desired values.

DataFrame caching: The `.df` property computes the DataFrame on first access
and caches it internally. Subsequent accesses return the cached DataFrame
without recomputation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

T = TypeVar("T")

# =============================================================================
# Query API Type Aliases and Constants (Phase 029)
# =============================================================================

MathType = Literal[
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
"""Aggregation function for query metrics."""

PerUserAggregation = Literal["average", "total", "min", "max"]
"""Per-user pre-aggregation type."""

FilterPropertyType = Literal["string", "number", "boolean", "datetime", "list"]
"""Property data type for filter conditions.

Includes ``"datetime"`` and ``"list"`` for API compatibility;
no Filter factory methods currently produce these types.
"""

PROPERTY_MATH_TYPES: frozenset[MathType] = frozenset(
    {"average", "median", "min", "max", "sum", "p25", "p75", "p90", "p99"}
)
"""Math types that require a property name."""

NO_PER_USER_MATH_TYPES: frozenset[MathType] = frozenset({"dau", "wau", "mau"})
"""Math types incompatible with per_user aggregation."""

# =============================================================================
# Base Class for Result Types with DataFrame Conversion
# =============================================================================


@dataclass(frozen=True)
class ResultWithDataFrame:
    """Base class for result types with lazy DataFrame conversion and table output.

    This base class provides common functionality for result types that:
    1. Store data in nested dict/list structures
    2. Support conversion to normalized DataFrames via a `df` property
    3. Need readable table output for CLI `--format table` option

    Attributes:
        _df_cache: Internal cache for lazy DataFrame conversion. Not part of
            the public API. Subclasses should not access this directly.
            This field is keyword-only to allow subclasses to define required
            fields without defaults.

    Methods:
        df: Property that must be implemented by subclasses to return a
            normalized DataFrame.
        to_table_dict: Converts the DataFrame to a list of dicts suitable
            for table formatting.

    Usage:
        Subclasses must implement the `df` property to normalize their data
        into a flat DataFrame structure. The base class handles caching and
        table serialization automatically.

    Example:
        ```python
        @dataclass(frozen=True)
        class MyResult(ResultWithDataFrame):
            data: dict[str, dict[str, int]]

            @property
            def df(self) -> pd.DataFrame:
                if self._df_cache is not None:
                    return self._df_cache

                rows = [{"key": k, "date": d, "count": c}
                        for k, dates in self.data.items()
                        for d, c in dates.items()]
                result_df = pd.DataFrame(rows)
                object.__setattr__(self, "_df_cache", result_df)
                return result_df

        result = MyResult(data={"A": {"2024-01-01": 10}})
        result.to_table_dict()
        # [{"key": "A", "date": "2024-01-01", "count": 10}]
        ```
    """

    _df_cache: pd.DataFrame | None = field(default=None, repr=False, kw_only=True)

    @property
    def df(self) -> pd.DataFrame:
        """Convert result data to normalized DataFrame.

        This property must be implemented by subclasses to convert their
        specific data structure into a flat, normalized DataFrame suitable
        for analysis and table display.

        The implementation should:
        1. Check if _df_cache is not None and return it (for performance)
        2. Build rows as list[dict[str, Any]] from the result's data
        3. Create a DataFrame from the rows (or empty DataFrame with columns)
        4. Cache the result using object.__setattr__(self, "_df_cache", result_df)
        5. Return the DataFrame

        Returns:
            Normalized DataFrame with flat columns suitable for analysis.
            Column names should be lowercase, descriptive, and consistent
            across result types where possible (e.g., "date", "count", "event").

        Raises:
            NotImplementedError: If subclass doesn't implement this property.

        Example:
            ```python
            df = result.df
            df.columns
            # Index(['date', 'segment', 'count'], dtype='object')
            ```
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement df property"
        )

    def to_table_dict(self) -> list[dict[str, Any]]:
        """Convert DataFrame rows to list of dicts for table formatting.

        This method uses the `df` property which normalizes nested data
        structures into flat tabular form, then converts to a list of
        records (one dict per row). This provides readable output for
        CLI `--format table` option.

        The normalized table format is much more readable than displaying
        nested dict/list structures as JSON blobs in table cells.

        Returns:
            List of dictionaries with normalized row data, one dict per row.
            Each dict has keys matching the DataFrame column names.
            Returns empty list if DataFrame is empty.

        Example:
            Without to_table_dict (unreadable table):
                ┃ SERIES                                              ┃
                ┃ {"US": {"2024-01-01": 100, "2024-01-02": 150}, ...} ┃

            With to_table_dict (readable table):
                ┃ DATE       ┃ SEGMENT ┃ COUNT ┃
                ┃ 2024-01-01 ┃ US      ┃ 100   ┃
                ┃ 2024-01-02 ┃ US      ┃ 150   ┃

        Note:
            This method is used automatically by CLI commands when
            `--format table` is specified. For other formats (json, jsonl, csv),
            use the `to_dict()` method which preserves the original structure.
        """
        from typing import cast

        df = self.df
        if df.empty:
            return []

        # Cast required because pandas to_dict("records") returns
        # list[dict[Hashable, Any]] but we know our columns are strings
        return cast(list[dict[str, Any]], df.to_dict("records"))


# =============================================================================
# Bookmark Type Aliases (Phase 015)
# =============================================================================

BookmarkType = Literal["insights", "funnels", "retention", "flows", "launch-analysis"]
"""Bookmark type values from the Mixpanel Bookmarks API.

Valid values:
    - insights: Standard metrics/events reports
    - funnels: Funnel conversion reports
    - retention: Cohort retention reports
    - flows: User path/navigation reports
    - launch-analysis: Impact/experiment reports
"""

SavedReportType = Literal["insights", "retention", "funnel", "flows"]
"""Report type detected from saved report query results.

Derived from headers array in the API response:
    - retention: Headers contain "$retention"
    - funnel: Headers contain "$funnel"
    - flows: Headers contain "$flows"
    - insights: Default when no special headers present
"""


@dataclass(frozen=True)
class SegmentationResult(ResultWithDataFrame):
    """Result of a segmentation query.

    Contains time-series data for an event, optionally segmented by a property.

    Inherits from ResultWithDataFrame to provide:
    - Lazy DataFrame caching via _df_cache field
    - Normalized table output via to_table_dict() method
    """

    event: str
    """Queried event name."""

    from_date: str
    """Query start date (YYYY-MM-DD)."""

    to_date: str
    """Query end date (YYYY-MM-DD)."""

    unit: Literal["day", "week", "month"]
    """Time unit for aggregation."""

    segment_property: str | None
    """Property used for segmentation (None if total only)."""

    total: int
    """Total count across all segments and time periods."""

    series: dict[str, dict[str, int]] = field(default_factory=dict)
    """Time series data by segment.

    Structure: {segment_name: {date_string: count}}
    Example: {"US": {"2024-01-01": 150, "2024-01-02": 200}, "EU": {...}}
    For unsegmented queries, segment_name is "total".
    """

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with columns: date, segment, count.

        For unsegmented queries, segment column is 'total'.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = []

        for segment_name, date_counts in self.series.items():
            for date_str, count in date_counts.items():
                rows.append(
                    {
                        "date": date_str,
                        "segment": segment_name,
                        "count": count,
                    }
                )

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=["date", "segment", "count"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "event": self.event,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "unit": self.unit,
            "segment_property": self.segment_property,
            "total": self.total,
            "series": self.series,
        }


@dataclass(frozen=True)
class FunnelStep:
    """Single step in a funnel."""

    event: str
    """Event name for this step."""

    count: int
    """Number of users at this step."""

    conversion_rate: float
    """Conversion rate from previous step (0.0 to 1.0)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "event": self.event,
            "count": self.count,
            "conversion_rate": self.conversion_rate,
        }


@dataclass(frozen=True)
class FunnelResult(ResultWithDataFrame):
    """Result of a funnel query.

    Contains step-by-step conversion data for a funnel.

    Inherits from ResultWithDataFrame to provide:
    - Lazy DataFrame caching via _df_cache field
    - Normalized table output via to_table_dict() method
    """

    funnel_id: int
    """Funnel identifier."""

    funnel_name: str
    """Funnel display name."""

    from_date: str
    """Query start date."""

    to_date: str
    """Query end date."""

    conversion_rate: float
    """Overall conversion rate (0.0 to 1.0)."""

    steps: list[FunnelStep] = field(default_factory=list)
    """Step-by-step breakdown."""

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with columns: step, event, count, conversion_rate."""
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = []

        for i, step in enumerate(self.steps, start=1):
            rows.append(
                {
                    "step": i,
                    "event": step.event,
                    "count": step.count,
                    "conversion_rate": step.conversion_rate,
                }
            )

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=["step", "event", "count", "conversion_rate"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "funnel_id": self.funnel_id,
            "funnel_name": self.funnel_name,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "conversion_rate": self.conversion_rate,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass(frozen=True)
class CohortInfo:
    """Retention data for a single cohort."""

    date: str
    """Cohort date (when users were 'born')."""

    size: int
    """Number of users in cohort."""

    retention: list[float] = field(default_factory=list)
    """Retention percentages by period (0.0 to 1.0)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "date": self.date,
            "size": self.size,
            "retention": self.retention,
        }


@dataclass(frozen=True)
class RetentionResult(ResultWithDataFrame):
    """Result of a retention query.

    Contains cohort-based retention data.

    Inherits from ResultWithDataFrame to provide:
    - Lazy DataFrame caching via _df_cache field
    - Normalized table output via to_table_dict() method
    """

    born_event: str
    """Event that defines cohort membership."""

    return_event: str
    """Event that defines return."""

    from_date: str
    """Query start date."""

    to_date: str
    """Query end date."""

    unit: Literal["day", "week", "month"]
    """Time unit for retention periods."""

    cohorts: list[CohortInfo] = field(default_factory=list)
    """Cohort retention data."""

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with columns: cohort_date, cohort_size, period_N."""
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = []

        for cohort in self.cohorts:
            row: dict[str, Any] = {
                "cohort_date": cohort.date,
                "cohort_size": cohort.size,
            }
            for i, retention_value in enumerate(cohort.retention):
                row[f"period_{i}"] = retention_value
            rows.append(row)

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=["cohort_date", "cohort_size"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "born_event": self.born_event,
            "return_event": self.return_event,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "unit": self.unit,
            "cohorts": [cohort.to_dict() for cohort in self.cohorts],
        }


@dataclass(frozen=True)
class JQLResult(ResultWithDataFrame):
    """Result of a JQL query.

    JQL (JavaScript Query Language) allows custom queries against Mixpanel data.

    Inherits from ResultWithDataFrame to provide:
    - Lazy DataFrame caching via _df_cache field
    - Normalized table output via to_table_dict() method

    The df property intelligently detects JQL result patterns (groupBy, percentiles,
    simple dicts) and converts them to clean tabular format.
    """

    _raw: list[Any] = field(default_factory=list, repr=False)
    """Raw result data from JQL execution."""

    @property
    def raw(self) -> list[Any]:
        """Raw result data from JQL execution."""
        return self._raw

    @property
    def df(self) -> pd.DataFrame:
        """Convert result to DataFrame with intelligent structure detection.

        The conversion strategy depends on the detected JQL result pattern:

        **groupBy results** (detected by {key: [...], value: X} structure):
            - Keys expanded to columns: key_0, key_1, key_2, ...
            - Single value: "value" column
            - Multiple reducers (value array): value_0, value_1, value_2, ...
            - Additional fields (from .map()): preserved as-is
            - Example: {"key": ["US"], "value": 100, "name": "USA"}
              -> columns: key_0, value, name

        **Nested percentile results** ([[{percentile: X, value: Y}, ...]]):
            - Outer list unwrapped, inner dicts converted directly

        **Simple list of dicts** (already well-structured):
            - Converted directly to DataFrame preserving all fields

        **Fallback for other structures** (scalars, mixed types, incompatible dicts):
            - Safely wrapped in single "value" column to prevent data loss
            - Used when structure doesn't match known patterns

        Raises:
            ValueError: If groupBy structure has inconsistent value types across rows
                (some scalar, some array) which indicates malformed query results.

        Returns:
            DataFrame representation, cached after first access.
        """
        if self._df_cache is not None:
            return self._df_cache

        result_df = self._convert_to_dataframe(self._raw)
        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def _convert_to_dataframe(self, raw: list[Any]) -> pd.DataFrame:
        """Convert raw JQL results to DataFrame.

        Args:
            raw: Raw JQL result data.

        Returns:
            DataFrame representation.
        """
        if not raw:
            return pd.DataFrame()

        # Detect groupBy structure: {key: [...], value: X}
        if self._is_groupby_structure(raw):
            return self._expand_groupby_structure(raw)

        # Special case: nested list of dicts (e.g., from percentiles after flatten)
        # Structure: [[{percentile: 50, value: 118}, ...]]
        if (
            len(raw) == 1
            and isinstance(raw[0], list)
            and raw[0]
            and isinstance(raw[0][0], dict)
        ):
            return pd.DataFrame(raw[0])

        # Handle list of dicts (already good structure or after .map())
        # But first check if ALL items are dicts to avoid pandas errors
        if isinstance(raw[0], dict) and all(isinstance(item, dict) for item in raw):
            try:
                return pd.DataFrame(raw)
            except (ValueError, TypeError):
                # Mixed dict structures, wrap safely
                return pd.DataFrame({"value": raw})

        # For other structures (lists, scalars, mixed types), wrap in value column
        return pd.DataFrame({"value": raw})

    def _is_groupby_structure(self, raw: list[Any]) -> bool:
        """Check if raw data has groupBy structure {key: [...], value: X}.

        Validates that ALL elements match the pattern to prevent KeyError
        during expansion. Allows additional fields (e.g., from .map()).

        Args:
            raw: Raw JQL result data.

        Returns:
            True if ALL elements match groupBy pattern.
        """
        if not raw:
            return False

        # Check ALL elements for consistent structure
        return all(
            isinstance(item, dict)
            and set(item.keys()) >= {"key", "value"}  # Allow additional fields!
            and isinstance(item.get("key"), list)
            for item in raw
        )

    def _expand_groupby_structure(self, raw: list[dict[str, Any]]) -> pd.DataFrame:
        """Expand groupBy {key: [...], value: X} structure to columns.

        Preserves additional fields (e.g., from .map()) and validates
        value type consistency across all rows.

        Args:
            raw: List of groupBy result objects.

        Returns:
            DataFrame with expanded key and value columns.

        Raises:
            ValueError: If value types are inconsistent across rows.
        """
        # Validate consistent value types
        value_is_list = [isinstance(item["value"], list) for item in raw]
        if not (all(value_is_list) or not any(value_is_list)):
            raise ValueError(
                "Inconsistent value types in groupBy results: "
                "some rows have scalar values, others have arrays. "
                "This typically indicates a malformed JQL query result."
            )

        rows = []
        for item in raw:
            row_dict: dict[str, Any] = {}

            # FIRST: Preserve all additional fields (anything except key/value)
            for k, v in item.items():
                if k not in {"key", "value"}:
                    row_dict[k] = v

            # THEN: Expand key array into key_0, key_1, key_2, ...
            keys = item["key"]
            for i, key_val in enumerate(keys):
                row_dict[f"key_{i}"] = key_val

            # THEN: Handle value - could be scalar or array (multiple reducers)
            value = item["value"]
            if isinstance(value, list):
                # Multiple reducers: expand to value_0, value_1, value_2
                for i, val in enumerate(value):
                    row_dict[f"value_{i}"] = val
            else:
                # Single reducer: just "value"
                row_dict["value"] = value

            rows.append(row_dict)

        return pd.DataFrame(rows)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "raw": self._raw,
            "row_count": len(self._raw),
        }


# Discovery Types


@dataclass(frozen=True)
class FunnelInfo:
    """A saved funnel definition.

    Represents a funnel saved in Mixpanel that can be queried
    using the funnel() method.
    """

    funnel_id: int
    """Unique identifier for funnel queries."""

    name: str
    """Human-readable funnel name."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "funnel_id": self.funnel_id,
            "name": self.name,
        }


@dataclass(frozen=True)
class SavedCohort:
    """A saved cohort definition.

    Represents a user cohort saved in Mixpanel for profile filtering.
    """

    id: int
    """Unique identifier for profile filtering."""

    name: str
    """Human-readable cohort name."""

    count: int
    """Current number of users in cohort."""

    description: str
    """Optional description (may be empty string)."""

    created: str
    """Creation timestamp (YYYY-MM-DD HH:mm:ss)."""

    is_visible: bool
    """Whether cohort is visible in Mixpanel UI."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "id": self.id,
            "name": self.name,
            "count": self.count,
            "description": self.description,
            "created": self.created,
            "is_visible": self.is_visible,
        }


@dataclass(frozen=True)
class BookmarkInfo:
    """Metadata for a saved report (bookmark) from the Mixpanel Bookmarks API.

    Represents a saved Insights, Funnel, Retention, or Flows report
    that can be queried using query_saved_report() or query_flows().

    Attributes:
        id: Unique bookmark identifier.
        name: User-defined report name.
        type: Report type (insights, funnels, retention, flows, launch-analysis).
        project_id: Parent Mixpanel project ID.
        created: Creation timestamp (ISO format).
        modified: Last modification timestamp (ISO format).
        workspace_id: Optional workspace ID if scoped to a workspace.
        dashboard_id: Optional parent dashboard ID if linked to a dashboard.
        description: Optional user-provided description.
        creator_id: Optional creator's user ID.
        creator_name: Optional creator's display name.
    """

    id: int
    """Unique bookmark identifier."""

    name: str
    """User-defined report name."""

    type: BookmarkType
    """Report type."""

    project_id: int
    """Parent Mixpanel project ID."""

    created: str
    """Creation timestamp (ISO format)."""

    modified: str
    """Last modification timestamp (ISO format)."""

    workspace_id: int | None = None
    """Workspace ID if scoped to a workspace."""

    dashboard_id: int | None = None
    """Parent dashboard ID if linked to a dashboard."""

    description: str | None = None
    """User-provided description."""

    creator_id: int | None = None
    """Creator's user ID."""

    creator_name: str | None = None
    """Creator's display name."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all bookmark metadata fields.
        """
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "project_id": self.project_id,
            "created": self.created,
            "modified": self.modified,
        }
        if self.workspace_id is not None:
            result["workspace_id"] = self.workspace_id
        if self.dashboard_id is not None:
            result["dashboard_id"] = self.dashboard_id
        if self.description is not None:
            result["description"] = self.description
        if self.creator_id is not None:
            result["creator_id"] = self.creator_id
        if self.creator_name is not None:
            result["creator_name"] = self.creator_name
        return result


@dataclass(frozen=True)
class TopEvent:
    """Today's event activity data.

    Represents an event's current activity including count and trend.
    """

    event: str
    """Event name."""

    count: int
    """Today's event count."""

    percent_change: float
    """Change vs yesterday (-1.0 to +infinity)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "event": self.event,
            "count": self.count,
            "percent_change": self.percent_change,
        }


@dataclass(frozen=True)
class EventCountsResult(ResultWithDataFrame):
    """Time-series event count data.

    Contains aggregate counts for multiple events over time with
    lazy DataFrame conversion support.

    Inherits from ResultWithDataFrame to provide:
    - Lazy DataFrame caching via _df_cache field
    - Normalized table output via to_table_dict() method
    """

    events: list[str]
    """Queried event names."""

    from_date: str
    """Query start date (YYYY-MM-DD)."""

    to_date: str
    """Query end date (YYYY-MM-DD)."""

    unit: Literal["day", "week", "month"]
    """Time unit for aggregation."""

    type: Literal["general", "unique", "average"]
    """Counting method used."""

    series: dict[str, dict[str, int]]
    """Time series data: {event_name: {date: count}}."""

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with columns: date, event, count.

        Conversion is lazy - computed on first access and cached.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = []
        for event_name, date_counts in self.series.items():
            for date_str, count in date_counts.items():
                rows.append(
                    {
                        "date": date_str,
                        "event": event_name,
                        "count": count,
                    }
                )

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=["date", "event", "count"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "events": self.events,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "unit": self.unit,
            "type": self.type,
            "series": self.series,
        }


@dataclass(frozen=True)
class PropertyCountsResult(ResultWithDataFrame):
    """Time-series property value distribution data.

    Contains aggregate counts by property values over time with
    lazy DataFrame conversion support.

    Inherits from ResultWithDataFrame to provide:
    - Lazy DataFrame caching via _df_cache field
    - Normalized table output via to_table_dict() method
    """

    event: str
    """Queried event name."""

    property_name: str
    """Property used for segmentation."""

    from_date: str
    """Query start date (YYYY-MM-DD)."""

    to_date: str
    """Query end date (YYYY-MM-DD)."""

    unit: Literal["day", "week", "month"]
    """Time unit for aggregation."""

    type: Literal["general", "unique", "average"]
    """Counting method used."""

    series: dict[str, dict[str, int]]
    """Time series data by property value.

    Structure: {property_value: {date: count}}
    Example: {"US": {"2024-01-01": 150, "2024-01-02": 200}, "EU": {...}}
    """

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with columns: date, value, count.

        Conversion is lazy - computed on first access and cached.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = []
        for value, date_counts in self.series.items():
            for date_str, count in date_counts.items():
                rows.append(
                    {
                        "date": date_str,
                        "value": value,
                        "count": count,
                    }
                )

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=["date", "value", "count"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "event": self.event,
            "property_name": self.property_name,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "unit": self.unit,
            "type": self.type,
            "series": self.series,
        }


# Phase 008: Query Service Enhancement Types


@dataclass(frozen=True)
class UserEvent:
    """Single event in a user's activity feed.

    Represents one event from a user's event history with timestamp
    and all associated properties.
    """

    event: str
    """Event name."""

    time: datetime
    """Event timestamp (UTC)."""

    properties: dict[str, Any] = field(default_factory=dict)
    """All event properties including system properties."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "event": self.event,
            "time": self.time.isoformat(),
            "properties": self.properties,
        }


@dataclass(frozen=True)
class ActivityFeedResult(ResultWithDataFrame):
    """Collection of user events from activity feed query.

    Contains chronological event history for one or more users
    with lazy DataFrame conversion support.

    Inherits from ResultWithDataFrame to provide:
    - Lazy DataFrame caching via _df_cache field
    - Normalized table output via to_table_dict() method
    """

    distinct_ids: list[str]
    """Queried user identifiers."""

    from_date: str | None
    """Start date filter (YYYY-MM-DD), None if not specified."""

    to_date: str | None
    """End date filter (YYYY-MM-DD), None if not specified."""

    events: list[UserEvent] = field(default_factory=list)
    """Event history (chronological order)."""

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with columns: event, time, distinct_id, + properties.

        Flattens event properties into individual columns.
        Conversion is lazy - computed on first access and cached.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = []
        for user_event in self.events:
            row: dict[str, Any] = {
                "event": user_event.event,
                "time": user_event.time,
                "distinct_id": user_event.properties.get("$distinct_id", ""),
            }
            # Flatten properties (excluding $distinct_id to avoid duplication)
            for key, value in user_event.properties.items():
                if key != "$distinct_id":
                    row[key] = value
            rows.append(row)

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=["event", "time", "distinct_id"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "distinct_ids": self.distinct_ids,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "event_count": len(self.events),
            "events": [e.to_dict() for e in self.events],
        }


@dataclass(frozen=True)
class SavedReportResult:
    """Data from a saved report (Insights, Retention, or Funnel).

    Contains data from a pre-configured saved report with automatic
    report type detection and lazy DataFrame conversion support.

    The report_type property automatically detects the report type based on
    headers: "$retention" indicates retention, "$funnel" indicates funnel,
    otherwise it's an insights report.

    Attributes:
        bookmark_id: Saved report identifier.
        computed_at: When report was computed (ISO format).
        from_date: Report start date.
        to_date: Report end date.
        headers: Report column headers (used for type detection).
        series: Report data (structure varies by report type).
    """

    bookmark_id: int
    """Saved report identifier."""

    computed_at: str
    """When report was computed (ISO format)."""

    from_date: str
    """Report start date."""

    to_date: str
    """Report end date."""

    headers: list[str] = field(default_factory=list)
    """Report column headers (used for type detection)."""

    series: dict[str, Any] = field(default_factory=dict)
    """Report data (structure varies by report type).

    For Insights reports: {event_name: {date: count}}
    For Retention reports: {series_name: {date: {segment: {first, counts, rates}}}}
    For Funnel reports: {count: {...}, overall_conv_ratio: {...}, ...}
    """

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def report_type(self) -> SavedReportType:
        """Detect the report type from headers.

        Returns:
            'retention' if headers contain '$retention',
            'funnel' if headers contain '$funnel',
            'flows' if headers contain '$flows',
            'insights' otherwise.
        """
        for header in self.headers:
            if "$retention" in header.lower():
                return "retention"
            if "$funnel" in header.lower():
                return "funnel"
            if "$flows" in header.lower():
                return "flows"
        return "insights"

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame.

        For Insights reports: columns are date, event, count.
        For Retention/Funnel reports: flattens the nested structure.

        Conversion is lazy - computed on first access and cached.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = []
        report_type = self.report_type

        if report_type == "insights":
            # Insights: {event_name: {date: count}}
            for event_name, date_counts in self.series.items():
                if isinstance(date_counts, dict):
                    for date_str, count in date_counts.items():
                        rows.append(
                            {
                                "date": date_str,
                                "event": event_name,
                                "count": count,
                            }
                        )
            result_df = (
                pd.DataFrame(rows)
                if rows
                else pd.DataFrame(columns=["date", "event", "count"])
            )
        else:
            # Retention and funnel reports have complex nested structures that vary
            # by report configuration. We preserve the full structure for direct
            # access via .series property. Users can navigate the nested dict as
            # needed for their specific report type.
            result_df = pd.DataFrame([{"series": self.series}])

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all report fields including detected report_type.
        """
        return {
            "bookmark_id": self.bookmark_id,
            "computed_at": self.computed_at,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "headers": self.headers,
            "series": self.series,
            "report_type": self.report_type,
        }


@dataclass(frozen=True)
class FlowsResult(ResultWithDataFrame):
    """Data from a saved Flows report.

    Contains user path/navigation data from a pre-configured Flows report
    with lazy DataFrame conversion support.

    Inherits from ResultWithDataFrame to provide:
    - Lazy DataFrame caching via _df_cache field
    - Normalized table output via to_table_dict() method

    Attributes:
        bookmark_id: Saved report identifier.
        computed_at: When report was computed (ISO format).
        steps: Flow step data with event sequences and counts.
        breakdowns: Path breakdown data showing user flow distribution.
        overall_conversion_rate: End-to-end conversion rate (0.0 to 1.0).
        metadata: Additional API metadata from the response.
    """

    bookmark_id: int
    """Saved report identifier."""

    computed_at: str
    """When report was computed (ISO format)."""

    steps: list[dict[str, Any]] = field(default_factory=list)
    """Flow step data with event sequences and counts."""

    breakdowns: list[dict[str, Any]] = field(default_factory=list)
    """Path breakdown data showing user flow distribution."""

    overall_conversion_rate: float = 0.0
    """End-to-end conversion rate (0.0 to 1.0)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional API metadata from the response."""

    @property
    def df(self) -> pd.DataFrame:
        """Convert steps to DataFrame.

        Returns DataFrame with columns derived from step data structure.
        Conversion is lazy - computed on first access and cached.
        """
        if self._df_cache is not None:
            return self._df_cache

        result_df = pd.DataFrame(self.steps) if self.steps else pd.DataFrame()

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all flows report fields.
        """
        return {
            "bookmark_id": self.bookmark_id,
            "computed_at": self.computed_at,
            "steps": self.steps,
            "breakdowns": self.breakdowns,
            "overall_conversion_rate": self.overall_conversion_rate,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class FrequencyResult(ResultWithDataFrame):
    """Event frequency distribution (addiction analysis).

    Contains frequency arrays showing how many users performed events
    in N time periods, with lazy DataFrame conversion support.

    Inherits from ResultWithDataFrame to provide:
    - Lazy DataFrame caching via _df_cache field
    - Normalized table output via to_table_dict() method
    """

    event: str | None
    """Filtered event name (None = all events)."""

    from_date: str
    """Query start date (YYYY-MM-DD)."""

    to_date: str
    """Query end date (YYYY-MM-DD)."""

    unit: Literal["day", "week", "month"]
    """Overall time period."""

    addiction_unit: Literal["hour", "day"]
    """Measurement granularity."""

    data: dict[str, list[int]] = field(default_factory=dict)
    """Frequency arrays by date.

    Structure: {date: [count_1, count_2, ...]}
    Example: {"2024-01-01": [100, 50, 25, 10]}

    Each array shows user counts by frequency:
    - Index 0: users active exactly 1 time
    - Index 1: users active exactly 2 times
    - Index N: users active exactly N+1 times
    """

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with columns: date, period_1, period_2, ...

        Each period_N column shows users active in at least N time periods.
        Conversion is lazy - computed on first access and cached.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = []
        for date_str, counts in self.data.items():
            row: dict[str, Any] = {"date": date_str}
            for i, count in enumerate(counts, start=1):
                row[f"period_{i}"] = count
            rows.append(row)

        result_df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date"])

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "event": self.event,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "unit": self.unit,
            "addiction_unit": self.addiction_unit,
            "data": self.data,
        }


@dataclass(frozen=True)
class NumericBucketResult(ResultWithDataFrame):
    """Events segmented into numeric property ranges.

    Contains time-series data bucketed by automatically determined
    numeric ranges, with lazy DataFrame conversion support.

    Inherits from ResultWithDataFrame to provide:
    - Lazy DataFrame caching via _df_cache field
    - Normalized table output via to_table_dict() method
    """

    event: str
    """Queried event name."""

    from_date: str
    """Query start date (YYYY-MM-DD)."""

    to_date: str
    """Query end date (YYYY-MM-DD)."""

    property_expr: str
    """The 'on' expression used for bucketing."""

    unit: Literal["hour", "day"]
    """Time aggregation unit."""

    series: dict[str, dict[str, int]] = field(default_factory=dict)
    """Bucket data: {range_string: {date: count}}."""

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with columns: date, bucket, count.

        Conversion is lazy - computed on first access and cached.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = []
        for bucket, date_counts in self.series.items():
            for date_str, count in date_counts.items():
                rows.append(
                    {
                        "date": date_str,
                        "bucket": bucket,
                        "count": count,
                    }
                )

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=["date", "bucket", "count"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "event": self.event,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "property_expr": self.property_expr,
            "unit": self.unit,
            "series": self.series,
        }


@dataclass(frozen=True)
class NumericSumResult(ResultWithDataFrame):
    """Sum of numeric property values per time unit.

    Contains daily or hourly sum totals for a numeric property
    with lazy DataFrame conversion support.

    Inherits from ResultWithDataFrame to provide:
    - Lazy DataFrame caching via _df_cache field
    - Normalized table output via to_table_dict() method
    """

    event: str
    """Queried event name."""

    from_date: str
    """Query start date (YYYY-MM-DD)."""

    to_date: str
    """Query end date (YYYY-MM-DD)."""

    property_expr: str
    """The 'on' expression summed."""

    unit: Literal["hour", "day"]
    """Time aggregation unit."""

    results: dict[str, float] = field(default_factory=dict)
    """Sum values: {date: sum}."""

    computed_at: str | None = None
    """Computation timestamp (if provided by API)."""

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with columns: date, sum.

        Conversion is lazy - computed on first access and cached.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = [
            {"date": date_str, "sum": value} for date_str, value in self.results.items()
        ]

        result_df = (
            pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date", "sum"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        result: dict[str, Any] = {
            "event": self.event,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "property_expr": self.property_expr,
            "unit": self.unit,
            "results": self.results,
        }
        if self.computed_at is not None:
            result["computed_at"] = self.computed_at
        return result


@dataclass(frozen=True)
class NumericAverageResult(ResultWithDataFrame):
    """Average of numeric property values per time unit.

    Contains daily or hourly average values for a numeric property
    with lazy DataFrame conversion support.

    Inherits from ResultWithDataFrame to provide:
    - Lazy DataFrame caching via _df_cache field
    - Normalized table output via to_table_dict() method
    """

    event: str
    """Queried event name."""

    from_date: str
    """Query start date (YYYY-MM-DD)."""

    to_date: str
    """Query end date (YYYY-MM-DD)."""

    property_expr: str
    """The 'on' expression averaged."""

    unit: Literal["hour", "day"]
    """Time aggregation unit."""

    results: dict[str, float] = field(default_factory=dict)
    """Average values: {date: average}."""

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with columns: date, average.

        Conversion is lazy - computed on first access and cached.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = [
            {"date": date_str, "average": value}
            for date_str, value in self.results.items()
        ]

        result_df = (
            pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date", "average"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "event": self.event,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "property_expr": self.property_expr,
            "unit": self.unit,
            "results": self.results,
        }


# Lexicon Schemas Types

EntityType = Literal["event", "profile"]
"""Type alias for Lexicon entity types accepted as input parameters.

Valid input types:
    - event: Standard tracked events
    - profile: User profile properties

Note: The Mixpanel API may return additional entity types in responses
(custom_event, group, lookup, collect_everything_event) which are accepted
but not supported as input filters.
"""


@dataclass(frozen=True)
class LexiconMetadata:
    """Mixpanel-specific metadata for Lexicon schemas and properties.

    Contains platform-specific information about how schemas and properties
    are displayed and organized in the Mixpanel UI.
    """

    source: str | None
    """Origin of the schema definition (e.g., 'api', 'csv', 'ui')."""

    display_name: str | None
    """Human-readable display name in Mixpanel UI."""

    tags: list[str]
    """Categorization tags for organization."""

    hidden: bool
    """Whether hidden from Mixpanel UI."""

    dropped: bool
    """Whether data is dropped/ignored."""

    contacts: list[str]
    """Owner email addresses."""

    team_contacts: list[str]
    """Team ownership labels."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all metadata fields.
        """
        return {
            "source": self.source,
            "display_name": self.display_name,
            "tags": self.tags,
            "hidden": self.hidden,
            "dropped": self.dropped,
            "contacts": self.contacts,
            "team_contacts": self.team_contacts,
        }


@dataclass(frozen=True)
class LexiconProperty:
    """Schema definition for a single property in a Lexicon schema.

    Describes the type and metadata for an event or profile property.
    """

    type: str
    """JSON Schema type (string, number, boolean, array, object, integer, null)."""

    description: str | None
    """Human-readable description of the property."""

    metadata: LexiconMetadata | None
    """Optional Mixpanel-specific metadata."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with type, and optionally description and metadata.
        """
        result: dict[str, Any] = {"type": self.type}
        if self.description is not None:
            result["description"] = self.description
        if self.metadata is not None:
            result["metadata"] = self.metadata.to_dict()
        return result


@dataclass(frozen=True)
class LexiconDefinition:
    """Full schema definition for an event or profile property in Lexicon.

    Contains the structural definition including description, properties,
    and platform-specific metadata.
    """

    description: str | None
    """Human-readable description of the entity."""

    properties: dict[str, LexiconProperty]
    """Property definitions keyed by property name."""

    metadata: LexiconMetadata | None
    """Optional Mixpanel-specific metadata for the entity."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with properties, and optionally description and metadata.
        """
        result: dict[str, Any] = {
            "properties": {k: v.to_dict() for k, v in self.properties.items()},
        }
        if self.description is not None:
            result["description"] = self.description
        if self.metadata is not None:
            result["metadata"] = self.metadata.to_dict()
        return result


@dataclass(frozen=True)
class LexiconSchema:
    """Complete schema definition from Mixpanel Lexicon.

    Represents a documented event or profile property definition
    from the Mixpanel data dictionary.
    """

    entity_type: str
    """Type of entity (e.g., 'event', 'profile', 'custom_event', 'group', etc.)."""

    name: str
    """Name of the event or profile property."""

    schema_json: LexiconDefinition
    """Full schema definition."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with entity_type, name, and schema_json.
        """
        return {
            "entity_type": self.entity_type,
            "name": self.name,
            "schema_json": self.schema_json.to_dict(),
        }


# =============================================================================
# JQL-Based Discovery Types (Phase 016)
# =============================================================================


@dataclass(frozen=True)
class PropertyValueCount:
    """A single value and its count from property distribution analysis.

    Represents one row in a property value distribution, showing the value,
    its occurrence count, and percentage of total.

    Attributes:
        value: The property value (can be string, number, bool, or None).
        count: Number of occurrences of this value.
        percentage: Percentage of total events (0.0 to 100.0).
    """

    value: str | int | float | bool | None
    """The property value."""

    count: int
    """Number of occurrences."""

    percentage: float
    """Percentage of total (0.0 to 100.0)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with value, count, and percentage.
        """
        return {
            "value": self.value,
            "count": self.count,
            "percentage": self.percentage,
        }


@dataclass(frozen=True)
class PropertyDistributionResult:
    """Distribution of values for a property from JQL analysis.

    Contains the top N values for a property with their counts and percentages,
    enabling quick understanding of property value distribution without processing
    all raw events.

    Attributes:
        event: The event type analyzed.
        property_name: The property name analyzed.
        from_date: Query start date (YYYY-MM-DD).
        to_date: Query end date (YYYY-MM-DD).
        total_count: Total number of events with this property defined.
        values: Top values with counts and percentages.
    """

    event: str
    """Event type analyzed."""

    property_name: str
    """Property name analyzed."""

    from_date: str
    """Query start date (YYYY-MM-DD)."""

    to_date: str
    """Query end date (YYYY-MM-DD)."""

    total_count: int
    """Total events with this property defined."""

    values: tuple[PropertyValueCount, ...]
    """Top values with counts and percentages."""

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with columns: value, count, percentage.

        Conversion is lazy - computed on first access and cached.

        Returns:
            DataFrame with value distribution data.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = [v.to_dict() for v in self.values]

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=["value", "count", "percentage"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all distribution data.
        """
        return {
            "event": self.event,
            "property_name": self.property_name,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "total_count": self.total_count,
            "values": [v.to_dict() for v in self.values],
        }


@dataclass(frozen=True)
class NumericPropertySummaryResult:
    """Statistical summary of a numeric property from JQL analysis.

    Contains min, max, sum, average, standard deviation, and percentiles
    for a numeric property, enabling understanding of value distributions
    without processing all raw events.

    Attributes:
        event: The event type analyzed.
        property_name: The property name analyzed.
        from_date: Query start date (YYYY-MM-DD).
        to_date: Query end date (YYYY-MM-DD).
        count: Number of events with this property defined.
        min: Minimum value.
        max: Maximum value.
        sum: Sum of all values.
        avg: Average value.
        stddev: Standard deviation.
        percentiles: Percentile values keyed by percentile number.
    """

    event: str
    """Event type analyzed."""

    property_name: str
    """Property name analyzed."""

    from_date: str
    """Query start date (YYYY-MM-DD)."""

    to_date: str
    """Query end date (YYYY-MM-DD)."""

    count: int
    """Number of events with this property defined."""

    min: float
    """Minimum value."""

    max: float
    """Maximum value."""

    sum: float
    """Sum of all values."""

    avg: float
    """Average value."""

    stddev: float
    """Standard deviation."""

    percentiles: dict[int, float]
    """Percentile values keyed by percentile number (e.g., {50: 98.0})."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all numeric summary data.
        """
        return {
            "event": self.event,
            "property_name": self.property_name,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "count": self.count,
            "min": self.min,
            "max": self.max,
            "sum": self.sum,
            "avg": self.avg,
            "stddev": self.stddev,
            "percentiles": {str(k): v for k, v in self.percentiles.items()},
        }


@dataclass(frozen=True)
class DailyCount:
    """Event count for a single date from daily counts analysis.

    Represents one row in a daily counts result, showing date, event, and count.

    Attributes:
        date: Date string (YYYY-MM-DD).
        event: Event name.
        count: Number of occurrences on this date.
    """

    date: str
    """Date string (YYYY-MM-DD)."""

    event: str
    """Event name."""

    count: int
    """Number of occurrences."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with date, event, and count.
        """
        return {
            "date": self.date,
            "event": self.event,
            "count": self.count,
        }


@dataclass(frozen=True)
class DailyCountsResult:
    """Time-series event counts by day from JQL analysis.

    Contains daily event counts for quick activity trend analysis
    without complex segmentation setup.

    Attributes:
        from_date: Query start date (YYYY-MM-DD).
        to_date: Query end date (YYYY-MM-DD).
        events: Event types included (None for all events).
        counts: Daily counts for each event.
    """

    from_date: str
    """Query start date (YYYY-MM-DD)."""

    to_date: str
    """Query end date (YYYY-MM-DD)."""

    events: tuple[str, ...] | None
    """Event types included (None for all events)."""

    counts: tuple[DailyCount, ...]
    """Daily counts for each event."""

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with columns: date, event, count.

        Conversion is lazy - computed on first access and cached.

        Returns:
            DataFrame with daily counts data.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = [c.to_dict() for c in self.counts]

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=["date", "event", "count"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all daily counts data.
        """
        return {
            "from_date": self.from_date,
            "to_date": self.to_date,
            "events": list(self.events) if self.events else None,
            "counts": [c.to_dict() for c in self.counts],
        }


@dataclass(frozen=True)
class EngagementBucket:
    """User count in an engagement bucket from engagement analysis.

    Represents one bucket in a user engagement distribution, showing
    how many users performed events in a certain frequency range.

    Attributes:
        bucket_min: Minimum events in this bucket.
        bucket_label: Human-readable label (e.g., "1", "2-5", "100+").
        user_count: Number of users in this bucket.
        percentage: Percentage of total users (0.0 to 100.0).
    """

    bucket_min: int
    """Minimum events in this bucket."""

    bucket_label: str
    """Human-readable label (e.g., '1', '2-5', '100+')."""

    user_count: int
    """Number of users in this bucket."""

    percentage: float
    """Percentage of total users (0.0 to 100.0)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with bucket data.
        """
        return {
            "bucket_min": self.bucket_min,
            "bucket_label": self.bucket_label,
            "user_count": self.user_count,
            "percentage": self.percentage,
        }


@dataclass(frozen=True)
class EngagementDistributionResult:
    """User engagement distribution from JQL analysis.

    Shows how many users performed N events, helping understand
    user engagement patterns without processing all raw events.

    Attributes:
        from_date: Query start date (YYYY-MM-DD).
        to_date: Query end date (YYYY-MM-DD).
        events: Event types included (None for all events).
        total_users: Total number of distinct users.
        buckets: Engagement buckets with user counts.
    """

    from_date: str
    """Query start date (YYYY-MM-DD)."""

    to_date: str
    """Query end date (YYYY-MM-DD)."""

    events: tuple[str, ...] | None
    """Event types included (None for all events)."""

    total_users: int
    """Total number of distinct users."""

    buckets: tuple[EngagementBucket, ...]
    """Engagement buckets with user counts."""

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with engagement bucket columns.

        Conversion is lazy - computed on first access and cached.

        Returns:
            DataFrame with engagement distribution data.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = [b.to_dict() for b in self.buckets]

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(
                columns=["bucket_min", "bucket_label", "user_count", "percentage"]
            )
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all engagement distribution data.
        """
        return {
            "from_date": self.from_date,
            "to_date": self.to_date,
            "events": list(self.events) if self.events else None,
            "total_users": self.total_users,
            "buckets": [b.to_dict() for b in self.buckets],
        }


@dataclass(frozen=True)
class PropertyCoverage:
    """Coverage statistics for a single property from coverage analysis.

    Shows how often a property is defined vs null for a given event type.

    Attributes:
        property: Property name.
        defined_count: Number of events with this property defined.
        null_count: Number of events with this property null/undefined.
        coverage_percentage: Percentage of events with property defined (0.0-100.0).
    """

    property: str
    """Property name."""

    defined_count: int
    """Number of events with property defined."""

    null_count: int
    """Number of events with property null/undefined."""

    coverage_percentage: float
    """Percentage with property defined (0.0 to 100.0)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with coverage data.
        """
        return {
            "property": self.property,
            "defined_count": self.defined_count,
            "null_count": self.null_count,
            "coverage_percentage": self.coverage_percentage,
        }


@dataclass(frozen=True)
class PropertyCoverageResult:
    """Property coverage analysis result from JQL.

    Shows which properties are consistently populated vs sparse,
    helping understand data quality before writing queries.

    Attributes:
        event: The event type analyzed.
        from_date: Query start date (YYYY-MM-DD).
        to_date: Query end date (YYYY-MM-DD).
        total_events: Total number of events analyzed.
        coverage: Coverage statistics for each property.
    """

    event: str
    """Event type analyzed."""

    from_date: str
    """Query start date (YYYY-MM-DD)."""

    to_date: str
    """Query end date (YYYY-MM-DD)."""

    total_events: int
    """Total number of events analyzed."""

    coverage: tuple[PropertyCoverage, ...]
    """Coverage statistics for each property."""

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with property coverage columns.

        Conversion is lazy - computed on first access and cached.

        Returns:
            DataFrame with property coverage data.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = [c.to_dict() for c in self.coverage]

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(
                columns=[
                    "property",
                    "defined_count",
                    "null_count",
                    "coverage_percentage",
                ]
            )
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all coverage data.
        """
        return {
            "event": self.event,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "total_events": self.total_events,
            "coverage": [c.to_dict() for c in self.coverage],
        }


# =============================================================================
# App API Types (OAuth & Workspace Scoping)
# =============================================================================


class PublicWorkspace(BaseModel):
    """A workspace within a Mixpanel project.

    Represents a workspace as returned by the Mixpanel App API
    ``GET /api/app/projects/{pid}/workspaces/public`` endpoint.
    Extra fields from the API response are preserved via ``extra="allow"``.

    Attributes:
        id: Workspace identifier.
        name: Human-readable workspace name.
        project_id: Parent project identifier.
        is_default: Whether this is the default workspace.
        description: Workspace description, if set.
        is_global: Whether workspace is global.
        is_restricted: Whether workspace has restrictions.
        is_visible: Whether workspace is visible.
        created_iso: ISO 8601 creation timestamp.
        creator_name: Name of workspace creator.

    Example:
        ```python
        ws = PublicWorkspace(
            id=1, name="Main", project_id=12345, is_default=True
        )
        assert ws.is_default is True
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int
    """Workspace identifier."""

    name: str
    """Human-readable workspace name."""

    project_id: int
    """Parent project identifier."""

    is_default: bool
    """Whether this is the default workspace."""

    description: str | None = None
    """Workspace description, if set."""

    is_global: bool | None = None
    """Whether workspace is global."""

    is_restricted: bool | None = None
    """Whether workspace has restrictions."""

    is_visible: bool | None = None
    """Whether workspace is visible."""

    created_iso: str | None = None
    """ISO 8601 creation timestamp."""

    creator_name: str | None = None
    """Name of workspace creator."""


class CursorPagination(BaseModel):
    """Cursor-based pagination metadata from App API responses.

    Attributes:
        page_size: Number of items per page.
        next_cursor: Cursor for next page, or None if last page.
        previous_cursor: Cursor for previous page.

    Example:
        ```python
        pagination = CursorPagination(page_size=100, next_cursor="abc123")
        assert pagination.next_cursor == "abc123"
        ```
    """

    model_config = ConfigDict(frozen=True)

    page_size: int
    """Number of items per page."""

    next_cursor: str | None = None
    """Cursor for next page (None = last page)."""

    previous_cursor: str | None = None
    """Cursor for previous page."""


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated App API response wrapper.

    Generic wrapper for paginated responses from the Mixpanel App API.
    Contains the results list, status, and optional pagination metadata.

    Attributes:
        status: Response status (typically "ok").
        results: Page of results.
        pagination: Pagination metadata, or None for single-page responses.

    Example:
        ```python
        response = PaginatedResponse[dict](
            status="ok",
            results=[{"id": 1}],
            pagination=CursorPagination(page_size=100),
        )
        assert len(response.results) == 1
        ```
    """

    model_config = ConfigDict(frozen=True)

    status: str
    """Response status (typically "ok")."""

    results: list[T]
    """Page of results."""

    pagination: CursorPagination | None = None
    """Pagination metadata, or None for single-page responses."""


# =============================================================================
# Dashboard Types (Phase 024)
# =============================================================================


class Dashboard(BaseModel):
    """A Mixpanel dashboard as returned by the App API.

    Represents the full dashboard entity including metadata, permissions,
    and optional layout/content fields. Extra fields from API evolution
    are preserved via ``extra="allow"``.

    Attributes:
        id: Unique dashboard identifier.
        title: Dashboard title.
        description: Dashboard description.
        is_private: Whether the dashboard is private.
        is_restricted: Whether the dashboard has restricted access.
        creator_id: ID of the dashboard creator.
        creator_name: Name of the dashboard creator.
        creator_email: Email of the dashboard creator.
        created: Creation timestamp (lenient parsing).
        modified: Last modification timestamp.
        is_favorited: Whether the current user has favorited this dashboard.
        pinned_date: Date the dashboard was pinned, if any.
        layout_version: Layout version metadata.
        unique_view_count: Number of unique viewers.
        total_view_count: Total view count.
        last_modified_by_id: ID of the last modifier.
        last_modified_by_name: Name of the last modifier.
        last_modified_by_email: Email of the last modifier.
        filters: Dashboard-level filters.
        breakdowns: Dashboard-level breakdowns.
        time_filter: Dashboard-level time filter.
        generation_type: How the dashboard was generated.
        parent_dashboard_id: Parent dashboard ID for nested dashboards.
        child_dashboards: Child dashboard references.
        can_update_basic: Permission flag.
        can_share: Permission flag.
        can_view: Permission flag.
        can_update_restricted: Permission flag.
        can_update_visibility: Permission flag.
        is_superadmin: Whether current user is superadmin.
        allow_staff_override: Whether staff override is allowed.
        can_pin: Whether current user can pin.
        is_shared_with_project: Whether shared with the project.
        creator: Creator identifier string.
        ancestors: Ancestor dashboard references.
        layout: Dashboard layout data.
        contents: Dashboard contents data.
        num_active_public_links: Number of active public links.
        new_content: New content data.
        template_type: Template type if created from a template.

    Example:
        ```python
        dashboard = Dashboard(
            id=1, title="Q1 Metrics", is_private=False,
            is_restricted=False, is_favorited=False,
            can_update_basic=True, can_share=True, can_view=True,
            can_update_restricted=False, can_update_visibility=False,
            is_superadmin=False, allow_staff_override=False,
            can_pin=True, is_shared_with_project=True, ancestors=[],
        )
        assert dashboard.title == "Q1 Metrics"
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int
    """Unique dashboard identifier."""

    title: str
    """Dashboard title."""

    description: str | None = None
    """Dashboard description."""

    is_private: bool = False
    """Whether the dashboard is private."""

    is_restricted: bool = False
    """Whether the dashboard has restricted access."""

    creator_id: int | None = None
    """ID of the dashboard creator."""

    creator_name: str | None = None
    """Name of the dashboard creator."""

    creator_email: str | None = None
    """Email of the dashboard creator."""

    created: datetime | None = None
    """Creation timestamp."""

    modified: datetime | None = None
    """Last modification timestamp."""

    is_favorited: bool = False
    """Whether the current user has favorited this dashboard."""

    pinned_date: str | None = None
    """Date the dashboard was pinned, if any."""

    layout_version: Any | None = None
    """Layout version metadata."""

    unique_view_count: int | None = None
    """Number of unique viewers."""

    total_view_count: int | None = None
    """Total view count."""

    last_modified_by_id: int | None = None
    """ID of the last modifier."""

    last_modified_by_name: str | None = None
    """Name of the last modifier."""

    last_modified_by_email: str | None = None
    """Email of the last modifier."""

    filters: list[Any] | None = None
    """Dashboard-level filters."""

    breakdowns: list[Any] | None = None
    """Dashboard-level breakdowns."""

    time_filter: Any | None = None
    """Dashboard-level time filter."""

    generation_type: str | None = None
    """How the dashboard was generated."""

    parent_dashboard_id: int | None = None
    """Parent dashboard ID for nested dashboards."""

    child_dashboards: list[Any] | None = None
    """Child dashboard references."""

    can_update_basic: bool = False
    """Permission: can update basic fields."""

    can_share: bool = False
    """Permission: can share."""

    can_view: bool = False
    """Permission: can view."""

    can_update_restricted: bool = False
    """Permission: can update restricted fields."""

    can_update_visibility: bool = False
    """Permission: can update visibility."""

    is_superadmin: bool = False
    """Whether current user is superadmin."""

    allow_staff_override: bool = False
    """Whether staff override is allowed."""

    can_pin: bool = False
    """Whether current user can pin."""

    is_shared_with_project: bool = False
    """Whether shared with the project."""

    creator: str | None = None
    """Creator identifier string."""

    ancestors: list[Any] = Field(default_factory=list)
    """Ancestor dashboard references."""

    layout: Any | None = None
    """Dashboard layout data."""

    contents: Any | None = None
    """Dashboard contents data."""

    num_active_public_links: int | None = None
    """Number of active public links."""

    new_content: Any | None = None
    """New content data."""

    template_type: str | None = None
    """Template type if created from a template."""


class CreateDashboardParams(BaseModel):
    """Parameters for creating a new dashboard.

    Attributes:
        title: Dashboard title (required).
        description: Dashboard description.
        is_private: Whether the dashboard should be private.
        is_restricted: Whether the dashboard should have restricted access.
        filters: Dashboard-level filters.
        breakdowns: Dashboard-level breakdowns.
        time_filter: Dashboard-level time filter.
        duplicate: ID of dashboard to duplicate.

    Example:
        ```python
        params = CreateDashboardParams(title="Q1 Metrics")
        data = params.model_dump(exclude_none=True)
        # {"title": "Q1 Metrics"}
        ```
    """

    title: str
    """Dashboard title (required)."""

    description: str | None = None
    """Dashboard description."""

    is_private: bool | None = None
    """Whether the dashboard should be private."""

    is_restricted: bool | None = None
    """Whether the dashboard should have restricted access."""

    filters: list[Any] | None = None
    """Dashboard-level filters."""

    breakdowns: list[Any] | None = None
    """Dashboard-level breakdowns."""

    time_filter: Any | None = None
    """Dashboard-level time filter."""

    duplicate: int | None = None
    """ID of dashboard to duplicate."""


class UpdateDashboardParams(BaseModel):
    """Parameters for updating an existing dashboard.

    All fields are optional — only provided fields are sent to the API.

    Attributes:
        title: New dashboard title.
        description: New dashboard description.
        is_private: New privacy setting.
        is_restricted: New restriction setting.
        filters: New dashboard-level filters.
        breakdowns: New dashboard-level breakdowns.
        time_filter: New dashboard-level time filter.
        layout: New dashboard layout data.
        content: New dashboard content data.

    Example:
        ```python
        params = UpdateDashboardParams(title="Q1 Metrics v2")
        data = params.model_dump(exclude_none=True)
        # {"title": "Q1 Metrics v2"}
        ```
    """

    title: str | None = None
    """New dashboard title."""

    description: str | None = None
    """New dashboard description."""

    is_private: bool | None = None
    """New privacy setting."""

    is_restricted: bool | None = None
    """New restriction setting."""

    filters: list[Any] | None = None
    """New dashboard-level filters."""

    breakdowns: list[Any] | None = None
    """New dashboard-level breakdowns."""

    time_filter: Any | None = None
    """New dashboard-level time filter."""

    layout: Any | None = None
    """New dashboard layout data."""

    content: Any | None = None
    """New dashboard content data."""


# =============================================================================
# Blueprint Types (Phase 024)
# =============================================================================


class BlueprintTemplate(BaseModel):
    """A dashboard blueprint template.

    Attributes:
        title_key: Template title key.
        description_key: Template description key.
        alternative_description_key: Alternative description key.
        number_of_reports: Number of reports in the template.

    Example:
        ```python
        template = BlueprintTemplate(
            title_key="onboarding", description_key="Get started"
        )
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    title_key: str
    """Template title key."""

    description_key: str
    """Template description key."""

    alternative_description_key: str | None = None
    """Alternative description key."""

    number_of_reports: int | None = None
    """Number of reports in the template."""


class BlueprintConfig(BaseModel):
    """Configuration for a dashboard blueprint.

    Attributes:
        variables: Template variable mappings.

    Example:
        ```python
        config = BlueprintConfig(variables={"event": "Signup"})
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    variables: dict[str, str]
    """Template variable mappings."""


class BlueprintCard(BaseModel):
    """A card in a blueprint dashboard.

    Attributes:
        card_type: Card type (serialized as ``"type"``).
        text_card_id: Text card ID, if applicable.
        bookmark_id: Bookmark ID, if applicable.
        markdown: Markdown content for text cards.
        name: Card name.
        params: Card parameters.

    Example:
        ```python
        card = BlueprintCard(card_type="report", bookmark_id=123)
        data = card.model_dump(by_alias=True, exclude_none=True)
        # {"type": "report", "bookmark_id": 123}
        ```
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    card_type: str = Field(alias="type")
    """Card type (serialized as ``"type"``)."""

    text_card_id: int | None = None
    """Text card ID, if applicable."""

    bookmark_id: int | None = None
    """Bookmark ID, if applicable."""

    markdown: str | None = None
    """Markdown content for text cards."""

    name: str | None = None
    """Card name."""

    params: dict[str, Any] | None = None
    """Card parameters."""


class BlueprintFinishParams(BaseModel):
    """Parameters for finalizing a blueprint dashboard.

    Attributes:
        dashboard_id: ID of the blueprint dashboard to finalize.
        cards: List of cards to include.

    Example:
        ```python
        params = BlueprintFinishParams(
            dashboard_id=1,
            cards=[BlueprintCard(card_type="report", bookmark_id=123)],
        )
        ```
    """

    dashboard_id: int
    """ID of the blueprint dashboard to finalize."""

    cards: list[BlueprintCard]
    """List of cards to include."""


class RcaSourceData(BaseModel):
    """Source data for RCA dashboard creation.

    Attributes:
        source_type: Source type (serialized as ``"type"``).
        date: Date string.
        metric_source: Whether this is a metric source.

    Example:
        ```python
        data = RcaSourceData(source_type="anomaly", date="2025-01-01")
        dumped = data.model_dump(by_alias=True, exclude_none=True)
        # {"type": "anomaly", "date": "2025-01-01"}
        ```
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    source_type: str = Field(alias="type")
    """Source type (serialized as ``"type"``)."""

    date: str | None = None
    """Date string."""

    metric_source: bool | None = None
    """Whether this is a metric source."""


class CreateRcaDashboardParams(BaseModel):
    """Parameters for creating an RCA dashboard.

    Attributes:
        rca_source_id: Source ID for RCA analysis.
        rca_source_data: Source data configuration.

    Example:
        ```python
        params = CreateRcaDashboardParams(
            rca_source_id=42,
            rca_source_data=RcaSourceData(source_type="anomaly"),
        )
        ```
    """

    rca_source_id: int
    """Source ID for RCA analysis."""

    rca_source_data: RcaSourceData
    """Source data configuration."""


class UpdateReportLinkParams(BaseModel):
    """Parameters for updating a report link on a dashboard.

    Attributes:
        link_type: Link type (serialized as ``"type"``).

    Example:
        ```python
        params = UpdateReportLinkParams(link_type="embedded")
        data = params.model_dump(by_alias=True, exclude_none=True)
        # {"type": "embedded"}
        ```
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    link_type: str = Field(alias="type")
    """Link type (serialized as ``"type"``)."""


class UpdateTextCardParams(BaseModel):
    """Parameters for updating a text card on a dashboard.

    Attributes:
        markdown: Markdown content for the text card.

    Example:
        ```python
        params = UpdateTextCardParams(markdown="# Hello")
        ```
    """

    model_config = ConfigDict(extra="allow")

    markdown: str | None = None
    """Markdown content for the text card."""


# =============================================================================
# Bookmark/Report Types (Phase 024)
# =============================================================================


class BookmarkMetadata(BaseModel):
    """Metadata associated with a bookmark/report.

    Contains optional display and calculation settings that vary by
    bookmark type (insights, funnels, retention, etc.).

    Attributes:
        table_display_mode: Table display mode setting.
        compare_enabled: Whether comparison is enabled.
        compare_filters: Comparison filter settings.
        retention_calculation_type: Retention calculation method.
        event_name: Associated event name.
        funnel_conversion_window: Funnel conversion window in days.
        funnel_breakdown_limit: Maximum funnel breakdown count.

    Example:
        ```python
        meta = BookmarkMetadata(
            table_display_mode="linear",
            compare_enabled=True,
        )
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    table_display_mode: str | None = None
    """Table display mode setting."""

    compare_enabled: bool | None = None
    """Whether comparison is enabled."""

    compare_filters: list[Any] | None = None
    """Comparison filter settings."""

    retention_calculation_type: str | None = None
    """Retention calculation method."""

    event_name: str | None = None
    """Associated event name."""

    funnel_conversion_window: int | None = None
    """Funnel conversion window in days."""

    funnel_breakdown_limit: int | None = None
    """Maximum funnel breakdown count."""


class Bookmark(BaseModel):
    """A Mixpanel bookmark (saved report) as returned by the App API.

    Represents the full bookmark entity including query parameters,
    metadata, and permissions. The ``bookmark_type`` field is aliased
    from ``"type"`` in the API response.

    Attributes:
        id: Unique bookmark identifier.
        project_id: Parent project identifier.
        name: Bookmark name.
        bookmark_type: Report type (aliased from ``"type"``).
        description: Bookmark description.
        icon: Bookmark icon.
        params: Query parameters (JSON value defining the report).
        dashboard_id: Associated dashboard ID.
        include_in_dashboard: Whether included in dashboard.
        is_default: Whether this is a default bookmark.
        creator_id: ID of the creator.
        creator_name: Name of the creator.
        creator_email: Email of the creator.
        created: Creation timestamp.
        modified: Last modification timestamp.
        last_modified_by_id: ID of the last modifier.
        last_modified_by_name: Name of the last modifier.
        last_modified_by_email: Email of the last modifier.
        metadata: Report-specific metadata.
        is_visibility_restricted: Visibility restriction flag.
        is_modification_restricted: Modification restriction flag.
        can_update_basic: Permission flag.
        can_view: Permission flag.
        can_share: Permission flag.
        generation_type: How the bookmark was generated.
        original_type: Original report type before conversion.
        unique_view_count: Number of unique viewers.
        total_view_count: Total view count.

    Example:
        ```python
        bookmark = Bookmark(
            id=1, name="Signup Funnel", bookmark_type="funnels",
            params={"events": [{"event": "Signup"}]},
        )
        assert bookmark.bookmark_type == "funnels"
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow", populate_by_name=True)

    id: int
    """Unique bookmark identifier."""

    project_id: int | None = None
    """Parent project identifier."""

    name: str
    """Bookmark name."""

    bookmark_type: str = Field(alias="type")
    """Report type (aliased from ``"type"``)."""

    description: str | None = None
    """Bookmark description."""

    icon: str | None = None
    """Bookmark icon."""

    params: dict[str, Any] | None = None
    """Query parameters (JSON value defining the report)."""

    dashboard_id: int | None = None
    """Associated dashboard ID."""

    include_in_dashboard: bool | None = None
    """Whether included in dashboard."""

    is_default: bool | None = None
    """Whether this is a default bookmark."""

    creator_id: int | None = None
    """ID of the creator."""

    creator_name: str | None = None
    """Name of the creator."""

    creator_email: str | None = None
    """Email of the creator."""

    created: datetime | None = None
    """Creation timestamp."""

    modified: datetime | None = None
    """Last modification timestamp."""

    last_modified_by_id: int | None = None
    """ID of the last modifier."""

    last_modified_by_name: str | None = None
    """Name of the last modifier."""

    last_modified_by_email: str | None = None
    """Email of the last modifier."""

    metadata: BookmarkMetadata | None = None
    """Report-specific metadata."""

    is_visibility_restricted: bool | None = None
    """Visibility restriction flag."""

    is_modification_restricted: bool | None = None
    """Modification restriction flag."""

    can_update_basic: bool | None = None
    """Permission: can update basic fields."""

    can_view: bool | None = None
    """Permission: can view."""

    can_share: bool | None = None
    """Permission: can share."""

    generation_type: str | None = None
    """How the bookmark was generated."""

    original_type: str | None = None
    """Original report type before conversion."""

    unique_view_count: int | None = None
    """Number of unique viewers."""

    total_view_count: int | None = None
    """Total view count."""


class CreateBookmarkParams(BaseModel):
    """Parameters for creating a new bookmark/report.

    Attributes:
        name: Bookmark name (required).
        bookmark_type: Report type (required, serialized as ``"type"``).
        params: Query parameters (required).
        description: Bookmark description.
        icon: Bookmark icon.
        dashboard_id: Dashboard to associate with.
        is_visibility_restricted: Visibility restriction flag.
        is_modification_restricted: Modification restriction flag.

    Example:
        ```python
        params = CreateBookmarkParams(
            name="Signup Funnel",
            bookmark_type="funnels",
            params={"events": [{"event": "Signup"}]},
        )
        data = params.model_dump(by_alias=True, exclude_none=True)
        ```
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    """Bookmark name (required)."""

    bookmark_type: str = Field(alias="type")
    """Report type (required, serialized as ``"type"``)."""

    params: dict[str, Any]
    """Query parameters (required)."""

    description: str | None = None
    """Bookmark description."""

    icon: str | None = None
    """Bookmark icon."""

    dashboard_id: int | None = None
    """Dashboard to associate with."""

    is_visibility_restricted: bool | None = None
    """Visibility restriction flag."""

    is_modification_restricted: bool | None = None
    """Modification restriction flag."""


class UpdateBookmarkParams(BaseModel):
    """Parameters for updating an existing bookmark/report.

    All fields are optional — only provided fields are sent to the API.

    Attributes:
        name: New bookmark name.
        params: New query parameters.
        description: New bookmark description.
        icon: New bookmark icon.
        dashboard_id: New associated dashboard ID.
        is_visibility_restricted: New visibility restriction.
        is_modification_restricted: New modification restriction.
        deleted: Soft-delete flag.

    Example:
        ```python
        params = UpdateBookmarkParams(name="Updated Funnel")
        data = params.model_dump(exclude_none=True)
        # {"name": "Updated Funnel"}
        ```
    """

    name: str | None = None
    """New bookmark name."""

    params: dict[str, Any] | None = None
    """New query parameters."""

    description: str | None = None
    """New bookmark description."""

    icon: str | None = None
    """New bookmark icon."""

    dashboard_id: int | None = None
    """New associated dashboard ID."""

    is_visibility_restricted: bool | None = None
    """New visibility restriction."""

    is_modification_restricted: bool | None = None
    """New modification restriction."""

    deleted: bool | None = None
    """Soft-delete flag."""


class BulkUpdateBookmarkEntry(BaseModel):
    """Entry for bulk-updating bookmarks.

    Attributes:
        id: Bookmark ID to update (required).
        name: New bookmark name.
        params: New query parameters.
        description: New bookmark description.
        icon: New bookmark icon.
        is_visibility_restricted: New visibility restriction.
        is_modification_restricted: New modification restriction.

    Example:
        ```python
        entry = BulkUpdateBookmarkEntry(id=123, name="Renamed")
        ```
    """

    id: int
    """Bookmark ID to update (required)."""

    name: str | None = None
    """New bookmark name."""

    params: dict[str, Any] | None = None
    """New query parameters."""

    description: str | None = None
    """New bookmark description."""

    icon: str | None = None
    """New bookmark icon."""

    is_visibility_restricted: bool | None = None
    """New visibility restriction."""

    is_modification_restricted: bool | None = None
    """New modification restriction."""


class BookmarkHistoryPagination(BaseModel):
    """Pagination metadata for bookmark history responses.

    Attributes:
        next_cursor: Cursor for next page.
        previous_cursor: Cursor for previous page.
        page_size: Number of items per page.

    Example:
        ```python
        pagination = BookmarkHistoryPagination(page_size=20)
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    next_cursor: str | None = None
    """Cursor for next page."""

    previous_cursor: str | None = None
    """Cursor for previous page."""

    page_size: int = 0
    """Number of items per page."""


class BookmarkHistoryResponse(BaseModel):
    """Response from the bookmark history endpoint.

    Attributes:
        results: List of history entries.
        pagination: Pagination metadata.

    Example:
        ```python
        response = BookmarkHistoryResponse(results=[{"action": "created"}])
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    results: list[Any] = Field(default_factory=list)
    """List of history entries."""

    pagination: BookmarkHistoryPagination | None = None
    """Pagination metadata."""


# =============================================================================
# Cohort Types (Phase 024)
# =============================================================================


class CohortCreator(BaseModel):
    """Creator information for a cohort.

    Attributes:
        id: Creator user ID.
        name: Creator name.
        email: Creator email.

    Example:
        ```python
        creator = CohortCreator(id=1, name="Alice", email="alice@example.com")
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int | None = None
    """Creator user ID."""

    name: str | None = None
    """Creator name."""

    email: str | None = None
    """Creator email."""


class Cohort(BaseModel):
    """A Mixpanel cohort as returned by the App API.

    Represents the full cohort entity with definition, metadata, and
    cross-references. Extra fields from API evolution are preserved
    via ``extra="allow"``.

    Attributes:
        id: Unique cohort identifier.
        name: Cohort name.
        description: Cohort description.
        count: Number of users in the cohort.
        is_visible: Whether the cohort is visible.
        is_locked: Whether the cohort is locked.
        data_group_id: Data group identifier.
        last_edited: Last edited timestamp string.
        created_by: Creator information.
        referenced_by: IDs of entities referencing this cohort.
        verified: Whether the cohort is verified.
        last_queried: Last queried timestamp string.
        referenced_directly_by: IDs of entities directly referencing this cohort.
        active_integrations: Active integration IDs.

    Example:
        ```python
        cohort = Cohort(id=1, name="Power Users")
        assert cohort.name == "Power Users"
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int
    """Unique cohort identifier."""

    name: str
    """Cohort name."""

    description: str | None = None
    """Cohort description."""

    count: int | None = None
    """Number of users in the cohort."""

    is_visible: bool | None = None
    """Whether the cohort is visible."""

    is_locked: bool | None = None
    """Whether the cohort is locked."""

    data_group_id: str | None = None
    """Data group identifier."""

    last_edited: str | None = None
    """Last edited timestamp string."""

    created_by: CohortCreator | None = None
    """Creator information."""

    referenced_by: list[int] | None = None
    """IDs of entities referencing this cohort."""

    verified: bool = False
    """Whether the cohort is verified."""

    last_queried: str | None = None
    """Last queried timestamp string."""

    referenced_directly_by: list[int] = Field(default_factory=list)
    """IDs of entities directly referencing this cohort."""

    active_integrations: list[int] = Field(default_factory=list)
    """Active integration IDs."""


class _DefinitionFlatteningModel(BaseModel):
    """Base model that flattens a ``definition`` dict into the top-level payload.

    Subclasses must declare a ``definition: dict[str, Any] | None`` field.
    During serialization, the definition's keys are merged into the
    top-level dict and the ``definition`` key is removed.
    """

    definition: dict[str, Any] | None = None
    """Definition dict (flattened into payload during serialization)."""

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize with ``definition`` flattened into the top level.

        Args:
            **kwargs: Keyword arguments passed to ``BaseModel.model_dump()``.

        Returns:
            Dict with ``definition`` fields merged into the top level.
        """
        data = super().model_dump(**kwargs)
        definition = data.pop("definition", None)
        if definition:
            data.update(definition)
        return data


class CreateCohortParams(_DefinitionFlatteningModel):
    """Parameters for creating a new cohort.

    The ``definition`` dict is flattened into the top-level JSON payload
    at serialization time — its keys become top-level fields in the request body.

    Attributes:
        name: Cohort name (required).
        description: Cohort description.
        data_group_id: Data group identifier.
        is_locked: Whether the cohort should be locked.
        is_visible: Whether the cohort should be visible.
        deleted: Soft-delete flag.

    Example:
        ```python
        params = CreateCohortParams(name="Power Users")
        data = params.model_dump(exclude_none=True)
        # {"name": "Power Users"}
        ```
    """

    name: str
    """Cohort name (required)."""

    description: str | None = None
    """Cohort description."""

    data_group_id: str | None = None
    """Data group identifier."""

    is_locked: bool | None = None
    """Whether the cohort should be locked."""

    is_visible: bool | None = None
    """Whether the cohort should be visible."""

    deleted: bool | None = None
    """Soft-delete flag."""


class UpdateCohortParams(_DefinitionFlatteningModel):
    """Parameters for updating an existing cohort.

    All fields are optional — only provided fields are sent to the API.
    The ``definition`` dict is flattened into the payload.

    Attributes:
        name: New cohort name.
        description: New cohort description.
        data_group_id: New data group identifier.
        is_locked: New lock setting.
        is_visible: New visibility setting.
        deleted: Soft-delete flag.

    Example:
        ```python
        params = UpdateCohortParams(name="Updated Cohort")
        data = params.model_dump(exclude_none=True)
        # {"name": "Updated Cohort"}
        ```
    """

    name: str | None = None
    """New cohort name."""

    description: str | None = None
    """New cohort description."""

    data_group_id: str | None = None
    """New data group identifier."""

    is_locked: bool | None = None
    """New lock setting."""

    is_visible: bool | None = None
    """New visibility setting."""

    deleted: bool | None = None
    """Soft-delete flag."""


class BulkUpdateCohortEntry(_DefinitionFlatteningModel):
    """Entry for bulk-updating cohorts.

    Attributes:
        id: Cohort ID to update (required).
        name: New cohort name.
        description: New cohort description.

    Example:
        ```python
        entry = BulkUpdateCohortEntry(id=1, name="Renamed")
        ```
    """

    id: int
    """Cohort ID to update (required)."""

    name: str | None = None
    """New cohort name."""

    description: str | None = None
    """New cohort description."""


# =============================================================================
# Feature Flag & Experiment Types (Phase 025)
# =============================================================================


class FeatureFlagStatus(str, Enum):
    """Lifecycle state of a feature flag.

    Attributes:
        ENABLED: Flag is active and serving variants.
        DISABLED: Flag is inactive (default state).
        ARCHIVED: Flag is soft-deleted, excluded from default listings.

    Example:
        ```python
        status = FeatureFlagStatus.ENABLED
        assert status.value == "enabled"
        ```
    """

    ENABLED = "enabled"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class ServingMethod(str, Enum):
    """Controls how flag values are delivered to clients.

    Attributes:
        CLIENT: Client-side evaluation (default).
        SERVER: Server-side evaluation only.
        REMOTE_OR_LOCAL: Remote preferred, local fallback.
        REMOTE_ONLY: Remote evaluation only.

    Example:
        ```python
        method = ServingMethod.CLIENT
        assert method.value == "client"
        ```
    """

    CLIENT = "client"
    SERVER = "server"
    REMOTE_OR_LOCAL = "remote_or_local"
    REMOTE_ONLY = "remote_only"


class FlagContractStatus(str, Enum):
    """Account-level flag contract status.

    Attributes:
        ACTIVE: Active contract.
        GRACE_PERIOD: Contract in grace period.
        EXPIRED: Contract expired.

    Example:
        ```python
        status = FlagContractStatus.ACTIVE
        assert status.value == "active"
        ```
    """

    ACTIVE = "active"
    GRACE_PERIOD = "grace_period"
    EXPIRED = "expired"


class ExperimentStatus(str, Enum):
    """Lifecycle state of an experiment.

    State transitions: ``draft`` → ``active`` (launch) → ``concluded``
    (conclude) → ``success`` | ``fail`` (decide).

    Attributes:
        DRAFT: Experiment created but not started.
        ACTIVE: Experiment running, collecting data.
        CONCLUDED: Experiment stopped, awaiting decision.
        SUCCESS: Experiment decided as successful.
        FAIL: Experiment decided as failed.

    Example:
        ```python
        status = ExperimentStatus.DRAFT
        assert status.value == "draft"
        ```
    """

    DRAFT = "draft"
    ACTIVE = "active"
    CONCLUDED = "concluded"
    SUCCESS = "success"
    FAIL = "fail"


class ExperimentCreator(BaseModel):
    """Creator metadata for an experiment.

    Attributes:
        id: Creator's user ID.
        first_name: Creator's first name.
        last_name: Creator's last name.

    Example:
        ```python
        creator = ExperimentCreator(id=1, first_name="Alice", last_name="Smith")
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int | None = None
    """Creator's user ID."""

    first_name: str | None = None
    """Creator's first name."""

    last_name: str | None = None
    """Creator's last name."""


class FeatureFlag(BaseModel):
    """A Mixpanel feature flag as returned by the App API.

    Represents the full feature flag entity including configuration,
    metadata, and permissions. Extra fields from API evolution are
    preserved via ``extra="allow"``.

    Attributes:
        id: Unique identifier (UUID).
        project_id: Project this flag belongs to.
        name: Human-readable name.
        key: Machine-readable key (unique per project).
        description: Optional description.
        status: Current lifecycle status.
        tags: Tags for organization.
        experiment_id: Linked experiment ID if flag backs an experiment.
        context: Flag context identifier.
        data_group_id: Data group identifier.
        serving_method: How flag values are delivered.
        ruleset: Variants, rollout rules, and test overrides.
        hash_salt: Salt for deterministic variant assignment.
        workspace_id: Workspace this flag belongs to.
        content_type: Content type identifier.
        created: ISO 8601 creation timestamp.
        modified: ISO 8601 last-modified timestamp.
        enabled_at: Timestamp when flag was last enabled.
        deleted: Timestamp when flag was deleted.
        creator_id: Creator's user ID.
        creator_name: Creator's display name.
        creator_email: Creator's email.
        last_modified_by_id: Last modifier's user ID.
        last_modified_by_name: Last modifier's display name.
        last_modified_by_email: Last modifier's email.
        is_favorited: Whether current user has favorited.
        pinned_date: Date flag was pinned.
        can_edit: Permission: can current user edit.

    Example:
        ```python
        flag = FeatureFlag(
            id="abc-123",
            project_id=12345,
            name="Dark Mode",
            key="dark_mode",
            status=FeatureFlagStatus.DISABLED,
            context="default",
            serving_method=ServingMethod.CLIENT,
            ruleset={"variants": []},
            created="2026-01-01T00:00:00Z",
            modified="2026-01-01T00:00:00Z",
        )
        assert flag.key == "dark_mode"
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow", populate_by_name=True)

    id: str
    """Unique identifier (UUID)."""

    project_id: int
    """Project this flag belongs to."""

    name: str
    """Human-readable name."""

    key: str
    """Machine-readable key (unique per project)."""

    description: str | None = None
    """Optional description."""

    status: FeatureFlagStatus = FeatureFlagStatus.DISABLED
    """Current lifecycle status."""

    tags: list[str] = Field(default_factory=list)
    """Tags for organization."""

    experiment_id: str | None = None
    """Linked experiment ID if flag backs an experiment."""

    context: str = ""
    """Flag context identifier."""

    data_group_id: str | None = None
    """Data group identifier."""

    serving_method: ServingMethod = ServingMethod.CLIENT
    """How flag values are delivered."""

    ruleset: dict[str, Any] = Field(default_factory=dict)
    """Variants, rollout rules, and test overrides."""

    hash_salt: str | None = None
    """Salt for deterministic variant assignment."""

    workspace_id: int | None = None
    """Workspace this flag belongs to."""

    content_type: str | None = None
    """Content type identifier."""

    created: str = ""
    """ISO 8601 creation timestamp."""

    modified: str = ""
    """ISO 8601 last-modified timestamp."""

    enabled_at: str | None = None
    """Timestamp when flag was last enabled."""

    deleted: str | None = None
    """Timestamp when flag was deleted."""

    creator_id: int | None = None
    """Creator's user ID."""

    creator_name: str | None = None
    """Creator's display name."""

    creator_email: str | None = None
    """Creator's email."""

    last_modified_by_id: int | None = None
    """Last modifier's user ID."""

    last_modified_by_name: str | None = None
    """Last modifier's display name."""

    last_modified_by_email: str | None = None
    """Last modifier's email."""

    is_favorited: bool | None = None
    """Whether current user has favorited."""

    pinned_date: str | None = None
    """Date flag was pinned."""

    can_edit: bool = False
    """Permission: can current user edit."""


class CreateFeatureFlagParams(BaseModel):
    """Parameters for creating a new feature flag.

    The Mixpanel API requires ``name``, ``key``, ``context``,
    ``serving_method``, ``tags``, and ``ruleset`` (with ``variants``
    and ``rollout`` sub-fields). Sensible defaults are provided for
    the non-obvious required fields so that minimal usage works::

        CreateFeatureFlagParams(name="Dark Mode", key="dark_mode")

    Attributes:
        name: Flag name (required).
        key: Unique machine-readable key (required).
        description: Optional description.
        status: Initial status (defaults to disabled).
        tags: Tags for organization (required by API, defaults to empty list).
        context: Flag context identifier (required by API, defaults
            to ``"distinct_id"``).
        serving_method: How flag values are delivered (required by API,
            defaults to ``ServingMethod.CLIENT``).
        ruleset: Ruleset with ``variants`` and ``rollout`` keys
            (required by API, defaults to a simple On/Off toggle).

    Example:
        ```python
        params = CreateFeatureFlagParams(name="Dark Mode", key="dark_mode")
        data = params.model_dump(exclude_none=True)
        ```
    """

    name: str
    """Flag name (required)."""

    key: str
    """Unique machine-readable key (required)."""

    description: str | None = None
    """Optional description."""

    status: FeatureFlagStatus | None = None
    """Initial status (defaults to disabled)."""

    tags: list[str] = Field(default_factory=list)
    """Tags for organization (required by API, defaults to empty list)."""

    context: str = "distinct_id"
    """Flag context identifier (required by API)."""

    serving_method: ServingMethod = ServingMethod.CLIENT
    """How flag values are delivered (required by API)."""

    ruleset: dict[str, Any] = Field(
        default_factory=lambda: {
            "variants": [
                {
                    "key": "On",
                    "value": True,
                    "is_control": False,
                    "split": 1.0,
                    "is_sticky": False,
                },
                {
                    "key": "Off",
                    "value": False,
                    "is_control": True,
                    "split": 0.0,
                    "is_sticky": False,
                },
            ],
            "rollout": [],
        }
    )
    """Ruleset with variants and rollout (required by API)."""


class UpdateFeatureFlagParams(BaseModel):
    """Parameters for updating an existing feature flag (PUT semantics).

    All required fields must always be provided since this performs a
    full replacement, not a partial update. The API requires ``tags``,
    ``context``, and ``serving_method`` in addition to ``name``, ``key``,
    ``status``, and ``ruleset``.

    Attributes:
        name: Flag name (required).
        key: Unique key (required).
        status: Target status (required).
        ruleset: Complete ruleset — replaces existing (required).
        description: Optional description.
        tags: Tags for organization (required by API, defaults to empty list).
        context: Flag context identifier (required by API, defaults
            to ``"distinct_id"``).
        serving_method: How flag values are delivered (required by API,
            defaults to ``ServingMethod.CLIENT``).

    Example:
        ```python
        params = UpdateFeatureFlagParams(
            name="Dark Mode",
            key="dark_mode",
            status=FeatureFlagStatus.ENABLED,
            ruleset={"variants": [], "rollout": []},
        )
        ```
    """

    name: str
    """Flag name (required)."""

    key: str
    """Unique key (required)."""

    status: FeatureFlagStatus
    """Target status (required)."""

    ruleset: dict[str, Any]
    """Complete ruleset — replaces existing (required)."""

    description: str | None = None
    """Optional description."""

    tags: list[str] = Field(default_factory=list)
    """Tags for organization (required by API, defaults to empty list)."""

    context: str = "distinct_id"
    """Flag context identifier (required by API)."""

    serving_method: ServingMethod = ServingMethod.CLIENT
    """How flag values are delivered (required by API)."""


class SetTestUsersParams(BaseModel):
    """Parameters for setting test user variant overrides on a flag.

    Attributes:
        users: Mapping of variant keys to user distinct IDs.

    Example:
        ```python
        params = SetTestUsersParams(users={"on": "user-1", "off": "user-2"})
        ```
    """

    users: dict[str, str]
    """Mapping of variant keys to user distinct IDs."""


class FlagHistoryParams(BaseModel):
    """Parameters for querying feature flag change history.

    Attributes:
        page: Pagination cursor.
        page_size: Results per page.

    Example:
        ```python
        params = FlagHistoryParams(page_size=50)
        ```
    """

    page: str | None = None
    """Pagination cursor."""

    page_size: int | None = None
    """Results per page."""


class FlagHistoryResponse(BaseModel):
    """Paginated change history for a feature flag.

    Attributes:
        events: Array of event arrays.
        count: Total number of events.

    Example:
        ```python
        response = FlagHistoryResponse(events=[[1, "change"]], count=1)
        assert response.count == 1
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    events: list[list[Any]]
    """Array of event arrays."""

    count: int
    """Total number of events."""


class FlagLimitsResponse(BaseModel):
    """Account-level feature flag usage and limits.

    Attributes:
        limit: Maximum allowed flags.
        is_trial: Whether account is on trial.
        current_usage: Current number of flags.
        contract_status: Contract status.

    Example:
        ```python
        limits = FlagLimitsResponse(
            limit=100, is_trial=False, current_usage=42,
            contract_status=FlagContractStatus.ACTIVE,
        )
        assert limits.current_usage == 42
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    limit: int
    """Maximum allowed flags."""

    is_trial: bool
    """Whether account is on trial."""

    current_usage: int
    """Current number of flags."""

    contract_status: FlagContractStatus
    """Contract status."""


class Experiment(BaseModel):
    """A Mixpanel A/B experiment as returned by the App API.

    Represents the full experiment entity including lifecycle state,
    variants, metrics, and metadata. Extra fields from API evolution
    are preserved via ``extra="allow"``.

    Attributes:
        id: Unique identifier (UUID).
        name: Human-readable name.
        description: Optional description.
        hypothesis: Experiment hypothesis.
        status: Current lifecycle status.
        variants: Variant configuration.
        metrics: Success metrics.
        settings: Experiment settings.
        exposures_cache: Cached exposure data.
        results_cache: Cached result data.
        start_date: ISO 8601 start date.
        end_date: ISO 8601 end date.
        created: ISO 8601 creation timestamp.
        updated: ISO 8601 last-updated timestamp.
        creator: Creator metadata.
        feature_flag: Linked feature flag data.
        is_favorited: Whether current user has favorited.
        pinned_date: Date experiment was pinned.
        tags: Tags for organization.
        can_edit: Permission: can current user edit.
        last_modified_by_id: Last modifier's user ID.
        last_modified_by_name: Last modifier's display name.
        last_modified_by_email: Last modifier's email.

    Example:
        ```python
        exp = Experiment(id="xyz-456", name="Checkout Flow Test")
        assert exp.name == "Checkout Flow Test"
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow", populate_by_name=True)

    id: str
    """Unique identifier (UUID)."""

    name: str
    """Human-readable name."""

    description: str | None = None
    """Optional description."""

    hypothesis: str | None = None
    """Experiment hypothesis."""

    status: ExperimentStatus | None = None
    """Current lifecycle status."""

    variants: list[Any] | dict[str, Any] | None = None
    """Variant configuration (list from API, may also be dict)."""

    metrics: list[Any] | dict[str, Any] | None = None
    """Success metrics (list from API, may also be dict)."""

    settings: dict[str, Any] | None = None
    """Experiment settings."""

    exposures_cache: dict[str, Any] | None = None
    """Cached exposure data."""

    results_cache: dict[str, Any] | None = None
    """Cached result data."""

    start_date: str | None = None
    """ISO 8601 start date."""

    end_date: str | None = None
    """ISO 8601 end date."""

    created: str | None = None
    """ISO 8601 creation timestamp."""

    updated: str | None = None
    """ISO 8601 last-updated timestamp."""

    creator: ExperimentCreator | None = None
    """Creator metadata."""

    feature_flag: dict[str, Any] | None = None
    """Linked feature flag data."""

    is_favorited: bool | None = None
    """Whether current user has favorited."""

    pinned_date: str | None = None
    """Date experiment was pinned."""

    tags: list[str] | None = None
    """Tags for organization."""

    can_edit: bool | None = None
    """Permission: can current user edit."""

    last_modified_by_id: int | None = None
    """Last modifier's user ID."""

    last_modified_by_name: str | None = None
    """Last modifier's display name."""

    last_modified_by_email: str | None = None
    """Last modifier's email."""


class CreateExperimentParams(BaseModel):
    """Parameters for creating a new experiment.

    Attributes:
        name: Experiment name (required).
        description: Optional description.
        hypothesis: Experiment hypothesis.
        settings: Experiment settings.
        access_type: Access control type.
        can_edit: Edit permission.

    Example:
        ```python
        params = CreateExperimentParams(name="Checkout Flow Test")
        data = params.model_dump(exclude_none=True)
        # {"name": "Checkout Flow Test"}
        ```
    """

    name: str
    """Experiment name (required)."""

    description: str | None = None
    """Optional description."""

    hypothesis: str | None = None
    """Experiment hypothesis."""

    settings: dict[str, Any] | None = None
    """Experiment settings."""

    access_type: str | None = None
    """Access control type."""

    can_edit: bool | None = None
    """Edit permission."""


class UpdateExperimentParams(BaseModel):
    """Parameters for updating an existing experiment (PATCH semantics).

    All fields optional — only provided fields are updated.

    Attributes:
        name: Updated name.
        description: Updated description.
        hypothesis: Updated hypothesis.
        variants: Updated variant config.
        metrics: Updated metrics.
        settings: Updated settings.
        start_date: Updated start date.
        end_date: Updated end date.
        tags: Updated tags.
        exposures_cache: Updated exposures cache.
        results_cache: Updated results cache.
        status: Updated status.
        global_access_type: Updated access type.

    Example:
        ```python
        params = UpdateExperimentParams(description="Updated")
        data = params.model_dump(exclude_none=True)
        # {"description": "Updated"}
        ```
    """

    name: str | None = None
    """Updated name."""

    description: str | None = None
    """Updated description."""

    hypothesis: str | None = None
    """Updated hypothesis."""

    variants: list[Any] | dict[str, Any] | None = None
    """Updated variant config (list or dict)."""

    metrics: list[Any] | dict[str, Any] | None = None
    """Updated metrics (list or dict)."""

    settings: dict[str, Any] | None = None
    """Updated settings."""

    start_date: str | None = None
    """Updated start date."""

    end_date: str | None = None
    """Updated end date."""

    tags: list[str] | None = None
    """Updated tags."""

    exposures_cache: dict[str, Any] | None = None
    """Updated exposures cache."""

    results_cache: dict[str, Any] | None = None
    """Updated results cache."""

    status: ExperimentStatus | None = None
    """Updated status."""

    global_access_type: str | None = None
    """Updated access type."""


class ExperimentConcludeParams(BaseModel):
    """Parameters for concluding an experiment.

    Attributes:
        end_date: Override end date (ISO 8601).

    Example:
        ```python
        params = ExperimentConcludeParams(end_date="2026-04-01")
        ```
    """

    end_date: str | None = None
    """Override end date (ISO 8601)."""


class ExperimentDecideParams(BaseModel):
    """Parameters for recording an experiment decision.

    Attributes:
        success: Whether the experiment succeeded (required).
        variant: Winning variant key.
        message: Decision summary message.

    Example:
        ```python
        params = ExperimentDecideParams(success=True, variant="simplified")
        ```
    """

    success: bool
    """Whether the experiment succeeded (required)."""

    variant: str | None = None
    """Winning variant key."""

    message: str | None = None
    """Decision summary message."""


class DuplicateExperimentParams(BaseModel):
    """Parameters for duplicating an experiment.

    Attributes:
        name: Name for the duplicated experiment (required).

    Example:
        ```python
        params = DuplicateExperimentParams(name="Checkout Flow Test v2")
        ```
    """

    name: str
    """Name for the duplicated experiment (required)."""


# =============================================================================
# Operational Tooling — Annotations (Phase 026)
# =============================================================================


class AnnotationUser(BaseModel):
    """Nested user info for annotation creator.

    Attributes:
        id: User ID.
        first_name: First name.
        last_name: Last name.

    Example:
        ```python
        user = AnnotationUser(id=1, first_name="Alice", last_name="Smith")
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int
    """User ID."""

    first_name: str
    """First name."""

    last_name: str
    """Last name."""


class AnnotationTag(BaseModel):
    """Annotation tag for categorization.

    Attributes:
        id: Tag ID.
        name: Tag name.
        project_id: Project ID.
        has_annotations: Whether tag has annotations.

    Example:
        ```python
        tag = AnnotationTag(id=1, name="releases")
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int
    """Tag ID."""

    name: str
    """Tag name."""

    project_id: int | None = None
    """Project ID."""

    has_annotations: bool | None = None
    """Whether tag has annotations."""


class Annotation(BaseModel):
    """Response model for a timeline annotation.

    Attributes:
        id: Annotation ID.
        project_id: Project ID.
        date: Annotation date (ISO format).
        description: Annotation text.
        user: Creator user info.
        tags: Associated tags.

    Example:
        ```python
        annotation = Annotation.model_validate(api_response)
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int
    """Annotation ID."""

    project_id: int
    """Project ID."""

    date: str
    """Annotation date (``%Y-%m-%d %H:%M:%S`` format)."""

    description: str
    """Annotation text."""

    user: AnnotationUser | None = None
    """Creator user info."""

    tags: list[AnnotationTag] = Field(default_factory=list)
    """Associated tags."""


class CreateAnnotationParams(BaseModel):
    """Parameters for creating a new annotation.

    Attributes:
        date: Date string in ``%Y-%m-%d %H:%M:%S`` format (required).
        description: Annotation text (max 512 characters, required).
        tags: Tag IDs to associate.
        user_id: Creator user ID.

    Example:
        ```python
        params = CreateAnnotationParams(
            date="2026-03-31 00:00:00", description="v2.5 release"
        )
        ```
    """

    date: str
    """Date string in ``%Y-%m-%d %H:%M:%S`` format."""

    description: str = Field(max_length=512)
    """Annotation text (max 512 characters)."""

    tags: list[int] | None = None
    """Tag IDs to associate."""

    user_id: int | None = None
    """Creator user ID."""


class UpdateAnnotationParams(BaseModel):
    """Parameters for updating an annotation (PATCH semantics).

    Only ``description`` and ``tags`` can be changed after creation;
    the annotation date is immutable.

    Attributes:
        description: New description (max 512 characters).
        tags: New tag IDs.

    Example:
        ```python
        params = UpdateAnnotationParams(description="Updated text")
        ```
    """

    description: str | None = Field(default=None, max_length=512)
    """New description (max 512 characters)."""

    tags: list[int] | None = None
    """New tag IDs."""


class CreateAnnotationTagParams(BaseModel):
    """Parameters for creating an annotation tag.

    Attributes:
        name: Tag name (required).

    Example:
        ```python
        params = CreateAnnotationTagParams(name="releases")
        ```
    """

    name: str
    """Tag name."""


# =============================================================================
# Operational Tooling — Webhooks (Phase 026)
# =============================================================================


class WebhookAuthType(str, Enum):
    """Authentication type for webhooks.

    Values:
        BASIC: HTTP Basic authentication.
    """

    BASIC = "basic"


class ProjectWebhook(BaseModel):
    """Response model for a project webhook.

    Attributes:
        id: Webhook ID (UUID string).
        name: Webhook name.
        url: Webhook URL.
        is_enabled: Whether enabled.
        auth_type: Authentication type.
        created: Creation timestamp.
        modified: Last modified timestamp.
        creator_id: Creator user ID.
        creator_name: Creator name.

    Example:
        ```python
        webhook = ProjectWebhook.model_validate(api_response)
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: str
    """Webhook ID (UUID string)."""

    name: str
    """Webhook name."""

    url: str
    """Webhook URL."""

    is_enabled: bool
    """Whether enabled."""

    auth_type: WebhookAuthType | None = None
    """Authentication type."""

    created: str | None = None
    """Creation timestamp."""

    modified: str | None = None
    """Last modified timestamp."""

    creator_id: int | None = None
    """Creator user ID."""

    creator_name: str | None = None
    """Creator name."""


class CreateWebhookParams(BaseModel):
    """Parameters for creating a webhook.

    Attributes:
        name: Webhook name (required).
        url: Webhook URL (required).
        auth_type: Auth type ("basic" or None).
        username: Basic auth username.
        password: Basic auth password.

    Example:
        ```python
        params = CreateWebhookParams(
            name="Pipeline webhook",
            url="https://example.com/webhook",
        )
        ```
    """

    name: str
    """Webhook name."""

    url: str
    """Webhook URL."""

    auth_type: WebhookAuthType | None = None
    """Auth type (e.g. WebhookAuthType.BASIC)."""

    username: str | None = None
    """Basic auth username."""

    password: str | None = None
    """Basic auth password."""


class UpdateWebhookParams(BaseModel):
    """Parameters for updating a webhook (PATCH semantics).

    Attributes:
        name: New name.
        url: New URL.
        auth_type: New auth type.
        username: New username.
        password: New password.
        is_enabled: New enabled state.

    Example:
        ```python
        params = UpdateWebhookParams(name="Updated name")
        ```
    """

    name: str | None = None
    """New name."""

    url: str | None = None
    """New URL."""

    auth_type: WebhookAuthType | None = None
    """New auth type."""

    username: str | None = None
    """New username."""

    password: str | None = None
    """New password."""

    is_enabled: bool | None = None
    """New enabled state."""


class WebhookTestParams(BaseModel):
    """Parameters for testing webhook connectivity.

    Attributes:
        url: URL to test (required).
        name: Webhook name.
        auth_type: Auth type.
        username: Username for auth.
        password: Password for auth.

    Example:
        ```python
        params = WebhookTestParams(url="https://example.com/webhook")
        ```
    """

    url: str
    """URL to test."""

    name: str | None = None
    """Webhook name."""

    auth_type: WebhookAuthType | None = None
    """Auth type."""

    username: str | None = None
    """Username for auth."""

    password: str | None = None
    """Password for auth."""


class WebhookTestResult(BaseModel):
    """Response model for webhook connectivity test.

    Attributes:
        success: Whether test succeeded.
        status_code: HTTP status code.
        message: Descriptive message.

    Example:
        ```python
        result = WebhookTestResult.model_validate(api_response)
        if result.success:
            print("Webhook is reachable")
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    success: bool
    """Whether test succeeded."""

    status_code: int
    """HTTP status code."""

    message: str
    """Descriptive message."""


class WebhookMutationResult(BaseModel):
    """Response model for webhook create/update (returns id + name only).

    Attributes:
        id: Webhook ID.
        name: Webhook name.

    Example:
        ```python
        result = WebhookMutationResult.model_validate(api_response)
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: str
    """Webhook ID."""

    name: str
    """Webhook name."""


# =============================================================================
# Operational Tooling — Alerts (Phase 026)
# =============================================================================


class AlertFrequencyPreset(int, Enum):
    """Preset frequency values for alert check intervals.

    Values:
        HOURLY: Check every hour (3600 seconds).
        DAILY: Check every day (86400 seconds).
        WEEKLY: Check every week (604800 seconds).
    """

    HOURLY = 3600
    DAILY = 86400
    WEEKLY = 604800


class AlertBookmark(BaseModel):
    """Nested bookmark info for an alert.

    Attributes:
        id: Bookmark ID.
        name: Bookmark name.
        type: Bookmark type.

    Example:
        ```python
        bookmark = AlertBookmark(id=1, name="Daily Signups")
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int
    """Bookmark ID."""

    name: str | None = None
    """Bookmark name."""

    type: str | None = None
    """Bookmark type."""


class AlertCreator(BaseModel):
    """Nested creator info for an alert.

    Attributes:
        id: User ID.
        first_name: First name.
        last_name: Last name.
        email: Email.

    Example:
        ```python
        creator = AlertCreator(id=1, email="alice@example.com")
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int
    """User ID."""

    first_name: str | None = None
    """First name."""

    last_name: str | None = None
    """Last name."""

    email: str | None = None
    """Email."""


class AlertWorkspace(BaseModel):
    """Nested workspace info for an alert.

    Attributes:
        id: Workspace ID.
        name: Workspace name.

    Example:
        ```python
        ws = AlertWorkspace(id=100, name="Production")
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int
    """Workspace ID."""

    name: str | None = None
    """Workspace name."""


class AlertProject(BaseModel):
    """Nested project info for an alert.

    Attributes:
        id: Project ID.
        name: Project name.

    Example:
        ```python
        proj = AlertProject(id=12345, name="My App")
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int
    """Project ID."""

    name: str | None = None
    """Project name."""


class CustomAlert(BaseModel):
    """Response model for a custom alert.

    Attributes:
        id: Alert ID.
        name: Alert name.
        bookmark: Linked saved report.
        condition: Trigger condition (opaque JSON).
        frequency: Check frequency in seconds.
        paused: Whether alert is paused.
        subscriptions: Notification targets.
        notification_windows: Notification window config.
        creator: Creator user info.
        workspace: Workspace metadata.
        project: Project metadata.
        created: Creation timestamp.
        modified: Last modified timestamp.
        last_checked: Last check timestamp.
        last_fired: Last trigger timestamp.
        valid: Whether alert is valid.
        results: Latest evaluation results.

    Example:
        ```python
        alert = CustomAlert.model_validate(api_response)
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int
    """Alert ID."""

    name: str
    """Alert name."""

    bookmark: AlertBookmark | None = None
    """Linked saved report."""

    condition: dict[str, Any] = Field(default_factory=dict)
    """Trigger condition (opaque JSON)."""

    frequency: int = 0
    """Check frequency in seconds."""

    paused: bool = False
    """Whether alert is paused."""

    subscriptions: list[dict[str, Any]] = Field(default_factory=list)
    """Notification targets."""

    notification_windows: dict[str, Any] | None = None
    """Notification window config."""

    creator: AlertCreator | None = None
    """Creator user info."""

    workspace: AlertWorkspace | None = None
    """Workspace metadata."""

    project: AlertProject | None = None
    """Project metadata."""

    created: str = ""
    """Creation timestamp."""

    modified: str = ""
    """Last modified timestamp."""

    last_checked: str | None = None
    """Last check timestamp."""

    last_fired: str | None = None
    """Last trigger timestamp."""

    valid: bool = True
    """Whether alert is valid."""

    results: dict[str, Any] | None = None
    """Latest evaluation results."""


class CreateAlertParams(BaseModel):
    """Parameters for creating a new alert.

    Attributes:
        bookmark_id: ID of linked bookmark (required).
        name: Alert name (required).
        condition: Trigger condition JSON (required).
        frequency: Check frequency in seconds (required).
        paused: Start paused or active (required).
        subscriptions: Notification targets (required).
        notification_windows: Notification window config.

    Example:
        ```python
        params = CreateAlertParams(
            bookmark_id=12345,
            name="Daily signups drop",
            condition={
                "keys": [{"header": "Signup", "value": "Signup"}],
                "type": "absolute",
                "op": "<",
                "value": 100,
            },
            frequency=AlertFrequencyPreset.DAILY,
            paused=False,
            subscriptions=[{"type": "email", "value": "team@example.com"}],
        )
        ```
    """

    bookmark_id: int
    """ID of linked bookmark."""

    name: str = Field(max_length=50)
    """Alert name (max 50 characters)."""

    condition: dict[str, Any]
    """Trigger condition JSON."""

    frequency: int
    """Check frequency in seconds. See ``AlertFrequencyPreset`` for common values."""

    paused: bool
    """Start paused or active."""

    subscriptions: list[dict[str, Any]]
    """Notification targets."""

    notification_windows: dict[str, Any] | None = None
    """Notification window config."""


class UpdateAlertParams(BaseModel):
    """Parameters for updating an alert (PATCH semantics).

    Attributes:
        name: New name.
        bookmark_id: New bookmark ID.
        condition: New condition.
        frequency: New frequency.
        paused: New pause state.
        subscriptions: New subscriptions.
        notification_windows: New notification windows.

    Example:
        ```python
        params = UpdateAlertParams(name="Updated alert", paused=True)
        ```
    """

    name: str | None = None
    """New name."""

    bookmark_id: int | None = None
    """New bookmark ID."""

    condition: dict[str, Any] | None = None
    """New condition."""

    frequency: int | None = None
    """New frequency."""

    paused: bool | None = None
    """New pause state."""

    subscriptions: list[dict[str, Any]] | None = None
    """New subscriptions."""

    notification_windows: dict[str, Any] | None = None
    """New notification windows."""


class AlertCount(BaseModel):
    """Response model for alert count and limits.

    Attributes:
        anomaly_alerts_count: Current alert count.
        alert_limit: Account limit.
        is_below_limit: Whether below limit.

    Example:
        ```python
        count = AlertCount.model_validate(api_response)
        if count.is_below_limit:
            print(f"{count.anomaly_alerts_count}/{count.alert_limit}")
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    anomaly_alerts_count: int
    """Current alert count."""

    alert_limit: int
    """Account limit."""

    is_below_limit: bool
    """Whether below limit."""


class AlertHistoryPagination(BaseModel):
    """Pagination metadata for alert history.

    Attributes:
        next_cursor: Next page cursor.
        previous_cursor: Previous page cursor.
        page_size: Page size.

    Example:
        ```python
        pagination = AlertHistoryPagination(page_size=20)
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    next_cursor: str | None = None
    """Next page cursor."""

    previous_cursor: str | None = None
    """Previous page cursor."""

    page_size: int = 20
    """Page size."""


class AlertHistoryResponse(BaseModel):
    """Response model for alert history (paginated).

    Attributes:
        results: History entries.
        pagination: Pagination metadata.

    Example:
        ```python
        history = AlertHistoryResponse.model_validate(api_response)
        for entry in history.results:
            print(entry)
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    results: list[dict[str, Any]] = Field(default_factory=list)
    """History entries."""

    pagination: AlertHistoryPagination | None = None
    """Pagination metadata."""


class AlertScreenshotResponse(BaseModel):
    """Response model for alert screenshot URL.

    Attributes:
        signed_url: Signed GCS URL for screenshot.

    Example:
        ```python
        resp = AlertScreenshotResponse.model_validate(api_response)
        print(resp.signed_url)
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    signed_url: str
    """Signed GCS URL for screenshot."""


class AlertValidation(BaseModel):
    """Per-alert validation result.

    Attributes:
        alert_id: Alert ID.
        alert_name: Alert name.
        valid: Whether valid.
        reason: Reason if invalid.

    Example:
        ```python
        v = AlertValidation(alert_id=1, alert_name="Test", valid=True)
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    alert_id: int
    """Alert ID."""

    alert_name: str
    """Alert name."""

    valid: bool
    """Whether valid."""

    reason: str | None = None
    """Reason if invalid."""


class ValidateAlertsForBookmarkParams(BaseModel):
    """Parameters for validating alerts against a bookmark.

    Attributes:
        alert_ids: Alert IDs to validate (required).
        bookmark_type: Bookmark type to validate against (required).
        bookmark_params: Bookmark params JSON (required).

    Example:
        ```python
        params = ValidateAlertsForBookmarkParams(
            alert_ids=[1, 2],
            bookmark_type="insights",
            bookmark_params={"event": "Signup"},
        )
        ```
    """

    alert_ids: list[int] = Field(min_length=1)
    """Alert IDs to validate (must not be empty)."""

    bookmark_type: Literal["insights", "funnels"]
    """Bookmark type to validate against."""

    bookmark_params: dict[str, Any]
    """Bookmark params JSON."""


class ValidateAlertsForBookmarkResponse(BaseModel):
    """Response model for alert-bookmark validation.

    Attributes:
        alert_validations: Per-alert validation results.
        invalid_count: Count of invalid alerts.

    Example:
        ```python
        resp = ValidateAlertsForBookmarkResponse.model_validate(api_response)
        if resp.invalid_count > 0:
            for v in resp.alert_validations:
                if not v.valid:
                    print(f"{v.alert_name}: {v.reason}")
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    alert_validations: list[AlertValidation] = Field(default_factory=list)
    """Per-alert validation results."""

    invalid_count: int = 0
    """Count of invalid alerts."""


# =============================================================================
# Data Governance — Data Definitions / Lexicon (Phase 027)
# =============================================================================


class PropertyResourceType(str, Enum):
    """Resource type for property definitions.

    Values:
        EVENT: Event property.
        USER: User profile property.
        GROUPPROFILE: Group profile property (wire format: ``groupprofile``).
    """

    EVENT = "event"
    USER = "user"
    GROUPPROFILE = "groupprofile"


class EventDefinition(BaseModel):
    """A Mixpanel event definition from the Lexicon.

    Attributes:
        id: Server-assigned event ID.
        name: Event name (unique identifier).
        display_name: Human-readable name.
        description: Event description.
        hidden: Whether hidden from UI.
        dropped: Whether data is dropped at ingestion.
        merged: Whether merged into another event.
        verified: Whether verified by governance team.
        tags: Assigned tag names.
        custom_event_id: Links to custom event.
        last_modified: ISO 8601 timestamp.
        status: Event status.
        platforms: Tracking platforms.
        created_utc: ISO 8601 creation timestamp.
        modified_utc: ISO 8601 modification timestamp.

    Example:
        ```python
        ev = EventDefinition(id=1, name="Purchase")
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    id: int
    """Server-assigned event ID."""

    name: str
    """Event name (unique identifier)."""

    display_name: str | None = None
    """Human-readable name."""

    description: str | None = None
    """Event description."""

    hidden: bool | None = None
    """Whether hidden from UI."""

    dropped: bool | None = None
    """Whether data is dropped at ingestion."""

    merged: bool | None = None
    """Whether merged into another event."""

    verified: bool | None = None
    """Whether verified by governance team."""

    tags: list[str] | None = None
    """Assigned tag names."""

    custom_event_id: int | None = None
    """Links to custom event."""

    last_modified: str | None = None
    """ISO 8601 timestamp."""

    status: str | None = None
    """Event status."""

    platforms: list[str] | None = None
    """Tracking platforms."""

    created_utc: str | None = None
    """ISO 8601 creation timestamp."""

    modified_utc: str | None = None
    """ISO 8601 modification timestamp."""


class PropertyDefinition(BaseModel):
    """A Mixpanel property definition from the Lexicon.

    Attributes:
        id: Server-assigned property ID.
        name: Property name.
        resource_type: Property resource type (event, user, groupprofile).
        description: Property description.
        hidden: Whether hidden from UI.
        dropped: Whether data is dropped.
        merged: Whether merged into another property.
        sensitive: PII flag.
        data_group_id: Data group identifier.

    Example:
        ```python
        prop = PropertyDefinition(id=1, name="$browser")
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    id: int | None = None
    """Server-assigned property ID (may be absent for custom properties)."""

    name: str
    """Property name."""

    resource_type: str | None = None
    """Property resource type (event, user, groupprofile)."""

    description: str | None = None
    """Property description."""

    hidden: bool | None = None
    """Whether hidden from UI."""

    dropped: bool | None = None
    """Whether data is dropped."""

    merged: bool | None = None
    """Whether merged into another property."""

    sensitive: bool | None = None
    """PII flag."""

    data_group_id: str | None = None
    """Data group identifier."""


class UpdateEventDefinitionParams(BaseModel):
    """Parameters for updating an event definition (PATCH semantics).

    All fields are optional; only set fields are sent.

    Attributes:
        hidden: Whether hidden from UI.
        dropped: Whether data is dropped.
        merged: Whether merged.
        verified: Whether verified.
        tags: Tag names to assign.
        description: Event description.

    Example:
        ```python
        params = UpdateEventDefinitionParams(
            description="User completed a purchase", verified=True
        )
        ```
    """

    hidden: bool | None = None
    """Whether hidden from UI."""

    dropped: bool | None = None
    """Whether data is dropped."""

    merged: bool | None = None
    """Whether merged."""

    verified: bool | None = None
    """Whether verified."""

    tags: list[str] | None = None
    """Tag names to assign."""

    description: str | None = None
    """Event description."""


class UpdatePropertyDefinitionParams(BaseModel):
    """Parameters for updating a property definition (PATCH semantics).

    All fields are optional; only set fields are sent.

    Attributes:
        hidden: Whether hidden from UI.
        dropped: Whether data is dropped.
        merged: Whether merged.
        sensitive: PII flag.
        description: Property description.

    Example:
        ```python
        params = UpdatePropertyDefinitionParams(sensitive=True)
        ```
    """

    hidden: bool | None = None
    """Whether hidden from UI."""

    dropped: bool | None = None
    """Whether data is dropped."""

    merged: bool | None = None
    """Whether merged."""

    sensitive: bool | None = None
    """PII flag."""

    description: str | None = None
    """Property description."""


class BulkEventUpdate(BaseModel):
    """A single event update entry for bulk operations.

    Attributes:
        name: Event name (identifier).
        id: Alternative identifier.
        hidden: Whether hidden from UI.
        dropped: Whether data is dropped.
        merged: Whether merged.
        verified: Whether verified.
        tags: Tag names.
        contacts: Contact emails.
        team_contacts: Team contact emails.

    Example:
        ```python
        entry = BulkEventUpdate(name="OldEvent", hidden=True)
        ```
    """

    name: str | None = None
    """Event name (identifier)."""

    id: int | None = None
    """Alternative identifier."""

    hidden: bool | None = None
    """Whether hidden from UI."""

    dropped: bool | None = None
    """Whether data is dropped."""

    merged: bool | None = None
    """Whether merged."""

    verified: bool | None = None
    """Whether verified."""

    tags: list[str] | None = None
    """Tag names."""

    contacts: list[str] | None = None
    """Contact emails."""

    team_contacts: list[str] | None = None
    """Team contact emails."""


class BulkUpdateEventsParams(BaseModel):
    """Parameters for bulk-updating event definitions.

    Attributes:
        events: List of event update entries (required).

    Example:
        ```python
        params = BulkUpdateEventsParams(
            events=[BulkEventUpdate(name="E1", hidden=True)]
        )
        ```
    """

    events: list[BulkEventUpdate]
    """List of event update entries."""


class BulkPropertyUpdate(BaseModel):
    """A single property update entry for bulk operations.

    Uses camelCase serialization to match the Django API contract.

    Attributes:
        name: Property name (required).
        resource_type: Resource type (required).
        id: Property ID.
        hidden: Whether hidden from UI.
        dropped: Whether data is dropped.
        sensitive: PII flag.
        data_group_id: Data group identifier.

    Example:
        ```python
        entry = BulkPropertyUpdate(name="$browser", resource_type="event")
        ```
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str
    """Property name."""

    resource_type: str
    """Resource type (event, user, groupprofile)."""

    id: int | None = None
    """Property ID."""

    hidden: bool | None = None
    """Whether hidden from UI."""

    dropped: bool | None = None
    """Whether data is dropped."""

    sensitive: bool | None = None
    """PII flag."""

    data_group_id: str | None = None
    """Data group identifier."""


class BulkUpdatePropertiesParams(BaseModel):
    """Parameters for bulk-updating property definitions.

    Attributes:
        properties: List of property update entries (required).

    Example:
        ```python
        params = BulkUpdatePropertiesParams(
            properties=[BulkPropertyUpdate(name="$browser", resource_type="event")]
        )
        ```
    """

    properties: list[BulkPropertyUpdate]
    """List of property update entries."""


class LexiconTag(BaseModel):
    """A Lexicon tag for categorizing event/property definitions.

    Attributes:
        id: Server-assigned tag ID.
        name: Tag name.

    Example:
        ```python
        tag = LexiconTag(id=1, name="core-metrics")
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    id: int
    """Server-assigned tag ID."""

    name: str
    """Tag name."""


class CreateTagParams(BaseModel):
    """Parameters for creating a Lexicon tag.

    Attributes:
        name: Tag name (required, non-empty).

    Example:
        ```python
        params = CreateTagParams(name="core-metrics")
        ```
    """

    name: str
    """Tag name."""


class UpdateTagParams(BaseModel):
    """Parameters for updating a Lexicon tag.

    Attributes:
        name: New tag name.

    Example:
        ```python
        params = UpdateTagParams(name="key-metrics")
        ```
    """

    name: str | None = None
    """New tag name."""


# =============================================================================
# Data Governance — Drop Filters (Phase 027)
# =============================================================================


class DropFilter(BaseModel):
    """A drop filter for discarding events at ingestion.

    Attributes:
        id: Server-assigned filter ID.
        event_name: Event name to filter.
        filters: Filter condition JSON.
        active: Whether the filter is active.
        display_name: Human-readable name.
        created: ISO 8601 creation timestamp.

    Example:
        ```python
        df = DropFilter(id=1, event_name="debug_log")
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    id: int
    """Server-assigned filter ID."""

    event_name: str
    """Event name to filter."""

    filters: list[Any] | None = None
    """Filter condition JSON."""

    active: bool | None = None
    """Whether the filter is active."""

    display_name: str | None = None
    """Human-readable name."""

    created: str | None = None
    """ISO 8601 creation timestamp."""


class CreateDropFilterParams(BaseModel):
    """Parameters for creating a drop filter.

    Attributes:
        event_name: Event name to filter (required).
        filters: Filter condition JSON (required).

    Example:
        ```python
        params = CreateDropFilterParams(
            event_name="debug_log",
            filters={"property": "env", "operator": "equals", "value": "test"},
        )
        ```
    """

    event_name: str
    """Event name to filter."""

    filters: Any  # Any justified: API accepts polymorphic filter JSON
    """Filter condition JSON."""


class UpdateDropFilterParams(BaseModel):
    """Parameters for updating a drop filter.

    Attributes:
        id: Drop filter ID (required).
        event_name: New event name.
        filters: New filter condition JSON.
        active: Whether the filter is active.

    Example:
        ```python
        params = UpdateDropFilterParams(id=123, active=False)
        ```
    """

    id: int
    """Drop filter ID."""

    event_name: str | None = None
    """New event name."""

    filters: Any | None = None  # Any justified: API accepts polymorphic filter JSON
    """New filter condition JSON."""

    active: bool | None = None
    """Whether the filter is active."""


class DropFilterLimitsResponse(BaseModel):
    """Response model for drop filter limits.

    Attributes:
        filter_limit: Maximum allowed filters.

    Example:
        ```python
        limits = DropFilterLimitsResponse(filter_limit=10)
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    filter_limit: int
    """Maximum allowed filters."""


# =============================================================================
# Data Governance — Custom Properties (Phase 027)
# =============================================================================


class CustomPropertyResourceType(str, Enum):
    """Resource type for custom properties.

    Values:
        EVENTS: Event-level custom property.
        PEOPLE: User profile custom property.
        GROUP_PROFILES: Group profile custom property.
    """

    EVENTS = "events"
    PEOPLE = "people"
    GROUP_PROFILES = "group_profiles"


class ComposedPropertyValue(BaseModel):
    """A composed property reference within a custom property formula.

    Attributes:
        type: Property type.
        type_cast: Type cast instruction.
        resource_type: Resource type (required).
        behavior: Behavior specification.
        join_property_type: Join property type.

    Example:
        ```python
        cpv = ComposedPropertyValue(resource_type="event")
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    type: str | None = None
    """Property type."""

    type_cast: str | None = None
    """Type cast instruction."""

    resource_type: str
    """Resource type."""

    behavior: Any | None = (
        None  # Any justified: API behavior spec varies by resource type
    )
    """Behavior specification."""

    join_property_type: str | None = None
    """Join property type."""


class CustomProperty(BaseModel):
    """A Mixpanel custom property (computed/formula property).

    Attributes:
        custom_property_id: Server-assigned property ID.
        name: Property name.
        description: Property description.
        resource_type: Resource type (events, people, group_profiles).
        property_type: Property type.
        display_formula: Formula expression.
        composed_properties: Referenced properties in formula.
        is_locked: Whether the property is locked.
        is_visible: Whether the property is visible.
        data_group_id: Data group identifier.
        created: ISO 8601 creation timestamp.
        modified: ISO 8601 modification timestamp.
        example_value: Example value.

    Example:
        ```python
        cp = CustomProperty(
            custom_property_id=1, name="Revenue", resource_type="events"
        )
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    custom_property_id: int
    """Server-assigned property ID."""

    name: str
    """Property name."""

    description: str | None = None
    """Property description."""

    resource_type: str
    """Resource type (events, people, group_profiles)."""

    property_type: str | None = None
    """Property type."""

    display_formula: str | None = None
    """Formula expression."""

    composed_properties: dict[str, ComposedPropertyValue] | None = None
    """Referenced properties in formula."""

    is_locked: bool | None = None
    """Whether the property is locked."""

    is_visible: bool | None = None
    """Whether the property is visible."""

    data_group_id: str | None = None
    """Data group identifier."""

    created: str | None = None
    """ISO 8601 creation timestamp."""

    modified: str | None = None
    """ISO 8601 modification timestamp."""

    example_value: str | None = None
    """Example value."""


class CreateCustomPropertyParams(BaseModel):
    """Parameters for creating a custom property.

    Validation rules:
    - ``display_formula`` and ``behavior`` are mutually exclusive.
    - ``behavior`` and ``composed_properties`` are mutually exclusive.
    - ``display_formula`` requires ``composed_properties``.
    - One of ``display_formula`` or ``behavior`` must be set.

    Attributes:
        name: Property name (required).
        resource_type: Resource type (required).
        description: Property description.
        display_formula: Formula expression (mutually exclusive with behavior).
        composed_properties: Referenced properties (required if display_formula set).
        is_locked: Whether the property is locked.
        is_visible: Whether the property is visible.
        data_group_id: Data group identifier.
        behavior: Behavior specification (mutually exclusive with display_formula).

    Example:
        ```python
        params = CreateCustomPropertyParams(
            name="Revenue Per User",
            resource_type="events",
            display_formula='number(properties["amount"])',
            composed_properties={"amount": ComposedPropertyValue(resource_type="event")},
        )
        ```
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str
    """Property name."""

    resource_type: str
    """Resource type (events, people, group_profiles)."""

    description: str | None = None
    """Property description."""

    display_formula: str | None = None
    """Formula expression (mutually exclusive with behavior)."""

    composed_properties: dict[str, ComposedPropertyValue] | None = None
    """Referenced properties (required if display_formula set)."""

    is_locked: bool | None = None
    """Whether the property is locked."""

    is_visible: bool | None = None
    """Whether the property is visible."""

    data_group_id: str | None = None
    """Data group identifier."""

    behavior: Any | None = (
        None  # Any justified: API behavior spec varies by resource type
    )
    """Behavior specification (mutually exclusive with display_formula)."""

    @model_validator(mode="after")
    def _validate_formula_behavior(self) -> CreateCustomPropertyParams:
        """Validate mutual exclusion of display_formula and behavior.

        Returns:
            The validated instance.

        Raises:
            ValueError: If validation rules are violated.
        """
        if self.display_formula is not None and self.behavior is not None:
            msg = "display_formula and behavior are mutually exclusive"
            raise ValueError(msg)

        if self.behavior is not None and self.composed_properties is not None:
            msg = "behavior and composed_properties are mutually exclusive"
            raise ValueError(msg)

        if self.display_formula is not None and self.composed_properties is None:
            msg = "display_formula requires composed_properties"
            raise ValueError(msg)

        if self.display_formula is None and self.behavior is None:
            msg = "one of display_formula or behavior must be set"
            raise ValueError(msg)

        return self


class UpdateCustomPropertyParams(BaseModel):
    """Parameters for updating a custom property (PUT — full replacement).

    Note: ``resource_type`` and ``data_group_id`` are immutable.

    Attributes:
        name: Property name.
        description: Property description.
        display_formula: Formula expression.
        composed_properties: Referenced properties.
        is_locked: Whether the property is locked.
        is_visible: Whether the property is visible.

    Example:
        ```python
        params = UpdateCustomPropertyParams(name="Updated Name")
        ```
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str | None = None
    """Property name."""

    description: str | None = None
    """Property description."""

    display_formula: str | None = None
    """Formula expression."""

    composed_properties: dict[str, ComposedPropertyValue] | None = None
    """Referenced properties."""

    is_locked: bool | None = None
    """Whether the property is locked."""

    is_visible: bool | None = None
    """Whether the property is visible."""


# =============================================================================
# Data Governance — Lookup Tables (Phase 027)
# =============================================================================


class LookupTable(BaseModel):
    """A Mixpanel lookup table.

    Attributes:
        id: Server-assigned table ID.
        name: Table name.
        token: Table token.
        created_at: ISO 8601 creation timestamp.
        last_modified_at: ISO 8601 modification timestamp.
        has_mapped_properties: Whether the table has mapped properties.

    Example:
        ```python
        lt = LookupTable(id=1, name="Product Catalog")
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    id: int
    """Server-assigned table ID."""

    name: str
    """Table name."""

    token: str | None = None
    """Table token."""

    created_at: str | None = None
    """ISO 8601 creation timestamp."""

    last_modified_at: str | None = None
    """ISO 8601 modification timestamp."""

    has_mapped_properties: bool | None = None
    """Whether the table has mapped properties."""


class UploadLookupTableParams(BaseModel):
    """Parameters for uploading a lookup table CSV.

    The upload is a 3-step process handled by the workspace method:
    1. Get a signed upload URL
    2. Upload CSV to signed URL
    3. Register the table

    Attributes:
        name: Table name (1-255 characters, required).
        file_path: Path to local CSV file (required).
        data_group_id: For replacing an existing table.

    Example:
        ```python
        params = UploadLookupTableParams(
            name="Product Catalog", file_path="/path/to/products.csv"
        )
        ```
    """

    name: str = Field(min_length=1, max_length=255)
    """Table name (1-255 characters)."""

    file_path: str
    """Path to local CSV file."""

    data_group_id: int | None = None
    """For replacing an existing table."""


class MarkLookupTableReadyParams(BaseModel):
    """Parameters for marking a lookup table as ready.

    Attributes:
        name: Table name (required).
        key: Primary key column name (required).
        data_group_id: For replacing an existing table.

    Example:
        ```python
        params = MarkLookupTableReadyParams(name="Products", key="product_id")
        ```
    """

    name: str
    """Table name."""

    key: str
    """Primary key column name."""

    data_group_id: int | None = None
    """For replacing an existing table."""


class LookupTableUploadUrl(BaseModel):
    """Response model for lookup table upload URL request.

    Attributes:
        url: Signed GCS upload URL.
        path: GCS path for registration.
        key: Primary key column name.

    Example:
        ```python
        upload = LookupTableUploadUrl(
            url="https://storage.googleapis.com/...",
            path="gs://bucket/path",
            key="id",
        )
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    url: str
    """Signed GCS upload URL."""

    path: str
    """GCS path for registration."""

    key: str
    """Primary key column name."""


class UpdateLookupTableParams(BaseModel):
    """Parameters for updating a lookup table.

    Attributes:
        name: New table name.

    Example:
        ```python
        params = UpdateLookupTableParams(name="Updated Catalog")
        ```
    """

    name: str | None = None
    """New table name."""


# =============================================================================
# Schema Registry Types (Phase 028)
# =============================================================================


class SchemaEntry(BaseModel):
    """A schema registry entry for an event, custom event, or profile.

    Represents a JSON Schema Draft 7 definition registered in the
    Mixpanel schema registry. Used for both API responses and as entries
    in bulk create/update operations.

    Attributes:
        entity_type: Entity type ("event", "custom_event", "profile").
        name: Entity name (event name or "$user" for profile).
        version: Schema version in YYYY-MM-DD format.
        schema_definition: JSON Schema Draft 7 definition (API field: schemaJson).

    Example:
        ```python
        entry = SchemaEntry(
            entity_type="event",
            name="Purchase",
            schema_definition={"properties": {"amount": {"type": "number"}}},
        )
        # Or using the API alias:
        entry = SchemaEntry(
            entityType="event", name="Purchase",
            schemaJson={"properties": {"amount": {"type": "number"}}},
        )
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    entity_type: str
    """Entity type: "event", "custom_event", or "profile"."""

    name: str
    """Entity name (event name or "$user" for profile)."""

    version: str | None = None
    """Schema version in YYYY-MM-DD format."""

    schema_definition: dict[str, Any] = Field(alias="schemaJson")
    """JSON Schema Draft 7 definition (API field: schemaJson)."""


class BulkCreateSchemasParams(BaseModel):
    """Parameters for bulk-creating schemas in the registry.

    Attributes:
        entries: Schema entries to create.
        truncate: If true, delete all existing schemas of entity_type
            before inserting.
        entity_type: Entity type for all entries (only "event" supported
            for batch operations).

    Example:
        ```python
        params = BulkCreateSchemasParams(
            entries=[
                SchemaEntry(name="Login", entity_type="event", schema_definition={...}),
            ],
            truncate=True,
            entity_type="event",
        )
        ```
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    entries: list[SchemaEntry]
    """Schema entries to create."""

    truncate: bool | None = None
    """If true, delete all existing schemas of entity_type before inserting."""

    entity_type: str | None = None
    """Entity type for all entries (only "event" supported for batch)."""


class BulkCreateSchemasResponse(BaseModel):
    """Response from a bulk schema creation operation.

    Attributes:
        added: Number of schemas added.
        deleted: Number of schemas deleted (from truncate).

    Example:
        ```python
        resp = BulkCreateSchemasResponse(added=5, deleted=3)
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    added: int
    """Number of schemas added."""

    deleted: int
    """Number of schemas deleted (from truncate)."""


class BulkPatchResult(BaseModel):
    """Per-entry result from a bulk schema update operation.

    Attributes:
        entity_type: Entity type processed.
        name: Entity name processed.
        status: Result status ("ok" or "error").
        error: Error message if status is "error".

    Example:
        ```python
        result = BulkPatchResult(
            entity_type="event", name="Login", status="ok"
        )
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    entity_type: str
    """Entity type processed."""

    name: str
    """Entity name processed."""

    status: str
    """Result status ("ok" or "error")."""

    error: str | None = None
    """Error message if status is "error"."""


class DeleteSchemasResponse(BaseModel):
    """Response from a schema deletion operation.

    Attributes:
        delete_count: Number of schemas deleted.

    Example:
        ```python
        resp = DeleteSchemasResponse(delete_count=3)
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    delete_count: int
    """Number of schemas deleted."""


# =============================================================================
# Schema Enforcement Types (Phase 028)
# =============================================================================


class SchemaEnforcementConfig(BaseModel):
    """Schema enforcement configuration for a project.

    Controls how Mixpanel handles events that don't match defined schemas.

    Attributes:
        id: Config ID.
        last_modified: Last modification timestamp.
        last_modified_by: User who last modified.
        rule_event: Enforcement action ("Warn and Accept", "Warn and Hide",
            "Warn and Drop").
        notification_emails: Notification recipients.
        events: Event enforcement rules.
        common_properties: Common property rules.
        user_properties: User property rules.
        initialized_by: User who initialized.
        initialized_from: Initialization start date.
        initialized_to: Initialization end date.
        state: Enforcement state ("planned" or "ingested").

    Example:
        ```python
        config = SchemaEnforcementConfig(
            id=1, rule_event="Warn and Accept", state="ingested"
        )
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    id: int | None = None
    """Config ID."""

    last_modified: str | None = None
    """Last modification timestamp."""

    last_modified_by: dict[str, Any] | None = None
    """User who last modified."""

    rule_event: str | None = None
    """Enforcement action: "Warn and Accept", "Warn and Hide", "Warn and Drop"."""

    notification_emails: list[str] | None = None
    """Notification recipients."""

    events: list[dict[str, Any]] | None = None
    """Event enforcement rules."""

    common_properties: list[dict[str, Any]] | None = None
    """Common property rules."""

    user_properties: list[dict[str, Any]] | None = None
    """User property rules."""

    initialized_by: dict[str, Any] | None = None
    """User who initialized."""

    initialized_from: str | None = None
    """Initialization start date."""

    initialized_to: str | None = None
    """Initialization end date."""

    state: str | None = None
    """Enforcement state ("planned" or "ingested")."""


class InitSchemaEnforcementParams(BaseModel):
    """Parameters for initializing schema enforcement.

    Attributes:
        rule_event: Enforcement action ("Warn and Accept", "Warn and Hide",
            "Warn and Drop").

    Example:
        ```python
        params = InitSchemaEnforcementParams(rule_event="Warn and Accept")
        ```
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    rule_event: str
    """Enforcement action."""


class UpdateSchemaEnforcementParams(BaseModel):
    """Parameters for partially updating schema enforcement.

    Attributes:
        notification_emails: Updated notification recipients.
        rule_event: Updated enforcement action.
        events: Updated event list.
        properties: Updated property map.

    Example:
        ```python
        params = UpdateSchemaEnforcementParams(
            rule_event="Warn and Drop",
            notification_emails=["data-team@example.com"],
        )
        ```
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    notification_emails: list[str] | None = None
    """Updated notification recipients."""

    rule_event: str | None = None
    """Updated enforcement action."""

    events: list[str] | None = None
    """Updated event list."""

    properties: dict[str, list[str]] | None = None
    """Updated property map."""


class ReplaceSchemaEnforcementParams(BaseModel):
    """Parameters for fully replacing schema enforcement configuration.

    All fields are required since this is a full replacement.

    Attributes:
        common_properties: Full common property rules.
        user_properties: Full user property rules.
        events: Full event rules.
        rule_event: Enforcement action.
        notification_emails: Notification recipients.
        schema_id: Schema definition ID.

    Example:
        ```python
        params = ReplaceSchemaEnforcementParams(
            events=[...],
            common_properties=[...],
            user_properties=[...],
            rule_event="Warn and Hide",
            notification_emails=["admin@example.com"],
        )
        ```
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    common_properties: list[dict[str, Any]]
    """Full common property rules."""

    user_properties: list[dict[str, Any]]
    """Full user property rules."""

    events: list[dict[str, Any]]
    """Full event rules."""

    rule_event: str
    """Enforcement action."""

    notification_emails: list[str]
    """Notification recipients."""

    schema_id: int | None = None
    """Schema definition ID."""


# =============================================================================
# Data Audit Types (Phase 028)
# =============================================================================


class AuditViolation(BaseModel):
    """A single violation found during a data audit.

    Attributes:
        violation: Violation type (e.g., "Unexpected Event",
            "Missing Property", "Unexpected Type for Property").
        name: Property or event name.
        platform: Platform ("iOS", "Android", "Web").
        version: Version string.
        count: Number of occurrences.
        event: Event name (for property violations).
        sensitive: Whether property is marked sensitive.
        property_type_error: Type mismatch description.

    Example:
        ```python
        v = AuditViolation(
            violation="Unexpected Event", name="DebugLog", count=42
        )
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    violation: str
    """Violation type."""

    name: str
    """Property or event name."""

    platform: str | None = None
    """Platform: "iOS", "Android", "Web"."""

    version: str | None = None
    """Version string."""

    count: int
    """Number of occurrences."""

    event: str | None = None
    """Event name (for property violations)."""

    sensitive: bool | None = None
    """Whether property is marked sensitive."""

    property_type_error: str | None = None
    """Type mismatch description."""


class AuditResponse(BaseModel):
    """Response from a data audit operation.

    Contains a list of schema violations and the timestamp when
    the audit was computed.

    Attributes:
        violations: List of audit violations.
        computed_at: Timestamp of audit computation.

    Example:
        ```python
        resp = AuditResponse(
            violations=[
                AuditViolation(violation="Unexpected Event", name="Debug", count=1)
            ],
            computed_at="2026-04-01T12:00:00Z",
        )
        ```
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    violations: list[AuditViolation]
    """List of audit violations."""

    computed_at: str
    """Timestamp of audit computation."""


# =============================================================================
# Data Volume Anomaly Types (Phase 028)
# =============================================================================


class DataVolumeAnomaly(BaseModel):
    """A detected data volume anomaly.

    Attributes:
        id: Anomaly ID.
        timestamp: Detection timestamp.
        actual_count: Actual observed count.
        predicted_upper: Upper bound of prediction.
        predicted_lower: Lower bound of prediction.
        percent_variance: Variance percentage.
        status: Anomaly status ("open" or "dismissed").
        project: Project ID.
        event: Event ID.
        event_name: Event name.
        property: Property ID.
        property_name: Property name.
        metric: Metric ID.
        metric_name: Metric name.
        metric_type: Metric type.
        primary_type: Primary anomaly type.
        drift_types: Drift type details.
        anomaly_class: Anomaly class ("Event", "Property",
            "PropertyTypeDrift", "Metric").

    Example:
        ```python
        anomaly = DataVolumeAnomaly(
            id=1, actual_count=1000, predicted_upper=500,
            predicted_lower=100, percent_variance="100%",
            status="open", project=12345, anomaly_class="Event",
        )
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    id: int
    """Anomaly ID."""

    timestamp: str | None = None
    """Detection timestamp."""

    actual_count: int
    """Actual observed count."""

    predicted_upper: int
    """Upper bound of prediction."""

    predicted_lower: int
    """Lower bound of prediction."""

    percent_variance: str
    """Variance percentage."""

    status: str
    """Anomaly status ("open" or "dismissed")."""

    project: int
    """Project ID."""

    event: int | None = None
    """Event ID."""

    event_name: str | None = None
    """Event name."""

    property: int | None = None
    """Property ID."""

    property_name: str | None = None
    """Property name."""

    metric: int | None = None
    """Metric ID."""

    metric_name: str | None = None
    """Metric name."""

    metric_type: str | None = None
    """Metric type."""

    primary_type: str | None = None
    """Primary anomaly type."""

    drift_types: dict[str, Any] | None = None
    """Drift type details."""

    anomaly_class: str
    """Anomaly class: "Event", "Property", "PropertyTypeDrift", "Metric"."""


class UpdateAnomalyParams(BaseModel):
    """Parameters for updating a single anomaly status.

    Attributes:
        id: Anomaly ID.
        status: New status ("open" or "dismissed").
        anomaly_class: Anomaly class.

    Example:
        ```python
        params = UpdateAnomalyParams(
            id=123, status="dismissed", anomaly_class="Event"
        )
        ```
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: int
    """Anomaly ID."""

    status: str
    """New status: "open" or "dismissed"."""

    anomaly_class: str
    """Anomaly class."""


class BulkAnomalyEntry(BaseModel):
    """A single entry in a bulk anomaly update.

    Attributes:
        id: Anomaly ID.
        anomaly_class: Anomaly class.

    Example:
        ```python
        entry = BulkAnomalyEntry(id=123, anomaly_class="Event")
        ```
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: int
    """Anomaly ID."""

    anomaly_class: str
    """Anomaly class."""


class BulkUpdateAnomalyParams(BaseModel):
    """Parameters for bulk-updating anomaly statuses.

    Attributes:
        anomalies: Anomalies to update.
        status: New status for all ("open" or "dismissed").

    Example:
        ```python
        params = BulkUpdateAnomalyParams(
            anomalies=[BulkAnomalyEntry(id=1, anomaly_class="Event")],
            status="dismissed",
        )
        ```
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    anomalies: list[BulkAnomalyEntry]
    """Anomalies to update."""

    status: str
    """New status for all."""


# =============================================================================
# Event Deletion Request Types (Phase 028)
# =============================================================================


class EventDeletionRequest(BaseModel):
    """An event deletion request with lifecycle status.

    Attributes:
        id: Request ID.
        display_name: Display name.
        event_name: Event to delete.
        from_date: Start date.
        to_date: End date.
        filters: Deletion filters.
        status: Request status ("Submitted", "Processing", "Completed", "Failed").
        deleted_events_count: Count of deleted events.
        created: Creation timestamp.
        requesting_user: User who requested.

    Example:
        ```python
        req = EventDeletionRequest(
            id=1, event_name="Test", from_date="2026-01-01",
            to_date="2026-01-31", status="Submitted",
            deleted_events_count=0, created="2026-04-01",
            requesting_user={"id": 1},
        )
        ```
    """

    model_config = ConfigDict(
        frozen=True, extra="allow", alias_generator=to_camel, populate_by_name=True
    )

    id: int
    """Request ID."""

    display_name: str | None = None
    """Display name."""

    event_name: str
    """Event to delete."""

    from_date: str
    """Start date."""

    to_date: str
    """End date."""

    filters: dict[str, Any] | None = None
    """Deletion filters."""

    status: str
    """Request status: "Submitted", "Processing", "Completed", "Failed"."""

    deleted_events_count: int
    """Count of deleted events."""

    created: str
    """Creation timestamp."""

    requesting_user: dict[str, Any]
    """User who requested."""


class CreateDeletionRequestParams(BaseModel):
    """Parameters for creating an event deletion request.

    Attributes:
        from_date: Start date (YYYY-MM-DD or datetime).
        to_date: End date.
        event_name: Event name to delete.
        filters: Optional deletion filters.

    Example:
        ```python
        params = CreateDeletionRequestParams(
            event_name="Test Event",
            from_date="2026-01-01",
            to_date="2026-01-31",
        )
        ```
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    from_date: str
    """Start date (YYYY-MM-DD or datetime)."""

    to_date: str
    """End date."""

    event_name: str
    """Event name to delete."""

    filters: dict[str, Any] | None = None
    """Optional deletion filters."""


class PreviewDeletionFiltersParams(BaseModel):
    """Parameters for previewing event deletion filters.

    This is a read-only operation that shows what events would match.

    Attributes:
        event_name: Event name.
        from_date: Start date.
        to_date: End date.
        filters: Optional filters.

    Example:
        ```python
        params = PreviewDeletionFiltersParams(
            event_name="Test Event",
            from_date="2026-01-01",
            to_date="2026-01-31",
        )
        ```
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    event_name: str
    """Event name."""

    from_date: str
    """Start date."""

    to_date: str
    """End date."""

    filters: dict[str, Any] | None = None
    """Optional filters."""


# =============================================================================
# Profile Page Result (API pagination)
# =============================================================================


@dataclass(frozen=True)
class ProfilePageResult:
    """Result from fetching a single page of profiles.

    Contains the profiles from one page of the Engage API along with
    pagination metadata for fetching subsequent pages.

    Attributes:
        profiles: List of profile dictionaries from this page.
        session_id: Session ID for fetching next page, None if no more pages.
        page: Zero-based page index that was fetched.
        has_more: True if there are more pages to fetch.
        total: Total number of profiles matching the query across all pages.
        page_size: Number of profiles per page (typically 1000).

    Example:
        ```python
        # Fetch first page to get pagination metadata
        result = api_client.export_profiles_page(page=0)
        all_profiles = list(result.profiles)

        # Pre-compute total pages for parallel fetching
        total_pages = result.num_pages
        print(f"Fetching {total_pages} pages ({result.total} profiles)")

        # Continue fetching if more pages
        while result.has_more:
            result = api_client.export_profiles_page(
                page=result.page + 1,
                session_id=result.session_id,
            )
            all_profiles.extend(result.profiles)
        ```
    """

    profiles: list[dict[str, Any]]
    """List of profile dictionaries from this page."""

    session_id: str | None
    """Session ID for fetching next page, None if no more pages."""

    page: int
    """Zero-based page index that was fetched."""

    has_more: bool
    """True if there are more pages to fetch."""

    total: int
    """Total number of profiles matching the query across all pages."""

    page_size: int
    """Number of profiles per page (typically 1000)."""

    @property
    def num_pages(self) -> int:
        """Calculate total number of pages needed.

        Uses ceiling division to ensure partial pages are counted.

        Returns:
            Total pages needed to fetch all profiles.
            Returns 0 if total is 0 (empty result set).

        Example:
            ```python
            result = api_client.export_profiles_page(page=0)
            # If total=5432 and page_size=1000, num_pages=6
            for page_idx in range(1, result.num_pages):
                # Fetch remaining pages...
            ```
        """
        if self.total == 0:
            return 0
        return math.ceil(self.total / self.page_size)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all page result fields including pagination metadata.
        """
        return {
            "profiles": self.profiles,
            "session_id": self.session_id,
            "page": self.page,
            "has_more": self.has_more,
            "profile_count": len(self.profiles),
            "total": self.total,
            "page_size": self.page_size,
            "num_pages": self.num_pages,
        }


# =============================================================================
# Query API Types (Phase 029)
# =============================================================================


@dataclass(frozen=True)
class Metric:
    """Encapsulates a single event to query with its aggregation settings.

    Used with ``Workspace.query()`` to specify per-event math, property,
    per-user aggregation, and filters. Plain event name strings inherit
    top-level query defaults; Metric objects override them.

    Attributes:
        event: Mixpanel event name.
        math: Aggregation function. Default: ``"total"``.
        property: Property name for property-based math (average, sum, etc.).
        per_user: Per-user pre-aggregation (average, total, min, max).
        filters: Per-metric filters (applied in addition to global ``where``).

    Example:
        ```python
        from mixpanel_data import Metric

        # Simple event with defaults
        m1 = Metric("Login")

        # With aggregation
        m2 = Metric("Purchase", math="average", property="amount")

        # With per-user aggregation
        m3 = Metric("Purchase", math="total", per_user="average")
        ```
    """

    event: str
    """Mixpanel event name."""

    math: MathType = "total"
    """Aggregation function."""

    property: str | None = None
    """Property name for property-based math types."""

    per_user: PerUserAggregation | None = None
    """Per-user pre-aggregation type."""

    filters: list[Filter] | None = None
    """Per-metric filters (list of Filter objects)."""


@dataclass(frozen=True)
class Filter:
    """Represents a typed filter condition on a property.

    Constructed exclusively via class methods — never instantiated directly.
    Each class method maps to specific filterType, filterOperator, and
    filterValue format in the bookmark JSON.

    Example:
        ```python
        from mixpanel_data import Filter

        f1 = Filter.equals("country", "US")
        f2 = Filter.greater_than("age", 18)
        f3 = Filter.between("amount", 10, 100)
        f4 = Filter.is_set("email")
        ```
    """

    _property: str
    """Property name to filter on."""

    _operator: str
    """Internal operator string."""

    _value: str | int | float | list[str] | list[int | float] | None
    """Value(s) to compare against.

    Shape varies by operator: list for equals/not_equals, str for
    contains/not_contains, numeric for greater_than/less_than,
    two-element list for between, None for is_set/is_not_set/is_true/is_false.
    """

    _property_type: FilterPropertyType = "string"
    """Data type of the property."""

    _resource_type: Literal["events", "people"] = "events"
    """Resource type to filter."""

    @classmethod
    def equals(
        cls,
        property: str,
        value: str | list[str],
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Create an equality filter.

        Args:
            property: Property name.
            value: Value or list of values.
            resource_type: Resource type. Default: ``"events"``.

        Returns:
            Filter for string equality.
        """
        val = [value] if isinstance(value, str) else value
        return cls(
            _property=property,
            _operator="equals",
            _value=val,
            _property_type="string",
            _resource_type=resource_type,
        )

    @classmethod
    def not_equals(
        cls,
        property: str,
        value: str | list[str],
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Create a not-equals filter.

        Args:
            property: Property name.
            value: Value or list of values.
            resource_type: Resource type. Default: ``"events"``.

        Returns:
            Filter for string inequality.
        """
        val = [value] if isinstance(value, str) else value
        return cls(
            _property=property,
            _operator="does not equal",
            _value=val,
            _property_type="string",
            _resource_type=resource_type,
        )

    @classmethod
    def contains(
        cls,
        property: str,
        value: str,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Create a contains (substring) filter.

        Args:
            property: Property name.
            value: Substring to match.
            resource_type: Resource type. Default: ``"events"``.

        Returns:
            Filter for substring containment.
        """
        return cls(
            _property=property,
            _operator="contains",
            _value=value,
            _property_type="string",
            _resource_type=resource_type,
        )

    @classmethod
    def not_contains(
        cls,
        property: str,
        value: str,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Create a not-contains filter.

        Args:
            property: Property name.
            value: Substring that must not match.
            resource_type: Resource type. Default: ``"events"``.

        Returns:
            Filter for substring non-containment.
        """
        return cls(
            _property=property,
            _operator="does not contain",
            _value=value,
            _property_type="string",
            _resource_type=resource_type,
        )

    @classmethod
    def greater_than(
        cls,
        property: str,
        value: int | float,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Create a greater-than filter.

        Args:
            property: Property name.
            value: Numeric threshold.
            resource_type: Resource type. Default: ``"events"``.

        Returns:
            Filter for numeric greater-than.
        """
        return cls(
            _property=property,
            _operator="is greater than",
            _value=value,
            _property_type="number",
            _resource_type=resource_type,
        )

    @classmethod
    def less_than(
        cls,
        property: str,
        value: int | float,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Create a less-than filter.

        Args:
            property: Property name.
            value: Numeric threshold.
            resource_type: Resource type. Default: ``"events"``.

        Returns:
            Filter for numeric less-than.
        """
        return cls(
            _property=property,
            _operator="is less than",
            _value=value,
            _property_type="number",
            _resource_type=resource_type,
        )

    @classmethod
    def between(
        cls,
        property: str,
        min_val: int | float,
        max_val: int | float,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Create a between (inclusive range) filter.

        Args:
            property: Property name.
            min_val: Minimum value (inclusive).
            max_val: Maximum value (inclusive).
            resource_type: Resource type. Default: ``"events"``.

        Returns:
            Filter for numeric range.
        """
        return cls(
            _property=property,
            _operator="is between",
            _value=[min_val, max_val],
            _property_type="number",
            _resource_type=resource_type,
        )

    @classmethod
    def is_set(
        cls,
        property: str,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Create a property-existence filter.

        Args:
            property: Property name.
            resource_type: Resource type. Default: ``"events"``.

        Returns:
            Filter for property existence.
        """
        return cls(
            _property=property,
            _operator="is set",
            _value=None,
            _property_type="string",
            _resource_type=resource_type,
        )

    @classmethod
    def is_not_set(
        cls,
        property: str,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Create a property-nonexistence filter.

        Args:
            property: Property name.
            resource_type: Resource type. Default: ``"events"``.

        Returns:
            Filter for property non-existence.
        """
        return cls(
            _property=property,
            _operator="is not set",
            _value=None,
            _property_type="string",
            _resource_type=resource_type,
        )

    @classmethod
    def is_true(
        cls,
        property: str,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Create a boolean true filter.

        Args:
            property: Property name.
            resource_type: Resource type. Default: ``"events"``.

        Returns:
            Filter for boolean true.
        """
        return cls(
            _property=property,
            _operator="true",
            _value=None,
            _property_type="boolean",
            _resource_type=resource_type,
        )

    @classmethod
    def is_false(
        cls,
        property: str,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Create a boolean false filter.

        Args:
            property: Property name.
            resource_type: Resource type. Default: ``"events"``.

        Returns:
            Filter for boolean false.
        """
        return cls(
            _property=property,
            _operator="false",
            _value=None,
            _property_type="boolean",
            _resource_type=resource_type,
        )


@dataclass(frozen=True)
class GroupBy:
    """Specifies a property breakdown with optional numeric bucketing.

    Used with ``Workspace.query()`` to break down results by property values.
    String properties are broken down by distinct values; numeric properties
    can be bucketed into ranges.

    Attributes:
        property: Property name to break down by.
        property_type: Data type of the property. Default: ``"string"``.
        bucket_size: Bucket width for numeric properties.
        bucket_min: Minimum value for numeric buckets.
        bucket_max: Maximum value for numeric buckets.

    Example:
        ```python
        from mixpanel_data import GroupBy

        # String breakdown
        g1 = GroupBy("country")

        # Numeric bucketed breakdown
        g2 = GroupBy(
            "revenue",
            property_type="number",
            bucket_size=50,
            bucket_min=0,
            bucket_max=500,
        )
        ```
    """

    property: str
    """Property name to break down by."""

    property_type: Literal["string", "number", "boolean", "datetime"] = "string"
    """Data type of the property."""

    bucket_size: int | float | None = None
    """Bucket width for numeric properties."""

    bucket_min: int | float | None = None
    """Minimum value for numeric buckets."""

    bucket_max: int | float | None = None
    """Maximum value for numeric buckets."""


@dataclass(frozen=True)
class QueryResult(ResultWithDataFrame):
    """Structured output from a Workspace.query() execution.

    Contains the query response data with lazy DataFrame conversion.
    The series structure varies by query mode:

    - Timeseries: ``{metric_name: {date_string: value}}``
    - Total: ``{metric_name: {"all": value}}``

    Attributes:
        computed_at: When the query was computed (ISO format).
        from_date: Effective start date from response.
        to_date: Effective end date from response.
        headers: Column headers from the insights response.
        series: Query result data (structure varies by mode).
        params: Generated bookmark params sent to API (for debugging/persistence).
        meta: Response metadata (sampling factor, limits hit).

    Example:
        ```python
        result = ws.query("Login", math="unique", last=7)

        # DataFrame access
        print(result.df.head())

        # Inspect generated params
        print(result.params)

        # Save as a report
        ws.create_bookmark(CreateBookmarkParams(
            name="Login Uniques (7d)",
            bookmark_type="insights",
            params=result.params,
        ))
        ```
    """

    computed_at: str
    """When the query was computed (ISO format)."""

    from_date: str
    """Effective start date from response."""

    to_date: str
    """Effective end date from response."""

    headers: list[str] = field(default_factory=list)
    """Column headers from the insights response."""

    series: dict[str, Any] = field(default_factory=dict)
    """Query result data.

    For timeseries: ``{metric_name: {date_string: value}}``
    For total: ``{metric_name: {"all": value}}``
    """

    params: dict[str, Any] = field(default_factory=dict)
    """Generated bookmark params sent to API (for debugging/persistence)."""

    meta: dict[str, Any] = field(default_factory=dict)
    """Response metadata (sampling factor, limits hit, etc.)."""

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame.

        For timeseries mode: columns are ``date``, ``event``, ``count``.
        For total mode: columns are ``event``, ``count``.
        Table mode: depends on API response structure; typically matches
        timeseries or total depending on date presence.

        Returns:
            Normalized DataFrame with one row per (date, metric) pair
            for timeseries, or one row per metric for total.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = []

        for metric_name, date_values in self.series.items():
            if not isinstance(date_values, dict):
                continue
            for date_key, value in date_values.items():
                if date_key == "all":
                    # Total mode: no date column
                    rows.append({"event": metric_name, "count": value})
                else:
                    normalized_date = date_key
                    rows.append(
                        {"date": normalized_date, "event": metric_name, "count": value}
                    )

        if not rows:
            result_df = pd.DataFrame(columns=["date", "event", "count"])
        elif "date" in rows[0]:
            result_df = pd.DataFrame(rows, columns=["date", "event", "count"])
        else:
            result_df = pd.DataFrame(rows, columns=["event", "count"])

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all QueryResult fields.
        """
        return {
            "computed_at": self.computed_at,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "headers": self.headers,
            "series": self.series,
            "params": self.params,
            "meta": self.meta,
        }
