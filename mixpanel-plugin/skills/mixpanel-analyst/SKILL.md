---
name: mixpanel-analyst
description: This skill should be used when the user asks about Mixpanel product analytics, event data, funnel analysis, retention curves, cohort analysis, segmentation queries, JQL, user behavior, conversion rates, churn, DAU/MAU, ARPU, revenue metrics, feature adoption, A/B test results, or any request to query, explore, visualize, or analyze Mixpanel data using Python.
allowed-tools: Bash Read Write
---

# Mixpanel Analyst — CodeMode

Analyze the user's Mixpanel data by **writing and executing Python code** that uses the `mixpanel_data` library and `pandas`. Act as a senior data analyst and product analytics expert.

## Core Principle: Code Over Tools

Write Python code. Never teach CLI commands. Never call MCP tools.

- **Quick lookups** → `python3 -c "..."` one-liners
- **Multi-step analysis** → write and execute `.py` files
- **Data manipulation** → pandas DataFrames (every result type has a `.df` property)
- **Visualization** → matplotlib / seaborn, saved to files

```python
# One-liner example
python3 -c "
import mixpanel_data as mp
ws = mp.Workspace()
r = ws.segmentation(event='Login', from_date='2025-01-01', to_date='2025-01-31')
print(r.df)
"
```

## On-Demand API Lookup

Before writing any API call you're unsure about, look up the exact signature:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.segmentation
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py SegmentationResult
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace          # list all methods
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py types               # list all types
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py exceptions          # list all exceptions
```

Use this before every unfamiliar method. It pulls live docstrings from the installed package — always accurate.

## Workspace Construction

```python
import mixpanel_data as mp

# From configured account
ws = mp.Workspace()                          # default account
ws = mp.Workspace(account="production")      # named account

# Environment variables: MP_USERNAME, MP_SECRET, MP_PROJECT_ID, MP_REGION
ws = mp.Workspace()

# With workspace ID for App API (entity CRUD)
ws = mp.Workspace(workspace_id=12345)
```

## Quick API Reference

### Discovery — What Data Exists?

```python
ws.events()                                    # → list[str]
ws.properties("Login")                         # → list[str]
ws.property_values("city", event="Login", limit=20)  # → list[str]
ws.top_events(limit=10)                        # → list[TopEvent]
ws.funnels()                                   # → list[FunnelInfo]
ws.cohorts()                                   # → list[SavedCohort]
ws.list_bookmarks()                            # → list[BookmarkInfo]
ws.lexicon_schemas()                           # → list[LexiconSchema]
```

### Analytics — Query the Data

```python
# Time-series event counts with optional breakdown
result = ws.segmentation(
    event="Login", from_date="2025-01-01", to_date="2025-01-31",
    unit="day",                                      # day | week | month
    on='properties["platform"]',                     # segment by property
    where='properties["country"] == "US"',           # filter
)
df = result.df  # pandas DataFrame

# Funnel conversion
result = ws.funnel(funnel_id=12345, from_date="2025-01-01", to_date="2025-01-31")

# Cohort retention
result = ws.retention(
    born_event="Sign Up", return_event="Login",
    from_date="2025-01-01", to_date="2025-01-31",
)

# JQL (JavaScript Query Language) for custom computation
result = ws.jql("""function main() {
  return Events({from_date: "2025-01-01", to_date: "2025-01-31"})
    .groupByUser(mixpanel.reducer.count())
    .map(u => ({user: u.key, count: u.value}))
}""")

# Additional queries
ws.event_counts(events=["Login", "Signup"], from_date=..., to_date=...)
ws.frequency(event="Purchase", from_date=..., to_date=...)
ws.activity_feed(distinct_ids=["user123"])
ws.query_saved_report(bookmark_id=456)
ws.query_flows(bookmark_id=789)
ws.segmentation_sum(event="Purchase", on='properties["revenue"]', ...)
ws.segmentation_average(event="Purchase", on='properties["duration"]', ...)
```

### Streaming — Raw Data Access

```python
# Memory-efficient event iteration
for event in ws.stream_events(from_date="2025-01-01", to_date="2025-01-02"):
    print(event["event_name"], event["event_time"], event["properties"])

# Profile iteration
for profile in ws.stream_profiles():
    print(profile["distinct_id"])
```

### Entity Management (App API)

Full CRUD for dashboards, cohorts, feature flags, experiments, alerts, annotations, webhooks, Lexicon definitions, and more. Use `help.py` to look up exact signatures:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.list_dashboards
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.create_cohort
python3 ${CLAUDE_SKILL_DIR}/scripts/help.py Workspace.list_feature_flags
```

### DataFrame Conversion

Every query result has a `.df` property returning a pandas DataFrame:

```python
result = ws.segmentation(event="Login", from_date="2025-01-01", to_date="2025-01-31")
df = result.df
df.plot(title="Login Trend")
df.to_csv("logins.csv")
print(df.describe())
```

## Filter Expression Syntax

```python
# WHERE — filter events
where='properties["platform"] == "iOS"'
where='properties["country"] IN ["US", "UK"]'
where='properties["revenue"] > 100'
where='defined(properties["email"])'

# ON — segment/breakdown
on='properties["platform"]'
on='properties["country"]'

# Combine with AND/OR/NOT
where='properties["platform"] == "iOS" AND properties["country"] == "US"'
```

## How to Think About Analysis

### 1. Always Start with Discovery

Before answering any question, explore the schema:

```python
import mixpanel_data as mp
ws = mp.Workspace()
events = ws.events()
top = ws.top_events(limit=10)
# Then drill into relevant events
props = ws.properties("Sign Up")
```

### 2. Classify with AARRR

Map every question to a pirate metric stage:

| Stage | Key Question | Primary Methods |
|-------|-------------|-----------------|
| **Acquisition** | Where do users come from? | `segmentation` with source/utm breakdown |
| **Activation** | Do they reach the aha moment? | `funnel`, `activity_feed` |
| **Retention** | Do they come back? | `retention`, `segmentation` over time |
| **Revenue** | Do they pay? | `segmentation_sum` on revenue, `funnel` to purchase |
| **Referral** | Do they invite others? | `segmentation` on invite/share events |

### 3. GQM for Vague Questions

For open-ended questions ("why is retention down?"), decompose with Goal-Question-Metric:

1. **Goal**: What business outcome are we investigating?
2. **Questions**: 3-5 specific, measurable sub-questions
3. **Metrics**: For each question, which `mixpanel_data` method answers it?

Then execute all queries and synthesize.

### 4. Provide Actionable Insights

Never just show data. Always:
- State the finding clearly
- Quantify the impact
- Suggest a concrete next step
- Flag anything unexpected

## Writing Effective Code

### One-Liners for Quick Answers

```python
python3 -c "
import mixpanel_data as mp; ws = mp.Workspace()
r = ws.segmentation(event='Login', from_date='2025-01-01', to_date='2025-01-31')
print(f'Total logins: {r.df.sum().values[0]:,.0f}')
"
```

### Scripts for Multi-Step Analysis

Write a `.py` file when you need:
- Multiple queries combined
- DataFrame transformations
- Visualizations saved to files
- Structured output (tables, reports)

```python
#!/usr/bin/env python3
"""Analyze signup funnel conversion by platform."""
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()

# Discovery
funnels = ws.funnels()
signup_funnel = next(f for f in funnels if "signup" in f.name.lower())

# Query
result = ws.funnel(
    funnel_id=signup_funnel.funnel_id,
    from_date="2025-01-01", to_date="2025-01-31",
    on='properties["platform"]',
)

# Analyze
df = result.df
print("\n=== Signup Funnel by Platform ===")
print(df.to_string())
```

### Parallel Investigation

When diagnosing a metric change, query multiple dimensions simultaneously. Since each query is independent, use `ThreadPoolExecutor` to run them in parallel — cutting wall-clock time proportionally:

```python
import mixpanel_data as mp
from concurrent.futures import ThreadPoolExecutor

ws = mp.Workspace()
base = dict(event="Sign Up", from_date="2025-01-01", to_date="2025-01-31")

# Run independent queries in parallel
def query_dim(dim):
    return ws.segmentation(**base, on=f'properties["{dim}"]').df

dims = ["platform", "country", "utm_source"]
with ThreadPoolExecutor(max_workers=4) as pool:
    results = dict(zip(dims, pool.map(query_dim, dims)))
overall = ws.segmentation(**base).df

# Compare and find the driver
for dim, df in results.items():
    print(f"\n=== By {dim} ===")
    print(df.sum().sort_values(ascending=False).head())
```

Use this pattern whenever you have 3+ independent queries — the speedup is significant for multi-dimensional investigations.

## Error Handling

```python
from mixpanel_data.exceptions import (
    AuthenticationError,  # 401 — bad credentials
    RateLimitError,       # 429 — back off and retry
    QueryError,           # 400 — bad parameters
    JQLSyntaxError,       # 412 — JQL script error
    WorkspaceScopeError,  # workspace_id required
)
```

If you encounter `AuthenticationError`, check credentials are set. If `RateLimitError`, add a short delay and retry. If `QueryError`, verify parameters with `help.py`.

## Additional Resources

Load these references on demand when the quick reference above is insufficient:

- [python-api.md](references/python-api.md) — Read when you need the full method signature for App API CRUD operations (dashboards, cohorts, flags, alerts, webhooks, Lexicon, schema registry, etc.)
- [pandas-patterns.md](references/pandas-patterns.md) — Read when building visualizations, doing statistical analysis, creating heatmaps, or working with streaming data as DataFrames
- [analytical-frameworks.md](references/analytical-frameworks.md) — Read when the user asks an open-ended question requiring structured investigation (GQM decomposition, diagnosis methodology, retention benchmarks)
- [code-patterns.md](references/code-patterns.md) — Read when you need a complete, copy-paste starting point for a common analysis scenario (funnel drop-off, retention curves, revenue analysis, feature adoption, executive dashboards)
