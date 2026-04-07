# The Agent That Can Actually Investigate

**Mixpanel's analytical engines are the most powerful primitives in product analytics. The unified query system makes them programmable — turning Claude from a chatbot that answers questions into an analyst that investigates them.**

---

## The Gap

Today's AI analytics tools — including MCP-based chatbots — work one query at a time. A user asks "why did conversion drop?", the chatbot runs a single query, returns a chart, and waits. The user rephrases, the chatbot runs another query. Each round-trip is isolated. There is no memory, no composition, no statistical rigor.

The hard part of analytics isn't running a query. It's knowing which four queries to run, joining the results, and testing a hypothesis — the investigation, not the lookup.

---

## The Breakthrough: Programmable Analytical Engines

`mixpanel_data` exposes Insights, Funnels, Retention, and Flows as **typed, composable Python methods** — the same engines that power Mixpanel's web UI, accessible through keyword arguments that an AI agent can reason about and construct programmatically.

An agent using this system can:

- **Choose the right engine** for each sub-question (DAU trend → Insights, conversion check → Funnels, churn signal → Retention, path divergence → Flows)
- **Run queries in parallel** across engines, merge on shared dimensions with pandas
- **Define cohorts inline** — describe a user segment in code, query against it immediately, no UI round-trip
- **Compute derived properties at query time** — define a formula like `price * quantity` and use it as a breakdown, filter, or aggregation target
- **Validate before executing** — 65+ client-side rules catch silent-failure scenarios before the API call
- **Apply the full scientific Python stack** — scipy for significance tests, NetworkX for path graph analysis, matplotlib for visualization

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
# One autonomous investigation
ws = mp.Workspace()

# 1. Quantify across 4 engines (parallel)
results = parallel({
  "trend": ws.query("Purchase", math="unique", last=60),
  "funnel": ws.query_funnel(["Browse","Cart","Purchase"], last=60),
  "retention": ws.query_retention("Purchase","Purchase", last=60),
  "flow": ws.query_flow("Cart", forward=3),
})

# 2. Segment the drop
for dim in ["platform","country","utm_source"]:
    ws.query("Purchase", last=60, group_by=dim)

# 3. Statistical test on the leading segment
from scipy.stats import ttest_ind
# → p=0.003, mobile drop is significant

# 4. Trace where mobile users go instead
ws.query_flow("Cart",
    where=Filter.equals("platform","mobile"),
    forward=3)

# 5. Save the investigation as a report
ws.create_bookmark(CreateBookmarkParams(
    name="Purchase Drop Investigation",
    params=results["funnel"].params))
```

One turn. Four engines. Statistical proof. Persistable.

</td>
</tr>
</table>

---

## Why Arb Is the Moat

The unified query system generates **bookmark params** — the native query language of Mixpanel's analytical database. There is no SQL translation layer, no generic query planner. Each method maps directly to a purpose-built engine: Arb's event aggregation, funnel state machine, cohort retention tracker, and path tracer.

No competitor has these primitives. A warehouse-based agent can write SQL against flat event tables, but it cannot express "conversion within 7 days, holding platform constant, excluding users who logged out between steps" in a single composable call. Mixpanel can — and now an AI agent can too.

---

## What This Foundation Enables

The four engines, cohort behaviors, and custom properties are the substrate. What comes next:

- **Autonomous investigation protocols** — agent receives a metric alert, runs the full diagnostic, produces a root-cause report with statistical evidence
- **Natural language → saved reports** — "Build me a weekly revenue dashboard" → agent constructs queries, validates params, saves as bookmarks, assembles dashboard
- **Self-improving analysis** — agent uses query results to define inline cohorts, tests hypotheses against them, refines iteratively — all in a single session
- **Exportable analytical artifacts** — every investigation produces `.params` JSON that can become a saved Mixpanel report, closing the loop between AI analysis and human workflow
