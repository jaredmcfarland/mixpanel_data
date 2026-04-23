# Configuration

mixpanel_data supports three authentication methods: **Service Accounts** (Basic Auth) for server-side automation, **OAuth 2.0 PKCE** for interactive browser login, and **raw OAuth bearer tokens** for non-interactive contexts like CI or AI agents. All three integrate with the same credential resolution chain.

!!! tip "Explore on DeepWiki"
    🤖 **[Authentication Setup →](https://deepwiki.com/jaredmcfarland/mixpanel_data/2.2-authentication-setup)**

    Ask questions about service accounts, OAuth, environment variables, or multi-account configuration.

## Authentication Methods

| Method | Best For | How It Works |
|--------|----------|--------------|
| **Service Account** (Basic Auth) | Scripts, CI/CD, automation | Username + secret from env vars or config file |
| **OAuth 2.0** (PKCE) | Interactive use, personal access | Browser-based login, tokens stored locally |
| **Raw OAuth Bearer Token** | CI, agents, ephemeral environments | Pre-obtained access token injected via env vars; no browser, no local storage |

Service accounts are the default and work everywhere. OAuth PKCE is ideal when you want to authenticate as yourself without managing service account credentials. Raw bearer tokens are the right choice when a managed OAuth client (e.g., a Claude Code plugin or CI pipeline) hands you a token and you cannot run the browser flow.

## Environment Variables

Set these environment variables to configure credentials:

| Variable | Description | Required |
|----------|-------------|----------|
| `MP_USERNAME` | Service account username | Yes (Basic Auth) |
| `MP_SECRET` | Service account secret | Yes (Basic Auth) |
| `MP_OAUTH_TOKEN` | Raw OAuth 2.0 bearer token (alternative to service account) | Yes (Bearer) |
| `MP_PROJECT_ID` | Mixpanel project ID | Yes |
| `MP_REGION` | Data residency region (`us`, `eu`, `in`) | No (default: `us`) |
| `MP_WORKSPACE_ID` | Workspace ID for App API operations | No |
| `MP_CONFIG_PATH` | Override config file location | No |
| `MP_ACCOUNT` | Account name to use from config file | No |

### Service Account (Basic Auth)

```bash
export MP_USERNAME="sa_abc123..."
export MP_SECRET="your-secret-here"
export MP_PROJECT_ID="12345"
export MP_REGION="us"
```

### Raw OAuth Bearer Token

For non-interactive contexts (CI, agents) that already hold an OAuth 2.0 access token:

```bash
export MP_OAUTH_TOKEN="<bearer-token>"
export MP_PROJECT_ID="12345"
export MP_REGION="us"  # or "eu", "in"
```

The library sends `Authorization: Bearer <token>` on every Mixpanel endpoint. Tokens injected this way are not persisted (no refresh capability — pass a fresh token when the previous one expires).

!!! note "Precedence when both are set"
    The full service-account env-var set (`MP_USERNAME` + `MP_SECRET` + `MP_PROJECT_ID` + `MP_REGION`) takes precedence when both sets are complete, so adding `MP_OAUTH_TOKEN` to a shell that already exports the service-account vars is safe — the bearer token is silently ignored and a debug-level log records the choice.

## Config File

For persistent credential storage, use the config file at `~/.mp/config.toml`:

```toml
default = "production"

[accounts.production]
username = "sa_abc123..."
secret = "..."
project_id = "12345"
region = "us"

[accounts.staging]
username = "sa_xyz789..."
secret = "..."
project_id = "67890"
region = "eu"

[accounts.development]
username = "sa_dev456..."
secret = "..."
project_id = "11111"
region = "us"
```

### Managing Accounts with CLI

Add a new account:

```bash
# Interactive prompt (secure, recommended)
mp auth add production \
    --username sa_abc123... \
    --project 12345 \
    --region us
# You'll be prompted for the secret with hidden input
```

For CI/CD environments, provide the secret via environment variable or stdin:

```bash
# Via environment variable
MP_SECRET=your-secret mp auth add production --username sa_abc123... --project 12345

# Via stdin
echo "$SECRET" | mp auth add production --username sa_abc123... --project 12345 --secret-stdin
```

List configured accounts:

```bash
mp auth list
```

Switch the default account:

```bash
mp auth switch staging
```

Remove an account:

```bash
mp auth remove development
```

Show account details (secrets hidden):

```bash
mp auth show production
```

### Managing Accounts with Python

```python
from mixpanel_data._internal.config import ConfigManager

config = ConfigManager()

# Add account
config.add_account(
    name="production",
    username="sa_abc123...",
    secret="your-secret",
    project_id="12345",
    region="us"
)

# List accounts
accounts = config.list_accounts()
for account in accounts:
    print(f"{account.name}: project {account.project_id} ({account.region})")

# Set default
config.set_default("production")

# Remove account
config.remove_account("old_account")
```

## OAuth Authentication

OAuth 2.0 with PKCE provides browser-based login without managing service account credentials. Tokens are stored locally per region.

### Login

```bash
# Login to your default region
mp auth login

# Login to a specific region and project
mp auth login --region eu --project-id 12345
```

This opens your browser for Mixpanel authorization. After approval, tokens are saved to `~/.mp/oauth/{region}/`.

### Check Status

```bash
mp auth status
```

Shows authentication state for each region (us, eu, in), including token expiry and scope.

### Get a Token

```bash
# Output raw access token (useful for piping to other tools)
mp auth token

# Use with curl
curl -H "Authorization: Bearer $(mp auth token)" https://mixpanel.com/api/app/...
```

### Logout

```bash
# Logout from a specific region
mp auth logout --region us

# Logout from all regions
mp auth logout
```

### Token Storage

OAuth tokens are stored as JSON files:

```
~/.mp/oauth/
├── tokens_us.json         # Access/refresh tokens, expiry, scope
├── client_us.json         # Dynamic client registration data
├── tokens_eu.json
├── client_eu.json
├── tokens_in.json
└── client_in.json
```

Tokens are automatically refreshed when expired. The client registration is cached per region.

## Credential Resolution Order

When creating a Workspace, credentials are resolved in this order:

1. **Environment variables** — either the service-account quad (`MP_USERNAME` + `MP_SECRET` + `MP_PROJECT_ID` + `MP_REGION`) or the OAuth-token triple (`MP_OAUTH_TOKEN` + `MP_PROJECT_ID` + `MP_REGION`). The service-account quad takes precedence when both sets are complete.
2. **Auth bridge file** — `MP_AUTH_FILE` or `~/.claude/mixpanel/auth.json` (for Claude Cowork environments).
3. **OAuth tokens from local storage** — Valid (non-expired) tokens from `~/.mp/oauth/`, populated by `mp auth login`.
4. **Named account** — `Workspace(account="staging")` or `MP_ACCOUNT=staging`.
5. **Default account** — The account marked as `default` in `config.toml`.

If a complete env-var set is present, it always wins. Otherwise the chain falls through bridge file → stored OAuth tokens → named or default config account.

Example showing resolution:

```python
import mixpanel_data as mp

# Uses environment variables (either set), then bridge file, then
# stored OAuth tokens, then config file
ws = mp.Workspace()

# Uses named account from config file (skips OAuth and bridge)
ws = mp.Workspace(account="staging")
```

## Data Residency Regions

Mixpanel stores data in regional data centers. Use the correct region for your project:

| Region | Code | API Endpoint |
|--------|------|--------------|
| United States | `us` | `mixpanel.com` |
| European Union | `eu` | `eu.mixpanel.com` |
| India | `in` | `in.mixpanel.com` |

!!! warning "Region Mismatch"
    Using the wrong region will result in authentication errors or empty data.

## Workspace ID

Some App API endpoints are scoped to a workspace. You can set a workspace ID globally:

```bash
# CLI: global option
mp --workspace-id 123 inspect events

# Or via environment variable
export MP_WORKSPACE_ID=123
```

```python
import mixpanel_data as mp

# Set at construction
ws = mp.Workspace(workspace_id=123)

# Or set later
ws.set_workspace_id(123)

# Auto-discover (uses default workspace)
ws_id = ws.resolve_workspace_id()
```

If no workspace ID is set, workspace-scoped endpoints will auto-discover by listing available workspaces and selecting the default.

## Next Steps

- [Streaming Data](../guide/streaming.md) — Stream events and profiles
- [API Reference](../api/index.md) — Complete API documentation
