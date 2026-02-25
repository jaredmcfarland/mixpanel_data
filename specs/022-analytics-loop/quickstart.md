# Quickstart: Operational Analytics Loop

**Feature**: 022-analytics-loop
**Date**: 2025-01-24

## Overview

The Operational Analytics Loop provides five MCP tools for systematic product health monitoring:

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `context` | Prime context with project landscape | Start of analysis session |
| `health` | Generate KPI dashboard | Daily/weekly health checks |
| `scan` | Detect anomalies | Find issues proactively |
| `investigate` | Root cause analysis | Deep-dive into anomalies |
| `report` | Synthesize findings | Share insights with team |

## Full Workflow Example

### Daily Analytics Check

```
User: Run my daily analytics check

Agent: I'll run through the Operational Analytics Loop.

[Calls context()]
Your project "MyApp" (ID: 123456) has:
- 47 events tracked (top: signup, login, purchase)
- 5 saved funnels
- 8 cohorts defined
- Data from Jan 2024 to today

[Calls health()]
**Health Dashboard (Last 30 days vs previous 30 days)**

| Metric | Current | Previous | Change |
|--------|---------|----------|--------|
| Signups | 12,450 | 14,200 | -12.3% ⚠️ |
| Activation | 34% | 32% | +2pp ✅ |
| D7 Retention | 18% | 21% | -3pp ⚠️ |

Concerns: Signups down, retention softening

[Calls scan()]
**Anomalies Detected (3)**

1. **[HIGH]** signup_drop_2025-01-15_a3f2b1c9
   - Signup conversion dropped 23% on Jan 15
   - Affected: Mobile web users
   - Confidence: 92%

2. **[MEDIUM]** retention_decline_2025-01-10_b2c1d3e4
   - D7 retention 4pp below baseline
   - Confidence: 78%

The signup drop looks critical. Should I investigate?

User: Yes, investigate the signup drop

[Calls investigate(anomaly_id="signup_drop_2025-01-15_a3f2b1c9")]
**Investigation: Signup Drop**

**Root Cause:** Mobile Safari users on iOS 17 experienced 67% drop
in signup completion due to email validation change.

**Contributing Factors:**
1. Mobile Safari iOS 17: 78% of impact (high confidence)
2. Signup step 2 abandonment: up 340%
3. Email validation errors: 2% → 34%

User: Generate a report

[Calls report()]
**📊 Analytics Brief: Signup Conversion Issue**

**Summary:** A deployment on Jan 14 broke email validation for
Mobile Safari users on iOS 17, causing 23% signup drop.

**Recommendations:**
1. **Immediate**: Verify iOS 17 Safari compatibility
2. **Soon**: Add browser-specific E2E tests
3. **Consider**: Real-time conversion monitoring
```

## Individual Tool Examples

### context - Project Landscape

```
# Basic context
Ask: "What's in my Mixpanel project?"
Uses: context()

# With schema details
Ask: "Show me the project including Lexicon schemas"
Uses: context(include_schemas=True)
```

**Output:**
```json
{
  "project": {"id": "123456", "name": "MyApp", "region": "us"},
  "events": {
    "total": 47,
    "top_events": ["signup", "login", "purchase", "page_view"],
    "categories": {"acquisition": 5, "activation": 8}
  },
  "funnels": [
    {"id": 1, "name": "Signup Flow", "steps": 4}
  ],
  "cohorts": [
    {"id": 101, "name": "Power Users", "count": 15000}
  ],
  "date_range": {"from_date": "2024-01-01", "to_date": "2025-01-24"}
}
```

### health - KPI Dashboard

```
# Quick health check
Ask: "How is my product doing?"
Uses: health()

# Specific date range
Ask: "Show me January metrics"
Uses: health(from_date="2025-01-01", to_date="2025-01-31")

# Focus on acquisition
Ask: "How are we doing on user acquisition?"
Uses: health(focus="acquisition")

# Year-over-year comparison
Ask: "Compare this month to last year"
Uses: health(compare_period="yoy")
```

**Output:**
```json
{
  "period": {"from_date": "2024-12-25", "to_date": "2025-01-24"},
  "comparison_period": {"from_date": "2024-11-25", "to_date": "2024-12-24"},
  "metrics": [
    {
      "name": "signups",
      "display_name": "Signups",
      "current": 12450,
      "previous": 14200,
      "change_percent": -12.3,
      "trend": "down"
    }
  ],
  "highlights": ["Activation rate improved 2 percentage points"],
  "concerns": ["Signups down 12%", "D7 retention softening"]
}
```

### scan - Anomaly Detection

```
# Scan for all anomalies
Ask: "Are there any issues with my metrics?"
Uses: scan()

# High sensitivity scan
Ask: "Find even small anomalies"
Uses: scan(sensitivity="high")

# Scan specific dimensions
Ask: "Check for issues by country and platform"
Uses: scan(dimensions=["country", "platform"])

# Only problems, no opportunities
Ask: "Just show me the problems"
Uses: scan(include_opportunities=False)
```

**Output:**
```json
{
  "period": {"from_date": "2024-12-25", "to_date": "2025-01-24"},
  "anomalies": [
    {
      "id": "signup_drop_2025-01-15_a3f2b1c9",
      "type": "drop",
      "severity": "high",
      "category": "acquisition",
      "summary": "Signup conversion dropped 23% on Jan 15",
      "event": "signup",
      "detected_at": "2025-01-15",
      "magnitude": 23.0,
      "confidence": 0.92
    }
  ],
  "scan_coverage": {"events_scanned": 20, "dimensions_scanned": 5}
}
```

### investigate - Root Cause Analysis

```
# Investigate from scan results
Ask: "Investigate that signup drop"
Uses: investigate(anomaly_id="signup_drop_2025-01-15_a3f2b1c9")

# Manual investigation
Ask: "What happened to signups on January 15?"
Uses: investigate(event="signup", date="2025-01-15")

# Quick investigation
Ask: "Do a quick check on the issue"
Uses: investigate(anomaly_id="...", depth="quick")

# Test specific hypothesis
Ask: "Was it caused by mobile Safari?"
Uses: investigate(anomaly_id="...", hypotheses=["Mobile Safari regression"])
```

**Output:**
```json
{
  "anomaly": {"id": "signup_drop_2025-01-15_a3f2b1c9", "...": "..."},
  "root_cause": "Email validation regex incompatible with iOS 17 Safari",
  "contributing_factors": [
    {
      "factor": "Mobile Safari iOS 17 users",
      "contribution": 78.0,
      "evidence": "67% drop in this segment vs 5% in others",
      "confidence": "high"
    }
  ],
  "timeline": [
    {"timestamp": "2025-01-14 23:00", "description": "Deploy detected", "significance": "high"},
    {"timestamp": "2025-01-15 02:00", "description": "First impact visible", "significance": "high"}
  ],
  "confidence": "high"
}
```

### report - Synthesis

```
# Report from investigation
Ask: "Generate a report on this"
Uses: report(investigation=investigation_result)

# Slack-formatted report
Ask: "Create a report for Slack"
Uses: report(investigation=..., format="slack")

# Manual findings
Ask: "Write up: signups down 23%, mobile Safari affected"
Uses: report(findings=["Signups down 23%", "Mobile Safari iOS 17 affected"])

# Include methodology
Ask: "Report with methodology section"
Uses: report(investigation=..., include_methodology=True)
```

**Output:**
```json
{
  "title": "Analytics Brief: Signup Conversion Issue",
  "generated_at": "2025-01-24T10:30:00Z",
  "summary": "A deployment on January 14th broke email validation for Mobile Safari users on iOS 17, causing a 23% drop in overall signups.",
  "key_findings": [
    "Signup conversion dropped 23% starting January 15",
    "Root cause: Email validation regex incompatible with iOS 17 Safari",
    "78% of impact concentrated in Mobile Safari segment"
  ],
  "recommendations": [
    {
      "action": "Verify iOS 17 Safari compatibility for all form validations",
      "priority": "immediate",
      "impact": "Recover lost signups",
      "effort": "low"
    }
  ],
  "markdown": "# Analytics Brief: Signup Conversion Issue\n\n## Summary\n..."
}
```

## Slash Commands

The tools are also available as Claude Code slash commands:

| Command | Tool |
|---------|------|
| `/mp-context` | context |
| `/mp-health` | health |
| `/mp-scan` | scan |
| `/mp-investigate` | investigate |
| `/mp-report` | report |

Example usage:
```
/mp-health --focus acquisition --from 2025-01-01
/mp-scan --sensitivity high
/mp-investigate --anomaly-id signup_drop_2025-01-15_a3f2b1c9
```

## Error Handling

When errors occur:

```json
{
  "error": "RateLimitError",
  "message": "Rate limit exceeded for query API",
  "guidance": "Wait 60 seconds and retry. Consider reducing scan scope."
}
```

## Graceful Degradation

When LLM sampling is unavailable, intelligent tools return raw data:

```json
{
  "status": "sampling_unavailable",
  "raw_data": {"...": "..."},
  "analysis_hints": [
    "Compare period-over-period changes",
    "Look for segment-specific patterns",
    "Check for temporal clustering"
  ]
}
```
