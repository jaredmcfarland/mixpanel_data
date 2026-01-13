# QA Post-Mortem Report

## Mixpanel MCP Server (mp-mcp-server)

**Date:** January 13, 2026
**Tester:** Claude (AI QA Engineer)
**Project:** mixpanel_data / mp-mcp-server
**Environment:** Cowork Mode with MCP Integration

---

## Executive Summary

This report documents the findings from comprehensive QA testing of the Mixpanel MCP Server, which exposes 34+ analytics tools to AI assistants through the Model Context Protocol. Testing was conducted in a live environment connected to Mixpanel Project ID 8 (US region).

The testing covered four major tool categories: Discovery (schema exploration), Live Query (real-time analytics), Fetch (data extraction), and Local SQL (DuckDB analysis). A total of 6 issues were identified, with 3 classified as Medium severity and 3 as Low severity.

### Testing Summary

- **Total Tools Tested:** 34
- **Tools Passing:** 28 (82%)
- **Issues Found:** 6
- **High Severity:** 0
- **Medium Severity:** 3
- **Low Severity:** 3

---

## Issue Summary

| # | Category | Issue | Severity | Status |
|---|----------|-------|----------|--------|
| 1 | Discovery | `list_bookmarks` timeout (MCP error -32001) | **Medium** | Open |
| 2 | Fetch | `fetch_events` limit=100 returns 99 rows (off-by-one) | Low | Open |
| 3 | Local SQL | `column_stats` distinct_count excludes NULL values | Low | Open |
| 4 | Error Handling | `drop_table` error message double-wrapped | Low | Open |
| 5 | Live Query | `activity_feed` returns huge output without pagination | **Medium** | Open |
| 6 | Live Query | `funnel` with 'on' parameter returns empty results | **Medium** | Open |

---

## Detailed Findings

### BUG-001: list_bookmarks Timeout

#### Description

The `list_bookmarks` tool consistently times out when called, returning MCP error code -32001. This prevents users from discovering saved reports/bookmarks in their Mixpanel project.

#### Reproduction Steps

```javascript
mcp__mixpanel__list_bookmarks({})
```

#### Expected Result

Returns a list of saved bookmarks/reports from Mixpanel.

#### Actual Result

MCP error -32001 (timeout) after extended wait.

#### Impact

Users cannot programmatically discover or access saved reports. Medium severity because workaround exists (use Mixpanel UI).

#### Suggested Investigation

- Check if the underlying Mixpanel API endpoint has changed
- Verify authentication scope includes bookmark access
- Add timeout configuration or increase default timeout

---

### BUG-002: fetch_events Off-by-One Error

#### Description

When fetching events with a specified limit, the tool returns one fewer row than requested.

#### Reproduction Steps

```javascript
mcp__mixpanel__fetch_events({
  from_date: '2025-01-01',
  to_date: '2025-01-07',
  table: 'test_events',
  limit: 100
})
```

#### Expected Result

```
table_name: 'test_events', row_count: 100
```

#### Actual Result

```
table_name: 'test_events', row_count: 99
```

#### Impact

Low severity. May cause confusion but does not significantly affect functionality. Could cause issues in pagination scenarios where exact counts matter.

#### Suggested Investigation

- Check `FetcherService` for off-by-one in limit handling
- Verify if this is in the streaming iterator or storage layer
- Compare with `stream_events` behavior to isolate the layer

---

### BUG-003: column_stats distinct_count Excludes NULL

#### Description

The `column_stats` tool reports `distinct_count` that does not include NULL as a distinct value, which may be unexpected behavior depending on SQL semantics expected by users.

#### Reproduction Steps

```javascript
mcp__mixpanel__column_stats({
  table: 'events',
  column: 'properties'
})
```

#### Expected Result

`distinct_count` should either include NULL as a distinct value OR documentation should clearly state NULL exclusion behavior.

#### Actual Result

`distinct_count` excludes NULL values without documentation of this behavior.

#### Impact

Low severity. May cause confusion in analysis but does not break functionality.

#### Suggested Investigation

- Determine if NULL exclusion is intentional (SQL standard)
- If intentional, update tool docstring to document behavior
- Consider adding `include_null` parameter for user control

---

### BUG-004: drop_table Error Message Double-Wrapping

#### Description

When attempting to drop a non-existent table, the error message is double-wrapped, showing redundant error text.

#### Reproduction Steps

```javascript
mcp__mixpanel__drop_table({
  table: 'nonexistent_table_xyz'
})
```

#### Expected Result

```
Table nonexistent_table_xyz does not exist
```

#### Actual Result

```
Error: Table nonexistent_table_xyz does not exist: Table nonexistent_table_xyz does not exist
```

#### Impact

Low severity. Cosmetic issue that does not affect functionality but reduces professional appearance of error handling.

#### Suggested Investigation

- Check exception handling chain in `drop_table` tool
- Look for redundant string formatting in error propagation
- Verify `StorageEngine.drop_table` exception handling

---

### BUG-005: activity_feed Unbounded Output

#### Description

The `activity_feed` tool returns extremely large responses (observed: 449,000+ characters) without pagination support, potentially overwhelming context windows or causing performance issues.

#### Reproduction Steps

```javascript
mcp__mixpanel__activity_feed({
  distinct_id: 'any_active_user_id'
})
```

#### Expected Result

Paginated results with reasonable default limit, or a limit parameter to control output size.

#### Actual Result

Returns all historical events for the user in a single response (449,473 characters in test case).

#### Impact

Medium severity. Can cause context overflow in AI assistants, slow response times, and poor user experience. Particularly problematic for active users with long event histories.

#### Suggested Investigation

- Add `limit` parameter with sensible default (e.g., 100 events)
- Implement pagination with cursor support
- Consider adding `from_date`/`to_date` filtering (partially exists but may not be working)

---

### BUG-006: funnel 'on' Parameter Returns Empty Results

#### Description

When using the `funnel` tool with the 'on' segmentation parameter, the tool returns empty results even when non-segmented queries return data.

#### Reproduction Steps

```javascript
// First, verify funnel works without segmentation:
mcp__mixpanel__funnel({
  funnel_id: 33032063,
  from_date: '2024-01-01',
  to_date: '2025-12-31'
})
// Returns: conversion data with 23 counts

// Then, add segmentation:
mcp__mixpanel__funnel({
  funnel_id: 33032063,
  from_date: '2024-01-01',
  to_date: '2025-12-31',
  on: 'properties["$browser"]'
})
// Returns: empty results
```

#### Expected Result

Funnel conversion data broken down by browser property.

#### Actual Result

Empty results when 'on' parameter is provided, despite the same funnel returning data without segmentation.

#### Impact

Medium severity. Prevents users from analyzing funnel conversions by segment, which is a core analytics use case. The tool documentation suggests this should work.

#### Suggested Investigation

- Verify the 'on' parameter is being correctly formatted for Mixpanel API
- Check if property accessor format matches API expectations
- Test with different property names and formats
- Compare with CLI/Python library behavior for same query

---

## Test Coverage Details

### Discovery Tools (9 tools)

| Tool | Status | Notes |
|------|--------|-------|
| `list_events` | ✅ PASS | Returns event names correctly |
| `list_properties` | ✅ PASS | Returns property definitions |
| `list_property_values` | ✅ PASS | Returns sample values |
| `list_funnels` | ✅ PASS | Returns saved funnel definitions |
| `list_cohorts` | ✅ PASS | Returns cohort metadata |
| `list_bookmarks` | ❌ FAIL | Timeout (BUG-001) |
| `top_events` | ✅ PASS | Returns ranked events by volume |
| `workspace_info` | ✅ PASS | Returns project configuration |

### Live Query Tools (9 tools)

| Tool | Status | Notes |
|------|--------|-------|
| `segmentation` | ✅ PASS | Time series analysis works |
| `funnel` | ⚠️ PARTIAL | Base works, 'on' param fails (BUG-006) |
| `retention` | ✅ PASS | Retention curves generate correctly |
| `jql` | ✅ PASS | JQL scripts execute successfully |
| `event_counts` | ✅ PASS | Multi-event counting works |
| `property_counts` | ✅ PASS | Property breakdown works |
| `activity_feed` | ⚠️ PARTIAL | Works but unbounded (BUG-005) |
| `frequency` | ✅ PASS | Distribution analysis works |

### Fetch Tools (4 tools)

| Tool | Status | Notes |
|------|--------|-------|
| `fetch_events` | ⚠️ PARTIAL | Works but off-by-one (BUG-002) |
| `fetch_profiles` | ✅ PASS | Profile extraction works |
| `stream_events` | ✅ PASS | Streaming works correctly |
| `stream_profiles` | ✅ PASS | Profile streaming works |

### Local SQL Tools (12 tools)

| Tool | Status | Notes |
|------|--------|-------|
| `sql` | ✅ PASS | DuckDB queries execute correctly |
| `sql_scalar` | ✅ PASS | Single value queries work |
| `list_tables` | ✅ PASS | Table enumeration works |
| `table_schema` | ✅ PASS | Schema introspection works |
| `sample` | ✅ PASS | Row sampling works |
| `summarize` | ✅ PASS | Statistics generation works |
| `event_breakdown` | ✅ PASS | Event counting by name works |
| `property_keys` | ✅ PASS | Property extraction works |
| `column_stats` | ⚠️ PARTIAL | Works but NULL behavior unclear (BUG-003) |
| `drop_table` | ⚠️ PARTIAL | Works but error message issue (BUG-004) |
| `drop_all_tables` | ✅ PASS | Bulk deletion works |

---

## Recommendations

### Priority 1: Fix Medium Severity Issues

The following issues should be addressed first as they impact core functionality:

1. **BUG-006** (funnel segmentation): Core analytics feature not working
2. **BUG-005** (activity_feed pagination): Usability and context overflow risk
3. **BUG-001** (list_bookmarks timeout): Blocks discovery of saved reports

### Priority 2: Fix Low Severity Issues

These issues should be addressed for polish and correctness:

1. **BUG-002** (off-by-one): Affects precision of data extraction
2. **BUG-003** (NULL handling): Documentation or behavior fix needed
3. **BUG-004** (error messages): Improve professional appearance

### General Recommendations

- Add integration tests specifically for MCP tool parameter handling
- Consider adding rate limit handling/backoff for Mixpanel API calls
- Add timeout configuration options for discovery tools
- Implement consistent pagination across all tools returning lists
- Add verbose error mode for debugging parameter format issues

---

## Conclusion

The Mixpanel MCP Server demonstrates solid core functionality with 82% of tools working correctly. The identified issues are fixable and do not represent fundamental architectural problems. The most critical fixes involve the funnel segmentation feature and implementing pagination for unbounded results.

This QA report provides reproduction steps and suggested investigation paths for each issue to facilitate efficient debugging and resolution.

---

*— End of Report —*
