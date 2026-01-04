"""Property-based tests for date_utils module.

Uses Hypothesis to verify invariants for split_date_range function
(feature 017-parallel-export).
"""

from __future__ import annotations

from datetime import date, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from mixpanel_data._internal.date_utils import split_date_range


# Strategy for generating valid date strings
@st.composite
def date_string(draw: st.DrawFn) -> str:
    """Generate a valid YYYY-MM-DD date string."""
    # Use reasonable date range to avoid edge cases with very old/future dates
    d = draw(st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31)))
    return d.strftime("%Y-%m-%d")


@st.composite
def date_range(draw: st.DrawFn) -> tuple[str, str]:
    """Generate a valid (from_date, to_date) pair where from_date <= to_date."""
    start = draw(st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 6, 30)))
    # End date is same or up to 365 days after start
    offset = draw(st.integers(min_value=0, max_value=365))
    end = start + timedelta(days=offset)
    return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))


class TestSplitDateRangeProperties:
    """Property-based tests for split_date_range."""

    @given(
        dates=date_range(),
        chunk_days=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=100)
    def test_chunks_cover_full_range(
        self, dates: tuple[str, str], chunk_days: int
    ) -> None:
        """Property: All chunks together should cover the full date range."""
        from_date, to_date = dates
        chunks = split_date_range(from_date, to_date, chunk_days=chunk_days)

        # First chunk starts at from_date
        assert chunks[0][0] == from_date

        # Last chunk ends at to_date
        assert chunks[-1][1] == to_date

    @given(
        dates=date_range(),
        chunk_days=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=100)
    def test_chunks_are_non_overlapping(
        self, dates: tuple[str, str], chunk_days: int
    ) -> None:
        """Property: Chunks should not overlap."""
        from_date, to_date = dates
        chunks = split_date_range(from_date, to_date, chunk_days=chunk_days)

        for i in range(len(chunks) - 1):
            current_end = date.fromisoformat(chunks[i][1])
            next_start = date.fromisoformat(chunks[i + 1][0])
            # There should be exactly 1 day gap between chunks
            assert next_start - current_end == timedelta(days=1)

    @given(
        dates=date_range(),
        chunk_days=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=100)
    def test_chunks_are_contiguous(
        self, dates: tuple[str, str], chunk_days: int
    ) -> None:
        """Property: Chunks should be contiguous (no gaps)."""
        from_date, to_date = dates
        chunks = split_date_range(from_date, to_date, chunk_days=chunk_days)

        for i in range(len(chunks) - 1):
            current_end = date.fromisoformat(chunks[i][1])
            next_start = date.fromisoformat(chunks[i + 1][0])
            # Next chunk should start day after current chunk ends
            assert next_start == current_end + timedelta(days=1)

    @given(
        dates=date_range(),
        chunk_days=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=100)
    def test_chunk_sizes_respect_max(
        self, dates: tuple[str, str], chunk_days: int
    ) -> None:
        """Property: No chunk should be larger than chunk_days."""
        from_date, to_date = dates
        chunks = split_date_range(from_date, to_date, chunk_days=chunk_days)

        for chunk_start, chunk_end in chunks:
            start = date.fromisoformat(chunk_start)
            end = date.fromisoformat(chunk_end)
            chunk_size = (end - start).days + 1  # Inclusive
            assert chunk_size <= chunk_days

    @given(
        dates=date_range(),
        chunk_days=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=100)
    def test_at_least_one_chunk(self, dates: tuple[str, str], chunk_days: int) -> None:
        """Property: Always returns at least one chunk."""
        from_date, to_date = dates
        chunks = split_date_range(from_date, to_date, chunk_days=chunk_days)

        assert len(chunks) >= 1

    @given(
        dates=date_range(),
        chunk_days=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=100)
    def test_chunk_dates_are_valid(
        self, dates: tuple[str, str], chunk_days: int
    ) -> None:
        """Property: All chunk dates are valid and parseable."""
        from_date, to_date = dates
        chunks = split_date_range(from_date, to_date, chunk_days=chunk_days)

        for chunk_start, chunk_end in chunks:
            # Should not raise
            start = date.fromisoformat(chunk_start)
            end = date.fromisoformat(chunk_end)
            # End should be >= start within each chunk
            assert end >= start

    @given(
        dates=date_range(),
        chunk_days=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=100)
    def test_chunks_within_original_range(
        self, dates: tuple[str, str], chunk_days: int
    ) -> None:
        """Property: All chunk dates fall within original range."""
        from_date, to_date = dates
        original_start = date.fromisoformat(from_date)
        original_end = date.fromisoformat(to_date)

        chunks = split_date_range(from_date, to_date, chunk_days=chunk_days)

        for chunk_start, chunk_end in chunks:
            start = date.fromisoformat(chunk_start)
            end = date.fromisoformat(chunk_end)
            assert start >= original_start
            assert end <= original_end

    @given(
        dates=date_range(),
        chunk_days=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=100)
    def test_total_days_equals_range_days(
        self, dates: tuple[str, str], chunk_days: int
    ) -> None:
        """Property: Sum of chunk days equals original range days."""
        from_date, to_date = dates
        original_start = date.fromisoformat(from_date)
        original_end = date.fromisoformat(to_date)
        expected_days = (original_end - original_start).days + 1  # Inclusive

        chunks = split_date_range(from_date, to_date, chunk_days=chunk_days)

        total_days = sum(
            (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
            for start, end in chunks
        )
        assert total_days == expected_days

    @given(dates=date_range())
    @settings(max_examples=100)
    def test_default_chunk_size_is_seven(self, dates: tuple[str, str]) -> None:
        """Property: Default chunk size produces chunks <= 7 days."""
        from_date, to_date = dates
        chunks = split_date_range(from_date, to_date)

        for chunk_start, chunk_end in chunks:
            start = date.fromisoformat(chunk_start)
            end = date.fromisoformat(chunk_end)
            chunk_size = (end - start).days + 1
            assert chunk_size <= 7

    @given(d=date_string())
    @settings(max_examples=50)
    def test_single_day_range_returns_single_chunk(self, d: str) -> None:
        """Property: Same start and end date returns single chunk."""
        chunks = split_date_range(d, d)

        assert len(chunks) == 1
        assert chunks[0] == (d, d)


class TestSplitDateRangeChunkCountProperties:
    """Properties related to number of chunks."""

    @given(
        dates=date_range(),
        chunk_days=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=100)
    def test_chunk_count_is_ceiling_division(
        self, dates: tuple[str, str], chunk_days: int
    ) -> None:
        """Property: Number of chunks is ceiling(total_days / chunk_days)."""
        from_date, to_date = dates
        original_start = date.fromisoformat(from_date)
        original_end = date.fromisoformat(to_date)
        total_days = (original_end - original_start).days + 1  # Inclusive

        chunks = split_date_range(from_date, to_date, chunk_days=chunk_days)

        expected_chunks = (
            total_days + chunk_days - 1
        ) // chunk_days  # Ceiling division
        assert len(chunks) == expected_chunks

    @given(
        start=st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 1, 1)),
        num_chunks=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=50)
    def test_exact_multiple_produces_even_chunks(
        self, start: date, num_chunks: int
    ) -> None:
        """Property: Range that is exact multiple of chunk size produces even chunks."""
        chunk_days = 7
        total_days = num_chunks * chunk_days
        end = start + timedelta(days=total_days - 1)

        from_date = start.strftime("%Y-%m-%d")
        to_date = end.strftime("%Y-%m-%d")

        chunks = split_date_range(from_date, to_date, chunk_days=chunk_days)

        assert len(chunks) == num_chunks
        # All chunks should be exactly chunk_days
        for chunk_start, chunk_end in chunks:
            s = date.fromisoformat(chunk_start)
            e = date.fromisoformat(chunk_end)
            assert (e - s).days + 1 == chunk_days
