# Introspection Feature Proposal

> Proposed features for mixpanel_data based on research findings. See [introspection-research.md](introspection-research.md) for background.

## Decision Criteria

Each feature evaluated against:
1. **Utility**: Does this genuinely help analysts/agents discover insights faster or avoid mistakes?
2. **Effort-to-value**: Is this a thin wrapper (low effort) or custom implementation (higher bar)?
3. **Fit**: Does it align with the existing API patterns in the codebase?
4. **Agent-friendliness**: Would an AI agent exploring unfamiliar data benefit from this?

---

## Quick Wins

Features that thin-wrap DuckDB built-ins with minimal code.

### 1. `summarize(table: str) → SummaryResult`

**User story:** An agent exploring an unfamiliar events table wants instant statistical context before writing queries.

**One-liner:** Expose DuckDB's `SUMMARIZE` command as a typed result.

```python
@dataclass(frozen=True)
class ColumnSummary:
    column_name: str
    column_type: str
    min: Any
    max: Any
    approx_unique: int
    avg: float | None
    std: float | None
    q25: Any
    q50: Any
    q75: Any
    count: int
    null_percentage: float

@dataclass(frozen=True)
class SummaryResult:
    table: str
    columns: list[ColumnSummary]

    @cached_property
    def df(self) -> pd.DataFrame: ...

# Usage
result = ws.summarize("events")
result.df  # Full summary as DataFrame
result.columns[0].null_percentage  # Typed access
```

**Justification:** Research showed `SUMMARIZE` returns exactly what analysts need first—min/max, quartiles, null rates, approximate cardinality. Zero implementation beyond parsing output.

---

### 2. `sample(table: str, n: int = 10) → pd.DataFrame`

**User story:** An agent wants to see actual data rows before querying, to understand property structure and value formats.

**One-liner:** Return n random rows from a table.

```python
# Usage
ws.sample("events")  # 10 random rows
ws.sample("events", n=5)  # 5 random rows

# Implementation: literally one line
def sample(self, table: str, n: int = 10) -> pd.DataFrame:
    return self.sql(f"SELECT * FROM {table} USING SAMPLE {n}")
```

**Justification:** DuckDB's `USING SAMPLE` is more representative than `LIMIT`. Agents need to see real data to understand JSON property shapes. Trivial to implement.

---

## High-Value Additions

Worth building despite requiring more implementation.

### 3. `event_breakdown(table: str) → EventBreakdownResult`

**User story:** An analyst fetched a month of events and wants to understand what's in there—which events, how many, how many users, when.

**Problem solved:** Currently requires writing a 10-line GROUP BY query every time. This is the #1 first question for any event dataset.

```python
@dataclass(frozen=True)
class EventStats:
    event_name: str
    count: int
    unique_users: int
    first_seen: datetime
    last_seen: datetime
    pct_of_total: float

@dataclass(frozen=True)
class EventBreakdownResult:
    table: str
    total_events: int
    total_users: int
    date_range: tuple[datetime, datetime]
    events: list[EventStats]

    @cached_property
    def df(self) -> pd.DataFrame: ...

# Usage
breakdown = ws.event_breakdown("events")
breakdown.total_events  # 1,234,567
breakdown.events[0].event_name  # "Page View"
breakdown.events[0].pct_of_total  # 45.2
```

**Implementation approach:**
```sql
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
```

**Justification:** Research identified event distribution as the foundational product analytics pattern. Every exploration starts here. The query is standard but tedious to type repeatedly.

---

### 4. `property_keys(table: str, event: str | None = None) → list[str]`

**User story:** An agent sees JSON properties column and needs to know what keys exist before querying them.

**Problem solved:** Remote `properties(event)` shows what Mixpanel knows about, but local data may differ. No way to discover keys in fetched JSON without manual inspection.

```python
# Usage
ws.property_keys("events")  # All keys across all events
# ['$browser', '$city', '$device', 'page', 'referrer', 'user_plan', ...]

ws.property_keys("events", event="Purchase")  # Keys for specific event
# ['$browser', 'amount', 'currency', 'product_id', 'quantity', ...]
```

**Implementation approach:**
```sql
-- Extract all keys from JSON properties
SELECT DISTINCT unnest(json_keys(properties)) as key
FROM {table}
WHERE event_name = ? OR ? IS NULL
ORDER BY key
```

**Justification:** Research showed JSON property storage is a core design decision. Agents exploring unfamiliar data need to bridge from seeing `properties JSON` column to knowing queryable fields. This mirrors the remote `properties()` API for local data.

---

### 5. `column_stats(table: str, column: str) → ColumnStatsResult`

**User story:** An analyst sees a column in `summarize()` output with high cardinality and wants to dig deeper—top values, distribution, nulls.

**Problem solved:** Deep column analysis requires 3-4 separate queries. This bundles common follow-up questions.

```python
@dataclass(frozen=True)
class ColumnStatsResult:
    table: str
    column: str
    dtype: str
    count: int
    null_count: int
    null_pct: float
    unique_count: int  # approx
    unique_pct: float
    top_values: list[tuple[Any, int]]  # (value, count) pairs

    # For numeric columns only
    min: float | None
    max: float | None
    mean: float | None
    std: float | None

    @cached_property
    def df(self) -> pd.DataFrame: ...

# Usage
stats = ws.column_stats("events", "event_name")
stats.unique_count  # 47
stats.top_values[:3]  # [('Page View', 45230), ('Click', 23451), ...]

# Works with JSON extraction
stats = ws.column_stats("events", "properties->>'$.country'")
```

**Implementation approach:**
- Single query with multiple aggregates: `COUNT`, `COUNT DISTINCT`, `approx_count_distinct`, `MIN`, `MAX`, `AVG`, `STDDEV`
- Second query for top values: `GROUP BY ... ORDER BY COUNT(*) DESC LIMIT 10`
- Type detection for conditional numeric stats

**Justification:** Research on ydata-profiling showed per-column deep dives are the natural next step after summary. The "top values" pattern is universal. Accepting JSON path expressions makes this work with Mixpanel's property model.

---

## Considered But Rejected

### HTML/Rich Profiling Reports

**Why skip:** ydata-profiling generates beautiful HTML reports. But mixpanel_data targets CLI/agent workflows where structured data beats rendered output. Agents can't parse HTML. The `summarize()` DataFrame provides the same information in a usable format.

### Data Validation/Expectations

**Why skip:** Great Expectations solves a different problem—CI/CD pipeline validation with persistent expectations. Our users are doing exploratory analysis, not enforcing contracts. If needed later, it's a separate concern that shouldn't pollute the exploration API.

### Histogram Visualization

**Why skip:** DuckDB's `histogram()` aggregate returns a MAP, but displaying histograms requires rendering decisions (bin count, ASCII vs rich). Agents don't need visualizations—they need numbers. Users can query `histogram()` directly via `sql()` if needed.

### Property Type Inference

**Why skip:** Detecting whether `properties->>'$.user_id'` is "really" numeric requires sampling and heuristics. High complexity, low marginal value over just showing top values and letting the human/agent infer.

### Anomaly Detection

**Why skip:** Detecting event volume anomalies or property drift requires baseline definitions and statistical thresholds. This is valuable but crosses from "introspection" into "monitoring"—a different product.

---

## Implementation Order

| Order | Feature | Rationale |
|-------|---------|-----------|
| 1 | `sample()` | 5 lines of code, immediately useful, validates the pattern |
| 2 | `summarize()` | Thin wrapper, high value, tests result type pattern |
| 3 | `event_breakdown()` | Core product analytics use case, moderate effort |
| 4 | `property_keys()` | Unlocks JSON exploration, pairs with `column_stats()` |
| 5 | `column_stats()` | Most complex, but builds on patterns from earlier features |

**Phase 1 (Quick):** `sample()` + `summarize()` — can ship together, minimal risk

**Phase 2 (Core):** `event_breakdown()` + `property_keys()` — the Mixpanel-specific value-add

**Phase 3 (Polish):** `column_stats()` — completes the exploration workflow

---

## API Surface Summary

```python
# After implementation, exploration workflow looks like:
ws = Workspace()
ws.fetch_events("jan", from_date="2024-01-01", to_date="2024-01-31")

ws.sample("jan")                    # See actual data rows
ws.summarize("jan")                 # Statistical overview
ws.event_breakdown("jan")           # What events, how many, who
ws.property_keys("jan", "Purchase") # What can I query in properties?
ws.column_stats("jan", "properties->>'$.amount'")  # Deep dive on one field

# Then do actual analysis
ws.sql("SELECT ...")
```

---

## Result Types Summary

New types to add to `types.py`:

| Type | Fields |
|------|--------|
| `ColumnSummary` | column_name, column_type, min, max, approx_unique, avg, std, q25, q50, q75, count, null_percentage |
| `SummaryResult` | table, columns: list[ColumnSummary], df property |
| `EventStats` | event_name, count, unique_users, first_seen, last_seen, pct_of_total |
| `EventBreakdownResult` | table, total_events, total_users, date_range, events: list[EventStats], df property |
| `ColumnStatsResult` | table, column, dtype, count, null_count, null_pct, unique_count, unique_pct, top_values, min, max, mean, std, df property |

All follow existing patterns: frozen dataclasses with lazy `.df` property.
