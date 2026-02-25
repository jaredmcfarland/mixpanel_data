---
description: Run the Operational Analytics Loop - scan for anomalies and investigate issues
allowed-tools: mcp__mp_mcp__context, mcp__mp_mcp__health, mcp__mp_mcp__scan, mcp__mp_mcp__investigate, mcp__mp_mcp__report
argument-hint: [context|health|scan|investigate|report]
---

# Mixpanel Analytics Loop

Guide the user through the Operational Analytics Loop workflow for proactive monitoring and investigation.

## Workflow Overview

The Analytics Loop is a structured workflow for product health monitoring:

```
context → health → scan → investigate → report
```

1. **context** - Gather project landscape (events, properties, funnels, cohorts)
2. **health** - Generate KPI dashboard with period comparison
3. **scan** - Detect anomalies using statistical methods
4. **investigate** - Root cause analysis on detected anomalies
5. **report** - Synthesize findings into actionable reports

## Step Selection

Determine which step to run from `$1` or ask the user:

- **context** - "Give me context on my Mixpanel project"
- **health** - "How is my product doing?"
- **scan** - "Are there any anomalies in my data?"
- **investigate** - "Investigate the signup drop"
- **report** - "Generate a report from this investigation"

---

## Step 1: Context

Gather the project landscape to understand what data is available.

**Use the `context` MCP tool:**

This returns:
- Project info (ID, region)
- Events summary (total, top events)
- Properties summary (event/user properties)
- Funnels list
- Cohorts list
- Bookmarks summary

**Example prompt**: "Give me context on my Mixpanel project"

---

## Step 2: Health

Generate a KPI dashboard comparing current vs previous period.

**Use the `health` MCP tool with parameters:**

- `acquisition_event` - Event for acquisition metric (default: "signup")
- `activation_event` - Event for activation metric
- `from_date` / `to_date` - Analysis period (default: last 30 days)
- `include_retention` - Whether to compute D7 retention

**Example prompts**:
- "How is my product doing?"
- "Show me KPIs for the last week"

---

## Step 3: Scan

Detect anomalies in event data using statistical methods.

**Use the `scan` MCP tool with parameters:**

- `events` - List of events to scan (default: top 10)
- `from_date` / `to_date` - Scan period (default: last 14 days)
- `sensitivity` - Detection sensitivity: "high", "medium", "low"

**Returns:**
- Ranked list of anomalies with severity
- Each anomaly has a unique `id` for investigation

**Example prompts**:
- "Are there any anomalies in my data?"
- "Check for issues in signup and login"

---

## Step 4: Investigate

Perform root cause analysis on a detected anomaly.

**Use the `investigate` MCP tool with parameters:**

- `anomaly_id` - ID from scan results (preferred)
- OR `event` + `date` + `anomaly_type` - Manual specification
- `dimensions` - List of dimensions to analyze

**Returns:**
- Contributing factors ranked by impact
- Timeline of events
- Correlated events
- Hypotheses for the root cause

**Example prompts**:
- "Investigate the signup drop" (use anomaly_id from scan)
- "Why did logins spike yesterday?"

---

## Step 5: Report

Synthesize findings into an actionable report.

**Use the `report` MCP tool with parameters:**

- `event` - Event analyzed
- `anomaly_type` - Type of anomaly (drop/spike/trend_change)
- `from_date` / `to_date` - Analysis period
- `root_cause` - Optional identified root cause
- `factors` - Optional contributing factors from investigation
- `include_slack_blocks` - Generate Slack-formatted output

**Returns:**
- Title and executive summary
- Key findings
- Recommendations with priority
- Full markdown report
- Optional Slack blocks

**Example prompts**:
- "Generate a report on the signup drop"
- "Create a Slack message about this issue"

---

## Full Workflow Example

1. **Start**: "Run the analytics loop for my project"

2. **Context first**:
   - Use `context` tool to understand the project
   - Identify key events and funnels

3. **Check health**:
   - Use `health` tool with identified acquisition event
   - Review highlights and concerns

4. **Scan for issues**:
   - Use `scan` tool on key events
   - Review any detected anomalies

5. **Investigate top anomaly**:
   - Use `investigate` with the anomaly_id
   - Review contributing factors and hypotheses

6. **Generate report**:
   - Use `report` with investigation findings
   - Share markdown or Slack output

---

## Quick Commands

**Daily check**:
```
"Check my product health and scan for any issues"
```

**Investigate specific issue**:
```
"Investigate why signup dropped on 2025-01-15"
```

**Full analysis with report**:
```
"Run the full analytics loop and generate a report"
```
