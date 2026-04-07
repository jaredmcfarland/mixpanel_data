# The Agent That Can Actually Investigate

**Mixpanel's analytical engines are the most powerful primitives in product analytics. The unified query system makes them programmable — turning Claude from a chatbot that answers questions into an analyst that investigates them.**

---

## The Gap

Today's AI analytics tools — including MCP-based chatbots — work one query at a time. A user asks "why did conversion drop?", the chatbot runs a single query, returns a chart, and waits. The user rephrases, the chatbot runs another query. Each round-trip is isolated. There is no memory, no composition, no statistical rigor.

The hard part of analytics isn't running a query. It's knowing which four queries to run, joining the results, and testing a hypothesis — the investigation, not the lookup.

---

## The Breakthrough: Programmable Analytical Engines

`mixpanel_data` exposes Insights, Funnels, Retention, and Flows as **typed, composable Python methods** — the same engines that power Mixpanel's web UI, accessible through keyword arguments that an AI agent can reason about and construct programmatically.

Every query reads like the question it answers:

```python
import mixpanel_data as mp
ws = mp.Workspace()

# "How many daily active users last quarter?"
ws.query("Login", math="dau", last=90)

# "What's our signup-to-purchase conversion?"
ws.query_funnel(["Signup", "Add to Cart", "Purchase"], conversion_window=7)

# "Do users come back after onboarding?"
ws.query_retention("Complete Onboarding", "Login", retention_unit="week", last=90)

# "What do users do after adding to cart?"
ws.query_flow("Add to Cart", forward=3)
```

Four engines. Four methods. Each returns a pandas DataFrame, persistable bookmark params, and engine-specific analysis tools. An agent picks the right engine the same way an analyst would — by the shape of the question.

### Filters, breakdowns, and formulas compose naturally

The building blocks — `Filter`, `GroupBy`, `Metric`, `Formula` — snap together like the UI controls they mirror:

```python
from mixpanel_data import Metric, Filter, GroupBy, Formula

# "Average purchase amount for US iOS users, by revenue bucket"
ws.query(
    "Purchase",
    math="average",
    math_property="amount",
    where=[Filter.equals("country", "US"), Filter.equals("platform", "iOS")],
    group_by=GroupBy("amount", property_type="number", bucket_size=50),
)

# "What % of signups purchase within 30 days? Show me the weekly trend."
ws.query(
    [Metric("Signup", math="unique"), Metric("Purchase", math="unique")],
    formula="(B / A) * 100",
    formula_label="Conversion Rate",
    unit="week",
    last=90,
)
```

Every parameter is typed. Autocomplete works everywhere. 65+ validation rules catch mistakes *before* the API call — no more silent empty results.

### Cohorts defined inline — no UI, no saved state

An agent can describe a user segment in code and query against it immediately:

```python
from mixpanel_data import CohortDefinition, CohortCriteria, CohortBreakdown

# Define "power users" on the fly — no trip to the UI
power_users = CohortDefinition(
    CohortCriteria.did_event("Purchase", at_least=3, within_days=30)
)

# How do power users retain vs. everyone else?
ws.query_retention(
    "Login", "Login",
    group_by=CohortBreakdown(power_users, name="Power Users"),
    retention_unit="week",
)
```

The agent reasons about the segment, defines it, and tests a hypothesis — in a single turn.

### Custom properties computed at query time

Define a formula and use it as if it were a real property — in breakdowns, filters, or aggregations:

```python
from mixpanel_data import InlineCustomProperty, CustomPropertyRef

# Compute revenue per unit on the fly
revenue = InlineCustomProperty.numeric("A * B", A="price", B="quantity")

# "What's the distribution of computed revenue?"
ws.query("Purchase", group_by=GroupBy(property=revenue, property_type="number", bucket_size=100))

# "Average of our saved LTV custom property, by country"
ws.query(Metric("Purchase", math="average", property=CustomPropertyRef(42)), group_by="country")
```

No saved custom property required. No bookmark JSON. The agent just describes the computation.

---

## Side-by-Side: "Why did purchase conversion drop last week?"

<table>
<tr><th width="50%">MCP Chatbot / Raw REST API</th><th width="50%">Unified Query System in Claude Code</th></tr>
<tr>
<td>

**Prompt 1**: "Why did purchase conversion drop?"
*→ Returns a single funnel chart. No segmentation.*

**Prompt 2**: "Break that down by platform"
*→ New chart. User spots mobile is down.*

**Prompt 3**: "Show me mobile retention"
*→ Separate endpoint, separate response format.*

**Prompt 4**: "What paths do mobile users take?"
*→ Requires a saved Flows report in the UI.*

**Prompt 5**: "Is this statistically significant?"
*→ "I can't perform statistical tests."*

5 round-trips. No cross-engine synthesis. No statistical validation. No persistable output.

</td>
<td>

```python
from concurrent.futures import ThreadPoolExecutor
from scipy.stats import ttest_ind

ws = mp.Workspace()

# 1. Query all four engines in parallel
with ThreadPoolExecutor() as pool:
    trend    = pool.submit(ws.query, "Purchase", math="unique", last=60)
    funnel   = pool.submit(ws.query_funnel, ["Browse","Cart","Purchase"], last=60)
    ret      = pool.submit(ws.query_retention, "Purchase", "Purchase", last=60)
    flow     = pool.submit(ws.query_flow, "Cart", forward=3)

# 2. Segment by platform — find the driver
segments = ws.query("Purchase", math="unique", last=60, group_by="platform")

# 3. Confirm statistically
mobile = segments.df[segments.df["event"].str.contains("mobile")]
other  = segments.df[~segments.df["event"].str.contains("mobile")]
t, p = ttest_ind(mobile["count"], other["count"])
# → p=0.003 — the mobile drop is real

# 4. What are mobile users doing instead?
ws.query_flow("Cart", where=Filter.equals("platform", "mobile"), forward=3)

# 5. Save the funnel as a Mixpanel report
ws.create_bookmark(CreateBookmarkParams(
    name="Purchase Drop Investigation",
    bookmark_type="funnels",
    params=funnel.result().params,
))
```

One turn. Four engines. Statistical proof. Saved as a Mixpanel report.

</td>
</tr>
</table>

---

## Why Arb Is the Moat

The unified query system generates **bookmark params** — the native query language of Mixpanel's analytical database. There is no SQL translation layer, no generic query planner. Each method maps directly to a purpose-built engine: Arb's event aggregation, funnel state machine, cohort retention tracker, and path tracer.

No competitor has these primitives. A warehouse-based agent can write SQL against flat event tables, but it cannot express this in a single composable call:

```python
ws.query_funnel(
    ["Browse", "Add to Cart", "Purchase"],
    conversion_window=7,
    holding_constant="platform",        # same device across all steps
    exclusions=["Logout"],              # remove users who logged out
    where=Filter.in_cohort(power_users, name="Power Users"),  # scoped to a cohort
    group_by="country",                 # segmented by geography
)
```

Conversion within 7 days, holding platform constant, excluding logouts, scoped to a behavioral cohort, segmented by country. One call. Mixpanel can express this because Arb was built for it — and now an AI agent can too.

---

## What This Foundation Enables

The four engines, cohort behaviors, and custom properties are the substrate. What comes next:

- **Autonomous investigation** — agent receives a metric alert, runs the full diagnostic across all four engines, produces a root-cause report with statistical evidence
- **Natural language → saved reports** — "Build me a weekly revenue dashboard" → agent constructs queries, validates params, saves as bookmarks, assembles dashboard
- **Self-improving analysis** — agent defines inline cohorts, tests hypotheses, refines iteratively — all in one session, all in code
- **Exportable artifacts** — every investigation produces `.params` JSON that becomes a saved Mixpanel report, closing the loop between AI analysis and human workflow
