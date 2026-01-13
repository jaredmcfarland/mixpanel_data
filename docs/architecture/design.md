# Architecture

mixpanel_data follows a layered architecture with clear separation of concerns.

!!! tip "Explore on DeepWiki"
    🤖 **[Architecture Deep Dive →](https://deepwiki.com/jaredmcfarland/mixpanel_data/5-architecture)**

    Ask questions about the architecture, trace data flows, or explore component relationships interactively.

## Layer Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI Layer (Typer)                      │
│         Argument parsing, output formatting, progress       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Public API Layer                          │
│              Workspace class, auth module                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Service Layer                           │
│     DiscoveryService, FetcherService, LiveQueryService      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Infrastructure Layer                       │
│       ConfigManager, MixpanelAPIClient, StorageEngine       │
└─────────────────────────────────────────────────────────────┘
```

## Components

### Workspace (Facade)

The `Workspace` class is the unified entry point that coordinates all services:

- **Credential Resolution** — Env vars → named account → default account
- **Service Orchestration** — Creates and manages service instances
- **Resource Management** — Context manager support for cleanup

### Services

#### DiscoveryService

Schema introspection with session-scoped caching:

- `list_events()` — All event names (cached)
- `list_properties(event)` — Properties for an event (cached per event)
- `list_property_values(property, event)` — Sample values (cached)
- `list_funnels()` — Saved funnels (cached)
- `list_cohorts()` — Saved cohorts (cached)
- `list_top_events()` — Today's top events (NOT cached, real-time)

#### FetcherService

Coordinates data ingestion from Mixpanel API to DuckDB, or direct streaming:

- Streaming transformation (memory efficient)
- Progress callback integration
- Returns `FetchResult` with metadata (fetch mode)
- Returns `Iterator[dict]` without storage (stream mode)

#### LiveQueryService

Executes live analytics queries against Mixpanel Query API:

- Segmentation, funnels, retention, JQL
- Event counts, property counts
- Activity feed, saved reports, flows, frequency
- Numeric aggregations (bucket, sum, average)

### Infrastructure

#### ConfigManager

TOML-based account management at `~/.mp/config.toml`:

- Account CRUD operations
- Credential resolution
- Default account management

#### MixpanelAPIClient

HTTP client with Mixpanel-specific features:

- Service account authentication
- Regional endpoint routing (US, EU, India)
- Automatic rate limit handling with exponential backoff
- Streaming JSONL parsing for large exports

#### StorageEngine

DuckDB-based storage:

- Persistent, ephemeral, and in-memory modes
- Table creation with streaming batch ingestion
- Query execution (DataFrame, scalar, rows)
- Schema introspection and metadata

## Data Paths

### Live Query Path

```
User Request → Workspace → LiveQueryService → MixpanelAPIClient → Mixpanel API
                                                      ↓
                                              Typed Result (e.g., SegmentationResult)
```

Best for:

- Real-time data needs
- One-off analysis
- Pre-computed Mixpanel reports

### Local Analysis Path

```
User Request → Workspace → FetcherService → MixpanelAPIClient → Mixpanel Export API
                                 ↓
                          StorageEngine (DuckDB)
                                 ↓
User Query → Workspace → StorageEngine → SQL Execution → DataFrame
```

Best for:

- Repeated queries over same data
- Custom SQL logic
- Context window preservation (AI agents)
- Offline analysis

### Streaming Path

```
User Request → Workspace → MixpanelAPIClient → Mixpanel Export API
                                    ↓
                          Iterator[dict] (no storage)
                                    ↓
                          Process each record inline
```

Best for:

- ETL pipelines to external systems
- One-time processing without storage
- Memory-constrained environments
- Unix pipeline integration (CLI `--stdout`)

## Key Design Decisions

### Explicit Table Management

Tables are never implicitly overwritten. Fetching to an existing table name raises `TableExistsError`. This prevents accidental data loss and makes data lineage explicit.

### Streaming Ingestion

The API client returns iterators, and storage accepts iterators. This enables memory-efficient processing of large datasets without loading everything into memory.

### JSON Property Storage

Event and profile properties are stored as JSON columns in DuckDB. This preserves the flexible Mixpanel schema while enabling powerful JSON querying:

```sql
SELECT properties->>'$.country' as country FROM events
```

### Immutable Credentials

Credentials are resolved once at Workspace construction. This prevents confusion from mid-session credential changes.

### Dependency Injection

All services accept their dependencies as constructor arguments. This enables:

- Easy testing with mocks
- Flexible composition
- Clear dependency relationships

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Language | Python 3.10+ | Type hints, modern syntax |
| CLI Framework | Typer | Declarative CLI building |
| Output Formatting | Rich | Tables, progress bars, colors |
| Validation | Pydantic | Data validation, settings |
| Database | DuckDB | Embedded analytical database |
| HTTP Client | httpx | Async-capable HTTP |
| DataFrames | pandas | Data analysis interface |

## Package Structure

```
src/mixpanel_data/
├── __init__.py              # Public API exports
├── workspace.py             # Workspace facade
├── auth.py                  # Public auth module
├── exceptions.py            # Exception hierarchy
├── types.py                 # Result types
├── py.typed                 # PEP 561 marker
├── _internal/               # Private implementation
│   ├── config.py            # ConfigManager, Credentials
│   ├── api_client.py        # MixpanelAPIClient
│   ├── storage.py           # StorageEngine
│   └── services/
│       ├── discovery.py     # DiscoveryService
│       ├── fetcher.py       # FetcherService
│       └── live_query.py    # LiveQueryService
└── cli/
    ├── main.py              # Typer app entry point
    ├── commands/            # Command implementations
    ├── formatters.py        # Output formatters
    └── utils.py             # CLI utilities
```
