---
description: Explore Mixpanel schema and discover events/properties
allowed-tools: Bash(mp inspect:*), Bash(mp query:*)
argument-hint: [operation] [event-name]
---

# Mixpanel Data Inspector

Explore Mixpanel schema, discover events, and analyze data structure.

## Pre-flight Check

Check credentials:

```bash
!$(mp auth test 2>&1 || echo "⚠️  No credentials configured")
```

If no credentials: Suggest running `/mp-auth` first.

## Operation Selection

Choose an inspection operation from `$1` or present menu:

### Category 1: Discover Schema (Live API)
1. **events** - List all tracked event names
2. **properties** - List properties for a specific event
3. **funnels** - List saved funnels
4. **cohorts** - List saved cohorts

### Category 2: Analyze Patterns (Live API)
5. **distribution** - Property value distribution (JQL)
6. **daily** - Daily event counts (JQL)

---

## Operation 1: events - List All Events

Discover all event names tracked in your Mixpanel project.

```bash
!$(mp inspect events --format table)
```

**Output**: List of all event names alphabetically sorted.

**Filter with jq** (JSON format only):
```bash
# Get first 5 events
mp inspect events --format json --jq '.[:5]'

# Find events containing "User"
mp inspect events --format json --jq '.[] | select(contains("User"))'

# Count total events
mp inspect events --format json --jq 'length'
```

**Chain suggestions:**
- Pick an interesting event → Run `/mp-inspect properties <event-name>` to see its properties
- Ready to stream specific events? → Run `/mp-fetch` to stream event data
- Want to see trending events? → Use CLI: `mp inspect top-events --format table`

---

## Operation 2: properties - Event Properties

Show all properties tracked for a specific event.

### Determine Event Name

- Use `$2` if provided (e.g., `/mp-inspect properties PageView`)
- Otherwise, ask user for event name
- Suggest running `events` operation first if unsure

### Execute

```bash
!$(mp inspect properties -e "<event-name>" --format table)
```

**Output**: Property names, data types, and example values.

**Chain suggestions:**
- Check property values → Run `/mp-inspect distribution <property-name>`
- Use in query filter → Run `/mp-query segmentation` with WHERE clause on this property
- Stream filtered events → Run `/mp-fetch` with event and property filters

---

## Operation 3: funnels - Saved Funnels

List all saved funnel definitions in your Mixpanel project.

```bash
!$(mp inspect funnels --format table)
```

**Output**: Funnel ID, name, and step count.

**Chain suggestions:**
- Analyze specific funnel → Run `/mp-funnel <funnel-id>`
- Create custom funnel → Run `/mp-funnel` and choose custom option
- See funnel details → Use CLI: `mp query funnel <funnel-id> --from <date> --to <date>`

---

## Operation 4: cohorts - Saved Cohorts

List all saved cohorts in your Mixpanel project.

```bash
!$(mp inspect cohorts --format table)
```

**Output**: Cohort ID, name, count, and description.

**Chain suggestions:**
- Stream cohort profiles → Use Python: `ws.stream_profiles(cohort_id="<cohort-id>")`
- Analyze cohort behavior → Run `/mp-retention` with cohort context

---

## Operation 5: distribution - Property Distribution

Analyze value distribution for a property using JQL (JavaScript Query Language).

### Required Parameters

- Property name (e.g., `country`, `plan`, `device_type`)
- Date range: `--from` and `--to` flags

### Execute

```bash
!$(mp query jql - --from <from-date> --to <to-date> << 'EOF'
function main() {
  return Events({
    from_date: params.from_date,
    to_date: params.to_date
  })
  .groupBy(['properties.<property-name>'], mixpanel.reducer.count())
  .sortDesc('value');
}
EOF
)
```

**Output**: Property values with counts and percentages.

**Chain suggestions:**
- Stream filtered data → Run `/mp-fetch` with WHERE clause on high-value properties
- Segmentation → Run `/mp-query segmentation --on <property>` for time-series

---

## Operation 6: daily - Daily Event Counts

Show daily event counts over time using JQL.

### Parameters

- Event name: Optional filter (use `-e` flag)
- Date range: `--from` and `--to` flags

### Execute

**All events:**
```bash
!$(mp query jql - --from <from-date> --to <to-date> << 'EOF'
function main() {
  return Events({
    from_date: params.from_date,
    to_date: params.to_date
  })
  .groupBy(['day'], mixpanel.reducer.count())
  .sortAsc('key.0');
}
EOF
)
```

**Specific event:**
```bash
!$(mp query jql - --from <from-date> --to <to-date> << 'EOF'
function main() {
  return Events({
    from_date: params.from_date,
    to_date: params.to_date,
    event_selectors: [{event: '<event-name>'}]
  })
  .groupBy(['day'], mixpanel.reducer.count())
  .sortAsc('key.0');
}
EOF
)
```

**Output**: Daily counts showing trends and patterns.

**Chain suggestions:**
- See detailed breakdown → Run `/mp-query segmentation` with property breakdown
- Stream period data → Run `/mp-fetch` for date range with high activity
- Retention analysis → Run `/mp-retention` to analyze user retention

---

## Next Steps

After inspecting your data:

- **Discovered interesting events?** → Run `/mp-fetch` to stream them
- **Ready to analyze?** → Run `/mp-query` to execute live queries or JQL
- **Need funnel analysis?** → Run `/mp-funnel` for conversion analysis
- **Need retention analysis?** → Run `/mp-retention` for user retention curves
- **Want a report?** → Run `/mp-report` to generate comprehensive analysis

## Troubleshooting

### No Credentials Configured

If `mp auth test` fails:
- Run `/mp-auth` to setup credentials first

### Event/Property Not Found

If inspection fails with "not found":
- Verify event name is correct (case-sensitive)
- Check property exists with `/mp-inspect properties -e <event>`
- Use `/mp-inspect events` to see all available events

### JQL Operations Slow

If distribution/daily operations timeout:
- Reduce date range (Mixpanel API limit: 60 days recommended)
- Check Mixpanel project size (large projects may be slower)
