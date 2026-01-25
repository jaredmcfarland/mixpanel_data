# Research: Operational Analytics Loop

**Feature**: 022-analytics-loop
**Date**: 2025-01-24
**Status**: Complete

## Research Topics

### 1. Anomaly Detection Algorithms

**Question**: What statistical methods should be used for detecting anomalies in analytics data?

**Decision**: Use a tiered approach with multiple detection methods.

**Methods Selected**:

1. **Z-Score for Daily Metrics** (Sensitivity: Medium/High)
   - Compare each day's value to rolling 30-day mean
   - Z > 2.0 = medium severity, Z > 3.0 = high severity
   - Works well for normally distributed metrics

2. **IQR (Interquartile Range) for Skewed Data** (Sensitivity: Low/Medium)
   - Q1 - 1.5*IQR to Q3 + 1.5*IQR defines normal range
   - More robust to outliers than z-score
   - Use for metrics with heavy tails (revenue, session duration)

3. **Percentage Change for Period Comparison** (Sensitivity: Configurable)
   - Compare current period to previous period
   - Thresholds: Low (>30%), Medium (>20%), High (>10%)
   - Simple, interpretable, business-friendly

4. **Trend Break Detection** (Simple Moving Average Cross)
   - 7-day SMA crosses 30-day SMA
   - Detects sustained shifts vs one-off spikes
   - Avoid complex change point detection (PELT, Bayesian) - overkill for this use case

**Rationale**: Complex ML-based detection requires training data and adds dependencies. Statistical methods are interpretable, fast, and sufficient for operational monitoring. The scan tool should surface candidates for human/agent judgment, not be a perfect classifier.

**Alternatives Rejected**:
- Prophet/ARIMA: Too slow, adds heavy dependencies
- Isolation Forest: Requires tuning, black-box
- Bayesian change point: Computationally expensive

---

### 2. Caching Strategy

**Question**: How to leverage existing caching middleware for workflow tools?

**Decision**: Rely on existing caching for discovery calls; add TTL hints for composed results.

**Existing Caching** (in `middleware/caching.py`):
- Auto-caches: `list_events`, `list_properties`, `list_funnels`, `list_cohorts`, `list_bookmarks`
- Default TTL: 300 seconds (5 minutes)
- No code changes needed for discovery primitives

**New Caching Considerations**:

1. **context tool**: All calls are cacheable primitives → fully cached automatically
2. **health tool**: Live queries (segmentation, retention) → NOT cached (fresh data needed)
3. **scan tool**: Mixed - discovery cached, queries fresh
4. **investigate tool**: Fresh queries needed for accurate diagnosis
5. **report tool**: Synthesis only, no caching applicable

**Rationale**: The caching middleware was designed for discovery. Live query results should be fresh to ensure accurate analysis. Adding query caching would require invalidation logic and could mask real changes.

**Alternatives Rejected**:
- Query result caching: Stale data risks in monitoring context
- Session-scoped cache: Would require shared state, violates stateless principle

---

### 3. Graceful Degradation Pattern

**Question**: How should intelligent tools behave when LLM sampling is unavailable?

**Decision**: Return structured raw data with analysis hints.

**Pattern** (from existing `diagnose_metric_drop`):

```python
@mcp.tool
@handle_errors
def intelligent_tool(ctx: Context, ...) -> dict[str, Any]:
    # Step 1: Gather data (always works)
    ws = get_workspace(ctx)
    raw_data = ws.some_query(...)

    # Step 2: Try synthesis
    try:
        synthesis = ctx.sample(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system="You are a Mixpanel analytics expert.",
            messages=[{"role": "user", "content": build_prompt(raw_data)}],
        )
        return {
            "status": "success",
            "synthesis": synthesis,
            "raw_data": raw_data,
        }
    except Exception:
        # Step 3: Graceful degradation
        return {
            "status": "sampling_unavailable",
            "raw_data": raw_data,
            "analysis_hints": [
                "Compare period-over-period changes",
                "Look for segment-specific patterns",
                "Check for temporal clustering",
            ],
        }
```

**Rationale**: Agents may run in environments where sampling is disabled or quota-limited. Raw data + hints enables agent to reason independently.

**Tools Using This Pattern**:
- `scan`: Synthesis ranks/prioritizes anomalies → degraded: raw anomaly list
- `investigate`: Synthesis identifies root cause → degraded: factor analysis data
- `report`: Synthesis generates prose → degraded: structured findings JSON

---

### 4. Anomaly ID Generation

**Question**: How to generate stable, deterministic IDs for anomalies?

**Decision**: Use content-based hashing with semantic components.

**ID Format**: `{event}_{type}_{date}_{hash8}`

**Hash Components**:
- Event name
- Anomaly type (drop, spike, trend_change, segment_shift)
- Detection date
- Dimension (if segment-specific)
- Dimension value (if segment-specific)

**Example IDs**:
- `signup_drop_2025-01-15_a3f2b1c9`
- `purchase_spike_2025-01-18_7d4e2f1a`
- `login_segment_shift_2025-01-10_country_US_b2c1d3e4`

**Implementation**:

```python
import hashlib

def generate_anomaly_id(
    event: str,
    anomaly_type: str,
    date: str,
    dimension: str | None = None,
    dimension_value: str | None = None,
) -> str:
    """Generate deterministic anomaly ID."""
    components = [event, anomaly_type, date]
    if dimension and dimension_value:
        components.extend([dimension, dimension_value])

    content = "|".join(components)
    hash_digest = hashlib.sha256(content.encode()).hexdigest()[:8]

    base = f"{event}_{anomaly_type}_{date}"
    if dimension and dimension_value:
        base = f"{base}_{dimension}_{dimension_value}"

    return f"{base}_{hash_digest}"
```

**Rationale**:
- Content-based = same anomaly gets same ID across scans
- Human-readable prefix = easy to understand what it refers to
- Short hash suffix = handles edge cases, ensures uniqueness

**Alternatives Rejected**:
- UUID: Not deterministic, can't reference same anomaly twice
- Sequential: Requires state persistence
- Timestamp-based: Ties ID to scan time, not anomaly time

---

### 5. Existing Tool Audit

**Question**: Which existing primitives will each workflow tool compose?

**Audit Results**:

| Workflow Tool | Primitives | Notes |
|---------------|------------|-------|
| context | `workspace_info`, `list_events`, `top_events(20)`, `list_funnels`, `list_cohorts`, `list_bookmarks(50)`, `lexicon_schemas` (optional) | All discovery, fully cached |
| health | `product_health_dashboard`, `event_counts`, `segmentation` (daily), `retention` | Mixed: dashboard is composed, queries are fresh |
| scan | `segmentation` (per-event), `property_counts`, `retention`, `funnel`, `jql` (custom) | Heavy query load, use parallel where possible |
| investigate | `diagnose_metric_drop`, `cohort_comparison`, `property_distribution`, `segmentation`, `activity_feed` | Existing diagnose tool is similar, reuse logic |
| report | (none - synthesis only) | Uses investigation results, no new queries |

**Key Finding**: The existing `diagnose_metric_drop` tool in `tools/intelligent/diagnose.py` already implements much of what `investigate` needs. Consider reusing its internal functions.

---

### 6. Rate Limiting Considerations

**Question**: Will workflow tools hit rate limits?

**Analysis**:

| Tool | Est. API Calls | Concern |
|------|----------------|---------|
| context | 7 | Low - all cacheable |
| health | 5-8 | Medium - mixed queries |
| scan | 10-30 | High - per-event scans |
| investigate | 5-10 | Medium - targeted queries |
| report | 0 | None - synthesis only |

**Full Workflow**: 27-55 API calls

**Rate Limit Budget**: 60 queries/hour, 5 concurrent

**Mitigation Strategies**:
1. **Prioritize events in scan**: Only scan top 10-20 events by default
2. **Use existing rate limiter**: `RateLimitedWorkspace` handles queuing
3. **Cache discovery**: Reduces calls by ~30%
4. **Batch where possible**: JQL can aggregate multiple checks

**Rationale**: Rate limiting is handled by middleware. Workflow tools should document their query budget in docstrings so users can plan accordingly.

---

## Summary of Decisions

| Decision | Choice | Confidence |
|----------|--------|------------|
| Anomaly detection | Z-score + IQR + % change | High |
| Caching | Use existing middleware | High |
| Degradation | Raw data + hints | High |
| Anomaly IDs | Content-based hash | High |
| Rate limiting | Trust middleware, document budget | High |

All research complete. Ready for Phase 1 design.
