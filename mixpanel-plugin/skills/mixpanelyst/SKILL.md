---
name: mixpanelyst
description: This skill should be used when the user asks about Mixpanel product analytics, event data, funnel analysis, retention curves, cohort analysis, segmentation queries, user behavior, conversion rates, churn, DAU/MAU, ARPU, revenue metrics, feature adoption, A/B test results, user paths, flow analysis, or any request to query, explore, visualize, or analyze Mixpanel data using Python.
allowed-tools: Bash Read Write WebFetch
---

# mixpanel_data API Reference

Analyze Mixpanel data by writing and executing Python code using the `mixpanel_data` library and `pandas`.

```python
import mixpanel_data as mp
ws = mp.Workspace()
result = ws.query("Login", last=30)
print(result.df.head())
```

## Query Engines

| Question | Method | Returns |
|----------|--------|---------|
| How much? How many? Trends? | `ws.query()` | `QueryResult` |
| Do users convert through a sequence? | `ws.query_funnel()` | `FunnelQueryResult` |
| Do users come back? | `ws.query_retention()` | `RetentionQueryResult` |
| What paths do users take? | `ws.query_flow()` | `FlowQueryResult` |
| Who are they? What do they look like? | `ws.query_user()` | `UserQueryResult` |

All result types have a `.df` property returning a pandas DataFrame and a `.params` dict containing the bookmark JSON.
`FlowQueryResult` also has `.graph` (NetworkX DiGraph) and `.anytree` (list of tree roots).

**Quick lookups** use `python3 -c "..."` one-liners. **Multi-step analysis** writes `.py` files.

## Discovery — ALWAYS Do Both Steps Before Querying

Guessing event names causes silent empty results. Guessing API parameters causes TypeErrors and invalid queries. **Discover both the data schema AND the API surface before writing any query.**

### Step 1: Discover the data schema

```python
import mixpanel_data as mp
from mixpanel_data import Filter, GroupBy, Metric
ws = mp.Workspace()

# 1. Find real event names
events = ws.events()
top = ws.top_events(limit=10)
print("Events:", events[:20])
print("Top:", [(e.event, e.count) for e in top])

# 2. Find real property names for the event you'll query
props = ws.properties("Login")  # use an actual event name from step 1
print("Properties:", props)

# 3. (Optional) Check property values to validate filter inputs
vals = ws.property_values("platform", event="Login")
print("Platforms:", vals)
```

### Step 2: Discover the API surface with `help.py`

**`help.py` is the source of truth for method signatures, parameter names, type constructors, and enum values.** The method signatures later in this document are summaries — always verify with `help.py` before using a method or type you haven't looked up.

**Never guess parameter names.** If you're unsure whether a parameter is called `property` or `math_property`, or what arguments `GroupBy()` accepts, run `help.py` first. Wrong parameter names cause TypeErrors that waste tool calls.

```bash
# Look up a query method BEFORE writing the query
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.query
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.query_funnel

# Look up types BEFORE constructing them
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Filter          # → classmethods: .equals(), .less_than(), etc.
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Metric          # → property=, NOT math_property=
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py GroupBy          # → property, property_type only
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py MathType         # → enum values

# Look up result types to know what columns .df returns
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py QueryResult
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py FlowQueryResult

# Search when you're not sure of the exact name
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py search cohort   # → CohortBreakdown, CohortMetric, CohortDefinition, ...
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py search retention # → query_retention, RetentionEvent, RetentionMathType, ...

# List everything
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py types            # all public types
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py exceptions        # all exceptions
```

For tutorials and guides: `WebFetch(url="https://jaredmcfarland.github.io/mixpanel_data/llms.txt")`

### Discovery method signatures

```python
def events(self) -> list[str]: ...
    # List all event names (cached).

def properties(self, event: str) -> list[str]: ...
    # List all property names for an event (cached).

def property_values(self, property_name: str, *, event: str | None = None, limit: int = 100) -> list[str]: ...
    # Get sample values for a property.

def top_events(self, *, type: Literal['general', 'average', 'unique'] = 'general', limit: int | None = None) -> list[TopEvent]: ...
    # Get today's most active events. TopEvent has .event (str), .count (int), .percent_change (float).

def funnels(self) -> list[FunnelInfo]: ...
    # List saved funnels.

def cohorts(self) -> list[SavedCohort]: ...
    # List saved cohorts.

def list_bookmarks(self, bookmark_type: BookmarkType | None = None) -> list[BookmarkInfo]: ...
    # List all saved reports (bookmarks).

def lexicon_schemas(self, *, entity_type: EntityType | None = None) -> list[LexiconSchema]: ...
    # List Lexicon schemas (event/property definitions).

def clear_discovery_cache(self) -> None: ...
    # Clear cached discovery results.
# User Guide: WebFetch(url="https://jaredmcfarland.github.io/mixpanel_data/guide/discovery/index.md")
```

## Workspace

```python
class Workspace:
    """Unified entry point for Mixpanel data operations."""

    def __init__(
        self,
        account: str | None = None,
        project_id: str | None = None,
        region: str | None = None,
        workspace_id: int | None = None,
        credential: str | None = None,
    ) -> None:
        """Create a new Workspace. Credentials resolved in order:
        1. Environment variables (MP_USERNAME, MP_SECRET, MP_PROJECT_ID, MP_REGION)
        2. OAuth tokens from local storage
        3. Named account/credential from config file
        4. Default account from config file
        """
        ...

    # --- Properties ---
    workspace_id: int | None       # Currently set workspace ID
    current_project: ProjectContext # Current project context
    current_credential: AuthCredential  # Current auth credential
    api: MixpanelAPIClient         # Direct API client access (escape hatch)
```

Supports context manager: `with mp.Workspace() as ws: ...`

### Project & Workspace Management

```python
def me(self, *, force_refresh: bool = False) -> Any: ...
    # Get /me response for current credentials (cached 24h).

def discover_projects(self) -> list[tuple[str, MeProjectInfo]]: ...
    # List all accessible projects via the /me API.

def discover_workspaces(self, project_id: str | None = None) -> list[MeWorkspaceInfo]: ...
    # List workspaces for a project via the /me API.

def switch_project(self, project_id: str, workspace_id: int | None = None) -> None: ...
    # Switch to a different project in-session.

def switch_workspace(self, workspace_id: int) -> None: ...
    # Switch workspace within the current project.

def set_workspace_id(self, workspace_id: int | None) -> None: ...
    # Set or clear the workspace ID for scoped App API requests.

def list_workspaces(self) -> list[PublicWorkspace]: ...
    # List all public workspaces for the current project.

def resolve_workspace_id(self) -> int: ...
    # Auto-discover and resolve workspace ID.

@staticmethod
def test_credentials(account: str | None = None) -> dict[str, Any]: ...
    # Test account credentials with a lightweight API call.

def close(self) -> None: ...
    # Close all resources (HTTP client). Idempotent.
```

### Insights Query

Run `python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.query` for the full signature.

```python
def query(
    self,
    events: str | Metric | CohortMetric | Formula | Sequence[...],
    *,
    from_date: str | None = None,        # YYYY-MM-DD, overrides last
    to_date: str | None = None,          # YYYY-MM-DD, requires from_date
    last: int = 30,                      # relative days (ignored if from_date set)
    unit: QueryTimeUnit = 'day',
    math: MathType = 'total',            # aggregation: total, unique, dau, average, sum, ...
    math_property: str | None = None,    # top-level shorthand; Metric() uses property= instead
    per_user: PerUserAggregation | None = None,
    percentile_value: int | float | None = None,
    group_by: str | GroupBy | CohortBreakdown | FrequencyBreakdown | list[...] | None = None,
    where: Filter | FrequencyFilter | list[...] | None = None,
    formula: str | None = None,          # e.g. "(B / A) * 100", requires 2+ events
    formula_label: str | None = None,
    rolling: int | None = None,
    cumulative: bool = False,
    mode: Literal['timeseries', 'total', 'table'] = 'timeseries',
    time_comparison: TimeComparison | None = None,
    data_group_id: int | None = None,
) -> QueryResult:
    # .df columns: timeseries → [date, event, count]
    #              total → [event, count]
    #              with group_by → adds segment column
    ...
```

### Funnel Query

Run `python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.query_funnel` for the full signature.

```python
def query_funnel(
    self,
    steps: list[str | FunnelStep],      # at least 2 steps required
    *,
    conversion_window: int = 14,
    conversion_window_unit: Literal['second', 'minute', 'hour', 'day', 'week', 'month', 'session'] = 'day',
    order: Literal['loose', 'any'] = 'loose',
    from_date: str | None = None, to_date: str | None = None, last: int = 30,
    unit: QueryTimeUnit = 'day',
    math: FunnelMathType = 'conversion_rate_unique',
    math_property: str | None = None,
    group_by: str | GroupBy | CohortBreakdown | list[...] | None = None,
    where: Filter | list[Filter] | None = None,
    exclusions: list[str | Exclusion] | None = None,
    holding_constant: str | HoldingConstant | list[...] | None = None,
    mode: Literal['steps', 'trends', 'table'] = 'steps',
    reentry_mode: FunnelReentryMode | None = None,
    time_comparison: TimeComparison | None = None,
    data_group_id: int | None = None,
) -> FunnelQueryResult:
    # .df columns: [step, event, count, step_conv_ratio, avg_time]
    # .overall_conversion_rate: float
    ...
```

### Retention Query

Run `python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.query_retention` for the full signature.

```python
def query_retention(
    self,
    born_event: str | RetentionEvent,
    return_event: str | RetentionEvent,
    *,
    retention_unit: TimeUnit = 'week',
    alignment: RetentionAlignment = 'birth',
    bucket_sizes: list[int] | None = None,
    from_date: str | None = None, to_date: str | None = None, last: int = 30,
    unit: QueryTimeUnit = 'day',
    math: RetentionMathType = 'retention_rate',
    group_by: str | GroupBy | CohortBreakdown | list[...] | None = None,
    where: Filter | list[Filter] | None = None,
    mode: RetentionMode = 'curve',
    unbounded_mode: RetentionUnboundedMode | None = None,
    retention_cumulative: bool = False,
    time_comparison: TimeComparison | None = None,
    data_group_id: int | None = None,
) -> RetentionQueryResult:
    # .df columns: [cohort_date, bucket, count, rate]  (+ segment with group_by)
    # .average: synthetic average across cohorts
    ...
```

### Flow Query

Run `python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.query_flow` for the full signature.

```python
def query_flow(
    self,
    event: str | FlowStep | Sequence[str | FlowStep],
    *,
    forward: int = 3, reverse: int = 0,
    from_date: str | None = None, to_date: str | None = None, last: int = 30,
    conversion_window: int = 7,
    conversion_window_unit: Literal['day', 'week', 'month', 'session'] = 'day',
    count_type: Literal['unique', 'total', 'session'] = 'unique',
    cardinality: int = 3,
    collapse_repeated: bool = False,
    hidden_events: list[str] | None = None,
    mode: Literal['sankey', 'paths', 'tree'] = 'sankey',
    where: Filter | list[Filter] | None = None,
    segments: str | GroupBy | CohortBreakdown | FrequencyBreakdown | list[...] | None = None,
    exclusions: list[str] | None = None,
    data_group_id: int | None = None,
) -> FlowQueryResult:
    # .df, .graph (NetworkX DiGraph), .anytree (tree mode)
    # .top_transitions(n), .drop_off_summary()
    ...
```

### User Profile Query

Run `python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.query_user` for the full signature.

```python
def query_user(
    self,
    *,
    where: Filter | list[Filter] | str | None = None,
    cohort: int | CohortDefinition | None = None,
    properties: list[str] | None = None,
    sort_by: str | None = None,
    sort_order: Literal['ascending', 'descending'] = 'descending',
    limit: int | None = 1,              # None = fetch all matching
    search: str | None = None,
    distinct_id: str | None = None,     # single user lookup
    distinct_ids: list[str] | None = None,  # batch lookup
    group_id: str | None = None,        # query group profiles
    as_of: str | int | None = None,     # point-in-time
    mode: Literal['profiles', 'aggregate'] = 'aggregate',
    aggregate: Literal['count', 'extremes', 'percentile', 'numeric_summary'] = 'count',
    aggregate_property: str | None = None,
    percentile: float | None = None,
    segment_by: list[int] | None = None,
    parallel: bool = False, workers: int = 5,
    include_all_users: bool = False,
) -> UserQueryResult:
    # .df, .total, .profiles
    ...
```

### Build Params (without executing)

Same parameters as the corresponding query methods, but return `dict[str, Any]` bookmark params without making an API call. Useful for creating saved reports (bookmarks).

```python
def build_params(self, events, **kwargs) -> dict[str, Any]: ...
def build_funnel_params(self, steps, **kwargs) -> dict[str, Any]: ...
def build_retention_params(self, born_event, return_event, **kwargs) -> dict[str, Any]: ...
def build_flow_params(self, event, **kwargs) -> dict[str, Any]: ...
def build_user_params(self, **kwargs) -> dict[str, Any]: ...
```

### Legacy Queries & Counts

These use older APIs. Prefer the typed query methods above when possible.

```python
def segmentation(self, event: str, *, from_date: str, to_date: str, on: str | None = None, unit: Literal['day', 'week', 'month'] = 'day', where: str | None = None) -> SegmentationResult: ...
def funnel(self, funnel_id: int, *, from_date: str, to_date: str, unit: str | None = None, on: str | None = None) -> FunnelResult: ...
def retention(self, *, born_event: str, return_event: str, from_date: str, to_date: str, born_where: str | None = None, return_where: str | None = None, interval: int = 1, interval_count: int = 10, unit: Literal['day', 'week', 'month'] = 'day') -> RetentionResult: ...
def event_counts(self, events: list[str], *, from_date: str, to_date: str, type: Literal['general', 'unique', 'average'] = 'general', unit: Literal['day', 'week', 'month'] = 'day') -> EventCountsResult: ...
def property_counts(self, event: str, property_name: str, *, from_date: str, to_date: str, type: Literal['general', 'unique', 'average'] = 'general', unit: Literal['day', 'week', 'month'] = 'day', values: list[str] | None = None, limit: int | None = None) -> PropertyCountsResult: ...
def frequency(self, *, from_date: str, to_date: str, unit: Literal['day', 'week', 'month'] = 'day', addiction_unit: Literal['hour', 'day'] = 'hour', event: str | None = None, where: str | None = None) -> FrequencyResult: ...
def activity_feed(self, distinct_ids: list[str], *, from_date: str | None = None, to_date: str | None = None) -> ActivityFeedResult: ...
def query_saved_report(self, bookmark_id: int, *, bookmark_type: Literal['insights', 'funnels', 'retention', 'flows'] = 'insights', from_date: str | None = None, to_date: str | None = None) -> SavedReportResult: ...
def query_saved_flows(self, bookmark_id: int) -> FlowsResult: ...
def segmentation_numeric(self, event: str, *, from_date: str, to_date: str, on: str, unit: Literal['hour', 'day'] = 'day', where: str | None = None, type: Literal['general', 'unique', 'average'] = 'general') -> NumericBucketResult: ...
def segmentation_sum(self, event: str, *, from_date: str, to_date: str, on: str, unit: Literal['hour', 'day'] = 'day', where: str | None = None) -> NumericSumResult: ...
def segmentation_average(self, event: str, *, from_date: str, to_date: str, on: str, unit: Literal['hour', 'day'] = 'day', where: str | None = None) -> NumericAverageResult: ...
```

### Entity CRUD (App API)

All entity methods require a workspace ID. Use `python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.<method>` for full signatures and parameter types.
User Guide: `WebFetch(url="https://jaredmcfarland.github.io/mixpanel_data/guide/entity-management/index.md")`

#### Dashboard (→ `Dashboard`)

`list_dashboards`, `create_dashboard`, `get_dashboard`, `update_dashboard`, `delete_dashboard`, `bulk_delete_dashboards`, `favorite_dashboard`, `unfavorite_dashboard`, `pin_dashboard`, `unpin_dashboard`, `add_report_to_dashboard`, `remove_report_from_dashboard`, `update_text_card`, `update_report_link`

**Blueprints:** `list_blueprint_templates` → `list[BlueprintTemplate]`, `create_blueprint`, `get_blueprint_config`, `update_blueprint_cohorts`, `finalize_blueprint`, `create_rca_dashboard`

**Helpers:** `get_bookmark_dashboard_ids` → `list[int]`, `get_dashboard_erf` → `dict`

#### Bookmark / Report (→ `Bookmark`)

`list_bookmarks_v2`, `create_bookmark`, `get_bookmark`, `update_bookmark`, `delete_bookmark`, `bulk_delete_bookmarks`, `bulk_update_bookmarks`, `bookmark_linked_dashboard_ids` → `list[int]`, `get_bookmark_history` → `BookmarkHistoryResponse`

#### Cohort (→ `Cohort`)

`list_cohorts_full`, `get_cohort`, `create_cohort`, `update_cohort`, `delete_cohort`, `bulk_delete_cohorts`, `bulk_update_cohorts`

#### Feature Flag (→ `FeatureFlag`)

`list_feature_flags`, `create_feature_flag`, `get_feature_flag`, `update_feature_flag`, `delete_feature_flag`, `archive_feature_flag`, `restore_feature_flag`, `duplicate_feature_flag`, `set_flag_test_users`, `get_flag_history` → `FlagHistoryResponse`, `get_flag_limits` → `FlagLimitsResponse`

#### Experiment (→ `Experiment`)

`list_experiments`, `create_experiment`, `get_experiment`, `update_experiment`, `delete_experiment`, `launch_experiment`, `conclude_experiment`, `decide_experiment`, `archive_experiment`, `restore_experiment`, `duplicate_experiment`, `list_erf_experiments` → `list[dict]`

#### Alert (→ `CustomAlert`)

`list_alerts`, `create_alert`, `get_alert`, `update_alert`, `delete_alert`, `bulk_delete_alerts`, `get_alert_count` → `AlertCount`, `get_alert_history` → `AlertHistoryResponse`, `test_alert`, `get_alert_screenshot_url`, `validate_alerts_for_bookmark`

#### Annotation (→ `Annotation`)

`list_annotations`, `create_annotation`, `get_annotation`, `update_annotation`, `delete_annotation`, `list_annotation_tags` → `list[AnnotationTag]`, `create_annotation_tag`

#### Webhook (→ `ProjectWebhook`)

`list_webhooks`, `create_webhook`, `update_webhook`, `delete_webhook`, `test_webhook`

#### Lexicon & Data Governance

**Event/Property Definitions:** `get_event_definitions`, `update_event_definition`, `delete_event_definition`, `bulk_update_event_definitions`, `get_property_definitions`, `update_property_definition`, `bulk_update_property_definitions`, `export_lexicon`, `get_event_history`, `get_property_history`

**Tags:** `list_lexicon_tags`, `create_lexicon_tag`, `update_lexicon_tag`, `delete_lexicon_tag`

**Drop Filters:** `list_drop_filters`, `create_drop_filter`, `update_drop_filter`, `delete_drop_filter`, `get_drop_filter_limits`

**Custom Properties:** `list_custom_properties`, `create_custom_property`, `get_custom_property`, `update_custom_property`, `delete_custom_property`, `validate_custom_property`

**Custom Events:** `list_custom_events`, `update_custom_event`, `delete_custom_event`

**Lookup Tables:** `list_lookup_tables`, `upload_lookup_table`, `download_lookup_table`, `update_lookup_table`, `delete_lookup_tables`

**Schema Registry:** `list_schema_registry`, `create_schema`, `update_schema`, `create_schemas_bulk`, `update_schemas_bulk`, `delete_schemas`

**Schema Enforcement:** `get_schema_enforcement`, `init_schema_enforcement`, `update_schema_enforcement`, `replace_schema_enforcement`, `delete_schema_enforcement`

**Audit & Monitoring:** `run_audit`, `run_audit_events_only`, `list_data_volume_anomalies`, `update_anomaly`, `bulk_update_anomalies`

**Data Deletion:** `list_deletion_requests`, `create_deletion_request`, `cancel_deletion_request`, `preview_deletion_filters`

**Other:** `get_tracking_metadata`

## Key Types

Run `python3 ${CLAUDE_SKILL_DIR}/scripts/help.py types` for the full list of all types. Use `help.py <TypeName>` for fields, constructors, and enum values.
Full reference: `WebFetch(url="https://jaredmcfarland.github.io/mixpanel_data/api/types/index.md")`

| Type | Purpose |
|------|---------|
| `Filter` | Property filter conditions (`.equals()`, `.contains()`, `.in_cohort()`, etc.) |
| `GroupBy` | Property breakdown with optional bucketing |
| `Formula` | Calculated metric expression referencing events by position (A, B, C...) |
| `Metric` | Event with per-event math/aggregation settings |
| `CohortMetric` | Track cohort size over time as an event metric |
| `FunnelStep` | Funnel step with per-step filters, labels, ordering |
| `Exclusion` | Event to exclude between funnel steps |
| `HoldingConstant` | Property to hold constant across funnel steps |
| `RetentionEvent` | Retention event with per-event filters |
| `FlowStep` | Flow anchor event with per-step forward/reverse configuration |
| `TimeComparison` | Period-over-period comparison (`.relative("month")`, `.absolute_start(...)`) |
| `FrequencyBreakdown` | Break down by how often users performed an event |
| `FrequencyFilter` | Filter by how often users performed an event |
| `CohortBreakdown` | Break down results by cohort membership |
| `CohortDefinition` | Inline cohort definition for user queries |
| `CohortCriteria` | Atomic condition for cohort membership |
| `CustomPropertyRef` | Reference to a persisted custom property by ID |
| `InlineCustomProperty` | Ephemeral computed property defined by formula |

**Aggregation enums** (use `help.py <EnumName>` to see all values):

| Enum | Used by | Common values |
|------|---------|---------------|
| `MathType` | `query()` | total, unique, dau, average, sum, min, max, percentile, sessions |
| `FunnelMathType` | `query_funnel()` | conversion_rate_unique, conversion_rate_total, average, median |
| `RetentionMathType` | `query_retention()` | retention_rate, retention_count |

## Statistical Analysis — numpy, scipy

All query results produce pandas DataFrames, which integrate directly with numpy and scipy:

```python
import numpy as np
from scipy import stats

# Compare two segments
a = result.df[result.df["platform"] == "iOS"]["count"]
b = result.df[result.df["platform"] == "Android"]["count"]
t_stat, p_value = stats.ttest_ind(a, b)
cohens_d = (a.mean() - b.mean()) / np.sqrt((a.std()**2 + b.std()**2) / 2)

# Useful scipy.stats tests: ttest_ind, mannwhitneyu, chi2_contingency, pearsonr, spearmanr
# Useful numpy: np.percentile, np.corrcoef, np.polyfit (trend lines)
```

## Visualization — matplotlib, seaborn

Save charts to files for the user. Always use a non-interactive backend:

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

fig, ax = plt.subplots(figsize=(10, 5))
result.df.plot(x="date", y="count", ax=ax)
ax.set_title("Daily Logins")
fig.savefig("chart.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# seaborn: sns.lineplot, sns.barplot, sns.heatmap (for retention matrices)
# Multi-panel: fig, axes = plt.subplots(2, 2) for dashboard-style layouts
```

## Exceptions

Full reference: `WebFetch(url="https://jaredmcfarland.github.io/mixpanel_data/api/exceptions/index.md")`

| Exception | When |
|-----------|------|
| `MixpanelDataError` | Base for all errors |
| `ConfigError` | No credentials resolved |
| `AccountNotFoundError` | Named account doesn't exist |
| `AuthenticationError` | Invalid credentials (401) |
| `QueryError` | Invalid query parameters (400) |
| `BookmarkValidationError` | Params failed validation |
| `RateLimitError` | Rate limit exceeded (429) |
| `ServerError` | Mixpanel server error (5xx) |
| `WorkspaceScopeError` | Workspace resolution error |
| `DateRangeTooLargeError` | Date range exceeds API maximum |
| `OAuthError` | OAuth flow error |
