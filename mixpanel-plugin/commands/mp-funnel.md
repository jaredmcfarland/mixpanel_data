---
description: Interactive wizard to build and analyze conversion funnels from Mixpanel data
allowed-tools: Bash(mp query funnel:*), Bash(mp inspect:*)
argument-hint: [funnel-id]
---

# Mixpanel Funnel Analysis

Guide the user through building and analyzing conversion funnels using saved Mixpanel funnels or custom event sequences.

## Pre-flight Check

Verify credentials are configured:

```bash
!$(mp auth test 2>&1 || echo "No credentials configured")
```

If credentials aren't configured, suggest running `/mp-auth` first.

## Funnel Analysis Options

Present two approaches:

1. **Saved Funnel** - Use existing funnel from Mixpanel UI (faster)
2. **Custom Funnel** - Build funnel from local event data (more flexible)

Ask which approach the user prefers.

---

## Option 1: Saved Funnel Analysis (Live API)

### 1. List Available Funnels

```bash
!$(mp inspect funnels --format table)
```

Show the user:
- Funnel ID
- Funnel name
- Number of steps

**Tip**: Use `/mp-inspect` to discover available events and cohorts for analysis context.

### 2. Select Funnel

If `$1` is provided, use that as funnel ID. Otherwise, ask user to choose from the list.

### 3. Configure Analysis Parameters

**Date Range** (required):
- From date (YYYY-MM-DD)
- To date (YYYY-MM-DD)
- Validate range is reasonable (suggest ≤ 90 days for performance)

**Time Unit** (optional):
- `day` (default)
- `week`
- `month`

**Segmentation** (optional):
- Property to segment by (e.g., `country`, `plan`, `source`)
- Shows conversion rates broken down by this property

### 4. Execute Funnel Query

**Basic funnel**:
```bash
mp query funnel <funnel-id> \
  --from <from-date> \
  --to <to-date> \
  --format table
```

**With segmentation**:
```bash
mp query funnel <funnel-id> \
  --from <from-date> \
  --to <to-date> \
  --unit <day|week|month> \
  --on <property> \
  --format table
```

### 5. Interpret Results

Show the user:
- **Overall conversion rate**: Final step / First step
- **Step-by-step drop-off**: Where users are leaving
- **Conversion rates by segment** (if segmented)

**Key insights to highlight**:
- Which step has the biggest drop-off?
- What's the overall conversion rate?
- How do segments compare?

---

## Option 2: Custom Funnel via JQL

Use JQL for custom funnel analysis not covered by saved funnels.

### 1. Define Funnel Steps

Ask the user for the event sequence (3-5 events recommended):
- Step 1: Event name (e.g., "View Product")
- Step 2: Event name (e.g., "Add to Cart")
- Step 3: Event name (e.g., "Checkout")
- Step 4: Event name (e.g., "Purchase")

### 2. Build JQL Funnel Query

```bash
mp query jql --script "
function main() {
  var funnel_events = ['View Product', 'Add to Cart', 'Checkout', 'Purchase'];

  return Events({
    from_date: '<from-date>',
    to_date: '<to-date>',
    event_selectors: funnel_events.map(function(e) { return {event: e}; })
  })
  .groupByUser(function(state, events) {
    state = state || {};
    events.forEach(function(event) {
      state[event.name] = (state[event.name] || 0) + 1;
    });
    state.funnel_stage = 0;
    for (var i = 0; i < funnel_events.length; i++) {
      if (state[funnel_events[i]] > 0) {
        state.funnel_stage = i + 1;
      } else {
        break;
      }
    }
    return state;
  })
  .groupBy(['value.funnel_stage'], mixpanel.reducer.count())
  .map(function(item) {
    return {
      stage: item.key[0],
      stage_name: funnel_events[item.key[0] - 1] || 'Not in funnel',
      users: item.value
    };
  });
}
"
```

### 3. Visualize Results

Offer to create a Python visualization:

```python
import mixpanel_data as mp
import matplotlib.pyplot as plt

ws = mp.Workspace()
result = ws.funnel(12345, from_date="2024-01-01", to_date="2024-01-31")

steps = [s.event for s in result.steps]
users = [s.count for s in result.steps]

fig, ax = plt.subplots(figsize=(10, 6))
ax.barh(steps, users, color=['#4CAF50', '#8BC34A', '#CDDC39', '#FFEB3B'])
ax.set_xlabel('Number of Users')
ax.set_title(f'Funnel: {result.overall_conversion_rate:.1%} conversion')
plt.tight_layout()
plt.savefig('funnel.png')
```

---

## Advanced Analysis: Segmented Funnels

Segment funnel results by property using the `--on` parameter:

```bash
mp query funnel <funnel-id> \
  --from 2024-01-01 --to 2024-01-31 \
  --on country --format table
```

---

## Common Funnel Patterns

**E-commerce Funnel**:
1. Product View → Add to Cart → Checkout → Purchase

**SaaS Signup Funnel**:
1. Landing Page → Sign Up → Onboarding → First Action

**Content Engagement Funnel**:
1. Page View → Scroll Depth → Click CTA → Convert

**Mobile App Funnel**:
1. App Open → Feature Discovery → Feature Use → Retention

---

## Insights and Recommendations

After showing results, provide actionable insights:

### High Drop-off Detection

If any step shows >50% drop-off:
> ⚠️ **High drop-off detected** at Step X → Step Y (Z% drop)
>
> **Recommendations**:
> - Investigate UX issues at Step X
> - Add tracking for abandonment reasons
> - A/B test simplified flow
> - Check for technical errors

### Segment Performance Comparison

If segmented:
> 📊 **Segment insights**:
> - Best performing: [Segment A] (X% conversion)
> - Worst performing: [Segment B] (Y% conversion)
> - Delta: Z percentage points
>
> **Recommendations**:
> - Study what makes [Segment A] successful
> - Optimize experience for [Segment B]
> - Consider separate funnels per segment

### Time-Based Trends

If using time units:
> 📈 **Trend analysis**:
> - Conversion improving/declining over time
> - Seasonal patterns detected
>
> **Recommendations**:
> - Investigate what changed during improvements
> - Prepare for seasonal variations

---

## Next Steps

After analysis, suggest:

1. **Deep dive on specific step**:
   ```bash
   /mp-query sql
   # Analyze users who dropped at specific step
   ```

2. **Retention analysis**:
   ```bash
   /mp-retention
   # Analyze retention for users who completed funnel
   ```

3. **Export for presentation**:
   ```bash
   mp query funnel <id> --from <date> --to <date> --format csv > funnel_results.csv
   ```

4. **Create custom report**:
   ```bash
   /mp-report funnel
   # Generate comprehensive funnel report
   ```

---

## Troubleshooting

**"Funnel not found"**:
- Check funnel ID with `mp inspect funnels`
- Verify access permissions in Mixpanel

**"No events found"**:
- Verify event names exactly match (case-sensitive)
- Check date range includes relevant data
- Run `mp inspect events` to see available events

**"Low sample size"**:
- Expand date range
- Check if events are being tracked correctly
- Verify filtering isn't too restrictive

**"Segmentation returns null"**:
- Property might not exist on all events
- Check property name with `mp inspect properties <event>`
- Use `defined(properties["prop"])` in filters
