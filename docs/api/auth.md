# Auth

The auth surface in `mixpanel_data` 0.4.0 is organized around three independent axes — Account, Project, Workspace — with three first-class account types, a single resolver, fluent in-session switching via `Workspace.use()`, and a Cowork bridge for remote authentication.

!!! tip "Explore on DeepWiki"
    🤖 **[Configuration Reference →](https://deepwiki.com/jaredmcfarland/mixpanel_data/7.3-configuration-reference)** (updated for 0.4.0)

    Ask questions about account types, session axes, OAuth, the Cowork bridge, or in-session switching.

## Overview

```python
import mixpanel_data as mp

# Construct a Workspace from active config
ws = mp.Workspace()

# Override per Workspace (env > param > target > bridge > [active] > default_project)
ws = mp.Workspace(account="team", project="3713224")
ws = mp.Workspace(target="ecom")
ws = mp.Workspace(session=mp.Session(account=..., project=..., workspace=...))

# In-session switching — fluent, O(1), no re-auth on project swap
ws.use(project="3018488").events()
ws.use(account="personal").events()    # rebuilds auth header; preserves _http
ws.use(target="ecom").events()         # applies all three axes atomically
ws.use(workspace=3448414).events()

# Functional namespaces (also re-exported as mp.accounts / mp.session / mp.targets)
summaries = mp.accounts.list()
mp.accounts.use("team")
active = mp.session.show()             # ActiveSession
mp.targets.add("ecom", account="team", project="3018488", workspace=3448414)
```

See [Configuration](../getting-started/configuration.md) for the full setup walkthrough.

## Account Types

`Account` is a Pydantic discriminated union over three first-class variants. The `type` field selects the variant; each variant carries the credentials it needs.

```python
from mixpanel_data import (
    Account,                      # discriminated union type
    ServiceAccount,               # type == "service_account"
    OAuthBrowserAccount,          # type == "oauth_browser"
    OAuthTokenAccount,            # type == "oauth_token"
    AccountType,                  # Literal["service_account" | "oauth_browser" | "oauth_token"]
    Region,                       # Literal["us" | "eu" | "in"]
)

account: Account = ServiceAccount(
    name="team",
    region="us",
    default_project="3018488",
    username="team-mp...",
    secret="...",
)

if isinstance(account, ServiceAccount):
    print(f"SA {account.name} → project {account.default_project}")
```

### ServiceAccount

Long-lived HTTP Basic Auth credentials. Best for CI / scripts / unattended automation.

::: mixpanel_data.ServiceAccount
    options:
      show_root_heading: true
      show_root_toc_entry: true

### OAuthBrowserAccount

PKCE browser flow; access/refresh tokens persisted at `~/.mp/accounts/{name}/tokens.json` and auto-refreshed on expiry.

::: mixpanel_data.OAuthBrowserAccount
    options:
      show_root_heading: true
      show_root_toc_entry: true

### OAuthTokenAccount

Static bearer token (CI / agents) — supplied inline or via an env var (`token_env`).

::: mixpanel_data.OAuthTokenAccount
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Session Axes

A `Session` is the immutable resolved state for a single Workspace at construction time — account, project, optional workspace, and the auth headers they generate.

::: mixpanel_data.Session
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.Project
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.WorkspaceRef
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.auth_types.ActiveSession
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Workspace.use() — In-Session Switching

`Workspace.use()` is the only in-session switching method. It returns `self` for fluent chaining and preserves the underlying `httpx.Client` and per-account `/me` cache across switches, so cross-project / cross-account iteration is O(1) per turn.

```python
import mixpanel_data as mp

ws = mp.Workspace()                                # active session

# In-session switching (returns self for chaining)
ws.use(account="team")                              # implicitly clears workspace
ws.use(project="3018488")
ws.use(workspace=3448414)
ws.use(target="ecom")                               # apply all three at once

# Persist the new state
ws.use(project="3018488", persist=True)             # writes [active].project

# Fluent chain
result = ws.use(project="3018488").segmentation(
    "Login", from_date="2026-04-01", to_date="2026-04-21"
)
```

Switching the active account clears the workspace (workspaces are project-scoped). The project re-resolves on account swap via `env > explicit > new account's default_project`. There is **no silent cross-axis fallback**: if an axis can't be resolved on the new account, `use()` raises `ConfigError`.

::: mixpanel_data.Workspace.use
    options:
      show_root_heading: false
      show_root_toc_entry: false

### Snapshot mode (parallel iteration)

For parallel cross-project iteration, snapshot the resolved `Session` and construct a fresh `Workspace` per task:

```python
from concurrent.futures import ThreadPoolExecutor
import mixpanel_data as mp

ws = mp.Workspace()
sessions = [
    ws.session.replace(project=mp.Project(id=p.id))
    for p in ws.projects()
]

def event_count(s: mp.Session) -> int:
    return len(mp.Workspace(session=s).events())

with ThreadPoolExecutor(max_workers=4) as pool:
    counts = list(pool.map(event_count, sessions))
```

## Functional Namespaces

The auth surface exposes three module-level namespaces re-exported from `mixpanel_data`. These are the canonical Python API for managing accounts, the active session, and saved targets.

### `mp.accounts`

Account lifecycle: register, switch, probe, OAuth flows, bridge export.

::: mixpanel_data.accounts
    options:
      show_root_heading: true
      show_root_toc_entry: true
      members:
        - list
        - add
        - update
        - remove
        - use
        - show
        - test
        - login
        - logout
        - token
        - export_bridge
        - remove_bridge

### `mp.session`

Read and write the persisted `[active]` block.

::: mixpanel_data.session
    options:
      show_root_heading: true
      show_root_toc_entry: true
      members:
        - show
        - use

### `mp.targets`

Manage saved (account, project, workspace?) cursor positions.

::: mixpanel_data.targets
    options:
      show_root_heading: true
      show_root_toc_entry: true
      members:
        - list
        - add
        - remove
        - use
        - show

## Result Types

Read-only structured results returned from the namespaces above.

### AccountSummary

::: mixpanel_data.AccountSummary
    options:
      show_root_heading: true
      show_root_toc_entry: true

### AccountTestResult

::: mixpanel_data.AccountTestResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

### OAuthLoginResult

::: mixpanel_data.OAuthLoginResult
    options:
      show_root_heading: true
      show_root_toc_entry: true

### Target

::: mixpanel_data.Target
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Credential Resolution Chain

When constructing a `Workspace`, each axis is resolved independently in this priority order:

1. **Environment variables** — `MP_ACCOUNT`, `MP_PROJECT_ID`, `MP_WORKSPACE_ID`, `MP_OAUTH_TOKEN`, etc.
2. **Constructor / CLI param** — `Workspace(account="...")`, `mp -a NAME ...`.
3. **Saved target** — `Workspace(target="ecom")`, `mp -t ecom ...`.
4. **Bridge file** — `MP_AUTH_FILE` or `~/.claude/mixpanel/auth.json`.
5. **Persisted active session** — the `[active]` block in `~/.mp/config.toml`.
6. **Account default** — `account.default_project` for the project axis.

See [Configuration → Credential Resolution Chain](../getting-started/configuration.md#credential-resolution-chain) for examples.

## Cowork Bridge (v2)

The Cowork bridge is a v2 JSON file that lets a remote VM authenticate against Mixpanel using your host machine's account and tokens. It embeds the full `Account`, optional OAuth tokens, and optional pinned project/workspace/headers.

```python
from pathlib import Path
import mixpanel_data as mp

# On the host
mp.accounts.export_bridge(to=Path("~/.claude/mixpanel/auth.json"))
mp.accounts.remove_bridge()
```

```bash
# CLI equivalents
mp account export-bridge --to ~/.claude/mixpanel/auth.json
mp account remove-bridge
mp session --bridge          # show bridge-resolved state
```

Default search order: `MP_AUTH_FILE` → `~/.claude/mixpanel/auth.json` → `./mixpanel_auth.json`.

::: mixpanel_data.auth_types.BridgeFile
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.auth_types.load_bridge
    options:
      show_root_heading: true
      show_root_toc_entry: true

## OAuth Token Plumbing

Low-level types for OAuth token handling. Most users never touch these directly — `mp.accounts.login(name)` drives the full flow and `OnDiskTokenResolver` materializes refreshed tokens automatically.

### OAuthTokens

::: mixpanel_data.auth_types.OAuthTokens
    options:
      show_root_heading: true
      show_root_toc_entry: true

### OAuthClientInfo

::: mixpanel_data.auth_types.OAuthClientInfo
    options:
      show_root_heading: true
      show_root_toc_entry: true

### TokenResolver Protocol

::: mixpanel_data.auth_types.TokenResolver
    options:
      show_root_heading: true
      show_root_toc_entry: true

### OnDiskTokenResolver

::: mixpanel_data.auth_types.OnDiskTokenResolver
    options:
      show_root_heading: true
      show_root_toc_entry: true
