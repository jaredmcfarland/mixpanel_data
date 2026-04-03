# mp_mcp

MCP (Model Context Protocol) server exposing mixpanel_data analytics capabilities to AI assistants like Claude Desktop. Built on **FastMCP 3.x** with intelligent tools, middleware, skills integration, and AI-powered analytics.

## What's New in v2

The MCP Server v2 transforms `mp_mcp` from a thin API wrapper into an **intelligent analytics platform**:

| Feature                   | Description                                                      |
| ------------------------- | ---------------------------------------------------------------- |
| **Intelligent Tools**     | AI-powered analysis using `ctx.sample()` for synthesis           |
| **Composed Tools**        | Multi-query orchestration (AARRR dashboards, GQM investigations) |
| **Interactive Workflows** | User confirmation via `ctx.elicit()` for large operations        |
| **Progress Reporting**    | Real-time updates for long-running fetches                       |
| **Middleware Layer**      | Caching, rate limiting, and audit logging                        |
| **Graceful Degradation**  | All tools work when sampling/elicitation unavailable             |
| **Skills Provider**       | FastMCP v3 skills integration for dynamic tool loading           |

## Features

- **Account Management**: List, switch, and test Mixpanel account credentials
- **Schema Discovery**: Explore events, properties, funnels, cohorts, Lexicon schemas, and bookmarks
- **Live Analytics**: Run segmentation, funnel, retention, JQL, and numeric aggregation queries
- **Saved Reports**: Execute saved Insights, Retention, Funnel, and Flows reports
- **Streaming**: Stream events and profiles directly from Mixpanel
- **Intelligent Tools**: AI-powered metric diagnosis and natural language queries
- **Composed Tools**: AARRR dashboards, GQM investigations, cohort comparisons
- **Interactive Workflows**: Guided analysis with user confirmation for large operations
- **Middleware**: Caching, rate limiting, and audit logging

## Installation

```bash
# From the repository root
pip install ./mp_mcp
```

## Quick Start

### 1. Configure Credentials

Set environment variables or create `~/.mp/config.toml`:

```bash
export MP_USERNAME="your-service-account-username"
export MP_SECRET="your-service-account-secret"
export MP_PROJECT_ID="123456"
export MP_REGION="us"  # or "eu", "in"
```

### 2. Configure Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mixpanel": {
      "command": "mp_mcp",
      "args": []
    }
  }
}
```

### 3. Restart Claude Desktop

The Mixpanel tools are now available!

## Usage

### CLI Options

```bash
mp_mcp --help

# Run with default settings (stdio transport)
mp_mcp

# Use a specific account
mp_mcp --account production

# Run with HTTP transport
mp_mcp --transport http --port 8000
```

### Example Conversations

**Schema Discovery:**

- "What events are tracked in my Mixpanel project?"
- "Show me the properties for the signup event"
- "List my saved funnels"

**Live Analytics:**

- "How many logins happened each day last week?"
- "What's the conversion rate for my signup funnel?"
- "Show day-7 retention for users who signed up last month"

**Intelligent Analysis (v2):**

- "Why did signups drop on January 7th?"
- "What features do our best users engage with?"
- "Generate a funnel optimization report"
- "Show me a product health dashboard"

**Interactive Workflows (v2):**

- "Help me analyze my data" (guided analysis)

## Available Tools

### Tool Tiers

| Tier            | Description                                | MCP Feature    |
| --------------- | ------------------------------------------ | -------------- |
| **Tier 1**      | Primitive tools (direct API calls)         | Standard tools |
| **Tier 2**      | Composed tools (multi-query orchestration) | Standard tools |
| **Tier 3**      | Intelligent tools (AI synthesis)           | `ctx.sample()` |
| **Interactive** | Elicitation workflows                      | `ctx.elicit()` |

### Auth (4 tools)

- `list_accounts` - List all configured Mixpanel accounts
- `show_account` - Show details for a specific account (secret redacted)
- `switch_account` - Set a Mixpanel account as default
- `test_credentials` - Test account credentials by pinging the API

### Discovery (11 tools)

- `list_events` - List all tracked events
- `list_properties` - Get properties for an event
- `list_property_values` - Get sample values for a property
- `list_funnels` - List saved funnels
- `list_cohorts` - List saved cohorts
- `list_bookmarks` - List saved reports
- `top_events` - Get most active events
- `workspace_info` - Get workspace configuration
- `lexicon_schemas` - List Lexicon schemas (data dictionary)
- `lexicon_schema` - Get a single Lexicon schema by entity type and name
- `clear_discovery_cache` - Clear cached discovery results

### Live Query (18 tools)

- `segmentation` - Time series event analysis
- `funnel` - Conversion funnel analysis
- `retention` - User retention analysis
- `jql` - Execute JQL scripts
- `event_counts` - Count multiple events
- `property_counts` - Property value breakdown
- `activity_feed` - User event history
- `frequency` - Event frequency distribution
- `query_saved_report` - Execute a saved Insights, Retention, or Funnel report
- `query_flows` - Execute a saved Flows report
- `segmentation_numeric` - Bucket events by numeric property ranges
- `segmentation_sum` - Calculate sum of numeric property over time
- `segmentation_average` - Calculate average of numeric property over time
- `property_distribution` - Get distribution of values for a property (JQL)
- `numeric_summary` - Get statistical summary for a numeric property (JQL)
- `daily_counts` - Get daily event counts (JQL)
- `engagement_distribution` - Get user engagement distribution (JQL)
- `property_coverage` - Get property coverage statistics (JQL)

### Streaming (2 tools)

- `stream_events` - Stream events directly from Mixpanel
- `stream_profiles` - Stream profiles directly from Mixpanel

### Intelligent Tools (3 tools) — Tier 3, Sampling-Powered

These tools use `ctx.sample()` for LLM-powered analysis and gracefully degrade when sampling is unavailable.

| Tool                         | Description                               |
| ---------------------------- | ----------------------------------------- |
| `diagnose_metric_drop`       | Analyze metric declines with AI synthesis |
| `ask_mixpanel`               | Natural language analytics queries        |
| `funnel_optimization_report` | Funnel analysis with recommendations      |

**Graceful Degradation**: When sampling is unavailable, these tools return raw query results with manual analysis hints instead of AI-synthesized findings.

### Composed Tools (3 tools) — Tier 2

These tools orchestrate multiple primitive queries into comprehensive analyses.

| Tool                       | Description                                                                          |
| -------------------------- | ------------------------------------------------------------------------------------ |
| `product_health_dashboard` | AARRR metrics (Acquisition, Activation, Retention, Revenue, Referral) in one request |
| `gqm_investigation`        | Goal-Question-Metric framework for structured investigation                          |
| `cohort_comparison`        | Compare user cohorts across behavioral dimensions                                    |

### Interactive Tools (1 tool) — Elicitation-Powered

These tools use `ctx.elicit()` for user confirmation and multi-step workflows.

| Tool               | Description                                       |
| ------------------ | ------------------------------------------------- |
| `guided_analysis`  | Interactive step-by-step analysis workflow         |

## Middleware

The server includes a middleware layer for cross-cutting concerns:

| Component         | Description                                    | Configuration                                    |
| ----------------- | ---------------------------------------------- | ------------------------------------------------ |
| **Caching**       | TTL-based response caching for discovery tools | 5-minute TTL                                     |
| **Rate Limiting** | Respects Mixpanel API limits                   | Query: 60/hr, 5 concurrent; Export: 60/hr, 3/sec |
| **Audit Logging** | Tool invocation logging with timing            | All tool calls logged                            |

### Rate Limit Details

| API        | Rate Limit                 | Concurrent Limit |
| ---------- | -------------------------- | ---------------- |
| Query API  | 60 requests/hour           | 5 concurrent     |
| Export API | 60 requests/hour, 3/second | 100 concurrent   |

When rate limited, the system automatically queues requests and reports wait time.

## Resources

Static and dynamic data accessible via MCP resources:

### Static Resources

- `workspace://info` - Workspace configuration
- `schema://events` - Event list
- `schema://funnels` - Funnel definitions
- `schema://cohorts` - Cohort definitions
- `schema://bookmarks` - Saved reports

### Dynamic Resource Templates (v2)

- `analysis://retention/{event}/weekly` - 12-week retention curve
- `analysis://trends/{event}/{days}` - Daily event counts
- `users://{id}/journey` - User event journey

## Prompts

Guided workflow templates for structured analysis:

| Prompt                    | Description                                                            |
| ------------------------- | ---------------------------------------------------------------------- |
| `analytics_workflow`      | Complete analytics exploration guide                                   |
| `funnel_analysis`         | Funnel conversion analysis workflow                                    |
| `retention_analysis`      | User retention analysis workflow                                       |
| `analysis_workflow`       | Data analysis guide                                                    |
| `gqm_framework`           | Goal-Question-Metric investigation framework                           |
| `aarrr_analysis`          | Pirate metrics (Acquisition, Activation, Retention, Revenue, Referral) |
| `experiment_analysis`     | A/B test and experiment analysis guide                                 |

## MCP Capabilities

This server leverages advanced MCP features:

| Feature             | Usage                                                  | Graceful Degradation        |
| ------------------- | ------------------------------------------------------ | --------------------------- |
| **Sampling**        | `ctx.sample()` for LLM analysis of query results       | Returns raw data with hints |
| **Elicitation**     | `ctx.elicit()` for interactive workflows               | Proceeds with warning       |
| **Tasks**           | Progress reporting via `ctx.report_progress()`         | Synchronous execution       |
| **Middleware**      | Request interception for caching, rate limiting, audit | N/A                         |
| **Skills Provider** | FastMCP v3 SkillsDirectoryProvider for dynamic skills  | Server runs without skills  |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    MCP Client                           │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                   Middleware Layer                      │
│  ┌─────────┐  ┌──────────────┐  ┌─────────────────┐     │
│  │ Logging │→ │ Rate Limiting│→ │     Caching     │     │
│  └─────────┘  └──────────────┘  └─────────────────┘     │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                     Tool Tiers                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Tier 3: Intelligent (sampling-powered)           │  │
│  │  diagnose_metric_drop, ask_mixpanel, funnel_report│  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Tier 2: Composed (multi-query orchestration)     │  │
│  │  product_health_dashboard, gqm_investigation, ... │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Tier 1: Primitive (direct API calls)             │  │
│  │  segmentation, funnel, retention, streaming, ... │  │
│  └───────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│              mixpanel_data.Workspace                    │
│  ┌─────────────┐  ┌────────────────┐  ┌─────────────┐   │
│  │  Discovery  │  │  Live Queries  │  │  Streaming  │   │
│  └─────────────┘  └────────────────┘  └─────────────┘   │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                   Mixpanel API                          │
└─────────────────────────────────────────────────────────┘
```

## Development

```bash
# Install with dev dependencies
pip install -e "./mp_mcp[dev]"

# Run tests
pytest mp_mcp/tests/

# Run with coverage
pytest mp_mcp/tests/ --cov=mp_mcp

# Type check
mypy mp_mcp/src/
```

### Project Structure

```
mp_mcp/src/mp_mcp/
├── server.py              # FastMCP 3.x server setup with lifespan
├── cli.py                 # CLI entry point (mp_mcp command)
├── context.py             # Workspace context management
├── errors.py              # Error handling decorators
├── types.py               # Result type definitions
├── resources.py           # MCP resources
├── prompts.py             # Framework prompts
├── tools/
│   ├── auth.py            # Account management tools
│   ├── discovery.py       # Schema discovery tools
│   ├── live_query.py      # Live query tools
│   ├── intelligent/       # Tier 3 sampling-powered tools
│   │   ├── diagnose.py
│   │   ├── ask.py
│   │   └── funnel_report.py
│   ├── composed/          # Tier 2 multi-query tools
│   │   ├── dashboard.py
│   │   ├── gqm.py
│   │   └── cohort.py
│   └── interactive/       # Elicitation workflows
│       └── guided.py
└── middleware/
    ├── caching.py         # Response caching
    ├── rate_limiting.py   # API rate limiting
    └── audit.py           # Tool invocation logging
```

## Technology Stack

- Python 3.10+ with FastMCP 3.x (including tasks support)
- FastMCP Skills Provider for dynamic skill loading
- mixpanel_data Workspace for analytics
- In-memory caches for middleware (no external dependencies)

## License

MIT
