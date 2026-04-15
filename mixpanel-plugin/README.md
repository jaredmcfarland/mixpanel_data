# mixpanel-data — CodeMode Analyst Plugin

Turn Claude into a senior data analyst and Mixpanel product analytics expert. Instead of calling CLI commands or MCP tools, Claude writes Python code using `mixpanel_data`'s four typed query engines plus `pandas`, `networkx`, and `anytree` for sophisticated multi-engine analysis. Ask questions in natural language — Claude autonomously writes and executes Python to answer them.

## Quick Start

```
1. /mixpanel-data:setup              # Install deps, verify auth
2. "How many signups last week?"      # Insights query
3. "Where do users drop off?"         # Funnel analysis
4. "Do users retain after onboarding?"# Retention curve
5. "What do users do after signup?"   # Flow analysis
```

## Query Engines

| Engine | Method | Core Question | Result Type |
|--------|--------|---------------|-------------|
| Insights | `ws.query()` | How much? How many? | `QueryResult` |
| Funnels | `ws.query_funnel()` | Do users convert through a sequence? | `FunnelQueryResult` |
| Retention | `ws.query_retention()` | Do users come back? | `RetentionQueryResult` |
| Flows | `ws.query_flow()` | What paths do users take? | `FlowQueryResult` |
| Users | `ws.query_user()` | Who are they? What do they look like? | `UserQueryResult` |

### Recent Additions

- **TimeComparison**: Period-over-period analysis across Insights, Funnels, and Retention
- **FrequencyBreakdown / FrequencyFilter**: Frequency-based breakdowns and filters
- **7 new MathTypes**: `cumulative_unique`, `sessions`, `unique_values`, `most_frequent`, `first_value`, `multi_attribution`, `numeric_summary`
- **Flow enhancements**: `segments`, `exclusions`, property filters, `FlowStep.session_event`
- **Funnel reentry**: `reentry_mode` parameter with 4 modes
- **Retention modes**: `unbounded_mode`, `retention_cumulative`, expanded `RetentionMathType`

When you ask a question, Claude writes Python using the appropriate engine:

### Insights (trending metrics)

```python
import mixpanel_data as mp
ws = mp.Workspace()
result = ws.query("Signup", last=30, unit="day")
df = result.df
```

### Funnels (conversion analysis)

```python
result = ws.query_funnel(
    ["Signup", "Onboarding Complete", "First Purchase"],
    conversion_window=14,
)
print(result.overall_conversion_rate)
print(result.df)  # step, event, count, step_conv_ratio, avg_time
```

### Retention (user return behavior)

```python
result = ws.query_retention(
    "Signup", "Login",
    retention_unit="week", last=90,
)
print(result.average)  # synthetic average across cohorts
print(result.df)       # cohort_date, bucket, count, rate
```

### Flows (user path analysis)

```python
result = ws.query_flow("Signup", forward=4)
g = result.graph                   # networkx DiGraph
print(result.top_transitions(5))   # highest-traffic paths
print(result.drop_off_summary())   # per-step drop-off

# Tree mode
result = ws.query_flow("Signup", mode="tree")
for tree in result.trees:
    print(tree.render())           # ASCII visualization
```

For detailed API docs, use `help.py` or the [hosted documentation](https://jaredmcfarland.github.io/mixpanel_data/).

## Components

| Type | Name | Invocation |
|------|------|------------|
| Command | auth | `/mp-auth` — manage credentials, accounts, OAuth |
| Skill | setup | `/mixpanel-data:setup` — install deps, verify auth |
| Skill | mixpanelyst | Auto-triggered on analytics questions |
| Skill | dashboard-expert | Auto-triggered on dashboard analysis, creation, and modification |

| Script | Purpose |
|--------|---------|
| `help.py` | Live API documentation lookup from library docstrings |
| `auth_manager.py` | Programmatic auth status and credential management (JSON output) |

## Authentication

Two auth methods: service account (Basic Auth) or OAuth 2.0 PKCE. Run `/mixpanel-data:setup` for first-time configuration, or `/mp-auth` to manage credentials after initial setup.

## Installation

### From GitHub

```bash
/plugin marketplace add jaredmcfarland/mixpanel_data
/plugin install mixpanel-data@mixpanel-data-marketplace
```

### Local development

```bash
claude --plugin-dir /path/to/mixpanel_data/mixpanel-plugin
```

Use `/reload-plugins` to pick up changes without restarting.

## Prerequisites

- Python 3.10+
- Mixpanel service account credentials (or OAuth)
- Claude Code with plugins enabled

## Directory Structure

```
mixpanel-plugin/
├── .claude-plugin/
│   └── plugin.json                     # Plugin manifest
├── skills/
│   ├── setup/
│   │   ├── SKILL.md                    # /mixpanel-data:setup
│   │   └── scripts/
│   │       └── setup.sh               # Dependency installer
│   ├── dashboard-expert/
│   │   ├── SKILL.md                    # Dashboard analyze, build, modify, explain
│   │   └── references/
│   │       ├── dashboard-reference.md  # API, layout, text cards, gotchas
│   │       ├── dashboard-templates.md  # 9 design templates (KPI, AARRR, etc.)
│   │       ├── bookmark-pipeline.md    # Query → bookmark → dashboard
│   │       └── chart-types.md          # Chart type selection guide
│   └── mixpanelyst/
│       ├── SKILL.md                    # API reference (distilled workspace.py)
│       └── scripts/
│           ├── help.py                 # Live API documentation lookup
│           └── auth_manager.py         # Auth status and management
├── commands/
│   └── auth.md                         # /mp-auth command
└── README.md
```

## Links

- [Library documentation](https://jaredmcfarland.github.io/mixpanel_data/)
- [Source repository](https://github.com/jaredmcfarland/mixpanel_data)

## License

MIT
