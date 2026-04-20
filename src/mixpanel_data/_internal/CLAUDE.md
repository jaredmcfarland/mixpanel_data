# Internal Implementation

Private infrastructure powering mixpanel_data's complete programmable interface to Mixpanel analytics. Do not import directly—use public API from `mixpanel_data`.

## Files

| File | Purpose |
|------|---------|
| `config.py` | Configuration management, credential resolution, TOML parsing |
| `api_client.py` | HTTP client for Mixpanel API (authentication, error handling) |
| `query/` | Query engine builders and validators (user_builders.py, user_validators.py) |
| `services/` | Domain services: DiscoveryService (events, properties, funnels, cohorts, bookmarks, lexicon), LiveQueryService (segmentation, retention, JQL) |

## Key Classes

### ConfigManager (`config.py`)
- Manages `~/.mp/config.toml`
- Resolves credentials (env vars → named account → default)
- CRUD for named accounts
- Thread-safe file operations

### Credentials (`config.py`)
- Immutable credential container
- Uses `SecretStr` for secret values
- Fields: username, secret, project_id, region

### MixpanelAPIClient (`api_client.py`)
- HTTP client using httpx
- Basic auth with service account credentials
- Region-aware base URLs (us, eu, in)
- Automatic error handling → exception mapping

## Credential Resolution Order

1. Environment variables — either service-account vars (`MP_USERNAME` + `MP_SECRET` + `MP_PROJECT_ID` + `MP_REGION`) or OAuth-token vars (`MP_OAUTH_TOKEN` + `MP_PROJECT_ID` + `MP_REGION`); service-account wins when both sets are complete
2. Auth bridge file (`MP_AUTH_FILE` or `~/.claude/mixpanel/auth.json`)
3. OAuth tokens from local storage (`~/.mp/oauth/`) — only when no `account` requested
4. Named account (if `account` parameter specified)
5. Default account from config file

See `ConfigManager.resolve_credentials` for the authoritative chain.

## Error Handling

`MixpanelAPIClient` maps HTTP errors to exceptions:
- 401 → `AuthenticationError`
- 429 → `RateLimitError`
- 400 → `QueryError`
- 5xx → `ServerError`

All exceptions include request/response context for debugging.

## Testing

Use dependency injection—all components accept dependencies:

```python
config = ConfigManager(_config_path=tmp_path)
client = MixpanelAPIClient(credentials, _http_client=mock_client)
```
