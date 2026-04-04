# mixpanel-data — CodeMode Analyst Plugin

Turn Claude into a senior data analyst and Mixpanel product analytics expert. Instead of calling CLI commands or MCP tools, Claude writes Python code using `mixpanel_data` + `pandas` to answer questions about your Mixpanel data.

## Philosophy

Inspired by CloudFlare's "Code Mode" MCP and Anthropic's "programmatic tool calling": **code is better than tools**. The agent writes Python that orchestrates analysis — parallel API calls, DataFrame transformations, visualizations — instead of issuing one-at-a-time commands.

## Quick Start

```
1. /mixpanel-data:setup              # Install mixpanel_data + pandas, verify auth
2. "How many signups last week?"      # Claude writes Python, executes, answers
3. "Why did retention drop?"          # Diagnostician agent investigates systematically
4. "Generate a Q1 executive report"   # Narrator agent creates a polished report
```

## Components

### Commands

| Command | Purpose |
|---------|---------|
| `/mp-auth` | Manage authentication — status, add/switch/test accounts, OAuth login |
| `/mp-auth list` | List all configured accounts |
| `/mp-auth add` | Guided service account setup (secrets entered securely in terminal) |
| `/mp-auth test` | Test current credentials against the Mixpanel API |
| `/mp-auth switch <name>` | Switch default account |
| `/mp-auth login` | OAuth browser-based login |

### Skills

| Skill | Invocation | Purpose |
|-------|-----------|---------|
| `setup` | `/mixpanel-data:setup` | Install dependencies, verify credentials |
| `mixpanel-analyst` | Auto-triggered | Core brain — CodeMode philosophy, Python API, analytical frameworks |

### Agents

| Agent | Model | Trigger | Purpose |
|-------|-------|---------|---------|
| `analyst` | Opus | General analytics questions | Orchestrator — queries data, interprets, recommends |
| `explorer` | Opus | Vague/open-ended questions | Schema discovery, GQM decomposition, hypothesis generation |
| `diagnostician` | Opus | "Why did X change?" | Root cause analysis across dimensions |
| `narrator` | Opus | Reports and summaries | Synthesizes findings into executive narratives |

### Scripts

| Script | Location | Purpose |
|--------|----------|---------|
| `setup.sh` | `skills/setup/scripts/` | Portable installer (uv → pip3 → pip fallback) |
| `help.py` | `skills/mixpanel-analyst/scripts/` | Programmatic docstring lookup for any class/method |
| `validate_bookmark.py` | `skills/mixpanel-analyst/scripts/` | Validate bookmark params JSON against canonical schema |
| `auth_manager.py` | `skills/mixpanel-analyst/scripts/` | Auth status, testing, account management (JSON output) |

### Reference Files (Progressive Disclosure)

| File | Lines | Content |
|------|-------|---------|
| `python-api.md` | ~300 | Complete Workspace method signatures |
| `pandas-patterns.md` | ~250 | DataFrame workflows, visualization patterns |
| `analytical-frameworks.md` | ~300 | AARRR, GQM, North Star, diagnosis methodology |
| `code-patterns.md` | ~300 | 12 ready-to-use Python analysis snippets |

## How It Works

When you ask a question about your Mixpanel data:

1. Claude loads the `mixpanel-analyst` skill (CodeMode philosophy + quick API reference)
2. Claude writes Python code using `mixpanel_data` to query your data
3. Results come back as pandas DataFrames for further analysis
4. Claude interprets the data and provides actionable insights

For complex investigations, Claude dispatches specialized agents:
- **Explorer** for vague questions → decomposes via GQM framework
- **Diagnostician** for "why did X change?" → segments across 4-6 dimensions
- **Narrator** for reports → pulls data across AARRR stages, writes polished markdown

The `help.py` script lets agents look up any method's exact signature on demand:

```bash
python3 help.py Workspace.segmentation   # → full signature + docstring
python3 help.py SegmentationResult        # → type fields + docs
python3 help.py types                     # → list all 150+ types
```

## Prerequisites

- Python 3.10+
- Mixpanel service account credentials (or OAuth)
- Claude Code with plugins enabled

## Installation

```bash
# Copy or symlink the mixpanel-plugin/ directory into your plugins location
# e.g. for local development:
ln -s /path/to/mixpanel-plugin ~/.claude/plugins/mixpanel-data
```

## Directory Structure

```
mixpanel-plugin/
├── .claude-plugin/
│   └── plugin.json                     # Plugin manifest (v2.0.0)
├── skills/
│   ├── setup/
│   │   ├── SKILL.md                    # /mixpanel-data:setup
│   │   └── scripts/
│   │       └── setup.sh               # Dependency installer
│   └── mixpanel-analyst/
│       ├── SKILL.md                    # Core brain skill
│       ├── scripts/
│       │   └── help.py                 # API documentation lookup
│       └── references/
│           ├── python-api.md           # Full method signatures
│           ├── pandas-patterns.md      # DataFrame patterns
│           ├── analytical-frameworks.md # AARRR, GQM, North Star
│           └── code-patterns.md        # Ready-to-use snippets
├── agents/
│   ├── analyst.md                      # General-purpose orchestrator
│   ├── explorer.md                     # Schema discovery + GQM
│   ├── diagnostician.md               # Root cause analysis
│   └── narrator.md                     # Executive storytelling
└── README.md
```

## Design Principles

1. **Code over tools** — Claude writes `python3 -c "..."` one-liners and `.py` files, never CLI commands
2. **Progressive disclosure** — Core knowledge in SKILL.md (~400 lines), detailed references loaded on demand
3. **On-demand API docs** — `help.py` pulls live docstrings so agents always have accurate signatures
4. **AARRR-first thinking** — Every question is classified into a pirate metric stage before querying
5. **GQM decomposition** — Vague questions are decomposed into Goal → Questions → Metrics
6. **Always discover first** — Agents explore the schema before writing queries
7. **Actionable insights** — Never just show data; always interpret and recommend

## Relationship to mixpanel_data

This plugin is a Claude Code interface to the [`mixpanel_data`](https://github.com/jaredmcfarland/mixpanel_data) Python library. The library provides the complete Mixpanel API surface (~170+ endpoints) as a Python facade. This plugin teaches Claude how to use that facade effectively for product analytics.

## License

MIT
