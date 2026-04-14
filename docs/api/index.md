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
result = ws.query("Login", math="unique", last=30)

# Direct imports
from mixpanel_data import Workspace, MixpanelDataError

# Insights Query types
from mixpanel_data import (
    Metric, Filter, Formula, GroupBy, QueryResult,
    MathType, PerUserAggregation, FilterPropertyType,
)

# Cohort Query types (cross-engine)
from mixpanel_data import (
    CohortBreakdown, CohortMetric,
    CohortDefinition, CohortCriteria,
)

# Retention Query types
from mixpanel_data import RetentionEvent, RetentionQueryResult

# Flow Query types
from mixpanel_data import FlowStep, FlowTreeNode, FlowQueryResult

# User Profile Query types
from mixpanel_data import UserQueryResult

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

# Schema governance types
from mixpanel_data import (
    SchemaEntry, BulkCreateSchemasParams,
    SchemaEnforcementConfig, AuditResponse,
    DataVolumeAnomaly, EventDeletionRequest,
)
```

## Core Components

### Workspace

The main entry point for all operations:

- **Discovery** — Explore events, properties, funnels, cohorts
- **Insights Queries** — Typed analytics queries using the Insights engine (`query()`)
- **Funnel Queries** — Typed funnel conversion analysis (`query_funnel()`)
- **Retention Queries** — Typed retention analysis with event pairs (`query_retention()`)
- **Flow Queries** — Typed flow path analysis (`query_flow()`)
- **User Profile Queries** — Typed user profile queries with filtering, sorting, and aggregation (`query_user()`)
- **Live Queries** — Legacy analytics endpoints (segmentation, funnels, retention, JQL)
- **Streaming** — Stream events and profiles directly from Mixpanel (ETL, pipelines)
- **Entity CRUD & Data Governance** — Create, read, update, delete dashboards, reports, cohorts, feature flags, experiments, plus Lexicon definitions, drop filters, custom properties, custom events, lookup tables, schema registry, schema enforcement, data auditing, volume anomalies, and event deletion requests

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

[View Exceptions](exceptions.md)

### Result Types

Typed results for all operations:

- **QueryResult** — Insights query results (from `query()`)
- **Metric**, **Filter**, **Formula**, **GroupBy** — Query building blocks
- **CohortBreakdown**, **CohortMetric** — Cohort-scoped query types (cross-engine)
- **CohortDefinition**, **CohortCriteria** — Inline cohort definition builder
- **FunnelQueryResult**, **FunnelStep**, **Exclusion** — Typed funnel results
- **RetentionQueryResult**, **RetentionEvent**, **RetentionAlignment**, **RetentionMode**, **RetentionMathType** — Typed retention results
- **FlowQueryResult**, **FlowStep**, **FlowTreeNode** — Typed flow analysis results
- **UserQueryResult** — Typed user profile query results
- **SegmentationResult** — Time-series data (legacy)
- **FunnelResult** — Funnel conversion data (legacy)
- **RetentionResult** — Retention cohort data (legacy)
- **Dashboard**, **Bookmark**, **Cohort** — Entity models for CRUD operations
- **EventDefinition**, **DropFilter**, **CustomProperty**, **LookupTable** — Data governance models
- **SchemaEntry**, **SchemaEnforcementConfig**, **AuditResponse**, **DataVolumeAnomaly**, **EventDeletionRequest** — Schema governance models
- And many more...

[View Result Types](types.md)

## Type Aliases

The library exports these type aliases:

```python
from mixpanel_data import CountType, HourDayUnit, TimeUnit, FilterDateUnit
from mixpanel_data import FlowCountType, FlowChartType

# CountType: Literal["general", "unique", "average", "median", "min", "max"]
# HourDayUnit: Literal["hour", "day"]
# TimeUnit: Literal["day", "week", "month", "quarter", "year"]
# FilterDateUnit: Literal["hour", "day", "week", "month"]
# FlowCountType: Literal["unique", "total", "session"]
# FlowChartType: Literal["sankey", "paths", "tree"]
```

## Complete API Reference

- [Workspace](workspace.md) — Main facade class
- [Auth](auth.md) — Authentication and configuration
- [Exceptions](exceptions.md) — Error handling
- [Result Types](types.md) — All result dataclasses
