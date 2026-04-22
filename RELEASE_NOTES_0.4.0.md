# mixpanel_data 0.4.0 — Auth Architecture Redesign

> **Status:** alpha · **Released:** 2026-04-22 · **Spec:** [042-auth-architecture-redesign](specs/042-auth-architecture-redesign/spec.md) · **PR:** [#126](https://github.com/jaredmcfarland/mixpanel_data/pull/126)

This release ships a **complete rewrite of the auth subsystem** — single
schema, single resolver, three first-class account types
(`service_account` / `oauth_browser` / `oauth_token`), and a clean
in-session switching API (`Workspace.use(...)`). It is a **hard break**
from 0.3.x: legacy v1 / v2 configs no longer load and there is no
auto-migration path.

## Highlights

- **Account → Project → Workspace** as the primary mental model. Every
  command, every namespace, every mental model maps to one of those
  three axes.
- **`Workspace.use(...)`** is the only in-session switching method.
  Returns `self` for fluent chaining; preserves the underlying
  `httpx.Client` instance and per-account `/me` cache across switches.
- **Three account types**, all first-class:
  - `service_account` — Basic-auth long-lived credentials
  - `oauth_browser` — PKCE browser flow, tokens persisted to
    `~/.mp/accounts/{name}/tokens.json`, auto-refresh on expiry
  - `oauth_token` — static bearer (CI / agents); inline or env-var
- **`mp account login NAME`** runs the full PKCE dance end-to-end and
  backfills `default_project` from the post-login `/me` probe.
- **`mp target add NAME --account A --project P [--workspace W]`** and
  `mp target use NAME` — saved (account, project, workspace?) cursor
  positions for fast cross-context switching.
- **Cowork bridge** — `mp account export-bridge --to PATH` / `mp account
  remove-bridge` writers, with `oauth_browser` token embedding so the
  bridge consumer authenticates without a fresh PKCE round.
- **`mp session [--bridge]`** — at-a-glance view of resolved auth state.
- **Plugin v5.0.0** — `auth_manager.py` collapsed from ~727 to 257
  lines, JSON output with `schema_version: 1` and discriminated `state`
  field; the `/mixpanel-data:auth` slash command consumes it
  unconditionally with no `if version >= 2` branches.
- **Cross-cutting iteration** — sequential (`ws.use(project=...)`) and
  snapshot (`Session.replace(project=...) + ThreadPoolExecutor`) modes
  documented in `examples/cross_project.py` and pinned by 12 integration
  tests.
- **Net code reduction:** ~13,000 LoC removed across the auth subsystem
  + plugin (legacy `ConfigManager`, `AccountInfo`, `AuthBridgeFile`,
  `auth_credential.py`, dual-init `Workspace`, `mp auth` /
  `mp projects` / `mp workspaces` / `mp context` CLI groups, plugin
  `if version >= 2` branches, etc.).

## BREAKING CHANGES

### Configuration schema

- **No legacy v1 / v2 detection.** `~/.mp/config.toml` files written
  by `mixpanel_data 0.3.x` (or earlier) raise a Pydantic validation
  error on first load. There is **no `mp config convert`** — the
  legacy detection was deleted and conversion was descoped. Recovery
  path: delete `~/.mp/config.toml` and re-add accounts with
  `mp account add ...`.
- `[active].project` is rejected (the project axis lives on the
  account itself as `default_project`). Sessions persist
  `[active].account` + `[active].workspace` only.
- v1 / v2 OAuth token files at `~/.mp/oauth/tokens_{region}.json` are
  no longer read; tokens now live at
  `~/.mp/accounts/{name}/tokens.json`.

### CLI command groups

The following entire command groups were **deleted** (no
backwards-compat shim, no deprecation banner):

| Removed | Replacement |
|---|---|
| `mp auth list/add/remove/switch/show/test/login/logout` | `mp account list/add/remove/use/show/test/login/logout` |
| `mp auth migrate` | (no replacement — schema break, wipe `~/.mp/config.toml`) |
| `mp auth cowork-setup` | `mp account export-bridge --to PATH` |
| `mp auth cowork-status` | `mp session --bridge` |
| `mp auth cowork-teardown` | `mp account remove-bridge [--at PATH]` |
| `mp projects list/use/show` | `mp project list/use/show` |
| `mp workspaces list/use/show` | `mp workspace list/use/show` |
| `mp context show` | `mp session` |
| `mp config convert` | (descoped — see above) |

### CLI globals

| Removed | Replacement |
|---|---|
| `--credential` | `--account` (`-a`) |
| `--workspace-id` | `--workspace` (`-w`) |
| (added) | `--project` (`-p`) |
| (added) | `--target` (`-t`) — apply a saved target |

`--target` is mutually exclusive with `--account`/`--project`/`--workspace`.

### Public Python API

The following public names were **deleted** from `mixpanel_data`:

| Removed | Notes |
|---|---|
| `Credentials`, `AuthMethod` | Internal shim types — use `Workspace(...)` directly. |
| `AccountInfo`, `CredentialInfo`, `ProjectAlias` | Replaced by `AccountSummary` / `Account` (discriminated union) / `Target`. |
| `MigrationResult`, `ActiveContext` | Migration descoped; active state lives in `Session` / `ActiveSession`. |
| `AuthCredential`, `CredentialType`, `ProjectContext`, `ResolvedSession` | v2 internals — see `Account` + `Session` instead. |
| `Workspace.set_workspace_id(...)` | `Workspace.use(workspace=N)` |
| `Workspace.switch_project(...)` | `Workspace.use(project=P)` |
| `Workspace.switch_workspace(...)` | `Workspace.use(workspace=N)` |
| `Workspace.current_credential()` | `Workspace.account` (read-only property) |
| `Workspace.current_project()` | `Workspace.project` (read-only property) |
| `Workspace.test_credentials(...)` | `mp.accounts.test(NAME)` returning `AccountTestResult` |

The following names were **added** as part of the v3 surface and are
canonical going forward (re-exported from `mixpanel_data`):

- **Discriminated account union:** `Account`, `AccountType`,
  `ServiceAccount`, `OAuthBrowserAccount`, `OAuthTokenAccount`,
  `Region`
- **Session axes:** `Session`, `Project`, `WorkspaceRef`,
  `ActiveSession`
- **Result types:** `AccountSummary`, `AccountTestResult`,
  `OAuthLoginResult`, `Target`
- **Token plumbing:** `OAuthTokens`, `OAuthClientInfo`,
  `TokenResolver`, `OnDiskTokenResolver`
- **Cowork bridge:** `BridgeFile`, `load_bridge`
- **Exceptions:** `AccountInUseError`, `WorkspaceScopeError`
- **Functional namespaces:** `mp.accounts`, `mp.session`, `mp.targets`

### Plugin

- Plugin manifest version bumps from `4.1.0` → `5.0.0`.
- Slash command `/mixpanel-data:auth` re-routes to the new subcommand
  vocabulary (`account / project / workspace / target / session /
  bridge`). Old verbs (`status / list / switch / migrate / context /
  cowork-setup`) are gone.
- `auth_manager.py` JSON shape is now stable with
  `schema_version: 1` and a discriminated `state` field
  (`ok` | `needs_account` | `needs_project` | `error`).

## Migration recipe

Because there is no `mp config convert`, the migration is manual but
brief:

```bash
# 1. Back up your existing config (it will become unreadable on 0.4.x)
cp ~/.mp/config.toml ~/.mp/config.toml.0.3-backup

# 2. Wipe and re-add accounts
rm ~/.mp/config.toml

# Service account
mp account add team --type service_account \
  --username <SA_USERNAME> --project <PROJECT_ID> --region us
# (will prompt for the secret with hidden input)

# OAuth browser
mp account add personal --type oauth_browser --region us
mp account login personal     # opens browser for PKCE flow
```

Confirm the new state:

```bash
mp session              # shows resolved account / project / workspace
mp account list         # shows all configured accounts
mp project list         # shows accessible projects via /me
```

## What stayed the same

- Service account add / list / use semantics
- Region defaults (`us`, `eu`, `in`)
- Output formats (`json`, `jsonl`, `table`, `csv`, `plain`)
- Discovery / live query / streaming / entity CRUD APIs (no auth-only
  methods affected — `Workspace.events()`, `.segmentation()`,
  `.list_dashboards()`, etc. are unchanged)
- All entity CRUD on dashboards, reports, cohorts, flags, experiments,
  alerts, annotations, webhooks, lexicon, drop filters, custom
  properties, custom events, lookup tables, schemas

## Test posture

- **5,954 tests pass** at HEAD `18233dc` (~91% coverage)
- **18 / 18 live tests pass** against the real Mixpanel API across all
  three account types (service_account / oauth_browser / oauth_token)
  + cross-mode switching + bridge file consumption + edge cases
- **mypy --strict + ruff** clean

## Notes for downstream consumers

- Pin `mixpanel_data~=0.4.0` once the package is published.
- Pin plugin `mixpanel-data >= 5.0.0` so the slash command consumes
  the new JSON contract.
- `MP_OAUTH_TOKEN` env-var auth (added in PR #125) is preserved and
  documented in `CLAUDE.md` as the recommended mode for non-interactive
  contexts (CI, agents).

## Acknowledgements

Built across a 12-commit branch on top of an extensive 6-agent
PR review (see `specs/042-auth-architecture-redesign/pr-126-review-plan.md`
for the cross-cutting findings + dispositions). Co-authored with
Claude Opus 4.7 (1M context).
