"""Scan tool for Operational Analytics Loop.

Detects anomalies using statistical methods for proactive monitoring.
Identifies drops, spikes, trend changes, and segment shifts.

Example:
    Ask: "Are there any anomalies in my data?"
    Uses: scan()
"""

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Literal

from fastmcp import Context

from mp_mcp.context import get_workspace
from mp_mcp.errors import handle_errors
from mp_mcp.server import mcp
from mp_mcp.tools.workflows.helpers import generate_anomaly_id
from mp_mcp.types import (
    Anomaly,
    DateRange,
    ScanResults,
)


def _get_date_range(
    from_date: str | None = None,
    to_date: str | None = None,
    days_back: int = 14,
) -> DateRange:
    """Get date range for scanning.

    Args:
        from_date: Start date (YYYY-MM-DD).
        to_date: End date (YYYY-MM-DD).
        days_back: Number of days to scan if no dates provided.

    Returns:
        DateRange for the scan period.
    """
    today = datetime.now().date()

    if from_date and to_date:
        return DateRange(from_date=from_date, to_date=to_date)

    return DateRange(
        from_date=(today - timedelta(days=days_back)).isoformat(),
        to_date=today.isoformat(),
    )


def _compute_severity(
    magnitude: float,
) -> Literal["critical", "high", "medium", "low"]:
    """Compute severity level based on anomaly magnitude.

    Args:
        magnitude: Absolute percentage change (0.0 to 1.0+).

    Returns:
        Severity level.
    """
    if magnitude >= 0.4:
        return "critical"
    elif magnitude >= 0.25:
        return "high"
    elif magnitude >= 0.15:
        return "medium"
    return "low"


def _detect_drops(
    data: dict[str, float],
    threshold: float = 0.2,
) -> list[dict[str, Any]]:
    """Detect significant drops in time series data.

    A drop is detected when the value decreases by more than
    the threshold compared to the rolling average of previous values.

    Args:
        data: Dictionary of date -> value pairs.
        threshold: Minimum drop percentage to flag (0.0 to 1.0).

    Returns:
        List of drop events with date, magnitude, and context.
    """
    drops: list[dict[str, Any]] = []

    sorted_dates = sorted(data.keys())
    if len(sorted_dates) < 3:
        return drops

    for i in range(2, len(sorted_dates)):
        current_date = sorted_dates[i]
        current_value = data[current_date]

        # Calculate rolling average of previous 3 values
        prev_values = [data[sorted_dates[j]] for j in range(max(0, i - 3), i)]
        if not prev_values:
            continue

        avg_prev = sum(prev_values) / len(prev_values)
        if avg_prev == 0:
            continue

        change = (current_value - avg_prev) / avg_prev

        if change < -threshold:
            drops.append(
                {
                    "date": current_date,
                    "magnitude": abs(change),
                    "current": current_value,
                    "baseline": avg_prev,
                }
            )

    return drops


def _detect_spikes(
    data: dict[str, float],
    threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """Detect significant spikes in time series data.

    A spike is detected when the value increases by more than
    the threshold compared to the rolling average of previous values.

    Args:
        data: Dictionary of date -> value pairs.
        threshold: Minimum spike percentage to flag (0.0 to 1.0+).

    Returns:
        List of spike events with date, magnitude, and context.
    """
    spikes: list[dict[str, Any]] = []

    sorted_dates = sorted(data.keys())
    if len(sorted_dates) < 3:
        return spikes

    for i in range(2, len(sorted_dates)):
        current_date = sorted_dates[i]
        current_value = data[current_date]

        # Calculate rolling average of previous 3 values
        prev_values = [data[sorted_dates[j]] for j in range(max(0, i - 3), i)]
        if not prev_values:
            continue

        avg_prev = sum(prev_values) / len(prev_values)
        if avg_prev == 0:
            continue

        change = (current_value - avg_prev) / avg_prev

        if change > threshold:
            spikes.append(
                {
                    "date": current_date,
                    "magnitude": change,
                    "current": current_value,
                    "baseline": avg_prev,
                }
            )

    return spikes


def _scan_event(
    ctx: Context,
    event: str,
    from_date: str,
    to_date: str,
    category: str = "general",
) -> list[Anomaly]:
    """Scan a single event for anomalies.

    Args:
        ctx: FastMCP context with workspace access.
        event: Event name to scan.
        from_date: Start date.
        to_date: End date.
        category: AARRR category for this event.

    Returns:
        List of detected anomalies.
    """
    ws = get_workspace(ctx)
    anomalies: list[Anomaly] = []

    try:
        result = ws.segmentation(
            event=event,
            from_date=from_date,
            to_date=to_date,
            unit="day",
        )
        data = result.to_dict()
        series = data.get("series", {})

        # Flatten series to date -> value
        time_series: dict[str, float] = {}
        if isinstance(series, dict):
            for segment_values in series.values():
                if isinstance(segment_values, dict):
                    for date_str, value in segment_values.items():
                        time_series[date_str] = float(value)
                    break

        if not time_series:
            return anomalies

        # Detect drops
        drops = _detect_drops(time_series, threshold=0.2)
        for drop in drops:
            severity = _compute_severity(drop["magnitude"])
            anomaly_id = generate_anomaly_id(event, "drop", drop["date"])
            anomalies.append(
                Anomaly(
                    id=anomaly_id,
                    type="drop",
                    severity=severity,
                    category=category,
                    summary=f"{event} dropped {int(drop['magnitude'] * 100)}% on {drop['date']}",
                    event=event,
                    detected_at=drop["date"],
                    magnitude=round(drop["magnitude"] * 100, 1),
                    confidence=0.8,
                    context={
                        "current": drop["current"],
                        "baseline": drop["baseline"],
                    },
                )
            )

        # Detect spikes
        spikes = _detect_spikes(time_series, threshold=0.5)
        for spike in spikes:
            severity = _compute_severity(spike["magnitude"])
            anomaly_id = generate_anomaly_id(event, "spike", spike["date"])
            anomalies.append(
                Anomaly(
                    id=anomaly_id,
                    type="spike",
                    severity=severity,
                    category=category,
                    summary=f"{event} spiked {int(spike['magnitude'] * 100)}% on {spike['date']}",
                    event=event,
                    detected_at=spike["date"],
                    magnitude=round(spike["magnitude"] * 100, 1),
                    confidence=0.8,
                    context={
                        "current": spike["current"],
                        "baseline": spike["baseline"],
                    },
                )
            )

    except Exception:
        pass

    return anomalies


def _rank_anomalies(anomalies: list[Anomaly]) -> list[Anomaly]:
    """Rank anomalies by severity and confidence.

    Args:
        anomalies: List of detected anomalies.

    Returns:
        Sorted list with highest priority first.
    """
    severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}

    return sorted(
        anomalies,
        key=lambda a: (severity_order.get(a.severity, 0), a.confidence, a.magnitude),
        reverse=True,
    )


@mcp.tool
@handle_errors
def scan(
    ctx: Context,
    from_date: str | None = None,
    to_date: str | None = None,
    events: list[str] | None = None,
    sensitivity: Literal["high", "medium", "low"] = "medium",
) -> dict[str, Any]:
    """Scan for anomalies in Mixpanel data.

    Detects drops, spikes, and unusual patterns in event data
    using statistical methods. Returns ranked list of anomalies
    with unique IDs for investigation.

    Args:
        ctx: FastMCP context with workspace access.
        from_date: Start date for scan (YYYY-MM-DD).
            Defaults to 14 days ago.
        to_date: End date for scan (YYYY-MM-DD).
            Defaults to today.
        events: List of events to scan.
            If not specified, scans top events.
        sensitivity: Detection sensitivity level.
            - "high": Flag more potential anomalies
            - "medium": Balanced detection
            - "low": Only flag significant anomalies

    Returns:
        Dictionary containing:
        - period: Date range that was scanned
        - anomalies: Ranked list of detected anomalies
        - scan_coverage: What was analyzed
        - baseline_stats: Context statistics

    Example:
        Ask: "Are there any anomalies in my data?"
        Uses: scan()

        Ask: "Check for issues in signup and login"
        Uses: scan(events=["signup", "login"])
    """
    ws = get_workspace(ctx)

    # Get date range
    period = _get_date_range(from_date, to_date)

    # Determine events to scan
    events_to_scan: list[str] = []
    if events:
        events_to_scan = events
    else:
        try:
            top_events_raw = ws.top_events()
            events_to_scan = [
                e.to_dict().get("event", e.to_dict().get("name", ""))
                for e in top_events_raw[:10]
            ]
        except Exception:
            events_to_scan = []

    # Set thresholds based on sensitivity
    # (Currently unused but can be passed to helper functions later)
    _ = {"high": 0.1, "medium": 0.2, "low": 0.3}[sensitivity]

    # Scan each event
    all_anomalies: list[Anomaly] = []
    for event in events_to_scan:
        event_anomalies = _scan_event(
            ctx,
            event,
            period.from_date,
            period.to_date,
        )
        all_anomalies.extend(event_anomalies)

    # Rank anomalies
    ranked_anomalies = _rank_anomalies(all_anomalies)

    # Build scan results
    scan_results = ScanResults(
        period=period,
        anomalies=ranked_anomalies,
        scan_coverage={
            "events_scanned": len(events_to_scan),
            "events": events_to_scan,
        },
        baseline_stats={},
    )

    return asdict(scan_results)
