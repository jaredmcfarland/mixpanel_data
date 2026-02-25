"""Report tool for Operational Analytics Loop.

Synthesizes findings from scan and investigate tools into actionable
reports with recommendations, formatted for various output targets.

Example:
    Ask: "Generate a report from the investigation"
    Uses: report(event="signup", anomaly_type="drop", ...)
"""

from dataclasses import asdict
from datetime import datetime
from typing import Any, Literal

from fastmcp import Context

from mp_mcp.context import get_workspace
from mp_mcp.errors import handle_errors
from mp_mcp.server import mcp
from mp_mcp.types import (
    DateRange,
    Recommendation,
    Report,
    ReportSection,
)


def _gather_metrics(
    ctx: Context,
    event: str,
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    """Gather key metrics for the report period.

    Args:
        ctx: FastMCP context with workspace access.
        event: Event to analyze.
        from_date: Start date.
        to_date: End date.

    Returns:
        Dictionary with metric values.
    """
    ws = get_workspace(ctx)
    metrics: dict[str, Any] = {}

    try:
        result = ws.segmentation(
            event=event,
            from_date=from_date,
            to_date=to_date,
            unit="day",
        )
        data = result.to_dict()
        metrics["total"] = data.get("total", 0)
        metrics["series"] = data.get("series", {})
    except Exception:
        metrics["total"] = 0
        metrics["series"] = {}

    return metrics


def _analyze_trend(
    ctx: Context,
    event: str,
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    """Analyze trend for the event over the period.

    Args:
        ctx: FastMCP context with workspace access.
        event: Event to analyze.
        from_date: Start date.
        to_date: End date.

    Returns:
        Dictionary with trend analysis.
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

        # Flatten to date -> value
        time_series: dict[str, float] = {}
        if isinstance(series, dict):
            for segment_values in series.values():
                if isinstance(segment_values, dict):
                    for date_str, value in segment_values.items():
                        time_series[date_str] = float(value)
                    break

        if not time_series:
            return {"trend": "unknown", "change_percent": 0}

        sorted_dates = sorted(time_series.keys())
        if len(sorted_dates) < 2:
            return {"trend": "unknown", "change_percent": 0}

        # Compare first and last periods
        first_half = sorted_dates[: len(sorted_dates) // 2]
        second_half = sorted_dates[len(sorted_dates) // 2 :]

        first_avg = sum(time_series[d] for d in first_half) / len(first_half)
        second_avg = sum(time_series[d] for d in second_half) / len(second_half)

        if first_avg == 0:
            return {"trend": "up" if second_avg > 0 else "flat", "change_percent": 100}

        change = ((second_avg - first_avg) / first_avg) * 100

        if change > 5:
            trend = "up"
        elif change < -5:
            trend = "down"
        else:
            trend = "flat"

        return {"trend": trend, "change_percent": round(change, 1)}

    except Exception:
        return {"trend": "unknown", "change_percent": 0}


def _normalize_factor(factor: dict[str, Any]) -> tuple[str, str, float, str]:
    """Normalize a factor dict to consistent format.

    Handles both investigation-style factors (dimension/value/impact as number)
    and user-provided factors (factor/description/impact as string).

    Args:
        factor: Raw factor dictionary.

    Returns:
        Tuple of (dimension, value, numeric_impact, description).
    """
    # Get dimension - support both "dimension" and "factor" keys
    dimension = factor.get("dimension") or factor.get("factor") or "unknown"

    # Get value - support both "value" and "dimension_value" keys
    value = factor.get("value") or factor.get("dimension_value") or ""

    # Get description if available
    description = factor.get("description", "")

    # Get impact - convert string priorities to numeric values
    raw_impact = factor.get("impact", 0)
    if isinstance(raw_impact, str):
        # Map string impact levels to numeric values
        impact_map = {"critical": 40, "high": 30, "medium": 20, "low": 10}
        numeric_impact = float(impact_map.get(raw_impact.lower(), 15))
    else:
        try:
            numeric_impact = float(raw_impact)
        except (TypeError, ValueError):
            numeric_impact = 0.0

    return dimension, value, numeric_impact, description


def _generate_recommendations(
    factors: list[dict[str, Any]] | None = None,
    anomaly_type: str = "drop",
    root_cause: str | None = None,
) -> list[Recommendation]:
    """Generate recommendations based on analysis.

    Args:
        factors: Contributing factors from investigation.
        anomaly_type: Type of anomaly (drop, spike, etc.).
        root_cause: Identified root cause if any.

    Returns:
        List of prioritized recommendations.
    """
    recommendations: list[Recommendation] = []

    # Generate recommendations from factors
    if factors:
        for i, factor in enumerate(factors[:3]):
            dimension, value, impact, description = _normalize_factor(factor)

            # Build action text - prefer description if value is empty
            if value:
                action_target = f"{dimension}={value}"
            elif description:
                action_target = f"{dimension}: {description}"
            else:
                action_target = dimension

            if anomaly_type == "drop":
                if abs(impact) > 20:
                    priority: Literal["immediate", "soon", "consider"] = "immediate"
                elif abs(impact) > 10:
                    priority = "soon"
                else:
                    priority = "consider"

                recommendations.append(
                    Recommendation(
                        action=f"Investigate {action_target} which contributed "
                        f"{abs(impact):.0f}% to the {anomaly_type}",
                        priority=priority,
                        impact=f"Address {abs(impact):.0f}% of the {anomaly_type}",
                        effort="medium" if i == 0 else "low",
                    )
                )
            else:
                # For spikes, recommendations are different
                recommendations.append(
                    Recommendation(
                        action=f"Monitor {action_target} which drove "
                        f"{impact:.0f}% of the {anomaly_type}",
                        priority="soon",
                        impact=f"Understand {impact:.0f}% of the {anomaly_type}",
                        effort="low",
                    )
                )

    # Add root cause recommendation if available
    if root_cause:
        recommendations.insert(
            0,
            Recommendation(
                action=f"Address root cause: {root_cause}",
                priority="immediate",
                impact="Resolve primary driver of the issue",
                effort="medium",
            ),
        )

    # Add default recommendations if none generated
    if not recommendations:
        recommendations.append(
            Recommendation(
                action=f"Set up monitoring for early {anomaly_type} detection",
                priority="soon",
                impact="Faster response to future issues",
                effort="low",
            )
        )
        recommendations.append(
            Recommendation(
                action="Review recent deployments and changes",
                priority="immediate",
                impact="Identify potential triggers",
                effort="low",
            )
        )

    return recommendations


def _generate_key_findings(
    anomaly_type: str,
    event: str,
    trend: dict[str, Any],
    factors: list[dict[str, Any]] | None = None,
    root_cause: str | None = None,
) -> list[str]:
    """Generate key findings for the report.

    Args:
        anomaly_type: Type of anomaly.
        event: Event analyzed.
        trend: Trend analysis results.
        factors: Contributing factors.
        root_cause: Identified root cause.

    Returns:
        List of key finding strings.
    """
    findings: list[str] = []

    # Main finding about the anomaly
    change_percent = trend.get("change_percent", 0)
    if anomaly_type == "drop":
        findings.append(
            f"{event} experienced a {abs(change_percent):.0f}% decrease "
            f"during the analysis period"
        )
    else:
        findings.append(
            f"{event} showed a {change_percent:.0f}% increase "
            f"during the analysis period"
        )

    # Add root cause if known
    if root_cause:
        findings.append(f"Primary cause identified: {root_cause}")

    # Add factor findings
    if factors:
        for factor in factors[:2]:
            dimension, value, impact, description = _normalize_factor(factor)
            if dimension and dimension != "unknown":
                if value:
                    findings.append(
                        f"{dimension}={value} contributed {abs(impact):.0f}% "
                        f"to the {anomaly_type}"
                    )
                elif description:
                    findings.append(f"{dimension}: {description}")

    if not findings:
        findings.append(f"Analysis of {event} {anomaly_type} completed")

    return findings


def _generate_sections(
    event: str,
    anomaly_type: str,
    metrics: dict[str, Any],
    trend: dict[str, Any],
    factors: list[dict[str, Any]] | None = None,
) -> list[ReportSection]:
    """Generate detailed report sections.

    Args:
        event: Event analyzed.
        anomaly_type: Type of anomaly.
        metrics: Gathered metrics.
        trend: Trend analysis.
        factors: Contributing factors.

    Returns:
        List of report sections.
    """
    sections: list[ReportSection] = []

    # Overview section
    sections.append(
        ReportSection(
            title="Overview",
            content=f"This report analyzes a {anomaly_type} in {event} events. "
            f"The overall trend was {trend.get('trend', 'unknown')} "
            f"with a {trend.get('change_percent', 0):.1f}% change.",
            data={"total_events": metrics.get("total", 0)},
        )
    )

    # Contributing factors section
    if factors:
        factor_text = "The following dimensions showed significant changes:\n\n"
        for factor in factors[:5]:
            dimension, value, impact, description = _normalize_factor(factor)
            if value:
                factor_text += f"- **{dimension}={value}**: {impact:.1f}% impact\n"
            elif description:
                factor_text += f"- **{dimension}**: {description}\n"
            else:
                factor_text += f"- **{dimension}**: {impact:.1f}% impact\n"

        sections.append(
            ReportSection(
                title="Contributing Factors",
                content=factor_text,
                data={"factors": factors[:5]},
            )
        )

    # Methodology section
    sections.append(
        ReportSection(
            title="Methodology",
            content="This analysis used segmentation queries to identify trends "
            "and dimensional breakdowns to identify contributing factors. "
            "All data was retrieved from Mixpanel's analytics API.",
        )
    )

    return sections


def _generate_markdown(report_obj: Report) -> str:
    """Generate markdown-formatted report.

    Args:
        report_obj: Report object to format.

    Returns:
        Markdown string.
    """
    lines: list[str] = []

    # Title
    lines.append(f"# {report_obj.title}")
    lines.append("")
    lines.append(f"*Generated: {report_obj.generated_at}*")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(report_obj.summary)
    lines.append("")

    # Key Findings
    lines.append("## Key Findings")
    lines.append("")
    for finding in report_obj.key_findings:
        lines.append(f"- {finding}")
    lines.append("")

    # Sections
    for section in report_obj.sections:
        lines.append(f"## {section.title}")
        lines.append("")
        lines.append(section.content)
        lines.append("")

    # Recommendations
    if report_obj.recommendations:
        lines.append("## Recommendations")
        lines.append("")
        for rec in report_obj.recommendations:
            priority_emoji = {
                "immediate": "🔴",
                "soon": "🟡",
                "consider": "🟢",
            }.get(rec.priority, "⚪")
            lines.append(f"{priority_emoji} **{rec.priority.upper()}**: {rec.action}")
            lines.append(f"   - Impact: {rec.impact}")
            lines.append(f"   - Effort: {rec.effort}")
            lines.append("")

    # Follow-ups
    if report_obj.suggested_follow_ups:
        lines.append("## Suggested Follow-ups")
        lines.append("")
        for follow_up in report_obj.suggested_follow_ups:
            lines.append(f"- {follow_up}")
        lines.append("")

    return "\n".join(lines)


def _generate_slack_blocks(report_obj: Report) -> list[dict[str, Any]]:
    """Generate Slack block formatting.

    Args:
        report_obj: Report object to format.

    Returns:
        List of Slack block dictionaries.
    """
    blocks: list[dict[str, Any]] = []

    # Header
    blocks.append(
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": report_obj.title,
            },
        }
    )

    # Summary
    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Summary:* {report_obj.summary}",
            },
        }
    )

    # Key findings
    findings_text = "*Key Findings:*\n"
    for finding in report_obj.key_findings[:3]:
        findings_text += f"• {finding}\n"

    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": findings_text,
            },
        }
    )

    # Recommendations
    if report_obj.recommendations:
        rec_text = "*Top Recommendations:*\n"
        for rec in report_obj.recommendations[:2]:
            priority_emoji = {
                "immediate": ":red_circle:",
                "soon": ":large_yellow_circle:",
                "consider": ":large_green_circle:",
            }.get(rec.priority, ":white_circle:")
            rec_text += f"{priority_emoji} {rec.action}\n"

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": rec_text,
                },
            }
        )

    return blocks


@mcp.tool
@handle_errors
def report(
    ctx: Context,
    event: str,
    anomaly_type: Literal["drop", "spike", "trend_change"],
    from_date: str,
    to_date: str,
    root_cause: str | None = None,
    factors: list[dict[str, Any]] | None = None,
    include_slack_blocks: bool = False,
) -> dict[str, Any]:
    """Generate a report synthesizing analysis findings.

    Creates a comprehensive report with executive summary,
    key findings, recommendations, and formatted output.

    Args:
        ctx: FastMCP context with workspace access.
        event: Event that was analyzed.
        anomaly_type: Type of anomaly detected.
        from_date: Start date of analysis period (YYYY-MM-DD).
        to_date: End date of analysis period (YYYY-MM-DD).
        root_cause: Optional identified root cause.
        factors: Optional list of contributing factors from investigation.
        include_slack_blocks: Whether to include Slack-formatted output.

    Returns:
        Dictionary containing:
        - title: Report title
        - generated_at: Timestamp
        - period_analyzed: Date range
        - summary: Executive summary
        - key_findings: Key findings list
        - sections: Detailed sections
        - recommendations: Prioritized recommendations
        - markdown: Full markdown report
        - slack_blocks: Optional Slack formatting

    Example:
        Ask: "Generate a report on the signup drop"
        Uses: report(
            event="signup",
            anomaly_type="drop",
            from_date="2025-01-01",
            to_date="2025-01-24",
        )
    """
    # Gather metrics and trend
    metrics = _gather_metrics(ctx, event, from_date, to_date)
    trend = _analyze_trend(ctx, event, from_date, to_date)

    # Generate report components
    key_findings = _generate_key_findings(
        anomaly_type=anomaly_type,
        event=event,
        trend=trend,
        factors=factors,
        root_cause=root_cause,
    )

    sections = _generate_sections(
        event=event,
        anomaly_type=anomaly_type,
        metrics=metrics,
        trend=trend,
        factors=factors,
    )

    recommendations = _generate_recommendations(
        factors=factors,
        anomaly_type=anomaly_type,
        root_cause=root_cause,
    )

    # Generate suggested follow-ups
    suggested_follow_ups: list[str] = [
        f"Continue monitoring {event} for changes",
        "Set up alerts for similar anomalies",
    ]
    if not root_cause:
        suggested_follow_ups.insert(
            0, "Conduct deeper investigation to identify root cause"
        )

    # Create title
    title = f"Analytics Brief: {event.title()} {anomaly_type.title()}"

    # Create summary
    change_percent = trend.get("change_percent", 0)
    if root_cause:
        summary = (
            f"{event} experienced a {abs(change_percent):.0f}% {anomaly_type} "
            f"during the analysis period. Root cause identified: {root_cause}. "
            f"See recommendations below."
        )
    else:
        summary = (
            f"{event} showed a {abs(change_percent):.0f}% change during the "
            f"analysis period. Further investigation may be needed to identify "
            f"the root cause."
        )

    # Build Report object
    period = DateRange(from_date=from_date, to_date=to_date)
    generated_at = datetime.now().isoformat()

    report_obj = Report(
        title=title,
        generated_at=generated_at,
        period_analyzed=period,
        summary=summary,
        key_findings=key_findings,
        sections=sections,
        recommendations=recommendations,
        methodology="Segmentation and dimensional analysis via Mixpanel API",
        suggested_follow_ups=suggested_follow_ups,
    )

    # Generate markdown
    report_obj.markdown = _generate_markdown(report_obj)

    # Generate Slack blocks if requested
    if include_slack_blocks:
        report_obj.slack_blocks = _generate_slack_blocks(report_obj)

    return asdict(report_obj)
