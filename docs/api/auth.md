# Auth Module

The auth module provides credential management, configuration, and OAuth 2.0 authentication.

!!! tip "Explore on DeepWiki"
    🤖 **[Configuration Reference →](https://deepwiki.com/jaredmcfarland/mixpanel_data/7.3-configuration-reference)**

    Ask questions about credential management, ConfigManager, OAuth, or account configuration.

## Overview

```python
from mixpanel_data._internal.config import ConfigManager
from mixpanel_data.auth_types import Account, ServiceAccount

# Manage service accounts
config = ConfigManager()
config.add_account(
    "production",
    type="service_account",
    region="us",
    default_project="12345",
    username="...",
    secret="...",
)
accounts = config.list_accounts()  # list[AccountSummary]

# Inspect a single account (returns the canonical ``Account`` discriminated union)
account: Account = config.get_account("production")
if isinstance(account, ServiceAccount):
    print(f"SA {account.name} → project {account.default_project}")
```

## ConfigManager

Manages the single-schema TOML config file (`~/.mp/config.toml`) — accounts, targets, and the `[active]` session axes. Higher-level workflows (`mp account add`, `mp account use`, `mp login`) live in `mixpanel_data.accounts` and `mixpanel_data.session`.

::: mixpanel_data._internal.config.ConfigManager
    options:
      show_root_heading: true
      show_root_toc_entry: true
      members:
        - __init__
        - config_path
        - list_accounts
        - get_account
        - add_account
        - update_account
        - remove_account
        - get_active
        - set_active
        - clear_active
        - apply_target

## Authentication

Authentication is dispatched on the account variant — see the [Account discriminated union](#account-discriminated-union) below. To drive a `Workspace` with a raw OAuth bearer token, set `MP_OAUTH_TOKEN` + `MP_PROJECT_ID` + `MP_REGION` env vars and let `Workspace()` resolve them — see [Configuration → Raw OAuth Bearer Token](../getting-started/configuration.md#raw-oauth-bearer-token).

## Account (discriminated union)

`Account` is the canonical persisted representation of a configured Mixpanel account. It is a Pydantic discriminated union dispatched on the `type` field — the runtime types are the three concrete variant classes below. Use `mixpanel_data.auth_types.Account` as the type hint and `pydantic.TypeAdapter(Account)` to construct from a raw dict.

```python
from mixpanel_data.auth_types import (
    Account,
    ServiceAccount,
    OAuthBrowserAccount,
    OAuthTokenAccount,
)

account: Account = ServiceAccount(
    name="prod",
    region="us",
    default_project="12345",
    username="...",
    secret="...",
)
```

### ServiceAccount

Long-lived HTTP Basic Auth credentials.

::: mixpanel_data.auth_types.ServiceAccount
    options:
      show_root_heading: true
      show_root_toc_entry: true

### OAuthBrowserAccount

PKCE browser flow; access/refresh tokens persisted on disk under `~/.mp/oauth/`.

::: mixpanel_data.auth_types.OAuthBrowserAccount
    options:
      show_root_heading: true
      show_root_toc_entry: true

### OAuthTokenAccount

Static bearer token (CI / agents) — supplied inline or via an env var.

::: mixpanel_data.auth_types.OAuthTokenAccount
    options:
      show_root_heading: true
      show_root_toc_entry: true

## AccountSummary

Read-only account metadata (no secrets) returned by `ConfigManager.list_accounts()` and `mp account list`.

::: mixpanel_data.types.AccountSummary
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
