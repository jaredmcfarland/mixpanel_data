---
name: dashboard-builder
description: Build, design, and manage Mixpanel dashboards with professional layouts, text cards, and multi-report sections. Use when the user asks to build, create, make, set up, or assemble a dashboard, or when they ask about dashboard layout, text cards, or report arrangement. Provides design templates, layout rules, text card formatting, and end-to-end workflows from data investigation through dashboard assembly.
allowed-tools: Bash Read Write
---

# Dashboard Builder

Build production-quality Mixpanel dashboards through an 8-phase workflow: investigate data, plan structure, build reports, create dashboard, arrange layout, add explainers, polish, and verify.

## Quick Start Example

A minimal 3-report dashboard in ~20 lines:

```python
import mixpanel_data as mp
from mixpanel_data.types import CreateDashboardParams, UpdateDashboardParams, CreateBookmarkParams
import json

ws = mp.Workspace()

# 1. Query metrics
dau = ws.query("Login", math="dau", last=90)
funnel = ws.query_funnel(["Signup", "Purchase"], last=90)
ret = ws.query_retention("Signup", "Login", last=90)

# 2. Create dashboard
dashboard = ws.create_dashboard(CreateDashboardParams(title="Product Health"))

# 3. Add intro text card
ws.update_dashboard(dashboard.id, UpdateDashboardParams(
    content={"action": "create", "content_type": "text",
             "content_params": {"markdown": "<h2>Product Health</h2><p>Core metrics updated daily.</p>"}}))

# 4. Add reports inline (no separate bookmarks needed)
for name, btype, params in [
    ("Daily Active Users", "insights", dau.params),
    ("Signup Conversion", "funnels", funnel.params),
    ("New User Retention", "retention", ret.params),
]:
    ws.update_dashboard(dashboard.id, UpdateDashboardParams(
        content={"action": "create", "content_type": "report",
                 "content_params": {"bookmark": {"name": name, "type": btype,
                                                 "params": json.dumps(params)}}}))
```

## The 8-Phase Workflow

### Phase 1: Investigate

Before building anything, discover the data. Never build reports for events with zero volume.

```python
import mixpanel_data as mp
ws = mp.Workspace()

# Discover events
events = ws.events()

# Check volumes for candidate events
for event in candidate_events:
    result = ws.segmentation(event=event, from_date="2025-01-01", to_date="2025-03-31")
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

1. **Dashboard title and description** (title max 255 chars, description max 400 chars)
2. **Sections** with header text cards describing each group of reports
3. **Reports per section** with chart type, events, breakdowns, and time range
4. **Grid width assignments** using the 12-column grid (see width table in Phase 5)

Example plan:

```
"Product Health Dashboard"
  Row 1:  [Intro text card (w=12)]
  Row 2:  [KPI: DAU (w=4)] [KPI: WAU (w=4)] [KPI: Signups (w=4)]
  Row 3:  [Text: "Growth Trends" (w=12)]
  Row 4:  [DAU Trend line (w=6)] [Signup Trend line (w=6)]
  Row 5:  [Text: "Conversion" (w=12)]
  Row 6:  [Signup Funnel (w=12)]
  Row 7:  [Text: "Retention" (w=12)]
  Row 8:  [Retention Curve (w=12)]
```

### Phase 3: Build Reports

Query each metric, inspect results to verify meaningful data, then prepare for dashboard creation.

```python
from mixpanel_data.types import CreateBookmarkParams

# Query and inspect
result = ws.query("Login", math="dau", group_by="platform", last=90)
print(result.df.describe())  # Verify meaningful data exists

# Save as standalone bookmark (Method A)
bookmark = ws.create_bookmark(CreateBookmarkParams(
    name="DAU by Platform (90d)",
    bookmark_type="insights",
    params=result.params,
))
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

### Phase 4: Create Dashboard

Create the dashboard, then add content. There are two methods for adding reports.

```python
from mixpanel_data.types import CreateDashboardParams, UpdateDashboardParams
import json

# Create the dashboard
dashboard = ws.create_dashboard(CreateDashboardParams(
    title="Product Health Dashboard",
    description="Key metrics for product health monitoring.",
))

# Add intro text card (always first)
ws.update_dashboard(dashboard.id, UpdateDashboardParams(
    content={
        "action": "create",
        "content_type": "text",
        "content_params": {
            "markdown": "<h2>Product Health Dashboard</h2><p>Key metrics for monitoring product health. Updated daily.</p>"
        },
    }
))
```

**Method A: From existing bookmark (clones it onto dashboard)**

```python
ws.add_report_to_dashboard(dashboard.id, bookmark.id)
```

**Method B: Inline report creation (preferred -- no separate bookmark needed)**

```python
ws.update_dashboard(dashboard.id, UpdateDashboardParams(
    content={
        "action": "create",
        "content_type": "report",
        "content_params": {
            "bookmark": {
                "name": "Daily Active Users",
                "type": "insights",
                "params": json.dumps(result.params),
                "description": "DAU over the last 90 days.",
            }
        },
    }
))
```

Method B is preferred because it creates the report directly on the dashboard without cloning or creating a separate bookmark entity.

### Phase 5: Arrange Layout

After adding all content, rearrange the 12-column grid.

```python
# Get current layout to discover row/cell IDs
dash = ws.get_dashboard(dashboard.id)
# dash.layout has: version, order (list of row IDs), rows (dict of row_id -> {height, cells})

# Update layout: set cell widths and row order
ws.update_dashboard(dashboard.id, UpdateDashboardParams(
    layout={
        "rows": {
            "row-id-1": {
                "height": 0,
                "cells": [
                    {"id": "cell-id-1", "width": 12,
                     "content_id": text_card_id, "content_type": "text"}
                ]
            },
            "row-id-2": {
                "height": 336,
                "cells": [
                    {"id": "cell-id-2", "width": 4,
                     "content_id": kpi1_id, "content_type": "report"},
                    {"id": "cell-id-3", "width": 4,
                     "content_id": kpi2_id, "content_type": "report"},
                    {"id": "cell-id-4", "width": 4,
                     "content_id": kpi3_id, "content_type": "report"},
                ]
            },
        },
        "rows_order": ["row-id-1", "row-id-2"],
    }
))
```

**Width assignment rules:**

| Content | Width | Rationale |
|---|---|---|
| Text card (section header) | 12 | Always full width |
| KPI metric card | 3 or 4 | Pack 3-4 per row |
| Line/bar chart (paired) | 6 | Side-by-side comparison |
| Line/bar chart (solo) | 12 | Full width for detail |
| Table | 12 | Needs full width |
| Funnel (3+ steps) | 12 | Complex funnels need space |
| Retention curve | 12 | Full width |
| Sankey/flow | 12 | Always full width |

Cell widths in a row must sum to 12. Max 4 items per row. Max 30 rows per dashboard.

**Height guidelines:**

| Configuration | Height |
|---|---|
| Text-only row | 0 (auto) |
| KPI row (3-4 cards) | 336 |
| 6+6 side-by-side | 418 |
| Single full-width chart | 500 |
| Full-width funnel/table | 588 |

### Phase 6: Add Explainer Cards (Optional)

Data-aware text cards beneath reports add context and insight.

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

### Phase 7: Polish and Share

- Review report names and descriptions for clarity
- Pin if it should appear at the top for all users: `ws.pin_dashboard(dashboard.id)`
- Favorite if it is a personal reference: `ws.favorite_dashboard(dashboard.id)`

### Phase 8: Verify

Open the dashboard and confirm:

1. All reports render with data (no empty charts)
2. Text cards are properly formatted (no raw HTML showing)
3. Layout is correct (correct widths, no overlapping)
4. Report order follows a logical narrative flow (overview first, then detail)

## Text Card Quick Reference

Text cards use a restricted subset of HTML. Full reference in `references/dashboard-reference.md`.

**Allowed tags:** `<h2>`, `<h3>`, `<p>`, `<strong>`, `<em>`, `<u>`, `<s>`, `<mark>`, `<code>`, `<blockquote>`, `<hr>`, `<ul>`, `<ol>`, `<li>`, `<a>`

**Forbidden tags:** `<h1>`, `<div>`, `<span>`, `<br>`, `<b>`, `<i>`, `<img>`, `<table>`

**Critical rule:** Strip all `\n` newlines from markdown strings before sending. Each HTML element renders as its own line. Newlines in the string cause Mixpanel's TipTap editor to mangle the HTML.

**Common patterns:**

```html
Section header:   <h2>Section Title</h2><p>One sentence description.</p>
Explainer:        <p>^ Brief data-driven insight about chart above.</p>
Methodology:      <p><em>Methodology:</em> How this metric is calculated.</p>
Key takeaway:     <h3>Key Takeaway</h3><p>One-sentence finding with <strong>bold numbers</strong>.</p>
```

## Critical Gotchas

1. **`CreateBookmarkParams(dashboard_id=X)` does NOT add the report to the dashboard layout.** Use `add_report_to_dashboard()` or the inline content action instead.

2. **`add_report_to_dashboard()` CLONES the bookmark.** It creates a "Duplicate of ..." copy. The original bookmark is unchanged.

3. **Inline report creation via content action is preferred.** No clone, no separate bookmark entity. Use the `content_params.bookmark` pattern from Phase 4 Method B.

4. **GET returns layout `order`, PATCH expects `rows_order`.** When reading a dashboard, the row ordering key is `order`. When patching layout, the key must be `rows_order`.

5. **Never include `version` key in layout PATCH payloads.** The API rejects it.

6. **Strip `\n` from text card markdown before sending.** Mixpanel's TipTap editor mangles HTML when newlines are present in the markdown string. Always call `.replace("\n", "")` on the markdown before sending.

7. **Dashboard description max 400 chars, title max 255 chars.** Exceeding these limits causes API errors.

8. **Max 4 items per row, max 30 rows per dashboard.** Plan sections to fit within these limits.

9. **Cell widths in a row must sum to 12.** Standard widths are 3, 4, 6, and 12.

## See Also

- `references/dashboard-reference.md` -- Complete API reference, layout system, content actions, and text card formatting rules
- `references/dashboard-templates.md` -- 9 purpose-built dashboard templates with section layouts and report specs
- `references/bookmark-pipeline.md` -- End-to-end pipeline from typed query to dashboard report for all 4 engines
- `references/chart-types.md` -- Complete chart type selection guide with slugs and use cases
