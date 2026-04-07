"""Mixpanel /me API types, caching, and service layer.

Provides models for the ``/api/app/me`` response along with a disk-based
cache (``MeCache``) and orchestration service (``MeService``) for project
and workspace discovery.

Types use ``extra="allow"`` for forward compatibility with API changes.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from mixpanel_data.exceptions import ConfigError

if TYPE_CHECKING:
    from mixpanel_data._internal.api_client import MixpanelAPIClient

logger = logging.getLogger(__name__)


class MeOrgInfo(BaseModel):
    """Organization information within a /me response.

    Uses ``extra="allow"`` for forward compatibility — unknown fields
    from the API are preserved in ``model_extra``.

    Args:
        id: Organization ID.
        name: Organization display name.
        role: User's role in this organization (optional).
        permissions: User's permissions in this organization (optional).

    Example:
        ```python
        org = MeOrgInfo(id=100, name="Acme Corp", role="admin")
        ```
    """

    model_config = ConfigDict(extra="allow")

    id: int
    """Organization ID."""

    name: str
    """Organization display name."""

    role: str | None = None
    """User's role in this organization."""

    permissions: list[str] | None = None
    """User's permissions in this organization."""


class MeProjectInfo(BaseModel):
    """Project information within a /me response.

    Uses ``extra="allow"`` for forward compatibility.

    Args:
        name: Project display name.
        organization_id: Owning organization ID.
        timezone: Project timezone (optional).
        has_workspaces: Whether project uses workspaces (optional).
        domain: Mixpanel domain for the project's cluster (optional).
        type: Project type, e.g. "PROJECT" or "ROLLUP" (optional).

    Example:
        ```python
        project = MeProjectInfo(
            name="AI Demo",
            organization_id=100,
            timezone="US/Pacific",
        )
        ```
    """

    model_config = ConfigDict(extra="allow")

    name: str
    """Project display name."""

    organization_id: int
    """Owning organization ID."""

    timezone: str | None = None
    """Project timezone."""

    has_workspaces: bool | None = None
    """Whether project uses workspaces."""

    domain: str | None = None
    """Mixpanel domain for the project's cluster."""

    type: str | None = None
    """Project type (e.g., 'PROJECT', 'ROLLUP')."""


class MeWorkspaceInfo(BaseModel):
    """Workspace information within a /me response.

    Uses ``extra="allow"`` for forward compatibility.

    Args:
        id: Workspace ID.
        name: Workspace display name.
        project_id: Parent project ID.
        is_default: Whether this is the project's default workspace (optional).
        is_global: Whether this is a global workspace (optional).
        is_restricted: Whether access is restricted (optional).
        is_visible: Whether workspace is visible (optional).
        description: Workspace description (optional).
        creator_name: Who created the workspace (optional).

    Example:
        ```python
        ws = MeWorkspaceInfo(
            id=3448413, name="Default", project_id=3713224, is_default=True,
        )
        ```
    """

    model_config = ConfigDict(extra="allow")

    id: int
    """Workspace ID."""

    name: str
    """Workspace display name."""

    project_id: int
    """Parent project ID."""

    is_default: bool | None = None
    """Whether this is the project's default workspace."""

    is_global: bool | None = None
    """Whether this is a global workspace."""

    is_restricted: bool | None = None
    """Whether access is restricted."""

    is_visible: bool | None = None
    """Whether workspace is visible."""

    description: str | None = None
    """Workspace description."""

    creator_name: str | None = None
    """Who created the workspace."""


class MeResponse(BaseModel):
    """Cached response from the Mixpanel /me API.

    All fields are optional for forward-compatible deserialization.
    Unknown fields are preserved via ``extra="allow"``.

    Args:
        user_id: Authenticated user's ID (optional).
        user_email: User's email (optional).
        user_name: User's display name (optional).
        organizations: Accessible organizations, keyed by org ID (optional).
        projects: Accessible projects, keyed by project ID (optional).
        workspaces: Accessible workspaces, keyed by workspace ID (optional).
        cached_at: When this response was cached (added by client, optional).
        cached_region: Which region this cache is for (added by client, optional).

    Example:
        ```python
        me = MeResponse(
            user_id=42,
            user_email="user@example.com",
            projects={"123": MeProjectInfo(name="My Project", organization_id=1)},
        )
        ```
    """

    model_config = ConfigDict(extra="allow")

    user_id: int | None = None
    """Authenticated user's ID."""

    user_email: str | None = None
    """User's email."""

    user_name: str | None = None
    """User's display name."""

    organizations: dict[str, MeOrgInfo] = {}
    """Accessible organizations, keyed by org ID."""

    projects: dict[str, MeProjectInfo] = {}
    """Accessible projects, keyed by project ID."""

    workspaces: dict[str, MeWorkspaceInfo] = {}
    """Accessible workspaces, keyed by workspace ID."""

    cached_at: float | None = None
    """Unix timestamp when this response was cached (added by caching layer)."""

    cached_region: str | None = None
    """Which region this cache is for (added by caching layer)."""


# Default cache TTL: 24 hours
_DEFAULT_TTL_SECONDS = 86400


class MeCache:
    """Disk-based cache for /me API responses.

    Stores responses as JSON files at ``{storage_dir}/me_{region}.json``
    with configurable TTL. Files are created with ``0o600`` permissions.

    Args:
        storage_dir: Directory for cache files. Defaults to ``~/.mp/oauth/``.
        ttl_seconds: Cache time-to-live in seconds. Default: 86400 (24h).

    Example:
        ```python
        cache = MeCache()
        cache.put("us", me_response)
        cached = cache.get("us")  # Returns MeResponse or None
        cache.invalidate("us")
        ```
    """

    def __init__(
        self,
        storage_dir: Path | None = None,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        """Initialize MeCache.

        Args:
            storage_dir: Override cache directory. Defaults to ``~/.mp/oauth/``.
            ttl_seconds: Cache TTL in seconds. Default: 86400 (24 hours).
        """
        if storage_dir is not None:
            self._storage_dir = storage_dir
        else:
            self._storage_dir = Path.home() / ".mp" / "oauth"
        self._ttl_seconds = ttl_seconds

    def _cache_path(self, region: str) -> Path:
        """Return the cache file path for a region.

        Args:
            region: Data residency region (us, eu, in).

        Returns:
            Path to the cache file.
        """
        return self._storage_dir / f"me_{region}.json"

    def get(self, region: str) -> MeResponse | None:
        """Retrieve a cached /me response for a region.

        Returns ``None`` if no cache exists, the cache is expired,
        or the cache file is corrupted.

        Args:
            region: Data residency region (us, eu, in).

        Returns:
            Cached MeResponse or None if cache miss/expired/corrupted.

        Example:
            ```python
            cache = MeCache()
            me = cache.get("us")
            if me is None:
                me = fetch_from_api()
                cache.put("us", me)
            ```
        """
        path = self._cache_path(region)
        if not path.exists():
            return None

        try:
            raw = path.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(raw)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("Corrupted cache file %s: %s", path, e)
            return None

        # Check TTL
        cached_at = data.get("cached_at")
        if cached_at is not None and isinstance(cached_at, (int, float)):
            age = time.time() - cached_at
            if age > self._ttl_seconds:
                logger.debug("Cache expired for region '%s' (age=%.0fs)", region, age)
                return None

        try:
            return MeResponse.model_validate(data)
        except Exception as e:
            logger.debug("Failed to parse cached /me response: %s", e)
            return None

    def put(self, region: str, response: MeResponse) -> None:
        """Store a /me response in the cache.

        Adds ``cached_at`` and ``cached_region`` metadata before writing.
        Creates the storage directory if it doesn't exist.
        Sets file permissions to ``0o600`` (owner-only read/write).

        Args:
            region: Data residency region (us, eu, in).
            response: MeResponse to cache.

        Example:
            ```python
            cache = MeCache()
            cache.put("us", me_response)
            ```
        """
        self._storage_dir.mkdir(parents=True, exist_ok=True)

        # Add cache metadata
        data = response.model_dump(mode="json")
        data["cached_at"] = time.time()
        data["cached_region"] = region

        path = self._cache_path(region)
        # Write atomically via temp file
        tmp_path = path.with_suffix(".tmp")
        try:
            tmp_path.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
            # Set permissions before rename
            os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
            tmp_path.replace(path)
        except OSError:
            # Clean up temp file on failure
            tmp_path.unlink(missing_ok=True)
            raise

    def invalidate(self, region: str) -> None:
        """Remove the cached /me response for a specific region.

        Args:
            region: Data residency region to invalidate.

        Example:
            ```python
            cache = MeCache()
            cache.invalidate("us")
            ```
        """
        path = self._cache_path(region)
        path.unlink(missing_ok=True)

    def invalidate_all(self) -> None:
        """Remove all cached /me responses.

        Example:
            ```python
            cache = MeCache()
            cache.invalidate_all()
            ```
        """
        for region in ("us", "eu", "in"):
            self.invalidate(region)


class MeService:
    """Orchestration service for /me API calls with caching.

    Wraps ``MixpanelAPIClient.me()`` with a ``MeCache`` layer and
    provides convenience methods for project and workspace discovery.

    Args:
        api_client: The API client for making /me requests.
        cache: Disk-based cache for /me responses.
        region: Data residency region (us, eu, in).

    Example:
        ```python
        svc = MeService(api_client, MeCache(), "us")
        me = svc.fetch()
        projects = svc.list_projects()
        ```
    """

    def __init__(
        self,
        api_client: MixpanelAPIClient,
        cache: MeCache,
        region: str,
    ) -> None:
        """Initialize MeService.

        Args:
            api_client: The API client for making /me requests.
            cache: Disk-based cache for /me responses.
            region: Data residency region (us, eu, in).
        """
        self._api_client = api_client
        self._cache = cache
        self._region = region
        self._cached_response: MeResponse | None = None

    def fetch(self, *, force_refresh: bool = False) -> MeResponse:
        """Fetch the /me response, using cache when available.

        Checks the in-memory cache first, then disk cache, then calls
        the API. Results are stored in both memory and disk caches.

        If the API returns 401 or 403, raises ``ConfigError`` with a
        clear message directing the user to specify ``--project`` explicitly.

        Args:
            force_refresh: If True, bypass all caches and call the API.

        Returns:
            The /me response (from cache or API).

        Raises:
            ConfigError: If the API returns 401/403, indicating the
                credentials lack permission for /me discovery.

        Example:
            ```python
            svc = MeService(api_client, cache, "us")
            me = svc.fetch()
            print(me.user_email)

            me2 = svc.fetch(force_refresh=True)  # bypasses cache
            ```
        """
        # Check in-memory cache first
        if not force_refresh and self._cached_response is not None:
            return self._cached_response

        # Check disk cache
        if not force_refresh:
            cached = self._cache.get(self._region)
            if cached is not None:
                self._cached_response = cached
                return cached

        # Call API
        try:
            raw = self._api_client.me()
        except Exception as exc:
            # Handle 401/403 from the API
            from mixpanel_data.exceptions import AuthenticationError, QueryError

            if isinstance(exc, AuthenticationError):
                raise ConfigError(
                    "Credentials lack permission for /me discovery. "
                    "Specify --project explicitly or use credentials with "
                    "/me access.",
                    details={"status_code": 401},
                ) from exc
            if isinstance(exc, QueryError) and exc.status_code == 403:
                raise ConfigError(
                    "Credentials lack permission for /me discovery. "
                    "Specify --project explicitly or use credentials with "
                    "/me access.",
                    details={"status_code": 403},
                ) from exc
            raise

        response = MeResponse.model_validate(raw)

        # Store in caches
        self._cache.put(self._region, response)
        self._cached_response = response

        return response

    def list_projects(self) -> list[tuple[str, MeProjectInfo]]:
        """List all accessible projects from the cached /me response.

        Calls ``fetch()`` if no cached response is available.

        Returns:
            List of ``(project_id, MeProjectInfo)`` tuples, sorted by
            project name.

        Example:
            ```python
            svc = MeService(api_client, cache, "us")
            for pid, info in svc.list_projects():
                print(f"{pid}: {info.name}")
            ```
        """
        me = self.fetch()
        items = list(me.projects.items())
        items.sort(key=lambda x: x[1].name.lower())
        return items

    def find_project(self, project_id: str) -> MeProjectInfo | None:
        """Find a specific project by ID from the cached /me response.

        Calls ``fetch()`` if no cached response is available.

        Args:
            project_id: The project ID to search for.

        Returns:
            ``MeProjectInfo`` if found, ``None`` otherwise.

        Example:
            ```python
            svc = MeService(api_client, cache, "us")
            info = svc.find_project("3713224")
            if info:
                print(info.name)
            ```
        """
        me = self.fetch()
        return me.projects.get(project_id)

    def list_workspaces(self, project_id: str | None = None) -> list[MeWorkspaceInfo]:
        """List workspaces, optionally filtered by project ID.

        Calls ``fetch()`` if no cached response is available.

        Args:
            project_id: If provided, only return workspaces for this project.
                If None, returns all workspaces.

        Returns:
            List of ``MeWorkspaceInfo`` objects, sorted by name.

        Example:
            ```python
            svc = MeService(api_client, cache, "us")
            for ws in svc.list_workspaces(project_id="3713224"):
                print(f"{ws.id}: {ws.name}")
            ```
        """
        me = self.fetch()
        workspaces = list(me.workspaces.values())

        if project_id is not None:
            pid_int = int(project_id)
            workspaces = [ws for ws in workspaces if ws.project_id == pid_int]

        workspaces.sort(key=lambda ws: ws.name.lower())
        return workspaces

    def find_default_workspace(self, project_id: str) -> MeWorkspaceInfo | None:
        """Find the default workspace for a project.

        Searches through workspaces with ``is_default=True`` for the given
        project. If no explicit default is found, returns ``None``.

        Args:
            project_id: The project ID to find the default workspace for.

        Returns:
            ``MeWorkspaceInfo`` for the default workspace, or ``None``
            if no default workspace exists.

        Example:
            ```python
            svc = MeService(api_client, cache, "us")
            default_ws = svc.find_default_workspace("3713224")
            if default_ws:
                print(f"Default: {default_ws.name} (id={default_ws.id})")
            ```
        """
        workspaces = self.list_workspaces(project_id=project_id)
        for ws in workspaces:
            if ws.is_default is True:
                return ws
        return None
