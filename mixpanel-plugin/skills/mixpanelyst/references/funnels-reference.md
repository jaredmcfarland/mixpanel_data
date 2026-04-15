# Funnels Query Reference — ws.query_funnel() Deep Dive

Complete reference for `Workspace.query_funnel()`, the typed funnel query engine. Covers every parameter, type, validation rule, and analysis pattern.

_Funnels inherit Filter, GroupBy, and time range handling from Insights — see [insights-reference.md](insights-reference.md) for the authoritative reference on these shared concepts._

## Complete Signature

```python
Workspace.query_funnel(
    steps: list[str | FunnelStep],
    *,
    conversion_window: int = 14,
    conversion_window_unit: Literal["second", "minute", "hour", "day",
                                     "week", "month", "session"] = "day",
    order: Literal["loose", "any"] = "loose",
    from_date: str | None = None,
    to_date: str | None = None,
    last: int = 30,
    unit: QueryTimeUnit = "day",
    math: FunnelMathType = "conversion_rate_unique",
    math_property: str | None = None,
    group_by: str | GroupBy | CohortBreakdown | list[str | GroupBy | CohortBreakdown] | None = None,
    where: Filter | list[Filter] | None = None,
    exclusions: list[str | Exclusion] | None = None,
    holding_constant: str | HoldingConstant | list[str | HoldingConstant] | None = None,
    mode: Literal["steps", "trends", "table"] = "steps",
    reentry_mode: FunnelReentryMode | None = None,  # funnel reentry behavior
    time_comparison: TimeComparison | None = None,   # period-over-period comparison
    data_group_id: int | None = None,                # data group scope
) -> FunnelQueryResult
```

**Companion method**: `ws.build_funnel_params()` has the identical signature but returns the bookmark params dict without making an API call. Useful for debugging, inspecting generated JSON, or passing to `create_bookmark()`.

---

## Steps: Defining the Funnel

### Simple String Steps

The simplest funnel uses plain event name strings:

```python
result = ws.query_funnel(["Signup", "Add to Cart", "Purchase"])
```

### FunnelStep Objects

Use `FunnelStep` for per-step filters, labels, or ordering overrides:

```python
from mixpanel_data import FunnelStep, Filter

step1 = FunnelStep("Signup")
step2 = FunnelStep(
    "Purchase",
    label="High-Value Purchase",
    filters=[Filter.greater_than("amount", 50)],
)
result = ws.query_funnel([step1, step2])
```

### FunnelStep Attributes

```python
@dataclass(frozen=True)
class FunnelStep:
    event: str                                          # Mixpanel event name (required)
    label: str | None = None                            # Display label (defaults to event name)
    filters: list[Filter] | None = None                 # Per-step filter conditions
    filters_combinator: Literal["all", "any"] = "all"   # AND/OR for per-step filters
    order: Literal["loose", "any"] | None = None        # Per-step ordering override
```

### Per-Step Filters

Per-step filters restrict which events count for that specific step, independently of the global `where` filters:

```python
result = ws.query_funnel([
    FunnelStep("Visit", filters=[Filter.equals("page", "/pricing")]),
    FunnelStep("Signup"),
    FunnelStep("Purchase", filters=[
        Filter.greater_than("amount", 25),
        Filter.equals("currency", "USD"),
    ]),
])
```

### Per-Step Filter Combinator

```python
# OR logic: match US or UK visitors
FunnelStep("Visit",
    filters=[
        Filter.equals("country", "US"),
        Filter.equals("country", "UK"),
    ],
    filters_combinator="any",  # Any filter can match
)
```

### Per-Step Ordering Override

Only meaningful when the top-level `order` is `"any"`. Allows individual steps to require strict ordering even in an any-order funnel:

```python
result = ws.query_funnel(
    [
        FunnelStep("Signup"),                              # Must happen in any order
        FunnelStep("Add to Cart"),                         # relative to other steps
        FunnelStep("Purchase", order="loose"),             # But Purchase must come after Cart
    ],
    order="any",
)
```

### Mixing Strings and FunnelStep Objects

```python
result = ws.query_funnel([
    "Visit",                                               # Simple string step
    "Signup",                                              # Simple string step
    FunnelStep("Purchase",                                 # Rich step with filter
        filters=[Filter.greater_than("amount", 10)]),
])
```

### Step Limits

- Minimum: 2 steps (F1)
- Maximum: 100 steps (F1)
- Each event name must be non-empty (F2)

---

## Exclusions

Exclusions remove users who perform a specific event between funnel steps. Users who trigger an excluded event during the conversion window are dropped from the funnel entirely.

### Simple String Exclusion

Excludes users who perform the event between any steps:

```python
result = ws.query_funnel(
    ["Signup", "Activate", "Purchase"],
    exclusions=["Logout", "Uninstall"],
)
```

### Targeted Exclusion with Step Ranges

Use `Exclusion` objects to restrict exclusion to specific step ranges:

```python
from mixpanel_data import Exclusion

result = ws.query_funnel(
    ["Visit", "Signup", "Activate", "Purchase"],
    exclusions=[
        Exclusion("Logout"),                        # Exclude between all steps (default)
        Exclusion("Refund", from_step=2, to_step=3),  # Only between Activate and Purchase
        Exclusion("Cancel", from_step=1, to_step=2),  # Only between Signup and Activate
    ],
)
```

### Exclusion Attributes

```python
@dataclass(frozen=True)
class Exclusion:
    event: str                  # Event name to exclude
    from_step: int = 0          # Start of exclusion range (0-indexed, inclusive)
    to_step: int | None = None  # End of exclusion range (0-indexed, inclusive). None = last step
```

### Exclusion Step Indexing

Steps are **0-indexed**:

```
Step 0: Visit
Step 1: Signup
Step 2: Activate
Step 3: Purchase
```

- `Exclusion("X", from_step=0, to_step=3)` — exclude between any steps (default)
- `Exclusion("X", from_step=1, to_step=2)` — exclude only between steps 1 and 2

### Exclusion Validation Rules

- Event name must be non-empty (F4)
- `from_step` must be >= 0 (F4e)
- `to_step` must be > `from_step` (F4b) — server requires strict ordering
- `to_step` must not exceed step count (F4c)
- `from_step` must not exceed step count (F4d)

---

## HoldingConstant

Holding a property constant means only counting users whose property value is the **same at every funnel step**. This is useful for ensuring consistent context across the conversion journey.

### Simple String Usage

```python
result = ws.query_funnel(
    ["Signup", "Purchase"],
    holding_constant=["platform"],  # Same platform at every step
)
```

### HoldingConstant Object

Use `HoldingConstant` for user-profile properties:

```python
from mixpanel_data import HoldingConstant

result = ws.query_funnel(
    ["Signup", "Purchase"],
    holding_constant=[
        HoldingConstant("device_id"),                           # Event property (default)
        HoldingConstant("plan_tier", resource_type="people"),   # User profile property
    ],
)
```

### HoldingConstant Attributes

```python
@dataclass(frozen=True)
class HoldingConstant:
    property: str                                               # Property name
    resource_type: Literal["events", "people"] = "events"       # Event or user property
```

### Limits and Validation

- Maximum **3** holding_constant properties per query (F8)
- Each property name must be non-empty (F8b)

### Use Cases

| Use Case | Property | Why |
|----------|----------|-----|
| Same-device funnel | `"device_id"` | User must complete all steps on the same device |
| Same-session funnel | `"session_id"` | User must complete all steps in the same session |
| Same-platform funnel | `"platform"` | User must stay on iOS or Android throughout |
| Consistent pricing tier | `"plan_tier"` (people) | User's plan must not change during conversion |

---

## Conversion Window

The conversion window defines how long a user has to complete all funnel steps after entering the funnel.

### Units and Maximums

| Unit | Maximum | Example |
|------|---------|---------|
| `second` | 31,708,800 (~1 year) | `conversion_window=3600` (1 hour) |
| `minute` | 528,480 (~1 year) | `conversion_window=60` (1 hour) |
| `hour` | 8,808 (~1 year) | `conversion_window=24` (1 day) |
| `day` | 367 (~1 year) | `conversion_window=14` (2 weeks, default) |
| `week` | 52 (~1 year) | `conversion_window=4` (1 month) |
| `month` | 12 (1 year) | `conversion_window=3` (1 quarter) |
| `session` | 12 | `conversion_window=1` (required) |

### Session-Based Conversion

Session-based funnels have special constraints:

```python
# Session funnel — all three are required together
result = ws.query_funnel(
    ["Add to Cart", "Checkout", "Purchase"],
    conversion_window=1,                        # Must be 1
    conversion_window_unit="session",           # Must be "session"
    math="conversion_rate_session",             # Must use session math
)
```

**Session constraints** (F9):
- `math="conversion_rate_session"` requires `conversion_window_unit="session"`
- `conversion_window_unit="session"` requires `conversion_window=1`

### Second-Unit Minimum

When using `conversion_window_unit="second"`, the minimum conversion_window is **2** (not 1) (F7b).

```python
# WRONG — minimum is 2 for seconds
ws.query_funnel(steps, conversion_window=1, conversion_window_unit="second")

# CORRECT
ws.query_funnel(steps, conversion_window=2, conversion_window_unit="second")
```

---

## FunnelMathType

_Counting and property aggregation types are shared with Insights — see [insights-reference.md](insights-reference.md) §MathType Deep Reference. Funnels add three conversion rate types: conversion_rate_unique, conversion_rate_total, conversion_rate_session._

```python
FunnelMathType = Literal[
    "conversion_rate_unique",   # Unique-user conversion rate (default)
    "conversion_rate_total",    # Total-event conversion rate
    "conversion_rate_session",  # Session-based conversion rate
    "unique",                   # Raw unique user count per step
    "total",                    # Raw total event count per step
    "average",                  # Mean of a numeric property per step
    "median",                   # Median of a numeric property per step
    "min",                      # Min of a numeric property per step
    "max",                      # Max of a numeric property per step
    "p25",                      # 25th percentile per step
    "p75",                      # 75th percentile per step
    "p90",                      # 90th percentile per step
    "p99",                      # 99th percentile per step
    "histogram",                # Distribution of a numeric property per step
]
```

### Conversion Rate Types

| Type | What It Measures | When to Use |
|------|-----------------|-------------|
| `conversion_rate_unique` | % of unique users who complete each step | Default. Standard funnel analysis. |
| `conversion_rate_total` | % of total events (a user can convert multiple times) | E-commerce where repeat purchases matter. |
| `conversion_rate_session` | % of sessions with complete conversion | Within-session conversion (requires session window). |

### Count Types

| Type | What It Measures | When to Use |
|------|-----------------|-------------|
| `unique` | Raw count of unique users at each step | When you need absolute numbers, not percentages. |
| `total` | Raw count of total events at each step | When one user can trigger a step multiple times. |

### Property Aggregation Types

All require `math_property` to be set (F10):

| Type | What It Measures | Example |
|------|-----------------|---------|
| `average` | Mean of property at each step | Average revenue per step |
| `median` | Median of property at each step | Median order value |
| `min` / `max` | Extremes | Smallest/largest order per step |
| `p25` / `p75` / `p90` / `p99` | Percentiles | Revenue distribution per step |
| `histogram` | Distribution of property values at each step | Revenue distribution per step |

```python
# Measure average revenue at each funnel step
result = ws.query_funnel(
    ["Add to Cart", "Checkout", "Purchase"],
    math="average",
    math_property="revenue",
)
```

### math_property Validation

- Property aggregation math types (average, median, min, max, p25-p99) require `math_property` (F10)
- Non-property math types (conversion_rate_*, unique, total) reject `math_property` (F11)

---

## Ordering: Loose vs Any

### Loose (default)

Users must complete steps **in order**, but other events can occur between steps:

```python
# User must do: Signup → (anything) → Activate → (anything) → Purchase
ws.query_funnel(["Signup", "Activate", "Purchase"], order="loose")
```

### Any

Users can complete steps in **any order** within the conversion window:

```python
# User can do steps in any sequence
ws.query_funnel(
    ["View Product", "Add to Wishlist", "Add to Cart"],
    order="any",
)
```

---

## Reentry Mode

Controls how users re-enter the funnel after completing all steps.

`FunnelReentryMode = Literal["default", "basic", "aggressive", "optimized"]`

| Mode | Behavior | Use Case |
|------|----------|----------|
| `default` | Server default behavior | General analysis |
| `basic` | Re-enter after conversion window expires | Standard repeat measurement |
| `aggressive` | Re-enter as soon as they convert | High-frequency funnels (e-commerce) |
| `optimized` | Server-optimized reentry | Best for most repeat-conversion funnels |

```python
# Aggressive reentry for repeat purchase analysis
result = ws.query_funnel(
    ["Browse", "Add to Cart", "Purchase"],
    reentry_mode="aggressive",
    last=30,
)
```

---

## Period-over-Period Comparison

_(→ [insights-reference.md](insights-reference.md) §TimeComparison for factory methods and validation rules)_

```python
from mixpanel_data import TimeComparison

# Compare this week's funnel against last week
result = ws.query_funnel(
    ["Signup", "Purchase"],
    time_comparison=TimeComparison.relative("week"),
    last=7,
)
```

---

## Data Group Scope

Scope a funnel query to a specific data group:

```python
# Scope to a data group
result = ws.query_funnel(["Signup", "Purchase"], data_group_id=42)
```

---

## Display Modes

### Steps (default)

Returns step-level detail. Best for drop-off analysis.

```python
result = ws.query_funnel(steps, mode="steps")
# result.df columns: step, event, count, step_conv_ratio, overall_conv_ratio,
#                     avg_time, avg_time_from_start
```

### Trends

Returns conversion rate over time. Best for tracking funnel performance trends.

```python
result = ws.query_funnel(steps, mode="trends")
# Shows how the overall conversion rate changes day-by-day
```

### Table

Returns tabular data.

```python
result = ws.query_funnel(steps, mode="table")
```

---

## FunnelQueryResult Structure

```python
result = ws.query_funnel(["Signup", "Purchase"])

result.overall_conversion_rate   # float 0.0-1.0 — end-to-end conversion
result.df                        # pandas DataFrame (lazy, cached)
result.steps_data                # list[dict] — raw step-level data
result.series                    # dict — raw API series data
result.params                    # dict — generated bookmark params
result.meta                      # dict — response metadata
result.computed_at               # str — ISO timestamp
result.from_date                 # str — resolved start date
result.to_date                   # str — resolved end date
```

### DataFrame Columns (mode="steps")

| Column | Type | Description |
|--------|------|-------------|
| `step` | int | Step number (1-indexed) |
| `event` | str | Event name |
| `count` | int | Number of users/events at this step |
| `step_conv_ratio` | float | Conversion rate from previous step (0.0-1.0) |
| `overall_conv_ratio` | float | Conversion rate from first step (0.0-1.0) |
| `avg_time` | float | Average time from previous step (seconds) |
| `avg_time_from_start` | float | Average time from first step (seconds) |

### steps_data Structure

Each entry in `steps_data` is a dict:

```python
{
    "event": "Purchase",
    "count": 1234,
    "step_conv_ratio": 0.45,
    "overall_conv_ratio": 0.12,
    "avg_time": 86400.0,            # seconds from previous step
    "avg_time_from_start": 259200.0, # seconds from first step
}
```

---

## Cohort-Scoped Funnels

_(→ [insights-reference.md](insights-reference.md) §Cohort Capabilities for the full cohort API including CohortDefinition inline syntax)_

### Cohort Filters

Restrict funnel analysis to a specific user segment:

```python
from mixpanel_data import Filter

# Funnel conversion for power users only
result = ws.query_funnel(
    ["Signup", "Activate", "Purchase"],
    where=Filter.in_cohort(123, "Power Users"),
    conversion_window=7,
)
print(f"Power user conversion: {result.overall_conversion_rate:.1%}")
```

### Cohort Breakdowns

Compare funnel conversion inside vs outside a cohort:

```python
from mixpanel_data import CohortBreakdown

result = ws.query_funnel(
    ["Signup", "Activate", "Purchase"],
    group_by=CohortBreakdown(123, "Power Users"),
)
# Compare "Power Users" vs "Not In Power Users" step-by-step conversion
```

---

## Analysis Patterns

### Drop-Off Analysis

Find where users abandon the funnel and quantify the loss:

```python
result = ws.query_funnel(["Visit", "Signup", "Activate", "Purchase"])
df = result.df

print(f"Overall conversion: {result.overall_conversion_rate:.1%}")
print("\nStep-by-step:")
for _, row in df.iterrows():
    drop = 1 - row["step_conv_ratio"] if row["step"] > 1 else 0
    print(f"  Step {row['step']}: {row['event']:20s} "
          f"count={row['count']:>6,.0f}  "
          f"conv={row['step_conv_ratio']:.1%}  "
          f"drop={drop:.1%}")

# Identify worst step
worst = df.loc[df["step_conv_ratio"].idxmin()]
print(f"\nBiggest drop-off: {worst['event']} ({1 - worst['step_conv_ratio']:.1%} drop)")
```

### Time-to-Convert Analysis

Understand how long each step takes:

```python
result = ws.query_funnel(["Signup", "Activate", "Purchase"])
df = result.df

for _, row in df.iterrows():
    if row["step"] > 1:
        hours = row["avg_time"] / 3600
        total_hours = row["avg_time_from_start"] / 3600
        print(f"  {row['event']}: {hours:.1f}h from previous, "
              f"{total_hours:.1f}h from start")
```

### Segment Comparison

Compare funnel performance across segments:

```python
result = ws.query_funnel(
    ["Signup", "Activate", "Purchase"],
    group_by="platform",
)
df = result.df

# Compare overall conversion by platform
by_platform = df.groupby("event").apply(
    lambda g: g[g["step"] == g["step"].max()]["overall_conv_ratio"].mean()
)
print("Conversion by platform:")
print(by_platform.sort_values(ascending=False))
```

### A/B Funnel Comparison

Compare funnel conversion between experiment variants:

```python
result = ws.query_funnel(
    ["Visit", "Signup", "Purchase"],
    group_by="experiment_variant",
)
# Compare conversion rates across variants
```

### Funnel Trends Over Time

Track how conversion changes over time:

```python
result = ws.query_funnel(
    ["Signup", "Purchase"],
    mode="trends",
    last=90,
    unit="week",
)
print(result.df)  # Weekly conversion rate trend
```

### Conversion Window Sensitivity

Test different conversion windows to find the optimal one:

```python
for window in [1, 3, 7, 14, 30]:
    result = ws.query_funnel(
        ["Signup", "Purchase"],
        conversion_window=window,
        conversion_window_unit="day",
    )
    print(f"  {window:2d}-day window: {result.overall_conversion_rate:.1%}")
```

### Persisting as a Saved Report

```python
from mixpanel_data import CreateBookmarkParams

result = ws.query_funnel(["Signup", "Activate", "Purchase"])

bm = ws.create_bookmark(CreateBookmarkParams(
    name="Signup Funnel",
    bookmark_type="funnels",
    params=result.params,
))
print(f"Funnel report saved: {bm.id}")
```

### Inspect Without Querying

```python
# Generate params without calling API
params = ws.build_funnel_params(
    ["Signup", "Activate", "Purchase"],
    conversion_window=7,
    group_by="platform",
)
import json
print(json.dumps(params, indent=2))
```

_For multi-engine patterns combining funnels with other engines (e.g., Funnel-Flow Complement), see [cross-query-synthesis.md](cross-query-synthesis.md) §Funnel-Flow Complement._

---

## Validation Rules Summary

### Funnel-Specific Rules (F-rules)

| Rule | Check | Error Code |
|------|-------|------------|
| F1 | At least 2 steps required; maximum 100 | `F1_MIN_STEPS`, `F1_MAX_STEPS` |
| F2 | Each step event must be non-empty string, no control/invisible chars | `F2_EMPTY_STEP_EVENT`, `F2_CONTROL_CHAR_STEP_EVENT`, `F2_INVISIBLE_STEP_EVENT` |
| F3 | `conversion_window` must be a positive integer | `F3_CONVERSION_WINDOW_POSITIVE`, `F3_CONVERSION_WINDOW_TYPE` |
| F3b | `conversion_window` must not exceed per-unit maximum | `F3_CONVERSION_WINDOW_MAX` |
| F4 | Exclusion event names must be non-empty; step ranges valid | `F4_EMPTY_EXCLUSION_EVENT`, `F4_EXCLUSION_STEP_ORDER`, `F4_EXCLUSION_STEP_BOUNDS` |
| F4e | Exclusion `from_step` must be >= 0 | `F4_EXCLUSION_NEGATIVE_STEP` |
| F5 | Time argument validation (delegates to V7-V10, V15, V20) | See insights V-rules |
| F6 | GroupBy validation (delegates to V11-V12, V18, V24) | See insights V-rules |
| F7 | `conversion_window_unit` must be valid | `F7_INVALID_WINDOW_UNIT` |
| F7b | Second-unit conversion window minimum is 2 | `F7_SECOND_MIN_WINDOW` |
| F8 | Maximum 3 `holding_constant` properties; each non-empty | `F8_MAX_HOLDING_CONSTANT`, `F8_EMPTY_HOLDING_CONSTANT_PROPERTY` |
| F9 | Session math requires session window; session window requires window=1 | `F9_SESSION_MATH_REQUIRES_SESSION_WINDOW`, `F9_SESSION_WINDOW_REQUIRES_ONE` |
| F10 | Property math requires `math_property` | `F10_MATH_MISSING_PROPERTY` |
| F11 | Non-property math rejects `math_property` | `F11_MATH_REJECTS_PROPERTY` |

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

1. **Minimum 2 steps** — A single-step "funnel" is not valid; use `ws.query()` for single-event analysis
2. **conversion_window is days by default** — `conversion_window=14` means 14 days, not 14 hours
3. **Session math trifecta** — Session-based funnels require all three: `conversion_window=1`, `conversion_window_unit="session"`, `math="conversion_rate_session"`
4. **Second-unit minimum is 2** — `conversion_window=1` with `conversion_window_unit="second"` is rejected
5. **Exclusion steps are 0-indexed** — Step 0 is the first step, not step 1
6. **to_step must be > from_step** — The server requires strict ordering, not >= but >
7. **Maximum 3 holding_constant** — The API rejects queries with more than 3 properties held constant
8. **Property math needs math_property** — Using `math="average"` without `math_property` triggers F10
9. **String exclusions exclude globally** — Passing `"Logout"` as a string excludes between all steps; use `Exclusion()` for targeted step ranges
10. **order="any" is per-funnel** — Per-step `order` override on `FunnelStep` only matters when the top-level order is `"any"`
