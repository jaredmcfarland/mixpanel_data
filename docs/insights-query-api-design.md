# Insights Query API Design

Design for `Workspace.query()` — a typed Python method that lets LLM agents execute common Mixpanel insights queries without constructing raw bookmark JSON.

---

## 1. Query Taxonomy

The research identified 14 common query patterns. `query()` targets the ones that are currently painful or impossible without raw bookmark JSON construction, while remaining trivial for patterns already well-served by existing methods.

| # | Pattern | Current Difficulty | `query()` Coverage | Priority |
|---|---------|-------------------|-------------------|----------|
| 1 | Event count over time | Easy (`segmentation`) | Yes — simplest case | P0 |
| 2 | Unique users over time | Easy (`segmentation`) | Yes — `math="unique"` | P0 |
| 3 | Segmentation by property | Easy (`segmentation`) | Yes — `group_by=` | P0 |
| 4 | Filtered aggregation | Medium | Yes — `where=` | P0 |
| 5 | Multi-metric comparison | **Painful** | Yes — `events=[...]` | P0 |
| 6 | Conversion rate formula | **Painful** | Yes — `formula=` | P0 |
| 7 | Property aggregation | Medium | Yes — `math="average"` + `math_property=` | P0 |
| 8 | DAU / WAU / MAU | **Impossible** | Yes — `math="dau"` | P0 |
| 9 | Per-user aggregation | **Painful** | Yes — `per_user=` | P1 |
| 10 | Ad-hoc funnel | **Painful** | No — separate concern | P2 (future) |
| 11 | Retention curve | Easy (`retention`) | No — use existing method | — |
| 12 | Rolling average | **Impossible** | Yes — `rolling=7` | P1 |
| 13 | Multiple breakdowns | **Painful** | Yes — `group_by=[...]` | P1 |
| 14 | Cohort comparison | **Painful** | No — needs cohort behavior type | P2 (future) |

**Coverage summary:** `query()` handles patterns 1-9 and 12-13, which constitute the vast majority of insights queries. Patterns 10, 11, and 14 are structurally different (funnels, retention, cohort behaviors) and are better served by dedicated methods.

---

## 2. Method Signature

```python
def query(
    self,
    events: str | Metric | Sequence[str | Metric],
    *,
    # Time range
    from_date: str | None = None,
    to_date: str | None = None,
    last: int = 30,
    unit: Literal["hour", "day", "week", "month", "quarter"] = "day",

    # Aggregation defaults (apply to plain-string events)
    math: MathType = "total",
    math_property: str | None = None,
    per_user: PerUserAggregation | None = None,

    # Breakdown
    group_by: str | GroupBy | list[str | GroupBy] | None = None,

    # Filters
    where: Filter | list[Filter] | None = None,

    # Formula
    formula: str | None = None,
    formula_label: str | None = None,

    # Analysis mode
    rolling: int | None = None,
    cumulative: bool = False,

    # Result shape
    mode: Literal["timeseries", "total", "table"] = "timeseries",
) -> QueryResult:
```

**Minimum viable call:**

```python
result = ws.query("Login")
# → total Login events per day for the last 30 days
```

---

## 3. Supporting Types

### 3.1 `Metric`

Encapsulates an event name with its aggregation settings. Plain strings are shorthand for `Metric(event_name)` with defaults inherited from the top-level `math`/`math_property`/`per_user` parameters.

```python
@dataclass(frozen=True)
class Metric:
    """A metric specification for Workspace.query().

    Use plain event name strings when default aggregation (total count)
    suffices. Use Metric when you need per-event control over aggregation,
    property math, per-user aggregation, or per-metric filters.

    Args:
        event: Mixpanel event name.
        math: Aggregation function. Default "total" (event count).
        property: Property name for property-based math
            (required when math is average/sum/min/max/median/p25/p75/p90/p99).
        per_user: Per-user pre-aggregation. Aggregates per user first,
            then across users (like a SQL subquery).
        filters: Per-metric filters (in addition to global where=).

    Examples:
        ```python
        Metric("Login")
        Metric("Login", math="unique")
        Metric("Login", math="dau")
        Metric("Purchase", math="total", property="revenue")
        Metric("Purchase", math="total", per_user="average")
        Metric("Purchase", filters=[Filter.greater_than("amount", 50)])
```
    """
    
    event: str
    math: MathType = "total"
    property: str | None = None
    per_user: PerUserAggregation | None = None
    filters: list[Filter] | None = None
```

### 3.2 `Filter`

Constructs filter conditions via class methods. Each method infers the correct `filterType`, `filterOperator`, and `filterValue` format for the underlying bookmark JSON, so callers never see those raw fields.

```python
@dataclass(frozen=True)
class Filter:
    """A filter condition for Workspace.query().

    Construct via class methods — do not instantiate directly.
    All methods take a property name as the first argument.

    Examples:
        ```python
        Filter.equals("browser", "Chrome")
        Filter.equals("browser", ["Chrome", "Firefox"])
        Filter.greater_than("amount", 100)
        Filter.between("age", 18, 65)
        Filter.contains("email", "@company.com")
        Filter.is_set("phone_number")
```
    """
    
    _property: str
    _operator: str
    _value: Any
    _property_type: FilterPropertyType
    _resource_type: Literal["events", "people"]
    
    # --- String filters ---
    
    @classmethod
    def equals(
        cls,
        property: str,
        value: str | list[str],
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Property equals value (or any value in list)."""
        ...
    
    @classmethod
    def not_equals(
        cls,
        property: str,
        value: str | list[str],
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Property does not equal value."""
        ...
    
    @classmethod
    def contains(
        cls,
        property: str,
        value: str,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Property contains substring."""
        ...
    
    @classmethod
    def not_contains(
        cls,
        property: str,
        value: str,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Property does not contain substring."""
        ...
    
    # --- Numeric filters ---
    
    @classmethod
    def greater_than(
        cls,
        property: str,
        value: int | float,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Property is greater than value."""
        ...
    
    @classmethod
    def less_than(
        cls,
        property: str,
        value: int | float,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Property is less than value."""
        ...
    
    @classmethod
    def between(
        cls,
        property: str,
        min_val: int | float,
        max_val: int | float,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Property is between min_val and max_val (inclusive)."""
        ...
    
    # --- Existence filters ---
    
    @classmethod
    def is_set(
        cls,
        property: str,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Property is defined (non-null)."""
        ...
    
    @classmethod
    def is_not_set(
        cls,
        property: str,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Property is not defined (null)."""
        ...
    
    # --- Boolean filter ---
    
    @classmethod
    def is_true(
        cls,
        property: str,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Boolean property is true."""
        ...
    
    @classmethod
    def is_false(
        cls,
        property: str,
        *,
        resource_type: Literal["events", "people"] = "events",
    ) -> Filter:
        """Boolean property is false."""
        ...
```

### 3.3 `GroupBy`

Specifies a property breakdown with optional type annotation and numeric bucketing. Plain strings are shorthand for `GroupBy(property_name)` with `property_type="string"`.

```python
@dataclass(frozen=True)
class GroupBy:
    """A breakdown specification for Workspace.query().

    Use plain strings for string property breakdowns (most common case).
    Use GroupBy when you need typed breakdowns or numeric bucketing.

    Args:
        property: Property name to break down by.
        property_type: Data type of the property. Determines how values
            are grouped and displayed. Default "string".
        bucket_size: Bucket width for numeric properties. Required when
            property_type is "number" and bucketing is desired.
        bucket_min: Minimum value for numeric buckets. Optional; if omitted,
            Mixpanel auto-detects from data.
        bucket_max: Maximum value for numeric buckets. Optional; if omitted,
            Mixpanel auto-detects from data.

    Examples:
        ```python
        # String breakdown (equivalent to just "platform")
        GroupBy("platform")

        # Numeric breakdown with buckets
        GroupBy("amount", property_type="number", bucket_size=10)

        # Numeric with explicit range
        GroupBy("age", property_type="number",
                bucket_size=5, bucket_min=0, bucket_max=100)

        # Boolean breakdown
        GroupBy("is_premium", property_type="boolean")
```
    """
    
    property: str
    property_type: Literal["string", "number", "boolean", "datetime"] = "string"
    bucket_size: int | float | None = None
    bucket_min: int | float | None = None
    bucket_max: int | float | None = None
```

### 3.4 `QueryResult`

Result type returned by `query()`. Extends `ResultWithDataFrame` with the generated bookmark params for debugging and persistence.

```python
@dataclass(frozen=True)
class QueryResult(ResultWithDataFrame):
    """Result of a Workspace.query() call.

    Contains query results with lazy DataFrame conversion and the
    generated bookmark params for debugging or persistence via
    create_bookmark().

    Attributes:
        computed_at: When the query was computed (ISO format).
        from_date: Effective start date of the query (extracted from
            response ``date_range.from_date``).
        to_date: Effective end date of the query (extracted from
            response ``date_range.to_date``).
        headers: Column headers from the insights response.
        series: Query result data. Structure varies by mode:
            - timeseries: ``{metric_name: {date_str: value}}``
            - total: ``{metric_name: {"all": value}}``
        params: The generated bookmark params JSON that was sent to the
            insights API. Useful for debugging, persistence via
            create_bookmark(), or inspection.
        meta: Response metadata from the insights engine, including
            ``min_sampling_factor``, ``is_segmentation_limit_hit``,
            ``sub_query_count``, and ``report_sections``.

    Examples:
        ```python
        result = ws.query("Login", last=30)
        print(result.df.head())

        # Persist the query as a saved report
        ws.create_bookmark(CreateBookmarkParams(
            name="Daily Logins",
            bookmark_type="insights",
            params=result.params,
        ))
```
    """
    
    computed_at: str
    """When the query was computed (ISO format)."""
    
    from_date: str
    """Effective start date (from response ``date_range.from_date``)."""
    
    to_date: str
    """Effective end date (from response ``date_range.to_date``)."""
    
    headers: list[str] = field(default_factory=list)
    """Column headers (used for response parsing)."""
    
    series: dict[str, Any] = field(default_factory=dict)
    """Query result data. Timeseries: ``{name: {date: val}}``.
    Total: ``{name: {"all": val}}``."""
    
    params: dict[str, Any] = field(default_factory=dict)
    """The generated bookmark params JSON sent to the API."""
    
    meta: dict[str, Any] = field(default_factory=dict)
    """Response metadata (sampling factor, limit hit, report sections)."""
    
    @property
    def df(self) -> pd.DataFrame:
        """Convert to normalized DataFrame.
    
        Columns: date, event/metric, count/value.
        For timeseries mode, one row per (date, metric) pair.
        For total mode, one row per metric.
        """
        if self._df_cache is not None:
            return self._df_cache
    
        rows: list[dict[str, Any]] = []
        for metric_name, date_values in self.series.items():
            if isinstance(date_values, dict):
                for date_str, value in date_values.items():
                    rows.append({
                        "date": date_str,
                        "event": metric_name,
                        "count": value,
                    })
            else:
                # Total mode: single aggregate value
                rows.append({
                    "event": metric_name,
                    "count": date_values,
                })
    
        if rows:
            result_df = pd.DataFrame(rows)
        else:
            result_df = pd.DataFrame(columns=["date", "event", "count"])
    
        object.__setattr__(self, "_df_cache", result_df)
        return result_df
```

### 3.5 Type Aliases

```python
MathType = Literal[
    # Counting
    "total", "unique", "dau", "wau", "mau",
    # Property aggregation (requires math_property)
    "average", "median", "min", "max",
    "p25", "p75", "p90", "p99",
]
# Note: Mixpanel has no "sum" math type. Use math="total" with
# a property to sum a numeric property's values.

PerUserAggregation = Literal["unique_values", "total", "average", "min", "max"]

FilterPropertyType = Literal["string", "number", "boolean", "datetime", "list"]

# Math types that require math_property to be set
PROPERTY_MATH_TYPES: set[str] = {
    "average", "median", "min", "max",
    "p25", "p75", "p90", "p99",
}

# Math types that are incompatible with per_user
NO_PER_USER_MATH_TYPES: set[str] = {"dau", "wau", "mau", "unique"}
```

---

## 4. Argument Reference

### 4.1 `events` (positional, required)

| Aspect | Detail |
|--------|--------|
| **Type** | `str \| Metric \| Sequence[str \| Metric]` |
| **Purpose** | Events to query. Each event becomes one entry in `sections.show[]`. |
| **Bookmark field** | `sections.show[].behavior.name` |
| **Behavior** | A plain `str` is shorthand for `Metric(event, math=<top-level math>, ...)`. A list produces multiple metrics. |

**Resolution rules:**
- `str` → `Metric(event, math=math, property=math_property, per_user=per_user)` using top-level defaults.
- `Metric` → used as-is; its fields take precedence over top-level defaults.
- `Sequence` → each element resolved independently. Plain strings inherit top-level defaults; `Metric` objects override them.

### 4.2 Time Range

Three modes, resolved in priority order:

| Mode | Params | Bookmark mapping | Example |
|------|--------|-----------------|---------|
| **Absolute** | `from_date` + `to_date` | `dateRangeType: "between"`, `value: [from, to]` | `from_date="2024-01-01", to_date="2024-03-31"` |
| **Partial absolute** | `from_date` only | `to_date` defaults to today | `from_date="2024-01-01"` |
| **Relative** (default) | `last` | `dateRangeType: "in the last"`, `window: {unit, value}` | `last=30` |

**Validation:**
- If `from_date` or `to_date` is set, relative mode is disabled. `last` is ignored.
- If `from_date` is set without `to_date`, `to_date` defaults to today.
- If only `to_date` is set without `from_date`, raise `ValueError` (ambiguous).
- If both explicit dates and `last != 30` are set, raise `ValueError` (conflicting).
- Dates must be `YYYY-MM-DD` format. Raise `ValueError` on parse failure.
- `last` must be a positive integer. Raise `ValueError` if `<= 0`.

| Param | Type | Default | Bookmark field |
|-------|------|---------|---------------|
| `from_date` | `str \| None` | `None` | `sections.time[0].value[0]` |
| `to_date` | `str \| None` | `None` | `sections.time[0].value[1]` |
| `last` | `int` | `30` | `sections.time[0].window.value` |

### 4.3 `unit`

| Aspect | Detail |
|--------|--------|
| **Type** | `Literal["hour", "day", "week", "month", "quarter"]` |
| **Default** | `"day"` |
| **Purpose** | Time granularity for the result AND the unit for `last` when using relative time. |
| **Bookmark field** | `sections.time[0].unit` and `sections.time[0].window.unit` |

When using relative mode (`last`), `unit` controls both:
- What "N" means in "last N units" (e.g., `last=4, unit="week"` = last 4 weeks)
- How data is grouped on the time axis (weekly buckets)

When using absolute mode (`from_date`/`to_date`), `unit` only controls time-axis granularity.

### 4.4 Aggregation Defaults

These apply to events passed as plain strings. `Metric` objects override these per-event.

| Param | Type | Default | Bookmark field | Notes |
|-------|------|---------|---------------|-------|
| `math` | `MathType` | `"total"` | `sections.show[].measurement.math` | See valid values in type alias |
| `math_property` | `str \| None` | `None` | `sections.show[].measurement.property.name` | **Required** when math is `average`, `median`, `min`, `max`, `sum`, `p25`, `p75`, `p90`, `p99`. Raise `ValueError` if missing. |
| `per_user` | `PerUserAggregation \| None` | `None` | `sections.show[].measurement.perUserAggregation` | Aggregates per-user first, then across users. Incompatible with `dau`/`wau`/`mau` math. |

### 4.5 `group_by`

| Aspect | Detail |
|--------|--------|
| **Type** | `str \| GroupBy \| list[str \| GroupBy] \| None` |
| **Default** | `None` |
| **Purpose** | Break down results by property value(s). Each entry becomes one item in `sections.group[]`. |
| **Bookmark field** | `sections.group[].propertyName`, `sections.group[].value`, `sections.group[].propertyType`, `sections.group[].customBucket` |

Plain strings are shorthand for `GroupBy(property, property_type="string")`. Use `GroupBy` objects for numeric breakdowns with bucketing, boolean breakdowns, or datetime breakdowns.

**Validation:**
- `GroupBy` with `property_type="number"` and `bucket_size` set: `bucket_size` must be positive.
- `bucket_min` / `bucket_max` without `bucket_size` raises `ValueError`.

### 4.6 `where`

| Aspect | Detail |
|--------|--------|
| **Type** | `Filter \| list[Filter] \| None` |
| **Default** | `None` |
| **Purpose** | Global filters applied to all metrics. |
| **Bookmark field** | `sections.filter[]` |

Multiple filters combine with AND logic (`determiner: "all"`). For OR logic across filter groups, use per-metric filters via `Metric(filters=[...])`.

### 4.7 Formula

| Param | Type | Default | Bookmark field |
|-------|------|---------|---------------|
| `formula` | `str \| None` | `None` | `sections.show[-1].definition` (appended as formula entry) |
| `formula_label` | `str \| None` | `None` (defaults to formula expression) | `sections.show[-1].name` |

Letters A-Z reference metrics by their position in `events`. When `formula` is set, all non-formula metrics are automatically marked `isHidden: true` so only the computed result appears in the output.

**Validation:** `formula` requires `events` to be a sequence with 2+ items (at least two metrics to reference). Raise `ValueError` if `formula` is set with a single event.

### 4.8 Analysis Mode

| Param | Type | Default | Bookmark field |
|-------|------|---------|---------------|
| `rolling` | `int \| None` | `None` | `displayOptions.analysis: "rolling"`, `displayOptions.rollingWindowSize` |
| `cumulative` | `bool` | `False` | `displayOptions.analysis: "cumulative"` |

**Validation:**
- `rolling` and `cumulative` are mutually exclusive. Raise `ValueError` if both are set.
- `rolling` must be a positive integer. Raise `ValueError` if `<= 0`.
- When neither is set, `displayOptions.analysis` is `"linear"` (the default).

### 4.9 `mode`

| Aspect | Detail |
|--------|--------|
| **Type** | `Literal["timeseries", "total", "table"]` |
| **Default** | `"timeseries"` |
| **Purpose** | Controls result aggregation semantics. |
| **Bookmark field** | `displayOptions.chartType` (translated — see mapping below) |

**Value mapping to bookmark JSON:**

| `mode` value | `displayOptions.chartType` | Semantics |
|-------------|---------------------------|-----------|
| `"timeseries"` | `"line"` | Per-period values. `math="unique"` counts unique users **per period** (not additive across periods). |
| `"total"` | `"bar"` | Aggregate totals. `math="unique"` deduplicates users across the **entire date range**. Use for KPI-style single numbers. |
| `"table"` | `"table"` | Tabular detail. |

This parameter is named `mode` (not `chart`) because the choice changes aggregation semantics, not just visualization.

---

## 5. Design Rationale

### 5.1 Why one `query()` method instead of many specialized methods

**Decision:** A single `query()` method that generates insights bookmark params.

**Alternatives considered:**
- (A) Extend existing methods (`segmentation`, `funnel`, `retention`) with more parameters
- (B) Create separate methods: `insights()`, `compare()`, `formula_query()`, etc.
- (C) A query builder pattern: `ws.insights().event("Login").math("unique").last(30).run()`

**Why (C) was rejected:** Builder patterns are verbose and don't play well with LLM code generation. LLMs are better at filling in keyword arguments than chaining methods — kwargs appear in function signatures and docstrings, which are heavily represented in training data.

**Why (A) was rejected:** The existing `segmentation()` method uses the legacy Query API (`/segmentation`), not the insights engine. They have different capabilities. Overloading `segmentation()` would either break its simple interface or create confusing behavioral differences.

**Why (B) was rejected:** The underlying bookmark JSON structure is the same for all these cases — they only differ in the contents of `sections.show[]`. Multiple methods would duplicate 90% of the parameter handling. A single method with union-typed `events` is more DRY and discoverable.

### 5.2 Why `Metric` class instead of expanding top-level params

**Decision:** Top-level `math`/`math_property`/`per_user` for the common case (all events share the same aggregation), `Metric` objects for per-event control.

**Rationale:** The simplest query — `ws.query("Login")` — should need zero aggregation configuration. The next step — `ws.query("Login", math="unique")` — should require exactly one kwarg. Only when events need different aggregations should the user reach for `Metric`. This progressive disclosure matches how LLMs build up complexity.

**Alternative:** Require `Metric` objects always. Rejected because `ws.query(Metric("Login"))` is more verbose than `ws.query("Login")` for the most common case.

### 5.3 Why `Filter` class methods instead of expression strings or dicts

**Decision:** `Filter.equals("browser", "Chrome")` style class methods.

**Alternatives considered:**
- (A) Expression strings: `where='properties["browser"] == "Chrome"'`
- (B) Dict shorthand: `where={"browser": "Chrome", "amount__gt": 100}`
- (C) Tuple syntax: `where=[("browser", "==", "Chrome")]`

**Why (A) was rejected:** The `where` expression syntax (used by `segmentation()`) and the structured filter JSON (used by bookmark params) are **different systems**. Accepting expression strings would require a parser that converts Mixpanel expression syntax to structured filter JSON — complex to build, fragile, and a source of subtle bugs. The expression language also has quirks (property accessor syntax, escaping rules) that make it error-prone for LLMs.

**Why (B) was rejected:** Dict shorthand requires encoding operator semantics into key names (`amount__gt`). This Django ORM pattern is familiar but doesn't compose well — how do you express `is_set`, `between`, or `contains` cleanly? It also lacks type safety.

**Why (C) was rejected:** Tuples are positional and fragile. No autocompletion, no discoverability.

**Why class methods won:** Each class method is self-documenting — an LLM can read `Filter.greater_than(property, value)` and know exactly what it does. Class methods handle the mapping from human-readable operations (`greater_than`) to Mixpanel-internal operators (`is greater than`) and the correct `filterValue` format (scalar vs. array) automatically.

### 5.4 Why `last=30` as default instead of requiring explicit dates

**Decision:** Default to last 30 days when no dates are provided.

**Rationale:** The most common analytics question is "what happened recently?" Requiring explicit dates for every query adds friction and forces LLMs to compute date strings. `ws.query("Login")` should Just Work and return something useful. 30 days is the Mixpanel UI default.

### 5.5 Why `mode` instead of `chart`

**Decision:** Name the parameter `mode` with semantic values (`"timeseries"`, `"total"`, `"table"`) instead of Mixpanel chart type names (`"line"`, `"bar"`, `"table"`).

**Rationale:** In Mixpanel's insights engine, `chartType: "bar"` vs `chartType: "line"` changes deduplication behavior for `math="unique"`. A bar chart with unique counts deduplicates across the entire date range; a line chart computes per-period unique counts (not additive). Calling this `chart` implies it's a display preference. Calling it `mode` with values like `"total"` vs `"timeseries"` communicates that it's a query-semantic choice. The mapping from mode values to bookmark `chartType` values is a one-line translation handled internally.

### 5.6 Why `GroupBy` from the start instead of strings-only

**Decision:** Accept `str | GroupBy | list[str | GroupBy]` from v1, rather than adding `GroupBy` later.

**Rationale:** Numeric property breakdowns (revenue buckets, age ranges) are common enough to justify first-class support. Adding `GroupBy` later would be a backward-compatible change in type signature but would require users who need bucketing to wait for v2. Since `GroupBy("platform")` is only marginally more verbose than `"platform"`, and plain strings remain supported as shorthand, there's no ergonomic cost to including `GroupBy` from the start. It also avoids the need to silently default `propertyType` to `"string"` for all properties — `GroupBy` makes the caller's intent explicit when the property type matters.

### 5.7 Why inline params execution instead of create-then-query

**Decision:** POST bookmark params directly to the `/insights` query endpoint rather than creating a temporary bookmark, querying it by ID, and deleting it.

**Rationale:** The create-query-delete pattern requires three API calls and creates transient state. Inline params is a single call with no side effects. It avoids the need for App API access (which requires OAuth or scoped service accounts) — inline params may work with Basic Auth just like the existing `segmentation()` method. During implementation, if the inline params path is not supported by the Mixpanel API, the create-query-delete pattern is the tested fallback (see §9.1).

### 5.8 Why `QueryResult` instead of reusing `SavedReportResult`

**Decision:** Introduce a new `QueryResult(ResultWithDataFrame)` type.

**Rationale:** `SavedReportResult` has a required `bookmark_id: int` field that is meaningless for inline queries. More importantly, `QueryResult` exposes `params: dict[str, Any]` — the generated bookmark JSON — which serves three purposes: (1) debugging when a query returns unexpected results, (2) persistence via `create_bookmark(params=result.params)`, and (3) learning the bookmark format by example. A clean type without vestigial fields is preferable to overloading an existing type with optional sentinel values.

### 5.9 Why fail-fast validation over server leniency

**Decision:** Validate parameter combinations client-side and raise `ValueError` immediately for clearly invalid inputs, rather than forwarding to the server.

**Rationale:** The Mixpanel server validation is lenient — it logs warnings for missing optional fields but often proceeds, producing confusing results (e.g., `math="average"` without a property silently falls back to `math="total"`). For an LLM-facing API, silent fallbacks are worse than errors. A `ValueError("math='average' requires math_property to be set")` is immediately actionable; a silently-wrong result requires debugging. Fail-fast also saves an API call. The full validation rule set is in §5.10.

### 5.10 Client-Side Validation Rules

All rules raise `ValueError` with a descriptive message at call time, before any API request.

| # | Rule | Message pattern |
|---|------|----------------|
| V1 | `math` in `PROPERTY_MATH_TYPES` and `math_property` is `None` | `math='{math}' requires math_property to be set` |
| V2 | `math` not in `PROPERTY_MATH_TYPES` and `math_property` is not `None` | `math_property is only valid with property-based math types (average, sum, etc.), not '{math}'` |
| V3 | `per_user` set and `math` in `NO_PER_USER_MATH_TYPES` | `per_user is incompatible with math='{math}'` |
| V4 | `formula` set and `events` resolves to < 2 metrics | `formula requires at least 2 events (got {n})` |
| V5 | `rolling` and `cumulative` both set | `rolling and cumulative are mutually exclusive` |
| V6 | `rolling` is not `None` and `<= 0` | `rolling must be a positive integer` |
| V7 | `last` is `<= 0` | `last must be a positive integer` |
| V8 | `to_date` set without `from_date` | `to_date requires from_date` |
| V9 | `last != 30` and (`from_date` or `to_date`) set | `Cannot combine last={last} with explicit dates; use either last or from_date/to_date` |
| V10 | `from_date` fails `YYYY-MM-DD` parse | `from_date must be YYYY-MM-DD format (got '{from_date}')` |
| V11 | `to_date` fails `YYYY-MM-DD` parse | `to_date must be YYYY-MM-DD format (got '{to_date}')` |
| V12 | `GroupBy.bucket_min` or `bucket_max` set without `bucket_size` | `bucket_min/bucket_max require bucket_size` |
| V13 | `GroupBy.bucket_size` is not `None` and `<= 0` | `bucket_size must be positive` |
| V14 | Same validation rules V1-V3 applied per-`Metric` for each `Metric` object's own `math`/`property`/`per_user` fields | Same messages, prefixed with metric event name |

### 5.11 What was excluded and why

| Excluded Feature | Reason |
|-----------------|--------|
| Ad-hoc funnels | Structurally different (`behavior.type: "funnel"`, requires `behaviors[]` with 2+ steps, different chart types). Better as a separate `funnel_query()` method. |
| Retention queries | Same — different structure, `behavior.type: "retention"`, exactly 2 events required. |
| Flows | Completely different JSON format (no `sections` wrapper). Already has `query_flows()`. |
| Cohort behaviors | Requires `behavior.type: "cohort"` with cohort IDs. Adds complexity for a niche use case. |
| Session-based math | Underdocumented. `math: "sessions"` semantics unclear. |
| Custom percentile | `math: "custom_percentile"` requires additional configuration that's not well-documented. |
| Histogram | `math: "histogram"` requires bucket configuration. Edge case. |
| `save_as` persistence | Separating query execution from bookmark persistence keeps `query()` focused. Users who want persistence can use `result.params` with `create_bookmark()`. |
| Multiple formulas | Single formula covers the 70% case. Multiple formulas add parameter complexity for diminishing returns. |

---

## 6. Bookmark Mapping

### 6.1 Parameter → JSON Field Reference

| API Parameter | Bookmark JSON Path | Notes |
|--------------|--------------------|-------|
| `events` (each resolved Metric) | `sections.show[]` | One `{type: "metric", behavior: {...}, measurement: {...}}` per event |
| `Metric.event` | `sections.show[].behavior.name` | |
| `Metric.math` | `sections.show[].measurement.math` | |
| `Metric.property` | `sections.show[].measurement.property` | `{name, type: "number", resourceType: "events"}` |
| `Metric.per_user` | `sections.show[].measurement.perUserAggregation` | |
| `Metric.filters` | `sections.show[].behavior.filters[]` | Structured filter JSON (same format as global filters) |
| `where` (each Filter) | `sections.filter[]` | Global filters across all metrics |
| `group_by` (str) | `sections.group[]` | `{propertyName, value, resourceType: "events", propertyType: "string"}` |
| `group_by` (GroupBy) | `sections.group[]` | `{propertyName, value, resourceType, propertyType, customBucket}` |
| `GroupBy.bucket_size/min/max` | `sections.group[].customBucket` | `{bucketSize, min, max}` |
| `from_date` / `to_date` | `sections.time[0].value` | `[from_date, to_date]` array |
| `last` + `unit` | `sections.time[0].window` | `{unit, value}` |
| `unit` | `sections.time[0].unit` | Time granularity |
| `formula` | `sections.show[-1]` (appended) | `{type: "formula", definition, name}` |
| `rolling` | `displayOptions.analysis` + `rollingWindowSize` | `"rolling"` + int |
| `cumulative` | `displayOptions.analysis` | `"cumulative"` |
| `mode` | `displayOptions.chartType` | `"timeseries"` → `"line"`, `"total"` → `"bar"`, `"table"` → `"table"` |
| (automatic) | `displayOptions.plotStyle` | Always `"standard"` |
| (automatic) | request body `queryLimits.limit` | Default `3000`. **Top-level request param**, NOT inside bookmark (server rejects it inside bookmark). |

### 6.2 Example: Simple event count

**API call:**
```python
ws.query("Login", last=7)
```

**Generated bookmark JSON:**
```json
{
  "sections": {
    "show": [
      {
        "type": "metric",
        "behavior": {
          "type": "event",
          "name": "Login",
          "resourceType": "events",
          "filtersDeterminer": "all",
          "filters": [],
          "dataGroupId": null,
          "dataset": "mixpanel"
        },
        "measurement": {
          "math": "total",
          "property": null,
          "perUserAggregation": null
        },
        "isHidden": false
      }
    ],
    "filter": [],
    "group": [],
    "time": [
      {
        "dateRangeType": "in the last",
        "unit": "day",
        "window": { "unit": "day", "value": 7 }
      }
    ],
    "formula": []
  },
  "displayOptions": {
    "chartType": "line",
    "plotStyle": "standard",
    "analysis": "linear"
  }
}
```

### 6.3 Example: Multi-metric formula with filters and typed breakdown

**API call:**
```python
ws.query(
    [Metric("Signup", math="unique"), Metric("Purchase", math="unique")],
    where=[Filter.equals("country", "US"), Filter.greater_than("age", 18)],
    group_by=GroupBy("revenue", property_type="number", bucket_size=50, bucket_min=0, bucket_max=500),
    formula="(B / A) * 100",
    formula_label="Conversion Rate",
    from_date="2024-01-01",
    to_date="2024-03-31",
    unit="week",
)
```

**Generated bookmark JSON:**
```json
{
  "sections": {
    "show": [
      {
        "type": "metric",
        "behavior": {
          "type": "event",
          "name": "Signup",
          "resourceType": "events",
          "filtersDeterminer": "all",
          "filters": [],
          "dataGroupId": null,
          "dataset": "mixpanel"
        },
        "measurement": {
          "math": "unique",
          "property": null,
          "perUserAggregation": null
        },
        "isHidden": true
      },
      {
        "type": "metric",
        "behavior": {
          "type": "event",
          "name": "Purchase",
          "resourceType": "events",
          "filtersDeterminer": "all",
          "filters": [],
          "dataGroupId": null,
          "dataset": "mixpanel"
        },
        "measurement": {
          "math": "unique",
          "property": null,
          "perUserAggregation": null
        },
        "isHidden": true
      },
      {
        "type": "formula",
        "name": "Conversion Rate",
        "definition": "(B / A) * 100",
        "measurement": {},
        "referencedMetrics": []
      }
    ],
    "filter": [
      {
        "resourceType": "events",
        "filterType": "string",
        "value": "country",
        "filterOperator": "equals",
        "filterValue": ["US"],
        "determiner": "all",
        "isHidden": false
      },
      {
        "resourceType": "events",
        "filterType": "number",
        "value": "age",
        "filterOperator": "is greater than",
        "filterValue": 18,
        "determiner": "all",
        "isHidden": false
      }
    ],
    "group": [
      {
        "resourceType": "events",
        "propertyType": "number",
        "propertyDefaultType": "number",
        "propertyName": "revenue",
        "value": "revenue",
        "typeCast": null,
        "customBucket": {
          "bucketSize": 50,
          "min": 0,
          "max": 500
        },
        "isHidden": false
      }
    ],
    "time": [
      {
        "dateRangeType": "between",
        "unit": "week",
        "value": ["2024-01-01", "2024-03-31"]
      }
    ],
    "formula": []
  },
  "displayOptions": {
    "chartType": "line",
    "plotStyle": "standard",
    "analysis": "linear"
  }
}
```

**Key details to note:**
- Both `Signup` and `Purchase` metrics have `isHidden: true` because `formula` is present
- The formula entry is appended to `sections.show[]` (not `sections.formula`)
- String filter uses `filterOperator: "equals"` with `filterValue: ["US"]` (array)
- Number filter uses `filterOperator: "is greater than"` with `filterValue: 18` (scalar)
- `GroupBy` with `property_type="number"` sets `propertyType: "number"` and populates `customBucket`
- `mode` is not present in the JSON — it's translated to `displayOptions.chartType`
- Time uses `dateRangeType: "between"` with `value: [from, to]` (array)

---

## 7. Example Calls

### 7.1 Total event count (simplest possible)

```python
# "How many Login events happened in the last 30 days, per day?"
result = ws.query("Login")
print(result.df.head())
#         date  event  count
# 0 2024-01-01  Login    142
# 1 2024-01-02  Login    158
```

### 7.2 Unique users with custom time range

```python
# "How many unique users logged in per week this quarter?"
result = ws.query(
    "Login",
    math="unique",
    from_date="2024-01-01",
    to_date="2024-03-31",
    unit="week",
)
```

### 7.3 DAU metric

```python
# "Show me DAU for the last 90 days"
result = ws.query("Login", math="dau", last=90)
```

### 7.4 Breakdown by property (string)

```python
# "Login counts broken down by platform, last 14 days"
result = ws.query("Login", group_by="platform", last=14)
```

### 7.5 Breakdown by property (numeric with buckets)

```python
# "Purchase counts by revenue bucket ($0-$500, $50 increments)"
result = ws.query(
    "Purchase",
    group_by=GroupBy("revenue", property_type="number",
                     bucket_size=50, bucket_min=0, bucket_max=500),
)
```

### 7.6 Filtered query

```python
# "Purchase events from US users on iOS, last 30 days"
result = ws.query(
    "Purchase",
    where=[
        Filter.equals("country", "US"),
        Filter.equals("platform", "iOS"),
    ],
)
```

### 7.7 Property aggregation

```python
# "Average purchase amount per day this month"
result = ws.query(
    "Purchase",
    math="average",
    math_property="amount",
    from_date="2024-03-01",
    to_date="2024-03-31",
)
```

### 7.8 Multi-metric comparison

```python
# "Compare Signup, Login, and Purchase counts over the last 30 days"
result = ws.query(["Signup", "Login", "Purchase"], math="unique")
```

### 7.9 Conversion rate formula

```python
# "What's the signup-to-purchase conversion rate by week?"
result = ws.query(
    [Metric("Signup", math="unique"), Metric("Purchase", math="unique")],
    formula="(B / A) * 100",
    formula_label="Conversion Rate",
    unit="week",
)
```

### 7.10 Per-user aggregation

```python
# "Average number of purchases per user per week"
result = ws.query(
    "Purchase",
    math="total",
    per_user="average",
    unit="week",
)
```

### 7.11 Rolling average with breakdown

```python
# "7-day rolling average of signups by country"
result = ws.query(
    "Signup",
    math="unique",
    group_by="country",
    rolling=7,
    last=60,
)
```

### 7.12 Aggregate KPI (single number)

```python
# "Total unique purchasers this month"
result = ws.query(
    "Purchase",
    math="unique",
    from_date="2024-03-01",
    to_date="2024-03-31",
    mode="total",
)
total = result.df["count"].iloc[0]
```

### 7.13 Complex: per-metric filters with formula

```python
# "Ratio of premium purchases to all purchases, by platform"
result = ws.query(
    [
        Metric("Purchase", math="unique"),
        Metric(
            "Purchase",
            math="unique",
            filters=[Filter.equals("plan", "premium")],
        ),
    ],
    formula="(B / A) * 100",
    formula_label="Premium %",
    group_by="platform",
    unit="week",
)
```

### 7.14 Persisting a query as a saved report

```python
# Run query, then save the generated params as a bookmark
result = ws.query(
    "Login",
    math="dau",
    group_by="platform",
    last=90,
)

# result.params contains the full bookmark JSON
ws.create_bookmark(CreateBookmarkParams(
    name="DAU by Platform (90d)",
    bookmark_type="insights",
    params=result.params,
))
```

---

## 8. Scope Boundaries

### In scope (v1)

- Insights queries for `behavior.type: "event"` (standard events)
- All counting math types: `total`, `unique`, `dau`, `wau`, `mau`
- Property aggregation math: `average`, `median`, `min`, `max`, `sum`, `p25`, `p75`, `p90`, `p99`
- Per-user aggregation
- Global filters (string, number, boolean, existence)
- Per-metric filters
- Breakdown by string, number, boolean, or datetime properties via `GroupBy`
- Numeric bucketing via `GroupBy.bucket_size` / `bucket_min` / `bucket_max`
- Formulas (single formula referencing metrics A-Z)
- Relative and absolute time ranges
- Rolling and cumulative analysis modes
- Mode selection (`timeseries`, `total`, `table`)
- `QueryResult` type with `.params` for debugging and persistence
- Client-side fail-fast validation of all parameter combinations (see §5.10)

### Could be added later (v2+)

| Feature | Complexity | Trigger |
|---------|-----------|---------|
| Ad-hoc funnels | Medium | `funnel_query()` method with step definitions |
| Ad-hoc retention | Medium | `retention_query()` method with event pairs |
| Cohort-based behaviors | Medium | Querying by cohort membership |
| Multiple formulas | Low | Multiple computed columns |
| Custom percentiles | Low | `math="percentile"` with a `percentile_value` param |
| Histogram math | Low | `math="histogram"` with bucket config |
| `save_as` parameter | Low | Persist query as named bookmark in one call |
| `build_params()` helper | Low | Return bookmark JSON without executing |
| Date filters | Medium | `Filter.before()`, `Filter.since()` |

### Should never be in `query()`

| Feature | Reason |
|---------|--------|
| Flows | Completely different JSON structure (no `sections`). Use `query_flows()`. |
| JQL | Deprecated, different execution path. Use `jql()`. |
| Cross-project queries | Not supported by Mixpanel API. |
| Bookmark CRUD | Separate concern. Use `create_bookmark()` / `update_bookmark()`. |
| Dashboard operations | Separate concern. |
| Display-only options | `plotStyle`, `theme`, axis options — purely presentational, no effect on query results. |
| Query caching/sampling hints | `use_query_cache`, `use_query_sampling` — infrastructure concerns, not query semantics. |

---

## 9. Resolved: Execution Path

All investigation items have been resolved through source code analysis and live API testing against the `ecommerce-demo` project (Basic Auth, service account).

### 9.1 Inline Params — Confirmed Working

The `/insights` endpoint accepts inline bookmark params via POST. No bookmark creation required.

**Request format (confirmed by source and live test):**

```
POST /api/query/insights
Content-Type: application/json
Authorization: Basic <base64(username:secret)>

{
  "project_id": 3018488,
  "bookmark": {
    "sections": {
      "show": [...],
      "filter": [...],
      "group": [...],
      "time": [...],
      "formula": []
    },
    "displayOptions": {
      "chartType": "line",
      "plotStyle": "standard",
      "analysis": "linear"
    }
  },
  "queryLimits": {"limit": 3000}
}
```

**Key details:**

| Detail | Finding |
|--------|---------|
| **Parameter name** | `bookmark` (dict, not stringified). The endpoint also accepts `bookmark_id` (int) and legacy `params` (stringified JSON), but `bookmark` is the preferred format. |
| **`queryLimits` placement** | **Top-level request param**, NOT inside the bookmark dict. Server rejects `queryLimits` inside bookmark with `"Extra inputs are not permitted at queryLimits"`. |
| **HTTP method** | POST with JSON body. GET with query string also works for `bookmark_id`, but inline bookmark params are too large for query strings. |
| **`project_id`** | Required in the request body alongside `bookmark`. |

**Source evidence:** `analytics/api/version_2_0/insights/bookmark.py:649-662` — `get_bookmark_from_request_params()` checks for `bookmark_id` first, then falls back to `request_params["bookmark"]`. The `insights_query()` function at `api.py:481` explicitly documents three accepted keys: `bookmark`, `bookmark_id`, or `params`.

### 9.2 Response Format — Confirmed Compatible

The inline params response has the same core structure as `query_saved_report()`.

**Response shape:**
```json
{
  "computed_at": "2026-04-03T06:11:50.670473+00:00",
  "date_range": {
    "from_date": "2023-05-25T00:00:00-07:00",
    "to_date": "2023-05-31T23:59:59.999000-07:00"
  },
  "headers": ["$metric"],
  "series": {
    "Product Added [Total Events]": {
      "2023-05-25T00:00:00-07:00": 756,
      "2023-05-26T00:00:00-07:00": 795
    }
  },
  "meta": {
    "min_sampling_factor": 1.0,
    "is_segmentation_limit_hit": false,
    "sub_query_count": 1,
    "report_sections": {
      "group": [],
      "show": [{"metric_key": "Product Added [Total Events]"}]
    }
  }
}
```

**Differences from `query_saved_report()` response:**

| Field | Inline params | `query_saved_report()` | Impact |
|-------|--------------|----------------------|--------|
| Date range | `date_range: {from_date, to_date}` (nested) | Flat `from_date`, `to_date` (extracted by `_transform_saved_report`) | `QueryResult` extracts from `date_range` |
| `meta` | Present | Absent | `QueryResult` stores it; `SavedReportResult` discards it |
| `bookmark_id` | Absent | Present | `QueryResult` doesn't need it |
| `series` keys | Same format | Same format | Compatible |
| `headers` | Same format | Same format | Compatible |

**Total mode (`chartType: "bar"`) response:**
```json
{
  "series": {
    "Product Added [Unique Users]": {"all": 3551}
  }
}
```
Total mode returns `{"all": <value>}` instead of per-date entries. The `QueryResult.df` property handles both structures.

**Multi-metric + formula response (confirmed working):**
- Hidden metrics (marked `isHidden: true`) do NOT appear in the response series
- Only visible metrics and formula results appear
- Formula values are computed server-side (e.g., `"Checkout Rate": {"2023-05-18...": 103.71}`)

### 9.3 Auth Requirements — Basic Auth Confirmed

**Basic Auth (service account) works.** Confirmed with live tests against `ecommerce-demo` (project 3018488, `auth_method=basic`).

The request handler (`request_handler.py:911`) supports `token` and `serviceaccount` auth types for the insights API. No OAuth required. This makes `query()` consistent with `segmentation()` — both work with Basic Auth service account credentials.

### 9.4 Implementation Notes

Based on these findings, the `query()` implementation should:

1. **Build bookmark params** from typed arguments (no `queryLimits` inside bookmark)
2. **POST to `/insights`** with body: `{"bookmark": <params>, "project_id": <id>, "queryLimits": {"limit": 3000}}`
3. **Parse response**: Extract `date_range.from_date` and `date_range.to_date` (nested), copy `computed_at`, `headers`, `series`, `meta`
4. **Return `QueryResult`** with all fields populated, including `params` (the bookmark dict sent)

No create-query-delete fallback is needed. The inline params path is the canonical implementation.

**Request construction (pseudocode):**
```python
url = self.api._build_url("query", "/insights")
body = {
    "bookmark": bookmark_params,       # the constructed dict
    "project_id": self._credentials.project_id,
    "queryLimits": {"limit": 3000},
}
response = self.api._request("POST", url, json_body=body)
# response keys: computed_at, date_range, headers, series, meta
```
