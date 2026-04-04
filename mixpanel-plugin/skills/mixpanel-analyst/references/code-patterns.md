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
    print(f"  {t.name:40s}")

# Drill into an event
event_name = top[0].name
props = ws.properties(event_name)
print(f"\nProperties for '{event_name}': {len(props)}")
for p in props[:15]:
    vals = ws.property_values(event_name, p, limit=5)
    print(f"  {p:30s} → {vals}")
```

## 2. Daily/Weekly Trend

```python
"""Track an event over time with rolling average."""
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()

df = ws.segmentation(
    event="Login", from_date="2025-01-01", to_date="2025-03-31", unit="day"
).df

df["7d_avg"] = df.iloc[:, 0].rolling(7).mean()
df["wow_change"] = df.iloc[:, 0].pct_change(7) * 100

print("=== Login Trend ===")
print(df.tail(14).to_string())
print(f"\nAvg daily: {df.iloc[:, 0].mean():,.0f}")
print(f"Peak: {df.iloc[:, 0].max():,.0f} on {df.iloc[:, 0].idxmax()}")
```

## 3. Segment Comparison

```python
"""Compare a metric across segments to find top/bottom performers."""
import mixpanel_data as mp

ws = mp.Workspace()

df = ws.segmentation(
    event="Purchase", from_date="2025-01-01", to_date="2025-01-31",
    on='properties["platform"]',
).df

totals = df.sum().sort_values(ascending=False)
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
    event="Login",
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
revenue = ws.segmentation_sum(
    event="Purchase", property="revenue",
    from_date="2025-01-01", to_date="2025-01-31",
).df

# Transaction count
txns = ws.segmentation(
    event="Purchase", from_date="2025-01-01", to_date="2025-01-31",
    type="general",
).df

# Unique buyers
buyers = ws.segmentation(
    event="Purchase", from_date="2025-01-01", to_date="2025-01-31",
    type="unique",
).df

combined = pd.DataFrame({
    "Revenue": revenue.iloc[:, 0],
    "Transactions": txns.iloc[:, 0],
    "Unique Buyers": buyers.iloc[:, 0],
})
combined["AOV"] = combined["Revenue"] / combined["Transactions"]
combined["ARPU"] = combined["Revenue"] / combined["Unique Buyers"]

print("=== Revenue Summary ===")
print(f"Total Revenue:     ${combined['Revenue'].sum():,.2f}")
print(f"Total Transactions: {combined['Transactions'].sum():,.0f}")
print(f"Avg Order Value:   ${combined['AOV'].mean():,.2f}")
print(f"ARPU:              ${combined['ARPU'].mean():,.2f}")
print(f"\nDaily breakdown:")
print(combined.tail(7).to_string())
```

## 7. User Journey Investigation

```python
"""Investigate a specific user's event sequence."""
import mixpanel_data as mp

ws = mp.Workspace()

# Get user's recent activity
result = ws.activity_feed(user_id="USER_DISTINCT_ID", limit=50)

print("=== User Activity ===")
for event in result.events:
    print(f"  {event.time}  {event.name:30s}  {event.properties}")
```

## 8. Period-over-Period Comparison

```python
"""Compare metrics between two time periods."""
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()
event = "Login"

current = ws.segmentation(event=event, from_date="2025-03-01", to_date="2025-03-31").df
previous = ws.segmentation(event=event, from_date="2025-02-01", to_date="2025-02-28").df

c_total = current.iloc[:, 0].sum()
p_total = previous.iloc[:, 0].sum()
change = (c_total - p_total) / p_total * 100

print(f"=== {event} — Month over Month ===")
print(f"Current:  {c_total:>10,.0f}")
print(f"Previous: {p_total:>10,.0f}")
print(f"Change:   {change:>+10.1f}%")

# By segment
for dim in ["platform", "country"]:
    curr = ws.segmentation(event=event, from_date="2025-03-01", to_date="2025-03-31",
                           on=f'properties["{dim}"]').df
    prev = ws.segmentation(event=event, from_date="2025-02-01", to_date="2025-02-28",
                           on=f'properties["{dim}"]').df
    delta = curr.sum() - prev.sum()
    print(f"\n--- Change by {dim} ---")
    print(delta.sort_values().head(5))
```

## 9. Feature Adoption Tracking

```python
"""Track adoption of a new feature over time."""
import mixpanel_data as mp

ws = mp.Workspace()

# Unique adopters per day
adopters = ws.segmentation(
    event="Use New Feature",
    from_date="2025-03-01", to_date="2025-03-31",
    unit="day", type="unique",
).df

# Total user base for comparison
total_users = ws.segmentation(
    event="Login",
    from_date="2025-03-01", to_date="2025-03-31",
    unit="day", type="unique",
).df

import pandas as pd
combined = pd.DataFrame({
    "Adopters": adopters.iloc[:, 0],
    "Active Users": total_users.iloc[:, 0],
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

ws = mp.Workspace()

# List available cohorts
cohorts = ws.cohorts()
for c in cohorts:
    print(f"  [{c.id}] {c.name} ({c.count} users)")

# Compare event rates between cohorts
# Use where filters to segment by cohort properties
paid = ws.segmentation(
    event="Feature Use", from_date="2025-01-01", to_date="2025-01-31",
    where='user["plan"] == "paid"', type="unique",
).df
free = ws.segmentation(
    event="Feature Use", from_date="2025-01-01", to_date="2025-01-31",
    where='user["plan"] == "free"', type="unique",
).df

import pandas as pd
comparison = pd.DataFrame({
    "Paid Users": paid.iloc[:, 0],
    "Free Users": free.iloc[:, 0],
})
print("=== Feature Use: Paid vs Free ===")
print(comparison.describe())
```

## 11. Multi-Metric Dashboard

```python
"""Generate a text-based executive dashboard."""
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()
period = dict(from_date="2025-03-01", to_date="2025-03-31")

# KPIs
dau = ws.segmentation(event="Login", **period, type="unique").df.iloc[:, 0].mean()
signups = ws.segmentation(event="Sign Up", **period).df.iloc[:, 0].sum()
purchases = ws.segmentation(event="Purchase", **period).df.iloc[:, 0].sum()
revenue = ws.segmentation_sum(event="Purchase", property="revenue", **period).df.iloc[:, 0].sum()

print("╔══════════════════════════════════╗")
print("║     EXECUTIVE DASHBOARD          ║")
print("║     March 2025                   ║")
print("╠══════════════════════════════════╣")
print(f"║  Avg DAU:      {dau:>12,.0f}      ║")
print(f"║  New Signups:  {signups:>12,.0f}      ║")
print(f"║  Purchases:    {purchases:>12,.0f}      ║")
print(f"║  Revenue:     ${revenue:>11,.2f}      ║")
print("╚══════════════════════════════════╝")
```

## 12. Data Governance Audit

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
anomalies = ws.list_data_volume_anomalies(limit=10)
if anomalies:
    print(f"\nRecent anomalies: {len(anomalies)}")
    for a in anomalies[:5]:
        print(f"  - {a}")
```

## Tips

- Always wrap `from_date`/`to_date` as strings: `"2025-01-01"` not `datetime`
- Use `type="unique"` for user counts, `type="general"` for event counts
- JQL is best for user-level calculations that cross events
- Use `help.py` to look up exact method signatures before writing
- Start simple, add complexity only when initial results suggest it's needed
- Print intermediate results to verify before building on them
