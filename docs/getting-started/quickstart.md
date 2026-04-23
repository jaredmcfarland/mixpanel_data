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
# Set the secret via env var (preferred)
export MP_SECRET="your-secret-here"
mp account add production --type service_account \
    --username sa_abc123... \
    --region us
# Added account 'production' (service_account, us). Set as active.
```

This stores credentials in `~/.mp/config.toml` and sets `production` as the active account.

For CI/CD environments where the secret lives in a shell variable, pipe it via stdin:

```bash
echo "$SECRET" | mp account add production --type service_account \
    --username sa_abc123... --region us --secret-stdin
```

### Option C: OAuth Login (Interactive)

For interactive use without managing service account credentials:

```bash
# Register an OAuth account
mp account add personal --type oauth_browser --region us

# Run the PKCE browser flow
mp account login personal
# Opening browser...
# ✓ Authenticated as jared@example.com

# Inspect resolved state
mp session
```

OAuth tokens are stored at `~/.mp/accounts/personal/tokens.json` and automatically refreshed when expired. The active project is backfilled from the post-login `/me` probe. See [Configuration → OAuth (browser) — token storage](configuration.md#oauth-browser-token-storage) for details.

### Option D: Raw OAuth Bearer Token (CI / Agents)

If a managed OAuth client (e.g., a Claude Code plugin or CI pipeline) hands you a pre-obtained access token, inject it via env vars without going through the browser flow:

```bash
export MP_OAUTH_TOKEN="<bearer-token>"
export MP_PROJECT_ID="12345"
export MP_REGION="us"  # or "eu", "in"
```

The library sends `Authorization: Bearer <token>` on every Mixpanel endpoint. Tokens injected this way are not persisted (no refresh — pass a fresh token when the previous one expires). See [Configuration → OAuth (static bearer / CI)](configuration.md#oauth-static-bearer-ci) and the precedence note under [Environment Variables](configuration.md#environment-variables).

## Step 2: Choose a Project

After authenticating, select which Mixpanel project to query:

=== "CLI"

    ```bash
    mp project list
    # ID        NAME              ORG       WORKSPACES
    # 3713224   AI Demo           Acme      ✓
    # 3018488   E-Commerce Demo   Acme      ✓

    mp project use 3713224
    # Active project: AI Demo (3713224)
    ```

=== "Python"

    ```python
    import mixpanel_data as mp

    ws = mp.Workspace()
    for project in ws.projects():
        print(project.id, project.name)

    ws.use(project="3713224", persist=True)
    ```

`mp project use` writes to the active account's `default_project`. To override per-call without persisting, pass `--project` / `-p` on the CLI or `Workspace(project="...")` in Python.

## Step 3: Test Your Connection

Verify credentials are working:

=== "CLI"

    ```bash
    mp account test
    # { "account_name": "production", "ok": true, "user": {...}, "accessible_project_count": 7 }
    ```

=== "Python"

    ```python
    import mixpanel_data as mp

    result = mp.accounts.test()  # AccountTestResult; raises ConfigError if no active account
    print(result.ok, result.user.email, result.accessible_project_count)
    ```

## Step 4: Explore Your Data

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
    events = ws.events()         # list[str]
    for name in events[:10]:
        print(name)
    ```

### Drill Into Properties

Once you know an event name, see what properties it has:

=== "CLI"

    ```bash
    mp inspect properties "Purchase"
    ```

=== "Python"

    ```python
    props = ws.properties("Purchase")    # list[str]
    for name in props:
        print(name)
    ```

### Sample Property Values

See actual values a property contains:

=== "CLI"

    ```bash
    mp inspect values "Purchase" "country"
    ```

=== "Python"

    ```python
    values = ws.property_values("country", event="Purchase")
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
    funnels = ws.funnels()
    cohorts = ws.cohorts()
    bookmarks = ws.list_bookmarks()
    ```

This discovery workflow ensures your queries reference real event names, valid properties, and actual values—no trial and error.

## Step 5: Run Analytics Queries

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

### Cohort-Scoped Queries

Scope any query to a user segment — define cohorts inline without saving them first:

```python
from mixpanel_data import CohortCriteria, CohortDefinition, Filter, CohortBreakdown

# Define a cohort on the fly
power_users = CohortDefinition(
    CohortCriteria.did_event("Purchase", at_least=3, within_days=30)
)

# Filter to that cohort
result = ws.query("Login", where=Filter.in_cohort(power_users, name="Power Users"))

# Compare cohort vs. everyone else
result = ws.query("Login", group_by=CohortBreakdown(power_users, name="Power Users"))
```

Cohort filters work across all five query methods. See the [Insights Queries guide — Cohort-Scoped Queries](../guide/query.md#cohort-scoped-queries) for full coverage.

### Funnel Queries

Define funnels inline with typed steps — no saved funnel required:

```python
from mixpanel_data import FunnelStep, Filter

# Simple funnel
result = ws.query_funnel(["Signup", "Purchase"])
print(f"Conversion: {result.overall_conversion_rate:.1%}")

# With per-step filters and conversion window
result = ws.query_funnel(
    [
        FunnelStep("Signup"),
        FunnelStep("Purchase", filters=[Filter.greater_than("amount", 50)]),
    ],
    conversion_window=7,
    last=90,
)
print(result.df)
```

See the [Funnel Queries guide](../guide/query-funnels.md) for full coverage.

### Retention Queries

Measure cohort retention with typed event pairs — no saved report required:

```python
from mixpanel_data import RetentionEvent, Filter

# Simple retention: do signups come back?
result = ws.query_retention("Signup", "Login", retention_unit="week", last=90)
print(result.df.head())
#   cohort_date  bucket  count      rate
# 0  2025-01-01       0   1000  1.000000
# 1  2025-01-01       1    800  0.800000

# With per-event filters and custom buckets
result = ws.query_retention(
    RetentionEvent("Signup", filters=[Filter.equals("source", "organic")]),
    "Login",
    retention_unit="day",
    bucket_sizes=[1, 3, 7, 14, 30],
)
```

See the [Retention Queries guide](../guide/query-retention.md) for full coverage.

### Flow Queries

Analyze user paths through your product — what do users do before and after key events:

```python
from mixpanel_data import FlowStep, Filter

# What happens after Purchase?
result = ws.query_flow("Purchase", forward=3, last=90)
print(result.top_transitions(5))

# With per-step filters and reverse analysis
result = ws.query_flow(
    FlowStep("Purchase", filters=[Filter.greater_than("amount", 50)]),
    forward=3,
    reverse=2,
)
print(result.nodes_df)
print(result.edges_df)
```

See the [Flow Queries guide](../guide/query-flows.md) for full coverage.

### User Profile Queries

Search, filter, and aggregate user profiles stored in Mixpanel:

```python
from mixpanel_data import Filter

# Query user profiles
result = ws.query_user(
    where=Filter.equals("plan", "premium"),
    properties=["$email", "$name", "ltv"],
    sort_by="ltv",
    sort_order="descending",
    limit=50,
)
print(f"{result.total} premium users")
print(result.df)

# Count matching profiles
count = ws.query_user(mode="aggregate", where=Filter.is_set("$email"))
print(f"Users with email: {count.value}")
```

See the [User Profile Queries guide](../guide/query-users.md) for full coverage.

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

## Step 6: Switch Accounts and Projects In-Session

`Workspace.use()` swaps any axis without rebuilding the underlying HTTP client (O(1) per swap), so cross-project iteration is cheap:

```python
import mixpanel_data as mp

ws = mp.Workspace()

# In-session switching (returns self for chaining)
ws.use(account="team")              # implicitly clears workspace
ws.use(project="3018488")
ws.use(workspace=3448414)
ws.use(target="ecom")               # apply all three at once

# Persist the new state
ws.use(project="3018488", persist=True)

# Iterate across projects
for project in ws.projects():
    ws.use(project=project.id)
    print(project.name, len(ws.events()))
```

See [Configuration → Saved Targets](configuration.md#saved-targets) for the full target workflow.

## Step 7: Manage Entities & Data Governance (Optional)

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

## Step 8: Stream Data

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
- [Funnel Queries](../guide/query-funnels.md) — Typed funnel conversion analysis
- [Retention Queries](../guide/query-retention.md) — Typed retention analysis with event pairs and custom buckets
- [Flow Queries](../guide/query-flows.md) — Typed flow path analysis with direction controls and visualization modes
- [User Profile Queries](../guide/query-users.md) — Typed user profile queries with filtering, sorting, and aggregation
- [Live Analytics](../guide/live-analytics.md) — Segmentation, funnels, retention
- [Entity Management](../guide/entity-management.md) — Manage dashboards, reports, cohorts, feature flags, and experiments
- [Data Governance](../guide/data-governance.md) — Manage Lexicon definitions, drop filters, custom properties, and lookup tables
- [Streaming Data](../guide/streaming.md) — Stream events and profiles for ETL pipelines
