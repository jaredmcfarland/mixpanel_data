# Library Documentation (Hosted)

The `mixpanel_data` library has comprehensive hosted documentation with LLM-optimized endpoints, plus an AI-powered wiki for interactive Q&A.

## Three Knowledge Layers

| Layer | Tool | Best for |
|-------|------|----------|
| Plugin references | `Read` | Analytical methodology — HOW to think about analytics |
| Hosted docs | `WebFetch` | Library documentation — WHAT the API does, with tutorials and examples |
| DeepWiki | `mcp__deepwiki__*` | Interactive Q&A — synthesized answers about architecture and implementation |

## Hosted Docs

**Base URL**: `https://jaredmcfarland.github.io/mixpanel_data/`

### Step 1: Discover what exists

Fetch the structured index (~3KB) to find the right page:

```
WebFetch(url="https://jaredmcfarland.github.io/mixpanel_data/llms.txt")
```

### Step 2: Read a specific page

Each page is available as raw markdown at its `index.md` path:

```
WebFetch(url="https://jaredmcfarland.github.io/mixpanel_data/guide/entity-management/index.md")
```

## DeepWiki (Interactive Q&A)

Ask synthesized questions about the `mixpanel_data` codebase, architecture, or implementation details. This plugin bundles the DeepWiki MCP server — the tools are available automatically.

**Tools:**

| Tool | Purpose |
|------|---------|
| `ask_question` | Ask any question and get an AI-powered answer grounded in the codebase |
| `read_wiki_structure` | Get a list of documentation topics for the repo |
| `read_wiki_contents` | Read full documentation about a specific topic |

**Usage** (always pass `repo="jaredmcfarland/mixpanel_data"`):

```
mcp__deepwiki__ask_question(repo="jaredmcfarland/mixpanel_data", question="How does the Workspace class resolve credentials?")
mcp__deepwiki__read_wiki_structure(repo="jaredmcfarland/mixpanel_data")
mcp__deepwiki__read_wiki_contents(repo="jaredmcfarland/mixpanel_data", path="Architecture Overview")
```

**When to use DeepWiki vs WebFetch docs:**
- **WebFetch docs** — You know which page you need (e.g., "entity management CRUD reference")
- **DeepWiki** — You have a question that may span multiple files or need synthesis (e.g., "how does auth credential resolution work end-to-end?")

## When to Use Docs vs Plugin References

| Need | Source |
|------|--------|
| Analytical methodology (AARRR, GQM, diagnosis) | Plugin references |
| NL→engine routing (50+ signal patterns) | Plugin references (query-taxonomy.md) |
| Cross-query synthesis (join strategies, templates) | Plugin references (cross-query-synthesis.md) |
| Advanced analysis (statistics, graph algorithms) | Plugin references (advanced-analysis.md) |
| Dashboard building (templates, pipeline) | Plugin references (dashboard-expert/) |
| **Comprehensive query tutorials with examples** | **Hosted docs** |
| **Entity management (CRUD for all entity types)** | **Hosted docs** |
| **Data governance (Lexicon, schemas, drop filters)** | **Hosted docs** |
| **Discovery guide (detailed)** | **Hosted docs** |
| **Streaming & ETL patterns** | **Hosted docs** |
| **Complete type reference (70+ types)** | **Hosted docs** |
| **Exception hierarchy & error codes** | **Hosted docs** |
| **Configuration & multi-account setup** | **Hosted docs** |
| **Architecture & design decisions** | **Hosted docs** |

## Page Map

Prepend `https://jaredmcfarland.github.io/mixpanel_data/` to any path below.

### Guides

| Topic | Path |
|-------|------|
| Unified query system overview | `guide/unified-query-system/index.md` |
| Discovery (detailed) | `guide/discovery/index.md` |
| Insights queries (tutorial) | `guide/query/index.md` |
| Funnel queries (tutorial) | `guide/query-funnels/index.md` |
| Retention queries (tutorial) | `guide/query-retention/index.md` |
| Flow queries (tutorial) | `guide/query-flows/index.md` |
| Entity management (full CRUD) | `guide/entity-management/index.md` |
| Data governance | `guide/data-governance/index.md` |
| Streaming & ETL | `guide/streaming/index.md` |
| Live analytics (legacy) | `guide/live-analytics/index.md` |

### API Reference

| Topic | Path |
|-------|------|
| API overview & imports | `api/index.md` |
| Workspace class (all methods) | `api/workspace/index.md` |
| Result types (70+ types) | `api/types/index.md` |
| Authentication | `api/auth/index.md` |
| Exceptions | `api/exceptions/index.md` |

### Other

| Topic | Path |
|-------|------|
| Project overview | `index.md` |
| Installation | `getting-started/installation/index.md` |
| Quick start | `getting-started/quickstart/index.md` |
| Configuration | `getting-started/configuration/index.md` |
| CLI overview | `cli/index.md` |
| CLI commands (full reference) | `cli/commands/index.md` |
| Architecture | `architecture/design/index.md` |
