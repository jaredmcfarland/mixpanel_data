---
description: Interactive query builder for JQL and live queries on Mixpanel data
allowed-tools: Bash(mp query:*), Bash(mp inspect:*)
argument-hint: [jql|segmentation|funnel|retention]
---

# Mixpanel Query Builder

Guide the user through building and executing queries on their Mixpanel data.

## Query Type Selection

Determine query type from `$1` or ask the user:

1. **jql** - Execute JavaScript Query Language for complex transformations
2. **segmentation** - Time-series event analysis with breakdowns
3. **funnel** - Conversion analysis through saved funnel steps
4. **retention** - Cohort retention analysis

---

## JQL Queries (JavaScript Query Language)

### 1. Explain JQL Use Case

JQL is for:
- Complex event transformations
- User-level aggregations
- Custom reducers and bucketing
- Advanced funnel logic

### 2. Build JQL Script

Help construct based on analysis needs:

**Basic event count**:
```javascript
function main() {
  return Events({
    from_date: '2024-01-01',
    to_date: '2024-01-31'
  }).reduce(mixpanel.reducer.count());
}
```

**Group by property**:
```javascript
function main() {
  return Events({
    from_date: '2024-01-01',
    to_date: '2024-01-31',
    event_selectors: [{event: 'Purchase'}]
  })
  .groupBy(['properties.country'], [
    mixpanel.reducer.count(),
    mixpanel.reducer.sum('properties.amount')
  ])
  .sortDesc('value');
}
```

**User-level analysis**:
```javascript
function main() {
  return Events({
    from_date: '2024-01-01',
    to_date: '2024-01-31'
  })
  .groupByUser(mixpanel.reducer.count())
  .filter(function(item) {
    return item.value > 10; // Active users with >10 events
  });
}
```

### 3. Save and Execute

Save the script to a file (e.g., `analysis.js`):

```bash
mp query jql analysis.js --format table
```

With parameters:
```bash
mp query jql analysis.js \
  --param from_date=2024-01-01 \
  --param to_date=2024-01-31 \
  --format table
```

---

## Segmentation Queries (Live API)

Time-series event analysis with optional property breakdown.

### Required Parameters

- **Event**: Event name to analyze
- **From date**: Start date (YYYY-MM-DD)
- **To date**: End date (YYYY-MM-DD)

### Optional Parameters

- **Segment by** (`--on`): Property to break down by (e.g., `country`, `plan`)
- **Unit** (`--unit`): Time granularity (`day`, `week`, `month`)
- **Filter** (`--where`): Filter expression

### Examples

**Basic event trend**:
```bash
mp query segmentation -e "Purchase" \
  --from 2024-01-01 \
  --to 2024-01-31 \
  --format table
```

**Segmented by property**:
```bash
mp query segmentation -e "Purchase" \
  --from 2024-01-01 \
  --to 2024-01-31 \
  --on country \
  --format table
```

**Filter with --jq**:
```bash
# Get just the total count
mp query segmentation -e "Purchase" \
  --from 2024-01-01 --to 2024-01-31 \
  --format json --jq '.total'

# Get top days by volume
mp query segmentation -e "Purchase" \
  --from 2024-01-01 --to 2024-01-31 \
  --format json --jq '.series | to_entries | sort_by(.value) | reverse | .[:5]'
```

**With filter**:
```bash
mp query segmentation -e "Purchase" \
  --from 2024-01-01 \
  --to 2024-01-31 \
  --on plan \
  --where 'properties["amount"] > 100' \
  --format table
```

---

## Funnel Queries (Live API)

Analyze conversion through saved funnel steps.

### 1. List Available Funnels

```bash
!$(mp inspect funnels --format table)
```

### 2. Select Funnel

Ask user to choose funnel by ID from the list.

### 3. Execute Funnel Analysis

```bash
mp query funnel <funnel-id> \
  --from 2024-01-01 \
  --to 2024-01-31 \
  --format table
```

**Optional**:
- `--unit day|week|month` - Time granularity
- `--on property` - Segment by property

---

## Retention Queries (Live API)

Cohort retention analysis.

### Required Parameters

- **Born event**: Event defining cohort entry (e.g., "Sign Up")
- **Return event**: Event defining return (e.g., "Login")
- **From/To dates**: Analysis period

### Example

```bash
mp query retention \
  --born "Sign Up" \
  --return "Login" \
  --from 2024-01-01 \
  --to 2024-01-31 \
  --unit week \
  --format table
```

**With filters**:
```bash
mp query retention \
  --born "Sign Up" \
  --return "Purchase" \
  --from 2024-01-01 \
  --to 2024-01-31 \
  --born-where 'properties["source"] == "organic"' \
  --return-where 'properties["amount"] > 50' \
  --format table
```

---

## Output and Next Steps

After query execution:

1. **Review results** in chosen format
2. **Refine query** if needed based on results
3. **Export data** using `--format csv` for spreadsheets
4. **Visualize** using Python + pandas (refer to skill patterns.md)
5. **Save query** to project for reuse

## Query Optimization Tips

**For JQL**:
- Filter with `event_selectors` rather than `.filter()` when possible
- Limit date ranges for faster results
- Use `groupByUser` for per-user analysis
- Leverage built-in reducers for common aggregations

**For Live Queries**:
- Smaller date ranges = faster results
- Use `--jq` to filter results client-side
- Use segmentation for simple time-series analysis

## Troubleshooting

**"Event not found"**: Check `mp inspect events` for available events
**"Invalid query"**: Check JQL syntax in skill reference files
**"Rate limit"**: Wait before retrying live queries
**"Authentication error"**: Run `/mp-auth` to reconfigure credentials
