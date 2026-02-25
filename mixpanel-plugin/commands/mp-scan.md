---
description: Scan for anomalies in your Mixpanel data using statistical detection
allowed-tools: mcp__mp_mcp__scan, mcp__mp_mcp__context
argument-hint: [events...]
---

# Mixpanel Anomaly Scanner

Detect drops, spikes, and unusual patterns in your event data.

## Overview

The scan tool uses statistical methods to identify:
- **Drops**: Significant decreases compared to rolling average
- **Spikes**: Significant increases compared to rolling average
- **Trend changes**: Shifts in baseline patterns

Each detected anomaly receives:
- A unique ID for investigation
- Severity rating (critical, high, medium, low)
- Confidence score

## Usage

**Default scan** (top 10 events, last 14 days):
```
"Scan for anomalies in my data"
```

**Specific events**:
```
"Scan for issues in signup, login, and purchase"
```

**Custom date range**:
```
"Scan the last 7 days for anomalies"
```

**High sensitivity** (more false positives, catches subtle issues):
```
"Scan with high sensitivity"
```

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `events` | List of events to scan | Top 10 events |
| `from_date` | Start date (YYYY-MM-DD) | 14 days ago |
| `to_date` | End date (YYYY-MM-DD) | Today |
| `sensitivity` | Detection threshold: high/medium/low | medium |

## Understanding Results

**Severity levels**:
- 🔴 **Critical**: 40%+ change from baseline
- 🟠 **High**: 25-40% change
- 🟡 **Medium**: 15-25% change
- 🟢 **Low**: <15% change

**Anomaly ID format**:
```
{event}_{type}_{date}_{hash}
```
Example: `signup_drop_2025-01-15_a3f2b1c9`

## Next Steps

After detecting anomalies:

1. **Investigate**: `/mp-analytics investigate` with the anomaly ID
2. **Report**: Generate a report on findings
3. **Monitor**: Set up alerts for recurring issues

## Examples

**Quick daily check**:
```
"Any anomalies in the last 7 days?"
```

**Focused scan**:
```
"Check if signups or activations have any issues"
```

**Full analysis**:
```
"Scan for anomalies and investigate the most severe one"
```
