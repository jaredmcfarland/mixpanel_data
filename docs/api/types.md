# Result Types

!!! tip "Explore on DeepWiki"
    🤖 **[Result Types Reference →](https://deepwiki.com/jaredmcfarland/mixpanel_data/7.5-result-type-reference)**

    Ask questions about result structures, DataFrame conversion, or type usage patterns.

All result types are immutable frozen dataclasses with:

- Lazy DataFrame conversion via the `.df` property
- JSON serialization via the `.to_dict()` method
- Full type hints for IDE/mypy support

## App API Types

Types for the Mixpanel App API infrastructure.

::: mixpanel_data.PublicWorkspace
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CursorPagination
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.PaginatedResponse
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Fetch Results

::: mixpanel_data.FetchResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Parallel Fetch Types

Types for parallel event fetching with progress tracking and failure handling.

::: mixpanel_data.ParallelFetchResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BatchProgress
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BatchResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Parallel Profile Fetch Types

Types for parallel profile fetching with page-based progress tracking.

::: mixpanel_data.ParallelProfileResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.ProfileProgress
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.ProfilePageResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Query Results

::: mixpanel_data.SegmentationResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.FunnelResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.FunnelStep
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.RetentionResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CohortInfo
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.JQLResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Discovery Types

::: mixpanel_data.FunnelInfo
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.SavedCohort
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.TopEvent
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Lexicon Types

::: mixpanel_data.LexiconSchema
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.LexiconDefinition
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.LexiconProperty
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.LexiconMetadata
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Event Analytics Results

::: mixpanel_data.EventCountsResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.PropertyCountsResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Advanced Query Results

::: mixpanel_data.UserEvent
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.ActivityFeedResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.FrequencyResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.NumericBucketResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.NumericSumResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.NumericAverageResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Bookmark Types

::: mixpanel_data.BookmarkInfo
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.SavedReportResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.FlowsResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

## JQL Discovery Types

::: mixpanel_data.PropertyDistributionResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.PropertyValueCount
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.NumericPropertySummaryResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.DailyCountsResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.DailyCount
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.EngagementDistributionResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.EngagementBucket
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.PropertyCoverageResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.PropertyCoverage
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Introspection Types

::: mixpanel_data.ColumnSummary
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.SummaryResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.EventStats
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.EventBreakdownResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.ColumnStatsResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Storage Types

::: mixpanel_data.TableMetadata
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.TableInfo
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.ColumnInfo
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.TableSchema
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.WorkspaceInfo
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Dashboard CRUD Types

::: mixpanel_data.Dashboard
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateDashboardParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateDashboardParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BlueprintTemplate
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BlueprintConfig
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BlueprintCard
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BlueprintFinishParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateRcaDashboardParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.RcaSourceData
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateReportLinkParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateTextCardParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Report CRUD Types

::: mixpanel_data.Bookmark
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BookmarkMetadata
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateBookmarkParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateBookmarkParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BulkUpdateBookmarkEntry
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BookmarkHistoryResponse
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BookmarkHistoryPagination
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Cohort CRUD Types

::: mixpanel_data.Cohort
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CohortCreator
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateCohortParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateCohortParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BulkUpdateCohortEntry
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Feature Flag Enums

::: mixpanel_data.FeatureFlagStatus
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.ServingMethod
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.FlagContractStatus
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Feature Flag Types

::: mixpanel_data.FeatureFlag
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateFeatureFlagParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateFeatureFlagParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.SetTestUsersParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.FlagHistoryParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.FlagHistoryResponse
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.FlagLimitsResponse
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Experiment Enums

::: mixpanel_data.ExperimentStatus
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Experiment Types

::: mixpanel_data.ExperimentCreator
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.Experiment
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateExperimentParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateExperimentParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.ExperimentConcludeParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.ExperimentDecideParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.DuplicateExperimentParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Annotation Types

::: mixpanel_data.Annotation
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AnnotationUser
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AnnotationTag
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateAnnotationParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateAnnotationParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateAnnotationTagParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Webhook Enums

::: mixpanel_data.WebhookAuthType
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Webhook Types

::: mixpanel_data.ProjectWebhook
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateWebhookParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateWebhookParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.WebhookTestParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.WebhookTestResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.WebhookMutationResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Alert Enums

::: mixpanel_data.AlertFrequencyPreset
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Alert Types

::: mixpanel_data.CustomAlert
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AlertBookmark
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AlertCreator
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AlertWorkspace
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AlertProject
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateAlertParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateAlertParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AlertCount
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AlertHistoryPagination
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AlertHistoryResponse
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AlertScreenshotResponse
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AlertValidation
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.ValidateAlertsForBookmarkParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.ValidateAlertsForBookmarkResponse
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Data Governance Enums

::: mixpanel_data.PropertyResourceType
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CustomPropertyResourceType
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Event Definition Types

::: mixpanel_data.EventDefinition
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateEventDefinitionParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BulkEventUpdate
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BulkUpdateEventsParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Property Definition Types

::: mixpanel_data.PropertyDefinition
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdatePropertyDefinitionParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BulkPropertyUpdate
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BulkUpdatePropertiesParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Lexicon Tag Types

::: mixpanel_data.LexiconTag
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateTagParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateTagParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Drop Filter Types

::: mixpanel_data.DropFilter
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateDropFilterParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateDropFilterParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.DropFilterLimitsResponse
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Custom Property Types

::: mixpanel_data.ComposedPropertyValue
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CustomProperty
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateCustomPropertyParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateCustomPropertyParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Lookup Table Types

::: mixpanel_data.LookupTable
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UploadLookupTableParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.MarkLookupTableReadyParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.LookupTableUploadUrl
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateLookupTableParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Schema Registry Types

Types for managing JSON Schema Draft 7 definitions in the schema registry.

::: mixpanel_data.SchemaEntry
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BulkCreateSchemasParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BulkCreateSchemasResponse
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BulkPatchResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.DeleteSchemasResponse
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Schema Enforcement Types

Types for configuring schema enforcement policies.

::: mixpanel_data.SchemaEnforcementConfig
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.InitSchemaEnforcementParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateSchemaEnforcementParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.ReplaceSchemaEnforcementParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Data Audit Types

Types for schema audit operations and violation reporting.

::: mixpanel_data.AuditViolation
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AuditResponse
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Data Volume Anomaly Types

Types for monitoring and managing data volume anomalies.

::: mixpanel_data.DataVolumeAnomaly
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.UpdateAnomalyParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BulkAnomalyEntry
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.BulkUpdateAnomalyParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Event Deletion Request Types

Types for managing event deletion requests.

::: mixpanel_data.EventDeletionRequest
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.CreateDeletionRequestParams
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.PreviewDeletionFiltersParams
    options:
      show_root_heading: true
      show_root_toc_entry: true
