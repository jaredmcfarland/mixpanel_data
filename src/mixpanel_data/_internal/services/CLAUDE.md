# Services Layer

Domain services implementing core business logic. These are internal implementation details—consume via the `Workspace` facade.

## Files

| File | Purpose |
|------|---------|
| `discovery.py` | Schema exploration (events, properties, funnels, cohorts) with caching |
| `fetcher.py` | Data ingestion from Mixpanel API → DuckDB storage |
| `live_query.py` | Real-time API queries (segmentation, funnels, retention, JQL) |

## Design Patterns

**Dependency Injection**: All services accept their dependencies (API client, storage) as constructor arguments. This enables testing with mocks.

**Lazy Initialization**: Services are created on-demand by `Workspace` when first accessed.

**Caching**: `DiscoveryService` caches schema data (events, properties, funnels) for the workspace lifetime. Call `clear_cache()` to force refresh.

**Streaming**: `FetcherService` uses iterators for memory-efficient data transfer—API returns iterator, storage consumes iterator.

## Service Responsibilities

### DiscoveryService
- Lists events, properties, property values
- Lists saved funnels and cohorts
- Gets top events (real-time, not cached)
- All results cached except `list_top_events()`

### FetcherService
- Fetches events and profiles from Export API
- Streams data to `StorageEngine` via iterators (fetch) or yields directly (stream)
- Returns `FetchResult` with metadata for fetch operations
- Supports progress callbacks for CLI

### LiveQueryService
- Executes real-time queries against Mixpanel API
- Segmentation, funnels, retention, JQL
- Event counts, property counts, insights, activity feed
- Frequency analysis, numeric aggregations
- Flows, saved reports, bookmarks, lexicon schemas

## Testing

Mock the API client and storage engine:

```python
mock_api = Mock(spec=MixpanelAPIClient)
mock_storage = Mock(spec=StorageEngine)
service = FetcherService(mock_api, mock_storage)
```
