# Pandas Patterns for Mixpanel Data

DataFrame workflows, visualization, and data science patterns using `mixpanel_data` results.

## DataFrame Conversion

Every query result type has a `.df` property:

```python
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()
result = ws.segmentation(event="Login", from_date="2025-01-01", to_date="2025-01-31")
df = result.df  # long-format DataFrame with columns: date, segment, count
```

## Common Transformations

### Time Series Analysis

```python
# Daily trend with rolling average
df = ws.segmentation(event="Login", from_date="2025-01-01", to_date="2025-03-31", unit="day").df

# For unsegmented queries, work with the count series
counts = df[df["segment"] == "total"].set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)

# Rolling average and week-over-week
counts_df = counts.to_frame()
counts_df["rolling_7d"] = counts.rolling(7).mean()
counts_df["wow_change"] = counts.pct_change(7) * 100
print(counts_df.tail(14))
```

### Segmented Analysis

```python
# Breakdown by property, find top segments
df = ws.segmentation(
    event="Purchase", from_date="2025-01-01", to_date="2025-01-31",
    on='properties["country"]'
).df

# Top 5 countries by total
totals = df.groupby("segment")["count"].sum().sort_values(ascending=False)
print("Top 5 countries:")
print(totals.head())

# Percentage distribution
pct = (totals / totals.sum() * 100).round(1)
print("\nDistribution:")
print(pct.head(10))
```

### Funnel Analysis

```python
result = ws.funnel(funnel_id=12345, from_date="2025-01-01", to_date="2025-01-31")
df = result.df

# Step-by-step conversion
for i, step in enumerate(result.steps):
    print(f"Step {i+1}: {step.event:30s} {step.conversion_rate:.1%}")

# Overall conversion
if result.steps:
    print(f"\nOverall: {result.conversion_rate:.1%}")
```

### Retention Heatmap

```python
import numpy as np

result = ws.retention(
    born_event="Sign Up", return_event="Login",
    from_date="2025-01-01", to_date="2025-02-28",
)
df = result.df

# Format as percentage heatmap
print("\n=== Retention Heatmap ===")
print(df.applymap(lambda x: f"{x:.0%}" if pd.notna(x) else "—").to_string())
```

### Combining Multiple Queries

```python
import pandas as pd
import mixpanel_data as mp

ws = mp.Workspace()

# Multiple metrics side by side
logins = ws.segmentation(event="Login", from_date="2025-01-01", to_date="2025-01-31").df
signups = ws.segmentation(event="Sign Up", from_date="2025-01-01", to_date="2025-01-31").df
purchases = ws.segmentation(event="Purchase", from_date="2025-01-01", to_date="2025-01-31").df

def extract_counts(df: pd.DataFrame) -> pd.Series:
    """Extract the count series from a long-format segmentation DataFrame."""
    s = df[df["segment"] == "total"].set_index("date")["count"]
    s.index = pd.to_datetime(s.index)
    return s

combined = pd.DataFrame({
    "Logins": extract_counts(logins),
    "Signups": extract_counts(signups),
    "Purchases": extract_counts(purchases),
})

# Derived metrics
combined["Activation Rate"] = combined["Logins"] / combined["Signups"]
combined["Purchase Rate"] = combined["Purchases"] / combined["Logins"]

print(combined.describe())
```

## Visualization

### Matplotlib Basics

```python
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

df = ws.segmentation(event="Login", from_date="2025-01-01", to_date="2025-01-31").df

fig, ax = plt.subplots(figsize=(12, 6))
df.plot(ax=ax, title="Daily Logins")
ax.set_ylabel("Count")
ax.set_xlabel("Date")
plt.tight_layout()
plt.savefig("logins.png", dpi=150)
print("Saved: logins.png")
```

### Multi-Series Comparison

```python
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Trend
logins_df.plot(ax=axes[0, 0], title="Logins", legend=False)
# Breakdown
by_platform.plot(ax=axes[0, 1], title="By Platform")
# Rolling average
logins_df.rolling(7).mean().plot(ax=axes[1, 0], title="7-Day Average", legend=False)
# Cumulative
logins_df.cumsum().plot(ax=axes[1, 1], title="Cumulative", legend=False)

plt.tight_layout()
plt.savefig("dashboard.png", dpi=150)
```

### Funnel Bar Chart

```python
steps = ["Visit", "Sign Up", "Activate", "Subscribe"]
counts = [10000, 4500, 2700, 810]
rates = [100, 45, 27, 8.1]

fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.bar(steps, counts, color=["#4A90D9", "#5BA5E0", "#7FBCE8", "#A3D4F0"])
for bar, rate in zip(bars, rates):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 100,
            f"{rate}%", ha="center", fontweight="bold")
ax.set_title("Signup Funnel")
ax.set_ylabel("Users")
plt.tight_layout()
plt.savefig("funnel.png", dpi=150)
```

### Retention Curve

```python
import numpy as np

retention_pcts = [100, 42, 28, 22, 18, 16, 14, 13]
days = list(range(len(retention_pcts)))

fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(days, retention_pcts, "o-", linewidth=2, markersize=8, color="#4A90D9")
ax.fill_between(days, retention_pcts, alpha=0.1, color="#4A90D9")
ax.set_xlabel("Day")
ax.set_ylabel("Retention %")
ax.set_title("User Retention Curve")
ax.set_ylim(0, 105)
ax.axhline(y=20, color="red", linestyle="--", alpha=0.5, label="Target: 20%")
ax.legend()
plt.tight_layout()
plt.savefig("retention_curve.png", dpi=150)
```

## Streaming Data to DataFrames

```python
import pandas as pd
import mixpanel_data as mp

ws = mp.Workspace()

# Stream events into a DataFrame
events = list(ws.stream_events(
    from_date="2025-01-01", to_date="2025-01-02", event="Purchase"
))
df = pd.DataFrame([
    {"time": e.time, "user": e.distinct_id, **e.properties}
    for e in events
])
df["time"] = pd.to_datetime(df["time"], unit="s")

print(f"Streamed {len(df)} events")
print(df.describe())
```

## Export Patterns

```python
# CSV
df.to_csv("output.csv", index=True)

# Excel
df.to_excel("output.xlsx", sheet_name="Analysis")

# JSON
df.to_json("output.json", orient="records", indent=2, date_format="iso")

# Multiple sheets
with pd.ExcelWriter("report.xlsx") as writer:
    logins_df.to_excel(writer, sheet_name="Logins")
    signups_df.to_excel(writer, sheet_name="Signups")
    retention_df.to_excel(writer, sheet_name="Retention")
```

## Statistical Analysis

```python
# Correlation between events
combined = pd.DataFrame({
    "feature_use": feature_df[feature_df["segment"] == "total"].set_index("date")["count"],
    "purchases": purchase_df[purchase_df["segment"] == "total"].set_index("date")["count"],
})
print(f"Correlation: {combined.corr().iloc[0, 1]:.3f}")

# Percentile analysis via JQL
result = ws.jql("""function main() {
  return Events({from_date: "2025-01-01", to_date: "2025-01-31",
                 event_selectors: [{event: "Session"}]})
    .groupByUser(mixpanel.reducer.numeric_summary("properties.duration"))
    .map(u => ({user: u.key, ...u.value}))
}""")
df = result.df
print(df[["avg", "min", "max"]].describe())
```

## Tips

- Always use `matplotlib.use("Agg")` before importing `plt` — ensures non-interactive mode
- Use `df[df["segment"] == "total"].set_index("date")["count"]` to extract the count series from unsegmented segmentation results (long format: columns `date`, `segment`, `count`)
- Call `.sum()`, `.mean()`, `.describe()` on DataFrames for quick summaries
- Use `pd.to_datetime()` when working with streamed event timestamps
- Save visualizations to files (`plt.savefig()`) rather than trying to display them
