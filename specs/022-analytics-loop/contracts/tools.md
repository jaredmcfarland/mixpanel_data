# Tool Contracts: Operational Analytics Loop

**Feature**: 022-analytics-loop
**Date**: 2025-01-24

## Tool Signatures

### 1. context

```python
@mcp.tool
@handle_errors
def context(
    ctx: Context,
    include_schemas: bool = False,
    include_sample_values: bool = False,
) -> dict[str, Any]:
    """Gather project context for analytics workflow.

    Aggregates project metadata, available events, funnels, cohorts,
    and bookmarks to provide foundation for subsequent analysis tools.
    This is typically the first step in the Operational Analytics Loop.

    Args:
        ctx: FastMCP context with workspace access.
        include_schemas: Include Lexicon schema definitions (slower).
        include_sample_values: Include sample property values (slower).

    Returns:
        Dictionary containing:
        - project: Project metadata (id, name, region)
        - events: Summary of tracked events (total, top_events, categories)
        - properties: Summary of available properties
        - funnels: List of saved funnel summaries
        - cohorts: List of saved cohort summaries
        - bookmarks: Summary of saved reports
        - date_range: Available data date range
        - schemas: Lexicon schemas (if include_schemas=True)

    Example:
        Ask: "Give me context on my Mixpanel project"
        Uses: context()

        Ask: "Show me my project schema including Lexicon"
        Uses: context(include_schemas=True)
    """
```

**Primitives Used**: `workspace_info`, `list_events`, `top_events`, `list_funnels`, `list_cohorts`, `list_bookmarks`, `lexicon_schemas`

**Caching**: All calls are discovery primitives → fully cached (5 min TTL)

**Rate Limit Budget**: ~7 API calls (all cacheable)

---

### 2. health

```python
@mcp.tool
@handle_errors
def health(
    ctx: Context,
    from_date: str | None = None,
    to_date: str | None = None,
    compare_period: str = "previous",
    focus: str | None = None,
    events: list[str] | None = None,
) -> dict[str, Any]:
    """Generate product health dashboard with KPIs and trends.

    Provides current period metrics with comparison to baseline,
    highlights positive changes, and flags concerning trends.

    Args:
        ctx: FastMCP context with workspace access.
        from_date: Start date (YYYY-MM-DD). Default: 30 days ago.
        to_date: End date (YYYY-MM-DD). Default: today.
        compare_period: Comparison baseline - "previous" (default),
            "yoy" (year-over-year), or specific dates "YYYY-MM-DD:YYYY-MM-DD".
        focus: Focus area - "acquisition", "activation", "retention", "revenue".
            If None, shows all AARRR metrics.
        events: Specific events to track. If None, uses top events.

    Returns:
        Dictionary containing:
        - period: Current analysis period
        - comparison_period: Baseline period
        - metrics: List of metrics with current/previous/change values
        - aarrr: AARRR framework breakdown (if determinable)
        - highlights: Positive observations
        - concerns: Concerning observations
        - daily_series: Time series data for trends

    Example:
        Ask: "How is my product doing?"
        Uses: health()

        Ask: "Show me acquisition metrics for January"
        Uses: health(from_date="2025-01-01", to_date="2025-01-31", focus="acquisition")

        Ask: "Compare this week to last year"
        Uses: health(compare_period="yoy")
    """
```

**Primitives Used**: `product_health_dashboard`, `event_counts`, `segmentation`, `retention`

**Caching**: Live queries → NOT cached (fresh data needed)

**Rate Limit Budget**: ~5-8 API calls

---

### 3. scan

```python
@mcp.tool
@handle_errors
def scan(
    ctx: Context,
    from_date: str | None = None,
    to_date: str | None = None,
    sensitivity: str = "medium",
    dimensions: list[str] | None = None,
    events: list[str] | None = None,
    include_opportunities: bool = True,
) -> dict[str, Any]:
    """Detect anomalies and interesting signals across the product.

    Scans key metrics for statistical anomalies using z-score, IQR,
    and trend break detection. Returns ranked list of signals with
    unique IDs for investigation.

    Args:
        ctx: FastMCP context with workspace access.
        from_date: Start date (YYYY-MM-DD). Default: 30 days ago.
        to_date: End date (YYYY-MM-DD). Default: today.
        sensitivity: Detection sensitivity - "low" (>30% change),
            "medium" (>20%), "high" (>10%).
        dimensions: Properties to analyze for segment-specific anomalies.
        events: Specific events to scan. If None, uses top 20 events.
        include_opportunities: Include positive signals (spikes, growth).

    Returns:
        Dictionary containing:
        - period: Date range scanned
        - anomalies: List of detected anomalies with:
            - id: Unique identifier for investigation
            - type: "drop", "spike", "trend_change", "segment_shift"
            - severity: "critical", "high", "medium", "low"
            - summary: Human-readable description
            - confidence: Statistical confidence (0-1)
        - scan_coverage: What was analyzed
        - baseline_stats: Baseline statistics for context

        If sampling unavailable, returns raw anomaly data with analysis_hints.

    Example:
        Ask: "Are there any anomalies in my data?"
        Uses: scan()

        Ask: "Scan for issues by country with high sensitivity"
        Uses: scan(sensitivity="high", dimensions=["country"])

        Ask: "Only show me problems, not opportunities"
        Uses: scan(include_opportunities=False)
    """
```

**Primitives Used**: `segmentation`, `property_counts`, `retention`, `funnel`, `jql`

**Caching**: Mixed - discovery cached, queries fresh

**Rate Limit Budget**: ~10-30 API calls (depends on event/dimension count)

**Sampling**: Yes (graceful degradation to raw data + hints)

---

### 4. investigate

```python
@mcp.tool
@handle_errors
def investigate(
    ctx: Context,
    anomaly_id: str | None = None,
    event: str | None = None,
    date: str | None = None,
    dimension: str | None = None,
    depth: str = "standard",
    hypotheses: list[str] | None = None,
) -> dict[str, Any]:
    """Deep-dive investigation into a specific anomaly.

    Performs dimensional decomposition, temporal analysis, and cohort
    comparison to identify root cause of an anomaly.

    Args:
        ctx: FastMCP context with workspace access.
        anomaly_id: Anomaly ID from scan results (preferred).
        event: Event name for manual investigation (if no anomaly_id).
        date: Date to investigate (YYYY-MM-DD, if no anomaly_id).
        dimension: Specific dimension to focus on.
        depth: Investigation depth - "quick" (fast, surface-level),
            "standard" (balanced), "deep" (thorough, slow).
        hypotheses: Suggested causes to prioritize testing.

    Returns:
        Dictionary containing:
        - anomaly: The anomaly being investigated
        - root_cause: Primary identified cause (if determined)
        - contributing_factors: Factors with contribution % and confidence
        - segments_analyzed: Segment breakdown
        - timeline: Chronological timeline of events
        - affected_vs_unaffected: Comparison data
        - confidence: Overall analysis confidence
        - limitations: What couldn't be determined
        - queries_run: Queries executed for transparency

        If sampling unavailable, returns raw analysis data with analysis_hints.

    Raises:
        ValueError: If neither anomaly_id nor (event + date) provided.

    Example:
        Ask: "Investigate the signup drop from the scan"
        Uses: investigate(anomaly_id="signup_drop_2025-01-15_a3f2b1c9")

        Ask: "What happened to signups on January 15?"
        Uses: investigate(event="signup", date="2025-01-15")

        Ask: "Do a quick check on the login issue"
        Uses: investigate(anomaly_id="...", depth="quick")

        Ask: "Test if this was caused by mobile Safari"
        Uses: investigate(anomaly_id="...", hypotheses=["Mobile Safari change"])
    """
```

**Primitives Used**: `diagnose_metric_drop`, `cohort_comparison`, `property_distribution`, `segmentation`, `activity_feed`

**Caching**: Fresh queries needed for accurate diagnosis

**Rate Limit Budget**: ~5-10 API calls

**Sampling**: Yes (graceful degradation to raw data + hints)

---

### 5. report

```python
@mcp.tool
@handle_errors
def report(
    ctx: Context,
    investigation: dict[str, Any] | None = None,
    findings: list[str] | None = None,
    format: str = "executive",
    include_methodology: bool = False,
    include_recommendations: bool = True,
) -> dict[str, Any]:
    """Synthesize findings into an actionable report.

    Generates a formatted report from investigation results or
    manual findings, with recommendations and follow-up suggestions.

    Args:
        ctx: FastMCP context with workspace access.
        investigation: Investigation result from investigate tool.
        findings: Manual findings list (if no investigation).
        format: Output format - "executive" (concise), "detailed" (full),
            "slack" (includes Slack blocks).
        include_methodology: Include how findings were discovered.
        include_recommendations: Include action recommendations.

    Returns:
        Dictionary containing:
        - title: Report title
        - generated_at: Generation timestamp
        - period_analyzed: Date range covered
        - summary: Executive summary (2-3 sentences)
        - key_findings: Bullet-point findings
        - sections: Detailed report sections
        - recommendations: Prioritized recommendations with effort/impact
        - suggested_follow_ups: Next steps
        - markdown: Full report in markdown format
        - slack_blocks: Slack block format (if format="slack")

        If sampling unavailable, returns structured data without prose synthesis.

    Raises:
        ValueError: If neither investigation nor findings provided.

    Example:
        Ask: "Generate a report from the investigation"
        Uses: report(investigation=investigation_result)

        Ask: "Create a Slack-formatted report with methodology"
        Uses: report(investigation=..., format="slack", include_methodology=True)

        Ask: "Write up these findings: signups down, mobile affected"
        Uses: report(findings=["Signups down 23%", "Mobile Safari affected"])
    """
```

**Primitives Used**: None (synthesis only)

**Caching**: N/A

**Rate Limit Budget**: 0 API calls

**Sampling**: Yes (graceful degradation to structured JSON)

---

## Error Handling

All tools use the `@handle_errors` decorator which converts exceptions to `ToolError`:

| Exception | ToolError Message | Guidance |
|-----------|-------------------|----------|
| `AuthenticationError` | Authentication failed | Check credentials |
| `RateLimitError` | Rate limit exceeded | Wait and retry |
| `InvalidParameterError` | Invalid parameter | Check parameter values |
| `NotFoundError` | Resource not found | Verify event/funnel exists |
| `MixpanelAPIError` | API error | Check Mixpanel status |

## Workflow Integration

Typical usage flow:

```
/context                           # Prime context
   ↓
/health                            # Check KPIs
   ↓
/scan                              # Find anomalies
   ↓
/investigate anomaly_id=...        # Root cause
   ↓
/report investigation=...          # Generate report
```

Each tool is also independently usable for ad-hoc analysis.
