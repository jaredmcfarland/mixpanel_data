# Retention Query Reference — ws.query_retention() Deep Dive

Complete reference for `Workspace.query_retention()`, the typed retention query engine. Covers every parameter, type, validation rule, and analysis pattern.

_Retention inherits Filter, GroupBy, and time range handling from Insights — see [insights-reference.md](insights-reference.md) for the authoritative reference. Note: retention_unit is separate from the query time unit._

## Complete Signature

```python
Workspace.query_retention(
    born_event: str | RetentionEvent,
    return_event: str | RetentionEvent,
    *,
    retention_unit: TimeUnit = "week",          # "day", "week", "month"
    alignment: RetentionAlignment = "birth",    # "birth", "interval_start"
    bucket_sizes: list[int] | None = None,      # custom retention buckets
    from_date: str | None = None,
    to_date: str | None = None,
    last: int = 30,
    unit: QueryTimeUnit = "day",
    math: RetentionMathType = "retention_rate",  # "retention_rate", "unique"
    group_by: str | GroupBy | CohortBreakdown | list[str | GroupBy | CohortBreakdown] | None = None,
    where: Filter | list[Filter] | None = None,
    mode: RetentionMode = "curve",              # "curve", "trends", "table"
    unbounded_mode: RetentionUnboundedMode | None = None,  # unbounded retention counting
    retention_cumulative: bool = False,                     # cumulative retention mode
    time_comparison: TimeComparison | None = None,          # period-over-period comparison
    data_group_id: int | None = None,                       # data group scope
) -> RetentionQueryResult
```

**Companion method**: `ws.build_retention_params()` has the identical signature but returns the bookmark params dict without making an API call. Useful for debugging, inspecting generated JSON, or passing to `create_bookmark()`.

---

## Born Event and Return Event

Retention queries require two events:
- **born_event**: The event that defines cohort membership. Users who perform this event enter the cohort on the date they first do it.
- **return_event**: The event that defines "returning." A user is retained in bucket N if they perform this event during that bucket's time window.

### Simple String Events

```python
result = ws.query_retention("Signup", "Login")
# Cohort: Users who signed up
# Retained: Users who logged in during each subsequent period
```

### RetentionEvent Objects

Use `RetentionEvent` when you need per-event filters:

```python
from mixpanel_data import RetentionEvent, Filter

born = RetentionEvent(
    "Signup",
    filters=[Filter.equals("source", "organic")],
)
ret = RetentionEvent(
    "Login",
    filters=[Filter.equals("platform", "mobile")],
)
result = ws.query_retention(born, ret)
```

### RetentionEvent Attributes

```python
@dataclass(frozen=True)
class RetentionEvent:
    event: str                                          # Mixpanel event name (required)
    filters: list[Filter] | None = None                 # Per-event filter conditions
    filters_combinator: Literal["all", "any"] = "all"   # AND/OR for filters
```

### Common Event Patterns

| Pattern | born_event | return_event | What It Measures |
|---------|-----------|--------------|-----------------|
| **Overall retention** | `"Signup"` | `"Login"` | Do new users come back? |
| **Stickiness** | `"Login"` | `"Login"` | Do active users keep returning? |
| **Feature retention** | `"Use Feature"` | `"Use Feature"` | Do feature users keep using it? |
| **Activation retention** | `"Signup"` | `"Core Action"` | Do signups reach activation? |
| **Purchase retention** | `"First Purchase"` | `"Purchase"` | Do buyers purchase again? |
| **Engagement depth** | `"Signup"` | `"Share Content"` | Do signups reach high engagement? |

### Filtered Retention

```python
# Organic vs paid retention comparison
organic = ws.query_retention(
    RetentionEvent("Signup", filters=[Filter.equals("source", "organic")]),
    "Login",
)
paid = ws.query_retention(
    RetentionEvent("Signup", filters=[Filter.equals("source", "paid")]),
    "Login",
)
```

---

## Retention Unit

`TimeUnit = Literal["day", "week", "month"]`

The retention unit defines the size of each retention bucket:

| Unit | Bucket Meaning | Best For |
|------|---------------|----------|
| `"day"` | D0, D1, D2, D3, ... | Short-term retention, daily products |
| `"week"` | W0, W1, W2, W3, ... (default) | Standard retention analysis |
| `"month"` | M0, M1, M2, M3, ... | Long-term retention, subscription products |

```python
# Daily retention (D1, D7, D30)
ws.query_retention("Signup", "Login", retention_unit="day")

# Weekly retention (default)
ws.query_retention("Signup", "Login", retention_unit="week")

# Monthly retention
ws.query_retention("Signup", "Login", retention_unit="month")
```

---

## Alignment Modes

`RetentionAlignment = Literal["birth", "interval_start"]`

### Birth Alignment (default)

Each user's retention clock starts from the date they performed the born event. Bucket 1 for User A might be a different calendar period than Bucket 1 for User B.

```python
ws.query_retention("Signup", "Login", alignment="birth")
```

**When to use**: Standard retention analysis. Each user's experience is measured from their own start point. This is what most people mean by "retention."

### Interval Start Alignment

All users in a cohort are aligned to the same calendar boundary. Bucket 1 is the same calendar period for everyone in that cohort.

```python
ws.query_retention("Signup", "Login", alignment="interval_start")
```

**When to use**: When you want to compare cohorts against the same calendar periods. Useful for seasonal analysis or when external events (launches, campaigns) affect retention.

### Comparison

```
Birth alignment (retention_unit="week"):
  User A signs up Mon → W1 = next Mon-Sun for User A
  User B signs up Thu → W1 = next Thu-Wed for User B

Interval start alignment (retention_unit="week"):
  User A signs up Mon → W1 = next calendar week for everyone
  User B signs up Thu → W1 = same next calendar week
```

---

## Custom Bucket Sizes

By default, retention uses uniform buckets (1, 2, 3, 4, ...). Custom bucket sizes let you define non-uniform intervals.

```python
# Standard milestones
ws.query_retention("Signup", "Login",
    retention_unit="day",
    bucket_sizes=[1, 3, 7, 14, 30, 60, 90],
)
# Buckets: D1, D3, D7, D14, D30, D60, D90

# Mobile app standard
ws.query_retention("Install", "Open",
    retention_unit="day",
    bucket_sizes=[1, 7, 14, 28],
)

# SaaS standard
ws.query_retention("Signup", "Login",
    retention_unit="week",
    bucket_sizes=[1, 2, 4, 8, 12],
)
```

### Validation Rules for bucket_sizes

- Values must be **positive integers** (R5) — no floats, no zero, no negatives
- Must be in **strictly ascending** order (R6) — `[1, 3, 7]` is valid; `[7, 3, 1]` is not; `[1, 1, 3]` is not
- Maximum **730** entries (R5c)

```python
# WRONG — not ascending
ws.query_retention("Signup", "Login", bucket_sizes=[7, 3, 1])  # R6 error

# WRONG — contains float
ws.query_retention("Signup", "Login", bucket_sizes=[1.0, 3.0])  # R5 error

# WRONG — contains zero
ws.query_retention("Signup", "Login", bucket_sizes=[0, 1, 7])  # R5 error

# WRONG — not strictly ascending (duplicates)
ws.query_retention("Signup", "Login", bucket_sizes=[1, 1, 7])  # R6 error

# CORRECT
ws.query_retention("Signup", "Login", bucket_sizes=[1, 3, 7, 14, 30])
```

---

## Unbounded Mode

`RetentionUnboundedMode = Literal["none", "carry_back", "carry_forward", "consecutive_forward"]`

Controls how users who return outside their exact retention bucket are counted:

| Mode | Behavior | Use Case |
|------|----------|----------|
| `none` | Standard counting — only count in the exact bucket (default) | Standard retention analysis |
| `carry_back` | If a user returns in bucket N, also count in all prior buckets | Fill gaps for irregular engagement |
| `carry_forward` | If a user returns in bucket N, count in all subsequent buckets | Optimistic retention view |
| `consecutive_forward` | Count forward from the last bucket where the user was active | Streak-based retention |

```python
# Carry-forward: once a user returns, count them as retained in all later buckets
result = ws.query_retention(
    "Signup", "Login",
    unbounded_mode="carry_forward",
    retention_unit="week", last=90,
)
```

---

## Cumulative Retention

Enable cumulative counting — each bucket shows the total number of users who returned at least once up to that point:

```python
result = ws.query_retention(
    "Signup", "Login",
    retention_cumulative=True,
    retention_unit="week", last=90,
)
```

---

## Period-over-Period Comparison

_(→ [insights-reference.md](insights-reference.md) §TimeComparison for factory methods and validation rules)_

```python
from mixpanel_data import TimeComparison

# Compare this month's retention against last month
result = ws.query_retention(
    "Signup", "Login",
    time_comparison=TimeComparison.relative("month"),
    retention_unit="week", last=30,
)
```

---

## RetentionMathType

`RetentionMathType = Literal["retention_rate", "unique", "total", "average"]`

| Type | Returns | Value Range | When to Use |
|------|---------|-------------|-------------|
| `retention_rate` | Percentage of cohort retained | 0.0 to 1.0 | Default. Compare retention across cohorts and segments. |
| `unique` | Raw count of unique users retained | 0 to cohort size | When absolute numbers matter (volume analysis). |
| `total` | Total event count per retention bucket | 0+ | When absolute event volume matters, not just unique users. |
| `average` | Average of a numeric property per bucket | float | Property-based retention (requires `math_property`). |

```python
# Percentage (default)
rates = ws.query_retention("Signup", "Login", math="retention_rate")
# rates.cohorts["2025-01-06"]["rates"] = [1.0, 0.45, 0.32, 0.28, ...]

# Raw counts
counts = ws.query_retention("Signup", "Login", math="unique")
# counts.cohorts["2025-01-06"]["counts"] = [500, 225, 160, 140, ...]

# Total login events per bucket
result = ws.query_retention("Signup", "Login", math="total")

# Average session duration per bucket
result = ws.query_retention("Signup", "Login", math="average", math_property="session_duration")
```

---

## Display Modes

`RetentionMode = Literal["curve", "trends", "table"]`

### Curve (default)

Shows the classic retention curve — how retention decays over successive buckets.

```python
result = ws.query_retention("Signup", "Login", mode="curve")
```

### Trends

Shows retention for specific buckets as trends over time. Useful for tracking whether D7 or D30 retention is improving.

```python
result = ws.query_retention("Signup", "Login", mode="trends")
```

### Table

Shows the full cohort-by-bucket matrix in tabular form.

```python
result = ws.query_retention("Signup", "Login", mode="table")
```

---

## RetentionQueryResult Structure

```python
result = ws.query_retention("Signup", "Login")

result.df               # pandas DataFrame (lazy, cached)
result.cohorts          # dict — cohort-level retention data
result.average          # dict — synthetic $average cohort
result.params           # dict — generated bookmark params
result.meta             # dict — response metadata
result.computed_at      # str — ISO timestamp
result.from_date        # str — resolved start date
result.to_date          # str — resolved end date
result.segments         # dict — per-segment data (when group_by used)
result.segment_averages # dict — per-segment averages (when group_by used)
```

### cohorts Structure

Keys are cohort date strings (`YYYY-MM-DD`), values are dicts:

```python
result.cohorts = {
    "2025-01-06": {
        "first": 500,                              # Cohort size (born users)
        "counts": [500, 225, 160, 140, 120],        # Retained users per bucket
        "rates": [1.0, 0.45, 0.32, 0.28, 0.24],    # Retention rate per bucket
    },
    "2025-01-13": {
        "first": 480,
        "counts": [480, 210, 144, 130],
        "rates": [1.0, 0.4375, 0.30, 0.27],
    },
}
```

### average Structure

Synthetic cohort representing the average across all cohorts:

```python
result.average = {
    "first": 490,                                   # Average cohort size
    "counts": [490, 217, 152, 135, 120],            # Average retained counts
    "rates": [1.0, 0.443, 0.31, 0.275, 0.245],     # Average retention rates
}
```

### DataFrame Columns

**Unsegmented** (no `group_by`):

| Column | Type | Description |
|--------|------|-------------|
| `cohort_date` | str | Cohort date (YYYY-MM-DD) |
| `bucket` | int | Retention bucket index (0 = born, 1 = first return period, ...) |
| `count` | int | Number of retained users |
| `rate` | float | Retention rate (0.0 to 1.0) |

**Segmented** (with `group_by`):

| Column | Type | Description |
|--------|------|-------------|
| `segment` | str | Segment value (e.g. "iOS", "Android") |
| `cohort_date` | str | Cohort date |
| `bucket` | int | Retention bucket index |
| `count` | int | Retained users |
| `rate` | float | Retention rate |

### Segmented Results

When `group_by` is used:

```python
result = ws.query_retention("Signup", "Login", group_by="platform")

# result.cohorts contains the $overall aggregate
# result.segments contains per-segment data
for segment_name, segment_cohorts in result.segments.items():
    print(f"\n{segment_name}:")
    for cohort_date, data in segment_cohorts.items():
        print(f"  {cohort_date}: W1={data['rates'][1]:.1%}")

# result.segment_averages has per-segment averages
for name, avg in result.segment_averages.items():
    print(f"{name} avg W1: {avg['rates'][1]:.1%}")
```

---

## Cohort-Scoped Retention

_(→ [insights-reference.md](insights-reference.md) §Cohort Capabilities for the full cohort API)_

### Cohort Filters

Measure retention for a specific user segment:

```python
from mixpanel_data import Filter

# Retention for power users only
result = ws.query_retention(
    "Signup", "Login",
    where=Filter.in_cohort(123, "Power Users"),
    retention_unit="week", last=90,
)
```

### Cohort Breakdowns

Compare retention curves inside vs outside a cohort:

```python
from mixpanel_data import CohortBreakdown

result = ws.query_retention(
    "Signup", "Login",
    group_by=CohortBreakdown(123, "Power Users"),
    retention_unit="week", last=90,
)
# Compares "Power Users" vs "Not In Power Users" retention curves
```

**Constraint**: `CohortBreakdown` and property `GroupBy` are mutually exclusive in retention (CB3). You cannot combine `CohortBreakdown(123, "Power Users")` with `"platform"` in the same `group_by` list. Use separate queries instead.

---

## Analysis Patterns

### Basic Retention Curve

```python
import mixpanel_data as mp

ws = mp.Workspace()
result = ws.query_retention("Signup", "Login", retention_unit="week", last=90)

# Print average retention curve
avg = result.average
print("Average retention curve:")
for i, rate in enumerate(avg.get("rates", [])):
    print(f"  W{i}: {rate:.1%}")
```

### Cohort Comparison

Compare retention across specific cohorts:

```python
result = ws.query_retention("Signup", "Login", retention_unit="week",
                             from_date="2025-01-01", to_date="2025-03-31")

# Compare first and last cohort
dates = sorted(result.cohorts.keys())
first_cohort = result.cohorts[dates[0]]
last_cohort = result.cohorts[dates[-1]]

min_buckets = min(len(first_cohort["rates"]), len(last_cohort["rates"]))
print(f"{'Bucket':>8}  {'First':>8}  {'Last':>8}  {'Delta':>8}")
for i in range(min_buckets):
    r1 = first_cohort["rates"][i]
    r2 = last_cohort["rates"][i]
    print(f"  W{i:>5}  {r1:>7.1%}  {r2:>7.1%}  {r2-r1:>+7.1%}")
```

### Benchmarking Against Industry Standards

```python
result = ws.query_retention("Signup", "Login", retention_unit="day",
                             bucket_sizes=[1, 7, 30])

avg = result.average
rates = avg.get("rates", [])

benchmarks = {
    "Consumer Mobile": {"D1": 0.30, "D7": 0.20, "D30": 0.12},
    "SaaS B2B": {"D1": 0.70, "D7": 0.50, "D30": 0.40},
}

print(f"Your product:")
labels = ["D0", "D1", "D7", "D30"]
for i, label in enumerate(labels):
    if i < len(rates):
        print(f"  {label}: {rates[i]:.1%}")

for category, bm in benchmarks.items():
    print(f"\n{category} benchmark:")
    for label, val in bm.items():
        print(f"  {label}: {val:.1%}")
```

### Segment Breakdown

```python
result = ws.query_retention("Signup", "Login", group_by="platform",
                             retention_unit="week")

# Compare W1 retention across segments
print("W1 retention by platform:")
for name, avg in result.segment_averages.items():
    rates = avg.get("rates", [])
    w1 = rates[1] if len(rates) > 1 else 0
    print(f"  {name}: {w1:.1%}")
```

### Retention Heatmap (Pivot)

```python
import pandas as pd

result = ws.query_retention("Signup", "Login", retention_unit="week", last=90)
df = result.df

# Pivot to cohort x bucket matrix
heatmap = df.pivot_table(
    index="cohort_date",
    columns="bucket",
    values="rate",
)

# Format as percentages
print("Retention Heatmap:")
print(heatmap.map(lambda x: f"{x:.0%}" if pd.notna(x) else "--").to_string())
```

### Feature Impact on Retention

Compare retention of users who used a feature vs those who did not:

```python
from mixpanel_data import RetentionEvent, Filter

# Feature users
feature_ret = ws.query_retention(
    RetentionEvent("Signup", filters=[Filter.is_set("used_feature_x")]),
    "Login",
    retention_unit="week",
)

# Non-feature users
no_feature_ret = ws.query_retention(
    RetentionEvent("Signup", filters=[Filter.is_not_set("used_feature_x")]),
    "Login",
    retention_unit="week",
)

feat_avg = feature_ret.average.get("rates", [])
no_feat_avg = no_feature_ret.average.get("rates", [])

print("Feature impact on retention:")
min_len = min(len(feat_avg), len(no_feat_avg))
for i in range(min_len):
    diff = feat_avg[i] - no_feat_avg[i]
    print(f"  W{i}: feature={feat_avg[i]:.1%}  "
          f"no-feature={no_feat_avg[i]:.1%}  "
          f"lift={diff:+.1%}")
```

### Inflection Point Detection

Find where retention stabilizes (the "plateau"):

```python
result = ws.query_retention("Signup", "Login", retention_unit="day",
                             bucket_sizes=[1, 3, 7, 14, 30, 60, 90])

rates = result.average.get("rates", [])
buckets = [0, 1, 3, 7, 14, 30, 60, 90][:len(rates)]

# Find where the rate of decline slows below 2pp per period
print("Retention decay analysis:")
for i in range(1, len(rates)):
    drop = rates[i-1] - rates[i]
    print(f"  D{buckets[i]:>3}: {rates[i]:.1%}  "
          f"(drop: {drop:+.1%} from D{buckets[i-1]})")
    if drop < 0.02 and i > 1:
        print(f"  >>> Plateau detected around D{buckets[i]}")
        break
```

### Rolling Retention (pandas)

Compute rolling average of retention rates across cohorts:

```python
import pandas as pd

result = ws.query_retention("Signup", "Login", retention_unit="week", last=180)
df = result.df

# For a specific bucket (e.g., W1), plot the rolling trend
w1 = df[df["bucket"] == 1].set_index("cohort_date")["rate"]
w1.index = pd.to_datetime(w1.index)
w1_rolling = w1.rolling(4).mean()  # 4-cohort rolling average

print("W1 retention trend (4-cohort rolling average):")
print(w1_rolling.dropna().tail(12))
```

### Persisting as a Saved Report

```python
from mixpanel_data import CreateBookmarkParams

result = ws.query_retention("Signup", "Login",
                             retention_unit="week", last=90)

bm = ws.create_bookmark(CreateBookmarkParams(
    name="Weekly Signup Retention (90d)",
    bookmark_type="retention",
    params=result.params,
))
print(f"Retention report saved: {bm.id}")
```

### Inspect Without Querying

```python
params = ws.build_retention_params(
    "Signup", "Login",
    retention_unit="week",
    bucket_sizes=[1, 4, 8, 12],
    group_by="platform",
)
import json
print(json.dumps(params, indent=2))
```

_For retention benchmarks by industry (Consumer Mobile, SaaS, E-commerce), see [analytical-frameworks.md](analytical-frameworks.md) §Retention. For Insights-Retention correlation patterns, see [cross-query-synthesis.md](cross-query-synthesis.md) §Insights-Retention Correlation._

---

## Validation Rules Summary

### Retention-Specific Rules (R-rules)

| Rule | Check | Error Code |
|------|-------|------------|
| R1 | `born_event` must be non-empty, no control/invisible chars | `R1_EMPTY_BORN_EVENT`, `R1_CONTROL_CHAR_BORN_EVENT`, `R1_INVISIBLE_BORN_EVENT` |
| R2 | `return_event` must be non-empty, no control/invisible chars | `R2_EMPTY_RETURN_EVENT`, `R2_CONTROL_CHAR_RETURN_EVENT`, `R2_INVISIBLE_RETURN_EVENT` |
| R3 | Time argument validation (delegates to V7-V10, V15, V20) | See insights V-rules |
| R4 | GroupBy validation (delegates to V11-V12, V18, V24) | See insights V-rules |
| R5 | `bucket_sizes` values must be positive integers; max 730 entries | `R5_BUCKET_SIZES_POSITIVE`, `R5_BUCKET_SIZES_INTEGER`, `R5_BUCKET_SIZES_TOO_MANY` |
| R6 | `bucket_sizes` must be in strictly ascending order | `R6_BUCKET_SIZES_ASCENDING` |
| R7 | `retention_unit` must be valid (day, week, month) | `R7_INVALID_RETENTION_UNIT` |
| R8 | `alignment` must be valid (birth, interval_start) | `R8_INVALID_ALIGNMENT` |
| R9 | `math` must be valid (retention_rate, unique) | `R9_INVALID_MATH` |
| R10 | `mode` must be valid (curve, trends, table) | `R10_INVALID_MODE` |
| R11 | `unit` must be valid (day, week, month) | `R11_INVALID_UNIT` |
| R12 | `group_by` property names must be non-empty | `R12_EMPTY_GROUP_BY` |

### Inherited Time Rules

| Rule | Check |
|------|-------|
| V7 | `last` must be positive |
| V8 | Date format YYYY-MM-DD |
| V9 | `to_date` requires `from_date` |
| V10 | Cannot combine dates with non-default `last` |
| V15 | `from_date` <= `to_date` |
| V20 | `last` max 3650 |

### Inherited GroupBy Rules

| Rule | Check |
|------|-------|
| V11 | `bucket_min`/`bucket_max` require `bucket_size` |
| V12 | `bucket_size` must be positive and require `property_type="number"` |
| V18 | `bucket_min` < `bucket_max` |
| V24 | Bucket values must be finite |

---

## Common Pitfalls

1. **retention_unit vs unit** — `retention_unit` sets the bucket size (day/week/month); `unit` is the time granularity for the query date range. They serve different purposes.
2. **bucket_sizes must be strictly ascending** — `[1, 1, 7]` fails because of the duplicate; `[7, 3, 1]` fails because it is descending.
3. **bucket_sizes values must be integers** — `[1.0, 3.0, 7.0]` fails. Use `[1, 3, 7]`.
4. **bucket_sizes values must be positive** — `[0, 1, 7]` fails. Start from 1.
5. **born_event = return_event measures stickiness** — This is a valid and common pattern, not a mistake.
6. **RetentionMathType has four values** — `"retention_rate"`, `"unique"`, `"total"`, and `"average"`. The `"average"` type requires `math_property` to be set.
7. **Segmented results use .segments** — When `group_by` is used, per-segment data is in `result.segments`, not `result.cohorts` (which has the $overall aggregate).
8. **Bucket 0 is always 100%** — The first bucket represents the born event itself, so its retention rate is always 1.0.
9. **alignment affects interpretation** — With `"birth"` alignment, each user's W1 starts from their signup date. With `"interval_start"`, W1 is the same calendar week for all users in that cohort.
10. **QueryTimeUnit differs from retention TimeUnit** — `unit` (the date range unit) supports `"hour"` and `"quarter"` in addition to day/week/month, but `retention_unit` only supports day/week/month.

_For retention heatmaps, cohort pivot tables, and LTV estimation from retention data, see [advanced-analysis.md](advanced-analysis.md) §Cohort Analysis with pandas._
