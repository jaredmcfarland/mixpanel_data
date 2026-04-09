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

_Each engine has a comprehensive reference: [insights](skills/mixpanel-analyst/references/insights-reference.md) | [funnels](skills/mixpanel-analyst/references/funnels-reference.md) | [retention](skills/mixpanel-analyst/references/retention-reference.md) | [flows](skills/mixpanel-analyst/references/flows-reference.md). For routing questions to the right engine, see [query-taxonomy.md](skills/mixpanel-analyst/references/query-taxonomy.md)._

## Agents

The plugin uses a specialist agent hierarchy. The **analyst** is the general-purpose entry point — it handles simple queries directly and delegates complex investigations to the appropriate specialist based on question type.

| Agent | Role | When to use |
|-------|------|-------------|
| **analyst** | Orchestrator | General analytics, dashboards, entity management, multi-metric queries |
| **explorer** | Schema discovery + GQM | Vague or open-ended questions, data landscape mapping, "what data do we have?" |
| **diagnostician** | Root cause analysis | "Why did X drop/spike?", metric changes, 8-step cross-engine investigation |
| **synthesizer** | Cross-engine analysis | Multi-engine joins, graph algorithms (NetworkX), statistical testing (scipy) |
| **narrator** | Executive reporting | Stakeholder reports, executive summaries, audience-tailored narratives |

```
Task(subagent_type="mixpanel-data:analyst", prompt="...")
Task(subagent_type="mixpanel-data:explorer", prompt="...")
Task(subagent_type="mixpanel-data:diagnostician", prompt="...")
Task(subagent_type="mixpanel-data:synthesizer", prompt="...")
Task(subagent_type="mixpanel-data:narrator", prompt="...")
```

_Agents draw on shared analytical frameworks ([AARRR, GQM, Diagnosis](skills/mixpanel-analyst/references/analytical-frameworks.md)) and [cross-query synthesis patterns](skills/mixpanel-analyst/references/cross-query-synthesis.md)._

## Components

| Type | Name | Invocation |
|------|------|------------|
| Command | auth | `/mp-auth` — manage credentials, accounts, OAuth |
| Skill | setup | `/mixpanel-data:setup` — install deps, verify auth |
| Skill | mixpanel-analyst | Auto-triggered on analytics questions |
| Skill | dashboard-builder | Auto-triggered on dashboard creation requests |

| Script | Purpose |
|--------|---------|
| `help.py` | Live API documentation lookup from library docstrings |
| `auth_manager.py` | Programmatic auth status and credential management (JSON output) |

## Authentication

Two auth methods: service account (Basic Auth) or OAuth 2.0 PKCE. Run `/mixpanel-data:setup` for first-time configuration, or `/mp-auth` to manage credentials after initial setup.

## Reference Library

### Engine References

| File | Content |
|------|---------|
| `insights-reference.md` | Deep insights API: MathTypes, filters, formulas, patterns |
| `funnels-reference.md` | Deep funnels API: steps, exclusions, conversion windows |
| `retention-reference.md` | Deep retention API: cohorts, buckets, alignment modes |
| `flows-reference.md` | Deep flows API: NetworkX graph, anytree, tree traversal |

### Analysis & Methodology

| File | Content |
|------|---------|
| `query-taxonomy.md` | NL-to-engine routing, decomposition patterns, join strategies |
| `cross-query-synthesis.md` | Multi-engine join strategies, 11 investigation templates |
| `advanced-analysis.md` | Statistical methods, graph algorithms, visualization |
| `analytical-frameworks.md` | AARRR, GQM, North Star, diagnosis methodology |

### API & Schema

| File | Content |
|------|---------|
| `python-api.md` | Complete method signatures for all Workspace methods |
| `bookmark-params.md` | Bookmark params JSON for entity management |

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
│   ├── dashboard-builder/
│   │   ├── SKILL.md                    # Dashboard building workflow (8 phases)
│   │   └── references/
│   │       ├── dashboard-reference.md  # API, layout, text cards, gotchas
│   │       ├── dashboard-templates.md  # 9 design templates (KPI, AARRR, etc.)
│   │       ├── bookmark-pipeline.md    # Query → bookmark → dashboard
│   │       └── chart-types.md          # Chart type selection guide
│   └── mixpanel-analyst/
│       ├── SKILL.md                    # Core brain skill (query taxonomy)
│       ├── scripts/
│       │   ├── help.py                 # API documentation lookup
│       │   └── auth_manager.py         # Auth status and management
│       └── references/
│           ├── query-taxonomy.md       # Query routing + decomposition
│           ├── insights-reference.md   # Deep insights API
│           ├── funnels-reference.md    # Deep funnels API
│           ├── retention-reference.md  # Deep retention API
│           ├── flows-reference.md      # Deep flows + graph/tree
│           ├── cross-query-synthesis.md # Multi-engine synthesis
│           ├── advanced-analysis.md    # Statistical + visualization
│           ├── analytical-frameworks.md # AARRR, GQM, diagnosis
│           ├── python-api.md           # Full method signatures
│           └── bookmark-params.md      # Bookmark params schema
├── agents/
│   ├── analyst.md                      # Orchestrator
│   ├── explorer.md                     # Schema discovery + GQM
│   ├── diagnostician.md               # Root cause analysis
│   ├── synthesizer.md                  # Cross-query analysis
│   └── narrator.md                     # Executive reporting
├── commands/
│   └── auth.md                         # /mp-auth command
└── README.md
```

## Links

- [Library documentation](https://jaredmcfarland.github.io/mixpanel_data/)
- [Source repository](https://github.com/jaredmcfarland/mixpanel_data)

## License

MIT
