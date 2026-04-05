# Code Patterns — Ready-to-Use Python Snippets

Copy-paste patterns for common Mixpanel analysis scenarios. Each pattern is self-contained and uses `mixpanel_data` + `pandas`.

## 1. Schema Exploration

```python
"""Explore what data is available in the project."""
import mixpanel_data as mp

ws = mp.Workspace()

# Overview
events = ws.events()
top = ws.top_events(limit=20)

print(f"Total events: {len(events)}")
print("\nTop events by volume:")
for t in top:
    print(f"  {t.event:40s} {t.count:>10,} ({t.percent_change:+.1f}%)")

# Drill into an event
event_name = top[0].event
props = ws.properties(event_name)
print(f"\nProperties for '{event_name}': {len(props)}")
for p in props[:15]:
    vals = ws.property_values(p, event=event_name, limit=5)
    print(f"  {p:30s} → {vals}")
```

## 2. Daily/Weekly Trend

```python
"""Track an event over time with rolling average."""
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()

result = ws.query("Login", last=90, unit="day")
df = result.df
counts = df.set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)

print(f"Total: {counts.sum():,.0f}")
print(f"Daily avg: {counts.mean():,.0f}")
trend = counts.to_frame()
trend["7d_avg"] = counts.rolling(7).mean()

print("=== Login Trend ===")
print(trend.tail(14).to_string())
print(f"\nPeak: {counts.max():,.0f} on {counts.idxmax()}")
```

## 3. Segment Comparison

```python
"""Compare a metric across segments to find top/bottom performers."""
import mixpanel_data as mp

ws = mp.Workspace()

result = ws.query("Purchase", last=30, group_by="platform")
df = result.df
totals = df.groupby("event")["count"].sum().sort_values(ascending=False)
pct = (totals / totals.sum() * 100).round(1)

print("=== Purchases by Platform ===")
for platform, count in totals.items():
    print(f"  {platform:20s} {count:>8,.0f}  ({pct[platform]}%)")
```

## 4. Funnel Drop-Off Analysis

```python
"""Analyze where users drop off in a funnel."""
import mixpanel_data as mp

ws = mp.Workspace()

# Find the funnel
funnels = ws.funnels()
for f in funnels:
    print(f"  [{f.funnel_id}] {f.name}")

# Analyze (replace with actual funnel_id)
result = ws.funnel(funnel_id=FUNNEL_ID, from_date="2025-01-01", to_date="2025-01-31")
df = result.df
print("\n=== Funnel Analysis ===")
print(df.to_string())
```

## 5. Retention Curve

```python
"""Calculate and display N-day retention."""
import mixpanel_data as mp

ws = mp.Workspace()

result = ws.retention(
    born_event="Sign Up",
    return_event="Login",
    from_date="2025-01-01",
    to_date="2025-02-28",
)
df = result.df

print("=== Retention ===")
print(df.to_string())

# Key metrics
if len(df.columns) > 1:
    d1 = df.iloc[:, 1].mean() if len(df.columns) > 1 else None
    d7 = df.iloc[:, 7].mean() if len(df.columns) > 7 else None
    d30 = df.iloc[:, 30].mean() if len(df.columns) > 30 else None
    print(f"\nAvg D1: {d1:.1%}" if d1 else "")
    print(f"Avg D7: {d7:.1%}" if d7 else "")
    print(f"Avg D30: {d30:.1%}" if d30 else "")
```

## 6. Revenue Analysis

```python
"""Analyze revenue trends and per-user metrics."""
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()

# Daily revenue
revenue = ws.query(
    "Purchase", math="total", math_property="revenue",
    from_date="2025-01-01", to_date="2025-01-31",
).df

# Average order value
aov = ws.query(
    "Purchase", math="average", math_property="revenue",
    from_date="2025-01-01", to_date="2025-01-31",
).df

# Revenue per user
arpu = ws.query(
    "Purchase", math="total", per_user="average",
    math_property="revenue",
    from_date="2025-01-01", to_date="2025-01-31",
).df

print("=== Revenue Summary ===")
print(f"Total Revenue:     ${revenue['count'].sum():,.2f}")
print(f"Avg Order Value:   ${aov['count'].mean():,.2f}")
print(f"ARPU:              ${arpu['count'].mean():,.2f}")
print(f"\nDaily revenue breakdown:")
print(revenue.tail(7).to_string())
```

## 7. User Journey Investigation

```python
"""Investigate a specific user's event sequence."""
import mixpanel_data as mp

ws = mp.Workspace()

# Get user's recent activity
result = ws.activity_feed(distinct_ids=["USER_DISTINCT_ID"])

print("=== User Activity ===")
for event in result.events:
    print(f"  {event.time}  {event.event:30s}  {event.properties}")
```

## 8. Period-over-Period Comparison

```python
"""Compare metrics between two time periods."""
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()

current = ws.query("Sign Up", from_date="2025-02-01", to_date="2025-02-28").df
previous = ws.query("Sign Up", from_date="2025-01-01", to_date="2025-01-31").df
c_total = current["count"].sum()
p_total = previous["count"].sum()
change = (c_total - p_total) / p_total * 100
print(f"MoM change: {change:+.1f}%")

# By dimension
for dim in ["platform", "country", "utm_source"]:
    c = ws.query("Sign Up", from_date="2025-02-01", to_date="2025-02-28", group_by=dim).df
    p = ws.query("Sign Up", from_date="2025-01-01", to_date="2025-01-31", group_by=dim).df
    c_by = c.groupby("event")["count"].sum()
    p_by = p.groupby("event")["count"].sum()
    print(f"\n=== By {dim} ===")
    combined = pd.DataFrame({"current": c_by, "previous": p_by}).fillna(0)
    combined["change_%"] = ((combined["current"] - combined["previous"]) / combined["previous"].replace(0, 1) * 100).round(1)
    print(combined.sort_values("change_%"))
```

## 9. Feature Adoption Tracking

```python
"""Track adoption of a new feature over time."""
import mixpanel_data as mp

ws = mp.Workspace()

# Unique adopters per day
adopters_df = ws.query(
    "Use New Feature", math="unique",
    from_date="2025-03-01", to_date="2025-03-31",
).df
adopters_s = adopters_df.set_index("date")["count"]

# Total user base for comparison
total_users_df = ws.query(
    "Login", math="unique",
    from_date="2025-03-01", to_date="2025-03-31",
).df
total_users_s = total_users_df.set_index("date")["count"]

import pandas as pd
combined = pd.DataFrame({
    "Adopters": adopters_s,
    "Active Users": total_users_s,
})
combined["Adoption %"] = (combined["Adopters"] / combined["Active Users"] * 100).round(1)

print("=== Feature Adoption ===")
print(combined.tail(14).to_string())
print(f"\nPeak adoption: {combined['Adoption %'].max():.1f}%")
print(f"Latest: {combined['Adoption %'].iloc[-1]:.1f}%")
```

## 10. Cohort Comparison

```python
"""Compare behavior across user cohorts."""
import mixpanel_data as mp
from mixpanel_data import Filter

ws = mp.Workspace()

# List available cohorts
cohorts = ws.cohorts()
for c in cohorts:
    print(f"  [{c.id}] {c.name} ({c.count} users)")

# Compare event rates between cohorts
# Use Filter objects to segment by cohort properties
paid = ws.query(
    "Purchase", from_date="2025-01-01", to_date="2025-01-31",
    where=Filter.equals("plan", "paid"),
).df
free = ws.query(
    "Purchase", from_date="2025-01-01", to_date="2025-01-31",
    where=Filter.equals("plan", "free"),
).df

import pandas as pd
comparison = pd.DataFrame({
    "Paid Users": paid.groupby("date")["count"].sum(),
    "Free Users": free.groupby("date")["count"].sum(),
})
print("=== Purchase: Paid vs Free ===")
print(comparison.describe())
```

## 11. Date-Filtered Analysis

```python
"""Filter by date properties — signup cohorts, time-bounded queries."""
import mixpanel_data as mp
from mixpanel_data import Filter

ws = mp.Workspace()

# Users who signed up in the last 30 days
recent_signups = ws.query(
    "Purchase",
    math="total",
    math_property="revenue",
    where=Filter.in_the_last("signup_date", 30, "day"),
    last=30,
)

# Activity before a specific date
early_users = ws.query(
    "Login",
    math="unique",
    where=Filter.before("created", "2024-01-01"),
    last=90,
)

# Custom percentile — p95 response time
p95_latency = ws.query(
    "API Call",
    math="percentile",
    math_property="duration_ms",
    percentile_value=95,
    last=30,
)

print("=== Recent Signup Revenue ===")
print(recent_signups.df.describe())
print("=== P95 Latency ===")
print(p95_latency.df.tail())
```

## 12. Multi-Metric Dashboard

```python
"""Generate a text-based executive dashboard."""
import mixpanel_data as mp
from concurrent.futures import ThreadPoolExecutor

ws = mp.Workspace()
period = dict(from_date="2025-01-01", to_date="2025-01-31")

queries = {
    "Signups": dict(events="Sign Up", math="unique", **period),
    "DAU": dict(events="Login", math="dau", **period),
    "Revenue": dict(events="Purchase", math="total", math_property="revenue", **period),
    "ARPU": dict(events="Purchase", math="total", per_user="average", math_property="revenue", **period),
}

def run_query(args):
    name, kwargs = args
    return name, ws.query(**kwargs).df

with ThreadPoolExecutor(max_workers=4) as pool:
    results = dict(pool.map(run_query, queries.items()))

print("╔══════════════════════════════════╗")
print("║     EXECUTIVE DASHBOARD          ║")
print("║     January 2025                 ║")
print("╠══════════════════════════════════╣")
print(f"║  Signups:      {results['Signups']['count'].sum():>12,.0f}      ║")
print(f"║  Avg DAU:      {results['DAU']['count'].mean():>12,.0f}      ║")
print(f"║  Revenue:     ${results['Revenue']['count'].sum():>11,.2f}      ║")
print(f"║  ARPU:        ${results['ARPU']['count'].mean():>11,.2f}      ║")
print("╚══════════════════════════════════╝")
```

## 13. Data Governance Audit

```python
"""Audit event schema and data quality."""
import mixpanel_data as mp

ws = mp.Workspace()

# Check Lexicon definitions
schemas = ws.lexicon_schemas()
events = ws.events()

documented = {s.name for s in schemas}
undocumented = set(events) - documented

print(f"Total events: {len(events)}")
print(f"Documented in Lexicon: {len(documented)}")
print(f"Undocumented: {len(undocumented)}")

if undocumented:
    print("\nUndocumented events:")
    for e in sorted(undocumented)[:20]:
        print(f"  - {e}")

# Check for volume anomalies
anomalies = ws.list_data_volume_anomalies()
if anomalies:
    print(f"\nRecent anomalies: {len(anomalies)}")
    for a in anomalies[:5]:
        print(f"  - {a}")
```

## 14. Create Dashboard with Reports

```python
"""Create a Mixpanel dashboard and populate it with reports programmatically."""
import mixpanel_data as mp
from mixpanel_data import CreateDashboardParams, CreateBookmarkParams, GroupBy

ws = mp.Workspace(account="myaccount")

# Step 1: Create dashboard
dashboard = ws.create_dashboard(CreateDashboardParams(title="Product Overview"))

# Step 2: Create reports via query()
r1 = ws.query("Sign Up", math="total", last=180, unit="month")
bm1 = ws.create_bookmark(CreateBookmarkParams(
    name="Signups Trend (6mo)", bookmark_type="insights", params=r1.params,
))

r2 = ws.query("Sign Up", last=180, unit="month", group_by="platform")
bm2 = ws.create_bookmark(CreateBookmarkParams(
    name="Signups by Platform", bookmark_type="insights", params=r2.params,
))

r3 = ws.query("Sign Up", math="dau", last=90)
bm3 = ws.create_bookmark(CreateBookmarkParams(
    name="DAU (90d)", bookmark_type="insights", params=r3.params,
))

# Step 3: Add to dashboard
for bm in [bm1, bm2, bm3]:
    ws.add_report_to_dashboard(dashboard.id, bm.id)

print(f"Dashboard created: {dashboard.id}")
```

## Tips

- Always wrap `from_date`/`to_date` as strings: `"2025-01-01"` not `datetime`
- `project_id` must be a **string**: `Workspace(project_id="8")` not `project_id=8`
- Use `type="unique"` for user counts, `type="general"` for event counts
- `TopEvent` has fields: `event` (str), `count` (int), `percent_change` (float) — no `rank`
- `BookmarkInfo.type` is a plain string (e.g., `"insights"`), not an enum — use directly, not `.value`
- JQL is best for user-level calculations that cross events
- Use `help.py` to look up exact method signatures before writing
- Start simple, add complexity only when initial results suggest it's needed
- Print intermediate results to verify before building on them
- When adding reports to dashboards, `source_bookmark_id` creates a clone ("Duplicate of ...") — edit the clone's name in Mixpanel UI if needed
