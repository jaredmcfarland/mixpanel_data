---
description: Gather project landscape and understand available Mixpanel data
allowed-tools: mcp__mp_mcp__context
argument-hint: [--schemas]
---

# Mixpanel Project Context

Understand what data is available in your Mixpanel project.

## Overview

The context tool aggregates:
- **Project info**: ID and data residency region
- **Events summary**: Total count and top events by volume
- **Properties summary**: Available event and user properties
- **Funnels**: Saved funnel configurations
- **Cohorts**: Defined user segments
- **Bookmarks**: Saved reports and analyses

## Usage

**Basic context** (recommended first step):
```
"Give me context on my Mixpanel project"
```

**With Lexicon schemas** (detailed property definitions):
```
"Get project context including schemas"
```

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `include_schemas` | Include Lexicon schema definitions | false |

## Understanding Results

**Events Summary**:
- `total`: Total number of tracked events
- `top_events`: Top 10 events by volume
- `categories`: AARRR categories if available

**Properties Summary**:
- `event_properties`: Number of event properties
- `user_properties`: Number of user/profile properties
- `common`: Properties that appear across multiple events

**Funnels**:
List of saved funnels with:
- `id`: Funnel identifier
- `name`: Funnel name
- `steps`: Number of steps

**Cohorts**:
List of defined cohorts with:
- `id`: Cohort identifier
- `name`: Cohort name
- `count`: Approximate user count

**Bookmarks**:
Summary of saved reports:
- `total`: Number of saved reports
- `by_type`: Breakdown by report type

## When to Use

**Starting a new analysis**:
Get context first to understand what data is available.

**Before building queries**:
Know which events and properties exist.

**Exploring unfamiliar project**:
Quickly understand the data structure.

## Next Steps

After getting context:

1. **Health check**: `/mp-health` with identified acquisition event
2. **Scan for issues**: `/mp-scan` on top events
3. **Query data**: `/mp-query` or `/mp-inspect` for details
4. **Analyze funnels**: `/mp-funnel` with listed funnel IDs

## Example Workflow

```
"Give me context on my project, then check health using the main signup event"
```

This will:
1. Gather project context
2. Identify the acquisition event from top events
3. Run health dashboard with that event
