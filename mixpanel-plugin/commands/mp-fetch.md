---
description: Interactive wizard to stream Mixpanel events or profiles via the API
allowed-tools: Bash(mp stream:*), Bash(mp inspect:*)
argument-hint: [events|profiles] [YYYY-MM-DD] [YYYY-MM-DD]
---

# Stream Mixpanel Data

This command guides users through streaming events or profiles from the Mixpanel API.

## Fetch Type Selection

Ask the user what they want to stream:
- **Events**: Time-series event data (requires date range)
- **Profiles**: User profile data (no date range needed)

If date arguments are provided (`$1`, `$2`), assume events. Otherwise, ask.

---

# Stream Mixpanel Events

Guide the user through streaming events from the Mixpanel Export API.

## Pre-flight Check

First, verify credentials are configured:

```bash
!$(mp auth test 2>&1 || echo "No credentials configured")
```

If credentials aren't configured, suggest running `/mp-auth` first.

## Stream Parameters

### 1. Date Range

**From date**: `$1` if provided, otherwise ask in YYYY-MM-DD format
**To date**: `$2` if provided, otherwise ask in YYYY-MM-DD format

**Validation**:
- Both dates must be in YYYY-MM-DD format
- From date must be <= to date

### 2. Optional Filters (Advanced)

Ask if the user wants to apply filters:

**Event filter** (optional):
- Specific event names to stream
- Example: `--events "Purchase" "Sign Up" "Page View"`

**WHERE clause** (optional):
- Mixpanel filter expression
- Example: `--where 'properties["country"] == "US" and properties["amount"] > 100'`
- Refer to query-expressions.md in skill for complete syntax

**Limit** (optional):
- Maximum events to stream
- Useful for testing or sampling

## Execute Stream

### Python API

```python
import mixpanel_data as mp

ws = mp.Workspace()
for event in ws.stream_events(
    from_date="<from-date>",
    to_date="<to-date>",
):
    print(event)
```

### CLI (stdout streaming)

```bash
mp stream events --from <from-date> --to <to-date>
```

### With Filters

```bash
mp stream events --from <from-date> --to <to-date> \
  --events "Purchase" \
  --where 'properties["amount"] > 100'
```

### Pipe to jq for Processing

```bash
# Extract specific fields
mp stream events --from 2024-01-01 --to 2024-01-31 | jq '.event'

# Filter and transform
mp stream events --from 2024-01-01 --to 2024-01-31 | jq 'select(.event == "Purchase") | .properties.amount'

# Convert to CSV
mp stream events --from 2024-01-01 --to 2024-01-31 | jq -r '[.event, .distinct_id] | @csv' > events.csv
```

## Post-Stream Next Steps

After streaming:

1. **Analyze with live queries**:
   - Run `/mp-query segmentation` for time-series analysis
   - Run `/mp-query funnel` for conversion analysis
   - Run `/mp-query retention` for retention analysis

2. **Explore schema**:
   - Run `/mp-inspect events` to discover event names
   - Run `/mp-inspect properties` to explore event properties

## Error Handling

**AuthenticationError**: Credentials invalid
- Solution: Run `/mp-auth` to reconfigure

**RateLimitError**: API rate limited
- Solution: Wait and retry (shows retry_after seconds)

**EventNotFoundError**: Event doesn't exist
- Solution: Check available events with `mp inspect events`

---

# Stream Mixpanel Profiles

Guide the user through streaming user profiles from the Mixpanel Engage API.

## Pre-flight Check

First, verify credentials are configured:

```bash
!$(mp auth test 2>&1 || echo "No credentials configured")
```

If credentials aren't configured, suggest running `/mp-auth` first.

## Stream Parameters

### 1. Optional Filters (Advanced)

Ask if the user wants to apply filters:

**Cohort filter** (optional):
- Filter to members of a specific cohort
- Example: `--cohort 12345`

**WHERE clause** (optional):
- Profile property filter expression
- Example: `--where 'properties["plan"] == "premium"'`

**Output properties** (optional):
- Specific properties to include
- Example: `--output-properties email,name,plan`

**Distinct IDs** (optional):
- Stream specific users by ID
- Example: `--distinct-ids user_1 --distinct-ids user_2`

**Group profiles** (optional):
- Stream group profiles instead of users
- Example: `--group-id companies`

**Behavioral filters** (optional):
- Filter users by behavior
- Example: `--behaviors '[{"window":"30d","name":"buyers","event_selectors":[{"event":"Purchase"}]}]' --where '(behaviors["buyers"] > 0)'`

## Execute Stream

### Python API

```python
import mixpanel_data as mp

ws = mp.Workspace()
for profile in ws.stream_profiles():
    print(profile)
```

### CLI (stdout streaming)

```bash
mp stream profiles
```

### With Filters

```bash
mp stream profiles \
  --cohort 12345 \
  --where 'properties["plan"] == "premium"'
```

## Post-Stream Next Steps

After streaming:

1. **Analyze with live queries**:
   - Run `/mp-query segmentation` for event analysis
   - Run `/mp-query retention` for retention analysis

2. **Explore schema**:
   - Run `/mp-inspect cohorts` to discover cohorts

## Error Handling

**AuthenticationError**: Credentials invalid
- Solution: Run `/mp-auth` to reconfigure

**RateLimitError**: API rate limited
- Solution: Wait and retry (shows retry_after seconds)

**ValidationError**: Invalid parameter combination
- `--distinct-id` and `--distinct-ids` are mutually exclusive
- `--behaviors` and `--cohort` are mutually exclusive
- `--include-all-users` requires `--cohort`
