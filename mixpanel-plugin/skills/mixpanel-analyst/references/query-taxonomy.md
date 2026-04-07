# Query Taxonomy — Routing, Decomposition, and Multi-Query Orchestration

Deep reference for mapping natural-language analytics questions to the correct `mixpanel_data` query engine(s), decomposing complex questions into sub-queries, joining results, and orchestrating multi-query execution.

## The Four Query Engines

| Engine | Method | Primary Use | Result Type |
|--------|--------|-------------|-------------|
| **Insights** | `ws.query()` | Trends, aggregations, breakdowns, formulas | `QueryResult` |
| **Funnels** | `ws.query_funnel()` | Step-by-step conversion, drop-off analysis | `FunnelQueryResult` |
| **Retention** | `ws.query_retention()` | Cohort retention curves, return behavior | `RetentionQueryResult` |
| **Flows** | `ws.query_flow()` | User path analysis, event sequences | `FlowQueryResult` |

Additionally, legacy methods (`segmentation`, `funnel`, `retention`, `jql`) remain available for specific cases, and discovery methods (`events`, `properties`, `property_values`, `top_events`) provide schema context.

---

## NL-to-Engine Signal Mapping

### Insights Engine Signals (ws.query)

| Signal Pattern | Example Question | Key Parameters |
|---|---|---|
| "how many", "count", "total" | "How many logins this month?" | `math="total"` |
| "unique users", "distinct users" | "How many unique users signed up?" | `math="unique"` |
| "DAU", "daily active" | "What's our DAU trend?" | `math="dau"` |
| "WAU", "weekly active" | "Show WAU for last quarter" | `math="wau"` |
| "MAU", "monthly active" | "MAU trend by platform" | `math="mau"` |
| "average", "mean" + property | "Average order value?" | `math="average", math_property="revenue"` |
| "median" + property | "Median session duration?" | `math="median", math_property="duration"` |
| "sum", "total revenue" | "Total revenue this month?" | `math="total", math_property="revenue"` |
| "p95", "p99", percentile | "P95 API latency?" | `math="percentile", percentile_value=95, math_property="latency"` |
| "min", "max" + property | "Max purchase amount?" | `math="max", math_property="amount"` |
| "by", "breakdown", "segment" | "Signups by country?" | `group_by="country"` |
| "trend", "over time" | "Login trend last 90 days?" | `last=90, unit="day"` |
| "compare", "ratio", "rate" | "Signup-to-purchase rate?" | `formula="(B / A) * 100"` |
| "rolling average" | "7-day rolling average of DAU?" | `rolling=7` |
| "cumulative", "running total" | "Cumulative signups?" | `cumulative=True` |
| "per user", "per person" | "Average revenue per user?" | `per_user="average", math_property="revenue"` |
| "distribution", "histogram" | "Revenue distribution?" | `math="histogram", math_property="revenue", per_user="total"` |
| "week over week", "WoW" | "WoW signup change?" | Two queries, different date ranges |
| "filtered by", "only where" | "Purchases where amount > 50?" | `where=Filter.greater_than("amount", 50)` |

### Funnel Engine Signals (ws.query_funnel)

| Signal Pattern | Example Question | Key Parameters |
|---|---|---|
| "funnel", "conversion" | "What's our signup funnel?" | `steps=["Signup", "Activate", "Purchase"]` |
| "drop-off", "where do users drop" | "Where do users drop off?" | `steps=[...], mode="steps"` |
| "step 1 to step 2" | "Conversion from cart to checkout?" | `steps=["Add to Cart", "Checkout"]` |
| "time to convert" | "How long to convert?" | Check `avg_time` in result |
| "within N days/hours" | "Convert within 7 days?" | `conversion_window=7, conversion_window_unit="day"` |
| "excluding users who" | "Funnel excluding logouts?" | `exclusions=["Logout"]` |
| "holding constant" | "Same-device funnel?" | `holding_constant=["device_id"]` |
| "loose order", "any order" | "Complete in any order?" | `order="any"` |
| "funnel trend over time" | "How is conversion trending?" | `mode="trends"` |
| "session-based conversion" | "Within-session conversion?" | `conversion_window_unit="session", math="conversion_rate_session"` |
| "A/B funnel comparison" | "Funnel by experiment group?" | `group_by="experiment_group"` |

### Retention Engine Signals (ws.query_retention)

| Signal Pattern | Example Question | Key Parameters |
|---|---|---|
| "retention", "come back" | "Do users come back after signup?" | `born_event="Signup", return_event="Login"` |
| "D1", "D7", "D30", "N-day" | "What's our D7 retention?" | `retention_unit="day"` |
| "weekly retention" | "Weekly retention curve?" | `retention_unit="week"` |
| "monthly retention" | "Monthly retention by cohort?" | `retention_unit="month"` |
| "churn", "stopped using" | "When do users churn?" | Retention curve, find inflection |
| "stickiness" | "How sticky is the product?" | `born_event="Login", return_event="Login"` |
| "feature retention" | "Do feature users retain better?" | Filter on born or return event |
| "cohort comparison" | "Jan vs Feb cohort retention?" | `group_by` or separate queries |
| "retention by segment" | "Retention by platform?" | `group_by="platform"` |
| "custom buckets" | "Retention at 1,3,7,14,30 days?" | `bucket_sizes=[1,3,7,14,30]` |
| "birth alignment" | "Align to user's first event?" | `alignment="birth"` |
| "calendar alignment" | "Align to calendar week?" | `alignment="interval_start"` |
| "raw counts vs rates" | "How many users retained?" | `math="unique"` vs `math="retention_rate"` |

### Flow Engine Signals (ws.query_flow)

| Signal Pattern | Example Question | Key Parameters |
|---|---|---|
| "flow", "path", "journey" | "What paths do users take after signup?" | `event="Signup", forward=5` |
| "what happens after" | "What happens after checkout?" | `event="Checkout", forward=3` |
| "what happens before" | "What do users do before purchasing?" | `event="Purchase", reverse=3` |
| "sankey", "user flow" | "Show the user flow diagram" | `mode="sankey"` |
| "top paths" | "Top 10 paths after onboarding?" | `mode="paths", cardinality=10` |
| "drop-off paths" | "Where do users go after dropping?" | Forward flow from drop-off event |
| "bidirectional" | "Activity around the purchase event?" | `forward=3, reverse=2` |

### Cohort-Scoped Signals (Cross-Engine)

| Signal Pattern | Example Question | Capability |
|---|---|---|
| "filter by cohort", "only [cohort]" | "Show DAU for power users only" | `where=Filter.in_cohort(...)` — any engine |
| "compare cohort", "[cohort] vs rest" | "How do power users differ?" | `group_by=CohortBreakdown(...)` — Insights/Funnels/Retention |
| "cohort size", "cohort growth" | "How is the power user cohort growing?" | `CohortMetric(...)` — Insights only |
| "define cohort inline" | "Users who purchased 3+ times in 30 days" | `CohortDefinition.all_of(CohortCriteria.did_event(...))` |

### Custom Property Signals (Cross-Engine)

| Signal Pattern | Example Question | Capability |
|---|---|---|
| "custom property", "computed property" | "Break down by revenue per unit" | `GroupBy(property=InlineCustomProperty.numeric(...))` |
| "saved custom property", "custom prop ID" | "Filter by our LTV custom property" | `Filter.*(property=CustomPropertyRef(ID))` |
| "formula property", "calculated field" | "Average of price times quantity" | `Metric(property=InlineCustomProperty.numeric(...))` |
| "list custom properties" | "What custom properties do we have?" | `ws.list_custom_properties()` |

### Discovery Signals (schema exploration)

| Signal Pattern | Method |
|---|---|
| "what events exist" | `ws.events()` |
| "what properties does X have" | `ws.properties("Event Name")` |
| "what values does property X have" | `ws.property_values("prop_name")` |
| "top events", "most popular" | `ws.top_events()` |
| "what funnels exist" | `ws.funnels()` |
| "what cohorts exist" | `ws.cohorts()` |

---

## Complex Question Decomposition

### Pattern 1: Diagnostic ("Why is X changing?")

**Question**: "Why are signups dropping?"

| Step | Engine | Query | Purpose |
|------|--------|-------|---------|
| 1 | Insights | `ws.query("Signup", last=60)` | Quantify the change |
| 2 | Insights | `ws.query("Signup", last=60, group_by="platform")` | Segment isolation |
| 3 | Insights | `ws.query("Signup", last=60, group_by="utm_source")` | Channel isolation |
| 4 | Insights | `ws.query("Signup", last=60, group_by="country")` | Geo isolation |
| 5 | Funnel | `ws.query_funnel(["Visit", "Signup"], last=60, group_by="platform")` | Conversion by segment |
| 6 | Insights | Correlate with `ws.query("Error", ...)` | Root cause candidates |

### Pattern 2: Feature Impact Assessment

**Question**: "How is the new feature performing?"

| Step | Engine | Query | Purpose |
|------|--------|-------|---------|
| 1 | Insights | `ws.query("Use Feature", math="unique", last=30)` | Adoption count |
| 2 | Insights | `ws.query(["Use Feature", "Login"], formula="(A/B)*100")` | Adoption rate |
| 3 | Retention | `ws.query_retention("Use Feature", "Login")` | Feature retention |
| 4 | Retention | `ws.query_retention("Signup", "Login")` | Baseline retention |
| 5 | Funnel | `ws.query_funnel(["Signup", "Purchase"], where=Filter.is_set("used_feature"))` | Feature users funnel |
| 6 | Funnel | `ws.query_funnel(["Signup", "Purchase"], where=Filter.is_not_set("used_feature"))` | Non-feature funnel |

### Pattern 3: Revenue Deep Dive

**Question**: "Analyze our revenue performance"

| Step | Engine | Query | Purpose |
|------|--------|-------|---------|
| 1 | Insights | `ws.query("Purchase", math="total", math_property="revenue")` | Total revenue trend |
| 2 | Insights | `ws.query("Purchase", math="average", math_property="revenue")` | AOV trend |
| 3 | Insights | `ws.query("Purchase", math="total", per_user="average", math_property="revenue")` | ARPU |
| 4 | Insights | `ws.query("Purchase", math="unique")` | Paying user count |
| 5 | Insights | `ws.query("Purchase", math="total", math_property="revenue", group_by="plan")` | Revenue by plan |
| 6 | Funnel | `ws.query_funnel(["Visit", "Signup", "Purchase"])` | Purchase funnel |
| 7 | Retention | `ws.query_retention("Purchase", "Purchase", retention_unit="month")` | Repeat purchase |

### Pattern 4: User Lifecycle Analysis

**Question**: "Map the complete user lifecycle"

| Step | Engine | Query | Purpose |
|------|--------|-------|---------|
| 1 | Discovery | `ws.top_events(limit=20)` | Identify key events |
| 2 | Funnel | `ws.query_funnel(["Signup", "Activate", "Core Action", "Purchase"])` | Full lifecycle funnel |
| 3 | Retention | `ws.query_retention("Signup", "Login", retention_unit="week")` | Overall retention |
| 4 | Retention | `ws.query_retention("Signup", "Core Action")` | Core action retention |
| 5 | Flows | `ws.query_flow(["Signup"], forward=5)` | Post-signup paths |
| 6 | Insights | `ws.query("Login", math="dau")` | Engagement trend |

### Pattern 5: Onboarding Optimization

**Question**: "Where is our onboarding failing?"

| Step | Engine | Query | Purpose |
|------|--------|-------|---------|
| 1 | Funnel | `ws.query_funnel(onboarding_steps, mode="steps")` | Step-level drop-off |
| 2 | Funnel | `ws.query_funnel(onboarding_steps, group_by="platform")` | Platform differences |
| 3 | Funnel | `ws.query_funnel(onboarding_steps, mode="trends")` | Trend over time |
| 4 | Flows | `ws.query_flow(["Signup"], forward=5)` | What users actually do |
| 5 | Retention | `ws.query_retention("Signup", "Core Action", bucket_sizes=[1,3,7])` | Time to activate |

### Pattern 6: A/B Test Analysis

**Question**: "How is experiment X performing?"

| Step | Engine | Query | Purpose |
|------|--------|-------|---------|
| 1 | Insights | `ws.query("Target Event", group_by="experiment_variant")` | Variant comparison |
| 2 | Funnel | `ws.query_funnel(steps, group_by="experiment_variant")` | Funnel by variant |
| 3 | Retention | `ws.query_retention(born, ret, group_by="experiment_variant")` | Retention by variant |
| 4 | Insights | `ws.query("Target Event", math="average", math_property="revenue", group_by="experiment_variant")` | Revenue by variant |

### Pattern 7: Engagement Scoring

**Question**: "Who are our power users?"

| Step | Engine | Query | Purpose |
|------|--------|-------|---------|
| 1 | Insights | `ws.query("Core Action", math="total", per_user="total", math_property="count")` | Actions per user |
| 2 | Insights | `ws.query("Core Action", math="dau")` | DAU trend |
| 3 | Insights | `ws.query(["Core Action", "Login"], formula="(A/B)*100")` | Engagement ratio |
| 4 | Retention | `ws.query_retention("Login", "Core Action", retention_unit="day")` | Daily stickiness |

### Pattern 8: Churn Investigation

**Question**: "Why are users churning?"

| Step | Engine | Query | Purpose |
|------|--------|-------|---------|
| 1 | Retention | `ws.query_retention("Signup", "Login", retention_unit="week")` | Baseline retention |
| 2 | Retention | `ws.query_retention("Signup", "Login", group_by="source")` | Retention by source |
| 3 | Insights | `ws.query("Login", math="unique", last=90)` | Active user trend |
| 4 | Funnel | `ws.query_funnel(["Login", "Core Action"])` | Activation rate |
| 5 | Flows | `ws.query_flow(["Last Login"], forward=3)` | Pre-churn behavior |

### Pattern 9: Growth Accounting

**Question**: "Break down our growth"

| Step | Engine | Query | Purpose |
|------|--------|-------|---------|
| 1 | Insights | `ws.query("Signup", math="unique", last=90, unit="week")` | New users |
| 2 | Insights | `ws.query("Login", math="wau", last=90, unit="week")` | WAU trend |
| 3 | Retention | `ws.query_retention("Login", "Login", retention_unit="week")` | Stickiness |
| 4 | Insights | Two period comparison for growth rate | WoW growth |

### Pattern 10: Content/Feature Ranking

**Question**: "Which features are most used?"

| Step | Engine | Query | Purpose |
|------|--------|-------|---------|
| 1 | Discovery | `ws.top_events(limit=50)` | Event volume ranking |
| 2 | Insights | `ws.query(feature_events, math="unique", mode="total")` | Unique users per feature |
| 3 | Retention | Multiple `query_retention` calls per feature | Feature-specific retention |
| 4 | Insights | `ws.query(feature_events, math="total", per_user="average", math_property="count")` | Frequency per user |

---

## Join Strategies

### Time-Aligned Join

Combine multiple insights queries on the same date range. All queries share the same x-axis (dates).

```python
import mixpanel_data as mp
import pandas as pd

ws = mp.Workspace()
period = dict(from_date="2025-01-01", to_date="2025-01-31")

signups = ws.query("Signup", math="unique", **period).df
logins = ws.query("Login", math="unique", **period).df
purchases = ws.query("Purchase", math="unique", **period).df

def extract(df: pd.DataFrame, name: str) -> pd.Series:
    s = df.set_index("date")["count"]
    s.name = name
    return s

combined = pd.concat([
    extract(signups, "signups"),
    extract(logins, "logins"),
    extract(purchases, "purchases"),
], axis=1)

combined["activation_rate"] = combined["logins"] / combined["signups"]
combined["purchase_rate"] = combined["purchases"] / combined["logins"]
```

### Segment-Aligned Join

Compare the same metric across different segments side by side.

```python
platforms = ws.query("Purchase", math="total", math_property="revenue",
                     group_by="platform", **period).df

pivot = platforms.pivot_table(
    index="date", columns="event", values="count", fill_value=0
)
pivot["total"] = pivot.sum(axis=1)
for col in pivot.columns:
    if col != "total":
        pivot[f"{col}_pct"] = (pivot[col] / pivot["total"] * 100).round(1)
```

### Funnel-Flow Complement

Use funnel drop-off to identify where users fail, then use flows to see what they do instead.

```python
# Step 1: Find the biggest drop-off
funnel = ws.query_funnel(["Visit", "Signup", "Activate", "Purchase"])
df = funnel.df
worst_step_idx = df["step_conv_ratio"].idxmin()
drop_event = df.loc[worst_step_idx, "event"]

# Step 2: See what users do instead of converting
flow = ws.query_flow([drop_event], forward=5)
print(flow.df)  # Top paths after drop-off point
```

### Insights-Retention Cohort Join

Use insights to identify a segment, then measure its retention.

```python
from mixpanel_data import Filter

# Step 1: Identify high-value segment
revenue = ws.query("Purchase", math="total", math_property="revenue",
                    group_by="plan", mode="total").df
top_plan = revenue.sort_values("count", ascending=False).iloc[0]["event"]

# Step 2: Measure retention for that segment
retention = ws.query_retention(
    "Login", "Login",
    where=Filter.equals("plan", top_plan),
    retention_unit="week",
)
print(f"Retention for {top_plan} plan:")
print(retention.df)
```

### Discovery Pipeline

Use discovery to build informed queries dynamically.

```python
# Step 1: Discover schema
events = ws.events()
top = ws.top_events(limit=10)
core_events = [t.event for t in top]

# Step 2: Discover properties for the top event
props = ws.properties(core_events[0])
print(f"Properties for {core_events[0]}: {props[:10]}")

# Step 3: Build queries from discovered schema
for event in core_events[:5]:
    result = ws.query(event, math="unique", last=7, mode="total")
    total = result.df["count"].sum()
    print(f"  {event}: {total:,.0f} unique users")
```

---

## Multi-Query Execution Patterns

### Sequential (dependency chain)

When each query depends on the previous result.

```python
# Q1 identifies the problem
trend = ws.query("Signup", last=60)
# Analyze trend to find the inflection
df = trend.df
df["pct_change"] = df["count"].pct_change()
inflection = df.loc[df["pct_change"].idxmin(), "date"]

# Q2 uses the inflection date
detail = ws.query("Signup", group_by="platform",
                  from_date=inflection, to_date="2025-03-31")
```

### Parallel (independent queries)

When queries are independent, run them concurrently for speed.

```python
from concurrent.futures import ThreadPoolExecutor

ws = mp.Workspace()
period = dict(from_date="2025-01-01", to_date="2025-01-31")

queries = {
    "dau": lambda: ws.query("Login", math="dau", **period),
    "signups": lambda: ws.query("Signup", math="unique", **period),
    "revenue": lambda: ws.query("Purchase", math="total",
                                 math_property="revenue", **period),
    "aov": lambda: ws.query("Purchase", math="average",
                             math_property="revenue", **period),
    "funnel": lambda: ws.query_funnel(["Signup", "Purchase"], **period),
    "retention": lambda: ws.query_retention("Signup", "Login", **period),
}

with ThreadPoolExecutor(max_workers=4) as pool:
    futures = {name: pool.submit(fn) for name, fn in queries.items()}
    results = {name: future.result() for name, future in futures.items()}

# All results available simultaneously
print(f"DAU avg: {results['dau'].df['count'].mean():,.0f}")
print(f"Funnel conversion: {results['funnel'].overall_conversion_rate:.1%}")
```

### Iterative (hypothesis-test-refine)

Refine queries based on intermediate findings.

```python
# Hypothesis 1: "Signups dropped because of mobile"
by_platform = ws.query("Signup", last=30, group_by="platform").df
mobile = by_platform[by_platform["event"] == "mobile"]

if mobile["count"].mean() < mobile["count"].iloc[:7].mean() * 0.8:
    # Confirmed: dig deeper into mobile
    by_source = ws.query("Signup", last=30,
                         where=Filter.equals("platform", "mobile"),
                         group_by="utm_source").df
    # Find the source that dropped
    # ...
else:
    # Hypothesis rejected: try another segment
    by_country = ws.query("Signup", last=30, group_by="country").df
    # ...
```

---

## Result Chain Architecture

The key insight is that every query method returns a result object with both `.df` (for analysis) and `.params` (for persistence). This enables powerful chaining.

### Query Result as Bookmark Input

```python
# Run a query, then save it as a Mixpanel report
result = ws.query("Login", math="dau", last=30, group_by="platform")

# The .params dict is a valid bookmark payload
from mixpanel_data import CreateBookmarkParams
bm = ws.create_bookmark(CreateBookmarkParams(
    name="DAU by Platform (30d)",
    bookmark_type="insights",
    params=result.params,
))
```

### DataFrame as Filter Input

```python
# Query 1: Find top countries
top = ws.query("Purchase", group_by="country", mode="total").df
top_countries = top.nlargest(5, "count")["event"].tolist()

# Query 2: Deep dive into top countries only
for country in top_countries:
    detail = ws.query("Purchase", math="average", math_property="revenue",
                       where=Filter.equals("country", country)).df
    print(f"{country}: AOV = ${detail['count'].mean():,.2f}")
```

### Cross-Engine Result Chaining

```python
# Funnel identifies drop-off step
funnel = ws.query_funnel(["Visit", "Signup", "Activate"])
drop_step = funnel.df.loc[funnel.df["step_conv_ratio"].idxmin()]

# Retention measures staying power of those who convert
retention = ws.query_retention(
    drop_step["event"],  # Born event = the step people drop at
    "Login",             # Return event
    retention_unit="week",
)

# Insights measures the volume impact
volume = ws.query(drop_step["event"], math="unique", last=30)
```

---

## Engine Selection Decision Tree

```
Is the question about sequential steps/conversion?
├── YES → query_funnel()
│   Is it about conversion trend over time? → mode="trends"
│   Is it about step-level detail? → mode="steps"
│   Is it about per-step property values? → math="average" + math_property
│
Is the question about users returning over time?
├── YES → query_retention()
│   Same event for born and return? → Stickiness analysis
│   Different events? → Behavioral retention
│   Need custom time buckets? → bucket_sizes=[1,3,7,14,30]
│
Is the question about user paths/sequences?
├── YES → query_flow()
│   After a specific event? → forward > 0
│   Before a specific event? → reverse > 0
│   Top paths view? → mode="paths"
│
Otherwise → query() (Insights)
    Single metric over time? → mode="timeseries"
    Compare segments? → group_by=...
    Combine metrics? → formula="..."
    Per-user metric? → per_user=...
```

---

### Pattern 11: Cohort Behavior Deep Dive

**Question**: "How do power users differ from everyone else?"

| Step | Engine | Query | Purpose |
|------|--------|-------|---------|
| 1 | Discovery | `ws.cohorts()` | Find relevant saved cohorts |
| 2 | Insights | `ws.query("Login", math="dau", group_by=CohortBreakdown(ID, "Power Users"))` | Engagement comparison |
| 3 | Funnels | `ws.query_funnel(steps, group_by=CohortBreakdown(ID, "Power Users"))` | Conversion comparison |
| 4 | Retention | `ws.query_retention(born, ret, group_by=CohortBreakdown(ID, "Power Users"))` | Retention comparison |
| 5 | Flows | `ws.query_flow(event, where=Filter.in_cohort(ID, "Power Users"))` | Path analysis for cohort |
| 6 | Insights | `ws.query([Metric("Login", math="unique"), CohortMetric(ID, "Power Users")], formula="(B/A)*100")` | Cohort share trend |

**Join strategy**: Segment-aligned — CohortBreakdown produces "in" vs "not in" segments across Insights, Funnels, and Retention. Flows uses Filter.in_cohort() since CohortBreakdown is not supported.

### Pattern 12: Custom Property Analysis

**Question**: "Analyze revenue per unit across segments"

| Step | Engine | Query | Purpose |
|------|--------|-------|---------|
| 1 | Discovery | `ws.list_custom_properties()` | Find existing custom properties |
| 2 | Insights | `ws.query("Purchase", group_by=GroupBy(property=InlineCustomProperty.numeric("A/B", A="revenue", B="units"), property_type="number", bucket_size=10))` | Distribution of computed metric |
| 3 | Insights | `ws.query(Metric("Purchase", math="average", property=InlineCustomProperty.numeric("A/B", A="revenue", B="units")), group_by="country")` | Computed metric by segment |
| 4 | Retention | `ws.query_retention("Purchase", "Purchase", group_by=GroupBy(property=CustomPropertyRef(42), property_type="number"))` | Repeat purchase by saved CP |

**Join strategy**: Time-aligned — all queries share the same date range. Custom property breakdowns produce the same segment structure as regular GroupBy breakdowns.
