# Quick Start

This guide walks you through your first queries with mixpanel_data in about 5 minutes.

!!! tip "Explore on DeepWiki"
    🤖 **[Quick Start Tutorial →](https://deepwiki.com/jaredmcfarland/mixpanel_data/2.3-quick-start-tutorial)**

    Ask questions about getting started, explore example workflows, or troubleshoot common issues.

## Prerequisites

You'll need:

- mixpanel_data installed (`pip install git+https://github.com/jaredmcfarland/mixpanel_data.git`)
- **Either** a Mixpanel service account (username, secret, project ID) **or** a Mixpanel user account (for OAuth login)
- Your project's data residency region (us, eu, or in)

## Step 1: Set Up Credentials

### Option A: Environment Variables (Service Account)

```bash
export MP_USERNAME="sa_abc123..."
export MP_SECRET="your-secret-here"
export MP_PROJECT_ID="12345"
export MP_REGION="us"
```

### Option B: Config File (Service Account)

```bash
# Interactive prompt (secure, recommended)
mp auth add production \
    --username sa_abc123... \
    --project 12345 \
    --region us
# You'll be prompted for the service account secret with hidden input
```

This stores credentials in `~/.mp/config.toml` and sets `production` as the default account.

For CI/CD environments, provide the secret via environment variable or stdin:

```bash
# Via environment variable
MP_SECRET=your-secret mp auth add production --username sa_abc123... --project 12345

# Via stdin
echo "$SECRET" | mp auth add production --username sa_abc123... --project 12345 --secret-stdin
```

### Option C: OAuth Login (Interactive)

For interactive use without managing service account credentials:

```bash
# Login via browser (opens Mixpanel authorization page)
mp auth login --region us --project-id 12345

# Check your auth status
mp auth status
```

OAuth tokens are stored locally at `~/.mp/oauth/` and automatically refreshed when expired. See [Configuration](configuration.md#oauth-authentication) for details.

## Step 2: Test Your Connection

Verify credentials are working:

=== "CLI"

    ```bash
    mp auth test
    ```

=== "Python"

    ```python
    import mixpanel_data as mp

    ws = mp.Workspace()
    ws.test_credentials()  # Raises AuthenticationError if invalid
    ```

## Step 3: Explore Your Data

Before writing queries, survey your data landscape. Discovery commands let you see what exists in your Mixpanel project without guessing.

### List Events

=== "CLI"

    ```bash
    mp inspect events
    ```

=== "Python"

    ```python
    import mixpanel_data as mp

    ws = mp.Workspace()
    events = ws.list_events()
    for e in events[:10]:
        print(e.name)
    ```

### Drill Into Properties

Once you know an event name, see what properties it has:

=== "CLI"

    ```bash
    mp inspect properties "Purchase"
    ```

=== "Python"

    ```python
    props = ws.list_properties("Purchase")
    for p in props:
        print(f"{p.name}: {p.type}")
    ```

### Sample Property Values

See actual values a property contains:

=== "CLI"

    ```bash
    mp inspect values "Purchase" "country"
    ```

=== "Python"

    ```python
    values = ws.list_property_values("Purchase", "country")
    print(values)  # ['US', 'UK', 'DE', 'FR', ...]
    ```

### See What's Active

Check today's top events by volume:

=== "CLI"

    ```bash
    mp inspect top-events
    ```

=== "Python"

    ```python
    top = ws.top_events()
    for e in top[:5]:
        print(f"{e.name}: {e.count:,} events")
    ```

### Browse Saved Assets

See funnels, cohorts, and saved reports already defined in Mixpanel:

=== "CLI"

    ```bash
    mp inspect funnels
    mp inspect cohorts
    mp inspect bookmarks
    ```

=== "Python"

    ```python
    funnels = ws.list_funnels()
    cohorts = ws.list_cohorts()
    bookmarks = ws.list_bookmarks()
    ```

This discovery workflow ensures your queries reference real event names, valid properties, and actual values—no trial and error.

## Step 4: Run Analytics Queries

### Insights Queries (Recommended)

Use `query()` for typed, composable analytics — DAU/WAU/MAU, formulas, filters, breakdowns, and more:

```python
import mixpanel_data as mp
from mixpanel_data import Metric, Filter

ws = mp.Workspace()

# Simple event count (last 30 days by default)
result = ws.query("Purchase")
print(result.df)

# DAU with property breakdown
result = ws.query("Login", math="dau", group_by="platform", last=90)

# Filtered aggregation
result = ws.query(
    "Purchase",
    math="total",
    math_property="amount",
    where=Filter.equals("country", "US"),
)

# Multi-metric formula
result = ws.query(
    [Metric("Signup", math="unique"), Metric("Purchase", math="unique")],
    formula="(B / A) * 100",
    formula_label="Conversion Rate",
)
```

See the [Insights Queries guide](../guide/query.md) for full coverage.

### Legacy Query Methods

For segmentation, funnels, and retention via the older Query API:

=== "CLI"

    ```bash
    mp query segmentation --event Purchase --from 2025-01-01 --to 2025-01-31 --format table

    # Filter results with built-in jq support
    mp query segmentation --event Purchase --from 2025-01-01 --to 2025-01-31 \
        --format json --jq '.total'
    ```

=== "Python"

    ```python
    import mixpanel_data as mp

    ws = mp.Workspace()

    result = ws.segmentation(
        event="Purchase",
        from_date="2025-01-01",
        to_date="2025-01-31"
    )

    # Access as DataFrame
    print(result.df)
    ```

## Step 5: Manage Entities & Data Governance (Optional)

Create, update, and delete dashboards, reports, cohorts, feature flags, and experiments:

=== "CLI"

    ```bash
    # List your dashboards
    mp dashboards list

    # Create a cohort
    mp cohorts create --name "Premium Users"

    # List saved reports
    mp reports list --type insights

    # Feature flags and experiments
    mp flags list
    mp experiments create --name "Checkout Flow Test"

    # Data governance
    mp lexicon events get --names Signup
    mp drop-filters list
    mp custom-properties list
    mp lookup-tables list
    mp schemas list
    mp lexicon enforcement get
    mp lexicon audit
    ```

=== "Python"

    ```python
    import mixpanel_data as mp

    ws = mp.Workspace()

    dashboards = ws.list_dashboards()
    cohort = ws.create_cohort(mp.CreateCohortParams(name="Premium Users"))
    reports = ws.list_bookmarks_v2(bookmark_type="insights")

    # Feature flags and experiments
    flags = ws.list_feature_flags()
    exp = ws.create_experiment(mp.CreateExperimentParams(name="Checkout Flow Test"))

    # Data governance
    event_defs = ws.get_event_definitions(names=["Signup"])
    drop_filters = ws.list_drop_filters()
    schemas = ws.list_schema_registry()
    audit = ws.run_audit()
    ```

See the [Entity Management guide](../guide/entity-management.md) for complete coverage of dashboard, report, cohort, feature flag, and experiment operations. See the [Data Governance guide](../guide/data-governance.md) for Lexicon definitions, drop filters, custom properties, custom events, lookup tables, schema registry, schema enforcement, data auditing, and event deletion requests.

## Step 6: Stream Data

For ETL pipelines or data processing, stream data directly:

=== "Python"

    ```python
    import mixpanel_data as mp

    ws = mp.Workspace()
    for event in ws.stream_events(from_date="2025-01-01", to_date="2025-01-31"):
        send_to_warehouse(event)
    ws.close()
    ```

## Next Steps

- [Configuration](configuration.md) — Multiple accounts and advanced settings
- [Insights Queries](../guide/query.md) — Typed analytics with DAU, formulas, filters, and breakdowns
- [Live Analytics](../guide/live-analytics.md) — Segmentation, funnels, retention
- [Entity Management](../guide/entity-management.md) — Manage dashboards, reports, cohorts, feature flags, and experiments
- [Data Governance](../guide/data-governance.md) — Manage Lexicon definitions, drop filters, custom properties, and lookup tables
- [Streaming Data](../guide/streaming.md) — Stream events and profiles for ETL pipelines
