# Insights Queries

Build typed analytics queries against Mixpanel's Insights engine — the same engine that powers the Mixpanel web UI.

!!! tip "New in v0.2"
    `Workspace.query()` is the primary way to run analytics queries programmatically. It supports capabilities not available through the legacy query methods, including DAU/WAU/MAU, multi-metric comparison, formulas, per-user aggregation, rolling windows, and percentiles.

## When to Use `query()`

`query()` uses the Insights engine via inline bookmark params. The legacy methods (`segmentation()`, `funnel()`, `retention()`) use the older Query API endpoints. Use `query()` when you need any of the capabilities in the right column:

| Capability | Legacy methods | `query()` |
|---|---|---|
| Simple event count over time | `segmentation()` | `ws.query("Login")` |
| Unique users | `segmentation(type="unique")` | `math="unique"` |
| DAU / WAU / MAU | Not available | `math="dau"` |
| Multi-metric comparison | Not available | `["Signup", "Login", "Purchase"]` |
| Formulas (conversion rates, ratios) | Not available | `formula="(B/A)*100"` |
| Per-user aggregation | Not available | `per_user="average"` |
| Rolling / cumulative analysis | Not available | `rolling=7` |
| Percentiles (p25/p75/p90/p99) | Not available | `math="p90"` |
| Typed filters | Expression strings | `Filter.equals("country", "US")` |
| Numeric bucketed breakdowns | Not available | `GroupBy("revenue", property_type="number")` |
| Save query as a report | N/A | `result.params` → `create_bookmark()` |

Use the legacy methods when:

- You need to query a saved funnel by ID → `funnel()`
- You need cohort retention curves → `query_retention()` ([Retention Queries](query-retention.md))
- You need raw JQL execution → `jql()`
- You need Flows analysis → `query_flows()`

For ad-hoc funnel conversion analysis with typed step definitions, see **[Funnel Queries](query-funnels.md)**.

## Getting Started

The simplest possible query — total event count per day for the last 30 days:

```python
import mixpanel_data as mp

ws = mp.Workspace()

result = ws.query("Login")
print(result.df.head())
#         date                    event  count
# 0  2025-03-01  Login [Total Events]    142
# 1  2025-03-02  Login [Total Events]    158
```

Add a time range and aggregation:

```python
# Unique users per week for the last 7 days
result = ws.query("Login", math="unique", last=7, unit="week")

# Last 90 days of DAU
result = ws.query("Login", math="dau", last=90)

# Specific date range
result = ws.query(
    "Purchase",
    from_date="2025-01-01",
    to_date="2025-03-31",
    unit="month",
)
```

## Aggregation

### Counting

| Math type | What it counts |
|---|---|
| `"total"` (default) | Total event occurrences |
| `"unique"` | Unique users per period |
| `"dau"` | Daily active users |
| `"wau"` | Weekly active users |
| `"mau"` | Monthly active users |

```python
# DAU over the last 90 days
result = ws.query("Login", math="dau", last=90)

# Monthly active users
result = ws.query("Login", math="mau", last=6, unit="month")
```

### Property Aggregation

Aggregate a numeric property across events. Requires `math_property`:

| Math type | Aggregation |
|---|---|
| `"total"` + `math_property` | Sum of a numeric property |
| `"average"` | Mean value |
| `"median"` | Median value |
| `"min"` / `"max"` | Extremes |
| `"p25"` / `"p75"` / `"p90"` / `"p99"` | Percentiles |
| `"percentile"` + `percentile_value` | Custom percentile (e.g. p95) |
| `"histogram"` | Distribution of property values |

```python
# Average purchase amount per day
result = ws.query(
    "Purchase",
    math="average",
    math_property="amount",
    from_date="2025-01-01",
    to_date="2025-01-31",
)

# P90 response time
result = ws.query("API Call", math="p90", math_property="duration_ms")

# Custom percentile (p95) — use math="percentile" with percentile_value
result = ws.query(
    "API Call",
    math="percentile",
    math_property="duration_ms",
    percentile_value=95,
)

# Histogram — distribution of purchase amounts
result = ws.query("Purchase", math="histogram", math_property="amount")
```

### Per-User Aggregation

Aggregate per user first, then across all users — like a SQL subquery. For example, "what's the average number of purchases per user per week?"

```python
# Average purchases per user per week
result = ws.query(
    "Purchase",
    math="total",
    per_user="average",
    unit="week",
)
```

Valid `per_user` values: `"unique_values"`, `"total"`, `"average"`, `"min"`, `"max"`.

!!! note
    `per_user` is incompatible with `dau`, `wau`, `mau`, and `unique` math types.

### The `Metric` Class

When different events need different aggregation settings, use `Metric` objects instead of plain strings:

```python
from mixpanel_data import Metric

# Different math per event
result = ws.query([
    Metric("Signup", math="unique"),
    Metric("Purchase", math="total", property="revenue"),
])
```

`Metric` also supports `percentile_value` for custom percentiles:

```python
# Per-metric custom percentile
result = ws.query(
    Metric("API Call", math="percentile", property="duration_ms", percentile_value=95),
)
```

Plain strings inherit the top-level `math`, `math_property`, and `per_user` defaults. `Metric` objects override them per-event:

```python
# These are equivalent:
ws.query("Login", math="unique")
ws.query(Metric("Login", math="unique"))

# Top-level defaults apply to all string events:
ws.query(["Signup", "Login"], math="unique")
# Both events use math="unique"

# Metric overrides per event:
ws.query([
    Metric("Signup", math="unique"),    # unique users
    Metric("Purchase", math="total"),   # total events
])
```

## Filters

### Global Filters

Apply filters across all metrics with `where=`. Construct filters using `Filter` class methods:

```python
from mixpanel_data import Filter

# Single filter
result = ws.query(
    "Purchase",
    where=Filter.equals("country", "US"),
)

# Multiple filters (combined with AND)
result = ws.query(
    "Purchase",
    where=[
        Filter.equals("country", "US"),
        Filter.greater_than("amount", 50),
    ],
)
```

### Available Filter Methods

**String filters:**

```python
Filter.equals("browser", "Chrome")           # equals value
Filter.equals("browser", ["Chrome", "Firefox"])  # equals any in list
Filter.not_equals("browser", "Safari")        # does not equal
Filter.contains("email", "@company.com")      # contains substring
Filter.not_contains("url", "staging")         # does not contain
```

**Numeric filters:**

```python
Filter.greater_than("amount", 100)            # > 100
Filter.less_than("age", 65)                   # < 65
Filter.between("amount", 10, 100)             # 10 <= x <= 100
```

**Existence filters:**

```python
Filter.is_set("phone_number")                 # property exists
Filter.is_not_set("email")                    # property is null
```

**Boolean filters:**

```python
Filter.is_true("is_premium")                  # boolean true
Filter.is_false("is_trial")                   # boolean false
```

### Per-Metric Filters

Apply filters to individual metrics using `Metric.filters`:

```python
from mixpanel_data import Metric, Filter

# Different filters on each event
result = ws.query([
    Metric("Purchase", math="unique"),
    Metric(
        "Purchase",
        math="unique",
        filters=[Filter.equals("plan", "premium")],
    ),
])
```

By default, multiple per-metric filters combine with AND logic. Use `filters_combinator="any"` for OR logic:

```python
result = ws.query(Metric(
    "Purchase",
    math="unique",
    filters=[
        Filter.equals("country", "US"),
        Filter.equals("country", "CA"),
    ],
    filters_combinator="any",  # match US OR CA
))
```

### Date Filters

Filter by datetime properties using purpose-built factory methods:

```python
from mixpanel_data import Filter

# Absolute date filters
Filter.on("created", "2025-01-15")              # exact date match
Filter.not_on("created", "2025-01-15")           # not on date
Filter.before("created", "2025-01-01")           # before a date
Filter.since("created", "2025-01-01")            # on or after a date
Filter.date_between("created", "2025-01-01", "2025-06-30")  # date range

# Relative date filters — "in the last N units"
Filter.in_the_last("created", 30, "day")         # last 30 days
Filter.in_the_last("last_seen", 2, "week")       # last 2 weeks
Filter.not_in_the_last("created", 90, "day")     # NOT in last 90 days
```

The relative date methods accept a `FilterDateUnit`: `"hour"`, `"day"`, `"week"`, or `"month"`.

```python
from mixpanel_data import FilterDateUnit  # Literal["hour", "day", "week", "month"]

# Example: recent signups with purchases
result = ws.query(
    "Purchase",
    where=Filter.in_the_last("signup_date", 7, "day"),
    last=30,
)
```

## Breakdowns

### String Breakdowns

Break down results by property values with `group_by`:

```python
# Simple string breakdown
result = ws.query("Login", group_by="platform", last=14)

# Multiple breakdowns
result = ws.query("Purchase", group_by=["country", "platform"])
```

### The `GroupBy` Class

For numeric bucketing, boolean breakdowns, or explicit type annotations, use `GroupBy`:

```python
from mixpanel_data import GroupBy

# Numeric breakdown with buckets
result = ws.query(
    "Purchase",
    group_by=GroupBy(
        "revenue",
        property_type="number",
        bucket_size=50,
        bucket_min=0,
        bucket_max=500,
    ),
)

# Boolean breakdown
result = ws.query(
    "Login",
    group_by=GroupBy("is_premium", property_type="boolean"),
)

# Mixed: string shorthand + GroupBy
result = ws.query(
    "Purchase",
    group_by=[
        "country",
        GroupBy("amount", property_type="number", bucket_size=25),
    ],
)
```

## Formulas

Compute derived metrics from multiple events. Letters A-Z reference events by their position in the list.

### Top-Level `formula` Parameter

```python
from mixpanel_data import Metric

# Conversion rate: purchases / signups * 100
result = ws.query(
    [Metric("Signup", math="unique"), Metric("Purchase", math="unique")],
    formula="(B / A) * 100",
    formula_label="Conversion Rate",
    unit="week",
)
```

When `formula` is set, the underlying metrics are automatically hidden — only the formula result appears in the output.

### `Formula` Class in Events List

For inline formula definitions, pass `Formula` objects alongside events:

```python
from mixpanel_data import Metric, Formula

result = ws.query([
    Metric("Signup", math="unique"),
    Metric("Purchase", math="unique"),
    Formula("(B / A) * 100", label="Conversion Rate"),
])
```

Both approaches produce identical results. Use whichever reads more naturally.

### Multi-Metric Comparison (No Formula)

Compare multiple events side by side without a formula:

```python
# Three events on the same chart
result = ws.query(
    ["Signup", "Login", "Purchase"],
    math="unique",
    last=30,
)
```

## Time Ranges

### Relative (Default)

By default, `query()` returns the last 30 days. Customize with `last` and `unit`:

```python
# Last 7 days (daily granularity)
result = ws.query("Login", last=7)

# Last 4 weeks (weekly granularity)
result = ws.query("Login", last=4, unit="week")

# Last 6 months
result = ws.query("Login", last=6, unit="month")
```

The `unit` controls both what "last N" means and how data is bucketed on the time axis.

### Absolute

Specify explicit start and end dates:

```python
# Q1 2025
result = ws.query(
    "Purchase",
    from_date="2025-01-01",
    to_date="2025-03-31",
    unit="week",
)

# From a date to today
result = ws.query("Login", from_date="2025-01-01")
```

Dates must be in `YYYY-MM-DD` format.

### Hourly Granularity

Use `unit="hour"` for intraday analysis:

```python
result = ws.query("Login", last=2, unit="hour")
```

## Analysis Modes

### Rolling Windows

Smooth noisy data with a rolling average:

```python
# 7-day rolling average of signups by country
result = ws.query(
    "Signup",
    math="unique",
    group_by="country",
    rolling=7,
    last=60,
)
```

### Cumulative

Show running totals over time:

```python
result = ws.query("Signup", math="unique", cumulative=True, last=30)
```

!!! note
    `rolling` and `cumulative` are mutually exclusive.

### Result Modes

The `mode` parameter controls result aggregation semantics:

| Mode | Semantics | Use case |
|---|---|---|
| `"timeseries"` (default) | Per-period values | Trends over time |
| `"total"` | Single aggregate across the date range | KPI numbers |
| `"table"` | Tabular detail | Detailed breakdowns |

```python
# Single KPI number: total unique purchasers this month
result = ws.query(
    "Purchase",
    math="unique",
    from_date="2025-03-01",
    to_date="2025-03-31",
    mode="total",
)
total = result.df["count"].iloc[0]
```

!!! warning "Mode affects aggregation"
    `mode="total"` with `math="unique"` deduplicates users across the **entire date range**. `mode="timeseries"` with `math="unique"` counts unique users **per period** (not additive across periods). This is not just a display difference — it changes the numbers.

## Working with Results

### `QueryResult`

`query()` returns a `QueryResult` with:

```python
result = ws.query("Login", math="unique", last=7)

# DataFrame (lazy, cached)
result.df                  # pandas DataFrame

# Raw series data
result.series              # {"Login [Unique Users]": {"2025-03-01...": 142, ...}}

# Time range
result.from_date           # "2025-03-25T00:00:00-07:00"
result.to_date             # "2025-03-31T23:59:59.999000-07:00"

# Metadata
result.computed_at         # "2025-03-31T12:00:00.000000+00:00"
result.headers             # ["$metric"]
result.meta                # {"min_sampling_factor": 1.0, ...}

# Generated bookmark params (for debugging or persistence)
result.params              # dict — the full bookmark JSON sent to API
```

### DataFrame Structure

For **timeseries** mode, the DataFrame has columns `date`, `event`, `count`:

```python
result = ws.query(["Signup", "Login"], math="unique")
print(result.df.head())
#         date                      event  count
# 0  2025-03-01  Signup [Unique Users]    85
# 1  2025-03-01   Login [Unique Users]   312
# 2  2025-03-02  Signup [Unique Users]    92
```

For **total** mode, the DataFrame has columns `event`, `count` (no date).

### Persisting as a Saved Report

The generated bookmark params can be saved as a Mixpanel report:

```python
from mixpanel_data import CreateBookmarkParams

# Run query
result = ws.query("Login", math="dau", group_by="platform", last=90)

# Save as a report using the generated params
ws.create_bookmark(CreateBookmarkParams(
    name="DAU by Platform (90d)",
    bookmark_type="insights",
    params=result.params,
))
```

### Debugging

Inspect `result.params` to see the exact bookmark JSON sent to the API. This is useful for:

- Understanding what was actually queried
- Comparing with Mixpanel web UI bookmark params
- Diagnosing unexpected results

```python
import json

result = ws.query("Login", math="unique", group_by="platform")
print(json.dumps(result.params, indent=2))
```

## Validation

`query()` validates all parameter combinations **before** making an API call and raises `ValueError` with descriptive messages:

| Rule | Error message |
|---|---|
| Property math without property | `math='average' requires math_property to be set` |
| Property set with counting math | `math_property is only valid with property-based math types` |
| Per-user with DAU/WAU/MAU | `per_user is incompatible with math='dau'` |
| Formula with < 2 events | `formula requires at least 2 events` |
| Rolling + cumulative | `rolling and cumulative are mutually exclusive` |
| `to_date` without `from_date` | `to_date requires from_date` |
| Invalid date format | `from_date must be YYYY-MM-DD format` |
| Invalid bucket config | `bucket_min/bucket_max require bucket_size` |

## Complete Examples

### Revenue Dashboard Metrics

```python
import mixpanel_data as mp
from mixpanel_data import Metric, Filter, GroupBy

ws = mp.Workspace()

# Total revenue by country this quarter
revenue = ws.query(
    "Purchase",
    math="total",
    math_property="amount",
    group_by="country",
    from_date="2025-01-01",
    to_date="2025-03-31",
    unit="month",
)

# Revenue distribution by bucket
distribution = ws.query(
    "Purchase",
    group_by=GroupBy(
        "amount",
        property_type="number",
        bucket_size=25,
        bucket_min=0,
        bucket_max=500,
    ),
    last=30,
)

# Conversion rate with per-metric filters
conversion = ws.query(
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

### User Engagement Analysis

```python
# 7-day rolling average of DAU by platform
engagement = ws.query(
    "Login",
    math="dau",
    group_by="platform",
    rolling=7,
    last=90,
)

# Average sessions per user per week
sessions = ws.query(
    "Session Start",
    math="total",
    per_user="average",
    unit="week",
    last=12,
)

# WAU trend for premium users
wau = ws.query(
    "Login",
    math="wau",
    where=Filter.is_true("is_premium"),
    last=6,
    unit="month",
)
```

## Generating Params Without Querying

Use `build_params()` to generate bookmark params without making an API call — useful for debugging, inspecting the generated JSON, or saving queries as reports:

```python
# Same arguments as query(), returns dict instead of QueryResult
params = ws.build_params(
    "Login",
    math="dau",
    group_by="platform",
    where=Filter.in_the_last("created", 30, "day"),
    last=90,
)

import json
print(json.dumps(params, indent=2))  # inspect the generated bookmark JSON

# Save as a report directly from params
ws.create_bookmark(CreateBookmarkParams(
    name="DAU by Platform (90d)",
    bookmark_type="insights",
    params=params,
))
```

## What's Next

`query()` is the foundation for a family of typed query methods. Each follows the same pattern — typed Python arguments generating the correct bookmark params:

- **[`query_funnel()`](query-funnels.md)** — Ad-hoc funnel conversion analysis with typed step definitions, exclusions, and conversion windows
- **[`query_retention()`](query-retention.md)** — Ad-hoc retention curves with event pairs, custom buckets, and alignment modes
- **Cohort behaviors** — Querying by cohort membership (coming soon)

## Next Steps

- [Funnel Queries](query-funnels.md) — Typed funnel conversion analysis
- [Retention Queries](query-retention.md) — Typed retention analysis with event pairs and custom buckets
- [Live Analytics](live-analytics.md) — Legacy query methods (segmentation, funnels, retention)
- [Data Discovery](discovery.md) — Explore events and properties before querying
- [API Reference — Workspace](../api/workspace.md) — Full method signature
- [API Reference — Types](../api/types.md) — Metric, Filter, GroupBy, QueryResult details
