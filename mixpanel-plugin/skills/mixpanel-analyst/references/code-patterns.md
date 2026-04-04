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
    print(f"  {t.event:40s}")

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

df = ws.segmentation(event="Login", from_date="2025-01-01", to_date="2025-03-31", unit="day").df
counts = df[df["segment"] == "total"].set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)

counts_df = counts.to_frame()
counts_df["7d_avg"] = counts.rolling(7).mean()
counts_df["wow_change"] = counts.pct_change(7) * 100

print("=== Login Trend ===")
print(counts_df.tail(14).to_string())
print(f"\nAvg daily: {counts.mean():,.0f}")
print(f"Peak: {counts.max():,.0f} on {counts.idxmax()}")
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

totals = df.groupby("segment")["count"].sum().sort_values(ascending=False)
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
revenue_df = ws.segmentation_sum(
    event="Purchase", on='properties["revenue"]',
    from_date="2025-01-01", to_date="2025-01-31",
).df
revenue_s = revenue_df[revenue_df["segment"] == "total"].set_index("date")["count"]

# Transaction count
txns_df = ws.segmentation(
    event="Purchase", from_date="2025-01-01", to_date="2025-01-31",
).df
txns_s = txns_df[txns_df["segment"] == "total"].set_index("date")["count"]

# Unique buyers
buyers_df = ws.event_counts(
    events=["Purchase"], from_date="2025-01-01", to_date="2025-01-31",
    type="unique",
).df
buyers_s = buyers_df[buyers_df["segment"] == "total"].set_index("date")["count"]

combined = pd.DataFrame({
    "Revenue": revenue_s,
    "Transactions": txns_s,
    "Unique Buyers": buyers_s,
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
event = "Login"

current_df = ws.segmentation(event=event, from_date="2025-03-01", to_date="2025-03-31").df
previous_df = ws.segmentation(event=event, from_date="2025-02-01", to_date="2025-02-28").df

c_total = current_df[current_df["segment"] == "total"]["count"].sum()
p_total = previous_df[previous_df["segment"] == "total"]["count"].sum()
change = (c_total - p_total) / p_total * 100 if p_total != 0 else 0

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
    curr_totals = curr.groupby("segment")["count"].sum()
    prev_totals = prev.groupby("segment")["count"].sum()
    delta = (curr_totals - prev_totals).dropna().sort_values()
    print(f"\n--- Change by {dim} ---")
    print(delta.head(5))
```

## 9. Feature Adoption Tracking

```python
"""Track adoption of a new feature over time."""
import mixpanel_data as mp

ws = mp.Workspace()

# Unique adopters per day
adopters_df = ws.event_counts(
    events=["Use New Feature"],
    from_date="2025-03-01", to_date="2025-03-31",
    unit="day", type="unique",
).df
adopters_s = adopters_df[adopters_df["segment"] == "total"].set_index("date")["count"]

# Total user base for comparison
total_users_df = ws.event_counts(
    events=["Login"],
    from_date="2025-03-01", to_date="2025-03-31",
    unit="day", type="unique",
).df
total_users_s = total_users_df[total_users_df["segment"] == "total"].set_index("date")["count"]

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

ws = mp.Workspace()

# List available cohorts
cohorts = ws.cohorts()
for c in cohorts:
    print(f"  [{c.id}] {c.name} ({c.count} users)")

# Compare event rates between cohorts
# Use where filters to segment by cohort properties
paid = ws.segmentation(
    event="Feature Use", from_date="2025-01-01", to_date="2025-01-31",
    where='user["plan"] == "paid"',
).df
free = ws.segmentation(
    event="Feature Use", from_date="2025-01-01", to_date="2025-01-31",
    where='user["plan"] == "free"',
).df

import pandas as pd
comparison = pd.DataFrame({
    "Paid Users": paid.groupby("date")["count"].sum(),
    "Free Users": free.groupby("date")["count"].sum(),
})
print("=== Feature Use: Paid vs Free ===")
print(comparison.describe())
```

## 11. Multi-Metric Dashboard

```python
"""Generate a text-based executive dashboard."""
import mixpanel_data as mp
from concurrent.futures import ThreadPoolExecutor

ws = mp.Workspace()
period = dict(from_date="2025-03-01", to_date="2025-03-31")

# Fetch all KPIs in parallel — each query is independent
with ThreadPoolExecutor(max_workers=4) as pool:
    f_dau = pool.submit(lambda: ws.event_counts(events=["Login"], **period, type="unique").df)
    f_signups = pool.submit(lambda: ws.segmentation(event="Sign Up", **period).df)
    f_purchases = pool.submit(lambda: ws.segmentation(event="Purchase", **period).df)
    f_revenue = pool.submit(lambda: ws.segmentation_sum(event="Purchase", on='properties["revenue"]', **period).df)

def _total(df: "pd.DataFrame") -> float:
    return df[df["segment"] == "total"]["count"].sum()

def _mean(df: "pd.DataFrame") -> float:
    return df[df["segment"] == "total"]["count"].mean()

dau = _mean(f_dau.result())
signups = _total(f_signups.result())
purchases = _total(f_purchases.result())
revenue = _total(f_revenue.result())

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
anomalies = ws.list_data_volume_anomalies()
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
