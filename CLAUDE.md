# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`mixpanel_data` is a Python library and CLI for working with Mixpanel analytics data, designed for AI coding agents. The core insight: agents should fetch data once into a local DuckDB database, then query it repeatedly with SQL—preserving context window for reasoning rather than consuming it with raw API responses.

**Status:** Design phase. Comprehensive specifications exist in `docs/`; no source code has been written yet.

## Naming Convention

| Context | Name | Example |
|---------|------|---------|
| PyPI package | `mixpanel_data` | `pip install mixpanel_data` |
| Python import | `mixpanel_data` | `import mixpanel_data as mp` |
| CLI command | `mp` | `mp fetch events --from 2024-01-01` |

## Architecture

Layered architecture with `Workspace` class as facade:

```
CLI Layer (Typer)           → Argument parsing, output formatting
    ↓
Public API Layer            → Workspace class, auth module
    ↓
Service Layer               → DiscoveryService, FetcherService, LiveQueryService
    ↓
Infrastructure Layer        → ConfigManager, MixpanelAPIClient, StorageEngine (DuckDB)
```

**Two data paths:**
- **Live queries**: Call Mixpanel API directly (segmentation, funnels, retention)
- **Local analysis**: Fetch → Store in DuckDB → Query with SQL → Iterate

## Technology Stack

- Python 3.11+, Typer (CLI), Rich (output), Pydantic (validation)
- DuckDB (embedded analytical database), httpx (HTTP client)
- pandas (DataFrame integration)

## Design Documents

Read in this order for implementation:

1. **[docs/mixpanel_data-project-brief.md](docs/mixpanel_data-project-brief.md)** — Vision and goals
2. **[docs/mixpanel_data-design.md](docs/mixpanel_data-design.md)** — Architecture, component specs, public API
3. **[docs/mp-cli-project-spec.md](docs/mp-cli-project-spec.md)** — Full CLI specification
4. **[docs/MIXPANEL_DATA_MODEL_REFERENCE.md](docs/MIXPANEL_DATA_MODEL_REFERENCE.md)** — Mixpanel data model for Pydantic/DuckDB mapping

## Intended Package Structure

```
src/mixpanel_data/
├── __init__.py              # Public API exports
├── workspace.py             # Workspace facade class
├── auth.py                  # Public auth module
├── exceptions.py            # All exception classes
├── types.py                 # Result types, dataclasses
├── _internal/               # Private implementation
│   ├── config.py            # ConfigManager
│   ├── api_client.py        # MixpanelAPIClient
│   ├── storage.py           # StorageEngine (DuckDB)
│   └── services/
│       ├── discovery.py     # DiscoveryService
│       ├── fetcher.py       # FetcherService
│       └── live_query.py    # LiveQueryService
└── cli/
    ├── main.py              # Typer app entry point
    └── commands/            # auth, fetch, query, inspect commands
```

## Key Design Decisions

- **Explicit table management**: Tables never implicitly overwritten; `TableExistsError` if exists
- **Streaming ingestion**: API returns iterators, storage accepts iterators (memory efficient)
- **JSON property storage**: Properties stored as JSON columns, queried with `properties->>'$.field'`
- **Immutable credentials**: Resolved once at Workspace construction
- **Dependency injection**: Services accept dependencies as constructor arguments for testing

## Mixpanel API Reference

Complete API documentation in `docs/api-docs/`:
- **Event Export API** — Raw event fetching for local storage
- **Query API** — Segmentation, funnels, retention, JQL
- **Lexicon Schemas API** — Event/property discovery

OpenAPI specs: `docs/api-docs/openapi/src/*.openapi.yaml`

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `MP_USERNAME` | Service account username |
| `MP_SECRET` | Service account secret |
| `MP_PROJECT_ID` | Project ID |
| `MP_REGION` | Data residency (us, eu, in) |
| `MP_CONFIG_PATH` | Override config file location |

Config file: `~/.mp/config.toml`

## Implementation Phases

1. **Foundation**: ConfigManager, MixpanelAPIClient, StorageEngine, exceptions
2. **Core**: FetcherService, DiscoveryService, Workspace, auth module
3. **Live Queries**: LiveQueryService, segmentation/funnel/retention
4. **CLI**: Typer app, all commands, formatters
5. **Polish**: SKILL.md, tests, PyPI release

## Active Technologies
- Python 3.11+ (per constitution) + Pydantic v2 (validation), tomli/tomllib (TOML parsing), pandas (DataFrame conversion) (001-foundation-layer)
- File-based TOML configuration at `~/.mp/config.toml` (001-foundation-layer)

## Recent Changes
- 001-foundation-layer: Added Python 3.11+ (per constitution) + Pydantic v2 (validation), tomli/tomllib (TOML parsing), pandas (DataFrame conversion)
