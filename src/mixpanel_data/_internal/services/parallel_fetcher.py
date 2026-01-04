"""Parallel Fetcher Service for concurrent Mixpanel data export.

Implements multi-threaded event fetching with producer-consumer pattern
to handle DuckDB's single-writer constraint (feature 017-parallel-export).
"""

from __future__ import annotations

import logging
import queue
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from mixpanel_data._internal.date_utils import split_date_range
from mixpanel_data._internal.rate_limiter import RateLimiter
from mixpanel_data.types import (
    BatchProgress,
    ParallelFetchResult,
    TableMetadata,
)

if TYPE_CHECKING:
    from mixpanel_data._internal.api_client import MixpanelAPIClient
    from mixpanel_data._internal.storage import StorageEngine

_logger = logging.getLogger(__name__)

# Sentinel value to signal writer thread to stop
_STOP_SENTINEL = object()

# Reserved keys that _transform_event extracts from properties.
_RESERVED_EVENT_KEYS = frozenset({"distinct_id", "time", "$insert_id"})


def _transform_event(event: dict[str, Any]) -> dict[str, Any]:
    """Transform API event to storage format.

    Args:
        event: Raw event from Mixpanel Export API with 'event' and 'properties' keys.

    Returns:
        Transformed event dict with event_name, event_time, distinct_id,
        insert_id, and properties keys.
    """
    properties = event.get("properties", {})

    # Extract and remove standard fields from properties (shallow copy to avoid mutation)
    remaining_props = dict(properties)
    distinct_id = remaining_props.pop("distinct_id", "")
    event_time_raw = remaining_props.pop("time", 0)
    insert_id = remaining_props.pop("$insert_id", None)

    # Convert Unix timestamp to datetime
    event_time = datetime.fromtimestamp(event_time_raw, tz=UTC)

    # Generate UUID if $insert_id is missing
    if insert_id is None:
        insert_id = str(uuid.uuid4())

    return {
        "event_name": event.get("event", ""),
        "event_time": event_time,
        "distinct_id": distinct_id,
        "insert_id": insert_id,
        "properties": remaining_props,
    }


class ParallelFetcherService:
    """Parallel fetcher for concurrent Mixpanel event export.

    Splits date ranges into chunks and fetches them in parallel using
    ThreadPoolExecutor. Uses a producer-consumer pattern with a queue
    to serialize DuckDB writes (single-writer constraint).

    Attributes:
        _api_client: Mixpanel API client for fetching events.
        _storage: DuckDB storage engine for persisting data.
        _default_max_workers: Default number of concurrent fetch threads.
        _chunk_days: Number of days per chunk for date range splitting.

    Example:
        ```python
        fetcher = ParallelFetcherService(api_client, storage)
        result = fetcher.fetch_events(
            name="events",
            from_date="2024-01-01",
            to_date="2024-03-31",
            max_workers=10,
        )
        print(f"Fetched {result.total_rows} rows in {result.duration_seconds}s")
        ```
    """

    def __init__(
        self,
        api_client: MixpanelAPIClient,
        storage: StorageEngine,
    ) -> None:
        """Initialize the parallel fetcher service.

        Args:
            api_client: Authenticated Mixpanel API client.
            storage: DuckDB storage engine for persisting data.
        """
        self._api_client = api_client
        self._storage = storage
        self._default_max_workers = 10
        self._chunk_days = 7

    def fetch_events(
        self,
        name: str,
        from_date: str,
        to_date: str,
        *,
        events: list[str] | None = None,
        where: str | None = None,
        max_workers: int | None = None,
        on_batch_complete: Callable[[BatchProgress], None] | None = None,
        append: bool = False,
        batch_size: int = 1000,
    ) -> ParallelFetchResult:
        """Fetch events in parallel and store in local database.

        Splits the date range into chunks and fetches them concurrently.
        Uses a producer-consumer pattern to serialize DuckDB writes.

        Args:
            name: Table name to create or append to.
            from_date: Start date (YYYY-MM-DD, inclusive).
            to_date: End date (YYYY-MM-DD, inclusive).
            events: Optional list of event names to filter.
            where: Optional filter expression.
            max_workers: Maximum concurrent fetch threads. Defaults to 10.
            on_batch_complete: Callback invoked when each batch completes.
            append: If True, append to existing table. If False (default), create new.
            batch_size: Number of rows per INSERT/COMMIT cycle.

        Returns:
            ParallelFetchResult with aggregated statistics and any failures.

        Raises:
            TableExistsError: If table exists and append=False.
            TableNotFoundError: If table doesn't exist and append=True.
        """
        start_time = datetime.now(UTC)
        workers = max_workers or self._default_max_workers

        # Split date range into chunks
        chunks = split_date_range(from_date, to_date, chunk_days=self._chunk_days)
        total_batches = len(chunks)

        _logger.info(
            "Starting parallel fetch: %d chunks, %d workers", total_batches, workers
        )

        # Rate limiter for concurrent API calls
        rate_limiter = RateLimiter(max_concurrent=workers)

        # Queue for serializing writes to DuckDB
        write_queue: queue.Queue[
            tuple[list[dict[str, Any]], TableMetadata, int] | object
        ] = queue.Queue()

        # Results tracking
        results_lock = threading.Lock()
        total_rows = 0
        successful_batches = 0
        failed_batches = 0
        failed_date_ranges: list[tuple[str, str]] = []
        table_created = False

        def fetch_chunk(
            chunk_from: str,
            chunk_to: str,
            batch_idx: int,
        ) -> None:
            """Fetch a single date range chunk."""
            nonlocal total_rows, successful_batches, failed_batches

            try:
                with rate_limiter.acquire():
                    # Fetch events from API
                    events_iter = self._api_client.export_events(
                        from_date=chunk_from,
                        to_date=chunk_to,
                        events=events,
                        where=where,
                    )

                    # Transform and collect events
                    transformed = [_transform_event(e) for e in events_iter]
                    rows = len(transformed)

                    # Create metadata for this batch
                    metadata = TableMetadata(
                        type="events",
                        fetched_at=datetime.now(UTC),
                        from_date=chunk_from,
                        to_date=chunk_to,
                        filter_events=events,
                        filter_where=where,
                    )

                    # Queue for writing
                    write_queue.put((transformed, metadata, batch_idx))

                    # Update results
                    with results_lock:
                        total_rows += rows
                        successful_batches += 1

                    # Invoke callback
                    if on_batch_complete:
                        progress = BatchProgress(
                            from_date=chunk_from,
                            to_date=chunk_to,
                            batch_index=batch_idx,
                            total_batches=total_batches,
                            rows=rows,
                            success=True,
                            error=None,
                        )
                        on_batch_complete(progress)

                    _logger.debug(
                        "Batch %d/%d completed: %s to %s, %d rows",
                        batch_idx + 1,
                        total_batches,
                        chunk_from,
                        chunk_to,
                        rows,
                    )

            except Exception as e:
                _logger.warning(
                    "Batch %d/%d failed: %s to %s, error: %s",
                    batch_idx + 1,
                    total_batches,
                    chunk_from,
                    chunk_to,
                    str(e),
                )

                with results_lock:
                    failed_batches += 1
                    failed_date_ranges.append((chunk_from, chunk_to))

                # Invoke callback with error
                if on_batch_complete:
                    progress = BatchProgress(
                        from_date=chunk_from,
                        to_date=chunk_to,
                        batch_index=batch_idx,
                        total_batches=total_batches,
                        rows=0,
                        success=False,
                        error=str(e),
                    )
                    on_batch_complete(progress)

        def writer_thread() -> None:
            """Single writer thread for DuckDB."""
            nonlocal table_created

            while True:
                item = write_queue.get()
                if item is _STOP_SENTINEL:
                    break

                # Type narrowing: item is now the tuple type
                # Cast since we know it's not the sentinel at this point
                batch_data = item[0]  # type: ignore[index]
                batch_metadata = item[1]  # type: ignore[index]
                batch_idx = item[2]  # type: ignore[index]
                data: list[dict[str, Any]] = batch_data
                metadata: TableMetadata = batch_metadata
                idx: int = batch_idx

                if not data:
                    continue

                try:
                    if not table_created and not append:
                        self._storage.create_events_table(
                            name=name,
                            data=iter(data),
                            metadata=metadata,
                            batch_size=batch_size,
                        )
                        table_created = True
                    else:
                        self._storage.append_events_table(
                            name=name,
                            data=iter(data),
                            metadata=metadata,
                            batch_size=batch_size,
                        )
                except Exception as e:
                    _logger.error("Failed to write batch %d: %s", idx, str(e))

        # Start writer thread
        writer = threading.Thread(target=writer_thread, daemon=True)
        writer.start()

        # Submit fetch tasks to thread pool
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for idx, (chunk_from, chunk_to) in enumerate(chunks):
                future = executor.submit(fetch_chunk, chunk_from, chunk_to, idx)
                futures.append(future)

            # Wait for all fetches to complete
            for future in as_completed(futures):
                # Just wait for completion, errors handled in fetch_chunk
                try:
                    future.result()
                except Exception as e:
                    _logger.error("Unexpected error in fetch task: %s", str(e))

        # Signal writer to stop and wait
        write_queue.put(_STOP_SENTINEL)
        writer.join()

        # Calculate duration
        completed_at = datetime.now(UTC)
        duration_seconds = (completed_at - start_time).total_seconds()

        _logger.info(
            "Parallel fetch completed: %d rows, %d/%d batches successful, %.2fs",
            total_rows,
            successful_batches,
            total_batches,
            duration_seconds,
        )

        return ParallelFetchResult(
            table=name,
            total_rows=total_rows,
            successful_batches=successful_batches,
            failed_batches=failed_batches,
            failed_date_ranges=tuple(failed_date_ranges),
            duration_seconds=duration_seconds,
            fetched_at=completed_at,
        )
