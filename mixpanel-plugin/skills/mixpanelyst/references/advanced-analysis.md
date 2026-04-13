# Advanced Analysis -- Statistical, ML, and Visualization Techniques

Advanced analytical methods using `mixpanel_data` results with pandas, numpy, scipy, scikit-learn, statsmodels, networkx, anytree, matplotlib, and seaborn.

---

## Statistical Methods

_These methods operate on DataFrames from any query engine. For applying them in multi-engine investigations, see [cross-query-synthesis.md](cross-query-synthesis.md) §Synthesis Patterns with pandas/numpy._

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

_For the retention API that produces these cohorts, see [retention-reference.md](retention-reference.md). For industry retention benchmarks to contextualize results, see [analytical-frameworks.md](analytical-frameworks.md) §Retention._

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

_These patterns extend the basic NetworkX integration in [flows-reference.md](flows-reference.md) §NetworkX Integration Patterns. The flow result's `.graph` property is the entry point._

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

_These patterns extend the basic anytree integration in [flows-reference.md](flows-reference.md) §anytree Integration Patterns. Use `result.anytree` to get converted trees._

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

_For multi-panel dashboards combining all four engines, see [cross-query-synthesis.md](cross-query-synthesis.md) §Multi-Engine Health Dashboard._

---

## Machine Learning with scikit-learn

_scikit-learn moves analytics from descriptive ("what happened") to predictive ("what will happen") and segmentation-driven ("what user groups exist"). These patterns operate on DataFrames from any query engine._

**Pre-flight: verify profile properties before building models.** The examples below assume properties like `logins_30d`, `purchases_30d`, and `features_used` exist on user profiles. These are typically set via scheduled scripts, computed properties, or backend `$set` calls. If your profiles lack behavioral counters, you can derive features from dates and metadata -- but check coverage first:

```python
# Audit profile property coverage before modeling
import itertools
sample = list(itertools.islice(ws.stream_profiles(), 100))
props_df = pd.DataFrame([p.get("properties", {}) for p in sample])

# Check desired features
for feat in ["logins_30d", "purchases_30d", "days_since_signup"]:
    if feat not in props_df.columns:
        print(f"  {feat}: MISSING — not set on any profile")
    else:
        coverage = props_df[feat].notna().mean()
        print(f"  {feat}: {coverage:.0%} coverage")

# If features are missing, derive from dates:
#   days_since_signup = (today - date_joined).days
#   days_since_last_login = (today - last_login).days
#   login_recency_ratio = days_since_last_login / days_since_signup
# Rule of thumb: features with <20% non-null coverage add noise, not signal.
```

### Behavioral Clustering — Automatic User Segmentation

Build user feature vectors from multiple queries, then cluster to discover natural segments. More objective than hand-defined cohorts.

```python
import mixpanel_data as mp
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

ws = mp.Workspace()

# Build user-level feature vectors from profile properties
profiles = []
for p in ws.stream_profiles():
    props = p.get("properties", {})
    profiles.append({
        "logins_30d": props.get("logins_30d", 0),
        "purchases_30d": props.get("purchases_30d", 0),
        "searches_30d": props.get("searches_30d", 0),
    })

features = pd.DataFrame(profiles).fillna(0)

# Normalize — different scales (logins vs purchases) would skew clustering
scaler = StandardScaler()
X = scaler.fit_transform(features)

# K-means with 4 clusters
kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
features["segment"] = kmeans.fit_predict(X)

# Profile each segment
for seg in sorted(features["segment"].unique()):
    group = features[features["segment"] == seg]
    print(f"\nSegment {seg} ({len(group):,} users):")
    print(f"  Avg logins:    {group['logins_30d'].mean():,.1f}")
    print(f"  Avg purchases: {group['purchases_30d'].mean():,.1f}")
    print(f"  Avg searches:  {group['searches_30d'].mean():,.1f}")

# Label segments based on their profiles
# NOTE: K-means cluster numbering is non-deterministic — cluster 0 will not
# reliably contain the same user type across runs. Always inspect each
# cluster's profile before assigning labels.
# After inspecting the profiles above, assign labels to match observed behavior:
segment_labels = {0: "Power Users", 1: "Browsers", 2: "Buyers", 3: "Dormant"}
features["label"] = features["segment"].map(segment_labels)
print(features["label"].value_counts())
# (Re-inspect and re-assign after every new fit)
```

**Choosing k**: Use the elbow method — plot inertia vs k and pick the bend.

```python
inertias = []
for k in range(2, 10):
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    km.fit(X)
    inertias.append(km.inertia_)

print("k | Inertia")
for k, inertia in zip(range(2, 10), inertias):
    print(f"{k} | {inertia:,.0f}")
```

### Anomaly Detection — Outlier Days and Users

Identify anomalous metric values using Isolation Forest (multivariate, handles non-normal distributions).

```python
import mixpanel_data as mp
import pandas as pd
from sklearn.ensemble import IsolationForest

ws = mp.Workspace()

# Daily metrics as features
dau = ws.query("Login", math="dau", last=180).df
signups = ws.query("Sign Up", math="unique", last=180).df
errors = ws.query("Error", math="total", last=180).df

daily = pd.DataFrame({
    "dau": dau.set_index("date")["count"],
    "signups": signups.set_index("date")["count"],
    "errors": errors.set_index("date")["count"],
}).fillna(0)
daily.index = pd.to_datetime(daily.index)

# Isolation Forest — detects multivariate outliers
iso = IsolationForest(contamination=0.05, random_state=42)
daily["anomaly"] = iso.fit_predict(daily[["dau", "signups", "errors"]])

# -1 = anomaly, 1 = normal
anomalies = daily[daily["anomaly"] == -1]
print(f"Detected {len(anomalies)} anomalous days out of {len(daily)}:")
for date, row in anomalies.iterrows():
    print(f"  {date.strftime('%Y-%m-%d')}: DAU={row['dau']:,.0f}, "
          f"Signups={row['signups']:,.0f}, Errors={row['errors']:,.0f}")
```

**Why Isolation Forest over z-scores?** Z-scores check one variable at a time. Isolation Forest catches days where the *combination* of metrics is unusual — e.g., normal DAU but abnormally high errors.

### Feature Importance — What Predicts Conversion?

Use Random Forest to rank which user properties most predict a target outcome (purchase, churn, activation).

```python
import mixpanel_data as mp
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score

ws = mp.Workspace()

# Stream user profiles with relevant properties
profiles = []
for p in ws.stream_profiles():
    props = p.get("properties", {})
    profiles.append({
        "logins_30d": props.get("logins_30d", 0),
        "searches_30d": props.get("searches_30d", 0),
        "days_since_signup": props.get("days_since_signup", 0),
        "platform": props.get("platform", "unknown"),
        "has_purchased": 1 if props.get("purchase_count", 0) > 0 else 0,
    })

df = pd.DataFrame(profiles)

# One-hot encode categorical features
df = pd.get_dummies(df, columns=["platform"], drop_first=True)

# Target: has_purchased
X = df.drop(columns=["has_purchased"])
y = df["has_purchased"]

# Train and extract feature importance
rf = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
rf.fit(X, y)

importance = pd.Series(rf.feature_importances_, index=X.columns).sort_values(ascending=False)
print("=== Feature Importance for Purchase Prediction ===")
for feat, imp in importance.head(10).items():
    bar = "#" * int(imp * 100)
    print(f"  {feat:25s} {imp:.3f} {bar}")

# Cross-validated accuracy (honest estimate — never report training accuracy alone)
cv_scores = cross_val_score(rf, X, y, cv=5, scoring="accuracy")
print(f"\nCV accuracy: {cv_scores.mean():.1%} +/- {cv_scores.std():.1%}")

# RED FLAG: near-perfect accuracy usually means leakage, not a great model.
if cv_scores.mean() > 0.95:
    print(f"\n⚠ CV accuracy {cv_scores.mean():.1%} is suspiciously high — investigate:")
    print("  - Does a feature encode the target? (e.g., purchase_count predicting has_purchased)")
    print("  - Are there complementary fields? (e.g., CRM lead vs contact status)")
    print("  - Is class imbalance inflating accuracy? Check AUC instead.")

# Cross-validated AUC (better than accuracy for imbalanced classes)
cv_auc = cross_val_score(rf, X, y, cv=5, scoring="roc_auc")
print(f"CV AUC: {cv_auc.mean():.3f} +/- {cv_auc.std():.3f}")
```

### Predictive Scoring — Churn Probability

Score each user's likelihood of churning using logistic regression.

```python
import mixpanel_data as mp
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ws = mp.Workspace()

# Build labeled dataset from user profiles
# KEY: features and label must cover DIFFERENT time windows to avoid
# target leakage. Use an observation window (e.g. days 31-60 ago) for
# features and a prediction window (last 30 days) for the churn label.
# If features and label share the same window, churned users have
# zero activity by definition — the model learns the labeling rule
# instead of genuine predictive patterns, inflating AUC.
profiles = []
for p in ws.stream_profiles():
    props = p.get("properties", {})
    profiles.append({
        "distinct_id": p["distinct_id"],
        # Observation-window features (days 31-60 ago)
        "logins_prev_month": props.get("logins_prev_month", 0),
        "purchases_prev_month": props.get("purchases_prev_month", 0),
        "feature_count": props.get("features_used", 0),
        # Prediction-window label (last 30 days)
        "churned": 1 if props.get("days_since_last_active", 999) > 30 else 0,
    })

df = pd.DataFrame(profiles)
feature_cols = ["logins_prev_month", "purchases_prev_month", "feature_count"]
X = df[feature_cols].fillna(0)
y = df["churned"]

# Cross-validate with pipeline (scaler inside each fold to prevent data leakage)
cv_pipeline = make_pipeline(StandardScaler(), LogisticRegression(random_state=42, max_iter=1000))
cv_scores = cross_val_score(cv_pipeline, X, y, cv=5, scoring="roc_auc")
print(f"Cross-validated AUC: {cv_scores.mean():.3f} +/- {cv_scores.std():.3f}")

# RED FLAG: AUC near 1.0 almost always means leakage, not a perfect model.
# Real-world churn models typically achieve AUC 0.65–0.80.
if cv_scores.mean() > 0.95:
    print(f"\n⚠ AUC={cv_scores.mean():.3f} is suspiciously high — investigate before trusting.")
    print("  Common causes: target leaked into features, complementary CRM fields,")
    print("  or observation/prediction windows overlap (see target leakage note above).")

# Train final model on full data and score all users
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)
lr = LogisticRegression(random_state=42, max_iter=1000)
lr.fit(X_scaled, y)
df["churn_probability"] = lr.predict_proba(X_scaled)[:, 1]

# Report risk tiers
print("\n=== Churn Risk Distribution ===")
bins = [0, 0.2, 0.5, 0.8, 1.0]
labels = ["Low", "Medium", "High", "Critical"]
df["risk_tier"] = pd.cut(df["churn_probability"], bins=bins, labels=labels, include_lowest=True)
print(df["risk_tier"].value_counts().sort_index())

# Coefficient interpretation
print("\n=== Feature Coefficients ===")
for feat, coef in zip(feature_cols, lr.coef_[0]):
    direction = "increases" if coef > 0 else "decreases"
    print(f"  {feat}: {coef:+.3f} ({direction} churn risk)")
```

### Dimensionality Reduction — Visualizing User Behavior Space

Use PCA or t-SNE to project high-dimensional behavior into 2D for visual exploration.

```python
import numpy as np
from sklearn.decomposition import PCA

# Assuming 'features' DataFrame and 'X' (scaled) from clustering section above
pca = PCA(n_components=2)
coords = pca.fit_transform(X)

print(f"Explained variance: PC1={pca.explained_variance_ratio_[0]:.1%}, "
      f"PC2={pca.explained_variance_ratio_[1]:.1%}, "
      f"Total={sum(pca.explained_variance_ratio_):.1%}")

# Scatter plot colored by cluster
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(10, 8))
scatter = ax.scatter(coords[:, 0], coords[:, 1], c=features["segment"],
                     cmap="viridis", alpha=0.5, s=10)
ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%} variance)")
ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%} variance)")
ax.set_title("User Behavior Space (PCA)")
plt.colorbar(scatter, label="Segment")
plt.tight_layout()
plt.savefig("user_behavior_pca.png", dpi=150)
print("Saved: user_behavior_pca.png")
```

---

## Time Series and Forecasting with statsmodels

_statsmodels adds proper time series modeling, forecasting, and regression diagnostics beyond what scipy provides. These patterns turn Mixpanel trends into forward-looking predictions._

**Data Preparation: Drop Today's Incomplete Data.** Queries using `last=N` include the current (incomplete) day. A half-finished day looks like a sudden crash to time-series models -- ARIMA forecasts a decline, decomposition shows a false anomaly, and regression slopes get pulled toward zero. Always drop today before modeling:

```python
import datetime
today = pd.Timestamp(datetime.date.today())
counts = counts[counts.index < today]
```

The examples below assume you have already excluded the current day.

### Time Series Decomposition (Trend + Seasonality + Residual)

Replaces hand-rolled decomposition with a proper statistical method. Handles multiplicative and additive seasonal patterns.

```python
import mixpanel_data as mp
import pandas as pd
from statsmodels.tsa.seasonal import seasonal_decompose

ws = mp.Workspace()

dau = ws.query("Login", math="dau", last=180).df
counts = dau.set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)
counts = counts.asfreq("D", method="ffill")  # ensure regular frequency

# Decompose: period=7 for weekly seasonality
decomposition = seasonal_decompose(counts, model="additive", period=7)

print("=== Time Series Decomposition ===")
print(f"Trend range: {decomposition.trend.min():,.0f} - {decomposition.trend.max():,.0f}")
print(f"Seasonal amplitude: {decomposition.seasonal.max() - decomposition.seasonal.min():,.0f}")
print(f"Residual std: {decomposition.resid.std():,.0f}")

# Is the trend actually declining, or is it just seasonal?
trend = decomposition.trend.dropna()
slope = (trend.iloc[-1] - trend.iloc[0]) / len(trend)
print(f"Trend direction: {slope:+.1f}/day ({'declining' if slope < 0 else 'growing'})")

# Visualization
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig = decomposition.plot()
fig.set_size_inches(14, 10)
plt.suptitle("DAU Decomposition (180 days)")
plt.tight_layout()
plt.savefig("dau_decomposition.png", dpi=150)
print("Saved: dau_decomposition.png")
```

### Forecasting with ARIMA / SARIMAX

Daily product metrics almost always have weekly seasonality (weekday/weekend patterns). Use SARIMAX as the default; fall back to plain ARIMA only if decomposition confirms no seasonal pattern.

```python
import mixpanel_data as mp
import pandas as pd
import numpy as np
import warnings
from statsmodels.tsa.statespace.sarimax import SARIMAX

ws = mp.Workspace()

dau = ws.query("Login", math="dau", last=90).df
counts = dau.set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)
counts = counts.asfreq("D", method="ffill")

# Drop today's incomplete data (see Data Preparation note above)
import datetime
today = pd.Timestamp(datetime.date.today())
counts = counts[counts.index < today]

# SARIMAX with weekly seasonality — the right default for daily metrics
model = SARIMAX(counts, order=(1, 1, 1), seasonal_order=(1, 1, 1, 7))
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=UserWarning, module="statsmodels")
    fitted = model.fit(disp=False)

# Forecast 14 days ahead
forecast = fitted.get_forecast(steps=14)
fc_mean = forecast.predicted_mean
fc_ci = forecast.conf_int(alpha=0.05)

# Non-negative metrics cannot go below zero — clip forecasts
fc_mean = fc_mean.clip(lower=0)
fc_ci = fc_ci.clip(lower=0)

print("=== 14-Day DAU Forecast (SARIMAX) ===")
print(f"Current DAU (last 7d avg): {counts.tail(7).mean():,.0f}")
print(f"Forecast DAU (next 7d avg): {fc_mean.head(7).mean():,.0f}")
print(f"Forecast DAU (next 14d avg): {fc_mean.mean():,.0f}")
print("\nDay-by-day forecast:")
for date, mean in fc_mean.items():
    ci_low = fc_ci.loc[date].iloc[0]
    ci_high = fc_ci.loc[date].iloc[1]
    print(f"  {date.strftime('%Y-%m-%d')}: {mean:,.0f} (95% CI: [{ci_low:,.0f}, {ci_high:,.0f}])")

# Model diagnostics
print(f"\nModel AIC: {fitted.aic:.1f}")
print(f"Model BIC: {fitted.bic:.1f}")

# Is this forecast actionable? If the CI is wider than the forecast,
# the prediction is too uncertain to act on — report that honestly.
avg_ci_width = (fc_ci.iloc[:, 1] - fc_ci.iloc[:, 0]).mean()
if avg_ci_width > fc_mean.mean():
    print(f"\n⚠ Average CI width ({avg_ci_width:,.0f}) exceeds forecast mean ({fc_mean.mean():,.0f}).")
    print("  This forecast is too uncertain to be actionable. Consider:")
    print("  - More historical data (last=180 instead of last=90)")
    print("  - Shorter forecast horizon (7 days instead of 14)")
    print("  - The metric may be too volatile to forecast reliably.")
```

**Non-seasonal alternative**: If decomposition shows no weekly pattern, use plain ARIMA. Do not assume (1,1,1) is a universal default -- treat it as a starting point.

```python
from statsmodels.tsa.arima.model import ARIMA

# Plain ARIMA — only when data has no seasonal pattern
model = ARIMA(counts, order=(1, 1, 1))
fitted = model.fit()
forecast = fitted.get_forecast(steps=14)
# Still clip for non-negative metrics:
fc_mean = forecast.predicted_mean.clip(lower=0)
```

### OLS Regression with Full Diagnostics

scipy gives p-values; statsmodels gives the full regression table with R-squared, confidence intervals, and diagnostic tests.

```python
import mixpanel_data as mp
import pandas as pd
import numpy as np
import statsmodels.api as sm

ws = mp.Workspace()

# Question: "Does search usage predict purchase revenue?"
searches = ws.query("Search", math="unique", last=90).df
revenue = ws.query("Purchase", math="total", math_property="revenue", last=90).df

daily = pd.DataFrame({
    "searches": searches.set_index("date")["count"],
    "revenue": revenue.set_index("date")["count"],
}).dropna()

# OLS with constant (intercept)
X = sm.add_constant(daily["searches"])
model = sm.OLS(daily["revenue"], X).fit()

# Full regression summary
print(model.summary())
# Key outputs:
#   R-squared: how much variance in revenue is explained by searches
#   coef (searches): revenue change per additional search
#   P>|t|: statistical significance
#   [0.025, 0.975]: 95% confidence interval for coefficient

# Actionable interpretation
coef = model.params["searches"]
p_val = model.pvalues["searches"]
r2 = model.rsquared
print("\n=== Interpretation ===")
print(f"Each additional daily searcher is associated with ${coef:,.2f} in revenue")
print(f"Search volume explains {r2:.1%} of revenue variance")
print(f"Relationship is {'statistically significant' if p_val < 0.05 else 'not significant'} (p={p_val:.4f})")
```

**When diagnostics flag issues.** If Durbin-Watson is well below 2.0 or Ljung-Box is significant, the regression may be **spurious** -- both variables share a common cycle (e.g., weekday/weekend), creating a false relationship. The R² looks impressive but is inflated.

Before trusting the result, try first-differencing to remove shared trends:

```python
# Remedy: regress daily *changes* instead of levels
daily_diff = daily.diff().dropna()
X_diff = sm.add_constant(daily_diff["searches"])
model_diff = sm.OLS(daily_diff["revenue"], X_diff).fit()

print(f"First-differenced R²: {model_diff.rsquared:.3f}")
print(f"First-differenced DW: {sm.stats.stattools.durbin_watson(model_diff.resid):.3f}")
# If R² drops sharply (e.g., 0.95 → 0.05), the original relationship
# was likely spurious — driven by shared trends, not a real connection.
# A modest R² with healthy diagnostics is more trustworthy than a
# high R² with autocorrelated residuals.
```

### Multiple Regression — Multi-Factor Analysis

Test multiple predictors simultaneously to identify which factors independently drive a metric.

```python
import mixpanel_data as mp
import pandas as pd
import statsmodels.api as sm

ws = mp.Workspace()
period = dict(last=90)

# Gather daily metrics
daily = pd.DataFrame({
    "signups": ws.query("Sign Up", math="unique", **period).df.set_index("date")["count"],
    "searches": ws.query("Search", math="unique", **period).df.set_index("date")["count"],
    "support_tickets": ws.query("Submit Ticket", math="total", **period).df.set_index("date")["count"],
    "revenue": ws.query("Purchase", math="total", math_property="revenue", **period).df.set_index("date")["count"],
}).dropna()

# Revenue as dependent, others as independent
X = sm.add_constant(daily[["signups", "searches", "support_tickets"]])
model = sm.OLS(daily["revenue"], X).fit()

print("=== Revenue Drivers (Multiple Regression) ===")
for var in ["signups", "searches", "support_tickets"]:
    coef = model.params[var]
    p = model.pvalues[var]
    sig = "*" if p < 0.05 else " "
    print(f"  {var:20s}: coef={coef:>10,.2f}, p={p:.4f} {sig}")
print(f"  R-squared: {model.rsquared:.3f} (adjusted: {model.rsquared_adj:.3f})")
print(f"  F-statistic p-value: {model.f_pvalue:.4f}")
```

**Check for multicollinearity with VIF.** When predictors are correlated (e.g., signups and searches both track overall traffic), coefficients become unreliable even if R² looks good.

```python
from statsmodels.stats.outliers_influence import variance_inflation_factor

# VIF for each predictor (exclude the constant)
X_check = daily[["signups", "searches", "support_tickets"]]
for i, col in enumerate(X_check.columns):
    vif = variance_inflation_factor(X_check.values, i)
    flag = " — WARNING: too high, coefficients unreliable" if vif > 10 else ""
    print(f"  {col:20s}: VIF={vif:.1f}{flag}")

# VIF > 10 means predictors share too much variance. Options:
#   1. Drop one of the correlated predictors
#   2. Combine them (e.g., signups + searches → "traffic index")
#   3. Use PCA to extract orthogonal components
#   4. If you only care about R² (prediction), not coefficients
#      (explanation), high VIF doesn't matter
# NOTE: Daily product metrics almost always have high VIF because
# they share weekday/weekend patterns. This is expected, not a bug.
```

### Granger Causality — Does Event A Cause Metric B to Change?

Test whether one time series helps predict another (beyond just correlation).

```python
import mixpanel_data as mp
import pandas as pd
import warnings
from statsmodels.tsa.stattools import grangercausalitytests

ws = mp.Workspace()

# Does a marketing campaign Granger-cause signups?
campaigns = ws.query("Campaign Impression", math="total", last=90).df
signups = ws.query("Sign Up", math="unique", last=90).df

daily = pd.DataFrame({
    "campaigns": campaigns.set_index("date")["count"],
    "signups": signups.set_index("date")["count"],
}).dropna()

# Test up to 7-day lags
print("=== Granger Causality: Campaign Impressions → Signups ===")
with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    results = grangercausalitytests(daily[["signups", "campaigns"]], maxlag=7, verbose=False)
for lag, result in results.items():
    f_stat = result[0]["ssr_ftest"][0]
    p_value = result[0]["ssr_ftest"][1]
    sig = "***" if p_value < 0.01 else "**" if p_value < 0.05 else "*" if p_value < 0.1 else ""
    print(f"  Lag {lag}d: F={f_stat:.2f}, p={p_value:.4f} {sig}")
```

### Retention Curve Modeling — Half-Life and Decay Projection

Model retention as a decay problem: "how quickly do users churn?" Fits aggregate retention rates to estimate half-life and project long-term retention.

```python
import mixpanel_data as mp
import pandas as pd
import numpy as np

ws = mp.Workspace()

# Get retention data
retention = ws.query_retention(
    "Sign Up", "Login",
    retention_unit="day",
    bucket_sizes=[1, 3, 7, 14, 30, 60, 90],
    last=180,
)

# Build survival data from retention rates
avg_rates = retention.average.get("rates", [])
buckets = [1, 3, 7, 14, 30, 60, 90][:len(avg_rates)]

# Convert retention rates to survival times
# Each rate represents P(survived to day d)
survival_df = pd.DataFrame({
    "day": buckets,
    "retention_rate": avg_rates,
    "churned_rate": [1 - r for r in avg_rates],
})

print("=== Retention as Survival Function ===")
for _, row in survival_df.iterrows():
    bar = "#" * int(row["retention_rate"] * 50)
    print(f"  Day {row['day']:>3d}: {row['retention_rate']:.1%} surviving {bar}")

# Half-life: when does retention cross 50%?
for i in range(len(avg_rates) - 1):
    if avg_rates[i] >= 0.5 > avg_rates[i + 1]:
        # Linear interpolation
        d1, d2 = buckets[i], buckets[i + 1]
        r1, r2 = avg_rates[i], avg_rates[i + 1]
        half_life = d1 + (0.5 - r1) / (r2 - r1) * (d2 - d1)
        print(f"\nHalf-life: ~{half_life:.0f} days (50% of users churn by this point)")
        break
else:
    if avg_rates[-1] >= 0.5:
        print(f"\nHalf-life: >{buckets[-1]} days (retention still above 50%)")
    else:
        print(f"\nHalf-life: <{buckets[0]} day(s)")

# Retention curve fit — shifted exponential: a*exp(-b*t) + c
# 'c' captures the "retained core" — users who stick around indefinitely.
# Pure exponential (c=0) forces retention toward zero, which almost never
# matches real product data. The shifted form typically fits dramatically
# better (e.g., R²=0.99 vs R²=0.95 for pure exponential).
from scipy.optimize import curve_fit

def shifted_exp_decay(t, a, b, c):
    """Shifted exponential: decays toward c (the retained core), not zero."""
    return a * np.exp(-b * np.array(t)) + c

try:
    popt, pcov = curve_fit(shifted_exp_decay, buckets, avg_rates,
                           p0=[0.5, 0.05, 0.05], maxfev=5000)
    a, b, c = popt
    print(f"\nShifted exponential: retention = {a:.2f} * exp(-{b:.4f} * t) + {c:.2f}")
    print(f"  Retained core (long-term floor): {c:.1%}")
    if b > 0:
        print(f"  Decay half-life: {np.log(2)/b:.0f} days (for the non-core portion)")

    # Goodness of fit
    predicted = shifted_exp_decay(np.array(buckets), *popt)
    ss_res = np.sum((np.array(avg_rates) - predicted) ** 2)
    ss_tot = np.sum((np.array(avg_rates) - np.mean(avg_rates)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    print(f"  R²: {r_squared:.4f}")

    projected_days = [120, 180, 365]
    for d in projected_days:
        projected_rate = shifted_exp_decay(d, *popt)
        print(f"  Projected D{d}: {projected_rate:.1%}")

except RuntimeError:
    print("\nShifted exponential did not converge — try pure exponential (less accurate):")
    def pure_exp_decay(t, a, b):
        return a * np.exp(-b * np.array(t))
    try:
        popt, _ = curve_fit(pure_exp_decay, buckets, avg_rates, p0=[1.0, 0.01], maxfev=5000)
        a, b = popt
        print(f"  retention = {a:.2f} * exp(-{b:.4f} * t)")
        print(f"  NOTE: pure exponential assumes retention decays to zero.")
        print(f"  If your retention plateaus above zero, projections will underestimate.")
        for d in [120, 180, 365]:
            print(f"  Projected D{d}: {pure_exp_decay(d, *popt):.1%}")
    except RuntimeError:
        print("  Neither model converged — retention may not follow exponential decay")
```

### Retention Curve Comparison Between Segments

Compare retention curves between segments and test for statistical significance.

**Pre-flight: verify the segmenting property has enough diversity.** If the property you're splitting on (e.g., `utm_medium`) has only one value, or one segment has near-zero users, the comparison is meaningless -- it will produce trivially significant results. Always check first:

```python
# Verify segment property has meaningful diversity before comparing
values = ws.property_values("utm_medium", event="Sign Up")
if len(values) < 2:
    print(f"WARNING: property has only {len(values)} value(s): {values}")
    print("Cannot perform meaningful segment comparison — try a different property.")
elif len(values) == 2:
    print(f"Two segments found: {values} — proceeding with comparison.")
else:
    print(f"{len(values)} segments found: {values[:5]}... — pick the two most relevant.")
```

```python
import mixpanel_data as mp
from mixpanel_data import Filter
import pandas as pd
import numpy as np
from scipy.stats import mannwhitneyu

ws = mp.Workspace()

# Compare organic vs paid user retention
# Use RetentionEvent with per-event filters on the born event only.
# A global where= filter would require utm_medium on both Sign Up AND
# Login events — but attribution properties typically exist only on
# signup, so Login events would be filtered out, producing artificially
# low or empty retention curves.
from mixpanel_data import RetentionEvent

organic = ws.query_retention(
    RetentionEvent("Sign Up", filters=[Filter.equals("utm_medium", "organic")]),
    "Login",
    retention_unit="day",
    bucket_sizes=[1, 7, 14, 30, 60],
    last=180,
)
paid = ws.query_retention(
    RetentionEvent("Sign Up", filters=[Filter.equals("utm_medium", "cpc")]),
    "Login",
    retention_unit="day",
    bucket_sizes=[1, 7, 14, 30, 60],
    last=180,
)

organic_rates = organic.average.get("rates", [])
paid_rates = paid.average.get("rates", [])
buckets = [1, 7, 14, 30, 60]
n = min(len(organic_rates), len(paid_rates), len(buckets))

comparison = pd.DataFrame({
    "day": buckets[:n],
    "organic": organic_rates[:n],
    "paid": paid_rates[:n],
})
comparison["lift"] = (comparison["organic"] - comparison["paid"]) / comparison["paid"]

print("=== Retention: Organic vs Paid ===")
print(comparison.to_string(
    index=False,
    formatters={
        "organic": lambda x: f"{x:.1%}",
        "paid": lambda x: f"{x:.1%}",
        "lift": lambda x: f"{x:+.1%}",
    },
))

# NOTE: Rough directional comparison only. Retention rates across buckets
# are NOT independent (D30 survivors ⊂ D7 survivors). For rigorous testing,
# compare a single bucket (e.g. D30) across multiple independent cohorts.
if len(organic_rates) >= 3 and len(paid_rates) >= 3:
    stat, p = mannwhitneyu(organic_rates, paid_rates, alternative="greater")
    print(f"\nOrganic > Paid? Mann-Whitney p={p:.4f}")
    print("Significant" if p < 0.05 else "Not significant")
```

---

## Tips and Gotchas

- **Always `matplotlib.use("Agg")`**: Set before `import matplotlib.pyplot`. Required for non-interactive environments (scripts, agents, CI).
- **`plt.savefig()` not `plt.show()`**: Save to files. `show()` blocks or fails in headless environments.
- **`plt.tight_layout()`**: Call before `savefig()` to prevent label clipping.
- **`plt.close(fig)`**: Close figures after saving to free memory, especially in loops.
- **scikit-learn requires numeric input**: Use `pd.get_dummies()` for categorical features. Always `StandardScaler()` before scale-sensitive methods (K-means, PCA, logistic regression).
- **statsmodels requires regular time indices**: Use `counts.asfreq("D", method="ffill")` before time series methods.
- **ARIMA convergence**: If ARIMA fails to converge, try a simpler order (0,1,1) or increase `maxiter`. Scope warning suppression with `warnings.catch_warnings()` — never use global `filterwarnings("ignore")`.
- **Feature importance is correlation, not causation**: Random Forest importance shows predictive power, not causal relationships. Use Granger causality or domain knowledge for causal claims.
- **Cross-validate predictions**: Never report model accuracy on training data alone. Use `cross_val_score()` for honest estimates.
- **Drop today before time-series modeling**: `last=N` includes the current incomplete day. A half-finished day looks like a sudden drop, poisoning forecasts and trend estimates. Always filter to `counts[counts.index < today]` before fitting models.
- **Suspect perfect scores**: AUC=1.0 or accuracy=100% almost always indicates data leakage or a trivial relationship (e.g., complementary CRM fields), not a great model. An AUC of 0.65-0.80 is typical for real-world churn/conversion models. Investigate before celebrating.
- **Retention decays to a floor, not zero**: Pure exponential decay `a*exp(-b*t)` assumes all users eventually churn. Real products have a "retained core." Use `a*exp(-b*t)+c` (shifted exponential) -- the `c` parameter estimates the long-term retention floor.
- **scipy is optional**: Statistical functions require `pip install scipy`. Check availability before using.
- **seaborn is optional**: Heatmaps and styled plots require `pip install seaborn`.
- **anytree is optional**: Tree rendering and export require `pip install anytree`.
- **networkx is optional**: Graph analysis requires `pip install networkx`.
- **scikit-learn is optional**: ML methods require `pip install scikit-learn`.
- **statsmodels is optional**: Forecasting and regression require `pip install statsmodels`.
- **Frozen results**: Query results are immutable. Cache in variables; do not re-query to re-access data.
- **Date indexing**: Always convert date columns with `pd.to_datetime()` before time-series operations.
- **Retention rates are floats 0-1**: Multiply by 100 for percentage display.
