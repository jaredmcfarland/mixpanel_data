# Implementation Plan: Operational Analytics Loop

**Branch**: `022-analytics-loop` | **Date**: 2025-01-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/022-analytics-loop/spec.md`

## Summary

Add five high-level orchestration tools (context, health, scan, investigate, report) to the mp_mcp MCP server. These tools compose existing primitives into a cohesive workflow for daily/weekly analytical rituals, following the established FastMCP patterns with `@mcp.tool` + `@handle_errors` decorators and rate-limited workspace access.

## Technical Context

**Language/Version**: Python 3.10+ (matches existing project requirements)
**Primary Dependencies**: FastMCP 2.x, mixpanel_data library, Pydantic v2
**Storage**: DuckDB (via mixpanel_data Workspace for local queries)
**Testing**: pytest with MagicMock for Context/Workspace mocking
**Target Platform**: MCP server running in Claude Code environment
**Project Type**: Single project (MCP server extension)
**Performance Goals**: Full workflow completes in <60 seconds for typical projects
**Constraints**: Rate-limited by Mixpanel API (60 query/hour, 5 concurrent)
**Scale/Scope**: 5 new MCP tools composing 17+ existing primitives

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Library-First | ✅ PASS | Tools compose existing Workspace methods, no new CLI logic |
| II. Agent-Native Design | ✅ PASS | Non-interactive tools with structured dict output |
| III. Context Window Efficiency | ✅ PASS | Summarized outputs, caching via middleware |
| IV. Two Data Paths | ✅ PASS | Tools use both live queries (health, scan) and local analysis |
| V. Explicit Over Implicit | ✅ PASS | All tool parameters explicit, no magic behavior |
| VI. Unix Philosophy | ✅ PASS | Each tool does one thing, composable workflow |
| VII. Secure by Default | ✅ PASS | Credentials via existing config, no new auth paths |

**All gates pass. Proceeding to Phase 0.**

## Project Structure

### Documentation (this feature)

```text
specs/022-analytics-loop/
├── plan.md              # This file
├── research.md          # Phase 0: Architecture decisions
├── data-model.md        # Phase 1: Pydantic/dataclass models
├── quickstart.md        # Phase 1: Usage examples
├── contracts/           # Phase 1: Tool signatures
└── tasks.md             # Phase 2: Implementation tasks
```

### Source Code (repository root)

```text
mp_mcp/
├── src/mp_mcp/
│   ├── server.py              # Add workflow tools import
│   ├── types.py               # ADD: New dataclasses for workflow results
│   ├── tools/
│   │   ├── __init__.py        # Add workflows import
│   │   └── workflows/         # NEW: Workflow tools directory
│   │       ├── __init__.py    # Re-export all tools
│   │       ├── context.py     # context tool
│   │       ├── health.py      # health tool
│   │       ├── scan.py        # scan tool
│   │       ├── investigate.py # investigate tool
│   │       └── report.py      # report tool
│   └── prompts.py             # ADD: Workflow guidance prompt (optional)
└── tests/
    └── unit/
        └── test_tools_workflows.py  # NEW: Unit tests

mixpanel-plugin/
├── commands/
│   ├── mp-context.md          # NEW: /mp-context slash command
│   ├── mp-health.md           # NEW: /mp-health slash command
│   ├── mp-scan.md             # NEW: /mp-scan slash command
│   ├── mp-investigate.md      # NEW: /mp-investigate slash command
│   └── mp-report.md           # NEW: /mp-report slash command
└── skills/
    └── mixpanel-data/
        └── operational-loop.md # NEW: Skill doc for workflow
```

**Structure Decision**: Single project extension following existing mp_mcp structure. New tools go in `tools/workflows/` subdirectory following the established pattern (tools/composed/, tools/intelligent/).

## Complexity Tracking

> No violations. All patterns follow existing architecture.

## Tool Architecture

### Tool Classification

| Tool | Tier | Pattern | Sampling Required |
|------|------|---------|-------------------|
| context | Composed | Multi-call aggregation | No |
| health | Composed | Multi-call + comparison | No |
| scan | Intelligent | Statistical analysis + AI synthesis | Yes (graceful degradation) |
| investigate | Intelligent | Root cause analysis + AI synthesis | Yes (graceful degradation) |
| report | Intelligent | Findings synthesis | Yes (graceful degradation) |

### Primitive Composition

| Workflow Tool | Existing Primitives Used |
|---------------|--------------------------|
| context | workspace_info, list_events, top_events, list_funnels, list_cohorts, list_bookmarks, lexicon_schemas |
| health | product_health_dashboard, event_counts, segmentation, retention |
| scan | segmentation, property_counts, retention, funnel, jql |
| investigate | diagnose_metric_drop, cohort_comparison, property_distribution, segmentation, activity_feed |
| report | (synthesis only - uses investigation results) |

### New Dataclasses Required

```python
# In mp_mcp/src/mp_mcp/types.py

@dataclass
class ContextPackage:
    """Project landscape for analytics context."""
    project: dict[str, Any]
    events: EventsSummary
    properties: PropertiesSummary
    funnels: list[FunnelSummary]
    cohorts: list[CohortSummary]
    bookmarks: BookmarksSummary
    date_range: DateRange
    schemas: list[dict[str, Any]] | None = None

@dataclass
class HealthDashboard:
    """Product health metrics with comparison."""
    period: DateRange
    comparison_period: DateRange
    metrics: list[Metric]
    aarrr: AARRRMetrics | None = None
    highlights: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    daily_series: dict[str, list[DataPoint]] = field(default_factory=dict)

@dataclass
class Anomaly:
    """Detected signal for investigation."""
    id: str
    type: Literal["drop", "spike", "trend_change", "segment_shift"]
    severity: Literal["critical", "high", "medium", "low"]
    category: str
    summary: str
    event: str
    dimension: str | None = None
    dimension_value: str | None = None
    detected_at: str = ""
    magnitude: float = 0.0
    confidence: float = 0.0
    context: dict[str, Any] = field(default_factory=dict)

@dataclass
class ScanResults:
    """Anomaly detection results."""
    period: DateRange
    anomalies: list[Anomaly]
    scan_coverage: dict[str, Any]
    baseline_stats: dict[str, Any]

@dataclass
class ContributingFactor:
    """Factor contributing to an anomaly."""
    factor: str
    contribution: float
    evidence: str
    confidence: Literal["high", "medium", "low"]

@dataclass
class Investigation:
    """Root cause analysis result."""
    anomaly: Anomaly
    root_cause: str | None = None
    contributing_factors: list[ContributingFactor] = field(default_factory=list)
    segments_analyzed: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    affected_vs_unaffected: dict[str, Any] = field(default_factory=dict)
    confidence: Literal["high", "medium", "low"] = "medium"
    limitations: list[str] = field(default_factory=list)
    queries_run: list[str] = field(default_factory=list)
    data_points: dict[str, Any] = field(default_factory=dict)

@dataclass
class Recommendation:
    """Actionable suggestion from analysis."""
    action: str
    priority: Literal["immediate", "soon", "consider"]
    impact: str
    effort: Literal["low", "medium", "high"]
    owner: str | None = None

@dataclass
class Report:
    """Synthesized findings report."""
    title: str
    generated_at: str
    period_analyzed: DateRange
    summary: str
    key_findings: list[str]
    sections: list[dict[str, Any]]
    recommendations: list[Recommendation]
    methodology: str | None = None
    queries_run: list[str] | None = None
    suggested_follow_ups: list[str] = field(default_factory=list)
    markdown: str = ""
    slack_blocks: list[dict[str, Any]] | None = None
```

## Phase 0: Research Summary

### Research Tasks

1. **Anomaly Detection Algorithms**: Best practices for z-score, IQR, change point detection in analytics context
2. **Caching Strategy**: How to leverage existing caching middleware for workflow tools
3. **Graceful Degradation**: Pattern for intelligent tools when sampling unavailable
4. **Anomaly ID Generation**: Deterministic ID scheme for referencing anomalies across calls

### Key Decisions

See [research.md](research.md) for detailed findings.

## Phase 1: Design Outputs

- [data-model.md](data-model.md) - Complete dataclass definitions
- [contracts/](contracts/) - Tool signatures and parameter specs
- [quickstart.md](quickstart.md) - Usage examples for each tool

## Implementation Order

Based on dependency analysis:

1. **context** - Foundation, no dependencies on other workflow tools
2. **health** - Uses context patterns, standalone metrics
3. **scan** - Depends on health patterns for metrics, adds anomaly detection
4. **investigate** - Depends on scan for anomaly format, adds root cause
5. **report** - Depends on investigate for findings, synthesis only

Each tool should be implemented with tests before proceeding to next.
