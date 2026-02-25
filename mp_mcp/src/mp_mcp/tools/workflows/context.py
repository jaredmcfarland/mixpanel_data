"""Context tool for Operational Analytics Loop.

Gathers project landscape to provide foundation for analytics workflow.
Aggregates events, properties, funnels, cohorts, and bookmarks into
a unified context package for subsequent analysis.

Example:
    Ask: "Give me context on my Mixpanel project"
    Uses: context()
"""

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from fastmcp import Context

from mp_mcp.context import get_workspace
from mp_mcp.errors import handle_errors
from mp_mcp.server import mcp
from mp_mcp.types import (
    BookmarksSummary,
    CohortSummary,
    ContextPackage,
    DateRange,
    EventsSummary,
    FunnelSummary,
    PropertiesSummary,
)


def _gather_events(ctx: Context) -> EventsSummary:
    """Gather events summary from workspace.

    Args:
        ctx: FastMCP context with workspace access.

    Returns:
        EventsSummary with total count, top events, and categories.
    """
    ws = get_workspace(ctx)

    try:
        # Get all events
        events = ws.events()

        # Get top events for activity ranking
        top_events_raw = ws.top_events()
        top_events = [
            e.to_dict().get("event", e.to_dict().get("name", ""))
            for e in top_events_raw[:10]
        ]

        return EventsSummary(
            total=len(events),
            top_events=top_events,
            categories={},  # Categories would come from Lexicon if available
        )

    except Exception:
        return EventsSummary(
            total=0,
            top_events=[],
            categories={},
        )


def _gather_properties(ctx: Context) -> PropertiesSummary:
    """Gather properties summary from workspace.

    Args:
        ctx: FastMCP context with workspace access.

    Returns:
        PropertiesSummary with counts and common properties.
    """
    ws = get_workspace(ctx)

    try:
        # Get event properties (first event has most properties typically)
        events = ws.events()
        event_props: list[str] = []
        if events:
            event_props = ws.properties(events[0])

        # User properties would come from profile schemas
        # For now, estimate based on event properties
        user_props_count = 0

        # Find common properties (appear in multiple events)
        common_props = ["$browser", "$os", "$city", "$country", "platform"]
        actual_common = [p for p in common_props if p in event_props]

        return PropertiesSummary(
            event_properties=len(event_props),
            user_properties=user_props_count,
            common=actual_common,
        )

    except Exception:
        return PropertiesSummary(
            event_properties=0,
            user_properties=0,
            common=[],
        )


def _gather_funnels_cohorts(
    ctx: Context,
) -> tuple[list[FunnelSummary], list[CohortSummary]]:
    """Gather funnels and cohorts from workspace.

    Args:
        ctx: FastMCP context with workspace access.

    Returns:
        Tuple of (funnel_summaries, cohort_summaries).
    """
    ws = get_workspace(ctx)

    # Gather funnels
    funnels: list[FunnelSummary] = []
    try:
        funnels_raw = ws.funnels()
        for f in funnels_raw:
            f_dict = f.to_dict()
            funnels.append(
                FunnelSummary(
                    id=f_dict.get("funnel_id", f_dict.get("id", 0)),
                    name=f_dict.get("name", "Unknown"),
                    steps=f_dict.get("steps", 0),
                )
            )
    except Exception:
        pass

    # Gather cohorts
    cohorts: list[CohortSummary] = []
    try:
        cohorts_raw = ws.cohorts()
        for c in cohorts_raw:
            c_dict = c.to_dict()
            cohorts.append(
                CohortSummary(
                    id=c_dict.get("cohort_id", c_dict.get("id", 0)),
                    name=c_dict.get("name", "Unknown"),
                    count=c_dict.get("count", 0),
                )
            )
    except Exception:
        pass

    return funnels, cohorts


def _gather_bookmarks(ctx: Context) -> BookmarksSummary:
    """Gather bookmarks summary from workspace.

    Args:
        ctx: FastMCP context with workspace access.

    Returns:
        BookmarksSummary with total count and breakdown by type.
    """
    ws = get_workspace(ctx)

    try:
        bookmarks_raw = ws.list_bookmarks()
        by_type: dict[str, int] = {}

        for b in bookmarks_raw:
            b_dict = b.to_dict()
            report_type = b_dict.get("report_type", b_dict.get("type", "unknown"))
            by_type[report_type] = by_type.get(report_type, 0) + 1

        return BookmarksSummary(
            total=len(bookmarks_raw),
            by_type=by_type,
        )

    except Exception:
        return BookmarksSummary(
            total=0,
            by_type={},
        )


def _get_date_range() -> DateRange:
    """Get default date range for context (last 90 days).

    Returns:
        DateRange with from_date and to_date.
    """
    today = datetime.now().date()
    from_date = (today - timedelta(days=90)).isoformat()
    to_date = today.isoformat()

    return DateRange(from_date=from_date, to_date=to_date)


def _gather_schemas(ctx: Context) -> list[dict[str, Any]] | None:
    """Gather Lexicon schemas if available.

    Args:
        ctx: FastMCP context with workspace access.

    Returns:
        List of schema dictionaries or None if not available.
    """
    ws = get_workspace(ctx)

    try:
        schemas_raw = ws.lexicon_schemas()
        return [s.to_dict() for s in schemas_raw]
    except Exception:
        return None


@mcp.tool
@handle_errors
def context(
    ctx: Context,
    include_schemas: bool = False,
) -> dict[str, Any]:
    """Gather project context for analytics workflow.

    Aggregates project metadata, events, properties, funnels, cohorts,
    and bookmarks into a unified context package. Use this as the first
    step in an analytics workflow to understand the project landscape.

    Args:
        ctx: FastMCP context with workspace access.
        include_schemas: Whether to include Lexicon schemas. Defaults to False
            as schemas can be large.

    Returns:
        Dictionary containing:
        - project: Project metadata (id, region)
        - events: Summary of tracked events
        - properties: Summary of available properties
        - funnels: List of saved funnel summaries
        - cohorts: List of saved cohort summaries
        - bookmarks: Summary of saved reports
        - date_range: Available data date range
        - schemas: Optional Lexicon schema definitions

    Example:
        Ask: "Give me context on my Mixpanel project"
        Uses: context()

        Ask: "What events and funnels are available?"
        Uses: context(include_schemas=False)
    """
    ws = get_workspace(ctx)

    # Gather project info
    project_info = ws.info()
    project = {
        "project_id": project_info.project_id,
        "region": project_info.region,
    }

    # Gather all context components
    events = _gather_events(ctx)
    properties = _gather_properties(ctx)
    funnels, cohorts = _gather_funnels_cohorts(ctx)
    bookmarks = _gather_bookmarks(ctx)
    date_range = _get_date_range()

    # Optionally gather schemas
    schemas = _gather_schemas(ctx) if include_schemas else None

    # Build context package
    context_package = ContextPackage(
        project=project,
        events=events,
        properties=properties,
        funnels=funnels,
        cohorts=cohorts,
        bookmarks=bookmarks,
        date_range=date_range,
        schemas=schemas,
    )

    return asdict(context_package)
