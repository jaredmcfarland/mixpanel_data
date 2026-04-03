# Integration Patterns

Common patterns for integrating mixpanel_data with pandas, jq, and Unix pipelines.

## Table of Contents
- Streaming Data Format
- pandas Integration
- jq Processing
- Unix Pipelines
- Multi-Account Workflows
- Data Science Workflows

## Streaming Data Format

### Event Format (from stream_events)
```json
{
    "event": "Purchase",
    "time": 1704067200,
    "distinct_id": "user_123",
    "properties": {
        "country": "US",
        "amount": 49.99,
        "plan": "premium"
    }
}
```

### Profile Format (from stream_profiles)
```json
{
    "distinct_id": "user_123",
    "properties": {
        "name": "Alice",
        "plan": "premium",
        "country": "US"
    },
    "last_seen": "2024-01-31T12:00:00"
}
```

## pandas Integration

### DataFrame from Live Queries
All result types have lazy `.df` conversion:

```python
# Segmentation
result = ws.segmentation("Purchase", from_date="2024-01-01", to_date="2024-01-31", on="country")
df = result.df  # Lazy conversion, cached

# Funnel
result = ws.funnel(12345, from_date="2024-01-01", to_date="2024-01-31")
df = result.df

# Retention
result = ws.retention("Sign Up", "Purchase", from_date="2024-01-01", to_date="2024-01-31")
df = result.df
```

### Visualization
```python
import matplotlib.pyplot as plt

# Segmentation visualization
result = ws.segmentation("Purchase", from_date="2024-01-01", to_date="2024-01-31", on="country")
pivot = result.df.pivot(index='date', columns='segment', values='count')
pivot.plot(figsize=(12, 6))
plt.title('Purchases by Country')
```

### DataFrame from Streaming
```python
import pandas as pd
import mixpanel_data as mp

ws = mp.Workspace()

# Collect streamed events into a DataFrame
events = list(ws.stream_events(from_date="2024-01-01", to_date="2024-01-31"))
df = pd.DataFrame(events)
```

## jq Processing

### Built-in --jq Option

The CLI has built-in jq support via the `--jq` option, eliminating the need for external tools:

```bash
# Filter events inline
mp inspect events --format json --jq '.[:5]'
mp inspect events --format json --jq '.[] | select(contains("User"))'

# Filter query results
mp query segmentation -e Purchase --from 2024-01-01 --to 2024-01-31 \
  --format json --jq '.total'
```

### External jq with Streaming

For streaming data, pipe to external jq:

```bash
# Single field
mp stream events --from 2024-01-01 --to 2024-01-01 | jq '.event'

# Multiple fields
mp stream events --from 2024-01-01 --to 2024-01-01 | jq '{event, time: .time, user: .distinct_id}'

# Properties
mp stream events --from 2024-01-01 --to 2024-01-01 | jq '.properties.country'
mp stream events --from 2024-01-01 --to 2024-01-01 | jq '.properties | keys'  # List all property keys
```

### Filtering
```bash
# Filter by event
mp stream events --from 2024-01-01 --to 2024-01-01 | jq 'select(.event == "Purchase")'

# Filter by property
mp stream events --from 2024-01-01 --to 2024-01-01 | jq 'select(.properties.country == "US")'

# Numeric comparison
mp stream events --from 2024-01-01 --to 2024-01-01 | jq 'select(.properties.amount > 100)'

# Multiple conditions
mp stream events --from 2024-01-01 --to 2024-01-01 | jq 'select(.event == "Purchase" and .properties.amount > 100)'
```

### Aggregation
```bash
# Count by event
mp stream events --from 2024-01-01 --to 2024-01-01 | jq -s 'group_by(.event) | map({event: .[0].event, count: length})'

# Sum numeric property
mp stream events --from 2024-01-01 --to 2024-01-01 | jq -s '[.[].properties.amount] | add'

# Unique users
mp stream events --from 2024-01-01 --to 2024-01-01 | jq -s '[.[].distinct_id] | unique | length'
```

### Transformation
```bash
# Flatten for CSV
mp stream events --from 2024-01-01 --to 2024-01-01 | jq -r '[.event, .distinct_id, .time, .properties.country] | @csv'

# Create new structure
mp stream events --from 2024-01-01 --to 2024-01-01 | jq '{
    event: .event,
    user: .distinct_id,
    country: .properties.country,
    amount: .properties.amount
}'
```

## Unix Pipelines

### Stream to CSV
```bash
# Events to CSV
mp stream events --from 2024-01-01 --to 2024-01-01 \
  | jq -r '[.event, .distinct_id, .time] | @csv' \
  > events.csv

# With headers
echo "event,user,time" > events.csv
mp stream events --from 2024-01-01 --to 2024-01-01 | jq -r '[.event, .distinct_id, .time] | @csv' >> events.csv
```

### Count with Filtering
```bash
# Count US purchases
mp stream events --from 2024-01-01 --to 2024-01-01 \
  | jq 'select(.event == "Purchase" and .properties.country == "US")' \
  | wc -l

# Sum amounts
mp stream events --from 2024-01-01 --to 2024-01-01 \
  | jq 'select(.event == "Purchase") | .properties.amount' \
  | awk '{sum+=$1} END {print sum}'
```

### Parallel Processing
```bash
# Process in batches
mp stream events --from 2024-01-01 --to 2024-01-01 | parallel --pipe -N1000 'python process_batch.py'

# Multiple date ranges in parallel
seq 1 12 | parallel 'mp stream events --from 2024-{}-01 --to 2024-{}-28 > month_{}.jsonl'
```

### Combine with Other Tools
```bash
# Sort by timestamp
mp stream events --from 2024-01-01 --to 2024-01-01 | jq -c '.' | sort -t'"' -k8

# Sample random events
mp stream events --from 2024-01-01 --to 2024-01-01 | shuf -n 100

# First/last N events
mp stream events --from 2024-01-01 --to 2024-01-01 | head -100
mp stream events --from 2024-01-01 --to 2024-01-01 | tail -100
```

## Multi-Account Workflows

### Python: Multiple Workspaces
```python
import mixpanel_data as mp

# Compare production vs staging
ws_prod = mp.Workspace(account="production")
ws_staging = mp.Workspace(account="staging")

prod_events = ws_prod.events()
staging_events = ws_staging.events()

# Find events only in prod
prod_only = set(prod_events) - set(staging_events)
print(f"Production-only events: {prod_only}")

ws_prod.close()
ws_staging.close()
```

### CLI: Account Flag
```bash
# List events from different accounts
mp --account production inspect events
mp --account staging inspect events

# Stream from multiple accounts
mp --account production stream events --from 2024-01-01 --to 2024-01-31 > prod.jsonl
mp --account staging stream events --from 2024-01-01 --to 2024-01-31 > staging.jsonl
```

## Data Science Workflows

### Funnel Analysis
```python
import mixpanel_data as mp
import matplotlib.pyplot as plt

ws = mp.Workspace()

# Get funnel data
funnels = ws.funnels()
print(f"Available funnels: {[f.name for f in funnels]}")

# Analyze conversion
result = ws.funnel(funnels[0].funnel_id, from_date="2024-01-01", to_date="2024-01-31")

# Visualize steps
steps = [(s.event, s.count, s.conversion_rate) for s in result.steps]
for event, count, rate in steps:
    print(f"{event}: {count} ({rate:.1%})")

# Bar chart
events = [s.event for s in result.steps]
counts = [s.count for s in result.steps]
plt.bar(events, counts)
plt.xticks(rotation=45)
plt.title(f'Funnel: {result.overall_conversion_rate:.1%} conversion')
plt.savefig('funnel.png', bbox_inches='tight')
```

### Retention Curves
```python
import mixpanel_data as mp
import matplotlib.pyplot as plt

ws = mp.Workspace()

result = ws.retention(
    born_event="Sign Up",
    return_event="Login",
    from_date="2024-01-01",
    to_date="2024-01-31",
    unit="week",
    interval_count=8,
)

# Plot retention curve
df = result.df
avg_retention = df.groupby('interval')['rate'].mean()
avg_retention.plot(kind='line', marker='o')
plt.xlabel('Weeks since signup')
plt.ylabel('Retention Rate')
plt.title('User Retention Curve')
plt.savefig('retention.png')
```

### User Segmentation (via JQL)
```python
import mixpanel_data as mp

ws = mp.Workspace()

# Segment users by activity using JQL
result = ws.jql("""
function main() {
  return Events({
    from_date: '2024-01-01',
    to_date: '2024-01-31'
  })
  .groupByUser([
    mixpanel.reducer.count(),
    mixpanel.reducer.count_unique('name')
  ])
  .groupBy([function(user) {
    var count = user.value[0];
    if (count > 100) return 'Super';
    if (count > 20) return 'Power';
    if (count > 5) return 'Regular';
    return 'Casual';
  }], mixpanel.reducer.count());
}
""")

print(result.data)
```

### Cohort Analysis (via Retention API)
```python
import mixpanel_data as mp

ws = mp.Workspace()

# Use the retention API for cohort analysis
result = ws.retention(
    born_event="Sign Up",
    return_event="Login",
    from_date="2024-01-01",
    to_date="2024-03-31",
    unit="week",
    interval_count=12,
)

df = result.df
print(df)
```
