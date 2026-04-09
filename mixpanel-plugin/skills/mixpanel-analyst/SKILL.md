---
name: mixpanel-analyst
description: This skill should be used when the user asks about Mixpanel product analytics, event data, funnel analysis, retention curves, cohort analysis, segmentation queries, JQL, user behavior, conversion rates, churn, DAU/MAU, ARPU, revenue metrics, feature adoption, A/B test results, user paths, flow analysis, or any request to query, explore, visualize, or analyze Mixpanel data using Python.
allowed-tools: Bash Read Write
---

# Mixpanel Analyst — CodeMode v3

Analyze the user's Mixpanel data by **writing and executing Python code** that uses the `mixpanel_data` library, `pandas`, `networkx`, and `anytree`. Act as a senior data analyst and product analytics expert.

## Core Principle: Code Over Tools

Write Python code. Never teach CLI commands. Never call MCP tools.

- **Quick lookups** → `python3 -c "..."` one-liners
- **Multi-step analysis** → write and execute `.py` files
- **Data manipulation** → pandas DataFrames (every result type has a `.df` property)
- **Graph analysis** → networkx on flow data (`.graph` property)
- **Tree analysis** → anytree on flow tree data (`.anytree` property)
- **Visualization** → matplotlib / seaborn, saved to files

```bash
python3 -c "
import mixpanel_data as mp; ws = mp.Workspace()
r = ws.query('Login', last=30)
print(f'Total logins (30d): {r.df[\"count\"].sum():,.0f}')
"
```

## The Four Query Engines

Mixpanel has four fundamentally different query engines. Each answers a different *type* of question. Choosing the right engine is the most important decision in any analysis.

| Engine | Method | Core Question | Result Type |
|--------|--------|--------------|-------------|
| **Insights** | `ws.query()` | How much? How many? | `QueryResult` |
| **Funnels** | `ws.query_funnel()` | Do users convert through a sequence? | `FunnelQueryResult` |
| **Retention** | `ws.query_retention()` | Do users come back? | `RetentionQueryResult` |
| **Flows** | `ws.query_flow()` | What paths do users take? | `FlowQueryResult` |

_Each engine has a dedicated deep reference — load on demand when the quick reference below is insufficient. For NL→engine routing with 50+ signal patterns, see [query-taxonomy.md](references/query-taxonomy.md)._

### Mental Model

- **Insights** — "I need to **measure a metric** over time." Counts, aggregations, DAU/WAU/MAU, property math, formulas, rolling averages. The workhorse for any "how much" or "how many" question.

- **Funnels** — "I need to measure **conversion through a process**." Ordered sequences of events with conversion windows, exclusions, and per-step filters. The answer to "what percentage of users complete X?"

- **Retention** — "I need to measure whether a **behavior repeats**." Born/return event pairs across cohorts with custom time buckets. The answer to "do users come back?"

- **Flows** — "I need to **explore the routes** through my product." Forward and reverse step tracing from anchor events, producing graphs and trees. The answer to "what do users do after/before X?"

### When in Doubt

- If the question is about **a number changing over time** → Insights
- If the question mentions **steps, conversion, drop-off** → Funnels
- If the question mentions **coming back, retention, churn, cohort** → Retention
- If the question mentions **paths, journeys, next steps, what leads to** → Flows
- If the question asks **"why did X change?"** → Multiple engines (see Cross-Query Patterns)

## Query Routing Decision Tree

Map natural language to the right engine:

```
User says...                              → Use...
─────────────────────────────────────────────────────
"how many", "count", "total", "trend"     → Insights
"DAU/WAU/MAU", "active users"             → Insights (math="dau")
"average/median/p99", "distribution"      → Insights (math=...)
"per user", "average per user"            → Insights (per_user=...)
"compare events", "formula"               → Insights (formula=...)
"rolling average", "cumulative"           → Insights (rolling/cumulative)
─────────────────────────────────────────────────────
"conversion", "funnel", "from X to Y"     → Funnels
"drop-off", "where do users leave"        → Funnels
"checkout/signup/onboarding completion"   → Funnels
"time to convert", "conversion window"    → Funnels
─────────────────────────────────────────────────────
"retention", "come back", "return rate"   → Retention
"D1/D7/D30", "churn", "stickiness"       → Retention
"cohort", "do they keep using"            → Retention
─────────────────────────────────────────────────────
"path", "flow", "journey"                → Flows
"what happens after X", "next steps"      → Flows (forward)
"what led to X", "how did they get to"    → Flows (reverse)
"user paths", "navigation patterns"       → Flows
─────────────────────────────────────────────────────
"why did X change/drop/spike"             → MULTI-ENGINE
"how is feature X performing"             → MULTI-ENGINE
"product health", "overview"              → MULTI-ENGINE
"what's wrong with onboarding"            → MULTI-ENGINE
```

### Multi-Query Decomposition

For complex questions, decompose into a query plan:

| Question Pattern | Engines | Sub-queries |
|---|---|---|
| "Why did X drop?" | All 4 | Insights (magnitude) → Funnels (conversion check) → Retention (return check) → Flows (path changes) |
| "Feature adoption?" | Ins+Fun+Ret | Insights (usage) + Funnels (discovery→use) + Retention (continued use) |
| "Onboarding health?" | Fun+Flow+Ret | Funnels (completion) + Flows (user paths) + Retention (post-onboarding) |
| "Product health?" | All 4 | DAU (Insights) + Key funnels + Retention curves + Top paths |

_(→ [query-taxonomy.md](references/query-taxonomy.md) §Complex Question Decomposition for 12 detailed decomposition patterns with code | [cross-query-synthesis.md](references/cross-query-synthesis.md) for implementation templates)_

## On-Demand API Lookup

Before any unfamiliar API call, look up the exact signature:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.query
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.query_funnel
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.query_retention
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.query_flow
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py QueryResult       # result types
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py FlowTreeNode      # tree node
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py types              # list all types
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py exceptions         # all exceptions
```

Use this before every unfamiliar method. It pulls live docstrings — always accurate.

## Workspace Construction

```python
import mixpanel_data as mp

ws = mp.Workspace()                          # default account
ws = mp.Workspace(account="production")      # named account (v1 config)
ws = mp.Workspace(credential="production")   # named credential (v2 config)
ws = mp.Workspace(workspace_id=12345)        # with workspace ID for App API
# project_id must be a STRING: ws = mp.Workspace(project_id="8")

# v2 config: discover and switch projects without re-constructing
projects = ws.discover_projects()            # list accessible projects via /me API
ws.switch_project("67890")                   # switch active project in-session
ws.switch_workspace(12345)                   # switch active workspace in-session
print(ws.current_project)                    # active ProjectContext
print(ws.current_credential)                 # active AuthCredential
```

## Quick API Reference — All Engines

### Discovery — What Data Exists?

```python
ws.events()                                    # → list[str]
ws.properties("Login")                         # → list[str]
ws.property_values("city", event="Login")      # → list[str]
ws.top_events(limit=10)                        # → list[TopEvent]
ws.funnels()                                   # → list[FunnelInfo]
ws.cohorts()                                   # → list[SavedCohort]
# Cohort IDs from cohorts() work with Filter.in_cohort(), CohortBreakdown(), CohortMetric()
ws.list_bookmarks()                            # → list[BookmarkInfo]
ws.lexicon_schemas()                           # → list[LexiconSchema]
ws.lexicon_schema("event", "Purchase")         # → LexiconSchema (definitions, tags)
```

### Insights — `ws.query()`

```python
from mixpanel_data import Metric, Filter, GroupBy, Formula
from mixpanel_data import CohortBreakdown, CohortMetric, CohortDefinition, CohortCriteria
from mixpanel_data import CustomPropertyRef, InlineCustomProperty

result = ws.query(
    events,              # str | Metric | Formula | Sequence[str | Metric | Formula]
    from_date=None,      # "YYYY-MM-DD" (overrides last)
    to_date=None,        # "YYYY-MM-DD"
    last=30,             # relative days (default)
    unit="day",          # hour | day | week | month | quarter
    math="total",        # see MathType table
    math_property=None,  # required for property-based math
    per_user=None,       # unique_values | total | average | min | max
    percentile_value=None, # int for math="percentile"
    group_by=None,       # str | GroupBy | list[str | GroupBy]
    where=None,          # Filter | list[Filter]
    formula=None,        # "(B / A) * 100" (requires 2+ events)
    formula_label=None,
    rolling=None,        # rolling window periods
    cumulative=False,    # mutually exclusive with rolling
    mode="timeseries",   # timeseries | total | table
) # → QueryResult
```

**MathType** (14 values):

| Math | What it measures | Requires math_property? |
|------|-----------------|------------------------|
| `total` | Event count (or sum if math_property set) | Optional |
| `unique` | Unique users | No |
| `dau` / `wau` / `mau` | Daily/Weekly/Monthly active users | No |
| `average` / `median` / `min` / `max` | Property aggregation | Yes |
| `p25` / `p75` / `p90` / `p99` | Property percentiles | Yes |
| `percentile` | Custom percentile (set percentile_value) | Yes |
| `histogram` | Property value distribution | Yes |

_Complete parameter reference → [insights-reference.md](references/insights-reference.md)_

**Result**: `result.df` (DataFrame) · `result.params` (bookmark JSON) · `result.series` (raw data) · `result.meta`

**Examples**:
```python
ws.query("Login", math="dau", last=90)                              # DAU trend
ws.query("Purchase", math="average", math_property="amount")        # avg purchase
ws.query("Login", where=Filter.equals("platform", "iOS"), group_by="country")
ws.query([Metric("Signup", math="unique"), Metric("Purchase", math="unique")],
         formula="(B/A)*100", formula_label="Conversion Rate")
ws.query("Signup", rolling=7)                                       # 7-day rolling avg
```

### Funnels — `ws.query_funnel()`

```python
from mixpanel_data import FunnelStep, Exclusion, HoldingConstant

result = ws.query_funnel(
    steps,                    # list[str | FunnelStep] (min 2)
    conversion_window=14,     # how long to complete
    conversion_window_unit="day",  # second|minute|hour|day|week|month|session
    order="loose",            # loose | any
    from_date=None, to_date=None, last=30, unit="day",
    math="conversion_rate_unique",  # see FunnelMathType
    math_property=None,       # for property aggregation math types
    group_by=None, where=None,
    exclusions=None,          # list[str | Exclusion]
    holding_constant=None,    # str | HoldingConstant | list
    mode="steps",             # steps | trends | table
) # → FunnelQueryResult
```

**FunnelStep**: `FunnelStep(event, label=None, filters=None, filters_combinator="all", order=None)`
**Exclusion**: `Exclusion(event, from_step=0, to_step=None)` — step ranges (0-indexed)
**HoldingConstant**: `HoldingConstant(property, resource_type="events")` — max 3

_Complete parameter reference → [funnels-reference.md](references/funnels-reference.md)_

**FunnelMathType**: `conversion_rate_unique` (default) · `conversion_rate_total` · `conversion_rate_session` · `unique` · `total` · `average` · `median` · `min` · `max` · `p25` · `p75` · `p90` · `p99`

**Result**: `result.overall_conversion_rate` · `result.df` (step, event, count, step_conv_ratio, overall_conv_ratio, avg_time) · `result.params`

**Examples**:
```python
ws.query_funnel(["Signup", "Purchase"])                              # simple
ws.query_funnel(["Signup", "Purchase"], conversion_window=7)         # 7-day window
ws.query_funnel([FunnelStep("Signup"), FunnelStep("Purchase",
    filters=[Filter.greater_than("amount", 50)], label="High-Value")])
ws.query_funnel(["Browse", "Cart", "Purchase"], exclusions=["Logout"])
ws.query_funnel(["Signup", "Purchase"], holding_constant="platform")
```

### Retention — `ws.query_retention()`

```python
from mixpanel_data import RetentionEvent

result = ws.query_retention(
    born_event,           # str | RetentionEvent
    return_event,         # str | RetentionEvent
    retention_unit="week",  # day | week | month
    alignment="birth",    # birth | interval_start
    bucket_sizes=None,    # list[int] ascending, max 730
    from_date=None, to_date=None, last=30, unit="day",
    math="retention_rate",  # retention_rate | unique
    group_by=None, where=None,
    mode="curve",         # curve | trends | table
) # → RetentionQueryResult
```

**RetentionEvent**: `RetentionEvent(event, filters=None, filters_combinator="all")`

_Complete parameter reference → [retention-reference.md](references/retention-reference.md)_

**Alignment**: `"birth"` (user's clock starts at born event) vs `"interval_start"` (calendar boundaries)

**Result**: `result.cohorts` (dict of cohort data) · `result.average` (synthetic average) · `result.df` (cohort_date, bucket, count, rate) · `result.params`

**Examples**:
```python
ws.query_retention("Signup", "Login")                                # weekly retention
ws.query_retention("Signup", "Login", retention_unit="day",
                   bucket_sizes=[1, 3, 7, 14, 30])                   # milestone buckets
ws.query_retention(
    RetentionEvent("Signup", filters=[Filter.equals("source", "organic")]),
    "Purchase", last=90)
ws.query_retention("Signup", "Login", mode="trends", unit="week")    # retention trends
```

### Flows — `ws.query_flow()`

```python
from mixpanel_data import FlowStep

result = ws.query_flow(
    event,                # str | FlowStep | Sequence[str | FlowStep]
    forward=3,            # 0-5 steps forward from anchor
    reverse=0,            # 0-5 steps reverse (at least one must be nonzero)
    from_date=None, to_date=None, last=30,
    conversion_window=7,
    conversion_window_unit="day",  # day | week | month | session
    count_type="unique",  # unique | total | session
    cardinality=3,        # 1-50 events per step position
    collapse_repeated=False,
    hidden_events=None,   # list[str]
    mode="sankey",        # sankey | paths | tree
) # → FlowQueryResult
```

**FlowStep**: `FlowStep(event, forward=None, reverse=None, label=None, filters=None, filters_combinator="all")`

_Complete parameter reference → [flows-reference.md](references/flows-reference.md)_

**Three modes produce different result structures**:

| Mode | Key properties | Use for |
|------|---------------|---------|
| `sankey` | `.nodes_df`, `.edges_df`, `.graph` (NetworkX DiGraph), `.top_transitions(n)`, `.drop_off_summary()` | Graph analysis, bottleneck detection |
| `paths` | `.df` (path_index, step, event, type, count) | Path ranking and comparison |
| `tree` | `.trees` (list[FlowTreeNode]), `.anytree` (list[AnyNode]) | Branching analysis, Graphviz export |

**Result**: `result.overall_conversion_rate` · `result.params` · mode-specific properties above

**Examples**:
```python
ws.query_flow("Purchase")                                            # 3 steps forward
ws.query_flow("Purchase", forward=0, reverse=5)                      # what led to purchase?
ws.query_flow("Purchase", mode="tree")                               # tree traversal
ws.query_flow(FlowStep("Purchase", filters=[Filter.greater_than("amount", 50)]))
ws.query_flow("Purchase", hidden_events=["Page View", "Session Start"])

# NetworkX graph analysis
g = result.graph
import networkx as nx
bottleneck = max(nx.betweenness_centrality(g, weight="count"),
                 key=nx.betweenness_centrality(g, weight="count").get)

# Tree traversal
for tree in result.trees:
    print(tree.render())  # ASCII visualization
    best_path = max(tree.all_paths(), key=lambda p: p[-1].converted_count)
```

### Filter Expression Syntax

_Summary of key filters. For the full Filter API (20+ methods, 7 categories, combining logic), see [insights-reference.md](references/insights-reference.md) §Filter Deep Reference._

All 4 query engines share the same `Filter` class:

```python
from mixpanel_data import Filter

# String
Filter.equals("platform", "iOS")              # or multi-value: ["iOS", "Android"]
Filter.not_equals("country", "US")
Filter.contains("email", "@company.com")
Filter.not_contains("page", "admin")

# Numeric
Filter.greater_than("revenue", 100)
Filter.less_than("age", 18)
Filter.between("age", 18, 65)              # inclusive range

# Existence & Boolean
Filter.is_set("email")
Filter.is_not_set("utm_source")
Filter.is_true("is_premium")
Filter.is_false("opted_out")

# Date
Filter.on("created", "2025-01-15")
Filter.before("created", "2025-01-01")
Filter.since("created", "2025-01-01")
Filter.in_the_last("created", 30, "day")
Filter.date_between("created", "2025-01-01", "2025-06-30")  # date range

# Cohort membership
Filter.in_cohort(123, "Power Users")                 # users in saved cohort
Filter.in_cohort(cohort_def, "Custom Segment")       # users matching inline definition
Filter.not_in_cohort(123, "Churned Users")           # users NOT in cohort

# Custom properties (saved or inline)
Filter.greater_than(property=CustomPropertyRef(42), value=100)
Filter.between(property=InlineCustomProperty.numeric("A*B", A="price", B="qty"), value=[10, 500])
```

### Streaming — Raw Data Access

```python
for event in ws.stream_events(from_date="2025-01-01", to_date="2025-01-02"):
    print(event["event_name"], event["event_time"], event["properties"])

for profile in ws.stream_profiles():
    print(profile["distinct_id"])
```

### Entity Management (App API)

Full CRUD for dashboards, cohorts, feature flags, experiments, alerts, annotations, webhooks, Lexicon. Use `help.py` to look up signatures:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.list_dashboards
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.create_bookmark
```

### Saving Queries as Mixpanel Reports

Every typed query generates persistable bookmark params:

```python
from mixpanel_data import CreateBookmarkParams

# query() → insights report
result = ws.query("Login", math="dau", last=90)
ws.create_bookmark(CreateBookmarkParams(
    name="DAU (90d)", bookmark_type="insights", params=result.params))

# query_funnel() → funnel report
result = ws.query_funnel(["Signup", "Purchase"])
ws.create_bookmark(CreateBookmarkParams(
    name="Signup→Purchase", bookmark_type="funnels", params=result.params))

# query_retention() → retention report
result = ws.query_retention("Signup", "Login")
ws.create_bookmark(CreateBookmarkParams(
    name="Signup Retention", bookmark_type="retention", params=result.params))

# query_flow() → flows report
result = ws.query_flow("Purchase", forward=3, reverse=1)
ws.create_bookmark(CreateBookmarkParams(
    name="Purchase Flows", bookmark_type="flows", params=result.params))

# build_*_params() generates params without executing the query
params = ws.build_funnel_params(["Signup", "Purchase"])
params = ws.build_retention_params("Signup", "Login")
params = ws.build_flow_params("Purchase", forward=3)
```

## Cross-Query Patterns

_Three common patterns below. For 6 join strategies and 11 investigation templates with full code, see [cross-query-synthesis.md](references/cross-query-synthesis.md)._

The engines complement each other. These patterns combine them for deeper analysis:

### Pattern 1: Funnel + Flow Complement

Funnels show **that** conversion dropped; Flows show **where** users went instead.

```python
# 1. Find the worst-converting step
funnel = ws.query_funnel(["Browse", "Add to Cart", "Checkout", "Purchase"])
worst = funnel.df.loc[funnel.df["step_conv_ratio"].idxmin()]

# 2. Trace where non-converters go
flow = ws.query_flow(worst["event"], forward=3)
print(flow.top_transitions(10))  # where they go instead
print(flow.drop_off_summary())   # per-step drop-off
```

### Pattern 2: Insights + Retention Correlation

Does behavior X predict retention?

```python
# Compare retention for high vs low usage segments
from mixpanel_data import RetentionEvent, Filter
power = ws.query_retention(
    RetentionEvent("Feature Used", filters=[Filter.greater_than("count", 5)]),
    "Any Active Event", last=90)
casual = ws.query_retention(
    RetentionEvent("Feature Used", filters=[Filter.less_than("count", 3)]),
    "Any Active Event", last=90)
# Compare power.average["rates"] vs casual.average["rates"]
```

### Pattern 3: Multi-Engine Investigation

For "why did X change?", query all engines in parallel:

```python
from concurrent.futures import ThreadPoolExecutor

ws = mp.Workspace()
queries = {
    "metric": lambda: ws.query("Purchase", math="total", math_property="revenue", last=60),
    "funnel": lambda: ws.query_funnel(["Browse", "Purchase"], last=60),
    "retention": lambda: ws.query_retention("Purchase", "Purchase", last=60),
    "flow": lambda: ws.query_flow("Purchase", reverse=3, last=60),
}
with ThreadPoolExecutor(max_workers=4) as pool:
    results = {k: pool.submit(v) for k, v in queries.items()}
    results = {k: v.result() for k, v in results.items()}
```

## Cohort-Scoped Queries

Cohorts cut across all four query engines. Three capabilities let you scope any analysis to a user segment:

| Capability | Parameter | Engines | Type |
|---|---|---|---|
| **Filter by cohort** | `where=` | All 4 | `Filter.in_cohort()` / `Filter.not_in_cohort()` |
| **Break down by cohort** | `group_by=` | Insights, Funnels, Retention | `CohortBreakdown` |
| **Track cohort size** | `events=` | Insights only | `CohortMetric` |

```python
from mixpanel_data import Filter, CohortBreakdown, CohortMetric

# 1. Filter: restrict any query to a cohort
result = ws.query("Login", math="dau", where=Filter.in_cohort(123, "Power Users"), last=30)

# 2. Breakdown: segment results by cohort membership (in vs not-in)
result = ws.query("Login", math="dau", group_by=CohortBreakdown(123, "Power Users"), last=30)

# 3. Metric: track cohort size over time (insights only)
result = ws.query(CohortMetric(123, "Power Users"), last=90)
```

### Inline Cohort Definitions

Build ad-hoc cohorts without saving them to Mixpanel:

```python
from mixpanel_data import CohortDefinition, CohortCriteria

premium_active = CohortDefinition.all_of(
    CohortCriteria.has_property("plan", "premium"),
    CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
)

# Use anywhere a cohort ID is accepted
result = ws.query("Login", where=Filter.in_cohort(premium_active, "Premium Active"), last=30)
result = ws.query("Login", group_by=CohortBreakdown(premium_active, "Premium Active"))
```

**Note**: When using inline `CohortDefinition` with `CohortMetric`, always provide a descriptive `name` parameter — it is required for server-side label generation.

## Custom Properties in Queries

Use saved custom properties or define computed properties inline — in breakdowns, filters, and measurement. Custom properties work everywhere a plain string property name does.

| Capability | Parameter | Engines | Type |
|---|---|---|---|
| **Breakdown by CP** | `group_by=` | Insights, Funnels, Retention | `GroupBy(property=...)` |
| **Filter by CP** | `where=` | Insights, Funnels\*, Retention\* | `Filter.*(property=...)` |
| **Measure a CP** | `Metric(property=...)` | Insights only | `Metric` |

\*Known server bug may cause errors in funnel/retention `where=` filters. Breakdowns work reliably in all three engines. Flows do not support custom properties.

### Saved Custom Properties

Reference by ID (find IDs with `ws.list_custom_properties()`):

```python
from mixpanel_data import CustomPropertyRef, GroupBy, Filter, Metric

ref = CustomPropertyRef(42)

# Breakdown
ws.query("Purchase", group_by=GroupBy(property=ref, property_type="number", bucket_size=50))

# Filter
ws.query("Purchase", where=Filter.greater_than(property=ref, value=100))

# Measurement (insights only — must use Metric, not math_property)
ws.query(Metric("Purchase", math="average", property=ref))
```

### Inline Custom Properties

Define a computed property at query time — no need to save it first:

```python
from mixpanel_data import InlineCustomProperty

# Convenience constructor for numeric formulas
revenue = InlineCustomProperty.numeric("A * B", A="price", B="quantity")

# Use anywhere a property name goes
ws.query("Purchase", group_by=GroupBy(property=revenue, property_type="number", bucket_size=100))
ws.query("Purchase", where=Filter.greater_than(property=revenue, value=1000))
ws.query(Metric("Purchase", math="average", property=revenue))
```

**Note**: Top-level `math_property=` only accepts strings. Use `Metric(property=...)` for custom property measurement.

## How to Think About Analysis

### 1. Always Start with Discovery

Before answering any question, explore the schema:

```python
events = ws.events()
top = ws.top_events(limit=10)
props = ws.properties("Sign Up")
```

### 2. Classify with AARRR

Map every question to a pirate metric stage and choose the right engine:

| Stage | Key Question | Primary Engines |
|-------|-------------|-----------------|
| **Acquisition** | Where do users come from? | Insights (source breakdown), Flows (entry paths) |
| **Activation** | Do they reach the aha moment? | Funnels (onboarding completion), Flows (activation paths) |
| **Retention** | Do they come back? | Retention (cohort curves), Insights (usage trends) |
| **Revenue** | Do they pay? | Insights (revenue metrics), Funnels (purchase conversion) |
| **Referral** | Do they invite others? | Insights (invite events), Funnels (invite→accept) |

_(→ [analytical-frameworks.md](references/analytical-frameworks.md) §AARRR for the complete framework with engine mappings and industry benchmarks)_

### 3. GQM for Vague Questions

Decompose with Goal-Question-Metric, specifying the engine for each:

1. **Goal**: What business outcome?
2. **Questions**: 3-5 specific sub-questions
3. **Metrics**: For each → which engine? which method? which params?
4. **Join strategy**: How to combine results?

_(→ [analytical-frameworks.md](references/analytical-frameworks.md) §GQM for 3 worked examples | the explorer agent implements a full 5-step GQM workflow)_

### 4. Provide Actionable Insights

Never just show data. Always:
- State the finding clearly
- Quantify the impact with specific numbers
- Compare to previous periods (WoW, MoM)
- Note sample sizes — small numbers = low confidence
- Suggest a concrete next step

## Advanced Libraries

Use these to extend Mixpanel's capabilities:

| Library | When to use | Access via |
|---------|------------|------------|
| **pandas** | Always — every result has `.df` | `result.df` |
| **networkx** | Flow graph analysis (centrality, shortest paths, cycles, PageRank) | `flow_result.graph` |
| **anytree** | Flow tree analysis (branching, parent traversal, Graphviz export) | `flow_result.anytree` or `tree.to_anytree()` |
| **numpy/scipy** | Statistical testing (t-test, chi-squared, correlation) | Import directly |
| **matplotlib/seaborn** | Visualization | Import directly |

### NetworkX Quick Patterns

```python
import networkx as nx
g = flow_result.graph

nx.shortest_path(g, "Signup@0", "Purchase@3")       # optimal path
nx.betweenness_centrality(g, weight="count")         # bottleneck detection
list(nx.simple_cycles(g))                            # loop detection
nx.pagerank(g, weight="count")                       # event importance
```

_Quick patterns here. For comprehensive graph analysis (subgraphs, centrality, comparison, path enumeration), see [flows-reference.md](references/flows-reference.md) §NetworkX Integration Patterns and [advanced-analysis.md](references/advanced-analysis.md) §Graph Analysis._

### anytree Quick Patterns

```python
from anytree import RenderTree
for root in flow_result.anytree:
    for pre, _, node in RenderTree(root):
        print(f"{pre}{node.event} ({node.total_count})")
```

### FlowTreeNode Quick Patterns

```python
for tree in flow_result.trees:
    tree.render()                                     # ASCII visualization
    tree.all_paths()                                  # all root-to-leaf paths
    tree.flatten()                                    # preorder traversal
    tree.find("Purchase")                             # search by event name
    tree.depth                                        # tree depth
    tree.conversion_rate                              # converted / total
    max(tree.flatten(), key=lambda n: n.drop_off_count)  # worst drop-off
```

_Quick patterns here. For tree traversal, pruning, multi-tree comparison, and Graphviz export, see [flows-reference.md](references/flows-reference.md) §anytree Integration Patterns and [advanced-analysis.md](references/advanced-analysis.md) §Tree Analysis._

## Bookmark Validation

_(→ [bookmark-params.md](references/bookmark-params.md) for the complete bookmark JSON structure and all validation rules across report types)_

All typed query methods (`query()`, `query_funnel()`, `query_retention()`, `query_flow()`) validate automatically before API calls. For manually constructed bookmark params, use the built-in `validate_bookmark()` function:

```python
from mixpanel_data import validate_bookmark

errors = validate_bookmark(params, bookmark_type="insights")  # or "funnels", "retention", "flows"
if errors:
    for e in errors:
        print(f"{e.code}: {e.message} (path: {e.path})")
```

## Error Handling

```python
from mixpanel_data.exceptions import (
    AuthenticationError,       # 401 — bad credentials
    RateLimitError,            # 429 — back off and retry
    QueryError,                # 400 — bad parameters
    BookmarkValidationError,   # pre-flight validation failure
    JQLSyntaxError,            # 412 — JQL script error
    WorkspaceScopeError,       # workspace_id required for App API
    ConfigError,               # credentials not configured
    ProjectNotFoundError,      # project ID not found in /me response
)
```

If `AuthenticationError` or `ConfigError`: check credentials with auth_manager.py and suggest `/mp-auth`. If `RateLimitError`: wait briefly and retry. If `BookmarkValidationError`: inspect `e.errors` for structured diagnostics with fix suggestions.

## Additional References

Load these on demand when the quick reference above is insufficient:

| Reference | When to load |
|-----------|-------------|
| [query-taxonomy.md](references/query-taxonomy.md) | Complex multi-engine question decomposition, 50+ NL→engine mappings, join strategies |
| [insights-reference.md](references/insights-reference.md) | Deep insights API: all MathTypes, PerUserAggregation, Filter methods, GroupBy, Formula, gotchas |
| [funnels-reference.md](references/funnels-reference.md) | Deep funnels API: FunnelStep, Exclusion, HoldingConstant, conversion windows, session math |
| [retention-reference.md](references/retention-reference.md) | Deep retention API: RetentionEvent, alignment, custom buckets, cohort analysis patterns |
| [flows-reference.md](references/flows-reference.md) | Deep flows API: FlowStep, NetworkX graph analysis, anytree traversal, FlowTreeNode methods |
| [cross-query-synthesis.md](references/cross-query-synthesis.md) | Multi-engine join strategies, 10 investigation templates, synthesis patterns |
| [advanced-analysis.md](references/advanced-analysis.md) | Statistical methods, trend analysis, graph algorithms, visualization gallery |
| [analytical-frameworks.md](references/analytical-frameworks.md) | AARRR deep dive, GQM methodology, diagnosis protocol, retention benchmarks |
| [python-api.md](references/python-api.md) | Complete method signatures for all Workspace methods including App API CRUD |
| [bookmark-params.md](references/bookmark-params.md) | Manual bookmark JSON construction for entity management |

**Dashboard Building** (separate skill — `skills/dashboard-builder/`):

| Reference | Content |
|-----------|---------|
| [SKILL.md](../dashboard-builder/SKILL.md) | 8-phase dashboard workflow: investigate → plan → build → layout → verify |
| [dashboard-reference.md](../dashboard-builder/references/dashboard-reference.md) | API types, content actions, layout grid, text card formatting, gotchas |
| [dashboard-templates.md](../dashboard-builder/references/dashboard-templates.md) | 9 purpose-built templates (KPI, Feature Launch, AARRR, Funnel, Retention, etc.) |
| [bookmark-pipeline.md](../dashboard-builder/references/bookmark-pipeline.md) | Query → bookmark → dashboard pipeline for all 4 engines |
| [chart-types.md](../dashboard-builder/references/chart-types.md) | Chart type selection, math types, width recommendations |
