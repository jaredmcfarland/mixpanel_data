# Bookmarks API Implementation Plan

**Feature:** List and Query Saved Reports via Bookmarks API
**Date:** 2025-12-25
**Status:** Draft
**Approach:** Test-Driven Development (TDD)

## Overview

This plan implements features for working with Mixpanel's Bookmarks API:

1. **`list_bookmarks()`** - List saved reports in a project
2. **`query_saved_report()`** - Rename `insights()` to accurately describe its capability
3. **`query_flows()`** - Query saved Flows reports (requires different endpoint)
4. **CLI updates** - `mp inspect bookmarks`, `mp query saved-report`, `mp query flows`

## Background

See [bookmarks-api-findings.md](../research/bookmarks-api-findings.md) for research findings.

**Key discoveries:**
- Bookmarks API: `GET /api/app/projects/{project_id}/bookmarks`
- The "app" endpoint type is already configured in `ENDPOINTS`
- Current `ws.insights()` works for insights, retention, and funnel bookmarks
- Flows require special handling (`/api/query/arb_funnels` + `query_type=flows`)
- Native funnel format is richer, but normalized format is sufficient for most use cases

**Important distinction:**
- `bookmark_id` = ID of a **saved report configuration** (from Bookmarks API)
- `funnel_id` = ID of a **funnel definition** (steps only, used with custom date params)

| Method | Purpose | ID Type |
|--------|---------|---------|
| `query_saved_report(bookmark_id)` | Execute saved report as-is | bookmark_id |
| `query_flows(bookmark_id)` | Execute saved flows report | bookmark_id |
| `funnel(funnel_id, from_date, to_date)` | Run funnel with custom params | funnel_id |
| `retention(born_event, ...)` | Construct new retention query | N/A |

---

## Phase 1: Types and Models

### 1.1 Test Specification

**File:** `tests/unit/test_types_bookmarks.py`

```python
"""Unit tests for bookmark-related types."""

class TestBookmarkType:
    """Tests for BookmarkType literal."""

    def test_bookmark_type_values(self) -> None:
        """BookmarkType should include all valid types."""
        from mixpanel_data.types import BookmarkType
        # Verify Literal includes: insights, funnels, retention, flows, launch-analysis

class TestBookmarkInfo:
    """Tests for BookmarkInfo dataclass."""

    def test_bookmark_info_required_fields(self) -> None:
        """BookmarkInfo should have required id, name, type fields."""

    def test_bookmark_info_optional_fields(self) -> None:
        """BookmarkInfo should allow None for optional fields."""

    def test_bookmark_info_to_dict(self) -> None:
        """BookmarkInfo.to_dict() should return JSON-serializable dict."""

    def test_bookmark_info_immutable(self) -> None:
        """BookmarkInfo should be frozen (immutable)."""

class TestSavedReportResult:
    """Tests for SavedReportResult (replacing InsightsResult)."""

    def test_saved_report_result_fields(self) -> None:
        """SavedReportResult should have bookmark_id, headers, series fields."""

    def test_saved_report_result_report_type_insights(self) -> None:
        """report_type should return 'insights' for standard reports."""

    def test_saved_report_result_report_type_retention(self) -> None:
        """report_type should return 'retention' when headers contain $retention."""

    def test_saved_report_result_report_type_funnel(self) -> None:
        """report_type should return 'funnel' when headers contain $funnel."""

    def test_saved_report_result_series_is_any(self) -> None:
        """series should accept nested structures (dict[str, Any])."""

class TestFlowsResult:
    """Tests for FlowsResult type."""

    def test_flows_result_required_fields(self) -> None:
        """FlowsResult should have steps, breakdowns, overall_conversion_rate."""

    def test_flows_result_to_dict(self) -> None:
        """FlowsResult.to_dict() should return JSON-serializable dict."""
```

### 1.2 Implementation Specification

**File:** `src/mixpanel_data/types.py`

```python
BookmarkType = Literal["insights", "funnels", "retention", "flows", "launch-analysis"]
"""Valid bookmark types for saved reports."""

SavedReportType = Literal["insights", "retention", "funnel"]
"""Report type detected from SavedReportResult headers."""

@dataclass(frozen=True)
class BookmarkInfo:
    """Metadata for a saved report (bookmark).

    Represents a saved Insights, Funnel, Retention, or Flows report
    from the Mixpanel Bookmarks API.
    """

    id: int
    """Unique bookmark identifier (use with query methods)."""

    name: str
    """User-defined report name."""

    type: BookmarkType
    """Report type (insights, funnels, retention, flows, launch-analysis)."""

    project_id: int
    """Project this bookmark belongs to."""

    created: str
    """Creation timestamp (ISO format)."""

    modified: str
    """Last modification timestamp (ISO format)."""

    # Optional fields
    workspace_id: int | None = None
    """Workspace ID if bookmark is workspace-scoped."""

    dashboard_id: int | None = None
    """Parent dashboard ID if linked to a dashboard."""

    description: str | None = None
    """User-provided description."""

    creator_id: int | None = None
    """ID of the user who created the bookmark."""

    creator_name: str | None = None
    """Name of the user who created the bookmark."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary."""


@dataclass(frozen=True)
class SavedReportResult:
    """Data from a saved report (Insights, Retention, or Funnel).

    Replaces InsightsResult. The report type can be detected from headers:
    - Insights: Contains metric/event names
    - Retention: Contains "$retention"
    - Funnel: Contains "$funnel"

    The series structure varies by report type - use report_type property
    to determine how to interpret the data.
    """

    bookmark_id: int
    """Saved report identifier."""

    computed_at: str
    """When report was computed (ISO format)."""

    from_date: str
    """Report start date."""

    to_date: str
    """Report end date."""

    headers: list[str] = field(default_factory=list)
    """Report column headers (indicates report type)."""

    series: dict[str, Any] = field(default_factory=dict)
    """Report data. Structure varies by report_type."""

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def report_type(self) -> SavedReportType:
        """Detect report type from headers.

        Returns:
            'retention' if headers contain '$retention',
            'funnel' if headers contain '$funnel',
            'insights' otherwise.
        """
        if "$retention" in self.headers:
            return "retention"
        if "$funnel" in self.headers:
            return "funnel"
        return "insights"

    @property
    def df(self) -> pd.DataFrame:
        """Convert to DataFrame (best effort for insights reports)."""
        # Implementation similar to current InsightsResult.df

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary."""


@dataclass(frozen=True)
class FlowsResult:
    """Data from a saved Flows report.

    Flows reports show user paths through events, returned from
    the /api/query/arb_funnels endpoint with query_type=flows.
    """

    bookmark_id: int
    """Saved report identifier."""

    computed_at: str
    """When report was computed (ISO format)."""

    steps: list[dict[str, Any]] = field(default_factory=list)
    """Flow step data."""

    breakdowns: list[dict[str, Any]] = field(default_factory=list)
    """Breakdown data for flow paths."""

    overall_conversion_rate: float = 0.0
    """Overall conversion rate through the flow."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional metadata from the API."""

    _df_cache: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def df(self) -> pd.DataFrame:
        """Convert steps to DataFrame."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary."""
```

**Export in `__init__.py`:** Add `BookmarkInfo`, `BookmarkType`, `SavedReportResult`, `SavedReportType`, `FlowsResult` to public exports.

**Migration:** Remove `InsightsResult` (project not yet released, no backward compatibility needed).

---

## Phase 2: `list_bookmarks()` Implementation

### 2.1 API Client Layer

#### Test Specification

**File:** `tests/unit/test_api_client_bookmarks.py`

```python
"""Unit tests for bookmarks API client methods."""

class TestListBookmarks:
    """Tests for MixpanelAPIClient.list_bookmarks()."""

    def test_list_bookmarks_calls_correct_endpoint(self, test_credentials) -> None:
        """list_bookmarks() should call /api/app/projects/{project_id}/bookmarks."""
        # Verify URL contains /api/app/projects/{project_id}/bookmarks
        # Verify v=2 query param is set

    def test_list_bookmarks_includes_project_id_in_path(self, test_credentials) -> None:
        """list_bookmarks() should include project_id in URL path."""

    def test_list_bookmarks_filters_by_type(self, test_credentials) -> None:
        """list_bookmarks(bookmark_type='insights') should add type param."""

    def test_list_bookmarks_returns_results_array(self, test_credentials) -> None:
        """list_bookmarks() should return the 'results' array from response."""

    def test_list_bookmarks_handles_empty_results(self, test_credentials) -> None:
        """list_bookmarks() should return empty list when no bookmarks exist."""

    def test_list_bookmarks_auth_error_on_401(self, test_credentials) -> None:
        """list_bookmarks() should raise AuthenticationError on 401."""

    def test_list_bookmarks_permission_error_on_403(self, test_credentials) -> None:
        """list_bookmarks() should raise QueryError on 403."""
```

#### Implementation Specification

**File:** `src/mixpanel_data/_internal/api_client.py`

```python
def list_bookmarks(
    self,
    bookmark_type: str | None = None,
) -> list[dict[str, Any]]:
    """List saved reports (bookmarks) for the project.

    Args:
        bookmark_type: Optional filter by type ('insights', 'funnels',
            'retention', 'flows', 'launch-analysis').

    Returns:
        List of bookmark dictionaries from the API.

    Raises:
        AuthenticationError: Invalid credentials (401).
        QueryError: Permission denied or invalid request (400/403).
    """
    url = self._build_url("app", f"/projects/{self.project_id}/bookmarks")
    params: dict[str, Any] = {"v": 2}

    if bookmark_type:
        params["type"] = bookmark_type

    result = self._request("GET", url, params=params, inject_project_id=False)
    return result.get("results", [])
```

### 2.2 Discovery Service Layer

#### Test Specification

**File:** `tests/unit/test_discovery_bookmarks.py`

```python
"""Unit tests for bookmark discovery methods."""

class TestDiscoveryServiceBookmarks:
    """Tests for DiscoveryService.list_bookmarks()."""

    def test_list_bookmarks_returns_bookmark_info_list(self, discovery_factory) -> None:
        """list_bookmarks() should return List[BookmarkInfo]."""

    def test_list_bookmarks_parses_all_fields(self, discovery_factory) -> None:
        """list_bookmarks() should correctly parse API response fields."""

    def test_list_bookmarks_handles_optional_fields(self, discovery_factory) -> None:
        """list_bookmarks() should handle missing optional fields gracefully."""

    def test_list_bookmarks_filters_by_type(self, discovery_factory) -> None:
        """list_bookmarks(bookmark_type='retention') should filter results."""

    def test_list_bookmarks_propagates_auth_error(self, discovery_factory) -> None:
        """list_bookmarks() should propagate AuthenticationError."""
```

#### Implementation Specification

**File:** `src/mixpanel_data/_internal/services/discovery.py`

```python
def list_bookmarks(
    self,
    bookmark_type: BookmarkType | None = None,
) -> list[BookmarkInfo]:
    """List saved reports (bookmarks) for the project.

    Args:
        bookmark_type: Optional filter by report type.

    Returns:
        List of BookmarkInfo with metadata for each saved report.

    Raises:
        AuthenticationError: Invalid credentials.
        QueryError: Permission denied or invalid request.
    """
    raw_bookmarks = self._api_client.list_bookmarks(
        bookmark_type=bookmark_type
    )
    return [_parse_bookmark_info(bm) for bm in raw_bookmarks]


def _parse_bookmark_info(data: dict[str, Any]) -> BookmarkInfo:
    """Parse API response to BookmarkInfo."""
    return BookmarkInfo(
        id=data["id"],
        name=data["name"],
        type=data["type"],
        project_id=data["project_id"],
        created=data["created"],
        modified=data["modified"],
        workspace_id=data.get("workspace_id"),
        dashboard_id=data.get("dashboard_id"),
        description=data.get("description"),
        creator_id=data.get("creator_id"),
        creator_name=data.get("creator_name"),
    )
```

### 2.3 Workspace Facade Layer

#### Test Specification

**File:** `tests/unit/test_workspace_bookmarks.py`

```python
"""Unit tests for Workspace bookmark methods."""

class TestWorkspaceListBookmarks:
    """Tests for Workspace.list_bookmarks()."""

    def test_list_bookmarks_delegation(self, workspace_factory) -> None:
        """list_bookmarks() should delegate to DiscoveryService."""

    def test_list_bookmarks_returns_bookmark_info_list(self, workspace_factory) -> None:
        """list_bookmarks() should return List[BookmarkInfo]."""

    def test_list_bookmarks_requires_api_credentials(self, workspace_factory) -> None:
        """list_bookmarks() should raise ConfigError without credentials."""

    def test_list_bookmarks_with_type_filter(self, workspace_factory) -> None:
        """list_bookmarks(bookmark_type='funnels') should pass filter."""
```

#### Implementation Specification

**File:** `src/mixpanel_data/workspace.py`

```python
def list_bookmarks(
    self,
    bookmark_type: BookmarkType | None = None,
) -> list[BookmarkInfo]:
    """List saved reports (bookmarks) in the project.

    Retrieves metadata for saved Insights, Funnel, Retention, and Flows
    reports. Use the returned bookmark IDs with query methods.

    Args:
        bookmark_type: Filter by report type. If None, returns all types.

    Returns:
        List of BookmarkInfo with id, name, type, and metadata.

    Raises:
        ConfigError: If API credentials not available.
        AuthenticationError: Invalid credentials.
        QueryError: Permission denied.

    Example:
        ```python
        ws = mp.Workspace()

        # List all saved reports
        bookmarks = ws.list_bookmarks()
        for bm in bookmarks:
            print(f"{bm.id}: {bm.name} ({bm.type})")

        # Filter by type
        insights = ws.list_bookmarks(bookmark_type="insights")
        retention = ws.list_bookmarks(bookmark_type="retention")
        ```
    """
    return self._require_discovery_service().list_bookmarks(
        bookmark_type=bookmark_type
    )
```

### 2.4 CLI Command (Optional)

**File:** `src/mixpanel_data/cli/commands/inspect.py`

```bash
mp inspect bookmarks [--type insights|funnels|retention|flows]
```

---

## Phase 3: Rename `insights()` to `query_saved_report()`

### 3.1 Motivation

The current `insights()` method actually works for insights, retention, and funnel bookmarks. The name is misleading. Since this project is not yet released, we can simply rename the method.

### 3.2 Test Specification

**File:** `tests/unit/test_workspace_bookmarks.py` (extend)

```python
class TestWorkspaceQuerySavedReport:
    """Tests for Workspace.query_saved_report()."""

    def test_query_saved_report_delegates_to_live_query(self, workspace_factory) -> None:
        """query_saved_report() should delegate to LiveQueryService."""

    def test_query_saved_report_returns_saved_report_result(self, workspace_factory) -> None:
        """query_saved_report() should return SavedReportResult."""

    def test_query_saved_report_works_with_retention_bookmark(self, workspace_factory) -> None:
        """query_saved_report() should work with retention bookmark."""
        # Verify headers contain $retention, report_type == 'retention'

    def test_query_saved_report_works_with_funnel_bookmark(self, workspace_factory) -> None:
        """query_saved_report() should work with funnel bookmark."""
        # Verify headers contain $funnel, report_type == 'funnel'

    def test_query_saved_report_requires_api_credentials(self, workspace_factory) -> None:
        """query_saved_report() should raise ConfigError without credentials."""
```

### 3.3 Implementation Specification

**File:** `src/mixpanel_data/workspace.py`

```python
def query_saved_report(self, bookmark_id: int) -> SavedReportResult:
    """Query a saved report by bookmark ID.

    Executes a saved Insights, Retention, or Funnel report and returns
    the results. Use the ``report_type`` property to determine the data format:

    - ``"insights"``: Standard metrics/events data
    - ``"retention"``: Cohort retention data with counts and rates
    - ``"funnel"``: Funnel step conversion data

    For Flows reports, use ``query_flows()`` instead.

    Args:
        bookmark_id: ID of the saved report (from ``list_bookmarks()``
            or Mixpanel URL).

    Returns:
        SavedReportResult with report data. Access ``series`` for the
        data and ``report_type`` to determine structure.

    Raises:
        ConfigError: If API credentials not available.
        AuthenticationError: Invalid credentials.
        QueryError: Invalid bookmark_id or report not found.

    Example:
        ```python
        ws = mp.Workspace()

        # List bookmarks to find IDs
        bookmarks = ws.list_bookmarks(bookmark_type="retention")
        for bm in bookmarks:
            print(f"{bm.id}: {bm.name}")

        # Query a specific saved report
        result = ws.query_saved_report(bookmark_id=12345678)

        # Check report type and parse accordingly
        if result.report_type == "retention":
            for metric, cohorts in result.series.items():
                for date, data in cohorts.items():
                    print(f"{date}: {data['$overall']['first']} users")
        ```
    """
    return self._live_query_service.query_saved_report(bookmark_id=bookmark_id)
```

### 3.4 Migration Tasks

- Rename `insights()` → `query_saved_report()` in:
  - `MixpanelAPIClient`
  - `LiveQueryService`
  - `Workspace`
- Rename `InsightsResult` → `SavedReportResult` in `types.py`
- Update all existing tests referencing `insights()` or `InsightsResult`
- Update CLI command from `mp query insights` → `mp query saved-report`

---

## Phase 4: `query_flows()` Implementation

### 4.1 Test Specification

**File:** `tests/unit/test_api_client_bookmarks.py` (extend)

```python
class TestQueryFlows:
    """Tests for MixpanelAPIClient.query_flows()."""

    def test_query_flows_calls_arb_funnels_endpoint(self, test_credentials) -> None:
        """query_flows() should call /api/query/arb_funnels."""

    def test_query_flows_includes_query_type_param(self, test_credentials) -> None:
        """query_flows() should include query_type=flows_sankey or flows."""

    def test_query_flows_returns_steps_and_breakdowns(self, test_credentials) -> None:
        """query_flows() should return dict with steps, breakdowns, etc."""
```

**File:** `tests/unit/test_live_query_bookmarks.py`

```python
class TestLiveQueryFlows:
    """Tests for LiveQueryService.query_flows()."""

    def test_query_flows_returns_flows_result(self, live_query_factory) -> None:
        """query_flows() should return FlowsResult."""

    def test_query_flows_parses_steps(self, live_query_factory) -> None:
        """query_flows() should parse steps from API response."""

    def test_query_flows_parses_conversion_rate(self, live_query_factory) -> None:
        """query_flows() should parse overallConversionRate."""
```

**File:** `tests/unit/test_workspace_bookmarks.py` (extend)

```python
class TestWorkspaceQueryFlows:
    """Tests for Workspace.query_flows()."""

    def test_query_flows_delegation(self, workspace_factory) -> None:
        """query_flows() should delegate to LiveQueryService."""

    def test_query_flows_returns_flows_result(self, workspace_factory) -> None:
        """query_flows() should return FlowsResult."""
```

### 4.2 Implementation Specification

**File:** `src/mixpanel_data/_internal/api_client.py`

```python
def query_flows(self, bookmark_id: int) -> dict[str, Any]:
    """Query a saved Flows report.

    Args:
        bookmark_id: ID of saved Flows report.

    Returns:
        Raw API response with steps, breakdowns, conversionRate.

    Raises:
        AuthenticationError: Invalid credentials.
        QueryError: Invalid bookmark_id or not a flows bookmark.
    """
    url = self._build_url("query", "/arb_funnels")
    params = {
        "bookmark_id": bookmark_id,
        "query_type": "flows_sankey",
    }
    return self._request("GET", url, params=params)
```

**File:** `src/mixpanel_data/_internal/services/live_query.py`

```python
def query_flows(self, bookmark_id: int) -> FlowsResult:
    """Query a saved Flows report.

    Args:
        bookmark_id: ID of saved Flows report.

    Returns:
        FlowsResult with steps, breakdowns, and conversion rate.
    """
    raw = self._api_client.query_flows(bookmark_id=bookmark_id)
    return _transform_flows(raw, bookmark_id)


def _transform_flows(raw: dict[str, Any], bookmark_id: int) -> FlowsResult:
    """Transform raw API response to FlowsResult."""
    return FlowsResult(
        bookmark_id=bookmark_id,
        computed_at=raw.get("computed_at", ""),
        steps=raw.get("steps", []),
        breakdowns=raw.get("breakdowns", []),
        overall_conversion_rate=raw.get("overallConversionRate", 0.0),
        metadata=raw.get("metadata", {}),
    )
```

**File:** `src/mixpanel_data/workspace.py`

```python
def query_flows(self, bookmark_id: int) -> FlowsResult:
    """Query a saved Flows report.

    Flows reports show user navigation paths between events.
    Only works with bookmarks of type "flows".

    Args:
        bookmark_id: ID of saved Flows report (from ``list_bookmarks()``).

    Returns:
        FlowsResult with steps, breakdowns, and conversion metrics.

    Raises:
        ConfigError: If API credentials not available.
        AuthenticationError: Invalid credentials.
        QueryError: Invalid bookmark_id or not a flows bookmark.

    Example:
        ```python
        ws = mp.Workspace()

        # Find flows bookmarks
        flows = ws.list_bookmarks(bookmark_type="flows")
        for f in flows:
            print(f"{f.id}: {f.name}")

        # Query a flows report
        result = ws.query_flows(bookmark_id=12345)
        print(f"Conversion rate: {result.overall_conversion_rate:.1%}")
        for step in result.steps:
            print(step)
        ```
    """
    return self._live_query_service.query_flows(bookmark_id=bookmark_id)
```

---

## Phase 5: CLI Commands

### 5.1 Test Specification

**File:** `tests/integration/cli/test_inspect_commands.py` (extend)

```python
class TestInspectBookmarks:
    """Tests for 'mp inspect bookmarks' command."""

    def test_inspect_bookmarks_lists_all(self, cli_runner, mock_workspace) -> None:
        """'mp inspect bookmarks' should list all bookmarks."""

    def test_inspect_bookmarks_filter_by_type(self, cli_runner, mock_workspace) -> None:
        """'mp inspect bookmarks --type insights' should filter."""

    def test_inspect_bookmarks_json_format(self, cli_runner, mock_workspace) -> None:
        """'mp inspect bookmarks --format json' should output JSON."""

    def test_inspect_bookmarks_table_format(self, cli_runner, mock_workspace) -> None:
        """'mp inspect bookmarks --format table' should output table."""
```

**File:** `tests/integration/cli/test_query_commands.py` (update)

```python
class TestQuerySavedReport:
    """Tests for 'mp query saved-report' command (replaces 'mp query insights')."""

    def test_query_saved_report_by_id(self, cli_runner, mock_workspace) -> None:
        """'mp query saved-report 12345' should query bookmark."""

    def test_query_saved_report_json_format(self, cli_runner, mock_workspace) -> None:
        """'mp query saved-report 12345 --format json' should output JSON."""


class TestQueryFlows:
    """Tests for 'mp query flows' command."""

    def test_query_flows_by_id(self, cli_runner, mock_workspace) -> None:
        """'mp query flows 12345' should query flows bookmark."""

    def test_query_flows_json_format(self, cli_runner, mock_workspace) -> None:
        """'mp query flows 12345 --format json' should output JSON."""
```

### 5.2 Implementation Specification

**File:** `src/mixpanel_data/cli/commands/inspect.py`

```python
@inspect_app.command("bookmarks")
def inspect_bookmarks(
    bookmark_type: Annotated[
        str | None,
        typer.Option("--type", "-t", help="Filter by type (insights, funnels, retention, flows)"),
    ] = None,
    format: Annotated[str, typer.Option("--format", "-f")] = "table",
) -> None:
    """List saved reports (bookmarks) in the project.

    Shows all saved Insights, Funnel, Retention, and Flows reports.
    Use --type to filter by report type.

    Examples:
        mp inspect bookmarks
        mp inspect bookmarks --type insights
        mp inspect bookmarks --type retention --format json
    """
```

**File:** `src/mixpanel_data/cli/commands/query.py`

```python
# Rename existing insights command
@query_app.command("saved-report")
def query_saved_report(
    bookmark_id: Annotated[int, typer.Argument(help="Saved report bookmark ID")],
    format: Annotated[str, typer.Option("--format", "-f")] = "json",
) -> None:
    """Query a saved report by bookmark ID.

    Works with Insights, Retention, and Funnel bookmarks.
    Use 'mp inspect bookmarks' to find bookmark IDs.

    Examples:
        mp query saved-report 12345678
        mp query saved-report 12345678 --format table
    """


@query_app.command("flows")
def query_flows(
    bookmark_id: Annotated[int, typer.Argument(help="Flows bookmark ID")],
    format: Annotated[str, typer.Option("--format", "-f")] = "json",
) -> None:
    """Query a saved Flows report.

    Use 'mp inspect bookmarks --type flows' to find flows bookmark IDs.

    Examples:
        mp query flows 12345678
        mp query flows 12345678 --format json
    """
```

### 5.3 CLI Migration Tasks

- Remove `mp query insights` command
- Add `mp query saved-report` command
- Add `mp query flows` command
- Add `mp inspect bookmarks` command
- Update help text and examples

---

## Implementation Order (TDD)

### Sprint 1: Types (Foundation)

1. **Write tests** for `BookmarkInfo`, `BookmarkType`, `SavedReportResult`, `FlowsResult`
2. **Implement** types in `types.py`
3. **Remove** `InsightsResult` (replace with `SavedReportResult`)
4. **Run tests** - all should pass

### Sprint 2: API Client Layer

1. **Write tests** for `MixpanelAPIClient.list_bookmarks()`
2. **Implement** `list_bookmarks()` API method
3. **Rename** `insights()` → `query_saved_report()` in API client
4. **Write tests** for `MixpanelAPIClient.query_flows()`
5. **Implement** `query_flows()` API method
6. **Run tests** - all should pass

### Sprint 3: Service Layer

1. **Write tests** for `DiscoveryService.list_bookmarks()`
2. **Implement** discovery service method
3. **Rename** `insights()` → `query_saved_report()` in `LiveQueryService`
4. **Write tests** for `LiveQueryService.query_flows()`
5. **Implement** `query_flows()` service method
6. **Run tests** - all should pass

### Sprint 4: Workspace Facade

1. **Write tests** for `Workspace.list_bookmarks()`
2. **Implement** workspace `list_bookmarks()`
3. **Rename** `insights()` → `query_saved_report()` in `Workspace`
4. **Write tests** for `Workspace.query_flows()`
5. **Implement** workspace `query_flows()`
6. **Update all existing tests** that reference `insights()` or `InsightsResult`
7. **Run tests** - all should pass

### Sprint 5: CLI and Documentation

1. **Write tests** for CLI commands
2. **Implement** `mp inspect bookmarks` command
3. **Rename** `mp query insights` → `mp query saved-report`
4. **Implement** `mp query flows` command
5. **Update** user documentation
6. **Run full test suite**

---

## Test Commands

```bash
# Run specific test files
just test tests/unit/test_types_bookmarks.py
just test tests/unit/test_api_client_bookmarks.py
just test tests/unit/test_discovery_bookmarks.py
just test tests/unit/test_workspace_bookmarks.py

# Run all bookmark-related tests
just test -k bookmark

# Run all tests (should pass after migration)
just test

# Full check before committing
just check
```

---

## Files to Create/Modify

### New Files
- `tests/unit/test_types_bookmarks.py`
- `tests/unit/test_api_client_bookmarks.py`
- `tests/unit/test_discovery_bookmarks.py`
- `tests/unit/test_workspace_bookmarks.py`
- `tests/unit/test_live_query_bookmarks.py`

### Modified Files (Types & Exports)
- `src/mixpanel_data/types.py`
  - Remove `InsightsResult`
  - Add `BookmarkInfo`, `BookmarkType`, `SavedReportResult`, `SavedReportType`, `FlowsResult`
- `src/mixpanel_data/__init__.py` - Update exports

### Modified Files (API Layer)
- `src/mixpanel_data/_internal/api_client.py`
  - Add `list_bookmarks()`
  - Rename `insights()` → `query_saved_report()`
  - Add `query_flows()`

### Modified Files (Service Layer)
- `src/mixpanel_data/_internal/services/discovery.py`
  - Add `list_bookmarks()`
- `src/mixpanel_data/_internal/services/live_query.py`
  - Rename `insights()` → `query_saved_report()`
  - Rename `_transform_insights()` → `_transform_saved_report()`
  - Add `query_flows()`, `_transform_flows()`

### Modified Files (Workspace)
- `src/mixpanel_data/workspace.py`
  - Add `list_bookmarks()`
  - Rename `insights()` → `query_saved_report()`
  - Add `query_flows()`

### Modified Files (CLI)
- `src/mixpanel_data/cli/commands/inspect.py` - Add `bookmarks` command
- `src/mixpanel_data/cli/commands/query.py`
  - Rename `insights` → `saved-report`
  - Add `flows` command

### Modified Files (Tests - Migration)
- `tests/unit/test_api_client_phase008.py` - Update `insights` → `query_saved_report`
- `tests/unit/test_live_query_phase008.py` - Update `insights` → `query_saved_report`
- `tests/unit/test_workspace.py` - Update `insights` → `query_saved_report`
- `tests/integration/cli/test_query_commands.py` - Update `insights` → `saved-report`

### Documentation
- `docs/guide/live-analytics.md` - Document new features

---

## Success Criteria

1. All tests pass (`just check` succeeds)
2. `ws.list_bookmarks()` returns typed `list[BookmarkInfo]`
3. `ws.query_saved_report()` works for insights, retention, funnel bookmarks
4. `ws.query_flows()` works for flows bookmarks
5. `SavedReportResult.report_type` correctly identifies report type
6. CLI commands work:
   - `mp inspect bookmarks`
   - `mp query saved-report <id>`
   - `mp query flows <id>`
7. Documentation updated with examples

---

## References

- [Bookmarks API Research](../research/bookmarks-api-findings.md)
- [Original Bookmark ID Guide](bookmark_id_guide.md)
- [Live Analytics Documentation](../../docs/guide/live-analytics.md)
