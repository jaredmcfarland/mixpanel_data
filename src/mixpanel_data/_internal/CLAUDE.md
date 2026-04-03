# Internal Implementation

Private infrastructure powering mixpanel_data's complete programmable interface to Mixpanel analytics. Do not import directly—use public API from `mixpanel_data`.

## Files

| File | Purpose |
|------|---------|
| `config.py` | Configuration management, credential resolution, TOML parsing |
| `api_client.py` | HTTP client for Mixpanel API (authentication, error handling) |
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

1. Environment variables: `MP_USERNAME`, `MP_SECRET`, `MP_PROJECT_ID`, `MP_REGION`
2. Named account (if `account` parameter specified)
3. Default account from config file

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
