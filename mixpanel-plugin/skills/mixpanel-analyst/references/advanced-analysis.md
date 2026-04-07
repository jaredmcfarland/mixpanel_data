# Advanced Analysis -- Statistical, Graph, and Visualization Techniques

Advanced analytical methods using `mixpanel_data` results with pandas, numpy, scipy, networkx, anytree, matplotlib, and seaborn.

---

## Statistical Methods

### t-test for Comparing Means Across Periods

Use when comparing a continuous metric (DAU, revenue, session duration) between two time periods.

```python
import mixpanel_data as mp
import pandas as pd
from scipy.stats import ttest_ind

ws = mp.Workspace()

before = ws.query("Login", math="dau", from_date="2025-01-01", to_date="2025-01-31").df
after = ws.query("Login", math="dau", from_date="2025-02-01", to_date="2025-02-28").df

before_vals = before["count"].values
after_vals = after["count"].values

t_stat, p_value = ttest_ind(before_vals, after_vals)

print(f"Before: mean={before_vals.mean():,.0f}, std={before_vals.std():,.0f}, n={len(before_vals)}")
print(f"After:  mean={after_vals.mean():,.0f}, std={after_vals.std():,.0f}, n={len(after_vals)}")
print(f"t-statistic: {t_stat:.3f}")
print(f"p-value: {p_value:.4f}")
print(f"Result: {'Significant' if p_value < 0.05 else 'Not significant'} at alpha=0.05")
```

### Chi-Squared for Comparing Proportions (Conversion Rates)

Use when comparing conversion rates or other proportions between groups.

```python
import numpy as np
from scipy.stats import chi2_contingency

# Funnel results for two periods
funnel_before = ws.query_funnel(["Signup", "Purchase"], from_date="2025-01-01", to_date="2025-01-31")
funnel_after = ws.query_funnel(["Signup", "Purchase"], from_date="2025-02-01", to_date="2025-02-28")

# Build contingency table: [[converted, not_converted], [converted, not_converted]]
before_entered = int(funnel_before.df.iloc[0]["count"])
before_converted = int(funnel_before.df.iloc[-1]["count"])
after_entered = int(funnel_after.df.iloc[0]["count"])
after_converted = int(funnel_after.df.iloc[-1]["count"])

observed = np.array([
    [before_converted, before_entered - before_converted],
    [after_converted, after_entered - after_converted],
])

chi2, p, dof, expected = chi2_contingency(observed)

print(f"Before: {before_converted}/{before_entered} = {before_converted/before_entered:.1%}")
print(f"After:  {after_converted}/{after_entered} = {after_converted/after_entered:.1%}")
print(f"Chi-squared: {chi2:.3f}, p={p:.4f}, dof={dof}")
print(f"Result: {'Significant' if p < 0.05 else 'Not significant'}")
```

### Mann-Whitney U for Non-Normal Distributions

Use when data is skewed (revenue, session duration) and normality cannot be assumed.

```python
from scipy.stats import mannwhitneyu

# Compare session durations between two user segments
sessions_mobile = ws.query(
    "Session End", math="average", math_property="duration",
    where=Filter.equals("platform", "iOS"), last=30,
).df["count"].values

sessions_web = ws.query(
    "Session End", math="average", math_property="duration",
    where=Filter.equals("platform", "Web"), last=30,
).df["count"].values

stat, p = mannwhitneyu(sessions_mobile, sessions_web, alternative="two-sided")
print(f"Mobile median: {np.median(sessions_mobile):,.1f}")
print(f"Web median: {np.median(sessions_web):,.1f}")
print(f"Mann-Whitney U: {stat:.0f}, p={p:.4f}")
```

### Confidence Intervals on Metrics

```python
import numpy as np
from scipy.stats import norm, t as t_dist

def confidence_interval(data, confidence=0.95):
    """Calculate CI using t-distribution (appropriate for small samples)."""
    n = len(data)
    mean = np.mean(data)
    se = np.std(data, ddof=1) / np.sqrt(n)
    t_crit = t_dist.ppf((1 + confidence) / 2, df=n - 1)
    margin = t_crit * se
    return mean, mean - margin, mean + margin

dau = ws.query("Login", math="dau", last=30).df["count"].values
mean, ci_low, ci_high = confidence_interval(dau)
print(f"DAU: {mean:,.0f} (95% CI: [{ci_low:,.0f}, {ci_high:,.0f}])")

revenue = ws.query("Purchase", math="total", math_property="revenue", last=30).df["count"].values
mean, ci_low, ci_high = confidence_interval(revenue)
print(f"Daily Revenue: ${mean:,.2f} (95% CI: [${ci_low:,.2f}, ${ci_high:,.2f}])")
```

### Effect Size (Cohen's d)

Quantifies the magnitude of difference between two groups, independent of sample size.

```python
import numpy as np

def cohens_d(group1, group2):
    """Calculate Cohen's d effect size."""
    n1, n2 = len(group1), len(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    pooled_std = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    if pooled_std == 0:
        return 0.0
    return (np.mean(group1) - np.mean(group2)) / pooled_std

# DAU before vs after a product change
before = ws.query("Login", math="dau", from_date="2025-01-01", to_date="2025-01-31").df["count"].values
after = ws.query("Login", math="dau", from_date="2025-02-01", to_date="2025-02-28").df["count"].values

d = cohens_d(after, before)
print(f"Cohen's d: {d:.3f}")
# Interpretation: |d| < 0.2 = negligible, 0.2-0.5 = small, 0.5-0.8 = medium, > 0.8 = large
magnitude = "negligible" if abs(d) < 0.2 else "small" if abs(d) < 0.5 else "medium" if abs(d) < 0.8 else "large"
print(f"Effect size: {magnitude}")
```

### Sample Size Validation

Before drawing conclusions, verify that sample sizes are adequate.

```python
import numpy as np
from scipy.stats import norm

def min_sample_size(baseline_rate, mde, alpha=0.05, power=0.8):
    """Minimum sample size per group for a two-proportion z-test.

    Args:
        baseline_rate: Current conversion rate (e.g. 0.10 for 10%).
        mde: Minimum detectable effect as relative change (e.g. 0.10 for 10% lift).
        alpha: Significance level.
        power: Statistical power.

    Returns:
        Required sample size per group.
    """
    p1 = baseline_rate
    p2 = baseline_rate * (1 + mde)
    p_avg = (p1 + p2) / 2

    z_alpha = norm.ppf(1 - alpha / 2)
    z_beta = norm.ppf(power)

    n = (
        (z_alpha * np.sqrt(2 * p_avg * (1 - p_avg))
         + z_beta * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
        / (p2 - p1) ** 2
    )
    return int(np.ceil(n))

# Example: 5% baseline conversion, detect 20% relative lift
n = min_sample_size(0.05, 0.20)
print(f"Need {n:,} users per group to detect 20% lift on 5% conversion (alpha=0.05, power=0.80)")

# Check current sample against requirement
funnel = ws.query_funnel(["Signup", "Purchase"], last=30)
actual_n = int(funnel.df.iloc[0]["count"])
print(f"Current sample: {actual_n:,} ({'sufficient' if actual_n >= n else 'INSUFFICIENT'})")
```

---

## Trend Analysis

### Linear Regression

```python
import numpy as np
import pandas as pd

dau = ws.query("Login", math="dau", last=90).df
counts = dau.set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)

x = np.arange(len(counts))
slope, intercept = np.polyfit(x, counts.values, 1)

print(f"Daily trend: {slope:+.1f} users/day")
print(f"Weekly trend: {slope * 7:+.1f} users/week")
print(f"Monthly trend: {slope * 30:+.1f} users/month")
print(f"Projected in 30 days: {intercept + slope * (len(x) + 30):,.0f}")

# R-squared
predicted = slope * x + intercept
ss_res = np.sum((counts.values - predicted) ** 2)
ss_tot = np.sum((counts.values - counts.values.mean()) ** 2)
r_squared = 1 - (ss_res / ss_tot)
print(f"R-squared: {r_squared:.3f}")
```

### Changepoint Detection

Identify when a trend changed direction.

```python
import numpy as np
import pandas as pd

def detect_changepoints(series, min_segment=7):
    """Detect changepoints using cumulative sum (CUSUM) method.

    Args:
        series: pandas Series of values.
        min_segment: Minimum days between changepoints.

    Returns:
        List of (date, direction) tuples.
    """
    values = series.values
    mean = values.mean()
    cusum = np.cumsum(values - mean)

    changepoints = []
    prev_idx = 0

    for i in range(min_segment, len(cusum) - min_segment):
        window_before = cusum[max(0, i - min_segment):i]
        window_after = cusum[i:min(len(cusum), i + min_segment)]

        if len(window_before) > 0 and len(window_after) > 0:
            diff = np.mean(window_after) - np.mean(window_before)
            if abs(diff) > 2 * np.std(cusum) and (i - prev_idx) >= min_segment:
                direction = "up" if diff > 0 else "down"
                changepoints.append((series.index[i], direction))
                prev_idx = i

    return changepoints

dau = ws.query("Login", math="dau", last=180).df
counts = dau.set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)

cps = detect_changepoints(counts)
print("Detected changepoints:")
for date, direction in cps:
    print(f"  {date.strftime('%Y-%m-%d')}: trend shifted {direction}")
```

### Seasonality Decomposition

```python
import pandas as pd
import numpy as np

dau = ws.query("Login", math="dau", last=90).df
counts = dau.set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)

# Day-of-week seasonality
dow_avg = counts.groupby(counts.index.dayofweek).mean()
dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
print("Day-of-week pattern:")
for i, name in enumerate(dow_names):
    pct_of_avg = dow_avg.iloc[i] / counts.mean() * 100
    bar = "#" * int(pct_of_avg / 5)
    print(f"  {name}: {dow_avg.iloc[i]:>8,.0f} ({pct_of_avg:>5.1f}%) {bar}")

# Decompose: trend + seasonal + residual
trend = counts.rolling(7, center=True).mean()
detrended = counts - trend
seasonal = detrended.groupby(detrended.index.dayofweek).transform("mean")
residual = counts - trend - seasonal

print(f"\nResidual std: {residual.std():,.0f} (noise level)")
print(f"Seasonal amplitude: {seasonal.max() - seasonal.min():,.0f}")
print(f"Trend range: {trend.max() - trend.min():,.0f}")
```

### Moving Average Smoothing

```python
import pandas as pd

dau = ws.query("Login", math="dau", last=90).df
counts = dau.set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)

smoothed = pd.DataFrame({
    "raw": counts,
    "7d_sma": counts.rolling(7).mean(),
    "14d_sma": counts.rolling(14).mean(),
    "7d_ema": counts.ewm(span=7).mean(),
})

print("=== Latest 7 Days ===")
print(smoothed.tail(7).round(0).to_string())

# Week-over-week change using smoothed data
wow = smoothed["7d_sma"].pct_change(7) * 100
print(f"\nWoW change (smoothed): {wow.iloc[-1]:+.1f}%")
```

---

## Cohort Analysis with pandas

### Cohort Pivot Table from RetentionQueryResult

```python
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()

result = ws.query_retention(
    "Sign Up", "Login",
    retention_unit="week",
    last=90,
)

# Pivot: rows = cohort_date, columns = bucket (week number), values = rate
df = result.df
pivot = df.pivot_table(index="cohort_date", columns="bucket", values="rate")
pivot.columns = [f"W{int(c)}" for c in pivot.columns]

print("=== Retention by Cohort (Weekly) ===")
print(pivot.map(lambda x: f"{x:.0%}" if pd.notna(x) else "").to_string())
```

### Retention Heatmap with Seaborn

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

result = ws.query_retention("Sign Up", "Login", retention_unit="week", last=90)
df = result.df

pivot = df.pivot_table(index="cohort_date", columns="bucket", values="rate")
pivot.columns = [f"W{int(c)}" for c in pivot.columns]

fig, ax = plt.subplots(figsize=(14, 8))
sns.heatmap(
    pivot,
    annot=True,
    fmt=".0%",
    cmap="YlGnBu",
    vmin=0, vmax=1,
    linewidths=0.5,
    ax=ax,
)
ax.set_title("Weekly Retention by Cohort")
ax.set_ylabel("Cohort (Signup Week)")
ax.set_xlabel("Weeks Since Signup")
plt.tight_layout()
plt.savefig("retention_heatmap.png", dpi=150)
print("Saved: retention_heatmap.png")
```

### Cohort-Based LTV Estimation

```python
import mixpanel_data as mp
import pandas as pd
import numpy as np

ws = mp.Workspace()

# Get retention curve (average across cohorts)
retention = ws.query_retention(
    "Sign Up", "Purchase",
    retention_unit="week",
    last=180,
)
avg_rates = retention.average.get("rates", [])

# Get average revenue per purchase
arpu = ws.query(
    "Purchase", math="total", per_user="average",
    math_property="revenue", last=180,
).df["count"].mean()

# Estimate LTV as cumulative retained revenue
weeks = list(range(len(avg_rates)))
cumulative_revenue = [arpu * sum(avg_rates[:w+1]) for w in weeks]

ltv_df = pd.DataFrame({
    "week": weeks,
    "retention_rate": avg_rates,
    "cumulative_ltv": cumulative_revenue,
})

print("=== LTV Estimation by Week ===")
print(ltv_df.to_string(index=False))
print(f"\nEstimated {len(weeks)}-week LTV: ${cumulative_revenue[-1]:,.2f}")
print(f"ARPU: ${arpu:,.2f}")
```

### Behavioral Cohort Comparison

```python
import mixpanel_data as mp
from mixpanel_data import Filter
import pandas as pd

ws = mp.Workspace()

# Define behavioral cohorts
cohorts = {
    "Power Users": Filter.greater_than("event_count_30d", 50),
    "Regular Users": Filter.between("event_count_30d", 10, 50),
    "Light Users": Filter.less_than("event_count_30d", 10),
}

# Compare retention for each cohort
retention_data = {}
for name, filter_condition in cohorts.items():
    result = ws.query_retention(
        "Sign Up", "Login",
        retention_unit="week",
        where=filter_condition,
        last=90,
    )
    rates = result.average.get("rates", [])
    retention_data[name] = rates

# Build comparison table
max_len = max(len(r) for r in retention_data.values())
comparison = pd.DataFrame({
    name: rates + [None] * (max_len - len(rates))
    for name, rates in retention_data.items()
}, index=[f"W{i}" for i in range(max_len)])

print("=== Retention by Behavioral Cohort ===")
print(comparison.map(lambda x: f"{x:.0%}" if pd.notna(x) else "").to_string())
```

---

## Graph Analysis with NetworkX (Beyond Basics)

These patterns build on the flow graph from `result.graph` (see flows-reference.md for fundamentals).

### Subgraph Extraction: Conversion vs Churn Paths

```python
import networkx as nx
import mixpanel_data as mp

ws = mp.Workspace()
result = ws.query_flow("Login", forward=5, cardinality=20)
G = result.graph

# Find all nodes on any path to Purchase
target_nodes = [n for n in G.nodes() if G.nodes[n].get("event") == "Purchase"]
conversion_nodes = set()
for target in target_nodes:
    conversion_nodes |= nx.ancestors(G, target) | {target}

# Conversion subgraph: all nodes/edges on paths to Purchase
conv_subgraph = G.subgraph(conversion_nodes).copy()

# Churn subgraph: nodes that never reach Purchase
churn_nodes = set(G.nodes()) - conversion_nodes
churn_subgraph = G.subgraph(churn_nodes).copy()

print(f"Conversion paths: {conv_subgraph.number_of_nodes()} nodes, "
      f"{conv_subgraph.number_of_edges()} edges")
print(f"Churn paths: {churn_subgraph.number_of_nodes()} nodes, "
      f"{churn_subgraph.number_of_edges()} edges")

# Compare traffic distribution
conv_traffic = sum(d.get("count", 0) for _, d in conv_subgraph.nodes(data=True))
churn_traffic = sum(d.get("count", 0) for _, d in churn_subgraph.nodes(data=True))
print(f"Traffic: conversion={conv_traffic:,}, churn={churn_traffic:,}")
```

### Graph Comparison: Before/After a Change

```python
import networkx as nx
import mixpanel_data as mp

ws = mp.Workspace()

before = ws.query_flow("Login", forward=3, from_date="2025-01-01", to_date="2025-01-31", cardinality=15)
after = ws.query_flow("Login", forward=3, from_date="2025-02-01", to_date="2025-02-28", cardinality=15)

G_before = before.graph
G_after = after.graph

# Nodes that appeared/disappeared
new_nodes = set(G_after.nodes()) - set(G_before.nodes())
lost_nodes = set(G_before.nodes()) - set(G_after.nodes())
common_nodes = set(G_before.nodes()) & set(G_after.nodes())

print(f"New nodes: {len(new_nodes)}")
for n in new_nodes:
    print(f"  + {n}: {G_after.nodes[n].get('count', 0):,}")

print(f"\nLost nodes: {len(lost_nodes)}")
for n in lost_nodes:
    print(f"  - {n}: {G_before.nodes[n].get('count', 0):,}")

# Traffic changes on common nodes
print(f"\nBiggest traffic changes:")
changes = []
for n in common_nodes:
    before_count = G_before.nodes[n].get("count", 0)
    after_count = G_after.nodes[n].get("count", 0)
    if before_count > 0:
        pct_change = (after_count - before_count) / before_count * 100
        changes.append((n, before_count, after_count, pct_change))

for n, bc, ac, pct in sorted(changes, key=lambda x: abs(x[3]), reverse=True)[:10]:
    print(f"  {n}: {bc:,} -> {ac:,} ({pct:+.1f}%)")
```

### Path Enumeration with Filtering

```python
import networkx as nx

result = ws.query_flow("Login", forward=5, cardinality=20)
G = result.graph

# All paths from Login to Purchase, max 6 steps
source = "Login@0"
targets = [n for n in G.nodes() if G.nodes[n].get("event") == "Purchase"]

all_paths = []
for target in targets:
    try:
        paths = list(nx.all_simple_paths(G, source, target, cutoff=6))
        all_paths.extend(paths)
    except nx.NodeNotFound:
        pass

# Rank by minimum edge weight (bottleneck throughput)
def path_throughput(G, path):
    if len(path) < 2:
        return 0
    return min(G.edges[path[i], path[i+1]].get("count", 0) for i in range(len(path) - 1))

ranked = sorted(all_paths, key=lambda p: path_throughput(G, p), reverse=True)
print(f"Found {len(ranked)} paths to Purchase:")
for i, path in enumerate(ranked[:10]):
    events = [G.nodes[n].get("event", n) for n in path]
    throughput = path_throughput(G, path)
    print(f"  {i+1}. {' -> '.join(events)} (bottleneck: {throughput:,})")
```

### Weighted Graph Metrics

```python
import networkx as nx
import numpy as np

result = ws.query_flow("Login", forward=5, cardinality=15)
G = result.graph

# Weighted in-degree / out-degree (by edge count)
weighted_in = {n: sum(G.edges[u, n].get("count", 0) for u in G.predecessors(n)) for n in G.nodes()}
weighted_out = {n: sum(G.edges[n, v].get("count", 0) for v in G.successors(n)) for n in G.nodes()}

# Net flow: positive = more traffic arriving, negative = more traffic leaving
net_flow = {n: weighted_in.get(n, 0) - weighted_out.get(n, 0) for n in G.nodes()}

# Biggest sinks (where traffic accumulates)
print("Traffic sinks (endpoints):")
for n, flow in sorted(net_flow.items(), key=lambda x: x[1], reverse=True)[:5]:
    print(f"  {n}: net_in={flow:,}")

# Biggest sources
print("\nTraffic sources:")
for n, flow in sorted(net_flow.items(), key=lambda x: x[1])[:5]:
    print(f"  {n}: net_out={abs(flow):,}")
```

---

## Tree Analysis with anytree

These patterns build on the anytree integration in flows-reference.md.

### Multi-Tree Comparison (Different Segments)

```python
import mixpanel_data as mp
from mixpanel_data import FlowStep, Filter
from anytree import RenderTree, findall

ws = mp.Workspace()

# Compare flow trees for two segments
mobile_flow = ws.query_flow(
    FlowStep("Login", forward=3, filters=[Filter.equals("platform", "iOS")]),
    mode="tree", last=90, cardinality=10,
)
web_flow = ws.query_flow(
    FlowStep("Login", forward=3, filters=[Filter.equals("platform", "Web")]),
    mode="tree", last=90, cardinality=10,
)

def tree_summary(trees, label):
    print(f"\n=== {label} ===")
    for tree in trees:
        print(f"Root: {tree.event} ({tree.total_count:,} users)")
        print(f"  Depth: {tree.depth}, Nodes: {tree.node_count}, Leaves: {tree.leaf_count}")
        paths = tree.all_paths()
        if paths:
            best = max(paths, key=lambda p: p[-1].total_count)
            print(f"  Top path: {' -> '.join(n.event for n in best)} ({best[-1].total_count:,})")

tree_summary(mobile_flow.trees, "Mobile")
tree_summary(web_flow.trees, "Web")

# Compare branching at first step
def first_step_branches(trees):
    branches = {}
    for tree in trees:
        for child in tree.children:
            pct = child.total_count / tree.total_count * 100 if tree.total_count else 0
            branches[child.event] = pct
    return branches

mobile_branches = first_step_branches(mobile_flow.trees)
web_branches = first_step_branches(web_flow.trees)

import pandas as pd
comparison = pd.DataFrame({
    "mobile_%": pd.Series(mobile_branches),
    "web_%": pd.Series(web_branches),
}).fillna(0)
comparison["diff"] = comparison["mobile_%"] - comparison["web_%"]
print("\n=== First Step Branches ===")
print(comparison.sort_values("diff", ascending=False).round(1))
```

### Pruning Strategies

Remove low-traffic branches to focus on significant paths.

```python
from anytree import RenderTree

result = ws.query_flow("Login", forward=4, mode="tree", cardinality=20)

def prune_tree(node, min_count=100, min_rate=0.01):
    """Recursively filter tree nodes below thresholds.

    Args:
        node: FlowTreeNode root.
        min_count: Minimum total_count to keep a node.
        min_rate: Minimum fraction of parent traffic to keep.

    Returns:
        Pruned anytree node, or None if pruned.
    """
    from anytree import AnyNode

    pruned_root = AnyNode(
        event=node.event,
        total_count=node.total_count,
        type=node.type,
        conversion_rate=node.conversion_rate,
    )
    for child in node.children:
        child_rate = child.total_count / node.total_count if node.total_count else 0
        if child.total_count >= min_count and child_rate >= min_rate:
            child_pruned = prune_tree(child, min_count, min_rate)
            if child_pruned is not None:
                child_pruned.parent = pruned_root

    return pruned_root

for tree in result.trees:
    pruned = prune_tree(tree, min_count=50, min_rate=0.05)
    print(f"\n=== Pruned Tree (min_count=50, min_rate=5%) ===")
    for pre, fill, node in RenderTree(pruned):
        print(f"{pre}{node.event} ({node.total_count:,})")
```

### Tree-Based Conversion Optimization

Find where intervention would yield the highest uplift.

```python
result = ws.query_flow("Login", forward=4, mode="tree", cardinality=15)

def opportunity_score(node):
    """Score = traffic * drop_off_rate. High score = high-impact optimization target."""
    return node.total_count * node.drop_off_rate

for tree in result.trees:
    all_nodes = tree.flatten()
    scored = [(n, opportunity_score(n)) for n in all_nodes if n.drop_off_count > 0]
    scored.sort(key=lambda x: x[1], reverse=True)

    print("=== Optimization Opportunities (traffic x drop-off rate) ===")
    for node, score in scored[:10]:
        print(f"  {node.event} (step {node.step_number}): "
              f"score={score:,.0f} "
              f"({node.total_count:,} users, {node.drop_off_rate:.0%} drop-off)")
```

### Graphviz Rendering Customization

```python
from anytree.exporter import UniqueDotExporter

result = ws.query_flow("Login", forward=3, mode="tree", cardinality=10)

for i, root in enumerate(result.anytree):
    def node_label(node):
        rate = node.converted_count / node.total_count if node.total_count else 0
        color_map = {
            "ANCHOR": "#4A90D9",
            "NORMAL": "#7FBCE8",
            "FORWARD": "#7FBCE8",
            "DROPOFF": "#FF6B6B",
            "PRUNED": "#CCCCCC",
        }
        color = color_map.get(node.type, "#EEEEEE")
        return (
            f'label="{node.event}\\n'
            f'{node.total_count:,} users\\n'
            f'conv: {rate:.0%}"'
            f', style=filled'
            f', fillcolor="{color}"'
            f', fontsize=10'
        )

    def edge_label(parent, child):
        pct = child.total_count / parent.total_count * 100 if parent.total_count else 0
        return f'label="{pct:.0f}%", fontsize=8'

    UniqueDotExporter(
        root,
        nodeattrfunc=node_label,
        edgeattrfunc=edge_label,
    ).to_dotfile(f"flow_tree_{i}.dot")
    print(f"Saved: flow_tree_{i}.dot")
    # Convert to image: dot -Tpng flow_tree_0.dot -o flow_tree_0.png
```

---

## Visualization Patterns

### Setup (Required)

```python
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend -- always set before importing pyplot
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
```

### Insights: Time Series with Trend Line

```python
import mixpanel_data as mp

ws = mp.Workspace()
result = ws.query("Login", math="dau", last=90)
df = result.df
counts = df.set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)

fig, ax = plt.subplots(figsize=(14, 6))

# Raw data + smoothed
ax.plot(counts.index, counts.values, alpha=0.3, color="#4A90D9", label="Daily")
ax.plot(counts.index, counts.rolling(7).mean(), color="#4A90D9", linewidth=2, label="7-day avg")

# Linear trend
x = np.arange(len(counts))
slope, intercept = np.polyfit(x, counts.values, 1)
ax.plot(counts.index, slope * x + intercept, "--", color="#FF6B6B", label=f"Trend ({slope:+.0f}/day)")

ax.set_title("Daily Active Users (90 days)")
ax.set_ylabel("DAU")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("dau_trend.png", dpi=150)
print("Saved: dau_trend.png")
```

### Funnel: Step Bar Chart with Drop-Off Annotations

```python
import mixpanel_data as mp

ws = mp.Workspace()
funnel = ws.query_funnel(["Visit", "Sign Up", "Activate", "Purchase"], last=90)
fdf = funnel.df

fig, ax = plt.subplots(figsize=(10, 6))
colors = ["#4A90D9", "#5BA5E0", "#7FBCE8", "#A3D4F0"]
bars = ax.bar(fdf["event"], fdf["count"], color=colors[:len(fdf)])

# Annotate with conversion rates
for i, (bar, row) in enumerate(zip(bars, fdf.itertuples())):
    ax.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + max(fdf["count"]) * 0.02,
        f"{row.overall_conv_ratio:.1%}",
        ha="center", fontweight="bold", fontsize=11,
    )
    if i > 0:
        ax.annotate(
            f"{row.step_conv_ratio:.0%}",
            xy=(bar.get_x(), bar.get_height()),
            xytext=(bar.get_x() - 0.15, bar.get_height() + max(fdf["count"]) * 0.06),
            arrowprops=dict(arrowstyle="->", color="#FF6B6B"),
            color="#FF6B6B", fontsize=9,
        )

ax.set_title("Conversion Funnel")
ax.set_ylabel("Users")
plt.tight_layout()
plt.savefig("funnel_chart.png", dpi=150)
print("Saved: funnel_chart.png")
```

### Retention: Curve with Benchmark

```python
import mixpanel_data as mp

ws = mp.Workspace()
result = ws.query_retention("Sign Up", "Login", retention_unit="day", bucket_sizes=[1, 3, 7, 14, 30], last=90)
avg_rates = result.average.get("rates", [])
buckets = [1, 3, 7, 14, 30][:len(avg_rates)]

# Industry benchmark (SaaS B2B)
benchmarks = {1: 0.70, 3: 0.55, 7: 0.45, 14: 0.38, 30: 0.35}

fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(buckets, [r * 100 for r in avg_rates], "o-", linewidth=2, markersize=8,
        color="#4A90D9", label="Your Product")
ax.plot(list(benchmarks.keys()), [v * 100 for v in benchmarks.values()], "s--",
        linewidth=1.5, markersize=6, color="#AAAAAA", label="SaaS Benchmark")

ax.fill_between(buckets, [r * 100 for r in avg_rates], alpha=0.1, color="#4A90D9")
ax.set_xlabel("Days Since Signup")
ax.set_ylabel("Retention %")
ax.set_title("Retention Curve vs Benchmark")
ax.set_ylim(0, 100)
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("retention_curve.png", dpi=150)
print("Saved: retention_curve.png")
```

### Multi-Panel Dashboard

```python
import mixpanel_data as mp
from concurrent.futures import ThreadPoolExecutor

ws = mp.Workspace()

# Parallel queries
def get_dau():
    return ws.query("Login", math="dau", last=30).df

def get_signups():
    return ws.query("Sign Up", math="unique", last=30).df

def get_revenue():
    return ws.query("Purchase", math="total", math_property="revenue", last=30).df

def get_funnel():
    return ws.query_funnel(["Signup", "Purchase"], last=30)

with ThreadPoolExecutor(max_workers=4) as pool:
    f_dau = pool.submit(get_dau)
    f_signups = pool.submit(get_signups)
    f_revenue = pool.submit(get_revenue)
    f_funnel = pool.submit(get_funnel)

dau_df = f_dau.result()
signups_df = f_signups.result()
revenue_df = f_revenue.result()
funnel_result = f_funnel.result()

fig, axes = plt.subplots(2, 2, figsize=(16, 10))

# Panel 1: DAU
ax = axes[0, 0]
counts = dau_df.set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)
ax.plot(counts.index, counts.values, color="#4A90D9")
ax.fill_between(counts.index, counts.values, alpha=0.1, color="#4A90D9")
ax.set_title(f"DAU (avg: {counts.mean():,.0f})")
ax.grid(True, alpha=0.3)

# Panel 2: Signups
ax = axes[0, 1]
s_counts = signups_df.set_index("date")["count"]
s_counts.index = pd.to_datetime(s_counts.index)
ax.bar(s_counts.index, s_counts.values, color="#5BA5E0", alpha=0.7)
ax.set_title(f"Daily Signups (total: {s_counts.sum():,.0f})")
ax.grid(True, alpha=0.3)

# Panel 3: Revenue
ax = axes[1, 0]
r_counts = revenue_df.set_index("date")["count"]
r_counts.index = pd.to_datetime(r_counts.index)
ax.plot(r_counts.index, r_counts.values, color="#2ECC71")
ax.fill_between(r_counts.index, r_counts.values, alpha=0.1, color="#2ECC71")
ax.set_title(f"Daily Revenue (total: ${r_counts.sum():,.0f})")
ax.grid(True, alpha=0.3)

# Panel 4: Funnel
ax = axes[1, 1]
fdf = funnel_result.df
ax.barh(fdf["event"][::-1], fdf["count"][::-1], color=["#A3D4F0", "#4A90D9"])
for i, row in fdf[::-1].iterrows():
    ax.text(row["count"] + max(fdf["count"]) * 0.02, i, f"{row['overall_conv_ratio']:.1%}", va="center")
ax.set_title(f"Funnel ({funnel_result.overall_conversion_rate:.1%} overall)")

plt.suptitle("Product Dashboard", fontsize=16, fontweight="bold")
plt.tight_layout()
plt.savefig("dashboard.png", dpi=150)
print("Saved: dashboard.png")
```

### Annotated Chart with Inflection Points

```python
import mixpanel_data as mp
import numpy as np

ws = mp.Workspace()

dau = ws.query("Login", math="dau", last=90).df
counts = dau.set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)

# Detect anomalies
rolling_mean = counts.rolling(7).mean()
rolling_std = counts.rolling(7).std()
z_scores = (counts - rolling_mean) / rolling_std
anomalies = counts[z_scores.abs() > 2]

fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(counts.index, counts.values, alpha=0.4, color="#4A90D9")
ax.plot(counts.index, rolling_mean.values, color="#4A90D9", linewidth=2, label="7-day avg")

# Annotate anomalies
for date, value in anomalies.items():
    z = z_scores[date]
    color = "#FF6B6B" if z < 0 else "#2ECC71"
    label = "dip" if z < 0 else "spike"
    ax.annotate(
        f"{label}\n{value:,.0f}",
        xy=(date, value),
        xytext=(0, 20 if z > 0 else -30),
        textcoords="offset points",
        ha="center",
        fontsize=8,
        color=color,
        arrowprops=dict(arrowstyle="->", color=color),
    )
    ax.scatter([date], [value], color=color, s=60, zorder=5)

ax.set_title("DAU with Anomaly Detection")
ax.set_ylabel("DAU")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("dau_annotated.png", dpi=150)
print("Saved: dau_annotated.png")
```

### Export Patterns

```python
# PNG (default for charts)
plt.savefig("chart.png", dpi=150, bbox_inches="tight")

# SVG (vector, scalable)
plt.savefig("chart.svg", format="svg", bbox_inches="tight")

# PDF (publication quality)
plt.savefig("chart.pdf", format="pdf", bbox_inches="tight")

# High-DPI for presentations
plt.savefig("chart_hd.png", dpi=300, bbox_inches="tight")

# Multiple charts to multi-page PDF
from matplotlib.backends.backend_pdf import PdfPages
with PdfPages("report.pdf") as pdf:
    for fig in [fig1, fig2, fig3]:
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)
print("Saved: report.pdf")
```

---

## Tips and Gotchas

- **Always `matplotlib.use("Agg")`**: Set before `import matplotlib.pyplot`. Required for non-interactive environments (scripts, agents, CI).
- **`plt.savefig()` not `plt.show()`**: Save to files. `show()` blocks or fails in headless environments.
- **`plt.tight_layout()`**: Call before `savefig()` to prevent label clipping.
- **`plt.close(fig)`**: Close figures after saving to free memory, especially in loops.
- **scipy is optional**: Statistical functions require `pip install scipy`. Check availability before using.
- **seaborn is optional**: Heatmaps and styled plots require `pip install seaborn`.
- **anytree is optional**: Tree rendering and export require `pip install anytree`.
- **networkx is optional**: Graph analysis requires `pip install networkx`.
- **Frozen results**: Query results are immutable. Cache in variables; do not re-query to re-access data.
- **Date indexing**: Always convert date columns with `pd.to_datetime()` before time-series operations.
- **Retention rates are floats 0-1**: Multiply by 100 for percentage display.
