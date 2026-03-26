# Exceptions

All library exceptions inherit from `MixpanelDataError`, enabling callers to catch all library errors with a single except clause.

!!! tip "Explore on DeepWiki"
    🤖 **[Error Handling Guide →](https://deepwiki.com/jaredmcfarland/mixpanel_data/7.4-error-codes-and-exceptions)**

    Ask questions about specific exceptions, error recovery patterns, or debugging strategies.

## Exception Hierarchy

```
MixpanelDataError
├── ConfigError
│   ├── AccountNotFoundError
│   └── AccountExistsError
├── APIError
│   ├── AuthenticationError
│   ├── RateLimitError
│   ├── QueryError
│   ├── ServerError
│   └── JQLSyntaxError
├── OAuthError
├── WorkspaceScopeError
├── TableExistsError
├── TableNotFoundError
├── DatabaseLockedError
└── DatabaseNotFoundError
```

## Catching Errors

```python
import mixpanel_data as mp

try:
    ws = mp.Workspace()
    result = ws.segmentation(event="Purchase", from_date="2025-01-01", to_date="2025-01-31")
except mp.AuthenticationError as e:
    print(f"Auth failed: {e.message}")
except mp.RateLimitError as e:
    print(f"Rate limited, retry after {e.retry_after}s")
except mp.OAuthError as e:
    print(f"OAuth error [{e.code}]: {e.message}")
except mp.WorkspaceScopeError as e:
    print(f"Workspace error [{e.code}]: {e.message}")
except mp.MixpanelDataError as e:
    print(f"Error [{e.code}]: {e.message}")
```

## Base Exception

::: mixpanel_data.MixpanelDataError
    options:
      show_root_heading: true
      show_root_toc_entry: true

## API Exceptions

::: mixpanel_data.APIError
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AuthenticationError
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.RateLimitError
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.QueryError
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.ServerError
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.JQLSyntaxError
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Configuration Exceptions

::: mixpanel_data.ConfigError
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AccountNotFoundError
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.AccountExistsError
    options:
      show_root_heading: true
      show_root_toc_entry: true

## OAuth Exceptions

Raised during OAuth 2.0 PKCE authentication flows.

| Error Code | Raised When |
|------------|-------------|
| `OAUTH_TOKEN_ERROR` | Token exchange fails |
| `OAUTH_REFRESH_ERROR` | Token refresh fails |
| `OAUTH_REGISTRATION_ERROR` | Dynamic client registration fails |
| `OAUTH_TIMEOUT` | Callback server times out waiting for authorization |
| `OAUTH_PORT_ERROR` | Cannot bind to a local port for the callback server |
| `OAUTH_BROWSER_ERROR` | Cannot open the authorization URL in the browser |

::: mixpanel_data.OAuthError
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Workspace Exceptions

Raised when workspace resolution fails for App API endpoints.

| Error Code | Raised When |
|------------|-------------|
| `NO_WORKSPACES` | No workspaces found for the project |
| `AMBIGUOUS_WORKSPACE` | Multiple workspaces found and none is marked as default |
| `WORKSPACE_NOT_FOUND` | Specified workspace ID does not exist |

::: mixpanel_data.WorkspaceScopeError
    options:
      show_root_heading: true
      show_root_toc_entry: true

## Storage Exceptions

Storage exceptions are raised during fetch and table operations:

| Exception | Raised When |
|-----------|-------------|
| `TableExistsError` | Fetching to an existing table without `append=True` or `--replace` |
| `TableNotFoundError` | Using `append=True` on a non-existent table |
| `DatabaseLockedError` | Another process has the database locked |
| `DatabaseNotFoundError` | Database file not found in read-only mode |

::: mixpanel_data.TableExistsError
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.TableNotFoundError
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.DatabaseLockedError
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.DatabaseNotFoundError
    options:
      show_root_heading: true
      show_root_toc_entry: true
