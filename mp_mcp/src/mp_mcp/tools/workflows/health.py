"""Health tool for Operational Analytics Loop.

Generates KPI dashboard with period comparison for monitoring product health.
Tracks key metrics like signups, activations, and retention with trends.

Example:
    Ask: "How is my product doing?"
    Uses: health()
"""

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Literal

from fastmcp import Context

from mp_mcp.context import get_workspace
from mp_mcp.errors import handle_errors
from mp_mcp.server import mcp
from mp_mcp.types import (
    DataPoint,
    DateRange,
    HealthDashboard,
    Metric,
)


def _get_date_ranges(
    from_date: str | None = None,
    to_date: str | None = None,
    comparison_period_days: int = 30,
) -> tuple[DateRange, DateRange]:
    """Get current and comparison date ranges.

    Args:
        from_date: Start date for current period (YYYY-MM-DD).
        to_date: End date for current period (YYYY-MM-DD).
        comparison_period_days: Number of days for each period.

    Returns:
        Tuple of (current_period, comparison_period).
    """
    today = datetime.now().date()

    if from_date and to_date:
        current_from = datetime.fromisoformat(from_date).date()
        current_to = datetime.fromisoformat(to_date).date()
        period_length = (current_to - current_from).days
    else:
        current_to = today
        current_from = today - timedelta(days=comparison_period_days)
        period_length = comparison_period_days

    comparison_to = current_from - timedelta(days=1)
    comparison_from = comparison_to - timedelta(days=period_length)

    return (
        DateRange(from_date=current_from.isoformat(), to_date=current_to.isoformat()),
        DateRange(
            from_date=comparison_from.isoformat(), to_date=comparison_to.isoformat()
        ),
    )


def _compute_change_percent(current: float, previous: float) -> float:
    """Compute percentage change between current and previous values.

    Args:
        current: Current period value.
        previous: Previous period value.

    Returns:
        Percentage change (positive = increase, negative = decrease).
    """
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)


def _determine_trend(
    current: float, previous: float, threshold: float = 5.0
) -> Literal["up", "down", "flat"]:
    """Determine trend direction based on change magnitude.

    Args:
        current: Current period value.
        previous: Previous period value.
        threshold: Percentage threshold for flat classification.

    Returns:
        Trend direction: "up", "down", or "flat".
    """
    change_percent = _compute_change_percent(current, previous)
    if change_percent > threshold:
        return "up"
    elif change_percent < -threshold:
        return "down"
    return "flat"


def _compute_metric(
    ctx: Context,
    name: str,
    display_name: str,
    event: str,
    from_date: str,
    to_date: str,
    comparison_from: str,
    comparison_to: str,
    unit: str = "count",
) -> Metric:
    """Compute a single metric with current and comparison values.

    Args:
        ctx: FastMCP context with workspace access.
        name: Metric identifier.
        display_name: Human-readable name.
        event: Event name to measure.
        from_date: Current period start date.
        to_date: Current period end date.
        comparison_from: Comparison period start date.
        comparison_to: Comparison period end date.
        unit: Metric unit.

    Returns:
        Metric with current, previous, and trend values.
    """
    ws = get_workspace(ctx)

    try:
        # Get current period data
        current_result = ws.segmentation(
            event=event,
            from_date=from_date,
            to_date=to_date,
            unit="day",
        )
        current_data = current_result.to_dict()
        current_value = float(current_data.get("total", 0))
    except Exception:
        current_value = 0.0

    try:
        # Get comparison period data
        previous_result = ws.segmentation(
            event=event,
            from_date=comparison_from,
            to_date=comparison_to,
            unit="day",
        )
        previous_data = previous_result.to_dict()
        previous_value = float(previous_data.get("total", 0))
    except Exception:
        previous_value = 0.0

    change_percent = _compute_change_percent(current_value, previous_value)
    trend = _determine_trend(current_value, previous_value)

    return Metric(
        name=name,
        display_name=display_name,
        current=current_value,
        previous=previous_value,
        change_percent=change_percent,
        trend=trend,
        unit=unit,
    )


def _compute_retention_metric(
    ctx: Context,
    event: str,
    from_date: str,
    to_date: str,
    comparison_from: str,
    comparison_to: str,
) -> Metric:
    """Compute retention metric with D7 retention values.

    Args:
        ctx: FastMCP context with workspace access.
        event: Event for retention analysis.
        from_date: Current period start date.
        to_date: Current period end date.
        comparison_from: Comparison period start date.
        comparison_to: Comparison period end date.

    Returns:
        Metric with D7 retention current, previous, and trend.
    """
    ws = get_workspace(ctx)

    def get_d7_retention(f_date: str, t_date: str) -> float:
        """Extract D7 retention value from retention query."""
        try:
            result = ws.retention(
                born_event=event,
                return_event=event,
                from_date=f_date,
                to_date=t_date,
                unit="day",
                interval_count=7,
            )
            data = result.to_dict()
            cohorts = data.get("cohorts", [])
            if cohorts:
                d7_values = []
                for cohort in cohorts:
                    retention_array = cohort.get("retention", [])
                    if len(retention_array) > 7:
                        d7_values.append(float(retention_array[7]))
                if d7_values:
                    return sum(d7_values) / len(d7_values)
        except Exception:
            pass
        return 0.0

    current_retention = get_d7_retention(from_date, to_date)
    previous_retention = get_d7_retention(comparison_from, comparison_to)

    change_percent = _compute_change_percent(current_retention, previous_retention)
    trend = _determine_trend(current_retention, previous_retention)

    return Metric(
        name="d7_retention",
        display_name="D7 Retention",
        current=round(current_retention * 100, 1),  # Convert to percentage
        previous=round(previous_retention * 100, 1),
        change_percent=change_percent,
        trend=trend,
        unit="percent",
    )


def _get_daily_series(
    ctx: Context,
    event: str,
    from_date: str,
    to_date: str,
) -> list[DataPoint]:
    """Get daily time series for an event.

    Args:
        ctx: FastMCP context with workspace access.
        event: Event name.
        from_date: Start date.
        to_date: End date.

    Returns:
        List of DataPoints with daily values.
    """
    ws = get_workspace(ctx)

    try:
        result = ws.segmentation(
            event=event,
            from_date=from_date,
            to_date=to_date,
            unit="day",
        )
        data = result.to_dict()
        series = data.get("series", {})

        points: list[DataPoint] = []
        if isinstance(series, dict):
            for segment_values in series.values():
                if isinstance(segment_values, dict):
                    for date_str, value in segment_values.items():
                        points.append(DataPoint(date=date_str, value=float(value)))
                    break  # Only need first segment for overall trend

        return sorted(points, key=lambda p: p.date)
    except Exception:
        return []


def _generate_insights(metrics: list[Metric]) -> tuple[list[str], list[str]]:
    """Generate highlights and concerns from metrics.

    Args:
        metrics: List of computed metrics.

    Returns:
        Tuple of (highlights, concerns) lists.
    """
    highlights: list[str] = []
    concerns: list[str] = []

    for metric in metrics:
        if metric.trend == "up" and metric.change_percent > 10:
            highlights.append(
                f"{metric.display_name} increased {metric.change_percent}% "
                f"({int(metric.previous)} -> {int(metric.current)})"
            )
        elif metric.trend == "down" and metric.change_percent < -10:
            concerns.append(
                f"{metric.display_name} decreased {abs(metric.change_percent)}% "
                f"({int(metric.previous)} -> {int(metric.current)})"
            )

    return highlights, concerns


@mcp.tool
@handle_errors
def health(
    ctx: Context,
    from_date: str | None = None,
    to_date: str | None = None,
    acquisition_event: str = "signup",
    activation_event: str | None = None,
    include_retention: bool = True,
) -> dict[str, Any]:
    """Generate product health dashboard with KPI comparison.

    Computes key metrics for current and comparison periods,
    identifies trends, and highlights significant changes.

    Args:
        ctx: FastMCP context with workspace access.
        from_date: Start date for analysis (YYYY-MM-DD).
            Defaults to 30 days ago.
        to_date: End date for analysis (YYYY-MM-DD).
            Defaults to today.
        acquisition_event: Event for acquisition metric.
            Defaults to "signup".
        activation_event: Event for activation metric.
            If not specified, uses acquisition_event.
        include_retention: Whether to compute retention metrics.
            Defaults to True.

    Returns:
        Dictionary containing:
        - period: Current analysis period
        - comparison_period: Baseline period for comparison
        - metrics: List of metrics with current/previous/trend
        - highlights: Positive observations
        - concerns: Concerning observations
        - daily_series: Time series data by metric

    Example:
        Ask: "How is my product doing?"
        Uses: health()

        Ask: "Show me KPIs for the last week"
        Uses: health(
            from_date="2025-01-17",
            to_date="2025-01-24",
        )
    """
    # Get date ranges
    current_period, comparison_period = _get_date_ranges(from_date, to_date)

    # Default activation to acquisition event
    if not activation_event:
        activation_event = acquisition_event

    # Compute metrics
    metrics: list[Metric] = []

    # Acquisition metric
    acquisition_metric = _compute_metric(
        ctx,
        name="acquisition",
        display_name="Acquisition",
        event=acquisition_event,
        from_date=current_period.from_date,
        to_date=current_period.to_date,
        comparison_from=comparison_period.from_date,
        comparison_to=comparison_period.to_date,
    )
    metrics.append(acquisition_metric)

    # Activation metric
    if activation_event != acquisition_event:
        activation_metric = _compute_metric(
            ctx,
            name="activation",
            display_name="Activation",
            event=activation_event,
            from_date=current_period.from_date,
            to_date=current_period.to_date,
            comparison_from=comparison_period.from_date,
            comparison_to=comparison_period.to_date,
        )
        metrics.append(activation_metric)

    # Retention metric
    if include_retention:
        retention_metric = _compute_retention_metric(
            ctx,
            event=acquisition_event,
            from_date=current_period.from_date,
            to_date=current_period.to_date,
            comparison_from=comparison_period.from_date,
            comparison_to=comparison_period.to_date,
        )
        metrics.append(retention_metric)

    # Generate insights
    highlights, concerns = _generate_insights(metrics)

    # Get daily series for primary metric
    daily_series: dict[str, list[DataPoint]] = {}
    acquisition_series = _get_daily_series(
        ctx,
        acquisition_event,
        current_period.from_date,
        current_period.to_date,
    )
    if acquisition_series:
        daily_series["acquisition"] = acquisition_series

    # Build dashboard
    dashboard = HealthDashboard(
        period=current_period,
        comparison_period=comparison_period,
        metrics=metrics,
        highlights=highlights,
        concerns=concerns,
        daily_series=daily_series,
    )

    return asdict(dashboard)
