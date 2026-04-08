# Design: Authentication, Project & Workspace Management Redesign

## Context

`mixpanel_data`'s current authentication system tightly couples *who you are* (credentials) with *what you're working on* (project). A single `Credentials` object bundles username, secret, project_id, and region into one immutable unit. This makes multi-project workflows painful: the real `~/.mp/config.toml` contains 7 duplicate accounts with identical service account credentials, differing only in `project_id`. OAuth tokens can have `project_id=None`, causing silent fallback to wrong projects. There's no project discovery, no workspace persistence, and no way to freely switch context.

This redesign separates authentication from project selection, adds `/me`-based discovery with disk caching, introduces persistent active context, and provides ergonomic CLI commands for project/workspace management.

---

## 1. Current System Analysis

### 1.1 How Authentication Works Today

**Credential resolution** (`_internal/config.py:280-369`) follows a strict priority:

1. Environment variables (`MP_USERNAME` + `MP_SECRET` + `MP_PROJECT_ID` + `MP_REGION` — all four required)
2. OAuth tokens from `~/.mp/oauth/tokens_{region}.json` (only if no explicit account requested)
3. Named account from `~/.mp/config.toml` `[accounts.{name}]`
4. Default account from config

**The `Credentials` model** (`config.py:64-185`) is frozen Pydantic:

```python
class Credentials(BaseModel):
    model_config = ConfigDict(frozen=True)
    username: str
    secret: SecretStr
    project_id: str          # REQUIRED, validated non-empty
    region: RegionType
    auth_method: AuthMethod  # basic or oauth
    oauth_access_token: SecretStr | None = None
```

**Config file schema** (`~/.mp/config.toml`):

```toml
default = "p8"
[accounts.ai-demo]
username = "jared-mp-demo.292e7c.mp-service-account"
secret = "aQUXhKokwLywLoxE3AxLt0g9dXC2G7bT"
project_id = "3713224"
region = "us"
```

**Workspace ID** is set dynamically per session via `Workspace(workspace_id=N)` or `set_workspace_id()`. Auto-discovery hits `GET /api/app/projects/{id}/workspaces/public` and picks the default. Not persisted to config.

### 1.2 Identified Problems

| # | Problem | Root Cause | Impact |
|---|---------|-----------|--------|
| 1 | **One project per account** | `Credentials` requires `project_id` at construction; config schema bundles them | 7 duplicate accounts in real config |
| 2 | **OAuth/SA interference** | OAuth skipped when `account` param is set; OAuth `project_id` can be `None` with silent fallback | Wrong project used silently |
| 3 | **No project discovery** | `/me` API not integrated; `mp auth add` requires manual `--project` | Users need out-of-band project IDs |
| 4 | **Workspace not persisted** | `workspace_id` only in-memory; no config storage | Must re-set every session |
| 5 | **No project switching** | `Credentials` is immutable; must create new `Workspace` instance | Clumsy multi-project workflows |
| 6 | **Credential priority confusing** | Env vars silently override OAuth and config | Hard to debug wrong credentials |
| 7 | **Region locked per account** | Region stored per account, not per credential | Must duplicate for multi-region |

### 1.3 Detailed Pain Point Analysis

#### Pain Point 1: One Project Per Account

**Location:** `Credentials` model (`config.py:64-86`) and config schema.

The `Credentials` model validates `project_id` as non-empty at construction time (`config.py:123`). Each account in `config.toml` bundles credentials + project_id as a single unit. A service account with access to 7 projects requires 7 duplicate config entries with identical `username`, `secret`, and `region` — differing only in `project_id`.

**Real-world evidence:** The actual `~/.mp/config.toml` contains accounts `ai-demo`, `b2b-demo`, `ecommerce-demo`, `finance-demo`, `healthcare-demo`, `media-demo`, and `social-demo`, all sharing the same service account `jared-mp-demo.292e7c.mp-service-account` with the same secret, duplicated 7 times.

#### Pain Point 2: OAuth/Service Account Interference

**Location:** `ConfigManager.resolve_credentials()` (`config.py:326-332`).

When `account` parameter is provided, OAuth token resolution is completely bypassed. Conversely, when no account is specified, OAuth takes priority over config file accounts. This creates confusing behavior:

- User has OAuth tokens AND named accounts → OAuth always wins (unless they specify `--account`)
- User specifies `--account` → OAuth is invisible, even if it has better permissions
- OAuth tokens store `project_id=None` → falls back to default account's project_id → if default changes, OAuth silently switches projects

**Location:** `_resolve_from_oauth()` (`config.py:371-422`).

The fallback chain for OAuth project_id: `token.project_id` → `MP_PROJECT_ID` env var → default account's project_id → `None` (credential resolution fails). This multi-level fallback makes it hard to predict which project is actually being used.

#### Pain Point 3: No Project Discovery

**Location:** `add_account()` CLI command (`cli/commands/auth.py:81`).

The `mp auth add` command requires `--project` as a mandatory parameter. There's no `mp projects list` or equivalent to discover accessible projects. The Mixpanel `/me` API returns all accessible projects, but this endpoint is not exposed in the Python library.

#### Pain Point 4: Workspace Not Persisted

**Location:** `Workspace.__init__()` (`workspace.py:305-370`) and `MixpanelAPIClient.resolve_workspace_id()` (`api_client.py:861-909`).

Workspace ID exists only in memory — set via constructor parameter or `set_workspace_id()`. Auto-discovery (listing workspaces and finding the default) happens every session. The config file has no field for workspace_id.

#### Pain Point 5: No In-Session Project Switching

**Location:** `Workspace` class — no `switch_project()` method exists.

Users must create a new `Workspace` instance with different parameters to work with a different project. The `Credentials` model is immutable, so even the API client can't be reconfigured.

#### Pain Point 6: Credential Priority Confusing

**Location:** `resolve_credentials()` (`config.py:321-324`).

Environment variables always take priority. A user with CI/CD env vars set locally will silently use those instead of their OAuth tokens or config file accounts, with no warning or indication.

#### Pain Point 7: Region Locked Per Account

**Location:** Config schema — `region` is a field within each account entry.

The same service account credentials can't be used across regions without duplicating the account entry.

---

### 1.4 What the Mixpanel `/me` API Returns

From the Django source (`analytics/webapp/app_api/me/utils.py:38-188`):

```
GET /api/app/me
Authorization: Basic <sa-credentials> | Bearer <oauth-token>

Response:
{
  "user_id": 12345,
  "user_email": "user@example.com",
  "user_name": "User Name",
  "organizations": {
    "<org_id>": {
      "id": 123,
      "name": "Org Name",
      "role": "owner",
      "permissions": ["write_dashboards", ...],
      "is_demo": false,
      "twofactor_auth_required": false
    }
  },
  "projects": {
    "<project_id>": {
      "name": "My Project",
      "organization_id": 123,
      "timezone": "US/Pacific",
      "domain": "mixpanel.com",
      "has_workspaces": true,
      "type": "PROJECT",
      "role": {"id": 1, "name": "admin"},
      "permissions": ["write_cohorts", ...],
      "feature_flags": [...],
      "has_integrated": true,
      "is_demo": false,
      "owner_id": 456,
      "utc_offset": "-08:00",
      "hasSensitiveAccess": false
    }
  },
  "workspaces": {
    "<workspace_id>": {
      "id": 789,
      "name": "Default",
      "project_id": 123,
      "is_default": true,
      "is_global": false,
      "is_restricted": false,
      "is_visible": true,
      "description": null,
      "creator_id": 456,
      "creator_name": "User Name",
      "membership_approval_required": true,
      "created_iso": "2024-01-01T00:00:00Z"
    }
  },
  "date_joined_iso": "2020-01-01T00:00:00Z",
  "is_staff": false,
  "user_bio": null,
  "user_phone": "",
  "user_login_flow": "password",
  "is_guest": false,
  "current_twofactor_method": null
}
```

**Optional query parameters:** `?project_id=X` or `?workspace_id=X` narrow the response to a single project/workspace, making it significantly faster.

**Auth support:** The `@auth_required(["user_details"])` decorator (`decorators.py:107-182`) accepts Session, Bearer, and Basic auth. Service accounts CAN call `/me`.

### 1.5 Why `/me` Is Slow

The `get_me()` function (`me/utils.py:38-188`) calls `load_projects_and_workspaces()` (`app_api/util.py:2306-2409`), which:

1. Queries ALL user's organizations and their grants (2 queries: org list + grants)
2. Interpolates staff roles with permission objects
3. Queries all projects in two passes: `PROJECT` type and `ROLLUP` type separately
4. For each project: prefetch-related organization feature flags, user, timezone, query_timezone, id_management
5. Queries workspace membership via THREE separate paths:
   - Individual memberships (`WorkspaceMember`)
   - Team memberships (`Team` → `WorkspaceTeam`)
   - Organization-wide memberships (`AllOrgUsersWorkspace`)
6. Checks project integration status (`projects_have_integrated`)
7. Checks sensitive data access per project (`user_has_sensitive_access_on_project`)
8. Computes custom role flags per organization

This results in 10+ database queries with multiple `prefetch_related` cascades, making the endpoint consistently slow (often 2-5 seconds).

### 1.6 How the Rust Crate Handles It

The Rust `mixpanel_data` crate (`mixpanel-desktop/src-tauri/crates/mixpanel_data/`) provides a production reference:

**Types** (`src/types/me.rs:16-56`):

```rust
pub struct MeResponse {
    pub user_id: u64,
    pub user_email: String,
    pub user_name: String,
    pub organizations: HashMap<String, OrgInfo>,
    pub projects: HashMap<String, ProjectInfo>,
    #[serde(flatten)]
    pub extra: HashMap<String, Value>,  // Forward compatibility
}

pub struct ProjectInfo {
    pub name: String,
    pub organization_id: u64,
    pub timezone: Option<String>,
    pub has_integrated: Option<bool>,
    pub is_demo: Option<bool>,
    #[serde(flatten)]
    pub extra: HashMap<String, Value>,
}
```

**Caching** (`src/auth/storage.rs:141-166`):

- Persists to `~/.mp/oauth/me_{region}.json` with `0o600` permissions
- Cleared on logout (`clear_tokens` also calls `clear_me` at line 137)
- No automatic TTL — cached until explicit invalidation
- Loaded/saved via `OAuthStorage.load_me()` / `save_me()`

**Workspace resolution** (`src/internal/api_client.rs:381-421`):

- Uses `tokio::sync::OnceCell<String>` for lazy, cached workspace ID
- Fetches `GET /api/app/projects/{id}/workspaces/public`, picks `is_default: true`
- Errors if no workspaces exist or none marked default

**Key design choice:** The Rust crate caches `/me` on login and clears it on logout. It does NOT have a TTL — the assumption is that org/project membership changes infrequently enough that manual refresh is acceptable.

---

## 2. Design Principles

1. **Separate identity from context.** Authentication ("who am I") is independent of project/workspace selection ("what am I working on"). They compose, not bundle.

2. **Discovery before configuration.** Users should discover what they have access to, then select — not manually enter project IDs they found elsewhere.

3. **Persistent context.** The active project and workspace should survive across sessions, CLI invocations, and Python script runs.

4. **Fast switching.** Changing projects or workspaces should be a config write, not a re-authentication.

5. **Cache the expensive thing.** The `/me` endpoint is slow; cache it aggressively to disk with a reasonable TTL. Use it as the source of truth for "what can I access?"

6. **Backward compatibility.** Existing `Workspace(account="name")`, env var usage, and v1 config files must continue working without changes.

7. **Agent-friendly.** Programmatic discovery and switching should be as simple as `ws.discover_projects()` and `ws.switch_project("123")`.

---

## 3. New Config Schema (v2)

### 3.1 Schema Definition

```toml
config_version = 2

# Active context — persisted across sessions
[active]
credential = "demo-sa"       # Which credential set to use
project_id = "3713224"        # Active project
workspace_id = 3448413        # Active workspace (optional)

# Credentials: pure authentication, no project binding
[credentials.demo-sa]
type = "service_account"
username = "jared-mp-demo.292e7c.mp-service-account"
secret = "aQUXhKokwLywLoxE3AxLt0g9dXC2G7bT"
region = "us"

[credentials.p8-sa]
type = "service_account"
username = "jared-mp.19df54.mp-service-account"
secret = "owbi8v1n9YD9RcQVN4duRjgJgvhoZ100"
region = "us"

[credentials.infra-sa]
type = "service_account"
username = "jared-inframetrics.1d5d63.mp-service-account"
secret = "G1izsBaI9PrzdLY0UROUpAHGf7MVGRto"
region = "us"

# OAuth credentials reference token storage (no inline secrets)
[credentials.my-oauth]
type = "oauth"
region = "us"
# Tokens stored in ~/.mp/oauth/tokens_us.json (managed by OAuth flow)

# Named project aliases for quick switching (optional convenience)
[projects.ai-demo]
project_id = "3713224"
credential = "demo-sa"           # Which credential to use
workspace_id = 3448413           # Default workspace (optional)

[projects.ecommerce]
project_id = "3018488"
credential = "demo-sa"

[projects.b2b]
project_id = "3018486"
credential = "demo-sa"

[projects.finance]
project_id = "3018493"
credential = "demo-sa"

[projects.healthcare]
project_id = "3018498"
credential = "demo-sa"

[projects.media]
project_id = "3018489"
credential = "demo-sa"

[projects.social]
project_id = "3018487"
credential = "demo-sa"

[projects.p8]
project_id = "8"
credential = "p8-sa"
workspace_id = 3448413
```

### 3.2 Key Differences from v1

| Aspect | v1 (Current) | v2 (New) |
|--------|-------------|----------|
| Auth + Project | Bundled in `[accounts.X]` | Separated: `[credentials.X]` + `[projects.X]` |
| Active selection | `default = "account-name"` | `[active]` section with credential + project + workspace |
| Workspace | Not in config | Stored in `active.workspace_id` and project aliases |
| OAuth | Implicit (tokens on disk) | Explicit credential entry with `type = "oauth"` |
| Duplication | Same SA creds repeated per project | One credential entry, many project aliases |
| Version detection | None | `config_version = 2` |

### 3.3 Migration Strategy

**Auto-detection:** `config_version` key presence determines schema version. Absent = v1.

**Migration command:** `mp auth migrate`

**Algorithm:**

1. Read v1 config
2. Group accounts by `(username, secret, region)` tuple — each unique group becomes one credential
3. Auto-name credentials: if group has 1 account, use account name; if multiple, derive a common name
4. Create project aliases from each account (account name becomes alias name)
5. Set `active` context from the old `default` account
6. Write v2 config
7. Backup v1 config to `config.toml.v1.bak`

**Example migration of the real config:**

The 7 demo accounts (`ai-demo`, `b2b-demo`, `ecommerce-demo`, `finance-demo`, `healthcare-demo`, `media-demo`, `social-demo`) all share `(jared-mp-demo.292e7c.mp-service-account, aQUXhK..., us)`. They collapse into:
- One `[credentials.demo-sa]` entry
- Seven `[projects.{name}]` aliases

Accounts with unique credentials (`p8`, `p82`, `inframetrics`) each get their own credential entry.

**Gradual migration:** Both v1 and v2 configs work simultaneously. No forced migration — users can stay on v1 indefinitely.

---

## 4. Type System

### 4.1 New Core Types

**File:** `src/mixpanel_data/_internal/auth_credential.py`

```python
from __future__ import annotations

import base64
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr

RegionType = Literal["us", "eu", "in"]


class CredentialType(str, Enum):
    """Type of authentication credential."""
    service_account = "service_account"
    oauth = "oauth"


class AuthCredential(BaseModel):
    """Pure authentication identity — no project binding.

    Represents 'who you are' independent of 'what you're working on'.
    Replaces the identity half of the old Credentials model.

    Args:
        name: Credential set name (matches key in config).
        type: Authentication type (service_account or oauth).
        region: Data residency region.
        username: Service account username (SA only).
        secret: Service account secret (SA only).
        oauth_access_token: OAuth Bearer token (OAuth only).
    """
    model_config = ConfigDict(frozen=True)

    name: str
    type: CredentialType
    region: RegionType

    # Service account fields
    username: str = ""
    secret: SecretStr = SecretStr("")

    # OAuth fields
    oauth_access_token: SecretStr | None = None

    def auth_header(self) -> str:
        """Build the Authorization header value.

        Returns:
            For service_account: "Basic <base64(username:secret)>".
            For oauth: "Bearer <access_token>".
        """
        if self.type == CredentialType.oauth:
            if self.oauth_access_token is None:
                raise ValueError("No OAuth access token available")
            return f"Bearer {self.oauth_access_token.get_secret_value()}"
        raw = f"{self.username}:{self.secret.get_secret_value()}"
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        return f"Basic {encoded}"


class ProjectContext(BaseModel):
    """What you're working on — project + optional workspace.

    This is the 'selection' part that was previously embedded in Credentials.
    Decoupled from authentication so that switching projects doesn't require
    re-authentication.

    Args:
        project_id: Mixpanel project identifier.
        workspace_id: Workspace within the project (None = project-level).
        project_name: Human-readable name (from /me cache or config).
        workspace_name: Human-readable name (from /me cache or API).
    """
    model_config = ConfigDict(frozen=True)

    project_id: str
    workspace_id: int | None = None
    project_name: str | None = None
    workspace_name: str | None = None


class ResolvedSession(BaseModel):
    """Fully resolved session: auth + project context.

    This is what MixpanelAPIClient needs to make requests. It composes
    an AuthCredential (who you are) with a ProjectContext (what you're
    working on).

    Replaces the old Credentials at the API client boundary.

    Args:
        auth: Authentication identity.
        project: Project and workspace selection.
    """
    model_config = ConfigDict(frozen=True)

    auth: AuthCredential
    project: ProjectContext

    @property
    def project_id(self) -> str:
        """Convenience: project_id for API params."""
        return self.project.project_id

    @property
    def region(self) -> RegionType:
        """Convenience: region from auth credential."""
        return self.auth.region

    def auth_header(self) -> str:
        """Delegate to auth credential."""
        return self.auth.auth_header()
```

### 4.2 Backward-Compatible Bridge

The existing `Credentials` class gains a `to_resolved_session()` method, allowing all existing code to work unchanged while internal components migrate to the new types:

```python
# Added to existing Credentials class in config.py

def to_resolved_session(self) -> ResolvedSession:
    """Convert legacy Credentials to new ResolvedSession.

    Returns:
        A ResolvedSession combining auth and project context.
    """
    from mixpanel_data._internal.auth_credential import (
        AuthCredential,
        CredentialType,
        ProjectContext,
        ResolvedSession,
    )
    auth = AuthCredential(
        name="<legacy>",
        type=(CredentialType.oauth if self.auth_method == AuthMethod.oauth
              else CredentialType.service_account),
        region=self.region,
        username=self.username,
        secret=self.secret,
        oauth_access_token=self.oauth_access_token,
    )
    project = ProjectContext(project_id=self.project_id)
    return ResolvedSession(auth=auth, project=project)
```

### 4.3 /me Response Types

**File:** `src/mixpanel_data/_internal/me.py`

```python
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class MeOrgInfo(BaseModel):
    """Organization info from /me response."""
    model_config = ConfigDict(frozen=True, extra="allow")
    id: int
    name: str
    role: str | None = None
    permissions: list[str] = []


class MeProjectInfo(BaseModel):
    """Project info from /me response."""
    model_config = ConfigDict(frozen=True, extra="allow")
    name: str
    organization_id: int
    timezone: str | None = None
    has_workspaces: bool = False
    domain: str | None = None
    type: str | None = None
    role: dict[str, Any] | None = None
    permissions: list[str] = []


class MeWorkspaceInfo(BaseModel):
    """Workspace info from /me response."""
    model_config = ConfigDict(frozen=True, extra="allow")
    id: int
    name: str
    project_id: int
    is_default: bool = False
    is_global: bool = False
    is_restricted: bool = False
    is_visible: bool = True
    description: str | None = None
    creator_name: str | None = None


class MeResponse(BaseModel):
    """Cached /me endpoint response.

    Uses extra="allow" for forward compatibility (mirrors the Rust crate's
    #[serde(flatten)] pattern — unknown API fields are preserved, not rejected).
    """
    model_config = ConfigDict(extra="allow")
    user_id: int | None = None
    user_email: str | None = None
    user_name: str | None = None
    organizations: dict[str, MeOrgInfo] = {}
    projects: dict[str, MeProjectInfo] = {}
    workspaces: dict[str, MeWorkspaceInfo] = {}
    # Cache metadata (added by us, not from API)
    cached_at: datetime | None = None
    cached_region: str | None = None
```

Uses `extra="allow"` on all models to ensure new API fields don't break deserialization — the same forward-compatibility strategy used by the Rust crate's `#[serde(flatten)] pub extra: HashMap<String, Value>`.

---

## 5. /me API Integration

### 5.1 MeCache

```python
class MeCache:
    """Disk-backed cache for /me responses.

    Storage: ~/.mp/oauth/me_{region}.json (0o600 permissions)
    TTL: 24 hours (configurable)
    Invalidation: logout, explicit refresh, auth change, TTL expiry
    """
    DEFAULT_TTL: timedelta = timedelta(hours=24)

    def __init__(
        self,
        storage_dir: Path | None = None,
        ttl: timedelta | None = None,
    ) -> None:
        self._storage_dir = storage_dir or Path.home() / ".mp" / "oauth"
        self._ttl = ttl or self.DEFAULT_TTL

    def get(self, region: str) -> MeResponse | None:
        """Load cached /me response if valid (not expired).

        Returns:
            MeResponse if cache exists and is within TTL, None otherwise.
        """
        path = self._cache_path(region)
        if not path.exists():
            return None
        response = MeResponse.model_validate_json(path.read_text())
        if response.cached_at is None:
            return None
        if datetime.now(tz=response.cached_at.tzinfo) - response.cached_at > self._ttl:
            return None  # Expired
        return response

    def put(self, response: MeResponse, region: str) -> None:
        """Cache /me response to disk with timestamp."""
        response.cached_at = datetime.now().astimezone()
        response.cached_region = region
        path = self._cache_path(region)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(response.model_dump_json(indent=2))
        # Set file permissions to 0o600 (owner-only)
        path.chmod(0o600)

    def invalidate(self, region: str | None = None) -> None:
        """Clear cache for region (or all regions if None)."""
        if region:
            path = self._cache_path(region)
            if path.exists():
                path.unlink()
        else:
            for r in ("us", "eu", "in"):
                self.invalidate(r)

    def _cache_path(self, region: str) -> Path:
        return self._storage_dir / f"me_{region}.json"
```

**TTL rationale:** 24 hours balances freshness vs. the `/me` endpoint's cost (2-5 seconds). Organization/project/workspace membership changes infrequently. Users can force-refresh via `mp projects refresh`.

### 5.2 MeService

```python
class MeService:
    """Fetches and caches the /me endpoint.

    Provides project and workspace discovery backed by the /me API.
    Uses disk cache to avoid repeated slow API calls.
    """

    def __init__(
        self,
        auth: AuthCredential,
        cache: MeCache | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._auth = auth
        self._cache = cache or MeCache()
        self._http_client = http_client

    def fetch(self, *, force_refresh: bool = False) -> MeResponse:
        """Get /me response (cached or fresh).

        Args:
            force_refresh: Bypass cache and call API.

        Returns:
            MeResponse with user, org, project, and workspace data.

        Raises:
            AuthenticationError: If credentials are invalid.
            APIError: If /me endpoint fails.
        """
        if not force_refresh:
            cached = self._cache.get(self._auth.region)
            if cached is not None:
                return cached
        response = self._call_me_api()
        self._cache.put(response, self._auth.region)
        return response

    def list_projects(self) -> list[tuple[str, MeProjectInfo]]:
        """All accessible projects, sorted by name.

        Returns:
            List of (project_id, MeProjectInfo) tuples.
        """
        me = self.fetch()
        return sorted(me.projects.items(), key=lambda x: x[1].name)

    def list_workspaces(self, project_id: str) -> list[MeWorkspaceInfo]:
        """Workspaces for a project, from /me cache.

        Args:
            project_id: The project to list workspaces for.

        Returns:
            List of MeWorkspaceInfo, sorted by name.
        """
        me = self.fetch()
        return sorted(
            [w for w in me.workspaces.values() if str(w.project_id) == project_id],
            key=lambda w: w.name,
        )

    def find_project(self, project_id: str) -> MeProjectInfo | None:
        """Look up a specific project by ID."""
        me = self.fetch()
        return me.projects.get(project_id)

    def find_default_workspace(self, project_id: str) -> MeWorkspaceInfo | None:
        """Find the default workspace for a project."""
        workspaces = self.list_workspaces(project_id)
        for ws in workspaces:
            if ws.is_default:
                return ws
        return workspaces[0] if workspaces else None

    def _call_me_api(self) -> MeResponse:
        """Call GET /api/app/me and parse response."""
        # Uses the auth credential's header and region for endpoint selection
        ...
```

### 5.3 Cache Invalidation Triggers

| Event | Action |
|-------|--------|
| `mp auth logout` | `MeCache.invalidate(region)` |
| `mp auth login` (new token) | `MeCache.invalidate(region)` + re-fetch on next access |
| `mp projects refresh` | `MeCache.invalidate(region)` + immediate re-fetch |
| TTL expiry (24h) | Automatic on next `MeService.fetch()` |
| Credential change | `MeCache.invalidate()` (all regions) |

---

## 6. Credential Resolution (New Priority)

```
resolve_session(credential, project_id, workspace_id) -> ResolvedSession

  1. ENV VARS: MP_USERNAME + MP_SECRET + MP_PROJECT_ID + MP_REGION
     All four required. Returns immediately with BasicAuth.
     (Unchanged from today — highest priority for CI/CD.)

  2. EXPLICIT PARAMS: credential + project_id + workspace_id
     From code (Workspace constructor) or CLI flags (--credential, --project).
     Auth loaded from config; project from parameter.

  3. LEGACY ACCOUNT: --account flag or Workspace(account="name")
     Resolves via v1 accounts (bundled) or v2 project aliases.
     Full backward compatibility.

  4. ACTIVE CONTEXT: [active] section from config
     Auth: active.credential → load from [credentials.X]
     Project: active.project_id → ProjectContext
     Workspace: active.workspace_id → ProjectContext.workspace_id

  5. OAUTH FALLBACK: Valid OAuth token for active region + active.project_id
     If no credential specified but OAuth tokens exist.

  6. FIRST AVAILABLE: First credential + first known project
     Better fallback than "no credentials configured" error.
```

**Key improvement:** Auth and project are resolved INDEPENDENTLY, then combined. OAuth no longer needs `project_id` in the token — it comes from `active.project_id` in the config.

### Resolution Data Flow

```
User Input:
  Workspace(credential="demo-sa", project_id="3713224")
    │
    ▼
ConfigManager.resolve_session(credential="demo-sa", project_id="3713224")
    │
    ├─ 1. Check env vars → not set, continue
    ├─ 2. Load credential "demo-sa" from [credentials.demo-sa]
    │     → AuthCredential(name="demo-sa", type=service_account,
    │                      username="jared-mp-demo...", secret=***, region="us")
    ├─ 3. Use provided project_id → ProjectContext(project_id="3713224")
    ├─ 4. Combine → ResolvedSession(auth=..., project=...)
    ▼
MixpanelAPIClient(session=resolved_session)
    │
    ├─ session.auth_header() → "Basic dXNlcjpzZWNyZXQ="
    ├─ session.project_id   → "3713224"
    └─ session.region       → "us"
```

---

## 7. API Client Changes

### 7.1 Accept ResolvedSession

```python
class MixpanelAPIClient:
    def __init__(
        self,
        credentials: Credentials | ResolvedSession,
        *,
        timeout: float = 120.0,
        export_timeout: float = 600.0,
        max_retries: int = 3,
        _transport: httpx.BaseTransport | None = None,
    ) -> None:
        # Normalize to ResolvedSession internally
        if isinstance(credentials, Credentials):
            self._session = credentials.to_resolved_session()
        else:
            self._session = credentials

        # All internal usage changes:
        # self._credentials.auth_header() → self._session.auth_header()
        # self._credentials.project_id   → self._session.project_id
        # self._credentials.region       → self._session.region
```

### 7.2 Project Switching via Factory

```python
def with_project(
    self, project_id: str, workspace_id: int | None = None
) -> MixpanelAPIClient:
    """Create a new client targeting a different project.

    Shares the same HTTP transport and auth, changes only project context.
    This is the key enabler for fast project switching — no re-auth needed.

    Args:
        project_id: New project to target.
        workspace_id: Optional workspace within the new project.

    Returns:
        A new MixpanelAPIClient with updated project context.
    """
    new_session = ResolvedSession(
        auth=self._session.auth,
        project=ProjectContext(project_id=project_id, workspace_id=workspace_id),
    )
    return MixpanelAPIClient(
        new_session,
        timeout=self._timeout,
        export_timeout=self._export_timeout,
        max_retries=self._max_retries,
        _transport=self._transport,
    )
```

### 7.3 /me Endpoint

```python
def me(self) -> dict[str, Any]:
    """Call GET /api/app/me.

    Unlike most App API endpoints, /me is NOT project-scoped — it returns
    information about the authenticated user across all organizations
    and projects.

    Returns:
        Raw /me response dict.
    """
    return self._app_api_request_raw("GET", "/me/", params=None, json_body=None)
```

---

## 8. Workspace Class Changes

### 8.1 Constructor (Backward Compatible)

```python
class Workspace:
    def __init__(
        self,
        # Existing parameters (backward compat)
        account: str | None = None,
        project_id: str | None = None,
        region: str | None = None,
        workspace_id: int | None = None,
        # New parameters
        credential: str | None = None,
        session: ResolvedSession | None = None,
        # DI for testing
        _config_manager: ConfigManager | None = None,
        _api_client: MixpanelAPIClient | None = None,
    ) -> None:
        """Create a Workspace.

        Construction modes (in priority order):
        1. Explicit session: Workspace(session=resolved_session)
        2. New-style:        Workspace(credential="name", project_id="123")
        3. Legacy account:   Workspace(account="name")
        4. Env vars / active context from config file
        """
```

### 8.2 New Methods

```python
# === Project/workspace discovery ===

def me(self, *, force_refresh: bool = False) -> MeResponse:
    """Get /me response for current credentials (cached).

    Returns user profile, accessible organizations, projects,
    and workspaces. Cached to disk for 24 hours.

    Args:
        force_refresh: Bypass cache and call API.

    Returns:
        MeResponse with full user context.
    """

def discover_projects(self) -> list[tuple[str, MeProjectInfo]]:
    """List all accessible projects via /me.

    Returns:
        List of (project_id, MeProjectInfo) tuples, sorted by name.

    Example:
        ```python
        ws = Workspace()
        for pid, info in ws.discover_projects():
            print(f"{pid}: {info.name}")
        ```
    """

def discover_workspaces(
    self, project_id: str | None = None
) -> list[MeWorkspaceInfo]:
    """List workspaces for a project.

    Args:
        project_id: Project to list workspaces for.
                    Defaults to current active project.

    Returns:
        List of MeWorkspaceInfo, sorted by name.
    """

# === Context switching (in-session, not persisted) ===

def switch_project(
    self, project_id: str, workspace_id: int | None = None
) -> None:
    """Switch to a different project.

    Creates a new API client with the new project context.
    Clears discovery caches since schema differs per project.
    Does NOT persist — use ConfigManager.set_active_project() for that.

    Args:
        project_id: New project to work with.
        workspace_id: Optional workspace within the new project.
    """

def switch_workspace(self, workspace_id: int) -> None:
    """Switch workspace within the current project.

    Cheaper than switch_project — no credential changes or cache clears.

    Args:
        workspace_id: New workspace to work with.
    """

# === Context inspection ===

@property
def current_project(self) -> ProjectContext:
    """Return the current project context."""

@property
def current_credential(self) -> AuthCredential:
    """Return the current auth credential (name, type, region)."""
```

### 8.3 Agent Usage Patterns

```python
import mixpanel_data as mp

# === Pattern 1: Discover and switch ===
ws = mp.Workspace()
projects = ws.discover_projects()
for pid, info in projects:
    print(f"{pid}: {info.name} (org: {info.organization_id})")
# Output:
#   3713224: AI Demo (org: 12345)
#   3018488: E-Commerce Demo (org: 12345)
#   8: P8 (org: 67890)

ws.switch_project("3713224")
workspaces = ws.discover_workspaces()
for w in workspaces:
    print(f"  {w.id}: {w.name} {'(default)' if w.is_default else ''}")
# Output:
#   3448413: Default (default)
#   3448414: Staging

# Work with current project
events = ws.events()
result = ws.segmentation(event="Login", from_date="2025-01-01", to_date="2025-01-31")

# Switch to another project (same credentials, instant)
ws.switch_project("3018488")
events2 = ws.events()  # Different project's schema


# === Pattern 2: Direct construction ===
ws = mp.Workspace(credential="demo-sa", project_id="3713224")


# === Pattern 3: Pre-built session ===
from mixpanel_data._internal.auth_credential import (
    AuthCredential, CredentialType, ProjectContext, ResolvedSession
)
session = ResolvedSession(
    auth=AuthCredential(name="test", type=CredentialType.service_account,
                        username="...", secret=SecretStr("..."), region="us"),
    project=ProjectContext(project_id="3713224"),
)
ws = mp.Workspace(session=session)


# === Pattern 4: Legacy (unchanged, still works) ===
ws = mp.Workspace(account="ai-demo")
ws = mp.Workspace()  # Uses active context or default
```

---

## 9. CLI Commands

### 9.1 New Command Groups

```
mp projects                              # Project management
  list [--refresh] [--format json|table] # List accessible projects (from /me)
  switch <project-id>                    # Set active project (persists)
  show                                   # Show current active project
  refresh                                # Force-refresh /me cache
  alias add <name> [--project] [--credential] [--workspace]
  alias remove <name>
  alias list

mp workspaces                            # Workspace management
  list [--project <id>]                  # List workspaces for project
  switch <workspace-id>                  # Set active workspace (persists)
  show                                   # Show current workspace

mp context                               # Context overview
  show                                   # Full context: credential + project + workspace
  switch <alias>                         # Switch to named project alias
```

### 9.2 Modified Existing Commands

**`mp auth add`** — drops required `--project`:

```bash
# New: credential-only (no project binding)
mp auth add demo-sa -u "jared-mp-demo.292e7c.mp-service-account"
# Secret prompted interactively
# → Creates [credentials.demo-sa] only

# Legacy: still works, creates credential + project alias
mp auth add demo-sa -u "user" --project 3713224
# → Creates [credentials.demo-sa] AND [projects.demo-sa] with project_id
```

**`mp auth list`** — shows credentials (not accounts) in v2 mode.

**`mp auth status`** — enhanced to show active context:

```
$ mp auth status
Credential:  demo-sa (service_account, us)
Project:     AI Demo (3713224)
Workspace:   Default (3448413)
OAuth:       Authenticated (expires 2026-04-08T12:00:00Z)
```

**`mp auth migrate`** — new command for v1 → v2 migration.

### 9.3 Global Options

```python
@app.callback()
def main(
    ctx: typer.Context,
    account: str | None = typer.Option(None, "--account", "-a",
        help="Legacy: named account (credential + project)"),
    credential: str | None = typer.Option(None, "--credential", "-c",
        help="Credential name from config"),
    project: str | None = typer.Option(None, "--project", "-p",
        help="Project ID (overrides active project)"),
    workspace_id: int | None = typer.Option(None, "--workspace-id",
        help="Workspace ID (overrides active workspace)"),
    region: str | None = typer.Option(None, "--region",
        help="Data residency region (overrides credential's region)"),
    output_format: str = typer.Option("json", "--format", "-f",
        help="Output format: json, jsonl, table, csv"),
)
```

### 9.4 Example Workflows

**First-time setup:**

```bash
$ mp auth add my-sa -u "jared.abc123.mp-service-account"
Secret: ********
Added credential 'my-sa' (region: us)

$ mp projects list
ID         NAME              ORG              WORKSPACES
3713224    AI Demo           Jared's Org      Yes
3018488    E-Commerce Demo   Jared's Org      Yes
8          P8                Jared's Org      Yes

$ mp projects switch 3713224
Switched to: AI Demo (3713224)

$ mp workspaces list
ID         NAME       DEFAULT
3448413    Default    Yes
3448414    Staging    No

$ mp context show
Credential:  my-sa (service_account, us)
Project:     AI Demo (3713224)
Workspace:   Default (3448413)
```

**Quick switching with aliases:**

```bash
$ mp projects alias add ecom --project 3018488 --credential my-sa
Created alias 'ecom' → project 3018488 (my-sa)

$ mp context switch ecom
Switched to: E-Commerce Demo (3018488) via my-sa

$ mp context switch ai-demo
Switched to: AI Demo (3713224) via my-sa
```

**OAuth workflow:**

```bash
$ mp auth login
Opening browser for Mixpanel OAuth...
Authenticated as user@example.com

$ mp projects list
# Shows ALL projects accessible via OAuth

$ mp projects switch 3713224
Switched to: AI Demo (3713224)

$ mp query segmentation -e Login --from 2025-01-01 --to 2025-01-31
# Works with OAuth token + selected project
```

**Migration from v1:**

```bash
$ mp auth migrate
Detected v1 config with 10 accounts.
Grouped into 4 unique credentials:
  demo-sa      → 7 projects (ai-demo, b2b-demo, ...)
  p8-sa        → 1 project (p8)
  p8-sa-2      → 1 project (p82)
  infra-sa     → 1 project (inframetrics)

Backed up: ~/.mp/config.toml.v1.bak
Written:   ~/.mp/config.toml (v2)

Active context set to: p8-sa → project 8 (was default 'p8')
```

---

## 10. ConfigManager Extensions

### 10.1 New Methods

```python
class ConfigManager:
    # === Existing (preserved for backward compat) ===
    def resolve_credentials(self, account=None) -> Credentials: ...
    def list_accounts(self) -> list[AccountInfo]: ...
    def add_account(self, name, username, secret, project_id, region) -> None: ...
    def remove_account(self, name) -> None: ...
    def set_default(self, name) -> None: ...
    def get_account(self, name) -> AccountInfo: ...

    # === New: session resolution ===
    def resolve_session(
        self,
        credential: str | None = None,
        project_id: str | None = None,
        workspace_id: int | None = None,
    ) -> ResolvedSession:
        """Resolve a full session from config.

        Works with both v1 and v2 config schemas. Resolution priority:
        1. Env vars (all four required)
        2. Explicit params (credential, project_id, workspace_id)
        3. Active context from config
        4. OAuth fallback
        5. First available credential + project
        """

    # === New: credential management (v2) ===
    def list_credentials(self) -> list[CredentialInfo]: ...
    def add_credential(
        self, name: str, type: str, username: str | None = None,
        secret: str | None = None, region: str = "us",
    ) -> None: ...
    def remove_credential(self, name: str) -> None: ...

    # === New: project alias management (v2) ===
    def list_project_aliases(self) -> list[ProjectAlias]: ...
    def add_project_alias(
        self, name: str, project_id: str,
        credential: str | None = None, workspace_id: int | None = None,
    ) -> None: ...
    def remove_project_alias(self, name: str) -> None: ...

    # === New: active context (v2) ===
    def get_active_context(self) -> ActiveContext: ...
    def set_active_credential(self, name: str) -> None: ...
    def set_active_project(
        self, project_id: str, workspace_id: int | None = None,
    ) -> None: ...
    def set_active_workspace(self, workspace_id: int) -> None: ...

    # === New: migration ===
    def config_version(self) -> int: ...
    def migrate_v1_to_v2(self) -> MigrationResult: ...
```

### 10.2 Version-Aware Resolution

```python
def resolve_session(self, credential=None, project_id=None, workspace_id=None):
    # Works with both v1 and v2
    version = self._config_version()
    if version == 1:
        return self._resolve_session_v1(credential, project_id, workspace_id)
    return self._resolve_session_v2(credential, project_id, workspace_id)

def _resolve_session_v1(self, credential, project_id, workspace_id):
    """Resolve session from v1 config.
    Maps 'credential' to 'account' name, uses existing resolve_credentials()."""
    creds = self.resolve_credentials(account=credential)
    if project_id:
        # Override project from resolved credentials
        creds = Credentials(
            username=creds.username, secret=creds.secret,
            project_id=project_id, region=creds.region,
            auth_method=creds.auth_method,
            oauth_access_token=creds.oauth_access_token,
        )
    session = creds.to_resolved_session()
    if workspace_id:
        session = ResolvedSession(
            auth=session.auth,
            project=ProjectContext(
                project_id=session.project_id, workspace_id=workspace_id,
            ),
        )
    return session
```

### 10.3 Supporting Dataclasses

```python
@dataclass(frozen=True)
class CredentialInfo:
    """Credential metadata (secret not included)."""
    name: str
    type: str           # "service_account" or "oauth"
    username: str       # SA username or "" for OAuth
    region: str
    is_active: bool     # Whether this is the active credential

@dataclass(frozen=True)
class ProjectAlias:
    """Named project shortcut."""
    name: str
    project_id: str
    credential: str | None
    workspace_id: int | None

@dataclass(frozen=True)
class ActiveContext:
    """Current active context from config."""
    credential: str | None
    project_id: str | None
    workspace_id: int | None

@dataclass(frozen=True)
class MigrationResult:
    """Result of v1 → v2 migration."""
    credentials_created: int
    project_aliases_created: int
    backup_path: Path
    active_credential: str
    active_project_id: str
```

---

## 11. File Changes Summary

### New Files

| File | Purpose |
|------|---------|
| `src/mixpanel_data/_internal/auth_credential.py` | `AuthCredential`, `CredentialType`, `ProjectContext`, `ResolvedSession` |
| `src/mixpanel_data/_internal/me.py` | `MeResponse` types, `MeCache`, `MeService` |
| `src/mixpanel_data/cli/commands/projects.py` | `mp projects` command group |
| `src/mixpanel_data/cli/commands/workspaces_cmd.py` | `mp workspaces` command group |
| `src/mixpanel_data/cli/commands/context.py` | `mp context` command group |
| `tests/unit/test_auth_credential.py` | Unit tests for new types |
| `tests/unit/test_me.py` | Unit tests for /me cache and service |
| `tests/unit/test_config_v2.py` | Unit tests for v2 config |
| `tests/unit/test_migration.py` | Unit tests for v1→v2 migration |
| `tests/unit/cli/test_projects_cli.py` | CLI tests for `mp projects` |
| `tests/unit/cli/test_workspaces_cli.py` | CLI tests for `mp workspaces` |
| `tests/unit/cli/test_context_cli.py` | CLI tests for `mp context` |

### Modified Files

| File | Changes |
|------|---------|
| `_internal/config.py` | Add `resolve_session()`, v2 config support, credential/project/context CRUD, migration |
| `_internal/api_client.py` | Accept `ResolvedSession` in constructor, add `with_project()`, add `me()` endpoint |
| `workspace.py` | New constructor paths (`credential`, `session`), `switch_project()`, `switch_workspace()`, `discover_projects()`, `discover_workspaces()`, `me()` |
| `auth.py` | Re-export new public types (`AuthCredential`, `ProjectContext`, `ResolvedSession`) |
| `__init__.py` | Export new public types |
| `cli/main.py` | Register new command groups, add `--credential`/`--project` global options |
| `cli/utils.py` | Update `get_workspace()` to use `resolve_session()` |
| `cli/commands/auth.py` | Simplify `add` (drop required `--project`), add `migrate` command |
| `_internal/auth/storage.py` | Add /me cache file management to `OAuthStorage` |
| `exceptions.py` | Add `ProjectNotFoundError` |

---

## 12. Implementation Phases

### Phase A: Foundation Types (no behavior changes)

1. Create `auth_credential.py` with `AuthCredential`, `CredentialType`, `ProjectContext`, `ResolvedSession`
2. Add `to_resolved_session()` to existing `Credentials`
3. Write comprehensive tests for all new types
4. Verify `mypy --strict` passes
5. Verify `just check` passes (no regressions)

### Phase B: /me Integration

1. Create `me.py` with `MeResponse`, `MeOrgInfo`, `MeProjectInfo`, `MeWorkspaceInfo`
2. Implement `MeCache` with TTL-based disk persistence
3. Implement `MeService` with fetch/cache logic
4. Add `me()` method to `MixpanelAPIClient`
5. Write tests with mocked HTTP responses
6. Extend `OAuthStorage` to manage /me cache files

### Phase C: Config v2

1. Add v2 schema detection (`config_version` check)
2. Implement `resolve_session()` alongside existing `resolve_credentials()`
3. Add credential CRUD methods (`list_credentials`, `add_credential`, `remove_credential`)
4. Add project alias CRUD methods
5. Add active context management (`get_active_context`, `set_active_*`)
6. Implement `migrate_v1_to_v2()` with backup
7. Write comprehensive tests including round-trip migration

### Phase D: API Client Adaptation

1. Make `MixpanelAPIClient.__init__` accept `Credentials | ResolvedSession`
2. Add `with_project()` factory method
3. Update internal references from `self._credentials` to `self._session`
4. Ensure ALL existing tests pass unchanged

### Phase E: Workspace Integration

1. Add new constructor paths to `Workspace` (`credential`, `session` params)
2. Implement `switch_project()`, `switch_workspace()`
3. Implement `discover_projects()`, `discover_workspaces()`, `me()`
4. Add `current_project`, `current_credential` properties
5. Ensure backward compat: `Workspace(account="name")` still works

### Phase F: CLI Commands

1. Create `mp projects` command group (list, switch, show, refresh, alias)
2. Create `mp workspaces` command group (list, switch, show)
3. Create `mp context` command group (show, switch)
4. Update `mp auth add` to drop required `--project`
5. Add `mp auth migrate` command
6. Add `mp auth status` enhancements
7. Register new commands in `main.py`
8. Add `--credential` and `--project` global options

### Phase G: Polish

1. Update `auth_manager.py` in plugin for new config schema
2. Update plugin skill to teach agents about discovery/switching
3. Property-based tests for config round-trips (Hypothesis)
4. Update CLAUDE.md and context docs
5. End-to-end manual testing against real Mixpanel API

---

## 13. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Service accounts can't call `/me` | Low (Django source shows it's supported) | High | Test with real SA credentials; fallback to explicit project_id if 403 |
| `/me` is very slow on first call | High (confirmed 2-5s) | Medium | Progress spinner in CLI; cache aggressively (24h); support `?project_id=X` filter |
| Config migration data loss | Low | High | Backup to `config.toml.v1.bak`; migration is opt-in, never forced |
| Concurrent config writes (race) | Low | Medium | Write to temp file + atomic rename (`os.replace`) |
| Breaking change in `/me` response | Low | Medium | `extra="allow"` on all Pydantic models; forward-compatible deserialization |
| Workspace constructor too complex | Medium | Low | Clear docstring with priority order; `session` param as escape hatch |
| Existing tests break | Medium | High | Phase D specifically validates all existing tests pass unchanged before proceeding |

---

## 14. Verification Plan

### Automated

1. **Unit tests:** All new types, config operations, cache logic, migration — every new function has tests
2. **Integration tests:** Mock HTTP for `/me` endpoint, full resolution pipeline with both v1 and v2 configs
3. **Property-based tests (Hypothesis):** Config round-trip (write → read = identity), migration (v1 → v2 preserves all data)
4. **CLI tests:** `invoke` runner tests for all new commands
5. **Regression:** `just check` passes at every phase (lint + typecheck + full test suite)

### Manual

1. `mp auth add` without `--project` succeeds
2. `mp projects list` shows all accessible projects from `/me`
3. `mp projects switch <id>` persists to config and is used by subsequent commands
4. `mp workspaces list` and `mp workspaces switch` work correctly
5. `mp context show` displays complete context (credential + project + workspace)
6. `mp context switch <alias>` switches everything at once
7. Existing `Workspace(account="name")` still works with v1 config (no migration needed)
8. `mp auth migrate` produces correct v2 config from real v1 config
9. OAuth login → projects list → switch → query works end-to-end
10. Env var override still takes highest priority
