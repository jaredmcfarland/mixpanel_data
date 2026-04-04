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

## SQL Mental Model

Think in SQL, then translate:

```
SQL                              Bookmark params
----------------------------------------------
SELECT COUNT(DISTINCT user)   →  measurement.math: "unique"
SELECT COUNT(*)               →  measurement.math: "total"
SELECT AVG(prop)              →  measurement.math: "average" + measurement.property
FROM events                   →  behavior.name: "<event_name>"
WHERE prop = 'val'            →  sections.filter[] or behavior.filters[]
GROUP BY prop                 →  sections.group[]
GROUP BY time_unit            →  sections.time[].unit + chartType: "line"
LIMIT N                       →  sorting.*.viewNLimit
A / B (ratio)                 →  FormulaShowClause with definition: "A / B"
```

## Report Type Detection

| `bookmark_type` | Params structure | Key indicator |
|---|---|---|
| `"insights"` | `sections` wrapper | `behavior.type: "event"` |
| `"funnels"` | `sections` wrapper | `behavior.type: "funnel"` with `behaviors[]` (2+ steps) |
| `"retention"` | `sections` wrapper | `behavior.type: "retention"` with `behaviors[]` (exactly 2) |
| `"flows"` | **Flat structure** (no `sections`) | Top-level `steps[]` and `date_range` |

---

## Insights Params

### Skeleton

```json
{
  "displayOptions": {"chartType": "<type>"},
  "sections": {
    "show": [/* metrics and/or formulas */],
    "time": [/* date range */],
    "filter": [/* global WHERE clauses */],
    "group": [/* GROUP BY breakdowns */]
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
| `stacked-bar` / `stacked-line` | Composition; use `plotStyle: "stacked"` with bar/line |

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
| `unique_values` | `COUNT(DISTINCT property)` |
| `histogram` | Distribution buckets |

#### Per-User Aggregation

Set `measurement.perUserAggregation` to `total`, `average`, `min`, `max`, or `unique_values`. This aggregates per user first, then applies `math` across users.

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

---

## Funnels Params

Uses `sections` wrapper like insights, but with `behavior.type: "funnel"` and steps in `behavior.behaviors[]`.

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
| `funnelOrder` | `"loose"` | `loose` = any order, `any` = strict order |

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

Uses `sections` wrapper with `behavior.type: "retention"` and exactly 2 behaviors: born event (index 0) and return event (index 1).

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

Flows use a **completely different flat structure** — no `sections` wrapper.

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
result = ws.query_flows(bookmark_id)
```

## Constraints

- **Funnels require 2+ steps** in `behavior.behaviors[]`
- **Retention requires exactly 2 events** — born (index 0) and return (index 1)
- **Flows do NOT use `sections`** — completely flat structure
- **String filter values for `equals`/`does not equal` must be arrays**: `["Chrome"]` not `"Chrome"`
- **`bar` gives aggregate totals; `line` gives time-series** — unique counts in `line` are NOT additive across periods
- **When formulas exist**, set `isHidden: true` on raw metric show clauses
- **Math types are context-dependent** — insights math != funnels math != retention math
