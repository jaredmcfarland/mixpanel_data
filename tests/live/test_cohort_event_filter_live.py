"""Live tests for cohort event-property filter rejection (CF3).

Verifies that inline CohortDefinitions with event-property filters
are rejected client-side with a clear ValueError, preventing the
server-side bug where Mixpanel's inline cohort evaluator silently
ignores event-property filter operators.

Also includes a parameterized "ground truth" test that exercises
top-level event filters via ws.query(where=...) to confirm the
working path remains correct.

Usage:
    uv run pytest tests/live/test_cohort_event_filter_live.py -v
"""

from __future__ import annotations

from typing import Any

import pytest

from mixpanel_data import (
    CohortCriteria,
    CohortDefinition,
    Filter,
    QueryResult,
    Workspace,
)

pytestmark = pytest.mark.live


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def ws() -> Workspace:
    """Create Workspace with p8 credentials.

    Returns:
        Workspace connected to project 8.
    """
    return Workspace(account="p8")


@pytest.fixture(scope="module")
def real_event(ws: Workspace) -> str:
    """Discover a real event name from project 8.

    Returns:
        First available event name.
    """
    events = ws.events()
    assert len(events) > 0, "No events found in project 8"
    return events[0]


# =============================================================================
# 1. CF3 Rejection Tests — Client-Side Guard
# =============================================================================


class TestCF3RejectionLive:
    """Verify CF3 guard prevents silent wrong results from inline cohort filters."""

    @pytest.mark.parametrize(
        ("label", "filter_factory", "factory_args"),
        [
            ("equals", Filter.equals, ("$browser", "Chrome")),
            ("not_equals", Filter.not_equals, ("$browser", "Chrome")),
            ("is_set", Filter.is_set, ("$browser",)),
            ("is_not_set", Filter.is_not_set, ("$browser",)),
            ("greater_than", Filter.greater_than, ("$screen_width", 1000)),
            ("less_than", Filter.less_than, ("$screen_width", 500)),
            ("contains", Filter.contains, ("$browser", "Chrome")),
        ],
    )
    def test_inline_cohort_with_event_filter_raises(
        self,
        real_event: str,
        label: str,
        filter_factory: Any,
        factory_args: tuple[Any, ...],
    ) -> None:
        """Filter.in_cohort rejects inline definition with event-property filter.

        Args:
            real_event: Real event name from project.
            label: Human-readable filter label.
            filter_factory: Filter class method to call.
            factory_args: Arguments for the filter factory.
        """
        f = filter_factory(*factory_args)
        defn = CohortDefinition.all_of(
            CohortCriteria.did_event(real_event, at_least=1, within_days=30, where=f)
        )
        with pytest.raises(ValueError, match="event-property filters"):
            Filter.in_cohort(defn, f"CF3-{label}")

    def test_inline_cohort_without_event_filter_accepted(
        self,
        ws: Workspace,
        real_event: str,
    ) -> None:
        """Inline cohort WITHOUT event-property filters still works end-to-end."""
        defn = CohortDefinition.all_of(
            CohortCriteria.did_event(real_event, at_least=1, within_days=90)
        )
        result = ws.query(
            real_event,
            where=Filter.in_cohort(defn, name="CF3-no-filter"),
            last=7,
        )
        assert isinstance(result, QueryResult)


# =============================================================================
# 2. Top-Level Event Filter Ground Truth (Working Path)
# =============================================================================


class TestTopLevelEventFilterGroundTruth:
    """Verify the top-level where= filter path remains correct.

    These tests confirm that ws.query(event, where=Filter.X(...)) works
    for all filter operators. This is the recommended workaround for
    event-property scoping instead of inline cohort filters.
    """

    @pytest.mark.parametrize(
        ("label", "filter_factory", "factory_args"),
        [
            ("equals", Filter.equals, ("$browser", "Chrome")),
            ("not_equals", Filter.not_equals, ("$browser", "Chrome")),
            ("is_set", Filter.is_set, ("$browser",)),
            ("is_not_set", Filter.is_not_set, ("$browser",)),
            ("contains", Filter.contains, ("$browser", "Chr")),
        ],
    )
    def test_top_level_filter_returns_result(
        self,
        ws: Workspace,
        real_event: str,
        label: str,  # noqa: ARG002 — used by parametrize for test ID
        filter_factory: Any,
        factory_args: tuple[Any, ...],
    ) -> None:
        """Top-level event filter returns valid QueryResult.

        Args:
            ws: Workspace instance.
            real_event: Real event name.
            label: Filter operator label (used in test ID).
            filter_factory: Filter class method.
            factory_args: Arguments for the filter factory.
        """
        f = filter_factory(*factory_args)
        result = ws.query(real_event, where=f, last=7, mode="total")
        assert isinstance(result, QueryResult)

    def test_is_set_and_is_not_set_are_complementary(
        self,
        ws: Workspace,
        real_event: str,
    ) -> None:
        """is_set + is_not_set unique users should sum to <= total unique users.

        This verifies the top-level filter path produces logically
        consistent results (the complement property that the broken
        inline cohort path violates).
        """
        total = ws.query(real_event, last=7, math="unique", mode="total")
        is_set = ws.query(
            real_event,
            where=Filter.is_set("$browser"),
            last=7,
            math="unique",
            mode="total",
        )
        is_not_set = ws.query(
            real_event,
            where=Filter.is_not_set("$browser"),
            last=7,
            math="unique",
            mode="total",
        )

        def _extract(r: QueryResult) -> int:
            """Extract scalar count from total-mode QueryResult."""
            v = r.df["count"].iloc[0]
            return int(v.get("all", 0)) if isinstance(v, dict) else int(v)

        total_n = _extract(total)
        set_n = _extract(is_set)
        not_set_n = _extract(is_not_set)

        # Complementary: set + not_set <= total (may be < due to multi-event users)
        assert set_n + not_set_n <= total_n + 1  # +1 for rounding tolerance
        # Each partition should be <= total
        assert set_n <= total_n
        assert not_set_n <= total_n
