# Authentication Architecture Redesign

**Status:** Proposed
**Author:** Jared McFarland (with Claude analysis)
**Date:** 2026-04-21
**Supersedes:** [`auth-project-workspace-redesign.md`](auth-project-workspace-redesign.md)

> **TL;DR.** The current authentication system carries the scar tissue of an
> incomplete v1→v2 migration: parallel code paths, duplicated terminology
> (`account` vs `credential`), six fallback layers for OAuth project resolution,
> and an `AuthCredential` model that is still wrapped in a v1 `Credentials`
> object before reaching the API client. This document proposes a clean break
> to a single, unified model — **Account → Project → Workspace** — with one
> resolution algorithm, one configuration schema, one CLI grammar, and one
> Python facade. All v1 code paths, the v1↔v2 bridge, and the `migrate_v1_to_v2`
> command are deleted. The redesign treats Mixpanel's three credential
> mechanisms (service accounts, OAuth PKCE, raw bearer tokens) as variants of
> a single `Account` type, and turns cross-account / cross-project /
> cross-workspace switching into a first-class, one-line operation.

---

## Table of Contents

1. [Current State](#1-current-state)
2. [Identified Problems](#2-identified-problems)
3. [Design Principles](#3-design-principles)
4. [Mental Model & Vocabulary](#4-mental-model--vocabulary)
5. [Configuration Schema](#5-configuration-schema)
6. [Type System](#6-type-system)
7. [Credential Resolution](#7-credential-resolution)
8. [Filesystem Layout](#8-filesystem-layout)
9. [Python Public API](#9-python-public-api)
10. [CLI Surface](#10-cli-surface)
11. [Plugin / Agent Surface](#11-plugin--agent-surface)
12. [Cross-Account / Cross-Project / Cross-Workspace Switching](#12-cross-account--cross-project--cross-workspace-switching)
13. [Discovery & The `/me` Endpoint](#13-discovery--the-me-endpoint)
14. [Cowork Bridge Files](#14-cowork-bridge-files)
15. [Tech Debt to Remove](#15-tech-debt-to-remove)
16. [Implementation Phases](#16-implementation-phases)
17. [Test Strategy](#17-test-strategy)
18. [Open Questions](#18-open-questions)
19. [Appendix A: Resolution Decision Tree](#appendix-a-resolution-decision-tree)
20. [Appendix B: Vocabulary Mapping (Old → New)](#appendix-b-vocabulary-mapping-old--new)

---

## 1. Current State

### 1.1 What exists today

The authentication system is a partially-completed migration. Two coexisting
schemas (v1 "accounts" and v2 "credentials + project aliases") share the same
file (`~/.mp/config.toml`), the same loader (`ConfigManager`), and the same
public-facing classes (`Workspace`, `auth_manager.py`). Both branches are
actively reachable from the CLI, the Python SDK, and the plugin agent script.

| Layer | v1 surface | v2 surface | Bridge between them |
|---|---|---|---|
| Config schema | `[accounts.X]` blocks + `default = "X"` | `[credentials.X]` + `[projects.X]` + `[active]` | `config_version = 2` flag |
| Auth model | `Credentials` (project-bundled, frozen) | `AuthCredential` + `ProjectContext` + `ResolvedSession` | `Credentials.to_resolved_session()` and `Workspace._session_to_credentials()` |
| Resolver | `ConfigManager.resolve_credentials()` | `ConfigManager.resolve_session()` | v2 resolver internally calls v1 resolver for legacy configs |
| API client | `MixpanelAPIClient(credentials: Credentials)` | (still takes `Credentials`) | `Workspace._session_to_credentials()` downgrades v2 → v1 before construction |
| CLI | `mp auth list/add/remove/switch/show/test` | `mp auth list` (forks on version), `mp projects/workspaces/context` | `if config.config_version() >= 2:` branches |
| Plugin script | `auth_manager.py status` (v1 path) | `auth_manager.py status` (v2 path with `if version >= 2:`) | Same script, branched everywhere |

**Lines of code in the auth surface:** ~7,200 across 15 files
(`config.py` alone is 1,937 lines, `cli/commands/auth.py` is 1,180 lines).

### 1.2 Where each user enters the system

Even with a single user (alpha tester) on a fresh machine, the system can
plausibly enter through **eight** different code paths to construct a single
authenticated request:

1. `MP_USERNAME` + `MP_SECRET` + `MP_PROJECT_ID` + `MP_REGION` (SA env quad)
2. `MP_OAUTH_TOKEN` + `MP_PROJECT_ID` + `MP_REGION` (OAuth env triple, PR #125)
3. Cowork bridge file at `~/.claude/mixpanel/auth.json`
4. OAuth tokens on disk at `~/.mp/oauth/tokens_{region}.json`
5. v1 named account from `[accounts.X]`
6. v1 default account from `default = "X"`
7. v2 named credential via `--credential X` + `[credentials.X]`
8. v2 active context via `[active] credential = "X"`

Each path has its own resolver function, its own fallback chain, and its own
edge cases. The OAuth-from-disk path alone consults six sources to determine
which `project_id` to attach (`tokens.project_id` → `MP_PROJECT_ID` env → v1
`default` account's project → v1 first account's project → v2
`active.project_id` → v2 first credential's region with `active.project_id` →
last-resort scan of all OAuth storage).

### 1.3 What v2 was supposed to deliver

The redesign that produced v2 (documented in
`context/auth-project-workspace-redesign.md`) had a clear mission:

- Decouple identity (`AuthCredential`) from selection (`ProjectContext`).
- Add `/me`-based discovery with disk caching.
- Make the active project + workspace persist across sessions.
- Make project switching as cheap as a config write.
- Eliminate the duplicate-account problem (one SA × N projects = N config entries).

**It mostly succeeded** — `Workspace.discover_projects()`, `switch_project()`,
the `/me` cache, and the v2 schema all work today. But the *cleanup* never
happened: v1 was never removed, the `Credentials` class is still on every code
path, and the entry-point story is now genuinely worse than v1 alone because
both schemas coexist.

---

## 2. Identified Problems

The user-cited problems map to deeper structural issues. Each is verified
against the current code.

### 2.1 v1/v2 discrepancies and migration tech debt (USER PROBLEM #1)

**Symptoms:**

- `Workspace.__init__` (`workspace.py:354-462`) has three branches: explicit
  `credential=` (v2), `config_version() >= 2` (v2), and the legacy v1 path.
  All three feed into the same `Credentials` object via
  `_session_to_credentials`.
- `ConfigManager.resolve_session` (`config.py:1562-1653`) calls
  `_resolve_session_v1` or `_resolve_session_v2` based on a `config_version`
  field. `_resolve_session_v1` calls `resolve_credentials()` then converts
  back. `_resolve_session_v2` re-implements the resolution from scratch.
- The plugin's `auth_manager.py` (`mixpanel-plugin/skills/mixpanelyst/scripts/auth_manager.py`)
  has `if version >= 2:` branches in 8 of 12 commands.
- The `mp auth list`, `mp auth add`, `mp auth show`, `mp auth switch`, and
  `mp auth test` commands all have version-conditional behavior or are
  v1-only and silently no-op for v2 users.
- `MixpanelAPIClient.with_project` (`api_client.py:1015-1062`) builds a fresh
  `Credentials` object instead of mutating a `ResolvedSession.project` —
  forces re-validation on every project switch.

**Root cause:** v1 was never deleted. v2 was layered on top.

### 2.2 Fresh installs default to v1 (USER PROBLEM #2)

**Verified:**

- `ConfigManager.config_version()` (`config.py:1038-1051`) returns `1` whenever
  the `config_version` key is absent — including the case of a brand-new file.
- `ConfigManager.add_account()` (`config.py:917-961`) writes a v1 `[accounts.X]`
  block and never sets `config_version = 2`.
- `mp auth add` (the most-used onboarding command) calls `add_account()`, so
  any user whose first action is "add a service account" is silently put on v1.
- Only `mp auth login` (OAuth) and `ConfigManager.add_credential()` /
  `add_project_alias()` set `config_version = 2`.
- The `_post_login_setup` helper in `cli/commands/auth.py:402-523` is the
  *only* thing that auto-promotes a fresh install to v2 (because OAuth
  hits `add_credential`), and it only runs for OAuth flows.

**Consequence:** SA-first users land on v1 forever unless they explicitly run
`mp auth migrate`. There's no reason for v1 to be the default.

### 2.3 Account/Project/Workspace not unified (USER PROBLEM #3)

**Verified:**

- v1 conflates "auth identity" and "project selection" into a single
  `[accounts.X]` block. Real-world `~/.mp/config.toml` has 7 demo accounts
  with identical SA credentials, differing only in `project_id`.
- v2 splits them — but the resulting `[credentials]` + `[projects]` +
  `[active]` schema requires three separate concepts the user has to learn
  ("credential" ≠ "account", "project alias" ≠ "project", "active context"
  is a fourth concept), and then a fifth ("workspace") that's only set
  per-session and lazily resolved.
- `mp account` does not exist; you have `mp auth`, `mp projects`, `mp workspaces`,
  and `mp context` — four separate command groups for one logical hierarchy.
- The Python `Workspace` class doesn't expose an account abstraction at all;
  it has `current_credential`, `current_project`, and `workspace_id` properties.

**Consequence:** The user mental model ("I have accounts → each has projects →
each has workspaces") is fragmented across five concepts (auth/credential,
account, project, project alias, workspace), each with its own CLI verb.

### 2.4 SA, OAuth PKCE, and bearer token not unified (USER PROBLEM #4)

**Verified:**

- Service accounts: stored in v1 `[accounts.X]` blocks with `username`+`secret`
  inline. v2 stores them in `[credentials.X]` with `type = "service_account"`.
- OAuth PKCE: triggered by `mp auth login`. Tokens stored in
  `~/.mp/oauth/tokens_{region}.json` (one slot per region, no scoping by
  account). v2 represents them as `[credentials.X]` with `type = "oauth"`
  and *no inline secret* — token is loaded from disk on resolution.
- Raw bearer tokens (PR #125): supplied via `MP_OAUTH_TOKEN` env var only.
  Cannot be persisted to config. Cannot be named. Cannot coexist with named
  credentials. The `Credentials.from_oauth_token` factory exists but is only
  reachable from `_resolve_from_env`.

These are *three different lifecycles* (rotated by user, refreshed by client,
refreshed externally) but they don't share a common abstraction. Switching
between them today means changing env vars, deleting files, or editing TOML
by hand. There is no `mp account use ci-token` equivalent.

**Consequence:** A user with all three credential types (a personal OAuth, a
team SA, and a CI bearer) cannot easily switch between them.

### 2.5 Other structural problems

| # | Problem | Evidence |
|---|---|---|
| 5 | `Credentials.project_id` is required at construction | `config.py:126-127` raises if empty, even for pure-identity OAuth credentials |
| 6 | OAuth tokens carry `project_id` (legacy artifact) | `OAuthTokens.project_id` field (`token.py:60`); should be unrelated to authentication |
| 7 | Six-layer fallback for OAuth `project_id` | `_resolve_region_and_project_for_oauth` (`config.py:655-723`) consults env, v1 default, v1 first, v2 active, v2 first credential's region, scan-all-tokens |
| 8 | Two ways to switch projects (in-session vs persisted) | `Workspace.switch_project()` doesn't write to config; `mp projects switch` doesn't update the Workspace instance |
| 9 | `mp context switch` only accepts aliases, not raw IDs | `cli/commands/context.py:60-109` — to "use" a project ID you must alias it first |
| 10 | Workspace ID buried in CLI flag (`--workspace-id`) but in CLI command (`mp workspaces switch`); inconsistent terminology | `main.py:106-113` vs `commands/workspaces_cmd.py` |
| 11 | OAuth tokens scoped by region only, not by account | `tokens_{region}.json` — cannot have two OAuth identities in `us` |
| 12 | Plugin's `auth_manager.py` has different semantics for `switch` based on version | v1: changes default account. v2: changes active credential |
| 13 | "switch" verb is overloaded | `mp auth switch` (default account), `mp projects switch` (active project), `mp workspaces switch` (active workspace), `mp context switch` (alias). Same word, four meanings |
| 14 | Bridge file embeds project context | `AuthBridgeFile.project_id` is required, even though the bridge is a credential courier. This couples Cowork sessions to a project |
| 15 | Custom headers handled via env var poisoning | `apply_config_custom_header()` mutates `os.environ` — invisible side effect, no per-account config |

---

## 3. Design Principles

These are intentionally short. Every later section references them.

1. **One model.** Account → Project → Workspace. No parallel hierarchy.
2. **One resolver.** A single function that returns a fully-resolved `Session`
   from a small, ordered set of inputs. No multi-layer fallbacks.
3. **One schema.** No `config_version` field — there is only one schema. Old
   configs are rejected with a clear migration script (one-shot, not a
   permanent compatibility branch).
4. **One word per concept.** "Account" replaces both "credential" and the v1
   "account". "Use" replaces "switch", "default", and "active". "Project" and
   "workspace" never get an `_id` suffix in user-facing surfaces.
5. **Cheap switching is the point.** Every layer (Python, CLI, agent) exposes
   a one-line operation to change account, project, or workspace.
6. **Identity is project-agnostic.** Authentication credentials never embed a
   `project_id`. Selecting a project is a separate, equally cheap operation.
7. **Discovery before configuration.** `mp project list` should work with
   nothing more than authentication. The user shouldn't need to know project
   IDs out of band.
8. **Agents are first-class users.** Every operation must be expressible
   non-interactively, with structured output, and without prompting for
   secrets.
9. **No dead branches.** When in doubt, delete. The package has handful of
   alpha testers; this is the right time to ship breaking changes.

---

## 4. Mental Model & Vocabulary

### 4.1 The hierarchy

```
Account                            (authentication identity)
  ├── auth method:  service_account | oauth_browser | oauth_token
  ├── region:       us | eu | in
  └── grants access to →
      Project                      (Mixpanel project — has data)
        ├── id, name, organization
        └── contains →
            Workspace              (slice of a project — has saved entities)
              └── id, name
```

### 4.2 Vocabulary

| Term | Meaning | Replaces |
|---|---|---|
| **Account** | A way to authenticate to Mixpanel. Has a `name`, a `type` (one of three), and a `region`. SA accounts have `username`+`secret`. OAuth-browser accounts manage tokens on disk. OAuth-token accounts hold a static bearer (in env or config). | v1 "account", v2 "credential" |
| **Project** | A Mixpanel project. Identified by Mixpanel's numeric `project_id`. Has a `name`, `organization_id`, `timezone`. | v1's project_id-as-config-field, v2 "project alias" |
| **Workspace** | A workspace within a project. Identified by Mixpanel's numeric `workspace_id`. Optional — if unset, App-API operations auto-resolve to the project's default workspace. | unchanged |
| **Session** | The triple `(Account, Project, Workspace?)`. The thing the API client needs to make a request. | v2 "ResolvedSession", v1 "Credentials" |
| **Active session** | The persisted session in `~/.mp/config.toml` `[active]`. | v1 "default", v2 "active context" |
| **Target** | An optional named shortcut for a `(Account, Project, Workspace?)` triple. Captures a saved-cursor-position you return to often. | v2 "project alias" |

### 4.3 Verbs

| Verb | Meaning |
|---|---|
| `add` | Register a new account or target |
| `remove` | Delete an account or target |
| `list` | Show all of a thing |
| `show` | Show details of one thing (or current state) |
| `use` | Set the active account / project / workspace / target |
| `test` | Verify an account's credentials work |
| `login` | Run the OAuth browser flow for an account |
| `logout` | Discard OAuth tokens for an account |
| `discover` | Hit `/me` to find available projects/workspaces (Python only; CLI says `list` with `--remote`) |

**Crucially:** `use` is the only verb for changing state. `switch`, `default`,
`set-active`, and `set-default` are all eliminated.

---

## 5. Configuration Schema

### 5.1 The schema

```toml
# ~/.mp/config.toml
# No config_version field. There is only one schema.

[active]
account   = "demo-sa"
project   = "3713224"      # numeric Mixpanel project ID
workspace = 3448413        # numeric Mixpanel workspace ID; optional

[accounts.demo-sa]
type     = "service_account"
region   = "us"
username = "jared-mp-demo.292e7c.mp-service-account"
secret   = "aQUXhKokwLywLoxE3AxLt0g9dXC2G7bT"

[accounts.p8-sa]
type     = "service_account"
region   = "us"
username = "jared-mp.19df54.mp-service-account"
secret   = "owbi8v1n9YD9RcQVN4duRjgJgvhoZ100"

[accounts.personal]
type   = "oauth_browser"
region = "us"
# Tokens stored in ~/.mp/accounts/personal/tokens.json
# Client info stored in ~/.mp/accounts/personal/client.json

[accounts.ci]
type      = "oauth_token"
region    = "us"
token_env = "MP_CI_TOKEN"       # OR (mutually exclusive)
# token   = "<inline-bearer>"    # if not pulling from env

[targets.ecom]
account   = "demo-sa"
project   = "3018488"
workspace = 3448414

[targets.production]
account = "personal"
project = "8"
# workspace omitted → resolves to the project's default workspace on demand

[settings]
# Optional global request-level settings.
custom_header = { name = "X-Mixpanel-Cluster", value = "internal-1" }
```

### 5.2 Schema invariants

- Every `[accounts.X]` block has `type` and `region`. The remaining required
  fields depend on `type`.
- For `type = "oauth_browser"`, no secret material lives in the TOML file.
  Tokens live at `~/.mp/accounts/{name}/tokens.json` (0o600).
- For `type = "oauth_token"`, exactly one of `token` or `token_env` is set.
  If `token_env`, the env variable is consulted at resolution time and may be
  absent (in which case the account is invalid until the user sets it).
- `[active].account` must reference an existing account, OR be absent (in
  which case env vars must supply auth).
- `[active].project` is a string (Mixpanel project IDs are numeric strings).
- `[active].workspace` is an integer (Mixpanel workspace IDs are integers).
- `[targets.X]` requires `account` and `project`. `workspace` is optional.
- No config version field. The presence of any `[accounts]` block and the
  absence of any v1-shaped fields is the schema.

### 5.3 What this is NOT

- Not multi-environment. There's exactly one config per machine. (Power users
  can use `MP_CONFIG_PATH` to point elsewhere.)
- Not a DCR (Dynamic Client Registration) cache. OAuth client info still lives
  beside the tokens on disk.
- Not a `/me` cache. That stays beside tokens on disk too.

---

## 6. Type System

### 6.1 The `Account` type (discriminated union)

```python
# src/mixpanel_data/_internal/auth/account.py

from __future__ import annotations

import base64
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


Region = Literal["us", "eu", "in"]


class _AccountBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    region: Region

    def auth_header(self, *, token_resolver: TokenResolver | None = None) -> str: ...
    def is_long_lived(self) -> bool: ...


class ServiceAccount(_AccountBase):
    type: Literal["service_account"] = "service_account"
    username: str
    secret: SecretStr

    def auth_header(self, *, token_resolver=None) -> str:
        raw = f"{self.username}:{self.secret.get_secret_value()}"
        encoded = base64.b64encode(raw.encode()).decode("ascii")
        return f"Basic {encoded}"

    def is_long_lived(self) -> bool:
        return True


class OAuthBrowserAccount(_AccountBase):
    """OAuth via PKCE browser flow. Tokens stored on disk and refreshed
    automatically. The Account itself carries no secret — secrets are
    looked up by name from on-disk storage at request time."""
    type: Literal["oauth_browser"] = "oauth_browser"

    def auth_header(self, *, token_resolver) -> str:
        token = token_resolver.get_browser_token(self.name, self.region)
        return f"Bearer {token}"

    def is_long_lived(self) -> bool:
        return True   # refresh-token-driven


class OAuthTokenAccount(_AccountBase):
    """Static OAuth bearer (CI, agents, ephemeral environments).
    Either inline `token` or `token_env` must be set; never both."""
    type: Literal["oauth_token"] = "oauth_token"
    token: SecretStr | None = None
    token_env: str | None = None

    def auth_header(self, *, token_resolver) -> str:
        token = token_resolver.get_static_token(self)
        return f"Bearer {token}"

    def is_long_lived(self) -> bool:
        return False  # caller-controlled; no refresh


Account = Annotated[
    ServiceAccount | OAuthBrowserAccount | OAuthTokenAccount,
    Field(discriminator="type"),
]
```

### 6.2 Project, WorkspaceRef, Session

> **Naming note.** The facade class is `mixpanel_data.Workspace` (the
> primary entry point that orchestrates discovery + queries). To avoid a name
> collision, the **data model** for "a workspace inside a project" is
> `WorkspaceRef`. This mirrors the existing precedent (the v2 design has both
> `MeWorkspaceInfo` and `PublicWorkspace` data types alongside the `Workspace`
> facade).

```python
# src/mixpanel_data/_internal/auth/session.py

from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, PositiveInt


class Project(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: Annotated[str, Field(min_length=1)]
    name: str | None = None
    organization_id: int | None = None


class WorkspaceRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: PositiveInt
    name: str | None = None


class Session(BaseModel):
    """The fully-resolved triple consumed by MixpanelAPIClient.

    `workspace` is `None` until the first workspace-scoped App API call is
    made, at which point it is auto-resolved to the project's default workspace
    and cached on the API client (NOT mutated on this frozen Session — the
    cache lives one level down on the client instance). This keeps Session
    construction cheap (no API call) while guaranteeing every project has a
    usable workspace, since Mixpanel always creates a default "All Project Data"
    workspace at project creation time. See §13.2.
    """
    model_config = ConfigDict(frozen=True)
    account: Account
    project: Project
    workspace: WorkspaceRef | None = None

    @property
    def project_id(self) -> str:
        return self.project.id

    @property
    def workspace_id(self) -> int | None:
        return self.workspace.id if self.workspace else None

    @property
    def region(self) -> Region:
        return self.account.region

    def auth_header(self, *, token_resolver) -> str:
        return self.account.auth_header(token_resolver=token_resolver)
```

### 6.3 What gets deleted

| Old type | Replacement | Notes |
|---|---|---|
| `Credentials` (config.py) | `Session` | The single project-bundled struct is gone |
| `AuthMethod` enum | `Account.type` discriminator | Strings via Literal |
| `AccountInfo` dataclass | `AccountSummary` | Same purpose, new shape (no `project_id` field) |
| `CredentialInfo` dataclass | `AccountSummary` | Merged with above |
| `AuthCredential` (auth_credential.py) | `Account` union | The discriminated union replaces the validator-soup model |
| `CredentialType` enum | `Account.type` discriminator | Same idea |
| `ProjectContext` (auth_credential.py) | `Project` + `WorkspaceRef` | Split apart; no more "context" wrapper |
| `ResolvedSession` | `Session` | Renamed for brevity; same role |
| `ProjectAlias` dataclass | `Target` | Renamed; same shape |
| `MigrationResult` dataclass | (deleted) | No migrations |
| `ActiveContext` dataclass | `ActiveSession` | Renamed for clarity |

---

## 7. Credential Resolution

### 7.1 The single resolver

There is one function. It is the only way to obtain a `Session` from
configuration.

```python
def resolve_session(
    *,
    account: str | None = None,
    project: str | None = None,
    workspace: int | None = None,
    target: str | None = None,
    config: ConfigManager | None = None,
) -> Session:
    """Resolve the active Session.

    Resolution order (first match wins for each axis independently).
    Env vars always win over config (CI/agent escape hatch).

    Account axis:
        1. MP_USERNAME+MP_SECRET+MP_REGION (synthetic ephemeral SA account)
        2. MP_OAUTH_TOKEN+MP_REGION (synthetic ephemeral OAuthToken account)
        3. `account` parameter (must reference [accounts.X])
        4. `target` parameter resolves to a target's account
        5. Bridge file (Cowork only — see §14)
        6. config [active].account

    Project axis:
        1. MP_PROJECT_ID env
        2. `project` parameter
        3. `target` parameter (after account axis resolves)
        4. Bridge file
        5. config [active].project

    Workspace axis (optional in the resolved Session, lazy-resolved on demand):
        1. MP_WORKSPACE_ID env
        2. `workspace` parameter
        3. `target` parameter
        4. Bridge file
        5. config [active].workspace
        6. None — left unresolved; lazy auto-resolves to the project's
           default workspace on the first workspace-scoped App API call.

    Raises:
        ConfigError: if Account or Project cannot be resolved.
        WorkspaceScopeError: only at Workspace-API call time, not here.
    """
```

### 7.2 What changed vs today

- **Independent axes.** Account, project, and workspace each resolve through
  their own ordered list. There is no "if account is set, skip OAuth" or "OAuth
  takes priority over config". Each axis is independent.
- **Env vars always win.** `MP_*` env vars sit at the top of every axis. This
  preserves the CI/agent escape hatch: if you set the env, you get the env,
  no matter what's in the config file. (Behavioral parity with PR #125.)
- **No multi-layer fallbacks for OAuth project.** OAuth tokens no longer carry
  a `project_id`. The project comes from CLI/env/config like everything else.
- **Env vars are credential records, not exceptions.** `MP_USERNAME`+`MP_SECRET`
  is treated as a synthetic, in-memory `ServiceAccount` named `"<env>"`.
  `MP_OAUTH_TOKEN` is a synthetic `OAuthTokenAccount` named `"<env>"`. They
  flow through the same code path as named accounts.
- **No "first available" fallbacks.** If no account is resolved, raise
  `ConfigError` with explicit instructions. Never silently pick a random
  account.
- **Workspace axis can resolve to None.** Unlike the other two axes,
  `workspace = None` is a valid Session — it means "use the project's default
  workspace, lazy-resolved on demand". See §13.2 for the rationale.
- **`account` and `target` are mutually exclusive at the input level.** If
  both are passed, raise `ValueError` immediately.

### 7.3 Resolution invariants

- The same inputs always produce the same `Session`. No environment-dependent
  surprises.
- The resolver does not read OAuth tokens, validate connectivity, or fetch
  `/me`. Those are post-resolution concerns. Resolution is pure config + env
  reading.
- The resolver doesn't mutate the environment. (Today
  `apply_config_custom_header` mutates `os.environ` — gone.)

### 7.4 Error messages

Each failure must say what's wrong AND what to do:

```text
ConfigError: No account configured.

Configure one of:
  • Service account:  mp account add <name>
  • OAuth (browser):  mp account login <name>
  • OAuth (token):    mp account add <name> --token-env MY_TOKEN
  • Env vars:         export MP_USERNAME=... MP_SECRET=... MP_REGION=...
                  OR: export MP_OAUTH_TOKEN=... MP_REGION=...
```

```text
ConfigError: No project selected.

Run `mp project list` to see available projects, then
`mp project use <id>` to select one.
```

---

## 8. Filesystem Layout

```
~/.mp/
├── config.toml                          # main config (0o600)
└── accounts/
    ├── demo-sa/                         # only created if account has on-disk artifacts
    │   └── (empty for SA — no on-disk state)
    ├── personal/                        # OAuth browser
    │   ├── tokens.json                  # access + refresh + expires_at (0o600)
    │   ├── client.json                  # DCR client_id (0o600)
    │   └── me.json                      # cached /me response (0o600)
    └── ci/                              # OAuth token (env-backed)
        └── (empty — secret is in env, /me cache optional)
```

### Notes

- One directory per account. Predictable. No region-scoped collisions.
- The `accounts/` parent dir replaces `oauth/`. The new name reflects what's
  inside: account-scoped state (not just OAuth).
- Service accounts get an empty directory only if there's something to store
  (currently nothing, but preserves room for `me.json` cache later).
- The Cowork bridge file path (`~/.claude/mixpanel/auth.json`) is unchanged.

---

## 9. Python Public API

### 9.1 Top-level imports

```python
import mixpanel_data as mp

# Construction
ws = mp.Workspace()                                      # use [active]
ws = mp.Workspace(account="demo-sa")                     # override account
ws = mp.Workspace(project="3713224")                     # override project
ws = mp.Workspace(account="demo-sa", project="3713224")  # override both
ws = mp.Workspace(target="ecom")                         # use a target
ws = mp.Workspace(session=my_session)                    # full bypass

# Inspect current state
ws.account        # → ServiceAccount(...) | OAuthBrowserAccount(...) | OAuthTokenAccount(...)
ws.project        # → Project(id="3713224", name="AI Demo", organization_id=12)
ws.workspace      # → WorkspaceRef(id=3448413, name="Default") | None
ws.session        # → Session(...)

# Switch in-session (no config write)
ws.use(account="other-sa")
ws.use(project="3018488")
ws.use(workspace=3448414)
ws.use(target="production")
ws.use(account="personal", project="8")  # multiple at once

# Discovery
projects = ws.projects()             # all accessible projects via /me, cached
workspaces = ws.workspaces()         # workspaces in current project
all_workspaces = ws.workspaces(project_all=True)  # cross-project
me = ws.me()                          # raw /me response

# Configuration management (mutates ~/.mp/config.toml)
mp.accounts.list()
mp.accounts.add("ci", type="oauth_token", region="us", token_env="MY_TOKEN")
mp.accounts.remove("ci")
mp.accounts.use("demo-sa")            # set [active].account
mp.accounts.test("demo-sa")           # ping /me

mp.targets.list()
mp.targets.add("ecom", account="demo-sa", project="3018488")
mp.targets.use("ecom")                # writes [active] from target

mp.session.show()                     # current [active]
mp.session.use(account=..., project=..., workspace=...)
```

### 9.2 The `Workspace.use()` method

This is the centerpiece of the cross-cutting switching story.

```python
def use(
    self,
    *,
    account: str | None = None,
    project: str | None = None,
    workspace: int | None = None,
    target: str | None = None,
    persist: bool = False,
) -> Self:
    """Switch the active session in this Workspace instance.

    Returns self for chaining: `ws.use(project="3").events()`

    Args:
        account: New account name. Re-authenticates (cheap — same auth method
                 lookup, new auth header). Implicitly resets project unless
                 `project` is also provided.
        project: New project ID. Cheaper than account change — no re-auth.
        workspace: New workspace ID within the current project.
        target: Apply all three from a target definition. Mutually exclusive
                with account/project/workspace.
        persist: If True, also write to ~/.mp/config.toml [active].

    Raises:
        ValueError: if `target` is combined with account/project/workspace.
        ConfigError: if account/target doesn't exist.
        AccountAccessError: if the account can't access the requested project
                            (only checked if discovery cache is populated).
    """
```

**Switching cost contract:**

| Switch | Cost |
|---|---|
| `ws.use(workspace=N)` | One in-memory field update |
| `ws.use(project=P)` | New API client (shared HTTP transport) |
| `ws.use(account=A)` | Re-resolve account; new auth header; clear caches |
| `ws.use(target=P)` | Same as the most-expensive of the above |

The HTTP `httpx.Client` instance is **always** preserved across switches. Only
auth headers and base-URL parameters change.

### 9.3 What's removed from `Workspace`

| Removed | Why |
|---|---|
| `set_workspace_id(N)` | Use `ws.use(workspace=N)` |
| `switch_project(p, w)` | Use `ws.use(project=p, workspace=w)` |
| `switch_workspace(N)` | Use `ws.use(workspace=N)` |
| `discover_projects()` | Renamed to `projects()` (parallel to `events()`) |
| `discover_workspaces()` | Renamed to `workspaces()` |
| `current_project` property | Use `ws.project` |
| `current_credential` property | Use `ws.account` |
| `workspace_id` property | Use `ws.workspace.id if ws.workspace else None` |
| `resolve_workspace_id()` | Internal — auto-resolves on first App API call, exposed via property |
| `test_credentials(account)` static method | Use `mp.accounts.test(name)` |
| `Workspace.open()` (if it exists?) | Always require resolved session |

### 9.4 The `mp.accounts`, `mp.targets`, `mp.session` namespaces

These replace the public `auth` module's `ConfigManager` surface. The
`ConfigManager` class becomes an internal implementation detail.

```python
# Public — clean, focused namespaces
import mixpanel_data as mp

mp.accounts.list()           → list[AccountSummary]
mp.accounts.add(...)         → None
mp.accounts.remove(name)     → list[str]   # orphaned target names
mp.accounts.use(name)        → None        # writes [active].account
mp.accounts.show(name)       → AccountSummary
mp.accounts.test(name)       → AccountTestResult
mp.accounts.login(name)      → OAuthLoginResult  # PKCE flow
mp.accounts.logout(name)     → None

mp.targets.list()            → list[Target]
mp.targets.add(...)          → None
mp.targets.remove(name)      → None
mp.targets.use(name)         → None
mp.targets.show(name)        → Target

mp.session.show()            → ActiveSession
mp.session.use(...)          → None
```

The internal `ConfigManager` still exists for testing/DI but is `_internal`.

---

## 10. CLI Surface

### 10.1 Command tree

```
mp account
  list                          List configured accounts
  add NAME --type TYPE [--region us|eu|in] ...
  remove NAME [--force]
  use NAME                      Set the active account
  show [NAME]                   Show account details (active if NAME omitted)
  test [NAME]                   Hit /me to verify
  login [NAME]                  Run the OAuth PKCE browser flow
  logout [NAME]                 Discard OAuth tokens

mp project
  list [--remote]               List from local config OR from /me
  use ID                        Set the active project
  show                          Show the active project

mp workspace
  list [--project ID]           List workspaces in current/given project
  use ID                        Set the active workspace
  show                          Show the active workspace

mp target
  list                          List configured targets
  add NAME --project ID [--account NAME] [--workspace ID]
  remove NAME [--force]
  use NAME                      Apply a target (sets active.account/project/workspace)
  show NAME

mp session                      Show the active session (account+project+workspace)

mp <other commands>             # all use the active session by default
```

### 10.2 Global flags (apply to every command)

| Flag | Env var | Purpose |
|---|---|---|
| `--account NAME` / `-a` | `MP_ACCOUNT` | Override account for this command |
| `--project ID` / `-p` | `MP_PROJECT_ID` | Override project for this command |
| `--workspace ID` / `-w` | `MP_WORKSPACE_ID` | Override workspace for this command |
| `--target NAME` | `MP_TARGET` | Apply a target for this command |

`--target` is mutually exclusive with `--account`/`--project`/`--workspace`.

### 10.3 Verbs that no longer exist

| Old verb | Why removed | Replacement |
|---|---|---|
| `mp auth` (group) | Conflated identity + project + setup | `mp account` |
| `mp auth switch` | Ambiguous (changes default) | `mp account use` |
| `mp auth migrate` | No more v1 → no migration | (deleted) |
| `mp auth cowork-setup` | Move to `mp account export-bridge` | `mp account export-bridge --to PATH` |
| `mp auth cowork-teardown` | Move to `mp account remove-bridge` | `mp account remove-bridge [--at PATH]` |
| `mp auth cowork-status` | Move to `mp session --bridge` | `mp session --bridge` |
| `mp projects switch` | "switch" overload | `mp project use` |
| `mp projects refresh` | One-off — fold into `mp project list --refresh` | `mp project list --refresh` |
| `mp workspaces switch` | "switch" overload | `mp workspace use` |
| `mp context show` | Redundant w/ `mp session` | `mp session` |
| `mp context switch` | Only worked on aliases | `mp target use` |

### 10.4 `mp account add` flows

The single command handles all three account types via `--type`:

```bash
# Service account (interactive secret prompt)
mp account add demo-sa --type service_account --username "..." --region us
# (prompts for secret; or read from MP_SECRET env / --secret-stdin)

# OAuth (browser) — registration only; tokens come from `mp account login`
mp account add personal --type oauth_browser --region us

# OAuth (static bearer)
mp account add ci --type oauth_token --token-env MP_CI_TOKEN --region us
mp account add ci --type oauth_token --token "ey..." --region us  # discouraged
```

After adding, the account is *not* automatically active. The first account
added becomes active automatically (sensible default for fresh installs).

### 10.5 Bootstrap UX (fresh install)

The user types `mp account list` on a fresh machine and sees:

```text
No accounts configured.

To get started:
  • OAuth (recommended):    mp account add personal --type oauth_browser
                            mp account login personal
  • Service account:         mp account add team --type service_account --username "..."
  • Static bearer (CI):      export MP_OAUTH_TOKEN=... MP_REGION=us MP_PROJECT_ID=...

Then:
  • mp project list          (discover available projects)
  • mp project use <id>      (select one)
```

### 10.6 Onboarding success path (hand-walked)

```bash
$ mp account add personal --type oauth_browser --region us
Added account 'personal' (oauth_browser, us). Set as active.

$ mp account login personal
Opening browser...
✓ Authenticated as jared@example.com

$ mp project list
ID        NAME              ORG       WORKSPACES
3713224   AI Demo           Acme      ✓
3018488   E-Commerce Demo   Acme      ✓
8         P8                Acme      ✓

$ mp project use 3713224
Active project: AI Demo (3713224)

$ mp workspace list
ID        NAME       DEFAULT
3448413   Default    ★
3448414   Staging

$ mp workspace use 3448413
Active workspace: Default (3448413)

$ mp session
Account:   personal (oauth_browser, us)
Project:   AI Demo (3713224)
Workspace: Default (3448413)
User:      jared@example.com
```

### 10.7 Power-user target workflow

```bash
$ mp target add ecom --account demo-sa --project 3018488
Added target 'ecom' → demo-sa/3018488

$ mp target add prod --account personal --project 8
Added target 'prod' → personal/8

$ mp target use ecom
Active: demo-sa → E-Commerce Demo (3018488)

$ mp target use prod
Active: personal → P8 (8)

$ mp --target ecom query segmentation -e Login --from 2026-04-01
# (one-off override without changing active session)
```

---

## 11. Plugin / Agent Surface

### 11.1 `auth_manager.py` (rewrite)

The current 727-line `auth_manager.py` collapses to ~250 lines because there
are no v1/v2 conditionals. Subcommands map 1:1 to CLI verbs:

```
python auth_manager.py session                   # session info as JSON
python auth_manager.py account list              # list accounts
python auth_manager.py account add <name> ...    # via JSON stdin for safety
python auth_manager.py account use <name>
python auth_manager.py account login <name>
python auth_manager.py account test <name>
python auth_manager.py project list [--remote]
python auth_manager.py project use <id>
python auth_manager.py workspace list
python auth_manager.py workspace use <id>
python auth_manager.py target list/add/use
python auth_manager.py bridge status
```

Every command outputs structured JSON with a stable shape. No version branches.

### 11.2 `/mixpanel-data:auth` slash command

The slash command (`mixpanel-plugin/commands/auth.md`) gets a substantial
trim — no v1/v2 conditional branches in routing. The existing security rule
("never ask for secrets in conversation") stays as-is.

The status-check workflow becomes:

1. `python auth_manager.py session` → returns one of three states:
   - `{"state": "ok", "account": {...}, "project": {...}, "workspace": {...}}`
   - `{"state": "needs_account", "next": [...suggested CLI commands...]}`
   - `{"state": "needs_project", "next": [...]}`
2. Plugin presents a 1-2 line summary and a single suggested next action.

### 11.3 Setup skill (`/mixpanel-data:setup`)

Setup verifies:
- `mixpanel_data` is installed
- `mp account list` runs
- If empty, walks the user through `mp account add` → `mp account login` →
  `mp project list` → `mp project use <id>`.

There is no migration step. Fresh installs are valid v3 configs from the
first command.

---

## 12. Cross-Account / Cross-Project / Cross-Workspace Switching

This is the **unique capability** the user called out. The redesign elevates
it to a first-class operation at every layer.

### 12.1 The promise

| Operation | Cost | One-line example |
|---|---|---|
| Loop over all my projects (one account) | One auth header lookup, N calls | `for p in ws.projects(): ws.use(project=p.id); ws.events()` |
| Loop over all my accounts | N auth lookups, M*N calls | `for a in mp.accounts.list(): ws = mp.Workspace(account=a.name); ...` |
| Cross-org analysis (one OAuth identity) | Trivially | `for p in ws.projects(): ws.use(project=p.id); ...` |
| Compare same query across two projects | Two clients, shared HTTP transport | `r1 = ws.use(project=A).segmentation(...); r2 = ws.use(project=B).segmentation(...)` |
| Quick A/B between credential types | One config write or none | `mp.accounts.use("demo-sa")` or `Workspace(account="demo-sa")` |

### 12.2 Concurrency

The current `Workspace` is single-context. Cross-cutting analysis has two
modes:

**Sequential mode** (default, mutates `self.session`):

```python
ws = mp.Workspace()
for p_id, info in ws.projects():
    ws.use(project=p_id)
    print(p_id, info.name, len(ws.events()))
```

**Snapshot mode** (immutable, parallel-safe):

```python
ws = mp.Workspace()
sessions = [ws.session.replace(project=Project(id=p_id))
            for p_id, _ in ws.projects()]

# Each Workspace is independent — safe for ThreadPoolExecutor / asyncio
with ThreadPoolExecutor() as pool:
    results = pool.map(lambda s: mp.Workspace(session=s).events(), sessions)
```

The `Session.replace(...)` Pydantic-style copier makes parallel iteration safe.
This is the new escape hatch for ETL-style cross-project workloads.

### 12.3 CLI cross-cutting

```bash
# One command across all projects via xargs:
mp project list -f jsonl | jq -r .id | \
  xargs -I{} mp --project {} query segmentation -e Login --from 2026-04-01
```

The CLI's per-command `--project` / `--account` / `--workspace` flags compose
naturally with shell loops.

### 12.4 The target pattern for power users

Targets are not aliases-for-projects (the v2 framing). They are
*saved-cursor-positions* — a snapshot of `(account, project, workspace)` you
return to often:

```bash
mp target add prod-events  --account demo-sa  --project 3713224 --workspace 3448413
mp target add staging-flag --account personal --project 8       --workspace 3448414
mp target use prod-events     # one command sets all three
```

---

## 13. Discovery & The `/me` Endpoint

### 13.1 What stays the same

- `/me` is the source of truth for "what can this account access?"
- Cached on disk per-account (`~/.mp/accounts/{name}/me.json`) with 24h TTL.
- Forward-compatible Pydantic models with `extra="allow"`.
- `MeService` orchestrates fetch+cache+invalidate.

### 13.2 Workspace optionality (evidence-based decision)

A second research pass through the official Mixpanel source
(`/Users/jaredmcfarland/Developer/analytics`) established the following facts:

- **Every project is born with a default workspace.** `webapp/project/utils.py:271`
  calls `create_all_projects_data_view` which creates a workspace named
  *"All Project Data"* with `is_default=True`, `is_global=True`,
  `is_visible=True` (lines 167–175). There is no path that produces a project
  without a workspace.
- **`/api/app/projects/{pid}/workspaces/public` never returns empty.** The
  default workspace is always present and visible.
- **Most App API endpoints are project-scoped, not workspace-scoped.**
  `webapp/app_api/projects/urls.py` shows `dashboards`, `cohorts`,
  `custom_properties`, `annotations`, `bookmarks`, `analysis`, `experiments`,
  `feature-flags` (project-level form), and `data-definitions` all live at
  `/api/app/projects/{pid}/...`. Workspace-scoped endpoints are the minority
  (events-by-workspace, alerts, some feature-flag operations).
- **The `/me` `has_workspaces` field is misleadingly named.** It means "has
  more than one active workspace" (`me/utils.py:149`:
  `project.workspace_set.filter_active().count() > 1`). A fresh project with
  only the default workspace returns `has_workspaces = False` — but it still
  has one workspace.

**Conclusion:** `Session.workspace` stays **optional in the type**, but with a
guarantee that **lazy resolution always succeeds**. The `MixpanelAPIClient`
auto-discovers and caches the default workspace on the first workspace-scoped
call. Construction of a Session is cheap (no network call). Workspace-scoped
calls are guaranteed to find a usable workspace.

This is *strictly better* than always-required:

- Always-required would force every Session construction to hit
  `/projects/{pid}/workspaces/public` (or `/me`) to get the default workspace
  ID — adds latency to every login, every CLI invocation, every `Workspace()`.
- Always-required would also poison cross-project iteration: switching projects
  would require fetching the new project's default workspace before any call
  could be made.
- Always-optional with lazy auto-resolution gives the same effective behavior
  without the upfront cost.

### 13.3 What changes

| Before | After |
|---|---|
| `MeCache(credential_name="demo-sa")` with optional scoping | Always per-account; the path is derived from the account name |
| Cache file at `~/.mp/oauth/me_us_demo-sa.json` | Cache file at `~/.mp/accounts/demo-sa/me.json` |
| `Workspace.discover_projects()` returns `list[tuple[str, MeProjectInfo]]` | `Workspace.projects()` returns `list[Project]` (the public type, with project_id, name, org) |
| `MeService` instantiated lazily inside `Workspace` | `MeService` is the public `mp.discovery` namespace |
| Fallback to "scan all OAuth tokens" when no project resolved | Removed — caller must specify an account |
| `MixpanelAPIClient.resolve_workspace_id()` consults `/projects/{pid}/workspaces/public` | Same, but cache the result on the client instance for the session lifetime |

### 13.4 SA accounts and `/me`

Service accounts CAN call `/me` (verified in the v2 design doc against Django
source). The new design uses the same code path for all account types — the
only difference is what the response contains (SA-bound projects vs OAuth-bound
projects).

### 13.5 Project discovery for unconfigured users

`mp project list` should work even before the user has selected a project.
The current code has a fallback (`_discover_projects_via_oauth` in
`projects.py:78-177`) that hits `/me` directly with a stored OAuth token. The
new design preserves this fallback, but as a generic "use any usable account"
strategy:

1. Resolve account axis normally.
2. Hit `/me` (no project_id required for this endpoint).
3. Display results.

If no account can be resolved, the error is the standard "no account
configured" message.

---

## 14. Cowork Bridge Files

### 14.1 What stays

- The bridge file (`~/.claude/mixpanel/auth.json` or
  `mixpanel_auth.json` in workspace root) remains the credential courier
  between host and Cowork VM.
- OAuth refresh tokens included, so the VM can renew expired access tokens
  without browser access.
- `MP_AUTH_FILE` env override stays.

### 14.2 What changes

| Before | After |
|---|---|
| Bridge embeds `project_id`, `workspace_id` | Bridge embeds *optional* `project` + `workspace` defaults; not required |
| Bridge embeds `auth_method` discriminator + nested oauth/sa sections | Bridge embeds an `Account` (full discriminated union) + optional `project` + optional `workspace` |
| Bridge custom_header is a separate field | Same |
| `mp auth cowork-setup/teardown/status` | `mp account export-bridge` / `mp account remove-bridge` / `mp session --bridge` |
| Apply custom headers via `os.environ` mutation | Account carries headers in its own model; no env mutation |

### 14.3 Bridge schema (new)

```json
{
  "version": 2,
  "account": {
    "type": "oauth_browser",
    "name": "personal",
    "region": "us",
    "tokens": {
      "access_token": "...",
      "refresh_token": "...",
      "expires_at": "2026-04-22T12:00:00Z",
      "client_id": "...",
      "scope": "..."
    }
  },
  "project": "3713224",
  "workspace": 3448413,
  "headers": {
    "X-Mixpanel-Cluster": "internal-1"
  }
}
```

The `account` field is the full account record (with secrets inline). The
`tokens` sub-object is only present for `oauth_browser` accounts.

### 14.4 Loading

In Cowork (or whenever `MP_AUTH_FILE` is set), the bridge is consulted by the
resolver as a synthetic config source:

- `account` axis: synthesize an in-memory account named `bridge`
- `project` axis: use bridge `project` if present, else fall through to env/config
- `workspace` axis: same
- `headers`: applied per-account, no env mutation

This makes the bridge fully isomorphic to a config file — same code path.

---

## 15. Tech Debt to Remove

This is the explicit "what to delete" list.

### 15.1 Files to delete entirely

- `src/mixpanel_data/_internal/auth_credential.py` (replaced by
  `_internal/auth/account.py` + `_internal/auth/session.py`)
- v1 paths inside `config.py` (the file shrinks from 1,937 lines to ~600)
- Migration code (`migrate_v1_to_v2`, `MigrationResult`, the `mp auth migrate`
  command)
- Cowork-specific CLI commands (folded into `mp account export-bridge`)
- The plugin's v1 status branches in `auth_manager.py`

### 15.2 Concepts to delete

- `config_version` field — there is one schema
- `default = "X"` field — replaced by `[active].account`
- v1 `[accounts.X]` blocks — replaced by `[accounts.X]` with new shape
  (note: same TOML key, different shape — clean break)
- `AuthMethod` enum (v1)
- `CredentialType` enum (v2) — the discriminator is the type field directly
- `AuthCredential` model (v2)
- `ProjectContext` model (v2)
- `ResolvedSession` model (v2) — renamed to `Session`
- `Credentials.from_oauth_token` factory — `OAuthTokenAccount` constructor replaces it
- `Workspace.test_credentials` static method — moved to `mp.accounts.test`
- The `Workspace._session_to_credentials` bridge method (no longer needed)
- The `MixpanelAPIClient.with_project` factory (replaced by simpler
  `MixpanelAPIClient.use(project=...)` mutation, since no `Credentials` to
  rebuild)
- The six-layer fallback in `_resolve_region_and_project_for_oauth`

### 15.3 What survives unchanged

- The `OAuthFlow` / PKCE / DCR machinery (`flow.py`, `pkce.py`,
  `client_registration.py`, `callback_server.py`) — only the storage paths change
- The `OAuthTokens` / `OAuthClientInfo` models in `token.py` — minor change:
  drop the `project_id` field
- The `MeResponse` / `MeProjectInfo` / `MeWorkspaceInfo` / `MeOrgInfo` models
  in `me.py`
- The `MeCache` and `MeService` (storage path changes; behavior unchanged)
- All exception types (`AuthenticationError`, `OAuthError`, `ConfigError`, etc.)
- All API endpoint URLs and request signing logic in `api_client.py`

### 15.4 Estimated LOC impact

Current: ~7,200 LOC across 15 files (auth subsystem).
Target:   ~3,500 LOC across 12 files. (~50% reduction.)

The delta comes from deleting v1 paths and the v1↔v2 bridge — not from cutting
features.

---

## 16. Implementation Phases

### Phase 0: Documentation review & approval

- Review this doc.
- Final review of vocabulary, schema, and method names. (Once these are baked
  in, changing them is expensive across CLI + Python + plugin.) — All eight
  open questions answered (see §18).

### Phase 1: New types (no behavior change)

- Add `_internal/auth/account.py` with the `Account` discriminated union.
- Add `_internal/auth/session.py` with `Project`, `Workspace`, `Session`.
- Property-based tests for round-trip serialization.
- All existing code continues to work.

### Phase 2: New resolver + ConfigManager

- Implement the single `resolve_session()` (described in §7).
- New `ConfigManager` methods: `add_account`, `list_accounts`, etc. with the
  new schema shape.
- Reject configs without the new shape (no `config_version` check — the new
  resolver simply doesn't understand v1 blocks).
- Parallel: implement a one-shot conversion script (`scripts/convert_legacy_config.py`)
  for the alpha testers — runs once, writes new config, archives old config to
  `~/.mp/config.toml.legacy`. This is *not* a runtime migration; it's a
  one-time tool.

### Phase 3: Rewire API client and Workspace

- `MixpanelAPIClient.__init__` takes `Session`, not `Credentials`.
- Delete `Credentials` and `_session_to_credentials`.
- `Workspace.__init__` accepts `account`/`project`/`workspace`/`target`/`session`
  parameters and resolves through the single resolver.
- Implement `Workspace.use()` for in-session switching.
- Update OAuth flow's storage path conventions (`oauth/` → `accounts/{name}/`).

### Phase 4: CLI rewrite

- New command groups: `mp account`, `mp project`, `mp workspace`, `mp target`,
  `mp session`. Each is a thin wrapper around `mp.accounts` / `mp.targets` /
  `mp.session` Python APIs.
- Delete `mp auth` (group), `mp context`, `mp projects` (plural), `mp workspaces`
  (plural).
- Update global flag set.

### Phase 5: Plugin rewrite

- New `auth_manager.py` (no version branches, ~250 lines).
- Update `/mixpanel-data:auth` command and skills accordingly.
- Update README and getting-started docs.

### Phase 6: Cowork bridge update

- New bridge schema (v2 — first real version, since v1 was unversioned).
- New `mp account export-bridge` / `remove-bridge` commands.
- Update `bridge.py` to produce/consume new shape.

### Phase 7: Documentation

- Update `CLAUDE.md` (project), `src/mixpanel_data/CLAUDE.md`,
  `src/mixpanel_data/cli/CLAUDE.md`.
- Update `context/mixpanel_data-design.md`.
- Update `mixpanel-plugin/README.md` and getting-started guides.
- Archive the v2 design doc with a note pointing to this redesign.

### Phase 8: Migration script + announcement

- Run conversion script against `~/.mp/config.toml` for each alpha tester,
  manually if needed (handful of users).
- Bump major version (`mixpanel_data 0.4.0`, plugin `5.0.0`).
- Release notes call out the breaking change explicitly.

---

## 17. Test Strategy

### 17.1 What to delete

- All v1 ↔ v2 round-trip tests
- Migration tests (`tests/unit/test_config_v2.py` migration cases)
- `test_workspace_oauth.py` cases that assert v1 behavior

### 17.2 What to keep

- OAuth PKCE flow tests (`test_auth_flow.py`, `test_auth_pkce.py`)
- DCR tests (`test_auth_registration.py`)
- Token storage tests (`test_auth_storage.py`) — adapted for new path layout
- Bridge file tests (`test_auth_bridge.py`) — adapted for new schema
- `MeCache` tests (`test_me.py` if exists, else new)

### 17.3 New test surface

- **Resolver invariants** (Hypothesis): for any valid input set, `resolve_session`
  is deterministic; resolution axes are independent; same env always → same
  Session.
- **Account discriminated union** (Hypothesis): round-trip JSON serialization
  for each variant, including `OAuthTokenAccount` with `token_env` references.
- **`Workspace.use()` semantics**: each switch axis preserves what it should,
  invalidates what it should (e.g., changing project clears `_me_service`,
  changing account clears everything except HTTP transport).
- **CLI snapshot tests** for the bootstrap UX (fresh install message),
  account-add wizard, project list, target use.
- **Plugin auth_manager.py end-to-end**: one-shot tests via subprocess that
  exercise each subcommand against a fixture config.

### 17.4 Mutation testing target

The auth system is critical infrastructure. Run mutmut against
`_internal/auth/account.py`, `_internal/auth/session.py`, and the resolver in
`config.py`. Target ≥85% mutation score.

---

## 18. Decisions

The eight open questions surfaced during the first design pass are all
resolved:

| # | Question | Decision | Rationale |
|---|---|---|---|
| 1 | Saved-cursor terminology | **`target`** | "Pin" felt Pinterest-y; "alias" undersells it (it's a triple, not a project rename); "bookmark" overlaps Mixpanel's "bookmark" entity. `target` reads cleanly: `mp target use ecom`, `mp --target ci ...`. |
| 2 | Switching verb | **`use`** | Short, reads naturally in CLI (`mp project use 3713224`), distinct from `set` (which implies global config writes). |
| 3 | Workspace required vs optional | **Optional in the type, lazy auto-resolution always succeeds** | Verified against Mixpanel source (`webapp/project/utils.py:271`, `webapp/app_api/projects/urls.py`): every project is born with a default workspace, but most App-API endpoints are project-scoped and don't need a `workspace_id`. Always-optional with guaranteed-resolvable lazy fetch gives the best of both worlds — cheap Session construction *and* never a "missing workspace" error. See §13.2 for the full evidence. |
| 4 | `MP_OAUTH_TOKEN` precedence | **Env vars win over config** | Preserves PR #125 behavior; env vars are the standard CI/agent escape hatch and the user's most direct override. |
| 5 | Version bump for the breaking change | **`mixpanel_data` 0.4.0, plugin 5.0.0** | Library is still pre-1.0; major schema change is appropriate for a minor bump while pre-1.0. Plugin major bump signals breaking-config to users on update. |
| 6 | Per-account custom headers | **Headers stay global in `[settings]`** | Simpler API surface. The per-account use case (different Mixpanel deployments per credential) is rare enough that the user can use `MP_CUSTOM_HEADER_*` env vars to override per-invocation when needed. |
| 7 | Multi-region OAuth on one account | **Region stays per-account** | Multi-region requires multiple account entries (`personal-us`, `personal-eu`). Avoids per-region token files inside one account dir, keeps the storage layout flat and predictable. |
| 8 | Auto-convert v1 configs at first run | **Explicit only — `mp config convert`** | Auto-conversion violates the "clean break" principle. Forces a moment of consent on the user. With a handful of alpha testers, the cost of an explicit step is negligible. |

These decisions are baked into the rest of this document. No remaining open
questions block implementation.

---

## Appendix A: Resolution Decision Tree

```
              resolve_session(account=, project=, workspace=, target=)
                                        │
                ┌───────────────────────┼───────────────────────┐
                ▼                       ▼                       ▼
        ACCOUNT axis            PROJECT axis            WORKSPACE axis
                │                       │                       │
   1. MP_USERNAME+...           1. MP_PROJECT_ID set?       1. MP_WORKSPACE_ID set?
        │ yes                       │ yes                       │ yes
        │  └─ synth ServiceAccount  │  └─ use as-is             │  └─ use as-is
        │ no                        │ no                        │ no
   2. MP_OAUTH_TOKEN+...        2. Param `project=`?        2. Param `workspace=`?
        │ yes                       │ yes                       │ yes
        │  └─ synth OAuthTokenAcc   │  └─ use as-is             │  └─ use as-is
        │ no                        │ no                        │ no
   3. Param `account=`?         3. Param `target=`?         3. Param `target=`?
        │ yes                       │ yes                       │ yes
        │  └─ load from config      │  └─ load target.project   │  └─ load target.workspace
        │ no                        │ no                        │ no
   4. Param `target=`?          4. Bridge file?             4. Bridge file?
        │ yes                       │ yes                       │ yes
        │  └─ load target.account   │  └─ use bridge.project    │  └─ use bridge.workspace
        │ no                        │ no                        │ no
   5. Bridge file?              5. [active].project?        5. [active].workspace?
        │ yes                       │ yes                       │ yes
        │  └─ use bridge.account    │  └─ use as-is             │  └─ use as-is
        │ no                        │ no                        │ no
   6. [active].account?         6. ConfigError              6. None
        │ yes                                                   │   (lazy auto-resolve to
        │  └─ load from [accounts.X]                            │    project default on first
        │ no                                                    │    workspace-scoped call;
   7. ConfigError                                               │    always succeeds — every
                                                                │    project has a default)
                │                       │                       │
                └───────────────────────┼───────────────────────┘
                                        ▼
                          Session(account, project, workspace?)
```

**Per-axis priority ordering:**

- Env vars are checked FIRST on every axis (CI/agent escape hatch — see §18 #4).
- Within each axis, env > explicit param > target > bridge > config.
- The three axes are independent — no "if X is set, skip Y" cross-axis logic.

**Workspace axis special case:** unlike account and project, the workspace
axis can resolve to `None`. This is not an error. The API client lazy-resolves
to the project's default workspace when (and only when) a workspace-scoped
endpoint is called. Because every Mixpanel project has a default workspace
(verified in source — see §13.2), this resolution always succeeds.

---

## Appendix B: Vocabulary Mapping (Old → New)

### Config schema

| v1 key | v2 key | New key |
|---|---|---|
| `default = "X"` | (n/a) | `[active].account = "X"` |
| `[accounts.X].username` | (n/a) | `[accounts.X].username` (same) |
| `[accounts.X].secret` | (n/a) | `[accounts.X].secret` (same) |
| `[accounts.X].project_id` | (n/a) | `[active].project` (decoupled) |
| `[accounts.X].region` | (n/a) | `[accounts.X].region` (same) |
| (n/a) | `config_version = 2` | (deleted) |
| (n/a) | `[credentials.X]` | `[accounts.X]` |
| (n/a) | `[projects.X]` | `[targets.X]` |
| (n/a) | `[active].credential` | `[active].account` |
| (n/a) | `[active].project_id` | `[active].project` |
| (n/a) | `[active].workspace_id` | `[active].workspace` |

### Python

| Old type / method | New |
|---|---|
| `mixpanel_data.auth.Credentials` | (deleted; use `Session`) |
| `mixpanel_data.auth.AccountInfo` | `mixpanel_data.AccountSummary` |
| `mixpanel_data.auth.AuthMethod` | (deleted; check `account.type`) |
| `mixpanel_data.auth.AuthCredential` | `mixpanel_data.Account` |
| `mixpanel_data.auth.CredentialType` | (deleted; use `account.type`) |
| `mixpanel_data.auth.ProjectContext` | `mixpanel_data.Project` + `mixpanel_data.WorkspaceRef` |
| `mixpanel_data.auth.ResolvedSession` | `mixpanel_data.Session` |
| `ConfigManager.resolve_credentials()` | (deleted) |
| `ConfigManager.resolve_session()` | `ConfigManager.resolve_session()` (new signature) |
| `ConfigManager.add_account()` | (deleted; use `mp.accounts.add()`) |
| `ConfigManager.add_credential()` | `ConfigManager.add_account()` |
| `ConfigManager.set_default()` | (deleted) |
| `ConfigManager.set_active_credential()` | `ConfigManager.set_active(account=)` |
| `ConfigManager.set_active_project()` | `ConfigManager.set_active(project=)` |
| `ConfigManager.set_active_workspace()` | `ConfigManager.set_active(workspace=)` |
| `ConfigManager.set_active_context()` | `ConfigManager.set_active(...)` |
| `ConfigManager.list_accounts()` | (deleted) |
| `ConfigManager.list_credentials()` | `ConfigManager.list_accounts()` |
| `ConfigManager.list_project_aliases()` | `ConfigManager.list_targets()` |
| `ConfigManager.add_project_alias()` | `ConfigManager.add_target()` |
| `ConfigManager.migrate_v1_to_v2()` | (deleted) |
| `Workspace.set_workspace_id()` | `Workspace.use(workspace=)` |
| `Workspace.switch_project()` | `Workspace.use(project=)` |
| `Workspace.switch_workspace()` | `Workspace.use(workspace=)` |
| `Workspace.discover_projects()` | `Workspace.projects()` |
| `Workspace.discover_workspaces()` | `Workspace.workspaces()` |
| `Workspace.current_project` | `Workspace.project` |
| `Workspace.current_credential` | `Workspace.account` |
| `Workspace.test_credentials()` (static) | `mp.accounts.test()` |

### CLI

| Old | New |
|---|---|
| `mp auth list` | `mp account list` |
| `mp auth add NAME ...` | `mp account add NAME --type service_account ...` |
| `mp auth remove NAME` | `mp account remove NAME` |
| `mp auth switch NAME` | `mp account use NAME` |
| `mp auth show [NAME]` | `mp account show [NAME]` |
| `mp auth test [NAME]` | `mp account test [NAME]` |
| `mp auth login` | `mp account login [NAME]` |
| `mp auth logout` | `mp account logout [NAME]` |
| `mp auth status` | `mp session` |
| `mp auth token` | `mp account token [NAME]` |
| `mp auth migrate` | (deleted) |
| `mp auth cowork-setup` | `mp account export-bridge` |
| `mp auth cowork-teardown` | `mp account remove-bridge` |
| `mp auth cowork-status` | `mp session --bridge` |
| `mp projects list` | `mp project list` |
| `mp projects switch ID` | `mp project use ID` |
| `mp projects show` | `mp project show` |
| `mp projects refresh` | `mp project list --refresh` |
| `mp projects alias add NAME ...` | `mp target add NAME ...` |
| `mp projects alias remove NAME` | `mp target remove NAME` |
| `mp projects alias list` | `mp target list` |
| `mp workspaces list` | `mp workspace list` |
| `mp workspaces switch ID` | `mp workspace use ID` |
| `mp workspaces show` | `mp workspace show` |
| `mp context show` | `mp session` |
| `mp context switch NAME` | `mp target use NAME` |
| `--account NAME` (global) | `--account NAME` (same) |
| `--credential NAME` (global) | (deleted; use `--account`) |
| `--project ID` (global) | `--project ID` (same) |
| `--workspace-id ID` (global) | `--workspace ID` (renamed) |
| (n/a) | `--target NAME` (new) |

---

*End of design document.*
