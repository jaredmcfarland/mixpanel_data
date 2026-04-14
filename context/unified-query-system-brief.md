# The Agentic Analytics Gap — and How `mixpanel_data` Closes It

**Author:** Jared McFarland | **Date:** April 2026 | **Audience:** Anant Gupta, Engineering & Product Leadership

---

## The Problem Every Analytics Platform Shares

AI agents are rewriting how teams interact with product data. But there's a structural problem across the entire analytics industry: **no product analytics vendor ships a query library for agents to use.**

- **Mixpanel's** Python SDK is write-only. JQL is deprecated. The MCP server is in beta with ~12 tools.
- **PostHog's** Python SDK is write-only. Querying requires hand-rolling HTTP requests against HogQL and parsing raw JSON.
- **Amplitude's** Python SDK is write-only. Their SQL access requires a Snowflake add-on.

Every platform has the same gap: agents can *send* data in, but they cannot *reason about* it programmatically. The official answer from every vendor, including Mixpanel, is either "use the UI" or "export to a warehouse and write SQL."

That's the gap `mixpanel_data` closes — from the client side.

---

## What the Unified Query System Actually Is

Four Python methods. One typed vocabulary. Every query validated before it touches the network.

```python
import mixpanel_data as mp
ws = mp.Workspace()

# Insights: "How many daily active users, by platform, last 90 days?"
result = ws.query("Login", math="dau", group_by="platform", last=90)

# Funnels: "What's the 7-day signup-to-purchase conversion?"
result = ws.query_funnel(["Signup", "Purchase"], conversion_window=7)

# Retention: "Do users come back weekly after onboarding?"
result = ws.query_retention("Onboard", "Login", retention_unit="week")

# Flows: "What do users do after hitting a paywall?"
result = ws.query_flow("Paywall Shown", forward=5, mode="sankey")
```

Each method returns a typed result with a **native pandas DataFrame** (`result.df`), the generated **bookmark params** (`result.params`) for debugging or persistence, and **computed metadata**. Filters, breakdowns, formulas, cohorts, custom properties, time ranges — all shared across engines, all strongly typed, all validated before execution.

Under the hood, these methods construct the same declarative JSON bookmark params that powers Mixpanel's UI reports, then POST them inline. **No temporary entities, no UI round-trips, no raw JSON construction.** The agent writes Python; the library handles the rest.

---

## Why This Is a Competitive Advantage

### No competitor has this. Period.

| Capability | mixpanel\_data | PostHog | Amplitude | Warehouses |
|---|:---:|:---:|:---:|:---:|
| Typed Python query library | **Yes** | No | No | No |
| Native DataFrame returns | **Yes** | No | No | Via connector |
| Analytics primitives as code objects | **Yes** | No | No | No |
| Pre-execution validation | **Yes** | No | No | No |
| Inline cohorts & custom properties | **Yes** | N/A | N/A | N/A |

PostHog offers HogQL (raw SQL over ClickHouse). Amplitude offers Snowflake-native SQL access. Both force agents to **reconstruct analytics concepts from raw tables on every query** — writing complex window functions for funnels, manual cohort bucketing for retention, recursive CTEs for path analysis. These are hard problems. Getting funnel SQL right at scale is notoriously error-prone, and every agent invocation is a fresh attempt.

`mixpanel_data` inverts this: the agent doesn't build analytics from primitives — **it starts from analytics primitives and reasons downward.** A funnel isn't a JOIN; it's `query_funnel(["Signup", "Purchase"])`. Retention isn't a self-join with date arithmetic; it's `query_retention("Signup", "Login")`. The agent stands on the shoulders of Mixpanel's purpose-built product analytics engine and sees further.

### Code-first unlocks what MCP tool-calling cannot

MCP servers — including Mixpanel's own — operate in a request-response loop: one tool call, one result, back to the LLM for the next decision. This is inherently serial and context-heavy.

`mixpanel_data` operates natively inside Python. That means agents can:

- **Run 4 engines in parallel** via `ThreadPoolExecutor` — Insights, Funnels, Retention, and Flows simultaneously
- **Chain queries programmatically** — find the worst funnel step, then trace what users do instead via Flows, then check if that behavior predicts churn via Retention
- **Join results with pandas** — merge DataFrames across engines on date, segment, or cohort
- **Apply statistical testing** — scipy for significance, NetworkX for path graph analysis, all without leaving the runtime
- **Iterate hypotheses in a loop** — segment a metric drop by 6 dimensions in parallel, identify the anomaly, drill deeper, all in one execution

This is the difference between an agent that asks a question and waits, and an agent that *investigates.* The compound effect of parallelization, composition, and iteration is a step change in analytical capability.

---

## What This Unlocks for Mixpanel

### 1. Internal agent capabilities

Mixpanel's own AI agents — whether powering Spark, internal tools, or customer-facing copilots — can use `mixpanel_data` as their query substrate. Instead of building and maintaining internal query-building code, every agent gets typed, validated, DataFrame-native access to all four report types through a single library.

### 2. A better foundation than building a new Query API

The company is planning a new Query API infrastructure built on a stripped-down bookmark language. `mixpanel_data` already parameterizes the *full* bookmark language with strong types and two-layer validation. The library could inform — or even become — the reference implementation for that API. Client-side solutions are arguably *better* for agents than server-side APIs: agents write Python, not cURL.

### 3. Rapid prototyping of new analytical workflows

Because queries are just Python, teams can prototype complex multi-stage analyses — "find churning power users, trace their last 5 sessions, compare their funnel conversion to retained users" — in minutes, not sprints. These prototypes can ship as saved reports, dashboards, or agent capabilities without building new UI.

### 4. Enhancing the MCP server

The existing MCP server's ~12 tools could be backed by `mixpanel_data` instead of raw API calls, immediately gaining validation, richer parameterization, and DataFrame-native results. New tools become trivial to add.

---

## The Bottom Line

The analytics industry is converging on a future where AI agents are the primary interface to product data. Every vendor is racing to build this. But today:

- PostHog gives agents SQL and says "figure it out."
- Amplitude gives agents SQL (via Snowflake) and says "figure it out."
- Mixpanel, without `mixpanel_data`, gives agents a beta MCP server and says "we're working on it."

`mixpanel_data` gives agents **typed analytics primitives, native DataFrames, validated queries, and the full power of Python's ecosystem** — all running on top of a database purpose-built for exactly these questions. Funnels, retention, flows, and segmentation aren't reconstructed from raw data on every query. They're first-class objects an agent can reason about, compose, parallelize, and iterate on.

No other product analytics platform offers anything like this. Not as an official product, not as a community library, not as a roadmap item. This is a genuine competitive moat — and it's ready now.
