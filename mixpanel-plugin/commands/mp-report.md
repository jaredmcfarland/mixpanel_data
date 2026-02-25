---
description: Generate actionable reports from analytics investigations
allowed-tools: mcp__mp_mcp__report, mcp__mp_mcp__investigate
argument-hint: <event> [--slack]
---

# Mixpanel Report Generator

Synthesize analytics findings into actionable reports.

## Overview

The report tool creates structured reports from investigation results:
- **Executive summary**: High-level overview for stakeholders
- **Key findings**: Data-driven insights with evidence
- **Recommendations**: Prioritized actions based on findings
- **Markdown output**: Full report for documentation
- **Slack blocks**: Optional Slack-formatted output

## Usage

**From investigation results** (preferred):
```
"Generate a report on the signup drop investigation"
```

**Manual specification**:
```
"Create a report on the login spike from Jan 10-15"
```

**With Slack formatting**:
```
"Generate a Slack report on the checkout drop"
```

## Parameters

| Parameter | Description | Required |
|-----------|-------------|----------|
| `event` | Event that was analyzed | Yes |
| `anomaly_type` | Type: drop/spike/trend_change | Yes |
| `from_date` | Start of analysis period (YYYY-MM-DD) | Yes |
| `to_date` | End of analysis period (YYYY-MM-DD) | Yes |
| `root_cause` | Identified root cause (from investigation) | Optional |
| `factors` | Contributing factors list | Optional |
| `include_slack_blocks` | Generate Slack-formatted output | Optional (default: false) |

## Understanding Results

**Title**: Brief description of the anomaly and period

**Executive Summary**:
- What happened
- When it happened
- Impact magnitude
- Root cause (if identified)

**Key Findings**:
Each finding includes:
- Observation from the data
- Supporting evidence
- Confidence level

**Recommendations**:
Prioritized actions with:
- `priority`: high/medium/low
- `action`: Specific step to take
- `rationale`: Why this matters

**Markdown Report**:
Full formatted report suitable for:
- Documentation
- Email sharing
- Wiki pages

**Slack Blocks** (if requested):
Structured message blocks for:
- Posting to Slack channels
- Incident response threads
- Team notifications

## Example Workflow

1. **Investigate first**:
   ```
   "Investigate the signup drop"
   ```

2. **Review findings**: Note the root cause and contributing factors

3. **Generate report**:
   ```
   "Create a report on these findings"
   ```

4. **Share with team**:
   ```
   "Generate a Slack message I can post to #product"
   ```

## Report Sections

The markdown report includes:

### 1. Overview
- Event and anomaly type
- Analysis period
- High-level summary

### 2. Metrics
- Current period values
- Previous period comparison
- Trend analysis

### 3. Contributing Factors
- Ranked by contribution percentage
- Evidence for each factor
- Confidence levels

### 4. Timeline
- Day-by-day breakdown
- Significant events marked
- Pattern identification

### 5. Recommendations
- Immediate actions
- Further investigation areas
- Monitoring suggestions

## Tips

**Include context**:
Pass the root cause and factors from investigation for richer reports.

**Use Slack for incidents**:
The Slack format is designed for quick team communication during incidents.

**Customize for audience**:
- Executive summary for leadership
- Full report for product/engineering
- Slack blocks for real-time updates

## Next Steps

After generating a report:

1. **Share findings**: Post to relevant channels
2. **Create tasks**: Turn recommendations into action items
3. **Set up monitoring**: Track the affected metrics going forward
4. **Schedule review**: Follow up on implemented fixes
