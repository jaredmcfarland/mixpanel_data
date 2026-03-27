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
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

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


# =============================================================================
# SQL Query Result Type
# =============================================================================


@dataclass(frozen=True)
class SQLResult:
    """Result from a SQL query with column metadata.

    Provides structured access to SQL query results including column names
    and row data. Supports conversion to list of dicts for JSON serialization
    and CLI output formatting.

    Attributes:
        columns: List of column names from the query.
        rows: List of row tuples containing the data.

    Example:
        ```python
        result = ws.sql_rows("SELECT name, age FROM users")
        print(result.columns)  # ['name', 'age']
        for row in result.rows:
            print(dict(zip(result.columns, row)))

        # Or convert to dicts directly:
        for row in result.to_dicts():
            print(row)  # {'name': 'Alice', 'age': 30}
        ```
    """

    columns: list[str]
    """List of column names from the query."""

    rows: list[tuple[Any, ...]]
    """List of row tuples containing the data."""

    def to_dicts(self) -> list[dict[str, Any]]:
        """Convert rows to list of dicts with column names as keys.

        Returns:
            List of dictionaries, one per row, with column names as keys.

        Example:
            ```python
            result = SQLResult(columns=["x", "y"], rows=[(1, 2), (3, 4)])
            dicts = result.to_dicts()
            # [{"x": 1, "y": 2}, {"x": 3, "y": 4}]
            ```
        """
        return [dict(zip(self.columns, row, strict=True)) for row in self.rows]

    def to_dict(self) -> dict[str, Any]:
        """Serialize result for JSON output.

        Returns:
            Dictionary with columns, rows (as lists), and row_count.
        """
        return {
            "columns": self.columns,
            "rows": [list(row) for row in self.rows],
            "row_count": len(self.rows),
        }

    def __len__(self) -> int:
        """Return number of rows.

        Returns:
            Count of rows in the result.
        """
        return len(self.rows)

    def __iter__(self) -> Iterator[tuple[Any, ...]]:
        """Iterate over rows.

        Yields:
            Row tuples from the result.
        """
        return iter(self.rows)


@dataclass(frozen=True)
class FetchResult:
    """Result of a data fetch operation.

    Represents the outcome of fetching events or profiles from Mixpanel
    and storing them in the local database.
    """

    table: str
    """Name of the created table."""

    rows: int
    """Number of rows fetched."""

    type: Literal["events", "profiles"]
    """Type of data fetched."""

    duration_seconds: float
    """Time taken to complete the fetch."""

    date_range: tuple[str, str] | None
    """Date range for events (None for profiles)."""

    fetched_at: datetime
    """Timestamp when fetch completed."""

    # Internal field for caching DataFrame (not part of public API)
    _data: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Convert result data to pandas DataFrame.

        Conversion is lazy - computed on first access and cached.

        Returns:
            DataFrame with fetched data.
        """
        if self._df_cache is not None:
            return self._df_cache

        result_df = pd.DataFrame(self._data) if self._data else pd.DataFrame()

        # Cache using object.__setattr__ for frozen dataclass
        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize result for JSON output.

        Returns:
            Dictionary representation (excludes raw data).
            datetime values are converted to ISO format strings.
        """
        return {
            "table": self.table,
            "rows": self.rows,
            "type": self.type,
            "duration_seconds": self.duration_seconds,
            "date_range": self.date_range,
            "fetched_at": self.fetched_at.isoformat(),
        }


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


# Storage Types


@dataclass(frozen=True)
class TableMetadata:
    """Metadata for a data fetch operation.

    This metadata is passed to table creation methods and stored in the
    database's internal _metadata table for tracking fetch operations.
    """

    type: Literal["events", "profiles"]
    """Type of data fetched."""

    fetched_at: datetime
    """When the fetch completed (UTC)."""

    from_date: str | None = None
    """Start date for events (YYYY-MM-DD), None for profiles."""

    to_date: str | None = None
    """End date for events (YYYY-MM-DD), None for profiles."""

    filter_events: list[str] | None = None
    """Event names filtered (if applicable)."""

    filter_where: str | None = None
    """WHERE clause filter (if applicable)."""

    filter_cohort_id: str | None = None
    """Cohort ID filter for profiles (if applicable)."""

    filter_output_properties: list[str] | None = None
    """Property names to include in output (if applicable)."""

    filter_group_id: str | None = None
    """Group ID for group profile queries (if applicable)."""

    filter_behaviors: str | None = None
    """Serialized behaviors filter for behavioral profile queries (if applicable)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "type": self.type,
            "fetched_at": self.fetched_at.isoformat(),
            "from_date": self.from_date,
            "to_date": self.to_date,
            "filter_events": self.filter_events,
            "filter_where": self.filter_where,
            "filter_cohort_id": self.filter_cohort_id,
            "filter_output_properties": self.filter_output_properties,
            "filter_group_id": self.filter_group_id,
            "filter_behaviors": self.filter_behaviors,
        }


@dataclass(frozen=True)
class TableInfo:
    """Information about a table in the database.

    Returned by list_tables() to provide summary information about
    available tables without retrieving full schemas.
    """

    name: str
    """Table name."""

    type: Literal["events", "profiles"]
    """Table type."""

    row_count: int
    """Number of rows."""

    fetched_at: datetime
    """When data was fetched (UTC)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "name": self.name,
            "type": self.type,
            "row_count": self.row_count,
            "fetched_at": self.fetched_at.isoformat(),
        }


@dataclass(frozen=True)
class ColumnInfo:
    """Information about a table column.

    Describes a single column's schema, including name, type,
    nullability constraints, and primary key status.
    """

    name: str
    """Column name."""

    type: str
    """DuckDB type (VARCHAR, TIMESTAMP, JSON, INTEGER, etc.)."""

    nullable: bool
    """Whether column allows NULL values."""

    primary_key: bool = False
    """Whether column is a primary key."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "name": self.name,
            "type": self.type,
            "nullable": self.nullable,
            "primary_key": self.primary_key,
        }


@dataclass(frozen=True)
class TableSchema:
    """Schema information for a table.

    Returned by get_schema() to describe the structure of a table,
    including all column definitions.
    """

    table_name: str
    """Table name."""

    columns: list[ColumnInfo]
    """Column definitions."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "table_name": self.table_name,
            "columns": [col.to_dict() for col in self.columns],
        }


# Workspace Types


@dataclass(frozen=True)
class WorkspaceInfo:
    """Information about a Workspace instance.

    Returned by Workspace.info() to provide metadata about the workspace
    including database location, connection details, and table summary.
    """

    path: Path | None
    """Database file path (None for ephemeral or in-memory workspaces)."""

    project_id: str
    """Mixpanel project ID."""

    region: str
    """Data residency region (us, eu, in)."""

    account: str | None
    """Named account used (None if credentials from environment)."""

    tables: list[str]
    """Names of tables in the database."""

    size_mb: float
    """Database file size in megabytes (0.0 for in-memory workspaces)."""

    created_at: datetime | None
    """When database was created (None if unknown)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "path": str(self.path) if self.path else None,
            "project_id": self.project_id,
            "region": self.region,
            "account": self.account,
            "tables": self.tables,
            "size_mb": self.size_mb,
            "created_at": self.created_at.isoformat() if self.created_at else None,
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


# Introspection Types


@dataclass(frozen=True)
class ColumnSummary:
    """Statistical summary of a single column from DuckDB's SUMMARIZE command.

    Contains per-column statistics including min/max, quartiles, null percentage,
    and approximate distinct counts. Numeric columns include additional stats
    like average and standard deviation.
    """

    column_name: str
    """Name of the column."""

    column_type: str
    """DuckDB data type (VARCHAR, TIMESTAMP, INTEGER, JSON, etc.)."""

    min: Any
    """Minimum value (type varies by column type)."""

    max: Any
    """Maximum value (type varies by column type)."""

    approx_unique: int
    """Approximate count of distinct values (HyperLogLog)."""

    avg: float | None
    """Mean value (None for non-numeric columns)."""

    std: float | None
    """Standard deviation (None for non-numeric columns)."""

    q25: Any
    """25th percentile value (None for non-numeric)."""

    q50: Any
    """Median / 50th percentile (None for non-numeric)."""

    q75: Any
    """75th percentile value (None for non-numeric)."""

    count: int
    """Number of non-null values."""

    null_percentage: float
    """Percentage of null values (0.0 to 100.0)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all column statistics.
        """
        return {
            "column_name": self.column_name,
            "column_type": self.column_type,
            "min": self.min,
            "max": self.max,
            "approx_unique": self.approx_unique,
            "avg": self.avg,
            "std": self.std,
            "q25": self.q25,
            "q50": self.q50,
            "q75": self.q75,
            "count": self.count,
            "null_percentage": self.null_percentage,
        }


@dataclass(frozen=True)
class SummaryResult:
    """Statistical summary of all columns in a table.

    Contains row count and per-column statistics from DuckDB's SUMMARIZE command.
    Provides both structured access via the columns list and DataFrame conversion
    via the df property.
    """

    table: str
    """Name of the summarized table."""

    row_count: int
    """Total number of rows in the table."""

    columns: list[ColumnSummary] = field(default_factory=list)
    """Per-column statistics."""

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with one row per column.

        Conversion is lazy - computed on first access and cached.

        Returns:
            DataFrame with column statistics.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = [col.to_dict() for col in self.columns]

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(
                columns=[
                    "column_name",
                    "column_type",
                    "min",
                    "max",
                    "approx_unique",
                    "avg",
                    "std",
                    "q25",
                    "q50",
                    "q75",
                    "count",
                    "null_percentage",
                ]
            )
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with table name, row count, and column statistics.
        """
        return {
            "table": self.table,
            "row_count": self.row_count,
            "columns": [col.to_dict() for col in self.columns],
        }


@dataclass(frozen=True)
class EventStats:
    """Statistics for a single event type.

    Contains count, unique users, date range, and percentage of total
    for a specific event in an events table.
    """

    event_name: str
    """Name of the event."""

    count: int
    """Total occurrences of this event."""

    unique_users: int
    """Count of distinct users who triggered this event."""

    first_seen: datetime
    """Earliest occurrence timestamp."""

    last_seen: datetime
    """Latest occurrence timestamp."""

    pct_of_total: float
    """Percentage of all events (0.0 to 100.0)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with event statistics (datetimes as ISO strings).
        """
        return {
            "event_name": self.event_name,
            "count": self.count,
            "unique_users": self.unique_users,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "pct_of_total": self.pct_of_total,
        }


@dataclass(frozen=True)
class EventBreakdownResult:
    """Distribution of events in a table.

    Contains aggregate statistics and per-event breakdown with counts,
    unique users, date ranges, and percentages.
    """

    table: str
    """Name of the analyzed table."""

    total_events: int
    """Total number of events in the table."""

    total_users: int
    """Total distinct users across all events."""

    date_range: tuple[datetime, datetime]
    """(earliest, latest) event timestamps."""

    events: list[EventStats] = field(default_factory=list)
    """Per-event statistics, ordered by count descending."""

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with one row per event type.

        Conversion is lazy - computed on first access and cached.

        Returns:
            DataFrame with event statistics.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = []
        for event in self.events:
            rows.append(
                {
                    "event_name": event.event_name,
                    "count": event.count,
                    "unique_users": event.unique_users,
                    "first_seen": event.first_seen,
                    "last_seen": event.last_seen,
                    "pct_of_total": event.pct_of_total,
                }
            )

        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(
                columns=[
                    "event_name",
                    "count",
                    "unique_users",
                    "first_seen",
                    "last_seen",
                    "pct_of_total",
                ]
            )
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with table info and event statistics.
        """
        return {
            "table": self.table,
            "total_events": self.total_events,
            "total_users": self.total_users,
            "date_range": [
                self.date_range[0].isoformat(),
                self.date_range[1].isoformat(),
            ],
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(frozen=True)
class ColumnStatsResult:
    """Deep statistical analysis of a single column.

    Provides detailed statistics including null rates, cardinality,
    top values, and numeric statistics (for numeric columns).
    Supports JSON path expressions for analyzing properties.
    """

    table: str
    """Name of the source table."""

    column: str
    """Column expression analyzed (may include JSON path)."""

    dtype: str
    """DuckDB data type of the column."""

    count: int
    """Number of non-null values."""

    null_count: int
    """Number of null values."""

    null_pct: float
    """Percentage of null values (0.0 to 100.0)."""

    unique_count: int
    """Approximate count of distinct values."""

    unique_pct: float
    """Percentage of values that are unique (0.0 to 100.0)."""

    top_values: list[tuple[Any, int]] = field(default_factory=list)
    """Most frequent (value, count) pairs."""

    min: float | None = None
    """Minimum value (None for non-numeric)."""

    max: float | None = None
    """Maximum value (None for non-numeric)."""

    mean: float | None = None
    """Mean value (None for non-numeric)."""

    std: float | None = None
    """Standard deviation (None for non-numeric)."""

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Convert top values to DataFrame with columns: value, count.

        Conversion is lazy - computed on first access and cached.

        Returns:
            DataFrame with top values and their counts.
        """
        if self._df_cache is not None:
            return self._df_cache

        rows: list[dict[str, Any]] = [
            {"value": value, "count": count} for value, count in self.top_values
        ]

        result_df = (
            pd.DataFrame(rows) if rows else pd.DataFrame(columns=["value", "count"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all column statistics.
        """
        return {
            "table": self.table,
            "column": self.column,
            "dtype": self.dtype,
            "count": self.count,
            "null_count": self.null_count,
            "null_pct": self.null_pct,
            "unique_count": self.unique_count,
            "unique_pct": self.unique_pct,
            "top_values": [[value, count] for value, count in self.top_values],
            "min": self.min,
            "max": self.max,
            "mean": self.mean,
            "std": self.std,
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
    enabling quick understanding of property value distribution without fetching
    all data locally.

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
    without fetching all data locally.

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
    user engagement patterns without fetching all data locally.

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
# Parallel Export Types (Phase 017)
# =============================================================================


@dataclass(frozen=True)
class BatchProgress:
    """Progress update for a parallel fetch batch.

    Sent to the on_batch_complete callback when a batch finishes
    (successfully or with error).

    Attributes:
        from_date: Start date of this batch (YYYY-MM-DD).
        to_date: End date of this batch (YYYY-MM-DD).
        batch_index: Zero-based index of this batch.
        total_batches: Total number of batches in the parallel fetch.
        rows: Number of rows fetched in this batch (0 if failed).
        success: Whether this batch completed successfully.
        error: Error message if failed, None if successful.

    Example:
        ```python
        def on_batch(progress: BatchProgress) -> None:
            status = "✓" if progress.success else "✗"
            print(f"[{status}] Batch {progress.batch_index + 1}/{progress.total_batches}")

        result = ws.fetch_events(
            name="events",
            from_date="2024-01-01",
            to_date="2024-03-31",
            parallel=True,
            on_batch_complete=on_batch,
        )
        ```
    """

    from_date: str
    """Start date of this batch (YYYY-MM-DD)."""

    to_date: str
    """End date of this batch (YYYY-MM-DD)."""

    batch_index: int
    """Zero-based index of this batch."""

    total_batches: int
    """Total number of batches in the parallel fetch."""

    rows: int
    """Number of rows fetched in this batch (0 if failed)."""

    success: bool
    """Whether this batch completed successfully."""

    error: str | None = None
    """Error message if failed, None if successful."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all batch progress fields.
        """
        return {
            "from_date": self.from_date,
            "to_date": self.to_date,
            "batch_index": self.batch_index,
            "total_batches": self.total_batches,
            "rows": self.rows,
            "success": self.success,
            "error": self.error,
        }


@dataclass(frozen=True)
class BatchResult:
    """Result of fetching a single date range chunk.

    Internal type used by ParallelFetcherService to track batch outcomes.
    Contains either the fetched data (on success) or error info (on failure).

    Attributes:
        from_date: Start date of this batch (YYYY-MM-DD).
        to_date: End date of this batch (YYYY-MM-DD).
        rows: Number of rows fetched (0 if failed).
        success: Whether the batch completed successfully.
        error: Exception message if failed, None if successful.

    Note:
        Data is not included in to_dict() as it's consumed by the writer
        thread and is not JSON-serializable (iterator of dicts).
    """

    from_date: str
    """Start date of this batch (YYYY-MM-DD)."""

    to_date: str
    """End date of this batch (YYYY-MM-DD)."""

    rows: int
    """Number of rows fetched (0 if failed)."""

    success: bool
    """Whether the batch completed successfully."""

    error: str | None = None
    """Exception message if failed, None if successful."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output (excludes data).

        Returns:
            Dictionary with batch result fields (excluding data).
        """
        return {
            "from_date": self.from_date,
            "to_date": self.to_date,
            "rows": self.rows,
            "success": self.success,
            "error": self.error,
        }


@dataclass(frozen=True)
class ParallelFetchResult:
    """Result of a parallel fetch operation.

    Aggregates results from all batches, providing summary statistics
    and information about any failures for retry.

    Attributes:
        table: Name of the created/appended table.
        total_rows: Total number of rows fetched across all batches.
        successful_batches: Number of batches that completed successfully.
        failed_batches: Number of batches that failed.
        failed_date_ranges: Date ranges (from_date, to_date) of failed batches.
        duration_seconds: Total time taken for the parallel fetch.
        fetched_at: Timestamp when fetch completed.

    Example:
        ```python
        result = ws.fetch_events(
            name="events",
            from_date="2024-01-01",
            to_date="2024-03-31",
            parallel=True,
        )

        if result.has_failures:
            print(f"Warning: {result.failed_batches} batches failed")
            for from_date, to_date in result.failed_date_ranges:
                print(f"  {from_date} to {to_date}")
        ```
    """

    table: str
    """Name of the created/appended table."""

    total_rows: int
    """Total number of rows fetched across all batches."""

    successful_batches: int
    """Number of batches that completed successfully."""

    failed_batches: int
    """Number of batches that failed."""

    failed_date_ranges: tuple[tuple[str, str], ...]
    """Date ranges (from_date, to_date) of failed batches for retry."""

    duration_seconds: float
    """Total time taken for the parallel fetch."""

    fetched_at: datetime
    """Timestamp when fetch completed."""

    @property
    def has_failures(self) -> bool:
        """Check if any batches failed.

        Returns:
            True if at least one batch failed, False otherwise.
        """
        return self.failed_batches > 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all result fields including has_failures.
        """
        return {
            "table": self.table,
            "total_rows": self.total_rows,
            "successful_batches": self.successful_batches,
            "failed_batches": self.failed_batches,
            "failed_date_ranges": [list(dr) for dr in self.failed_date_ranges],
            "duration_seconds": self.duration_seconds,
            "fetched_at": self.fetched_at.isoformat(),
            "has_failures": self.has_failures,
        }


# =============================================================================
# Parallel Profile Fetch Types (Phase 019)
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


@dataclass(frozen=True)
class ProfileProgress:
    """Progress update for a parallel profile fetch page.

    Sent to the on_page_complete callback when a page finishes
    (successfully or with error). Used for progress visibility during
    parallel profile fetching operations.

    Attributes:
        page_index: Zero-based index of this page.
        total_pages: Total pages if known, None if not yet determined.
        rows: Number of rows fetched in this page (0 if failed).
        success: Whether this page completed successfully.
        error: Error message if failed, None if successful.
        cumulative_rows: Total rows fetched so far across all pages.

    Example:
        ```python
        def on_page(progress: ProfileProgress) -> None:
            status = "✓" if progress.success else "✗"
            pct = f"{progress.page_index + 1}/{progress.total_pages}" if progress.total_pages else f"{progress.page_index + 1}/?"
            print(f"[{status}] Page {pct}: {progress.cumulative_rows} total rows")

        result = ws.fetch_profiles(
            name="users",
            parallel=True,
            on_page_complete=on_page,
        )
        ```
    """

    page_index: int
    """Zero-based index of this page."""

    total_pages: int | None
    """Total pages if known, None if not yet determined."""

    rows: int
    """Number of rows fetched in this page (0 if failed)."""

    success: bool
    """Whether this page completed successfully."""

    error: str | None
    """Error message if failed, None if successful."""

    cumulative_rows: int
    """Total rows fetched so far across all pages."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all profile progress fields.
        """
        return {
            "page_index": self.page_index,
            "total_pages": self.total_pages,
            "rows": self.rows,
            "success": self.success,
            "error": self.error,
            "cumulative_rows": self.cumulative_rows,
        }


@dataclass(frozen=True)
class ParallelProfileResult:
    """Result of a parallel profile fetch operation.

    Aggregates results from all pages, providing summary statistics
    and information about any failures for retry.

    Attributes:
        table: Name of the created/appended table.
        total_rows: Total number of rows fetched across all pages.
        successful_pages: Number of pages that completed successfully.
        failed_pages: Number of pages that failed.
        failed_page_indices: Page indices of failed pages for retry.
        duration_seconds: Total time taken for the parallel fetch.
        fetched_at: Timestamp when fetch completed.

    Example:
        ```python
        result = ws.fetch_profiles(
            name="users",
            parallel=True,
        )

        if result.has_failures:
            print(f"Warning: {result.failed_pages} pages failed")
            for idx in result.failed_page_indices:
                print(f"  Page {idx}")
        ```
    """

    table: str
    """Name of the created/appended table."""

    total_rows: int
    """Total number of rows fetched across all pages."""

    successful_pages: int
    """Number of pages that completed successfully."""

    failed_pages: int
    """Number of pages that failed."""

    failed_page_indices: tuple[int, ...]
    """Page indices of failed pages for retry."""

    duration_seconds: float
    """Total time taken for the parallel fetch."""

    fetched_at: datetime
    """Timestamp when fetch completed."""

    @property
    def has_failures(self) -> bool:
        """Check if any pages failed.

        Returns:
            True if at least one page failed, False otherwise.
        """
        return self.failed_pages > 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output.

        Returns:
            Dictionary with all result fields including has_failures.
        """
        return {
            "table": self.table,
            "total_rows": self.total_rows,
            "successful_pages": self.successful_pages,
            "failed_pages": self.failed_pages,
            "failed_page_indices": list(self.failed_page_indices),
            "duration_seconds": self.duration_seconds,
            "fetched_at": self.fetched_at.isoformat(),
            "has_failures": self.has_failures,
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

    ancestors: list[Any] = []  # noqa: RUF012
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

    card_type: str = ""
    """Card type (serialized as ``"type"``)."""

    text_card_id: int | None = None
    """Text card ID, if applicable."""

    bookmark_id: int | None = None
    """Bookmark ID, if applicable."""

    markdown: str | None = None
    """Markdown content for text cards."""

    name: str | None = None
    """Card name."""

    params: Any | None = None
    """Card parameters."""

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize with ``card_type`` renamed to ``type``.

        Args:
            **kwargs: Keyword arguments passed to ``BaseModel.model_dump()``.

        Returns:
            Dict with ``card_type`` serialized as ``type``.
        """
        data = super().model_dump(**kwargs)
        if "card_type" in data:
            data["type"] = data.pop("card_type")
        return data


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
        dumped = data.model_dump(exclude_none=True)
        # {"type": "anomaly", "date": "2025-01-01"}
        ```
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    source_type: str = ""
    """Source type (serialized as ``"type"``)."""

    date: str | None = None
    """Date string."""

    metric_source: bool | None = None
    """Whether this is a metric source."""

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize with ``source_type`` renamed to ``type``.

        Args:
            **kwargs: Keyword arguments passed to ``BaseModel.model_dump()``.

        Returns:
            Dict with ``source_type`` serialized as ``type``.
        """
        data = super().model_dump(**kwargs)
        if "source_type" in data:
            data["type"] = data.pop("source_type")
        return data


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
        data = params.model_dump(exclude_none=True)
        # {"type": "embedded"}
        ```
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    link_type: str = ""
    """Link type (serialized as ``"type"``)."""

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize with ``link_type`` renamed to ``type``.

        Args:
            **kwargs: Keyword arguments passed to ``BaseModel.model_dump()``.

        Returns:
            Dict with ``link_type`` serialized as ``type``.
        """
        data = super().model_dump(**kwargs)
        if "link_type" in data:
            data["type"] = data.pop("link_type")
        return data


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

    params: Any = None
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
        data = params.model_dump(exclude_none=True)
        ```
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    """Bookmark name (required)."""

    bookmark_type: str
    """Report type (required, serialized as ``"type"``)."""

    params: Any
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

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize with ``bookmark_type`` renamed to ``type``.

        Args:
            **kwargs: Keyword arguments passed to ``BaseModel.model_dump()``.

        Returns:
            Dict with ``bookmark_type`` serialized as ``type``.
        """
        data = super().model_dump(**kwargs)
        if "bookmark_type" in data:
            data["type"] = data.pop("bookmark_type")
        return data


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

    params: Any | None = None
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

    params: Any | None = None
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

    results: list[Any] = []  # noqa: RUF012
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

    referenced_directly_by: list[int] = []  # noqa: RUF012
    """IDs of entities directly referencing this cohort."""

    active_integrations: list[int] = []  # noqa: RUF012
    """Active integration IDs."""


class CreateCohortParams(BaseModel):
    """Parameters for creating a new cohort.

    The ``definition`` dict is flattened into the top-level JSON payload
    at serialization time, matching the Rust ``#[serde(flatten)]`` behavior.

    Attributes:
        name: Cohort name (required).
        description: Cohort description.
        data_group_id: Data group identifier.
        is_locked: Whether the cohort should be locked.
        is_visible: Whether the cohort should be visible.
        deleted: Soft-delete flag.
        definition: Cohort definition (flattened into payload).

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

    definition: dict[str, Any] | None = None
    """Cohort definition (flattened into payload)."""

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


class UpdateCohortParams(BaseModel):
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
        definition: New cohort definition (flattened into payload).

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

    definition: dict[str, Any] | None = None
    """New cohort definition (flattened into payload)."""

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


class BulkUpdateCohortEntry(BaseModel):
    """Entry for bulk-updating cohorts.

    Attributes:
        id: Cohort ID to update (required).
        name: New cohort name.
        description: New cohort description.
        definition: New cohort definition (flattened into payload).

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

    definition: dict[str, Any] | None = None
    """New cohort definition (flattened into payload)."""

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
