---
description: Generate retention analysis and retention curves from Mixpanel data
allowed-tools: Bash(mp query retention:*), Bash(mp inspect:*)
argument-hint: [born-event] [return-event]
---

# Mixpanel Retention Analysis

Guide the user through building retention analyses and retention curves to understand user behavior over time.

## Pre-flight Check

Verify credentials are configured:

```bash
!$(mp auth test 2>&1 || echo "No credentials configured")
```

If not configured, suggest running `/mp-auth` first.

## Retention Analysis Types

Present three analysis types:

1. **Retention Analysis** - How many users return after initial action (Live API)
2. **Cohort Behavior** - Compare behavior across user cohorts (Local SQL)
3. **Time-to-Event** - How long until users perform key actions (Local SQL)

Ask which type the user wants to perform.

---

## Type 1: Retention Analysis (Live API)

Classic retention: What % of users return to perform an action?

### 1. Define Cohort Entry Event

**Born Event**: Event that defines cohort membership
- Use `$1` if provided, otherwise ask

**Examples**:
- "Sign Up" - New user cohorts
- "First Purchase" - Buyer cohorts
- "Feature Activation" - Feature adoption cohorts

### 2. Define Return Event

**Return Event**: Event indicating user returned
- Use `$2` if provided, otherwise ask

**Examples**:
- "Login" - General activity
- "Purchase" - Repeat purchases
- "Feature Use" - Continued feature use

### 3. Configure Analysis Parameters

**Date Range**:
- From date (YYYY-MM-DD)
- To date (YYYY-MM-DD)
- This defines when cohorts are created (born event window)

**Time Unit**:
- `day` - Daily cohorts (good for recent data)
- `week` - Weekly cohorts (recommended for most analyses)
- `month` - Monthly cohorts (good for long-term trends)

**Retention Intervals**:
- Number of intervals to track (default: 11)
- Example: 11 weeks means track retention for 11 weeks after cohort birth

**Filters** (optional):
- `--born-where`: Filter cohort entry (e.g., only organic signups)
- `--return-where`: Filter return events (e.g., only purchases >$50)

### 4. Execute Retention Query

**Basic retention**:
```bash
mp query retention \
  --born "<born-event>" \
  --return "<return-event>" \
  --from <from-date> \
  --to <to-date> \
  --unit <day|week|month> \
  --format table
```

**With filters**:
```bash
mp query retention \
  --born "Sign Up" \
  --return "Purchase" \
  --from 2024-01-01 \
  --to 2024-01-31 \
  --unit week \
  --interval-count 12 \
  --born-where 'properties["source"] == "organic"' \
  --return-where 'properties["amount"] > 50' \
  --format table
```

### 5. Interpret Retention Results

**Key metrics to highlight**:

**Day 0 Retention**: % who return on the same day/week/month
> 📊 Day 0: X% - This is your immediate activation rate

**Day 1/Week 1 Retention**: First return after initial period
> 📊 Week 1: X% - Critical metric for product stickiness

**Long-term Retention**: Retention at final interval
> 📊 Week 11: X% - Shows long-term value

**Retention Curve Shape**:
- **Steep decline**: Poor onboarding or value prop
- **Gradual decline**: Natural attrition
- **Flattening**: Found product-market fit
- **Uptick**: Reactivation campaigns working

### 6. Visualize Retention Curve

Offer to create visualization:

```python
import pandas as pd
import matplotlib.pyplot as plt

# Assuming retention data from query
intervals = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
retention_rates = [100, 45, 38, 35, 32, 30, 28, 27, 26, 25, 24, 24]

fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(intervals, retention_rates, marker='o', linewidth=2, markersize=8)
ax.set_xlabel('Weeks Since Cohort Birth')
ax.set_ylabel('Retention Rate (%)')
ax.set_title('User Retention Curve')
ax.grid(True, alpha=0.3)
ax.axhline(y=retention_rates[-1], color='r', linestyle='--', alpha=0.5, label=f'Stabilized at {retention_rates[-1]}%')

plt.legend()
plt.tight_layout()
plt.savefig('retention_curve.png')
print("Retention curve saved to retention_curve.png")
```

---

## Type 2: Segmented Retention Analysis

Compare retention across different user segments.

### 1. Segment by Property

Use the `--on` parameter to break down retention by a property:

```bash
mp query retention \
  --born "Sign Up" \
  --return "Login" \
  --from 2024-01-01 \
  --to 2024-01-31 \
  --unit week \
  --on source
```

### 2. Compare Segments

Run multiple retention queries with different filters:

```bash
# Organic users retention
mp query retention \
  --born "Sign Up" --return "Login" \
  --from 2024-01-01 --to 2024-01-31 \
  --born-where 'properties["source"] == "organic"'

# Paid users retention
mp query retention \
  --born "Sign Up" --return "Login" \
  --from 2024-01-01 --to 2024-01-31 \
  --born-where 'properties["source"] == "paid"'
```

### 3. Visualize with Python

```python
import mixpanel_data as mp
import matplotlib.pyplot as plt

ws = mp.Workspace()

# Get retention data
result = ws.retention(
    born_event="Sign Up",
    return_event="Login",
    from_date="2024-01-01",
    to_date="2024-01-31",
    unit="week",
    interval_count=12,
)

df = result.df
pivot = df.pivot(index='cohort', columns='interval', values='rate')

# Create heatmap
import seaborn as sns
fig, ax = plt.subplots(figsize=(15, 8))
sns.heatmap(pivot, annot=True, fmt='.1f', cmap='RdYlGn', ax=ax)
ax.set_title('Cohort Retention Heatmap')
plt.savefig('cohort_heatmap.png')
```

---

## Type 3: Time-to-Event Analysis (via JQL)

Analyze how long it takes users to reach milestones using JQL.

### 1. Define Events

**Starting Event**: Where the clock starts (e.g., "Sign Up")
**Target Event**: What we're measuring time to (e.g., "First Purchase")

### 2. Build Time-to-Event JQL Query

```bash
mp query jql --script "
function main() {
  return Events({
    from_date: '2024-01-01',
    to_date: '2024-03-31',
    event_selectors: [
      {event: 'Sign Up'},
      {event: 'Purchase'}
    ]
  })
  .groupByUser(function(state, events) {
    state = state || {signup: null, purchase: null};
    events.forEach(function(e) {
      if (e.name === 'Sign Up' && !state.signup) state.signup = e.time;
      if (e.name === 'Purchase' && !state.purchase) state.purchase = e.time;
    });
    return state;
  })
  .filter(function(user) {
    return user.value.signup && user.value.purchase;
  })
  .map(function(user) {
    var days = (user.value.purchase - user.value.signup) / (1000 * 60 * 60 * 24);
    var bucket = days < 1 ? 'Same day' :
                 days <= 7 ? '2-7 days' :
                 days <= 30 ? '1-4 weeks' : '1+ months';
    return {bucket: bucket, count: 1};
  })
  .groupBy(['bucket'], mixpanel.reducer.count());
}
"
```

---

## Cohort Insights and Recommendations

### Strong Retention Indicators

> ✅ **Healthy retention** detected:
> - Week 1 retention > 40%
> - Curve flattens after week 4
> - Long-term retention > 20%
>
> **This indicates**: Strong product-market fit

### Weak Retention Indicators

> ⚠️ **Retention concerns** detected:
> - Steep drop-off in first week
> - Week 1 retention < 25%
> - Continuous decline without flattening
>
> **Recommendations**:
> - Improve onboarding experience
> - Add early activation hooks
> - Survey churned users
> - Implement retention campaigns

### Cohort Comparison Insights

> 📊 **Cohort performance varies**:
> - [Best cohort]: X% higher retention than average
> - [Worst cohort]: Y% lower retention
>
> **Investigate**:
> - What was different about successful cohorts?
> - Product changes during that period?
> - Marketing campaign differences?
> - External factors (seasonality, competition)?

---

## Next Steps

After cohort analysis, suggest:

1. **Segment retention by property**:
   ```bash
   mp query retention --born "Sign Up" --return "Login" \
     --from 2024-01-01 --to 2024-01-31 --on source
   ```

3. **Export for stakeholders**:
   ```bash
   mp query retention [...] --format csv > retention_report.csv
   ```

4. **Create dashboard report**:
   ```bash
   /mp-report cohort
   # Generate comprehensive cohort report
   ```

---

## Troubleshooting

**"No retention data"**:
- Verify born event exists: `mp inspect events`
- Check date range includes cohort births
- Ensure return event is tracked

**"All retention is 0%"**:
- Return event might not be occurring
- Check event names are exact matches
- Verify time window is appropriate

**"Cohort sizes too small"**:
- Expand date range for cohort births
- Use weekly/monthly instead of daily cohorts
- Check if filtering is too restrictive
