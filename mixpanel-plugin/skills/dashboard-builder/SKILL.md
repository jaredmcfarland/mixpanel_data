---
name: dashboard-builder
description: Build, design, and manage Mixpanel dashboards with professional layouts, text cards, and multi-report sections. Use when the user asks to build, create, make, set up, or assemble a dashboard, or when they ask about dashboard layout, text cards, or report arrangement. Provides design templates, layout rules, text card formatting, and end-to-end workflows from data investigation through dashboard assembly.
allowed-tools: Bash Read Write
---

# Dashboard Builder

Build production-quality Mixpanel dashboards through a 6-phase workflow: investigate data, plan structure, build reports, create dashboard with layout, add explainers, then polish and verify.

## Quick Start Example

A minimal 3-report dashboard with proper layout:

```python
import mixpanel_data as mp
from mixpanel_data.types import (
    CreateDashboardParams, DashboardRow, DashboardRowContent,
)
import json

ws = mp.Workspace()

# 1. Query metrics
dau = ws.query("Login", math="dau", last=90)
funnel = ws.query_funnel(["Signup", "Purchase"], last=90)
ret = ws.query_retention("Signup", "Login", last=90)

# 2. Helper functions
def text(html):
    return DashboardRowContent(content_type="text", content_params={"markdown": html})

def report(name, btype, result):
    return DashboardRowContent(content_type="report", content_params={
        "bookmark": {"name": name, "type": btype, "params": json.dumps(result.params)}})

# 3. Create dashboard with layout in one call
dashboard = ws.create_dashboard(CreateDashboardParams(
    title="Product Health",
    rows=[
        DashboardRow(contents=[text("<h2>Product Health</h2><p>Core metrics.</p>")]),
        DashboardRow(contents=[
            report("Daily Active Users", "insights", dau),
            report("Signup Conversion", "funnels", funnel),
            report("New User Retention", "retention", ret),
        ]),
    ],
))
```

## The 6-Phase Workflow

### Phase 1: Investigate

Before building anything, discover the data. Never build reports for events with zero volume.

```python
import mixpanel_data as mp
ws = mp.Workspace()

# Discover events and top events by volume
events = ws.events()
top = ws.top_events(limit=15)
for t in top:
    print(f"{t.event}: {t.count:,} ({t.percent_change:+.1%})")

# Check volumes for candidate events
for event in candidate_events:
    result = ws.query(event, from_date="2025-01-01", to_date="2025-03-31")
    print(f"{event}: {result.df['count'].sum():,.0f} total")

# Explore properties for breakdowns
props = ws.properties(event="key_event")
values = ws.property_values(event="key_event", property="platform", limit=20)

# Test hypotheses with typed queries
funnel = ws.query_funnel(
    ["Signup", "Onboarding", "First Action"],
    from_date="2025-01-01", to_date="2025-03-31",
)
print(f"Overall conversion: {funnel.overall_conversion_rate:.1%}")
```

**Key rule:** Always validate events and properties against the live schema before building reports. Zero-volume events produce empty charts that waste dashboard space.

### Phase 2: Plan Dashboard Structure

Present a proposed structure to the user before building. Choose a template from `references/dashboard-templates.md` as a starting point.

A plan should include:

1. **Dashboard title and description**
2. **Sections** with header text cards
3. **Reports per section** with chart type and events
4. **Grid layout** — which items share a row

#### Dashboard Title and Description

- **Title** (max 255 chars): Concise, descriptive. State what the dashboard monitors.
  - Good: "AARRR Product Health Dashboard", "Q1 Signup Funnel Analysis", "Feature Launch: AI Chat"
  - Bad: "Dashboard", "Metrics", "My Board"
- **Description** (max 400 chars): One sentence explaining the dashboard's purpose and time scope.
  - Good: "Full-funnel product health metrics across Acquisition, Activation, Retention, Revenue, and Engagement. Last 90 days."
  - Bad: "Some metrics" or left empty

#### Report Titles and Descriptions

- **Report title** (max 255 chars): 3-8 words, Title Case. Describe what the chart measures.
  - Good: "Daily Active Users (90d)", "Signup Conversion Funnel", "New User Weekly Retention"
  - Bad: "Login Event Count", "Funnel", "Untitled Report"
- **Report description** (optional): One sentence explaining what to look for in this chart.
  - Good: "DAU segmented by platform. Watch for weekend dips and platform-specific trends."

#### The 12-Column Grid Layout

Mixpanel dashboards use a **12-column grid**. Items in the same `DashboardRow` share the row and have their widths auto-distributed:

| Items in row | Auto width each | Layout |
|---|---|---|
| 1 item | 12 (full width) | Single chart or text card spanning the row |
| 2 items | 6 + 6 | Side-by-side comparison |
| 3 items | 4 + 4 + 4 | Three KPIs or related metrics |
| 4 items | 3 + 3 + 3 + 3 | Four KPI cards |

**Constraints:** Max 4 items per row. Max 30 rows per dashboard.

**What goes full width (1 per row):** Funnels with 3+ steps, retention curves, Sankey flows, data tables, text card section headers.

**What goes side-by-side (2 per row):** Paired comparisons (trend vs trend, control vs variant), related line/bar charts.

**What packs 3-4 per row:** KPI metric cards (`insights-metric` chart type).

#### Text Cards: Section Structure

Text cards use **HTML** (not markdown). They provide narrative structure.

**Every dashboard MUST have:**
- **Row 1: Intro text card** — explains the dashboard's purpose, data scope, and key definitions
- **Section headers** before each group of reports — 2-4 word title + one sentence description

**Allowed HTML tags:** `<h1>`, `<h2>`, `<h3>`, `<p>`, `<strong>`, `<em>`, `<u>`, `<s>`, `<mark>`, `<code>`, `<blockquote>`, `<hr>`, `<br>`, `<ul>`, `<ol>`, `<li>`, `<a href="...">`

**Forbidden tags (stripped by server):** `<div>`, `<span>`, `<b>` (use `<strong>`), `<i>` (use `<em>`), `<img>`, `<table>`

**Critical:** Strip all `\n` newlines from HTML before sending. Each HTML element renders as its own line. Newlines cause Mixpanel's TipTap editor to mangle the content.

**Patterns:**
```
Intro:        <h2>Dashboard Title</h2><p>What this dashboard shows and why. Time period: last 90 days.</p>
Section:      <h2>Acquisition</h2><p>How users discover and sign up for the product.</p>
Explainer:    <p>^ Signup conversion is <strong>23.4%</strong>, up 2.1pp from last month.</p>
Methodology:  <p><em>Methodology:</em> DAU = unique users with any event per day.</p>
Takeaway:     <h3>Key Takeaway</h3><p>Retention stabilizes at <strong>Day 7</strong> (~18%).</p>
```

**Prefer `<h2>` over `<h1>` for section headers. Use `<br>` sparingly — prefer separate `<p>` elements.**

#### Example Plan

```
"AARRR Product Health Dashboard"
"Full-funnel metrics across Acquisition, Activation, Retention, Revenue, and Engagement. Last 90 days."

  Row 1:  [Intro text card]                                    → full width
  Row 2:  [KPI: DAU] [KPI: Signups] [KPI: Purchases]          → 3 KPIs, w=4 each
  Row 3:  [Text: "Acquisition"]                                → section header
  Row 4:  [Signup Trend line] [Signups by Source bar]           → paired, w=6 each
  Row 5:  [Text: "Activation"]                                 → section header
  Row 6:  [Activation Funnel]                                  → full width (3+ steps)
  Row 7:  [Text: "Retention"]                                  → section header
  Row 8:  [Retention Curve]                                    → full width
  Row 9:  [Text: "Revenue"]                                    → section header
  Row 10: [Purchase Trend] [Purchase Funnel]                    → paired, w=6 each
```

### Phase 3: Query Reports

Query each metric and inspect results to verify meaningful data.

```python
# Query and inspect
result = ws.query("Login", math="dau", group_by="platform", last=90)
print(result.df.describe())  # Verify meaningful data exists
```

**Report naming rules:**
- 3-8 words, Title Case
- Describe what the chart measures, not the events
- Good: "Daily Active Users", "Signup Conversion Funnel", "7-Day Retention Curve"
- Bad: "Login Event Count", "Events Funnel", "Retention"

**Chart type selection** (see `references/chart-types.md` for the complete guide):

| Use Case | Chart Type |
|---|---|
| Headline KPI number | `insights-metric` |
| Trend over time | `line` |
| Categorical comparison | `bar` |
| Detailed breakdown | `table` |
| Conversion visualization | `funnel-steps` |
| Retention analysis | `retention-curve` |
| User flow visualization | `sankey` |

**`per_user` note:** When using `per_user` aggregation (e.g., `per_user="average"`), you must also set `math_property` to a numeric property. `per_user` without `math_property` raises a validation error.

### Phase 4: Create Dashboard with Layout

Create the dashboard with all content and layout in a single call using `rows`. Each `DashboardRow` contains 1-4 content items. Items in the same row are placed side-by-side with auto-distributed widths (12-column grid).

```python
from mixpanel_data.types import (
    CreateDashboardParams, DashboardRow, DashboardRowContent,
)
import json

# Helper functions for building row content
def text(html):
    """Create a text card content item."""
    return DashboardRowContent(content_type="text", content_params={"markdown": html})

def report(name, btype, result, description=None):
    """Create a report content item from a typed query result."""
    params = {"bookmark": {"name": name, "type": btype,
                            "params": json.dumps(result.params)}}
    if description:
        params["bookmark"]["description"] = description
    return DashboardRowContent(content_type="report", content_params=params)

# Create dashboard with layout
dashboard = ws.create_dashboard(CreateDashboardParams(
    title="Product Health Dashboard",
    description="Key metrics for product health monitoring.",
    rows=[
        # Row 1: Intro text card (full width)
        DashboardRow(contents=[
            text("<h2>Product Health Dashboard</h2><p>Key metrics updated daily.</p>"),
        ]),
        # Row 2: 3 KPI cards (auto w=4 each)
        DashboardRow(contents=[
            report("DAU (90d)", "insights", dau_result),
            report("Signups (90d)", "insights", signups_result),
            report("Purchases (90d)", "insights", purchases_result),
        ]),
        # Row 3: Section header
        DashboardRow(contents=[
            text("<h2>Conversion</h2><p>Key conversion funnels.</p>"),
        ]),
        # Row 4: Full-width funnel
        DashboardRow(contents=[
            report("Signup Funnel", "funnels", funnel_result),
        ]),
        # Row 5: Section header
        DashboardRow(contents=[
            text("<h2>Retention</h2><p>Do users come back?</p>"),
        ]),
        # Row 6: Side-by-side comparison (auto w=6 each)
        DashboardRow(contents=[
            report("Weekly Retention", "retention", retention_result),
            report("User Journeys", "flows", flow_result),
        ]),
    ],
))
```

**Why `rows` matters:** Layout structure (which items share a row) is set at creation time. Items added later via `update_dashboard()` each get their own full-width row, and the API does not support merging items across rows after creation.

**Width auto-distribution:** Items in a row automatically share the 12-column grid equally. 1 item = w12, 2 items = w6+w6, 3 items = w4+w4+w4, 4 items = w3+w3+w3+w3.

**Adding content after creation:** You can still add items via `update_dashboard()` — they appear as new full-width rows at the bottom. This is fine for explainer cards (Phase 5) but not ideal for reports that should share a row.

```python
# Add a text card after creation (gets its own row)
ws.update_dashboard(dashboard.id, UpdateDashboardParams(
    content={"action": "create", "content_type": "text",
             "content_params": {"markdown": "<p>^ DAU is <strong>12,450</strong>.</p>"}}
))
```

**Height adjustment:** Row heights default to 0 (auto). To set explicit heights, PATCH the layout after creation:

```python
dash = ws.get_dashboard(dashboard.id)
layout = dash.layout
# Modify heights within existing rows (don't restructure which cells are in which row)
for row_id in layout["order"]:
    row = layout["rows"][row_id]
    n_cells = len(row["cells"])
    if n_cells >= 3:
        row["height"] = 336   # KPI row
    elif n_cells == 2:
        row["height"] = 418   # side-by-side
    elif row["cells"][0]["content_type"] == "report":
        row["height"] = 500   # single report

ws.update_dashboard(dashboard.id, UpdateDashboardParams(
    layout={"rows": layout["rows"], "rows_order": layout["order"]}
))
```

**Width and height reference:**

| Content | Items/Row | Auto Width | Recommended Height |
|---|---|---|---|
| Text card (section header) | 1 | 12 | 0 (auto) |
| KPI metric cards | 3-4 | 4 or 3 | 336 |
| Paired charts | 2 | 6 | 418 |
| Single chart | 1 | 12 | 500 |
| Full-width funnel/table | 1 | 12 | 588 |

Max 4 items per row. Max 30 rows per dashboard.

### Phase 5: Add Explainer Cards (Optional)

Data-aware text cards beneath reports add context and insight. These are added after creation and get their own rows.

```python
# Query current values for the explainer
result = ws.query("Login", math="dau", last=30)
latest_value = result.df.iloc[-1]["count"]
prev_value = result.df.iloc[-8]["count"]  # 7 days prior
trend_pct = ((latest_value - prev_value) / prev_value) * 100

ws.update_dashboard(dashboard.id, UpdateDashboardParams(
    content={
        "action": "create",
        "content_type": "text",
        "content_params": {
            "markdown": (
                f"<p>^ DAU is <strong>{latest_value:,.0f}</strong>, "
                f"{'up' if trend_pct > 0 else 'down'} "
                f"<strong>{abs(trend_pct):.1f}%</strong> vs. last week.</p>"
            ).replace("\n", "")
        },
    }
))
```

### Phase 6: Polish, Share, and Verify

- Review report names and descriptions for clarity
- Pin if it should appear at the top for all users: `ws.pin_dashboard(dashboard.id)`
- Favorite if it is a personal reference: `ws.favorite_dashboard(dashboard.id)`
- Verify: open the dashboard and confirm all reports render with data, text cards display correctly, and layout matches the plan

## Critical Gotchas

1. **Layout structure is set at creation time via `rows`.** The API does not support merging items across rows after creation. Always plan your layout and pass `rows` to `CreateDashboardParams`. Items added later via `update_dashboard()` each get their own full-width row.

2. **Layout PATCH can only adjust widths and heights within existing rows.** You can change cell widths and row heights, but you cannot move a cell from one row to another. If the layout is wrong, delete and recreate the dashboard.

3. **`per_user` requires `math_property`.** Using `per_user="average"` (or any per-user aggregation) without setting `math_property` to a numeric property raises `BookmarkValidationError`.

4. **`CreateBookmarkParams(dashboard_id=X)` does NOT add the report to the dashboard layout.** Use `add_report_to_dashboard()` or the inline content action instead.

5. **`add_report_to_dashboard()` CLONES the bookmark.** It creates a "Duplicate of ..." copy. The original bookmark is unchanged. Use `rows` in `CreateDashboardParams` or the inline content action to avoid cloning.

6. **GET returns layout `order`, PATCH expects `rows_order`.** When reading a dashboard, the row ordering key is `order`. When patching layout, the key must be `rows_order`.

7. **Never include `version` key in layout PATCH payloads.** The API rejects it.

8. **Strip `\n` from text card markdown before sending.** Mixpanel's TipTap editor mangles HTML when newlines are present. Always call `.replace("\n", "")` on the markdown before sending.

9. **Dashboard description max 400 chars, title max 255 chars.** Exceeding these limits causes API errors.

10. **Max 4 items per row, max 30 rows per dashboard.** Plan sections to fit within these limits. Cell widths in a row must sum to 12. Standard widths are 3, 4, 6, and 12.

## See Also

- `references/dashboard-reference.md` -- Complete API reference, layout system, content actions, and text card formatting rules
- `references/dashboard-templates.md` -- 9 purpose-built dashboard templates with section layouts and report specs
- `references/bookmark-pipeline.md` -- End-to-end pipeline from typed query to dashboard report for all 4 engines
- `references/chart-types.md` -- Complete chart type selection guide with slugs and use cases
