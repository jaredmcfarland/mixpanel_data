# Feature Specification: Operational Analytics Loop

**Feature Branch**: `022-analytics-loop`
**Created**: 2025-01-24
**Status**: Draft
**Input**: User description: "Add five high-level orchestration tools to the mixpanel-data MCP server and corresponding slash commands for the Claude Code plugin. These tools compose existing primitives into a cohesive workflow for daily/weekly analytical rituals."

## Overview

The Operational Analytics Loop is a structured, recurring workflow for maintaining product health awareness through Mixpanel analytics. It provides a five-stage analytical pipeline designed for both human analysts and AI agents, enabling systematic discovery, investigation, and reporting of product insights.

This feature adds five orchestration tools to the existing MCP server:
1. **Context** - Prime the context window with project landscape
2. **Health** - Generate health metrics dashboard
3. **Scan** - Detect anomalies and interesting signals
4. **Investigate** - Deep-dive into specific anomalies
5. **Report** - Synthesize findings into actionable briefs

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Daily Analytics Check (Priority: P1)

An analyst or AI agent performs their daily product health review by running through the complete Operational Analytics Loop to identify issues, investigate anomalies, and generate a report.

**Why this priority**: This is the primary use case that exercises all five tools in sequence, delivering the core value proposition of systematic, repeatable analytics workflows.

**Independent Test**: Can be fully tested by running `/context` → `/health` → `/scan` → `/investigate` → `/report` in sequence and verifying each stage produces usable output for the next stage.

**Acceptance Scenarios**:

1. **Given** a configured Mixpanel project, **When** the user runs `/context`, **Then** the system returns project metadata, events, funnels, cohorts, and date range information in a structured format.

2. **Given** context has been primed, **When** the user runs `/health`, **Then** the system returns a dashboard with current KPIs, comparison to previous period, highlights, and concerns.

3. **Given** health metrics are available, **When** the user runs `/scan`, **Then** the system returns a ranked list of anomalies sorted by severity and confidence with unique identifiers for investigation.

4. **Given** anomalies have been detected, **When** the user runs `/investigate` with an anomaly ID, **Then** the system returns root cause analysis, contributing factors, timeline, and evidence.

5. **Given** an investigation has been completed, **When** the user runs `/report`, **Then** the system generates an executive summary with key findings, recommendations, and suggested follow-ups.

---

### User Story 2 - Quick Health Check (Priority: P2)

An analyst wants a quick overview of product health without running the full workflow. They run just the health command to see current KPIs and trends.

**Why this priority**: Health checks are the most common standalone operation for monitoring product status without requiring full investigation.

**Independent Test**: Can be tested by running `/health` alone and verifying it returns a complete dashboard with metrics and trends.

**Acceptance Scenarios**:

1. **Given** a configured Mixpanel project, **When** the user runs `/health` without prior context, **Then** the system fetches required data and returns a health dashboard.

2. **Given** the user specifies a date range, **When** they run `/health --from 2025-01-01 --to 2025-01-15`, **Then** the dashboard reflects only that time period.

3. **Given** the user wants to focus on a specific area, **When** they run `/health --focus acquisition`, **Then** the dashboard emphasizes acquisition-related metrics.

---

### User Story 3 - Investigate Known Issue (Priority: P2)

An analyst is aware of a specific metric drop or anomaly and wants to investigate it directly without running a full scan.

**Why this priority**: Direct investigation of known issues is common when teams are already aware of problems from other sources.

**Independent Test**: Can be tested by running `/investigate` with manual parameters (event, date, dimension) and verifying root cause analysis is returned.

**Acceptance Scenarios**:

1. **Given** the user knows a specific event had issues, **When** they run `/investigate --event signup --date 2025-01-15`, **Then** the system analyzes that specific event for that date.

2. **Given** an investigation is in progress, **When** the user provides hypotheses to test, **Then** the system prioritizes those hypotheses in the analysis.

3. **Given** the user wants a quick investigation, **When** they run `/investigate --depth quick`, **Then** the system returns a faster but less comprehensive analysis.

---

### User Story 4 - Ad-hoc Anomaly Scan (Priority: P3)

An analyst wants to proactively scan for anomalies across specific dimensions or events without running the full workflow.

**Why this priority**: Targeted scans are useful for periodic monitoring of specific areas of concern.

**Independent Test**: Can be tested by running `/scan` with dimension filters and verifying anomalies are detected within those constraints.

**Acceptance Scenarios**:

1. **Given** a configured Mixpanel project, **When** the user runs `/scan --dimensions country,platform`, **Then** the system scans for anomalies specifically across those dimensions.

2. **Given** the user wants high sensitivity, **When** they run `/scan --sensitivity high`, **Then** more potential anomalies are surfaced (lower confidence threshold).

3. **Given** the user only wants problems (not opportunities), **When** they run `/scan --include-opportunities false`, **Then** only negative anomalies are returned.

---

### User Story 5 - Standalone Report Generation (Priority: P3)

An analyst has gathered findings manually and wants to generate a formatted report without running the full investigation workflow.

**Why this priority**: Report generation from arbitrary findings supports integration with manual analysis workflows.

**Independent Test**: Can be tested by running `/report` with a list of findings and verifying formatted output is generated.

**Acceptance Scenarios**:

1. **Given** the user has manual findings, **When** they run `/report --findings "Signups dropped 23%" --findings "Mobile Safari affected"`, **Then** a formatted report is generated from those inputs.

2. **Given** the user needs Slack-formatted output, **When** they run `/report --format slack`, **Then** the output includes Slack block formatting.

3. **Given** the user wants methodology documented, **When** they run `/report --include-methodology`, **Then** the report includes how findings were discovered.

---

### Edge Cases

- What happens when the Mixpanel project has no data in the requested date range?
- How does the system handle API rate limits during multi-query operations?
- What happens when an anomaly ID from a previous scan is no longer valid?
- How does the system behave when the project has no saved funnels or cohorts?
- What happens when the scan finds no anomalies (healthy product)?
- How does investigate handle anomalies with insufficient data for root cause analysis?
- What happens when LLM synthesis fails during report generation?

## Requirements *(mandatory)*

### Functional Requirements

**Context Tool**:
- **FR-001**: System MUST aggregate project metadata, events, funnels, cohorts, and bookmarks into a single context package
- **FR-002**: System MUST support optional inclusion of Lexicon schemas
- **FR-003**: System MUST support optional inclusion of sample property values
- **FR-004**: Context output MUST be optimized for AI agent context window efficiency (summary format, not full data dumps)

**Health Tool**:
- **FR-005**: System MUST generate a health dashboard with current period metrics and comparison to baseline
- **FR-006**: System MUST support configurable date ranges with sensible defaults (30 days)
- **FR-007**: System MUST support comparison to previous period, year-over-year, or custom dates
- **FR-008**: System MUST support focus areas (acquisition, activation, retention, revenue)
- **FR-009**: System MUST generate highlights (positive changes) and concerns (negative changes)
- **FR-010**: System MUST include daily time series data for trend visualization

**Scan Tool**:
- **FR-011**: System MUST detect statistical anomalies using outlier detection (z-score, IQR)
- **FR-012**: System MUST detect trend breaks using change point analysis
- **FR-013**: System MUST detect segment composition shifts
- **FR-014**: System MUST detect funnel step degradation
- **FR-015**: System MUST detect retention curve changes
- **FR-016**: System MUST assign unique identifiers to each anomaly for investigation reference
- **FR-017**: System MUST rank anomalies by severity multiplied by confidence
- **FR-018**: System MUST support configurable sensitivity levels (low, medium, high)
- **FR-019**: System MUST support filtering by dimensions and events
- **FR-020**: System MUST support including opportunity signals (positive anomalies)

**Investigate Tool**:
- **FR-021**: System MUST accept an anomaly ID from scan results OR manual specification (event, date, dimension)
- **FR-022**: System MUST perform dimensional decomposition to identify which segments changed
- **FR-023**: System MUST perform temporal analysis to identify when the anomaly started
- **FR-024**: System MUST perform cohort comparison between affected and unaffected users
- **FR-025**: System MUST identify contributing factors with confidence levels
- **FR-026**: System MUST support configurable investigation depth (quick, standard, deep)
- **FR-027**: System MUST support hypothesis testing when hypotheses are provided
- **FR-028**: System MUST include raw evidence and queries run for transparency

**Report Tool**:
- **FR-029**: System MUST synthesize investigation results into an executive summary
- **FR-030**: System MUST generate prioritized recommendations with effort and impact estimates
- **FR-031**: System MUST support multiple output formats (executive, detailed, slack)
- **FR-032**: System MUST optionally include methodology documentation
- **FR-033**: System MUST generate suggested follow-up actions
- **FR-034**: System MUST accept manual findings when no investigation is provided

**Cross-cutting**:
- **FR-035**: All tools MUST operate independently without requiring shared session state
- **FR-036**: All tools MUST compose existing MCP primitives (workspace_info, list_events, segmentation, etc.)
- **FR-037**: All tools MUST implement caching for discovery data within session duration
- **FR-038**: Query results MUST be cached with TTL based on data freshness requirements

### Key Entities

- **ContextPackage**: Aggregated project landscape including project info, events summary, funnels, cohorts, bookmarks, and optional schemas
- **HealthDashboard**: Current period metrics with comparison data, AARRR breakdown, highlights, concerns, and trend series
- **Anomaly**: Detected signal with unique ID, type, severity, category, summary, affected event/dimension, magnitude, confidence, and investigation context
- **ScanResults**: Collection of ranked anomalies with scan coverage and baseline statistics
- **ContributingFactor**: Factor contributing to an anomaly with contribution percentage, evidence, and confidence
- **Investigation**: Complete root cause analysis including anomaly, contributing factors, timeline, comparisons, and evidence
- **Recommendation**: Actionable suggestion with priority, impact estimate, and effort estimate
- **Report**: Formatted findings document with summary, key findings, sections, recommendations, and suggested follow-ups

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Full workflow (context → health → scan → investigate → report) completes in under 60 seconds for typical projects (under 100 events, 10 funnels)
- **SC-002**: Anomaly detection achieves at least 80% precision (flagged items are verified real issues when manually reviewed)
- **SC-003**: Reports include at least 3 specific, implementable recommendations per investigation
- **SC-004**: Each tool works reliably as a standalone command (no errors when run independently)
- **SC-005**: Agent can execute full workflow autonomously without human intervention for standard cases
- **SC-006**: Context package reduces agent context usage by at least 50% compared to manually gathering equivalent information
- **SC-007**: Health dashboard identifies concerning metrics with at least 90% recall (when human analysts review, 90%+ of real concerns are flagged)
- **SC-008**: Investigation correctly identifies root cause or primary contributing factor in at least 70% of cases (when verified against known issues)

## Assumptions

- The existing MCP server primitives (workspace_info, list_events, segmentation, retention, funnel, etc.) are stable and available
- AI agents using these tools have sufficient context window capacity for typical project outputs
- Mixpanel API rate limits are sufficient for the multi-query operations required by scan and investigate
- LLM synthesis via MCP sampling is available for report generation
- Standard statistical methods (z-score, IQR, change point analysis) are appropriate for anomaly detection without requiring ML models

## Dependencies

- Existing MCP tools: workspace_info, list_events, top_events, list_funnels, list_cohorts, list_bookmarks, lexicon_schemas, product_health_dashboard, event_counts, segmentation, retention, funnel, property_counts, property_distribution, diagnose_metric_drop, cohort_comparison, activity_feed, jql
- MCP sampling capability for LLM synthesis in report generation
- Claude Code plugin infrastructure for slash commands

## Out of Scope

- Anomaly persistence across sessions (detected anomalies are not stored long-term)
- Learning which anomalies users care about
- Scheduled/automated runs
- Integration with notification systems (Slack alerts, email)
- Custom comparison periods (vs competitor, vs goal) beyond previous period and year-over-year
