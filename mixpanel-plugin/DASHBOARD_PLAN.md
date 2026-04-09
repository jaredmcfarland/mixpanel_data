# Dashboard Builder — Post-PR #108 Gap Analysis

**Scope:** Dashboard creation and management only — layout, text cards, content actions, update operations, styling. NOT report/bookmark param construction.

**Date:** 2025-04-09

---

## Executive Summary

The dashboard-builder skill covers the happy path well: create a dashboard with `rows`, add text cards and inline reports, set heights and widths. However, the plugin's two most prominent gotchas — "layout structure is set at creation time" and "layout PATCH can only adjust widths and heights" — are **incorrect**. The MCP server proves you CAN add cells to existing rows, delete cells, reorder rows, and create new rows after creation. The plugin is teaching agents an overly restrictive model that will cause them to delete and recreate dashboards unnecessarily.

**15 gaps** across 4 categories. Most are medium-effort documentation additions.

---

## Category 1: Post-Creation Layout Manipulation (HIGH PRIORITY)

The plugin's SKILL.md gotchas #1 and #2 state:
> "Layout structure is set at creation time via `rows`."
> "Layout PATCH can only adjust widths and heights within existing rows."

Both are wrong. The MCP server's `create_cell()` method (`mcp_server/api/dashboards.py:237-255`) proves that you can add a cell to a **specific existing row** after creation by sending `content` AND `layout` together in a single PATCH:

```python
body = {
    "content": {
        "action": "create",
        "content_type": "report",
        "content_params": { ... },
    },
    "layout": dashboard.layout_with_new_cell(row_id),  # specifies which row
}
await self.patch_dashboard(project_id, dashboard_id, body)
```

The key insight the plugin misses: **you can send `content` and `layout` in the same PATCH request.** The plugin only documents sending one or the other.

### Gap 1.1: Combined Content + Layout PATCH

**What the plugin teaches:** Send `content` OR `layout` in `UpdateDashboardParams`, never both.

**What the MCP does:** Sends both simultaneously. The `content` creates the item, and the `layout` specifies where it goes (including into an existing row). This is how you add a cell to a specific row after creation.

**Impact:** Without this, agents can only append items as new full-width rows at the bottom. They can't insert a 4th KPI card into an existing row of 3.

### Gap 1.2: Adding Cells to Existing Rows

**Source:** `mixpanel_mcp/mcp_server/utils/dashboards.py:177-200`

When adding a cell to an existing row, the layout payload includes the existing row with its cells plus a new temp cell. The MCP auto-redistributes widths:

```python
new_count = len(row["cells"]) + 1
cell_width = ROW_TOTAL_WIDTH // new_count  # 12 / (N+1)
for cell in row["cells"]:
    cell["width"] = cell_width
row["cells"].append({"temp_id": "-1", "width": cell_width})
```

For a row with 2 cells (width 6+6), adding a 3rd redistributes to 4+4+4.

### Gap 1.3: Update Operation Ordering

**Source:** `mixpanel_mcp/mcp_server/utils/dashboards.py:294-463`

When making multiple changes to a dashboard, operations must execute in this order. The MCP re-fetches the dashboard between layout-modifying operations:

1. **Metadata** (title/description) — standalone PATCH
2. **Cell creates** — new content added first
3. **rows_order** — reorder after creates so temp IDs can resolve
4. **Cell updates** — modify existing content
5. **Cell deletes** — remove content
6. **Row deletes** — remove entire rows last

Wrong order causes failures: reordering before creating temp rows gives "unknown row ID"; deleting before creating leaves layout gaps.

### Gap 1.4: Temp ID Resolution

**Source:** `mixpanel_mcp/mcp_server/utils/dashboards.py:337-369`

When creating new rows during an update:

1. Assign temp string IDs (e.g., `"temp-row-1"`)
2. Call cell create → new rows appear in the dashboard response
3. Diff row sets before/after to discover real row IDs
4. Map `temp-row-1 → real-row-abc123`
5. Substitute in `rows_order` before sending

Power-tools uses negative integers (`"-1"`, `"-2"`) as temp row IDs. Same concept, different convention.

### Gap 1.5: Cross-Type Cell Updates

**Source:** `mixpanel_mcp/mcp_server/utils/dashboards.py:390-435`

The API rejects changing `content_type` on an update action. To convert a text cell to a report cell (or vice versa), you must:

1. Delete the old cell (with layout update removing it from the row)
2. Create a new cell in the same position (with layout update adding it back)

The MCP auto-detects cross-type updates and converts to delete+create internally.

### Gap 1.6: Content Action `move` Is Undocumented

The plugin's `dashboard-reference.md` Section 2 lists `move` as a content action but provides no example, parameters, or explanation. Neither reference project uses it either — both achieve moves through delete+create. Either document it or remove it from the action list.

---

## Category 2: Dashboard Operations & Best Practices (MEDIUM PRIORITY)

### Gap 2.1: Auto-Share and Auto-Pin After Creation

**Source:** `mixpanel-power-tools/index.js:1363-1384`

Power-tools automatically shares and pins every new dashboard as part of creation:

```javascript
const shareResponse = await this.shareDash(dashId);
const pinDashResponse = await this.pinDash(dashId);
```

The plugin mentions pin/favorite in Phase 6 ("Polish") as optional, but doesn't emphasize that **dashboards are invisible to the team by default**. The skill should recommend pinning after creation as standard practice, not an afterthought.

### Gap 2.2: Fallback Text Cards on Report Failure

**Source:** `mixpanel-power-tools/macros/ai/ai-dash-builder.js:157-214`

When a report fails to generate during dashboard building, power-tools substitutes an error text card:

```html
<p><strong>Failed:</strong> {prompt description}</p><p>{error.message}</p>
```

The dashboard still gets created with placeholders explaining what went wrong. The plugin has no guidance for graceful degradation — a single failed report could abort the entire dashboard build.

### Gap 2.3: Cross-Project Duplication

**Source:** `mixpanel-power-tools/index.js:1514-1519`

The plugin documents `CreateDashboardParams(duplicate=dashboard_id)` for same-project duplication. Power-tools also supports cross-project:

```javascript
const payload = { duplicate: dashId, target_project_id: newProjectId };
```

This is a `POST /dashboards/` with both fields. The plugin's Python library would need a `target_project_id` field on `CreateDashboardParams` to support this.

### Gap 2.4: Dashboard-Level Filters & Breakdowns

The plugin lists `filters` and `breakdowns` as `list[Any] | None` on `CreateDashboardParams` but never explains what goes in them. From the MCP and power-tools research, dashboard-level filters are typically empty arrays and appear to be configured through the UI rather than the API. The plugin should either:

- Document the filter structure if it's API-configurable
- Or explicitly note that dashboard-level filters are UI-only and the API params are for reading/preserving existing filters

---

## Category 3: Existing Dashboard Analysis (MEDIUM PRIORITY)

### Gap 3.1: Structured Dashboard Extraction

**Source:** `mixpanel-power-tools/tools/dashboard-analysis.js:68-151`

Power-tools' `analyzeDashboard()` returns a structured extraction:

```javascript
{
  reports: [{
    id, name, type, chartType, events, groupBy,
    contentId, isOwned,     // report vs report-link
    width, rowId, rawParams // layout position
  }],
  existingTextCards: [{
    contentId, markdown,
    isSectionHeader: true   // detected via /<h2[\s>]/i.test(markdown)
  }],
  layoutRows: [{
    rowId,
    cells: [{ contentId, contentType, width }]
  }],
  allContentIds: [...]
}
```

The plugin's analyst agent says "analyze existing → `ws.get_dashboard()` + summarize" but gives no guidance on how to extract this structure from the raw layout. Agents will struggle to understand an existing dashboard's organization without this pattern.

### Gap 3.2: Report-Link vs Report Distinction

**Source:** `mixpanel_mcp/mcp_server/types/dashboards.py`

`content_type: "report"` means the dashboard **owns** the report — you can edit its params. `content_type: "report-link"` means it's a **reference** to a report owned by another dashboard — read-only. The plugin documents `update_report_link()` but doesn't explain when you encounter report-links or that you can't edit their params.

This matters when analyzing or modifying existing dashboards: attempting to update a report-link's params will fail silently or error.

### Gap 3.3: Section Header Detection Pattern

**Source:** `mixpanel-power-tools/tools/dashboard-analysis.js:106-115`

When analyzing existing dashboards, detect section boundaries by testing text card content for `<h2>` tags:

```javascript
isSectionHeader: /<h2[\s>]/i.test(markdown)
```

This lets agents understand the logical grouping of reports on an existing dashboard, which is essential for "add a report to the Retention section" type requests.

---

## Category 4: Text Card & Styling Details (LOW PRIORITY)

### Gap 4.1: Whitespace Collapsing

**Source:** `mixpanel-power-tools/index.js:1846-1852`

Power-tools strips newlines AND collapses whitespace:

```javascript
const clean = (markdown || '')
    .replace(/\n/g, '')
    .replace(/\s+/g, ' ')
    .trim();
```

The plugin only documents stripping `\n`. Multiple spaces or tabs in HTML content could also cause rendering issues. Should recommend `.replace("\n", "").strip()` at minimum, and note that excessive whitespace should be avoided.

### Gap 4.2: Text Card Character Limit Discrepancy

The plugin says "server accepts up to 5,000,000 characters" (dashboard-reference.md line 648). The MCP validates `TextContent.html_content` at **max 2,000 characters** (`mcp_server/types/dashboards.py:52-59`). The practical limit for readable dashboard text cards is well under 500 characters (the plugin's recommendation).

The 2,000-char MCP limit is likely a sensible guard rail. The 5M figure may be the raw API limit but producing text cards that long would be unusable. The plugin should revise its stated limit to 2,000 chars to match the MCP's validated ceiling, and keep the "under 500 chars" recommendation.

### Gap 4.3: Layout Builder Algorithm

**Source:** `mixpanel-power-tools/tools/layout-builder.js:104-139`

Power-tools has a `sectionsToRows()` function that packs items into 12-column rows respecting desired widths:

```
For each item:
  If currentWidth + itemWidth > 12 and row has items → push row, start new
  Add item to row, increment currentWidth
  If currentWidth >= 12 → push row, reset
```

This is a simple bin-packing algorithm. The plugin's Phase 4 handles this implicitly through `DashboardRow` construction, but agents building dashboards programmatically (e.g., from a template with variable content) could benefit from seeing this algorithm explicitly. Currently the plugin assumes the agent knows how to pack items into rows.

---

## What the Plugin Already Covers Well

For completeness — areas where the plugin matches or exceeds the references:

| Area | Plugin Coverage |
|------|----------------|
| 12-column grid system | Complete with width table and height guidelines |
| Text card HTML tags | Full allowed/forbidden tag list with examples |
| Newline stripping | Documented with correct `.replace("\n", "")` pattern |
| Content actions | All 6 actions listed (create, delete, update, move, duplicate, undelete) |
| Layout GET vs PATCH format | `order` vs `rows_order`, `version` exclusion |
| Dashboard time filters | All 3 types (relative, since, between) with examples |
| 11 gotchas | Comprehensive, though 2 need correction (see Category 1) |
| 9 dashboard templates | Neither reference has structured templates |
| Inline report creation | Well-documented as preferred over `add_report_to_dashboard()` |
| DashboardRow/DashboardRowContent types | Clean typed API unique to this plugin |

---

## Priority Matrix

| Priority | Gaps | Impact | Fix |
|----------|------|--------|-----|
| **P0 — Incorrect guidance** | 1.1, 1.2, 1.3 | Agents delete+recreate dashboards unnecessarily; can't add to existing rows | Correct gotchas #1/#2 in SKILL.md; add combined content+layout PATCH pattern to dashboard-reference.md |
| **P1 — Missing capabilities** | 1.4, 1.5, 1.6, 3.1, 3.2 | Can't do complex updates; can't analyze existing dashboards | Add update operations section to dashboard-reference.md |
| **P2 — Best practices** | 2.1, 2.2, 2.3, 3.3 | Team visibility, graceful degradation, cross-project | Add to SKILL.md Phase 6 and analyst agent |
| **P3 — Minor details** | 2.4, 4.1, 4.2, 4.3 | Edge cases, text card limits | Targeted fixes to reference docs |

---

## Source File Reference

### analytics/mixpanel_mcp/ (dashboard-specific)

| File | Key Knowledge |
|------|---------------|
| `mcp_server/api/dashboards.py:237-255` | `create_cell()` — sends content+layout together to add cell to specific row |
| `mcp_server/utils/dashboards.py:177-200` | `layout_with_new_cell()` — width redistribution algorithm, temp cell creation |
| `mcp_server/utils/dashboards.py:294-463` | `execute_update_operations()` — strict operation ordering, temp ID resolution |
| `mcp_server/utils/dashboards.py:390-435` | Cross-type cell update → delete+create pattern |
| `mcp_server/types/dashboards.py:234-258` | `CellCreate` model with `row_id` field for targeting specific rows |
| `mcp_server/types/dashboards.py:52-59` | `TextContent` — max 2000 chars, no newlines |

### mixpanel-power-tools/ (dashboard-specific)

| File | Key Knowledge |
|------|---------------|
| `index.js:1363-1384` | `createDash()` — auto-share and auto-pin after creation |
| `index.js:1524-1617` | `reconcileLayouts()` — item matching by type+name (reports), markdown (text) |
| `index.js:1846-1852` | `addTextCard()` — newline strip + whitespace collapse |
| `tools/layout-builder.js:34-93` | `buildLayoutPatch()` — constructs layout PATCH from desired rows + current state |
| `tools/layout-builder.js:104-139` | `sectionsToRows()` — bin-packing algorithm for 12-column grid |
| `tools/dashboard-analysis.js:68-151` | `analyzeDashboard()` — structured extraction with ownership, header detection |
| `macros/ai/ai-dash-builder.js:221-339` | Assemble stage — item creation → fresh fetch → layout pack → PATCH |
