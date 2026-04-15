# Cross-Query Synthesis -- Multi-Engine Analysis Playbook

How to combine results from `query()`, `query_funnel()`, `query_retention()`, and `query_flow()` to answer questions no single engine can. Each engine reveals one facet of user behavior; joining them produces compound insights.

_This playbook implements the decomposition patterns from [query-taxonomy.md](query-taxonomy.md) using the strategic frameworks from [analytical-frameworks.md](analytical-frameworks.md). For per-engine parameter details, see the individual engine references._

## Engine Quick Reference

| Engine | Method | Returns | Best for |
|--------|--------|---------|----------|
| Insights | `ws.query()` | `QueryResult` | Trends, volumes, breakdowns, formulas |
| Funnels | `ws.query_funnel()` | `FunnelQueryResult` | Sequential conversion, step timing |
| Retention | `ws.query_retention()` | `RetentionQueryResult` | Cohort return rates over time |
| Flows | `ws.query_flow()` | `FlowQueryResult` | User paths, branching, graph analysis |

All results expose `.df` (DataFrame) and `.params` (bookmark JSON for persistence).

---

## Join Strategy 1: Time-Aligned Join

**Use when**: Two metrics share the same date range and you want to correlate daily/weekly trends.

**Join key**: `date` column.

```python
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()
period = dict(from_date="2025-01-01", to_date="2025-03-31")

# Two insights queries over the same period
signups = ws.query("Sign Up", math="unique", **period).df
purchases = ws.query("Purchase", math="unique", **period).df

# Extract count series indexed by date
def to_series(df, name):
    s = df.set_index("date")["count"]
    s.index = pd.to_datetime(s.index)
    s.name = name
    return s

combined = pd.DataFrame({
    "signups": to_series(signups, "signups"),
    "purchases": to_series(purchases, "purchases"),
})
combined["conversion_rate"] = combined["purchases"] / combined["signups"]
combined["7d_conv_avg"] = combined["conversion_rate"].rolling(7).mean()

print(combined.describe())
print(f"\nCorrelation: {combined['signups'].corr(combined['purchases']):.3f}")
```

---

## Join Strategy 2: Segment-Aligned Join

**Use when**: Two metrics share the same `group_by` dimension and you want to compare across segments.

**Join key**: segment column (the `event` column in grouped results, or the group_by property value).

```python
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()
period = dict(from_date="2025-01-01", to_date="2025-03-31")

# Insights: purchases by platform
purchases_by_platform = ws.query(
    "Purchase", math="unique", group_by="platform", **period,
).df
purchase_totals = purchases_by_platform.groupby("event")["count"].sum()

# Retention: retention by platform
retention_by_platform = ws.query_retention(
    "Sign Up", "Login", group_by="platform", last=90,
)
# Average retention rate per segment
ret_avg = {}
for segment, avg_data in retention_by_platform.segment_averages.items():
    rates = avg_data.get("rates", [])
    ret_avg[segment] = rates[7] if len(rates) > 7 else (rates[-1] if rates else 0.0)

# Join on platform
combined = pd.DataFrame({
    "purchases": purchase_totals,
    "d7_retention": pd.Series(ret_avg),
}).dropna()

print("Platform comparison:")
print(combined.sort_values("purchases", ascending=False))
print(f"\nCorrelation (purchases vs retention): {combined['purchases'].corr(combined['d7_retention']):.3f}")
```

---

## Join Strategy 3: Funnel-Flow Complement

_(→ [funnels-reference.md](funnels-reference.md) for FunnelStep/Exclusion details | [flows-reference.md](flows-reference.md) for FlowStep/NetworkX/anytree)_

**Use when**: Funnels tell you THAT users drop off; flows tell you WHERE they go instead.

**Principle**: Funnels quantify the conversion rate at each step. Flows reveal the specific events users do instead of converting.

```python
import mixpanel_data as mp
from mixpanel_data import FlowStep

ws = mp.Workspace()

# Step 1: Funnel shows drop-off rates
funnel = ws.query_funnel(
    ["Sign Up", "Add to Cart", "Checkout", "Purchase"],
    conversion_window=7,
    last=90,
)
print("=== Funnel Drop-Off ===")
for _, row in funnel.df.iterrows():
    print(f"  Step {int(row['step'])}: {row['event']:20s} "
          f"count={int(row['count']):>6,} "
          f"step_conv={row['step_conv_ratio']:.1%} "
          f"overall={row['overall_conv_ratio']:.1%}")

# Step 2: Find the worst drop-off step
worst_step_idx = funnel.df["step_conv_ratio"].idxmin()
worst_event = funnel.df.loc[worst_step_idx, "event"]
print(f"\nWorst drop-off at: {worst_event}")

# Step 3: Flow from the worst step to see WHERE users go instead
flow = ws.query_flow(
    FlowStep(worst_event, forward=3, reverse=0),
    last=90,
    cardinality=15,
)
print(f"\n=== Where users go after {worst_event} (instead of converting) ===")
for src, tgt, count in flow.top_transitions(n=10):
    print(f"  {src} -> {tgt}: {count:,}")

# Step 4: Identify specific alternative paths
for step, info in flow.drop_off_summary().items():
    if info["rate"] > 0.2:
        print(f"\n  {step}: {info['rate']:.0%} drop-off ({info['dropoff']:,} users)")
```

---

## Join Strategy 4: Insights-Retention Correlation

_(→ [retention-reference.md](retention-reference.md) §Analysis Patterns for retention-specific patterns | [analytical-frameworks.md](analytical-frameworks.md) §Retention for industry benchmarks)_

**Use when**: You want to test whether a specific behavior predicts better retention.

**Principle**: Segment users by behavior (using insights), then compare retention curves across segments.

```python
import mixpanel_data as mp
from mixpanel_data import Filter

ws = mp.Workspace()

# Hypothesis: "Users who Search within 7 days of signup retain better"

# Retention for users who searched (born + filter)
from mixpanel_data import RetentionEvent
searchers = ws.query_retention(
    RetentionEvent("Sign Up"),
    RetentionEvent("Login"),
    retention_unit="day",
    bucket_sizes=[1, 3, 7, 14, 30],
    where=Filter.is_set("first_search_date"),
    last=90,
)

# Retention for all users (baseline)
baseline = ws.query_retention(
    "Sign Up", "Login",
    retention_unit="day",
    bucket_sizes=[1, 3, 7, 14, 30],
    last=90,
)

# Compare retention curves
import pandas as pd

searcher_rates = searchers.average.get("rates", [])
baseline_rates = baseline.average.get("rates", [])
buckets = [1, 3, 7, 14, 30]

comparison = pd.DataFrame({
    "bucket": buckets[:len(searcher_rates)],
    "searchers": searcher_rates[:len(buckets)],
    "baseline": baseline_rates[:len(buckets)],
})
comparison["lift"] = (comparison["searchers"] - comparison["baseline"]) / comparison["baseline"] * 100

print("=== Retention: Searchers vs Baseline ===")
print(comparison.to_string(index=False))

# Statistical test
if len(searcher_rates) >= 2 and len(baseline_rates) >= 2:
    from scipy.stats import mannwhitneyu
    stat, p = mannwhitneyu(searcher_rates, baseline_rates, alternative="greater")
    print(f"\nMann-Whitney U: stat={stat:.2f}, p={p:.4f}")
    print("Significant" if p < 0.05 else "Not significant")
```

---

## Join Strategy 5: Multi-Engine Health Dashboard

**Use when**: You need a parallel snapshot of product health across all engines.

**Principle**: Run all queries concurrently with `ThreadPoolExecutor`, then compose a unified view.

```python
import mixpanel_data as mp
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

ws = mp.Workspace()

def run_insights():
    dau = ws.query("Login", math="dau", last=30).df
    revenue = ws.query("Purchase", math="total", math_property="revenue", last=30).df
    return {
        "avg_dau": dau["count"].mean(),
        "total_revenue": revenue["count"].sum(),
    }

def run_funnel():
    result = ws.query_funnel(
        ["Sign Up", "Add to Cart", "Purchase"],
        conversion_window=7, last=30,
    )
    return {
        "funnel_conversion": result.overall_conversion_rate,
        "funnel_steps": result.df.to_dict("records"),
    }

def run_retention():
    result = ws.query_retention("Sign Up", "Login", retention_unit="day", last=30)
    rates = result.average.get("rates", [])
    return {
        "d1_retention": rates[1] if len(rates) > 1 else None,
        "d7_retention": rates[7] if len(rates) > 7 else None,
    }

def run_flows():
    result = ws.query_flow("Sign Up", forward=3, last=30)
    return {
        "flow_conversion": result.overall_conversion_rate,
        "top_path": result.top_transitions(n=1),
    }

# Run all four engines in parallel
queries = {
    "insights": run_insights,
    "funnel": run_funnel,
    "retention": run_retention,
    "flows": run_flows,
}

results = {}
with ThreadPoolExecutor(max_workers=4) as pool:
    futures = {pool.submit(fn): name for name, fn in queries.items()}
    for future in as_completed(futures):
        name = futures[future]
        try:
            results[name] = future.result()
        except Exception as e:
            results[name] = {"error": str(e)}

# Compose dashboard
print("=" * 50)
print("PRODUCT HEALTH DASHBOARD")
print("=" * 50)
ins = results.get("insights", {})
fun = results.get("funnel", {})
ret = results.get("retention", {})
flo = results.get("flows", {})

print(f"  Avg DAU:           {ins.get('avg_dau', 'N/A'):>12,.0f}")
print(f"  Total Revenue:    ${ins.get('total_revenue', 0):>11,.2f}")
print(f"  Funnel Conv:       {fun.get('funnel_conversion', 0):>11.1%}")
print(f"  D1 Retention:      {ret.get('d1_retention', 0):>11.1%}")
print(f"  D7 Retention:      {ret.get('d7_retention', 0):>11.1%}")
print(f"  Flow Conv:         {flo.get('flow_conversion', 0):>11.1%}")
print("=" * 50)
```

---

## Join Strategy 6: Cohort-Aligned Cross-Engine Analysis

**Use when**: You want to understand how a specific user cohort behaves differently across all four engines.

**Principle**: Define the cohort filter once, pass it to all engines via `where=Filter.in_cohort()`, then compare cohort behavior to the overall population. For engines that support it, use `CohortBreakdown` to get in-vs-out segmentation in a single query.

```python
import mixpanel_data as mp
from mixpanel_data import Filter, CohortBreakdown, CohortMetric, Metric
from concurrent.futures import ThreadPoolExecutor

ws = mp.Workspace()
cohort_id = 123
cohort_name = "Power Users"
cohort_filter = Filter.in_cohort(cohort_id, cohort_name)

queries = {
    # Insights: engagement breakdown (in vs out)
    "engagement": lambda: ws.query(
        "Login", math="dau",
        group_by=CohortBreakdown(cohort_id, cohort_name),
        last=30,
    ),
    # Funnels: conversion comparison (in vs out)
    "funnel": lambda: ws.query_funnel(
        ["Signup", "Activate", "Purchase"],
        group_by=CohortBreakdown(cohort_id, cohort_name),
        last=30,
    ),
    # Retention: retention comparison (in vs out)
    "retention": lambda: ws.query_retention(
        "Signup", "Login",
        group_by=CohortBreakdown(cohort_id, cohort_name),
        retention_unit="week", last=90,
    ),
    # Flows: path analysis (filter only — CohortBreakdown not supported)
    "flow": lambda: ws.query_flow(
        "Purchase", forward=0, reverse=3,
        where=cohort_filter, last=30,
    ),
    # Cohort size trend
    "size": lambda: ws.query(
        [Metric("Login", math="unique"), CohortMetric(cohort_id, cohort_name)],
        formula="(B / A) * 100", formula_label="Power User %",
        last=90,
    ),
}

with ThreadPoolExecutor(max_workers=5) as pool:
    futures = {name: pool.submit(fn) for name, fn in queries.items()}
    results = {name: future.result() for name, future in futures.items()}
```

**Unique insight**: CohortBreakdown produces in-vs-out comparison in a single query for 3 engines. Flows requires a separate cohort-filtered query. CohortMetric tracks the cohort's share of total users over time.

---

## Join Strategy 7: Period-over-Period Cross-Engine

**Use when**: Comparing current vs previous period across multiple engines.

**Join key**: `TimeComparison` applied consistently across engines.

```python
import mixpanel_data as mp
from mixpanel_data import TimeComparison

ws = mp.Workspace()
tc = TimeComparison.relative("month")

# Same comparison period across all engines
signups = ws.query("Signup", math="unique", time_comparison=tc, last=30)
funnel = ws.query_funnel(["Signup", "Purchase"], time_comparison=tc, last=30)
retention = ws.query_retention("Signup", "Login", time_comparison=tc, last=30)

# Each result now includes comparison period data
# Analyze trends, conversion, and retention changes together
```

Use `TimeComparison.relative("week")` for WoW analysis, `"month"` for MoM, `"quarter"` for QoQ. All three engines return comparison data in the same response.

---

## Join Strategy 8: Profile Enrichment Join

**Use when**: You have identified interesting users via a behavioral engine (insights, funnels, retention, flows) and want to understand WHO they are -- their demographics, plan, company size, or other profile attributes.

**Principle**: Behavioral identification (event engines) followed by profile extraction (Users engine) followed by demographic analysis (pandas). This is the canonical cross-engine pattern for `query_user()`.

**Join key**: `distinct_id` (implicit -- cohort definition or distinct_id list bridges engines).

```python
import mixpanel_data as mp
from mixpanel_data import Filter, CohortDefinition, CohortCriteria
import pandas as pd

ws = mp.Workspace()

# Step 1: Identify interesting users via behavioral engine
# e.g., find users who purchased but did not return (retention analysis)
retention = ws.query_retention("Purchase", "Purchase", retention_unit="week", last=90)
# Inspect retention.average to understand repeat purchase rates

# Step 2: Profile those users with query_user
profiles = ws.query_user(
    cohort=CohortDefinition.all_of(
        CohortCriteria.did_event("Purchase", within_days=90),
    ),
    properties=["$email", "plan", "company_size", "signup_source"],
    limit=1000,
)

# Step 3: Analyze demographics of the behavioral cohort
print(profiles.df.groupby("plan").size())
print(profiles.df.groupby("company_size").agg({"distinct_id": "count"}))

# Step 4: Compare segments
by_source = profiles.df.groupby("signup_source").agg(
    users=("distinct_id", "count"),
    top_plan=("plan", lambda x: x.mode().iloc[0] if len(x) > 0 else "unknown"),
)
print(by_source.sort_values("users", ascending=False))
```

**Unique insight**: Event engines tell you WHAT users did. `query_user()` tells you WHO they are. Combining both answers "what kind of people do X?" -- the foundation for targeting, personalization, and demographic analysis.

---

## Synthesis Patterns with pandas/numpy

### Correlation Analysis Across Query Results

```python
import pandas as pd
import numpy as np

# Align multiple daily metrics on date
metrics = {
    "dau": ws.query("Login", math="dau", last=90).df,
    "signups": ws.query("Sign Up", math="unique", last=90).df,
    "purchases": ws.query("Purchase", math="unique", last=90).df,
    "support_tickets": ws.query("Submit Ticket", math="total", last=90).df,
}

combined = pd.DataFrame({
    name: df.set_index("date")["count"]
    for name, df in metrics.items()
})
combined.index = pd.to_datetime(combined.index)

# Correlation matrix
corr = combined.corr()
print("=== Correlation Matrix ===")
print(corr.round(3))

# Strongest correlations (off-diagonal)
import itertools
pairs = list(itertools.combinations(combined.columns, 2))
for a, b in sorted(pairs, key=lambda p: abs(corr.loc[p[0], p[1]]), reverse=True):
    r = corr.loc[a, b]
    print(f"  {a} <-> {b}: r={r:.3f}")
```

### Statistical Significance Testing

_(→ [advanced-analysis.md](advanced-analysis.md) §Statistical Methods for complete treatment: t-tests, chi-squared, Mann-Whitney U, confidence intervals, effect sizes, sample size validation)_

```python
from scipy.stats import ttest_ind, chi2_contingency
import numpy as np

# t-test: Did DAU change between two periods?
dau_before = ws.query("Login", math="dau", from_date="2025-01-01", to_date="2025-01-31").df["count"]
dau_after = ws.query("Login", math="dau", from_date="2025-02-01", to_date="2025-02-28").df["count"]

t_stat, p_value = ttest_ind(dau_before, dau_after)
print(f"DAU change: t={t_stat:.2f}, p={p_value:.4f}")
print(f"  Before: {dau_before.mean():,.0f} +/- {dau_before.std():,.0f}")
print(f"  After:  {dau_after.mean():,.0f} +/- {dau_after.std():,.0f}")
print(f"  {'Significant' if p_value < 0.05 else 'Not significant'} at p<0.05")

# Chi-squared: Did conversion rate change?
# Before: 1000 entered funnel, 120 converted
# After: 1100 entered, 165 converted
observed = np.array([[120, 880], [165, 935]])
chi2, p, dof, expected = chi2_contingency(observed)
print(f"\nConversion change: chi2={chi2:.2f}, p={p:.4f}")
```

### Impact Quantification (Lift and Confidence Intervals)

```python
import numpy as np
from scipy.stats import norm

def lift_with_ci(control_rate, test_rate, control_n, test_n, confidence=0.95):
    """Calculate lift and confidence interval for conversion rate change."""
    lift = (test_rate - control_rate) / control_rate if control_rate else 0

    # Standard error of difference
    se = np.sqrt(
        control_rate * (1 - control_rate) / control_n
        + test_rate * (1 - test_rate) / test_n
    )

    z = norm.ppf(1 - (1 - confidence) / 2)
    diff = test_rate - control_rate
    ci_low = diff - z * se
    ci_high = diff + z * se

    return {
        "lift": lift,
        "diff": diff,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "significant": (ci_low > 0) or (ci_high < 0),
    }

# Example: funnel conversion before/after a change
before = ws.query_funnel(["Signup", "Purchase"], from_date="2025-01-01", to_date="2025-01-31")
after = ws.query_funnel(["Signup", "Purchase"], from_date="2025-02-01", to_date="2025-02-28")

before_n = before.df.iloc[0]["count"]
after_n = after.df.iloc[0]["count"]

result = lift_with_ci(
    before.overall_conversion_rate,
    after.overall_conversion_rate,
    before_n, after_n,
)
print(f"Lift: {result['lift']:.1%}")
print(f"95% CI: [{result['ci_low']:.4f}, {result['ci_high']:.4f}]")
print(f"Significant: {result['significant']}")
```

### Trend Detection and Anomaly Identification

```python
import numpy as np
import pandas as pd

dau = ws.query("Login", math="dau", last=90).df
counts = dau.set_index("date")["count"]
counts.index = pd.to_datetime(counts.index)

# Rolling statistics
rolling_mean = counts.rolling(7).mean()
rolling_std = counts.rolling(7).std()

# Z-score anomalies (>2 sigma from rolling mean)
z_scores = (counts - rolling_mean) / rolling_std
anomalies = counts[z_scores.abs() > 2]

print(f"Found {len(anomalies)} anomalous days:")
for date, value in anomalies.items():
    z = z_scores[date]
    direction = "spike" if z > 0 else "dip"
    print(f"  {date.strftime('%Y-%m-%d')}: {value:,.0f} ({direction}, z={z:.1f})")

# Linear trend
x = np.arange(len(counts))
slope, intercept = np.polyfit(x, counts.values, 1)
daily_change = slope
weekly_change = slope * 7
print(f"\nTrend: {daily_change:+.1f}/day ({weekly_change:+.1f}/week)")
```

---

## Multi-Engine Investigation Templates

### Template 1: Revenue Drop Diagnosis (4-engine)

_(→ [analytical-frameworks.md](analytical-frameworks.md) §Diagnosis Methodology for the systematic diagnostic framework)_

**Question**: "Revenue dropped 20% this month. Why?"

| # | Sub-Question | Engine | Method | Key Params |
|---|-------------|--------|--------|------------|
| 1 | Did daily revenue actually drop? When? | Insights | `query()` | `math="total", math_property="revenue", unit="day"` |
| 2 | Which segment drove the drop? | Insights | `query()` | `group_by="platform"` (then country, plan) |
| 3 | Did purchase funnel conversion change? | Funnels | `query_funnel()` | Steps: Browse -> Cart -> Checkout -> Purchase |
| 4 | Did buyer retention decline? | Retention | `query_retention()` | `born_event="First Purchase", return_event="Purchase"` |
| 5 | Where do users go instead of purchasing? | Flows | `query_flow()` | Reverse from Purchase, `forward=0, reverse=5` |

**Join strategy**: Time-aligned (daily revenue + daily funnel conversion). Segment-aligned (revenue by platform + retention by platform).

**Unique insight**: Combine funnel step-conv with flow transitions to pinpoint exactly WHERE in the purchase path users diverge AND what they do instead.

### Template 2: Feature Adoption Analysis (4-engine)

_(→ [analytical-frameworks.md](analytical-frameworks.md) §Feature Adoption Framework for the 4-step methodology this template implements)_

**Question**: "How is the new Search feature performing?"

| # | Sub-Question | Engine | Method | Key Params |
|---|-------------|--------|--------|------------|
| 1 | How many users tried it? Daily trend? | Insights | `query()` | `math="unique"`, event="Use Search" |
| 2 | What % of active users adopt it? | Insights | `query()` | Formula: `(A / B) * 100` (Search / Login) |
| 3 | Do adopters convert better? | Funnels | `query_funnel()` | Compare with/without `where=Filter.is_set("first_search_date")` |
| 4 | Do adopters retain better? | Retention | `query_retention()` | `where` filter on search usage |
| 5 | What do users do before/after searching? | Flows | `query_flow()` | Bidirectional from "Use Search" |

**Join strategy**: Segment-aligned (adopters vs non-adopters across funnel + retention). Time-aligned (adoption curve vs revenue curve).

**Unique insight**: Flows reveal whether Search actually connects users to purchase paths, while retention confirms long-term stickiness.

### Template 3: Onboarding Optimization (3-engine)

**Question**: "How can we improve onboarding completion?"

| # | Sub-Question | Engine | Method | Key Params |
|---|-------------|--------|--------|------------|
| 1 | What is the current onboarding funnel? | Funnels | `query_funnel()` | Steps: Signup -> Profile -> First Action |
| 2 | Where do users go when they drop from onboarding? | Flows | `query_flow()` | Forward from each funnel step |
| 3 | Does onboarding completion predict retention? | Retention | `query_retention()` | Compare completers vs non-completers |
| 4 | Which step has the worst timing? | Funnels | `query_funnel()` | Check `avg_time` between steps |

**Join strategy**: Funnel-Flow complement (funnel identifies worst step, flow reveals escape paths). Insights-Retention correlation (completion predicts return).

**Unique insight**: The flow from the worst funnel step shows exactly what distracts users, enabling targeted interventions.

### Template 4: Churn Investigation (3-engine)

**Question**: "Why are users churning after week 2?"

| # | Sub-Question | Engine | Method | Key Params |
|---|-------------|--------|--------|------------|
| 1 | Which cohorts show the steepest drop at week 2? | Retention | `query_retention()` | `retention_unit="week", group_by="signup_source"` |
| 2 | What do churners do in their last session? | Flows | `query_flow()` | Reverse from "Last Active" or session-end event |
| 3 | Do churners use fewer features? | Insights | `query()` | Compare feature event counts: churners vs retained |
| 4 | Is there a behavioral inflection point? | Insights | `query()` | Daily engagement trend leading up to churn |

**Join strategy**: Segment-aligned (retention segments matched to flow paths). Time-aligned (engagement trend correlated with churn timing).

**Unique insight**: Retention identifies WHEN churn happens, flows reveal the last-session behavior pattern, and insights quantify the engagement gap.

### Template 5: Campaign Effectiveness (2-engine)

**Question**: "Did the Q1 marketing campaign work?"

| # | Sub-Question | Engine | Method | Key Params |
|---|-------------|--------|--------|------------|
| 1 | Did signups increase during the campaign? | Insights | `query()` | `group_by="utm_campaign"`, compare periods |
| 2 | Did campaign users convert to paid? | Funnels | `query_funnel()` | `where=Filter.equals("utm_campaign", "q1_promo")` |
| 3 | How does campaign user quality compare? | Insights | `query()` | ARPU by utm_campaign |
| 4 | Do campaign users retain? | Retention | `query_retention()` | `where=Filter.equals("utm_campaign", "q1_promo")` |

**Join strategy**: Segment-aligned (campaign vs organic across funnel + retention). Time-aligned (campaign period vs pre/post).

**Unique insight**: Volume (insights) + quality (funnel conversion) + durability (retention) gives a complete picture. A campaign can drive volume but attract low-quality users who churn.

### Template 6: A/B Test Analysis (3-engine)

**Question**: "Which variant of the checkout flow performs better?"

| # | Sub-Question | Engine | Method | Key Params |
|---|-------------|--------|--------|------------|
| 1 | Conversion rate by variant | Funnels | `query_funnel()` | `where=Filter.equals("experiment_variant", "A")` vs `"B"` |
| 2 | Revenue per user by variant | Insights | `query()` | `math="total", per_user="average", math_property="revenue"` |
| 3 | Do winners retain better? | Retention | `query_retention()` | Filter by variant |
| 4 | User path differences by variant | Flows | `query_flow()` | Filter by variant |

**Join strategy**: Segment-aligned (variant A vs B across all engines). Statistical testing (chi-squared on conversion, t-test on revenue).

**Unique insight**: A variant can win on conversion but lose on retention. Flows reveal WHY -- different paths mean different user experiences.

### Template 7: User Journey Mapping (2-engine)

**Question**: "What does the typical user journey look like?"

| # | Sub-Question | Engine | Method | Key Params |
|---|-------------|--------|--------|------------|
| 1 | What are the most common paths from signup? | Flows | `query_flow()` | `forward=5, mode="tree", cardinality=15` |
| 2 | How do power users differ from casual users? | Insights | `query()` | Compare feature usage: high-freq vs low-freq |
| 3 | What are the critical branching points? | Flows | `query_flow()` | NetworkX centrality analysis |
| 4 | Which events correlate with long-term engagement? | Insights | `query()` | Event frequency correlated with WAU |

**Join strategy**: Flow graph analysis identifies critical events, then insights quantifies their impact on engagement metrics.

**Unique insight**: Flow tree branching reveals the exact decision points where users diverge toward power-user vs casual paths.

### Template 8: Activation Metric Identification (3-engine)

**Question**: "What behavior predicts long-term retention?"

| # | Sub-Question | Engine | Method | Key Params |
|---|-------------|--------|--------|------------|
| 1 | Which events correlate with D30 retention? | Retention | `query_retention()` | Test each candidate event as `return_event` |
| 2 | Does frequency matter? (1x vs 3x vs 5x) | Insights | `query()` | Per-user frequency distribution |
| 3 | How quickly must the action happen? | Funnels | `query_funnel()` | Signup -> Candidate Event, vary conversion window |
| 4 | What path leads to the activation event? | Flows | `query_flow()` | Reverse from candidate activation event |

**Join strategy**: Iterative -- retention identifies candidate metrics, funnels determine timing threshold, flows map the path.

**Unique insight**: Activation = specific event + frequency threshold + time window. All three engines contribute a dimension.

### Template 9: Product-Market Fit Assessment (3-engine)

**Question**: "Do we have product-market fit?"

| # | Sub-Question | Engine | Method | Key Params |
|---|-------------|--------|--------|------------|
| 1 | Is retention flat or declining? | Retention | `query_retention()` | Long window (90+ days), look for plateau |
| 2 | Are core action frequencies growing? | Insights | `query()` | `math="unique"` for core actions, weekly trend |
| 3 | What % of signups reach the aha moment? | Funnels | `query_funnel()` | Signup -> Activation Event |
| 4 | Do retained users deepen engagement? | Insights | `query()` | `per_user="average"` for actions, month-over-month |
| 5 | What paths do retained users take? | Flows | `query_flow()` | Forward from activation, `mode="tree"` |

**Join strategy**: Time-aligned (retention plateau timing + engagement growth curves). Funnel-flow complement (activation path).

**Unique insight**: PMF = retention plateau + growing engagement depth + clear activation path. Three engines confirm the three signals.

### Template 10: Growth Bottleneck Identification (4-engine)

_(→ [analytical-frameworks.md](analytical-frameworks.md) §AARRR for the pirate metrics framework used in growth analysis)_

**Question**: "Where is the biggest bottleneck in our growth?"

| # | Sub-Question | Engine | Method | Key Params |
|---|-------------|--------|--------|------------|
| 1 | Where in AARRR is the weakest link? | Insights | `query()` | DAU, signups, purchases, invites -- absolute + trends |
| 2 | What is the acquisition-to-activation conversion? | Funnels | `query_funnel()` | Visit -> Signup -> First Action |
| 3 | Is the problem acquisition or retention? | Retention | `query_retention()` | Overall + segmented by acquisition channel |
| 4 | Where do users get stuck in the activation path? | Flows | `query_flow()` | Forward from Signup, `cardinality=20` |
| 5 | Period-over-period comparison | Insights | `query()` | Compare current vs previous month for all AARRR stages |

**Join strategy**: AARRR framework alignment -- each engine maps to a lifecycle stage. The stage with the worst metric is the bottleneck.

**Unique insight**: Quantify each AARRR stage (insights), identify conversion gaps (funnels), validate retention (retention), and map specific friction points (flows). The bottleneck is where the compounding loss is greatest.

### Template 11: Cohort Behavior Deep Dive (4-engine)

**Question**: "How do power users differ from everyone else?"

| # | Sub-Question | Engine | Method | Key Params |
|---|-------------|--------|--------|------------|
| 1 | How does engagement differ? | Insights | `query()` | `group_by=CohortBreakdown(ID, "Power Users")` |
| 2 | Do they convert better? | Funnels | `query_funnel()` | `group_by=CohortBreakdown(ID, "Power Users")` |
| 3 | Do they retain better? | Retention | `query_retention()` | `group_by=CohortBreakdown(ID, "Power Users")` |
| 4 | What paths do they take? | Flows | `query_flow()` | `where=Filter.in_cohort(ID, "Power Users")` |
| 5 | Is the cohort growing? | Insights | `query()` | `CohortMetric(ID, "Power Users")` + formula |

**Join strategy**: Segment-aligned — CohortBreakdown gives in-vs-out comparison across 3 engines. Flows uses Filter.in_cohort() since CohortBreakdown is not supported.

**Unique insight**: A single cohort definition drives consistent segmentation across all engines. Insights + CohortMetric shows whether the cohort is growing, while the other engines reveal why members behave differently.

---

## Reusable Multi-Engine Runner

A helper for running multiple queries in parallel with error handling:

```python
import mixpanel_data as mp
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

def run_multi_engine(
    ws: mp.Workspace,
    queries: dict[str, Callable[[], Any]],
    max_workers: int = 4,
) -> dict[str, Any]:
    """Run multiple query functions in parallel with error handling.

    Args:
        ws: Workspace instance (shared across threads -- httpx is thread-safe).
        queries: Mapping of name -> callable that returns a result.
        max_workers: Thread pool size.

    Returns:
        Dict mapping name -> result or {"error": str}.
    """
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fn): name for name, fn in queries.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                results[name] = {"error": str(e)}
    return results

# Usage
ws = mp.Workspace()
results = run_multi_engine(ws, {
    "dau": lambda: ws.query("Login", math="dau", last=30),
    "funnel": lambda: ws.query_funnel(["Signup", "Purchase"], last=30),
    "retention": lambda: ws.query_retention("Signup", "Login", last=30),
    "flow": lambda: ws.query_flow("Signup", forward=3, last=30),
})

for name, result in results.items():
    if isinstance(result, dict) and "error" in result:
        print(f"  {name}: ERROR - {result['error']}")
    else:
        print(f"  {name}: OK ({type(result).__name__})")
```

---

## Tips and Gotchas

_For per-engine pitfalls, see the Common Pitfalls sections in each engine reference: [insights-reference.md](insights-reference.md) | [funnels-reference.md](funnels-reference.md) | [retention-reference.md](retention-reference.md) | [flows-reference.md](flows-reference.md)._

- **Thread safety**: `Workspace` uses `httpx` which is thread-safe. A single `ws` instance can be shared across threads in `ThreadPoolExecutor`.
- **Date alignment**: Always use the same `from_date`/`to_date` or `last` when comparing across engines. Misaligned dates produce misleading correlations.
- **Segment naming**: Insights `group_by` produces segments in the `event` column. Retention produces segments in `result.segments` keys. Map them explicitly when joining.
- **Rate limits**: Mixpanel rate-limits API calls. Running 4 engines in parallel is fine, but launching 20+ concurrent queries may trigger `RateLimitError`.
- **Funnel vs flow conversion**: Funnel conversion measures users who complete ALL steps in order. Flow conversion measures the fraction reaching any end state. They are complementary, not equivalent.
- **Bookmark persistence**: All results have `.params` for saving as Mixpanel reports. Use `ws.create_bookmark()` to persist any query for the team.
- **Result caching**: Query results are immutable frozen dataclasses. Cache them in variables rather than re-querying.
- **Empty results**: Always check for empty DataFrames before joining. A failed query returns an empty DF with correct column names.
