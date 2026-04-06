# Retention Queries

Build typed retention analysis against Mixpanel's Insights engine — define born/return event pairs, retention periods, custom buckets, and segmentation inline without creating saved reports first.

!!! tip "New in v0.4"
    `Workspace.query_retention()` is the typed way to run retention analysis programmatically. It supports capabilities not available through the legacy `retention()` method, including per-event filters, custom retention buckets, alignment modes, display modes, and typed breakdowns.

## When to Use `query_retention()`

`query_retention()` builds retention bookmark params and posts them to the Insights engine. The legacy `retention()` method queries the older Retention API endpoint. Use `query_retention()` when you need any of the capabilities in the right column:

| Capability | Legacy `retention()` | `query_retention()` |
|---|---|---|
| Basic cohort retention | `retention(born_event=..., return_event=...)` | `query_retention("Signup", "Login")` |
| Per-event filters | Expression strings only | `RetentionEvent("Signup", filters=[...])` |
| Custom retention buckets | Not available | `bucket_sizes=[1, 3, 7, 14, 30]` |
| Alignment modes | Not available | `alignment="birth"` or `"interval_start"` |
| Display modes | Not available | `mode="curve"`, `"trends"`, or `"table"` |
| Typed filters | Expression strings | `where=Filter.equals("country", "US")` |
| Property breakdowns | `on="country"` | `group_by="country"` |
| Math types | Not available | `math="retention_rate"` or `"unique"` |
| Save query as a report | N/A | `result.params` → `create_bookmark()` |

Use the legacy `retention()` when:

- You need the older Query API response format → `retention(born_event=..., return_event=...)`
- You need `born_where` / `return_where` expression-string filters → `retention(born_where='...')`

## Getting Started

The simplest possible retention query — weekly retention over the last 30 days:

```python
import mixpanel_data as mp

ws = mp.Workspace()

result = ws.query_retention("Signup", "Login")
print(result.average)  # synthetic average across all cohorts
print(result.df.head())
#   cohort_date  bucket  count      rate
# 0  2025-01-01       0   1000  1.000000
# 1  2025-01-01       1    800  0.800000
# 2  2025-01-01       2    650  0.650000
```

Add a time range and retention unit:

```python
# Daily retention over the last 14 days
result = ws.query_retention("Signup", "Login", retention_unit="day", last=14)

# Monthly retention over the last 180 days
result = ws.query_retention("Signup", "Login", retention_unit="month", last=180)

# Specific date range
result = ws.query_retention(
    "Signup",
    "Login",
    from_date="2025-01-01",
    to_date="2025-03-31",
    retention_unit="week",
)
```

## Events

### Plain Strings

The simplest way to define born and return events — pass event names as strings:

```python
result = ws.query_retention("Signup", "Login")
```

The first argument is the **born event** (defines cohort membership) and the second is the **return event** (defines what counts as returning).

### The `RetentionEvent` Class

For per-event configuration with filters, use `RetentionEvent` objects:

```python
from mixpanel_data import RetentionEvent, Filter

result = ws.query_retention(
    RetentionEvent("Signup", filters=[Filter.equals("source", "organic")]),
    RetentionEvent("Login"),
)
```

`RetentionEvent` fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `event` | `str` | (required) | Mixpanel event name |
| `filters` | `list[Filter] \| None` | `None` | Per-event filter conditions |
| `filters_combinator` | `"all" \| "any"` | `"all"` | How per-event filters combine (AND/OR) |

Plain strings and `RetentionEvent` objects can be mixed freely:

```python
result = ws.query_retention(
    "Signup",  # plain string — no filters needed
    RetentionEvent("Purchase", filters=[Filter.greater_than("amount", 0)]),
)
```

### Per-Event Filters

Apply filters to individual events using `RetentionEvent.filters`. These restrict which events count for that specific role (born or return):

```python
from mixpanel_data import RetentionEvent, Filter

result = ws.query_retention(
    RetentionEvent("Signup", filters=[Filter.equals("source", "organic")]),
    RetentionEvent("Purchase", filters=[
        Filter.equals("country", "US"),
        Filter.greater_than("amount", 25),
    ]),
)
```

By default, multiple per-event filters combine with AND logic. Use `filters_combinator="any"` for OR logic:

```python
result = ws.query_retention(
    "Signup",
    RetentionEvent(
        "Purchase",
        filters=[
            Filter.equals("country", "US"),
            Filter.equals("country", "CA"),
        ],
        filters_combinator="any",  # match US OR CA
    ),
)
```

See [Insights Queries — Filters](query.md#filters) for the full list of `Filter` factory methods.

## Retention Unit

Control the retention period granularity:

| Unit | Description |
|---|---|
| `"day"` | Daily retention buckets |
| `"week"` (default) | Weekly retention buckets |
| `"month"` | Monthly retention buckets |

```python
# Daily retention
result = ws.query_retention("Signup", "Login", retention_unit="day", last=14)

# Weekly retention (default)
result = ws.query_retention("Signup", "Login", retention_unit="week", last=90)

# Monthly retention
result = ws.query_retention("Signup", "Login", retention_unit="month", last=180)
```

## Alignment

The `alignment` parameter controls how retention periods are anchored:

| Alignment | Behavior |
|---|---|
| `"birth"` (default) | Each user's retention clock starts from their born event |
| `"interval_start"` | Retention periods align to calendar boundaries (start of day/week/month) |

```python
# Birth-aligned (default) — each user's clock starts individually
result = ws.query_retention("Signup", "Login", alignment="birth")

# Interval-aligned — retention periods snap to calendar boundaries
result = ws.query_retention("Signup", "Login", alignment="interval_start")
```

## Custom Buckets

By default, retention uses uniform bucket sizes (bucket 0, 1, 2, ...). Use `bucket_sizes` for non-uniform retention periods:

```python
# Custom day-based buckets: day 1, 3, 7, 14, 30
result = ws.query_retention(
    "Signup",
    "Login",
    retention_unit="day",
    bucket_sizes=[1, 3, 7, 14, 30],
)
```

Bucket sizes must be:

- Positive integers
- In strictly ascending order
- Maximum 730 values

## Aggregation

The `math` parameter controls what metric is computed:

| Math type | What it measures |
|---|---|
| `"retention_rate"` (default) | Percentage of cohort retained per bucket (0.0–1.0) |
| `"unique"` | Raw unique user count per bucket |

```python
# Retention rate (default)
result = ws.query_retention("Signup", "Login", math="retention_rate")

# Raw unique user counts
result = ws.query_retention("Signup", "Login", math="unique")
```

## Filters

### Global Filters

Apply filters across the entire query with `where=`:

```python
from mixpanel_data import Filter

# Single filter
result = ws.query_retention(
    "Signup",
    "Login",
    where=Filter.equals("country", "US"),
)

# Multiple filters (AND logic)
result = ws.query_retention(
    "Signup",
    "Login",
    where=[
        Filter.equals("platform", "web"),
        Filter.is_true("is_premium"),
    ],
)
```

Global filters apply to the overall query. For event-specific filtering, use `RetentionEvent.filters` (see [Events — Per-Event Filters](#per-event-filters)).

See [Insights Queries — Available Filter Methods](query.md#available-filter-methods) for the complete filter reference.

## Breakdowns

Break down retention results by property values with `group_by`:

```python
from mixpanel_data import GroupBy

# Simple string breakdown
result = ws.query_retention("Signup", "Login", group_by="platform")

# Multiple breakdowns
result = ws.query_retention("Signup", "Login", group_by=["country", "platform"])

# Numeric bucketing
result = ws.query_retention(
    "Signup",
    "Purchase",
    group_by=GroupBy("amount", property_type="number", bucket_size=50),
)
```

See [Insights Queries — Breakdowns](query.md#breakdowns) for the full `GroupBy` reference.

## Time Ranges

### Relative (Default)

By default, `query_retention()` returns the last 30 days. Customize with `last` (always in days) and `unit` (aggregation granularity):

```python
# Last 7 days
result = ws.query_retention("Signup", "Login", last=7)

# Last 90 days, weekly granularity
result = ws.query_retention("Signup", "Login", last=90, unit="week")

# Last 180 days, monthly granularity
result = ws.query_retention("Signup", "Login", last=180, unit="month")
```

### Absolute

Specify explicit start and end dates:

```python
# Q1 2025
result = ws.query_retention(
    "Signup",
    "Login",
    from_date="2025-01-01",
    to_date="2025-03-31",
)
```

Dates must be in `YYYY-MM-DD` format.

## Display Modes

The `mode` parameter controls result presentation:

| Mode | Chart type | Use case |
|---|---|---|
| `"curve"` (default) | Retention curve | Standard retention analysis |
| `"trends"` | Line chart | Track retention performance over time |
| `"table"` | Table | Detailed cohort-level comparison |

```python
# Retention curve (default)
result = ws.query_retention("Signup", "Login", mode="curve")

# Trends over time
result = ws.query_retention(
    "Signup",
    "Login",
    mode="trends",
    last=90,
    unit="week",
)

# Tabular format
result = ws.query_retention("Signup", "Login", mode="table")
```

## Working with Results

### `RetentionQueryResult`

`query_retention()` returns a `RetentionQueryResult` with:

```python
result = ws.query_retention("Signup", "Login", retention_unit="week", last=90)

# Cohort data — keyed by cohort date
for date, data in result.cohorts.items():
    print(f"{date}: {data['first']} users born")
    print(f"  Retention: {data['rates']}")  # [1.0, 0.8, 0.65, ...]

# Synthetic average across all cohorts
result.average          # {"first": 500, "counts": [...], "rates": [...]}

# DataFrame (lazy, cached)
result.df
#   cohort_date  bucket  count      rate
# 0  2025-01-01       0   1000  1.000000
# 1  2025-01-01       1    800  0.800000
# 2  2025-01-01       2    650  0.650000
# 3  2025-01-08       0    950  1.000000
# 4  2025-01-08       1    760  0.800000

# Time range
result.from_date        # "2025-01-01"
result.to_date          # "2025-03-31"

# Metadata
result.computed_at      # "2025-03-31T12:00:00.000000+00:00"
result.meta             # {"sampling_factor": 1.0, ...}

# Generated bookmark params (for debugging or persistence)
result.params           # dict — the full bookmark JSON sent to API
```

### DataFrame Structure

The DataFrame has one row per (cohort_date, bucket) pair:

| Column | Description |
|---|---|
| `cohort_date` | Date string identifying the cohort (users born on this date) |
| `bucket` | Retention bucket index (0 = born period, 1 = first return period, ...) |
| `count` | Number of users retained in this bucket |
| `rate` | Retention rate for this bucket (count / cohort size, 0.0–1.0) |

### Cohort Data Structure

Each entry in `result.cohorts` is a dict with:

| Key | Type | Description |
|---|---|---|
| `first` | `int` | Cohort size — users who did the born event on this date |
| `counts` | `list[int]` | User counts retained per bucket |
| `rates` | `list[float]` | Retention rates per bucket (0.0–1.0) |

### Persisting as a Saved Report

The generated bookmark params can be saved as a Mixpanel report:

```python
from mixpanel_data import CreateBookmarkParams

result = ws.query_retention("Signup", "Login", retention_unit="week", last=90)

ws.create_bookmark(CreateBookmarkParams(
    name="Signup → Login Retention (Weekly)",
    bookmark_type="retention",
    params=result.params,
))
```

### Debugging

Inspect `result.params` to see the exact bookmark JSON sent to the API:

```python
import json

result = ws.query_retention("Signup", "Login")
print(json.dumps(result.params, indent=2))
```

## Validation

`query_retention()` validates all parameter combinations **before** making an API call and raises `BookmarkValidationError` with descriptive messages:

| Rule | Error code | Error message |
|---|---|---|
| Empty born event name | `R1_EMPTY_BORN_EVENT` | Born event name must be a non-empty string |
| Control chars in born event | `R1_CONTROL_CHAR_BORN_EVENT` | Born event name contains control characters |
| Empty return event name | `R2_EMPTY_RETURN_EVENT` | Return event name must be a non-empty string |
| Control chars in return event | `R2_CONTROL_CHAR_RETURN_EVENT` | Return event name contains control characters |
| Non-positive bucket sizes | `R5_BUCKET_SIZES_POSITIVE` | Each bucket size must be a positive integer |
| Float bucket sizes | `R5_BUCKET_SIZES_INTEGER` | Bucket sizes must be integers, not floats |
| Buckets not ascending | `R6_BUCKET_SIZES_ASCENDING` | Bucket sizes must be in strictly ascending order |
| Invalid retention unit | `R7_INVALID_RETENTION_UNIT` | Must be one of: day, week, month |
| Invalid alignment | `R8_INVALID_ALIGNMENT` | Must be one of: birth, interval_start |
| Invalid math | `R9_INVALID_MATH` | Must be one of: retention_rate, unique |
| Invalid mode | `R10_INVALID_MODE` | Must be one of: curve, trends, table |
| Invalid unit | `R11_INVALID_UNIT` | Must be one of: day, week, month |

Errors are collected — all validation issues are reported at once, not just the first:

```python
from mixpanel_data import BookmarkValidationError

try:
    ws.query_retention("", "Login", bucket_sizes=[5, 3, 1])
except BookmarkValidationError as e:
    for error in e.errors:
        print(f"[{error.code}] {error.path}: {error.message}")
    # [R1_EMPTY_BORN_EVENT] born_event: Born event name must be a non-empty string
    # [R6_BUCKET_SIZES_ASCENDING] bucket_sizes: Bucket sizes must be in strictly ascending order
```

## Complete Examples

### User Onboarding Retention

```python
import mixpanel_data as mp
from mixpanel_data import RetentionEvent, Filter

ws = mp.Workspace()

# Weekly retention: do new signups come back?
result = ws.query_retention(
    RetentionEvent("Signup", filters=[Filter.equals("source", "organic")]),
    "Login",
    retention_unit="week",
    last=90,
    group_by="platform",
)

# Inspect average retention curve
avg = result.average
print(f"Cohort size: {avg['first']}")
for i, rate in enumerate(avg['rates']):
    print(f"  Week {i}: {rate:.1%}")

# Export to DataFrame for further analysis
print(result.df)
```

### Product Engagement

```python
# Do users who complete onboarding keep making purchases?
result = ws.query_retention(
    "Complete Onboarding",
    "Purchase",
    retention_unit="month",
    last=180,
    where=Filter.is_true("is_premium"),
)

# Custom bucket sizes for key retention milestones
milestone_retention = ws.query_retention(
    "Signup",
    "Login",
    retention_unit="day",
    bucket_sizes=[1, 3, 7, 14, 30, 60, 90],
    last=90,
)
```

### Retention Trends

```python
# Track how retention is changing over time
result = ws.query_retention(
    "Signup",
    "Login",
    mode="trends",
    unit="week",
    retention_unit="week",
    last=180,
)
print(result.df)
```

## Generating Params Without Querying

Use `build_retention_params()` to generate bookmark params without making an API call — useful for debugging, inspecting the generated JSON, or saving queries as reports:

```python
# Same arguments as query_retention(), returns dict instead of RetentionQueryResult
params = ws.build_retention_params(
    "Signup",
    "Login",
    retention_unit="week",
    bucket_sizes=[1, 3, 7, 14, 30],
    last=90,
)

import json
print(json.dumps(params, indent=2))  # inspect the generated bookmark JSON

# Save as a report directly from params
from mixpanel_data import CreateBookmarkParams

ws.create_bookmark(CreateBookmarkParams(
    name="Signup → Login Retention (Custom Buckets)",
    bookmark_type="retention",
    params=params,
))
```

## Next Steps

- [Insights Queries](query.md) — Typed analytics with DAU, formulas, filters, and breakdowns
- [Funnel Queries](query-funnels.md) — Typed funnel conversion analysis with steps, exclusions, and conversion windows
- [Live Analytics — Retention](live-analytics.md#retention) — Legacy retention method
- [API Reference — Workspace](../api/workspace.md) — Full method signatures
- [API Reference — Types](../api/types.md) — RetentionEvent, RetentionQueryResult, RetentionAlignment, RetentionMode, RetentionMathType details
