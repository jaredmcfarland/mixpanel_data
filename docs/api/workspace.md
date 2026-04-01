# Workspace

The `Workspace` class is the unified entry point for all Mixpanel data operations.

!!! tip "Explore on DeepWiki"
    🤖 **[Workspace Class Deep Dive →](https://deepwiki.com/jaredmcfarland/mixpanel_data/3.2.1-workspace-class)**

    Ask questions about Workspace methods, explore usage patterns, or understand how services are orchestrated.

## Overview

Workspace orchestrates four internal services and provides direct App API access:

- **DiscoveryService** — Schema exploration (events, properties, funnels, cohorts)
- **FetcherService** — Data ingestion from Mixpanel to DuckDB, or streaming without storage
- **LiveQueryService** — Real-time analytics queries
- **StorageEngine** — Local SQL query execution
- **Entity CRUD** — Create, read, update, delete dashboards, reports, and cohorts via Mixpanel App API

## Key Features

### Parallel Fetching

For large date ranges, use `parallel=True` for up to 10x faster exports:

```python
# Parallel fetch for large date ranges (recommended)
result = ws.fetch_events(
    name="events",
    from_date="2024-01-01",
    to_date="2024-12-31",
    parallel=True
)

print(f"Fetched {result.total_rows} rows in {result.duration_seconds:.1f}s")
```

Parallel fetching:

- Splits date ranges into 7-day chunks (configurable via `chunk_days`)
- Fetches chunks concurrently (configurable via `max_workers`, default: 10)
- Returns `ParallelFetchResult` with batch statistics and failure tracking
- Supports progress callbacks via `on_batch_complete`

### Parallel Profile Fetching

For large profile datasets, use `parallel=True` for up to 5x faster exports:

```python
# Parallel profile fetch for large datasets
result = ws.fetch_profiles(
    name="users",
    parallel=True,
    max_workers=5  # Default and max is 5
)

print(f"Fetched {result.total_rows} profiles in {result.duration_seconds:.1f}s")
print(f"Pages: {result.successful_pages} succeeded, {result.failed_pages} failed")
```

Parallel profile fetching:

- Uses page-based parallelism with session IDs for consistency
- Fetches pages concurrently (configurable via `max_workers`, default: 5, max: 5)
- Returns `ParallelProfileResult` with page statistics and failure tracking
- Supports progress callbacks via `on_page_complete`

### Append Mode

The `fetch_events()` and `fetch_profiles()` methods support an `append` parameter for incremental data loading:

```python
# Initial fetch
ws.fetch_events(name="events", from_date="2025-01-01", to_date="2025-01-31")

# Append more data (duplicates are automatically skipped)
ws.fetch_events(name="events", from_date="2025-02-01", to_date="2025-02-28", append=True)
```

This is useful for:

- **Incremental loading**: Fetch data in chunks without creating multiple tables
- **Crash recovery**: Resume a failed fetch from the last successful point
- **Extending date ranges**: Add more historical or recent data to an existing table
- **Retrying failed parallel batches**: Use append mode to retry specific date ranges

Duplicate events (by `insert_id`) and profiles (by `distinct_id`) are automatically skipped via `INSERT OR IGNORE`.

### Entity CRUD

Manage dashboards, reports (bookmarks), and cohorts programmatically via the Mixpanel App API:

```python
import mixpanel_data as mp

ws = mp.Workspace()

# Dashboards
dashboards = ws.list_dashboards()
new_dash = ws.create_dashboard(mp.CreateDashboardParams(title="Q1 Metrics"))
ws.update_dashboard(new_dash.id, mp.UpdateDashboardParams(title="Q1 Metrics v2"))
ws.favorite_dashboard(new_dash.id)

# Reports (Bookmarks)
reports = ws.list_bookmarks_v2()
report = ws.create_bookmark(mp.CreateBookmarkParams(
    name="Daily Signups",
    bookmark_type="insights"
))

# Cohorts
cohorts = ws.list_cohorts_full()
cohort = ws.create_cohort(mp.CreateCohortParams(name="Power Users"))
ws.update_cohort(cohort.id, mp.UpdateCohortParams(name="Super Users"))
```

All entity CRUD operations require a workspace ID, set via `MP_WORKSPACE_ID` environment variable, `--workspace-id` CLI flag, or `ws.set_workspace_id()`. See the [Entity Management guide](../guide/entity-management.md) for complete coverage.

### Advanced Profile Fetching

The `fetch_profiles()` and `stream_profiles()` methods support advanced filtering options:

```python
# Fetch specific users by ID
ws.fetch_profiles(name="vip_users", distinct_ids=["user_1", "user_2", "user_3"])

# Fetch group profiles (e.g., companies)
ws.fetch_profiles(name="companies", group_id="companies")

# Fetch users based on behavior
ws.fetch_profiles(
    name="purchasers",
    behaviors=[{"window": "30d", "name": "buyers", "event_selectors": [{"event": "Purchase"}]}],
    where='(behaviors["buyers"] > 0)'
)

# Query historical profile state
ws.fetch_profiles(
    name="profiles_last_week",
    as_of_timestamp=int(time.time()) - 604800  # 7 days ago
)

# Get all users with cohort membership marked
ws.fetch_profiles(
    name="cohort_analysis",
    cohort_id="12345",
    include_all_users=True
)
```

**Parameter constraints:**

- `distinct_id` and `distinct_ids` are mutually exclusive
- `behaviors` and `cohort_id` are mutually exclusive
- `include_all_users` requires `cohort_id` to be set

## Class Reference

::: mixpanel_data.Workspace
    options:
      show_root_heading: true
      show_root_toc_entry: true
      members:
        - __init__
        - ephemeral
        - memory
        - open
        - close
        - test_credentials
        - workspace_id
        - set_workspace_id
        - list_workspaces
        - resolve_workspace_id
        - events
        - properties
        - property_values
        - funnels
        - cohorts
        - list_bookmarks
        - top_events
        - lexicon_schemas
        - lexicon_schema
        - clear_discovery_cache
        - fetch_events
        - fetch_profiles
        - stream_events
        - stream_profiles
        - sql
        - sql_scalar
        - sql_rows
        - segmentation
        - funnel
        - retention
        - jql
        - event_counts
        - property_counts
        - activity_feed
        - query_saved_report
        - query_flows
        - frequency
        - segmentation_numeric
        - segmentation_sum
        - segmentation_average
        - property_distribution
        - numeric_summary
        - daily_counts
        - engagement_distribution
        - property_coverage
        - info
        - tables
        - table_schema
        - drop
        - drop_all
        - sample
        - summarize
        - event_breakdown
        - property_keys
        - column_stats
        - connection
        - db_path
        - api
        # Dashboard CRUD
        - list_dashboards
        - create_dashboard
        - get_dashboard
        - update_dashboard
        - delete_dashboard
        - bulk_delete_dashboards
        - favorite_dashboard
        - unfavorite_dashboard
        - pin_dashboard
        - unpin_dashboard
        - remove_report_from_dashboard
        - list_blueprint_templates
        - create_blueprint
        - get_blueprint_config
        - update_blueprint_cohorts
        - finalize_blueprint
        - create_rca_dashboard
        - get_bookmark_dashboard_ids
        - get_dashboard_erf
        - update_report_link
        - update_text_card
        # Report/Bookmark CRUD
        - list_bookmarks_v2
        - create_bookmark
        - get_bookmark
        - update_bookmark
        - delete_bookmark
        - bulk_delete_bookmarks
        - bulk_update_bookmarks
        - bookmark_linked_dashboard_ids
        - get_bookmark_history
        # Cohort CRUD
        - list_cohorts_full
        - get_cohort
        - create_cohort
        - update_cohort
        - delete_cohort
        - bulk_delete_cohorts
        - bulk_update_cohorts
