# Analytical Frameworks for Product Analytics

Deep reference for AARRR, GQM, North Star, and diagnosis methodology. Use these frameworks to structure investigations and deliver actionable insights.

## AARRR (Pirate Metrics)

The AARRR framework maps the user lifecycle into five stages. Classify every question into a stage before choosing which `mixpanel_data` methods to call.

The library provides four typed query engines. Choose the right engine for each question:

| Engine | Method | Best For |
|--------|--------|----------|
| **Insights** | `ws.query()` | Time series, totals, breakdowns, formulas |
| **Funnels** | `ws.query_funnel()` | Step-by-step conversion, drop-off analysis |
| **Retention** | `ws.query_retention()` | Cohort curves, return rates over time |
| **Flows** | `ws.query_flow()` | User path analysis, entry/exit patterns |

### Acquisition — "Where do users come from?"

**Questions**: Traffic sources, campaign effectiveness, channel attribution, entry paths
**Engines**: Insights (source breakdown) + Flows (entry paths)
**Key methods**: `query` with group_by breakdown, `query_flow` for entry path analysis

```python
# Channel analysis (Insights)
result = ws.query("Visit", last=30, group_by="utm_source")
by_source = result.df.groupby("event")["count"].sum().sort_values(ascending=False)
print("Top acquisition channels:")
print(by_source.head(10))

# Entry path analysis (Flows) — what do users do after landing?
flow = ws.query_flow("Visit", forward=3, last=30)
print("Top entry paths:")
for src, tgt, count in flow.top_transitions(5):
    print(f"  {src} -> {tgt}: {count}")
```

### Activation — "Do they reach the aha moment?"

**Questions**: Onboarding completion, time-to-value, first key action, activation paths
**Engines**: Funnels (onboarding completion) + Flows (activation paths)
**Key methods**: `query_funnel` for conversion, `query_flow` for path discovery

```python
from mixpanel_data import FunnelStep, Filter

# Onboarding funnel (Funnels)
result = ws.query_funnel(
    ["Sign Up", "Complete Profile", "First Action"],
    conversion_window=7,
    last=30,
)
print(f"Overall conversion: {result.steps_data[-1]['overall_conv_ratio']:.1%}")
for step in result.steps_data:
    print(f"  {step['event']}: {step['count']} ({step['step_conv_ratio']:.1%})")

# Activation paths (Flows) — what paths lead to activation?
flow = ws.query_flow("First Action", reverse=3, last=30)
print("Paths leading to activation:")
for src, tgt, count in flow.top_transitions(5):
    print(f"  {src} -> {tgt}: {count}")
```

**Cohort-scoped**: Compare activation funnels across cohorts: `ws.query_funnel(steps, group_by=CohortBreakdown(ID, "Power Users"))`

### Retention — "Do they come back?"

**Questions**: Return rates, cohort behavior, churn patterns, sticky features
**Engines**: Retention (cohort curves) + Insights (usage trends)
**Key methods**: `query_retention` for cohort analysis, `query` for trend monitoring

```python
# Cohort retention curve (Retention)
result = ws.query_retention(
    "Sign Up", "Login",
    retention_unit="week", last=90,
)
print(result.df)

# Average retention across cohorts
avg = result.average
print(f"Cohort size avg: {avg['first']}")
for i, rate in enumerate(avg['rates']):
    print(f"  Week {i}: {rate:.1%}")

# Feature stickiness trend (Insights)
stickiness = ws.query(
    "Use Feature X", math="dau", last=30,
)
print(f"DAU trend for Feature X:")
print(stickiness.df)
```

**Cohort-scoped**: Compare retention curves across cohorts: `ws.query_retention(born, ret, group_by=CohortBreakdown(ID, "Power Users"))`

**Benchmarks**:
| Industry | D1 | D7 | D30 |
|----------|-----|-----|------|
| Consumer Mobile | 25-40% | 10-20% | 5-10% |
| SaaS B2B | 60-80% | 40-60% | 95%+ monthly |
| E-commerce | — | 20-30% | 20-30% |
| Social/Community | 40-60% | 25-40% | 20-30% |

### Revenue — "Do they pay?"

**Questions**: Conversion to paid, ARPU, LTV indicators, upgrade triggers
**Engines**: Insights (revenue metrics) + Funnels (purchase conversion)
**Key methods**: `query` with math aggregations, `query_funnel` for purchase flow

```python
# Daily revenue (Insights)
revenue = ws.query(
    "Purchase", math="total", math_property="revenue",
    from_date="2025-01-01", to_date="2025-01-31",
)

# ARPU (Insights)
arpu = ws.query(
    "Purchase", math="total", per_user="average",
    math_property="revenue",
    from_date="2025-01-01", to_date="2025-01-31",
)

# Purchase conversion funnel (Funnels)
purchase_funnel = ws.query_funnel(
    ["View Product", "Add to Cart", "Checkout", "Purchase"],
    conversion_window=7, last=30,
)
print(f"View -> Purchase: {purchase_funnel.steps_data[-1]['overall_conv_ratio']:.1%}")
```

**Cohort-scoped**: Track cohort revenue contribution: `ws.query(CohortMetric(ID, "Paying Users"), last=90)` alongside revenue metrics.

### Referral — "Do they invite others?"

**Questions**: Invite rates, viral coefficient, referral attribution
**Engines**: Insights (invite events) + Funnels (invite-to-accept)
**Key methods**: `query` for invite volume, `query_funnel` for invite-to-accept conversion

```python
# Referral volume (Insights)
invites = ws.query("Invite Sent", last=30, mode="total").df
accepts = ws.query("Invite Accepted", last=30, mode="total").df
invites_total = invites["count"].sum()
viral_coefficient = accepts["count"].sum() / invites_total if invites_total > 0 else 0
print(f"Viral coefficient: {viral_coefficient:.2f}")

# Invite-to-accept funnel (Funnels)
invite_funnel = ws.query_funnel(
    ["Invite Sent", "Invite Viewed", "Invite Accepted"],
    conversion_window=14, last=30,
)
for step in invite_funnel.steps_data:
    print(f"  {step['event']}: {step['count']} ({step['step_conv_ratio']:.1%})")
```

## GQM (Goal-Question-Metric)

Use GQM to decompose vague questions into actionable queries. This is your primary tool for open-ended requests like "why is X happening?"

### Process

1. **State the Goal**: What business outcome are we investigating?
2. **Generate Questions**: 3-5 specific, measurable sub-questions
3. **Map to Metrics**: For each question, identify the engine and `mixpanel_data` method

### Example: "Why is retention down?"

| # | Question | Metric | Engine | Method |
|---|----------|--------|--------|--------|
| 1 | Did overall D7 retention change? | D7 retention % | Retention | `query_retention("Sign Up", "Login", retention_unit="day")` |
| 2 | Which user segment is most affected? | Retention by platform/country | Retention | `query_retention(..., group_by="platform")` |
| 3 | Did onboarding completion change? | Funnel conversion rate | Funnels | `query_funnel(["Sign Up", "Complete Profile", "First Action"])` |
| 4 | Are users engaging with core features? | Feature event frequency | Insights | `query("Core Feature", math="dau", last=30)` |
| 5 | Did user paths change? | Flow patterns before/after | Flows | `query_flow("Core Feature", reverse=3)` |

### Example: "How is the new feature performing?"

| # | Question | Metric | Engine | Method |
|---|----------|--------|--------|--------|
| 1 | How many users tried it? | Unique users | Insights | `query("Feature X", math="unique", last=30)` |
| 2 | What's the adoption curve? | Daily unique users over time | Insights | `query("Feature X", math="unique", unit="day")` |
| 3 | Do adopters retain better? | Retention of feature users vs non-users | Retention | `query_retention("Sign Up", "Feature X")` |
| 4 | Is there a conversion impact? | Funnel rates with/without feature use | Funnels | `query_funnel(["Feature X", "Purchase"])` |
| 5 | How do users discover it? | Paths leading to feature | Flows | `query_flow("Feature X", reverse=3)` |

### Example: "How do power users differ from everyone else?"

| # | Question | Metric | Engine | Method |
|---|----------|--------|--------|--------|
| 1 | How does engagement differ? | DAU in vs out of cohort | Insights | `query("Login", math="dau", group_by=CohortBreakdown(ID, "Power Users"))` |
| 2 | Do they convert better? | Funnel conversion by cohort | Funnels | `query_funnel(steps, group_by=CohortBreakdown(ID, "Power Users"))` |
| 3 | Do they retain better? | Retention by cohort | Retention | `query_retention(born, ret, group_by=CohortBreakdown(ID, "Power Users"))` |
| 4 | What paths do they take? | Flow analysis for cohort | Flows | `query_flow(event, where=Filter.in_cohort(ID, "Power Users"))` |
| 5 | Is the cohort growing? | Cohort size over time | Insights | `query(CohortMetric(ID, "Power Users"), last=90)` |

## Feature Adoption Framework

Use funnels, retention, and flows together to measure feature adoption holistically.

### Step 1: Measure Discovery (Flows)

How do users find the feature? Identify entry paths:

```python
# What paths lead to feature discovery?
discovery = ws.query_flow("Feature X Used", reverse=3, last=30)
print("Discovery paths:")
for src, tgt, count in discovery.top_transitions(10):
    print(f"  {src} -> {tgt}: {count}")
```

### Step 2: Measure Activation (Funnels)

What percentage of users who discover the feature complete a meaningful action?

```python
# Discovery-to-value funnel
activation = ws.query_funnel(
    ["Feature X Viewed", "Feature X Used", "Feature X Value Received"],
    conversion_window=7, last=30,
)
for step in activation.steps_data:
    print(f"  {step['event']}: {step['step_conv_ratio']:.1%}")
```

### Step 3: Measure Habit Formation (Retention)

Do users come back to use the feature repeatedly?

```python
# Feature-specific retention
habit = ws.query_retention(
    "Feature X Used", "Feature X Used",
    retention_unit="week", last=60,
)
avg = habit.average
print("Feature retention curve:")
for i, rate in enumerate(avg["rates"][:8]):
    print(f"  Week {i}: {rate:.1%}")
```

### Step 4: Measure Impact (Insights)

Does feature adoption correlate with business outcomes?

```python
from mixpanel_data import Metric, Formula

# Compare adopters vs non-adopters on revenue
result = ws.query(
    [
        Metric("Purchase", math="total", math_property="revenue",
               where=Filter.is_set("feature_x_used")),
        Metric("Purchase", math="total", math_property="revenue"),
    ],
    formula="(A / B) * 100", formula_label="Adopter Revenue Share %",
    last=30,
)
print(result.df)
```

## North Star Metric Framework

A North Star metric captures the core value your product delivers. All analysis should connect back to it.

### Identifying the North Star

| Product Type | North Star | Supporting Metrics |
|-------------|-----------|-------------------|
| Social media | Daily active users | Posts created, engagement rate, time in app |
| E-commerce | Weekly purchases | Cart additions, checkout starts, AOV |
| SaaS | Weekly active workspaces | Features used, collaboration events, integrations |
| Marketplace | Transactions completed | Listings created, searches, buyer-seller messages |
| Content | Time reading/watching | Articles opened, completion rate, shares |

### Measurement Pattern

Use the appropriate engine for each metric type:

```python
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()

# North Star: Weekly Active Users (Insights)
wau = ws.query("Any Active Event", math="unique", unit="week", last=90)
wau_df = wau.df
print(f"WAU trend: {wau_df['count'].pct_change().mean():.1%} avg weekly growth")

# Supporting: New user activation rate (Funnels)
activation = ws.query_funnel(
    ["Sign Up", "Core Action"],
    conversion_window=7, last=30,
)
print(f"Activation rate: {activation.steps_data[-1]['overall_conv_ratio']:.1%}")

# Supporting: User retention (Retention)
ret = ws.query_retention("Sign Up", "Core Action", retention_unit="week", last=90)
print(f"Week-1 retention: {ret.average['rates'][1]:.1%}")

# Supporting: User journey health (Flows)
flow = ws.query_flow("Core Action", forward=2, reverse=2, last=30)
print(f"Drop-off summary: {flow.drop_off_summary()}")
```

## Diagnosis Methodology

When a metric changes unexpectedly, follow this structured investigation using all four query engines.

### Step 1: Quantify the Change (Insights)

```python
# Compare periods
current = ws.query("X", from_date="2025-03-01", to_date="2025-03-31").df
previous = ws.query("X", from_date="2025-02-01", to_date="2025-02-28").df
change_pct = (current["count"].sum() - previous["count"].sum()) / previous["count"].sum() * 100
print(f"Change: {change_pct:.1f}%")
```

### Step 2: Segment the Change (Insights)

Break down by 4-6 dimensions to isolate the driver:

```python
dimensions = ["platform", "country", "utm_source", "plan_type", "device_type"]
for dim in dimensions:
    current = ws.query("X", from_date=..., to_date=..., group_by=dim).df
    previous = ws.query("X", from_date=..., to_date=..., group_by=dim).df
    delta = (current.groupby("event")["count"].sum() - previous.groupby("event")["count"].sum()).dropna()
    print(f"\n=== By {dim} ===")
    print(delta.sort_values().head(5))  # biggest drops
```

### Step 3: Check Conversion Funnels (Funnels)

Did conversion rates change in key funnels?

```python
# Compare funnel conversion across periods
current_funnel = ws.query_funnel(
    ["Sign Up", "Activate", "Convert"],
    from_date="2025-03-01", to_date="2025-03-31",
)
previous_funnel = ws.query_funnel(
    ["Sign Up", "Activate", "Convert"],
    from_date="2025-02-01", to_date="2025-02-28",
)
for curr, prev in zip(current_funnel.steps_data, previous_funnel.steps_data):
    delta = curr["step_conv_ratio"] - prev["step_conv_ratio"]
    print(f"  {curr['event']}: {prev['step_conv_ratio']:.1%} -> {curr['step_conv_ratio']:.1%} ({delta:+.1%})")
```

### Step 4: Check Retention (Retention)

Did retention patterns shift?

```python
# Compare retention curves
current_ret = ws.query_retention(
    "Sign Up", "Core Action",
    from_date="2025-03-01", to_date="2025-03-31",
    retention_unit="day",
)
previous_ret = ws.query_retention(
    "Sign Up", "Core Action",
    from_date="2025-02-01", to_date="2025-02-28",
    retention_unit="day",
)
curr_rates = current_ret.average["rates"]
prev_rates = previous_ret.average["rates"]
for i in range(min(len(curr_rates), len(prev_rates), 7)):
    delta = curr_rates[i] - prev_rates[i]
    print(f"  D{i}: {prev_rates[i]:.1%} -> {curr_rates[i]:.1%} ({delta:+.1%})")
```

### Step 5: Check User Paths (Flows)

Did user paths change?

```python
# Compare flow patterns
current_flow = ws.query_flow("Core Action", reverse=3,
    from_date="2025-03-01", to_date="2025-03-31")
previous_flow = ws.query_flow("Core Action", reverse=3,
    from_date="2025-02-01", to_date="2025-02-28")
print("Current top paths:")
for src, tgt, count in current_flow.top_transitions(5):
    print(f"  {src} -> {tgt}: {count}")
print("Previous top paths:")
for src, tgt, count in previous_flow.top_transitions(5):
    print(f"  {src} -> {tgt}: {count}")
```

### Step 6: Find the Inflection Point (Insights)

```python
# Daily granularity to find exact date
daily = ws.query("X", from_date="2025-02-15", to_date="2025-03-15", unit="day").df
daily_counts = daily.groupby("date")["count"].sum().reset_index()
daily_counts["rolling_avg"] = daily_counts["count"].rolling(3).mean()
daily_counts["pct_change"] = daily_counts["count"].pct_change()
print("Biggest daily drops:")
print(daily_counts.nsmallest(5, "pct_change"))
```

### Step 7: Synthesize and Recommend

Structure findings as:
1. **What happened**: Metric X dropped Y% between date A and date B
2. **Root cause**: Segment Z (e.g., iOS users) accounts for N% of the drop, starting on date C
3. **Funnel impact**: Step conversion at [step] dropped from X% to Y%
4. **Retention impact**: D7 retention dropped by Z percentage points
5. **Path change**: Users shifted from path A to path B
6. **Correlation**: This coincides with [release / campaign / seasonal pattern]
7. **Recommendation**: Investigate [specific area], consider [specific action]
8. **Next steps**: Monitor [metric] daily, set up alert at [threshold]

## Delivering Insights

### Always Provide Context

- Compare to previous period (WoW, MoM)
- Include sample sizes — a 50% drop in 10 users is noise
- Note confidence level: "This is directional" vs "This is statistically significant"

### Structure Recommendations

| Priority | Type | Example |
|----------|------|---------|
| **Quick wins** | Low effort, clear impact | "Fix the broken CTA on mobile signup" |
| **Test hypotheses** | A/B test candidates | "Test reducing form fields from 6 to 3" |
| **Strategic** | Larger initiatives | "Redesign onboarding flow for mobile" |
| **Monitor** | Set up tracking | "Create daily alert for iOS conversion < 15%" |
