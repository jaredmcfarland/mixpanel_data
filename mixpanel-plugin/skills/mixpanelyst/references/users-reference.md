---
name: users-reference
description: Deep reference for query_user() — user profile queries, filtering, sorting, aggregate counts, cross-engine composition, and feature extraction
---

# User Query Reference — ws.query_user() Deep Dive

Complete reference for `Workspace.query_user()`, the typed user profile query engine for Mixpanel's Engage API.

_User queries use Filter for property filtering — see [insights-reference.md](insights-reference.md) for the authoritative Filter reference._

## When to Use query_user()

- **"Who" questions** — which users match a set of profile attributes?
- **Profile attribute lookup** — retrieve email, plan, city, LTV, or any user property
- **User counts** — how many users match a filter? (aggregate mode)
- **Targeting lists** — extract distinct IDs for cohort creation or messaging
- **Profile analysis** — pull profile properties into a DataFrame for segmentation or comparison
- **Cross-engine profiling** — enrich insights/funnel/retention results with user-level attributes

## Complete Signature

```python
Workspace.query_user(
    *,
    where: Filter | list[Filter] | str | None = None,   # property filters (AND-combined)
    cohort: int | CohortDefinition | None = None,        # saved cohort ID or inline definition
    properties: list[str] | None = None,                 # output properties to include
    sort_by: str | None = None,                          # property to sort by
    sort_order: Literal["ascending", "descending"] = "descending",
    limit: int | None = 1,                               # max profiles; default=1; None=fetch all
    search: str | None = None,                           # full-text search across properties
    distinct_id: str | None = None,                      # single user lookup
    distinct_ids: list[str] | None = None,               # batch user lookup
    group_id: str | None = None,                         # query group profiles instead of users
    as_of: str | int | None = None,                      # point-in-time (ISO date or Unix ts)
    mode: Literal["profiles", "aggregate"] = "aggregate",
    aggregate: Literal["count", "extremes", "percentile", "numeric_summary"] = "count",
    aggregate_property: str | None = None,               # required for non-count aggregations
    percentile: float | None = None,                     # required when aggregate="percentile" (0-100)
    segment_by: list[int] | None = None,                 # cohort IDs for segmented aggregation
    parallel: bool = False,                              # concurrent page fetching
    workers: int = 5,                                    # max parallel workers
    include_all_users: bool = False,                     # include non-members in cohort results
) -> UserQueryResult
```

**Companion method**: `ws.build_user_params()` has the identical signature and returns the engage API params dict without making an API call. Useful for debugging and inspecting generated params.

## UserQueryResult

| Field | Type | Description |
|-------|------|-------------|
| `computed_at` | `str` | ISO timestamp of query execution |
| `total` | `int` | Number of profiles returned (`len(profiles)`) |
| `profiles` | `list[dict]` | Normalized profile dicts; empty for aggregate mode |
| `params` | `dict` | Engage API params used (for debugging) |
| `meta` | `dict` | Execution metadata (timing, pages fetched) |
| `mode` | `Literal["profiles", "aggregate"]` | Output mode |
| `aggregate_data` | `dict \| int \| float \| None` | Raw aggregate; `None` for profiles mode |

| Property | Type | Description |
|----------|------|-------------|
| `.df` | `DataFrame` | Lazy; columns: `distinct_id`, `last_seen`, then alphabetical (`$` prefix stripped) |
| `.distinct_ids` | `list[str]` | Distinct IDs from profiles; empty for aggregate mode |
| `.value` | `int \| float \| None` | Scalar aggregate for unsegmented; `None` otherwise |
| `.to_dict()` | `dict` | JSON-serializable output of all fields |

## Mode: profiles

```python
# Basic filter + limit
result = ws.query_user(mode="profiles", where=Filter.equals("plan", "premium"), limit=50)
print(f"Total premium users: {result.total}")
print(result.df.head())

# Properties selection + sort
result = ws.query_user(
    mode="profiles",
    where=Filter.greater_than("ltv", 100),
    properties=["$email", "$city", "ltv"],
    sort_by="ltv",
    sort_order="descending",
    limit=100,
)
df = result.df  # columns: distinct_id, last_seen, city, email, ltv

# Single user lookup
result = ws.query_user(mode="profiles", distinct_id="user_abc123")

# Batch lookup
result = ws.query_user(
    mode="profiles",
    distinct_ids=["user_001", "user_002", "user_003"],
    limit=3,
)

# CohortDefinition behavioral filter
from mixpanel_data import CohortDefinition, CohortCriteria
result = ws.query_user(
    mode="profiles",
    cohort=CohortDefinition.all_of(
        CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
    ),
    properties=["$email", "plan"],
    limit=500,
)
```

## Mode: aggregate (default)

Aggregate mode is the default (`mode="aggregate"`), so you can omit it:

```python
# Simple count
result = ws.query_user(
    where=Filter.equals("plan", "premium"),
)
print(result.value)  # 1532

# Extremes (min/max) of a property
result = ws.query_user(
    aggregate="extremes",
    aggregate_property="age",
)
print(result.aggregate_data)  # {"max": 75, "min": 18, "nth_percentile": 46}

# Percentile
result = ws.query_user(
    aggregate="percentile",
    aggregate_property="ltv",
    percentile=90,
)
print(result.aggregate_data)  # {"percentile": 90, "result": 4500}

# Numeric summary (count, mean, variance, sum_of_squares)
result = ws.query_user(
    aggregate="numeric_summary",
    aggregate_property="ltv",
)
print(result.aggregate_data)  # {"count": 1532, "mean": 245.6, "var": 1234.5, ...}

# Segmented count by cohort IDs
result = ws.query_user(
    segment_by=[12345, 67890],
)
print(result.df)  # columns: segment, value
```

## Parallel Fetching

Enable concurrent page fetching for large result sets:

```python
result = ws.query_user(
    mode="profiles",
    where=Filter.equals("country_code", "US"),
    properties=["$email", "plan", "ltv"],
    parallel=True,
    workers=5,
    limit=5000,
)
print(f"Fetched {result.total} profiles")
```

Only takes effect when `parallel=True` and `limit > 1`. The `workers` param controls concurrency (default 5).

## Cross-Engine Composition

```python
# Pattern 1: Insights segment -> query_user for profiles
insights = ws.query("Purchase", math="unique", group_by="plan", last=30, mode="total")
result = ws.query_user(
    mode="profiles",
    where=Filter.equals("plan", "enterprise"),
    properties=["$email", "$city", "ltv", "company"],
    sort_by="ltv",
    limit=200,
)

# Pattern 2: query_user distinct_ids -> downstream use
result = ws.query_user(
    mode="profiles",
    where=[Filter.equals("plan", "premium"), Filter.greater_than("ltv", 500)],
    limit=1000,
)
target_ids = result.distinct_ids  # for cohort creation or messaging

# Pattern 3: Behavioral cohort -> profile extraction
from mixpanel_data import CohortDefinition, CohortCriteria
result = ws.query_user(
    mode="profiles",
    cohort=CohortDefinition.all_of(
        CohortCriteria.did_event("Login", at_least=0, within_days=30),
    ),
    properties=["$email", "plan", "ltv", "$last_seen"],
    limit=500,
)
churn_risk_df = result.df
```

## Profile Segmentation

```python
import pandas as pd

result = ws.query_user(
    mode="profiles",
    properties=["ltv", "session_count", "days_since_signup"],
    parallel=True, workers=5, limit=5000,
)
df = result.df[["ltv", "session_count", "days_since_signup"]].dropna()
df["ltv_tier"] = pd.qcut(df["ltv"], q=4, labels=["Low", "Mid-Low", "Mid-High", "High"])
print(df.groupby("ltv_tier").mean())
```

## Limitations

- **limit**: `int | None`, default `1`. Set higher values for bulk queries. `None` fetches all matching profiles.
- **Aggregate functions**: `count`, `extremes` (min/max), `percentile`, `numeric_summary` (count/mean/var). Maps 1:1 to the Mixpanel engage/stats API.
- **No time dimension**: Returns current profile state. Use `as_of` for point-in-time snapshots, but no time-series output. Combine with insights or retention for time-based analysis.
- **Property filtering**: Complex OR logic across different properties requires raw selector strings rather than `Filter` objects.
