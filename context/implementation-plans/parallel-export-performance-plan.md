# Parallel Export Performance Improvement Plan

## Goal
Improve performance of `export_events` operations by parallelizing requests within Mixpanel's rate limits.

**Scope**: Events only first. Profiles will follow in a subsequent PR.

## Rate Limits (from Mixpanel docs)
- **Export API**: 60 queries/hour, 3 queries/second, **100 max concurrent**

## Design Decisions

### 1. Threading: **Stay Synchronous with ThreadPoolExecutor**
- Entire codebase is 100% synchronous - introducing async would require extensive refactoring
- `concurrent.futures.ThreadPoolExecutor` is simpler than old `multiprocessing.pool.ThreadPool`
- Rate limiting straightforward with `threading.Semaphore`

### 2. Date Batching: **Fixed 7-day Chunks**
- Split date ranges into 7-day chunks for parallel fetching
- Simple, predictable, easy to understand and debug
- Example: 30-day range = 5 chunks (4x7 + 2 days)

### 3. Concurrency: **Moderate (10-20 concurrent)**
- Target 10-15 concurrent requests (balanced approach using ~15% of 100 limit)
- Provides good speedup while staying safely under limits

### 4. Storage Strategy: **Queue with Single Writer Thread**
- DuckDB requires serialized writes (single-writer constraint)
- Producer-consumer pattern: workers produce, single writer consumes
- Bounded queue provides backpressure and memory efficiency

```
[Worker 1] -\
[Worker 2] ---> [Queue (bounded)] ---> [Writer Thread] ---> [DuckDB]
...         -/
[Worker N] -/
```

### 5. API: **Optional `parallel=True` Parameter**
```python
# Existing API unchanged (backward compatible)
result = ws.fetch_events(from_date="2024-01-01", to_date="2024-01-31")

# New parallel mode
result = ws.fetch_events(
    from_date="2024-01-01",
    to_date="2024-01-31",
    parallel=True,               # Enable parallel fetching
    max_workers=10,              # Optional: default 10
    on_batch_complete=callback,  # Optional: per-batch callback
)
```

### 6. Error Handling: **Partial Success with Retry Info**
- Continue on batch failure, report partial results
- `ParallelFetchResult.failed_date_ranges` lists failed batches for retry

---

## Implementation Phases (TDD Approach)

Each phase follows strict TDD: **Write tests FIRST, then implement until tests pass.**

### Phase 1: Core Types & Rate Limiting

#### 1.1 Tests First
**Create:** `tests/unit/test_types_parallel.py`
```python
# Test BatchResult creation and immutability
# Test ParallelFetchResult creation, properties, to_dict()
# Test has_failures property
# Test failed_date_ranges property
```

**Create:** `tests/unit/test_rate_limiter.py`
```python
# Test semaphore limits concurrent access
# Test context manager acquire/release
# Test blocking when at capacity
```

#### 1.2 Implementation
**Modify:** `src/mixpanel_data/types.py`
- Add `BatchProgress`, `BatchResult`, `ParallelFetchResult` dataclasses

**Create:** `src/mixpanel_data/_internal/rate_limiter.py`
- Implement `RateLimiter` class with semaphore

#### 1.3 Verify
- Run `just test -k test_types_parallel`
- Run `just test -k test_rate_limiter`
- Run `just typecheck`

---

### Phase 2: Date Range Utilities

#### 2.1 Tests First
**Create:** `tests/unit/test_date_utils.py`
```python
# Test single day range returns single chunk
# Test 7-day range returns single chunk
# Test 8-day range returns two chunks
# Test 30-day range returns correct chunks
# Test edge case: from_date == to_date
# Test invalid date format raises ValueError
```

**Create:** `tests/unit/test_date_utils_pbt.py` (Property-Based)
```python
# Property: all chunks cover original range exactly
# Property: no gaps between chunks
# Property: no overlaps between chunks
# Property: each chunk <= chunk_days
```

#### 2.2 Implementation
**Create:** `src/mixpanel_data/_internal/date_utils.py`
```python
def split_date_range(
    from_date: str,
    to_date: str,
    chunk_days: int = 7
) -> list[tuple[str, str]]:
    """Split a date range into chunks for parallel processing."""
```

#### 2.3 Verify
- Run `just test -k test_date_utils`
- Run `just test-pbt -k test_date_utils_pbt`
- Run `just typecheck`

---

### Phase 3: Parallel Fetcher Service

#### 3.1 Tests First
**Create:** `tests/unit/test_parallel_fetcher.py`
```python
# Test fetch_events_parallel with single chunk (degrades to sequential)
# Test fetch_events_parallel with multiple chunks
# Test on_batch_complete callback is called for each batch
# Test progress_callback receives aggregated counts
# Test partial failure: some batches succeed, some fail
# Test all batches fail: returns ParallelFetchResult with all failures
# Test max_workers limits concurrency
```

**Create:** `tests/integration/test_parallel_fetcher.py`
```python
# Test end-to-end with mocked API client
# Test DuckDB receives all events in correct order
# Test memory usage stays bounded (queue backpressure)
```

#### 3.2 Implementation
**Create:** `src/mixpanel_data/_internal/services/parallel_fetcher.py`
```python
class ParallelFetcherService:
    """Parallel fetcher using producer-consumer pattern."""

    def __init__(self, api_client, storage, max_workers=10, queue_size=10): ...
    def fetch_events_parallel(self, name, from_date, to_date, **kwargs) -> ParallelFetchResult: ...
```

#### 3.3 Verify
- Run `just test -k test_parallel_fetcher`
- Run `just typecheck`
- Run `just test-cov` (ensure 90%+ coverage on new code)

---

### Phase 4: Integrate into FetcherService

#### 4.1 Tests First
**Modify:** `tests/unit/test_fetcher_service.py`
```python
# Test fetch_events with parallel=False (existing behavior unchanged)
# Test fetch_events with parallel=True delegates to ParallelFetcherService
# Test parallel=True with max_workers passes through
# Test parallel=True with on_batch_complete passes through
```

#### 4.2 Implementation
**Modify:** `src/mixpanel_data/_internal/services/fetcher.py`
- Add `parallel: bool = False` parameter
- Add `max_workers: int | None = None` parameter
- Add `on_batch_complete: Callable[[BatchProgress], None] | None = None`
- Delegate to `ParallelFetcherService` when `parallel=True`

#### 4.3 Verify
- Run `just test -k test_fetcher_service`
- Run `just typecheck`

---

### Phase 5: Workspace API

#### 5.1 Tests First
**Modify:** `tests/unit/test_workspace.py`
```python
# Test fetch_events with parallel=True
# Test fetch_events validates max_workers > 0
# Test fetch_events returns ParallelFetchResult when parallel=True
```

#### 5.2 Implementation
**Modify:** `src/mixpanel_data/workspace.py`
- Add `parallel`, `max_workers`, `on_batch_complete` to `fetch_events()`
- Validate parameters
- Pass through to FetcherService

#### 5.3 Verify
- Run `just test -k test_workspace`
- Run `just typecheck`

---

### Phase 6: CLI Integration

#### 6.1 Tests First
**Modify:** `tests/cli/test_fetch_commands.py`
```python
# Test `mp fetch events --parallel` uses parallel mode
# Test `mp fetch events --parallel --workers 5` passes workers
# Test `mp fetch events` without --parallel uses sequential (existing)
# Test progress output shows batch completion
# Test partial failure exits with non-zero code
```

#### 6.2 Implementation
**Modify:** `src/mixpanel_data/cli/commands/fetch.py`
- Add `--parallel` / `-p` flag
- Add `--workers N` option (default: 10)
- Display batch progress during execution
- Show failure summary if any batches failed

#### 6.3 Verify
- Run `just test -k test_fetch_commands`
- Run `just check` (full lint, typecheck, test suite)

---

## Key Files to Modify

| File | Changes |
|------|---------|
| `src/mixpanel_data/types.py` | Add `BatchProgress`, `BatchResult`, `ParallelFetchResult` |
| `src/mixpanel_data/_internal/rate_limiter.py` | NEW: `RateLimiter` class |
| `src/mixpanel_data/_internal/date_utils.py` | NEW: `split_date_range()` |
| `src/mixpanel_data/_internal/services/parallel_fetcher.py` | NEW: `ParallelFetcherService` |
| `src/mixpanel_data/_internal/services/fetcher.py` | Add `parallel`, `max_workers` params |
| `src/mixpanel_data/workspace.py` | Add parallel params to fetch methods |
| `src/mixpanel_data/cli/commands/fetch.py` | Add `--parallel`, `--workers` flags |

---

## Testing Strategy (TDD)

**Golden Rule**: Tests are written FIRST in each phase. Implementation only begins after tests are defined.

### Test Files Created
| Test File | Purpose |
|-----------|---------|
| `tests/unit/test_types_parallel.py` | BatchResult, ParallelFetchResult types |
| `tests/unit/test_rate_limiter.py` | RateLimiter concurrency control |
| `tests/unit/test_date_utils.py` | Date range splitting |
| `tests/unit/test_date_utils_pbt.py` | Property-based tests for date utils |
| `tests/unit/test_parallel_fetcher.py` | ParallelFetcherService unit tests |
| `tests/integration/test_parallel_fetcher.py` | End-to-end with mocked API |

### Quality Gates
- **Unit tests**: Must pass before moving to next phase
- **Coverage**: 90%+ on all new code (`just test-cov`)
- **Type checking**: `just typecheck` passes with --strict
- **Property-based**: Hypothesis tests for invariants
- **Mutation testing**: 80%+ mutation score (`just mutate-check`)

---

## Dependencies

**No new external dependencies.** Uses stdlib only:
- `concurrent.futures.ThreadPoolExecutor`
- `threading.Semaphore`, `threading.Lock`
- `queue.Queue`

---

## Rate Limiting Implementation

Moderate approach (~15% of limits for safety margin):
- **Export API**: 10-15 concurrent requests (limit is 100 concurrent)
- Uses semaphore for concurrency control

```python
class RateLimiter:
    def __init__(self, max_concurrent: int = 10) -> None:
        self._semaphore = threading.Semaphore(max_concurrent)

    @contextmanager
    def acquire(self) -> Iterator[None]:
        self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()
```

---

## Expected Performance Improvement

For a 90-day date range export:
- **Sequential**: 1 request (up to hours for large datasets)
- **Parallel (10 workers)**: ~13 chunks of 7 days each, processed in parallel
- **Speedup**: Up to 10x faster for I/O-bound exports

---

## Future Work (Out of Scope)

- **Profiles parallel fetching**: Session-based pagination requires different approach
- **Async/await**: Could provide additional performance but requires architecture change
- **Adaptive chunking**: Could optimize based on data density heuristics
