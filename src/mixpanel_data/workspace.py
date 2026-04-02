"""Workspace facade for Mixpanel data operations.

The Workspace class is the unified entry point for all Mixpanel data operations,
orchestrating DiscoveryService, FetcherService, LiveQueryService, and StorageEngine.

Example:
    Basic usage with credentials from config:

    ```python
    ws = Workspace()
    ws.fetch_events(from_date="2024-01-01", to_date="2024-01-31")
    df = ws.sql("SELECT * FROM events LIMIT 10")
    ws.close()
    ```

    Ephemeral workspace for temporary analysis:

    ```python
    with Workspace.ephemeral() as ws:
        ws.fetch_events(from_date="2024-01-01", to_date="2024-01-31")
        total = ws.sql_scalar("SELECT COUNT(*) FROM events")
    # Database automatically deleted
    ```

    Query-only access to existing database:

    ```python
    ws = Workspace.open("path/to/database.db")
    df = ws.sql("SELECT * FROM events")
    ws.close()
    ```
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import duckdb
import pandas as pd

from mixpanel_data._internal.api_client import MixpanelAPIClient
from mixpanel_data._internal.config import ConfigManager, Credentials
from mixpanel_data._internal.services.discovery import DiscoveryService
from mixpanel_data._internal.services.fetcher import FetcherService
from mixpanel_data._internal.services.live_query import LiveQueryService
from mixpanel_data._internal.storage import StorageEngine
from mixpanel_data._internal.transforms import transform_event, transform_profile
from mixpanel_data._literal_types import TableType
from mixpanel_data.exceptions import ConfigError, MixpanelDataError, QueryError
from mixpanel_data.types import (
    ActivityFeedResult,
    AlertCount,
    AlertHistoryResponse,
    AlertScreenshotResponse,
    Annotation,
    AnnotationTag,
    BatchProgress,
    BlueprintConfig,
    BlueprintFinishParams,
    BlueprintTemplate,
    Bookmark,
    BookmarkHistoryResponse,
    BookmarkInfo,
    BookmarkType,
    BulkUpdateBookmarkEntry,
    BulkUpdateCohortEntry,
    BulkUpdateEventsParams,
    BulkUpdatePropertiesParams,
    Cohort,
    ColumnStatsResult,
    ColumnSummary,
    CreateAlertParams,
    CreateAnnotationParams,
    CreateAnnotationTagParams,
    CreateBookmarkParams,
    CreateCohortParams,
    CreateCustomPropertyParams,
    CreateDashboardParams,
    CreateDropFilterParams,
    CreateExperimentParams,
    CreateFeatureFlagParams,
    CreateRcaDashboardParams,
    CreateTagParams,
    CreateWebhookParams,
    CustomAlert,
    CustomProperty,
    DailyCountsResult,
    Dashboard,
    DropFilter,
    DropFilterLimitsResponse,
    DuplicateExperimentParams,
    EngagementDistributionResult,
    EntityType,
    EventBreakdownResult,
    EventCountsResult,
    EventDefinition,
    EventStats,
    Experiment,
    ExperimentConcludeParams,
    ExperimentDecideParams,
    FeatureFlag,
    FetchResult,
    FlagHistoryResponse,
    FlagLimitsResponse,
    FlowsResult,
    FrequencyResult,
    FunnelInfo,
    FunnelResult,
    JQLResult,
    LexiconSchema,
    LexiconTag,
    LookupTable,
    LookupTableUploadUrl,
    MarkLookupTableReadyParams,
    NumericAverageResult,
    NumericBucketResult,
    NumericPropertySummaryResult,
    NumericSumResult,
    ParallelFetchResult,
    ParallelProfileResult,
    ProfileProgress,
    ProjectWebhook,
    PropertyCountsResult,
    PropertyCoverageResult,
    PropertyDefinition,
    PropertyDistributionResult,
    PublicWorkspace,
    RetentionResult,
    SavedCohort,
    SavedReportResult,
    SegmentationResult,
    SetTestUsersParams,
    SQLResult,
    SummaryResult,
    TableInfo,
    TableSchema,
    TopEvent,
    UpdateAlertParams,
    UpdateAnnotationParams,
    UpdateBookmarkParams,
    UpdateCohortParams,
    UpdateCustomPropertyParams,
    UpdateDashboardParams,
    UpdateDropFilterParams,
    UpdateEventDefinitionParams,
    UpdateExperimentParams,
    UpdateFeatureFlagParams,
    UpdateLookupTableParams,
    UpdatePropertyDefinitionParams,
    UpdateReportLinkParams,
    UpdateTagParams,
    UpdateTextCardParams,
    UpdateWebhookParams,
    UploadLookupTableParams,
    ValidateAlertsForBookmarkParams,
    ValidateAlertsForBookmarkResponse,
    WebhookMutationResult,
    WebhookTestParams,
    WebhookTestResult,
    WorkspaceInfo,
)

# Batch size validation bounds
_MIN_BATCH_SIZE = 100
_MAX_BATCH_SIZE = 100_000

# Limit validation bounds (Mixpanel API restriction)
_MIN_LIMIT = 1
_MAX_LIMIT = 100_000


def _validate_batch_size(batch_size: int) -> None:
    """Validate batch_size is within the allowed range.

    Args:
        batch_size: Number of rows per commit.

    Raises:
        ValueError: If batch_size is outside the valid range.
    """
    if batch_size < _MIN_BATCH_SIZE:
        raise ValueError(
            f"batch_size must be at least {_MIN_BATCH_SIZE}, got {batch_size}"
        )
    if batch_size > _MAX_BATCH_SIZE:
        raise ValueError(
            f"batch_size must be at most {_MAX_BATCH_SIZE}, got {batch_size}"
        )


def _validate_limit(limit: int | None) -> None:
    """Validate limit is within the allowed range.

    Mixpanel API restricts the limit parameter to a maximum of 100000 events.
    This validation catches invalid values early to avoid wasting an API call.

    Args:
        limit: Maximum number of events to return, or None for no limit.

    Raises:
        ValueError: If limit is outside the valid range (1 to 100000).
    """
    if limit is None:
        return
    if limit < _MIN_LIMIT:
        raise ValueError(f"limit must be at least {_MIN_LIMIT}, got {limit}")
    if limit > _MAX_LIMIT:
        raise ValueError(f"limit must be at most {_MAX_LIMIT}, got {limit}")


class Workspace:
    """Unified entry point for Mixpanel data operations.

    The Workspace class is a facade that orchestrates all services:
    - DiscoveryService for schema exploration
    - FetcherService for data ingestion
    - LiveQueryService for real-time analytics
    - StorageEngine for local SQL queries

    Examples:
        Basic usage with credentials from config:

        ```python
        ws = Workspace()
        ws.fetch_events(from_date="2024-01-01", to_date="2024-01-31")
        df = ws.sql("SELECT * FROM events LIMIT 10")
        ```

        Ephemeral workspace for temporary analysis:

        ```python
        with Workspace.ephemeral() as ws:
            ws.fetch_events(from_date="2024-01-01", to_date="2024-01-31")
            total = ws.sql_scalar("SELECT COUNT(*) FROM events")
        # Database automatically deleted
        ```

        Query-only access to existing database:

        ```python
        ws = Workspace.open("path/to/database.db")
        df = ws.sql("SELECT * FROM events")
        ```
    """

    # =========================================================================
    # LIFECYCLE & CONSTRUCTION
    # =========================================================================

    def __init__(
        self,
        account: str | None = None,
        project_id: str | None = None,
        region: str | None = None,
        path: str | Path | None = None,
        read_only: bool = False,
        workspace_id: int | None = None,
        # Dependency injection for testing
        _config_manager: ConfigManager | None = None,
        _api_client: MixpanelAPIClient | None = None,
        _storage: StorageEngine | None = None,
    ) -> None:
        """Create a new Workspace with credentials and optional database path.

        Credentials are resolved in priority order:
        1. Environment variables (MP_USERNAME, MP_SECRET, MP_PROJECT_ID, MP_REGION)
        2. OAuth tokens from local storage (if available and not expired)
        3. Named account from config file (if account parameter specified)
        4. Default account from config file

        Args:
            account: Named account from config file to use.
            project_id: Override project ID from credentials.
            region: Override region from credentials (us, eu, in).
            path: Path to database file. If None, uses default location.
            read_only: If True, open database in read-only mode allowing
                concurrent reads. Defaults to False (write access).
            workspace_id: Optional workspace ID for scoped App API requests.
                If provided, the API client will use workspace-scoped paths.
            _config_manager: Injected ConfigManager for testing.
            _api_client: Injected MixpanelAPIClient for testing.
            _storage: Injected StorageEngine for testing.

        Raises:
            ConfigError: If no credentials can be resolved.
            AccountNotFoundError: If named account doesn't exist.
        """
        # Store injected or create default ConfigManager
        self._config_manager = _config_manager or ConfigManager()

        # Resolve credentials
        self._credentials: Credentials | None = None
        self._account_name: str | None = account

        # Resolve credentials (may raise ConfigError or AccountNotFoundError)
        self._credentials = self._config_manager.resolve_credentials(account)

        # Apply overrides if provided
        if project_id or region:
            from typing import cast

            from pydantic import SecretStr

            from mixpanel_data._internal.config import RegionType

            resolved_region = region or self._credentials.region
            self._credentials = Credentials(
                username=self._credentials.username,
                secret=SecretStr(self._credentials.secret.get_secret_value()),
                project_id=project_id or self._credentials.project_id,
                region=cast(RegionType, resolved_region),
            )

        # Initialize storage lazily
        # Store path for lazy initialization, or use injected storage directly
        self._db_path: Path | None = None
        self._storage: StorageEngine | None = None
        self._read_only = read_only

        if _storage is not None:
            # Injected storage - use directly
            self._storage = _storage
        else:
            # Determine database path for lazy initialization
            if path is not None:
                self._db_path = Path(path) if isinstance(path, str) else path
            else:
                # Default path: ~/.mp/data/{project_id}.db
                self._db_path = (
                    Path.home() / ".mp" / "data" / f"{self._credentials.project_id}.db"
                )
            # NOTE: StorageEngine is NOT created here - see storage property

        # Lazy-initialized services (None until first use)
        self._api_client: MixpanelAPIClient | None = _api_client
        self._discovery: DiscoveryService | None = None
        self._fetcher: FetcherService | None = None
        self._live_query: LiveQueryService | None = None

        # Set workspace_id on the api_client if provided
        self._initial_workspace_id = workspace_id
        if workspace_id is not None and self._api_client is not None:
            self._api_client.set_workspace_id(workspace_id)

    @classmethod
    @contextmanager
    def ephemeral(
        cls,
        account: str | None = None,
        project_id: str | None = None,
        region: str | None = None,
        _config_manager: ConfigManager | None = None,
        _api_client: MixpanelAPIClient | None = None,
    ) -> Iterator[Workspace]:
        """Create a temporary workspace that auto-deletes on exit.

        Args:
            account: Named account from config file to use.
            project_id: Override project ID from credentials.
            region: Override region from credentials.
            _config_manager: Injected ConfigManager for testing.
            _api_client: Injected MixpanelAPIClient for testing.

        Yields:
            Workspace: A workspace with temporary database.

        Example:
            ```python
            with Workspace.ephemeral() as ws:
                ws.fetch_events(from_date="2024-01-01", to_date="2024-01-31")
                print(ws.sql_scalar("SELECT COUNT(*) FROM events"))
            # Database file automatically deleted
            ```
        """
        storage = StorageEngine.ephemeral()
        ws = cls(
            account=account,
            project_id=project_id,
            region=region,
            _config_manager=_config_manager,
            _api_client=_api_client,
            _storage=storage,
        )
        try:
            yield ws
        finally:
            ws.close()

    @classmethod
    @contextmanager
    def memory(
        cls,
        account: str | None = None,
        project_id: str | None = None,
        region: str | None = None,
        _config_manager: ConfigManager | None = None,
        _api_client: MixpanelAPIClient | None = None,
    ) -> Iterator[Workspace]:
        """Create a workspace with true in-memory database.

        The database exists only in RAM with zero disk footprint.
        All data is lost when the context manager exits.

        Best for:
        - Small datasets where zero disk footprint is required
        - Unit tests without filesystem side effects
        - Quick exploratory queries

        For large datasets, prefer ephemeral() which benefits from
        DuckDB's compression (can be 8x faster for large workloads).

        Args:
            account: Named account from config file to use.
            project_id: Override project ID from credentials.
            region: Override region from credentials.
            _config_manager: Injected ConfigManager for testing.
            _api_client: Injected MixpanelAPIClient for testing.

        Yields:
            Workspace: A workspace with in-memory database.

        Example:
            ```python
            with Workspace.memory() as ws:
                ws.fetch_events(from_date="2024-01-01", to_date="2024-01-01")
                total = ws.sql_scalar("SELECT COUNT(*) FROM events")
            # Database gone - no cleanup needed, no files left behind
            ```
        """
        storage = StorageEngine.memory()
        ws = cls(
            account=account,
            project_id=project_id,
            region=region,
            _config_manager=_config_manager,
            _api_client=_api_client,
            _storage=storage,
        )
        try:
            yield ws
        finally:
            ws.close()

    @classmethod
    def open(cls, path: str | Path, *, read_only: bool = True) -> Workspace:
        """Open an existing database for query-only access.

        This method opens a database without requiring API credentials.
        Discovery, fetching, and live query methods will be unavailable.

        Args:
            path: Path to existing database file.
            read_only: If True (default), open in read-only mode allowing
                concurrent reads. Set to False for write access.

        Returns:
            Workspace: A workspace with access to stored data.

        Raises:
            FileNotFoundError: If database file doesn't exist.

        Example:
            ```python
            ws = Workspace.open("my_data.db")
            df = ws.sql("SELECT * FROM events")
            ws.close()
            ```
        """
        db_path = Path(path) if isinstance(path, str) else path
        storage = StorageEngine.open_existing(db_path, read_only=read_only)

        # Create instance without credential resolution
        instance = object.__new__(cls)
        instance._config_manager = ConfigManager()
        instance._credentials = None
        instance._account_name = None
        instance._db_path = db_path
        instance._storage = storage
        instance._read_only = read_only
        instance._api_client = None
        instance._discovery = None
        instance._fetcher = None
        instance._live_query = None

        return instance

    def __enter__(self) -> Workspace:
        """Enter context manager.

        Returns:
            Self for use in 'with' statement.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit context manager, closing all resources.

        Closes the database connection and HTTP client. Exceptions are
        NOT suppressed - they propagate normally after cleanup.
        """
        self.close()

    def close(self) -> None:
        """Close all resources (database connection, HTTP client).

        This method is idempotent and safe to call multiple times.
        """
        # Close storage
        if self._storage is not None:
            self._storage.close()

        # Close API client if we created one
        if self._api_client is not None:
            self._api_client.close()
            self._api_client = None

    @staticmethod
    def test_credentials(account: str | None = None) -> dict[str, Any]:
        """Test account credentials by making a lightweight API call.

        This method verifies that credentials are valid and can access the
        Mixpanel API. It's useful for validating configuration before
        attempting more expensive operations.

        Args:
            account: Named account to test. If None, tests the default account
                or credentials from environment variables.

        Returns:
            Dict containing:
                - success: bool - Whether the test succeeded
                - account: str | None - Account name tested
                - project_id: str - Project ID from credentials
                - region: str - Region from credentials
                - events_found: int - Number of events found (validation metric)

        Raises:
            AccountNotFoundError: If named account doesn't exist.
            AuthenticationError: If credentials are invalid.
            ConfigError: If no credentials can be resolved.

        Example:
            ```python
            # Test default account
            result = Workspace.test_credentials()
            if result["success"]:
                print(f"Authenticated to project {result['project_id']}")

            # Test specific account
            result = Workspace.test_credentials("production")
            ```
        """
        config_manager = ConfigManager()
        credentials = config_manager.resolve_credentials(account)

        # Get account info if we used a named account
        account_info = None
        if account is not None:
            account_info = config_manager.get_account(account)
        else:
            # Check if credentials came from a default account
            accounts = config_manager.list_accounts()
            for acc in accounts:
                if acc.is_default:
                    account_info = acc
                    break

        # Create API client and test with a lightweight call
        api_client = MixpanelAPIClient(credentials)
        try:
            events = api_client.get_events()
            event_count = len(list(events)) if events else 0

            return {
                "success": True,
                "account": account_info.name if account_info else None,
                "project_id": credentials.project_id,
                "region": credentials.region,
                "events_found": event_count,
            }
        finally:
            api_client.close()

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _get_api_client(self) -> MixpanelAPIClient:
        """Get or create the API client (lazy initialization).

        Returns:
            MixpanelAPIClient instance.
        """
        if self._api_client is None:
            if self._credentials is None:
                raise ConfigError(
                    "API access requires credentials. "
                    "Use Workspace() with credentials instead of Workspace.open()."
                )
            self._api_client = MixpanelAPIClient(self._credentials)
            if self._initial_workspace_id is not None:
                self._api_client.set_workspace_id(self._initial_workspace_id)
        return self._api_client

    def _require_api_client(self) -> MixpanelAPIClient:
        """Get API client or raise if unavailable.

        Returns:
            MixpanelAPIClient instance.

        Raises:
            ConfigError: If credentials are not available.
        """
        if self._credentials is None:
            raise ConfigError(
                "API access requires credentials. "
                "Use Workspace() with credentials instead of Workspace.open()."
            )
        return self._get_api_client()

    # =========================================================================
    # WORKSPACE MANAGEMENT
    # =========================================================================

    @property
    def workspace_id(self) -> int | None:
        """Return the currently set workspace ID, or None if not set.

        This returns the explicit workspace ID set via ``set_workspace_id()``
        or the constructor's ``workspace_id`` parameter. It does NOT
        auto-discover a workspace ID (use ``resolve_workspace_id()`` for that).

        Returns:
            The workspace ID if explicitly set, ``None`` otherwise.

        Example:
            ```python
            ws = Workspace(workspace_id=42)
            assert ws.workspace_id == 42

            ws2 = Workspace()
            assert ws2.workspace_id is None
            ```
        """
        client = self._get_api_client()
        return client.workspace_id

    def set_workspace_id(self, workspace_id: int | None) -> None:
        """Set or clear the workspace ID for scoped App API requests.

        When set, App API requests that use ``maybe_scoped_path()`` or
        ``require_scoped_path()`` will target the specified workspace.
        Setting to ``None`` clears the workspace scope.

        Args:
            workspace_id: Workspace ID to use, or ``None`` to clear.

        Example:
            ```python
            ws = Workspace()
            ws.set_workspace_id(789)
            assert ws.workspace_id == 789

            ws.set_workspace_id(None)
            assert ws.workspace_id is None
            ```
        """
        self._initial_workspace_id = workspace_id
        client = self._get_api_client()
        client.set_workspace_id(workspace_id)

    def list_workspaces(self) -> list[PublicWorkspace]:
        """List all public workspaces for the current project.

        Delegates to the API client's ``list_workspaces()`` method, which
        calls ``GET /api/app/projects/{pid}/workspaces/public``.

        Returns:
            List of ``PublicWorkspace`` models for the project.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            workspaces = ws.list_workspaces()
            for w in workspaces:
                print(f"{w.name} (id={w.id}, default={w.is_default})")
            ```
        """
        client = self._require_api_client()
        return client.list_workspaces()

    def resolve_workspace_id(self) -> int:
        """Resolve the workspace ID for scoped requests.

        Resolution order:
        1. Explicit workspace ID (set via ``set_workspace_id()``)
        2. Cached auto-discovered workspace ID
        3. Auto-discover by listing workspaces and finding the default

        Returns:
            The resolved workspace ID.

        Raises:
            ConfigError: If credentials are not available.
            WorkspaceScopeError: If no workspaces are found for the project.

        Example:
            ```python
            ws = Workspace()
            ws_id = ws.resolve_workspace_id()
            print(f"Using workspace {ws_id}")
            ```
        """
        client = self._require_api_client()
        return client.resolve_workspace_id()

    @staticmethod
    def _try_float(value: Any) -> float | None:
        """Attempt to convert a value to float, returning None if not possible.

        Used for handling DuckDB SUMMARIZE output where avg/std may be
        non-numeric for certain column types (e.g., timestamps).

        Args:
            value: Value to convert.

        Returns:
            Float value if conversion succeeds, None otherwise.
        """
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @property
    def _discovery_service(self) -> DiscoveryService:
        """Get or create discovery service (lazy initialization)."""
        if self._discovery is None:
            self._discovery = DiscoveryService(self._require_api_client())
        return self._discovery

    @property
    def storage(self) -> StorageEngine:
        """Get or create storage engine (lazy initialization).

        Only connects to database when first accessed. API-only operations
        (discovery, live queries, streaming) don't touch the database.

        Returns:
            StorageEngine instance.

        Raises:
            DatabaseLockedError: If database is locked by another process.
            OSError: If the database file cannot be created or opened due to
                filesystem permission issues or other I/O errors.
            RuntimeError: If no database path configured (shouldn't happen
                in normal use).
        """
        if self._storage is None:
            if self._db_path is None:
                raise RuntimeError("No database path configured")
            self._storage = StorageEngine(path=self._db_path, read_only=self._read_only)
        return self._storage

    @property
    def _fetcher_service(self) -> FetcherService:
        """Get or create fetcher service (lazy initialization)."""
        if self._fetcher is None:
            self._fetcher = FetcherService(
                self._require_api_client(),
                self.storage,  # Uses lazy storage property
            )
        return self._fetcher

    @property
    def _live_query_service(self) -> LiveQueryService:
        """Get or create live query service (lazy initialization)."""
        if self._live_query is None:
            self._live_query = LiveQueryService(self._require_api_client())
        return self._live_query

    # =========================================================================
    # DISCOVERY METHODS
    # =========================================================================

    def events(self) -> list[str]:
        """List all event names in the Mixpanel project.

        Results are cached for the lifetime of the Workspace.

        Returns:
            Alphabetically sorted list of event names.

        Raises:
            ConfigError: If API credentials not available.
            AuthenticationError: If credentials are invalid.
        """
        return self._discovery_service.list_events()

    def properties(self, event: str) -> list[str]:
        """List all property names for an event.

        Results are cached per event for the lifetime of the Workspace.

        Args:
            event: Event name to get properties for.

        Returns:
            Alphabetically sorted list of property names.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._discovery_service.list_properties(event)

    def property_values(
        self,
        property_name: str,
        *,
        event: str | None = None,
        limit: int = 100,
    ) -> list[str]:
        """Get sample values for a property.

        Results are cached per (property, event, limit) for the lifetime of the Workspace.

        Args:
            property_name: Property to get values for.
            event: Optional event to filter by.
            limit: Maximum number of values to return.

        Returns:
            List of sample property values as strings.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._discovery_service.list_property_values(
            property_name, event=event, limit=limit
        )

    def funnels(self) -> list[FunnelInfo]:
        """List saved funnels in the Mixpanel project.

        Results are cached for the lifetime of the Workspace.

        Returns:
            List of FunnelInfo objects (funnel_id, name).

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._discovery_service.list_funnels()

    def cohorts(self) -> list[SavedCohort]:
        """List saved cohorts in the Mixpanel project.

        Results are cached for the lifetime of the Workspace.

        Returns:
            List of SavedCohort objects.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._discovery_service.list_cohorts()

    def list_bookmarks(
        self,
        bookmark_type: BookmarkType | None = None,
    ) -> list[BookmarkInfo]:
        """List all saved reports (bookmarks) in the project.

        Retrieves metadata for all saved Insights, Funnel, Retention, and
        Flows reports in the project.

        Args:
            bookmark_type: Optional filter by report type. Valid values are
                'insights', 'funnels', 'retention', 'flows', 'launch-analysis'.
                If None, returns all bookmark types.

        Returns:
            List of BookmarkInfo objects with report metadata.
            Empty list if no bookmarks exist.

        Raises:
            ConfigError: If API credentials not available.
            QueryError: Permission denied or invalid type parameter.
        """
        return self._discovery_service.list_bookmarks(bookmark_type=bookmark_type)

    def top_events(
        self,
        *,
        type: Literal["general", "average", "unique"] = "general",
        limit: int | None = None,
    ) -> list[TopEvent]:
        """Get today's most active events.

        This method is NOT cached (returns real-time data).

        Args:
            type: Counting method (general, average, unique).
            limit: Maximum number of events to return.

        Returns:
            List of TopEvent objects (event, count, percent_change).

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._discovery_service.list_top_events(type=type, limit=limit)

    def clear_discovery_cache(self) -> None:
        """Clear cached discovery results.

        Subsequent discovery calls will fetch fresh data from the API.
        """
        if self._discovery is not None:
            self._discovery.clear_cache()

    # =========================================================================
    # LEXICON SCHEMA METHODS
    # =========================================================================

    def lexicon_schemas(
        self,
        *,
        entity_type: EntityType | None = None,
    ) -> list[LexiconSchema]:
        """List Lexicon schemas in the project.

        Retrieves documented event and profile property schemas from the
        Mixpanel Lexicon (data dictionary).

        Results are cached for the lifetime of the Workspace.

        Args:
            entity_type: Optional filter by type ("event" or "profile").
                If None, returns all schemas.

        Returns:
            Alphabetically sorted list of LexiconSchema objects.

        Raises:
            ConfigError: If API credentials not available.
            AuthenticationError: If credentials are invalid.

        Note:
            The Lexicon API has a strict 5 requests/minute rate limit.
            Caching helps avoid hitting this limit; call clear_discovery_cache()
            only when fresh data is needed.
        """
        return self._discovery_service.list_schemas(entity_type=entity_type)

    def lexicon_schema(
        self,
        entity_type: EntityType,
        name: str,
    ) -> LexiconSchema:
        """Get a single Lexicon schema by entity type and name.

        Retrieves a documented schema for a specific event or profile property
        from the Mixpanel Lexicon (data dictionary).

        Results are cached for the lifetime of the Workspace.

        Args:
            entity_type: Entity type ("event" or "profile").
            name: Entity name.

        Returns:
            LexiconSchema for the specified entity.

        Raises:
            ConfigError: If API credentials not available.
            AuthenticationError: If credentials are invalid.
            QueryError: If schema not found.

        Note:
            The Lexicon API has a strict 5 requests/minute rate limit.
            Caching helps avoid hitting this limit; call clear_discovery_cache()
            only when fresh data is needed.
        """
        return self._discovery_service.get_schema(entity_type, name)

    # =========================================================================
    # FETCHING METHODS
    # =========================================================================

    def fetch_events(
        self,
        name: str = "events",
        *,
        from_date: str,
        to_date: str,
        events: list[str] | None = None,
        where: str | None = None,
        limit: int | None = None,
        progress: bool = True,
        append: bool = False,
        batch_size: int = 1000,
        parallel: bool = False,
        max_workers: int | None = None,
        on_batch_complete: Callable[[BatchProgress], None] | None = None,
        chunk_days: int = 7,
    ) -> FetchResult | ParallelFetchResult:
        """Fetch events from Mixpanel and store in local database.

        Note:
            This is a potentially long-running operation that streams data from
            Mixpanel's Export API. For large date ranges, use ``parallel=True``
            for significantly faster exports (up to 10x speedup).

        Args:
            name: Table name to create or append to (default: "events").
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            events: Optional list of event names to filter.
            where: Optional WHERE clause for filtering.
            limit: Optional maximum number of events to return (max 100000).
            progress: Show progress bar (default: True).
            append: If True, append to existing table. If False (default), create new.
            batch_size: Number of rows per INSERT/COMMIT cycle. Controls the
                memory/IO tradeoff: smaller values use less memory but more
                disk IO; larger values use more memory but less IO.
                Default: 1000. Valid range: 100-100000.
            parallel: If True, use parallel fetching with multiple threads.
                Splits date range into 7-day chunks and fetches concurrently.
                Enables export of date ranges exceeding 100 days. Default: False.
            max_workers: Maximum concurrent fetch threads when parallel=True.
                Default: 10. Higher values may hit Mixpanel rate limits.
                Ignored when parallel=False.
            on_batch_complete: Callback invoked when each batch completes
                during parallel fetch. Receives BatchProgress with status.
                Useful for custom progress reporting. Ignored when parallel=False.
            chunk_days: Days per chunk for parallel date range splitting.
                Default: 7. Valid range: 1-100. Smaller values create more
                parallel batches but may increase API overhead.
                Ignored when parallel=False.

        Returns:
            FetchResult when parallel=False, ParallelFetchResult when parallel=True.
            ParallelFetchResult includes per-batch statistics and any failure info.

        Raises:
            TableExistsError: If table exists and append=False.
            TableNotFoundError: If table doesn't exist and append=True.
            ConfigError: If API credentials not available.
            AuthenticationError: If credentials are invalid.
            ValueError: If batch_size is outside valid range (100-100000).
            ValueError: If limit is outside valid range (1-100000).
            ValueError: If max_workers is not positive.
            ValueError: If chunk_days is not in range 1-100.

        Example:
            ```python
            # Sequential fetch (default)
            result = ws.fetch_events(
                name="events",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

            # Parallel fetch for large date ranges
            result = ws.fetch_events(
                name="events_q4",
                from_date="2024-10-01",
                to_date="2024-12-31",
                parallel=True,
            )

            # With custom progress callback
            def on_batch(progress: BatchProgress) -> None:
                print(f"Batch {progress.batch_index + 1}/{progress.total_batches}")

            result = ws.fetch_events(
                name="events",
                from_date="2024-01-01",
                to_date="2024-03-31",
                parallel=True,
                on_batch_complete=on_batch,
            )
            ```
        """
        # Validate parameters early to avoid wasted API calls
        _validate_batch_size(batch_size)
        _validate_limit(limit)

        # Validate max_workers for parallel mode
        if max_workers is not None and max_workers <= 0:
            raise ValueError("max_workers must be positive")

        # Validate chunk_days for parallel mode
        if chunk_days <= 0:
            raise ValueError("chunk_days must be positive")
        if chunk_days > 100:
            raise ValueError("chunk_days must be at most 100")

        # Create progress callback if requested (only for interactive terminals)
        progress_callback = None
        pbar = None
        if progress and sys.stderr.isatty() and not parallel:
            try:
                from rich.progress import Progress, SpinnerColumn, TextColumn

                pbar = Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    TextColumn("{task.completed} rows"),
                )
                task = pbar.add_task("Fetching events...", total=None)
                pbar.start()

                def callback(count: int) -> None:
                    pbar.update(task, completed=count)

                progress_callback = callback
            except Exception:
                # Progress bar unavailable or failed to initialize, skip silently
                pass

        try:
            result = self._fetcher_service.fetch_events(
                name=name,
                from_date=from_date,
                to_date=to_date,
                events=events,
                where=where,
                limit=limit,
                progress_callback=progress_callback,
                append=append,
                batch_size=batch_size,
                parallel=parallel,
                max_workers=max_workers,
                on_batch_complete=on_batch_complete,
                chunk_days=chunk_days,
            )
        finally:
            if pbar is not None:
                pbar.stop()

        return result

    def fetch_profiles(
        self,
        name: str = "profiles",
        *,
        where: str | None = None,
        cohort_id: str | None = None,
        output_properties: list[str] | None = None,
        progress: bool = True,
        append: bool = False,
        batch_size: int = 1000,
        distinct_id: str | None = None,
        distinct_ids: list[str] | None = None,
        group_id: str | None = None,
        behaviors: list[dict[str, Any]] | None = None,
        as_of_timestamp: int | None = None,
        include_all_users: bool = False,
        parallel: bool = False,
        max_workers: int | None = None,
        on_page_complete: Callable[[ProfileProgress], None] | None = None,
    ) -> FetchResult | ParallelProfileResult:
        """Fetch user profiles from Mixpanel and store in local database.

        Note:
            This is a potentially long-running operation that streams data from
            Mixpanel's Engage API. For large profile sets, use ``parallel=True``
            for up to 5x faster exports.

        Args:
            name: Table name to create or append to (default: "profiles").
            where: Optional WHERE clause for filtering.
            cohort_id: Optional cohort ID to filter by. Only profiles that are
                members of this cohort will be returned.
            output_properties: Optional list of property names to include in
                the response. If None, all properties are returned.
            progress: Show progress bar (default: True).
            append: If True, append to existing table. If False (default), create new.
            batch_size: Number of rows per INSERT/COMMIT cycle. Controls the
                memory/IO tradeoff: smaller values use less memory but more
                disk IO; larger values use more memory but less IO.
                Default: 1000. Valid range: 100-100000.
            distinct_id: Optional single user ID to fetch. Mutually exclusive
                with distinct_ids.
            distinct_ids: Optional list of user IDs to fetch. Mutually exclusive
                with distinct_id. Duplicates are automatically removed.
            group_id: Optional group type identifier (e.g., "companies") to fetch
                group profiles instead of user profiles.
            behaviors: Optional list of behavioral filters. Each dict should have
                'window' (e.g., "30d"), 'name' (identifier), and 'event_selectors'
                (list of {"event": "Name"}). Use with `where` parameter to filter,
                e.g., where='(behaviors["name"] > 0)'. Mutually exclusive with
                cohort_id.
            as_of_timestamp: Optional Unix timestamp to query profile state at
                a specific point in time. Must be in the past.
            include_all_users: If True, include all users and mark cohort membership.
                Only valid when cohort_id is provided.
            parallel: If True, use parallel fetching with multiple threads.
                Uses page-based parallelism for concurrent profile fetching.
                Enables up to 5x faster exports. Default: False.
            max_workers: Maximum concurrent fetch threads when parallel=True.
                Default: 5, capped at 5. Ignored when parallel=False.
            on_page_complete: Callback invoked when each page completes during
                parallel fetch. Receives ProfileProgress with status.
                Useful for custom progress reporting. Ignored when parallel=False.

        Returns:
            FetchResult when parallel=False, ParallelProfileResult when parallel=True.
            ParallelProfileResult includes per-page statistics and any failure info.

        Raises:
            TableExistsError: If table exists and append=False.
            TableNotFoundError: If table doesn't exist and append=True.
            ConfigError: If API credentials not available.
            ValueError: If batch_size is outside valid range (100-100000) or
                mutually exclusive parameters are provided.
        """
        # Validate batch_size
        _validate_batch_size(batch_size)

        # Validate max_workers for parallel mode
        if max_workers is not None and max_workers <= 0:
            raise ValueError("max_workers must be positive")

        # Create progress callback if requested (only for interactive terminals)
        # Sequential mode uses spinner progress bar
        progress_callback = None
        pbar = None
        if progress and sys.stderr.isatty() and not parallel:
            try:
                from rich.progress import Progress, SpinnerColumn, TextColumn

                pbar = Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    TextColumn("{task.completed} rows"),
                )
                task = pbar.add_task("Fetching profiles...", total=None)
                pbar.start()

                def callback(count: int) -> None:
                    pbar.update(task, completed=count)

                progress_callback = callback
            except Exception:
                # Progress bar unavailable or failed to initialize, skip silently
                pass

        try:
            result = self._fetcher_service.fetch_profiles(
                name=name,
                where=where,
                cohort_id=cohort_id,
                output_properties=output_properties,
                progress_callback=progress_callback,
                append=append,
                batch_size=batch_size,
                distinct_id=distinct_id,
                distinct_ids=distinct_ids,
                group_id=group_id,
                behaviors=behaviors,
                as_of_timestamp=as_of_timestamp,
                include_all_users=include_all_users,
                parallel=parallel,
                max_workers=max_workers,
                on_page_complete=on_page_complete,
            )
        finally:
            if pbar is not None:
                pbar.stop()

        return result

    # =========================================================================
    # STREAMING METHODS
    # =========================================================================

    def stream_events(
        self,
        *,
        from_date: str,
        to_date: str,
        events: list[str] | None = None,
        where: str | None = None,
        limit: int | None = None,
        raw: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """Stream events directly from Mixpanel API without storing.

        Yields events one at a time as they are received from the API.
        No database files or tables are created.

        Args:
            from_date: Start date inclusive (YYYY-MM-DD format).
            to_date: End date inclusive (YYYY-MM-DD format).
            events: Optional list of event names to filter. If None, all events returned.
            where: Optional Mixpanel filter expression (e.g., 'properties["country"]=="US"').
            limit: Optional maximum number of events to return (max 100000).
            raw: If True, return events in raw Mixpanel API format.
                 If False (default), return normalized format with datetime objects.

        Yields:
            dict[str, Any]: Event dictionaries in normalized or raw format.

        Raises:
            ConfigError: If API credentials are not available.
            AuthenticationError: If credentials are invalid.
            RateLimitError: If rate limit exceeded after max retries.
            QueryError: If filter expression is invalid.
            ValueError: If limit is outside valid range (1-100000).

        Example:
            ```python
            ws = Workspace()
            for event in ws.stream_events(from_date="2024-01-01", to_date="2024-01-31"):
                process(event)
            ws.close()
            ```

            With raw format:

            ```python
            for event in ws.stream_events(
                from_date="2024-01-01", to_date="2024-01-31", raw=True
            ):
                legacy_system.ingest(event)
            ```
        """
        # Validate limit early to avoid wasted API calls
        _validate_limit(limit)

        api_client = self._require_api_client()
        event_iterator = api_client.export_events(
            from_date=from_date,
            to_date=to_date,
            events=events,
            where=where,
            limit=limit,
        )

        if raw:
            yield from event_iterator
        else:
            for event in event_iterator:
                yield transform_event(event)

    def stream_profiles(
        self,
        *,
        where: str | None = None,
        cohort_id: str | None = None,
        output_properties: list[str] | None = None,
        raw: bool = False,
        distinct_id: str | None = None,
        distinct_ids: list[str] | None = None,
        group_id: str | None = None,
        behaviors: list[dict[str, Any]] | None = None,
        as_of_timestamp: int | None = None,
        include_all_users: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """Stream user profiles directly from Mixpanel API without storing.

        Yields profiles one at a time as they are received from the API.
        No database files or tables are created.

        Args:
            where: Optional Mixpanel filter expression for profile properties.
            cohort_id: Optional cohort ID to filter by. Only profiles that are
                members of this cohort will be returned.
            output_properties: Optional list of property names to include in
                the response. If None, all properties are returned.
            raw: If True, return profiles in raw Mixpanel API format.
                 If False (default), return normalized format.
            distinct_id: Optional single user ID to fetch. Mutually exclusive
                with distinct_ids.
            distinct_ids: Optional list of user IDs to fetch. Mutually exclusive
                with distinct_id. Duplicates are automatically removed.
            group_id: Optional group type identifier (e.g., "companies") to fetch
                group profiles instead of user profiles.
            behaviors: Optional list of behavioral filters. Each dict should have
                'window' (e.g., "30d"), 'name' (identifier), and 'event_selectors'
                (list of {"event": "Name"}). Use with `where` parameter to filter,
                e.g., where='(behaviors["name"] > 0)'. Mutually exclusive with
                cohort_id.
            as_of_timestamp: Optional Unix timestamp to query profile state at
                a specific point in time. Must be in the past.
            include_all_users: If True, include all users and mark cohort membership.
                Only valid when cohort_id is provided.

        Yields:
            dict[str, Any]: Profile dictionaries in normalized or raw format.

        Raises:
            ConfigError: If API credentials are not available.
            AuthenticationError: If credentials are invalid.
            RateLimitError: If rate limit exceeded after max retries.
            ValueError: If mutually exclusive parameters are provided.

        Example:
            ```python
            ws = Workspace()
            for profile in ws.stream_profiles():
                sync_to_crm(profile)
            ws.close()
            ```

            Filter to premium users:

            ```python
            for profile in ws.stream_profiles(where='properties["plan"]=="premium"'):
                send_survey(profile)
            ```

            Filter by cohort and select specific properties:

            ```python
            for profile in ws.stream_profiles(
                cohort_id="12345",
                output_properties=["$email", "$name"]
            ):
                send_email(profile)
            ```

            Fetch specific users by ID:

            ```python
            for profile in ws.stream_profiles(distinct_ids=["user_1", "user_2"]):
                print(profile)
            ```

            Fetch group profiles:

            ```python
            for company in ws.stream_profiles(group_id="companies"):
                print(company)
            ```
        """
        api_client = self._require_api_client()
        profile_iterator = api_client.export_profiles(
            where=where,
            cohort_id=cohort_id,
            output_properties=output_properties,
            distinct_id=distinct_id,
            distinct_ids=distinct_ids,
            group_id=group_id,
            behaviors=behaviors,
            as_of_timestamp=as_of_timestamp,
            include_all_users=include_all_users,
        )

        if raw:
            yield from profile_iterator
        else:
            for profile in profile_iterator:
                yield transform_profile(profile)

    # =========================================================================
    # LOCAL QUERY METHODS
    # =========================================================================

    def sql(self, query: str) -> pd.DataFrame:
        """Execute SQL query and return results as DataFrame.

        Args:
            query: SQL query string.

        Returns:
            pandas DataFrame with query results.

        Raises:
            QueryError: If query is invalid.
        """
        return self.storage.execute_df(query)

    def sql_scalar(self, query: str) -> Any:
        """Execute SQL query and return single scalar value.

        Args:
            query: SQL query that returns a single value.

        Returns:
            The scalar result (int, float, str, etc.).

        Raises:
            QueryError: If query is invalid or returns multiple values.
        """
        return self.storage.execute_scalar(query)

    def sql_rows(self, query: str) -> SQLResult:
        """Execute SQL query and return structured result with column metadata.

        Args:
            query: SQL query string.

        Returns:
            SQLResult with column names and row tuples.

        Raises:
            QueryError: If query is invalid.

        Example:
            ```python
            result = ws.sql_rows("SELECT name, age FROM users")
            print(result.columns)  # ['name', 'age']
            for row in result.rows:
                print(row)  # ('Alice', 30)

            # Or convert to dicts for JSON output:
            for row in result.to_dicts():
                print(row)  # {'name': 'Alice', 'age': 30}
            ```
        """
        return self.storage.execute_rows(query)

    # =========================================================================
    # LIVE QUERY METHODS
    # =========================================================================

    def segmentation(
        self,
        event: str,
        *,
        from_date: str,
        to_date: str,
        on: str | None = None,
        unit: Literal["day", "week", "month"] = "day",
        where: str | None = None,
    ) -> SegmentationResult:
        """Run a segmentation query against Mixpanel API.

        Args:
            event: Event name to query.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            on: Optional property to segment by.
            unit: Time unit for aggregation.
            where: Optional WHERE clause.

        Returns:
            SegmentationResult with time-series data.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._live_query_service.segmentation(
            event=event,
            from_date=from_date,
            to_date=to_date,
            on=on,
            unit=unit,
            where=where,
        )

    def funnel(
        self,
        funnel_id: int,
        *,
        from_date: str,
        to_date: str,
        unit: str | None = None,
        on: str | None = None,
    ) -> FunnelResult:
        """Run a funnel analysis query.

        Args:
            funnel_id: ID of saved funnel.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            unit: Optional time unit.
            on: Optional property to segment by.

        Returns:
            FunnelResult with step conversion rates.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._live_query_service.funnel(
            funnel_id=funnel_id,
            from_date=from_date,
            to_date=to_date,
            unit=unit,
            on=on,
        )

    def retention(
        self,
        *,
        born_event: str,
        return_event: str,
        from_date: str,
        to_date: str,
        born_where: str | None = None,
        return_where: str | None = None,
        interval: int = 1,
        interval_count: int = 10,
        unit: Literal["day", "week", "month"] = "day",
    ) -> RetentionResult:
        """Run a retention analysis query.

        Args:
            born_event: Event that defines cohort entry.
            return_event: Event that defines return.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            born_where: Optional filter for born event.
            return_where: Optional filter for return event.
            interval: Retention interval.
            interval_count: Number of intervals.
            unit: Time unit.

        Returns:
            RetentionResult with cohort retention data.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._live_query_service.retention(
            born_event=born_event,
            return_event=return_event,
            from_date=from_date,
            to_date=to_date,
            born_where=born_where,
            return_where=return_where,
            interval=interval,
            interval_count=interval_count,
            unit=unit,
        )

    def jql(self, script: str, params: dict[str, Any] | None = None) -> JQLResult:
        """Execute a custom JQL script.

        Args:
            script: JQL script code.
            params: Optional parameters to pass to script.

        Returns:
            JQLResult with raw query results.

        Raises:
            ConfigError: If API credentials not available.
            JQLSyntaxError: If script has syntax errors.
        """
        return self._live_query_service.jql(script=script, params=params)

    def event_counts(
        self,
        events: list[str],
        *,
        from_date: str,
        to_date: str,
        type: Literal["general", "unique", "average"] = "general",
        unit: Literal["day", "week", "month"] = "day",
    ) -> EventCountsResult:
        """Get event counts for multiple events.

        Args:
            events: List of event names.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            type: Counting method.
            unit: Time unit.

        Returns:
            EventCountsResult with time-series per event.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._live_query_service.event_counts(
            events=events,
            from_date=from_date,
            to_date=to_date,
            type=type,
            unit=unit,
        )

    def property_counts(
        self,
        event: str,
        property_name: str,
        *,
        from_date: str,
        to_date: str,
        type: Literal["general", "unique", "average"] = "general",
        unit: Literal["day", "week", "month"] = "day",
        values: list[str] | None = None,
        limit: int | None = None,
    ) -> PropertyCountsResult:
        """Get event counts broken down by property values.

        Args:
            event: Event name.
            property_name: Property to break down by.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            type: Counting method.
            unit: Time unit.
            values: Optional list of property values to include.
            limit: Maximum number of property values.

        Returns:
            PropertyCountsResult with time-series per property value.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._live_query_service.property_counts(
            event=event,
            property_name=property_name,
            from_date=from_date,
            to_date=to_date,
            type=type,
            unit=unit,
            values=values,
            limit=limit,
        )

    def activity_feed(
        self,
        distinct_ids: list[str],
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> ActivityFeedResult:
        """Get activity feed for specific users.

        Args:
            distinct_ids: List of user identifiers.
            from_date: Optional start date filter.
            to_date: Optional end date filter.

        Returns:
            ActivityFeedResult with user events.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._live_query_service.activity_feed(
            distinct_ids=distinct_ids,
            from_date=from_date,
            to_date=to_date,
        )

    def query_saved_report(
        self,
        bookmark_id: int,
        *,
        bookmark_type: Literal[
            "insights", "funnels", "retention", "flows"
        ] = "insights",
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> SavedReportResult:
        """Query a saved report by bookmark type.

        Routes to the appropriate Mixpanel API endpoint based on bookmark_type
        and returns the normalized result.

        Args:
            bookmark_id: ID of saved report (from list_bookmarks or Mixpanel URL).
            bookmark_type: Type of bookmark to query. Determines which API endpoint
                is called. Defaults to 'insights'.
            from_date: Start date (YYYY-MM-DD). Required for funnels, optional otherwise.
            to_date: End date (YYYY-MM-DD). Required for funnels, optional otherwise.

        Returns:
            SavedReportResult with report data and report_type property.

        Raises:
            ConfigError: If API credentials not available.
            QueryError: If bookmark_id is invalid or report not found.
        """
        return self._live_query_service.query_saved_report(
            bookmark_id=bookmark_id,
            bookmark_type=bookmark_type,
            from_date=from_date,
            to_date=to_date,
        )

    def query_flows(self, bookmark_id: int) -> FlowsResult:
        """Query a saved Flows report.

        Executes a saved Flows report by its bookmark ID, returning
        step data, breakdowns, and conversion rates.

        Args:
            bookmark_id: ID of saved flows report (from list_bookmarks or Mixpanel URL).

        Returns:
            FlowsResult with steps, breakdowns, and conversion rate.

        Raises:
            ConfigError: If API credentials not available.
            QueryError: If bookmark_id is invalid or report not found.
        """
        return self._live_query_service.query_flows(bookmark_id=bookmark_id)

    def frequency(
        self,
        *,
        from_date: str,
        to_date: str,
        unit: Literal["day", "week", "month"] = "day",
        addiction_unit: Literal["hour", "day"] = "hour",
        event: str | None = None,
        where: str | None = None,
    ) -> FrequencyResult:
        """Analyze event frequency distribution.

        Args:
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            unit: Overall time unit.
            addiction_unit: Measurement granularity.
            event: Optional event filter.
            where: Optional WHERE clause.

        Returns:
            FrequencyResult with frequency distribution.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._live_query_service.frequency(
            from_date=from_date,
            to_date=to_date,
            unit=unit,
            addiction_unit=addiction_unit,
            event=event,
            where=where,
        )

    def segmentation_numeric(
        self,
        event: str,
        *,
        from_date: str,
        to_date: str,
        on: str,
        unit: Literal["hour", "day"] = "day",
        where: str | None = None,
        type: Literal["general", "unique", "average"] = "general",
    ) -> NumericBucketResult:
        """Bucket events by numeric property ranges.

        Args:
            event: Event name.
            from_date: Start date.
            to_date: End date.
            on: Numeric property expression.
            unit: Time unit.
            where: Optional filter.
            type: Counting method.

        Returns:
            NumericBucketResult with bucketed data.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._live_query_service.segmentation_numeric(
            event=event,
            from_date=from_date,
            to_date=to_date,
            on=on,
            unit=unit,
            where=where,
            type=type,
        )

    def segmentation_sum(
        self,
        event: str,
        *,
        from_date: str,
        to_date: str,
        on: str,
        unit: Literal["hour", "day"] = "day",
        where: str | None = None,
    ) -> NumericSumResult:
        """Calculate sum of numeric property over time.

        Args:
            event: Event name.
            from_date: Start date.
            to_date: End date.
            on: Numeric property expression.
            unit: Time unit.
            where: Optional filter.

        Returns:
            NumericSumResult with sum values per period.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._live_query_service.segmentation_sum(
            event=event,
            from_date=from_date,
            to_date=to_date,
            on=on,
            unit=unit,
            where=where,
        )

    def segmentation_average(
        self,
        event: str,
        *,
        from_date: str,
        to_date: str,
        on: str,
        unit: Literal["hour", "day"] = "day",
        where: str | None = None,
    ) -> NumericAverageResult:
        """Calculate average of numeric property over time.

        Args:
            event: Event name.
            from_date: Start date.
            to_date: End date.
            on: Numeric property expression.
            unit: Time unit.
            where: Optional filter.

        Returns:
            NumericAverageResult with average values per period.

        Raises:
            ConfigError: If API credentials not available.
        """
        return self._live_query_service.segmentation_average(
            event=event,
            from_date=from_date,
            to_date=to_date,
            on=on,
            unit=unit,
            where=where,
        )

    # =========================================================================
    # JQL-BASED REMOTE DISCOVERY METHODS
    # =========================================================================

    def property_distribution(
        self,
        event: str,
        property: str,
        *,
        from_date: str,
        to_date: str,
        limit: int = 20,
    ) -> PropertyDistributionResult:
        """Get distribution of values for a property.

        Uses JQL to count occurrences of each property value, returning
        counts and percentages sorted by frequency.

        Args:
            event: Event name to analyze.
            property: Property name to get distribution for.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            limit: Maximum number of values to return. Default: 20.

        Returns:
            PropertyDistributionResult with value counts and percentages.

        Raises:
            ConfigError: If API credentials not available.
            QueryError: Script execution error.

        Example:
            ```python
            result = ws.property_distribution(
                event="Purchase",
                property="country",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )
            for v in result.values:
                print(f"{v.value}: {v.count} ({v.percentage:.1f}%)")
            ```
        """
        return self._live_query_service.property_distribution(
            event=event,
            property=property,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
        )

    def numeric_summary(
        self,
        event: str,
        property: str,
        *,
        from_date: str,
        to_date: str,
        percentiles: list[int] | None = None,
    ) -> NumericPropertySummaryResult:
        """Get statistical summary for a numeric property.

        Uses JQL to compute count, min, max, avg, stddev, and percentiles
        for a numeric property.

        Args:
            event: Event name to analyze.
            property: Numeric property name.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            percentiles: Percentiles to compute. Default: [25, 50, 75, 90, 95, 99].

        Returns:
            NumericPropertySummaryResult with statistics.

        Raises:
            ConfigError: If API credentials not available.
            QueryError: Script execution error or non-numeric property.

        Example:
            ```python
            result = ws.numeric_summary(
                event="Purchase",
                property="amount",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )
            print(f"Avg: {result.avg}, Median: {result.percentiles[50]}")
            ```
        """
        return self._live_query_service.numeric_summary(
            event=event,
            property=property,
            from_date=from_date,
            to_date=to_date,
            percentiles=percentiles,
        )

    def daily_counts(
        self,
        *,
        from_date: str,
        to_date: str,
        events: list[str] | None = None,
    ) -> DailyCountsResult:
        """Get daily event counts.

        Uses JQL to count events by day, optionally filtered to specific events.

        Args:
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            events: Optional list of events to count. None = all events.

        Returns:
            DailyCountsResult with date/event/count tuples.

        Raises:
            ConfigError: If API credentials not available.
            QueryError: Script execution error.

        Example:
            ```python
            result = ws.daily_counts(
                from_date="2024-01-01",
                to_date="2024-01-07",
                events=["Purchase", "Signup"],
            )
            for c in result.counts:
                print(f"{c.date} {c.event}: {c.count}")
            ```
        """
        return self._live_query_service.daily_counts(
            from_date=from_date,
            to_date=to_date,
            events=events,
        )

    def engagement_distribution(
        self,
        *,
        from_date: str,
        to_date: str,
        events: list[str] | None = None,
        buckets: list[int] | None = None,
    ) -> EngagementDistributionResult:
        """Get user engagement distribution.

        Uses JQL to bucket users by their event count, showing how many
        users performed N events.

        Args:
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            events: Optional list of events to count. None = all events.
            buckets: Bucket boundaries. Default: [1, 2, 5, 10, 25, 50, 100].

        Returns:
            EngagementDistributionResult with user counts per bucket.

        Raises:
            ConfigError: If API credentials not available.
            QueryError: Script execution error.

        Example:
            ```python
            result = ws.engagement_distribution(
                from_date="2024-01-01",
                to_date="2024-01-31",
            )
            for b in result.buckets:
                print(f"{b.bucket_label}: {b.user_count} ({b.percentage:.1f}%)")
            ```
        """
        return self._live_query_service.engagement_distribution(
            from_date=from_date,
            to_date=to_date,
            events=events,
            buckets=buckets,
        )

    def property_coverage(
        self,
        event: str,
        properties: list[str],
        *,
        from_date: str,
        to_date: str,
    ) -> PropertyCoverageResult:
        """Get property coverage statistics.

        Uses JQL to count how often each property is defined (non-null)
        vs undefined for the specified event.

        Args:
            event: Event name to analyze.
            properties: List of property names to check.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).

        Returns:
            PropertyCoverageResult with coverage statistics per property.

        Raises:
            ConfigError: If API credentials not available.
            QueryError: Script execution error.

        Example:
            ```python
            result = ws.property_coverage(
                event="Purchase",
                properties=["coupon_code", "referrer"],
                from_date="2024-01-01",
                to_date="2024-01-31",
            )
            for c in result.coverage:
                print(f"{c.property}: {c.coverage_percentage:.1f}% defined")
            ```
        """
        return self._live_query_service.property_coverage(
            event=event,
            properties=properties,
            from_date=from_date,
            to_date=to_date,
        )

    # =========================================================================
    # INTROSPECTION METHODS
    # =========================================================================

    def info(self) -> WorkspaceInfo:
        """Get metadata about this workspace.

        Returns:
            WorkspaceInfo with path, project_id, region, account, tables, size.
        """
        path = self.storage.path
        tables = [t.name for t in self.storage.list_tables()]

        # Calculate database size and creation time
        size_mb = 0.0
        created_at: datetime | None = None
        if path is not None and path.exists():
            try:
                stat = path.stat()
                size_mb = stat.st_size / 1_000_000
                created_at = datetime.fromtimestamp(stat.st_ctime)
            except (OSError, PermissionError):
                # File became inaccessible, use defaults
                pass

        return WorkspaceInfo(
            path=path,
            project_id=self._credentials.project_id if self._credentials else "unknown",
            region=self._credentials.region if self._credentials else "unknown",
            account=self._account_name,
            tables=tables,
            size_mb=size_mb,
            created_at=created_at,
        )

    def tables(self) -> list[TableInfo]:
        """List tables in the local database.

        Returns:
            List of TableInfo objects (name, type, row_count, fetched_at).
        """
        return self.storage.list_tables()

    def table_schema(self, table: str) -> TableSchema:
        """Get schema for a table in the local database.

        Args:
            table: Table name.

        Returns:
            TableSchema with column definitions.

        Raises:
            TableNotFoundError: If table doesn't exist.
        """
        return self.storage.get_schema(table)

    def sample(self, table: str, n: int = 10) -> pd.DataFrame:
        """Return random sample rows from a table.

        Uses DuckDB's reservoir sampling for representative results.
        Unlike LIMIT, sampling returns rows from throughout the table.

        Args:
            table: Table name to sample from.
            n: Number of rows to return (default: 10).

        Returns:
            DataFrame with n random rows. If table has fewer than n rows,
            returns all available rows.

        Raises:
            TableNotFoundError: If table doesn't exist.

        Example:
            ```python
            ws = Workspace()
            ws.sample("events")  # 10 random rows
            ws.sample("events", n=5)  # 5 random rows
            ```
        """
        # Validate table exists
        self.storage.get_schema(table)

        # Use DuckDB's reservoir sampling
        sql = f'SELECT * FROM "{table}" USING SAMPLE {n}'
        return self.storage.execute_df(sql)

    def summarize(self, table: str) -> SummaryResult:
        """Get statistical summary of all columns in a table.

        Uses DuckDB's SUMMARIZE command to compute min/max, quartiles,
        null percentage, and approximate distinct counts for each column.

        Args:
            table: Table name to summarize.

        Returns:
            SummaryResult with per-column statistics and total row count.

        Raises:
            TableNotFoundError: If table doesn't exist.

        Example:
            ```python
            result = ws.summarize("events")
            result.row_count         # 1234567
            result.columns[0].null_percentage  # 0.5
            result.df                # Full summary as DataFrame
            ```
        """
        # Validate table exists
        self.storage.get_schema(table)

        # Get row count
        row_count = self.storage.execute_scalar(f'SELECT COUNT(*) FROM "{table}"')

        # Get column statistics using SUMMARIZE
        summary_df = self.storage.execute_df(f'SUMMARIZE "{table}"')

        # Convert to ColumnSummary objects (to_dict is more efficient than iterrows)
        columns: list[ColumnSummary] = []
        for row in summary_df.to_dict("records"):
            columns.append(
                ColumnSummary(
                    column_name=str(row["column_name"]),
                    column_type=str(row["column_type"]),
                    min=row["min"],
                    max=row["max"],
                    approx_unique=int(row["approx_unique"]),
                    avg=self._try_float(row["avg"]),
                    std=self._try_float(row["std"]),
                    q25=row["q25"],
                    q50=row["q50"],
                    q75=row["q75"],
                    count=int(row["count"]),
                    null_percentage=float(row["null_percentage"]),
                )
            )

        return SummaryResult(
            table=table,
            row_count=int(row_count),
            columns=columns,
        )

    def event_breakdown(self, table: str) -> EventBreakdownResult:
        """Analyze event distribution in a table.

        Computes per-event counts, unique users, date ranges, and
        percentage of total for each event type.

        Args:
            table: Table name containing events. Must have columns:
                   event_name, event_time, distinct_id.

        Returns:
            EventBreakdownResult with per-event statistics.

        Raises:
            TableNotFoundError: If table doesn't exist.
            QueryError: If table lacks required columns (event_name,
                       event_time, distinct_id). Error message lists
                       the specific missing columns.

        Example:
            ```python
            breakdown = ws.event_breakdown("events")
            breakdown.total_events           # 1234567
            breakdown.events[0].event_name   # "Page View"
            breakdown.events[0].pct_of_total # 45.2
            ```
        """
        # Validate table exists and get schema
        schema = self.storage.get_schema(table)
        column_names = {col.name for col in schema.columns}

        # Check for required columns
        required_columns = {"event_name", "event_time", "distinct_id"}
        missing = required_columns - column_names
        if missing:
            raise QueryError(
                f"event_breakdown() requires columns {required_columns}, "
                f"but '{table}' is missing: {missing}",
                status_code=0,
            )

        # Get aggregate statistics
        agg_sql = f"""
            SELECT
                COUNT(*) as total_events,
                COUNT(DISTINCT distinct_id) as total_users,
                MIN(event_time) as min_time,
                MAX(event_time) as max_time
            FROM "{table}"
        """
        agg_result = self.storage.execute_rows(agg_sql)
        total_events, total_users, min_time, max_time = agg_result.rows[0]

        # Handle empty table
        if total_events == 0:
            return EventBreakdownResult(
                table=table,
                total_events=0,
                total_users=0,
                date_range=(datetime.min, datetime.min),
                events=[],
            )

        # Get per-event statistics
        breakdown_sql = f"""
            SELECT
                event_name,
                COUNT(*) as count,
                COUNT(DISTINCT distinct_id) as unique_users,
                MIN(event_time) as first_seen,
                MAX(event_time) as last_seen,
                ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as pct_of_total
            FROM "{table}"
            GROUP BY event_name
            ORDER BY count DESC
        """
        breakdown_rows = self.storage.execute_rows(breakdown_sql)

        events: list[EventStats] = []
        for row in breakdown_rows:
            event_name, count, unique_users, first_seen, last_seen, pct = row
            events.append(
                EventStats(
                    event_name=str(event_name),
                    count=int(count),
                    unique_users=int(unique_users),
                    first_seen=first_seen
                    if isinstance(first_seen, datetime)
                    else datetime.fromisoformat(str(first_seen)),
                    last_seen=last_seen
                    if isinstance(last_seen, datetime)
                    else datetime.fromisoformat(str(last_seen)),
                    pct_of_total=float(pct),
                )
            )

        return EventBreakdownResult(
            table=table,
            total_events=int(total_events),
            total_users=int(total_users),
            date_range=(
                min_time
                if isinstance(min_time, datetime)
                else datetime.fromisoformat(str(min_time)),
                max_time
                if isinstance(max_time, datetime)
                else datetime.fromisoformat(str(max_time)),
            ),
            events=events,
        )

    def property_keys(
        self,
        table: str,
        event: str | None = None,
    ) -> list[str]:
        """List all JSON property keys in a table.

        Extracts distinct keys from the 'properties' JSON column.
        Useful for discovering queryable fields in event properties.

        Args:
            table: Table name with a 'properties' JSON column.
            event: Optional event name to filter by. If provided, only
                   returns keys present in events of that type.

        Returns:
            Alphabetically sorted list of property key names.
            Empty list if no keys found.

        Raises:
            TableNotFoundError: If table doesn't exist.
            QueryError: If table lacks 'properties' column.

        Example:
            All keys across all events:

            ```python
            ws.property_keys("events")
            # ['$browser', '$city', 'page', 'referrer', 'user_plan']
            ```

            Keys for specific event type:

            ```python
            ws.property_keys("events", event="Purchase")
            # ['amount', 'currency', 'product_id', 'quantity']
            ```
        """
        # Validate table exists and get schema
        schema = self.storage.get_schema(table)
        column_names = {col.name for col in schema.columns}

        # Check for required column
        if "properties" not in column_names:
            raise QueryError(
                f"property_keys() requires a 'properties' column, "
                f"but '{table}' does not have one",
                status_code=0,
            )

        # Build query with optional event filter
        if event is not None:
            # Check if event_name column exists
            if "event_name" not in column_names:
                raise QueryError(
                    f"Cannot filter by event: '{table}' lacks 'event_name' column",
                    status_code=0,
                )
            sql = f"""
                SELECT DISTINCT unnest(json_keys(properties)) as key
                FROM "{table}"
                WHERE event_name = ?
                ORDER BY key
            """
            result = self.storage.execute_rows_params(sql, [event])
            rows = result.rows
        else:
            sql = f"""
                SELECT DISTINCT unnest(json_keys(properties)) as key
                FROM "{table}"
                ORDER BY key
            """
            result = self.storage.execute_rows(sql)
            rows = result.rows

        return [str(row[0]) for row in rows]

    def column_stats(
        self,
        table: str,
        column: str,
        *,
        top_n: int = 10,
    ) -> ColumnStatsResult:
        """Get detailed statistics for a single column.

        Performs deep analysis including null rates, cardinality,
        top values, and numeric statistics (for numeric columns).

        The column parameter supports JSON path expressions for
        analyzing properties stored in JSON columns:
        - `properties->>'$.country'` for string extraction
        - `CAST(properties->>'$.amount' AS DOUBLE)` for numeric

        Args:
            table: Table name to analyze.
            column: Column name or expression to analyze.
            top_n: Number of top values to return (default: 10).

        Returns:
            ColumnStatsResult with comprehensive column statistics.

        Raises:
            TableNotFoundError: If table doesn't exist.
            QueryError: If column expression is invalid.

        Example:
            Analyze standard column:

            ```python
            stats = ws.column_stats("events", "event_name")
            stats.unique_count      # 47
            stats.top_values[:3]    # [('Page View', 45230), ...]
            ```

            Analyze JSON property:

            ```python
            stats = ws.column_stats("events", "properties->>'$.country'")
            ```

        Security:
            The column parameter is interpolated directly into SQL queries
            to allow expression syntax. Only use with trusted input from
            developers or AI coding agents. Do not pass untrusted user input.
        """
        # Validate table exists
        self.storage.get_schema(table)

        # Get total row count
        total_rows = self.storage.execute_scalar(f'SELECT COUNT(*) FROM "{table}"')

        # Get basic stats: count, null_count, approx unique
        stats_sql = f"""
            SELECT
                COUNT({column}) as count,
                COUNT(*) - COUNT({column}) as null_count,
                APPROX_COUNT_DISTINCT({column}) as unique_count
            FROM "{table}"
        """
        try:
            stats_result = self.storage.execute_rows(stats_sql)
        except Exception as e:
            raise QueryError(
                f"Invalid column expression: {column}. Error: {e}",
                status_code=0,
            ) from e

        count, null_count, unique_count = stats_result.rows[0]

        # Calculate percentages
        null_pct = (null_count / total_rows * 100) if total_rows > 0 else 0.0
        unique_pct = (unique_count / count * 100) if count > 0 else 0.0

        # Get top values
        top_sql = f"""
            SELECT {column} as value, COUNT(*) as cnt
            FROM "{table}"
            WHERE {column} IS NOT NULL
            GROUP BY {column}
            ORDER BY cnt DESC
            LIMIT {top_n}
        """
        top_result = self.storage.execute_rows(top_sql)
        top_values: list[tuple[Any, int]] = [
            (row[0], int(row[1])) for row in top_result.rows
        ]

        # Detect column type to determine if numeric stats apply
        type_sql = (
            f'SELECT typeof({column}) FROM "{table}" WHERE {column} IS NOT NULL LIMIT 1'
        )
        try:
            type_result = self.storage.execute_rows(type_sql)
            dtype = str(type_result.rows[0][0]) if type_result.rows else "UNKNOWN"
        except Exception:
            dtype = "UNKNOWN"

        # Get numeric stats if applicable
        min_val: float | None = None
        max_val: float | None = None
        mean_val: float | None = None
        std_val: float | None = None

        numeric_types = {
            "INTEGER",
            "BIGINT",
            "DOUBLE",
            "FLOAT",
            "DECIMAL",
            "HUGEINT",
            "SMALLINT",
            "TINYINT",
            "UBIGINT",
            "UINTEGER",
            "USMALLINT",
            "UTINYINT",
        }
        if dtype.upper() in numeric_types:
            numeric_sql = f"""
                SELECT
                    MIN({column}) as min_val,
                    MAX({column}) as max_val,
                    AVG({column}) as mean_val,
                    STDDEV({column}) as std_val
                FROM "{table}"
            """
            try:
                numeric_result = self.storage.execute_rows(numeric_sql)
                if numeric_result.rows:
                    row = numeric_result.rows[0]
                    min_val = float(row[0]) if row[0] is not None else None
                    max_val = float(row[1]) if row[1] is not None else None
                    mean_val = float(row[2]) if row[2] is not None else None
                    std_val = float(row[3]) if row[3] is not None else None
            except Exception:
                # Not numeric, skip
                pass

        return ColumnStatsResult(
            table=table,
            column=column,
            dtype=dtype,
            count=int(count),
            null_count=int(null_count),
            null_pct=round(null_pct, 2),
            unique_count=int(unique_count),
            unique_pct=round(unique_pct, 2),
            top_values=top_values,
            min=min_val,
            max=max_val,
            mean=mean_val,
            std=std_val,
        )

    # =========================================================================
    # TABLE MANAGEMENT METHODS
    # =========================================================================

    def drop(self, *names: str) -> None:
        """Drop specified tables.

        Args:
            *names: Table names to drop.

        Raises:
            TableNotFoundError: If any table doesn't exist.
        """
        for name in names:
            self.storage.drop_table(name)

    def drop_all(self, type: TableType | None = None) -> None:
        """Drop all tables from the workspace, optionally filtered by type.

        Permanently removes all tables and their data. When used with the type
        parameter, only tables matching the specified type are dropped.

        Args:
            type: Optional table type filter. Valid values: "events", "profiles".
                  If None, all tables are dropped regardless of type.

        Raises:
            TableNotFoundError: If a table cannot be dropped (rare in practice).

        Example:
            Drop all event tables:

            ```python
            ws = Workspace()
            ws.drop_all(type="events")  # Only drops event tables
            ws.close()
            ```

            Drop all tables:

            ```python
            ws = Workspace()
            ws.drop_all()  # Drops everything
            ws.close()
            ```
        """
        tables = self.storage.list_tables()
        for table in tables:
            if type is None or table.type == type:
                self.storage.drop_table(table.name)

    # =========================================================================
    # ESCAPE HATCHES
    # =========================================================================

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Direct access to the DuckDB connection.

        Use this for operations not covered by the Workspace API.

        Returns:
            The underlying DuckDB connection.
        """
        return self.storage.connection

    @property
    def db_path(self) -> Path | None:
        """Path to the DuckDB database file.

        Returns the filesystem path where data is stored. Useful for:
        - Knowing where your data lives
        - Opening the same database later with ``Workspace.open(path)``
        - Debugging and logging

        Returns:
            The database file path, or None for in-memory workspaces.

        Example:
            Save the path for later use::

                ws = mp.Workspace()
                path = ws.db_path
                ws.close()

                # Later, reopen the same database
                ws = mp.Workspace.open(path)
        """
        return self.storage.path

    @property
    def api(self) -> MixpanelAPIClient:
        """Direct access to the Mixpanel API client.

        Use this escape hatch for Mixpanel API operations not covered by the
        Workspace class. The client handles authentication automatically.

        The client provides:
            - ``request(method, url, **kwargs)``: Make authenticated requests
              to any Mixpanel API endpoint.
            - ``project_id``: The configured project ID for constructing URLs.
            - ``region``: The configured region ('us', 'eu', or 'in').

        Returns:
            The underlying MixpanelAPIClient.

        Raises:
            ConfigError: If API credentials not available.

        Example:
            Fetch event schema from the Lexicon Schemas API::

                import mixpanel_data as mp
                from urllib.parse import quote

                ws = mp.Workspace()
                client = ws.api

                # Build the URL with proper encoding
                event_name = quote("Added To Cart", safe="")
                url = f"https://mixpanel.com/api/app/projects/{client.project_id}/schemas/event/{event_name}"

                # Make the authenticated request
                schema = client.request("GET", url)
                print(schema)
        """
        return self._require_api_client()

    # =========================================================================
    # DASHBOARD CRUD (Phase 024)
    # =========================================================================

    def list_dashboards(self, *, ids: list[int] | None = None) -> list[Dashboard]:
        """List dashboards for the current project/workspace.

        Retrieves all dashboards visible to the authenticated user,
        optionally filtered by specific IDs.

        Args:
            ids: Optional list of dashboard IDs to filter by.

        Returns:
            List of ``Dashboard`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            dashboards = ws.list_dashboards()
            for d in dashboards:
                print(f"{d.title} (id={d.id})")
            ```
        """
        client = self._require_api_client()
        raw = client.list_dashboards(ids=ids)
        return [Dashboard.model_validate(d) for d in raw]

    def create_dashboard(self, params: CreateDashboardParams) -> Dashboard:
        """Create a new dashboard.

        Args:
            params: Dashboard creation parameters.

        Returns:
            The newly created ``Dashboard``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid parameters (400, 422).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            dashboard = ws.create_dashboard(
                CreateDashboardParams(title="Q1 Metrics")
            )
            ```
        """
        client = self._require_api_client()
        raw = client.create_dashboard(params.model_dump(exclude_none=True))
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for create_dashboard",
            )
        return Dashboard.model_validate(raw)

    def get_dashboard(self, dashboard_id: int) -> Dashboard:
        """Get a single dashboard by ID.

        Args:
            dashboard_id: Dashboard identifier.

        Returns:
            The ``Dashboard`` object.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            dashboard = ws.get_dashboard(12345)
            ```
        """
        client = self._require_api_client()
        raw = client.get_dashboard(dashboard_id)
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for get_dashboard",
            )
        return Dashboard.model_validate(raw)

    def update_dashboard(
        self, dashboard_id: int, params: UpdateDashboardParams
    ) -> Dashboard:
        """Update an existing dashboard.

        Args:
            dashboard_id: Dashboard identifier.
            params: Fields to update.

        Returns:
            The updated ``Dashboard``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found or invalid params (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            updated = ws.update_dashboard(
                12345, UpdateDashboardParams(title="New Title")
            )
            ```
        """
        client = self._require_api_client()
        raw = client.update_dashboard(
            dashboard_id, params.model_dump(exclude_none=True)
        )
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for update_dashboard",
            )
        return Dashboard.model_validate(raw)

    def delete_dashboard(self, dashboard_id: int) -> None:
        """Delete a dashboard.

        Args:
            dashboard_id: Dashboard identifier.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_dashboard(12345)
            ```
        """
        client = self._require_api_client()
        client.delete_dashboard(dashboard_id)

    def bulk_delete_dashboards(self, ids: list[int]) -> None:
        """Delete multiple dashboards.

        Args:
            ids: List of dashboard IDs to delete.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: One or more IDs not found (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.bulk_delete_dashboards([1, 2, 3])
            ```
        """
        client = self._require_api_client()
        client.bulk_delete_dashboards(ids)

    # =========================================================================
    # DASHBOARD ADVANCED OPERATIONS (Phase 024)
    # =========================================================================

    def favorite_dashboard(self, dashboard_id: int) -> None:
        """Favorite a dashboard.

        Args:
            dashboard_id: Dashboard identifier.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.favorite_dashboard(12345)
            ```
        """
        client = self._require_api_client()
        client.favorite_dashboard(dashboard_id)

    def unfavorite_dashboard(self, dashboard_id: int) -> None:
        """Unfavorite a dashboard.

        Args:
            dashboard_id: Dashboard identifier.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.unfavorite_dashboard(12345)
            ```
        """
        client = self._require_api_client()
        client.unfavorite_dashboard(dashboard_id)

    def pin_dashboard(self, dashboard_id: int) -> None:
        """Pin a dashboard.

        Args:
            dashboard_id: Dashboard identifier.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.pin_dashboard(12345)
            ```
        """
        client = self._require_api_client()
        client.pin_dashboard(dashboard_id)

    def unpin_dashboard(self, dashboard_id: int) -> None:
        """Unpin a dashboard.

        Args:
            dashboard_id: Dashboard identifier.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.unpin_dashboard(12345)
            ```
        """
        client = self._require_api_client()
        client.unpin_dashboard(dashboard_id)

    def remove_report_from_dashboard(
        self, dashboard_id: int, bookmark_id: int
    ) -> Dashboard:
        """Remove a report from a dashboard.

        Args:
            dashboard_id: Dashboard identifier.
            bookmark_id: Bookmark/report identifier to remove.

        Returns:
            The updated ``Dashboard``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard or bookmark not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            updated = ws.remove_report_from_dashboard(12345, 42)
            ```
        """
        client = self._require_api_client()
        raw = client.remove_report_from_dashboard(dashboard_id, bookmark_id)
        return Dashboard.model_validate(raw)

    def list_blueprint_templates(
        self, *, include_reports: bool = False
    ) -> list[BlueprintTemplate]:
        """List available dashboard blueprint templates.

        Args:
            include_reports: Whether to include report details.

        Returns:
            List of ``BlueprintTemplate`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            templates = ws.list_blueprint_templates()
            ```
        """
        client = self._require_api_client()
        raw = client.list_blueprint_templates(include_reports=include_reports)
        return [BlueprintTemplate.model_validate(t) for t in raw]

    def create_blueprint(self, template_type: str) -> Dashboard:
        """Create a dashboard from a blueprint template.

        Args:
            template_type: Blueprint template type identifier.

        Returns:
            The newly created ``Dashboard``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid template type (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            dashboard = ws.create_blueprint("onboarding")
            ```
        """
        client = self._require_api_client()
        raw = client.create_blueprint(template_type)
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for create_blueprint",
            )
        return Dashboard.model_validate(raw)

    def get_blueprint_config(self, dashboard_id: int) -> BlueprintConfig:
        """Get the blueprint configuration for a dashboard.

        Args:
            dashboard_id: Dashboard identifier.

        Returns:
            ``BlueprintConfig`` with template variables.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            config = ws.get_blueprint_config(12345)
            ```
        """
        client = self._require_api_client()
        raw = client.get_blueprint_config(dashboard_id)
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for get_blueprint_config",
            )
        return BlueprintConfig.model_validate(raw)

    def update_blueprint_cohorts(self, cohorts: list[dict[str, Any]]) -> None:
        """Update cohorts for blueprint configuration.

        Args:
            cohorts: List of cohort configuration dicts.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid cohort configuration (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.update_blueprint_cohorts([{"id": 1, "name": "Test"}])
            ```
        """
        client = self._require_api_client()
        client.update_blueprint_cohorts(cohorts)

    def finalize_blueprint(self, params: BlueprintFinishParams) -> Dashboard:
        """Finalize a blueprint dashboard with cards.

        Args:
            params: Blueprint finalization parameters.

        Returns:
            The finalized ``Dashboard``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid parameters (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            dashboard = ws.finalize_blueprint(
                BlueprintFinishParams(
                    dashboard_id=1,
                    cards=[BlueprintCard(card_type="report", bookmark_id=42)],
                )
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True, by_alias=True)
        raw = client.finalize_blueprint(body)
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for finalize_blueprint",
            )
        return Dashboard.model_validate(raw)

    def create_rca_dashboard(self, params: CreateRcaDashboardParams) -> Dashboard:
        """Create an RCA (Root Cause Analysis) dashboard.

        Args:
            params: RCA dashboard parameters.

        Returns:
            The newly created ``Dashboard``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid parameters (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            dashboard = ws.create_rca_dashboard(
                CreateRcaDashboardParams(
                    rca_source_id=42,
                    rca_source_data=RcaSourceData(source_type="anomaly"),
                )
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True, by_alias=True)
        raw = client.create_rca_dashboard(body)
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for create_rca_dashboard",
            )
        return Dashboard.model_validate(raw)

    def get_bookmark_dashboard_ids(self, bookmark_id: int) -> list[int]:
        """Get dashboard IDs containing a bookmark/report.

        Args:
            bookmark_id: Bookmark identifier.

        Returns:
            List of dashboard IDs.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Bookmark not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            dash_ids = ws.get_bookmark_dashboard_ids(42)
            ```
        """
        client = self._require_api_client()
        return client.get_bookmark_dashboard_ids(bookmark_id)

    def get_dashboard_erf(self, dashboard_id: int) -> dict[str, Any]:
        """Get ERF data for a dashboard.

        Args:
            dashboard_id: Dashboard identifier.

        Returns:
            Dict with ERF metrics data.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            erf = ws.get_dashboard_erf(12345)
            ```
        """
        client = self._require_api_client()
        return client.get_dashboard_erf(dashboard_id)

    def update_report_link(
        self,
        dashboard_id: int,
        report_link_id: int,
        params: UpdateReportLinkParams,
    ) -> None:
        """Update a report link on a dashboard.

        Args:
            dashboard_id: Dashboard identifier.
            report_link_id: Report link identifier.
            params: Update parameters.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard or link not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.update_report_link(
                12345, 42, UpdateReportLinkParams(link_type="embedded")
            )
            ```
        """
        client = self._require_api_client()
        client.update_report_link(
            dashboard_id,
            report_link_id,
            params.model_dump(by_alias=True, exclude_none=True),
        )

    def update_text_card(
        self,
        dashboard_id: int,
        text_card_id: int,
        params: UpdateTextCardParams,
    ) -> None:
        """Update a text card on a dashboard.

        Args:
            dashboard_id: Dashboard identifier.
            text_card_id: Text card identifier.
            params: Update parameters.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard or text card not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.update_text_card(
                12345, 99, UpdateTextCardParams(markdown="# Hello")
            )
            ```
        """
        client = self._require_api_client()
        client.update_text_card(
            dashboard_id,
            text_card_id,
            params.model_dump(exclude_none=True),
        )

    # =========================================================================
    # BOOKMARK/REPORT CRUD (Phase 024)
    # =========================================================================

    def list_bookmarks_v2(
        self,
        *,
        bookmark_type: BookmarkType | None = None,
        ids: list[int] | None = None,
    ) -> list[Bookmark]:
        """List bookmarks/reports via the App API v2 endpoint.

        Args:
            bookmark_type: Optional report type filter (e.g., ``"funnels"``).
            ids: Optional list of bookmark IDs to filter by.

        Returns:
            List of ``Bookmark`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            reports = ws.list_bookmarks_v2(bookmark_type="funnels")
            for r in reports:
                print(f"{r.name} ({r.bookmark_type})")
            ```
        """
        client = self._require_api_client()
        raw = client.list_bookmarks_v2(bookmark_type=bookmark_type, ids=ids)
        return [Bookmark.model_validate(b) for b in raw]

    def create_bookmark(self, params: CreateBookmarkParams) -> Bookmark:
        """Create a new bookmark (saved report).

        Args:
            params: Bookmark creation parameters.

        Returns:
            The newly created ``Bookmark``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid parameters (400, 422).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            report = ws.create_bookmark(CreateBookmarkParams(
                name="Signup Funnel",
                bookmark_type="funnels",
                params={"events": [{"event": "Signup"}]},
            ))
            ```
        """
        client = self._require_api_client()
        raw = client.create_bookmark(
            params.model_dump(by_alias=True, exclude_none=True)
        )
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for create_bookmark",
            )
        return Bookmark.model_validate(raw)

    def get_bookmark(self, bookmark_id: int) -> Bookmark:
        """Get a single bookmark by ID.

        Args:
            bookmark_id: Bookmark identifier.

        Returns:
            The ``Bookmark`` object.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Bookmark not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            report = ws.get_bookmark(12345)
            ```
        """
        client = self._require_api_client()
        raw = client.get_bookmark(bookmark_id)
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for get_bookmark",
            )
        return Bookmark.model_validate(raw)

    def update_bookmark(
        self, bookmark_id: int, params: UpdateBookmarkParams
    ) -> Bookmark:
        """Update an existing bookmark.

        Args:
            bookmark_id: Bookmark identifier.
            params: Fields to update.

        Returns:
            The updated ``Bookmark``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Bookmark not found or invalid params (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            updated = ws.update_bookmark(
                12345, UpdateBookmarkParams(name="Renamed")
            )
            ```
        """
        client = self._require_api_client()
        raw = client.update_bookmark(bookmark_id, params.model_dump(exclude_none=True))
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for update_bookmark",
            )
        return Bookmark.model_validate(raw)

    def delete_bookmark(self, bookmark_id: int) -> None:
        """Delete a bookmark.

        Args:
            bookmark_id: Bookmark identifier.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Bookmark not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_bookmark(12345)
            ```
        """
        client = self._require_api_client()
        client.delete_bookmark(bookmark_id)

    def bulk_delete_bookmarks(self, ids: list[int]) -> None:
        """Delete multiple bookmarks.

        Args:
            ids: List of bookmark IDs to delete.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: One or more IDs not found (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.bulk_delete_bookmarks([1, 2, 3])
            ```
        """
        client = self._require_api_client()
        client.bulk_delete_bookmarks(ids)

    def bulk_update_bookmarks(self, entries: list[BulkUpdateBookmarkEntry]) -> None:
        """Update multiple bookmarks.

        Args:
            entries: List of bookmark update entries.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid entries or IDs not found (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.bulk_update_bookmarks([
                BulkUpdateBookmarkEntry(id=1, name="Renamed"),
            ])
            ```
        """
        client = self._require_api_client()
        client.bulk_update_bookmarks([e.model_dump(exclude_none=True) for e in entries])

    def bookmark_linked_dashboard_ids(self, bookmark_id: int) -> list[int]:
        """Get dashboard IDs linked to a bookmark.

        Args:
            bookmark_id: Bookmark identifier.

        Returns:
            List of dashboard IDs.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Bookmark not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            dash_ids = ws.bookmark_linked_dashboard_ids(42)
            ```
        """
        client = self._require_api_client()
        return client.bookmark_linked_dashboard_ids(bookmark_id)

    def get_bookmark_history(
        self,
        bookmark_id: int,
        *,
        cursor: str | None = None,
        page_size: int | None = None,
    ) -> BookmarkHistoryResponse:
        """Get the change history for a bookmark.

        Args:
            bookmark_id: Bookmark identifier.
            cursor: Opaque pagination cursor.
            page_size: Maximum entries per page.

        Returns:
            ``BookmarkHistoryResponse`` with results and pagination.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Bookmark not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            history = ws.get_bookmark_history(12345, page_size=10)
            ```
        """
        client = self._require_api_client()
        raw = client.get_bookmark_history(
            bookmark_id, cursor=cursor, page_size=page_size
        )
        return BookmarkHistoryResponse.model_validate(raw)

    # =========================================================================
    # COHORT CRUD (Phase 024)
    # =========================================================================

    def list_cohorts_full(
        self,
        *,
        data_group_id: str | None = None,
        ids: list[int] | None = None,
    ) -> list[Cohort]:
        """List cohorts via the App API (full detail).

        Unlike ``cohorts()`` which uses the discovery endpoint, this method
        uses the App API and returns full ``Cohort`` objects with all metadata.

        Args:
            data_group_id: Optional data group filter.
            ids: Optional list of cohort IDs to filter by.

        Returns:
            List of ``Cohort`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            cohorts = ws.list_cohorts_full()
            for c in cohorts:
                print(f"{c.name} ({c.count} users)")
            ```
        """
        client = self._require_api_client()
        raw = client.list_cohorts_app(data_group_id=data_group_id, ids=ids)
        return [Cohort.model_validate(c) for c in raw]

    def get_cohort(self, cohort_id: int) -> Cohort:
        """Get a single cohort by ID via the App API.

        Args:
            cohort_id: Cohort identifier.

        Returns:
            The ``Cohort`` object.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Cohort not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            cohort = ws.get_cohort(12345)
            ```
        """
        client = self._require_api_client()
        raw = client.get_cohort(cohort_id)
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for get_cohort",
            )
        return Cohort.model_validate(raw)

    def create_cohort(self, params: CreateCohortParams) -> Cohort:
        """Create a new cohort.

        Args:
            params: Cohort creation parameters.

        Returns:
            The newly created ``Cohort``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid parameters (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            cohort = ws.create_cohort(
                CreateCohortParams(name="Power Users")
            )
            ```
        """
        client = self._require_api_client()
        raw = client.create_cohort(params.model_dump(exclude_none=True))
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for create_cohort",
            )
        return Cohort.model_validate(raw)

    def update_cohort(self, cohort_id: int, params: UpdateCohortParams) -> Cohort:
        """Update an existing cohort.

        Args:
            cohort_id: Cohort identifier.
            params: Fields to update.

        Returns:
            The updated ``Cohort``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Cohort not found or invalid params (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            updated = ws.update_cohort(
                12345, UpdateCohortParams(name="Renamed")
            )
            ```
        """
        client = self._require_api_client()
        raw = client.update_cohort(cohort_id, params.model_dump(exclude_none=True))
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for update_cohort",
            )
        return Cohort.model_validate(raw)

    def delete_cohort(self, cohort_id: int) -> None:
        """Delete a cohort.

        Args:
            cohort_id: Cohort identifier.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Cohort not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_cohort(12345)
            ```
        """
        client = self._require_api_client()
        client.delete_cohort(cohort_id)

    def bulk_delete_cohorts(self, ids: list[int]) -> None:
        """Delete multiple cohorts.

        Args:
            ids: List of cohort IDs to delete.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: One or more IDs not found (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.bulk_delete_cohorts([1, 2, 3])
            ```
        """
        client = self._require_api_client()
        client.bulk_delete_cohorts(ids)

    def bulk_update_cohorts(self, entries: list[BulkUpdateCohortEntry]) -> None:
        """Update multiple cohorts.

        Args:
            entries: List of cohort update entries.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid entries or IDs not found (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.bulk_update_cohorts([
                BulkUpdateCohortEntry(id=1, name="Renamed"),
            ])
            ```
        """
        client = self._require_api_client()
        client.bulk_update_cohorts([e.model_dump(exclude_none=True) for e in entries])

    # =========================================================================
    # FEATURE FLAG CRUD (Phase 025)
    # =========================================================================

    def list_feature_flags(
        self, *, include_archived: bool = False
    ) -> list[FeatureFlag]:
        """List feature flags for the current project/workspace.

        Args:
            include_archived: When True, include archived flags.

        Returns:
            List of ``FeatureFlag`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            flags = ws.list_feature_flags()
            for f in flags:
                print(f"{f.name} ({f.key})")
            ```
        """
        client = self._require_api_client()
        raw = client.list_feature_flags(include_archived=include_archived)
        return [FeatureFlag.model_validate(f) for f in raw]

    def create_feature_flag(self, params: CreateFeatureFlagParams) -> FeatureFlag:
        """Create a new feature flag.

        Args:
            params: Flag creation parameters.

        Returns:
            The newly created ``FeatureFlag``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Duplicate key or invalid parameters (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            flag = ws.create_feature_flag(
                CreateFeatureFlagParams(name="Dark Mode", key="dark_mode")
            )
            ```
        """
        client = self._require_api_client()
        raw = client.create_feature_flag(params.model_dump(exclude_none=True))
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for create_feature_flag",
            )
        return FeatureFlag.model_validate(raw)

    def get_feature_flag(self, flag_id: str) -> FeatureFlag:
        """Get a single feature flag by ID.

        Args:
            flag_id: Feature flag UUID.

        Returns:
            The ``FeatureFlag`` object.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            flag = ws.get_feature_flag("abc-123-uuid")
            ```
        """
        client = self._require_api_client()
        raw = client.get_feature_flag(flag_id)
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for get_feature_flag",
            )
        return FeatureFlag.model_validate(raw)

    def update_feature_flag(
        self, flag_id: str, params: UpdateFeatureFlagParams
    ) -> FeatureFlag:
        """Update a feature flag (full replacement, PUT semantics).

        Args:
            flag_id: Feature flag UUID.
            params: Complete flag configuration.

        Returns:
            The updated ``FeatureFlag``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found or invalid params (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            updated = ws.update_feature_flag(
                "abc-123", UpdateFeatureFlagParams(
                    name="X", key="x",
                    status=FeatureFlagStatus.ENABLED,
                    ruleset={"variants": []},
                )
            )
            ```
        """
        client = self._require_api_client()
        raw = client.update_feature_flag(flag_id, params.model_dump(exclude_none=True))
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for update_feature_flag",
            )
        return FeatureFlag.model_validate(raw)

    def delete_feature_flag(self, flag_id: str) -> None:
        """Delete a feature flag.

        Args:
            flag_id: Feature flag UUID.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_feature_flag("abc-123-uuid")
            ```
        """
        client = self._require_api_client()
        client.delete_feature_flag(flag_id)

    # =========================================================================
    # FEATURE FLAG LIFECYCLE (Phase 025)
    # =========================================================================

    def archive_feature_flag(self, flag_id: str) -> None:
        """Archive a feature flag (soft-delete).

        Args:
            flag_id: Feature flag UUID.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.archive_feature_flag("abc-123-uuid")
            ```
        """
        client = self._require_api_client()
        client.archive_feature_flag(flag_id)

    def restore_feature_flag(self, flag_id: str) -> FeatureFlag:
        """Restore an archived feature flag.

        Args:
            flag_id: Feature flag UUID.

        Returns:
            The restored ``FeatureFlag``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            restored = ws.restore_feature_flag("abc-123-uuid")
            ```
        """
        client = self._require_api_client()
        raw = client.restore_feature_flag(flag_id)
        return FeatureFlag.model_validate(raw)

    def duplicate_feature_flag(self, flag_id: str) -> FeatureFlag:
        """Duplicate a feature flag.

        Args:
            flag_id: Feature flag UUID.

        Returns:
            The newly created duplicate ``FeatureFlag``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            dup = ws.duplicate_feature_flag("abc-123-uuid")
            ```
        """
        client = self._require_api_client()
        raw = client.duplicate_feature_flag(flag_id)
        return FeatureFlag.model_validate(raw)

    # =========================================================================
    # FEATURE FLAG OPERATIONS (Phase 025)
    # =========================================================================

    def set_flag_test_users(self, flag_id: str, params: SetTestUsersParams) -> None:
        """Set test user variant overrides for a feature flag.

        Args:
            flag_id: Feature flag UUID.
            params: Test user mapping.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404) or invalid payload (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.set_flag_test_users(
                "abc-123",
                SetTestUsersParams(users={"on": "user-1"}),
            )
            ```
        """
        client = self._require_api_client()
        client.set_flag_test_users(flag_id, params.model_dump())

    def get_flag_history(
        self,
        flag_id: str,
        *,
        page: str | None = None,
        page_size: int | None = None,
    ) -> FlagHistoryResponse:
        """Get paginated change history for a feature flag.

        Args:
            flag_id: Feature flag UUID.
            page: Pagination cursor.
            page_size: Results per page.

        Returns:
            ``FlagHistoryResponse`` with events and count.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            history = ws.get_flag_history("abc-123", page_size=50)
            ```
        """
        client = self._require_api_client()
        query_params: dict[str, str] = {}
        if page is not None:
            query_params["page"] = page
        if page_size is not None:
            query_params["page_size"] = str(page_size)
        raw = client.get_flag_history(
            flag_id, params=query_params if query_params else None
        )
        return FlagHistoryResponse.model_validate(raw)

    def get_flag_limits(self) -> FlagLimitsResponse:
        """Get account-level feature flag limits and usage.

        Returns:
            ``FlagLimitsResponse`` with limit, usage, trial, and contract status.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            limits = ws.get_flag_limits()
            print(f"{limits.current_usage}/{limits.limit}")
            ```
        """
        client = self._require_api_client()
        raw = client.get_flag_limits()
        return FlagLimitsResponse.model_validate(raw)

    # =========================================================================
    # EXPERIMENT CRUD (Phase 025)
    # =========================================================================

    def list_experiments(self, *, include_archived: bool = False) -> list[Experiment]:
        """List experiments for the current project.

        Args:
            include_archived: When True, include archived experiments.

        Returns:
            List of ``Experiment`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            experiments = ws.list_experiments()
            for e in experiments:
                print(f"{e.name} (status={e.status})")
            ```
        """
        client = self._require_api_client()
        raw = client.list_experiments(include_archived=include_archived)
        return [Experiment.model_validate(e) for e in raw]

    def create_experiment(self, params: CreateExperimentParams) -> Experiment:
        """Create a new experiment in Draft status.

        Args:
            params: Experiment creation parameters.

        Returns:
            The newly created ``Experiment``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid parameters (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            exp = ws.create_experiment(
                CreateExperimentParams(name="Checkout Flow Test")
            )
            ```
        """
        client = self._require_api_client()
        raw = client.create_experiment(params.model_dump(exclude_none=True))
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for create_experiment",
            )
        return Experiment.model_validate(raw)

    def get_experiment(self, experiment_id: str) -> Experiment:
        """Get a single experiment by ID.

        Args:
            experiment_id: Experiment UUID.

        Returns:
            The ``Experiment`` object.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Experiment not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            exp = ws.get_experiment("xyz-456-uuid")
            ```
        """
        client = self._require_api_client()
        raw = client.get_experiment(experiment_id)
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for get_experiment",
            )
        return Experiment.model_validate(raw)

    def update_experiment(
        self, experiment_id: str, params: UpdateExperimentParams
    ) -> Experiment:
        """Update an experiment (PATCH semantics).

        Args:
            experiment_id: Experiment UUID.
            params: Fields to update.

        Returns:
            The updated ``Experiment``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Experiment not found or invalid params (400, 404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            updated = ws.update_experiment(
                "xyz-456", UpdateExperimentParams(description="Updated")
            )
            ```
        """
        client = self._require_api_client()
        raw = client.update_experiment(
            experiment_id, params.model_dump(exclude_none=True)
        )
        if raw is None:
            raise MixpanelDataError(
                "API returned empty response for update_experiment",
            )
        return Experiment.model_validate(raw)

    def delete_experiment(self, experiment_id: str) -> None:
        """Delete an experiment.

        Args:
            experiment_id: Experiment UUID.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Experiment not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_experiment("xyz-456-uuid")
            ```
        """
        client = self._require_api_client()
        client.delete_experiment(experiment_id)

    # =========================================================================
    # EXPERIMENT LIFECYCLE (Phase 025)
    # =========================================================================

    def launch_experiment(self, experiment_id: str) -> Experiment:
        """Launch an experiment (Draft → Active).

        Args:
            experiment_id: Experiment UUID.

        Returns:
            The launched ``Experiment`` with updated status.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid state transition (400) or not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            launched = ws.launch_experiment("xyz-456-uuid")
            ```
        """
        client = self._require_api_client()
        raw = client.launch_experiment(experiment_id)
        return Experiment.model_validate(raw)

    def conclude_experiment(
        self,
        experiment_id: str,
        *,
        params: ExperimentConcludeParams | None = None,
    ) -> Experiment:
        """Conclude an experiment (Active → Concluded).

        Always sends a JSON body (empty ``{}`` if no params).

        Args:
            experiment_id: Experiment UUID.
            params: Optional conclude parameters (e.g. end date override).

        Returns:
            The concluded ``Experiment``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid state transition (400) or not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            concluded = ws.conclude_experiment("xyz-456-uuid")
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True) if params else {}
        raw = client.conclude_experiment(experiment_id, body)
        return Experiment.model_validate(raw)

    def decide_experiment(
        self, experiment_id: str, params: ExperimentDecideParams
    ) -> Experiment:
        """Record the experiment decision (Concluded → Success/Fail).

        Args:
            experiment_id: Experiment UUID.
            params: Decision parameters (success, variant, message).

        Returns:
            The decided ``Experiment`` with terminal status.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid state transition (400) or not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            decided = ws.decide_experiment(
                "xyz-456",
                ExperimentDecideParams(success=True, variant="simplified"),
            )
            ```
        """
        client = self._require_api_client()
        raw = client.decide_experiment(
            experiment_id, params.model_dump(exclude_none=True)
        )
        return Experiment.model_validate(raw)

    # =========================================================================
    # EXPERIMENT MANAGEMENT (Phase 025)
    # =========================================================================

    def archive_experiment(self, experiment_id: str) -> None:
        """Archive an experiment.

        Args:
            experiment_id: Experiment UUID.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Experiment not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.archive_experiment("xyz-456-uuid")
            ```
        """
        client = self._require_api_client()
        client.archive_experiment(experiment_id)

    def restore_experiment(self, experiment_id: str) -> Experiment:
        """Restore an archived experiment.

        Args:
            experiment_id: Experiment UUID.

        Returns:
            The restored ``Experiment``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Experiment not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            restored = ws.restore_experiment("xyz-456-uuid")
            ```
        """
        client = self._require_api_client()
        raw = client.restore_experiment(experiment_id)
        return Experiment.model_validate(raw)

    def duplicate_experiment(
        self,
        experiment_id: str,
        params: DuplicateExperimentParams,
    ) -> Experiment:
        """Duplicate an experiment.

        A name is required because the Mixpanel API returns an empty
        response body when duplicating without one.

        Args:
            experiment_id: Experiment UUID.
            params: Duplication parameters (``name`` is required).

        Returns:
            The newly created duplicate ``Experiment``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Experiment not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            dup = ws.duplicate_experiment(
                "xyz-456-uuid",
                DuplicateExperimentParams(name="Copy"),
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.duplicate_experiment(experiment_id, body)
        return Experiment.model_validate(raw)

    def list_erf_experiments(self) -> list[dict[str, Any]]:
        """List experiments in ERF (Experiment Results Framework) format.

        Returns:
            List of experiment dicts in ERF format.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            erf = ws.list_erf_experiments()
            ```
        """
        client = self._require_api_client()
        return client.list_erf_experiments()

    # =========================================================================
    # Annotations (Phase 026)
    # =========================================================================

    def list_annotations(
        self,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        tags: list[int] | None = None,
    ) -> list[Annotation]:
        """List timeline annotations for the project.

        Args:
            from_date: Start date filter (ISO format, e.g. ``"2026-01-01"``).
            to_date: End date filter (ISO format, e.g. ``"2026-03-31"``).
            tags: Tag IDs to filter by.

        Returns:
            List of ``Annotation`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            annotations = ws.list_annotations(from_date="2026-01-01")
            for ann in annotations:
                print(f"{ann.date}: {ann.description}")
            ```
        """
        client = self._require_api_client()
        raw_list = client.list_annotations(
            from_date=from_date, to_date=to_date, tags=tags
        )
        return [Annotation.model_validate(item) for item in raw_list]

    def create_annotation(self, params: CreateAnnotationParams) -> Annotation:
        """Create a new timeline annotation.

        Args:
            params: Annotation creation parameters (date, description required).

        Returns:
            The created ``Annotation``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ann = ws.create_annotation(
                CreateAnnotationParams(
                    date="2026-03-31", description="v2.5 release"
                )
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.create_annotation(body)
        return Annotation.model_validate(raw)

    def get_annotation(self, annotation_id: int) -> Annotation:
        """Get a single annotation by ID.

        Args:
            annotation_id: Annotation ID.

        Returns:
            The ``Annotation`` object.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Annotation not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ann = ws.get_annotation(42)
            print(ann.description)
            ```
        """
        client = self._require_api_client()
        raw = client.get_annotation(annotation_id)
        return Annotation.model_validate(raw)

    def update_annotation(
        self, annotation_id: int, params: UpdateAnnotationParams
    ) -> Annotation:
        """Update an annotation (PATCH semantics).

        Args:
            annotation_id: Annotation ID.
            params: Fields to update (description, tags).

        Returns:
            The updated ``Annotation``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Annotation not found (404) or validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ann = ws.update_annotation(
                42, UpdateAnnotationParams(description="Updated text")
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.update_annotation(annotation_id, body)
        return Annotation.model_validate(raw)

    def delete_annotation(self, annotation_id: int) -> None:
        """Delete an annotation.

        Args:
            annotation_id: Annotation ID.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Annotation not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_annotation(42)
            ```
        """
        client = self._require_api_client()
        client.delete_annotation(annotation_id)

    def list_annotation_tags(self) -> list[AnnotationTag]:
        """List annotation tags for the project.

        Returns:
            List of ``AnnotationTag`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            tags = ws.list_annotation_tags()
            for tag in tags:
                print(tag.name)
            ```
        """
        client = self._require_api_client()
        raw_list = client.list_annotation_tags()
        return [AnnotationTag.model_validate(item) for item in raw_list]

    def create_annotation_tag(self, params: CreateAnnotationTagParams) -> AnnotationTag:
        """Create a new annotation tag.

        Args:
            params: Tag creation parameters (name required).

        Returns:
            The created ``AnnotationTag``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            tag = ws.create_annotation_tag(
                CreateAnnotationTagParams(name="releases")
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.create_annotation_tag(body)
        return AnnotationTag.model_validate(raw)

    # =========================================================================
    # Webhook CRUD (Phase 026)
    # =========================================================================

    def list_webhooks(self) -> list[ProjectWebhook]:
        """List all webhooks for the current project.

        Returns:
            List of ``ProjectWebhook`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            webhooks = ws.list_webhooks()
            for wh in webhooks:
                print(f"{wh.name} -> {wh.url}")
            ```
        """
        client = self._require_api_client()
        raw_list = client.list_webhooks()
        return [ProjectWebhook.model_validate(item) for item in raw_list]

    def create_webhook(self, params: CreateWebhookParams) -> WebhookMutationResult:
        """Create a new webhook.

        Args:
            params: Webhook creation parameters.

        Returns:
            ``WebhookMutationResult`` with the new webhook's id and name.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            result = ws.create_webhook(
                CreateWebhookParams(name="Pipeline", url="https://example.com/hook")
            )
            print(result.id)
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.create_webhook(body)
        return WebhookMutationResult.model_validate(raw)

    def update_webhook(
        self, webhook_id: str, params: UpdateWebhookParams
    ) -> WebhookMutationResult:
        """Update an existing webhook.

        Args:
            webhook_id: Webhook UUID string.
            params: Fields to update (PATCH semantics).

        Returns:
            ``WebhookMutationResult`` with the updated webhook's id and name.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Webhook not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            result = ws.update_webhook(
                "wh-uuid-123",
                UpdateWebhookParams(name="Renamed Hook"),
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.update_webhook(webhook_id, body)
        return WebhookMutationResult.model_validate(raw)

    def delete_webhook(self, webhook_id: str) -> None:
        """Delete a webhook.

        Args:
            webhook_id: Webhook UUID string.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Webhook not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_webhook("wh-uuid-123")
            ```
        """
        client = self._require_api_client()
        client.delete_webhook(webhook_id)

    def test_webhook(self, params: WebhookTestParams) -> WebhookTestResult:
        """Test webhook connectivity.

        Args:
            params: Webhook test parameters (url is required).

        Returns:
            ``WebhookTestResult`` with success, status_code, and message.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            result = ws.test_webhook(
                WebhookTestParams(url="https://example.com/hook")
            )
            if result.success:
                print("Webhook is reachable")
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.test_webhook(body)
        return WebhookTestResult.model_validate(raw)

    # =========================================================================
    # Alert CRUD (Phase 026)
    # =========================================================================

    def list_alerts(
        self,
        *,
        bookmark_id: int | None = None,
        skip_user_filter: bool | None = None,
    ) -> list[CustomAlert]:
        """List custom alerts for the current project.

        Args:
            bookmark_id: Filter alerts by linked bookmark ID.
            skip_user_filter: If True, list alerts for all users.

        Returns:
            List of ``CustomAlert`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            alerts = ws.list_alerts()
            for alert in alerts:
                print(f"{alert.name} (paused={alert.paused})")
            ```
        """
        client = self._require_api_client()
        raw_list = client.list_alerts(
            bookmark_id=bookmark_id, skip_user_filter=skip_user_filter
        )
        return [CustomAlert.model_validate(item) for item in raw_list]

    def create_alert(self, params: CreateAlertParams) -> CustomAlert:
        """Create a new custom alert.

        Args:
            params: Alert creation parameters (bookmark_id, name, condition,
                frequency, paused, and subscriptions are required).

        Returns:
            The created ``CustomAlert``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            alert = ws.create_alert(
                CreateAlertParams(
                    bookmark_id=123,
                    name="Daily signups drop",
                    condition={"operator": "less_than", "value": 100},
                    frequency=86400,
                    paused=False,
                    subscriptions=[{"type": "email", "value": "team@co.com"}],
                )
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.create_alert(body)
        return CustomAlert.model_validate(raw)

    def get_alert(self, alert_id: int) -> CustomAlert:
        """Get a single custom alert by ID.

        Args:
            alert_id: Alert ID (integer).

        Returns:
            The ``CustomAlert`` object.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Alert not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            alert = ws.get_alert(42)
            print(alert.name)
            ```
        """
        client = self._require_api_client()
        raw = client.get_alert(alert_id)
        return CustomAlert.model_validate(raw)

    def update_alert(self, alert_id: int, params: UpdateAlertParams) -> CustomAlert:
        """Update a custom alert (PATCH semantics).

        Args:
            alert_id: Alert ID (integer).
            params: Fields to update.

        Returns:
            The updated ``CustomAlert``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Alert not found (404) or validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            alert = ws.update_alert(
                42, UpdateAlertParams(name="Renamed alert")
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.update_alert(alert_id, body)
        return CustomAlert.model_validate(raw)

    def delete_alert(self, alert_id: int) -> None:
        """Delete a custom alert.

        Args:
            alert_id: Alert ID (integer).

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Alert not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_alert(42)
            ```
        """
        client = self._require_api_client()
        client.delete_alert(alert_id)

    def bulk_delete_alerts(self, ids: list[int]) -> None:
        """Bulk-delete custom alerts.

        Args:
            ids: List of alert IDs to delete.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.bulk_delete_alerts([1, 2, 3])
            ```
        """
        client = self._require_api_client()
        client.bulk_delete_alerts(ids)

    def get_alert_count(self, *, alert_type: str | None = None) -> AlertCount:
        """Get alert count and limits.

        Args:
            alert_type: Optional filter by alert type.

        Returns:
            ``AlertCount`` with count, limit, and is_below_limit.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            count = ws.get_alert_count()
            if count.is_below_limit:
                print(f"{count.anomaly_alerts_count}/{count.alert_limit}")
            ```
        """
        client = self._require_api_client()
        raw = client.get_alert_count(alert_type=alert_type)
        return AlertCount.model_validate(raw)

    def get_alert_history(
        self,
        alert_id: int,
        *,
        page_size: int | None = None,
        next_cursor: str | None = None,
        previous_cursor: str | None = None,
    ) -> AlertHistoryResponse:
        """Get alert trigger history (paginated).

        Args:
            alert_id: Alert ID (integer).
            page_size: Number of results per page.
            next_cursor: Cursor for the next page.
            previous_cursor: Cursor for the previous page.

        Returns:
            ``AlertHistoryResponse`` with results and pagination metadata.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Alert not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            history = ws.get_alert_history(42, page_size=10)
            for entry in history.results:
                print(entry)
            ```
        """
        client = self._require_api_client()
        raw = client.get_alert_history(
            alert_id,
            page_size=page_size,
            next_cursor=next_cursor,
            previous_cursor=previous_cursor,
        )
        return AlertHistoryResponse.model_validate(raw)

    def test_alert(self, params: CreateAlertParams) -> dict[str, Any]:
        """Send a test alert notification.

        Args:
            params: Alert parameters for the test (same shape as create).

        Returns:
            Dictionary with test result status (opaque response).

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            result = ws.test_alert(
                CreateAlertParams(
                    bookmark_id=123, name="Test",
                    condition={}, frequency=86400,
                    paused=False, subscriptions=[],
                )
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        return client.test_alert(body)

    def get_alert_screenshot_url(self, gcs_key: str) -> AlertScreenshotResponse:
        """Get a signed URL for an alert screenshot.

        Args:
            gcs_key: GCS object key for the screenshot.

        Returns:
            ``AlertScreenshotResponse`` with the signed URL.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Screenshot not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            resp = ws.get_alert_screenshot_url("screenshots/abc.png")
            print(resp.signed_url)
            ```
        """
        client = self._require_api_client()
        raw = client.get_alert_screenshot_url(gcs_key)
        return AlertScreenshotResponse.model_validate(raw)

    def validate_alerts_for_bookmark(
        self, params: ValidateAlertsForBookmarkParams
    ) -> ValidateAlertsForBookmarkResponse:
        """Validate alerts against a bookmark configuration.

        Args:
            params: Validation parameters (alert_ids, bookmark_type,
                bookmark_params are required).

        Returns:
            ``ValidateAlertsForBookmarkResponse`` with per-alert validations
            and invalid count.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            resp = ws.validate_alerts_for_bookmark(
                ValidateAlertsForBookmarkParams(
                    alert_ids=[1, 2],
                    bookmark_type="insights",
                    bookmark_params={"event": "Signup"},
                )
            )
            if resp.invalid_count > 0:
                for v in resp.alert_validations:
                    if not v.valid:
                        print(f"{v.alert_name}: {v.reason}")
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.validate_alerts_for_bookmark(body)
        return ValidateAlertsForBookmarkResponse.model_validate(raw)

    # =============================================================================
    # Data Governance — Data Definitions / Lexicon (Phase 027)
    # =============================================================================

    def get_event_definitions(self, *, names: list[str]) -> list[EventDefinition]:
        """Get event definitions from Lexicon by name.

        Retrieves metadata (description, tags, visibility, etc.) for the
        specified events from the Mixpanel Lexicon.

        Args:
            names: List of event names to look up.

        Returns:
            List of ``EventDefinition`` objects for the requested events.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            defs = ws.get_event_definitions(names=["Signup", "Login"])
            for d in defs:
                print(f"{d.name}: {d.description}")
            ```
        """
        client = self._require_api_client()
        raw_list = client.get_event_definitions(names)
        return [EventDefinition.model_validate(x) for x in raw_list]

    def update_event_definition(
        self, event_name: str, params: UpdateEventDefinitionParams
    ) -> EventDefinition:
        """Update an event definition in Lexicon.

        Args:
            event_name: Name of the event to update.
            params: Fields to update (description, display_name,
                hidden, dropped, tags, owners).

        Returns:
            The updated ``EventDefinition``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Event not found (404) or validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            definition = ws.update_event_definition(
                "Signup",
                UpdateEventDefinitionParams(description="User signed up"),
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.update_event_definition(event_name, body)
        return EventDefinition.model_validate(raw)

    def delete_event_definition(self, event_name: str) -> None:
        """Delete an event definition from Lexicon.

        Args:
            event_name: Name of the event to delete.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Event not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_event_definition("OldEvent")
            ```
        """
        client = self._require_api_client()
        client.delete_event_definition(event_name)

    def bulk_update_event_definitions(
        self, params: BulkUpdateEventsParams
    ) -> list[EventDefinition]:
        """Bulk-update event definitions in Lexicon.

        Args:
            params: Bulk update parameters containing a list of event
                updates (name + fields to change).

        Returns:
            List of updated ``EventDefinition`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            defs = ws.bulk_update_event_definitions(
                BulkUpdateEventsParams(events=[
                    {"name": "Signup", "description": "User signed up"},
                    {"name": "Login", "hidden": True},
                ])
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw_list = client.bulk_update_event_definitions(body)
        return [EventDefinition.model_validate(x) for x in raw_list]

    def get_property_definitions(
        self,
        *,
        names: list[str],
        resource_type: str | None = None,
    ) -> list[PropertyDefinition]:
        """Get property definitions from Lexicon by name.

        Retrieves metadata (description, tags, visibility, etc.) for the
        specified properties from the Mixpanel Lexicon.

        Args:
            names: List of property names to look up.
            resource_type: Optional resource type filter (e.g. ``"event"``,
                ``"user"``, ``"group"``).

        Returns:
            List of ``PropertyDefinition`` objects for the requested properties.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            defs = ws.get_property_definitions(
                names=["plan_type", "country"],
                resource_type="event",
            )
            for d in defs:
                print(f"{d.name}: {d.description}")
            ```
        """
        client = self._require_api_client()
        raw_list = client.get_property_definitions(names, resource_type=resource_type)
        return [PropertyDefinition.model_validate(x) for x in raw_list]

    def update_property_definition(
        self, property_name: str, params: UpdatePropertyDefinitionParams
    ) -> PropertyDefinition:
        """Update a property definition in Lexicon.

        Args:
            property_name: Name of the property to update.
            params: Fields to update (description, display_name,
                hidden, dropped, tags, owners).

        Returns:
            The updated ``PropertyDefinition``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Property not found (404) or validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            definition = ws.update_property_definition(
                "plan_type",
                UpdatePropertyDefinitionParams(description="User plan tier"),
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.update_property_definition(property_name, body)
        return PropertyDefinition.model_validate(raw)

    def bulk_update_property_definitions(
        self, params: BulkUpdatePropertiesParams
    ) -> list[PropertyDefinition]:
        """Bulk-update property definitions in Lexicon.

        Args:
            params: Bulk update parameters containing a list of property
                updates (name + fields to change).

        Returns:
            List of updated ``PropertyDefinition`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            defs = ws.bulk_update_property_definitions(
                BulkUpdatePropertiesParams(properties=[
                    {"name": "plan_type", "description": "User plan tier"},
                    {"name": "country", "hidden": True},
                ])
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True, by_alias=True)
        raw_list = client.bulk_update_property_definitions(body)
        return [PropertyDefinition.model_validate(x) for x in raw_list]

    # ---- Tags ----

    def list_lexicon_tags(self) -> list[str]:
        """List all Lexicon tags.

        The API returns tag names as plain strings (not structured objects).

        Returns:
            List of tag name strings.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            tags = ws.list_lexicon_tags()
            for name in tags:
                print(name)
            ```
        """
        client = self._require_api_client()
        raw_list = client.list_lexicon_tags()
        return [str(x) for x in raw_list]

    def create_lexicon_tag(self, params: CreateTagParams) -> LexiconTag:
        """Create a new Lexicon tag.

        Args:
            params: Tag creation parameters (name is required).

        Returns:
            The created ``LexiconTag``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400) or tag already exists.
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            tag = ws.create_lexicon_tag(CreateTagParams(name="core-events"))
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.create_lexicon_tag(body)
        return LexiconTag.model_validate(raw)

    def update_lexicon_tag(self, tag_id: int, params: UpdateTagParams) -> LexiconTag:
        """Update a Lexicon tag.

        Args:
            tag_id: Tag ID (integer).
            params: Fields to update (e.g. name).

        Returns:
            The updated ``LexiconTag``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Tag not found (404) or validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            tag = ws.update_lexicon_tag(
                5, UpdateTagParams(name="renamed-tag")
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.update_lexicon_tag(tag_id, body)
        return LexiconTag.model_validate(raw)

    def delete_lexicon_tag(self, tag_name: str) -> None:
        """Delete a Lexicon tag by name.

        Args:
            tag_name: Name of the tag to delete.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Tag not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_lexicon_tag("deprecated-tag")
            ```
        """
        client = self._require_api_client()
        client.delete_lexicon_tag(tag_name)

    # =============================================================================
    # Data Governance — Drop Filters (Phase 027)
    # =============================================================================

    def list_drop_filters(self) -> list[DropFilter]:
        """List all drop filters.

        Returns:
            List of ``DropFilter`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            filters = ws.list_drop_filters()
            for f in filters:
                print(f"{f.event_name}: {f.status}")
            ```
        """
        client = self._require_api_client()
        raw_list = client.list_drop_filters()
        return [DropFilter.model_validate(x) for x in raw_list]

    def create_drop_filter(self, params: CreateDropFilterParams) -> list[DropFilter]:
        """Create a new drop filter.

        Args:
            params: Drop filter creation parameters.

        Returns:
            Full list of ``DropFilter`` objects after creation.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            filters = ws.create_drop_filter(
                CreateDropFilterParams(
                    event_name="Debug Event",
                    filter_type="events",
                )
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw_list = client.create_drop_filter(body)
        return [DropFilter.model_validate(x) for x in raw_list]

    def update_drop_filter(self, params: UpdateDropFilterParams) -> list[DropFilter]:
        """Update a drop filter.

        Args:
            params: Drop filter update parameters (must include the filter ID).

        Returns:
            Full list of ``DropFilter`` objects after update.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Filter not found (404) or validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            filters = ws.update_drop_filter(
                UpdateDropFilterParams(
                    id=42, event_name="Debug Event v2"
                )
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw_list = client.update_drop_filter(body)
        return [DropFilter.model_validate(x) for x in raw_list]

    def delete_drop_filter(self, drop_filter_id: int) -> list[DropFilter]:
        """Delete a drop filter.

        Args:
            drop_filter_id: Drop filter ID (integer).

        Returns:
            Full list of remaining ``DropFilter`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Filter not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            remaining = ws.delete_drop_filter(42)
            ```
        """
        client = self._require_api_client()
        raw_list = client.delete_drop_filter(drop_filter_id)
        return [DropFilter.model_validate(x) for x in raw_list]

    def get_drop_filter_limits(self) -> DropFilterLimitsResponse:
        """Get drop filter usage limits.

        Returns:
            ``DropFilterLimitsResponse`` with current count and maximum
            allowed drop filters.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            limits = ws.get_drop_filter_limits()
            print(f"{limits.count}/{limits.limit} filters used")
            ```
        """
        client = self._require_api_client()
        raw = client.get_drop_filter_limits()
        return DropFilterLimitsResponse.model_validate(raw)

    # =============================================================================
    # Data Governance — Custom Properties (Phase 027)
    # =============================================================================

    def list_custom_properties(self) -> list[CustomProperty]:
        """List all custom properties.

        Returns:
            List of ``CustomProperty`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            props = ws.list_custom_properties()
            for p in props:
                print(f"{p.name}: {p.definition}")
            ```
        """
        client = self._require_api_client()
        raw_list = client.list_custom_properties()
        return [CustomProperty.model_validate(x) for x in raw_list]

    def create_custom_property(
        self, params: CreateCustomPropertyParams
    ) -> CustomProperty:
        """Create a new custom property.

        Args:
            params: Custom property creation parameters (name,
                definition, resource_type are required).

        Returns:
            The created ``CustomProperty``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            prop = ws.create_custom_property(
                CreateCustomPropertyParams(
                    name="Full Name",
                    definition="...",
                    resource_type="event",
                )
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True, by_alias=True)
        raw = client.create_custom_property(body)
        return CustomProperty.model_validate(raw)

    def get_custom_property(self, property_id: str) -> CustomProperty:
        """Get a custom property by ID.

        Args:
            property_id: Custom property ID (string).

        Returns:
            The ``CustomProperty`` object.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Property not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            prop = ws.get_custom_property("abc123")
            print(prop.name)
            ```
        """
        client = self._require_api_client()
        raw = client.get_custom_property(property_id)
        return CustomProperty.model_validate(raw)

    def update_custom_property(
        self, property_id: str, params: UpdateCustomPropertyParams
    ) -> CustomProperty:
        """Update a custom property.

        Args:
            property_id: Custom property ID (string).
            params: Fields to update.

        Returns:
            The updated ``CustomProperty``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Property not found (404) or validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            prop = ws.update_custom_property(
                "abc123",
                UpdateCustomPropertyParams(name="Renamed Property"),
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True, by_alias=True)
        raw = client.update_custom_property(property_id, body)
        return CustomProperty.model_validate(raw)

    def delete_custom_property(self, property_id: str) -> None:
        """Delete a custom property.

        Args:
            property_id: Custom property ID (string).

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Property not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_custom_property("abc123")
            ```
        """
        client = self._require_api_client()
        client.delete_custom_property(property_id)

    def validate_custom_property(
        self, params: CreateCustomPropertyParams
    ) -> dict[str, Any]:
        """Validate a custom property definition without creating it.

        Args:
            params: Custom property parameters to validate.

        Returns:
            Validation result as a raw dictionary.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            result = ws.validate_custom_property(
                CreateCustomPropertyParams(
                    name="Full Name",
                    definition="...",
                    resource_type="event",
                )
            )
            print(result)
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True, by_alias=True)
        return client.validate_custom_property(body)

    # =============================================================================
    # Data Governance — Lookup Tables (Phase 027)
    # =============================================================================

    def list_lookup_tables(
        self, *, data_group_id: int | None = None
    ) -> list[LookupTable]:
        """List lookup tables.

        Args:
            data_group_id: Optional filter by data group ID.

        Returns:
            List of ``LookupTable`` objects.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            tables = ws.list_lookup_tables()
            for t in tables:
                print(f"{t.name}: {t.row_count} rows")
            ```
        """
        client = self._require_api_client()
        raw_list = client.list_lookup_tables(data_group_id=data_group_id)
        return [LookupTable.model_validate(x) for x in raw_list]

    def upload_lookup_table(self, params: UploadLookupTableParams) -> dict[str, Any]:
        """Upload a CSV file as a new lookup table.

        Performs a 3-step upload process:
        1. Obtains a signed upload URL from the API.
        2. Uploads the CSV file to the signed URL.
        3. Registers the lookup table with the uploaded data.

        Args:
            params: Upload parameters including ``name``, ``file_path``
                (path to the CSV file), and optional ``data_group_id``.

        Returns:
            Registration response dict (contains ``id`` of the created table).

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400) or file not found.
            ServerError: Server-side errors (5xx).
            FileNotFoundError: If the CSV file does not exist.

        Example:
            ```python
            ws = Workspace()
            table = ws.upload_lookup_table(
                UploadLookupTableParams(
                    name="Country Codes",
                    file_path="/path/to/countries.csv",
                )
            )
            print(f"Created: {table.name}")
            ```
        """
        client = self._require_api_client()

        # Step 1: Get signed upload URL
        url_info = client.get_lookup_upload_url()

        # Step 2: Read and upload the CSV file
        csv_bytes = Path(params.file_path).read_bytes()
        client.upload_to_signed_url(url_info["url"], csv_bytes)

        # Step 3: Register the lookup table
        form_data: dict[str, str] = {
            "name": params.name,
            "path": url_info["path"],
            "key": url_info["key"],
        }
        if params.data_group_id is not None:
            form_data["data-group-id"] = str(params.data_group_id)

        return client.register_lookup_table(form_data)

    def mark_lookup_table_ready(
        self, params: MarkLookupTableReadyParams
    ) -> LookupTable:
        """Mark a lookup table as ready after upload.

        Args:
            params: Parameters including ``name``, ``key``, and optional
                ``data_group_id``.

        Returns:
            The updated ``LookupTable``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            table = ws.mark_lookup_table_ready(
                MarkLookupTableReadyParams(
                    name="Country Codes",
                    key="uploads/abc123.csv",
                )
            )
            ```
        """
        client = self._require_api_client()
        form_data: dict[str, str] = {
            "name": params.name,
            "key": params.key,
        }
        if params.data_group_id is not None:
            form_data["data-group-id"] = str(params.data_group_id)

        raw = client.mark_lookup_table_ready(form_data)
        return LookupTable.model_validate(raw)

    def get_lookup_upload_url(
        self, content_type: str = "text/csv"
    ) -> LookupTableUploadUrl:
        """Get a signed URL for uploading lookup table data.

        Args:
            content_type: MIME type of the file to upload
                (default: ``"text/csv"``).

        Returns:
            ``LookupTableUploadUrl`` with the signed URL, path, and key.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            url_info = ws.get_lookup_upload_url()
            print(url_info.url)
            ```
        """
        client = self._require_api_client()
        raw = client.get_lookup_upload_url(content_type)
        return LookupTableUploadUrl.model_validate(raw)

    def get_lookup_upload_status(self, upload_id: str) -> dict[str, Any]:
        """Get the processing status of a lookup table upload.

        Args:
            upload_id: Upload ID returned from the upload process.

        Returns:
            Raw status dictionary with processing details.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Upload not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            status = ws.get_lookup_upload_status("upload-abc123")
            print(status["state"])
            ```
        """
        client = self._require_api_client()
        return client.get_lookup_upload_status(upload_id)

    def update_lookup_table(
        self, data_group_id: int, params: UpdateLookupTableParams
    ) -> LookupTable:
        """Update a lookup table.

        Args:
            data_group_id: Data group ID of the lookup table.
            params: Fields to update.

        Returns:
            The updated ``LookupTable``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Table not found (404) or validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            table = ws.update_lookup_table(
                123,
                UpdateLookupTableParams(name="Renamed Table"),
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.update_lookup_table(data_group_id, body)
        return LookupTable.model_validate(raw)

    def delete_lookup_tables(self, data_group_ids: list[int]) -> None:
        """Delete one or more lookup tables.

        Args:
            data_group_ids: List of data group IDs to delete.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_lookup_tables([123, 456])
            ```
        """
        client = self._require_api_client()
        client.delete_lookup_tables(data_group_ids)

    def download_lookup_table(
        self,
        data_group_id: int,
        *,
        file_name: str | None = None,
        limit: int | None = None,
    ) -> bytes:
        """Download lookup table data as raw bytes (CSV).

        Args:
            data_group_id: Data group ID of the lookup table.
            file_name: Optional file name filter.
            limit: Optional row limit.

        Returns:
            Raw CSV bytes of the lookup table data.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Table not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            csv_data = ws.download_lookup_table(123)
            Path("output.csv").write_bytes(csv_data)
            ```
        """
        client = self._require_api_client()
        return client.download_lookup_table(
            data_group_id, file_name=file_name, limit=limit
        )

    def get_lookup_download_url(self, data_group_id: int) -> str:
        """Get a signed download URL for a lookup table.

        Args:
            data_group_id: Data group ID of the lookup table.

        Returns:
            Signed URL string for downloading the lookup table data.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Table not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            url = ws.get_lookup_download_url(123)
            print(url)
            ```
        """
        client = self._require_api_client()
        return client.get_lookup_download_url(data_group_id)

    # =============================================================================
    # Data Governance — Custom Events (Phase 027)
    # =============================================================================

    def list_custom_events(self) -> list[EventDefinition]:
        """List all custom events.

        Returns:
            List of ``EventDefinition`` objects for custom events.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            events = ws.list_custom_events()
            for e in events:
                print(e.name)
            ```
        """
        client = self._require_api_client()
        raw_list = client.list_custom_events()
        return [EventDefinition.model_validate(x) for x in raw_list]

    def update_custom_event(
        self, event_name: str, params: UpdateEventDefinitionParams
    ) -> EventDefinition:
        """Update a custom event definition.

        Args:
            event_name: Name of the custom event to update.
            params: Fields to update (description, display_name, etc.).

        Returns:
            The updated ``EventDefinition``.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Event not found (404) or validation error (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            event = ws.update_custom_event(
                "My Custom Event",
                UpdateEventDefinitionParams(description="Updated desc"),
            )
            ```
        """
        client = self._require_api_client()
        body = params.model_dump(exclude_none=True)
        raw = client.update_custom_event(event_name, body)
        return EventDefinition.model_validate(raw)

    def delete_custom_event(self, event_name: str) -> None:
        """Delete a custom event.

        Args:
            event_name: Name of the custom event to delete.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Event not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            ws.delete_custom_event("My Custom Event")
            ```
        """
        client = self._require_api_client()
        client.delete_custom_event(event_name)

    # =============================================================================
    # Data Governance — Tracking & History (Phase 027)
    # =============================================================================

    def get_tracking_metadata(self, event_name: str) -> dict[str, Any]:
        """Get tracking metadata for an event.

        Retrieves information about how an event is being tracked
        (sources, SDKs, volume, etc.).

        Args:
            event_name: Name of the event.

        Returns:
            Raw tracking metadata dictionary.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Event not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            metadata = ws.get_tracking_metadata("Signup")
            print(metadata)
            ```
        """
        client = self._require_api_client()
        return client.get_tracking_metadata(event_name)

    def get_event_history(self, event_name: str) -> list[dict[str, Any]]:
        """Get change history for an event definition.

        Args:
            event_name: Name of the event.

        Returns:
            List of history entries (raw dictionaries) showing changes
            to the event definition over time.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Event not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            history = ws.get_event_history("Signup")
            for entry in history:
                print(f"{entry['timestamp']}: {entry['action']}")
            ```
        """
        client = self._require_api_client()
        return client.get_event_history(event_name)

    def get_property_history(
        self, property_name: str, entity_type: str
    ) -> list[dict[str, Any]]:
        """Get change history for a property definition.

        Args:
            property_name: Name of the property.
            entity_type: Entity type (e.g. ``"event"``, ``"user"``,
                ``"group"``).

        Returns:
            List of history entries (raw dictionaries) showing changes
            to the property definition over time.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            QueryError: Property not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            history = ws.get_property_history("plan_type", "event")
            for entry in history:
                print(f"{entry['timestamp']}: {entry['action']}")
            ```
        """
        client = self._require_api_client()
        return client.get_property_history(property_name, entity_type)

    # ---- Export ----

    def export_lexicon(
        self, *, export_types: list[str] | None = None
    ) -> dict[str, Any]:
        """Export Lexicon data definitions.

        Exports event and property definitions from Lexicon, optionally
        filtered by type.

        Args:
            export_types: Optional list of types to export (e.g.
                ``["events", "event_properties", "user_properties"]``).

        Returns:
            Raw export dictionary containing the exported definitions.

        Raises:
            ConfigError: If credentials are not available.
            AuthenticationError: Invalid credentials (401).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            ws = Workspace()
            export = ws.export_lexicon(export_types=["events"])
            print(len(export.get("events", [])))
            ```
        """
        client = self._require_api_client()
        return client.export_lexicon(export_types=export_types)
