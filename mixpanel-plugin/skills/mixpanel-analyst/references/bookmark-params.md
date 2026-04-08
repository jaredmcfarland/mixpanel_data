# Bookmark Params Reference — Building Valid Query JSON

How to construct the `params` dict for `Workspace.create_bookmark()` and `Workspace.update_bookmark()`. The `params` field defines what data the report queries — it is the bookmark's query language.

## Quick Start

```python
import mixpanel_data as mp
from mixpanel_data.types import CreateBookmarkParams

ws = mp.Workspace(workspace_id=WORKSPACE_ID)

# Create an insights report
bookmark = ws.create_bookmark(CreateBookmarkParams(
    name="Daily Signups (30d)",
    bookmark_type="insights",
    params={
        "displayOptions": {"chartType": "line"},
        "sections": {
            "show": [{
                "type": "metric",
                "behavior": {
                    "type": "event", "name": "Sign Up",
                    "resourceType": "events",
                    "filtersDeterminer": "all", "filters": []
                },
                "measurement": {"math": "unique"}
            }],
            "time": [{"dateRangeType": "in the last", "unit": "day",
                       "window": {"unit": "day", "value": 30}}],
            "filter": [],
            "group": []
        }
    },
))
```

## Preferred: Use Typed Query Methods

For all report types, prefer the typed query methods which generate valid bookmark params automatically with full validation. Manual bookmark JSON construction is rarely needed.

| Report Type | Preferred Method | Result Type |
|-------------|-----------------|-------------|
| Insights | `ws.query()` | `QueryResult` |
| Funnels | `ws.query_funnel()` | `FunnelQueryResult` |
| Retention | `ws.query_retention()` | `RetentionQueryResult` |
| Flows | `ws.query_flow()` | `FlowQueryResult` |

```python
import mixpanel_data as mp
from mixpanel_data import Metric, Filter, CreateBookmarkParams

ws = mp.Workspace()

# Insights — run a query, then save as a report
result = ws.query("Login", math="dau", group_by="platform", last=90)
ws.create_bookmark(CreateBookmarkParams(
    name="DAU by Platform (90d)",
    bookmark_type="insights",
    params=result.params,
))

# Funnels — same pattern
funnel = ws.query_funnel(["Sign Up", "Purchase"], conversion_window=7)
ws.create_bookmark(CreateBookmarkParams(
    name="Signup to Purchase (7d window)",
    bookmark_type="funnels",
    params=funnel.params,
))

# Retention — same pattern
ret = ws.query_retention("Sign Up", "Login", retention_unit="week")
ws.create_bookmark(CreateBookmarkParams(
    name="Weekly Signup Retention",
    bookmark_type="retention",
    params=ret.params,
))

# Flows — same pattern
flow = ws.query_flow("Purchase", reverse=3)
ws.create_bookmark(CreateBookmarkParams(
    name="Paths to Purchase",
    bookmark_type="flows",
    params=flow.params,
))
```

Use manual bookmark JSON (documented below) only for:
- **Edge cases** where the typed query methods cannot express the exact bookmark structure needed

---

## SQL Mental Model

Bookmark params are a declarative query — like SQL in JSON form. For insights, the `sections` object maps directly to SQL clauses:

```
sections.show[]    →  SELECT        (each show clause = one metric column)
sections.filter[]  →  WHERE         (global — applies to all metrics)
sections.group[]   →  GROUP BY      (property breakdowns)
sections.time[]    →  GROUP BY time (implicit, controls line chart granularity)
sorting            →  ORDER BY / LIMIT
```

Within each show clause:

```
behavior.name         →  FROM <table>       (which event to query)
behavior.filters[]    →  AND <per-metric>   (additional WHERE, scoped to this metric only)
measurement.math      →  aggregate function (COUNT DISTINCT, AVG, SUM, ...)
measurement.property  →  aggregate column   (for AVG/MIN/MAX/percentiles)
```

Formulas reference other metrics by letter (A = first, B = second):

```
definition: "(A / B) * 100"  →  computed column
```

Not all SQL is expressible: no JOINs, no subqueries, no UNION. Formulas are the closest to derived columns. Funnels, retention, and flows go beyond SQL — see their sections below.

## Report Type Detection

| `bookmark_type` | Params structure | Key indicator |
|---|---|---|
| `"insights"` | `sections` wrapper | `behavior.type: "event"` |
| `"funnels"` | `sections` wrapper | `behavior.type: "funnel"` with `behaviors[]` (2+ steps) |
| `"retention"` | `sections` wrapper | `behavior.type: "retention"` with `behaviors[]` (exactly 2) |
| `"flows"` | **Flat structure** (no `sections`) | Top-level `steps[]` and `date_range` |

---

## Insights Params

> **Note:** For new queries, prefer the typed query methods (`ws.query()`, `ws.query_funnel()`, `ws.query_retention()`, `ws.query_flow()`) which generate these params automatically. See "Preferred: Use Typed Query Methods" above. The raw JSON format below is documented for reference.

### Skeleton

```json
{
  "displayOptions": {"chartType": "<type>"},
  "sections": {
    "show": [/* SELECT — metrics and formulas */],
    "time": [/* GROUP BY time — date range + granularity */],
    "filter": [/* WHERE — global filters across all metrics */],
    "group": [/* GROUP BY — property breakdowns */]
  }
}
```

### Chart Types

| chartType | Use case |
|---|---|
| `bar` | Aggregate totals (single number per segment, deduplicated across date range) |
| `line` | Time series (per-period values; NOT additive for unique counts) |
| `table` | Tabular detail |
| `pie` | Part-of-whole composition |
| `column` | Vertical bar |
| `insights-metric` | Single KPI number |
| `bar-stacked` / `stacked-line` / `stacked-column` | Composition; plotStyle is set to `"stacked"` automatically |

### Measurement Math

#### Counting
| math | SQL equivalent |
|---|---|
| `unique` | `COUNT(DISTINCT user_id)` |
| `total` | `COUNT(*)` |
| `sessions` | `COUNT(DISTINCT session_id)` |
| `dau` / `wau` / `mau` | Daily/weekly/monthly active users |

#### Property Aggregation (requires `measurement.property`)
| math | SQL equivalent |
|---|---|
| `average` | `AVG(property)` |
| `median` | `PERCENTILE_CONT(0.5)` |
| `min` / `max` | `MIN` / `MAX` |
| `p25` / `p75` / `p90` / `p99` | Percentiles |
| `custom_percentile` | Custom percentile (set `measurement.percentile`) |
| `unique_values` | `COUNT(DISTINCT property)` |
| `histogram` | Distribution buckets |

#### Per-User Aggregation

Set `measurement.perUserAggregation` to `total`, `average`, `min`, `max`, or `unique_values`. This aggregates per user first, then applies `math` across users — like a nested query: `SELECT AVG(user_total) FROM (SELECT user_id, COUNT(*) as user_total ... GROUP BY user_id)`.

Example — "Average number of purchases per user":
```json
"measurement": {"math": "average", "perUserAggregation": "total"}
```

### Show Clause — Metric

```json
{
  "type": "metric",
  "behavior": {
    "type": "event",
    "name": "Sign Up",
    "resourceType": "events",
    "filtersDeterminer": "all",
    "filters": []
  },
  "measurement": {"math": "unique"}
}
```

With property aggregation:
```json
"measurement": {
  "math": "average",
  "property": {
    "name": "Amount", "dataset": "mixpanel",
    "defaultType": "number", "type": "number",
    "resourceType": "events"
  }
}
```

With custom percentile (e.g. p95):
```json
"measurement": {
  "math": "custom_percentile",
  "percentile": 95,
  "property": {
    "name": "duration_ms", "dataset": "mixpanel",
    "defaultType": "number", "type": "number",
    "resourceType": "events"
  }
}
```

Note: `query()` maps `math="percentile"` to `"custom_percentile"` in bookmark JSON and `percentile_value` to `measurement.percentile`.

### Show Clause — Formula

```json
{
  "type": "formula",
  "name": "Conversion Rate",
  "definition": "(A / B) * 100",
  "measurement": {},
  "referencedMetrics": []
}
```

Letters A-Z reference metrics by position in the `show` array (A = first, B = second).

When formulas are present, set `isHidden: true` on the raw metric show clauses to hide them from visualization.

### Show Clause — Cohort Metric

Tracks cohort size over time. Math is always `unique`.

```json
{
  "type": "metric",
  "behavior": {
    "type": "cohort",
    "name": "Power Users",
    "resourceType": "cohorts",
    "filtersDeterminer": "all",
    "filters": [],
    "id": 12345
  },
  "measurement": {"math": "unique"}
}
```

For inline definitions, replace `"id"` with `"raw_cohort"`:
```json
"behavior": {
  "type": "cohort",
  "name": "Custom Cohort",
  "resourceType": "events",
  "raw_cohort": {"selector": {...}, "behaviors": {...}}
}
```

### Time Clause

Relative (last N days):
```json
{"dateRangeType": "in the last", "unit": "day", "window": {"unit": "day", "value": 30}}
```

Absolute (specific dates):
```json
{"dateRangeType": "between", "unit": "day", "value": ["2024-01-01", "2024-03-31"]}
```

Presets:
```json
{"dateRangeType": "since", "value": "$start_of_current_day", "unit": "hour"}
```

The `unit` field controls time granularity for line charts: `hour`, `day`, `week`, `month`.

### Filter Clause

```json
{
  "resourceType": "events",
  "filterType": "string",
  "defaultType": "string",
  "value": "$browser",
  "filterValue": ["Chrome"],
  "filterOperator": "equals"
}
```

#### Filter Operators

| Property Type | Operators |
|---|---|
| string | `equals`, `does not equal`, `contains`, `does not contain`, `is set`, `is not set` |
| number | `is equal to`, `is not equal to`, `is greater than`, `is less than`, `is at least`, `is at most`, `is between` |
| boolean | `true`, `false` |
| datetime | `was on`, `was before`, `was since` |

#### filterValue Format
- String `equals` / `does not equal`: array `["Chrome"]`
- String `contains` / `does not contain`: plain string `"Chrome"`
- Number operators: numeric `42`
- `is between`: array `[10, 100]`
- `is set` / `is not set`: `null`
- Boolean: `true` / `false`

#### Resource Types
- `"events"` — event properties (`$browser`, `$city`, custom event props)
- `"people"` — user profile properties (`$name`, `$email`, custom user props)

### Cohort Filter Clause

Filters by cohort membership. Uses `filterType: "list"` with `value: "$cohorts"`.

Saved cohort:
```json
{
  "resourceType": "events",
  "filterType": "list",
  "defaultType": "list",
  "value": "$cohorts",
  "filterOperator": "contains",
  "filterValue": [{"cohort": {"id": 12345, "name": "Power Users", "negated": false}}]
}
```

Inline cohort definition:
```json
{
  "resourceType": "events",
  "filterType": "list",
  "defaultType": "list",
  "value": "$cohorts",
  "filterOperator": "contains",
  "filterValue": [{"cohort": {"raw_cohort": {"selector": {...}, "behaviors": {...}}, "name": "Custom Cohort", "negated": false}}]
}
```

For `Filter.not_in_cohort()`, set `"filterOperator": "does not contain"` and `"negated": true`.

### Group (Breakdown) Clause

Event property breakdown:
```json
{
  "resourceType": "events",
  "propertyType": "string", "propertyDefaultType": "string",
  "propertyName": "$browser", "value": "$browser"
}
```

User property breakdown:
```json
{
  "resourceType": "people",
  "propertyType": "string", "propertyDefaultType": "string",
  "propertyName": "Plan", "value": "Plan"
}
```

Numeric bucketing:
```json
{
  "propertyName": "Amount", "propertyType": "number", "propertyDefaultType": "number",
  "resourceType": "events", "value": "Amount",
  "customBucket": {"bucketSize": 10, "min": 0, "max": 100}
}
```

### Cohort Breakdown Clause

Segments results by cohort membership (in vs not-in).

```json
{
  "value": ["Power Users", "Not In Power Users"],
  "resourceType": "events",
  "profileType": null,
  "search": "",
  "dataGroupId": null,
  "propertyType": null,
  "typeCast": null,
  "cohorts": [
    {"name": "Power Users", "negated": false, "data_group_id": null, "id": 12345, "groups": []},
    {"name": "Power Users", "negated": true, "data_group_id": null, "id": 12345, "groups": []}
  ],
  "isHidden": false
}
```

The `value` array contains display labels for each segment. The `cohorts` array contains one entry per segment. When `include_negated=True` (default), a second entry with `"negated": true` creates the "Not In [name]" segment. For inline definitions, replace `"id"` with `"raw_cohort": {"selector": {...}, "behaviors": {...}}` and omit `"groups"`.

---

## Funnels Params

Funnels go beyond simple SQL aggregation — they express sequential event analysis with time constraints (like a self-join with window functions). Uses `sections` wrapper like insights, but with `behavior.type: "funnel"` and ordered steps in `behavior.behaviors[]`.

```json
{
  "displayOptions": {"chartType": "funnel-steps"},
  "sections": {
    "show": [{
      "type": "metric",
      "behavior": {
        "type": "funnel", "name": "funnel",
        "resourceType": "events",
        "filtersDeterminer": "all", "filters": [],
        "conversionWindowDuration": 7, "conversionWindowUnit": "day",
        "funnelOrder": "loose",
        "behaviors": [
          {"type": "event", "name": "Sign Up", "filters": [], "filtersDeterminer": "all"},
          {"type": "event", "name": "Purchase", "filters": [], "filtersDeterminer": "all"}
        ]
      },
      "measurement": {"math": "unique"}
    }],
    "time": [{"dateRangeType": "in the last", "unit": "day", "window": {"unit": "day", "value": 30}}],
    "filter": [], "group": []
  }
}
```

### Funnel-Specific Fields

| Field | Default | Description |
|---|---|---|
| `conversionWindowDuration` | 7 | Max time between first and last step |
| `conversionWindowUnit` | `"day"` | second, minute, hour, day, week, month, session |
| `funnelOrder` | `"loose"` | `loose` = any order, `strict` = steps must be in order |

### Funnel Math Types
`unique`, `general`, `session`, `conversion_rate`, `conversion_rate_unique`, `conversion_rate_total`, `conversion_rate_session`, `total`

### Chart Types
`funnel-steps` (default bar), `funnel-top-paths` (common paths), `line` (conversion trend over time)

### Per-Step Filters

Each step in `behaviors[]` can have inline filters:
```json
{
  "type": "event", "name": "Page View",
  "filtersDeterminer": "all",
  "filters": [{
    "resourceType": "events", "filterType": "string", "defaultType": "string",
    "value": "page_url", "filterValue": ["/pricing"], "filterOperator": "equals"
  }]
}
```

---

## Retention Params

Retention goes beyond SQL — it's cohort analysis, tracking whether users who did event A come back to do event B over time intervals. Uses `sections` wrapper with `behavior.type: "retention"` and exactly 2 behaviors: born event (index 0) and return event (index 1).

```json
{
  "displayOptions": {"chartType": "retention-curve"},
  "sections": {
    "show": [{
      "type": "metric",
      "behavior": {
        "type": "retention", "name": "retention",
        "resourceType": "events",
        "filtersDeterminer": "all", "filters": [],
        "retentionType": "birth", "retentionAlignmentType": "birth",
        "retentionUnit": "day",
        "retentionUnbounded": false, "retentionUnboundedMode": "none",
        "behaviors": [
          {"type": "event", "name": "Sign Up", "filters": [], "filtersDeterminer": "all"},
          {"type": "event", "name": "Login", "filters": [], "filtersDeterminer": "all"}
        ]
      },
      "measurement": {"math": "retention_rate", "retentionBucketIndex": 0, "retentionCumulative": false}
    }],
    "time": [{"dateRangeType": "in the last", "unit": "day", "window": {"unit": "day", "value": 30}}],
    "filter": [], "group": []
  }
}
```

### Retention-Specific Fields

| Field | Default | Description |
|---|---|---|
| `retentionType` | `"birth"` | `birth` = first-time users, `addiction` = any occurrence |
| `retentionAlignmentType` | `"birth"` | `birth` = align to first event |
| `retentionUnit` | `"day"` | Cohort interval: day, week, month |
| `retentionUnbounded` | `false` | Allow unbounded windows |

### Retention Math Types
`unique`, `retention_rate`, `total`, `average`

### Chart Types
`retention-curve` (default), `line` (trend over time)

---

## Flows Params

Flows have no SQL analogy — they're graph traversal, showing the paths users take before and after anchor events. Completely different flat structure — no `sections` wrapper.

```json
{
  "steps": [{
    "event": "Product Viewed",
    "forward": 3, "reverse": 0,
    "bool_op": "and",
    "property_filter_params_list": []
  }],
  "date_range": {
    "type": "in the last",
    "from_date": {"unit": "day", "value": 30},
    "to_date": "$now", "exclusion_offset": null
  },
  "chartType": "sankey",
  "flows_merge_type": "graph",
  "count_type": "unique",
  "cardinality_threshold": 10,
  "version": 2,
  "conversion_window": {"unit": "day", "value": 7},
  "anchor_position": 1,
  "alignment": [1, 0],
  "collapse_repeated": false,
  "show_custom_events": true,
  "hidden_events": []
}
```

### Step Fields

| Field | Default | Description |
|---|---|---|
| `event` | required | Event name |
| `forward` | 0 | Hops to show AFTER this event (0-3) |
| `reverse` | 0 | Hops to show BEFORE this event (0-3) |

### Flows Date Range

Relative:
```json
{"type": "in the last", "from_date": {"unit": "day", "value": 30}, "to_date": "$now", "exclusion_offset": null}
```

Absolute:
```json
{"type": "between", "from_date": "2024-01-01", "to_date": "2024-03-31", "exclusion_offset": null}
```

### Flows Inline Filters

Different format from insights filters:
```json
{
  "property_filter": {
    "filter_type": "string", "filter_operator": "equals",
    "filter_value": ["Chrome"], "property": "$browser",
    "selected_property_type": "string"
  }
}
```

### Chart Types
`sankey` (default Sankey diagram), `paths` (path list table)

### Common Patterns
- **What happens after Sign Up?** — `forward: 3, reverse: 0`
- **What leads to Purchase?** — `forward: 0, reverse: 3`
- **Bidirectional from key event** — `forward: 3, reverse: 2`

---

## Common System Properties

| Property | Type | Resource | Description |
|---|---|---|---|
| `$browser` | string | events | Browser name |
| `$city` | string | events | City |
| `$country_code` | string | events | Country |
| `$os` | string | events | Operating system |
| `$device` | string | events | Device type |
| `$referring_domain` | string | events | Referrer domain |
| `$current_url` | string | events | Page URL |
| `$name` | string | people | User display name |
| `$email` | string | people | User email |
| `$created` | datetime | people | User creation date |
| `$last_seen` | datetime | people | Last activity |

---

## Python Integration

### Create a Bookmark

```python
from mixpanel_data.types import CreateBookmarkParams

bookmark = ws.create_bookmark(CreateBookmarkParams(
    name="Weekly Signups by Platform",
    bookmark_type="insights",
    params={...},  # params dict as described above
    description="Tracks signup volume segmented by platform",
))
print(f"Created bookmark {bookmark.id}: {bookmark.name}")
```

### Update Bookmark Params

```python
from mixpanel_data.types import UpdateBookmarkParams

ws.update_bookmark(bookmark_id, UpdateBookmarkParams(
    params={...},  # new params dict
))
```

### Read Params from Existing Bookmark

```python
bookmark = ws.get_bookmark(bookmark_id)
print(bookmark.params)       # the params dict
print(bookmark.bookmark_type) # insights, funnels, retention, flows
```

### Query a Bookmark

```python
# Insights, funnels, retention
result = ws.query_saved_report(bookmark_id)
df = result.df

# Flows
result = ws.query_saved_flows(bookmark_id)
```

## Validation

**Always validate params before calling `create_bookmark()` or `update_bookmark()`.**

Use the built-in `validate_bookmark()` function from `mixpanel_data`:

```python
from mixpanel_data import validate_bookmark

# Validate with explicit type
errors = validate_bookmark(params, bookmark_type="insights")  # or "funnels", "retention", "flows"
if errors:
    for e in errors:
        print(f"{e.code}: {e.message} (path: {e.path})")
```

The validator checks:
- Required fields (`displayOptions`, `sections`, `sections.show`, `sections.time`)
- Valid `chartType` values (context-dependent: insights vs flows)
- Valid `math` types (context-dependent: insights vs funnels vs retention)
- Filter operators and resource types
- Funnel step count (minimum 2)
- Retention event count (exactly 2)
- Flows structure (`steps[]`, `date_range`)

For queries created via `query()`, `query_funnel()`, `query_retention()`, and `query_flow()`, validation is automatic (45 rules, two layers). Use `validate_bookmark()` directly for manually-constructed params.

---

## Constraints

- **Funnels require 2+ steps** in `behavior.behaviors[]`
- **Retention requires exactly 2 events** — born (index 0) and return (index 1)
- **Flows do NOT use `sections`** — completely flat structure
- **String filter values for `equals`/`does not equal` must be arrays**: `["Chrome"]` not `"Chrome"`
- **`bar` gives aggregate totals; `line` gives time-series** — unique counts in `line` are NOT additive across periods
- **When formulas exist**, set `isHidden: true` on raw metric show clauses
- **Math types are context-dependent** — insights math != funnels math != retention math
