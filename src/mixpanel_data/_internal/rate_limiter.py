"""Rate limiter for controlling parallel fetch concurrency.

Provides a semaphore-based rate limiter that limits the number of
concurrent operations for parallel export (feature 017).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class RateLimiter:
    """Semaphore-based rate limiter for concurrent operations.

    Limits the number of concurrent operations using a threading semaphore.
    Used by ParallelFetcherService to stay within Mixpanel's rate limits.

    Attributes:
        max_concurrent: Maximum number of concurrent operations allowed.

    Example:
        ```python
        limiter = RateLimiter(max_concurrent=10)

        def fetch_chunk(chunk: tuple[str, str]) -> list[dict]:
            with limiter.acquire():
                return api.fetch_events(chunk[0], chunk[1])

        # Multiple threads can call fetch_chunk, but only 10 will
        # execute concurrently
        ```
    """

    def __init__(self, max_concurrent: int = 10) -> None:
        """Initialize the rate limiter.

        Args:
            max_concurrent: Maximum number of concurrent operations.
                Defaults to 10 (conservative ~10% of Mixpanel's 100 limit).

        Raises:
            ValueError: If max_concurrent is not positive.
        """
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be positive")

        self._max_concurrent = max_concurrent
        self._semaphore = threading.Semaphore(max_concurrent)

    @property
    def max_concurrent(self) -> int:
        """Get the maximum concurrent operations limit.

        Returns:
            Maximum number of concurrent operations allowed.
        """
        return self._max_concurrent

    @contextmanager
    def acquire(self) -> Iterator[None]:
        """Acquire a slot for a concurrent operation.

        Context manager that acquires a semaphore slot on entry and
        releases it on exit (including on exception).

        Yields:
            None when a slot is acquired.

        Example:
            ```python
            limiter = RateLimiter(max_concurrent=5)

            with limiter.acquire():
                # This block will only execute when a slot is available
                result = expensive_operation()
            # Slot is automatically released when exiting the context
            ```
        """
        self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()
