"""Unit tests for date_utils module.

Tests for split_date_range function used for parallel fetch
chunking (feature 017-parallel-export).
"""

from __future__ import annotations

import pytest

from mixpanel_data._internal.date_utils import split_date_range


class TestSplitDateRange:
    """Tests for split_date_range function."""

    def test_split_single_day_range(self) -> None:
        """Single day range returns one chunk."""
        chunks = split_date_range("2024-01-01", "2024-01-01")

        assert len(chunks) == 1
        assert chunks[0] == ("2024-01-01", "2024-01-01")

    def test_split_range_smaller_than_chunk_size(self) -> None:
        """Range smaller than chunk size returns single chunk."""
        chunks = split_date_range("2024-01-01", "2024-01-05", chunk_days=7)

        assert len(chunks) == 1
        assert chunks[0] == ("2024-01-01", "2024-01-05")

    def test_split_range_equal_to_chunk_size(self) -> None:
        """Range exactly equal to chunk size returns single chunk."""
        chunks = split_date_range("2024-01-01", "2024-01-07", chunk_days=7)

        assert len(chunks) == 1
        assert chunks[0] == ("2024-01-01", "2024-01-07")

    def test_split_range_into_two_chunks(self) -> None:
        """Range slightly larger than chunk size splits into two chunks."""
        chunks = split_date_range("2024-01-01", "2024-01-08", chunk_days=7)

        assert len(chunks) == 2
        assert chunks[0] == ("2024-01-01", "2024-01-07")
        assert chunks[1] == ("2024-01-08", "2024-01-08")

    def test_split_range_into_multiple_chunks(self) -> None:
        """Large range splits into multiple 7-day chunks."""
        # 30 days: Jan 1-7, Jan 8-14, Jan 15-21, Jan 22-28, Jan 29-30
        chunks = split_date_range("2024-01-01", "2024-01-30", chunk_days=7)

        assert len(chunks) == 5
        assert chunks[0] == ("2024-01-01", "2024-01-07")
        assert chunks[1] == ("2024-01-08", "2024-01-14")
        assert chunks[2] == ("2024-01-15", "2024-01-21")
        assert chunks[3] == ("2024-01-22", "2024-01-28")
        assert chunks[4] == ("2024-01-29", "2024-01-30")

    def test_split_range_exact_multiple_of_chunk_size(self) -> None:
        """Range that is exact multiple of chunk size splits evenly."""
        # 21 days = 3 chunks of 7 days
        chunks = split_date_range("2024-01-01", "2024-01-21", chunk_days=7)

        assert len(chunks) == 3
        assert chunks[0] == ("2024-01-01", "2024-01-07")
        assert chunks[1] == ("2024-01-08", "2024-01-14")
        assert chunks[2] == ("2024-01-15", "2024-01-21")

    def test_split_range_custom_chunk_size(self) -> None:
        """Custom chunk size is respected."""
        chunks = split_date_range("2024-01-01", "2024-01-15", chunk_days=5)

        assert len(chunks) == 3
        assert chunks[0] == ("2024-01-01", "2024-01-05")
        assert chunks[1] == ("2024-01-06", "2024-01-10")
        assert chunks[2] == ("2024-01-11", "2024-01-15")

    def test_split_range_one_day_chunks(self) -> None:
        """Chunk size of 1 creates one chunk per day."""
        chunks = split_date_range("2024-01-01", "2024-01-03", chunk_days=1)

        assert len(chunks) == 3
        assert chunks[0] == ("2024-01-01", "2024-01-01")
        assert chunks[1] == ("2024-01-02", "2024-01-02")
        assert chunks[2] == ("2024-01-03", "2024-01-03")

    def test_split_range_across_month_boundary(self) -> None:
        """Ranges crossing month boundaries are handled correctly."""
        chunks = split_date_range("2024-01-28", "2024-02-05", chunk_days=7)

        assert len(chunks) == 2
        assert chunks[0] == ("2024-01-28", "2024-02-03")
        assert chunks[1] == ("2024-02-04", "2024-02-05")

    def test_split_range_across_year_boundary(self) -> None:
        """Ranges crossing year boundaries are handled correctly."""
        chunks = split_date_range("2023-12-28", "2024-01-05", chunk_days=7)

        assert len(chunks) == 2
        assert chunks[0] == ("2023-12-28", "2024-01-03")
        assert chunks[1] == ("2024-01-04", "2024-01-05")

    def test_split_range_leap_year_february(self) -> None:
        """Leap year February is handled correctly."""
        # 2024 is a leap year (Feb 29 exists)
        chunks = split_date_range("2024-02-25", "2024-03-05", chunk_days=7)

        assert len(chunks) == 2
        assert chunks[0] == ("2024-02-25", "2024-03-02")
        assert chunks[1] == ("2024-03-03", "2024-03-05")

    def test_split_range_non_leap_year_february(self) -> None:
        """Non-leap year February is handled correctly."""
        # 2023 is not a leap year (Feb 28 is last day)
        chunks = split_date_range("2023-02-25", "2023-03-05", chunk_days=7)

        assert len(chunks) == 2
        assert chunks[0] == ("2023-02-25", "2023-03-03")
        assert chunks[1] == ("2023-03-04", "2023-03-05")

    def test_split_range_returns_list_of_tuples(self) -> None:
        """split_date_range returns list of (from_date, to_date) tuples."""
        chunks = split_date_range("2024-01-01", "2024-01-14", chunk_days=7)

        assert isinstance(chunks, list)
        assert all(isinstance(chunk, tuple) for chunk in chunks)
        assert all(len(chunk) == 2 for chunk in chunks)

    def test_split_range_no_overlapping_chunks(self) -> None:
        """Chunks should not overlap."""
        chunks = split_date_range("2024-01-01", "2024-01-30", chunk_days=7)

        for i in range(len(chunks) - 1):
            current_end = chunks[i][1]
            next_start = chunks[i + 1][0]
            # End of current chunk should be before start of next
            assert current_end < next_start

    def test_split_range_covers_full_range(self) -> None:
        """All dates in original range are covered by chunks."""
        from_date = "2024-01-01"
        to_date = "2024-01-30"
        chunks = split_date_range(from_date, to_date, chunk_days=7)

        # First chunk starts at from_date
        assert chunks[0][0] == from_date
        # Last chunk ends at to_date
        assert chunks[-1][1] == to_date

    def test_split_range_default_chunk_size_is_seven(self) -> None:
        """Default chunk size is 7 days."""
        chunks = split_date_range("2024-01-01", "2024-01-08")

        assert len(chunks) == 2
        assert chunks[0] == ("2024-01-01", "2024-01-07")
        assert chunks[1] == ("2024-01-08", "2024-01-08")

    def test_split_range_invalid_date_format(self) -> None:
        """Invalid date format raises ValueError."""
        with pytest.raises(ValueError):
            split_date_range("01-01-2024", "2024-01-07")

        with pytest.raises(ValueError):
            split_date_range("2024-01-01", "Jan 7, 2024")

    def test_split_range_from_date_after_to_date(self) -> None:
        """from_date after to_date raises ValueError."""
        with pytest.raises(ValueError, match="from_date.*must be.*before.*to_date"):
            split_date_range("2024-01-15", "2024-01-01")

    def test_split_range_invalid_chunk_size(self) -> None:
        """chunk_days must be positive integer."""
        with pytest.raises(ValueError, match="chunk_days must be positive"):
            split_date_range("2024-01-01", "2024-01-07", chunk_days=0)

        with pytest.raises(ValueError, match="chunk_days must be positive"):
            split_date_range("2024-01-01", "2024-01-07", chunk_days=-1)

    def test_split_range_large_range(self) -> None:
        """Large date range (90+ days) splits correctly."""
        # 92 days: Oct 1 - Dec 31
        chunks = split_date_range("2024-10-01", "2024-12-31", chunk_days=7)

        # 92 days / 7 days per chunk = ~14 chunks
        assert len(chunks) == 14  # 13 full weeks + 1 partial

        # Verify coverage
        assert chunks[0][0] == "2024-10-01"
        assert chunks[-1][1] == "2024-12-31"

    def test_split_range_100_days(self) -> None:
        """100 day range splits into expected number of chunks."""
        # 100 days
        chunks = split_date_range("2024-01-01", "2024-04-09", chunk_days=7)

        # 100 days / 7 = 14.28... -> 15 chunks
        assert len(chunks) == 15


class TestSplitDateRangeEdgeCases:
    """Edge case tests for split_date_range."""

    def test_split_range_very_large_chunk_size(self) -> None:
        """Chunk size larger than range returns single chunk."""
        chunks = split_date_range("2024-01-01", "2024-01-10", chunk_days=100)

        assert len(chunks) == 1
        assert chunks[0] == ("2024-01-01", "2024-01-10")

    def test_split_range_preserves_date_format(self) -> None:
        """Output dates preserve YYYY-MM-DD format."""
        chunks = split_date_range("2024-01-01", "2024-01-14", chunk_days=7)

        for from_date, to_date in chunks:
            assert len(from_date) == 10
            assert len(to_date) == 10
            assert from_date[4] == "-" and from_date[7] == "-"
            assert to_date[4] == "-" and to_date[7] == "-"
