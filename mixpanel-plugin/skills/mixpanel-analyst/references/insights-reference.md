# Insights Query Reference — ws.query() Deep Dive

Complete reference for `Workspace.query()`, the primary typed query engine for Mixpanel insights. Covers every parameter, type, validation rule, and common pattern.

## Complete Signature

```python
Workspace.query(
    events: str | Metric | CohortMetric | Formula | Sequence[str | Metric | CohortMetric | Formula],
    *,
    from_date: str | None = None,          # "YYYY-MM-DD"; mutually exclusive with last
    to_date: str | None = None,            # "YYYY-MM-DD"; defaults to today
    last: int = 30,                        # relative window in units; ignored if from_date set
    unit: QueryTimeUnit = "day",           # "hour", "day", "week", "month", "quarter"
    math: MathType = "total",              # aggregate function (14 types)
    math_property: str | None = None,      # required for property-based math
    per_user: PerUserAggregation | None = None,  # per-user pre-aggregation
    percentile_value: int | float | None = None,  # required when math="percentile"
    group_by: str | GroupBy | CohortBreakdown | list[str | GroupBy | CohortBreakdown] | None = None,
    where: Filter | list[Filter] | None = None,
    formula: str | None = None,            # e.g. "(A / B) * 100"
    formula_label: str | None = None,
    rolling: int | None = None,            # rolling window size
    cumulative: bool = False,
    mode: Literal["timeseries", "total", "table"] = "timeseries",
) -> QueryResult
```

**Companion method**: `ws.build_params()` has the identical signature but returns the bookmark params dict without making an API call. Useful for debugging, inspecting generated JSON, or passing to `create_bookmark()`.

---

## MathType Deep Reference

`MathType = Literal["total", "unique", "dau", "wau", "mau", "average", "median", "min", "max", "p25", "p75", "p90", "p99", "percentile", "histogram"]`

### Counting Types (no math_property required)

| Type | What It Counts | Use Case | Gotchas |
|------|---------------|----------|---------|
| `total` | Event occurrences | Volume metrics, page views | Without `math_property`, counts events. With `math_property`, **sums** the property. There is no `"sum"` math type. |
| `unique` | Distinct users who triggered the event | User counts, reach | Incompatible with `per_user` |

### Active User Types (no math_property required)

| Type | Window | Use Case | Gotchas |
|------|--------|----------|---------|
| `dau` | 1 day | Daily engagement | All three are incompatible with `per_user`. |
| `wau` | 7 days | Weekly engagement | Uses a rolling 7-day window, not calendar week. |
| `mau` | 28 days | Monthly engagement | Uses a rolling 28-day window, not calendar month. |

### Property Aggregation Types (math_property REQUIRED)

| Type | Aggregation | Use Case | Example Property |
|------|------------|----------|-----------------|
| `average` | Arithmetic mean | AOV, avg session duration | `"revenue"`, `"duration_ms"` |
| `median` | 50th percentile | Typical value (skew-resistant) | `"load_time"` |
| `min` | Minimum value | Best-case performance | `"response_time"` |
| `max` | Maximum value | Worst-case, peak values | `"order_total"` |
| `p25` | 25th percentile | Lower quartile | `"session_length"` |
| `p75` | 75th percentile | Upper quartile | `"revenue"` |
| `p90` | 90th percentile | Performance SLO target | `"latency_ms"` |
| `p99` | 99th percentile | Tail latency | `"response_time"` |

### Special Types (math_property REQUIRED)

| Type | What It Does | Additional Requirements |
|------|-------------|----------------------|
| `percentile` | Custom percentile | Requires `percentile_value` (e.g. `95` for p95). Maps to `custom_percentile` in bookmark JSON. |
| `histogram` | Property value distribution | Requires `per_user` (e.g. `per_user="total"`). Shows how the property values are distributed across users. |

### Common Mistakes

```python
# WRONG: There is no "sum" math type
ws.query("Purchase", math="sum", math_property="revenue")  # ValueError

# CORRECT: Use "total" with math_property to sum
ws.query("Purchase", math="total", math_property="revenue")

# WRONG: percentile without percentile_value
ws.query("API Call", math="percentile", math_property="duration")  # V26 error

# CORRECT: percentile with value
ws.query("API Call", math="percentile", math_property="duration", percentile_value=95)

# WRONG: histogram without per_user
ws.query("Purchase", math="histogram", math_property="revenue")  # V27 error

# CORRECT: histogram with per_user
ws.query("Purchase", math="histogram", math_property="revenue", per_user="total")
```

---

## PerUserAggregation Deep Reference

`PerUserAggregation = Literal["unique_values", "total", "average", "min", "max"]`

### Mental Model: Two-Layer Computation

Per-user aggregation is a **subquery**. The system first computes the aggregate **for each individual user**, then applies the top-level `math` across all users.

```
Step 1 (per-user):  For each user, compute per_user(math_property)
Step 2 (aggregate): Across all per-user values, compute math()
```

### Types

| per_user | Step 1 (per user) | Example |
|----------|------------------|---------|
| `total` | Sum the property value for each user | Total revenue per user |
| `average` | Average the property value for each user | Avg order value per user |
| `min` | Minimum property value for each user | Smallest order per user |
| `max` | Maximum property value for each user | Largest order per user |
| `unique_values` | Count distinct property values per user | Number of distinct products per user |

### Requirements and Constraints

- **Requires `math_property`** — always (rule V3B)
- **Incompatible with `dau`, `wau`, `mau`, `unique`** — these already operate at the user level (rule V3)
- Compatible with `total`, `average`, `median`, `min`, `max`, `p25`, `p75`, `p90`, `p99`, `percentile`, `histogram`

### Examples

```python
# ARPU: Sum revenue per user, then average across users
ws.query("Purchase", math="total", per_user="average", math_property="revenue")
# Read as: "For each user, sum their revenue. Then average across all users."

# Revenue distribution: Sum per user, show histogram
ws.query("Purchase", math="histogram", per_user="total", math_property="revenue")

# Power user identification: Count events per user, show p90
ws.query("Core Action", math="p90", per_user="total", math_property="count")
# Read as: "For each user, count their total. What's the 90th percentile?"

# Product diversity: Distinct products per user, then average
ws.query("Purchase", math="average", per_user="unique_values", math_property="product_id")
```

---

## Filter Deep Reference

`Filter` is a frozen dataclass constructed exclusively via class methods. Each method sets the appropriate `filterType`, `filterOperator`, and `filterValue` in the bookmark JSON.

### String Filters

| Factory Method | Operator | Value Type | Example |
|---|---|---|---|
| `Filter.equals(prop, val)` | `"equals"` | `str \| list[str]` | `Filter.equals("country", "US")` |
| `Filter.not_equals(prop, val)` | `"does not equal"` | `str \| list[str]` | `Filter.not_equals("status", "inactive")` |
| `Filter.contains(prop, val)` | `"contains"` | `str` | `Filter.contains("email", "@gmail")` |
| `Filter.not_contains(prop, val)` | `"does not contain"` | `str` | `Filter.not_contains("url", "test")` |

Multi-value equals: `Filter.equals("country", ["US", "UK", "CA"])` matches any of the values.

### Numeric Filters

| Factory Method | Operator | Value Type | Example |
|---|---|---|---|
| `Filter.greater_than(prop, val)` | `"is greater than"` | `int \| float` | `Filter.greater_than("age", 18)` |
| `Filter.less_than(prop, val)` | `"is less than"` | `int \| float` | `Filter.less_than("price", 100)` |
| `Filter.between(prop, min, max)` | `"is between"` | Two `int \| float` | `Filter.between("amount", 10, 500)` |

Note: There are no `greater_than_or_equal` or `less_than_or_equal` factory methods on the `Filter` class. The bookmark API supports these operators internally but they are not exposed as convenience methods.

### Existence Filters

| Factory Method | Operator | Example |
|---|---|---|
| `Filter.is_set(prop)` | `"is set"` | `Filter.is_set("email")` |
| `Filter.is_not_set(prop)` | `"is not set"` | `Filter.is_not_set("phone")` |

### Boolean Filters

| Factory Method | Operator | Example |
|---|---|---|
| `Filter.is_true(prop)` | `"true"` | `Filter.is_true("is_premium")` |
| `Filter.is_false(prop)` | `"false"` | `Filter.is_false("is_bot")` |

### Date/Datetime Filters

| Factory Method | Operator | Value | Example |
|---|---|---|---|
| `Filter.on(prop, date)` | `"was on"` | `"YYYY-MM-DD"` | `Filter.on("created", "2025-01-15")` |
| `Filter.not_on(prop, date)` | `"was not on"` | `"YYYY-MM-DD"` | `Filter.not_on("$time", "2025-03-01")` |
| `Filter.before(prop, date)` | `"was before"` | `"YYYY-MM-DD"` | `Filter.before("created", "2024-01-01")` |
| `Filter.since(prop, date)` | `"was since"` | `"YYYY-MM-DD"` | `Filter.since("signup_date", "2025-01-01")` |
| `Filter.in_the_last(prop, qty, unit)` | `"was in the"` | `int` + `FilterDateUnit` | `Filter.in_the_last("signup_date", 30, "day")` |
| `Filter.not_in_the_last(prop, qty, unit)` | `"was not in the"` | `int` + `FilterDateUnit` | `Filter.not_in_the_last("last_login", 90, "day")` |
| `Filter.date_between(prop, from, to)` | `"was between"` | Two `"YYYY-MM-DD"` | `Filter.date_between("created", "2025-01-01", "2025-03-31")` |

`FilterDateUnit = Literal["hour", "day", "week", "month"]`

### Resource Type

All filter methods accept `resource_type` keyword argument: `"events"` (default) or `"people"` (user profile properties).

```python
# Filter on user profile property
Filter.equals("plan", "premium", resource_type="people")
```

### Combining Filters

Pass a list to `where=` for AND logic (all must match):

```python
ws.query("Purchase",
    where=[
        Filter.greater_than("amount", 50),
        Filter.equals("country", "US"),
        Filter.in_the_last("signup_date", 30, "day"),
    ])
```

Per-metric filters on `Metric` objects support `filters_combinator`:

```python
Metric("Purchase",
    filters=[
        Filter.equals("country", "US"),
        Filter.equals("country", "UK"),
    ],
    filters_combinator="any",  # OR logic — US or UK
)
```

---

## GroupBy Deep Reference

### String Breakdown (default)

```python
# Simple string breakdown
ws.query("Purchase", group_by="country")

# Equivalent using GroupBy object
ws.query("Purchase", group_by=GroupBy("country"))  # property_type defaults to "string"
```

### Numeric Bucketed Breakdown

Requires `property_type="number"` and all three bucket parameters: `bucket_size`, `bucket_min`, `bucket_max`.

```python
from mixpanel_data import GroupBy

ws.query("Purchase",
    math="total",
    group_by=GroupBy(
        "revenue",
        property_type="number",
        bucket_size=50,
        bucket_min=0,
        bucket_max=500,
    ))
# Result: segments like "0-50", "50-100", "100-150", ...
```

**Validation rules**:
- `bucket_size` must be positive (V12)
- `bucket_size` requires `property_type="number"` (V12B)
- `bucket_size` requires both `bucket_min` and `bucket_max` (V12C)
- `bucket_min` must be less than `bucket_max` (V18)
- `bucket_min`/`bucket_max` require `bucket_size` (V11)
- All bucket values must be finite (V24)

### Boolean Breakdown

```python
ws.query("Purchase", group_by=GroupBy("is_premium", property_type="boolean"))
# Result: segments "true" and "false"
```

### Multiple Breakdowns

```python
ws.query("Purchase", group_by=["country", "platform"])
# Result: segments like "US - iOS", "US - Android", "UK - iOS", ...
```

---

## Formula Patterns

### Top-Level Formula (convenience)

When using a single formula across 2+ events:

```python
# Conversion rate
ws.query(
    ["Signup", "Purchase"],
    formula="(B / A) * 100",
    formula_label="Conversion %",
)

# Ratio
ws.query(
    ["Error", "Request"],
    formula="(A / B) * 100",
    formula_label="Error Rate %",
)
```

### Inline Formula (in events list)

When mixing metrics and formulas:

```python
from mixpanel_data import Metric, Formula

result = ws.query([
    Metric("Signup", math="unique"),
    Metric("Purchase", math="unique"),
    Formula("(B / A) * 100", label="Conv Rate %"),
])
# result.df includes rows for all three: Signup count, Purchase count, and the formula
```

### Multi-Metric Comparison (no formula)

```python
from mixpanel_data import Metric

result = ws.query([
    Metric("Login", math="unique", label="Logins"),
    Metric("Purchase", math="unique", label="Purchases"),
    Metric("Signup", math="unique", label="Signups"),
])
# Each metric appears as its own series in result.df
```

### Formula Validation

- Formula requires 2+ events (V4)
- Formula must reference at least one position letter A-Z (V16)
- Position letters must not exceed event count — e.g., with 2 events, only A and B are valid (V19)
- Letters map to event positions: A = first event, B = second, C = third, etc.

---

## Metric Object Patterns

`Metric` allows per-event overrides of math, property, per_user, and filters.

```python
from mixpanel_data import Metric, Filter

# Per-event math override
result = ws.query([
    Metric("Login", math="unique"),          # Count unique users
    Metric("Purchase", math="total",
           property="revenue"),               # Sum revenue
    Metric("Session", math="average",
           property="duration"),              # Average duration
])

# Per-event filters (in addition to global where=)
result = ws.query([
    Metric("Purchase",
           math="total",
           property="revenue",
           filters=[Filter.equals("platform", "iOS")],
           label="iOS Revenue"),
    Metric("Purchase",
           math="total",
           property="revenue",
           filters=[Filter.equals("platform", "Android")],
           label="Android Revenue"),
])

# Per-event per_user
result = ws.query(
    Metric("Purchase",
           math="average",
           property="revenue",
           per_user="total"),
)
# "For each user sum revenue, then average across users"

# Custom percentile on Metric
result = ws.query(
    Metric("API Call",
           math="percentile",
           property="latency_ms",
           percentile_value=95),
)
```

---

## Time Range Patterns

### Relative (last=)

```python
ws.query("Login", last=7)          # Last 7 days
ws.query("Login", last=90)         # Last 90 days
ws.query("Login", last=12, unit="month")  # Last 12 months
ws.query("Login", last=4, unit="quarter") # Last 4 quarters
ws.query("Login", last=24, unit="hour")   # Last 24 hours (hourly data)
```

### Absolute (from_date/to_date)

```python
ws.query("Login", from_date="2025-01-01", to_date="2025-03-31")
ws.query("Login", from_date="2025-01-01")  # to_date defaults to today
```

### Validation Rules

- `from_date` and `to_date` must be `YYYY-MM-DD` format (V8)
- `to_date` requires `from_date` (V9)
- Cannot combine `from_date` with non-default `last` (V10)
- `from_date` must be before or equal to `to_date` (V15)
- `last` must be positive (V7) and max 3650 (V20)

### Unit Options

`QueryTimeUnit = Literal["hour", "day", "week", "month", "quarter"]`

- `"hour"` — Hourly granularity. Best with short ranges (last 24-72 hours).
- `"day"` — Daily granularity. The default. Best for most analyses.
- `"week"` — Weekly granularity. Good for reducing noise.
- `"month"` — Monthly granularity. Good for long-term trends.
- `"quarter"` — Quarterly granularity. Good for business reporting.

---

## Analysis Modes: Rolling and Cumulative

### Rolling Average

Smooths data by computing the average over a sliding window.

```python
ws.query("Login", math="dau", rolling=7)    # 7-day rolling average
ws.query("Signup", rolling=14)               # 14-day rolling window
```

- `rolling` must be a positive integer (V6)
- Maximum rolling window: 365 (V23)

### Cumulative

Shows the running total over time.

```python
ws.query("Signup", math="unique", cumulative=True)  # Cumulative signups
```

### Mutual Exclusivity

Rolling and cumulative cannot be used together (V5).

```python
# WRONG — V5 error
ws.query("Signup", rolling=7, cumulative=True)
```

---

## Display Modes

`mode: Literal["timeseries", "total", "table"]`

### Timeseries (default)

Returns one data point per time unit. DataFrame columns: `date`, `event`, `count`.

```python
result = ws.query("Login", last=30, mode="timeseries")
# result.df columns: date, event, count
# One row per day (or per unit)
```

### Total

Returns a single aggregate value per metric/segment. DataFrame columns: `event`, `count`.

```python
result = ws.query("Login", last=30, mode="total")
# result.df columns: event, count
# One row total (or one row per segment if group_by used)
```

### Table

Returns data in tabular format. Column structure depends on API response — typically matches timeseries or total depending on date presence.

```python
result = ws.query("Login", last=30, group_by="country", mode="table")
```

---

## Cohort Capabilities

Three cohort-specific features enhance insights queries. Each accepts saved cohort IDs (`int`) or inline `CohortDefinition` objects.

### Cohort Filters (where=)

Restrict any query to users in (or not in) a cohort:

```python
from mixpanel_data import Filter, CohortDefinition, CohortCriteria

# Saved cohort
result = ws.query("Login", math="dau", where=Filter.in_cohort(123, "Power Users"), last=30)

# Inline definition
premium = CohortDefinition.all_of(
    CohortCriteria.has_property("plan", "premium"),
    CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
)
result = ws.query("Login", where=Filter.in_cohort(premium, "Premium Users"), last=30)

# Exclude a cohort
result = ws.query("Login", where=Filter.not_in_cohort(123, "Churned"), last=30)
```

### Cohort Breakdowns (group_by=)

Segment results by cohort membership — "in cohort" vs "not in cohort":

```python
from mixpanel_data import CohortBreakdown

# Basic cohort breakdown
result = ws.query("Login", math="dau", group_by=CohortBreakdown(123, "Power Users"), last=30)
# Result segments: "Power Users" and "Not In Power Users"

# Mix with property breakdowns
result = ws.query("Login", group_by=[CohortBreakdown(123, "Power Users"), "platform"])

# Without negated segment
result = ws.query("Login", group_by=CohortBreakdown(123, "Power Users", include_negated=False))
```

### Cohort Metrics (events=)

Track cohort size over time as a metric series:

```python
from mixpanel_data import CohortMetric, Metric, Formula

# Standalone — cohort size trend
result = ws.query(CohortMetric(123, "Power Users"), last=90)

# Mixed with event metrics + formula
result = ws.query(
    [Metric("Login", math="unique"), CohortMetric(123, "Power Users")],
    formula="(B / A) * 100", formula_label="Power User %",
    last=90,
)
```

**Known limitation**: `CohortMetric` with inline `CohortDefinition` triggers a server-side 500 error. Use saved cohort IDs.

### Cohort Validation Rules

| Rule | Check | Error |
|------|-------|-------|
| CF1 | Cohort ID must be positive integer (when `int`) | `CF1_COHORT_ID_POSITIVE` |
| CF2 | Cohort name must be non-empty when provided | `CF2_COHORT_NAME_EMPTY` |
| CB1 | CohortBreakdown cohort ID must be positive | `CB1_BREAKDOWN_ID_POSITIVE` |
| CB2 | CohortBreakdown name must be non-empty when provided | `CB2_BREAKDOWN_NAME_EMPTY` |
| CB3 | CohortBreakdown and property GroupBy mutually exclusive in retention | `CB3_RETENTION_MUTUAL_EXCLUSION` |
| CM1 | CohortMetric cohort ID must be positive | `CM1_METRIC_ID_POSITIVE` |
| CM2 | CohortMetric name must be non-empty when provided | `CM2_METRIC_NAME_EMPTY` |
| CM3 | CohortMetric math is always "unique" | `CM3_METRIC_MATH_UNIQUE` |
| CM4 | CohortMetric is insights-only | `CM4_METRIC_INSIGHTS_ONLY` |

---

## QueryResult Structure

```python
result = ws.query("Login", math="dau", last=30)

result.df           # pandas DataFrame (lazy, cached on first access)
result.params       # dict — generated bookmark params JSON
result.series       # dict — raw series data from API
result.from_date    # str — resolved start date ("2025-03-01")
result.to_date      # str — resolved end date ("2025-03-31")
result.computed_at  # str — API computation timestamp (ISO format)
result.meta         # dict — response metadata (sampling_factor, etc.)
result.headers      # list[str] — column headers from insights response
```

### DataFrame Columns by Mode

| Mode | Columns | Rows |
|------|---------|------|
| timeseries | `date`, `event`, `count` | One per (date, metric/segment) |
| total | `event`, `count` | One per metric/segment |
| table | Varies | Depends on API response |

### Persisting as a Saved Report

```python
from mixpanel_data import CreateBookmarkParams

result = ws.query("Login", math="dau", last=30, group_by="platform")

bm = ws.create_bookmark(CreateBookmarkParams(
    name="DAU by Platform (30d)",
    bookmark_type="insights",
    params=result.params,  # Pass the generated params directly
))
print(f"Report created: {bm.id}")
```

---

## Ready-to-Use Code Patterns

### 1. DAU Trend with Rolling Average

```python
import mixpanel_data as mp

ws = mp.Workspace()
result = ws.query("Login", math="dau", last=90)
df = result.df.set_index("date")
df.index = pd.to_datetime(df.index)
df["7d_avg"] = df["count"].rolling(7).mean()
print(df.tail(14))
```

### 2. Property Aggregation (Revenue)

```python
# Total revenue (sum)
revenue = ws.query("Purchase", math="total", math_property="revenue", last=30)

# Average order value
aov = ws.query("Purchase", math="average", math_property="revenue", last=30)

# ARPU (per-user sum, then average)
arpu = ws.query("Purchase", math="total", per_user="average",
                math_property="revenue", last=30)

print(f"Total: ${revenue.df['count'].sum():,.2f}")
print(f"AOV: ${aov.df['count'].mean():,.2f}")
print(f"ARPU: ${arpu.df['count'].mean():,.2f}")
```

### 3. Segment Comparison

```python
result = ws.query("Purchase", math="total", math_property="revenue",
                  group_by="platform", mode="total", last=30)
df = result.df.sort_values("count", ascending=False)
total = df["count"].sum()
df["pct"] = (df["count"] / total * 100).round(1)
print(df)
```

### 4. Formula: Conversion Rate

```python
from mixpanel_data import Metric, Formula

result = ws.query([
    Metric("Visit", math="unique"),
    Metric("Signup", math="unique"),
    Formula("(B / A) * 100", label="Signup Rate %"),
], last=30)
print(result.df)
```

### 5. Rolling Average

```python
result = ws.query("Login", math="dau", rolling=7, last=90)
# API computes the rolling average server-side
print(result.df.tail(14))
```

### 6. Filtered Breakdown

```python
from mixpanel_data import Filter

result = ws.query("Purchase",
    math="total", math_property="revenue",
    where=[
        Filter.greater_than("amount", 10),
        Filter.in_the_last("signup_date", 90, "day"),
    ],
    group_by="country",
    last=30)
print(result.df)
```

### 7. Multi-Event Comparison

```python
from mixpanel_data import Metric

result = ws.query([
    Metric("Signup", math="unique", label="Signups"),
    Metric("Activate", math="unique", label="Activations"),
    Metric("Purchase", math="unique", label="Purchases"),
], last=30)
print(result.df)
```

### 8. Period-over-Period

```python
current = ws.query("Signup", math="unique",
                    from_date="2025-03-01", to_date="2025-03-31")
previous = ws.query("Signup", math="unique",
                    from_date="2025-02-01", to_date="2025-02-28")

c_total = current.df["count"].sum()
p_total = previous.df["count"].sum()
change = (c_total - p_total) / p_total * 100
print(f"MoM change: {change:+.1f}%")
```

---

## Validation Rules Summary

### Layer 1: Argument Validation (V-rules)

| Rule | Check | Error |
|------|-------|-------|
| V0 | At least one event required | `V0_NO_EVENTS` |
| V1 | Property math requires `math_property` | `V1_MATH_REQUIRES_PROPERTY` |
| V2 | Non-property math rejects `math_property` | `V2_MATH_REJECTS_PROPERTY` |
| V3 | `per_user` incompatible with dau/wau/mau/unique | `V3_PER_USER_INCOMPATIBLE` |
| V3B | `per_user` requires `math_property` | `V3B_PER_USER_REQUIRES_PROPERTY` |
| V4 | Formula requires 2+ events | `V4_FORMULA_MIN_EVENTS` |
| V5 | Rolling and cumulative are mutually exclusive | `V5_ROLLING_CUMULATIVE_EXCLUSIVE` |
| V6 | Rolling must be positive | `V6_ROLLING_POSITIVE` |
| V7 | `last` must be positive | `V7_LAST_POSITIVE` |
| V8 | Date format must be YYYY-MM-DD | `V8_DATE_FORMAT` |
| V9 | `to_date` requires `from_date` | `V9_TO_REQUIRES_FROM` |
| V10 | Cannot combine explicit dates with non-default `last` | `V10_DATE_LAST_EXCLUSIVE` |
| V11 | `bucket_min`/`bucket_max` require `bucket_size` | `V11_BUCKET_REQUIRES_SIZE` |
| V12 | `bucket_size` must be positive | `V12_BUCKET_SIZE_POSITIVE` |
| V12B | `bucket_size` requires `property_type="number"` | `V12B_BUCKET_REQUIRES_NUMBER` |
| V12C | `bucket_size` requires both `bucket_min` and `bucket_max` | `V12C_BUCKET_REQUIRES_BOUNDS` |
| V13 | Per-Metric: math requiring property needs property | `V13_METRIC_MATH_PROPERTY` |
| V14 | Per-Metric: non-property math rejects property | `V14_METRIC_REJECTS_PROPERTY` |
| V15 | `from_date` must be <= `to_date` | `V15_DATE_ORDER` |
| V16 | Formula must contain position letters (A-Z) | `V16_FORMULA_SYNTAX` |
| V17 | Event name must be non-empty | `V17_EMPTY_EVENT` |
| V18 | `bucket_min` must be < `bucket_max` | `V18_BUCKET_ORDER` |
| V19 | Formula position letters must not exceed event count | `V19_FORMULA_BOUNDS` |
| V20 | `last` max 3650 (10 years) | `V20_LAST_TOO_LARGE` |
| V21 | Event must be string or Metric | `V21_INVALID_EVENT_TYPE` |
| V22 | No control/invisible characters in event names | `V22_CONTROL_CHAR_EVENT` |
| V23 | Rolling window max 365 | `V23_ROLLING_TOO_LARGE` |
| V24 | Bucket values must be finite (not NaN/Inf) | `V24_BUCKET_NOT_FINITE` |
| V26 | `math="percentile"` requires `percentile_value` | `V26_PERCENTILE_REQUIRES_VALUE` |
| V27 | `math="histogram"` requires `per_user` | `V27_HISTOGRAM_REQUIRES_PER_USER` |

### Layer 2: Bookmark Structure Validation (B-rules)

| Rule | Check |
|------|-------|
| B1 | `sections` key present |
| B2 | `displayOptions` key present |
| B3-B4 | `sections.show` non-empty list |
| B5 | Valid `chartType` |
| B6-B8 | Show clause has valid behavior with event name |
| B9-B11 | Valid math, property, perUserAggregation |
| B12-B13 | Valid time unit and dateRangeType |
| B14-B16 | Valid filter type, operator, resourceType |
| B17 | Valid property type in group clause |
| B18 | Filter has property identifier |
| B19 | Valid filtersDeterminer (any/all) |
| B20-B21 | filterValue non-empty and within size limits |

---

## Common Pitfalls Quick Reference

1. **No "sum" math type** — Use `math="total"` with `math_property="property_name"` to sum a numeric property
2. **per_user requires math_property** — Always set `math_property` when using `per_user`
3. **per_user incompatible with dau/wau/mau/unique** — These already aggregate at the user level
4. **formula requires 2+ events** — A formula like `"A * 100"` needs at least events A and B
5. **rolling and cumulative are mutually exclusive** — Pick one or neither
6. **percentile requires percentile_value** — `math="percentile"` without `percentile_value` fails validation
7. **histogram requires per_user** — `math="histogram"` without `per_user` fails validation
8. **Cannot mix explicit dates with non-default last** — Use `from_date`/`to_date` OR `last`, not both
9. **to_date requires from_date** — You cannot set `to_date` alone
10. **project_id must be a string** — `Workspace(project_id=8)` raises `ValidationError`; use `project_id="8"`
