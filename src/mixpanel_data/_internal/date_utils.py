"""Date utilities for parallel export chunking.

Provides functions for splitting date ranges into chunks for
parallel processing (feature 017).
"""

from __future__ import annotations

from datetime import date, timedelta


def split_date_range(
    from_date: str,
    to_date: str,
    chunk_days: int = 7,
) -> list[tuple[str, str]]:
    """Split a date range into non-overlapping chunks.

    Divides a date range into chunks of up to chunk_days each, suitable
    for parallel processing. The last chunk may be smaller than chunk_days
    if the range doesn't divide evenly.

    Args:
        from_date: Start date in YYYY-MM-DD format.
        to_date: End date in YYYY-MM-DD format (inclusive).
        chunk_days: Maximum days per chunk. Defaults to 7.

    Returns:
        List of (from_date, to_date) tuples, each representing a chunk.
        Chunks are non-overlapping and contiguous.

    Raises:
        ValueError: If dates are not in YYYY-MM-DD format,
            from_date is after to_date, or chunk_days is not positive.

    Example:
        ```python
        # Split 30 days into 7-day chunks
        chunks = split_date_range("2024-01-01", "2024-01-30")
        # Returns:
        # [("2024-01-01", "2024-01-07"),
        #  ("2024-01-08", "2024-01-14"),
        #  ("2024-01-15", "2024-01-21"),
        #  ("2024-01-22", "2024-01-28"),
        #  ("2024-01-29", "2024-01-30")]

        # Custom chunk size
        chunks = split_date_range("2024-01-01", "2024-01-15", chunk_days=5)
        # Returns:
        # [("2024-01-01", "2024-01-05"),
        #  ("2024-01-06", "2024-01-10"),
        #  ("2024-01-11", "2024-01-15")]
        ```
    """
    if chunk_days <= 0:
        raise ValueError("chunk_days must be positive")

    # Parse dates
    try:
        start = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
    except ValueError as e:
        raise ValueError(
            f"Invalid date format. Expected YYYY-MM-DD, got from_date={from_date!r}, "
            f"to_date={to_date!r}"
        ) from e

    if start > end:
        raise ValueError(
            f"from_date ({from_date}) must be on or before to_date ({to_date})"
        )

    chunks: list[tuple[str, str]] = []
    current_start = start

    while current_start <= end:
        # Calculate chunk end (up to chunk_days - 1 days after start, but not past end)
        chunk_end = min(current_start + timedelta(days=chunk_days - 1), end)

        chunks.append(
            (current_start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d"))
        )

        # Move to next chunk start
        current_start = chunk_end + timedelta(days=1)

    return chunks
