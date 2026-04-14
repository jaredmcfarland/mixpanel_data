# Mixpanel Query API Capability Audit Report

## Executive Summary

A systematic, exhaustive audit of Mixpanel's query API capabilities across three codebases — the mixpanel_data Python library, the Mixpanel analytics server source, and mixpanel-power-tools — reveals **29 confirmed gaps** where capabilities the Mixpanel platform supports are either missing from or suboptimally exposed in the mixpanel_data unified query engine.

| Category | Audited | No Gap | Partial | Confirmed Gap |
|----------|---------|--------|---------|---------------|
| Math types (Insights) | 21 | 14 | 0 | **7** |
| Math types (Funnels) | 14 | 13 | 0 | **1** |
| Math types (Retention) | 4 | 2 | 0 | **2** |
| Per-user aggregation | 6 | 5 | 0 | **1** |
| Segment method | 1 | 0 | 0 | **1** |
| Filter operators | 35 | 22 | 0 | **6 actionable** |
| Behavioral cohorts | 6 | 0 | 0 | **6** |
| Funnel advanced modes | 1 | 0 | 0 | **1** |
| Retention advanced modes | 2 | 0 | 0 | **2** |
| Frequency analysis | 3 | 0 | 0 | **3** |
| Time comparison | 1 | 0 | 0 | **1** |
| Flows advanced features | 5 | 0 | 0 | **5** |
| Group analytics scoping | 1 | 0 | 0 | **1** |
| Custom property formulas | 1 | 1 | 0 | 0 |
| Lookup table joins | 1 | 1 | 0 | 0 |
| Multiple breakdowns | 1 | 1 | 0 | 0 |
| Display options | 6 | 6 | 0 | 0 |

**Confirmed non-gaps**: Custom property formulas (server-evaluated), lookup table joins (server-resolved), multiple breakdowns (already supported via `list[GroupBy]`), display options (data-affecting options already exposed; UI-only options intentionally excluded).

---

## Gap Priority Matrix

| # | Gap | Engine | Severity | Effort | Agent Value |
|---|-----|--------|----------|--------|-------------|
| 1 | Expand `MathType` Literal (7 missing) | Insights | CRITICAL | SMALL | HIGH — unlocks cumulative_unique, sessions, unique_values, most_frequent, first_value, multi_attribution, numeric_summary |
| 2 | Add `segment_method` to `Metric` class | Insights/Funnels/Retention | CRITICAL | SMALL | HIGH — controls first-touch vs all-touch attribution |
| 3 | Add `funnelReentryMode` parameter | Funnels | HIGH | SMALL | HIGH — fundamentally changes funnel calculation |
| 4 | Add `retentionUnboundedMode` parameter | Retention | HIGH | SMALL | HIGH — carry_back/carry_forward/consecutive_forward |
| 5 | Add `retentionCumulative` parameter | Retention | HIGH | TRIVIAL | HIGH — cumulative vs period-over-period retention |
| 6 | Expand `RetentionMathType` (2 missing) | Retention | HIGH | TRIVIAL | MEDIUM — adds total and average math for retention |
| 7 | Add time comparison support | Insights/Funnels/Retention | HIGH | MEDIUM | HIGH — period-over-period overlay analysis |
| 8 | Add bookmark-level frequency analysis | Insights | HIGH | MEDIUM | HIGH — frequency breakdown, frequency filter |
| 9 | Behavioral cohort aggregation operators | All (via cohort filters) | HIGH | MEDIUM | HIGH — "users whose avg purchase > $50" vs just count |
| 10 | Add missing `Filter` factory methods | All | MEDIUM | SMALL | MEDIUM — not_between, starts_with, ends_with, numeric aliases, date operators |
| 11 | Add `FunnelMathType` histogram | Funnels | MEDIUM | TRIVIAL | LOW — niche use case |
| 12 | Add `data_group_id` to query engines | All | MEDIUM | SMALL | MEDIUM — group analytics scoping |
| 13 | Flow breakdowns/segments | Flows | MEDIUM | MEDIUM | MEDIUM — segment flow paths by property |
| 14 | Flow exclusions | Flows | MEDIUM | SMALL | MEDIUM — exclude events between flow steps |
| 15 | Flow session events | Flows | MEDIUM | SMALL | MEDIUM — $session_start/$session_end as flow anchors |
| 16 | Flow global property filters | Flows | MEDIUM | SMALL | MEDIUM — filter_by_event in addition to filter_by_cohort |
| 17 | Add `PerUserAggregation` session_replay_id_value | Insights | LOW | TRIVIAL | LOW — niche session replay use case |

---

## Detailed Findings

### Tier 1: Critical Gaps — Type Expansions and Core Parameters

#### 1.1 Expand `MathType` Literal (7 missing types)

The `MathType` Literal in `_literal_types.py` exposes 15 values, but `VALID_MATH_INSIGHTS` in `bookmark_enums.py` accepts 21. Seven server-supported math types are invisible to type-checking:

| Missing Math Type | What It Does | Requires Property? |
|-------------------|-------------|-------------------|
| `cumulative_unique` | Running total of unique users over time | No |
| `sessions` | Count of sessions (not users or events) | No |
| `unique_values` | Count of distinct property values | Yes |
| `most_frequent` | Most common property value | Yes |
| `first_value` | First property value seen per user | Yes |
| `multi_attribution` | Multi-touch attribution across events | Yes |
| `numeric_summary` | Count/mean/variance/sum_of_squares in one call | Yes |

**Implementation**: Add these 7 values to the `MathType` Literal type. Update the docstring table. No builder changes needed — `bookmark_enums.py` already accepts them; only the public type annotation is too restrictive.

**Files to modify**:
- `src/mixpanel_data/_literal_types.py:46-62` — Expand `MathType` Literal
- `src/mixpanel_data/_internal/bookmark_enums.py:128-142` — Update `MATH_REQUIRING_PROPERTY` if needed (verify `unique_values`, `most_frequent`, `first_value`, `multi_attribution`, `numeric_summary` all require property)

#### 1.2 Add `segment_method` to `Metric` Class

The `Metric` class has no `segment_method` field. The Mixpanel server validates `segment_method` with exactly two values:

```python
# From analytics/backend/arb/params.py
def _validate_segment_method(self, segment_method):
    if segment_method not in ("first", "all"):
        raise ValidationError("invalid segment_method: %s" % segment_method)
```

| Value | Meaning |
|-------|---------|
| `"all"` | Count all qualifying events per user (default) |
| `"first"` | Count only the first qualifying event per user |

**Context restriction**: Only valid for retention, addiction (frequency), and funnel query types — NOT insights.

**Note**: Power-tools incorrectly accepts `"last"` — this is a bug. Server rejects it.

**Bookmark JSON position**: `sections.show[N].measurement.segmentMethod`

**Implementation**:
- Add `segment_method: Literal["all", "first"] | None = None` to `Metric` class
- Add `SegmentMethod = Literal["all", "first"]` to `_literal_types.py`
- Thread through bookmark builders into `measurement` block
- Add validation: reject segment_method for insights-only queries

**Files to modify**:
- `src/mixpanel_data/_literal_types.py` — Add `SegmentMethod` Literal
- `src/mixpanel_data/types.py` — Add field to `Metric` dataclass
- `src/mixpanel_data/_internal/bookmark_builders.py` — Thread to measurement block

#### 1.3 Add `funnelReentryMode` Parameter

Funnel reentry mode controls how users re-entering a funnel are counted. Completely absent from mixpanel_data.

**Field name**: `funnelReentryMode`
**Bookmark JSON position**: `sections.show[0].behavior.funnelReentryMode`

| Value | Meaning |
|-------|---------|
| `"default"` | Server-default reentry behavior |
| `"basic"` | Users can re-enter funnel at steps after the first |
| `"aggressive"` | Users re-entering generate additional conversion counts |
| `"optimized"` | Server-optimized reentry calculation |

**Server source**: `FunnelReentryModeType` enum in `analytics/lib/common/mxpnl/report/bookmarks/insights/show.py:42-46`

**Default**: If absent, server assumes `"default"`.

**Power-tools validation rule**: `F6_BAD_REENTRY` — enum validation

**Implementation**:
- Add `FunnelReentryMode = Literal["default", "basic", "aggressive", "optimized"]` to `_literal_types.py`
- Add `reentry_mode: FunnelReentryMode | None = None` parameter to `query_funnel()` and `build_funnel_params()`
- Thread through `_build_funnel_params()` → behavior block in bookmark JSON
- Add enum constant `VALID_FUNNEL_REENTRY_MODES` to `bookmark_enums.py`

**Files to modify**:
- `src/mixpanel_data/_literal_types.py` — Add Literal type
- `src/mixpanel_data/workspace.py` — Add parameter to query_funnel/build_funnel_params
- `src/mixpanel_data/_internal/bookmark_builders.py` — Thread to behavior block
- `src/mixpanel_data/_internal/bookmark_enums.py` — Add enum constant
- `src/mixpanel_data/_internal/validation.py` — Add validation rule

#### 1.4 Add `retentionUnboundedMode` Parameter

Controls how users are counted across retention buckets. Completely absent from mixpanel_data.

**Field name**: `retentionUnboundedMode`
**Bookmark JSON position**: `sections.show[0].behavior.retentionUnboundedMode`

| Value | Meaning |
|-------|---------|
| `"none"` | Standard retention — only count users active in specific bucket (default) |
| `"carry_back"` | Include users who became active before the birth period |
| `"carry_forward"` | Count users who return after gaps as retained in all intermediate buckets |
| `"consecutive_forward"` | Count users only on consecutive return events |

**Server source**: `RetentionUnboundedModeType` enum in `analytics/lib/common/mxpnl/report/bookmarks/insights/show.py:66-70`

**Default**: `"none"` (explicitly — see `analytics/mixpanel_mcp/mcp_server/utils/reports/retention.py`)

**Power-tools validation rule**: `R8B_BAD_UNBOUNDED` — enum validation

**Implementation**: Same pattern as funnelReentryMode.

**Files to modify**: Same set as 1.3.

#### 1.5 Add `retentionCumulative` Parameter

Boolean flag controlling cumulative vs period-over-period retention display. Completely absent.

**Field name**: `retentionCumulative`
**Bookmark JSON position**: `sections.show[0].measurement.retentionCumulative` (NOTE: in `measurement`, NOT `behavior`)

| Value | Meaning |
|-------|---------|
| `true` | Cumulative retention — retain users across all prior periods |
| `false` | Period-over-period retention (default) |

**Server source**: `BehaviorMeasurement.retentionCumulative` in `show.py:295`

**Implementation**: Add `cumulative: bool = False` parameter to `query_retention()` and `build_retention_params()`. Thread to measurement block.

#### 1.6 Expand `RetentionMathType` (2 missing types)

`RetentionMathType` Literal has `retention_rate` and `unique`, but `VALID_MATH_RETENTION` accepts `total` and `average` too.

| Missing Type | What It Does |
|-------------|-------------|
| `"total"` | Raw total event count per retention bucket |
| `"average"` | Mean of a numeric property per retention bucket |

**Implementation**: Add to `RetentionMathType` Literal. No builder changes needed.

---

### Tier 2: High-Value New Features

#### 2.1 Time Comparison (Period-Over-Period)

Time comparison overlays a second time period on the same query for comparison. Supported in insights, funnels, and retention (NOT flows). Completely absent from mixpanel_data.

**Bookmark JSON position**: `params.timeComparison` (top-level, alongside `sections`)

**Discriminated union with 3 types**:

```python
# Type 1: Relative (previous N periods)
{"type": "relative", "unit": "day"}  # or "week", "month", "quarter", "year"

# Type 2: Absolute start date
{"type": "absolute-start", "date": "2024-01-15"}

# Type 3: Absolute end date
{"type": "absolute-end", "date": "2024-06-30"}
```

**Valid `type` values**: `"relative"`, `"absolute-start"`, `"absolute-end"`
**Valid `unit` values** (when type=relative): `"day"`, `"week"`, `"month"`, `"quarter"`, `"year"`
**Date format** (when type=absolute-*): `YYYY-MM-DD`

**Semantics**:
- `sections.time[]` defines the primary period
- `timeComparison` defines an overlay period
- `type: "relative"` offsets backward from primary period start
- `type: "absolute-start"` uses that date as comparison start (end inferred from primary period length)
- `type: "absolute-end"` uses that date as comparison end (start inferred backward)

**Power-tools validation rules** (bookmark-validator.js:761-790):
- `B5D_TC_NOT_OBJECT`: must be an object
- `B5D_BAD_TC_TYPE`: type must be valid
- `B5D_TC_MISSING_UNIT` / `B5D_BAD_TC_UNIT`: relative requires valid unit
- `B5D_TC_MISSING_DATE` / `B5D_TC_BAD_DATE`: absolute types require YYYY-MM-DD date

**Implementation**:
- Add `TimeComparison` type (frozen dataclass or union) to `types.py`
- Add `time_comparison: TimeComparison | None = None` to `query()`, `query_funnel()`, `query_retention()`, and their `build_*_params()` counterparts
- Add builder to serialize to bookmark JSON
- Add validation rules

**Files to modify**:
- `src/mixpanel_data/types.py` — Add `TimeComparison`, `RelativeTimeComparison`, `AbsoluteTimeComparison`
- `src/mixpanel_data/workspace.py` — Add parameter to 3 query methods + 3 build_params methods
- `src/mixpanel_data/_internal/bookmark_builders.py` — Add time comparison serialization
- `src/mixpanel_data/_internal/validation.py` — Add validation rules
- `src/mixpanel_data/_literal_types.py` — Add `TimeComparisonType` and `TimeComparisonUnit` Literals

#### 2.2 Bookmark-Level Frequency Analysis

Frequency analysis (addiction analysis) measures how many times users perform events. mixpanel_data has a legacy `frequency()` method calling the old `/retention/addiction` endpoint, but does NOT support frequency as a bookmark-level query capability. This means agents cannot:
- Break down any insights query by event frequency
- Filter any query to users who performed events N times
- Build frequency metrics in the bookmark query system

**Three components needed**:

##### 2.2.1 Frequency as Breakdown (`FrequencyBreakdown`)

Goes into `sections.group[]`:

```json
{
  "dataset": "$mixpanel",
  "behavior": {
    "aggregationOperator": "total",
    "event": {"label": "SIGNUP", "value": "SIGNUP"},
    "filters": [],
    "filtersOperator": "and",
    "dateRange": null,
    "behaviorType": "$frequency"
  },
  "value": "SIGNUP Frequency",
  "resourceType": "people",
  "propertyType": "number",
  "dataGroupId": null,
  "customBucket": {
    "bucketSize": 1,
    "min": 0,
    "max": 10,
    "disabled": false
  }
}
```

Key constraints:
- `resourceType` MUST be `"people"` (not events)
- `behaviorType` MUST be `"$frequency"` (sentinel value)
- `aggregationOperator` is always `"total"`

##### 2.2.2 Frequency as Filter (`FrequencyFilter`)

Goes into `sections.filter[]`:

```json
{
  "dataset": "$mixpanel",
  "value": "LOGIN Frequency",
  "resourceType": "people",
  "customProperty": {
    "name": "LOGIN Frequency",
    "behavior": {
      "aggregationOperator": "total",
      "event": {"label": "LOGIN", "value": "LOGIN"},
      "filters": [],
      "filtersOperator": "and",
      "dateRange": null,
      "behaviorType": "$frequency"
    },
    "propertyType": "number",
    "resourceType": "people"
  },
  "customPropertyId": "$temp-<random-id>",
  "filterType": "number",
  "filterOperator": "is at least",
  "filterValue": 5,
  "dataGroupId": null
}
```

Valid filter operators for frequency: `"is at least"`, `"is at most"`, `"is greater than"`, `"is less than"`, `"is equal to"`, `"is between"`

##### 2.2.3 Frequency Show Clause

Uses `type: "addiction"` behavior block in `sections.show[]`.

**Implementation**:
- Add `FrequencyBreakdown` dataclass to `types.py`
- Add `FrequencyFilter` dataclass (or extend `Filter` class) to `types.py`
- Accept `FrequencyBreakdown` in `group_by` parameter
- Accept `FrequencyFilter` in `where` parameter
- Add builders to `bookmark_builders.py`
- Add validation rules

#### 2.3 Behavioral Cohort Aggregation Operators

`CohortCriteria.did_event()` currently only supports count-based frequency thresholds (`at_least`/`at_most`/`exactly`). The server supports aggregation operators that enable property-value-based behavioral cohorts:

| Aggregation | What It Enables |
|-------------|----------------|
| `"total"` | "Users whose total purchase amount > $100" |
| `"unique"` | "Users with 3+ unique product categories" |
| `"average"` | "Users whose average session duration > 5 min" |
| `"min"` | "Users whose minimum order value > $20" |
| `"max"` | "Users whose maximum cart size > 10" |
| `"median"` | "Users whose median purchase value > $50" |

The power-tools' `buildRawCohort()` function accepts an `aggregation` parameter that sets `customProperty.behavior.aggregationOperator`. This field is completely absent from `CohortCriteria.did_event()`.

**Implementation**:
- Add `aggregation: Literal["total", "unique", "average", "min", "max", "median"] | None = None` to `CohortCriteria.did_event()`
- Add `aggregation_property: str | None = None` for the property to aggregate on
- Update serialization to emit `aggregationOperator` in the behavioral condition

---

### Tier 3: Medium-Value Completeness

#### 3.1 Missing Filter Factory Methods

Of ~35 operators in `VALID_FILTER_OPERATORS`, the `Filter` class covers ~22 via factory methods. The actionable gaps (excluding legacy date aliases and numeric aliases for existing methods):

| Missing Operator | Recommended Method | Notes |
|-----------------|-------------------|-------|
| `"not between"` | `Filter.not_between(prop, min, max)` | Numeric negation of between |
| `"starts with"` | `Filter.starts_with(prop, prefix)` | String prefix matching — in power-tools `VALID_FILTER_OPERATORS_BY_TYPE` |
| `"ends with"` | `Filter.ends_with(prop, suffix)` | String suffix matching — same source |
| `"was not between"` | `Filter.date_not_between(prop, start, end)` | Date range negation |
| `"was in the next"` | `Filter.in_the_next(prop, value, unit)` | Future relative date |
| `"is at least"` / `"is at most"` | `Filter.at_least(prop, val)` / `Filter.at_most(prop, val)` | Inclusive numeric bounds (>=, <=) |

**Lower priority** (mostly aliases for existing methods):
- `"is equal to"` — alias for `"equals"` with numeric semantics
- `"is greater than or equal to"` — alias for `"is at least"`
- `"is less than or equal to"` — alias for `"is at most"`
- `"was less than"` — relative date operator
- `"before the last"` — relative date operator

**Implementation**: Add factory methods to `Filter` class. Each is ~10 lines following existing patterns.

#### 3.2 Expand `FunnelMathType` (1 missing)

Add `"histogram"` to `FunnelMathType` Literal. Already in `VALID_MATH_FUNNELS`.

#### 3.3 Add `data_group_id` to Query Engines

`dataGroupId` is hardcoded to `None` in 6 locations across `bookmark_builders.py` and `workspace.py`. Group analytics customers cannot scope queries to specific data groups (companies, accounts).

**Where data_group_id IS used**: `list_cohorts_full()`, `list_lookup_tables()`, `upload_lookup_table()`, `update_lookup_table()`, `delete_lookup_tables()`

**Where data_group_id is NOT used**: `query()`, `query_funnel()`, `query_retention()`, `query_flow()`, and all `build_*_params()` methods

**Implementation**: Add `data_group_id: int | None = None` parameter to all query/build methods. Thread through to bookmark builders to replace hardcoded `None`.

#### 3.4 Flow Breakdowns/Segments

Power-tools' `buildFlowsReport` supports a `segments` array for breaking down flow paths by property. mixpanel_data does not expose this.

#### 3.5 Flow Exclusions

Power-tools supports `exclusions` array in flows for excluding events between specific steps. mixpanel_data does not expose this.

#### 3.6 Flow Session Events

Power-tools maps `$session_start` → `session_event: "start"` and `$session_end` → `session_event: "end"` via `SESSION_EVENT_MAP`. mixpanel_data's `FlowStep` only accepts event names, not session event types.

#### 3.7 Flow Global Property Filters

Power-tools supports `filter_by_event` for global property filters on flows. mixpanel_data only supports cohort filters via the `where` parameter (enforced by `build_flow_cohort_filter()`).

---

### Tier 4: Confirmed Non-Gaps (No Action Needed)

| Item | Status | Evidence |
|------|--------|----------|
| Custom property formulas (IFS, string ops) | NO GAP | Formula string passed as-is; server evaluates. Both codebases produce identical `displayFormula` + `composedProperties` JSON. |
| Lookup table joins in queries | NO GAP | Joins are server-resolved via `get_rollup_dataset_joins()` based on show clause metadata. Client never constructs joins. |
| Multiple/nested breakdowns | NO GAP | `build_group_section()` already accepts `list[str \| GroupBy \| CohortBreakdown]` and produces one entry per item in `sections.group[]`. |
| Display options (plotStyle, yAxisOptions, valueMode) | NO GAP (for agents) | These are purely UI rendering options. Data-affecting options (analysis, rollingWindowSize) are already exposed via `rolling` and `cumulative` parameters. |

---

## Implementation Sequencing

### Phase A: Type Expansions and Parameter Additions (Tier 1)

*Estimated effort: 2-3 days. Low risk — expanding existing patterns.*

| Step | What | Files | Effort |
|------|------|-------|--------|
| A1 | Expand `MathType` Literal (+7 values) | `_literal_types.py` | TRIVIAL |
| A2 | Expand `RetentionMathType` Literal (+2 values) | `_literal_types.py` | TRIVIAL |
| A3 | Expand `FunnelMathType` Literal (+1 value) | `_literal_types.py` | TRIVIAL |
| A4 | Add `SegmentMethod` Literal + field to `Metric` | `_literal_types.py`, `types.py`, `bookmark_builders.py` | SMALL |
| A5 | Add `FunnelReentryMode` Literal + parameter | `_literal_types.py`, `workspace.py`, `bookmark_builders.py`, `bookmark_enums.py`, `validation.py` | SMALL |
| A6 | Add `RetentionUnboundedMode` Literal + parameter | Same files as A5 | SMALL |
| A7 | Add `retentionCumulative` parameter | `workspace.py`, `bookmark_builders.py` | TRIVIAL |
| A8 | Add missing `Filter` factory methods (6 methods) | `types.py` | SMALL |

### Phase B: New Feature Types (Tier 2)

*Estimated effort: 3-5 days. Medium risk — new types and builders.*

| Step | What | Files | Effort |
|------|------|-------|--------|
| B1 | Add `TimeComparison` types + parameter | `types.py`, `_literal_types.py`, `workspace.py`, `bookmark_builders.py`, `validation.py` | MEDIUM |
| B2 | Add `FrequencyBreakdown` type + builder | `types.py`, `bookmark_builders.py`, `workspace.py` | MEDIUM |
| B3 | Add `FrequencyFilter` type + builder | `types.py`, `bookmark_builders.py` | MEDIUM |
| B4 | Add aggregation operators to `CohortCriteria.did_event()` | `types.py` | MEDIUM |

### Phase C: Completeness (Tier 3)

*Estimated effort: 2-3 days. Low-medium risk.*

| Step | What | Files | Effort |
|------|------|-------|--------|
| C1 | Add `data_group_id` to all query engines | `workspace.py`, `bookmark_builders.py` | SMALL |
| C2 | Add flow breakdowns/segments | `workspace.py`, `bookmark_builders.py`, `types.py` | MEDIUM |
| C3 | Add flow exclusions | `workspace.py`, `types.py` | SMALL |
| C4 | Add flow session events | `types.py`, `workspace.py` | SMALL |
| C5 | Add flow global property filters | `workspace.py`, `bookmark_builders.py` | SMALL |

---

## Appendix A: Complete Insights Math Type Matrix

| Math Type | In `MathType` Literal | In `VALID_MATH_INSIGHTS` | In power-tools | Requires Property | No Per-User | Gap |
|-----------|:---------------------:|:------------------------:|:--------------:|:-----------------:|:-----------:|:---:|
| total | YES | YES | YES | Optional | No | - |
| unique | YES | YES | YES | No | Yes | - |
| cumulative_unique | **NO** | YES | YES | No | - | **GAP** |
| sessions | **NO** | YES | YES | No | - | **GAP** |
| dau | YES | YES | YES | No | Yes | - |
| wau | YES | YES | YES | No | Yes | - |
| mau | YES | YES | YES | No | Yes | - |
| average | YES | YES | YES | Yes | No | - |
| median | YES | YES | YES | Yes | No | - |
| min | YES | YES | YES | Yes | No | - |
| max | YES | YES | YES | Yes | No | - |
| p25 | YES | YES | YES | Yes | No | - |
| p75 | YES | YES | YES | Yes | No | - |
| p90 | YES | YES | YES | Yes | No | - |
| p99 | YES | YES | YES | Yes | No | - |
| percentile | YES (maps to custom_percentile) | YES (as custom_percentile) | YES | Yes | No | - |
| histogram | YES | YES | YES | Yes | No | - |
| unique_values | **NO** | YES | YES | Yes | No | **GAP** |
| most_frequent | **NO** | YES | YES | Yes | - | **GAP** |
| first_value | **NO** | YES | YES | Yes | - | **GAP** |
| multi_attribution | **NO** | YES | YES | Yes | - | **GAP** |
| numeric_summary | **NO** | YES | YES | Yes | No | **GAP** |

## Appendix B: Complete Filter Operator Matrix

| Operator | Property Types | Filter Method | Gap |
|----------|---------------|---------------|-----|
| `equals` | string | `Filter.equals()` | - |
| `does not equal` | string | `Filter.not_equals()` | - |
| `is equal to` | number | (none) | Alias gap |
| `contains` | string | `Filter.contains()` | - |
| `does not contain` | string | `Filter.not_contains()` | - |
| `is set` | all | `Filter.is_set()` | - |
| `is not set` | all | `Filter.is_not_set()` | - |
| `is at least` | number | (none) | **GAP** |
| `is at most` | number | (none) | **GAP** |
| `is between` | number | `Filter.between()` | - |
| `between` | number | (covered by `Filter.between()`) | - |
| `not between` | number | (none) | **GAP** |
| `is greater than` | number | `Filter.greater_than()` | - |
| `is less than` | number | `Filter.less_than()` | - |
| `is greater than or equal to` | number | (none) | Alias for is at least |
| `is less than or equal to` | number | (none) | Alias for is at most |
| `true` | boolean | `Filter.is_true()` | - |
| `false` | boolean | `Filter.is_false()` | - |
| `was on` | datetime | `Filter.on()` | - |
| `was not on` | datetime | `Filter.not_on()` | - |
| `was in the` | datetime | `Filter.in_the_last()` | - |
| `was not in the` | datetime | `Filter.not_in_the_last()` | - |
| `was between` | datetime | `Filter.date_between()` | - |
| `was not between` | datetime | (none) | **GAP** |
| `was less than` | datetime | (none) | Minor gap |
| `was before` | datetime | `Filter.before()` | - |
| `was since` | datetime | `Filter.since()` | - |
| `was in the next` | datetime | (none) | **GAP** |
| `on` | datetime (legacy) | (covered by `was on`) | - |
| `not on` | datetime (legacy) | (covered by `was not on`) | - |
| `in the last` | datetime (legacy) | (covered by `was in the`) | - |
| `not in the last` | datetime (legacy) | (covered by `was not in the`) | - |
| `before the last` | datetime (legacy) | (none) | Minor gap |
| `before` | datetime (legacy) | (covered by `was before`) | - |
| `in the next` | datetime (legacy) | (covered by `was in the next`) | - |
| `since` | datetime (legacy) | (covered by `was since`) | - |
| `starts with` | string (in power-tools OPERATORS_BY_TYPE) | (none) | **GAP** |
| `ends with` | string (in power-tools OPERATORS_BY_TYPE) | (none) | **GAP** |

## Appendix C: Behavioral Cohort Feature Matrix

| Feature | power-tools `buildRawCohort` | `CohortCriteria` | Gap |
|---------|:---------------------------:|:-----------------:|:---:|
| Count-based frequency (at_least/at_most/exactly) | YES | YES | - |
| Aggregation: total | YES | **NO** | **GAP** |
| Aggregation: unique | YES | **NO** | **GAP** |
| Aggregation: average | YES | **NO** | **GAP** |
| Aggregation: min | YES | **NO** | **GAP** |
| Aggregation: max | YES | **NO** | **GAP** |
| Aggregation: median | YES | **NO** | **GAP** |
| Event property filters | YES | YES (via `where=`) | - |
| Time scoping (within_days/weeks/months) | YES | YES | - |
| Absolute date range (from_date/to_date) | NO | YES | - |
| Negation (did_not_do_event) | YES | YES | - |
| Cohort references (in_cohort/not_in_cohort) | NO | YES | - |
| AND/OR composition (all_of/any_of) | NO | YES | - |
| Property criteria (has_property) | NO | YES | - |

## Appendix D: Bookmark JSON Examples for Key New Capabilities

### D1: Funnel Reentry Mode

```json
{
  "sections": {
    "show": [{
      "type": "metric",
      "behavior": {
        "type": "funnel",
        "funnelReentryMode": "aggressive",
        "behaviors": [
          {"type": "event", "name": "View Product"},
          {"type": "event", "name": "Add to Cart"},
          {"type": "event", "name": "Purchase"}
        ]
      }
    }]
  }
}
```

### D2: Retention Unbounded + Cumulative

```json
{
  "sections": {
    "show": [{
      "type": "metric",
      "behavior": {
        "type": "retention",
        "retentionUnboundedMode": "carry_forward",
        "retentionUnit": "week",
        "behaviors": [
          {"type": "event", "name": "Signup"},
          {"type": "event", "name": "Login"}
        ]
      },
      "measurement": {
        "math": "retention_rate",
        "retentionCumulative": true
      }
    }]
  }
}
```

### D3: Time Comparison (Relative)

```json
{
  "sections": {
    "time": [{"dateRangeType": "in the last", "window": {"value": 30, "unit": "day"}, "unit": "day"}],
    "show": [{"type": "metric", "behavior": {"type": "event", "name": "Signup"}}]
  },
  "timeComparison": {
    "type": "relative",
    "unit": "month"
  }
}
```

### D4: Frequency Breakdown

```json
{
  "sections": {
    "group": [{
      "dataset": "$mixpanel",
      "behavior": {
        "aggregationOperator": "total",
        "event": {"label": "Purchase", "value": "Purchase"},
        "behaviorType": "$frequency",
        "filters": [],
        "filtersOperator": "and",
        "dateRange": null
      },
      "value": "Purchase Frequency",
      "resourceType": "people",
      "propertyType": "number",
      "customBucket": {"bucketSize": 1, "min": 0, "max": 10}
    }]
  }
}
```

### D5: Segment Method

```json
{
  "sections": {
    "show": [{
      "type": "metric",
      "behavior": {"type": "event", "name": "Purchase"},
      "measurement": {
        "math": "total",
        "segmentMethod": "first"
      }
    }]
  }
}
```

---

*Audit completed April 14, 2026. Sources: mixpanel_data (Python), mixpanel-power-tools (JavaScript), mixpanel_headless/analytics (Mixpanel server).*
