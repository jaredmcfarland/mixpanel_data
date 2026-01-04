"""Unit tests for parallel fetch types.

Tests for BatchProgress, BatchResult, and ParallelFetchResult dataclasses
introduced in feature 017-parallel-export.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from mixpanel_data.types import (
    BatchProgress,
    BatchResult,
    ParallelFetchResult,
)


class TestBatchProgress:
    """Tests for BatchProgress dataclass."""

    def test_create_successful_batch_progress(self) -> None:
        """BatchProgress can be created for a successful batch."""
        progress = BatchProgress(
            from_date="2024-01-01",
            to_date="2024-01-07",
            batch_index=0,
            total_batches=5,
            rows=1000,
            success=True,
            error=None,
        )

        assert progress.from_date == "2024-01-01"
        assert progress.to_date == "2024-01-07"
        assert progress.batch_index == 0
        assert progress.total_batches == 5
        assert progress.rows == 1000
        assert progress.success is True
        assert progress.error is None

    def test_create_failed_batch_progress(self) -> None:
        """BatchProgress can be created for a failed batch."""
        progress = BatchProgress(
            from_date="2024-01-08",
            to_date="2024-01-14",
            batch_index=1,
            total_batches=5,
            rows=0,
            success=False,
            error="Rate limit exceeded",
        )

        assert progress.from_date == "2024-01-08"
        assert progress.to_date == "2024-01-14"
        assert progress.batch_index == 1
        assert progress.total_batches == 5
        assert progress.rows == 0
        assert progress.success is False
        assert progress.error == "Rate limit exceeded"

    def test_batch_progress_is_frozen(self) -> None:
        """BatchProgress should be immutable (frozen dataclass)."""
        progress = BatchProgress(
            from_date="2024-01-01",
            to_date="2024-01-07",
            batch_index=0,
            total_batches=5,
            rows=1000,
            success=True,
        )

        with pytest.raises(AttributeError):
            progress.rows = 2000  # type: ignore[misc]

    def test_batch_progress_to_dict(self) -> None:
        """BatchProgress.to_dict() returns JSON-serializable dictionary."""
        progress = BatchProgress(
            from_date="2024-01-01",
            to_date="2024-01-07",
            batch_index=0,
            total_batches=5,
            rows=1000,
            success=True,
            error=None,
        )

        d = progress.to_dict()

        assert d["from_date"] == "2024-01-01"
        assert d["to_date"] == "2024-01-07"
        assert d["batch_index"] == 0
        assert d["total_batches"] == 5
        assert d["rows"] == 1000
        assert d["success"] is True
        assert d["error"] is None

        # Verify JSON serializable
        json_str = json.dumps(d)
        assert isinstance(json_str, str)

    def test_batch_progress_to_dict_with_error(self) -> None:
        """BatchProgress.to_dict() includes error message when failed."""
        progress = BatchProgress(
            from_date="2024-01-01",
            to_date="2024-01-07",
            batch_index=0,
            total_batches=5,
            rows=0,
            success=False,
            error="Connection timeout",
        )

        d = progress.to_dict()

        assert d["success"] is False
        assert d["error"] == "Connection timeout"

    def test_batch_progress_error_default_is_none(self) -> None:
        """BatchProgress error field defaults to None."""
        progress = BatchProgress(
            from_date="2024-01-01",
            to_date="2024-01-07",
            batch_index=0,
            total_batches=5,
            rows=1000,
            success=True,
        )

        assert progress.error is None


class TestBatchResult:
    """Tests for BatchResult dataclass."""

    def test_create_successful_batch_result(self) -> None:
        """BatchResult can be created for a successful batch."""
        result = BatchResult(
            from_date="2024-01-01",
            to_date="2024-01-07",
            rows=1000,
            success=True,
            error=None,
        )

        assert result.from_date == "2024-01-01"
        assert result.to_date == "2024-01-07"
        assert result.rows == 1000
        assert result.success is True
        assert result.error is None

    def test_create_failed_batch_result(self) -> None:
        """BatchResult can be created for a failed batch."""
        result = BatchResult(
            from_date="2024-01-08",
            to_date="2024-01-14",
            rows=0,
            success=False,
            error="API error: 500",
        )

        assert result.from_date == "2024-01-08"
        assert result.to_date == "2024-01-14"
        assert result.rows == 0
        assert result.success is False
        assert result.error == "API error: 500"

    def test_batch_result_is_frozen(self) -> None:
        """BatchResult should be immutable (frozen dataclass)."""
        result = BatchResult(
            from_date="2024-01-01",
            to_date="2024-01-07",
            rows=1000,
            success=True,
        )

        with pytest.raises(AttributeError):
            result.rows = 2000  # type: ignore[misc]

    def test_batch_result_to_dict(self) -> None:
        """BatchResult.to_dict() returns JSON-serializable dictionary."""
        result = BatchResult(
            from_date="2024-01-01",
            to_date="2024-01-07",
            rows=1000,
            success=True,
            error=None,
        )

        d = result.to_dict()

        assert d["from_date"] == "2024-01-01"
        assert d["to_date"] == "2024-01-07"
        assert d["rows"] == 1000
        assert d["success"] is True
        assert d["error"] is None

        # Verify JSON serializable
        json_str = json.dumps(d)
        assert isinstance(json_str, str)

    def test_batch_result_error_default_is_none(self) -> None:
        """BatchResult error field defaults to None."""
        result = BatchResult(
            from_date="2024-01-01",
            to_date="2024-01-07",
            rows=1000,
            success=True,
        )

        assert result.error is None


class TestParallelFetchResult:
    """Tests for ParallelFetchResult dataclass."""

    def test_create_successful_parallel_fetch_result(self) -> None:
        """ParallelFetchResult can be created for a fully successful fetch."""
        fetched_at = datetime(2024, 1, 15, 10, 30, 0)
        result = ParallelFetchResult(
            table="events_q4",
            total_rows=10000,
            successful_batches=5,
            failed_batches=0,
            failed_date_ranges=(),
            duration_seconds=45.5,
            fetched_at=fetched_at,
        )

        assert result.table == "events_q4"
        assert result.total_rows == 10000
        assert result.successful_batches == 5
        assert result.failed_batches == 0
        assert result.failed_date_ranges == ()
        assert result.duration_seconds == 45.5
        assert result.fetched_at == fetched_at

    def test_create_partial_failure_parallel_fetch_result(self) -> None:
        """ParallelFetchResult can be created with some failed batches."""
        fetched_at = datetime(2024, 1, 15, 10, 30, 0)
        failed_ranges = (
            ("2024-01-08", "2024-01-14"),
            ("2024-01-22", "2024-01-28"),
        )
        result = ParallelFetchResult(
            table="events_q4",
            total_rows=8000,
            successful_batches=3,
            failed_batches=2,
            failed_date_ranges=failed_ranges,
            duration_seconds=52.1,
            fetched_at=fetched_at,
        )

        assert result.successful_batches == 3
        assert result.failed_batches == 2
        assert result.failed_date_ranges == failed_ranges
        assert len(result.failed_date_ranges) == 2

    def test_parallel_fetch_result_is_frozen(self) -> None:
        """ParallelFetchResult should be immutable (frozen dataclass)."""
        result = ParallelFetchResult(
            table="events_q4",
            total_rows=10000,
            successful_batches=5,
            failed_batches=0,
            failed_date_ranges=(),
            duration_seconds=45.5,
            fetched_at=datetime.now(),
        )

        with pytest.raises(AttributeError):
            result.total_rows = 20000  # type: ignore[misc]

    def test_has_failures_property_no_failures(self) -> None:
        """has_failures property returns False when no batches failed."""
        result = ParallelFetchResult(
            table="events_q4",
            total_rows=10000,
            successful_batches=5,
            failed_batches=0,
            failed_date_ranges=(),
            duration_seconds=45.5,
            fetched_at=datetime.now(),
        )

        assert result.has_failures is False

    def test_has_failures_property_with_failures(self) -> None:
        """has_failures property returns True when batches failed."""
        result = ParallelFetchResult(
            table="events_q4",
            total_rows=8000,
            successful_batches=3,
            failed_batches=2,
            failed_date_ranges=(("2024-01-08", "2024-01-14"),),
            duration_seconds=52.1,
            fetched_at=datetime.now(),
        )

        assert result.has_failures is True

    def test_parallel_fetch_result_to_dict(self) -> None:
        """ParallelFetchResult.to_dict() returns JSON-serializable dictionary."""
        fetched_at = datetime(2024, 1, 15, 10, 30, 0)
        failed_ranges = (("2024-01-08", "2024-01-14"),)
        result = ParallelFetchResult(
            table="events_q4",
            total_rows=8000,
            successful_batches=4,
            failed_batches=1,
            failed_date_ranges=failed_ranges,
            duration_seconds=52.1,
            fetched_at=fetched_at,
        )

        d = result.to_dict()

        assert d["table"] == "events_q4"
        assert d["total_rows"] == 8000
        assert d["successful_batches"] == 4
        assert d["failed_batches"] == 1
        assert d["failed_date_ranges"] == [["2024-01-08", "2024-01-14"]]
        assert d["duration_seconds"] == 52.1
        assert d["fetched_at"] == "2024-01-15T10:30:00"
        assert d["has_failures"] is True

        # Verify JSON serializable
        json_str = json.dumps(d)
        assert isinstance(json_str, str)

    def test_parallel_fetch_result_to_dict_empty_failures(self) -> None:
        """ParallelFetchResult.to_dict() handles empty failed_date_ranges."""
        fetched_at = datetime(2024, 1, 15, 10, 30, 0)
        result = ParallelFetchResult(
            table="events_q4",
            total_rows=10000,
            successful_batches=5,
            failed_batches=0,
            failed_date_ranges=(),
            duration_seconds=45.5,
            fetched_at=fetched_at,
        )

        d = result.to_dict()

        assert d["failed_date_ranges"] == []
        assert d["has_failures"] is False

    def test_failed_date_ranges_is_tuple(self) -> None:
        """failed_date_ranges uses tuple for immutability."""
        result = ParallelFetchResult(
            table="events_q4",
            total_rows=10000,
            successful_batches=5,
            failed_batches=0,
            failed_date_ranges=(),
            duration_seconds=45.5,
            fetched_at=datetime.now(),
        )

        assert isinstance(result.failed_date_ranges, tuple)
