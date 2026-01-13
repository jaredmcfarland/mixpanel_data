# mixpanel_data Documentation

This directory contains all design documentation, specifications, and reference materials for the `mixpanel_data` library.

**A complete programmable interface to Mixpanel analytics**—Python library and CLI for discovery, querying, and data extraction.

## Document Hierarchy

```
context/
├── CLAUDE.md                              # This file - directory guide
├── mixpanel_data-project-brief.md         # Vision, goals, design principles
├── mixpanel_data-design.md                # Architecture and technical design
├── mixpanel_data-api-specification.md     # Python library API specification
├── mp-cli-api-specification.md            # CLI command specification
├── mp-cli-project-spec.md                 # Full project specification
├── mixpanel-data-model-reference.md       # Mixpanel data model (events, profiles)
├── mixpanel-http-api-specification.md     # Mixpanel HTTP API (all 11 APIs)
├── mixpanel-query-expression-language.md  # Query expression syntax
└── jql.md                                 # JQL (deprecated, maintenance mode)
```

## Reading Order

**For understanding the project:**
1. **[mixpanel_data-project-brief.md](mixpanel_data-project-brief.md)** — Vision, goals, design principles
2. **[mixpanel_data-design.md](mixpanel_data-design.md)** — Architecture, layers, system design
3. **[mp-cli-project-spec.md](mp-cli-project-spec.md)** — Full specification with command hierarchy

**For implementation:**
1. **[mixpanel_data-api-specification.md](mixpanel_data-api-specification.md)** — Python library API design
2. **[mp-cli-api-specification.md](mp-cli-api-specification.md)** — CLI commands and options
3. **[mixpanel-data-model-reference.md](mixpanel-data-model-reference.md)** — Data model for Pydantic/DuckDB mapping

## Core Capabilities

- **Discovery**: Explore your project schema—events, properties, funnels, cohorts, bookmarks
- **Live Analytics**: Segmentation, funnels, retention, saved reports, flows—direct API queries
- **Data Extraction**: Fetch events and profiles for local analysis or streaming to external systems
- **Local SQL**: Store in DuckDB, query with SQL—fetch once, iterate many times
- **JQL Execution**: Run custom JavaScript Query Language scripts

## For Humans and Agents

The entire surface area is self-documenting:

- Every CLI command supports `--help` with complete argument descriptions
- Python API uses typed dataclasses—IDEs show available fields
- Exceptions include error codes and context for programmatic handling
- Discoverable schema: `list_events()`, `list_properties()`, `list_funnels()`, `list_cohorts()`, `list_bookmarks()`

Both human developers and AI coding agents can explore capabilities without external documentation.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  CLI Layer (Typer + Rich)                                   │
│  src/mixpanel_data/cli/ - Commands, formatters, validators  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Public API Layer                                           │
│  Workspace class - Unified facade for all operations        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Service Layer                                              │
│  DiscoveryService | FetcherService | LiveQueryService       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Infrastructure Layer                                       │
│  ConfigManager | MixpanelAPIClient | StorageEngine (DuckDB) │
└─────────────────────────────────────────────────────────────┘
```

**Two data paths:**
- **Live queries**: Call Mixpanel API directly (segmentation, funnels, retention, saved reports, flows, JQL)
- **Local analysis**: Fetch → Store in DuckDB → Query with SQL → Iterate

## Naming Convention

| Context | Name | Example |
|---------|------|---------|
| PyPI package | `mixpanel_data` | `pip install mixpanel_data` |
| Python import | `mixpanel_data` | `import mixpanel_data as mp` |
| CLI command | `mp` | `mp fetch events --from 2025-01-01` |

## Design Principles

1. **Library-First** — CLI wraps library; every capability is programmatic
2. **Agent-Native** — Non-interactive, structured output, composable
3. **Context Efficient** — Fetch once, query many times
4. **Two Data Paths** — Live queries (quick) vs local DB (deep analysis)
5. **Unix Philosophy** — One thing well, compose with other tools
6. **Explicit Over Implicit** — No global state, explicit table creation/deletion
7. **Secure by Default** — Credentials in config file, never in code

## Python Library API

**Entry point:** `from mixpanel_data import Workspace`

```python
import mixpanel_data as mp

ws = mp.Workspace()

# Discovery - explore your project schema
events = ws.list_events()
props = ws.list_properties("Purchase")
funnels = ws.list_funnels()
cohorts = ws.list_cohorts()
bookmarks = ws.list_bookmarks()

# Live analytics queries
seg = ws.segmentation("Purchase", from_date="2025-01-01", to_date="2025-01-31", on="country")
funnel = ws.funnel(funnel_id=funnels[0].id, from_date="2025-01-01", to_date="2025-01-31")
ret = ws.retention("Signup", "Purchase", from_date="2025-01-01", to_date="2025-01-31")
report = ws.saved_report(bookmark_id=bookmarks[0].id)

# Fetch data to local storage
ws.fetch_events("events_jan", from_date="2025-01-01", to_date="2025-01-31")
ws.fetch_profiles("users")

# Query local data with SQL
df = ws.sql("SELECT * FROM events_jan LIMIT 10")
count = ws.sql_scalar("SELECT COUNT(*) FROM users")

# Stream without storage
for event in ws.stream_events(from_date="2025-01-01", to_date="2025-01-07"):
    process(event)

# Introspection
tables = ws.tables()
schema = ws.schema("events_jan")

# Cleanup
ws.drop("events_jan")
ws.close()
```

## CLI Commands (Implemented)

### Authentication (6 commands)
```bash
mp auth list                              # List configured accounts
mp auth add <name>                        # Add new account
mp auth remove <name>                     # Remove account
mp auth switch <name>                     # Set default account
mp auth show [name]                       # Show account details
mp auth test [name]                       # Test credentials
```

### Data Fetching (2 commands)
```bash
mp fetch events <name> --from DATE --to DATE [--events E1,E2] [--where EXPR] [--stdout]
mp fetch profiles <name> [--where EXPR] [--stdout]
```

Use `--stdout` to stream as JSONL instead of storing locally.

### Queries
```bash
# Local SQL
mp query sql "SELECT * FROM events LIMIT 10"

# Live analytics
mp query segmentation <event> --from DATE --to DATE [--on PROP] [--unit day|week|month]
mp query funnel <id> --from DATE --to DATE [--unit day|week|month]
mp query retention --born EVENT --return EVENT --from DATE --to DATE
mp query saved-report <bookmark_id>
mp query flows <event> --from DATE --to DATE [--direction before|after|both]
mp query jql <script> [--params JSON]

# Additional query commands
mp query event-counts --events E1,E2 --from DATE --to DATE
mp query property-counts <event> <property> --from DATE --to DATE
mp query frequency --from DATE --to DATE [--event E]
mp query segmentation-numeric <event> --from DATE --to DATE --on PROP
mp query segmentation-sum <event> --from DATE --to DATE --on PROP
mp query segmentation-average <event> --from DATE --to DATE --on PROP
```

### Inspection
```bash
# Discovery - explore project schema
mp inspect events                         # List event types
mp inspect properties --event <event>     # List properties for event
mp inspect values <property> [--event E]  # List property values
mp inspect funnels                        # List saved funnels
mp inspect cohorts                        # List saved cohorts
mp inspect bookmarks                      # List saved reports/insights

# Local database introspection
mp inspect tables                         # List local tables
mp inspect schema <table>                 # Table schema details
mp inspect drop <table> [--all]           # Drop table(s)
```

### Output Formats
All commands support `--format` option:
- `json` — Pretty-printed JSON (default for most)
- `jsonl` — JSON Lines (streaming)
- `table` — Rich table (human-readable)
- `csv` — CSV with headers
- `plain` — Minimal output

## Data Model

- **Events** — Timestamped actions (`event`, `distinct_id`, `time`, `properties`)
- **User Profiles** — Mutable user state (`$set`, `$append`, `$unset`)
- **Group Profiles** — Organization/account attributes
- **Lookup Tables** — Arbitrary entity enrichment

See [mixpanel-data-model-reference.md](mixpanel-data-model-reference.md) for complete reference.

## Reference Documentation

### Mixpanel HTTP API
**[mixpanel-http-api-specification.md](mixpanel-http-api-specification.md)** — Complete API specification for all 11 Mixpanel APIs:
- Event Export API, Query API, Ingestion API, Identity API
- Lexicon Schemas API, GDPR API, Annotations API
- Feature Flags API, Service Accounts API
- Data Pipelines API (deprecated), Warehouse Connectors API
- Authentication methods (Service Account, Project Token, OAuth)
- Regional endpoints (US, EU, India)
- Rate limits and error codes

### Query Languages
- **[mixpanel-query-expression-language.md](mixpanel-query-expression-language.md)** — Filter expressions, operators, functions
- **[jql.md](jql.md)** — JavaScript Query Language (deprecated, maintenance mode)

## Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.10+ | DuckDB/Pandas ecosystem, modern typing |
| CLI | Typer | Type hints, auto-generated help |
| Output | Rich | Tables, progress bars, colors |
| Validation | Pydantic v2 | API response validation, frozen models |
| Database | DuckDB | Embedded, analytical, JSON support |
| HTTP | httpx | Async support, connection pooling |
| Package Manager | uv | Fast, reliable dependency management |
| Task Runner | just | Simple command runner |

## Development Workflow

### Prerequisites
- Python 3.10+ (3.12 recommended)
- [uv](https://docs.astral.sh/uv/) — Package manager
- [just](https://github.com/casey/just) — Command runner

### Commands
```bash
just              # List all commands
just check        # Run all checks (lint, typecheck, test)
just test         # Run tests
just test-cov     # Run tests with coverage
just lint         # Lint with ruff
just lint-fix     # Auto-fix lint errors
just fmt          # Format with ruff
just typecheck    # Type check with mypy
just sync         # Sync dependencies
just mp --help    # Run the CLI
```

### Adding New Documentation
- Follow naming: `mixpanel_data-*.md` or `mp-cli-*.md`
- Update this CLAUDE.md with the new file
- Cross-reference from related documents

### Updating Specifications
- Keep version numbers in sync across related docs
- Update "Last Updated" dates
- Ensure CLI spec matches library API spec
