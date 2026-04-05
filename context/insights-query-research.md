# Insights Query System Research

Research into Mixpanel's "insights" bookmark query system to inform the design of a typed Python `query()` method for mixpanel_data.

---

## 1. Bookmark Schema & Structure

### 1.1 The Two Bookmark APIs

mixpanel_data exposes bookmarks through two distinct API layers:

**Discovery API** (`list_bookmarks`) — returns lightweight `BookmarkInfo` dataclasses via the legacy bookmarks endpoint. Fields: `id`, `name`, `type`, `project_id`, `created`, `modified`, plus optional `workspace_id`, `dashboard_id`, `description`, `creator_id`, `creator_name`.

**App API v2** (`list_bookmarks_v2`, `create_bookmark`, etc.) — returns full `Bookmark` Pydantic models with the complete `params` dict, permissions, view counts, and metadata. This is the API that matters for query construction.

Source: `src/mixpanel_data/types.py:2860-2991` (Bookmark model), `src/mixpanel_data/workspace.py:2233-2264` (list_bookmarks_v2)

### 1.2 Bookmark Type Constants

```python
# types.py:168-177
BookmarkType = Literal["insights", "funnels", "retention", "flows", "launch-analysis"]

# Analytics internal constants (webapp/bookmarks/models.py:79-95)
class TYPED_BOOKMARK_TYPES:
    INSIGHTS = "insights"
    SEGMENTATION = "segmentation3"  # Legacy — auto-converts to insights on read
    RETENTION = "retention"
    FUNNELS = "funnels"
    FLOWS = "flows"
    IMPACT = "launch-analysis"
```

The legacy `segmentation3` type is transparently converted to `insights` during serialization. The API never returns `segmentation3` — this conversion is invisible to consumers.

### 1.3 The `params` Field — Heart of the System

The `params` field on a Bookmark is a `dict[str, Any]` — an opaque JSON blob that encodes the entire query definition. Its structure varies by bookmark type but follows a consistent pattern for insights, funnels, and retention (flows is the exception).

**Top-level structure for insights/funnels/retention:**

```json
{
  "sections": {
    "show":   [],   // SELECT — metrics to compute (REQUIRED, min 1)
    "filter": [],   // WHERE — global filters across all metrics
    "group":  [],   // GROUP BY — property breakdowns
    "time":   [],   // Time range + granularity (REQUIRED, exactly 1)
    "formula": []   // Computed columns referencing metrics by letter (A, B, C...)
  },
  "displayOptions": {
    "chartType": "line",       // REQUIRED — visualization type
    "plotStyle": "standard",   // Optional: "standard" | "stacked"
    "analysis": "linear",      // Optional: "linear" | "rolling" | "cumulative"
    "rollingWindowSize": 7     // Optional — for rolling analysis
  },
  "queryLimits": { "limit": 3000 },  // Optional — result row limit
  "use_query_cache": true,           // Optional
  "use_query_sampling": false        // Optional
}
```

**Flows uses a completely flat structure (no `sections` wrapper):**

```json
{
  "steps": [{ "event": "...", "forward": 3, "reverse": 0, ... }],
  "date_range": { "type": "in the last", "from_date": {...}, "to_date": "$now" },
  "chartType": "sankey",
  "count_type": "unique",
  "cardinality_threshold": 10,
  "version": 2
}
```

### 1.4 The SQL Mental Model

The `sections` structure maps directly to SQL concepts:

| Section | SQL Analog | Purpose |
|---------|-----------|---------|
| `sections.show[]` | `SELECT` | Each entry = one metric column |
| `sections.filter[]` | `WHERE` | Global filters applied to all metrics |
| `sections.group[]` | `GROUP BY` | Property breakdowns |
| `sections.time[]` | `GROUP BY time` | Implicit time dimension + granularity |
| `displayOptions.chartType` | — | Presentation only (but `bar` vs `line` affects aggregation semantics) |
| `formula[]` | Computed columns | Reference metrics by position letter (A, B, C...) |

Source: `mixpanel-plugin/skills/mixpanel-analyst/references/bookmark-params.md`

### 1.5 Show Clause — Metric Definition

Each entry in `sections.show` defines one metric. Two formats exist:

**Metric format:**

```json
{
  "type": "metric",
  "behavior": {
    "type": "event",            // "event" | "custom-event" | "cohort" | "people" | "funnel" | "retention"
    "name": "Sign Up",          // Event name or identifier
    "resourceType": "events",   // "events" | "people" | "cohorts"
    "filtersDeterminer": "all", // "all" | "any" — how per-metric filters combine
    "filters": [],              // Per-metric filters (same structure as section.filter)
    "dataGroupId": null,        // Optional — for group analytics
    "behaviors": [],            // Nested behaviors (funnels: 2+ steps, retention: exactly 2)
    "dataset": "mixpanel"       // Data source
  },
  "measurement": {
    "math": "total",            // Aggregation operator (see §1.6)
    "property": null,           // Required for property-based math (average, sum, etc.)
    "perUserAggregation": null,  // Optional — aggregate per-user first, then across users
    "rolling": null,            // Optional — rolling window config
    "cumulative": false         // Optional — cumulative aggregation
  },
  "isHidden": false             // Hide from visualization (useful when consumed by formula)
}
```

**Formula format:**

```json
{
  "type": "formula",
  "name": "Conversion Rate",
  "definition": "(B / A) * 100",  // Letters reference metrics by position
  "measurement": {},
  "referencedMetrics": []
}
```

Letters A-Z reference metrics by their position in the `show` array. When formulas are present, the raw metrics they reference are typically marked `isHidden: true`.

### 1.6 Aggregation Operators (math types)

Math types are **context-dependent** — different operators are valid for insights vs funnels vs retention:

**Insights math:**

| Category | Operators |
|----------|----------|
| Counting | `total`, `unique`, `sessions`, `dau`, `wau`, `mau`, `cumulative_unique` |
| Property aggregation (requires `measurement.property`) | `average`, `median`, `min`, `max`, `p25`, `p75`, `p90`, `p99`, `custom_percentile`, `histogram`, `unique_values`, `numeric_summary` |
| Per-user (requires `perUserAggregation`) | First aggregates per user, then across users — like a nested subquery |

**Funnels math:** `unique`, `general`, `session`, `total`, `conversion_rate`, `conversion_rate_unique`, `conversion_rate_total`, `conversion_rate_session`

**Retention math:** `unique`, `retention_rate`, `total`, `average`

**Per-user aggregation values:** `average`, `max`, `min`, `total`, `unique_values`

Source: `analytics/bookmark_parser/insights/validate.py:44-76`

### 1.7 Filter Clause

```json
{
  "resourceType": "events",       // "events" | "people"
  "filterType": "string",         // "string" | "number" | "datetime" | "boolean" | "list" | "object"
  "value": "$browser",            // Property name
  "filterOperator": "equals",     // See operator table below
  "filterValue": ["Chrome"],      // Value(s) to match — format depends on operator
  "filterDateUnit": null,         // For datetime filters
  "determiner": "all",            // "all" | "any" — how multiple filters combine
  "isHidden": false
}
```

**Filter operators by type:**

| Type | Operators |
|------|----------|
| String | `equals`, `does not equal`, `contains`, `does not contain`, `is set`, `is not set` |
| Number | `is equal to`, `is not equal to`, `is greater than`, `is less than`, `is at least`, `is at most`, `is between` |
| Boolean | `true`, `false` |
| DateTime | `was on`, `was before`, `was since` |

**filterValue format varies by operator:**
- `equals` / `does not equal`: array `["Chrome"]`
- `contains` / `does not contain`: plain string `"Chrome"`
- Number operators: numeric `42`
- `is between`: array `[10, 100]`
- `is set` / `is not set`: `null`

### 1.8 Group (Breakdown) Clause

```json
{
  "resourceType": "events",       // "events" | "people"
  "propertyType": "string",       // Property data type
  "propertyDefaultType": "string",
  "propertyName": "$browser",     // Property name
  "value": "$browser",            // Alternative property name field
  "typeCast": null,               // Optional type casting
  "customBucket": null,           // Optional numeric bucketing
  "isHidden": false
}
```

**Numeric bucketing:**

```json
{
  "propertyName": "Amount",
  "propertyType": "number",
  "resourceType": "events",
  "customBucket": { "bucketSize": 10, "min": 0, "max": 100 }
}
```

### 1.9 Time Clause

Multiple value formats exist:

**Relative (last N days):**
```json
{
  "dateRangeType": "in the last",
  "unit": "day",
  "window": { "unit": "day", "value": 30 }
}
```

**Absolute (specific dates):**
```json
{
  "dateRangeType": "between",
  "unit": "day",
  "value": ["2024-01-01", "2024-03-31"]
}
```

**Preset:**
```json
{
  "dateRangeType": "since",
  "value": "$start_of_current_day",
  "unit": "hour"
}
```

Valid time units: `second`, `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year`

### 1.10 Chart Types

| Chart Type | Semantics |
|-----------|----------|
| `line` | Time series — per-period values (unique counts NOT additive across periods) |
| `bar` | Aggregate totals — single number per segment (deduplicated across time range) |
| `column` | Vertical bar variant |
| `pie` | Part-of-whole composition |
| `table` | Tabular detail |
| `insights-metric` | Single KPI number |
| `bar-stacked` | Stacked bar composition |
| `stacked-line` | Stacked line composition |
| `stacked-column` | Stacked column composition |

**Important:** `bar` vs `line` is not purely presentational — it changes aggregation behavior. A `bar` chart with `math: "unique"` deduplicates users across the entire date range. A `line` chart shows per-period unique counts that are NOT additive.

### 1.11 Fields That Drive Query Behavior vs. Presentational

**Query-driving fields:**
- `sections.show[].behavior` — what events/entities to query
- `sections.show[].measurement` — how to aggregate
- `sections.filter[]` — what to filter
- `sections.group[]` — how to break down
- `sections.time[]` — date range and granularity
- `sections.formula[]` — computed metrics
- `displayOptions.chartType` — affects aggregation semantics (bar vs line)
- `displayOptions.analysis` — linear vs rolling vs cumulative
- `displayOptions.rollingWindowSize` — rolling window size
- `queryLimits` — result row limits

**Presentational-only fields:**
- `displayOptions.plotStyle` — standard vs stacked rendering
- `displayOptions.theme` — color/styling
- `displayOptions.primaryYAxisOptions` — Y-axis customization
- `sections.show[].isHidden` — visibility in chart (but still computed)
- `use_query_cache` — performance hint
- `use_query_sampling` — performance hint

---

## 2. Mixpanel Internals

### 2.1 Database Model

The Django `TypedBookmark` model (`webapp/bookmarks/models.py:209-377`) stores:

| Field | Type | Notes |
|-------|------|-------|
| `id` | int (auto) | Primary key |
| `project` | FK(Info) | Parent project |
| `user` | FK(User) | Creator |
| `type` | CharField(255) | Bookmark type identifier |
| `name` | CharField(255) | User-defined name |
| `params` | TextField | JSON blob — the entire query definition |
| `dashboard` | FK(Dashboard, null) | Optional parent dashboard |
| `workspace` | FK(Workspace, null) | Optional workspace scope |
| `is_visibility_restricted` | bool | Access control |
| `is_modification_restricted` | bool | Access control |
| `generation_type` | Enum | USER_CREATED, TEMPLATE_GENERATED, RCA_GENERATED, etc. |
| `created` / `modified` | datetime | Timestamps |
| `deleted` | datetime(null) | Soft delete |

### 2.2 Validation Pipeline

When a bookmark is created or updated, validation happens in `webapp/app_api/projects/bookmarks/views.py:886-918`:

```python
bookmark_params = json.loads(fields.get("params"))
if bookmark_type == "insights" or "sections" in bookmark_params:
    validate_insights_bookmark_params_schema(bookmark_params)

    # Enforce per-project metric count limit
    metrics_limit = get_insights_metrics_limit(project.id)
    number_of_metrics = len(bookmark_params.get("sections", {}).get("show", []))
    if number_of_metrics > metrics_limit:
        raise ValidationError(f"Too many metrics. Limit: {metrics_limit}")
```

The schema validation (`bookmark_parser/insights/validate.py:537-766`) uses the `voluptuous` library. It validates:
- Required keys: `sections.show` (min 1), `sections.time`, `displayOptions.chartType`
- Valid math operators per behavior type
- Property requirements for property-based math (average requires `measurement.property`)
- Funnel: minimum 2 steps in `behavior.behaviors`
- Retention: exactly 2 events in `behavior.behaviors`
- Filter operator validity per filter type

**Key insight:** Validation is lenient on missing optional keys — it only hard-fails on missing `show`, `time`, or `filter` sections. Other missing keys log warnings but proceed.

### 2.3 Bookmark-to-Query Conversion

Bookmarks are not executed directly. A conversion layer (`api/version_2_0/insights/bookmark.py:285-320`) transforms bookmark params into `InsightsParams` for the query engine:

```python
def create_param_sections_from_bookmark(bookmark_params):
    """Transforms bookmark sections into query-ready sections."""
    sections = {}

    # 1. Process standard sections — filter attributes allowed per section
    for section in VALID_SECTIONS:  # show, group, filter, time, cohorts, formula
        for clause in bookmark_params["sections"].get(section.name, []):
            converted_clause = convert_clause(section, clause)
            sections[section.name].append(converted_clause)

    # 2. Show section transforms (rolling, cumulative)
    sections["show"] = transform_show_section(
        show_section=sections["show"],
        analysis=bookmark_params["displayOptions"].get("analysis"),
        rolling_window_size=bookmark_params["displayOptions"].get("rollingWindowSize")
    )

    # 3. Time section transforms — normalize multiple value formats
    sections["time"] = _bm_time_clause_to_insights_params_time_section(
        bookmark_params["sections"]["time"][0]
    )

    return sections
```

The allowed attributes per section are explicitly defined:
- **SHOW_SECTION**: accepts all non-nil attributes
- **GROUP_SECTION**: behavior, customPropertyId, customProperty, value, resourceType, propertyType, typeCast, unit, customBucket, cohorts, isHidden, and ~10 more
- **FILTER_SECTION**: behavior, customPropertyId, value, resourceType, determiner, filterType, filterOperator, filterValue, filterDateUnit, listItemFilters, profileHistoryOptions, isHidden, and ~8 more

### 2.4 Time Clause Conversion

The time clause supports multiple value formats that get normalized:

```python
def _bm_time_clause_to_insights_params_time_section(bm_time_clause):
    time_section = {"time_aggregation_unit": bm_time_clause.get("unit")}

    value = bm_time_clause.get("value")
    if isinstance(value, list):       # Absolute: ["2024-01-01", "2024-03-31"]
        time_section["from_date"] = value[0]
        time_section["to_date"] = value[1] if len(value) > 1 else None
    elif isinstance(value, int):      # Relative: 30 (with unit)
        time_section["window"] = {"value": value, "unit": bm_time_clause["unit"]}
    elif isinstance(value, str):      # Preset: "$start_of_current_day"
        time_section["relative_date"] = value
    # Also handles "window" sub-object and "dateRangeType" variants
```

### 2.5 Query Execution

The `InsightsParams` class (`api/version_2_0/insights/params.py:227-300`) takes converted bookmark params and:
1. Parses behaviors into event selectors
2. Validates filter conditions
3. Sets up time context
4. Configures query limits (defaults: 3,000 for insights, 200 for funnels/retention)
5. Prepares grouping/segmentation

### 2.6 Entity Reference Tracking

A post-save signal handler (`webapp/bookmarks/models.py:586-715`) tracks which events and properties each bookmark references. This powers the "used in" feature in the Lexicon UI and enables impact analysis when events/properties are renamed or removed.

### 2.7 Legacy Type Conversion

`segmentation3` type bookmarks are transparently converted to `insights` during serialization:

```python
if bookmark.type == TYPED_BOOKMARK_TYPES.SEGMENTATION:
    params_override = segmentation_params_to_insights(params)
    bookmark.add_serialization_overrides(type="insights", params=json.dumps(params_override))
```

**Implication for API design:** We never need to handle `segmentation3` — the API always returns `insights`.

### 2.8 Bookmark Migrations

Before serialization, bookmarks pass through `run_bookmark_migrations()` which upgrades legacy param formats. This means the `params` structure evolves over time, and the API always returns the latest format.

---

## 3. JQL (JavaScript Query Language)

### 3.1 Status: Maintenance Mode

JQL is **deprecated** and Mixpanel recommends discontinuing use. From the official docs:

> JQL is currently in maintenance mode. We recommend using alternative methods:
> - Raw Event export: Export API or Data Pipelines
> - User Profile export: Engage Query API or Data Pipelines
> - Other reporting: Query API or in-app Core Reports

Source: `context/jql.md`

### 3.2 Current Exposure in mixpanel_data

```python
# workspace.py:1034
def jql(self, script: str, params: dict[str, Any] | None = None) -> JQLResult:
    """Execute a JQL (JavaScript Query Language) query."""
```

JQL is also used internally by several discovery methods for generating insights:
- `property_distribution()` — uses JQL to compute property value distributions
- `numeric_summary()` — uses JQL to compute statistical summaries of numeric properties

### 3.3 JQL Design Patterns Worth Noting

Despite deprecation, JQL's design has patterns relevant to API design:

**Data Sources:**
```javascript
Events({
    from_date: "2024-01-01",
    to_date: "2024-01-31",
    event_selectors: [
        {event: "Purchase"},
        {event: "Purchase", selector: 'properties["amount"] > 100'},
    ]
})
```

**Chainable Transformations:**
```javascript
Events({...})
    .filter(e => e.properties.amount > 100)
    .groupBy(["properties.country"], mixpanel.reducer.count())
    .sortDesc("value")
```

**Built-in Reducers:**
`count()`, `sum(accessor)`, `avg(accessor)`, `min(accessor)`, `max(accessor)`, `numeric_percentiles(accessor, [50, 90, 99])`, `numeric_summary(accessor)`

**Key takeaway:** JQL's fluent chaining and declarative reducer pattern is a proven UX model. However, JQL's flexibility makes it impossible to optimize server-side — which is why Mixpanel is moving away from it. A typed Python API should provide the declarative ergonomics without the unconstrained flexibility.

### 3.4 Relationship to Bookmarks

JQL and bookmarks are **independent** systems:
- Bookmarks use the insights/segmentation query engine (structured JSON params → optimized query plan)
- JQL executes arbitrary JavaScript against the raw event stream
- You cannot save a JQL script as a bookmark
- Bookmarks cannot express arbitrary JQL logic

The overlap is conceptual — both answer analytics questions — but they use completely different execution paths.

---

## 4. Current mixpanel_data Capabilities

### 4.1 Query Methods (Direct API)

These methods call the Mixpanel Query API directly with typed parameters:

```python
# Time-series event counts with optional breakdown and filter
ws.segmentation(
    event="Login",
    from_date="2025-01-01", to_date="2025-01-31",
    unit="day",                                   # day | week | month
    on='properties["platform"]',                  # breakdown property
    where='properties["country"] == "US"',         # filter expression
) -> SegmentationResult

# Funnel conversion analysis (requires pre-saved funnel)
ws.funnel(
    funnel_id=12345,
    from_date="2025-01-01", to_date="2025-01-31",
    on='properties["platform"]',                  # optional breakdown
) -> FunnelResult

# Cohort retention analysis
ws.retention(
    born_event="Sign Up", return_event="Login",
    from_date="2025-01-01", to_date="2025-01-31",
    born_where='properties["source"] == "organic"', # filter on birth event
    return_where=None,                               # filter on return event
    interval=1, interval_count=10,
    unit="day",                                      # day | week | month
) -> RetentionResult

# JQL (deprecated but functional)
ws.jql(script="function main() { ... }") -> JQLResult

# Multi-event time series
ws.event_counts(
    events=["Login", "Signup"],
    from_date="2025-01-01", to_date="2025-01-31",
    type="general",  # general | unique | average
    unit="day",
) -> EventCountsResult

# Event counts broken down by property values
ws.property_counts(
    event="Purchase", property_name="platform",
    from_date="2025-01-01", to_date="2025-01-31",
    type="general", unit="day",
    values=["iOS", "Android"], limit=10,
) -> PropertyCountsResult

# Numeric property aggregation
ws.segmentation_sum(event="Purchase", on='properties["revenue"]', ...) -> NumericSumResult
ws.segmentation_average(event="Purchase", on='properties["duration"]', ...) -> NumericAverageResult
ws.segmentation_numeric(event="Purchase", on='properties["price"]', ...) -> NumericBucketResult

# Frequency distribution
ws.frequency(event="Purchase", from_date=..., to_date=..., unit="day") -> FrequencyResult

# Statistical summaries (uses JQL internally)
ws.property_distribution(event="Purchase", property="amount", ...) -> PropertyDistributionResult
ws.numeric_summary(event="Purchase", property="amount", ...) -> NumericPropertySummaryResult
```

Source: `src/mixpanel_data/workspace.py:923-1443`

### 4.2 Bookmark-Based Queries

```python
# Execute a saved report by ID (routes to correct API endpoint based on type)
ws.query_saved_report(
    bookmark_id=12345,
    bookmark_type="insights",     # insights | funnels | retention | flows
    from_date=None, to_date=None, # optional date override
) -> SavedReportResult

# Execute a saved flows report
ws.query_flows(bookmark_id=789) -> FlowsResult
```

### 4.3 Bookmark CRUD

```python
ws.list_bookmarks(bookmark_type="insights") -> list[BookmarkInfo]
ws.list_bookmarks_v2(bookmark_type="insights", ids=[1,2,3]) -> list[Bookmark]
ws.create_bookmark(CreateBookmarkParams(name="...", bookmark_type="insights", params={...})) -> Bookmark
ws.get_bookmark(12345) -> Bookmark
ws.update_bookmark(12345, UpdateBookmarkParams(name="Renamed", params={...})) -> Bookmark
ws.delete_bookmark(12345) -> None
ws.bulk_delete_bookmarks([1, 2, 3]) -> None
ws.bulk_update_bookmarks([BulkUpdateBookmarkEntry(id=1, name="...")]) -> None
ws.bookmark_linked_dashboard_ids(12345) -> list[int]
ws.get_bookmark_history(12345, cursor=None, page_size=10) -> BookmarkHistoryResponse
```

### 4.4 Filter Expression System

The `where` parameter on query methods accepts Mixpanel's filter expression language:

```python
# Property access
'properties["browser"] == "Chrome"'
'user["plan_type"] == "premium"'

# Comparison operators
'properties["age"] > 18'
'properties["price"] >= 10 and properties["price"] <= 100'

# Logical operators
'properties["plan"] == "premium" and properties["active"] == true'
'properties["source"] == "web" or properties["source"] == "mobile"'
'not properties["beta_user"]'

# Set operations
'properties["country"] in ["US", "CA", "UK"]'

# String contains
'properties["email"] contains "@company.com"'

# Existence checks
'defined(properties["email"])'

# Date comparisons
'properties["created"] > datetime(2024, 1, 1)'
```

**Expression normalization** (`_internal/expressions.py`): The `on` parameter for segmentation automatically wraps bare property names:
- `"country"` → `'properties["country"]'`
- `'properties["country"]'` → passes through unchanged

This convenience only applies to `on` (breakdown), not to `where` (filter).

Source: `context/mixpanel-query-expression-language.md`

### 4.5 What's Easy, What's Painful, What's Impossible

**Easy (one method call):**
- Single event count over time: `ws.segmentation(event="Login", ...)`
- Single event breakdown by one property: `ws.segmentation(event="Login", on="platform", ...)`
- Saved funnel analysis: `ws.funnel(funnel_id=123, ...)`
- Cohort retention: `ws.retention(born_event="Signup", return_event="Login", ...)`
- Execute any saved report: `ws.query_saved_report(bookmark_id=456)`

**Painful (requires bookmark JSON construction):**
- Multi-metric comparisons (e.g., signups vs purchases over time)
- Formula-based metrics (e.g., conversion rate = purchases / signups)
- Per-user aggregation (e.g., average revenue per user per week)
- Multiple breakdowns simultaneously
- Complex per-metric filters (different filters on different metrics)
- Property aggregations with percentiles (p90 response time)

**Impossible without bookmark JSON:**
- DAU/WAU/MAU metrics (only available through bookmark `math: "dau"`)
- Cumulative unique counts
- Rolling window analysis
- Histogram distributions via the insights engine
- Custom percentiles (p99, custom_percentile)
- Funnel/retention queries with arbitrary step definitions (not saved)

**Impossible entirely:**
- Ad-hoc funnel queries (must use a saved funnel_id or construct bookmark params)
- Cross-project queries
- Real-time streaming with bookmark-style aggregations

### 4.6 The `params: dict[str, Any]` Gap

The critical gap: `CreateBookmarkParams.params` is typed as `dict[str, Any]`. Users must hand-construct a complex nested JSON structure with no type safety, no autocompletion, and no validation until runtime. The plugin's `validate_bookmark.py` script provides client-side validation, but it's external to the library API.

---

## 5. Common Query Patterns

### Pattern 1: Event Count Over Time
**Intent:** How many times did event X happen per day/week/month?
**Difficulty:** Easy — `ws.segmentation()` handles this directly.
**Bookmark params:**
```json
{
  "sections": {
    "show": [{
      "type": "metric",
      "behavior": { "type": "event", "name": "Login", "resourceType": "events", "filters": [] },
      "measurement": { "math": "total" }
    }],
    "time": [{ "dateRangeType": "in the last", "unit": "day", "window": { "unit": "day", "value": 30 }}],
    "filter": [], "group": []
  },
  "displayOptions": { "chartType": "line" }
}
```

### Pattern 2: Unique Users Over Time
**Intent:** How many distinct users performed event X per day?
**Difficulty:** Easy for `ws.segmentation()` with `type="unique"`, but bookmark `math: "unique"` is more powerful (supports `dau`/`wau`/`mau` variants).
**Bookmark params:** Same as Pattern 1 but `"math": "unique"`.

### Pattern 3: Segmentation by Property
**Intent:** Break down event counts by a property (e.g., platform, country).
**Difficulty:** Easy — `ws.segmentation(on="platform")`.
**Bookmark params:** Same as Pattern 1 plus `"group": [{ "resourceType": "events", "propertyType": "string", "propertyName": "platform", "value": "platform" }]`.

### Pattern 4: Filtered Aggregation
**Intent:** Count events matching a condition (e.g., purchases > $100 in the US).
**Difficulty:** Medium — `ws.segmentation(where='...')` works for simple cases, but combining global and per-metric filters requires bookmark JSON.
**Bookmark params:** Adds `"filter": [{ "resourceType": "events", "filterType": "string", "value": "country", "filterValue": ["US"], "filterOperator": "equals" }]` to sections.

### Pattern 5: Multi-Metric Comparison
**Intent:** Show signups AND purchases on the same chart.
**Difficulty:** Painful — requires constructing bookmark JSON with multiple show clauses. No direct API method.
**Bookmark params:** Two entries in `sections.show[]`, each with different `behavior.name`.

### Pattern 6: Conversion Rate Formula
**Intent:** Compute purchases / signups * 100 over time.
**Difficulty:** Painful — requires bookmark with two hidden metrics + formula.
**Bookmark params:**
```json
{
  "sections": {
    "show": [
      { "type": "metric", "behavior": { "name": "Sign Up" }, "measurement": { "math": "unique" }, "isHidden": true },
      { "type": "metric", "behavior": { "name": "Purchase" }, "measurement": { "math": "unique" }, "isHidden": true },
      { "type": "formula", "name": "Conversion Rate", "definition": "(B / A) * 100" }
    ]
  }
}
```

### Pattern 7: Property Aggregation (Revenue, Duration)
**Intent:** Average purchase amount over time.
**Difficulty:** Medium — `ws.segmentation_average()` handles this, but percentiles/histograms need bookmark JSON.
**Bookmark params:** `"measurement": { "math": "average", "property": { "name": "Amount", "type": "number", "resourceType": "events" } }`.

### Pattern 8: DAU / WAU / MAU
**Intent:** Track daily/weekly/monthly active users.
**Difficulty:** Impossible without bookmark — no direct API method. Must use `math: "dau"` in bookmark params.
**Bookmark params:** `"measurement": { "math": "dau" }` (or `"wau"`, `"mau"`).

### Pattern 9: Per-User Aggregation
**Intent:** Average number of purchases per user per week (aggregate per-user first, then across users).
**Difficulty:** Painful — requires bookmark with `perUserAggregation`.
**Bookmark params:** `"measurement": { "math": "average", "perUserAggregation": "total" }`.

### Pattern 10: Ad-Hoc Funnel
**Intent:** What % of users who did A then did B within 7 days?
**Difficulty:** Painful — requires constructing full funnel bookmark params. Currently `ws.funnel()` requires a pre-saved `funnel_id`.
**Bookmark params:**
```json
{
  "sections": {
    "show": [{
      "type": "metric",
      "behavior": {
        "type": "funnel", "name": "funnel", "resourceType": "events",
        "conversionWindowDuration": 7, "conversionWindowUnit": "day",
        "funnelOrder": "loose",
        "behaviors": [
          { "type": "event", "name": "Sign Up", "filters": [] },
          { "type": "event", "name": "Purchase", "filters": [] }
        ]
      },
      "measurement": { "math": "unique" }
    }]
  },
  "displayOptions": { "chartType": "funnel-steps" }
}
```

### Pattern 11: Retention Curve
**Intent:** Of users who signed up, what % came back to do X in week 1, 2, 3...?
**Difficulty:** Easy for basic use — `ws.retention()`. Bookmark needed for segmented retention or custom settings.
**Bookmark params:**
```json
{
  "sections": {
    "show": [{
      "behavior": {
        "type": "retention", "retentionType": "birth", "retentionUnit": "day",
        "behaviors": [
          { "type": "event", "name": "Sign Up" },
          { "type": "event", "name": "Login" }
        ]
      },
      "measurement": { "math": "retention_rate" }
    }]
  },
  "displayOptions": { "chartType": "retention-curve" }
}
```

### Pattern 12: Rolling Average
**Intent:** 7-day rolling average of daily signups.
**Difficulty:** Impossible without bookmark — no direct API method. Requires `displayOptions.analysis: "rolling"` and `rollingWindowSize: 7`.

### Pattern 13: Multiple Breakdowns
**Intent:** Break down purchases by platform AND country simultaneously.
**Difficulty:** Painful — requires bookmark JSON with multiple entries in `sections.group[]`.

### Pattern 14: Cohort Comparison
**Intent:** Compare behavior of users from cohort A vs cohort B.
**Difficulty:** Painful — requires bookmark JSON with cohort behavior type.

---

## 6. Design Implications

### 6.1 Critical Findings

**The bookmark params structure IS the query language.** There is no simpler underlying query primitive for multi-metric, formula-based, or advanced aggregation queries. The conversion layer (`create_param_sections_from_bookmark`) simply validates and normalizes — it doesn't transform the structure significantly. A typed Python API must generate valid bookmark params JSON.

**The existing Query API methods are a subset.** `ws.segmentation()`, `ws.funnel()`, `ws.retention()` cover ~40% of what the insights engine can do. The remaining 60% (multi-metric, formulas, DAU/WAU/MAU, per-user aggregation, rolling windows, histograms, custom percentiles, ad-hoc funnels) is only accessible through bookmark params construction.

**Chart type affects semantics.** `bar` vs `line` changes deduplication behavior for unique counts. This is not purely presentational — the API must understand this distinction.

**Filter syntax differs between layers.** The `where` parameter on `ws.segmentation()` uses Mixpanel's expression language (`properties["x"] == "y"`). Bookmark filters use a structured JSON format (`filterOperator: "equals"`, `filterValue: ["y"]`). These are two different filter systems that cannot be interchanged.

### 6.2 What Matters Most for API Design

1. **Type-safe metric construction** — The show clause is the most complex and error-prone part. Users need typed builders for event metrics, property aggregations, formulas, and per-user aggregations.

2. **Filter builder** — Converting between human-readable filters and the JSON filter format is a major pain point. A fluent builder or expression parser would eliminate most validation errors.

3. **Time range normalization** — The four different time clause formats (relative window, absolute dates, presets, legacy int values) should collapse to a simple interface.

4. **Report type routing** — The API should handle insights vs funnel vs retention differences internally. Users shouldn't need to know that funnels need `behavior.type: "funnel"` with `behaviors[]` containing 2+ steps.

5. **Validation before API call** — The plugin's `validate_bookmark.py` proves that client-side validation catches most errors. This should be built into the typed API.

### 6.3 What We Can Safely Ignore

1. **JQL** — Deprecated, separate execution path, doesn't interact with bookmarks. Not relevant to `query()` design.

2. **Legacy segmentation3 type** — Auto-converted server-side. We never see it.

3. **Bookmark migrations** — Server-side concern. We always receive the latest format.

4. **Entity reference tracking** — Server-side feature. No impact on query construction.

5. **Permission fields** — `is_visibility_restricted`, `is_modification_restricted`, etc. are CRUD concerns, not query concerns.

6. **Most displayOptions fields** — `theme`, `primaryYAxisOptions`, `plotStyle` are presentational. The exception is `chartType` and `analysis`/`rollingWindowSize` which affect query behavior.

7. **Flows** — Completely different structure (flat, no `sections`). Should be handled separately, not unified with insights/funnels/retention.

### 6.4 Ambiguities and Risks

**Underdocumented areas:**
- The exact semantics of `perUserAggregation` combinations (which `math` + `perUserAggregation` pairs are valid?)
- Custom percentile configuration (how is `custom_percentile` parameterized?)
- Multi-attribution settings (`measurement.multiAttribution`)
- Session-based math (`sessions` math type, `session` conversion window unit)
- The `cohort` behavior type in show clauses — how does it differ from `event`?
- `listItemFilters` and `profileHistoryOptions` — complex nested filter structures for list/object properties

**Validation edge cases:**
- The server validation is lenient on missing optional keys — it logs warnings but proceeds. Our client-side validation should match this leniency or risk rejecting valid queries.
- Per-project metric count limits are configurable — we can't validate this client-side without an API call.
- The relationship between `filterValue` format and `filterOperator` is implicit — there's no schema that says "equals requires an array, contains requires a string."

**Behavioral subtleties:**
- `bar` chart with `math: "unique"` deduplicates across the entire date range. `line` chart computes per-period. This means the same logical query ("unique users") produces different numbers depending on chart type.
- `isHidden: true` metrics are still computed — they just don't appear in visualization. This is critical for formula support.
- The `group` vs `group_by` keys in sections appear to be aliases — the analytics code accepts both, but `group` is the canonical form.

### 6.5 Key Design Constraints

1. **The `query()` method must produce valid bookmark params JSON** — there is no alternative query format for advanced features.
2. **Two execution paths exist**: (a) create a bookmark then query it by ID, or (b) pass params inline to the insights query endpoint. Path (b) avoids creating persistent state but may have different caching behavior.
3. **Result types already exist** — `SavedReportResult`, `SegmentationResult`, etc. have `.df` properties that produce DataFrames. The new `query()` method should return compatible types.
4. **The filter expression language (for `where`) and the structured filter JSON (for bookmark params) are NOT interchangeable** — the API may need to support both or choose one and provide conversion utilities.
