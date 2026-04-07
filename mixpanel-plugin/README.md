# mixpanel-data — CodeMode Analyst Plugin (v3.0.0)

Turn Claude into a senior data analyst and Mixpanel product analytics expert. Instead of calling CLI commands or MCP tools, Claude writes Python code using `mixpanel_data`'s four typed query engines plus `pandas`, `networkx`, and `anytree` for sophisticated multi-engine analysis.

## Query Taxonomy

| Engine | Method | Core Question | Result Type |
|--------|--------|---------------|-------------|
| Insights | `ws.query()` | How much? How many? | `QueryResult` |
| Funnels | `ws.query_funnel()` | Do users convert through a sequence? | `FunnelQueryResult` |
| Retention | `ws.query_retention()` | Do users come back? | `RetentionQueryResult` |
| Flows | `ws.query_flow()` | What paths do users take? | `FlowQueryResult` |

## Components

| Type | Name | Invocation |
|------|------|------------|
| Command | auth | `/mp-auth` |
| Skill | setup | `/mixpanel-data:setup` |
| Skill | mixpanel-analyst | Auto-triggered on analytics questions |
| Agent | analyst | Task tool — orchestrator |
| Agent | explorer | Task tool — schema discovery |
| Agent | diagnostician | Task tool — root cause |
| Agent | synthesizer | Task tool — cross-query analysis |
| Agent | narrator | Task tool — executive reports |
| Script | help.py | API doc lookup |
| Script | auth_manager.py | Auth management |
| Script | validate_bookmark.py | Bookmark validation |

## Usage

### Quick Start

```
1. /mixpanel-data:setup              # Install deps, verify auth
2. "How many signups last week?"      # Insights query
3. "Where do users drop off?"         # Funnel analysis
4. "Do users retain after onboarding?"# Retention curve
5. "What do users do after signup?"   # Flow analysis
```

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

## Agent Usage

For complex investigations, Claude dispatches specialized agents via the Task tool:

```
Task(subagent_type="mixpanel-data:analyst", prompt="...")
Task(subagent_type="mixpanel-data:explorer", prompt="...")
Task(subagent_type="mixpanel-data:diagnostician", prompt="...")
Task(subagent_type="mixpanel-data:synthesizer", prompt="...")
Task(subagent_type="mixpanel-data:narrator", prompt="...")
```

- **analyst** — General-purpose orchestrator; routes queries, coordinates investigations
- **explorer** — Schema discovery, GQM decomposition, investigation planning
- **diagnostician** — Root cause analysis using all 4 query engines
- **synthesizer** — Cross-query analysis with pandas, networkx, anytree, scipy
- **narrator** — Executive summaries and stakeholder reports

## Reference Files

| File | Content |
|------|---------|
| `query-taxonomy.md` | NL-to-engine routing, decomposition patterns, join strategies |
| `insights-reference.md` | Deep insights API: MathTypes, filters, formulas, patterns |
| `funnels-reference.md` | Deep funnels API: steps, exclusions, conversion windows |
| `retention-reference.md` | Deep retention API: cohorts, buckets, alignment modes |
| `flows-reference.md` | Deep flows API: NetworkX graph, anytree, tree traversal |
| `cross-query-synthesis.md` | Multi-engine join strategies, 10 investigation templates |
| `advanced-analysis.md` | Statistical methods, graph algorithms, visualization |
| `analytical-frameworks.md` | AARRR, GQM, North Star, diagnosis methodology |
| `python-api.md` | Complete method signatures for all Workspace methods |
| `bookmark-params.md` | Bookmark params JSON for entity management |

## Installation

```bash
# Option 1: Add as a local dev marketplace
/plugin marketplace add /path/to/mixpanel_data/mixpanel-plugin
/plugin install mixpanel-data@mixpanel-data

# Option 2: Symlink into plugins directory
ln -s /path/to/mixpanel_data/mixpanel-plugin ~/.claude/plugins/mixpanel-data
```

Then restart Claude Code.

## Prerequisites

- Python 3.10+
- Mixpanel service account credentials (or OAuth)
- Claude Code with plugins enabled

## Directory Structure

```
mixpanel-plugin/
├── .claude-plugin/
│   └── plugin.json                     # Plugin manifest (v3.0.0)
├── skills/
│   ├── setup/
│   │   ├── SKILL.md                    # /mixpanel-data:setup
│   │   └── scripts/
│   │       └── setup.sh               # Dependency installer
│   └── mixpanel-analyst/
│       ├── SKILL.md                    # Core brain skill (query taxonomy)
│       ├── scripts/
│       │   ├── help.py                 # API documentation lookup
│       │   ├── auth_manager.py         # Auth status and management
│       │   ├── validate_bookmark.py    # Bookmark params validation
│       │   └── schemas/
│       │       └── bookmark.json       # Canonical JSON schema
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

## License

MIT
