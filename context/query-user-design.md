# `query_user()` Design Document — The 5th Query Engine

> **Status**: Draft v2  
> **Date**: 2026-04-12  
> **Author**: Design synthesis from codebase research  
> **Spec**: Standalone (builds on 029, 031, 032, 033, 034)

---

## 1. Executive Summary

`query_user()` is the 5th and final engine in the unified query system, completing the taxonomy of Mixpanel analytics:

| Engine | Method | Data Shape | API Endpoint |
|--------|--------|-----------|--------------|
| Insights | `query()` | Time-series aggregates | `POST /query/insights` |
| Funnels | `query_funnel()` | Step-wise conversion | `POST /query/insights` |
| Retention | `query_retention()` | Cohort curves | `POST /query/insights` |
| Flows | `query_flow()` | Path graphs | `POST /query/arb_funnels` |
| **Users** | **`query_user()`** | **Profile records / aggregates** | **`POST /engage`** |

The first four engines query **aggregated report data** — time series, conversion rates, retention curves, user flows. `query_user()` queries **individual user profile records** and can compute **aggregate statistics** across the user base. This is fundamentally different: instead of "how many users did X?", you ask "which users match these criteria, what do I know about them, and what are the aggregate patterns?"

The design challenge is making this feel like a natural 5th member of the family despite the underlying API being structurally different. The key insight: the **Filter type** becomes the bridge. Users learn one vocabulary — `Filter.equals()`, `Filter.greater_than()`, `Filter.in_cohort()` — and it works everywhere, whether filtering time-series aggregates or querying individual profiles.

**Three capabilities ship in v1**:
1. **Profile listing** (`mode="profiles"`) — individual user records as DataFrames
2. **Aggregate statistics** (`mode="aggregate"`) — count/sum/mean/min/max across matching profiles, with optional cohort segmentation
3. **Parallel fetching** (`parallel=True`) — concurrent page fetching for large result sets (up to 5x speedup)

---

## 2. Background

### 2.1 What Exists Today

The project has `stream_profiles()` — a low-level iterator that yields profile dicts one at a time from the `/engage` API. It accepts raw selector strings and handles pagination internally:

```python
for profile in ws.stream_profiles(where='properties["plan"] == "premium"'):
    process(profile)
```

This is useful for ETL pipelines and streaming use cases, but it:
- Returns raw dicts, not DataFrames
- Accepts raw selector strings, not typed `Filter` objects
- Has no result metadata (total count, computed_at)
- Can't sort, search, or limit results
- Can't compute aggregates (count, sum, mean) across profiles
- Doesn't participate in the unified query engine vocabulary

### 2.2 What's Missing

The unified query system has four engines that share a common vocabulary (`where=`, `group_by=`, `last=`). Profile queries live outside this system. An AI agent that can fluently query insights, funnels, retention, and flows must drop down to raw strings and manual iteration to answer "who are my premium users sorted by LTV?" or "how many users match this behavioral cohort?"

### 2.3 The /engage API

The Mixpanel `/engage` HTTP API provides 5 sub-endpoints via a `filter_type` parameter:

| Sub-endpoint | Purpose | Coverage in `query_user()` |
|---|---|---|
| **default** | List/query user profiles | `mode="profiles"` |
| **stats** | Aggregate profile statistics | `mode="aggregate"` |
| **properties** | List available profile properties | Already covered by `ws.properties()` |
| **values** | List values for a property | Already covered by `ws.property_values()` |
| **aliases** | Resolve identity aliases | Niche, separate concern |

The default endpoint supports filtering, property selection, sorting, pagination, full-text search, cohort filtering, point-in-time queries, and group profiles.

The stats endpoint returns aggregate values (count, sum, mean, min, max) across matching profiles, with optional cohort segmentation. It always aggregates over the full date range — no time-series granularity (the API forces `unit="range"` internally).

**Rate limits**: 60 queries/hour, max 5 concurrent. Each pagination page counts as a query.

### 2.4 Behavioral Filtering

The engage API accepts a `behaviors` parameter that defines event-based user criteria (e.g., "performed Purchase at least 3 times in the last 30 days"). Server-side, the API transparently converts behaviors into a cohort query via `__convert_engage_query_to_cohort_query()` before execution.

**How it works**: The `behaviors` parameter is a JSON-encoded list of behavior definitions. Each behavior has a `name`, `event_selectors`, and a time `window`. The `where` selector then references behavior outcomes by name (e.g., `behaviors["purchased"] > 0`).

**Constraint**: `behaviors` cannot be combined with `filter_by_cohort` or `group_by_cohorts` — they are mutually exclusive because the server converts behaviors into `filter_by_cohort` internally.

`stream_profiles()` accepts behaviors as raw `list[dict[str, Any]]` — this remains the low-level escape hatch. For `query_user()`, behavioral filtering is expressed exclusively through `cohort=CohortDefinition(...)`, which is fully typed and composes naturally with the `CohortCriteria` builder methods. This eliminates raw string selectors (behavior name references like `behaviors["x"] >= 3`) from the query_user API surface, keeping agents safe from hallucinated selector syntax.

---

## 3. Design Goals

1. **Unified vocabulary**: `where=Filter.equals(...)` works identically to other engines
2. **DataFrame-native**: Results as pandas DataFrames, consistent with `ResultWithDataFrame`
3. **Size control**: Property selection, result limiting, and filtering prevent unbounded data transfer
4. **Full /engage power**: Sorting, search, cohort filtering, point-in-time queries, group profiles, aggregate statistics
5. **Composition**: Results compose naturally with other engine outputs via DataFrame joins and cohort IDs
6. **Progressive disclosure**: `ws.query_user()` returns 1 sample + total count (safe default); scale up with `limit=`
7. **Validation before execution**: Same two-layer validation as other engines
8. **Parallel performance**: Concurrent page fetching for large result sets (up to 5x speedup)
9. **Aggregate analytics**: Count, sum, mean, min, max across matching profiles with cohort segmentation
10. **Typed behavioral filtering**: Behavioral criteria expressed exclusively through `CohortDefinition` + `CohortCriteria` — fully typed, no raw strings, agent-safe

---

## 4. API Design

### 4.1 Method Signature

```python
def query_user(
    self,
    *,
    # ── Filtering (shared vocabulary) ──────────────────────
    where: Filter | list[Filter] | str | None = None,
    cohort: int | CohortDefinition | None = None,

    # ── Property Selection ─────────────────────────────────
    properties: list[str] | None = None,

    # ── Ordering ───────────────────────────────────────────
    sort_by: str | None = None,
    sort_order: Literal["ascending", "descending"] = "descending",

    # ── Result Size ────────────────────────────────────────
    limit: int | None = 1,

    # ── Full-Text Search ───────────────────────────────────
    search: str | None = None,

    # ── Specific Users ─────────────────────────────────────
    distinct_id: str | None = None,
    distinct_ids: list[str] | None = None,

    # ── Group Profiles ─────────────────────────────────────
    group_id: str | None = None,

    # ── Point-in-Time ──────────────────────────────────────
    as_of: str | int | None = None,

    # ── Output Mode ────────────────────────────────────────
    mode: Literal["profiles", "aggregate"] = "profiles",

    # ── Aggregation (mode="aggregate" only) ────────────────
    aggregate: Literal["count", "sum", "mean", "min", "max"] = "count",
    aggregate_property: str | None = None,
    segment_by: list[int] | None = None,

    # ── Performance ────────────────────────────────────────
    parallel: bool = False,
    workers: int = 5,

    # ── Advanced ───────────────────────────────────────────
    include_all_users: bool = False,
) -> UserQueryResult:
```

**Design rationale for parameter ordering**: Parameters are ordered by expected frequency of use. Filtering, property selection, and limiting are most common. Mode/aggregation and performance tuning are less common. Advanced parameters appear last.

### 4.2 Parameter Reference

#### `where` — Filter Profiles

Accepts the same `Filter` type used by all other engines, plus raw selector strings as an escape hatch.

```python
# Typed filters (recommended — unified vocabulary)
ws.query_user(where=Filter.equals("plan", "premium"))
ws.query_user(where=[
    Filter.greater_than("ltv", 100),
    Filter.is_set("email"),
])

# Raw selector string (escape hatch — full engage API power)
ws.query_user(where='properties["plan"] == "premium" and properties["ltv"] > 100')
```

When `Filter` objects are provided, they are translated to engage API selector syntax internally (see §5). Multiple filters in a list are AND-combined.

**Type**: `Filter | list[Filter] | str | None`  
**Default**: `None` (no filtering — return all profiles)  
**Engage API mapping**: `where` parameter (selector string)

#### `cohort` — Filter by Cohort Membership

Restricts results to members of a saved cohort or an inline cohort definition. This is the primary mechanism for **behavioral filtering** — embed behavioral criteria inside a `CohortDefinition`.

```python
# Saved cohort by ID
ws.query_user(cohort=12345)

# Equivalent using Filter
ws.query_user(where=Filter.in_cohort(12345))

# Inline CohortDefinition with behavioral criteria
ws.query_user(
    cohort=CohortDefinition.all_of(
        CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
        CohortCriteria.has_property("plan", "premium"),
    ),
)
```

**Type**: `int | CohortDefinition | None`  
**Default**: `None`  
**Engage API mapping**: `filter_by_cohort` — `{"id": <int>}` for saved cohorts, `{"raw_cohort": <definition>}` for inline definitions  
**Mutual exclusions**: Cannot combine with `Filter.in_cohort()` in `where` (validation error U2).

#### `properties` — Select Output Properties

Controls which profile properties appear in the result DataFrame. When `None`, all properties are returned. For large profile sets, specifying properties dramatically reduces response size and speeds up queries.

```python
# All properties (default)
ws.query_user(limit=100)

# Selected properties only
ws.query_user(
    properties=["$email", "$name", "plan", "ltv", "signup_date"],
    limit=100,
)
```

**Type**: `list[str] | None`  
**Default**: `None` (all properties)  
**Engage API mapping**: `output_properties` (JSON-encoded array)  
**Note**: `$distinct_id` and `$last_seen` are always included regardless of selection. Only applies to `mode="profiles"`.

#### `sort_by` — Order Results

Sort profiles by a property value. Particularly useful with `limit` to get "top N" results.

```python
# Top 50 users by LTV
ws.query_user(sort_by="ltv", sort_order="descending", limit=50)

# Most recently active users
ws.query_user(sort_by="$last_seen", sort_order="descending", limit=100)
```

**Type**: `str | None`  
**Default**: `None` (Mixpanel default ordering)  
**Engage API mapping**: `sort_key='properties["<value>"]'`  
**Note**: Only applies to `mode="profiles"`.

#### `sort_order` — Sort Direction

**Type**: `Literal["ascending", "descending"]`  
**Default**: `"descending"`  
**Engage API mapping**: `sort_order`

#### `limit` — Maximum Profiles to Return

Caps the total number of profiles returned. Passed **server-side** to the ARB query engine (not just client-side truncation), so the API only returns `limit` profiles in the response — minimizing network transfer.

The default of `1` is deliberately safe: a bare `ws.query_user()` call returns 1 sample profile and the `total` count of all matching profiles. This is the cheapest possible "count + peek" operation — one lightweight API call.

```python
# Default: 1 profile + total count (safe, cheap)
result = ws.query_user(where=Filter.equals("plan", "premium"))
print(f"{result.total} premium users")  # e.g., 45000
print(result.df)  # 1 sample row

# Explicit larger fetch
result = ws.query_user(where=Filter.equals("plan", "premium"), limit=500)

# All matching profiles (explicit opt-in, may be large)
result = ws.query_user(where=Filter.equals("plan", "premium"), limit=None)
```

**Type**: `int | None`  
**Default**: `1`  
**Engage API mapping**: `limit` parameter (server-side cap on total results). `None` omits the limit parameter, fetching all matching profiles via pagination.  
**Note**: The `total` field in the result always reflects the **full** matching count regardless of `limit`. Only applies to `mode="profiles"`.

#### `search` — Full-Text Search

Search across profile properties for a text substring. Searches `$distinct_id`, `$email`, and selected output properties.

```python
ws.query_user(search="alice@example.com", limit=10)
```

**Type**: `str | None`  
**Default**: `None`  
**Engage API mapping**: `search` parameter  
**Note**: Only applies to `mode="profiles"`.

#### `distinct_id` / `distinct_ids` — Fetch Specific Users

Look up one or more users by their distinct ID.

```python
ws.query_user(distinct_id="user_abc123")
ws.query_user(distinct_ids=["user_1", "user_2", "user_3"])
```

**Type**: `str | None` / `list[str] | None`  
**Mutual exclusion**: Cannot provide both (validation error U1). Only applies to `mode="profiles"`.

#### `group_id` — Query Group Profiles

Query group analytics entities (companies, accounts) instead of user profiles.

```python
ws.query_user(group_id="companies", limit=100)
```

**Type**: `str | None`  
**Default**: `None` (user profiles)  
**Engage API mapping**: `data_group_id`

#### `as_of` — Point-in-Time Query

Query profile state at a specific point in the past.

```python
ws.query_user(as_of="2025-01-01", distinct_id="user_123")
ws.query_user(as_of=1704067200, distinct_id="user_123")
```

**Type**: `str | int | None`  
**Default**: `None` (current state)  
**Engage API mapping**: `as_of_timestamp` (Unix epoch integer)  
**Conversion**: `str` in YYYY-MM-DD format → midnight UTC Unix timestamp. `int` passed directly.

#### `mode` — Output Mode

Controls whether `query_user()` returns individual profile records or aggregate statistics.

```python
# Default: individual profiles as DataFrame
ws.query_user(mode="profiles", limit=100)

# Aggregate: count/sum/mean across matching profiles
ws.query_user(mode="aggregate", where=Filter.equals("plan", "premium"))
```

**Type**: `Literal["profiles", "aggregate"]`  
**Default**: `"profiles"`  
**Engage API mapping**: `filter_type=""` for profiles, `filter_type="stats"` for aggregate

| Mode | API Endpoint | Returns | DataFrame Shape |
|------|-------------|---------|-----------------|
| `"profiles"` | `/engage` (default) | Individual profile records | `[distinct_id, last_seen, prop1, ...]` |
| `"aggregate"` | `/engage` (stats) | Aggregate statistics | `[metric, value]` or `[segment, value]` |

#### `aggregate` — Aggregation Function (mode="aggregate" only)

The aggregation function to apply across matching profiles.

```python
# Count profiles
ws.query_user(mode="aggregate", where=Filter.equals("plan", "premium"))
# → DataFrame: metric="count", value=45000

# Average LTV
ws.query_user(mode="aggregate", aggregate="mean", aggregate_property="ltv")
# → DataFrame: metric="mean(ltv)", value=127.50

# Sum of revenue
ws.query_user(mode="aggregate", aggregate="sum", aggregate_property="revenue")
# → DataFrame: metric="sum(revenue)", value=5750000
```

**Type**: `Literal["count", "sum", "mean", "min", "max"]`  
**Default**: `"count"`  
**Engage API mapping**: `action` parameter — `"count()"`, `"sum(property)"`, `"mean(property)"`, etc.  
**Note**: `"sum"`, `"mean"`, `"min"`, `"max"` require `aggregate_property`. `"count"` does not.

#### `aggregate_property` — Property to Aggregate (mode="aggregate" only)

The profile property to compute the aggregation on. Required for all aggregation functions except `"count"`.

**Type**: `str | None`  
**Default**: `None`  
**Validation**: Required when `aggregate` is not `"count"` (validation error U15).

#### `segment_by` — Cohort Segmentation (mode="aggregate" only)

Break down aggregate results by cohort membership. Each cohort ID produces a separate row in the result DataFrame.

```python
# Count profiles segmented by cohorts
ws.query_user(
    mode="aggregate",
    segment_by=[123, 456, 789],  # cohort IDs
)
# → DataFrame:
#   segment    | count
#   cohort_123 | 5000
#   cohort_456 | 3200
#   cohort_789 | 1800
```

**Type**: `list[int] | None`  
**Default**: `None` (no segmentation — single aggregate value)  
**Engage API mapping**: `segment_by_cohorts` parameter

#### `parallel` — Enable Parallel Fetching (mode="profiles" only)

Enables concurrent page fetching for large result sets. When `True`, page 0 is fetched sequentially (to obtain total count and session ID), then remaining pages are fetched in parallel using a thread pool.

```python
# Sequential (default) — simple, predictable
ws.query_user(where=Filter.equals("plan", "premium"), limit=10000)

# Parallel — up to 5x faster for large result sets
ws.query_user(where=Filter.equals("plan", "premium"), limit=10000, parallel=True)
```

**Type**: `bool`  
**Default**: `False`  
**Performance**: Up to 5x speedup for multi-page result sets  
**Note**: Single-page results see no benefit. Only applies to `mode="profiles"`.

| Limit | Pages | Sequential | Parallel (5 workers) | Speedup |
|-------|-------|------------|---------------------|---------|
| 1 (default) | 1 | ~200ms | N/A | — |
| 1,000 | 1 | ~2s | ~2s | 1x |
| 5,000 | 5 | ~10s | ~2s | 5x |
| 25,000 | 25 | ~50s | ~10s | 5x |
| 60,000 | 60 | ~120s | ~24s | 5x |

#### `workers` — Concurrent Worker Count (parallel=True only)

Maximum number of concurrent page fetch threads. Capped at 5 (Mixpanel API hard limit). Values above 5 are silently reduced.

**Type**: `int`  
**Default**: `5`  
**Hard cap**: `5` (engage API concurrent query limit)  
**Note**: Ignored when `parallel=False`.

#### `include_all_users` — Include Non-Members in Cohort Queries

When used with `cohort`, returns all users with a flag indicating cohort membership.

**Type**: `bool`  
**Default**: `False`  
**Requires**: `cohort` parameter (validation error U7).

### 4.3 `UserQueryResult` Type

```python
@dataclass(frozen=True)
class UserQueryResult(ResultWithDataFrame):
    """Result from a user profile query.

    Supports two modes:
    - mode="profiles": Individual profile records with lazy DataFrame
    - mode="aggregate": Aggregate statistics (count/sum/mean/min/max)

    Attributes:
        computed_at: ISO timestamp when the query was computed by Mixpanel.
        total: Total profiles matching the filter, regardless of limit.
        profiles: Normalized profile dicts (empty for mode="aggregate").
        params: Engage API parameters used (for debugging/reproduction).
        meta: Response metadata (session_id, pages_fetched, etc.).
        mode: Which output mode produced this result.
        aggregate_data: Raw aggregate result (for mode="aggregate" only).
    """

    computed_at: str
    total: int
    profiles: list[dict[str, Any]]
    params: dict[str, Any]
    meta: dict[str, Any]
    mode: Literal["profiles", "aggregate"] = "profiles"
    aggregate_data: dict[str, Any] | int | float | None = None

    @property
    def df(self) -> pd.DataFrame:
        """Mode-aware DataFrame.

        mode="profiles":
            One row per user. Columns: distinct_id, last_seen, <properties>.
        mode="aggregate":
            One row per metric (or per segment). Columns: metric, value
            (or segment, value when segment_by used).
        """
        ...

    @property
    def distinct_ids(self) -> list[str]:
        """List of distinct IDs in the result (mode="profiles" only)."""
        ...

    @property
    def value(self) -> int | float | None:
        """Convenience: the aggregate value (mode="aggregate" only).

        Returns the single aggregate result when no segmentation is used.
        Returns None for mode="profiles" or segmented aggregates.
        """
        ...
```

**Mode-aware behavior**:

| Field | `mode="profiles"` | `mode="aggregate"` |
|-------|--------------------|--------------------|
| `profiles` | List of normalized profile dicts | Empty list `[]` |
| `aggregate_data` | `None` | Raw aggregate result (int/float/dict) |
| `.df` | `[distinct_id, last_seen, props...]` | `[metric, value]` or `[segment, value]` |
| `.distinct_ids` | List of IDs from profiles | Empty list `[]` |
| `.value` | `None` | Scalar aggregate result |
| `.total` | Total matching count | Total matching count |

### 4.4 DataFrame Schema

#### Profile Mode (`mode="profiles"`)

```
┌──────────────┬─────────────────────┬───────────────────┬─────────┬────────┬─────┐
│ distinct_id  │ last_seen           │ email             │ plan    │ city   │ ltv │
├──────────────┼─────────────────────┼───────────────────┼─────────┼────────┼─────┤
│ user_001     │ 2025-04-10 14:30:00 │ alice@example.com │ premium │ SF     │ 250 │
│ user_002     │ 2025-04-09 08:20:00 │ bob@example.com   │ free    │ NYC    │  15 │
│ user_003     │ 2025-04-11 22:15:00 │ None              │ premium │ London │ 180 │
└──────────────┴─────────────────────┴───────────────────┴─────────┴────────┴─────┘
```

**Column rules**:

| Column | Type | Presence |
|--------|------|----------|
| `distinct_id` | `str` | Always first column |
| `last_seen` | `str` (ISO datetime) | Always present (if profile has activity) |
| `<property>` | Varies | All properties, or those specified via `properties=` |

**Construction logic**:
1. Extract `distinct_id` and `last_seen` from each normalized profile
2. Flatten `properties` dict — each key becomes a column
3. Union all property keys across profiles (fill missing with `NaN`)
4. If `properties` specified, only include those columns (plus `distinct_id`, `last_seen`)
5. Column order: `distinct_id`, `last_seen`, then alphabetically sorted properties

**Property name normalization**: The `$` prefix on Mixpanel built-in properties is stripped in DataFrame columns: `$email` → `email`, `$name` → `name`, `$city` → `city`. Custom properties (no `$` prefix) are unchanged. The `properties` parameter accepts either form.

#### Aggregate Mode (`mode="aggregate"`)

**Without segmentation**:

```
┌────────────┬──────────┐
│ metric     │ value    │
├────────────┼──────────┤
│ count      │ 45000    │
└────────────┴──────────┘
```

```
┌────────────┬──────────┐
│ metric     │ value    │
├────────────┼──────────┤
│ mean(ltv)  │ 127.50   │
└────────────┴──────────┘
```

**With cohort segmentation** (`segment_by=[123, 456]`):

```
┌────────────┬──────────┐
│ segment    │ value    │
├────────────┼──────────┤
│ cohort_123 │ 5000     │
│ cohort_456 │ 3200     │
└────────────┴──────────┘
```

### 4.5 `build_user_params()`

Generates engage API parameters without executing the query:

```python
def build_user_params(
    self,
    *,
    # Same parameters as query_user(), excluding limit, parallel, workers
    where: Filter | list[Filter] | str | None = None,
    cohort: int | CohortDefinition | None = None,
    properties: list[str] | None = None,
    sort_by: str | None = None,
    sort_order: Literal["ascending", "descending"] = "descending",
    search: str | None = None,
    distinct_id: str | None = None,
    distinct_ids: list[str] | None = None,
    group_id: str | None = None,
    as_of: str | int | None = None,
    mode: Literal["profiles", "aggregate"] = "profiles",
    aggregate: Literal["count", "sum", "mean", "min", "max"] = "count",
    aggregate_property: str | None = None,
    segment_by: list[int] | None = None,
    include_all_users: bool = False,
) -> dict[str, Any]:
```

**Return format** (profiles mode):

```python
{
    "project_id": 12345,
    "where": 'properties["plan"] == "premium"',
    "output_properties": ["$email", "$name", "plan"],
    "sort_key": 'properties["ltv"]',
    "sort_order": "descending",
    "filter_by_cohort": {"id": 67890},
}
```

**Return format** (aggregate mode):

```python
{
    "project_id": 12345,
    "filter_type": "stats",
    "where": 'properties["plan"] == "premium"',
    "action": "mean(ltv)",
    "segment_by_cohorts": {"cohort_123": true, "cohort_456": true},
}
```

---

## 5. Filter Translation

The critical bridge between the unified `Filter` type and the engage API's selector string syntax.

### 5.1 Architecture

```
Filter.equals("plan", "premium")
         │
         ▼
filter_to_selector(filter)        ← New utility function
         │
         ▼
'properties["plan"] == "premium"'  → Engage API `where` parameter
```

A new function `filter_to_selector()` in `_internal/query/user_builders.py` translates `Filter` instances to engage selector strings.

### 5.2 Operator Mapping

| Filter Factory Method | Internal Operator | Selector Output | Example |
|---|---|---|---|
| `Filter.equals("p", "v")` | `"equals"` | `properties["p"] == "v"` | `properties["plan"] == "premium"` |
| `Filter.equals("p", ["a","b"])` | `"equals"` | `... == "a" or ... == "b"` | Multi-value OR |
| `Filter.not_equals("p", "v")` | `"does not equal"` | `properties["p"] != "v"` | `properties["plan"] != "free"` |
| `Filter.contains("p", "v")` | `"contains"` | `"v" in properties["p"]` | `"corp" in properties["email"]` |
| `Filter.not_contains("p", "v")` | `"does not contain"` | `not "v" in properties["p"]` | `not "gmail" in properties["email"]` |
| `Filter.greater_than("p", n)` | `"is greater than"` | `properties["p"] > n` | `properties["age"] > 25` |
| `Filter.less_than("p", n)` | `"is less than"` | `properties["p"] < n` | `properties["revenue"] < 100` |
| `Filter.between("p", a, b)` | `"is between"` | `... >= a and ... <= b` | `properties["age"] >= 18 and properties["age"] <= 65` |
| `Filter.is_set("p")` | `"is set"` | `defined(properties["p"])` | `defined(properties["email"])` |
| `Filter.is_not_set("p")` | `"is not set"` | `not defined(properties["p"])` | `not defined(properties["phone"])` |
| `Filter.is_true("p")` | `"is true"` | `properties["p"] == true` | `properties["active"] == true` |
| `Filter.is_false("p")` | `"is false"` | `properties["p"] == false` | `properties["churned"] == false` |

### 5.3 Property Name Translation

```python
def _property_to_selector(prop: str) -> str:
    """Translate a property name to engage selector syntax."""
    return f'properties["{prop}"]'
```

No automatic `$` prefix handling — the property name is used as-is. `Filter.equals("$email", "alice@example.com")` → `properties["$email"] == "alice@example.com"`.

### 5.4 Multiple Filter Combination

Multiple filters are AND-combined:

```python
where=[
    Filter.equals("plan", "premium"),
    Filter.greater_than("ltv", 100),
    Filter.is_set("email"),
]
# → 'properties["plan"] == "premium" and properties["ltv"] > 100 and defined(properties["email"])'
```

### 5.5 Cohort Filter Extraction

When `Filter.in_cohort()` appears in the `where` list, it is **extracted** and routed to the `filter_by_cohort` engage API parameter:

```python
where=[
    Filter.in_cohort(12345),
    Filter.equals("plan", "premium"),
]
# Extracted: filter_by_cohort={"id": 12345}
# Selector: 'properties["plan"] == "premium"'
```

`Filter.not_in_cohort()` cannot be directly mapped to an engage API parameter. If encountered, a `BookmarkValidationError` is raised with a suggestion to use cohort-based approaches or raw selector syntax.

### 5.6 CohortDefinition in Filter

When `Filter.in_cohort(CohortDefinition(...))` is used, the inline definition is passed to `filter_by_cohort` as a `raw_cohort`:

```python
where=Filter.in_cohort(
    CohortDefinition.all_of(
        CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
    )
)
# Extracted: filter_by_cohort={"raw_cohort": <serialized definition>}
```

This is the **`CohortDefinition` path** for behavioral filtering — an alternative to the direct `behaviors` parameter. Both paths work; see §8 for when to use which.

### 5.7 Raw Selector Escape Hatch

When `where` is a `str`, it is passed directly to the engage API:

```python
ws.query_user(where='properties["$last_seen"] > "2025-01-01"')
```

A `str` value for `where` cannot be combined with `Filter` objects (validation error U10).

### 5.8 Value Formatting

| Python Type | Selector Format | Example |
|---|---|---|
| `str` | Double-quoted | `"premium"` |
| `int` | Bare number | `100` |
| `float` | Bare number | `99.5` |
| `bool` (via `is_true`/`is_false`) | Bare keyword | `true` / `false` |
| `list[str]` (multi-value equals) | OR chain | `... == "a" or ... == "b"` |

---

## 6. Validation Rules

Following the two-layer validation pattern. All errors collected before raising `BookmarkValidationError`.

### Layer 1: Argument Validation

| Code | Rule |
|---|---|
| **U1** | `distinct_id` and `distinct_ids` are mutually exclusive |
| **U2** | `cohort` and `Filter.in_cohort()` in `where` are mutually exclusive |
| **U3** | `limit` must be positive if provided |
| **U4** | `distinct_ids` must be non-empty list if provided |
| **U5** | `sort_by` must be non-empty string if provided |
| **U6** | `as_of` string must be valid YYYY-MM-DD |
| **U7** | `include_all_users` requires `cohort` |
| **U8** | `as_of` timestamp must not be in the future |
| **U9** | `where` as string and `where` as Filter are mutually exclusive types |
| **U10** | Filter property names must be non-empty strings |
| **U11** | `properties` items must be non-empty strings |
| **U12** | `Filter.not_in_cohort()` not supported for profile queries |
| **U13** | At most one `Filter.in_cohort()` in where list |
| **U14** | `aggregate_property` required when `aggregate` is not `"count"` |
| **U15** | `aggregate_property` must not be set when `aggregate` is `"count"` |
| **U16** | `segment_by` requires `mode="aggregate"` |
| **U17** | `segment_by` cohort IDs must be positive integers |
| **U18** | `parallel` only applies to `mode="profiles"` |
| **U19** | `sort_by` only applies to `mode="profiles"` |
| **U20** | `search` only applies to `mode="profiles"` |
| **U21** | `distinct_id`/`distinct_ids` only apply to `mode="profiles"` |
| **U22** | `properties` only applies to `mode="profiles"` |
| **U23** | `workers` must be between 1 and 5 |
| **U24** | `cohort` as `CohortDefinition` must serialize successfully via `to_dict()` |

### Layer 2: Parameter Validation

| Code | Rule |
|---|---|
| **UP1** | `sort_order` must be "ascending" or "descending" |
| **UP2** | `filter_by_cohort` must have "id" or "raw_cohort" key |
| **UP3** | `output_properties` must be non-empty array if present |
| **UP4** | `action` must be valid aggregation expression |

---

## 7. Architecture & Implementation

### 7.1 Component Layers

```
┌─────────────────────────────────────────────────────────┐
│                  Workspace (Public API)                   │
│                                                           │
│  query_user()           build_user_params()               │
│    │                       │                              │
│    ├── _validate_user_args()  ← Layer 1 validation        │
│    │                                                      │
│    ├── _build_user_params()   ← Filter translation,       │
│    │                            param construction        │
│    │                                                      │
│    ├── mode="profiles"?                                   │
│    │   ├── parallel=True?                                 │
│    │   │   └── _execute_user_query_parallel()             │
│    │   │       └── ThreadPoolExecutor                     │
│    │   │           └── api_client.export_profiles_page()  │
│    │   └── parallel=False?                                │
│    │       └── _execute_user_query_sequential()           │
│    │           └── api_client.export_profiles_page()      │
│    │                                                      │
│    ├── mode="aggregate"?                                  │
│    │   └── _execute_user_aggregate()                      │
│    │       └── api_client.engage_stats()  ← NEW           │
│    │                                                      │
│    └── _transform_user_result()  ← Build UserQueryResult  │
│                                                           │
├───────────────────────────────────────────────────────────┤
│              Filter Translation Layer (NEW)                │
│                                                           │
│  filter_to_selector(filter) → str                         │
│  filters_to_selector(filters) → str                       │
│  extract_cohort_filter(filters) → (cohort, remaining)     │
│                                                           │
├───────────────────────────────────────────────────────────┤
│              API Client Layer                              │
│                                                           │
│  export_profiles_page()  → ProfilePageResult  (existing)  │
│  engage_stats()          → dict               (NEW)       │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### 7.2 Data Flow — Profile Mode (Sequential)

```
query_user(where=Filter.equals("plan", "premium"), properties=["$email"])
    │  (limit=1 by default)
    │
    ▼  _validate_user_args() — checks U1-U24
    ▼  _build_user_params() — Filter → selector, cohort extraction
    ▼  _execute_user_query_sequential(params, limit=1)
    │    Page 0 with limit=1 → total=45000, 1 profile returned
    │    Single API call, minimal payload
    ▼  _transform_user_result(profiles, total=45000, ...)
    │
    ▼  UserQueryResult(total=45000, profiles=[1 dict], mode="profiles")
       .df → DataFrame with 1 row (sample profile)
       .total → 45000 (full matching count)
```

### 7.3 Data Flow — Profile Mode (Parallel)

```
query_user(..., parallel=True, limit=10000)
    │
    ▼  _validate_user_args(), _build_user_params()
    ▼  _execute_user_query_parallel(params, limit=10000, workers=5)
    │
    │  ┌─ Sequential: Page 0 ─────────────────────────────────────┐
    │  │  → total=45000, session_id="abc", page_size=1000          │
    │  │  → num_pages_needed = min(ceil(10000/1000), ceil(45000/1000)) = 10 │
    │  │  → Collect page 0 profiles                                │
    │  └──────────────────────────────────────────────────────────┘
    │
    │  ┌─ Parallel: Pages 1-9 via ThreadPoolExecutor(max_workers=5)─┐
    │  │  Worker 1: page 1  ──┐                                      │
    │  │  Worker 2: page 2  ──┤                                      │
    │  │  Worker 3: page 3  ──┼── as_completed() ── collect profiles │
    │  │  Worker 4: page 4  ──┤                                      │
    │  │  Worker 5: page 5  ──┘                                      │
    │  │  Worker 1: page 6  ──┐  (workers recycled)                  │
    │  │  Worker 2: page 7  ──┤                                      │
    │  │  Worker 3: page 8  ──┼── as_completed() ── collect profiles │
    │  │  Worker 4: page 9  ──┘                                      │
    │  └─────────────────────────────────────────────────────────────┘
    │
    │  Combine all page results, truncate to limit
    ▼
    UserQueryResult(total=45000, profiles=[10000 dicts], meta={pages_fetched: 10})
```

**Key parallel implementation details**:

1. **Page 0 always sequential** — must obtain `total`, `session_id`, and `page_size` before dispatching parallel work
2. **Worker cap at 5** — Mixpanel engage API hard limit; exceeding triggers 429s
3. **Limit-aware dispatch** — only dispatch `ceil(limit / page_size)` pages, not all pages
4. **`as_completed()` collection** — process pages as they finish, don't wait for slowest
5. **No DuckDB concern** — collecting into a list, not writing to storage (simpler than `ParallelProfileFetcherService`)
6. **Rate limit warning** — log warning if total pages > 48 (approaching 60/hour limit)
7. **Error tolerance** — failed pages recorded in `meta["failed_pages"]`; partial results returned rather than failing entirely
8. **Exponential backoff** — built into `api_client._request()` for 429 responses (1s, 2s, 4s)

### 7.4 Data Flow — Aggregate Mode

```
query_user(mode="aggregate", where=Filter.equals("plan", "premium"),
           aggregate="mean", aggregate_property="ltv", segment_by=[123, 456])
    │
    ▼  _validate_user_args() — checks mode-specific rules (U14-U22)
    ▼  _build_user_params() — builds stats endpoint params
    │    {
    │      "filter_type": "stats",
    │      "where": 'properties["plan"] == "premium"',
    │      "action": "mean(ltv)",
    │      "segment_by_cohorts": {"cohort_123": true, "cohort_456": true},
    │    }
    ▼  _execute_user_aggregate(params)
    │    → Single POST to /engage (stats sub-endpoint)
    │    → Response: {"results": {"cohort_123": 145.0, "cohort_456": 98.5}, ...}
    ▼  _transform_user_result(aggregate_data={"cohort_123": 145.0, ...}, ...)
    │
    ▼  UserQueryResult(
         mode="aggregate",
         total=45000,
         profiles=[],
         aggregate_data={"cohort_123": 145.0, "cohort_456": 98.5},
       )
       .df →  segment    | value
              cohort_123 | 145.0
              cohort_456 | 98.5
       .value → None (segmented, use .df instead)
```

**Stats endpoint behavior**:
- Always aggregates over full date range (`unit="range"`, `from_date="2010-01-01"` forced internally)
- Single API call, no pagination needed
- Response is a scalar value or dict of values (when segmented)

### 7.5 API Client — New Method

```python
def engage_stats(
    self,
    *,
    where: str | None = None,
    action: str = "count()",
    cohort_id: str | None = None,
    segment_by_cohorts: dict[str, bool] | None = None,
    group_id: str | None = None,
    as_of_timestamp: int | None = None,
    include_all_users: bool = False,
) -> dict[str, Any]:
    """Query aggregate statistics from the Engage stats endpoint.

    Returns the raw stats response with 'results', 'status', and
    'computed_at' fields.
    """
```

This is a new method on `MixpanelAPIClient` that POSTs to `/engage` with `filter_type=stats`.

### 7.6 Memory Management

1. **`limit=1` default**: Safe out-of-the-box — 1 API call, 1 profile, total count
2. **Server-side limit**: `limit` is passed to the ARB query engine, so the API only returns `limit` profiles — no wasted network transfer
3. **`properties` parameter**: Reduces per-profile payload by selecting only needed columns
4. **Parallel limit-awareness**: Only fetches `ceil(limit / page_size)` pages
5. **Streaming alternative**: For memory-constrained processing, use `stream_profiles()` instead
6. **Lazy DataFrame**: DataFrame only materialized when `.df` is accessed
7. **Aggregate mode**: Single API call, minimal memory footprint

---

## 8. Behavioral Filtering via CohortDefinition

Behavioral filtering in `query_user()` is expressed exclusively through the `cohort` parameter using `CohortDefinition` + `CohortCriteria`. This eliminates raw string selectors from the API surface, keeping agents safe from hallucinated behavior-reference syntax.

**Why not a direct `behaviors` parameter?** The engage API does accept a raw `behaviors` list, but using it requires pairing with a raw `where` string that references behavior names (e.g., `'behaviors["bought"] >= 3'`). This string is:
- Unvalidated at the Python layer (errors surface only at query time)
- A hallucination magnet for AI agents (behavior names, operators, and quoting must all be exact)
- Redundant with `CohortDefinition`, which the server converts behaviors into anyway

The `stream_profiles()` method retains raw `behaviors` support as a low-level escape hatch. `query_user()` offers only the typed path.

### 8.1 Simple Behavioral Filter

```python
# "Users who purchased at least 3 times in the last 30 days"
ws.query_user(
    cohort=CohortDefinition.all_of(
        CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
    ),
    properties=["$email", "plan", "ltv"],
    sort_by="ltv",
    sort_order="descending",
)
```

### 8.2 Behavioral + Property Criteria

```python
# "Premium users who purchased 3+ times AND viewed pricing page"
ws.query_user(
    cohort=CohortDefinition.all_of(
        CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
        CohortCriteria.did_event("View Pricing", at_least=1, within_days=7),
        CohortCriteria.has_property("plan", "premium"),
    ),
    properties=["$email", "ltv"],
)
```

### 8.3 OR Logic (Any-of)

```python
# "Users who purchased OR added to cart in the last 7 days"
ws.query_user(
    cohort=CohortDefinition.any_of(
        CohortCriteria.did_event("Purchase", at_least=1, within_days=7),
        CohortCriteria.did_event("Add to Cart", at_least=1, within_days=7),
    ),
    properties=["$email", "plan"],
)
```

### 8.4 Saved Cohort by ID

```python
# Reuse a cohort defined in the Mixpanel UI
ws.query_user(cohort=12345, properties=["$email", "plan"])
```

### 8.5 Implementation: `cohort` Parameter Routing

```python
if isinstance(cohort, int):
    params["filter_by_cohort"] = json.dumps({"id": cohort})
elif isinstance(cohort, CohortDefinition):
    params["filter_by_cohort"] = json.dumps({
        "raw_cohort": cohort.to_dict()
    })
```

The `CohortDefinition.to_dict()` serializes the full selector tree including embedded behavioral criteria. The engage API accepts this via `filter_by_cohort.raw_cohort` — server-side, this follows the same code path as the legacy `behaviors` parameter (both go through the cohort query engine).

---

## 9. Alignment with Existing Engines

### 9.1 Shared Vocabulary

| Feature | Insights | Funnels | Retention | Flows | **Users** |
|---|---|---|---|---|---|
| `where=Filter.equals(...)` | Yes | Yes | Yes | Cohort only | **Yes** |
| `group_by=` | Yes | Yes | Yes | No | No (N/A) |
| `from_date`/`to_date` | Yes | Yes | Yes | Yes | No (N/A) |
| `last=` | Yes | Yes | Yes | Yes | No (N/A) |
| `mode=` | Yes | Yes | Yes | Yes | **Yes** |
| `properties=` | No | No | No | No | **Yes (new)** |
| `sort_by=` | No | No | No | No | **Yes (new)** |
| `limit=` | No | No | No | No | **Yes (new)** |
| `parallel=` | No | No | No | No | **Yes (new)** |
| `aggregate=` | No | No | No | No | **Yes (new)** |
| Result `.df` | Yes | Yes | Yes | Yes | **Yes** |
| Result `.params` | Yes | Yes | Yes | Yes | **Yes** |
| Result `.meta` | Yes | Yes | Yes | Yes | **Yes** |
| `build_*_params()` | Yes | Yes | Yes | Yes | **Yes** |
| `BookmarkValidationError` | Yes | Yes | Yes | Yes | **Yes** |

### 9.2 Differences & Rationale

| Difference | Rationale |
|---|---|
| **No `group_by`** | Profiles are individual records, not aggregates. Use `segment_by` in aggregate mode for cohort-level breakdown. |
| **No `from_date`/`to_date`/`last`** | Profiles represent current state. Use `as_of` for historical snapshots. The stats endpoint forces its own date range. |
| **No `math`** | No per-event aggregation. Use `aggregate` in aggregate mode for profile-level statistics. |
| **`where` accepts `str`** | Engage API uses selector strings. Raw strings are the natural escape hatch for advanced syntax. |
| **`params` is not bookmark JSON** | Engage uses a different parameter format. Can reproduce query but not save as Mixpanel bookmark. |
| **`parallel` is new** | Other engines return bounded data from single API calls. Profiles need multi-page fetching. |

---

## 10. Composition Examples

### 10.1 Profile-First Analysis

```python
top_users = ws.query_user(
    where=[
        Filter.equals("plan", "premium"),
        Filter.greater_than("ltv", 100),
    ],
    properties=["$email", "$name", "plan", "ltv", "company"],
    sort_by="ltv",
    sort_order="descending",
    limit=100,
)

print(f"Top {len(top_users.profiles)} of {top_users.total} premium users")
print(top_users.df.describe())
```

### 10.2 Aggregate Statistics

```python
# How many premium users?
result = ws.query_user(
    mode="aggregate",
    where=Filter.equals("plan", "premium"),
)
print(f"Premium users: {result.value}")

# Average LTV by cohort
result = ws.query_user(
    mode="aggregate",
    aggregate="mean",
    aggregate_property="ltv",
    segment_by=[123, 456],  # "Premium" and "Enterprise" cohorts
)
print(result.df)
#   segment    | value
#   cohort_123 | 145.0
#   cohort_456 | 320.5
```

### 10.3 Behavioral Filtering

```python
# Users who purchased 3+ times in last 30 days, sorted by LTV
active_buyers = ws.query_user(
    cohort=CohortDefinition.all_of(
        CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
    ),
    properties=["$email", "plan", "ltv"],
    sort_by="ltv",
    sort_order="descending",
    limit=200,
)
print(f"Active buyers: {active_buyers.total}")

# Behavioral + property: premium users who are active buyers
power_users = ws.query_user(
    cohort=CohortDefinition.all_of(
        CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
        CohortCriteria.did_event("Login", at_least=5, within_days=7),
        CohortCriteria.has_property("plan", "premium"),
    ),
    properties=["$email", "ltv", "company"],
    sort_by="ltv",
    sort_order="descending",
)
```

### 10.4 Cross-Engine: Insights → Users

```python
# Step 1: Which plans drive the most DAU?
dau_by_plan = ws.query("Login", math="dau", group_by="plan", last=30)

# Step 2: Get profiles from top plan
top_plan = dau_by_plan.df.sort_values("count", ascending=False).iloc[0]["event"]
users_on_plan = ws.query_user(
    where=Filter.equals("plan", top_plan),
    properties=["$email", "company", "ltv"],
    sort_by="ltv",
    sort_order="descending",
    limit=200,
)

print(f"Plan '{top_plan}' has {users_on_plan.total} users")
```

### 10.5 Cross-Engine: Funnel → Users (Cohort Bridge)

```python
# Step 1: Measure onboarding funnel
funnel = ws.query_funnel(
    ["Signup", "Onboarding Complete", "First Purchase"],
    last=30,
)

# Step 2: Get profiles of activated users (saved cohort)
activated = ws.query_user(
    cohort=789,  # "Completed Onboarding" cohort
    properties=["$email", "plan", "signup_date", "onboarding_score"],
    sort_by="onboarding_score",
    sort_order="descending",
)

print(activated.df.groupby("plan")["onboarding_score"].mean())
```

### 10.6 Parallel Fetch for Large Result Sets

```python
# Fetch all premium users with parallel fetching
all_premium = ws.query_user(
    where=Filter.equals("plan", "premium"),
    properties=["$email", "ltv", "signup_date"],
    parallel=True,
    workers=5,
)

print(f"Fetched {len(all_premium.profiles)} profiles "
      f"across {all_premium.meta['pages_fetched']} pages "
      f"in {all_premium.meta['duration_seconds']:.1f}s")
```

### 10.7 Group Profiles

```python
companies = ws.query_user(
    group_id="companies",
    where=Filter.greater_than("arr", 50000),
    properties=["company_name", "arr", "employee_count", "plan"],
    sort_by="arr",
    sort_order="descending",
    limit=50,
)
```

---

## 11. Implementation Plan

All features ship in a single phase. Tasks are organized by dependency.

### Task 1: New Types

**File**: `src/mixpanel_data/types.py`

Add `UserQueryResult` frozen dataclass extending `ResultWithDataFrame`:
- Fields: `computed_at`, `total`, `profiles`, `params`, `meta`, `mode`, `aggregate_data`
- Property: `df` (lazy cached, mode-aware DataFrame)
- Property: `distinct_ids` (convenience list, profiles mode)
- Property: `value` (convenience scalar, aggregate mode)
- Method: `to_dict()` (JSON serialization)

Add validation error codes `U1`–`U24` and `UP1`–`UP4`.

**Tests**: `tests/test_types_user_query_result.py`
- DataFrame construction from profiles (column schema, $-prefix stripping)
- DataFrame from aggregate data (metric/value schema, segmented schema)
- Empty profiles → empty DataFrame
- `distinct_ids` and `value` properties
- Mode-aware behavior
- `to_dict()` serialization
- Lazy caching behavior

#### Task 2: Filter → Selector Translation

**File**: `src/mixpanel_data/_internal/query/user_builders.py` (new)

Functions:
- `filter_to_selector(filter: Filter) -> str`
- `filters_to_selector(filters: list[Filter]) -> str`
- `extract_cohort_filter(filters: list[Filter]) -> tuple[int | CohortDefinition | None, list[Filter]]`
- `_property_to_selector(prop: str) -> str`
- `_value_to_selector(value: str | int | float | bool) -> str`

**Tests**: `tests/test_user_builders.py`
- Each operator mapping (equals, not_equals, contains, greater_than, etc.)
- Multi-value equals (OR chain)
- Multiple filters AND combination
- Cohort filter extraction (saved ID and inline CohortDefinition)
- Value formatting (strings, numbers, booleans)
- Edge cases: special characters in values, empty strings

#### Task 3: Argument Validation

**File**: `src/mixpanel_data/_internal/query/user_validators.py` (new)

Function: `validate_user_args(...) -> list[ValidationError]`

Implements rules U1–U23. Includes mode-aware validation (aggregate-only params rejected in profiles mode and vice versa).

**Tests**: `tests/test_user_validators.py`
- Each validation rule individually
- Mode-specific validation (aggregate params with profiles mode → error)
- Multiple simultaneous violations
- Valid argument combinations pass cleanly

#### Task 4: Parameter Builder

**File**: `src/mixpanel_data/workspace.py`

Private method `_build_user_params()`:
1. Call `validate_user_args()` — raise if errors
2. Handle `where` (Filter translation or raw string passthrough)
3. Extract cohort filters; route CohortDefinition to `raw_cohort`
4. Build engage API params dict (different for profiles vs aggregate)
5. Handle `as_of` conversion (YYYY-MM-DD → Unix timestamp)
6. Handle `sort_by` → `sort_key` translation
7. Handle `aggregate` → `action` translation
8. Handle `segment_by` → `segment_by_cohorts` translation
9. Run Layer 2 validation

Public method `build_user_params()` — delegates to private method.

**Tests**: `tests/test_workspace_build_user_params.py`

**Depends on**: Tasks 2, 3

#### Task 5: API Client — `engage_stats()`

**File**: `src/mixpanel_data/_internal/api_client.py`

New method `engage_stats()`:
- POSTs to `/engage` with `filter_type=stats`
- Accepts `where`, `action`, `cohort_id`, `segment_by_cohorts`, etc.
- Returns raw response dict

**Tests**: `tests/test_api_client_engage_stats.py`

#### Task 6: Sequential Query Execution

**File**: `src/mixpanel_data/workspace.py`

Private method `_execute_user_query_sequential()`:
- Use `export_profiles_page()` for page 0 (capture total, session_id)
- Sequential pagination until limit or exhaustion
- Return collected profiles + metadata

**Tests**: `tests/test_workspace_query_user.py`

**Depends on**: Tasks 1, 4

#### Task 7: Parallel Query Execution

**File**: `src/mixpanel_data/workspace.py`

Private method `_execute_user_query_parallel()`:
- Page 0 sequential (metadata)
- Calculate pages needed (limit-aware)
- ThreadPoolExecutor(max_workers=min(workers, 5))
- Dispatch pages 1..N, collect via `as_completed()`
- Rate limit warning if pages > 48
- Error tolerance: failed pages in meta, partial results returned
- Return collected profiles + metadata

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def _execute_user_query_parallel(
    self,
    params: dict[str, Any],
    limit: int | None,
    workers: int,
) -> tuple[list[dict], int, str, dict]:
    api_client = self._require_api_client()

    # Page 0: sequential for metadata
    page_0 = api_client.export_profiles_page(page=0, ...)
    profiles = list(page_0.profiles)
    total = page_0.total
    session_id = page_0.session_id

    if not page_0.has_more or (limit and len(profiles) >= limit):
        # Single page or limit already met
        if limit:
            profiles = profiles[:limit]
        return profiles, total, page_0.computed_at, {...}

    # Calculate pages needed
    pages_for_limit = (
        math.ceil(limit / page_0.page_size) if limit else page_0.num_pages
    )
    total_pages = min(pages_for_limit, page_0.num_pages)

    if total_pages > 48:
        logger.warning(
            "Fetching %d pages approaches the 60/hour rate limit", total_pages
        )

    # Parallel fetch pages 1..N
    failed_pages: list[int] = []
    capped_workers = min(workers, 5)

    with ThreadPoolExecutor(max_workers=capped_workers) as executor:
        futures = {
            executor.submit(
                api_client.export_profiles_page,
                page=page_idx,
                session_id=session_id,
                ...
            ): page_idx
            for page_idx in range(1, total_pages)
        }

        for future in as_completed(futures):
            page_idx = futures[future]
            try:
                result = future.result()
                profiles.extend(result.profiles)
            except Exception as e:
                failed_pages.append(page_idx)
                logger.warning("Page %d failed: %s", page_idx, e)

            # Early exit if limit reached
            if limit and len(profiles) >= limit:
                executor.shutdown(wait=False, cancel_futures=True)
                break

    if limit:
        profiles = profiles[:limit]

    meta = {
        "session_id": session_id,
        "pages_fetched": total_pages - len(failed_pages),
        "failed_pages": failed_pages,
        "parallel": True,
        "workers": capped_workers,
    }

    return profiles, total, computed_at, meta
```

**Tests**: `tests/test_workspace_query_user_parallel.py`
- Single page → no parallel benefit
- Multi-page parallel fetch
- Limit-aware page dispatch
- Failed page handling (partial results)
- Worker cap enforcement
- Rate limit warning threshold

**Depends on**: Tasks 1, 4

#### Task 8: Aggregate Query Execution

**File**: `src/mixpanel_data/workspace.py`

Private method `_execute_user_aggregate()`:
- Build stats endpoint params
- Call `api_client.engage_stats()`
- Parse response (scalar or segmented dict)
- Return aggregate data + metadata

**Tests**: `tests/test_workspace_query_user_aggregate.py`

**Depends on**: Tasks 1, 4, 5

#### Task 9: Public `query_user()` Method

**File**: `src/mixpanel_data/workspace.py`

Public method tying everything together:
1. `_build_user_params()`
2. Route by mode:
   - `"profiles"` + `parallel=False` → `_execute_user_query_sequential()`
   - `"profiles"` + `parallel=True` → `_execute_user_query_parallel()`
   - `"aggregate"` → `_execute_user_aggregate()`
3. Normalize profiles via `transform_profile()`
4. Build and return `UserQueryResult`

**Tests**: `tests/test_workspace_query_user_integration.py`

**Depends on**: Tasks 6, 7, 8

#### Task 10: Public API Exports

**File**: `src/mixpanel_data/__init__.py`

Export `UserQueryResult` from public API.

#### Task 11: Documentation

**File**: `docs/guide/unified-query-system.md`

Add section on `query_user()`:
- Overview as 5th engine
- Basic usage, aggregate mode, parallel fetching
- Behavioral filtering via CohortDefinition
- Composition with other engines

### Dependency Map

```
Task 1 (Types) ─────────────────────────────┐
Task 2 (Filter Translation) ──► Task 4 ─────┤
Task 3 (Validation) ──────────► (Param   ───┤
                                 Builder)    │
Task 5 (API Client) ──────────────────────┐  │
                                          │  │
                          ┌── Task 6 (Sequential) ──┐
               Task 4 ───┤                          ├─► Task 9 (Public API) ─► Task 10
                          ├── Task 7 (Parallel) ────┤
                          └── Task 8 (Aggregate) ───┘

Task 11 (Docs) — independent, can proceed in parallel
```

Tasks 1, 2, 3, 5 can execute in parallel. Task 4 depends on 2 and 3. Tasks 6, 7, 8 depend on 1 and 4 (and 5 for aggregate). Task 9 depends on 6, 7, 8.

### Testing Strategy

| Test Level | Scope | Framework |
|---|---|---|
| **Unit** | Filter translation, validation, types, aggregate parsing | pytest, mocked |
| **Unit** | Parameter building, DataFrame construction | pytest, mocked |
| **Integration** | End-to-end query_user() with mocked API client | pytest, dependency injection |
| **Integration** | Parallel execution with mocked page responses | pytest, ThreadPoolExecutor |
| **PBT** | Filter translation invariants | Hypothesis |
| **PBT** | DataFrame schema invariants (profiles + aggregate) | Hypothesis |

**Property-based test ideas**:
- For any Filter, `filter_to_selector()` produces a syntactically valid selector string
- For any list of profiles, `.df` has exactly `len(profiles)` rows
- `distinct_id` column is always present and matches profile data
- When `properties` specified, only those columns (plus `distinct_id`, `last_seen`) appear
- `total >= len(profiles)` always holds
- For aggregate mode, `.value` matches first row of `.df`

---

## 12. Future Considerations

These are deliberately out of scope for v1 but worth noting:

1. **CLI integration** (`mp query user`): Add Typer command with `--format`, `--parallel`, `--mode` flags
2. **Reactive limit warnings**: Log to stderr when `limit=None` fetches > 10k profiles
3. **Async support**: `async_query_user()` using `asyncio` + `httpx.AsyncClient`
4. **Identity resolution**: Expose the `/engage/aliases` sub-endpoint for ID mapping
5. **Property value discovery**: Expose `/engage/values` for profile property value listing (beyond what `ws.property_values()` provides)

---

## 13. Open Questions

1. **`$` prefix stripping in DataFrame columns**: Should we strip `$` from Mixpanel built-in property names in the DataFrame (`$email` → `email`)? **Recommendation**: Strip by default for ergonomics. Users who need raw names can use `profiles` list.

2. **`segment_by` naming**: Should cohort segments use the cohort ID (`cohort_123`) or look up the cohort name? **Recommendation**: Use cohort ID as key (`cohort_<id>`) for simplicity. Users can rename via DataFrame operations.

4. **Parallel error policy**: Should a single page failure cause the entire query to fail, or return partial results? **Recommendation**: Return partial results with failed pages listed in `meta["failed_pages"]`. Document this behavior.

5. **CohortDefinition availability**: Verify that the existing `CohortDefinition` type's `to_dict()` output is accepted by the engage `filter_by_cohort.raw_cohort` parameter. If not, a translation layer is needed.

---

## Appendix A: Engage API Selector Syntax Reference

```
# Property access
properties["property_name"]
user["property_name"]           # Alternative syntax

# Comparison
properties["plan"] == "premium"
properties["age"] > 25
properties["age"] >= 18

# String
"substring" in properties["email"]
not "substring" in properties["email"]

# Existence
defined(properties["email"])
not defined(properties["phone"])

# Boolean
properties["active"] == true

# Logical
properties["a"] == "x" and properties["b"] > 10
properties["a"] == "x" or properties["a"] == "y"

# Special
NOW    # Current project timestamp (epoch)
```

## Appendix B: Comparison with `stream_profiles()`

| Feature | `stream_profiles()` | `query_user()` |
|---|---|---|
| Return type | `Iterator[dict]` | `UserQueryResult` (with `.df`) |
| Filtering | Raw selector `str` | `Filter` objects + raw `str` escape hatch |
| Behavioral filtering | `behaviors: list[dict]` (raw strings) | `cohort=CohortDefinition(...)` (fully typed, agent-safe) |
| Property selection | `output_properties` | `properties` |
| Sorting | Not supported | `sort_by` + `sort_order` |
| Search | Not supported | `search` |
| Limiting | Manual (`break` in loop) | `limit` parameter |
| Aggregation | Not supported | `mode="aggregate"` with sum/mean/min/max |
| Parallel fetch | Not supported | `parallel=True` with up to 5 workers |
| Total count | Not available | `result.total` |
| Metadata | Not available | `result.meta`, `result.computed_at` |
| Validation | `ValueError` for mutually exclusive params | `BookmarkValidationError` with all errors |
| Memory model | Streaming (one at a time) | Collected (all in memory) |
| Use case | ETL, large-scale processing | Analysis, DataFrame ops, AI agents |

Both methods use the same underlying API client infrastructure. `query_user()` is the high-level, DataFrame-native interface; `stream_profiles()` remains the low-level, memory-efficient alternative.

## Appendix C: Stats Endpoint Behavior

The engage stats sub-endpoint (`filter_type=stats`) has unique server-side behavior:

| Aspect | Behavior |
|---|---|
| `from_date` | Force-overridden to `2010-01-01` (SCD lookback) |
| `to_date` | Auto-set to current date |
| `unit` | Always `"range"` (no time-series) |
| `access_sensitive_data` | Forced to `true` |
| Pagination | None — single aggregated response |
| Response | Scalar value or dict of segment values |
| `behaviors` | Rejected — use `filter_by_cohort` |
