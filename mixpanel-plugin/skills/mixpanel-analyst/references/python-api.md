# Python API Reference — Complete Workspace Methods

Full method signatures for `mixpanel_data.Workspace`, organized by domain. Every method listed here is callable on a `Workspace` instance. Use `help.py` for live docstrings with parameter descriptions.

## Construction

```python
import mixpanel_data as mp

ws = mp.Workspace()                              # default account
ws = mp.Workspace(account="prod")                # named account
ws = mp.Workspace(workspace_id=12345)            # with workspace for App API
ws = mp.Workspace(project_id=67890, region="eu") # explicit project
```

## Discovery

```python
ws.events() -> list[str]
ws.properties(event: str) -> list[str]
ws.property_values(property_name: str, *, event: str | None = None, limit: int = 100) -> list[str]
ws.top_events(limit: int = 10) -> list[TopEvent]
ws.funnels() -> list[FunnelInfo]
ws.cohorts() -> list[SavedCohort]
ws.list_bookmarks(bookmark_type: BookmarkType | None = None) -> list[BookmarkInfo]
ws.lexicon_schemas() -> list[LexiconSchema]
ws.lexicon_schema(entity_type: EntityType, name: str) -> LexiconSchema
ws.clear_discovery_cache() -> None
```

## Analytics — Core Queries

```python
ws.segmentation(
    event: str, *, from_date: str, to_date: str,
    on: str | None = None,
    unit: Literal["day","week","month"] = "day",
    where: str | None = None,
) -> SegmentationResult

ws.funnel(
    funnel_id: int, from_date: str, to_date: str,
    unit: Literal["day","week","month"] | None = None,
    on: str | None = None,
) -> FunnelResult

ws.retention(
    *, born_event: str, return_event: str,
    from_date: str, to_date: str,
    born_where: str | None = None,
    return_where: str | None = None,
    interval: int = 1,
    interval_count: int = 10,
    unit: Literal["day","week","month"] = "day",
) -> RetentionResult

ws.jql(script: str, params: dict | None = None) -> JQLResult

ws.query_saved_report(bookmark_id: int) -> SavedReportResult
```

## Analytics — Extended Queries

```python
ws.event_counts(
    events: list[str], unit: str = "day",
    from_date: str = ..., to_date: str = ...,
    where: str | None = None,
) -> EventCountsResult

ws.property_counts(
    event: str, property: str, unit: str = "day",
    from_date: str = ..., to_date: str = ...,
    where: str | None = None,
) -> PropertyCountsResult

ws.activity_feed(distinct_ids: list[str], *, from_date: str | None = None, to_date: str | None = None) -> ActivityFeedResult

ws.query_flows(bookmark_id: int) -> FlowsResult

ws.frequency(
    *, from_date: str, to_date: str,
    unit: str = ..., event: str | None = None,
    where: str | None = None,
) -> FrequencyResult

ws.segmentation_numeric(
    event: str, property: str, unit: str = "day",
    from_date: str = ..., to_date: str = ...,
    where: str | None = None,
) -> NumericBucketResult

ws.segmentation_sum(
    event: str, on: str, unit: str = "day",
    from_date: str = ..., to_date: str = ...,
    where: str | None = None,
) -> NumericSumResult

ws.segmentation_average(
    event: str, on: str, unit: str = "day",
    from_date: str = ..., to_date: str = ...,
    where: str | None = None,
) -> NumericAverageResult
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
    from_date: str, to_date: str,
    events: list[str] | None = None,
    where: str | None = None,
) -> Iterator[dict[str, Any]]

ws.stream_profiles(
    where: str | None = None,
    cohort_id: str | None = None,
    output_properties: list[str] | None = None,
    raw: bool = False,
    distinct_id: str | None = None,
    distinct_ids: list[str] | None = None,
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
```

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

## Key Result Types

All query results have a `.df` property returning a pandas DataFrame. Key types:

| Type | From Method | Key Properties |
|------|------------|----------------|
| `SegmentationResult` | `segmentation()` | `.df`, `.data`, `.series` |
| `FunnelResult` | `funnel()` | `.df`, `.steps`, `.conversion_rates` |
| `RetentionResult` | `retention()` | `.df`, `.data` |
| `JQLResult` | `jql()` | `.df`, `.data` |
| `EventCountsResult` | `event_counts()` | `.df`, `.data` |
| `ActivityFeedResult` | `activity_feed()` | `.events` |
| `FlowsResult` | `query_flows()` | `.df`, `.data` |
| `FrequencyResult` | `frequency()` | `.df`, `.data` |

## Exception Hierarchy

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
├── OAuthError
└── WorkspaceScopeError
```
