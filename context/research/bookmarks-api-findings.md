# Mixpanel Bookmarks API Research Findings

**Date:** 2025-12-25
**Status:** Validated via testing against production Mixpanel API

This document catalogs findings from investigating the undocumented Mixpanel Bookmarks API and its integration with the Query APIs for saved reports.

## Overview

Mixpanel uses "bookmarks" as the internal representation for saved reports across all report types. The Bookmarks API provides a way to programmatically list saved reports, and the Query APIs can execute them by `bookmark_id`.

## Bookmarks API

### Endpoint

```
GET /api/app/projects/{project_id}/bookmarks
GET /api/app/workspaces/{workspace_id}/bookmarks
```

### Authentication

Service Account Basic Auth (same as other Mixpanel APIs).

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `v` | int | API version. Use `2` for better performance and response format. |
| `type` | string | Filter by bookmark type (see below). |
| `id[]` | int | Fetch specific bookmark(s) by ID. |
| `eligible_for_dashboard` | bool | Only return dashboard-eligible bookmarks. |

### Bookmark Types

| Type | Description | Count (test project) |
|------|-------------|---------------------|
| `insights` | Insights/segmentation reports | 2,059 |
| `funnels` | Funnel reports | 282 |
| `retention` | Retention reports | 144 |
| `flows` | Flows/Sankey reports | 74 |
| `launch-analysis` | Impact Reports | 2 |
| `segmentation3` | Legacy segmentation (documented but none found) | 0 |

### Response Structure (v2)

```python
{
    "results": [
        {
            "id": 63877017,                    # Bookmark ID for Query API
            "name": "Monthly Recurring Revenue",
            "type": "insights",
            "project_id": 3409416,
            "workspace_id": None,
            "dashboard_id": None,              # Parent dashboard if linked
            "created": "2024-09-18T16:39:49",
            "modified": "2025-08-26T05:16:50",
            "creator_id": 12345,
            "creator_name": "John Doe",
            "creator_email": "john@example.com",
            "description": "...",
            "icon": "...",
            "params": {...},                   # Full query configuration
            "is_visibility_restricted": False,
            "is_modification_restricted": False,
            "can_view": True,
            "can_share": True,
            # ... additional metadata
        }
    ]
}
```

### Example Usage

```python
import mixpanel_data as mp

ws = mp.Workspace()
client = ws.api

# List all Insights bookmarks
url = f"https://mixpanel.com/api/app/projects/{client.project_id}/bookmarks"
response = client.request("GET", url, params={"type": "insights", "v": 2})

for bookmark in response["results"]:
    print(f"{bookmark['id']}: {bookmark['name']}")
```

## Querying Saved Reports

### Endpoint Compatibility Matrix

| Bookmark Type | `/api/query/insights` | `/api/query/retention` | `/api/query/arb_funnels` |
|--------------|----------------------|----------------------|-------------------------|
| `insights` | ✅ Native | ❌ | ❌ |
| `retention` | ✅ Normalized | ✅ Native | ❌ |
| `funnels` | ✅ Normalized | ❌ | ✅ Native |
| `flows` | ❌ | ❌ | ✅ (requires `query_type`) |

### Key Finding: Insights Endpoint is Universal

The `/api/query/insights` endpoint accepts `insights`, `retention`, and `funnels` bookmark types. It normalizes responses to a unified schema:

```python
{
    "headers": ["$retention", "segment"],  # Indicates data type
    "computed_at": "2025-12-25T04:45:53.842011+00:00",
    "date_range": {...},
    "meta": {...},
    "series": {
        "Metric Name": {"segment1": value1, "segment2": value2}
    }
}
```

This means `ws.insights(bookmark_id=...)` works for:
- Insights reports ✅
- Retention reports ✅ (headers include `$retention`)
- Funnel reports ✅

### Flows Require Special Handling

Flows bookmarks require the `/api/query/arb_funnels` endpoint with explicit `query_type`:

```python
client.request(
    "GET",
    "https://mixpanel.com/api/query/arb_funnels",
    params={
        "bookmark_id": 63880055,
        "project_id": client.project_id,
        "query_type": "flows_sankey"  # or "flows"
    }
)
```

Response format:
```python
{
    "steps": [...],
    "breakdowns": [...],
    "overallConversionRate": 0.15,
    "metadata": {...},
    "computed_at": "..."
}
```

### Native vs Normalized Response Formats

**Retention via `/api/query/retention`** (native cohort format):
```python
{
    "2024-03-18T00:00:00": {...},
    "2024-03-25T00:00:00": {...},
    # Keys are cohort dates
}
```

**Retention via `/api/query/insights`** (normalized):
```python
{
    "headers": ["$retention", "segment"],
    "series": {"born_event and then return_event": {...}}
}
```

**Funnels via `/api/query/arb_funnels`** (native):
```python
{
    "computed_at": "...",
    "data": [...],  # Step-by-step conversion data
    "meta": {...},
    "min_sampling_factor": 1.0
}
```

### Normalized Response Data Quality

**Key Finding:** The normalized responses from `/api/query/insights` contain **complete, useful data** - not just metadata.

**Retention Data Structure (via insights endpoint):**
```python
result = ws.insights(bookmark_id=63880740)  # retention bookmark
result.headers  # ['$retention', 'segment']
result.series   # Full retention matrix:
# {
#     'integrate SDK and then Any event': {
#         '2024-03-18T00:00:00-07:00': {
#             '$overall': {
#                 'first': 3123,                    # Cohort size
#                 'counts': [1317, 1296, 1282, ...], # Returning users per period
#                 'rates': [0.4217, 0.415, 0.4105, ...] # Retention rates
#             },
#             'SMB': {'first': 1543, 'counts': [...], 'rates': [...]},
#             'Mid Market': {'first': 1056, 'counts': [...], 'rates': [...]},
#             'Enterprise': {'first': 524, 'counts': [...], 'rates': [...]}
#         },
#         '2024-03-25T00:00:00-07:00': {...},
#         # Additional cohort dates...
#     }
# }
```

**What's included:**
- ✅ Full cohort sizes (`first`)
- ✅ Absolute return counts per period (`counts`)
- ✅ Retention rates per period (`rates`)
- ✅ All configured segments
- ✅ All cohort dates in the report

**Current limitation:** `InsightsResult.df` doesn't parse the nested retention structure optimally - it stores the nested dict as a single column. The raw `result.series` dict contains all the data needed for proper retention analysis.

### Native vs Normalized: Data Richness Comparison

#### Retention Bookmarks
**Same data, different structure.** Both endpoints return:
- `first`: Cohort size
- `counts`: Array of returning users per period
- `rates`: Array of retention rates per period

The normalized format adds metadata (`headers`, `date_range`, `computed_at`).

#### Funnel Bookmarks
**Native is richer.** Normalized loses:

| Data | Native | Normalized |
|------|--------|------------|
| Per-date breakdown | ✅ Data per month | ❌ Aggregated only |
| Frequency buckets | ✅ `convert_step_freq_buckets` | ❌ Missing |
| Dropoff distribution | ✅ `dropoff_step_freq_buckets` | ❌ Missing |
| Rate distributions | ✅ `conversion_rate_step_freq_buckets` | ❌ Missing |

**Native funnel data includes:**
```python
{
  "2024-09-01": {
    "steps": [{
      "count": 2045,
      "event": "sign up",
      "step_conv_ratio": 1,
      "overall_conv_ratio": 1,
      "avg_time": null,
      "convert_step_freq_buckets": {"buckets": [452, 14, 1, ...]},  # How many converted 1x, 2x, 3x
      "dropoff_step_freq_buckets": {"buckets": [1510, 68, ...]},   # Dropoff distribution
    }, ...]
  }
}
```

**Normalized funnel data (simpler but less detailed):**
```python
{
  "count": {"1. sign up": {"all": 6030}, "2. integrate SDK": {"all": 2844}},
  "overall_conv_ratio": {"1. sign up": {"all": 1.0}, "2. integrate SDK": {"all": 0.47}},
  "step_conv_ratio": {...},
  "avg_time": {...},
  "avg_time_from_start": {...}
}
```

#### Recommendation by Report Type

| Report Type | Recommended Endpoint | Reason |
|-------------|---------------------|--------|
| Retention | Either | Same data |
| Funnels | `/api/query/arb_funnels` (native) | Per-date trends + frequency buckets |
| Flows | `/api/query/arb_funnels` + `query_type=flows` | Only option |
| Insights | `/api/query/insights` | Native endpoint |

## Series Key Naming

The `series` key in `InsightsResult` is the **metric definition**, NOT the bookmark name:

| Bookmark Name | Series Key |
|---------------|------------|
| "Monthly Recurring Revenue" | `Monthly Recurring Revenue` (happens to match) |
| "MRR Trend" | `MRR [Sum of MRR]` |
| "MRR Growth" | `MRR [Sum of MRR]` |
| "Retention after Integrating" | `integrate SDK and then Any event` |

To get the user-friendly report name, query the Bookmarks API - it's not available in the query response.

## Regional Endpoints

| Region | Bookmarks API Base | Query API Base |
|--------|-------------------|----------------|
| US | `https://mixpanel.com` | `https://mixpanel.com` |
| EU | `https://eu.mixpanel.com` | `https://eu.mixpanel.com` |
| IN | `https://in.mixpanel.com` | `https://in.mixpanel.com` |

## Implementation Recommendations

### 1. Add `list_bookmarks()` Method

```python
def list_bookmarks(
    self,
    bookmark_type: Literal["insights", "funnels", "retention", "flows"] | None = None,
) -> list[BookmarkInfo]:
    """List saved reports (bookmarks) in the project."""
```

### 2. Extend `insights()` Documentation

Document that `ws.insights(bookmark_id)` works for insights, retention, and funnel bookmarks. Consider renaming to `query_saved_report()` or adding an alias.

### 3. Add `flows()` Method for Saved Flows

```python
def flows(self, bookmark_id: int) -> FlowsResult:
    """Query a saved Flows report."""
    # Use /api/query/arb_funnels with query_type=flows_sankey
```

### 4. Consider Unified `query_bookmark()` Method

```python
def query_bookmark(self, bookmark_id: int) -> InsightsResult | FunnelResult | FlowsResult:
    """Query any saved report by bookmark ID.

    Automatically determines the correct endpoint based on bookmark type.
    """
```

## Test Script

A working test script is available at [`scripts/test_bookmarks_api.py`](../scripts/test_bookmarks_api.py).

## References

- [Bookmark ID Guide](implementation-plans/bookmark_id_guide.md) - Original research document
- [Live Analytics Guide](../docs/guide/live-analytics.md) - Current documentation for `ws.insights()`
