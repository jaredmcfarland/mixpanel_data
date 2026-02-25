---
description: Generate a product health dashboard with KPI comparison
allowed-tools: mcp__mp_mcp__health, mcp__mp_mcp__context
argument-hint: [acquisition_event]
---

# Mixpanel Product Health Dashboard

Generate a KPI dashboard comparing current vs previous period metrics.

## Overview

The health tool provides:
- **Acquisition metrics**: Signup/registration counts with trends
- **Activation metrics**: First key action completion
- **Retention metrics**: D7 retention rates
- **Period comparison**: Current vs previous period changes
- **Highlights & concerns**: Automatic insight generation

## Usage

**Default health check** (last 30 days):
```
"How is my product doing?"
```

**Custom acquisition event**:
```
"Show health dashboard using 'registration' as the acquisition event"
```

**Custom date range**:
```
"Show KPIs for the last week"
```

**Include activation**:
```
"Check health with signup as acquisition and first_purchase as activation"
```

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `acquisition_event` | Event for acquisition metric | "signup" |
| `activation_event` | Event for activation metric | Same as acquisition |
| `from_date` | Start of current period (YYYY-MM-DD) | 30 days ago |
| `to_date` | End of current period (YYYY-MM-DD) | Today |
| `include_retention` | Compute D7 retention | true |

## Understanding Results

**Metrics returned**:
- Current value
- Previous period value
- Change percentage
- Trend direction (up/down/flat)

**Trend indicators**:
- ↑ **Up**: >5% increase
- ↓ **Down**: >5% decrease
- → **Flat**: Within ±5%

**Highlights**: Positive observations (>10% improvement)
**Concerns**: Negative observations (>10% decline)

## Daily Series

The response includes daily time series data for:
- Visual trend analysis
- Identifying specific dates with issues
- Comparing patterns over time

## Next Steps

After reviewing health:

1. **Investigate concerns**: If metrics are down, use `/mp-scan` to find anomalies
2. **Dig deeper**: Use `/mp-query` for detailed segmentation
3. **Report**: Generate a summary with `/mp-analytics report`

## Examples

**Morning standup check**:
```
"Quick health check for the product"
```

**Weekly review**:
```
"Show me the health dashboard for last week compared to the week before"
```

**Custom metrics**:
```
"Health check using trial_start as acquisition and subscription_created as activation"
```
