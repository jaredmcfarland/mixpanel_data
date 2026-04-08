# Python API Reference — Complete Workspace Methods

Full method signatures for `mixpanel_data.Workspace`, organized by domain. Every method listed here is callable on a `Workspace` instance. Use `help.py` for live docstrings with parameter descriptions.

## Construction

```python
import mixpanel_data as mp

ws = mp.Workspace()                              # default account
ws = mp.Workspace(account="prod")                # named account (v1 config)
ws = mp.Workspace(credential="prod")             # named credential (v2 config)
ws = mp.Workspace(workspace_id=12345)            # with workspace for App API
ws = mp.Workspace(project_id="67890", region="eu") # explicit project — project_id is a STRING
```

**Gotcha**: `project_id` must be a **string**, not an int. `Workspace(project_id=8)` raises `ValidationError`.

**v1 vs v2 config**: `account=` uses v1 account-based config. `credential=` uses v2 credential-based config (decoupled auth identity from project context). Both work — v2 enables project switching without reconfiguring auth. Migrate with `ConfigManager().migrate_v1_to_v2()`.

## Discovery

```python
ws.events() -> list[str]
ws.properties(event: str) -> list[str]
ws.property_values(property_name: str, *, event: str | None = None, limit: int = 100) -> list[str]
ws.top_events(*, type: Literal["general","average","unique"] = "general", limit: int | None = None) -> list[TopEvent]
ws.funnels() -> list[FunnelInfo]
ws.cohorts() -> list[SavedCohort]
ws.list_bookmarks(bookmark_type: BookmarkType | None = None) -> list[BookmarkInfo]
ws.lexicon_schemas() -> list[LexiconSchema]
ws.lexicon_schema(entity_type: EntityType, name: str) -> LexiconSchema
ws.clear_discovery_cache() -> None
```

## Typed Query API — Insights (Primary)

`Workspace.query()` generates valid Mixpanel insights bookmark params from keyword arguments, with two-layer validation (45 rules). Prefer this over legacy segmentation/event_counts methods for all insights-style queries.

_For complete parameter documentation with examples and pitfalls, see [insights-reference.md](insights-reference.md)._

```python
ws.query(
    events: str | Metric | CohortMetric | Formula | Sequence[str | Metric | CohortMetric | Formula],
    *,
    from_date: str | None = None,          # "YYYY-MM-DD"; mutually exclusive with `last`
    to_date: str | None = None,            # "YYYY-MM-DD"; defaults to today
    last: int = 30,                        # relative window in `unit`s; ignored if from_date set
    unit: Literal["hour", "day", "week", "month", "quarter"] = "day",
    math: MathType = "total",              # aggregate function
    math_property: str | None = None,      # required for average/median/min/max/p25/p75/p90/p99/percentile/histogram
    percentile_value: int | float | None = None,  # required when math="percentile" (e.g. 95)
    per_user: PerUserAggregation | None = None,  # nest per-user then aggregate
    group_by: str | GroupBy | CohortBreakdown | list[str | GroupBy | CohortBreakdown] | None = None,
    where: Filter | list[Filter] | None = None,
    formula: str | None = None,            # e.g. "(A / B) * 100"
    formula_label: str | None = None,
    rolling: int | None = None,            # rolling window size
    cumulative: bool = False,
    mode: Literal["timeseries", "total", "table"] = "timeseries",
) -> QueryResult
```

### Metric

```python
from mixpanel_data import Metric

Metric(
    event: str,                            # event name
    math: MathType = "total",
    math_property: str | None = None,
    per_user: PerUserAggregation | None = None,
    percentile_value: int | float | None = None,  # required when math="percentile"
    where: Filter | list[Filter] | None = None,
    label: str | None = None,              # display label
)
```

### Filter

```python
from mixpanel_data import Filter

Filter.equals(property, value, *, resource_type="events")
Filter.not_equals(property, value, *, resource_type="events")
Filter.contains(property, value, *, resource_type="events")
Filter.not_contains(property, value, *, resource_type="events")
Filter.greater_than(property, value, *, resource_type="events")
Filter.less_than(property, value, *, resource_type="events")
Filter.between(property, low, high, *, resource_type="events")
Filter.is_set(property, *, resource_type="events")
Filter.is_not_set(property, *, resource_type="events")
Filter.is_true(property, *, resource_type="events")
Filter.is_false(property, *, resource_type="events")

# Date/datetime filters
Filter.on(property, date, *, resource_type="events")                    # exact date (YYYY-MM-DD)
Filter.not_on(property, date, *, resource_type="events")                # not on date
Filter.before(property, date, *, resource_type="events")                # before date
Filter.since(property, date, *, resource_type="events")                 # on or after date
Filter.in_the_last(property, quantity, date_unit, *, resource_type="events")      # last N units
Filter.not_in_the_last(property, quantity, date_unit, *, resource_type="events")  # NOT in last N
Filter.date_between(property, from_date, to_date, *, resource_type="events")     # date range

# Cohort membership
Filter.in_cohort(cohort, name=None)       # cohort: int | CohortDefinition; works with all 4 engines via where=
Filter.not_in_cohort(cohort, name=None)   # excludes users in the cohort
```

`FilterDateUnit = Literal["hour", "day", "week", "month"]` — used by `in_the_last()` and `not_in_the_last()`.

### GroupBy

```python
from mixpanel_data import GroupBy

GroupBy(
    property: str,
    property_type: str = "string",         # "string", "number", "boolean", "datetime"
    bucket_size: int | None = None,        # numeric bucketing
    bucket_min: int | None = None,
    bucket_max: int | None = None,
)
```

### CohortBreakdown

```python
from mixpanel_data import CohortBreakdown

CohortBreakdown(
    cohort: int | CohortDefinition,      # saved cohort ID or inline definition
    name: str | None = None,             # display name (used as series label)
    include_negated: bool = True,         # include "Not In [name]" segment
)
```

Used in `group_by=` for `query()`, `query_funnel()`, and `query_retention()`. Not supported for `query_flow()`. Mixable with property `GroupBy` in insights and funnels. In retention, `CohortBreakdown` and property `GroupBy` are mutually exclusive (CB3).

```python
# Segment DAU by cohort membership
result = ws.query("Login", math="dau", group_by=CohortBreakdown(123, "Power Users"), last=30)

# Mix cohort + property breakdowns
result = ws.query("Login", group_by=[CohortBreakdown(123, "Power Users"), "platform"])
```

### CohortMetric

```python
from mixpanel_data import CohortMetric

CohortMetric(
    cohort: int | CohortDefinition,      # saved cohort ID or inline definition
    name: str | None = None,             # display name / series label
)
```

Used in `events=` for `query()` only (insights). Creates a `behavior.type: "cohort"` show clause tracking cohort size over time. Math is always `"unique"` (CM3). Cannot be used with `query_funnel()`, `query_retention()`, or `query_flow()` (CM4).

Inline `CohortDefinition` is supported. Always provide a `name` for the series label.

```python
# Track cohort size over time
result = ws.query(CohortMetric(123, "Power Users"), last=90)

# Power user percentage formula
result = ws.query(
    [Metric("Login", math="unique"), CohortMetric(123, "Power Users")],
    formula="(B / A) * 100", formula_label="Power User %",
)
```

### CohortDefinition and CohortCriteria

Build inline cohort definitions for use with `Filter.in_cohort()`, `CohortBreakdown`, and `CohortMetric`.

```python
from mixpanel_data import CohortDefinition, CohortCriteria

# Atomic criteria (factory methods)
CohortCriteria.did_event(event, *, at_least=None, within_days=None)
CohortCriteria.has_property(property, value, *, operator="equals")
CohortCriteria.in_cohort(cohort_id)
CohortCriteria.not_in_cohort(cohort_id)

# Combining with logic
CohortDefinition.all_of(*criteria)    # AND
CohortDefinition.any_of(*criteria)    # OR
CohortDefinition(*criteria)           # shorthand for all_of

# Serialization
definition.to_dict()  # -> {"selector": {...}, "behaviors": {...}}
```

```python
# Compose an inline definition
premium_active = CohortDefinition.all_of(
    CohortCriteria.has_property("plan", "premium"),
    CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
)

# Use in any cohort capability
result = ws.query("Login", where=Filter.in_cohort(premium_active, "Premium Active"), last=30)
result = ws.query("Login", group_by=CohortBreakdown(premium_active, "Premium Active"))
```

### Formula

```python
from mixpanel_data import Formula

Formula(
    expression: str,                       # e.g. "(A / B) * 100"; letters A-Z reference events by position
    label: str | None = None,
)
```

### QueryResult

```python
result = ws.query("Login", math="dau", last=30)

result.df          # pandas DataFrame (lazy cached); timeseries columns: date, event, count; total columns: event, count
result.params      # dict — generated bookmark params JSON (pass to create_bookmark)
result.series      # raw series data from API
result.meta        # response metadata
result.from_date   # resolved start date
result.to_date     # resolved end date
result.computed_at # API computation timestamp
```

### MathType

| Value | Meaning | Requires `math_property`? |
|-------|---------|--------------------------|
| `total` | Total event count | No (but if set, sums that property) |
| `unique` | Unique users | No |
| `dau` | Daily active users | No |
| `wau` | Weekly active users | No |
| `mau` | Monthly active users | No |
| `average` | Average of property | Yes |
| `median` | Median of property | Yes |
| `min` | Minimum of property | Yes |
| `max` | Maximum of property | Yes |
| `p25` | 25th percentile | Yes |
| `p75` | 75th percentile | Yes |
| `p90` | 90th percentile | Yes |
| `p99` | 99th percentile | Yes |
| `percentile` | Custom percentile (requires `percentile_value`) | Yes |
| `histogram` | Distribution of property values | Yes |

There is **no `"sum"`** math type. To sum a property, use `math="total"` with `math_property="..."`.

`math="percentile"` requires `percentile_value` (e.g. `percentile_value=95` for p95). `math="histogram"` shows property value distribution.

### PerUserAggregation

| Value | Meaning |
|-------|---------|
| `unique_values` | Count distinct property values per user |
| `total` | Total count per user |
| `average` | Average per user |
| `min` | Minimum per user |
| `max` | Maximum per user |

Requires `math_property`. Incompatible with `dau`, `wau`, `mau`, `unique`.

---

### build_params()

Same signature as `query()` but returns the bookmark params dict without making an API call:

```python
ws.build_params(
    events, *, from_date, to_date, last, unit, math, math_property,
    percentile_value, per_user, group_by, where, formula, formula_label,
    rolling, cumulative, mode,
) -> dict
```

Useful for debugging, inspecting generated JSON, or passing to `create_bookmark()`.

---

## Typed Query API — Funnels

_Complete reference → [funnels-reference.md](funnels-reference.md)_

`Workspace.query_funnel()` generates valid funnel bookmark params from keyword arguments, posts them inline, and returns a structured `FunnelQueryResult`. Prefer this over the legacy `funnel()` method for all ad-hoc funnel queries.

```python
ws.query_funnel(
    steps: list[str | FunnelStep],
    *,
    conversion_window: int = 14,           # max time between first and last step
    conversion_window_unit: Literal[
        "second", "minute", "hour", "day", "week", "month", "session"
    ] = "day",
    order: Literal["loose", "any"] = "loose",  # loose = steps in order, any = any order
    from_date: str | None = None,          # "YYYY-MM-DD"; mutually exclusive with `last`
    to_date: str | None = None,            # "YYYY-MM-DD"; defaults to today
    last: int = 30,                        # relative window in `unit`s; ignored if from_date set
    unit: QueryTimeUnit = "day",
    math: FunnelMathType = "conversion_rate_unique",
    math_property: str | None = None,
    group_by: str | GroupBy | CohortBreakdown | list[str | GroupBy | CohortBreakdown] | None = None,
    where: Filter | list[Filter] | None = None,
    exclusions: list[str | Exclusion] | None = None,
    holding_constant: str | HoldingConstant | list[str | HoldingConstant] | None = None,
    mode: Literal["steps", "trends", "table"] = "steps",
) -> FunnelQueryResult
```

### FunnelStep

```python
from mixpanel_data import FunnelStep

FunnelStep(
    event: str,                            # event name for this step
    label: str | None = None,              # display label (defaults to event name)
    filters: list[Filter] | None = None,   # per-step filter conditions
    filters_combinator: Literal["all", "any"] = "all",  # AND vs OR for per-step filters
    order: Literal["loose", "any"] | None = None,  # per-step ordering override
)
```

### Exclusion

```python
from mixpanel_data import Exclusion

Exclusion(
    event: str,                            # event name to exclude between steps
    from_step: int | None = None,          # start of exclusion range (0-indexed, inclusive)
    to_step: int | None = None,            # end of exclusion range (0-indexed, inclusive)
)
```

Use plain strings for full-range exclusions; use `Exclusion` objects to target specific step ranges.

### HoldingConstant

```python
from mixpanel_data import HoldingConstant

HoldingConstant(
    property: str,                         # property name to hold constant across steps
    resource_type: Literal["events", "people"] = "events",
)
```

When held constant, only users whose property value is the same at every funnel step are counted as converting.

### FunnelQueryResult

```python
result = ws.query_funnel(["Sign Up", "Purchase"], conversion_window=7)

result.df              # pandas DataFrame with step-level data
result.steps_data      # list of step dicts: event, count, step_conv_ratio, overall_conv_ratio, avg_time, avg_time_from_start
result.series          # raw series data from API
result.params          # generated bookmark params (pass to create_bookmark)
result.meta            # response metadata
result.from_date       # resolved start date
result.to_date         # resolved end date
result.computed_at     # API computation timestamp

# Access step-level data
for step in result.steps_data:
    print(f"{step['event']}: {step['count']} ({step['overall_conv_ratio']:.1%})")
```

### FunnelMathType

| Value | Meaning | Requires `math_property`? |
|-------|---------|--------------------------|
| `conversion_rate_unique` | Conversion rate by unique users (default) | No |
| `conversion_rate_total` | Conversion rate by total events | No |
| `conversion_rate_session` | Conversion rate by sessions | No |
| `unique` | Unique user counts per step | No |
| `total` | Total event counts per step | No |
| `average` | Average of a numeric property | Yes |
| `median` | Median of a numeric property | Yes |
| `min` | Minimum of a numeric property | Yes |
| `max` | Maximum of a numeric property | Yes |
| `p25` | 25th percentile | Yes |
| `p75` | 75th percentile | Yes |
| `p90` | 90th percentile | Yes |
| `p99` | 99th percentile | Yes |

### build_funnel_params()

Same signature as `query_funnel()` but returns the bookmark params dict without making an API call:

```python
ws.build_funnel_params(
    steps, *, conversion_window, conversion_window_unit, order,
    from_date, to_date, last, unit, math, math_property,
    group_by, where, exclusions, holding_constant, mode,
) -> dict
```

---

## Typed Query API — Retention

_Complete reference → [retention-reference.md](retention-reference.md)_

`Workspace.query_retention()` generates valid retention bookmark params from keyword arguments, posts them inline, and returns a structured `RetentionQueryResult`. Prefer this over the legacy `retention()` method for all ad-hoc retention queries.

```python
ws.query_retention(
    born_event: str | RetentionEvent,      # event that defines cohort membership
    return_event: str | RetentionEvent,    # event that defines "coming back"
    *,
    retention_unit: TimeUnit = "week",     # cohort interval: day, week, month
    alignment: RetentionAlignment = "birth",  # birth = align to first event
    bucket_sizes: list[int] | None = None, # custom bucket sizes
    from_date: str | None = None,          # "YYYY-MM-DD"; mutually exclusive with `last`
    to_date: str | None = None,            # "YYYY-MM-DD"; defaults to today
    last: int = 30,                        # relative window in `unit`s; ignored if from_date set
    unit: QueryTimeUnit = "day",
    math: RetentionMathType = "retention_rate",
    group_by: str | GroupBy | CohortBreakdown | list[str | GroupBy | CohortBreakdown] | None = None,
    where: Filter | list[Filter] | None = None,
    mode: RetentionMode = "curve",
) -> RetentionQueryResult
```

**Constraint**: `CohortBreakdown` and property `GroupBy` are mutually exclusive in retention queries (CB3).

### RetentionEvent

```python
from mixpanel_data import RetentionEvent

RetentionEvent(
    event: str,                            # event name
    filters: list[Filter] | None = None,   # per-event filter conditions
    filters_combinator: Literal["all", "any"] = "all",  # AND vs OR
)
```

Use plain event-name strings for simple queries; use `RetentionEvent` objects when you need per-event filters.

### RetentionQueryResult

```python
result = ws.query_retention("Sign Up", "Login", retention_unit="week", last=90)

result.df              # pandas DataFrame: cohort_date, bucket, count, rate
result.cohorts         # dict: cohort_date -> {first, counts, rates}
result.average         # synthetic $average cohort: {first, counts, rates}
result.params          # generated bookmark params (pass to create_bookmark)
result.meta            # response metadata
result.from_date       # resolved start date
result.to_date         # resolved end date
result.computed_at     # API computation timestamp

# Segmented queries (when group_by is used)
result.segments        # dict: segment_name -> {cohort_date -> {first, counts, rates}}
result.segment_averages  # dict: segment_name -> {first, counts, rates}

# Access average retention curve
avg = result.average
print(f"Cohort size: {avg['first']}")
for i, rate in enumerate(avg['rates']):
    print(f"  Week {i}: {rate:.1%}")
```

### RetentionMathType

| Value | Meaning |
|-------|---------|
| `retention_rate` | Retention rate (percentage, default) |
| `unique` | Unique user counts per bucket |

### RetentionAlignment

| Value | Meaning |
|-------|---------|
| `birth` | Align cohorts to their born event date (default) |
| `interval_start` | Align to calendar interval start |

### RetentionMode

| Value | Meaning |
|-------|---------|
| `curve` | Retention curve visualization (default) |
| `trends` | Retention trend over time |
| `table` | Tabular cohort data |

### build_retention_params()

Same signature as `query_retention()` but returns the bookmark params dict without making an API call:

```python
ws.build_retention_params(
    born_event, return_event, *, retention_unit, alignment, bucket_sizes,
    from_date, to_date, last, unit, math, group_by, where, mode,
) -> dict
```

---

## Typed Query API — Flows

_Complete reference → [flows-reference.md](flows-reference.md)_

`Workspace.query_flow()` generates valid flow bookmark params from keyword arguments, posts them to `/arb_funnels`, and returns a structured `FlowQueryResult`. Prefer this over the legacy `query_saved_flows()` method for all ad-hoc flow queries.

```python
ws.query_flow(
    event: str | FlowStep | Sequence[str | FlowStep],
    *,
    forward: int = 3,                      # hops to show AFTER anchor event (0-3)
    reverse: int = 0,                      # hops to show BEFORE anchor event (0-3)
    from_date: str | None = None,          # "YYYY-MM-DD"; mutually exclusive with `last`
    to_date: str | None = None,            # "YYYY-MM-DD"; defaults to today
    last: int = 30,                        # relative window in `unit`s; ignored if from_date set
    conversion_window: int = 7,            # max time window for flow
    conversion_window_unit: Literal["day", "week", "month", "session"] = "day",
    count_type: Literal["unique", "total", "session"] = "unique",
    cardinality: int = 3,                  # max distinct events per step
    collapse_repeated: bool = False,       # merge consecutive same-event nodes
    hidden_events: list[str] | None = None,  # events to exclude from visualization
    mode: Literal["sankey", "paths", "tree"] = "sankey",
) -> FlowQueryResult
```

### FlowStep

```python
from mixpanel_data import FlowStep

FlowStep(
    event: str,                            # event name to anchor on
    forward: int | None = None,            # per-step forward hops (None = use query default)
    reverse: int | None = None,            # per-step reverse hops (None = use query default)
    label: str | None = None,              # display label (defaults to event name)
    filters: list[Filter] | None = None,   # per-step filter conditions
    filters_combinator: Literal["all", "any"] = "all",  # AND vs OR for per-step filters
)
```

### FlowQueryResult

```python
result = ws.query_flow("Login", forward=3, last=30)

result.computed_at              # ISO timestamp when computed
result.steps                    # list of step-node dicts from API
result.flows                    # list of flow-edge dicts
result.breakdowns               # breakdown dicts (when breakdown used)
result.overall_conversion_rate  # overall conversion (0.0 to 1.0)
result.params                   # generated bookmark params
result.meta                     # response metadata
result.mode                     # "sankey", "paths", or "tree"
result.trees                    # list[FlowTreeNode] (populated in tree mode)

# DataFrames (lazy cached)
result.df                       # alias for nodes_df (sankey) or trees_df (tree)
result.nodes_df                 # DataFrame of nodes: step, event, type, count, anchor_type, ...
result.edges_df                 # DataFrame of edges: source_step, source_event, target_step, target_event, count, ...

# Graph analysis
result.graph                    # networkx DiGraph — nodes keyed as "Event@step"
result.top_transitions(n=10)    # list of (source, target, count) tuples, sorted by count desc
result.drop_off_summary()       # dict with per-step drop-off counts and rates

# Tree mode (mode="tree")
result.trees                    # list[FlowTreeNode] — recursive prefix trees
result.anytree                  # list[AnyNode] — anytree wrappers for rendering/traversal
```

### FlowTreeNode

```python
from mixpanel_data.types import FlowTreeNode

FlowTreeNode(
    event: str,                            # event name at this position
    type: FlowNodeType,                    # "ANCHOR", "NORMAL", "DROPOFF", "PRUNED", "FORWARD", "REVERSE"
    step_number: int,                      # zero-based step index
    total_count: int,                      # users reaching this node
    drop_off_count: int = 0,               # users who dropped off here
    converted_count: int = 0,              # users who continued past here
    anchor_type: FlowAnchorType = "NORMAL",  # "NORMAL", "RELATIVE_REVERSE", "RELATIVE_FORWARD"
    is_computed: bool = False,             # whether this is a computed/custom event
    children: tuple[FlowTreeNode, ...] = (),  # child nodes (subsequent events)
    time_percentiles_from_start: dict = {},  # timing from flow start
    time_percentiles_from_prev: dict = {},   # timing from previous node
)

# Computed properties
node.conversion_rate -> float             # converted_count / total_count
node.depth -> int                         # max depth of subtree
node.node_count -> int                    # total nodes in subtree

# Methods
node.all_paths() -> list[list[FlowTreeNode]]  # all root-to-leaf paths
node.flatten() -> list[FlowTreeNode]      # preorder traversal of all nodes
node.find(event) -> list[FlowTreeNode]    # search subtree by event name
node.render() -> str                      # ASCII box-drawing tree visualization
node.to_dict() -> dict                    # serialize to JSON-compatible dict
node.to_anytree() -> AnyNode              # convert to anytree node for rendering/export
```

### FlowNodeType

| Value | Meaning |
|-------|---------|
| `ANCHOR` | The anchor event (starting point) |
| `NORMAL` | A regular event in the flow |
| `DROPOFF` | Users who dropped off at this point |
| `PRUNED` | Events below cardinality threshold |
| `FORWARD` | Forward-direction node |
| `REVERSE` | Reverse-direction node |

### FlowAnchorType

| Value | Meaning |
|-------|---------|
| `NORMAL` | Standard anchor position |
| `RELATIVE_REVERSE` | Anchor relative to reverse direction |
| `RELATIVE_FORWARD` | Anchor relative to forward direction |

### FlowCountType

`Literal["unique", "total", "session"]` — how to count users/events in flows.

### FlowChartType

`Literal["sankey", "paths", "tree"]` — visualization mode for the flow chart.

### build_flow_params()

Same signature as `query_flow()` but returns the bookmark params dict without making an API call:

```python
ws.build_flow_params(
    event, *, forward, reverse, from_date, to_date, last,
    conversion_window, conversion_window_unit, count_type,
    cardinality, collapse_repeated, hidden_events, mode,
) -> dict
```

**Cohort support**: `query_flow()` supports cohort filters via `where=Filter.in_cohort(...)` but does NOT support `CohortBreakdown` or `CohortMetric`.

---

## Analytics — Legacy Core Queries

```python
ws.segmentation(
    event: str, *, from_date: str, to_date: str,
    on: str | None = None,
    unit: Literal["day","week","month"] = "day",
    where: str | None = None,
) -> SegmentationResult
# Legacy — prefer: ws.query() for insights-style queries

ws.funnel(
    funnel_id: int, from_date: str, to_date: str,
    unit: Literal["day","week","month"] | None = None,
    on: str | None = None,
) -> FunnelResult
# Legacy — prefer: ws.query_funnel() for ad-hoc funnels

ws.retention(
    *, born_event: str, return_event: str,
    from_date: str, to_date: str,
    born_where: str | None = None,
    return_where: str | None = None,
    interval: int = 1,
    interval_count: int = 10,
    unit: Literal["day","week","month"] = "day",
) -> RetentionResult
# Legacy — prefer: ws.query_retention() for ad-hoc retention queries

ws.jql(script: str, params: dict | None = None) -> JQLResult

ws.query_saved_report(bookmark_id: int) -> SavedReportResult
```

## Analytics — Extended Queries

```python
ws.event_counts(
    events: list[str], *, from_date: str, to_date: str,
    type: Literal["general", "unique", "average"] = "general",
    unit: Literal["day", "week", "month"] = "day",
) -> EventCountsResult

ws.property_counts(
    event: str, property_name: str, *, from_date: str, to_date: str,
    type: Literal["general", "unique", "average"] = "general",
    unit: Literal["day", "week", "month"] = "day",
) -> PropertyCountsResult

ws.activity_feed(distinct_ids: list[str], *, from_date: str | None = None, to_date: str | None = None) -> ActivityFeedResult

ws.query_saved_flows(bookmark_id: int) -> FlowsResult
# Legacy — prefer: ws.query_flow() for ad-hoc flow queries

ws.frequency(
    *, from_date: str, to_date: str,
    unit: Literal["day", "week", "month"] = "day",
    addiction_unit: Literal["hour", "day"] = "hour",
    event: str | None = None,
    where: str | None = None,
) -> FrequencyResult

ws.segmentation_numeric(
    event: str, *, from_date: str, to_date: str,
    on: str, unit: Literal["hour", "day"] = "day",
    where: str | None = None,
    type: Literal["general", "unique", "average"] = "general",
) -> NumericBucketResult

ws.segmentation_sum(
    event: str, on: str, *, from_date: str, to_date: str,
    unit: Literal["hour", "day"] = "day",
    where: str | None = None,
) -> NumericSumResult
# Legacy — prefer: ws.query(event, math="total", math_property="...")

ws.segmentation_average(
    event: str, on: str, *, from_date: str, to_date: str,
    unit: Literal["hour", "day"] = "day",
    where: str | None = None,
) -> NumericAverageResult
# Legacy — prefer: ws.query(event, math="average", math_property="...")
```

## Analytics — JQL Discovery Helpers

```python
ws.property_distribution(event: str, property: str, limit: int = 20) -> PropertyDistributionResult
ws.numeric_summary(event: str, property: str) -> NumericPropertySummaryResult
ws.daily_counts(event: str, from_date: str, to_date: str) -> DailyCountsResult
ws.engagement_distribution(event: str, from_date: str, to_date: str) -> EngagementDistributionResult
ws.property_coverage(event: str, property: str, from_date: str, to_date: str) -> PropertyCoverageResult
```

## Streaming

```python
ws.stream_events(
    *, from_date: str, to_date: str,
    events: list[str] | None = None,
    where: str | None = None,
    limit: int | None = None,
    raw: bool = False,
) -> Iterator[dict[str, Any]]

ws.stream_profiles(
    *,
    where: str | None = None,
    cohort_id: str | None = None,
    output_properties: list[str] | None = None,
    raw: bool = False,
    distinct_id: str | None = None,
    distinct_ids: list[str] | None = None,
    group_id: str | None = None,
    behaviors: list[dict[str, Any]] | None = None,
    as_of_timestamp: int | None = None,
    include_all_users: bool = False,
) -> Iterator[dict[str, Any]]
```

## Dashboard CRUD

```python
ws.list_dashboards(ids: list[int] | None = None) -> list[Dashboard]
ws.create_dashboard(params: CreateDashboardParams) -> Dashboard
ws.get_dashboard(dashboard_id: int) -> Dashboard
ws.update_dashboard(dashboard_id: int, params: UpdateDashboardParams) -> Dashboard
ws.delete_dashboard(dashboard_id: int) -> None
ws.bulk_delete_dashboards(ids: list[int]) -> None
ws.favorite_dashboard(dashboard_id: int) -> None
ws.unfavorite_dashboard(dashboard_id: int) -> None
ws.pin_dashboard(dashboard_id: int) -> None
ws.unpin_dashboard(dashboard_id: int) -> None
ws.remove_report_from_dashboard(dashboard_id: int, report_id: int) -> None
ws.add_report_to_dashboard(dashboard_id: int, bookmark_id: int) -> Dashboard
```

**Gotchas**:
- `CreateBookmarkParams(dashboard_id=X)` does **NOT** add the report to the dashboard layout — use `add_report_to_dashboard()` instead
- `add_report_to_dashboard()` clones the bookmark, creating a "Duplicate of ..." copy on the dashboard
- `finalize_blueprint()` only works on blueprint-created dashboards, not regular ones
- Dashboard `layout` cannot be set via `update_dashboard()` PATCH (API rejects `order` and `version` keys)

### Dashboard Layout Structure

The `Dashboard.layout` field follows this format (read-only via API):

```python
{
    "rows": {
        "rowId1": {
            "cells": [
                {"id": "cellId", "width": 6, "content_id": 12345, "content_type": "report"},
                {"id": "cellId", "width": 6, "content_id": 67890, "content_type": "report"},
            ],
            "height": 0,
        },
    },
    "order": ["rowId1", ...],  # row display order
    "version": "2.0.0",
}
```

Width is a 12-column grid (6+6 = side by side, 12 = full width).

## Bookmark / Report CRUD

```python
ws.list_bookmarks_v2(type: BookmarkType | None = None, limit: int = 50, offset: int = 0) -> list[Bookmark]
ws.create_bookmark(params: CreateBookmarkParams) -> Bookmark
ws.get_bookmark(bookmark_id: int) -> Bookmark
ws.update_bookmark(bookmark_id: int, params: UpdateBookmarkParams) -> Bookmark
ws.delete_bookmark(bookmark_id: int) -> None
ws.bulk_delete_bookmarks(ids: list[int]) -> None
ws.bulk_update_bookmarks(entries: list[BulkUpdateBookmarkEntry]) -> None
ws.bookmark_linked_dashboard_ids(bookmark_id: int) -> list[int]
ws.get_bookmark_history(bookmark_id: int, limit: int = 20, offset: int = 0) -> BookmarkHistoryResponse
```

## Cohort CRUD

```python
ws.list_cohorts_full(limit: int = 50, offset: int = 0) -> list[Cohort]
ws.get_cohort(cohort_id: int) -> Cohort
ws.create_cohort(params: CreateCohortParams) -> Cohort
ws.update_cohort(cohort_id: int, params: UpdateCohortParams) -> Cohort
ws.delete_cohort(cohort_id: int) -> None
ws.bulk_delete_cohorts(ids: list[int]) -> None
ws.bulk_update_cohorts(entries: list[BulkUpdateCohortEntry]) -> None
```

## Feature Flag CRUD

```python
ws.list_feature_flags(status: FeatureFlagStatus | None = None, limit: int = 50, offset: int = 0) -> list[FeatureFlag]
ws.create_feature_flag(params: CreateFeatureFlagParams) -> FeatureFlag
ws.get_feature_flag(flag_id: str) -> FeatureFlag
ws.update_feature_flag(flag_id: str, params: UpdateFeatureFlagParams) -> FeatureFlag
ws.delete_feature_flag(flag_id: str) -> None
ws.archive_feature_flag(flag_id: str) -> None
ws.restore_feature_flag(flag_id: str) -> FeatureFlag
ws.duplicate_feature_flag(flag_id: str) -> FeatureFlag
ws.set_flag_test_users(flag_id: str, params: SetTestUsersParams) -> None
ws.get_flag_history(flag_id: str, params: FlagHistoryParams) -> FlagHistoryResponse
ws.get_flag_limits() -> FlagLimitsResponse
```

## Experiment CRUD

```python
ws.list_experiments(include_archived: bool = False) -> list[Experiment]
ws.create_experiment(params: CreateExperimentParams) -> Experiment
ws.get_experiment(experiment_id: str) -> Experiment
ws.update_experiment(experiment_id: str, params: UpdateExperimentParams) -> Experiment
ws.delete_experiment(experiment_id: str) -> None
ws.launch_experiment(experiment_id: str) -> Experiment
ws.conclude_experiment(experiment_id: str, params: ExperimentConcludeParams) -> Experiment
ws.decide_experiment(experiment_id: str, params: ExperimentDecideParams) -> Experiment
ws.archive_experiment(experiment_id: str) -> None
ws.restore_experiment(experiment_id: str) -> Experiment
ws.duplicate_experiment(experiment_id: str, params: DuplicateExperimentParams) -> Experiment
```

## Alert CRUD

```python
ws.list_alerts(limit: int = 50, offset: int = 0) -> list[CustomAlert]
ws.create_alert(params: CreateAlertParams) -> CustomAlert
ws.get_alert(alert_id: int) -> CustomAlert
ws.update_alert(alert_id: int, params: UpdateAlertParams) -> CustomAlert
ws.delete_alert(alert_id: int) -> None
ws.bulk_delete_alerts(ids: list[int]) -> None
ws.get_alert_count(alert_type: str | None = None) -> AlertCount
ws.get_alert_history(limit: int = 20, offset: int = 0) -> AlertHistoryResponse
ws.test_alert(params: CreateAlertParams) -> dict
```

## Annotation CRUD

```python
ws.list_annotations(limit: int = 50, offset: int = 0) -> list[Annotation]
ws.create_annotation(params: CreateAnnotationParams) -> Annotation
ws.get_annotation(annotation_id: int) -> Annotation
ws.update_annotation(annotation_id: int, params: UpdateAnnotationParams) -> Annotation
ws.delete_annotation(annotation_id: int) -> None
ws.list_annotation_tags() -> list[AnnotationTag]
ws.create_annotation_tag(params: CreateAnnotationTagParams) -> AnnotationTag
```

## Webhook CRUD

```python
ws.list_webhooks() -> list[ProjectWebhook]
ws.create_webhook(params: CreateWebhookParams) -> WebhookMutationResult
ws.update_webhook(webhook_id: str, params: UpdateWebhookParams) -> WebhookMutationResult
ws.delete_webhook(webhook_id: str) -> None
ws.test_webhook(params: WebhookTestParams) -> WebhookTestResult
```

## Data Governance — Lexicon

```python
ws.get_event_definitions(names: list[str]) -> list[EventDefinition]
ws.update_event_definition(name: str, params: UpdateEventDefinitionParams) -> EventDefinition
ws.delete_event_definition(event_name: str) -> None
ws.bulk_update_event_definitions(entries: list[BulkEventUpdate]) -> list[EventDefinition]
ws.get_property_definitions(names: list[str], resource_type: PropertyResourceType) -> list[PropertyDefinition]
ws.update_property_definition(name: str, resource_type: PropertyResourceType, params: UpdatePropertyDefinitionParams) -> PropertyDefinition
ws.bulk_update_property_definitions(entries: list[BulkPropertyUpdate]) -> list[PropertyDefinition]
ws.list_lexicon_tags() -> list[LexiconTag]
ws.create_lexicon_tag(params: CreateTagParams) -> LexiconTag
ws.update_lexicon_tag(tag_id: int, params: UpdateTagParams) -> LexiconTag
ws.delete_lexicon_tag(tag_name: str) -> None
ws.export_lexicon(export_types: list[str] | None = None) -> dict
```

## Data Governance — Drop Filters, Custom Properties, Lookup Tables

```python
# Drop Filters
ws.list_drop_filters() -> list[DropFilter]
ws.create_drop_filter(params: CreateDropFilterParams) -> list[DropFilter]
ws.update_drop_filter(params: UpdateDropFilterParams) -> list[DropFilter]
ws.delete_drop_filter(drop_filter_id: int) -> list[DropFilter]

# Custom Properties
ws.list_custom_properties() -> list[CustomProperty]
ws.create_custom_property(params: CreateCustomPropertyParams) -> CustomProperty
ws.get_custom_property(property_id: str) -> CustomProperty
ws.update_custom_property(property_id: str, params: UpdateCustomPropertyParams) -> CustomProperty
ws.delete_custom_property(property_id: str) -> None

# Custom Events
ws.list_custom_events() -> list[EventDefinition]
ws.update_custom_event(event_name: str, params: dict) -> EventDefinition
ws.delete_custom_event(event_name: str) -> None

# Lookup Tables
ws.list_lookup_tables(limit: int = 50, offset: int = 0) -> list[LookupTable]
ws.upload_lookup_table(params: UploadLookupTableParams) -> LookupTable
ws.update_lookup_table(data_group_id: int, params: UpdateLookupTableParams) -> LookupTable
ws.delete_lookup_tables(data_group_ids: list[int]) -> None
ws.download_lookup_table(data_group_id: int, file_path: str) -> None
```

## Schema Registry & Audit

```python
ws.list_schema_registry(limit: int = 50, offset: int = 0) -> list[SchemaEntry]
ws.create_schema(event_name: str, properties: dict) -> SchemaEntry
ws.update_schema(event_name: str, properties: dict) -> SchemaEntry
ws.delete_schemas(event_names: list[str]) -> DeleteSchemasResponse
ws.get_schema_enforcement() -> SchemaEnforcementConfig
ws.run_audit() -> AuditResponse
ws.list_data_volume_anomalies(limit: int = 50, offset: int = 0) -> list[DataVolumeAnomaly]
```

## Deletion Requests

```python
ws.list_deletion_requests() -> list[EventDeletionRequest]
ws.create_deletion_request(params: CreateDeletionRequestParams) -> EventDeletionRequest
ws.cancel_deletion_request(request_id: int) -> list[EventDeletionRequest]
```

## Workspace Management

```python
ws.list_workspaces() -> list[PublicWorkspace]
ws.workspace_id -> int | None                   # property
ws.set_workspace_id(workspace_id: int | None) -> None
ws.resolve_workspace_id() -> int
ws.test_credentials() -> bool
ws.api -> MixpanelAPIClient                     # escape hatch for custom requests
```

## Session & Project Management (v2 Config)

These methods require the v2 config schema (credential + project context). Migrate with `ConfigManager().migrate_v1_to_v2()` or `mp auth migrate`.

```python
# Identity & discovery via /me API
ws.me(*, force_refresh: bool = False) -> MeResponse
ws.discover_projects() -> list[tuple[str, MeProjectInfo]]   # (org_name, project_info) pairs
ws.discover_workspaces(project_id: str | None = None) -> list[MeWorkspaceInfo]

# In-session switching (changes the live Workspace without re-constructing)
ws.switch_project(project_id: str, workspace_id: int | None = None) -> None
ws.switch_workspace(workspace_id: int) -> None

# Current session info (properties)
ws.current_project -> ProjectContext          # active project_id, workspace_id
ws.current_credential -> AuthCredential       # active auth identity (name, type, region)
```

### MeResponse / MeProjectInfo / MeWorkspaceInfo

```python
from mixpanel_data._internal.me import MeResponse, MeProjectInfo, MeWorkspaceInfo

# MeProjectInfo fields
proj.id          # int — project ID
proj.name        # str — project display name
proj.timezone    # str — project timezone

# MeWorkspaceInfo fields
wsi.id           # int — workspace ID
wsi.name         # str — workspace display name

# MeResponse fields
me.organizations  # list[MeOrgInfo] — orgs with nested projects
```

### Auth v2 Types

```python
from mixpanel_data import AuthCredential, CredentialType, ProjectContext, ResolvedSession

# AuthCredential — standalone auth identity
cred.name         # str — credential name
cred.type         # CredentialType — "service_account" or "oauth"
cred.region       # str — "us", "eu", "in"
cred.auth_header() # str — "Bearer <token>" or "Basic <encoded>"

# ProjectContext — project + optional workspace selection
ctx.project_id    # str
ctx.workspace_id  # int | None

# ResolvedSession — credential + project context composition
session.credential   # AuthCredential
session.project      # ProjectContext
session.workspace_id # int | None (convenience property)
```

## Key Result Types

All query results have a `.df` property returning a pandas DataFrame. Key types:

| Type | From Method | Key Properties |
|------|------------|----------------|
| `SegmentationResult` | `segmentation()` | `.df`, `.data`, `.series` |
| `FunnelResult` | `funnel()` | `.df`, `.steps` (list of `FunnelResultStep`), `.conversion_rate` |
| `RetentionResult` | `retention()` | `.df`, `.data` |
| `JQLResult` | `jql()` | `.df`, `.data` |
| `EventCountsResult` | `event_counts()` | `.df`, `.data` |
| `ActivityFeedResult` | `activity_feed()` | `.events` |
| `FlowsResult` | `query_saved_flows()` | `.df`, `.data` |
| `FrequencyResult` | `frequency()` | `.df`, `.data` |
| `QueryResult` | `query()` | `.df`, `.params`, `.series`, `.meta`, `.from_date`, `.to_date`, `.computed_at` |
| `FunnelQueryResult` | `query_funnel()` | `.df`, `.steps_data`, `.params`, `.series`, `.meta`, `.from_date`, `.to_date`, `.computed_at` |
| `RetentionQueryResult` | `query_retention()` | `.df`, `.cohorts`, `.average`, `.segments`, `.segment_averages`, `.params`, `.meta`, `.from_date`, `.to_date`, `.computed_at` |
| `FlowQueryResult` | `query_flow()` | `.df`, `.nodes_df`, `.edges_df`, `.graph`, `.trees`, `.anytree`, `.top_transitions()`, `.drop_off_summary()`, `.params`, `.meta`, `.computed_at` |

## Exception Hierarchy

_For error handling patterns and recovery strategies, see [Auth Error Recovery](../../../agents/analyst.md#auth-error-recovery) in the analyst agent._

```
MixpanelDataError (base)
├── ConfigError
│   ├── AccountNotFoundError
│   └── AccountExistsError
├── APIError
│   ├── AuthenticationError (401)
│   ├── RateLimitError (429)
│   ├── QueryError (400)
│   │   └── JQLSyntaxError (412)
│   └── ServerError (5xx)
├── ProjectNotFoundError
├── OAuthError
└── WorkspaceScopeError
```
