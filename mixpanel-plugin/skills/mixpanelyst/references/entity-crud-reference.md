# Entity CRUD & Legacy Query Reference

All entity methods require a workspace ID. Use `python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.<method>` for full signatures and parameter types.
User Guide: `WebFetch(url="https://mixpanel.github.io/mixpanel-headless/guide/entity-management/index.md")`

## Dashboard (→ `Dashboard`)

`list_dashboards`, `create_dashboard`, `get_dashboard`, `update_dashboard`, `delete_dashboard`, `bulk_delete_dashboards`, `favorite_dashboard`, `unfavorite_dashboard`, `pin_dashboard`, `unpin_dashboard`, `add_report_to_dashboard`, `remove_report_from_dashboard`, `update_text_card`, `update_report_link`

**Blueprints:** `list_blueprint_templates` → `list[BlueprintTemplate]`, `create_blueprint`, `get_blueprint_config`, `update_blueprint_cohorts`, `finalize_blueprint`, `create_rca_dashboard`

**Helpers:** `get_bookmark_dashboard_ids` → `list[int]`, `get_dashboard_erf` → `dict`

## Bookmark / Report (→ `Bookmark`)

`list_bookmarks_v2`, `create_bookmark`, `get_bookmark`, `update_bookmark`, `delete_bookmark`, `bulk_delete_bookmarks`, `bulk_update_bookmarks`, `bookmark_linked_dashboard_ids` → `list[int]`, `get_bookmark_history` → `BookmarkHistoryResponse`

## Cohort (→ `Cohort`)

`list_cohorts_full`, `get_cohort`, `create_cohort`, `update_cohort`, `delete_cohort`, `bulk_delete_cohorts`, `bulk_update_cohorts`

## Feature Flag (→ `FeatureFlag`)

`list_feature_flags`, `create_feature_flag`, `get_feature_flag`, `update_feature_flag`, `delete_feature_flag`, `archive_feature_flag`, `restore_feature_flag`, `duplicate_feature_flag`, `set_flag_test_users`, `get_flag_history` → `FlagHistoryResponse`, `get_flag_limits` → `FlagLimitsResponse`

## Experiment (→ `Experiment`)

`list_experiments`, `create_experiment`, `get_experiment`, `update_experiment`, `delete_experiment`, `launch_experiment`, `conclude_experiment`, `decide_experiment`, `archive_experiment`, `restore_experiment`, `duplicate_experiment`, `list_erf_experiments` → `list[dict]`

## Alert (→ `CustomAlert`)

`list_alerts`, `create_alert`, `get_alert`, `update_alert`, `delete_alert`, `bulk_delete_alerts`, `get_alert_count` → `AlertCount`, `get_alert_history` → `AlertHistoryResponse`, `test_alert`, `get_alert_screenshot_url`, `validate_alerts_for_bookmark`

## Annotation (→ `Annotation`)

`list_annotations`, `create_annotation`, `get_annotation`, `update_annotation`, `delete_annotation`, `list_annotation_tags` → `list[AnnotationTag]`, `create_annotation_tag`

## Webhook (→ `ProjectWebhook`)

`list_webhooks`, `create_webhook`, `update_webhook`, `delete_webhook`, `test_webhook`

## Lexicon & Data Governance

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

## Legacy Queries & Counts

Older API wrappers. Prefer the typed query methods in SKILL.md when possible. Use `help.py Workspace.<method>` for full signatures.

`segmentation`, `funnel`, `retention`, `event_counts`, `property_counts`, `frequency`, `activity_feed`, `query_saved_report`, `query_saved_flows`, `segmentation_numeric`, `segmentation_sum`, `segmentation_average`
