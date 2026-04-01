# Entity Management

Manage Mixpanel dashboards, reports (bookmarks), and cohorts programmatically. Full CRUD operations with bulk support.

!!! note "Prerequisites"
    Entity management requires:

    - **Authentication** — Service account or OAuth credentials
    - **Workspace ID** — Set via `MP_WORKSPACE_ID` env var, `--workspace-id` CLI flag, or `ws.set_workspace_id()`

    Find your workspace ID with `mp inspect info` or `ws.info()`.

## Dashboards

### List Dashboards

=== "Python"

    ```python
    import mixpanel_data as mp

    ws = mp.Workspace()

    # List all dashboards
    dashboards = ws.list_dashboards()
    for d in dashboards:
        print(f"{d.id}: {d.title}")

    # Filter by specific IDs
    dashboards = ws.list_dashboards(ids=[123, 456])
    ```

=== "CLI"

    ```bash
    # List all dashboards
    mp dashboards list

    # Filter by IDs
    mp dashboards list --ids 123,456

    # Table format for quick scanning
    mp dashboards list --format table
    ```

### Create a Dashboard

=== "Python"

    ```python
    new_dash = ws.create_dashboard(mp.CreateDashboardParams(
        title="Q1 Metrics",
        description="Quarterly performance overview",
    ))
    print(f"Created dashboard {new_dash.id}: {new_dash.title}")
    ```

=== "CLI"

    ```bash
    mp dashboards create --title "Q1 Metrics" --description "Quarterly performance overview"
    ```

### Get, Update, Delete

=== "Python"

    ```python
    # Get a dashboard by ID
    dash = ws.get_dashboard(123)

    # Update
    updated = ws.update_dashboard(123, mp.UpdateDashboardParams(
        title="Q1 Metrics (Updated)",
        description="Revised quarterly overview",
    ))

    # Delete
    ws.delete_dashboard(123)

    # Bulk delete
    ws.bulk_delete_dashboards([123, 456, 789])
    ```

=== "CLI"

    ```bash
    # Get details
    mp dashboards get 123

    # Update
    mp dashboards update 123 --title "Q1 Metrics (Updated)"

    # Delete
    mp dashboards delete 123

    # Bulk delete
    mp dashboards bulk-delete --ids 123,456,789
    ```

### Favorites and Pins

=== "Python"

    ```python
    ws.favorite_dashboard(123)
    ws.unfavorite_dashboard(123)

    ws.pin_dashboard(123)
    ws.unpin_dashboard(123)
    ```

=== "CLI"

    ```bash
    mp dashboards favorite 123
    mp dashboards unfavorite 123

    mp dashboards pin 123
    mp dashboards unpin 123
    ```

### Remove a Report from a Dashboard

=== "Python"

    ```python
    updated_dash = ws.remove_report_from_dashboard(
        dashboard_id=123,
        bookmark_id=456
    )
    ```

=== "CLI"

    ```bash
    mp dashboards remove-report 123 --bookmark-id 456
    ```

### Blueprint Dashboards

Create dashboards from pre-built templates:

=== "Python"

    ```python
    # List available templates
    templates = ws.list_blueprint_templates()
    for t in templates:
        print(f"{t.title_key}: {t.number_of_reports} reports")

    # Create from template
    dash = ws.create_blueprint(template_type="product_analytics")

    # Configure and finalize
    config = ws.get_blueprint_config(dash.id)
    ws.finalize_blueprint(mp.BlueprintFinishParams(
        dashboard_id=dash.id,
        cards=config.cards,
    ))
    ```

=== "CLI"

    ```bash
    # List templates
    mp dashboards blueprints

    # Create from template
    mp dashboards blueprint-create --template-type product_analytics
    ```

### Advanced Dashboard Operations

=== "Python"

    ```python
    # Create an RCA (Root Cause Analysis) dashboard
    rca_dash = ws.create_rca_dashboard(mp.CreateRcaDashboardParams(
        rca_source_id=123,
        rca_source_data=mp.RcaSourceData(source_type="metric"),
    ))

    # Get ERF metrics
    erf = ws.get_dashboard_erf(dashboard_id=123)

    # Update dashboard components
    ws.update_report_link(
        dashboard_id=123,
        report_link_id=456,
        params=mp.UpdateReportLinkParams(link_type="embedded"),
    )
    ws.update_text_card(
        dashboard_id=123,
        text_card_id=789,
        params=mp.UpdateTextCardParams(markdown="## Updated Header"),
    )
    ```

=== "CLI"

    ```bash
    # Get ERF metrics
    mp dashboards erf 123

    # Update text card
    mp dashboards update-text-card 123 --text-card-id 789 --markdown "## Updated"
    ```

---

## Reports (Bookmarks)

Reports in Mixpanel are stored as "bookmarks". Each bookmark has a type (insights, funnels, flows, retention, etc.) and a params JSON object defining the query.

### List Reports

=== "Python"

    ```python
    # List all reports
    reports = ws.list_bookmarks_v2()

    # Filter by type
    insights = ws.list_bookmarks_v2(bookmark_type="insights")
    funnels = ws.list_bookmarks_v2(bookmark_type="funnels")

    # Filter by IDs
    specific = ws.list_bookmarks_v2(ids=[123, 456])

    for r in reports:
        print(f"{r.id}: {r.name} ({r.bookmark_type})")
    ```

=== "CLI"

    ```bash
    # List all reports
    mp reports list

    # Filter by type
    mp reports list --type insights
    mp reports list --type funnels

    # Filter by IDs
    mp reports list --ids 123,456
    ```

### Create a Report

=== "Python"

    ```python
    report = ws.create_bookmark(mp.CreateBookmarkParams(
        name="Daily Signups",
        bookmark_type="insights",
        description="Track daily signup volume",
        params={"event": "Signup"},
    ))
    print(f"Created report {report.id}: {report.name}")
    ```

=== "CLI"

    ```bash
    mp reports create \
        --name "Daily Signups" \
        --type insights \
        --description "Track daily signup volume" \
        --params '{"event": "Signup"}'
    ```

### Get, Update, Delete

=== "Python"

    ```python
    # Get
    report = ws.get_bookmark(123)

    # Update
    updated = ws.update_bookmark(123, mp.UpdateBookmarkParams(
        name="Daily Signups v2",
        description="Updated tracking",
    ))

    # Delete
    ws.delete_bookmark(123)

    # Bulk operations
    ws.bulk_delete_bookmarks([123, 456])
    ws.bulk_update_bookmarks([
        mp.BulkUpdateBookmarkEntry(id=123, name="Renamed Report"),
        mp.BulkUpdateBookmarkEntry(id=456, description="Updated desc"),
    ])
    ```

=== "CLI"

    ```bash
    # Get
    mp reports get 123

    # Update
    mp reports update 123 --name "Daily Signups v2"

    # Delete
    mp reports delete 123

    # Bulk delete
    mp reports bulk-delete --ids 123,456
    ```

### Report History and Dashboard Links

=== "Python"

    ```python
    # View change history
    history = ws.get_bookmark_history(bookmark_id=123)
    for entry in history.data:
        print(entry)

    # Paginate through history
    history = ws.get_bookmark_history(bookmark_id=123, page_size=10)
    if history.pagination.has_more:
        next_page = ws.get_bookmark_history(
            bookmark_id=123,
            cursor=history.pagination.cursor,
        )

    # Find which dashboards contain this report
    dashboard_ids = ws.bookmark_linked_dashboard_ids(bookmark_id=123)
    ```

=== "CLI"

    ```bash
    # View history
    mp reports history 123

    # Get linked dashboards
    mp reports linked-dashboards 123
    ```

---

## Cohorts

### List Cohorts

=== "Python"

    ```python
    # List all cohorts
    cohorts = ws.list_cohorts_full()

    # Filter by data group
    cohorts = ws.list_cohorts_full(data_group_id="default")

    # Filter by IDs
    cohorts = ws.list_cohorts_full(ids=[123, 456])

    for c in cohorts:
        print(f"{c.id}: {c.name} ({c.count} users)")
    ```

=== "CLI"

    ```bash
    # List all cohorts
    mp cohorts list

    # Filter by data group
    mp cohorts list --data-group-id default

    # Filter by IDs
    mp cohorts list --ids 123,456
    ```

### Create a Cohort

=== "Python"

    ```python
    cohort = ws.create_cohort(mp.CreateCohortParams(
        name="Power Users",
        description="Users with 10+ sessions in last 30 days",
    ))
    print(f"Created cohort {cohort.id}: {cohort.name}")
    ```

=== "CLI"

    ```bash
    mp cohorts create --name "Power Users" --description "Users with 10+ sessions"
    ```

### Get, Update, Delete

=== "Python"

    ```python
    # Get
    cohort = ws.get_cohort(123)

    # Update
    updated = ws.update_cohort(123, mp.UpdateCohortParams(
        name="Super Users",
        description="Updated criteria",
    ))

    # Delete
    ws.delete_cohort(123)

    # Bulk operations
    ws.bulk_delete_cohorts([123, 456])
    ws.bulk_update_cohorts([
        mp.BulkUpdateCohortEntry(id=123, name="Renamed Cohort"),
        mp.BulkUpdateCohortEntry(id=456, description="Updated"),
    ])
    ```

=== "CLI"

    ```bash
    # Get
    mp cohorts get 123

    # Update
    mp cohorts update 123 --name "Super Users"

    # Delete
    mp cohorts delete 123

    # Bulk delete
    mp cohorts bulk-delete --ids 123,456
    ```

---

## Next Steps

- [API Reference — Workspace](../api/workspace.md) — Complete method signatures and docstrings
- [API Reference — Types](../api/types.md) — Dashboard, Bookmark, Cohort type definitions
- [CLI Reference](../cli/index.md) — Full CLI command documentation
