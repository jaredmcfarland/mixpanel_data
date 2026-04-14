# Source-Aware Plugin Architecture — Design Spec

**Status:** Design approved, ready for implementation planning
**Date:** 2026-04-13

## Motivation

The mixpanel-data marketplace plugin (`mixpanel-plugin/`) is a sibling directory to the library source (`src/mixpanel_data/`) in the same repository. When Claude Code clones the marketplace, it clones the entire repo — meaning the full library source, tests, design docs, and CI config are all available inside the plugin installation at `~/.claude/plugins/marketplaces/mixpanel-data-marketplace/`.

This structural property is currently unexploited. The agents have hand-written API references and a `help.py` introspection script, but no awareness that the actual source code is sitting right next to them.

### Use Cases

1. **Error diagnosis** — Agent hits an exception, reads the source to understand why (e.g., reads validators to understand rule U30 that rejected its query). Reactive, triggered by failure.

2. **API deepening** — Agent wants to understand a parameter's behavior more deeply than the docstring explains (e.g., what does `alignment="birth"` actually do to the date math?). Exploratory, triggered by uncertainty.

3. **Bug discovery / fix PRs** — Agent notices something wrong during a session and can investigate, confirm, and open a fix PR against the library. Proactive, triggered by the agent's judgment.

### Target Audience

Mixpanel engineers who install the plugin. They are both users and potential contributors. The plugin becomes an analytics tool AND a development accelerator — use it, find issues, fix them, all in the same session.

## Architecture — Four Components

### Component 1: Source Awareness in Existing Prompts

Every agent and the mixpanelyst skill get a "Source Code Access" section. This is the foundation — agents simply *know* the source is there.

#### Mixpanelyst SKILL.md Addition

```markdown
## Source Code Access

The full `mixpanel_data` library source ships with this plugin. Use it to diagnose errors,
understand parameter behavior, and discover bugs.

### Paths

| Resource | Path |
|----------|------|
| Library source | `${CLAUDE_PLUGIN_ROOT}/../src/mixpanel_data/` |
| Tests | `${CLAUDE_PLUGIN_ROOT}/../tests/` |
| Design docs | `${CLAUDE_PLUGIN_ROOT}/../context/` |
| Project standards | `${CLAUDE_PLUGIN_ROOT}/../CLAUDE.md` |

### Package Map

workspace.py              — All public query & CRUD methods (the facade)
types.py                  — Result types, params models, enums
exceptions.py             — Exception hierarchy
auth.py                   — Public auth module
_internal/
  api_client.py           — HTTP client, request/response handling
  config.py               — Credential & config resolution
  bookmark_builders.py    — Query params → bookmark JSON translation
  validation.py           — Bookmark validation rules
  transforms.py           — API response → result type transforms
  services/
    discovery.py          — Schema discovery (events, properties, cohorts)
    live_query.py         — Query execution against Mixpanel APIs

### Escalation Order

1. **help.py** — signatures + docstrings (fastest, cheapest)
2. **help.py source** — targeted source snippet (20-50 lines)
3. **Read/Grep** — full file reads (when you need surrounding context)
4. **Librarian agent** — deep investigation (multi-file tracing, bug confirmation)

### When to Read Source

- Exception with a code/message you don't understand → read the raising method
- Parameter behavior unclear after checking docstring → read the builder
- Unexpected result shape → read the type's `.df` property implementation
- Suspect a library bug → delegate to librarian agent
```

#### Agent Prompts (analyst, diagnostician, explorer, narrator, synthesizer)

Each gets a condensed version:

```markdown
## Source Code Access

Library source is at `${CLAUDE_PLUGIN_ROOT}/../src/mixpanel_data/`. Use `help.py source <symbol>`
for targeted snippets. For deep investigation or bug discovery, delegate to the **librarian** agent.
```

---

### Component 2: help.py `source` Subcommand

Extend the existing `help.py` with a `source` subcommand that uses Python's `inspect` module to locate and display the actual source code for any symbol.

#### Usage

```bash
python3 help.py source Workspace.query_user     # method body + file:line
python3 help.py source UserQueryResult           # class definition + fields
python3 help.py source BookmarkValidationError   # exception class
python3 help.py source Workspace.query_user 50   # show 50 lines of context (default: 30)
```

#### Output Format

```
# Workspace.query_user — source
# File: /path/to/src/mixpanel_data/workspace.py:842-892

    def query_user(
        self,
        *,
        where: Filter | list[Filter] | str | None = None,
        ...
    ) -> UserQueryResult:
        """Query user profiles from Mixpanel's Engage API.
        ...
        """
        params = self._build_user_params(...)
        response = self._service.engage_query(params)
        return UserQueryResult.from_response(response, params)
```

#### Implementation Approach

- Uses `inspect.getsource()` and `inspect.getsourcefile()` to resolve symbol → file + line
- Falls back to reading from `${CLAUDE_PLUGIN_ROOT}/../src/` if inspect doesn't resolve
- Optional context-lines argument (default 30) to control output size
- Shows file path relative to source root for readability

#### Why This Matters

Reading all of `workspace.py` (~600 lines) to understand one method burns context. `help.py source` returns just the relevant 20-50 lines. This is the difference between source access being practical vs. wasteful.

---

### Component 3: Librarian Agent

A new agent at `mixpanel-plugin/agents/librarian.md` that specializes in library source navigation, implementation Q&A, and bug fix PRs.

#### Definition

```yaml
name: librarian
description: |
  Deep-dive into the mixpanel_data library source code. Use for implementation questions
  ("how does credential resolution work?"), error diagnosis ("why does query_user reject
  as_of in aggregate mode?"), and bug fix PRs. Has full read access to source, tests,
  and design documents.
model: sonnet
tools: Read, Write, Bash, Grep, Glob
```

#### Three Modes of Operation

| Mode | Trigger | Output |
|---|---|---|
| **Explain** | "How does X work?" | Source-grounded explanation with file:line references |
| **Diagnose** | "Why did this error occur?" | Root cause with exact source location + fix suggestion |
| **Fix** | "Create a fix PR for this bug" | Branch, fix, tests, commit, PR |

#### Explain Mode

Answers implementation questions by tracing through source:

```
Agent dispatches: "How does Workspace resolve credentials when both
account= and credential= are provided?"

Librarian reads: workspace.py __init__, _internal/config.py, auth.py
Returns: "Credential resolution follows this priority: (1) explicit credential=
uses v2 config lookup via ConfigManager.get_credential(). (2) explicit account=
uses v1 config lookup. (3) Neither provided → tries env vars MP_USERNAME/MP_SECRET,
then falls back to default credential/account. See workspace.py:45-67 and
_internal/config.py:120-145."
```

#### Diagnose Mode

Traces errors to their source location:

```
Agent dispatches: "query_user raised QueryError: 'as_of is not supported
in aggregate mode'. Explain why and suggest the correct usage."

Librarian reads: workspace.py query_user method, finds validation check
Returns: "Validation rule U30 at workspace.py:892 rejects as_of when
mode='aggregate'. as_of is only valid for mode='profiles' — it sets
a point-in-time snapshot. For aggregate counts, the API always uses
current state. Fix: remove as_of parameter, or switch to mode='profiles'."
```

#### Fix Mode

Context-aware workflow depending on where the agent is running:

**If current working directory IS the library repo:**
1. Create feature branch from main
2. Write failing test (TDD per CLAUDE.md standards)
3. Implement fix
4. Run `just check` (lint + typecheck + test)
5. Commit with conventional format
6. Push and create PR via `gh`

**If current working directory is NOT the library repo:**
1. Investigate in the marketplace clone (read-only)
2. Produce a structured bug report:
   - File, line, root cause
   - Suggested fix (code diff)
   - Test that would catch it
   - Severity assessment
3. Offer: "Want me to clone the repo and create a fix PR?"
4. If approved, clone to a temp worktree and proceed with fix workflow

#### What the Librarian Knows (baked into prompt)

- Full package map with file descriptions
- Project code quality standards (from CLAUDE.md — TDD, mypy --strict, docstrings, 90% coverage)
- How to run tests (`just check`, `just test -k <name>`)
- Exception hierarchy and validation rule naming conventions
- How to navigate the layered architecture (CLI → Workspace → Services → API Client)

---

### Component 4: Integration — How Agents Delegate

#### Delegation Rules

| Situation | Who handles |
|---|---|
| Quick error → read one method to understand | Agent handles directly (Read tool) |
| "How does X work internally?" | Delegate to librarian (Explain) |
| Unexpected behavior, suspect a bug | Delegate to librarian (Diagnose) |
| Confirmed bug, wants a fix | Delegate to librarian (Fix) |
| User asks about library internals | Delegate to librarian (Explain) |

#### Analyst Prompt Update (delegation table addition)

```markdown
| Question type | Route to |
|---|---|
| ... existing delegation rules ... |
| Implementation question ("how does X work?") | **Librarian** (explain mode) |
| Error you can't diagnose from docstrings | **Librarian** (diagnose mode) |
| Confirmed library bug | **Librarian** (fix mode) |
```

#### User-Facing Discovery

Agents can proactively surface source-level capabilities:

> "I notice you hit a QueryError. I can investigate the library source to understand exactly why this failed — want me to dig in?"

For Mixpanel engineers:

> "I found what looks like a bug in the retention parameter validation — bucket_sizes allows [0] but the API rejects it. Want me to create a fix PR?"

---

## Summary of Changes

| Component | Files Changed | New Files |
|---|---|---|
| Source awareness (prompts) | `skills/mixpanelyst/SKILL.md`, 5 agent `.md` files | None |
| help.py source subcommand | `skills/mixpanelyst/scripts/help.py` | None |
| Librarian agent | None | `agents/librarian.md` |
| Integration (delegation) | `agents/analyst.md`, `agents/diagnostician.md` | None |

## Path Verification

Confirmed on 2026-04-13 that the relative path mechanics work:

```
${CLAUDE_PLUGIN_ROOT} = mixpanel-plugin/
${CLAUDE_PLUGIN_ROOT}/../src/mixpanel_data/  → full library source
${CLAUDE_PLUGIN_ROOT}/../tests/              → full test suite
${CLAUDE_PLUGIN_ROOT}/../context/            → design documents
${CLAUDE_PLUGIN_ROOT}/../CLAUDE.md           → project standards
```

Package structure at time of design:

```
src/mixpanel_data/
├── workspace.py
├── types.py
├── exceptions.py
├── auth.py
├── _internal/
│   ├── api_client.py
│   ├── auth_credential.py
│   ├── bookmark_builders.py
│   ├── bookmark_enums.py
│   ├── config.py
│   ├── expressions.py
│   ├── me.py
│   ├── pagination.py
│   ├── segfilter.py
│   ├── transforms.py
│   ├── validation.py
│   ├── auth/
│   │   ├── bridge.py
│   │   ├── callback_server.py
│   │   ├── client_registration.py
│   │   ├── flow.py
│   │   ├── pkce.py
│   │   ├── storage.py
│   │   └── token.py
│   └── services/
│       ├── discovery.py
│       └── live_query.py
└── cli/
    └── commands/
```

## Open Questions

- **Staleness**: The marketplace clone is pinned to whatever commit was last fetched. Source may lag behind the latest `main`. Should the librarian detect and warn about this?
- **Dependencies in clone**: The marketplace clone may not have `mixpanel_data` installed in a venv. The `help.py source` subcommand needs the package importable. Should we fall back to raw file reads with `ast` parsing?
- **Scope of fix mode**: Should the librarian only fix bugs, or also implement missing features? Suggest limiting to bug fixes initially.
