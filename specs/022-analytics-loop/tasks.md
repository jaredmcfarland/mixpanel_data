# Tasks: Operational Analytics Loop

**Input**: Design documents from `/specs/022-analytics-loop/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Tests are included as this project requires pytest coverage per CLAUDE.md (90% coverage minimum).

**Organization**: Tasks are organized to enable incremental delivery. Each tool is a self-contained increment that contributes to multiple user stories.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story(s) this task belongs to (US1, US2, etc.)
- Include exact file paths in descriptions

## User Story Mapping

| Tool | Contributes To | Standalone Story |
|------|----------------|------------------|
| context | US1 | - |
| health | US1, US2 | US2 |
| scan | US1, US4 | US4 |
| investigate | US1, US3 | US3 |
| report | US1, US5 | US5 |

---

## Phase 1: Setup

**Purpose**: Create project structure and configure imports

- [ ] T001 Create workflows directory at mp_mcp/src/mp_mcp/tools/workflows/
- [ ] T002 Create __init__.py at mp_mcp/src/mp_mcp/tools/workflows/__init__.py with tool re-exports
- [ ] T003 Update mp_mcp/src/mp_mcp/tools/__init__.py to import workflows module
- [ ] T004 Update mp_mcp/src/mp_mcp/server.py to import workflows tools

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add all shared dataclasses that tools depend on

**⚠️ CRITICAL**: No tool implementation can begin until types are defined

### Types for All Tools

- [ ] T005 [P] Add DateRange dataclass to mp_mcp/src/mp_mcp/types.py
- [ ] T006 [P] Add Metric dataclass to mp_mcp/src/mp_mcp/types.py
- [ ] T007 [P] Add DataPoint dataclass to mp_mcp/src/mp_mcp/types.py

### Types for Context Tool

- [ ] T008 [P] Add EventsSummary dataclass to mp_mcp/src/mp_mcp/types.py
- [ ] T009 [P] Add PropertiesSummary dataclass to mp_mcp/src/mp_mcp/types.py
- [ ] T010 [P] Add FunnelSummary dataclass to mp_mcp/src/mp_mcp/types.py
- [ ] T011 [P] Add CohortSummary dataclass to mp_mcp/src/mp_mcp/types.py
- [ ] T012 [P] Add BookmarksSummary dataclass to mp_mcp/src/mp_mcp/types.py
- [ ] T013 Add ContextPackage dataclass to mp_mcp/src/mp_mcp/types.py (depends on T008-T012)

### Types for Health Tool

- [ ] T014 Add HealthDashboard dataclass to mp_mcp/src/mp_mcp/types.py (depends on T005-T007)

### Types for Scan Tool

- [ ] T015 [P] Add Anomaly dataclass to mp_mcp/src/mp_mcp/types.py
- [ ] T016 Add ScanResults dataclass to mp_mcp/src/mp_mcp/types.py (depends on T005, T015)

### Types for Investigate Tool

- [ ] T017 [P] Add ContributingFactor dataclass to mp_mcp/src/mp_mcp/types.py
- [ ] T018 [P] Add TimelineEvent dataclass to mp_mcp/src/mp_mcp/types.py
- [ ] T019 Add Investigation dataclass to mp_mcp/src/mp_mcp/types.py (depends on T015, T017, T018)

### Types for Report Tool

- [ ] T020 [P] Add Recommendation dataclass to mp_mcp/src/mp_mcp/types.py
- [ ] T021 [P] Add ReportSection dataclass to mp_mcp/src/mp_mcp/types.py
- [ ] T022 Add Report dataclass to mp_mcp/src/mp_mcp/types.py (depends on T005, T020, T021)

### Helper Functions

- [ ] T023 Add generate_anomaly_id() helper function to mp_mcp/src/mp_mcp/tools/workflows/__init__.py per research.md

**Checkpoint**: All types defined - tool implementation can now begin

---

## Phase 3: Context Tool (US1)

**Goal**: Implement context tool that aggregates project landscape for analytics workflow

**Independent Test**: Call context() and verify it returns project metadata, events, funnels, cohorts

### Tests for Context Tool

- [ ] T024 [P] [US1] Create unit test file mp_mcp/tests/unit/test_tools_workflows_context.py with test fixtures
- [ ] T025 [P] [US1] Add test_context_basic() - verify context returns all required fields
- [ ] T026 [P] [US1] Add test_context_with_schemas() - verify include_schemas parameter
- [ ] T027 [P] [US1] Add test_context_error_handling() - verify graceful handling of partial failures

### Implementation for Context Tool

- [ ] T028 [US1] Create context tool skeleton in mp_mcp/src/mp_mcp/tools/workflows/context.py with @mcp.tool and @handle_errors decorators
- [ ] T029 [US1] Implement _gather_events() helper that calls workspace_info, list_events, top_events
- [ ] T030 [US1] Implement _gather_funnels_cohorts() helper that calls list_funnels, list_cohorts
- [ ] T031 [US1] Implement _gather_bookmarks() helper that calls list_bookmarks
- [ ] T032 [US1] Implement _gather_schemas() helper that calls lexicon_schemas (optional)
- [ ] T033 [US1] Implement main context() function that composes helpers into ContextPackage
- [ ] T034 [US1] Update mp_mcp/src/mp_mcp/tools/workflows/__init__.py to export context
- [ ] T035 [US1] Run tests and verify context tool passes all test cases

**Checkpoint**: Context tool complete and tested

---

## Phase 4: Health Tool (US1, US2)

**Goal**: Implement health tool that generates KPI dashboard with comparison metrics

**Independent Test**: Call health() standalone and verify it returns dashboard with metrics and trends

### Tests for Health Tool

- [ ] T036 [P] [US1,US2] Create unit test file mp_mcp/tests/unit/test_tools_workflows_health.py with test fixtures
- [ ] T037 [P] [US1,US2] Add test_health_basic() - verify health returns metrics and comparison
- [ ] T038 [P] [US1,US2] Add test_health_date_range() - verify custom date range handling
- [ ] T039 [P] [US1,US2] Add test_health_focus_area() - verify focus parameter filters metrics
- [ ] T040 [P] [US1,US2] Add test_health_highlights_concerns() - verify highlights and concerns generation

### Implementation for Health Tool

- [ ] T041 [US1,US2] Create health tool skeleton in mp_mcp/src/mp_mcp/tools/workflows/health.py
- [ ] T042 [US1,US2] Implement _compute_date_ranges() helper for period calculation
- [ ] T043 [US1,US2] Implement _gather_metrics() helper that calls product_health_dashboard, event_counts
- [ ] T044 [US1,US2] Implement _compute_comparison() helper that calculates period-over-period changes
- [ ] T045 [US1,US2] Implement _generate_insights() helper that creates highlights and concerns lists
- [ ] T046 [US1,US2] Implement main health() function that composes helpers into HealthDashboard
- [ ] T047 [US1,US2] Update mp_mcp/src/mp_mcp/tools/workflows/__init__.py to export health
- [ ] T048 [US1,US2] Run tests and verify health tool passes all test cases

**Checkpoint**: Health tool complete - US2 (Quick Health Check) now functional

---

## Phase 5: Scan Tool (US1, US4)

**Goal**: Implement scan tool that detects anomalies using statistical methods

**Independent Test**: Call scan() and verify it returns ranked anomalies with unique IDs

### Tests for Scan Tool

- [ ] T049 [P] [US1,US4] Create unit test file mp_mcp/tests/unit/test_tools_workflows_scan.py with test fixtures
- [ ] T050 [P] [US1,US4] Add test_scan_basic() - verify scan returns anomalies list
- [ ] T051 [P] [US1,US4] Add test_scan_anomaly_id_generation() - verify deterministic IDs
- [ ] T052 [P] [US1,US4] Add test_scan_sensitivity_levels() - verify low/medium/high thresholds
- [ ] T053 [P] [US1,US4] Add test_scan_dimension_filter() - verify dimensions parameter
- [ ] T054 [P] [US1,US4] Add test_scan_graceful_degradation() - verify behavior when sampling unavailable

### Implementation for Scan Tool

- [ ] T055 [US1,US4] Create scan tool skeleton in mp_mcp/src/mp_mcp/tools/workflows/scan.py
- [ ] T056 [US1,US4] Implement _detect_zscore_anomalies() helper for statistical outlier detection
- [ ] T057 [US1,US4] Implement _detect_percentage_changes() helper for period comparison
- [ ] T058 [US1,US4] Implement _detect_trend_breaks() helper for SMA crossover detection
- [ ] T059 [US1,US4] Implement _rank_anomalies() helper that sorts by severity * confidence
- [ ] T060 [US1,US4] Implement _synthesize_anomalies() helper for AI-enhanced ranking (with graceful degradation)
- [ ] T061 [US1,US4] Implement main scan() function that composes detection methods
- [ ] T062 [US1,US4] Update mp_mcp/src/mp_mcp/tools/workflows/__init__.py to export scan
- [ ] T063 [US1,US4] Run tests and verify scan tool passes all test cases

**Checkpoint**: Scan tool complete - US4 (Ad-hoc Anomaly Scan) now functional

---

## Phase 6: Investigate Tool (US1, US3)

**Goal**: Implement investigate tool that performs root cause analysis on anomalies

**Independent Test**: Call investigate() with manual event/date params and verify root cause analysis

### Tests for Investigate Tool

- [ ] T064 [P] [US1,US3] Create unit test file mp_mcp/tests/unit/test_tools_workflows_investigate.py with test fixtures
- [ ] T065 [P] [US1,US3] Add test_investigate_with_anomaly_id() - verify anomaly_id lookup
- [ ] T066 [P] [US1,US3] Add test_investigate_with_manual_params() - verify event/date/dimension params
- [ ] T067 [P] [US1,US3] Add test_investigate_depth_levels() - verify quick/standard/deep
- [ ] T068 [P] [US1,US3] Add test_investigate_contributing_factors() - verify factor analysis
- [ ] T069 [P] [US1,US3] Add test_investigate_graceful_degradation() - verify behavior when sampling unavailable

### Implementation for Investigate Tool

- [ ] T070 [US1,US3] Create investigate tool skeleton in mp_mcp/src/mp_mcp/tools/workflows/investigate.py
- [ ] T071 [US1,US3] Implement _resolve_anomaly() helper that accepts id OR manual params
- [ ] T072 [US1,US3] Implement _dimensional_decomposition() helper using segmentation by dimensions
- [ ] T073 [US1,US3] Implement _temporal_analysis() helper to identify anomaly start time
- [ ] T074 [US1,US3] Implement _cohort_comparison() helper using existing cohort_comparison primitive
- [ ] T075 [US1,US3] Implement _identify_factors() helper that aggregates contributing factors
- [ ] T076 [US1,US3] Implement _synthesize_investigation() helper for AI-enhanced root cause (with graceful degradation)
- [ ] T077 [US1,US3] Implement main investigate() function that composes analysis methods
- [ ] T078 [US1,US3] Update mp_mcp/src/mp_mcp/tools/workflows/__init__.py to export investigate
- [ ] T079 [US1,US3] Run tests and verify investigate tool passes all test cases

**Checkpoint**: Investigate tool complete - US3 (Investigate Known Issue) now functional

---

## Phase 7: Report Tool (US1, US5)

**Goal**: Implement report tool that synthesizes findings into actionable briefs

**Independent Test**: Call report() with manual findings and verify formatted output

### Tests for Report Tool

- [ ] T080 [P] [US1,US5] Create unit test file mp_mcp/tests/unit/test_tools_workflows_report.py with test fixtures
- [ ] T081 [P] [US1,US5] Add test_report_from_investigation() - verify synthesis from investigation
- [ ] T082 [P] [US1,US5] Add test_report_from_findings() - verify synthesis from manual findings
- [ ] T083 [P] [US1,US5] Add test_report_formats() - verify executive/detailed/slack formats
- [ ] T084 [P] [US1,US5] Add test_report_recommendations() - verify recommendations generation
- [ ] T085 [P] [US1,US5] Add test_report_graceful_degradation() - verify behavior when sampling unavailable

### Implementation for Report Tool

- [ ] T086 [US1,US5] Create report tool skeleton in mp_mcp/src/mp_mcp/tools/workflows/report.py
- [ ] T087 [US1,US5] Implement _extract_findings() helper that handles investigation OR manual findings
- [ ] T088 [US1,US5] Implement _generate_summary() helper for executive summary synthesis
- [ ] T089 [US1,US5] Implement _generate_recommendations() helper based on findings
- [ ] T090 [US1,US5] Implement _format_markdown() helper for markdown output
- [ ] T091 [US1,US5] Implement _format_slack_blocks() helper for Slack output
- [ ] T092 [US1,US5] Implement main report() function that composes formatting methods
- [ ] T093 [US1,US5] Update mp_mcp/src/mp_mcp/tools/workflows/__init__.py to export report
- [ ] T094 [US1,US5] Run tests and verify report tool passes all test cases

**Checkpoint**: Report tool complete - US5 (Standalone Report) now functional. US1 (Daily Analytics Check) now complete.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Add slash commands, documentation, and final quality checks

### Slash Commands

- [ ] T095 [P] Create /mp-context slash command in mixpanel-plugin/commands/mp-context.md
- [ ] T096 [P] Create /mp-health slash command in mixpanel-plugin/commands/mp-health.md
- [ ] T097 [P] Create /mp-scan slash command in mixpanel-plugin/commands/mp-scan.md
- [ ] T098 [P] Create /mp-investigate slash command in mixpanel-plugin/commands/mp-investigate.md
- [ ] T099 [P] Create /mp-report slash command in mixpanel-plugin/commands/mp-report.md

### Skill Documentation

- [ ] T100 Create operational-loop skill doc in mixpanel-plugin/skills/mixpanel-data/operational-loop.md

### Workflow Prompt (Optional)

- [ ] T101 Add workflow_guidance prompt to mp_mcp/src/mp_mcp/prompts.py

### Quality Checks

- [ ] T102 Run `just check` to verify lint, typecheck, and test pass
- [ ] T103 Run `just test-cov` to verify 90%+ coverage
- [ ] T104 Validate quickstart.md examples work end-to-end
- [ ] T105 Update mp_mcp README with workflow tools documentation

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1: Setup
    ↓
Phase 2: Foundational (types.py)
    ↓
Phase 3-7: Tools (can run in priority order)
    ↓
Phase 8: Polish
```

### Tool Dependencies (within Phases 3-7)

```
context (Phase 3) ─────────────────────────────────────────┐
    ↓                                                      │
health (Phase 4) ──────────────────────────────────────────┤
    ↓                                                      │
scan (Phase 5) ────────────────────────────────────────────┤
    ↓                                                      │
investigate (Phase 6) ────────────────────────────────────>│
    ↓                                                      │
report (Phase 7) ──────────────────────────────────────────┘
                                                           ↓
                                               US1 Complete
```

### User Story Completion Order

| After Phase | User Stories Complete |
|-------------|----------------------|
| Phase 4 | US2 (Quick Health Check) |
| Phase 5 | US4 (Ad-hoc Anomaly Scan) |
| Phase 6 | US3 (Investigate Known Issue) |
| Phase 7 | US1 (Daily Analytics Check), US5 (Standalone Report) |

---

## Parallel Opportunities

### Phase 2 (Foundational Types)

All type tasks marked [P] can run in parallel - they're in different dataclass definitions:

```bash
# Parallel batch 1: Supporting types
Task: T005 "Add DateRange dataclass"
Task: T006 "Add Metric dataclass"
Task: T007 "Add DataPoint dataclass"

# Parallel batch 2: Context types
Task: T008-T012 (all EventsSummary through BookmarksSummary)

# Parallel batch 3: Other tool types
Task: T015 "Add Anomaly dataclass"
Task: T017 "Add ContributingFactor dataclass"
Task: T018 "Add TimelineEvent dataclass"
Task: T020 "Add Recommendation dataclass"
Task: T021 "Add ReportSection dataclass"
```

### Within Each Tool Phase

Tests marked [P] can run in parallel within each phase:

```bash
# Phase 4 example - all health tests in parallel
Task: T036-T040 (all health tests)

# Then implementation sequentially
Task: T041-T048 (health implementation)
```

### Phase 8 (Slash Commands)

All slash command tasks (T095-T099) can run in parallel - different files:

```bash
Task: T095 "Create /mp-context slash command"
Task: T096 "Create /mp-health slash command"
Task: T097 "Create /mp-scan slash command"
Task: T098 "Create /mp-investigate slash command"
Task: T099 "Create /mp-report slash command"
```

---

## Implementation Strategy

### MVP First (Phases 1-4)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: Context tool
4. Complete Phase 4: Health tool
5. **STOP and VALIDATE**: Test `/health` independently (US2 complete)
6. Can demo daily health checks now

### Incremental Delivery

| Milestone | Stories Complete | Demo Capability |
|-----------|------------------|-----------------|
| After Phase 4 | US2 | Quick health checks |
| After Phase 5 | US2, US4 | Health + anomaly scans |
| After Phase 6 | US2, US3, US4 | Health + scans + investigations |
| After Phase 7 | All (US1-US5) | Full workflow + all standalone |

### Single Developer Approach

1. Work through phases sequentially (1 → 8)
2. Run tests after each tool phase
3. Each phase adds functional capability
4. Commit after each phase completes

---

## Notes

- All tools use `@mcp.tool` + `@handle_errors` decorator pattern
- All tools use `get_workspace(ctx)` for rate-limited access
- All results return `dict[str, Any]` via `asdict()`
- Intelligent tools (scan, investigate, report) implement graceful degradation
- Tests should mock Context and Workspace per existing patterns in mp_mcp/tests/unit/
- Per CLAUDE.md: use markdown code fences in docstrings, not doctest style `>>>`
