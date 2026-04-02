# mixpanel_data

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/github/license/jaredmcfarland/mixpanel_data)](LICENSE)

> **⚠️ Pre-release Software**: This package is under active development and not yet published to PyPI. APIs may change between versions.

A complete programmable interface to Mixpanel analytics—Python library and CLI for discovery, querying, and data extraction.

## Why mixpanel_data?

Mixpanel's web UI is powerful for interactive exploration, but programmatic access requires navigating multiple REST endpoints with different conventions. **mixpanel_data** provides a unified interface: discover your schema, run analytics queries, and extract data—all through consistent Python methods or CLI commands.

Core analytics—segmentation, funnels, retention, saved reports—plus entity management (dashboards, reports, cohorts, feature flags, experiments), raw JQL execution, and local SQL analysis via [DuckDB](https://duckdb.org).

## Installation

Install directly from GitHub (package not yet published to PyPI):

```bash
pip install git+https://github.com/jaredmcfarland/mixpanel_data.git
```

Requires Python 3.10+. Verify installation:

```bash
mp --version
```

## Quick Start

### 1. Authenticate

**Option A: OAuth Login (interactive, recommended)**

```bash
mp auth login --region us --project-id 12345  # Opens browser
mp auth status  # Verify connection
```

**Option B: Service Account (scripts, CI/CD)**

```bash
# Interactive prompt (secure)
mp auth add production --username sa_xxx --project 12345 --region us
# You'll be prompted for the service account secret with hidden input

mp auth test  # Verify connection
```

Alternative methods for CI/CD:

```bash
# Via inline environment variable (secret is only exposed to this command)
MP_SECRET=xxx mp auth add production --username sa_xxx --project 12345

# Via stdin (useful when secret is already in a variable)
echo "$SECRET" | mp auth add production --username sa_xxx --project 12345 --secret-stdin
```

Or set all credentials as environment variables: `MP_USERNAME`, `MP_SECRET`, `MP_PROJECT_ID`, `MP_REGION`

### 2. Explore Your Data

```bash
mp inspect events                      # List all events
mp inspect properties --event Purchase # Properties for an event
mp inspect funnels                     # Saved funnels
```

### 3. Fetch Events to Local Storage

```bash
# Sequential fetch for small date ranges
mp fetch events jan --from 2025-01-01 --to 2025-01-31

# Parallel fetch for large date ranges (up to 10x faster)
mp fetch events q1 --from 2025-01-01 --to 2025-03-31 --parallel
```

### 4. Query with SQL

```bash
mp query sql "SELECT event_name, COUNT(*) FROM jan GROUP BY 1 ORDER BY 2 DESC" --format table
```

### 5. Run Live Analytics

```bash
mp query segmentation --event Purchase --from 2025-01-01 --to 2025-01-31 --on country
```

### 6. Or Stream Directly (No Storage)

```bash
# Stream events as JSONL for piping to other tools
mp fetch events --from 2025-01-01 --to 2025-01-31 --stdout | jq '.event_name'
```

## Python API

```python
import mixpanel_data as mp

ws = mp.Workspace()

# Discover what's in your project
events = ws.list_events()
props = ws.list_properties("Purchase")
funnels = ws.list_funnels()
cohorts = ws.list_cohorts()

# Run live analytics queries
result = ws.segmentation(
    event=events[0].name,
    from_date="2025-01-01",
    to_date="2025-01-31",
    on="country"
)
print(result.df)  # pandas DataFrame

# Query a saved funnel
funnel = ws.funnel(
    funnel_id=funnels[0].id,
    from_date="2025-01-01",
    to_date="2025-01-31"
)

# Manage entities
dashboards = ws.list_dashboards()
cohort = ws.create_cohort(mp.CreateCohortParams(name="Power Users"))

# Feature flags and experiments
flags = ws.list_feature_flags()
flag = ws.create_feature_flag(mp.CreateFeatureFlagParams(name="Dark Mode", key="dark_mode"))
experiments = ws.list_experiments()
exp = ws.create_experiment(mp.CreateExperimentParams(name="Checkout Flow Test"))

# Operational tooling
alerts = ws.list_alerts()
annotations = ws.list_annotations(from_date="2025-01-01")
webhooks = ws.list_webhooks()

# Data governance
event_defs = ws.get_event_definitions(names=["Signup"])
drop_filters = ws.list_drop_filters()
custom_props = ws.list_custom_properties()
lookup_tables = ws.list_lookup_tables()

# Fetch events into local DuckDB for SQL analysis
ws.fetch_events("jan", from_date="2025-01-01", to_date="2025-01-31")

# Use parallel=True for large date ranges (up to 10x faster)
ws.fetch_events("q1", from_date="2025-01-01", to_date="2025-03-31", parallel=True)

# Fetch profiles (use parallel=True for large datasets, up to 5x faster)
ws.fetch_profiles("users", parallel=True)

df = ws.sql("""
    SELECT
        DATE_TRUNC('day', event_time) as day,
        event_name,
        COUNT(*) as count
    FROM jan
    GROUP BY 1, 2
    ORDER BY 1, 3 DESC
""")
```

### Temporary Workspaces

For one-off analysis without persisting data:

```python
# Ephemeral: temp file with compression (best for large datasets)
with mp.Workspace.ephemeral() as ws:
    ws.fetch_events("events", from_date="2025-01-01", to_date="2025-01-31")
    total = ws.sql_scalar("SELECT COUNT(*) FROM events")
# Database automatically deleted

# In-memory: zero disk footprint (best for small datasets, testing)
with mp.Workspace.memory() as ws:
    ws.fetch_events("events", from_date="2025-01-01", to_date="2025-01-07")
    total = ws.sql_scalar("SELECT COUNT(*) FROM events")
# No files ever created
```

### Streaming

For ETL pipelines or one-time processing without storage:

```python
# Stream events directly to external system
for event in ws.stream_events(from_date="2025-01-01", to_date="2025-01-31"):
    send_to_warehouse(event)
```

## CLI Reference

**`mp auth`** — Authentication: `login`, `logout`, `status`, `token` (OAuth); `list`, `add`, `remove`, `switch`, `show`, `test` (service accounts)

**`mp fetch`** — Extract data: `events`, `profiles` (add `--parallel` for up to 10x faster event exports or 5x faster profile exports, `--stdout` to stream as JSONL)

**`mp query`** — Run analytics: `sql`, `segmentation`, `funnel`, `retention`, `jql`, `saved-report`, `flows`, and 7 more

**`mp dashboards`** — Dashboard management: `list`, `create`, `get`, `update`, `delete`, `favorite`, `pin`, blueprints, and more

**`mp reports`** — Report management: `list`, `create`, `get`, `update`, `delete`, bulk operations, history

**`mp cohorts`** — Cohort management: `list`, `create`, `get`, `update`, `delete`, bulk operations

**`mp flags`** — Feature flag management: `list`, `create`, `get`, `update`, `delete`, `archive`, `restore`, `duplicate`, `set-test-users`, `history`, `limits`

**`mp experiments`** — Experiment management: `list`, `create`, `get`, `update`, `delete`, `launch`, `conclude`, `decide`, `archive`, `restore`, `duplicate`, `erf`

**`mp alerts`** — Alert management: `list`, `create`, `get`, `update`, `delete`, `bulk-delete`, `count`, `history`, `test`, `screenshot`, `validate`

**`mp annotations`** — Annotation management: `list`, `create`, `get`, `update`, `delete`, plus `tags list` and `tags create`

**`mp webhooks`** — Webhook management: `list`, `create`, `update`, `delete`, `test`

**`mp lexicon`** — Lexicon management: `events get/update/delete/bulk-update`, `properties get/update/bulk-update`, `tags list/create/update/delete`, `tracking-metadata`, `event-history`, `property-history`, `export`

**`mp drop-filters`** — Drop filter management: `list`, `create`, `update`, `delete`, `limits`

**`mp custom-properties`** — Custom property management: `list`, `get`, `create`, `update`, `delete`, `validate`

**`mp custom-events`** — Custom event management: `list`, `update`, `delete`

**`mp lookup-tables`** — Lookup table management: `list`, `upload`, `update`, `delete`, `download`, `upload-url`, `download-url`

**`mp inspect`** — Discover schema: `events`, `properties`, `funnels`, `cohorts`, `bookmarks`; local DB: `tables`, `schema`, `drop`, and 5 more

All commands support `--format` (`json`, `jsonl`, `table`, `csv`, `plain`) and `--help`.

### Filtering with --jq

Commands that output JSON support `--jq` for client-side filtering:

```bash
# Get first 5 events
mp inspect events --format json --jq '.[:5]'

# Extract total from segmentation
mp query segmentation --event Purchase --from 2025-01-01 --to 2025-01-31 \
    --format json --jq '.total'

# Filter SQL results
mp query sql "SELECT * FROM events LIMIT 100" --format json \
    --jq '.[] | select(.event_name == "Purchase")'
```

See [CLI Reference](https://jaredmcfarland.github.io/mixpanel_data/cli/) for complete documentation.

## DuckDB JSON Queries

Mixpanel properties are stored as JSON columns:

```sql
-- Extract property
SELECT properties->>'$.country' as country FROM events

-- Filter on property
SELECT * FROM events WHERE properties->>'$.plan' = 'premium'

-- Cast numeric
SELECT SUM(CAST(properties->>'$.amount' AS DECIMAL)) FROM events
```

## Documentation

Full documentation: [jaredmcfarland.github.io/mixpanel_data](https://jaredmcfarland.github.io/mixpanel_data/)

- [Installation](https://jaredmcfarland.github.io/mixpanel_data/getting-started/installation/)
- [Quick Start](https://jaredmcfarland.github.io/mixpanel_data/getting-started/quickstart/)
- [CLI Reference](https://jaredmcfarland.github.io/mixpanel_data/cli/)
- [Python API](https://jaredmcfarland.github.io/mixpanel_data/api/)
- [Streaming Guide](https://jaredmcfarland.github.io/mixpanel_data/guide/streaming/)
- [SQL Query Guide](https://jaredmcfarland.github.io/mixpanel_data/guide/sql-queries/)
- [Live Analytics](https://jaredmcfarland.github.io/mixpanel_data/guide/live-analytics/)

- [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/jaredmcfarland/mixpanel_data)

## For Humans and Agents

The entire surface area is self-documenting. Every CLI command supports `--help` with complete argument descriptions. The Python API uses typed dataclasses for all return values—IDEs show you what fields are available. Exceptions include error codes and context for programmatic handling. This means both human developers and AI coding agents can explore capabilities without external documentation.

Key design features:

- **Entity CRUD & Data Governance**: Full lifecycle management of dashboards, reports, cohorts, feature flags, experiments, alerts, annotations, webhooks, plus Lexicon definitions, drop filters, custom properties, custom events, and lookup tables via Mixpanel App API
- **Discoverable schema**: `list_events()`, `list_properties()`, `list_funnels()`, `list_cohorts()`, `list_bookmarks()` reveal what's in your project before you query
- **Consistent interfaces**: Same operations available as Python methods and CLI commands
- **Structured output**: All CLI commands support `--format json` for machine-readable responses, plus `--jq` for inline filtering
- **Parallel fetching**: Up to 10x faster event exports for large date ranges, 5x faster profile exports via `--parallel` or `parallel=True`
- **Local SQL iteration**: Fetch once, query repeatedly—no re-fetching needed
- **Dual authentication**: Service accounts (Basic Auth) for automation, OAuth 2.0 PKCE for interactive use
- **Typed exceptions**: Error codes and context for programmatic handling

## Claude Code Plugin

This project also includes a Claude Code plugin that brings analytics workflows directly into conversational AI interactions.

Ask questions about your Mixpanel data in natural language and get guided, interactive analytics workflows—all within Claude Code.

**Installation:**

```bash
/plugin marketplace add jaredmcfarland/mixpanel_data
/plugin install mixpanel-data
```

Then restart Claude Code.

**What you get:**

- **Auto-discovery skill**: `mixpanel-data` skill activates when you mention Mixpanel, analytics, funnels, or retention—loads comprehensive reference docs and guides your workflow
- **7 interactive commands**:
  - `/mp-auth` - Secure credential management with account switching
  - `/mp-inspect` - 12-operation schema explorer (events, properties, funnels, cohorts, tables)
  - `/mp-fetch` - Guided data ingestion with validation
  - `/mp-query` - Universal query builder (SQL, JQL, live analytics)
  - `/mp-funnel` - Conversion analysis with visualizations
  - `/mp-retention` - Retention curves and cohort analysis
  - `/mp-report` - Comprehensive reporting with automated insights
- **4 specialist agents**: Auto-invoked based on your questions
  - `mixpanel-analyst` - General analytics, SQL/JQL query building
  - `funnel-optimizer` - Conversion analysis and drop-off diagnostics
  - `retention-specialist` - Cohort behavior and retention curves
  - `jql-expert` - Advanced JavaScript queries and transformations
- **Multiple query paths**: SQL (DuckDB local analysis), JQL (complex transforms), or Mixpanel API (live analytics)
- **Secure by design**: Credentials managed outside conversation context

Learn more: [Plugin Documentation](mixpanel-plugin/README.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

MIT
