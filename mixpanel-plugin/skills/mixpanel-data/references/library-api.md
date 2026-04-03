# Python Library API Reference

Complete reference for the `mixpanel_data` Python library.

## Table of Contents
- Workspace Construction
- Discovery Methods
- Streaming Methods
- Live Query Methods
- Escape Hatches

## Workspace Construction

### Workspace()
```python
Workspace(
    account: str | None = None,       # Named account from config
    region: str | None = None,        # Override region (us, eu, in)
)
```
Standard constructor with credentials from config/environment.

## Discovery Methods

### events()
```python
def events(self) -> list[str]
```
List all event names in the project. Cached.

### properties()
```python
def properties(self, event: str) -> list[str]
```
List properties for a specific event. Cached.

### property_values()
```python
def property_values(
    self,
    property_name: str,
    event: str | None = None,
    limit: int = 100,
) -> list[str]
```
Sample values for a property. Cached.

### funnels()
```python
def funnels(self) -> list[FunnelInfo]
```
List saved funnels. Returns `FunnelInfo(funnel_id, name)`. Cached.

### cohorts()
```python
def cohorts(self) -> list[SavedCohort]
```
List saved cohorts. Returns `SavedCohort(id, name, count, description)`. Cached.

### top_events()
```python
def top_events(
    self,
    type: Literal["general", "unique", "average"] = "general",
    limit: int | None = None,
) -> list[TopEvent]
```
Today's trending events. NOT cached.

### list_bookmarks()
```python
def list_bookmarks(
    self,
    bookmark_type: Literal["insights", "funnels", "retention", "flows", "launch-analysis"] | None = None,
) -> list[BookmarkInfo]
```
List saved reports, optionally filtered by type. NOT cached.

### lexicon_schemas()
```python
def lexicon_schemas(
    self,
    entity_type: Literal["event", "profile", "group", "lookup"] | None = None,
) -> list[LexiconSchema]
```
List Lexicon data dictionary schemas. Cached.

### clear_discovery_cache()
```python
def clear_discovery_cache(self) -> None
```
Force refresh of cached discovery data.

## Streaming Methods

### stream_events()
```python
def stream_events(
    self,
    from_date: str,
    to_date: str,
    events: list[str] | None = None,
    where: str | None = None,
    limit: int | None = None,
) -> Iterator[dict]
```
Stream events without local storage. Memory-efficient for large datasets.

### stream_profiles()
```python
def stream_profiles(
    self,
    where: str | None = None,
    cohort_id: str | None = None,
    output_properties: list[str] | None = None,
    raw: bool = False,
    distinct_id: str | None = None,     # Single user ID to fetch
    distinct_ids: list[str] | None = None,  # Multiple user IDs
    group_id: str | None = None,        # Group type for group profiles
    behaviors: list[dict] | None = None,  # Behavioral filters
    as_of_timestamp: int | None = None,   # Historical state Unix timestamp
    include_all_users: bool = False,      # Include all users with cohort marking
) -> Iterator[dict]
```
Stream profiles without local storage.

**Parameter Constraints:**
- `distinct_id` and `distinct_ids` are mutually exclusive
- `behaviors` and `cohort_id` are mutually exclusive
- `include_all_users` requires `cohort_id`

## Live Query Methods

### segmentation()
```python
def segmentation(
    self,
    event: str,
    from_date: str,
    to_date: str,
    on: str | None = None,              # Property to segment by
    unit: Literal["day", "week", "month"] = "day",
    where: str | None = None,           # Filter expression
) -> SegmentationResult
```
Time-series event counts with optional property breakdown.

Returns `SegmentationResult(event, from_date, to_date, unit, segment_property, total, series)`.
Access `.df` for DataFrame.

### funnel()
```python
def funnel(
    self,
    funnel_id: int,
    from_date: str,
    to_date: str,
    unit: Literal["day", "week", "month"] | None = None,
    on: str | None = None,
) -> FunnelResult
```
Conversion analysis through saved funnel steps.

Returns `FunnelResult(funnel_id, from_date, to_date, steps, overall_conversion_rate)`.

### retention()
```python
def retention(
    self,
    born_event: str,                    # Cohort entry event
    return_event: str,                  # Return event
    from_date: str,
    to_date: str,
    born_where: str | None = None,      # Filter for born event
    return_where: str | None = None,    # Filter for return event
    unit: Literal["day", "week", "month"] = "day",
    interval_count: int = 11,           # Number of intervals
) -> RetentionResult
```
Cohort retention analysis.

### jql()
```python
def jql(
    self,
    script: str,
    params: dict[str, Any] | None = None,
) -> JQLResult
```
Execute JavaScript Query Language script.

### event_counts()
```python
def event_counts(
    self,
    events: list[str],
    from_date: str,
    to_date: str,
    type: Literal["general", "unique", "average"] = "general",
    unit: Literal["day", "week", "month"] = "day",
) -> EventCountsResult
```
Multi-event time series comparison.

### property_counts()
```python
def property_counts(
    self,
    event: str,
    property_name: str,
    from_date: str,
    to_date: str,
    type: Literal["general", "unique", "average"] = "general",
    unit: Literal["day", "week", "month"] = "day",
    limit: int = 10,
    values: list[str] | None = None,
) -> PropertyCountsResult
```
Event breakdown by property values.

### activity_feed()
```python
def activity_feed(
    self,
    distinct_ids: list[str],
    from_date: str | None = None,
    to_date: str | None = None,
) -> ActivityFeedResult
```
User event history for specific users.

### query_saved_report()
```python
def query_saved_report(self, bookmark_id: int) -> SavedReportResult
```
Execute a saved Insights, Retention, or Funnel report.

### query_flows()
```python
def query_flows(self, bookmark_id: int) -> FlowsResult
```
Execute a saved Flows report.

### frequency()
```python
def frequency(
    self,
    from_date: str,
    to_date: str,
    unit: Literal["day", "week", "month"] = "day",
    addiction_unit: Literal["hour", "day"] = "hour",
    event: str | None = None,
    where: str | None = None,
) -> FrequencyResult
```
Event frequency distribution (addiction analysis).

### segmentation_numeric()
```python
def segmentation_numeric(
    self,
    event: str,
    from_date: str,
    to_date: str,
    on: str,                            # Numeric property
    unit: Literal["hour", "day"] = "day",
    where: str | None = None,
    type: Literal["general", "unique", "average"] = "general",
) -> NumericBucketResult
```
Bucket events by numeric property ranges.

### segmentation_sum()
```python
def segmentation_sum(
    self,
    event: str,
    from_date: str,
    to_date: str,
    on: str,
    unit: Literal["hour", "day"] = "day",
    where: str | None = None,
) -> NumericSumResult
```
Sum numeric property over time.

### segmentation_average()
```python
def segmentation_average(
    self,
    event: str,
    from_date: str,
    to_date: str,
    on: str,
    unit: Literal["hour", "day"] = "day",
    where: str | None = None,
) -> NumericAverageResult
```
Average numeric property over time.

## Escape Hatches

### api
```python
@property
def api(self) -> MixpanelAPIClient
```
Direct API client for custom requests.
