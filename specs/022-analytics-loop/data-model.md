# Data Model: Operational Analytics Loop

**Feature**: 022-analytics-loop
**Date**: 2025-01-24

## Overview

This document defines the dataclass models for the five workflow tools. All models are Python dataclasses that serialize to JSON via `asdict()`.

## Supporting Types

These types are used by multiple workflow tools:

```python
from dataclasses import dataclass, field
from typing import Any, Literal

@dataclass
class DateRange:
    """Date range for analytics queries.

    Attributes:
        from_date: Start date in YYYY-MM-DD format.
        to_date: End date in YYYY-MM-DD format.
    """
    from_date: str
    to_date: str


@dataclass
class Metric:
    """A single metric with current and comparison values.

    Attributes:
        name: Metric identifier (e.g., "signups", "d7_retention").
        display_name: Human-readable name.
        current: Current period value.
        previous: Comparison period value.
        change_percent: Percentage change from previous.
        trend: Direction indicator.
        unit: Metric unit (e.g., "count", "percent", "currency").
    """
    name: str
    display_name: str
    current: float
    previous: float
    change_percent: float
    trend: Literal["up", "down", "flat"]
    unit: str = "count"


@dataclass
class DataPoint:
    """Single data point for time series.

    Attributes:
        date: Date in YYYY-MM-DD format.
        value: Numeric value for that date.
    """
    date: str
    value: float
```

## Context Tool Types

```python
@dataclass
class EventsSummary:
    """Summary of tracked events.

    Attributes:
        total: Total number of distinct events.
        top_events: List of most active event names.
        categories: Event counts by category (if categorized).
    """
    total: int
    top_events: list[str]
    categories: dict[str, int] = field(default_factory=dict)


@dataclass
class PropertiesSummary:
    """Summary of event and user properties.

    Attributes:
        event_properties: Count of event properties.
        user_properties: Count of user/profile properties.
        common: Properties that appear across multiple events.
    """
    event_properties: int
    user_properties: int
    common: list[str] = field(default_factory=list)


@dataclass
class FunnelSummary:
    """Summary of a saved funnel.

    Attributes:
        id: Funnel ID in Mixpanel.
        name: Funnel name.
        steps: Number of steps in the funnel.
    """
    id: int
    name: str
    steps: int


@dataclass
class CohortSummary:
    """Summary of a saved cohort.

    Attributes:
        id: Cohort ID in Mixpanel.
        name: Cohort name.
        count: Approximate user count.
    """
    id: int
    name: str
    count: int


@dataclass
class BookmarksSummary:
    """Summary of saved reports/bookmarks.

    Attributes:
        total: Total number of saved reports.
        by_type: Counts by report type (insight, board, etc.).
    """
    total: int
    by_type: dict[str, int] = field(default_factory=dict)


@dataclass
class ContextPackage:
    """Complete project context for analytics workflow.

    Aggregates project metadata, available events, funnels, cohorts,
    and bookmarks to provide foundation for subsequent analysis.

    Attributes:
        project: Project metadata (id, name, region).
        events: Summary of tracked events.
        properties: Summary of available properties.
        funnels: List of saved funnel summaries.
        cohorts: List of saved cohort summaries.
        bookmarks: Summary of saved reports.
        date_range: Available data date range.
        schemas: Optional Lexicon schema definitions.

    Example:
        ```python
        context = ContextPackage(
            project={"id": "123456", "name": "MyApp", "region": "us"},
            events=EventsSummary(total=47, top_events=["signup", "login"]),
            properties=PropertiesSummary(event_properties=120, user_properties=45),
            funnels=[FunnelSummary(id=1, name="Signup Flow", steps=4)],
            cohorts=[CohortSummary(id=101, name="Power Users", count=15000)],
            bookmarks=BookmarksSummary(total=12, by_type={"insight": 8, "board": 4}),
            date_range=DateRange(from_date="2024-01-01", to_date="2025-01-24"),
        )
        ```
    """
    project: dict[str, Any]
    events: EventsSummary
    properties: PropertiesSummary
    funnels: list[FunnelSummary]
    cohorts: list[CohortSummary]
    bookmarks: BookmarksSummary
    date_range: DateRange
    schemas: list[dict[str, Any]] | None = None
```

## Health Tool Types

```python
@dataclass
class HealthDashboard:
    """Product health metrics dashboard with period comparison.

    Provides current KPIs, comparison to baseline period,
    and quick insights for monitoring product health.

    Attributes:
        period: Current analysis period.
        comparison_period: Baseline period for comparison.
        metrics: List of key metrics with current/previous values.
        aarrr: Optional AARRR framework breakdown.
        highlights: List of positive observations.
        concerns: List of concerning observations.
        daily_series: Time series data by metric name.

    Example:
        ```python
        dashboard = HealthDashboard(
            period=DateRange("2025-01-01", "2025-01-24"),
            comparison_period=DateRange("2024-12-01", "2024-12-24"),
            metrics=[
                Metric("signups", "Signups", 12450, 14200, -12.3, "down"),
                Metric("d7_retention", "D7 Retention", 0.18, 0.21, -14.3, "down", "percent"),
            ],
            highlights=["Activation rate improved 2pp"],
            concerns=["Signups down 12%", "Retention softening"],
        )
        ```
    """
    period: DateRange
    comparison_period: DateRange
    metrics: list[Metric]
    aarrr: dict[str, Any] | None = None
    highlights: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    daily_series: dict[str, list[DataPoint]] = field(default_factory=dict)
```

## Scan Tool Types

```python
@dataclass
class Anomaly:
    """Detected anomaly or signal for investigation.

    Represents a statistical anomaly detected during scan,
    with unique ID for reference in investigate tool.

    Attributes:
        id: Unique identifier for this anomaly (deterministic).
        type: Type of anomaly detected.
        severity: Severity level based on magnitude and impact.
        category: AARRR category or custom category.
        summary: Human-readable description.
        event: Primary event involved.
        dimension: Property name if segment-specific.
        dimension_value: Property value if segment-specific.
        detected_at: Date when anomaly was detected.
        magnitude: Size of change (absolute or percentage).
        confidence: Statistical confidence (0.0 to 1.0).
        context: Additional context for investigation.

    Example:
        ```python
        anomaly = Anomaly(
            id="signup_drop_2025-01-15_a3f2b1c9",
            type="drop",
            severity="high",
            category="acquisition",
            summary="Signup conversion dropped 23% on Jan 15",
            event="signup",
            detected_at="2025-01-15",
            magnitude=23.0,
            confidence=0.92,
        )
        ```
    """
    id: str
    type: Literal["drop", "spike", "trend_change", "segment_shift"]
    severity: Literal["critical", "high", "medium", "low"]
    category: str
    summary: str
    event: str
    dimension: str | None = None
    dimension_value: str | None = None
    detected_at: str = ""
    magnitude: float = 0.0
    confidence: float = 0.0
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanResults:
    """Results from anomaly detection scan.

    Contains ranked list of detected anomalies and metadata
    about what was analyzed.

    Attributes:
        period: Date range that was scanned.
        anomalies: List of detected anomalies, ranked by severity * confidence.
        scan_coverage: What events/dimensions were analyzed.
        baseline_stats: Baseline statistics for context.

    Example:
        ```python
        results = ScanResults(
            period=DateRange("2025-01-01", "2025-01-24"),
            anomalies=[anomaly1, anomaly2],
            scan_coverage={"events_scanned": 20, "dimensions_scanned": 5},
            baseline_stats={"avg_daily_signups": 450, "avg_d7_retention": 0.20},
        )
        ```
    """
    period: DateRange
    anomalies: list[Anomaly]
    scan_coverage: dict[str, Any] = field(default_factory=dict)
    baseline_stats: dict[str, Any] = field(default_factory=dict)
```

## Investigate Tool Types

```python
@dataclass
class ContributingFactor:
    """Factor contributing to an anomaly.

    Attributes:
        factor: Description of the factor (e.g., "Mobile Safari users").
        contribution: Percentage of total change explained (0-100).
        evidence: Supporting data or observation.
        confidence: Confidence level in this factor.

    Example:
        ```python
        factor = ContributingFactor(
            factor="Mobile Safari iOS 17 users",
            contribution=78.0,
            evidence="67% drop in this segment vs 5% in others",
            confidence="high",
        )
        ```
    """
    factor: str
    contribution: float
    evidence: str
    confidence: Literal["high", "medium", "low"]


@dataclass
class TimelineEvent:
    """Event in the anomaly timeline.

    Attributes:
        timestamp: When the event occurred.
        description: What happened.
        significance: How significant this event is.
    """
    timestamp: str
    description: str
    significance: Literal["high", "medium", "low"]


@dataclass
class Investigation:
    """Complete root cause analysis for an anomaly.

    Contains contributing factors, timeline, segment analysis,
    and supporting evidence.

    Attributes:
        anomaly: The anomaly being investigated.
        root_cause: Primary identified cause (if determined).
        contributing_factors: Factors explaining the anomaly.
        segments_analyzed: Segments that were analyzed.
        timeline: Timeline of relevant events.
        affected_vs_unaffected: Comparison of affected vs unaffected users.
        confidence: Overall confidence in the analysis.
        limitations: What couldn't be determined.
        queries_run: List of queries executed for transparency.
        data_points: Raw data supporting the analysis.

    Example:
        ```python
        investigation = Investigation(
            anomaly=anomaly,
            root_cause="Email validation regex broke on iOS 17 Safari",
            contributing_factors=[factor1, factor2],
            timeline=[
                TimelineEvent("2025-01-14 23:00", "Deploy detected", "high"),
                TimelineEvent("2025-01-15 02:00", "First impact visible", "high"),
            ],
            confidence="high",
            limitations=["Cannot confirm code change without deploy logs"],
        )
        ```
    """
    anomaly: Anomaly
    root_cause: str | None = None
    contributing_factors: list[ContributingFactor] = field(default_factory=list)
    segments_analyzed: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    affected_vs_unaffected: dict[str, Any] = field(default_factory=dict)
    confidence: Literal["high", "medium", "low"] = "medium"
    limitations: list[str] = field(default_factory=list)
    queries_run: list[str] = field(default_factory=list)
    data_points: dict[str, Any] = field(default_factory=dict)
```

## Report Tool Types

```python
@dataclass
class Recommendation:
    """Actionable recommendation from analysis.

    Attributes:
        action: What should be done.
        priority: When it should be done.
        impact: Expected impact of the action.
        effort: Estimated effort to implement.
        owner: Suggested owner (if determinable).

    Example:
        ```python
        rec = Recommendation(
            action="Verify iOS 17 Safari compatibility for all form validations",
            priority="immediate",
            impact="Recover 23% of lost signups",
            effort="low",
        )
        ```
    """
    action: str
    priority: Literal["immediate", "soon", "consider"]
    impact: str
    effort: Literal["low", "medium", "high"]
    owner: str | None = None


@dataclass
class ReportSection:
    """Section within a report.

    Attributes:
        title: Section heading.
        content: Section content (markdown).
        data: Optional structured data for the section.
    """
    title: str
    content: str
    data: dict[str, Any] | None = None


@dataclass
class Report:
    """Synthesized findings report.

    Complete report with executive summary, findings,
    recommendations, and formatted output.

    Attributes:
        title: Report title.
        generated_at: Timestamp when report was generated.
        period_analyzed: Date range covered by analysis.
        summary: Executive summary (2-3 sentences).
        key_findings: Bullet-point key findings.
        sections: Detailed report sections.
        recommendations: Prioritized recommendations.
        methodology: Optional methodology description.
        queries_run: Optional list of queries for transparency.
        suggested_follow_ups: Suggested next steps.
        markdown: Full report in markdown format.
        slack_blocks: Optional Slack block formatting.

    Example:
        ```python
        report = Report(
            title="Analytics Brief: Signup Conversion Issue",
            generated_at="2025-01-24T10:30:00Z",
            period_analyzed=DateRange("2025-01-01", "2025-01-24"),
            summary="A deployment on January 14th broke email validation...",
            key_findings=[
                "Signup conversion dropped 23% starting January 15",
                "Root cause: Email validation regex incompatible with iOS 17",
            ],
            recommendations=[rec1, rec2],
            suggested_follow_ups=["Quantify revenue impact"],
        )
        ```
    """
    title: str
    generated_at: str
    period_analyzed: DateRange
    summary: str
    key_findings: list[str]
    sections: list[ReportSection] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    methodology: str | None = None
    queries_run: list[str] | None = None
    suggested_follow_ups: list[str] = field(default_factory=list)
    markdown: str = ""
    slack_blocks: list[dict[str, Any]] | None = None
```

## Type Registry

Summary of all new types to add to `mp_mcp/src/mp_mcp/types.py`:

| Type | Category | Used By |
|------|----------|---------|
| DateRange | Supporting | All tools |
| Metric | Supporting | health |
| DataPoint | Supporting | health |
| EventsSummary | Context | context |
| PropertiesSummary | Context | context |
| FunnelSummary | Context | context |
| CohortSummary | Context | context |
| BookmarksSummary | Context | context |
| ContextPackage | Context | context |
| HealthDashboard | Health | health |
| Anomaly | Scan | scan, investigate |
| ScanResults | Scan | scan |
| ContributingFactor | Investigate | investigate |
| TimelineEvent | Investigate | investigate |
| Investigation | Investigate | investigate, report |
| Recommendation | Report | report |
| ReportSection | Report | report |
| Report | Report | report |

**Total**: 18 new dataclasses
