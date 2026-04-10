# Changelog

All notable changes to `mixpanel_data` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- **Cohort event-property filters now raise instead of producing silent wrong results.**
  `Filter.in_cohort()` and `Filter.not_in_cohort()` with an inline
  `CohortDefinition` containing `CohortCriteria.did_event(where=...)` now
  raise `ValueError` with actionable workaround suggestions. Previously,
  Mixpanel's inline cohort evaluator silently ignored event-property filter
  operators — string filters collapsed to `is_set` semantics, and numeric
  filters were dropped entirely — returning plausible but wrong population
  counts with no error or warning.

  **Affected API surface**: `Filter.in_cohort(CohortDefinition, ...)` and
  `Filter.not_in_cohort(CohortDefinition, ...)` when the definition contains
  any `CohortCriteria.did_event(..., where=Filter.X(...))`.

  **Migration**: If your code passes event-property filters inside inline
  cohort definitions, switch to one of these working alternatives:
  - Top-level: `ws.query("event", where=Filter.equals("prop", "val"))`
  - Funnels: `FunnelStep("event", filters=[Filter.equals("prop", "val")])`
  - Retention: `RetentionEvent("event", filters=[Filter.equals("prop", "val")])`
  - Saved cohort: `ws.create_cohort(...)` then `Filter.in_cohort(<saved_id>)`

  **Root cause**: The inline cohort selector uses a legacy
  `event_selector.selector` JSON schema with operators (`==`, `!=`,
  `defined`, `not defined`, `>`, `<`) that the server's cohort engine
  does not honor. The top-level filter path uses a different, fully
  supported schema (`filterOperator`, `filterValue`, etc.). This is a
  server-side bug; the client-side guard prevents callers from hitting it.
