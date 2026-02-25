---
description: Root cause analysis on detected anomalies with dimensional decomposition
allowed-tools: mcp__mp_mcp__investigate, mcp__mp_mcp__scan, mcp__mp_mcp__report
argument-hint: <anomaly_id or event>
---

# Mixpanel Anomaly Investigation

Perform root cause analysis to understand why an anomaly occurred.

## Overview

The investigate tool performs:
- **Dimensional decomposition**: Which segments drove the change?
- **Temporal analysis**: When exactly did the change happen?
- **Correlation detection**: What other events changed at the same time?
- **Hypothesis generation**: What likely caused this?

## Usage

**From scan results** (preferred):
```
"Investigate the signup drop"
```
Uses the anomaly_id from previous scan results.

**Manual specification**:
```
"Investigate why login spiked on 2025-01-15"
```

**With custom dimensions**:
```
"Investigate the signup drop, breaking down by country and browser"
```

## Parameters

| Parameter | Description | Required |
|-----------|-------------|----------|
| `anomaly_id` | ID from scan results | Preferred |
| `event` | Event name | If no anomaly_id |
| `date` | Date of anomaly (YYYY-MM-DD) | If no anomaly_id |
| `anomaly_type` | drop/spike/trend_change | If no anomaly_id |
| `dimensions` | Properties to analyze | Optional (defaults to common) |

**Default dimensions analyzed**:
- `$browser`
- `$os`
- `$city`
- `platform`

## Understanding Results

**Contributing Factors**:
Each factor shows:
- Which segment changed (e.g., "Safari iOS users")
- Contribution percentage (how much of the change this explains)
- Evidence (what the data shows)
- Confidence level (high/medium/low)

**Timeline**:
Shows daily values with baseline comparison:
- `ANOMALY:` marks the detected date
- Significance levels indicate unusual values

**Correlations**:
Other events that changed at the same time:
- Positive correlation: changed in same direction
- Negative correlation: changed in opposite direction

**Hypotheses**:
Generated explanations based on the data:
- Top contributing factors
- Correlated events
- Suggested areas to explore

## Example Investigation Flow

1. **Run scan** (if not already done):
   ```
   "Scan for anomalies in signup"
   ```

2. **Review results**: Note the anomaly_id from top result

3. **Investigate**:
   ```
   "Investigate signup_drop_2025-01-15_a3f2b1c9"
   ```

4. **Review findings**:
   - Check top contributing factors
   - Look for patterns in timeline
   - Consider correlated events

5. **Generate report**:
   ```
   "Create a report on this investigation"
   ```

## Tips for Investigation

**Choose meaningful dimensions**:
- Platform-related: `$browser`, `$os`, `platform`
- Geographic: `$city`, `$country`, `region`
- User segments: `plan`, `user_type`, `source`

**Consider the timeline**:
- Did the change happen suddenly or gradually?
- Was it a one-day spike or sustained change?
- Are there patterns (weekends, holidays)?

**Look for correlations**:
- Did other key events change?
- Is there a cascade effect (signup → activation → purchase)?

## Next Steps

After investigation:

1. **Report**: `/mp-analytics report` to share findings
2. **Query**: `/mp-query` for deeper analysis
3. **Monitor**: Set up alerts for the affected segment
