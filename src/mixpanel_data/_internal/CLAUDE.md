# Internal Implementation

Private infrastructure powering mixpanel_data's complete programmable interface to Mixpanel analytics. Do not import directly—use public API from `mixpanel_data`.

## Files

| File | Purpose |
|------|---------|
| `config.py` | Configuration management, credential resolution, TOML parsing |
| `api_client.py` | HTTP client for Mixpanel API (authentication, error handling) |
| `storage.py` | DuckDB storage engine (table management, SQL execution) |
| `services/` | Domain services: DiscoveryService (events, properties, funnels, cohorts, bookmarks, lexicon), FetcherService (events, profiles), LiveQueryService (segmentation, retention, JQL) |

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

### StorageEngine (`storage.py`)
- DuckDB connection management
- Table creation with metadata tracking
- Schema introspection
- SQL query execution (DataFrame, scalar, rows)

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

## Storage Schema

Events table structure:
- `event` (VARCHAR): Event name
- `time` (TIMESTAMP): Event timestamp
- `distinct_id` (VARCHAR): User identifier
- `insert_id` (VARCHAR): Dedup key
- `properties` (JSON): All event properties

Profiles table structure:
- `distinct_id` (VARCHAR): User identifier
- `properties` (JSON): Profile properties

Metadata stored in `_metadata` table for fetch tracking.

## Testing

Use dependency injection—all components accept dependencies:

```python
config = ConfigManager(_config_path=tmp_path)
storage = StorageEngine(path=tmp_path / "test.db")
client = MixpanelAPIClient(credentials, _http_client=mock_client)
```
