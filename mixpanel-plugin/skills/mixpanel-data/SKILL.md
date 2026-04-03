---
name: mixpanel-data
description: Analyze Mixpanel analytics data using the mixpanel_data Python library or mp CLI. Use when working with Mixpanel event data, user profiles, funnels, retention, cohorts, segmentation queries, JQL scripts, or streaming data. Triggers on mentions of Mixpanel, event analytics, funnel analysis, retention curves, user behavior tracking, JQL queries, filter expressions, 'stream data from Mixpanel', 'query Mixpanel', 'analyze user behavior', 'export Mixpanel data', 'mp command', or requests to work with analytics pipelines. Supports filter expressions for WHERE/ON clauses, JQL (JavaScript Query Language) for complex transformations, Python scripts with pandas integration, and CLI pipelines with jq/Unix tools.
---

# Mixpanel Data Analysis

Pure API client for Mixpanel analytics — stream events/profiles, run live queries (segmentation, funnels, retention, JQL), and manage entities via the App API.

## Documentation Access

Full documentation is hosted at **https://jaredmcfarland.github.io/mixpanel_data/** with LLM-optimized access:

| Resource | URL | Use Case |
|----------|-----|----------|
| **llms.txt** | `https://jaredmcfarland.github.io/mixpanel_data/llms.txt` | Index of all docs with descriptions |
| **llms-full.txt** | `https://jaredmcfarland.github.io/mixpanel_data/llms-full.txt` | Complete documentation (~400KB) |
| **Individual pages** | `https://jaredmcfarland.github.io/mixpanel_data/{path}/index.md` | Specific topic deep-dive |

### When to Fetch Documentation

- **Use this skill** for quick patterns, common examples, and API summaries
- **Fetch llms.txt** to discover what documentation exists
- **Fetch llms-full.txt** when you need comprehensive reference (API signatures, all parameters, edge cases)
- **Fetch individual .md** for focused deep-dives (e.g., `/api/workspace/index.md` for Workspace class details)

### Documentation Structure

| Path | Content |
|------|---------|
| `/getting-started/installation/index.md` | Installation options |
| `/getting-started/quickstart/index.md` | 5-minute tutorial |
| `/getting-started/configuration/index.md` | Credentials and config |
| `/guide/fetching/index.md` | Fetching events/profiles |
| `/guide/streaming/index.md` | Streaming without storage |
| `/guide/streaming/index.md` | Streaming events and profiles |
| `/guide/live-analytics/index.md` | Segmentation, funnels, retention |
| `/guide/discovery/index.md` | Schema exploration |
| `/api/workspace/index.md` | Workspace class reference |
| `/api/auth/index.md` | Authentication module |
| `/api/exceptions/index.md` | Exception hierarchy |
| `/api/types/index.md` | Result types |
| `/cli/commands/index.md` | CLI command reference |

## Reference Files Guide

When you need detailed information, read these reference files:

| File | When to Read |
|------|--------------|
| [library-api.md](references/library-api.md) | Complete Python API signatures, parameters, return types for all Workspace methods |
| [cli-commands.md](references/cli-commands.md) | Full CLI command reference with all options and examples |
| [query-expressions.md](references/query-expressions.md) | Complete filter expression syntax, JQL reference, built-in reducers, bucketing |
| [patterns.md](references/patterns.md) | Streaming patterns, pandas integration, jq/Unix pipelines, data science workflows |
| [documentation.md](references/documentation.md) | How to fetch external documentation from llms.txt, page URLs, fetch strategy |

## When to Use

### Python Library (`mixpanel_data`)
- Building scripts, notebooks, or data pipelines
- Need DataFrame results for pandas/visualization
- Complex multi-step analysis
- Programmatic credential management

### CLI (`mp`)
- Quick one-off queries
- Shell scripting or Unix pipelines
- Streaming data to jq, awk, or other tools
- Non-Python environments

## Two Data Paths

### Path 1: Live Queries (Quick Answers)
Call Mixpanel API directly for real-time metrics.

```python
# Python
result = ws.segmentation("Purchase", from_date="2024-01-01", to_date="2024-01-31", on="country")
print(result.df)
```

```bash
# CLI
mp query segmentation -e Purchase --from 2024-01-01 --to 2024-01-31 --on country
```

### Path 2: Streaming (Pipelines)
Stream events/profiles for processing with external tools.

```python
# Python - memory-efficient streaming
for event in ws.stream_events(from_date="2024-01-01", to_date="2024-01-31"):
    print(event)

for profile in ws.stream_profiles():
    print(profile)
```

```bash
# CLI - pipe to jq or other tools
mp stream events --from 2024-01-01 --to 2024-01-01 | jq '.event'
mp stream events --from 2024-01-01 --to 2024-01-01 | jq -r '[.event, .distinct_id] | @csv' > events.csv
```

## Filter Expressions (WHERE/ON)

Filter expressions use SQL-like syntax for filtering and segmenting data in API calls.

**ON Parameter** (segmentation): Accepts bare property names (auto-wrapped) or full expressions
```bash
mp query segmentation -e Purchase --on country
```

**WHERE Parameter** (filtering): Always uses full expression syntax
```bash
mp query segmentation -e Purchase --where 'properties["amount"] > 100 and properties["plan"] in ["premium", "enterprise"]'
```

For complete expression syntax (comparison, logical, set operations, existence functions, date/time functions), see [references/query-expressions.md](references/query-expressions.md).

## JQL (JavaScript Query Language)

Full JavaScript-based query language for complex transformations. Use `Events()`, `People()`, `join()` with transformations like `.filter()`, `.map()`, `.groupBy()`, `.reduce()`.

```bash
mp query jql script.js --param from_date=2024-01-01
```

For complete JQL reference (data sources, transformations, built-in reducers, bucketing, common patterns), see [references/query-expressions.md](references/query-expressions.md).

## Credentials

Resolution priority:
1. Environment variables: `MP_USERNAME`, `MP_SECRET`, `MP_PROJECT_ID`, `MP_REGION`
2. Named account: `Workspace(account="prod")` or `mp --account prod`
3. Default account from `~/.mp/config.toml`

## Quick Start Examples

### Python: Stream and Analyze

```python
import mixpanel_data as mp

ws = mp.Workspace()

# Stream events
for event in ws.stream_events(from_date="2024-01-01", to_date="2024-01-31"):
    print(event)

# Run segmentation
result = ws.segmentation("Purchase", from_date="2024-01-01", to_date="2024-01-31", on="country")
print(result.df)

# Schema discovery
events = ws.events()
props = ws.properties("Purchase")

ws.close()
```

### CLI: Discover and Query

```bash
# Discover available events
mp inspect events --format table

# Run segmentation query
mp query segmentation -e Purchase --from 2024-01-01 --to 2024-01-31 --on country

# Stream events for processing
mp stream events --from 2024-01-01 --to 2024-01-31 | jq '.event'
```

### CLI: Live Queries

```bash
# Segmentation
mp query segmentation -e Purchase --from 2024-01-01 --to 2024-01-31 --on country

# Funnel (requires saved funnel ID)
mp inspect funnels  # List funnels to get ID
mp query funnel 12345 --from 2024-01-01 --to 2024-01-31

# Retention
mp query retention --born "Sign Up" --return "Purchase" --from 2024-01-01 --to 2024-01-31
```

## Data Format

Streamed events contain: `event` (name), `time`, `distinct_id`, `properties` (dict)
Streamed profiles contain: `distinct_id`, `properties` (dict), `last_seen`

See [references/patterns.md](references/patterns.md) for integration patterns.

## Output Formats (CLI)

`--format json` (default), `jsonl`, `table`, `csv`, `plain`

### Filtering with --jq

Commands that output JSON also support the `--jq` option for client-side filtering using jq syntax:

```bash
# Get first 5 events
mp inspect events --format json --jq '.[:5]'

# Filter by name pattern
mp inspect events --format json --jq '.[] | select(contains("User"))'

# Extract fields from query results
mp query segmentation -e Purchase --from 2024-01-01 --to 2024-01-31 \
  --format json --jq '.total'
```

Note: `--jq` only works with `--format json` or `--format jsonl`.

## API Overview

The Workspace class provides three main capability areas:

1. **Discovery**: `events()`, `properties()`, `funnels()`, `cohorts()` - Explore project schema
2. **Streaming**: `stream_events()`, `stream_profiles()` - Stream data from Mixpanel API
3. **Analytics**: `segmentation()`, `funnel()`, `retention()`, `jql()` - Live queries and analysis
4. **Entity CRUD**: Dashboards, reports, cohorts, feature flags, experiments, alerts, annotations, webhooks, Lexicon

### Advanced Profile Streaming

`stream_profiles()` supports advanced filtering:

```python
# Stream specific users by ID
for p in ws.stream_profiles(distinct_ids=["user_1", "user_2"]):
    print(p)

# Stream group profiles (companies, accounts, etc.)
for p in ws.stream_profiles(group_id="companies"):
    print(p)

# Stream users by behavior (e.g., purchased in last 30 days)
for p in ws.stream_profiles(
    behaviors=[{"window": "30d", "name": "buyers", "event_selectors": [{"event": "Purchase"}]}],
    where='(behaviors["buyers"] > 0)'
):
    print(p)

# Query historical profile state
for p in ws.stream_profiles(as_of_timestamp=1704067200):
    print(p)

# Cohort membership analysis (include non-members with flag)
for p in ws.stream_profiles(cohort_id="12345", include_all_users=True):
    print(p)
```

**Parameter constraints**: `distinct_id`/`distinct_ids` mutually exclusive; `behaviors`/`cohort_id` mutually exclusive; `include_all_users` requires `cohort_id`.

For complete method signatures and parameters, see [references/library-api.md](references/library-api.md).

## Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `AuthenticationError` | Invalid credentials | Check `mp auth test` |
| `RateLimitError` | API rate limited | Wait for retry_after seconds |
| `EventNotFoundError` | Event not in project | Check `mp inspect events` |
