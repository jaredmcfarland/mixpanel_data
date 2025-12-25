# Implementation Plan: Local Introspection API

**Created**: 2024-12-25
**Status**: Draft
**Input**: [introspection-feature-proposal.md](../introspection-feature-proposal.md)

## Problem Statement

After fetching Mixpanel data into a local DuckDB database, users (human analysts and AI agents) need to quickly understand what's in the data before writing queries. Currently this requires:

- Writing custom SQL queries to see sample data
- Manually composing `SUMMARIZE` commands
- Crafting GROUP BY queries to understand event distribution
- Using `json_keys()` to discover JSON property structure
- Multiple queries to analyze individual columns

This friction slows exploration and is especially problematic for AI agents that need to understand unfamiliar data before generating analysis queries.

## Proposed Solution

Add 5 introspection methods to the `Workspace` class that expose DuckDB's built-in capabilities through typed, discoverable APIs:

| Method | Returns | Purpose |
|--------|---------|---------|
| `sample(table, n=10)` | `pd.DataFrame` | Random sample rows for data inspection |
| `summarize(table)` | `SummaryResult` | Statistical summary of all columns |
| `event_breakdown(table)` | `EventBreakdownResult` | Event distribution analysis |
| `property_keys(table, event=None)` | `list[str]` | JSON property key discovery |
| `column_stats(table, column)` | `ColumnStatsResult` | Deep single-column analysis |

All methods follow existing patterns:
- Frozen dataclass results with lazy `.df` property
- Full type hints and comprehensive docstrings
- JSON-serializable via `to_dict()`
- Work with any table, not just event/profile tables

---

## Phase 1: Quick Wins

### Feature 1: `sample(table, n=10)`

**User Story**: An agent wants to see actual data rows before querying, to understand property structure and value formats.

**Implementation**: One-line DuckDB wrapper.

```python
# In Workspace class
def sample(self, table: str, n: int = 10) -> pd.DataFrame:
    """Return random sample rows from a table.

    Uses DuckDB's reservoir sampling for representative results.
    Unlike LIMIT, sampling returns rows from throughout the table.

    Args:
        table: Table name to sample from.
        n: Number of rows to return (default: 10).

    Returns:
        DataFrame with n random rows.

    Raises:
        TableNotFoundError: If table doesn't exist.

    Example:
        ```python
        ws = Workspace()
        ws.sample("events")  # 10 random rows
        ws.sample("events", n=5)  # 5 random rows
        ```
    """
    # Validate table exists first
    self._storage.get_schema(table)
    return self._storage.execute_df(f"SELECT * FROM {table} USING SAMPLE {n}")
```

**SQL Used**: `SELECT * FROM {table} USING SAMPLE {n}`

**Files to Modify**:
| File | Changes |
|------|---------|
| `src/mixpanel_data/workspace.py` | Add `sample()` method |
| `tests/unit/test_workspace.py` | Add tests for `sample()` |

**Tests**:
```python
def test_sample_returns_n_rows():
    """Sample returns requested number of rows."""
    # Create table with 100 rows
    # Call ws.sample("table", n=5)
    # Assert len(result) == 5

def test_sample_default_n():
    """Sample defaults to 10 rows."""
    # Create table with 100 rows
    # Call ws.sample("table")
    # Assert len(result) == 10

def test_sample_nonexistent_table_raises():
    """Sample raises TableNotFoundError for missing table."""
    # Call ws.sample("nonexistent")
    # Assert raises TableNotFoundError
```

---

### Feature 2: `summarize(table)`

**User Story**: An agent exploring an unfamiliar events table wants instant statistical context before writing queries.

**Implementation**: Parse DuckDB's `SUMMARIZE` output into typed result.

#### Result Types

```python
# In types.py

@dataclass(frozen=True)
class ColumnSummary:
    """Statistical summary of a single column.

    Contains aggregated statistics from DuckDB's SUMMARIZE command.
    Numeric-only fields (avg, std, quartiles) are None for non-numeric columns.
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
    """Approximate count of distinct values (using HyperLogLog)."""

    avg: float | None
    """Mean value (None for non-numeric columns)."""

    std: float | None
    """Standard deviation (None for non-numeric columns)."""

    q25: Any
    """25th percentile value (None for non-numeric columns)."""

    q50: Any
    """Median / 50th percentile value (None for non-numeric columns)."""

    q75: Any
    """75th percentile value (None for non-numeric columns)."""

    count: int
    """Number of non-null values."""

    null_percentage: float
    """Percentage of null values (0.0 to 100.0)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
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

    Wraps DuckDB's SUMMARIZE command output with typed access.
    """

    table: str
    """Name of the summarized table."""

    row_count: int
    """Total number of rows in the table."""

    columns: list[ColumnSummary]
    """Per-column statistics."""

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with one row per column.

        Columns: column_name, column_type, min, max, approx_unique,
                 avg, std, q25, q50, q75, count, null_percentage
        """
        if self._df_cache is not None:
            return self._df_cache

        rows = [col.to_dict() for col in self.columns]
        result_df = pd.DataFrame(rows) if rows else pd.DataFrame()

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "table": self.table,
            "row_count": self.row_count,
            "columns": [col.to_dict() for col in self.columns],
        }
```

#### Workspace Method

```python
def summarize(self, table: str) -> SummaryResult:
    """Get statistical summary of all columns in a table.

    Uses DuckDB's SUMMARIZE command to compute min/max, quartiles,
    null percentage, and approximate distinct counts for each column.

    Args:
        table: Table name to summarize.

    Returns:
        SummaryResult with per-column statistics and total row count.

    Raises:
        TableNotFoundError: If table doesn't exist.

    Example:
        ```python
        result = ws.summarize("events")
        result.row_count         # 1234567
        result.columns[0].null_percentage  # 0.5
        result.df                # Full summary as DataFrame
        ```
    """
    # Validate table exists
    self._storage.get_schema(table)

    # Get row count
    row_count = self._storage.execute_scalar(f"SELECT COUNT(*) FROM {table}")

    # Get summary - DuckDB SUMMARIZE returns a table with one row per column
    summary_df = self._storage.execute_df(f"SUMMARIZE {table}")

    # Parse into ColumnSummary objects
    columns: list[ColumnSummary] = []
    for _, row in summary_df.iterrows():
        columns.append(ColumnSummary(
            column_name=row["column_name"],
            column_type=row["column_type"],
            min=row["min"],
            max=row["max"],
            approx_unique=int(row["approx_unique"]),
            avg=row.get("avg"),  # None for non-numeric
            std=row.get("std"),
            q25=row.get("q25"),
            q50=row.get("q50"),
            q75=row.get("q75"),
            count=int(row["count"]),
            null_percentage=float(row["null_percentage"]),
        ))

    return SummaryResult(table=table, row_count=row_count, columns=columns)
```

**DuckDB SUMMARIZE Output Format**:
```
┌─────────────┬─────────────┬─────────┬─────────┬───────────────┬─────────┬─────────┬─────────┬─────────┬─────────┬───────────────┬───────┐
│ column_name │ column_type │   min   │   max   │ approx_unique │   avg   │   std   │   q25   │   q50   │   q75   │ null_percentage│ count │
├─────────────┼─────────────┼─────────┼─────────┼───────────────┼─────────┼─────────┼─────────┼─────────┼─────────┼───────────────┼───────┤
│ event_name  │ VARCHAR     │ Click   │ View    │            47 │ NULL    │ NULL    │ NULL    │ NULL    │ NULL    │           0.0 │ 10000 │
│ event_time  │ TIMESTAMP   │ 2024-01 │ 2024-01 │         10000 │ NULL    │ NULL    │ NULL    │ NULL    │ NULL    │           0.0 │ 10000 │
│ distinct_id │ VARCHAR     │ user1   │ user999 │           892 │ NULL    │ NULL    │ NULL    │ NULL    │ NULL    │           0.0 │ 10000 │
└─────────────┴─────────────┴─────────┴─────────┴───────────────┴─────────┴─────────┴─────────┴─────────┴─────────┴───────────────┴───────┘
```

**Files to Modify**:
| File | Changes |
|------|---------|
| `src/mixpanel_data/types.py` | Add `ColumnSummary`, `SummaryResult` |
| `src/mixpanel_data/workspace.py` | Add `summarize()` method |
| `tests/unit/test_types.py` | Add tests for new types |
| `tests/unit/test_workspace.py` | Add tests for `summarize()` |

**Tests**:
```python
def test_summarize_returns_all_columns():
    """Summarize returns stats for each column."""
    # Create table with known schema
    # Call ws.summarize("table")
    # Assert len(result.columns) matches column count

def test_summarize_numeric_columns_have_stats():
    """Numeric columns have avg, std, quartiles."""
    # Create table with numeric column
    # Assert result.columns[n].avg is not None

def test_summarize_string_columns_null_numeric_stats():
    """String columns have None for numeric stats."""
    # Create table with VARCHAR column
    # Assert result.columns[n].avg is None

def test_summarize_row_count_correct():
    """Row count matches actual table size."""
    # Create table with 100 rows
    # Assert result.row_count == 100

def test_summarize_df_property():
    """df property returns DataFrame with correct columns."""
    # Call ws.summarize("table")
    # Assert result.df columns match expected
```

---

## Phase 2: Core Product Analytics

### Feature 3: `event_breakdown(table)`

**User Story**: An analyst fetched a month of events and wants to understand what's in there—which events, how many, how many users, when.

**Implementation**: Custom SQL aggregation returning typed result.

#### Result Types

```python
# In types.py

@dataclass(frozen=True)
class EventStats:
    """Statistics for a single event type.

    Contains count, unique users, date range, and percentage of total.
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
        """Serialize for JSON output."""
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

    Provides a summary of event types with counts, user counts,
    and temporal range for each event.
    """

    table: str
    """Name of the analyzed table."""

    total_events: int
    """Total number of events in the table."""

    total_users: int
    """Total distinct users across all events."""

    date_range: tuple[datetime, datetime]
    """(earliest, latest) event timestamps in the table."""

    events: list[EventStats]
    """Per-event statistics, ordered by count descending."""

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame with one row per event type.

        Columns: event_name, count, unique_users, first_seen,
                 last_seen, pct_of_total
        """
        if self._df_cache is not None:
            return self._df_cache

        rows = [e.to_dict() for e in self.events]
        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=[
                "event_name", "count", "unique_users",
                "first_seen", "last_seen", "pct_of_total"
            ])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "table": self.table,
            "total_events": self.total_events,
            "total_users": self.total_users,
            "date_range": [
                self.date_range[0].isoformat(),
                self.date_range[1].isoformat(),
            ],
            "events": [e.to_dict() for e in self.events],
        }
```

#### Workspace Method

```python
def event_breakdown(self, table: str) -> EventBreakdownResult:
    """Analyze event distribution in a table.

    Computes per-event counts, unique users, date ranges, and
    percentage of total for each event type.

    Args:
        table: Table name containing events (must have event_name,
               event_time, and distinct_id columns).

    Returns:
        EventBreakdownResult with per-event statistics.

    Raises:
        TableNotFoundError: If table doesn't exist.
        QueryError: If table lacks required columns.

    Example:
        ```python
        breakdown = ws.event_breakdown("events")
        breakdown.total_events           # 1234567
        breakdown.events[0].event_name   # "Page View"
        breakdown.events[0].pct_of_total # 45.2
        ```
    """
    # Validate table exists and has required columns
    schema = self._storage.get_schema(table)
    required = {"event_name", "event_time", "distinct_id"}
    actual = {col.name for col in schema.columns}
    missing = required - actual
    if missing:
        raise QueryError(
            f"event_breakdown() requires columns {required}, "
            f"but {table} is missing: {missing}"
        )

    # Get totals
    totals = self._storage.execute_rows(f"""
        SELECT
            COUNT(*) as total_events,
            COUNT(DISTINCT distinct_id) as total_users,
            MIN(event_time) as min_time,
            MAX(event_time) as max_time
        FROM {table}
    """)[0]

    total_events = totals[0]
    total_users = totals[1]
    date_range = (totals[2], totals[3])

    # Get per-event breakdown
    rows = self._storage.execute_rows(f"""
        SELECT
            event_name,
            COUNT(*) as count,
            COUNT(DISTINCT distinct_id) as unique_users,
            MIN(event_time) as first_seen,
            MAX(event_time) as last_seen,
            COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as pct_of_total
        FROM {table}
        GROUP BY event_name
        ORDER BY count DESC
    """)

    events = [
        EventStats(
            event_name=row[0],
            count=row[1],
            unique_users=row[2],
            first_seen=row[3],
            last_seen=row[4],
            pct_of_total=round(row[5], 2),
        )
        for row in rows
    ]

    return EventBreakdownResult(
        table=table,
        total_events=total_events,
        total_users=total_users,
        date_range=date_range,
        events=events,
    )
```

**Files to Modify**:
| File | Changes |
|------|---------|
| `src/mixpanel_data/types.py` | Add `EventStats`, `EventBreakdownResult` |
| `src/mixpanel_data/workspace.py` | Add `event_breakdown()` method |
| `tests/unit/test_types.py` | Add tests for new types |
| `tests/unit/test_workspace.py` | Add tests for `event_breakdown()` |

**Tests**:
```python
def test_event_breakdown_returns_all_events():
    """Breakdown includes all unique event names."""
    # Create table with 3 distinct events
    # Assert len(result.events) == 3

def test_event_breakdown_counts_correct():
    """Event counts match actual data."""
    # Create table with known counts per event
    # Assert counts match

def test_event_breakdown_pct_sums_to_100():
    """Percentages sum to approximately 100."""
    # Create table with events
    # Assert sum of pct_of_total ≈ 100

def test_event_breakdown_ordered_by_count():
    """Events ordered by count descending."""
    # Create table with varying event counts
    # Assert result.events[0].count >= result.events[1].count

def test_event_breakdown_date_range_correct():
    """Date range matches actual min/max timestamps."""
    # Create table with known date range
    # Assert date_range matches

def test_event_breakdown_missing_columns_raises():
    """Raises QueryError with clear message if required columns missing."""
    # Create table without event_name column
    # Call ws.event_breakdown("table")
    # Assert raises QueryError with message mentioning missing columns
```

---

### Feature 4: `property_keys(table, event=None)`

**User Story**: An agent sees a JSON properties column and needs to know what keys exist before querying them.

**Implementation**: Extract distinct keys from JSON column using DuckDB's `json_keys()`.

#### Workspace Method

```python
def property_keys(
    self,
    table: str,
    event: str | None = None,
) -> list[str]:
    """List all JSON property keys in a table.

    Extracts distinct keys from the 'properties' JSON column.
    Useful for discovering queryable fields in event properties.

    Args:
        table: Table name with a 'properties' JSON column.
        event: Optional event name to filter by. If provided, only
               returns keys present in events of that type.

    Returns:
        Alphabetically sorted list of property key names.

    Raises:
        TableNotFoundError: If table doesn't exist.
        QueryError: If table lacks 'properties' column.

    Example:
        ```python
        # All keys across all events
        ws.property_keys("events")
        # ['$browser', '$city', 'page', 'referrer', 'user_plan']

        # Keys for specific event type
        ws.property_keys("events", event="Purchase")
        # ['amount', 'currency', 'product_id', 'quantity']
        ```
    """
    # Validate table exists
    self._storage.get_schema(table)

    if event is not None:
        query = f"""
            SELECT DISTINCT unnest(json_keys(properties)) as key
            FROM {table}
            WHERE event_name = ?
            ORDER BY key
        """
        # Use parameterized query for safety
        result = self._storage.connection.execute(query, [event]).fetchall()
    else:
        query = f"""
            SELECT DISTINCT unnest(json_keys(properties)) as key
            FROM {table}
            ORDER BY key
        """
        result = self._storage.execute_rows(query)

    return [row[0] for row in result]
```

**Notes on Implementation**:
- DuckDB's `json_keys()` returns a list of keys for each JSON object
- `unnest()` expands the list so we can aggregate across all rows
- Parameterized query used for event filter to prevent SQL injection
- Returns empty list if no properties column or no keys found

**Files to Modify**:
| File | Changes |
|------|---------|
| `src/mixpanel_data/workspace.py` | Add `property_keys()` method |
| `tests/unit/test_workspace.py` | Add tests for `property_keys()` |

**Tests**:
```python
def test_property_keys_returns_all_keys():
    """Returns all distinct keys from properties column."""
    # Create table with JSON properties {"a": 1, "b": 2}
    # Assert result contains ["a", "b"]

def test_property_keys_with_event_filter():
    """Filters keys to specific event type."""
    # Create table with different keys per event
    # Assert filtered result only contains keys from that event

def test_property_keys_sorted_alphabetically():
    """Keys returned in alphabetical order."""
    # Create table with keys in random order
    # Assert result is sorted

def test_property_keys_empty_properties():
    """Returns empty list for empty properties."""
    # Create table with empty JSON {}
    # Assert result == []

def test_property_keys_missing_column_raises():
    """Raises QueryError if properties column missing."""
    # Create table without properties column
    # Assert raises QueryError
```

---

## Phase 3: Deep Column Analysis

### Feature 5: `column_stats(table, column)`

**User Story**: An analyst sees a column in `summarize()` output with high cardinality and wants to dig deeper—top values, distribution, nulls.

**Implementation**: Multiple queries bundled into comprehensive column analysis.

#### Result Type

```python
# In types.py

@dataclass(frozen=True)
class ColumnStatsResult:
    """Deep statistical analysis of a single column.

    Combines multiple analyses: basic stats, null analysis,
    cardinality, and top values.
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

    top_values: list[tuple[Any, int]]
    """Most frequent (value, count) pairs, ordered by count descending."""

    # Numeric-only fields (None for non-numeric columns)
    min: float | None
    """Minimum value (None for non-numeric)."""

    max: float | None
    """Maximum value (None for non-numeric)."""

    mean: float | None
    """Mean value (None for non-numeric)."""

    std: float | None
    """Standard deviation (None for non-numeric)."""

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Convert top_values to DataFrame.

        Columns: value, count
        """
        if self._df_cache is not None:
            return self._df_cache

        rows = [{"value": v, "count": c} for v, c in self.top_values]
        result_df = (
            pd.DataFrame(rows)
            if rows
            else pd.DataFrame(columns=["value", "count"])
        )

        object.__setattr__(self, "_df_cache", result_df)
        return result_df

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "table": self.table,
            "column": self.column,
            "dtype": self.dtype,
            "count": self.count,
            "null_count": self.null_count,
            "null_pct": self.null_pct,
            "unique_count": self.unique_count,
            "unique_pct": self.unique_pct,
            "top_values": [[v, c] for v, c in self.top_values],
            "min": self.min,
            "max": self.max,
            "mean": self.mean,
            "std": self.std,
        }
```

#### Workspace Method

```python
def column_stats(
    self,
    table: str,
    column: str,
    *,
    top_n: int = 10,
) -> ColumnStatsResult:
    """Get detailed statistics for a single column.

    Performs deep analysis including null rates, cardinality,
    top values, and numeric statistics (for numeric columns).

    The column parameter supports JSON path expressions for
    analyzing properties stored in JSON columns:
    - `properties->>'$.country'` for string extraction
    - `CAST(properties->>'$.amount' AS DOUBLE)` for numeric

    Args:
        table: Table name to analyze.
        column: Column name or expression to analyze.
        top_n: Number of top values to return (default: 10).

    Returns:
        ColumnStatsResult with comprehensive column statistics.

    Raises:
        TableNotFoundError: If table doesn't exist.
        QueryError: If column expression is invalid.

    Example:
        ```python
        # Analyze standard column
        stats = ws.column_stats("events", "event_name")
        stats.unique_count      # 47
        stats.top_values[:3]    # [('Page View', 45230), ('Click', 23451), ...]

        # Analyze JSON property
        stats = ws.column_stats("events", "properties->>'$.country'")
        ```
    """
    # Validate table exists
    self._storage.get_schema(table)

    # Determine column type
    type_query = f"SELECT typeof({column}) FROM {table} LIMIT 1"
    try:
        dtype = self._storage.execute_scalar(type_query)
    except Exception:
        dtype = "UNKNOWN"

    # Basic stats query
    stats = self._storage.execute_rows(f"""
        SELECT
            COUNT({column}) as count,
            COUNT(*) - COUNT({column}) as null_count,
            (COUNT(*) - COUNT({column})) * 100.0 / COUNT(*) as null_pct,
            approx_count_distinct({column}) as unique_count
        FROM {table}
    """)[0]

    count = stats[0]
    null_count = stats[1]
    null_pct = round(stats[2], 2)
    unique_count = stats[3]
    unique_pct = round(unique_count * 100.0 / count, 2) if count > 0 else 0.0

    # Top values
    top_values_query = f"""
        SELECT {column} as value, COUNT(*) as cnt
        FROM {table}
        WHERE {column} IS NOT NULL
        GROUP BY {column}
        ORDER BY cnt DESC
        LIMIT {top_n}
    """
    top_rows = self._storage.execute_rows(top_values_query)
    top_values = [(row[0], row[1]) for row in top_rows]

    # Numeric stats (only if column appears numeric)
    min_val = max_val = mean_val = std_val = None
    is_numeric = dtype.upper() in (
        "TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT",
        "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC",
    )

    if is_numeric:
        numeric_stats = self._storage.execute_rows(f"""
            SELECT
                MIN({column}),
                MAX({column}),
                AVG({column}),
                STDDEV({column})
            FROM {table}
        """)[0]
        min_val = numeric_stats[0]
        max_val = numeric_stats[1]
        mean_val = numeric_stats[2]
        std_val = numeric_stats[3]

    return ColumnStatsResult(
        table=table,
        column=column,
        dtype=dtype,
        count=count,
        null_count=null_count,
        null_pct=null_pct,
        unique_count=unique_count,
        unique_pct=unique_pct,
        top_values=top_values,
        min=min_val,
        max=max_val,
        mean=mean_val,
        std=std_val,
    )
```

**Files to Modify**:
| File | Changes |
|------|---------|
| `src/mixpanel_data/types.py` | Add `ColumnStatsResult` |
| `src/mixpanel_data/workspace.py` | Add `column_stats()` method |
| `tests/unit/test_types.py` | Add tests for `ColumnStatsResult` |
| `tests/unit/test_workspace.py` | Add tests for `column_stats()` |

**Tests**:
```python
def test_column_stats_counts_correct():
    """Count and null_count are accurate."""
    # Create table with known null distribution
    # Assert count and null_count match

def test_column_stats_top_values_ordered():
    """Top values ordered by count descending."""
    # Create table with known value frequencies
    # Assert top_values order matches frequency

def test_column_stats_numeric_has_stats():
    """Numeric columns have min/max/mean/std."""
    # Create table with numeric column
    # Assert min, max, mean, std are not None

def test_column_stats_string_no_numeric_stats():
    """String columns have None for numeric stats."""
    # Create table with string column
    # Assert min, max, mean, std are None

def test_column_stats_json_path_expression():
    """JSON path expressions work for properties."""
    # Create table with JSON properties
    # Call column_stats with properties->>'$.key'
    # Assert returns valid stats

def test_column_stats_top_n_parameter():
    """top_n parameter limits returned values."""
    # Create table with many distinct values
    # Call column_stats with top_n=5
    # Assert len(top_values) == 5
```

---

## CLI Integration

### New Commands in `inspect` Group

Add 5 new commands to `src/mixpanel_data/cli/commands/inspect.py`:

```python
@inspect_app.command("sample")
@handle_errors
def inspect_sample(
    ctx: typer.Context,
    table: Annotated[str, typer.Option("--table", "-t", help="Table name.")],
    n: Annotated[int, typer.Option("--rows", "-n", help="Number of rows.")] = 10,
    format: FormatOption = "table",
) -> None:
    """Show random sample rows from a table.

    Returns representative rows using reservoir sampling.
    Useful for inspecting data structure before writing queries.

    [dim]Examples:[/dim]
      mp inspect sample -t events
      mp inspect sample -t events -n 5 --format json
    """
    workspace = get_workspace(ctx)
    df = workspace.sample(table, n=n)
    output_result(ctx, df.to_dict(orient="records"), format=format)


@inspect_app.command("summarize")
@handle_errors
def inspect_summarize(
    ctx: typer.Context,
    table: Annotated[str, typer.Option("--table", "-t", help="Table name.")],
    format: FormatOption = "table",
) -> None:
    """Show statistical summary of all columns.

    Displays min/max, quartiles, null rates, and cardinality
    for each column using DuckDB's SUMMARIZE command.

    [dim]Examples:[/dim]
      mp inspect summarize -t events
      mp inspect summarize -t events --format json
    """
    workspace = get_workspace(ctx)
    result = workspace.summarize(table)
    output_result(ctx, result.to_dict(), format=format)


@inspect_app.command("breakdown")
@handle_errors
def inspect_breakdown(
    ctx: typer.Context,
    table: Annotated[str, typer.Option("--table", "-t", help="Table name.")],
    format: FormatOption = "table",
) -> None:
    """Show event distribution in a table.

    Displays counts, unique users, date ranges, and percentages
    for each event type. Requires event_name, event_time, and
    distinct_id columns.

    [dim]Examples:[/dim]
      mp inspect breakdown -t events
      mp inspect breakdown -t events --format json
    """
    workspace = get_workspace(ctx)
    result = workspace.event_breakdown(table)
    output_result(ctx, result.to_dict(), format=format)


@inspect_app.command("keys")
@handle_errors
def inspect_keys(
    ctx: typer.Context,
    table: Annotated[str, typer.Option("--table", "-t", help="Table name.")],
    event: Annotated[
        str | None,
        typer.Option("--event", "-e", help="Filter to specific event.")
    ] = None,
    format: FormatOption = "json",
) -> None:
    """List JSON property keys in a table.

    Extracts all distinct keys from the properties JSON column.
    Optionally filter to keys present in a specific event type.

    [dim]Examples:[/dim]
      mp inspect keys -t events
      mp inspect keys -t events -e "Purchase"
      mp inspect keys -t events --format table
    """
    workspace = get_workspace(ctx)
    keys = workspace.property_keys(table, event=event)
    output_result(ctx, keys, format=format)


@inspect_app.command("column")
@handle_errors
def inspect_column(
    ctx: typer.Context,
    table: Annotated[str, typer.Option("--table", "-t", help="Table name.")],
    column: Annotated[str, typer.Option("--column", "-c", help="Column name or expression.")],
    top_n: Annotated[int, typer.Option("--top", help="Number of top values.")] = 10,
    format: FormatOption = "json",
) -> None:
    """Show detailed statistics for a column.

    Analyzes null rates, cardinality, top values, and numeric
    stats. Supports JSON path expressions like properties->>'$.key'.

    [dim]Examples:[/dim]
      mp inspect column -t events -c event_name
      mp inspect column -t events -c "properties->>'$.country'"
      mp inspect column -t events -c distinct_id --top 20
    """
    workspace = get_workspace(ctx)
    result = workspace.column_stats(table, column, top_n=top_n)
    output_result(ctx, result.to_dict(), format=format)
```

**Files to Modify**:
| File | Changes |
|------|---------|
| `src/mixpanel_data/cli/commands/inspect.py` | Add 5 new commands |
| `tests/cli/test_inspect.py` | Add CLI tests |

---

## Implementation Order

| Phase | Feature | Estimated Effort | Dependencies |
|-------|---------|-----------------|--------------|
| 1a | `sample()` | ~1 hour | None |
| 1b | `summarize()` | ~2 hours | ColumnSummary, SummaryResult types |
| 2a | `event_breakdown()` | ~3 hours | EventStats, EventBreakdownResult types |
| 2b | `property_keys()` | ~1 hour | None |
| 3 | `column_stats()` | ~3 hours | ColumnStatsResult type |
| 4 | CLI commands | ~2 hours | All above |

**Total**: ~12 hours of implementation

---

## Testing Strategy

### Unit Tests

Each feature requires:
1. **Happy path**: Normal usage returns expected results
2. **Edge cases**: Empty tables, single row, null values
3. **Error cases**: Missing table, invalid columns, missing required columns
4. **Type verification**: Results are correct types, df property works

### Integration Tests

Create integration tests that exercise the full workflow:

```python
def test_introspection_workflow():
    """Test typical exploration workflow."""
    with Workspace.memory() as ws:
        # Simulate fetched data
        ws.connection.execute("""
            CREATE TABLE events AS
            SELECT * FROM (VALUES
                ('PageView', TIMESTAMP '2024-01-01', 'user1', '{"page": "/home"}'),
                ('Click', TIMESTAMP '2024-01-02', 'user1', '{"button": "signup"}'),
                ('PageView', TIMESTAMP '2024-01-03', 'user2', '{"page": "/pricing"}')
            ) AS t(event_name, event_time, distinct_id, properties)
        """)

        # Sample
        sample = ws.sample("events", n=2)
        assert len(sample) == 2

        # Summarize
        summary = ws.summarize("events")
        assert summary.row_count == 3

        # Event breakdown
        breakdown = ws.event_breakdown("events")
        assert breakdown.total_events == 3
        assert len(breakdown.events) == 2  # PageView, Click

        # Property keys
        keys = ws.property_keys("events")
        assert "page" in keys
        assert "button" in keys

        # Column stats
        stats = ws.column_stats("events", "event_name")
        assert stats.unique_count == 2
```

---

## Export Updates

Update `src/mixpanel_data/__init__.py` to export new types:

```python
from mixpanel_data.types import (
    # ... existing exports ...
    ColumnSummary,
    SummaryResult,
    EventStats,
    EventBreakdownResult,
    ColumnStatsResult,
)
```

---

## Success Criteria

| ID | Criterion |
|----|-----------|
| SC-001 | `sample()` returns requested number of random rows |
| SC-002 | `summarize()` returns typed statistics for all columns |
| SC-003 | `event_breakdown()` accurately counts events and users |
| SC-004 | `property_keys()` discovers all JSON keys |
| SC-005 | `column_stats()` handles both regular and JSON path columns |
| SC-006 | All result types have working `.df` property |
| SC-007 | All result types serialize correctly via `to_dict()` |
| SC-008 | CLI commands work with all output formats |
| SC-009 | All methods raise appropriate errors for missing tables |
| SC-010 | Tests achieve >90% coverage of new code |

---

## Future Considerations

Not in scope for this implementation, but worth noting:

1. **Caching**: Summary results could be cached per table, invalidated on table modification
2. **Progress reporting**: For large tables, summarize() could report progress
3. **Sampling strategies**: Could add stratified sampling option
4. **Export**: Could add `to_csv()`, `to_parquet()` methods to result types
5. **Visualization**: Could add histogram rendering for CLI (ASCII charts)
