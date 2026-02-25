"""Investigate tool for Operational Analytics Loop.

Performs root cause analysis on detected anomalies by analyzing
dimensional breakdowns, temporal patterns, and contributing factors.

Example:
    Ask: "Investigate the signup drop"
    Uses: investigate(anomaly_id="...")
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
    ContributingFactor,
    DateRange,
    Investigation,
    TimelineEvent,
)


def _parse_anomaly_id(anomaly_id: str) -> dict[str, str]:
    """Parse anomaly ID to extract event, type, and date.

    Args:
        anomaly_id: Anomaly ID in format {event}_{type}_{date}_{hash}.

    Returns:
        Dictionary with event, anomaly_type, and date fields.

    Raises:
        ValueError: If anomaly_id format is invalid.
    """
    parts = anomaly_id.split("_")
    if len(parts) < 4:
        raise ValueError(f"Invalid anomaly ID format: {anomaly_id}")

    # Last part is hash, third-from-last is date (YYYY-MM-DD format)
    # Handle events with underscores by finding the date pattern
    for i, part in enumerate(parts):
        if len(part) == 10 and part[4] == "-" and part[7] == "-":
            # Found date at position i
            event = "_".join(parts[: i - 1]) if i > 1 else parts[0]
            anomaly_type = parts[i - 1] if i > 0 else "unknown"
            date = part
            return {
                "event": event,
                "anomaly_type": anomaly_type,
                "date": date,
            }

    # Fallback: assume standard format
    return {
        "event": parts[0],
        "anomaly_type": parts[1],
        "date": parts[2],
    }


AnomalyType = Literal["drop", "spike", "trend_change", "segment_shift"]


def _validate_anomaly_type(type_str: str) -> AnomalyType:
    """Validate and return a valid anomaly type.

    Args:
        type_str: String representation of anomaly type.

    Returns:
        Valid AnomalyType literal.
    """
    valid_types: list[AnomalyType] = ["drop", "spike", "trend_change", "segment_shift"]
    if type_str in valid_types:
        return type_str  # type: ignore[return-value]
    return "drop"


def _create_anomaly_from_id(anomaly_id: str) -> Anomaly:
    """Create an Anomaly object from an anomaly ID.

    Args:
        anomaly_id: Anomaly ID to parse.

    Returns:
        Anomaly object with parsed fields.
    """
    parsed = _parse_anomaly_id(anomaly_id)
    anomaly_type = _validate_anomaly_type(parsed["anomaly_type"])
    return Anomaly(
        id=anomaly_id,
        type=anomaly_type,
        severity="medium",  # Default; actual severity would come from scan
        category="general",
        summary=f"{parsed['event']} {parsed['anomaly_type']} on {parsed['date']}",
        event=parsed["event"],
        detected_at=parsed["date"],
        magnitude=0.0,
        confidence=0.5,
        context={},
    )


def _get_investigation_period(anomaly_date: str, lookback_days: int = 14) -> DateRange:
    """Get date range for investigation centered around anomaly.

    Args:
        anomaly_date: Date of the anomaly (YYYY-MM-DD).
        lookback_days: Number of days to look back from anomaly.

    Returns:
        DateRange covering the investigation period.
    """
    anomaly = datetime.fromisoformat(anomaly_date).date()
    from_date = (anomaly - timedelta(days=lookback_days)).isoformat()
    to_date = (anomaly + timedelta(days=3)).isoformat()  # Include a few days after

    return DateRange(from_date=from_date, to_date=to_date)


def _dimensional_decomposition(
    ctx: Context,
    event: str,
    from_date: str,
    to_date: str,
    anomaly_date: str,
    dimensions: list[str] | None = None,
) -> list[ContributingFactor]:
    """Decompose anomaly by dimensions to identify contributing segments.

    Args:
        ctx: FastMCP context with workspace access.
        event: Event name to analyze.
        from_date: Start date for analysis.
        to_date: End date for analysis.
        anomaly_date: Date of the anomaly.
        dimensions: List of dimensions to analyze.

    Returns:
        List of ContributingFactors ordered by impact.
    """
    ws = get_workspace(ctx)
    factors: list[ContributingFactor] = []

    # Default dimensions to check
    if not dimensions:
        dimensions = ["$browser", "$os", "$city", "platform"]

    for dimension in dimensions:
        try:
            # Get segmented data
            result = ws.segmentation(
                event=event,
                from_date=from_date,
                to_date=to_date,
                unit="day",
                property_name=dimension,
            )
            data = result.to_dict()
            series = data.get("series", {})

            if not isinstance(series, dict):
                continue

            # Analyze each segment for the anomaly date
            segment_changes: list[tuple[str, float, float]] = []

            for segment_name, segment_values in series.items():
                if not isinstance(segment_values, dict):
                    continue

                # Get value on anomaly date and baseline
                anomaly_value = float(segment_values.get(anomaly_date, 0))

                # Calculate baseline from previous dates
                baseline_values = [
                    float(v) for d, v in segment_values.items() if d < anomaly_date
                ]
                if not baseline_values:
                    continue

                baseline = sum(baseline_values) / len(baseline_values)
                if baseline == 0:
                    continue

                change = (anomaly_value - baseline) / baseline
                segment_changes.append((segment_name, change, abs(change * baseline)))

            # Sort by absolute impact
            segment_changes.sort(key=lambda x: x[2], reverse=True)

            # Take top contributing segments
            for segment_name, change, _impact in segment_changes[:3]:
                if abs(change) > 0.1:  # At least 10% change
                    contribution = round(abs(change) * 100, 1)
                    confidence: Literal["high", "medium", "low"] = (
                        "high"
                        if abs(change) > 0.3
                        else "medium"
                        if abs(change) > 0.15
                        else "low"
                    )
                    factors.append(
                        ContributingFactor(
                            factor=f"{dimension}={segment_name}",
                            contribution=contribution,
                            evidence=f"Changed {round(change * 100, 1)}% during anomaly period",
                            confidence=confidence,
                        )
                    )

        except Exception:
            continue

    # Sort by contribution
    factors.sort(key=lambda f: f.contribution, reverse=True)
    return factors[:10]  # Return top 10 factors


def _temporal_analysis(
    ctx: Context,
    event: str,
    from_date: str,
    to_date: str,
    anomaly_date: str,
) -> list[TimelineEvent]:
    """Analyze temporal patterns around the anomaly.

    Args:
        ctx: FastMCP context with workspace access.
        event: Event name to analyze.
        from_date: Start date for analysis.
        to_date: End date for analysis.
        anomaly_date: Date of the anomaly.

    Returns:
        List of TimelineEvents showing the pattern.
    """
    ws = get_workspace(ctx)
    timeline: list[TimelineEvent] = []

    try:
        result = ws.segmentation(
            event=event,
            from_date=from_date,
            to_date=to_date,
            unit="day",
        )
        data = result.to_dict()
        series = data.get("series", {})

        # Flatten to date -> value
        time_series: dict[str, float] = {}
        if isinstance(series, dict):
            for segment_values in series.values():
                if isinstance(segment_values, dict):
                    for date_str, value in segment_values.items():
                        time_series[date_str] = float(value)
                    break

        if not time_series:
            return timeline

        sorted_dates = sorted(time_series.keys())

        # Calculate rolling average for baseline
        for i, date in enumerate(sorted_dates):
            value = time_series[date]

            # Calculate baseline from previous 7 days
            start_idx = max(0, i - 7)
            prev_values = [time_series[sorted_dates[j]] for j in range(start_idx, i)]
            baseline = sum(prev_values) / len(prev_values) if prev_values else value

            # Determine significance
            if baseline > 0:
                change = (value - baseline) / baseline
                if abs(change) > 0.15:
                    significance: Literal["high", "medium", "low"] = (
                        "high" if abs(change) > 0.3 else "medium"
                    )
                else:
                    significance = "low"
            else:
                significance = "low"

            description = f"Value: {value:.0f} (baseline: {baseline:.1f})"
            if date == anomaly_date:
                description = f"ANOMALY: {description}"

            timeline.append(
                TimelineEvent(
                    timestamp=date,
                    description=description,
                    significance=significance,
                )
            )

    except Exception:
        pass

    return timeline


def _identify_correlations(
    ctx: Context,
    event: str,
    from_date: str,
    to_date: str,
    anomaly_date: str,
) -> list[dict[str, Any]]:
    """Identify correlated events that changed around the anomaly.

    Args:
        ctx: FastMCP context with workspace access.
        event: Primary event being investigated.
        from_date: Start date for analysis.
        to_date: End date for analysis.
        anomaly_date: Date of the anomaly.

    Returns:
        List of correlated events with their changes.
    """
    ws = get_workspace(ctx)
    correlations: list[dict[str, Any]] = []

    try:
        # Get top events to check for correlations
        top_events_raw = ws.top_events()
        events_to_check = [
            e.to_dict().get("event", e.to_dict().get("name", ""))
            for e in top_events_raw[:10]
        ]

        for check_event in events_to_check:
            if check_event == event:
                continue

            try:
                result = ws.segmentation(
                    event=check_event,
                    from_date=from_date,
                    to_date=to_date,
                    unit="day",
                )
                data = result.to_dict()
                series = data.get("series", {})

                # Get time series
                time_series: dict[str, float] = {}
                if isinstance(series, dict):
                    for segment_values in series.values():
                        if isinstance(segment_values, dict):
                            for date_str, value in segment_values.items():
                                time_series[date_str] = float(value)
                            break

                if not time_series or anomaly_date not in time_series:
                    continue

                # Calculate change on anomaly date
                anomaly_value = time_series[anomaly_date]
                prev_dates = [d for d in sorted(time_series.keys()) if d < anomaly_date]
                if not prev_dates:
                    continue

                baseline_values = [time_series[d] for d in prev_dates[-7:]]
                baseline = sum(baseline_values) / len(baseline_values)

                if baseline == 0:
                    continue

                change = (anomaly_value - baseline) / baseline

                if abs(change) > 0.15:  # At least 15% change
                    correlations.append(
                        {
                            "event": check_event,
                            "change_percent": round(change * 100, 1),
                            "correlation_type": "positive"
                            if change > 0
                            else "negative",
                        }
                    )

            except Exception:
                continue

    except Exception:
        pass

    # Sort by absolute change
    correlations.sort(key=lambda x: abs(x["change_percent"]), reverse=True)
    return correlations[:5]


def _generate_hypotheses(
    factors: list[ContributingFactor],
    correlations: list[dict[str, Any]],
    anomaly_type: str,
) -> list[str]:
    """Generate hypotheses based on analysis results.

    Args:
        factors: Contributing factors from dimensional analysis.
        correlations: Correlated events.
        anomaly_type: Type of anomaly (drop, spike, etc.).

    Returns:
        List of hypothesis strings.
    """
    hypotheses: list[str] = []

    # Generate hypotheses from top factors
    for factor in factors[:3]:
        hypotheses.append(
            f"The {anomaly_type} may be driven by {factor.factor} "
            f"(contributed {factor.contribution}%)"
        )

    # Generate hypotheses from correlations
    for corr in correlations[:2]:
        if corr["correlation_type"] == "positive":
            hypotheses.append(
                f"Correlated with {corr['event']} which also changed "
                f"{corr['change_percent']}%"
            )
        else:
            hypotheses.append(
                f"Inversely correlated with {corr['event']} which changed "
                f"{corr['change_percent']}%"
            )

    if not hypotheses:
        hypotheses.append(
            "No clear pattern identified. Consider checking for external factors."
        )

    return hypotheses


@mcp.tool
@handle_errors
def investigate(
    ctx: Context,
    anomaly_id: str | None = None,
    event: str | None = None,
    date: str | None = None,
    anomaly_type: Literal["drop", "spike", "trend_change"] | None = None,
    dimensions: list[str] | None = None,
) -> dict[str, Any]:
    """Investigate an anomaly to identify root causes.

    Performs dimensional decomposition, temporal analysis, and
    correlation detection to generate hypotheses about what
    caused the anomaly.

    Args:
        ctx: FastMCP context with workspace access.
        anomaly_id: Anomaly ID from scan results.
            Preferred method - contains event, type, and date.
        event: Event name to investigate.
            Required if anomaly_id not provided.
        date: Date to investigate (YYYY-MM-DD).
            Required if anomaly_id not provided.
        anomaly_type: Type of anomaly to investigate.
            Defaults to "drop" if not specified.
        dimensions: List of dimensions to analyze.
            Defaults to common dimensions.

    Returns:
        Dictionary containing:
        - anomaly: The anomaly being investigated
        - investigation_period: Date range analyzed
        - contributing_factors: Ranked factors by impact
        - timeline: Temporal pattern around anomaly
        - correlations: Related events that changed
        - hypotheses: Possible explanations
        - confidence: Investigation confidence score

    Example:
        Ask: "Investigate the signup drop"
        Uses: investigate(anomaly_id="signup_drop_2025-01-15_a3f2b1c9")

        Ask: "Why did logins spike yesterday?"
        Uses: investigate(
            event="login",
            date="2025-01-23",
            anomaly_type="spike",
        )
    """
    # Parse or create anomaly
    if anomaly_id:
        anomaly = _create_anomaly_from_id(anomaly_id)
        event_name = anomaly.event
        anomaly_date = anomaly.detected_at
        atype = anomaly.type
    elif event and date:
        atype = anomaly_type or "drop"
        anomaly_id = generate_anomaly_id(event, atype, date)
        anomaly = Anomaly(
            id=anomaly_id,
            type=atype,
            severity="medium",
            category="general",
            summary=f"{event} {atype} on {date}",
            event=event,
            detected_at=date,
            magnitude=0.0,
            confidence=0.5,
            context={},
        )
        event_name = event
        anomaly_date = date
    else:
        return {
            "error": "Either anomaly_id or both event and date must be provided",
        }

    # Get investigation period
    period = _get_investigation_period(anomaly_date)

    # Perform dimensional decomposition
    factors = _dimensional_decomposition(
        ctx,
        event_name,
        period.from_date,
        period.to_date,
        anomaly_date,
        dimensions,
    )

    # Perform temporal analysis
    timeline = _temporal_analysis(
        ctx,
        event_name,
        period.from_date,
        period.to_date,
        anomaly_date,
    )

    # Identify correlations
    correlations = _identify_correlations(
        ctx,
        event_name,
        period.from_date,
        period.to_date,
        anomaly_date,
    )

    # Generate hypotheses
    hypotheses = _generate_hypotheses(factors, correlations, atype)

    # Calculate confidence based on data quality
    confidence_score = 0.5
    if factors:
        confidence_score += 0.2
    if timeline and len(timeline) > 7:
        confidence_score += 0.15
    if correlations:
        confidence_score += 0.15

    # Map score to confidence level
    if confidence_score >= 0.8:
        confidence_level: Literal["high", "medium", "low"] = "high"
    elif confidence_score >= 0.6:
        confidence_level = "medium"
    else:
        confidence_level = "low"

    # Determine root cause from top factor
    root_cause: str | None = None
    if factors:
        top_factor = factors[0]
        root_cause = (
            f"{top_factor.factor} contributed {top_factor.contribution}% to the {atype}"
        )

    # Build segments analyzed list
    segments_analyzed: list[dict[str, Any]] = []
    for factor in factors[:5]:
        segments_analyzed.append(
            {
                "factor": factor.factor,
                "contribution": factor.contribution,
                "evidence": factor.evidence,
            }
        )

    # Build data points with correlation info
    data_points: dict[str, Any] = {
        "investigation_period": {
            "from_date": period.from_date,
            "to_date": period.to_date,
        },
        "correlations": correlations,
        "hypotheses": hypotheses,
    }

    # Build investigation result
    investigation = Investigation(
        anomaly=anomaly,
        root_cause=root_cause,
        contributing_factors=factors,
        segments_analyzed=segments_analyzed,
        timeline=timeline,
        confidence=confidence_level,
        data_points=data_points,
    )

    return asdict(investigation)
