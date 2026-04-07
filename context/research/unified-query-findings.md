# Unified Query System — Research Findings

*Research date: 2026-04-07*
*Sources: Mixpanel REST API Reference (developer.mixpanel.com), Mixpanel MCP Server docs (docs.mixpanel.com/docs/mcp), mixpanel_data internal specifications*

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Raw REST API Experience — Endpoint by Endpoint](#2-the-raw-rest-api-experience--endpoint-by-endpoint)
3. [What the Current Mixpanel MCP Server Can and Cannot Do](#3-what-the-current-mixpanel-mcp-server-can-and-cannot-do)
4. [Cognitive Overhead for LLM Agents](#4-cognitive-overhead-for-llm-agents)
5. [Key Pain Points](#5-key-pain-points)
6. [What the Unified Query System Changes](#6-what-the-unified-query-system-changes)
7. [Appendix: Raw JSON Payload Examples](#7-appendix-raw-json-payload-examples)

---

## 1. Executive Summary

An LLM agent trying to perform product analytics against Mixpanel today faces a fragmented, under-documented, and error-prone landscape:

- **9+ separate API endpoint families** with inconsistent authentication, parameter formats, and response shapes
- **Two incompatible query paradigms** — legacy GET-parameter endpoints and modern bookmark-JSON endpoints — with no documentation explaining when to use which
- **A proprietary expression language** for filters (`properties["x"] == "y"`) that must be string-encoded into URL parameters, with no schema and no validation
- **Silent failures** — invalid queries frequently return empty results or wrong aggregations rather than error messages
- **Rate limits of 60 queries/hour** with no retry guidance and opaque error responses
- **The MCP server** provides 23 tools but abstracts away query construction entirely — the agent cannot inspect, modify, compose, or validate queries

The `mixpanel_data` unified query system eliminates this complexity with typed Python objects, 65+ client-side validation rules, four engine-specific builders, and first-class result types with DataFrame integration.

---

## 2. The Raw REST API Experience — Endpoint by Endpoint

### 2.1 API Organization and Base URLs

Mixpanel's API is split across **6 different base URL patterns** depending on function and region:

| Function | US Base URL | EU Base URL | India Base URL |
|----------|-------------|-------------|----------------|
| Query API | `mixpanel.com/api/2.0` | `eu.mixpanel.com/api/2.0` | `in.mixpanel.com/api/2.0` |
| Bookmark Query | `mixpanel.com/api/query` | `eu.mixpanel.com/api/query` | `in.mixpanel.com/api/query` |
| Event Export | `data.mixpanel.com/api/2.0` | `data-eu.mixpanel.com/api/2.0` | N/A |
| Ingestion | `api.mixpanel.com` | `api-eu.mixpanel.com` | `api-in.mixpanel.com` |
| App API (CRUD) | `mixpanel.com/api/app` | `eu.mixpanel.com/api/app` | `in.mixpanel.com/api/app` |
| Feature Flags | `api.mixpanel.com/flags` | `api-eu.mixpanel.com/flags` | `api-in.mixpanel.com/flags` |
| MCP Server | `mcp.mixpanel.com/mcp` | `mcp-eu.mixpanel.com/mcp` | `mcp-in.mixpanel.com/mcp` |

An agent must select the correct base URL based on (a) what it's trying to do and (b) which region the customer's project is in. There is no unified entry point.

### 2.2 Authentication Schemes

Four different authentication methods, each used by different endpoints:

| Method | Format | Used By |
|--------|--------|---------|
| **Service Account** (recommended) | HTTP Basic: `base64(username:secret)` | Query API, Export API, Lexicon, Annotations |
| **Project Token** | URL param or body field `token=...` | Ingestion (/track), Identity, Feature Flags, GDPR |
| **Project Secret** (legacy) | HTTP Basic: `base64(secret:)` — note empty password | Some Export endpoints, Feature Flags |
| **OAuth 2.0 Bearer** | `Authorization: Bearer <token>` | GDPR API, App API, MCP Server |

Key gotcha: Service Account auth requires passing `project_id` as a query parameter. Project Secret auth does not. The agent must know which auth method is in use to decide whether to include `project_id`. Getting this wrong produces a 401 with no explanation.

### 2.3 Segmentation Endpoint (Insights)

**Endpoint**: `GET /api/2.0/segmentation` (legacy) or `GET /api/query/insights` (bookmark-based)

#### Legacy Endpoint

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `event` | string | Yes | Single event name only |
| `from_date` | string | Yes | `YYYY-MM-DD` format |
| `to_date` | string | Yes | `YYYY-MM-DD` format |
| `type` | string | No | `general`, `unique`, `average` — only 3 options |
| `unit` | string | No | `minute`, `hour`, `day`, `week`, `month` |
| `on` | string | No | Property expression for segmentation (custom syntax) |
| `where` | string | No | Filter expression (custom syntax) |
| `limit` | integer | No | Default 60, max 10,000 — but does nothing without `on` |

**Response shape**:
```json
{
  "data": {
    "series": ["2024-01-01", "2024-01-02"],
    "values": {
      "Login": {"2024-01-01": 100, "2024-01-02": 150}
    }
  },
  "legend_size": 1
}
```

**What's missing from legacy**: DAU/WAU/MAU, percentile aggregations, per-user math, formulas, rolling averages, cumulative analysis, custom properties, cohort-based filtering, multiple events per query. The legacy endpoint supports roughly 3 of the 14+ measurement types available in the Mixpanel UI.

#### Bookmark-Based Endpoint

`GET /api/query/insights` requires `bookmark_id` — a pre-saved report. You cannot construct an ad-hoc query. To run an ad-hoc query via the modern engine, you must:

1. Construct bookmark params JSON (deeply nested, undocumented schema)
2. POST to create a bookmark via the App API
3. GET the bookmark query results
4. Optionally DELETE the bookmark

This is a 3-step process for a single query, requiring two different auth methods (App API uses OAuth, Query API uses Basic Auth).

### 2.4 Funnel Endpoint

**Endpoint**: `GET /api/2.0/funnels`

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `funnel_id` | integer | **Yes** | Must reference a pre-saved funnel |
| `from_date` | string | Yes | `YYYY-MM-DD` |
| `to_date` | string | Yes | `YYYY-MM-DD` |
| `length` | integer | No | Conversion window (max 90 days) |
| `length_unit` | string | No | `second`, `minute`, `hour`, `day` |
| `unit` | string | No | `day`, `week`, `month` |
| `on` | string | No | Segment by property |
| `where` | string | No | Filter expression |
| `limit` | integer | No | Max 10,000, requires `on` |

**Critical limitation**: The agent **cannot define funnel steps ad-hoc** via the REST API. It must use a pre-saved `funnel_id`. To run an ad-hoc funnel:
1. Create a bookmark with funnel steps via App API (OAuth)
2. Query it via the bookmark query endpoint
3. Parse the completely different response format

**Response shape** (legacy):
```json
{
  "meta": {"dates": ["2024-01-01"]},
  "data": {
    "2024-01-01": {
      "steps": [
        {
          "count": 32688, "avg_time": 2, "avg_time_from_start": 5,
          "step_conv_ratio": 1.0, "overall_conv_ratio": 1.0,
          "goal": "App Open", "event": "App Open"
        }
      ],
      "analysis": {
        "completion": 20524, "starting_amount": 32688,
        "steps": 2, "worst": 1
      }
    }
  }
}
```

Note: The response nests steps inside date keys, with different field names (`step_conv_ratio` vs `overall_conv_ratio`) and an `analysis` sub-object. This is entirely different from the segmentation response format.

### 2.5 Retention Endpoint

**Endpoint**: `GET /api/2.0/retention`

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `from_date` | string | Yes | `YYYY-MM-DD` |
| `to_date` | string | Yes | `YYYY-MM-DD` |
| `retention_type` | string | No | `birth` or `compounded` |
| `born_event` | string | No | Required for `birth` type — but not validated |
| `event` | string | No | Return event |
| `born_where` | string | No | Filter for born event (expression syntax) |
| `where` | string | No | Filter for return event |
| `interval` | integer | No | Units per bucket |
| `interval_count` | integer | No | Number of buckets |
| `unit` | string | No | `day`, `week`, `month` |
| `unbounded_retention` | boolean | No | Accumulates right-to-left |
| `on` | string | No | Segment by property |

**Response shape** (third different format):
```json
{
  "2024-01-01": {
    "counts": [1000, 800, 600, 400],
    "first": 1000
  },
  "2024-01-02": {
    "counts": [900, 700, 500],
    "first": 950
  }
}
```

**Gotchas**:
- `born_event` is required when `retention_type=birth` but the server doesn't validate — it silently returns empty data
- The 0th element of `counts` represents users retained within the first interval, not on day 0
- `unbounded_retention` changes the semantics of the counts array but the response structure is identical — the agent cannot tell from the response which mode was used
- No percentage values in the legacy response — the agent must compute `counts[i] / first` manually

### 2.6 Rate Limits and Throttling

| API | Rate Limit | Concurrent | Timeout |
|-----|-----------|------------|---------|
| Query API (all endpoints) | 60/hour | 5 concurrent | 10 seconds |
| Event Export | 60/hour, 3/second | 100 concurrent | — |
| Ingestion | 2 GB/minute | 10-20 clients | — |
| Lexicon Schemas | 5/minute | — | — |
| GDPR | 1/second | — | — |
| MCP Server | 600/hour | — | — |

**Error response for rate limiting**: The documentation does not specify the response format for 429 errors. In practice, the server returns either:
- HTTP 429 with no body
- HTTP 429 with `{"error": "Rate limit exceeded", "status": 0}`
- HTTP 402 (yes, 402) with `"Too many requests"` in some older endpoints

There is no `Retry-After` header. The agent must implement its own backoff.

### 2.7 Error Handling

Mixpanel's error responses are inconsistent across APIs:

**Query API errors**:
```json
// 400 Bad Request — but often with no useful message
{"error": "Invalid request", "request": "/api/2.0/segmentation?..."}

// 401 — inconsistent format
{"error": "not authenticated", "request": null}
// or just
"Unauthorized"

// 500 — opaque
{"error": "An internal error occurred", "request": null}
```

**Ingestion API errors** (completely different format):
```json
// verbose=1
{"status": 0, "error": "Invalid token"}

// strict=1 with partial failures
{
  "code": 400,
  "num_records_imported": 1999,
  "status": "Bad Request",
  "failed_records": [{"index": 0, "field": "properties.time", "message": "'properties.time' is invalid"}]
}
```

**App API errors** (yet another format):
```json
{"status": "error", "error": "Forbidden", "details": "..."}
```

An agent must handle at least 4 different error response formats.

### 2.8 The Expression Language

Filter and segmentation expressions use a proprietary syntax that must be string-encoded into URL parameters:

```
properties["browser"] == "Chrome"
properties["age"] > 18 and properties["country"] in ["US", "UK"]
defined(properties["email"]) and not (properties["status"] in ["deleted"])
```

**Pain points for agents**:
- No JSON schema — the syntax is documented only by examples
- String quoting rules are ambiguous (double quotes inside URL-encoded strings)
- Property names with special characters require escaping but the escaping rules are undocumented
- Date functions (`datetime(2024, 1, 1)`) have a different signature than any standard date library
- Type coercion is implicit and sometimes surprising
- Invalid expressions return empty results rather than errors

---

## 3. What the Current Mixpanel MCP Server Can and Cannot Do

### 3.1 Available Tools (23 total)

**Analytics (3 tools)**:
| Tool | What It Does | Limitations |
|------|-------------|-------------|
| `Run-Query` | Execute insights, funnels, flows, retention | Accepts structured params; agent must construct or the MCP server translates NL |
| `Get-Query-Schema` | Get the JSON schema for query construction | Returns the schema but agent still must build valid JSON |
| `Get-Report` | Retrieve a saved report with optional results | Read-only; cannot modify or compose |

**Dashboard Management (6 tools)**:
| Tool | What It Does |
|------|-------------|
| `Create-Dashboard` | Create dashboard with text cards and reports |
| `List-Dashboards` | Browse dashboards |
| `Get-Dashboard` | Get metadata, cards, reports |
| `Update-Dashboard` | Modify metadata and layout |
| `Duplicate-Dashboard` | Copy a dashboard |
| `Delete-Dashboard` | Delete a dashboard |

**Data Discovery (7 tools)**:
| Tool | What It Does |
|------|-------------|
| `Get-Projects` | List projects and workspaces |
| `Get-Events` | Browse events |
| `Get-Property-Names` | Explore properties for events or users |
| `Get-Property-Values` | Discover values for a property |
| `Get-Event-Details` | Full event metadata |
| `Get-Issues` | Data quality issues |
| `Get-Lexicon-URL` | Direct link to Lexicon |

**Data Management (6 tools)**:
| Tool | What It Does |
|------|-------------|
| `Edit-Event` | Update event description, display name, tags, visibility |
| `Edit-Property` | Update property metadata and PII classification |
| `Create-Tag` / `Rename-Tag` / `Delete-Tag` | Tag management |
| `Dismiss-Issues` | Bulk-dismiss data quality issues |

**Session Replay (1 tool)**:
| Tool | What It Does |
|------|-------------|
| `Get-User-Replays-Data` | Analyze user replays with event data |

### 3.2 What the MCP Server Cannot Do

| Capability | Available? | Impact |
|-----------|-----------|--------|
| Multi-step analysis (query A results → parameterize query B) | No | Cannot do root cause analysis, hypothesis testing |
| Local computation on results (pandas, scipy, numpy) | No | Cannot join datasets, run statistics, detect anomalies |
| Parallel query execution | No | Sequential only; 6-query analysis takes 6 round-trips |
| Custom property formulas at query time | Not documented | Cannot compute derived metrics |
| Inline cohort definitions | Not documented | Cannot scope queries to ad-hoc user segments |
| Query param inspection and modification | No | Opaque — agent cannot see or modify the generated query |
| Client-side validation before execution | No | Errors surface only after server round-trip |
| Persist queries as Mixpanel reports | Partial (dashboards only) | Cannot save a query as a bookmark for later use |
| Cross-engine result composition | No | Cannot merge insights + funnel + retention into one analysis |
| Flow graph algorithms | No | No NetworkX integration, no path analysis |
| Streaming/export raw events | No | Cannot access raw event data |
| Cohort CRUD | No | Cannot create or manage cohorts |
| Feature flag management | No | Cannot manage experiments or flags |
| Webhook/alert management | No | Cannot configure alerts or webhooks |

### 3.3 Rate Limits and Access Control

- **600 requests/hour per user** (10x the raw Query API's 60/hour — a significant improvement)
- OAuth authentication via existing Mixpanel credentials
- All project permissions and roles apply
- Org admin must enable MCP access globally before any user can connect
- **Not HIPAA-compliant** — data is sent to the connected AI provider
- MCP server is read/write — connected AI assistants can modify dashboards, events, and properties

### 3.4 The Fundamental MCP Limitation

The MCP server is a **request-response proxy**. The agent sends a question, gets back a result. It cannot:

1. **Compose** — combine results from multiple queries into a unified analysis
2. **Inspect** — see the query that was generated, modify it, learn from it
3. **Validate** — check query correctness before execution
4. **Iterate** — use one result to parameterize the next query programmatically
5. **Compute** — run local statistical tests, ML models, or graph algorithms on results

This means the MCP server is useful for **single-question lookups** ("What was DAU last week?") but inadequate for **multi-step analytical workflows** ("Why did conversion drop, and what segments are driving it?").

---

## 4. Cognitive Overhead for LLM Agents

### 4.1 Knowledge Requirements — Raw REST API

To use the raw REST API, an agent must internalize:

| Knowledge Area | Items to Learn | Error Mode |
|---------------|---------------|------------|
| Base URL selection | 6 URL patterns x 3 regions = 18 URLs | Wrong URL → 404 or wrong region's data |
| Auth scheme selection | 4 methods, each for different endpoints | Wrong auth → 401, often no error message |
| Parameter formatting | Expression language syntax, date formats, JSON encoding | Invalid expression → empty results (silent) |
| Response parsing | 4+ different response shapes across endpoints | Wrong parser → crash or wrong data |
| Error handling | 4+ error response formats | Unhandled error → agent hallucinates |
| Rate limit management | Per-endpoint limits, no Retry-After header | 429 → must implement backoff blindly |
| Legacy vs modern endpoints | When to use `/segmentation` vs `/query/insights` | Wrong choice → missing features or extra complexity |
| Funnel pre-requisites | Funnels require saved funnel_id (legacy) or bookmark creation (modern) | No ad-hoc funnels → 3-step workflow |

**Estimated context tokens**: An agent needs ~8,000-12,000 tokens of API documentation in context to reliably construct queries across all four engines. This is before any user data or conversation history.

### 4.2 Multi-Step Analysis Workflow — Without Library

A common analytics question: *"Why did our signup-to-purchase conversion drop last week?"*

**Steps an agent must execute manually**:

1. **Determine auth** — resolve service account credentials, base64-encode, select correct base URL for region
2. **Discover schema** — GET `/events/names` to find relevant events, GET `/events/properties/top` to find properties
3. **Run funnel query** — but funnels require `funnel_id`, so:
   a. Find existing funnel via GET `/funnels/list`
   b. If no matching funnel exists, create a bookmark via App API (different auth)
   c. Query the bookmark
4. **Run segmentation queries** — one per property to segment by (platform, country, etc.)
5. **Parse 3+ different response formats** — funnel format vs segmentation format
6. **Compute deltas manually** — subtract last week's values from this week's, calculate percentage changes
7. **Identify significant segments** — no statistical testing available, agent must eyeball
8. **Synthesize findings** — correlate across queries manually

**Total API calls**: 8-15 calls across 3+ auth methods and 2+ response formats
**Failure modes**: 12+ points where silent failures can produce wrong conclusions

### 4.3 Multi-Step Analysis — With Unified Query System

The same analysis:

```python
import mixpanel_data as mp
from concurrent.futures import ThreadPoolExecutor

ws = mp.Workspace()

# 4 parallel queries, typed, validated before execution
with ThreadPoolExecutor(max_workers=4) as pool:
    funnel = pool.submit(ws.query_funnel,
        steps=[("Signup", {}), ("Purchase", {})],
        from_date="2025-03-24", to_date="2025-03-30")
    funnel_prev = pool.submit(ws.query_funnel,
        steps=[("Signup", {}), ("Purchase", {})],
        from_date="2025-03-17", to_date="2025-03-23")
    by_platform = pool.submit(ws.query_funnel,
        steps=[("Signup", {}), ("Purchase", {})],
        from_date="2025-03-24", to_date="2025-03-30",
        group_by=[GroupBy.property("platform")])
    by_country = pool.submit(ws.query_funnel,
        steps=[("Signup", {}), ("Purchase", {})],
        from_date="2025-03-24", to_date="2025-03-30",
        group_by=[GroupBy.property("country")])

# All results are typed DataFrames — merge with pandas
import pandas as pd
delta = funnel.result().df.merge(funnel_prev.result().df, ...)
significant = by_platform.result().df[by_platform.result().df["conversion_rate"] < 0.5]
```

**Total API calls**: 4 (parallel)
**Failure modes**: 0 silent failures — validation catches errors before execution
**Agent context needed**: ~2,000 tokens of Python function signatures

---

## 5. Key Pain Points

### 5.1 Untyped JSON Everywhere

The REST API communicates entirely in untyped JSON. There is no OpenAPI/Swagger spec for the query endpoints. The bookmark params JSON schema is not published. An agent must learn the schema from examples and hope for the best.

**Specific problems**:
- Field names are inconsistent: `filterType` vs `propertyType` vs `defaultType` in the same object
- Enum values are undocumented: `"is greater than"` vs `"greater_than"` vs `"gt"` — which does the server accept?
- Singular vs plural conventions: `resourceType: "event"` inside `composedProperties` but `resourceType: "events"` at the filter level — this is an **undocumented server requirement** that causes silent failures
- Nested objects have no schema: the `customProperty` object inside a filter entry has ~8 fields, none documented

### 5.2 Multiple Auth Schemes

An agent building a complete analytics workflow must juggle:
- Basic Auth (service account) for queries
- OAuth Bearer for App API CRUD
- Project Token for ingestion
- Different `project_id` parameter requirements per auth method

There is no unified auth story. The MCP server helps here (OAuth only) but limits the agent to MCP's 23 tools.

### 5.3 Separate Endpoints Per Query Type

Each analytical engine has its own endpoint with its own parameter set and response format:

| Engine | Endpoint | Params | Response Shape |
|--------|----------|--------|---------------|
| Segmentation | `/segmentation` | `event`, `on`, `where`, `type` | `{data: {series: [], values: {}}}` |
| Funnels | `/funnels` | `funnel_id`, `length`, `length_unit` | `{data: {"date": {steps: [], analysis: {}}}}` |
| Retention | `/retention` | `born_event`, `event`, `retention_type` | `{"date": {counts: [], first: N}}` |
| Insights (bookmark) | `/query/insights` | `bookmark_id` | `{series: {}, headers: [], computed_at: ""}` |

Four endpoints, four parameter sets, four response parsers. The agent must maintain four separate code paths.

### 5.4 Manual Date Handling

- All dates must be `YYYY-MM-DD` strings — no relative date support ("last 7 days")
- No timezone specification — dates are interpreted in the project's timezone (which the agent must know)
- The retention endpoint silently extends the query window beyond `to_date` to find retained users — the response may include data outside the requested range
- The funnel endpoint queries beyond `to_date` to identify completions within the conversion window
- Time comparison features ("this week vs last week") require the agent to compute both date ranges manually

### 5.5 No Client-Side Validation

The REST API performs minimal server-side validation. Common failure modes:

| Mistake | What Happens | What Should Happen |
|---------|-------------|-------------------|
| Wrong `type` value in segmentation | Silently uses default (`general`) | Error: "Invalid type 'foo', expected general/unique/average" |
| Missing `born_event` in birth retention | Returns empty data | Error: "born_event required when retention_type=birth" |
| Invalid `where` expression | Returns empty results or 500 | Error: "Syntax error in expression at position 15" |
| Wrong `resourceType` in bookmark JSON | Returns wrong data or empty | Error: "resourceType must be 'events' at filter level" |
| `funnel_id` that doesn't exist | 404 with no context | Error: "Funnel 12345 not found in project" |
| `on` property that doesn't exist | Returns empty segmentation | Error: "Property 'foo' not found for event 'Bar'" |

### 5.6 Opaque Error Messages

When the server does return errors, they are frequently unhelpful:

```
{"error": "An internal error occurred"}           ← no context
{"error": "Invalid request"}                       ← what's invalid?
{"error": "not authenticated"}                     ← which auth method was expected?
"Unauthorized"                                     ← not even JSON
{"status": 0, "error": "Invalid token"}            ← different format, same endpoint family
```

The agent cannot self-correct because the error provides no guidance on what to fix.

### 5.7 Undocumented Conventions and Gotchas

Discovered through implementation experience:

1. **`resourceType` singular vs plural**: Inside `composedProperties`, use `"event"`. At the filter/group level, use `"events"`. No documentation explains this.

2. **Custom properties in funnels/retention**: The server has a bug where custom property filters in funnel and retention queries require a different JSON structure than in insights queries. The `resourceType` field must be propagated differently.

3. **Cohort filters**: Filtering by cohort requires a `$cohorts` property name with special `filterOperator` values (`"is equal to"` for inclusion, `"is not equal to"` for exclusion) and `filterValue` set to the cohort ID as a string. None of this is documented.

4. **The `limit` parameter**: Does nothing unless `on` is specified. No warning or error.

5. **The `interval` vs `unit` parameters**: Mutually exclusive in some endpoints, complementary in others. No documentation clarifies which.

6. **Bookmark `queryGenerationMode`**: Must be set to `"segmentation"` for insights, but this is not the same as the `/segmentation` endpoint. Confusing naming.

7. **Empty `meta.dates` array**: In funnel responses, the dates array in `meta` may not match the dates in `data`. The agent must use `data` keys, not `meta.dates`.

---

## 6. What the Unified Query System Changes

### 6.1 The Complete API Surface

The `mixpanel_data` library exposes four typed query methods mapping to Mixpanel's four analytical engines, plus cross-cutting cohort and custom property capabilities:

| Method | Engine | Question It Answers | Key Capabilities |
|--------|--------|-------------------|-----------------|
| `ws.query()` | Insights/Arb | "How much? How many?" | 14 MathTypes (DAU/WAU/MAU, percentiles, per-user), formulas, rolling/cumulative, 3 display modes |
| `ws.query_funnel()` | Funnels | "Do users convert?" | Ad-hoc steps (no saved funnel needed), per-step filters, exclusions, holding constant, session conversion |
| `ws.query_retention()` | Retention | "Do users come back?" | Born/return event pairs, custom buckets, birth/interval alignment, 3 display modes |
| `ws.query_flow()` | Flows | "What paths do users take?" | Forward/reverse tracing, NetworkX DiGraph, anytree integration |

**Cross-cutting capabilities**:
- **Cohort scoping**: `Filter.in_cohort()` / `Filter.not_in_cohort()` — works in all 4 engines
- **Cohort breakdowns**: `CohortBreakdown` — segment by cohort membership
- **Custom properties**: `CustomPropertyRef(id)` or `InlineCustomProperty.numeric("A*B", A="price", B="qty")` — works in filters, group_by, and measurements
- **18 typed filter methods**: `equals`, `greater_than`, `between`, `is_set`, `is_true`, `in_the_last`, `date_between`, etc.

### 6.2 Typed/Validated Python vs. Raw REST JSON

| Dimension | Raw REST API | Unified Query System |
|-----------|-------------|---------------------|
| Query construction | Hand-craft nested JSON or expression strings | Typed Python keyword arguments |
| Validation | None client-side; silent failures | 65+ rules (V-series, B-series, CP-series) catch errors before API call |
| Filters | `properties["x"] == "y"` as URL-encoded string | `Filter.equals("x", "y")` with type checking |
| Custom properties | 3 different JSON structures, undocumented conventions | `InlineCustomProperty.numeric("A*B", A="price", B="qty")` |
| Cohort scoping | Manual `$cohorts` magic values | `Filter.in_cohort(definition)` |
| Error messages | `{"error": "Invalid request"}` | `ValidationError(code="V-023", message="...", fix="...")` |
| Response parsing | 4 different formats, manual extraction | Frozen dataclasses with `.df` (pandas), `.to_dict()` |
| Ad-hoc funnels | Impossible via REST; 3-step bookmark workflow | `ws.query_funnel(steps=[...])` — one call |
| Parallel execution | Manual threading with 4 different parsers | `ThreadPoolExecutor` — all queries return typed results |

### 6.3 How It Maps to Arb's Native Data Model

The unified query system generates **bookmark params JSON** — the same format the Mixpanel web UI uses internally. This means:

1. **Full feature parity** with the web UI — anything the UI can query, the library can query
2. **No SQL translation layer** — direct access to Arb's purpose-built analytical primitives
3. **Persistable queries** — `result.params` can be saved as Mixpanel reports via `create_bookmark()`

### 6.4 What This Enables for LLM Agents

| Pattern | Without Library | With Library |
|---------|----------------|-------------|
| "Why did X drop?" | 6+ sequential API calls, 3+ auth methods, manual computation | 4 parallel typed queries → pandas merge → scipy t-test |
| Multi-metric dashboard | Multiple endpoints, different response parsers | `ThreadPoolExecutor` with 6 concurrent queries, all returning DataFrames |
| Hypothesis testing | Manual prompt refinement across multiple MCP calls | Query results parameterize follow-up queries programmatically |
| Cross-engine analysis | Impossible — different response formats | `pd.merge()` on shared date/segment keys |
| Flow graph analysis | Not available via REST or MCP | `result.graph` (NetworkX) → betweenness centrality, shortest paths |
| Statistical significance | Agent must compute manually from raw numbers | `scipy.stats.ttest_ind()` on result DataFrames |

### 6.5 The Local Python Ecosystem Advantage

With the unified query system, the agent has the full scientific Python stack:

| Library | What It Enables |
|---------|----------------|
| **pandas** | DataFrame joins, pivots, rolling calculations, time-series resampling |
| **scipy** | Statistical significance testing (t-test, chi-squared, Mann-Whitney) |
| **NetworkX** | Graph algorithms on flow data (betweenness centrality, shortest path, community detection) |
| **anytree** | Tree traversal on flow trees (parent references, Graphviz export) |
| **matplotlib/seaborn** | Retention heatmaps, funnel waterfalls, flow Sankey diagrams |
| **numpy** | Correlation matrices, trend detection, anomaly scoring |

None of this is possible through REST API calls or MCP tool invocations alone.

---

## 7. Appendix: Raw JSON Payload Examples

### 7.1 Bookmark Params JSON for a Simple Insights Query

"Show me daily Purchase event count, filtered to US, broken down by platform"

```json
{
  "bookmark": {
    "sections": {
      "show": [{
        "behavior": {
          "type": "event",
          "event": {"name": "Purchase"}
        },
        "measurement": {
          "math": "total",
          "property": null,
          "perUserAggregation": null
        }
      }],
      "filter": [{
        "resourceType": "events",
        "filterType": "string",
        "defaultType": "string",
        "value": "country",
        "filterValue": "US",
        "filterOperator": "equals",
        "dataset": "$mixpanel"
      }],
      "group": [{
        "resourceType": "events",
        "propertyType": "string",
        "typeCast": null,
        "value": "platform",
        "propertyName": "platform"
      }],
      "time": [{
        "dateRangeType": "between",
        "unit": "day",
        "value": ["2025-03-01", "2025-03-31"]
      }]
    },
    "displayOptions": {
      "chartType": "line",
      "plotStyle": "standard",
      "analysis": "linear",
      "value": "absolute"
    }
  },
  "queryGenerationMode": "segmentation"
}
```

**~40 lines of JSON** for a query that the unified system expresses as:

```python
ws.query(
    event="Purchase",
    filters=[Filter.equals("country", "US")],
    group_by=[GroupBy.property("platform")],
    from_date="2025-03-01",
    to_date="2025-03-31",
)
```

### 7.2 Inline Custom Property in a Filter

"Filter to orders where price * quantity > 1000"

```json
{
  "resourceType": "events",
  "filterType": "number",
  "defaultType": "number",
  "customProperty": {
    "displayFormula": "A * B",
    "composedProperties": {
      "A": {"value": "price", "type": "number", "resourceType": "event"},
      "B": {"value": "quantity", "type": "number", "resourceType": "event"}
    },
    "name": "",
    "description": "",
    "propertyType": "number",
    "resourceType": "events"
  },
  "dataset": "$mixpanel",
  "filterValue": 1000,
  "filterOperator": "is greater than"
}
```

Note the `resourceType: "event"` (singular) inside `composedProperties` vs `resourceType: "events"` (plural) at the filter level and inside `customProperty`. This undocumented convention causes silent failures.

**Equivalent unified system call**:

```python
cp = InlineCustomProperty.numeric("A * B", A="price", B="qty")
filters = [Filter.greater_than(cp, 1000)]
```

### 7.3 Cohort-Scoped Funnel with Custom Properties

"Show signup-to-purchase conversion for the 'Power Users' cohort, broken down by computed LTV tier"

This requires constructing a bookmark with:
- Funnel steps array (2 entries)
- Cohort filter entry with `$cohorts` magic property
- Custom property group-by with `composedProperties`
- Funnel-specific display options

The bookmark JSON for this query is **~120 lines**. The equivalent unified system call is **~8 lines** of typed Python.

---

*This research was conducted to inform the strategic positioning of the `mixpanel_data` unified query system relative to the raw Mixpanel REST API and MCP server.*
