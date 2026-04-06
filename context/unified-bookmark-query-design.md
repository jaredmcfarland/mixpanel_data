# Unified Bookmark Query System — Design Document

**Date**: 2026-04-05
**Status**: Design — Decisions Finalized
**Builds on**: `specs/029-insights-query-api/` (PR #86, #87)
**Reference**: `analytics/` repo (Mixpanel canonical implementation)

---

## 1. Executive Summary

This document specifies the design for extending `mixpanel_data`'s typed query system — currently limited to insights bookmarks via `Workspace.query()` — to cover the full Mixpanel bookmark query language: **funnels**, **retention**, and **flows**.

The system adds three new public methods — `query_funnel()`, `query_retention()`, and `query_flow()` — that reuse the infrastructure already built for `query()`: the two-layer validation engine, the bookmark params builder, the `Filter`/`GroupBy` types, and the `_resolve_and_build_params` pipeline. Each method generates valid bookmark JSON for its report type, POSTs it to the `/insights` endpoint (funnels, retention) or `/arb_funnels` endpoint (flows), and returns a typed result with lazy DataFrame conversion.

### Why Not One Method?

The research reveals that insights, funnels, retention, and flows have **fundamentally different `behavior` structures** in `sections.show[]`. They also have different required parameters, different valid math types, different chart types, different response formats, and different result semantics. A single `query()` method accepting all four would require:

- A union-typed `events` parameter that changes meaning per report type
- Conditional validation rules that depend on which behavior type is being built
- A union return type that loses type specificity

Separate methods with shared infrastructure is both more type-safe and more discoverable. An LLM agent seeing `query_funnel(steps=[...])` immediately knows it's building a funnel. An LLM seeing `query(events=[...], behavior_type="funnel")` has to reason about which parameters apply.

### Design Principles

1. **Shared infrastructure, separate interfaces** — Reuse `Filter`, `GroupBy`, validation engine, time range handling, and API client. Separate what's semantically different.
2. **Progressive disclosure** — The simplest funnel is `query_funnel(["Signup", "Purchase"])`. Everything else is a keyword argument.
3. **Fail-fast with actionable errors** — Two-layer validation catches invalid combinations before any API call, with structured `ValidationError` objects including fuzzy-matched suggestions.
4. **Result types match semantics** — Funnel results have step-level conversion data. Retention results have cohort-level rates. Flows results have node/edge graphs. Each gets a typed result class with an appropriate `.df` shape.
5. **Debuggable** — Every result includes `.params` (the bookmark JSON sent) for inspection and persistence via `create_bookmark()`.

---

## 2. Architecture

### 2.1 What Already Exists

```
Workspace
├── query()              → QueryResult          (insights bookmarks)
├── build_params()       → dict                  (params without execution)
├── _resolve_and_build_params()                  (shared validation + build pipeline)
├── _build_query_params()                        (insights bookmark JSON builder)
├── _build_filter_entry()                        (Filter → bookmark filter dict)
│
├── _internal/
│   ├── validation.py                            (two-layer validation engine)
│   │   ├── validate_query_args()                (Layer 1: argument rules V0-V27)
│   │   └── validate_bookmark()                  (Layer 2: structure rules B1-B19)
│   ├── bookmark_enums.py                        (canonical enum constants)
│   ├── api_client.py
│   │   ├── insights_query()                     (POST /insights with inline params)
│   │   └── query_flows()                        (GET /arb_funnels with bookmark_id)
│   └── services/live_query.py
│       ├── query()                              (insights: build body → POST → transform)
│       ├── query_flows()                        (flows: GET by bookmark_id → transform)
│       └── _transform_query_result()            (response → QueryResult)
│
├── types.py
│   ├── Metric, Filter, GroupBy, Formula         (input types)
│   ├── QueryResult                              (insights result)
│   └── FlowsResult                              (flows result — existing, bookmark_id-based)
│
└── exceptions.py
    ├── BookmarkValidationError                  (wraps list[ValidationError])
    └── ValidationError                          (path, message, code, severity, suggestion)
```

### 2.2 What Will Be Added

```
Workspace
├── query_funnel()       → FunnelQueryResult     (NEW)
├── query_retention()    → RetentionQueryResult  (NEW)
├── query_flow()         → FlowQueryResult       (NEW)
├── build_funnel_params()  → dict                (NEW — params without execution)
├── build_retention_params() → dict              (NEW — params without execution)
├── build_flow_params()    → dict                (NEW — params without execution)
│
├── _build_funnel_params()                       (NEW — funnel bookmark JSON builder)
├── _build_retention_params()                    (NEW — retention bookmark JSON builder)
├── _build_flow_params()                         (NEW — flows bookmark JSON builder)
│
├── _internal/
│   ├── validation.py
│   │   ├── validate_funnel_args()               (NEW — Layer 1 funnel rules)
│   │   ├── validate_retention_args()            (NEW — Layer 1 retention rules)
│   │   ├── validate_flow_args()                 (NEW — Layer 1 flow rules)
│   │   └── validate_bookmark()                  (EXTENDED — funnel/retention structure rules)
│   ├── bookmark_enums.py                        (EXTENDED — funnel/retention/flows enums)
│   ├── api_client.py
│   │   └── arb_funnels_query()                  (NEW — POST /arb_funnels with inline params)
│   └── services/live_query.py
│       ├── query_funnel()                       (NEW — insights endpoint with funnel behavior)
│       ├── query_retention()                    (NEW — insights endpoint with retention behavior)
│       ├── query_flow()                         (NEW — arb_funnels endpoint with flows params)
│       ├── _transform_funnel_result()           (NEW)
│       ├── _transform_retention_result()        (NEW)
│       └── _transform_flow_result()             (NEW)
│
├── types.py
│   ├── FunnelStep                               (NEW — frozen dataclass)
│   ├── FunnelQueryResult                        (NEW — frozen dataclass)
│   ├── RetentionQueryResult                     (NEW — frozen dataclass)
│   ├── FlowStep                                 (NEW — frozen dataclass)
│   ├── FlowQueryResult                          (NEW — frozen dataclass)
│   └── FunnelMathType, RetentionMathType, ...   (NEW — type aliases)
```

### 2.3 Shared vs. Report-Specific

| Component | Shared | Insights | Funnels | Retention | Flows |
|-----------|--------|----------|---------|-----------|-------|
| `Filter` type | Yes | Yes | Yes | Yes | Yes (via `_build_segfilter_entry()`)* |
| `GroupBy` type | Yes | Yes | Yes | Yes | No** |
| Time range handling | Yes | Yes | Yes | Yes | Different format*** |
| `_build_filter_entry()` | Yes | Yes | Yes (per-step) | Yes (per-event) | Via segfilter converter* |
| Two-layer validation | Yes | Yes | Yes | Yes | Yes |
| `BookmarkValidationError` | Yes | Yes | Yes | Yes | Yes |
| `validate_bookmark()` L2 | Partially | Yes | Extended | Extended | Separate |
| Bookmark JSON structure | `sections.*` | Yes | Yes | Yes | Flat (no sections) |
| API endpoint | — | `/insights` | `/insights` | `/insights` | `/arb_funnels` |
| Auth | Yes | Basic/OAuth | Basic/OAuth | Basic/OAuth | Basic/OAuth |

\* Flows use legacy `property_filter_params_list` (segfilter format) per step. A `_build_segfilter_entry()` converter translates `Filter` objects to segfilter format (~100 lines).
\** Flows use `segments` and `group_by` at the top level, not `sections.group[]`.
\*** Flows use a flat `date_range` object, not `sections.time[]`.

---

## 3. Funnels: `query_funnel()`

### 3.1 Method Signature

```python
def query_funnel(
    self,
    steps: Sequence[str | FunnelStep],
    *,
    # Conversion window
    conversion_window: int = 14,
    conversion_window_unit: Literal["second", "minute", "hour", "day", "week", "month", "session"] = "day",

    # Funnel ordering
    order: Literal["loose", "any"] = "loose",

    # Time range (shared pattern)
    from_date: str | None = None,
    to_date: str | None = None,
    last: int = 30,
    unit: Literal["hour", "day", "week", "month", "quarter"] = "day",

    # Aggregation
    math: FunnelMathType = "conversion_rate_unique",

    # Breakdown (shared)
    group_by: str | GroupBy | list[str | GroupBy] | None = None,

    # Filters (shared — global)
    where: Filter | list[Filter] | None = None,

    # Exclusions
    exclusions: list[str | Exclusion] | None = None,

    # Hold property constant
    holding_constant: str | HoldingConstant | list[str | HoldingConstant] | None = None,

    # Result shape
    mode: Literal["steps", "trends", "table"] = "steps",
) -> FunnelQueryResult:
```

### 3.2 `FunnelStep` Type

```python
@dataclass(frozen=True)
class FunnelStep:
    """A single step in a funnel query.

    Use plain event name strings when no per-step configuration is needed.
    Use FunnelStep for per-step filters, custom labels, or any-order control.

    Attributes:
        event: Mixpanel event name.
        label: Display label for this step (defaults to event name).
        filters: Per-step filters.
        filters_combinator: How per-step filters combine ("all"=AND, "any"=OR).
        order: Per-step ordering override for any-order funnels.
            Only meaningful when the funnel's top-level order="any".

    Example:
        ```python
        FunnelStep("Sign Up")
        FunnelStep("Purchase", label="First Purchase",
                   filters=[Filter.greater_than("amount", 50)])
        ```
    """

    event: str
    label: str | None = None
    filters: list[Filter] | None = None
    filters_combinator: Literal["all", "any"] = "all"
    order: Literal["loose", "any"] | None = None
```

### 3.3 `FunnelMathType`

```python
FunnelMathType = Literal[
    # Conversion rates (most common)
    "conversion_rate_unique",   # Unique users conversion rate (default)
    "conversion_rate_total",    # Total events conversion rate
    "conversion_rate_session",  # Session-based conversion rate

    # Raw counts
    "unique",                   # Unique users at each step
    "total",                    # Total events at each step

    # Property aggregation (requires holding_constant or group_by on property)
    "average", "median", "min", "max",
    "p25", "p75", "p90", "p99",
]
```

### 3.4 `FunnelQueryResult`

```python
@dataclass(frozen=True)
class FunnelQueryResult(ResultWithDataFrame):
    """Result of a funnel query.

    Contains step-level conversion data with timing and statistical
    significance information.

    Attributes:
        computed_at: When the query was computed (ISO format).
        from_date: Effective start date.
        to_date: Effective end date.
        steps_data: List of step-level results. Each entry is a dict with:
            count, step_conv_ratio, overall_conv_ratio,
            avg_time (seconds from previous step),
            avg_time_from_start (seconds from step 1).
        series: Raw series data from API (for advanced use).
        params: Generated bookmark params (for debugging/persistence).
        meta: Response metadata.
    """

    computed_at: str
    from_date: str
    to_date: str
    steps_data: list[dict[str, Any]] = field(default_factory=list)
    series: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def overall_conversion_rate(self) -> float:
        """End-to-end conversion rate (step 1 to last step)."""
        if not self.steps_data:
            return 0.0
        return self.steps_data[-1].get("overall_conv_ratio", 0.0)

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame.

        Columns: step, event, count, step_conv_ratio, overall_conv_ratio,
                 avg_time, avg_time_from_start.
        One row per funnel step.
        """
        ...
```

### 3.2b `Exclusion` Type

```python
@dataclass(frozen=True)
class Exclusion:
    """An event to exclude between funnel steps.

    Use plain event name strings to exclude between ALL steps.
    Use Exclusion for step-range targeting.

    Attributes:
        event: Event name to exclude.
        from_step: Start of exclusion range (0-indexed). Default: 0.
        to_step: End of exclusion range (0-indexed).
            Default: None (= last step).

    Example:
        ```python
        # Exclude Logout between all steps
        exclusions=["Logout"]

        # Exclude Refund only between steps 2 and 3
        exclusions=[Exclusion("Refund", from_step=2, to_step=3)]
        ```
    """

    event: str
    from_step: int = 0
    to_step: int | None = None
```

### 3.2c `HoldingConstant` Type

```python
@dataclass(frozen=True)
class HoldingConstant:
    """A property to hold constant across funnel steps.

    Use plain property name strings for event properties (the common case).
    Use HoldingConstant for user-property HPC.

    Attributes:
        property: Property name to hold constant.
        resource_type: Resource type. Default: "events".

    Example:
        ```python
        # Hold platform constant (event property)
        holding_constant="platform"

        # Hold plan constant (user property)
        holding_constant=HoldingConstant("plan", resource_type="people")
        ```
    """

    property: str
    resource_type: Literal["events", "people"] = "events"
```

### 3.5 Bookmark JSON Mapping

```python
# query_funnel(["Signup", "Purchase"], conversion_window=7, math="conversion_rate_unique")
# generates:
{
    "sections": {
        "show": [{
            "behavior": {
                "type": "funnel",
                "name": None,
                "resourceType": "events",
                "dataGroupId": None,
                "filters": [],
                "behaviors": [
                    {"id": None, "type": "event", "name": "Signup",
                     "filters": [], "filtersDeterminer": "all", "funnelOrder": "loose"},
                    {"id": None, "type": "event", "name": "Purchase",
                     "filters": [], "filtersDeterminer": "all", "funnelOrder": "loose"},
                ],
                "conversionWindowDuration": 7,
                "conversionWindowUnit": "day",
                "funnelOrder": "loose",
                "exclusions": [],
                "aggregateBy": [],
                "dataset": "$mixpanel",
                "profileType": None,
                "search": "",
            },
            "measurement": {
                "math": "conversion_rate_unique",
                "stepIndex": None,
                "property": None,
                "perUserAggregation": None,
            },
        }],
        "filter": [],
        "group": [],
        "time": [{"dateRangeType": "in the last", "unit": "day",
                  "window": {"unit": "day", "value": 30}}],
        "formula": [],
    },
    "displayOptions": {
        "chartType": "funnel-steps",
        "analysis": "linear",
    },
}
```

### 3.6 Execution Path

Funnel bookmarks with `sections.show[].behavior.type == "funnel"` are POSTed to the same `/api/query/insights` endpoint as insights bookmarks. The Mixpanel insights API internally detects the funnel behavior type (at `api.py:1248`) and delegates to `funnels_query` (the `arb_funnels` service). The response is then converted back to the insights result format.

This means we can reuse the existing `insights_query()` API client method. The only difference is the bookmark params structure and the response parsing.

### 3.7 Validation Rules (Layer 1)

| Code | Rule | Message |
|------|------|---------|
| F1 | At least 2 steps required | `funnel requires at least 2 steps (got {n})` |
| F2 | Each step event must be non-empty | `step[{i}] event name must be non-empty` |
| F3 | conversion_window must be positive | `conversion_window must be positive` |
| F4 | exclusions must reference valid event names | `exclusion '{name}' is not in the funnel steps` |
| F5 | Shared time range rules (V7-V11 from insights) | Reuse existing validation |
| F6 | Shared GroupBy rules (V11-V12 from insights) | Reuse existing validation |

### 3.8 Example Calls

```python
# Simplest funnel
result = ws.query_funnel(["Signup", "Purchase"])

# With conversion window and ordering
result = ws.query_funnel(
    ["Signup", "Add to Cart", "Checkout", "Purchase"],
    conversion_window=7,
    conversion_window_unit="day",
    order="loose",
)

# With per-step filters
result = ws.query_funnel([
    FunnelStep("Signup"),
    FunnelStep("Purchase", filters=[Filter.greater_than("amount", 50)]),
])

# Trends view (conversion over time)
result = ws.query_funnel(
    ["Signup", "Purchase"],
    mode="trends",
    unit="week",
    last=90,
)

# Segmented funnel
result = ws.query_funnel(
    ["Signup", "Purchase"],
    group_by="platform",
    where=[Filter.equals("country", "US")],
)

# Debug / persist
print(result.params)
ws.create_bookmark(CreateBookmarkParams(
    name="Signup → Purchase Funnel",
    bookmark_type="funnels",
    params=result.params,
))
```

---

## 4. Retention: `query_retention()`

### 4.1 Method Signature

```python
def query_retention(
    self,
    born_event: str | RetentionEvent,
    return_event: str | RetentionEvent,
    *,
    # Retention configuration
    retention_unit: Literal["day", "week", "month"] = "week",
    alignment: Literal["birth", "interval_start"] = "birth",
    bucket_sizes: list[int] | None = None,

    # Time range (shared pattern)
    from_date: str | None = None,
    to_date: str | None = None,
    last: int = 30,
    unit: Literal["hour", "day", "week", "month", "quarter"] = "day",

    # Aggregation
    math: RetentionMathType = "retention_rate",

    # Breakdown (shared)
    group_by: str | GroupBy | list[str | GroupBy] | None = None,

    # Filters (shared — global)
    where: Filter | list[Filter] | None = None,

    # Result shape
    mode: Literal["curve", "trends", "table"] = "curve",
) -> RetentionQueryResult:
```

### 4.2 `RetentionEvent` Type

```python
@dataclass(frozen=True)
class RetentionEvent:
    """An event specification for a retention query.

    Use plain event name strings for simple cases.
    Use RetentionEvent for per-event filters.

    Attributes:
        event: Mixpanel event name.
        filters: Per-event filters.
        filters_combinator: How filters combine ("all"=AND, "any"=OR).

    Example:
        ```python
        RetentionEvent("Login")
        RetentionEvent("Login", filters=[Filter.equals("platform", "iOS")])
        ```
    """

    event: str
    filters: list[Filter] | None = None
    filters_combinator: Literal["all", "any"] = "all"
```

### 4.3 `RetentionMathType`

```python
RetentionMathType = Literal[
    "retention_rate",   # Percentage retained (default)
    "unique",           # Unique users per cohort/bucket
]
```

### 4.4 `RetentionQueryResult`

```python
@dataclass(frozen=True)
class RetentionQueryResult(ResultWithDataFrame):
    """Result of a retention query.

    Contains cohort-level retention data with rates per bucket.

    Attributes:
        computed_at: When the query was computed (ISO format).
        from_date: Effective start date.
        to_date: Effective end date.
        cohorts: Dict mapping cohort date → {first, counts, rates}.
            ``first``: cohort size (users who did born_event).
            ``counts``: list of user counts per retention bucket.
            ``rates``: list of retention rates per bucket (count/first).
        average: The ``$average`` synthetic cohort aggregating all cohorts.
        params: Generated bookmark params (for debugging/persistence).
        meta: Response metadata (incomplete_buckets, etc.).
    """

    computed_at: str
    from_date: str
    to_date: str
    cohorts: dict[str, dict[str, Any]] = field(default_factory=dict)
    average: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame.

        Columns: cohort_date, bucket, count, rate.
        One row per (cohort, retention bucket) pair.
        """
        ...
```

### 4.5 Bookmark JSON Mapping

```python
# query_retention("Signup", "Login", retention_unit="week")
# generates:
{
    "sections": {
        "show": [{
            "behavior": {
                "type": "retention",
                "resourceType": "events",
                "behaviors": [
                    {"type": "event", "name": "Signup",
                     "filters": [], "filtersDeterminer": "all"},
                    {"type": "event", "name": "Login",
                     "filters": [], "filtersDeterminer": "all"},
                ],
                "retentionUnit": "week",
                "retentionCustomBucketSizes": [],
                "retentionAlignmentType": "birth",
                "retentionUnboundedMode": None,
                "dataGroupId": None,
            },
            "measurement": {
                "math": "retention_rate",
                "retentionBucketIndex": 0,
                "retentionSegmentationEvent": None,
            },
        }],
        "filter": [],
        "group": [],
        "time": [{"dateRangeType": "in the last", "unit": "day",
                  "window": {"unit": "day", "value": 30}}],
        "formula": [],
    },
    "displayOptions": {
        "chartType": "retention-curve",
    },
}
```

### 4.6 Execution Path

Retention bookmarks with `sections.show[].behavior.type == "retention"` are also POSTed to `/api/query/insights`. The insights API detects the retention behavior type (at `api.py:2946`) and delegates to `retention_query` (the retention service). The response flows back through the insights result formatter.

Same as funnels: reuse `insights_query()` API client, different params structure, different response parsing.

### 4.7 Validation Rules (Layer 1)

| Code | Rule | Message |
|------|------|---------|
| R1 | born_event must be non-empty | `born_event must be a non-empty string` |
| R2 | return_event must be non-empty | `return_event must be a non-empty string` |
| R3 | Shared time range rules (V7-V11) | Reuse existing validation |
| R4 | Shared GroupBy rules (V11-V12) | Reuse existing validation |
| R5 | bucket_sizes must be positive integers | `bucket_sizes values must be positive integers` |
| R6 | bucket_sizes must be in ascending order | `bucket_sizes must be in ascending order` |

### 4.8 Example Calls

```python
# Simplest retention
result = ws.query_retention("Signup", "Login")

# Weekly retention with 90-day window
result = ws.query_retention(
    "Signup", "Login",
    retention_unit="week",
    last=90,
)

# With per-event filters
result = ws.query_retention(
    RetentionEvent("Signup", filters=[Filter.equals("source", "organic")]),
    RetentionEvent("Login"),
    retention_unit="day",
)

# Segmented retention
result = ws.query_retention(
    "Signup", "Purchase",
    group_by="platform",
    retention_unit="week",
)

# Trends view (retention over time)
result = ws.query_retention(
    "Signup", "Login",
    mode="trends",
    unit="week",
    last=90,
)

# Custom non-uniform retention buckets
result = ws.query_retention(
    "Signup", "Login",
    retention_unit="day",
    bucket_sizes=[1, 3, 7, 14, 30],
)

# Inspect the cohort data
print(result.average)         # Average retention across cohorts
print(result.cohorts.keys())  # Cohort dates
print(result.df.head())       # Tabular view
```

---

## 5. Flows: `query_flow()`

### 5.1 The Flows Difference

Flows bookmarks are fundamentally different from insights/funnels/retention:

1. **Flat structure** — No `sections` wrapper. All fields are top-level.
2. **Different endpoint** — Uses `/arb_funnels` with `query_type=flows_sankey` or `flows_top_paths`, not `/insights`.
3. **Step semantics** — Steps define an "anchor" event with `forward` (steps after) and `reverse` (steps before) counts, not a sequential funnel.
4. **Filter format** — Uses legacy `property_filter_params_list` (segfilter format), not the `sections.filter[]` structured format.
5. **Response structure** — Returns a node/edge graph, not time-series or step-array data.

Because of these differences, `query_flow()` builds a flat params dict (not `sections`-based) and uses a separate API path.

### 5.2 Method Signature

```python
def query_flow(
    self,
    event: str | FlowStep | Sequence[str | FlowStep],
    *,
    # Flow configuration
    forward: int = 3,
    reverse: int = 0,

    # Time range
    from_date: str | None = None,
    to_date: str | None = None,
    last: int = 30,

    # Conversion window
    conversion_window: int = 7,
    conversion_window_unit: Literal["day", "week", "month"] = "day",

    # Counting
    count_type: Literal["unique", "total", "session"] = "unique",

    # Flow settings
    cardinality: int = 3,
    collapse_repeated: bool = False,
    hidden_events: list[str] | None = None,

    # Result shape
    mode: Literal["sankey", "paths"] = "sankey",
) -> FlowQueryResult:
```

### 5.3 `FlowStep` Type

```python
@dataclass(frozen=True)
class FlowStep:
    """An anchor step for a flow query.

    Use plain event name strings for simple flows (single anchor event
    with top-level forward/reverse counts). Use FlowStep for per-step
    forward/reverse control or per-step filters.

    Attributes:
        event: Mixpanel event name.
        forward: Number of steps to show after this event (0-5).
        reverse: Number of steps to show before this event (0-5).
        label: Display label for this step.

    Example:
        ```python
        FlowStep("Purchase", forward=3, reverse=2)
        FlowStep("Checkout", forward=0, reverse=3, label="Checkout Flow")
        ```
    """

    event: str
    forward: int | None = None
    reverse: int | None = None
    label: str | None = None
    filters: list[Filter] | None = None
    filters_combinator: Literal["and", "or"] = "and"
```

### 5.4 `FlowQueryResult`

```python
@dataclass(frozen=True)
class FlowQueryResult(ResultWithDataFrame):
    """Result of an ad-hoc flow query.

    Contains node/edge graph data representing user paths.

    Attributes:
        computed_at: When the query was computed (ISO format).
        steps: Flow step data with nodes and edges.
        breakdowns: Path breakdown data.
        overall_conversion_rate: End-to-end flow conversion rate.
        params: Generated flows bookmark params (for debugging/persistence).
        meta: Response metadata (sampling factor, etc.).
    """

    computed_at: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    breakdowns: list[dict[str, Any]] = field(default_factory=list)
    overall_conversion_rate: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def df(self) -> pd.DataFrame:
        """Convert flow steps to DataFrame.

        Flattens the node/edge graph into rows with columns:
        step_index, event, count, edges (list of next events).
        """
        ...
```

### 5.5 Bookmark JSON Mapping

Flows use a flat structure — no `sections` wrapper:

```python
# query_flow("Purchase", forward=3, reverse=2)
# generates:
{
    "steps": [
        {"event": "Purchase", "step_label": "Purchase",
         "forward": 3, "reverse": 2,
         "bool_op": "and", "property_filter_params_list": []},
    ],
    "date_range": {
        "type": "in the last",
        "from_date": {"unit": "day", "value": 30},
        "to_date": "$now",
    },
    "chartType": "sankey",
    "flows_merge_type": "graph",
    "count_type": "unique",
    "cardinality_threshold": 3,
    "version": 2,
    "conversion_window": {"unit": "day", "value": 7},
    "anchor_position": 1,
    "collapse_repeated": False,
    "show_custom_events": True,
    "hidden_events": [],
    "exclusions": [],
}
```

### 5.6 Execution Path

Flows queries use the `/arb_funnels` endpoint with inline bookmark params — confirmed working via source code analysis (`FunnelMetricParams.get_bookmark_from_params()` at `funnel_metric_params.py:674` checks for inline `bookmark` dict before `bookmark_id`).

**Request format**:
```python
POST /api/2.0/arb_funnels
{
    "bookmark": flows_params_dict,        # flat flows bookmark (no sections wrapper)
    "project_id": project_id,
    "query_type": "flows_sankey",         # or "flows_top_paths" for paths mode
}
```

A new `arb_funnels_query()` method on `MixpanelAPIClient` handles this POST. The existing `query_flows()` API client method (GET with `bookmark_id`) remains for querying saved flows reports.

### 5.7 Validation Rules (Layer 1)

| Code | Rule | Message |
|------|------|---------|
| FL1 | At least one event/step required | `flow requires at least one event` |
| FL2 | Each step event must be non-empty | `step[{i}] event name must be non-empty` |
| FL3 | forward must be 0-5 | `forward must be between 0 and 5` |
| FL4 | reverse must be 0-5 | `reverse must be between 0 and 5` |
| FL5 | forward + reverse must be > 0 | `flow step must have at least one forward or reverse step` |
| FL6 | cardinality must be 1-50 | `cardinality must be between 1 and 50` |
| FL7 | conversion_window must be positive | `conversion_window must be positive` |
| FL8 | last must be positive | Reuse existing V7 |

### 5.8 Example Calls

```python
# Simplest flow — what happens after Purchase?
result = ws.query_flow("Purchase", forward=3)

# What happens before AND after Purchase?
result = ws.query_flow("Purchase", forward=3, reverse=2)

# With conversion window and counting
result = ws.query_flow(
    "Add to Cart",
    forward=5,
    conversion_window=14,
    count_type="unique",
)

# Multiple anchor steps
result = ws.query_flow([
    FlowStep("Signup", forward=3, reverse=0),
    FlowStep("Purchase", forward=0, reverse=3),
])

# Hide noisy events
result = ws.query_flow(
    "Checkout",
    forward=3,
    hidden_events=["Page View", "Session Start"],
)

# Paths view (list of top paths instead of sankey graph)
result = ws.query_flow("Purchase", forward=3, mode="paths")
```

---

## 6. Infrastructure Reuse Plan

### 6.1 Shared Time Range Handling

All four methods use the same time range parameters: `from_date`, `to_date`, `last`, `unit`. The validation rules (V7-V11, V15, V20) are identical. The bookmark time section generation differs only in format:

- **Insights/Funnels/Retention**: `sections.time[{"dateRangeType": "...", ...}]`
- **Flows**: `date_range: {"type": "...", "from_date": {...}, "to_date": "$now"}`

Extract a shared `_build_time_section()` for sections-based reports and a separate `_build_date_range()` for flows.

### 6.2 Shared Filter Handling

`Filter` objects and `_build_filter_entry()` are reused for:
- **Global filters**: `sections.filter[]` (insights, funnels, retention)
- **Per-event/step filters**: `behavior.behaviors[].filters[]` (funnel steps, retention events)
- **Flows step filters**: Converted to `property_filter_params_list` via `_build_segfilter_entry()`

A `_build_segfilter_entry(f: Filter) -> dict` converter (~100 lines) translates `Filter` objects to the legacy segfilter format used by flows steps. Key mappings:

| Aspect | Bookmark filter (`_build_filter_entry`) | Segfilter (`_build_segfilter_entry`) |
|--------|----------------------------------------|--------------------------------------|
| Operator | Human-readable (`"equals"`) | Symbolic (`"=="`) |
| Property location | `value: "country"` | `property: {"name": "country", "source": "properties"}` |
| String equals value | `filterValue: ["US"]` | `filter.operand: ["US"]` |
| Number value | `filterValue: 50` | `filter.operand: "50"` (stringified) |
| Boolean | `filterOperator: "true"` | No operator field, `filter.operand: "true"` |
| Date format | `YYYY-MM-DD` | `MM/DD/YYYY` |
| Resource type | `resourceType: "events"` | `property.source: "properties"` |

**Reference implementations in `analytics/`:**

| File | What | Lines |
|------|------|-------|
| `iron/common/widgets/property-filter-menu/models/segfilter.ts` | Canonical TypeScript bidirectional converter. `toSegfilterFilter()` is the PropertyFilter→segfilter direction. | ~L403+ |
| `iron/common/widgets/property-filter-menu/models/__test__/segfilter.ts` | Round-trip test cases for every operator type — serves as the specification. | Full file |
| `iron/common/widgets/property-filter-menu/models/segfilter.ts` | `Segfilter` interface definition (`property`, `type`, `selected_property_type`, `filter`). | L110-115 |
| `iron/common/widgets/property-filter-menu/models/segfilter.ts` | `SegfilterFilter` interface (`operator`, `operand`, `segments`, `unit`). | L82-89 |
| `iron/common/widgets/property-filter-menu/models/segfilter.ts` | `Property` interface (`name`, `source`, `type`). | L91-101 |
| `bookmark_parser/common/segfilter/segfilter_to_property_filter.py` | Python segfilter→PropertyFilter converter (the reverse direction — useful for understanding field mappings). | Full file |
| `mixpanel_mcp/mcp_server/utils/reports/flows.py` | Existing (buggy) Python PropertyFilter→segfilter attempt: `convert_to_property_filter_params()`. Known bugs: wrong `"is set"` mapping, wrong `"contains"` mapping, no type-aware operand shaping. | L73-143 |
| `iron/common/report/funnels/models/types.ts` | `BookmarkBaseStep` + `PropertyFilterParams` types defining the step structure that contains `property_filter_params_list`. | L17-55 |

### 6.3 Shared GroupBy Handling

`GroupBy` objects and the group section builder are reused identically for insights, funnels, and retention. All three write to `sections.group[]`. Flows do not use `sections.group[]` — they have a top-level `group_by` array with a different format.

For v1, flows `group_by` is not exposed (it's complex and flows-specific). Users who need segmented flows can use `create_bookmark()` + `query_flows()`.

### 6.4 Shared Validation Infrastructure

The two-layer validation pattern is reused across all report types:

```python
# Layer 1: Argument validation (report-specific)
errors = validate_funnel_args(steps=..., math=..., ...)  # NEW
errors = validate_retention_args(born_event=..., ...)     # NEW
errors = validate_flow_args(event=..., forward=..., ...)  # NEW

# Layer 2: Bookmark structure validation (shared, extended)
errors = validate_bookmark(params, bookmark_type="funnels")    # EXTENDED
errors = validate_bookmark(params, bookmark_type="retention")  # EXTENDED
# Flows: separate flat-bookmark validator
errors = validate_flow_bookmark(params)                        # NEW
```

The `bookmark_type` parameter on `validate_bookmark()` is already present but unused — it was designed for exactly this extension. The validator will use `bookmark_type` to select the correct valid math types (VALID_MATH_FUNNELS, VALID_MATH_RETENTION) and validate behavior-type-specific fields.

### 6.5 Shared `build_*_params()` Pattern

Each report type gets a public `build_*_params()` method that mirrors `build_params()`:

```python
ws.build_funnel_params(["Signup", "Purchase"])      # → dict
ws.build_retention_params("Signup", "Login")         # → dict
ws.build_flow_params("Purchase", forward=3)          # → dict
```

These enable:
- **Debugging**: Inspect the generated bookmark JSON
- **Persistence**: Pass to `create_bookmark()` to save as a report
- **Testing**: Verify params without credentials or API access

---

## 7. Response Format Differences

### 7.1 How Each Report Type Responds

| Report | Endpoint | Response Shape | Key Fields |
|--------|----------|---------------|------------|
| Insights | `/insights` | `{computed_at, date_range, headers, series, meta}` | `series: {metric_name: {date: value}}` |
| Funnels | `/insights` (delegates to arb) | Same wrapper, but `series` contains step data | Step arrays with `count`, `step_conv_ratio`, `overall_conv_ratio`, `avg_time` |
| Retention | `/insights` (delegates to retention) | Same wrapper, but `series` contains cohort data | Cohort dicts with `first`, `counts[]`, `rates[]` |
| Flows | `/arb_funnels` | `{computed_at, steps, breakdowns, overallConversionRate, metadata}` | `steps[].nodes[].edges[]` graph structure |

### 7.2 DataFrame Shapes

| Report | DataFrame Columns | Rows |
|--------|-------------------|------|
| Insights (timeseries) | `date, event, count` | One per (date, metric) |
| Insights (total) | `event, count` | One per metric |
| Funnels (steps) | `step, event, count, step_conv_ratio, overall_conv_ratio, avg_time` | One per step |
| Funnels (trends) | `date, event, count` | One per (date, step) — like insights |
| Retention (curve) | `cohort_date, bucket, count, rate` | One per (cohort, bucket) |
| Retention (trends) | `date, event, count` | Like insights |
| Flows | `step_index, event, type, count` | One per node |

---

## 8. Phased Implementation Plan

### Phase 1: Shared Infrastructure Extraction

Extract shared components from the existing `query()` pipeline:
- `_build_time_section()` — shared time clause builder for sections-based reports
- `_build_date_range()` — flows-specific flat date range builder
- `_build_segfilter_entry()` — `Filter` → segfilter converter (~100 lines)
- `_validate_time_args()` — extracted from `validate_query_args()`
- `_validate_group_by_args()` — extracted from `validate_query_args()`
- Extend `bookmark_enums.py` with funnel/retention/flows-specific constants

### Phase 2: Funnels (`query_funnel()`)

- `FunnelStep` and `FunnelQueryResult` types
- `validate_funnel_args()` — Layer 1 validation
- `_build_funnel_params()` — bookmark JSON builder
- `build_funnel_params()` — public params helper
- `query_funnel()` — public method
- `_transform_funnel_result()` — response parser
- Extend `validate_bookmark()` for funnel structure (L2)

### Phase 3: Retention (`query_retention()`)

- `RetentionEvent` and `RetentionQueryResult` types
- `validate_retention_args()` — Layer 1 validation
- `_build_retention_params()` — bookmark JSON builder
- `build_retention_params()` — public params helper
- `query_retention()` — public method
- `_transform_retention_result()` — response parser
- Extend `validate_bookmark()` for retention structure (L2)

### Phase 4: Flows (`query_flow()`)

- `FlowStep` and `FlowQueryResult` types
- `validate_flow_args()` — Layer 1 validation
- `_build_flow_params()` — flat bookmark builder (uses `_build_segfilter_entry()` for per-step filters)
- `validate_flow_bookmark()` — separate L2 for flat structure
- `build_flow_params()` — public params helper
- `query_flow()` — public method
- `arb_funnels_query()` — new API client method (POST with inline `bookmark` + `query_type`)
- `_transform_flow_result()` — response parser

### Phase 5: Polish

- Property-based tests (Hypothesis) for all new types
- Mutation testing on new validation rules
- Documentation: docstrings, quickstart examples
- Exports in `__init__.py`

---

## 9. Resolved Design Decisions

All design questions were resolved through source code analysis and collaborative discussion.

### 9.1 Flows Inline Params → **Inline POST to `/arb_funnels`**

`/arb_funnels` accepts an inline `bookmark` dict in the POST body. Confirmed via `FunnelMetricParams.get_bookmark_from_params()` at `funnel_metric_params.py:674` — inline `bookmark` is checked before `bookmark_id`. Single API call, no transient state.

Request body: `{"bookmark": flows_params, "project_id": id, "query_type": "flows_sankey"}`.

### 9.2 Flows Per-Step Filters → **Build `Filter` → segfilter converter in v1**

A `_build_segfilter_entry()` converter (~100 lines) translates `Filter` objects to the legacy segfilter format. The conversion is well-specified by the TypeScript reference implementation (`segfilter.ts:toSegfilterFilter`) with round-trip tests. Key structural differences: symbolic operators (`"=="` vs `"equals"`), stringified numbers, MM/DD/YYYY dates, `source: "properties"` vs `resourceType: "events"`.

`FlowStep` accepts `filters: list[Filter] | None` and `filters_combinator: Literal["and", "or"]`.

### 9.3 Funnel Exclusions → **Typed `exclusions: list[str | Exclusion]`**

Plain strings exclude between ALL steps (common case). `Exclusion(event, from_step=0, to_step=None)` enables step-range targeting. Maps to bookmark `behavior.exclusions[]` with `steps: {"from": N, "to": M}`.

### 9.4 Funnel Hold Property Constant → **Typed `holding_constant: str | HoldingConstant | list[...]`**

Plain strings hold event properties constant (common case). `HoldingConstant(property, resource_type="events")` enables user-property HPC. Maps to bookmark `behavior.aggregateBy[]`.

### 9.5 Retention Custom Bucket Sizes → **Include `bucket_sizes: list[int] | None` in v1**

Optional parameter for non-uniform retention periods (e.g., `[1, 3, 7, 14, 30]`). Maps directly to `retentionCustomBucketSizes`. Validation: positive integers in ascending order. `None` (default) = uniform buckets via `retention_unit`.

---

## 10. Summary: API Surface

### New Public Types

| Type | Purpose |
|------|---------|
| `FunnelStep` | Funnel step with optional label, per-step filters, and ordering |
| `Exclusion` | Funnel step exclusion with optional step-range targeting |
| `HoldingConstant` | Hold-property-constant with resource type control |
| `FunnelMathType` | Literal for funnel math types |
| `FunnelQueryResult` | Funnel result with step data and conversion rates |
| `RetentionEvent` | Retention event with optional per-event filters |
| `RetentionMathType` | Literal for retention math types |
| `RetentionQueryResult` | Retention result with cohort data and rates |
| `FlowStep` | Flow anchor step with forward/reverse counts and per-step filters |
| `FlowQueryResult` | Flow result with node/edge graph data |

### New Public Methods

| Method | Minimum Call | Returns |
|--------|-------------|---------|
| `query_funnel(steps)` | `ws.query_funnel(["Signup", "Purchase"])` | `FunnelQueryResult` |
| `query_retention(born, return)` | `ws.query_retention("Signup", "Login")` | `RetentionQueryResult` |
| `query_flow(event)` | `ws.query_flow("Purchase", forward=3)` | `FlowQueryResult` |
| `build_funnel_params(steps)` | `ws.build_funnel_params(["Signup", "Purchase"])` | `dict` |
| `build_retention_params(born, return)` | `ws.build_retention_params("Signup", "Login")` | `dict` |
| `build_flow_params(event)` | `ws.build_flow_params("Purchase", forward=3)` | `dict` |

### Reused Types (from existing `query()`)

`Filter`, `GroupBy`, `Formula`, `BookmarkValidationError`, `ValidationError`, `FilterDateUnit`, `FilterPropertyType`

### New Internal Components

| Component | Purpose |
|-----------|---------|
| `_build_segfilter_entry()` | Convert `Filter` → segfilter format for flows steps (~100 lines) |
| `_build_time_section()` | Shared time clause builder for sections-based reports |
| `_build_date_range()` | Flows-specific flat date range builder |
| `validate_funnel_args()` | Layer 1 funnel validation (F1-F6) |
| `validate_retention_args()` | Layer 1 retention validation (R1-R6) |
| `validate_flow_args()` | Layer 1 flow validation (FL1-FL8) |
| `validate_flow_bookmark()` | Layer 2 for flat flows structure |
| `arb_funnels_query()` | API client: POST to `/arb_funnels` with inline params |

---

## Appendix A: Canonical Bookmark JSON Reference

### A.1 Insights Behavior (`behavior.type: "event"`)

```json
{
  "type": "event",
  "name": "Login",
  "resourceType": "events",
  "filtersDeterminer": "all",
  "filters": []
}
```

### A.2 Funnel Behavior (`behavior.type: "funnel"`)

```json
{
  "type": "funnel",
  "name": null,
  "resourceType": "events",
  "dataGroupId": null,
  "filters": [],
  "behaviors": [
    {"id": null, "type": "event", "name": "Signup",
     "filters": [], "filtersDeterminer": "all", "funnelOrder": "loose"},
    {"id": null, "type": "event", "name": "Purchase",
     "filters": [], "filtersDeterminer": "all", "funnelOrder": "loose"}
  ],
  "conversionWindowDuration": 14,
  "conversionWindowUnit": "day",
  "funnelOrder": "loose",
  "exclusions": [],
  "aggregateBy": [],
  "dataset": "$mixpanel",
  "profileType": null,
  "search": ""
}
```

### A.3 Retention Behavior (`behavior.type: "retention"`)

```json
{
  "type": "retention",
  "resourceType": "events",
  "dataGroupId": null,
  "behaviors": [
    {"type": "event", "name": "Signup",
     "filters": [], "filtersDeterminer": "all"},
    {"type": "event", "name": "Login",
     "filters": [], "filtersDeterminer": "all"}
  ],
  "retentionUnit": "week",
  "retentionCustomBucketSizes": [],
  "retentionAlignmentType": "birth",
  "retentionUnboundedMode": null
}
```

### A.4 Flows Bookmark (flat — no sections)

```json
{
  "steps": [
    {"event": "Purchase", "step_label": "Purchase",
     "forward": 3, "reverse": 2,
     "bool_op": "and", "property_filter_params_list": []}
  ],
  "date_range": {
    "type": "in the last",
    "from_date": {"unit": "day", "value": 30},
    "to_date": "$now"
  },
  "chartType": "sankey",
  "flows_merge_type": "graph",
  "count_type": "unique",
  "cardinality_threshold": 3,
  "version": 2,
  "conversion_window": {"unit": "day", "value": 7},
  "anchor_position": 1,
  "collapse_repeated": false,
  "show_custom_events": true,
  "hidden_events": [],
  "exclusions": []
}
```

### A.5 Measurement Block Differences

| Report | measurement.math | Extra Fields |
|--------|-----------------|-------------|
| Insights | `total`, `unique`, `dau`, `average`, etc. | `property`, `perUserAggregation`, `percentile` |
| Funnels | `conversion_rate_unique`, `unique`, `total`, etc. | `stepIndex`, `actionMode`, `actionStep` |
| Retention | `retention_rate`, `unique` | `retentionBucketIndex`, `retentionSegmentationEvent` |
| Flows | N/A (top-level `count_type`) | N/A |

### A.6 DisplayOptions Differences

| Report | chartType Values | Extra Fields |
|--------|-----------------|-------------|
| Insights | `line`, `bar`, `table`, `pie`, `insights-metric` | `analysis`, `rollingWindowSize` |
| Funnels | `funnel-steps`, `funnel-top-paths`, `line`, `bar`, `table` | `funnelStepsSelectedTableColumns`, `statSigControl` |
| Retention | `retention-curve`, `line`, `bar`, `table` | `selected_segments`, `expanded_segments` |
| Flows | N/A (top-level `chartType`) | N/A |
