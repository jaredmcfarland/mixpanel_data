# API Overview

The `mixpanel_data` Python API provides programmatic access to all library functionality.

!!! tip "Explore on DeepWiki"
    🤖 **[Python API Reference →](https://deepwiki.com/jaredmcfarland/mixpanel_data/7.2-python-api-reference)**

    Ask questions about API methods, explore usage patterns, or get help with specific functionality.

## Import Patterns

```python
# Recommended: import with alias
import mixpanel_data as mp

ws = mp.Workspace()
result = ws.segmentation(...)

# Direct imports
from mixpanel_data import Workspace, FetchResult, MixpanelDataError

# Auth utilities
from mixpanel_data.auth import ConfigManager, Credentials, AuthMethod

# OAuth and workspace exceptions
from mixpanel_data import OAuthError, WorkspaceScopeError

# App API types
from mixpanel_data import PublicWorkspace, CursorPagination, PaginatedResponse

# Entity CRUD types
from mixpanel_data import (
    Dashboard, CreateDashboardParams, UpdateDashboardParams,
    Bookmark, CreateBookmarkParams, UpdateBookmarkParams,
    Cohort, CreateCohortParams, UpdateCohortParams,
)

# Data governance types
from mixpanel_data import (
    EventDefinition, UpdateEventDefinitionParams,
    DropFilter, CreateDropFilterParams,
    CustomProperty, CreateCustomPropertyParams,
    LookupTable, UploadLookupTableParams,
)
```

## Core Components

### Workspace

The main entry point for all operations:

- **Discovery** — Explore events, properties, funnels, cohorts
- **Fetching** — Download events and profiles to local storage
- **Streaming** — Stream data directly without storage (ETL, pipelines)
- **Local Queries** — SQL queries against DuckDB
- **Live Queries** — Real-time analytics from Mixpanel API
- **Entity CRUD & Data Governance** — Create, read, update, delete dashboards, reports, cohorts, feature flags, experiments, plus Lexicon definitions, drop filters, custom properties, custom events, and lookup tables
- **Introspection** — Examine local tables and schemas

[View Workspace API](workspace.md)

### Auth Module

Credential and account management:

- **ConfigManager** — Manage accounts in config file
- **Credentials** — Credential container with secrets (Basic Auth and OAuth)
- **AuthMethod** — Authentication method enum (`basic`, `oauth`)
- **AccountInfo** — Account metadata (without secrets)
- **OAuthFlow** — OAuth 2.0 PKCE login flow orchestration
- **OAuthStorage** — Local token and client info persistence

[View Auth API](auth.md)

### Exceptions

Structured error handling:

- **MixpanelDataError** — Base exception
- **APIError** — HTTP/API errors
- **ConfigError** — Configuration errors
- **OAuthError** — OAuth authentication errors
- **WorkspaceScopeError** — Workspace resolution errors
- **TableExistsError** / **TableNotFoundError** — Storage errors

[View Exceptions](exceptions.md)

### Result Types

Typed results for all operations:

- **FetchResult** — Fetch operation results
- **SegmentationResult** — Time-series data
- **FunnelResult** — Funnel conversion data
- **RetentionResult** — Retention cohort data
- **Dashboard**, **Bookmark**, **Cohort** — Entity models for CRUD operations
- **EventDefinition**, **DropFilter**, **CustomProperty**, **LookupTable** — Data governance models
- And many more...

[View Result Types](types.md)

## Type Aliases

The library exports these type aliases:

```python
from mixpanel_data import CountType, HourDayUnit, TimeUnit

# CountType: Literal["general", "unique", "average", "median", "min", "max"]
# HourDayUnit: Literal["hour", "day"]
# TimeUnit: Literal["day", "week", "month", "quarter", "year"]
```

## Complete API Reference

- [Workspace](workspace.md) — Main facade class
- [Auth](auth.md) — Authentication and configuration
- [Exceptions](exceptions.md) — Error handling
- [Result Types](types.md) — All result dataclasses
