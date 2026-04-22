# mixpanel_data Package

A complete programmable interface to Mixpanel analytics—Python library and CLI for discovery, querying, streaming, and entity management.

**Design principles:**
- **Self-documenting**: Typed dataclasses with `.df` and `.to_dict()`, exceptions with structured context
- **Discovery-first**: List events, properties, funnels, cohorts, and bookmarks before querying
- **API-first**: Live API queries for analytics, streaming for data extraction

Public API for the Mixpanel data library. Import from here, not from `_internal`.

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Public exports (Workspace, exceptions, types) |
| `workspace.py` | Main facade class orchestrating all operations |
| `auth.py` | Thin re-export of legacy auth surface (ConfigManager, Credentials, AuthMethod, BridgeFile, load_bridge) |
| `auth_types.py` | v3 auth surface (Account discriminated union + ServiceAccount/OAuthBrowserAccount/OAuthTokenAccount, Session, Region, OAuthTokens, etc.) |
| `accounts.py` | Functional API for account lifecycle (`mp.accounts.add/use/login/...`) |
| `session.py` | Functional API for active-session axes (`mp.session.show/use`) |
| `targets.py` | Functional API for named targets (account+project+workspace bundles) |
| `exceptions.py` | Exception hierarchy with structured error context |
| `types.py` | Result dataclasses (SegmentationResult, FunnelResult, etc.) + AccountSummary |
| `_literal_types.py` | Literal type aliases (TimeUnit, CountType, HourDayUnit) |
| `_internal/` | Private implementation (do not import directly) |
| `cli/` | Command-line interface |

## Primary Entry Point

```python
from mixpanel_data import Workspace

# Standard usage (credentials from env/config)
ws = Workspace()
events = ws.list_events()
result = ws.segmentation(event="Login", from_date="2025-01-01", to_date="2025-01-31")
ws.close()

# Context manager (auto-cleanup)
with Workspace() as ws:
    for event in ws.stream_events(from_date="2025-01-01", to_date="2025-01-31"):
        process(event)
```

## Workspace Methods

**Discovery** (self-documenting API): `events()`, `properties()`, `property_values()`, `funnels()`, `cohorts()`, `list_bookmarks()`, `top_events()`, `lexicon_schemas()`, `lexicon_schema()`, `clear_discovery_cache()`

**Streaming**: `stream_events()`, `stream_profiles()`

**Core Analytics**: `segmentation()`, `funnel()`, `retention()`, `query_saved_report()`

**Typed Flow Queries**: `query_flow()`, `build_flow_params()`

**User Profile Queries**: `query_user()`, `build_user_params()`

**Extended Live Queries**: `jql()`, `event_counts()`, `property_counts()`, `activity_feed()`, `query_saved_flows()`, `frequency()`, `segmentation_numeric()`, `segmentation_sum()`, `segmentation_average()`

**JQL Discovery**: `property_distribution()`, `numeric_summary()`, `daily_counts()`, `engagement_distribution()`, `property_coverage()`

**Dashboard CRUD**: `list_dashboards()`, `create_dashboard()`, `get_dashboard()`, `update_dashboard()`, `delete_dashboard()`, `bulk_delete_dashboards()`, `favorite_dashboard()`, `unfavorite_dashboard()`, `pin_dashboard()`, `unpin_dashboard()`, `remove_report_from_dashboard()`, `list_blueprint_templates()`, `create_blueprint()`, `get_blueprint_config()`, `update_blueprint_cohorts()`, `finalize_blueprint()`, `create_rca_dashboard()`, `get_bookmark_dashboard_ids()`, `get_dashboard_erf()`, `update_report_link()`, `update_text_card()`

**Report/Bookmark CRUD**: `list_bookmarks_v2()`, `create_bookmark()`, `get_bookmark()`, `update_bookmark()`, `delete_bookmark()`, `bulk_delete_bookmarks()`, `bulk_update_bookmarks()`, `bookmark_linked_dashboard_ids()`, `get_bookmark_history()`

**Cohort CRUD**: `list_cohorts_full()`, `get_cohort()`, `create_cohort()`, `update_cohort()`, `delete_cohort()`, `bulk_delete_cohorts()`, `bulk_update_cohorts()`

**Feature Flag CRUD**: `list_feature_flags()`, `create_feature_flag()`, `get_feature_flag()`, `update_feature_flag()`, `delete_feature_flag()`, `archive_feature_flag()`, `restore_feature_flag()`, `duplicate_feature_flag()`, `set_flag_test_users()`, `get_flag_history()`, `get_flag_limits()`

**Experiment CRUD**: `list_experiments()`, `create_experiment()`, `get_experiment()`, `update_experiment()`, `delete_experiment()`, `launch_experiment()`, `conclude_experiment()`, `decide_experiment()`, `archive_experiment()`, `restore_experiment()`, `duplicate_experiment()`, `list_erf_experiments()`

**Annotation CRUD**: `list_annotations()`, `create_annotation()`, `get_annotation()`, `update_annotation()`, `delete_annotation()`, `list_annotation_tags()`, `create_annotation_tag()`

**Webhook CRUD**: `list_webhooks()`, `create_webhook()`, `update_webhook()`, `delete_webhook()`, `test_webhook()`

**Alert CRUD**: `list_alerts()`, `create_alert()`, `get_alert()`, `update_alert()`, `delete_alert()`, `bulk_delete_alerts()`, `get_alert_count()`, `get_alert_history()`, `test_alert()`, `get_alert_screenshot_url()`, `validate_alerts_for_bookmark()`

**Data Governance — Lexicon**: `get_event_definitions()`, `update_event_definition()`, `delete_event_definition()`, `bulk_update_event_definitions()`, `get_property_definitions()`, `update_property_definition()`, `bulk_update_property_definitions()`, `list_lexicon_tags()`, `create_lexicon_tag()`, `update_lexicon_tag()`, `delete_lexicon_tag()`, `get_tracking_metadata()`, `get_event_history()`, `get_property_history()`, `export_lexicon()`

**Data Governance — Drop Filters**: `list_drop_filters()`, `create_drop_filter()`, `update_drop_filter()`, `delete_drop_filter()`, `get_drop_filter_limits()`

**Data Governance — Custom Properties**: `list_custom_properties()`, `create_custom_property()`, `get_custom_property()`, `update_custom_property()`, `delete_custom_property()`, `validate_custom_property()`

**Data Governance — Lookup Tables**: `list_lookup_tables()`, `upload_lookup_table()`, `mark_lookup_table_ready()`, `get_lookup_upload_url()`, `get_lookup_upload_status()`, `update_lookup_table()`, `delete_lookup_tables()`, `download_lookup_table()`, `get_lookup_download_url()`

**Data Governance — Custom Events**: `list_custom_events()`, `create_custom_event()`, `update_custom_event()`, `delete_custom_event()`

**Escape Hatches**: `api` (MixpanelAPIClient)

## Exception Hierarchy

```
MixpanelDataError
├── ConfigError
│   ├── AccountNotFoundError
│   └── AccountExistsError
├── APIError
│   ├── AuthenticationError
│   ├── RateLimitError
│   ├── QueryError
│   │   └── JQLSyntaxError
│   └── ServerError
├── OAuthError
└── WorkspaceScopeError
```

All exceptions provide `.to_dict()` for JSON serialization and structured `.details`.

## Result Types

All frozen dataclasses with:
- `.df` property: Lazy DataFrame conversion (cached)
- `.to_dict()`: JSON-serializable output

Key types: `SegmentationResult`, `FunnelResult`, `RetentionResult`, `JQLResult`, `SavedReportResult`, `FlowsResult`, `UserQueryResult`, `BookmarkInfo`, `PropertyDistributionResult`, `NumericPropertySummaryResult`, `DailyCountsResult`, `EngagementDistributionResult`, `PropertyCoverageResult`, `Dashboard`, `CreateDashboardParams`, `UpdateDashboardParams`, `Bookmark`, `CreateBookmarkParams`, `UpdateBookmarkParams`, `Cohort`, `CreateCohortParams`, `UpdateCohortParams`, `BlueprintTemplate`, `BlueprintConfig`, `BookmarkHistoryResponse`

## Type Aliases

For type hints in consuming code:
- `TimeUnit = Literal["day", "week", "month"]`
- `HourDayUnit = Literal["hour", "day"]`
- `CountType = Literal["general", "unique", "average"]`
