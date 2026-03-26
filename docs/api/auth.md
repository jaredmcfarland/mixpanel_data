# Auth Module

The auth module provides credential management, configuration, and OAuth 2.0 authentication.

!!! tip "Explore on DeepWiki"
    🤖 **[Configuration Reference →](https://deepwiki.com/jaredmcfarland/mixpanel_data/7.3-configuration-reference)**

    Ask questions about credential management, ConfigManager, OAuth, or account configuration.

## Overview

```python
from mixpanel_data.auth import ConfigManager, Credentials, AccountInfo, AuthMethod

# Manage service accounts
config = ConfigManager()
config.add_account("production", username="...", secret="...", project_id="...", region="us")
accounts = config.list_accounts()

# Resolve credentials (checks env vars → OAuth tokens → config file)
creds = config.resolve_credentials(account="production")

# Check auth method
if creds.auth_method == AuthMethod.oauth:
    print(f"Using OAuth: {creds.auth_header()[:20]}...")
```

## ConfigManager

Manages accounts stored in the TOML config file (`~/.mp/config.toml`) and resolves credentials from multiple sources including OAuth tokens.

::: mixpanel_data.auth.ConfigManager
    options:
      show_root_heading: true
      show_root_toc_entry: true
      members:
        - __init__
        - config_path
        - resolve_credentials
        - list_accounts
        - add_account
        - remove_account
        - set_default
        - get_account

## AuthMethod

Enum for authentication method selection.

::: mixpanel_data._internal.config.AuthMethod
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Credentials

Immutable container for authentication credentials. Supports both Basic Auth (service accounts) and OAuth Bearer token authentication.

**Key fields:**

- `username`, `secret`, `project_id`, `region` — Standard credential fields
- `auth_method` — `AuthMethod.basic` (default) or `AuthMethod.oauth`
- `oauth_access_token` — OAuth access token (required when `auth_method` is `oauth`)

**Key methods:**

- `auth_header()` — Returns the appropriate `Authorization` header value (`"Basic <base64>"` or `"Bearer <token>"`)

::: mixpanel_data.auth.Credentials
    options:
      show_root_heading: true
      show_root_toc_entry: true

## AccountInfo

Account metadata (without the secret).

::: mixpanel_data.auth.AccountInfo
    options:
      show_root_heading: true
      show_root_toc_entry: true

## OAuth 2.0 Module

The OAuth module (`mixpanel_data._internal.auth`) implements the OAuth 2.0 PKCE flow for interactive authentication.

### OAuthFlow

Orchestrates the complete OAuth 2.0 PKCE login flow: dynamic client registration, browser-based authorization, token exchange, and token refresh.

```python
from mixpanel_data._internal.auth.flow import OAuthFlow
from mixpanel_data._internal.auth.storage import OAuthStorage

storage = OAuthStorage()
flow = OAuthFlow(region="us", storage=storage)

# Interactive login (opens browser)
tokens = flow.login(project_id="12345")

# Get valid token (auto-refreshes if expired)
tokens = flow.get_valid_token(region="us")
```

### OAuthTokens

Immutable model for OAuth access and refresh tokens.

**Key fields:** `access_token`, `refresh_token`, `expires_at`, `scope`, `token_type`, `project_id`

**Key methods:** `is_expired()` (includes 30-second safety buffer), `from_token_response(data, project_id)`

### OAuthClientInfo

Dynamic Client Registration metadata.

**Key fields:** `client_id`, `region`, `redirect_uri`, `scope`, `created_at`

### OAuthStorage

Manages JSON persistence of tokens and client info at `~/.mp/oauth/`.

```python
from mixpanel_data._internal.auth.storage import OAuthStorage

storage = OAuthStorage()
tokens = storage.load_tokens(region="us")
storage.delete_tokens(region="us")
storage.delete_all()  # Clear all regions
```

**Key methods:** `load_tokens(region)`, `save_tokens(tokens, region)`, `delete_tokens(region)`, `load_client_info(region)`, `save_client_info(info)`, `delete_all()`

### PkceChallenge

PKCE challenge generation (RFC 7636).

```python
from mixpanel_data._internal.auth.pkce import PkceChallenge

challenge = PkceChallenge.generate()
# challenge.verifier — URL-safe random string (43-128 chars)
# challenge.challenge — SHA256 hash, Base64URL encoded
# challenge.challenge_method — Always "S256"
```
