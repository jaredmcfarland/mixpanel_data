# Configuration

mixpanel_data supports two authentication methods: **Service Accounts** (Basic Auth) for server-side automation and **OAuth 2.0** for interactive use. Both methods support multiple configuration approaches.

!!! tip "Explore on DeepWiki"
    🤖 **[Authentication Setup →](https://deepwiki.com/jaredmcfarland/mixpanel_data/2.2-authentication-setup)**

    Ask questions about service accounts, OAuth, environment variables, or multi-account configuration.

## Authentication Methods

| Method | Best For | How It Works |
|--------|----------|--------------|
| **Service Account** (Basic Auth) | Scripts, CI/CD, automation | Username + secret from env vars or config file |
| **OAuth 2.0** (PKCE) | Interactive use, personal access | Browser-based login, tokens stored locally |

Service accounts are the default and work everywhere. OAuth is ideal when you want to authenticate as yourself without managing service account credentials.

## Environment Variables

Set these environment variables to configure service account credentials:

| Variable | Description | Required |
|----------|-------------|----------|
| `MP_USERNAME` | Service account username | Yes (Basic Auth) |
| `MP_SECRET` | Service account secret | Yes (Basic Auth) |
| `MP_PROJECT_ID` | Mixpanel project ID | Yes |
| `MP_REGION` | Data residency region (`us`, `eu`, `in`) | No (default: `us`) |
| `MP_WORKSPACE_ID` | Workspace ID for App API operations | No |
| `MP_CONFIG_PATH` | Override config file location | No |
| `MP_ACCOUNT` | Account name to use from config file | No |

Example:

```bash
export MP_USERNAME="sa_abc123..."
export MP_SECRET="your-secret-here"
export MP_PROJECT_ID="12345"
export MP_REGION="us"
```

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
from mixpanel_data.auth import ConfigManager

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
├── us/
│   ├── tokens.json        # Access/refresh tokens, expiry, scope
│   └── client_info.json   # Dynamic client registration data
├── eu/
│   └── ...
└── in/
    └── ...
```

Tokens are automatically refreshed when expired. The client registration is cached per region.

## Credential Resolution Order

When creating a Workspace, credentials are resolved in this order:

1. **Environment variables** — `MP_USERNAME`, `MP_SECRET`, `MP_PROJECT_ID`, `MP_REGION` (all four required)
2. **OAuth tokens** — Valid (non-expired) tokens from `~/.mp/oauth/`
3. **Named account** — `Workspace(account="staging")` or `MP_ACCOUNT=staging`
4. **Default account** — The account marked as `default` in config.toml

If environment variables provide all four values, they take priority. Otherwise, the system checks for a valid OAuth token before falling back to config file accounts.

Example showing resolution:

```python
import mixpanel_data as mp

# Uses explicit arguments
ws = mp.Workspace(
    username="sa_...",
    secret="...",
    project_id="12345"
)

# Uses environment variables (if set), then OAuth, then config
ws = mp.Workspace()

# Uses named account from config file
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

## Workspace Path

By default, the workspace database is stored at `./mixpanel.db`. Override with:

```python
import mixpanel_data as mp

# Custom path
ws = mp.Workspace(path="./data/analytics.db")

# Ephemeral (temporary, auto-deleted)
with mp.Workspace.ephemeral() as ws:
    # ... work with data
# Database deleted on exit
```

For CLI, use the `--db` option:

```bash
mp fetch events --db ./data/my_project.db --from 2025-01-01 --to 2025-01-31
```

## Next Steps

- [Fetching Data](../guide/fetching.md) — Learn about data ingestion
- [API Reference](../api/index.md) — Complete API documentation
