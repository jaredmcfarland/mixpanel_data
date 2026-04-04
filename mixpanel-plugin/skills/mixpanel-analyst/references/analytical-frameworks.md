# Analytical Frameworks for Product Analytics

Deep reference for AARRR, GQM, North Star, and diagnosis methodology. Use these frameworks to structure investigations and deliver actionable insights.

## AARRR (Pirate Metrics)

The AARRR framework maps the user lifecycle into five stages. Classify every question into a stage before choosing which `mixpanel_data` methods to call.

### Acquisition — "Where do users come from?"

**Questions**: Traffic sources, campaign effectiveness, channel attribution
**Key methods**: `segmentation` with utm/source breakdown, `event_counts`

```python
# Channel analysis
result = ws.segmentation(
    event="Visit", from_date="2025-01-01", to_date="2025-01-31",
    on='properties["utm_source"]',
)
by_source = result.df.groupby("segment")["count"].sum().sort_values(ascending=False)
print("Top acquisition channels:")
print(by_source.head(10))
```

### Activation — "Do they reach the aha moment?"

**Questions**: Onboarding completion, time-to-value, first key action
**Key methods**: `funnel`, `activity_feed`, `segmentation` on activation events

```python
# Onboarding funnel
result = ws.funnel(funnel_id=ONBOARDING_FUNNEL_ID, from_date=..., to_date=...)

# Time-to-first-action via JQL
result = ws.jql("""function main() {
  return Events({from_date: "2025-01-01", to_date: "2025-01-31",
                 event_selectors: [{event: "Sign Up"}, {event: "First Purchase"}]})
    .groupByUser([mixpanel.reducer.min("time"), mixpanel.reducer.max("time")])
    .map(u => ({user: u.key, hours_to_activate: (u.value[1] - u.value[0]) / 3600}))
}""")
```

### Retention — "Do they come back?"

**Questions**: Return rates, cohort behavior, churn patterns, sticky features
**Key methods**: `retention`, `segmentation` over time, `frequency`

```python
# N-day retention
result = ws.retention(
    born_event="Sign Up", return_event="Login",
    from_date="2025-01-01", to_date="2025-02-28",
)
print(result.df)

# Feature stickiness
freq = ws.frequency(event="Use Feature X", from_date=..., to_date=...)
```

**Benchmarks**:
| Industry | D1 | D7 | D30 |
|----------|-----|-----|------|
| Consumer Mobile | 25-40% | 15-25% | 10-15% |
| SaaS B2B | 60-80% | 40-60% | 30-50% |
| E-commerce | — | 20-30% | 10-20% |
| Social/Community | 40-60% | 25-40% | 20-30% |

### Revenue — "Do they pay?"

**Questions**: Conversion to paid, ARPU, LTV indicators, upgrade triggers
**Key methods**: `segmentation_sum` on revenue, `funnel` to purchase, `jql` for per-user revenue

```python
# Daily revenue
revenue = ws.segmentation_sum(
    event="Purchase", on='properties["revenue"]',
    from_date="2025-01-01", to_date="2025-01-31",
)

# ARPU via JQL
result = ws.jql("""function main() {
  return Events({from_date: "2025-01-01", to_date: "2025-01-31",
                 event_selectors: [{event: "Purchase"}]})
    .groupByUser(mixpanel.reducer.sum("properties.revenue"))
    .reduce(mixpanel.reducer.numeric_summary())
}""")
```

### Referral — "Do they invite others?"

**Questions**: Invite rates, viral coefficient, referral attribution
**Key methods**: `segmentation` on invite/share events, `jql` for viral loops

```python
# Referral tracking
invites = ws.segmentation(event="Invite Sent", from_date=..., to_date=...).df
accepts = ws.segmentation(event="Invite Accepted", from_date=..., to_date=...).df
invites_total = invites["count"].sum()
viral_coefficient = accepts["count"].sum() / invites_total if invites_total > 0 else 0
print(f"Viral coefficient: {viral_coefficient:.2f}")
```

## GQM (Goal-Question-Metric)

Use GQM to decompose vague questions into actionable queries. This is your primary tool for open-ended requests like "why is X happening?"

### Process

1. **State the Goal**: What business outcome are we investigating?
2. **Generate Questions**: 3-5 specific, measurable sub-questions
3. **Map to Metrics**: For each question, identify the `mixpanel_data` method

### Example: "Why is retention down?"

| # | Question | Metric | Method |
|---|----------|--------|--------|
| 1 | Did overall D7 retention change? | D7 retention % | `retention()` |
| 2 | Which user segment is most affected? | Retention by platform/country | `retention()` with segmentation |
| 3 | Did onboarding completion change? | Funnel conversion rate | `funnel()` |
| 4 | Are users engaging with core features? | Feature event frequency | `frequency()` or `segmentation()` |
| 5 | Was there a specific date the drop started? | Daily retention trend | `segmentation()` of return events |

### Example: "How is the new feature performing?"

| # | Question | Metric | Method |
|---|----------|--------|--------|
| 1 | How many users tried it? | Unique users | `event_counts(events=[...], type="unique")` |
| 2 | What's the adoption curve? | Daily unique users over time | `event_counts(events=[...], unit="day", type="unique")` |
| 3 | Do adopters retain better? | Retention of feature users vs non-users | `retention()` with where filters |
| 4 | Is there a conversion impact? | Funnel rates with/without feature use | `funnel()` comparisons |
| 5 | Which segments adopt fastest? | Feature use by segment | `segmentation()` with on breakdown |

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

```python
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()

# North Star: Weekly Active Users (WAU)
wau = ws.event_counts(
    events=["Any Active Event"], from_date="2025-01-01", to_date="2025-03-31",
    unit="week", type="unique",
)

# Supporting metrics
engagement = ws.frequency(event="Core Action", from_date=..., to_date=...)
retention = ws.retention(born_event="Sign Up", return_event="Core Action", from_date=..., to_date=...)

wau_series = wau.df.groupby("date")["count"].sum()
print(f"WAU trend: {wau_series.pct_change().mean():.1%} avg weekly growth")
```

## Diagnosis Methodology

When a metric changes unexpectedly, follow this structured investigation.

### Step 1: Quantify the Change

```python
# Compare periods
current = ws.segmentation(event="X", from_date="2025-03-01", to_date="2025-03-31").df
previous = ws.segmentation(event="X", from_date="2025-02-01", to_date="2025-02-28").df
change_pct = (current["count"].sum() - previous["count"].sum()) / previous["count"].sum() * 100
print(f"Change: {change_pct:.1f}%")
```

### Step 2: Segment the Change

Break down by 4-6 dimensions to isolate the driver:

```python
dimensions = ["platform", "country", "utm_source", "plan_type", "device_type"]
for dim in dimensions:
    current = ws.segmentation(event="X", from_date=..., to_date=..., on=f'properties["{dim}"]').df
    previous = ws.segmentation(event="X", from_date=..., to_date=..., on=f'properties["{dim}"]').df
    delta = (current.groupby("segment")["count"].sum() - previous.groupby("segment")["count"].sum()).dropna()
    print(f"\n=== By {dim} ===")
    print(delta.sort_values().head(5))  # biggest drops
```

### Step 3: Find the Inflection Point

```python
# Daily granularity to find exact date
daily = ws.segmentation(event="X", from_date="2025-02-15", to_date="2025-03-15", unit="day").df
daily_counts = daily.groupby("date")["count"].sum().reset_index()
daily_counts["rolling_avg"] = daily_counts["count"].rolling(3).mean()
daily_counts["pct_change"] = daily_counts["count"].pct_change()
print("Biggest daily drops:")
print(daily_counts.nsmallest(5, "pct_change"))
```

### Step 4: Correlate with Other Metrics

```python
# Did other metrics change at the same time?
metrics = {
    "target": ws.segmentation(event="X", from_date=..., to_date=...).df,
    "logins": ws.segmentation(event="Login", from_date=..., to_date=...).df,
    "errors": ws.segmentation(event="Error", from_date=..., to_date=...).df,
    "signups": ws.segmentation(event="Sign Up", from_date=..., to_date=...).df,
}
combined = pd.DataFrame({k: v.groupby("date")["count"].sum() for k, v in metrics.items()})
print(combined.corr())
```

### Step 5: Synthesize and Recommend

Structure findings as:
1. **What happened**: Metric X dropped Y% between date A and date B
2. **Root cause**: Segment Z (e.g., iOS users) accounts for N% of the drop, starting on date C
3. **Correlation**: This coincides with [release / campaign / seasonal pattern]
4. **Recommendation**: Investigate [specific area], consider [specific action]
5. **Next steps**: Monitor [metric] daily, set up alert at [threshold]

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
