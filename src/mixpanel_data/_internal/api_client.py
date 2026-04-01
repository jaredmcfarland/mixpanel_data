"""Mixpanel API Client.

Low-level HTTP client for all Mixpanel APIs. Handles:
- Authentication via HTTP Basic auth (service accounts) or OAuth 2.0 Bearer tokens
- Regional endpoint routing (US, EU, India)
- Automatic rate limit handling with exponential backoff
- Streaming JSONL parsing for large exports

This is a private implementation detail. Users should use the Workspace class
or service layer instead of accessing this module directly.
"""

from __future__ import annotations

import base64
import json
import logging
import random
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

import httpx

from mixpanel_data._internal.config import Credentials
from mixpanel_data.exceptions import (
    AuthenticationError,
    JQLSyntaxError,
    MixpanelDataError,
    QueryError,
    RateLimitError,
    ServerError,
    WorkspaceScopeError,
)
from mixpanel_data.types import ProfilePageResult, PublicWorkspace

if TYPE_CHECKING:
    from types import TracebackType

logger = logging.getLogger(__name__)


def _iter_jsonl_lines(response: httpx.Response) -> Iterator[str]:
    """Iterate over JSONL lines from a streaming response with proper buffering.

    The httpx iter_lines() method can incorrectly split lines at chunk boundaries,
    especially with gzip-compressed responses. This function uses iter_bytes() with
    manual buffering to handle incomplete lines correctly.

    Args:
        response: An httpx streaming Response object (from client.stream()).

    Yields:
        Complete lines from the response, stripped of trailing newlines.
        Empty lines are skipped.

    Example:
        ```python
        with client.stream("GET", url) as response:
            for line in _iter_jsonl_lines(response):
                event = json.loads(line)
        ```
    """
    # Use bytearray for efficient in-place buffer extension (bytes would copy on each +=)
    buffer = bytearray()
    for chunk in response.iter_bytes():
        buffer.extend(chunk)
        # Extract complete lines from buffer
        while True:
            newline_pos = buffer.find(b"\n")
            if newline_pos == -1:
                break
            line = bytes(buffer[:newline_pos])
            del buffer[: newline_pos + 1]
            line_str = line.decode("utf-8", errors="replace").strip()
            if line_str:
                yield line_str
    # Handle any remaining data in buffer (final line without trailing newline)
    if buffer:
        line_str = bytes(buffer).decode("utf-8", errors="replace").strip()
        if line_str:
            yield line_str


# Regional endpoint configuration
# Each region has separate URLs for query APIs and export/data APIs
ENDPOINTS: dict[str, dict[str, str]] = {
    "us": {
        "query": "https://mixpanel.com/api/query",
        "export": "https://data.mixpanel.com/api/2.0",
        "engage": "https://mixpanel.com/api/2.0/engage",
        "app": "https://mixpanel.com/api/app",
    },
    "eu": {
        "query": "https://eu.mixpanel.com/api/query",
        "export": "https://data-eu.mixpanel.com/api/2.0",
        "engage": "https://eu.mixpanel.com/api/2.0/engage",
        "app": "https://eu.mixpanel.com/api/app",
    },
    "in": {
        "query": "https://in.mixpanel.com/api/query",
        "export": "https://data-in.mixpanel.com/api/2.0",
        "engage": "https://in.mixpanel.com/api/2.0/engage",
        "app": "https://in.mixpanel.com/api/app",
    },
}


class MixpanelAPIClient:
    """Low-level HTTP client for Mixpanel APIs.

    Handles authentication, rate limiting, and response parsing. Most users
    won't use this directly—they'll use the Workspace class instead.

    Example:
        ```python
        from mixpanel_data._internal.config import ConfigManager
        from mixpanel_data._internal.api_client import MixpanelAPIClient

        config = ConfigManager()
        credentials = config.resolve_credentials()

        with MixpanelAPIClient(credentials) as client:
            events = client.get_events()
            print(events)
        ```
    """

    def __init__(
        self,
        credentials: Credentials,
        *,
        timeout: float = 120.0,
        export_timeout: float = 600.0,
        max_retries: int = 3,
        _transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Initialize the API client.

        Args:
            credentials: Immutable authentication credentials.
            timeout: Request timeout in seconds for regular requests.
            export_timeout: Request timeout for export operations.
            max_retries: Maximum retry attempts for rate-limited requests.
            _transport: Internal parameter for testing with MockTransport.
        """
        self._credentials = credentials
        self._timeout = timeout
        self._export_timeout = export_timeout
        self._max_retries = max_retries
        self._client: httpx.Client | None = None
        self._transport = _transport
        self._workspace_id: int | None = None
        self._cached_workspace_id: int | None = None

    def _get_auth_header(self) -> str:
        """Generate HTTP Basic auth header value.

        Returns:
            Base64-encoded "username:secret" prefixed with "Basic ".
        """
        secret = self._credentials.secret.get_secret_value()
        auth_string = f"{self._credentials.username}:{secret}"
        encoded = base64.b64encode(auth_string.encode()).decode()
        return f"Basic {encoded}"

    def _build_url(self, api_type: str, path: str) -> str:
        """Build full URL for the given API type and path.

        Args:
            api_type: One of "query", "export", "engage", or "app".
            path: API endpoint path (e.g., "/segmentation").

        Returns:
            Full URL for the endpoint.
        """
        region = self._credentials.region
        base = ENDPOINTS[region][api_type]
        # Ensure path starts with /
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"

    def _ensure_client(self) -> httpx.Client:
        """Ensure HTTP client is initialized.

        Returns:
            The httpx.Client instance.
        """
        if self._client is None:
            self._client = httpx.Client(
                timeout=self._timeout,
                transport=self._transport,
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> MixpanelAPIClient:
        """Enter context manager."""
        self._ensure_client()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context manager, closing client."""
        self.close()

    def _handle_response(
        self,
        response: httpx.Response,
        *,
        request_method: str | None = None,
        request_url: str | None = None,
        request_params: dict[str, Any] | None = None,
        request_body: dict[str, Any] | None = None,
        script: str | None = None,
    ) -> Any:
        """Handle API response, raising appropriate exceptions with full context.

        All exceptions include request/response context for debugging and
        autonomous recovery by AI agents.

        Status code handling:
            - 200-299: Parse and return JSON response
            - 400: QueryError with error message from response body
            - 401: AuthenticationError (invalid credentials)
            - 403: QueryError (permission denied)
            - 404: QueryError (resource not found)
            - 412: JQLSyntaxError (JQL script errors with parsed details)
            - 5xx: ServerError with status code and error details

        Note: 429 (rate limit) is handled separately in _request() with retry logic.

        Args:
            response: The HTTP response to handle.
            request_method: HTTP method used (GET, POST).
            request_url: Full request URL.
            request_params: Query parameters sent.
            request_body: Request body sent (for POST).
            script: Optional JQL script for error context (used for 412 errors).

        Returns:
            Parsed JSON response for successful requests.

        Raises:
            AuthenticationError: On 401 response.
            QueryError: On 400 response.
            JQLSyntaxError: On 412 response (JQL script errors).
            ServerError: On 5xx response.
        """
        # Parse response body for error details
        response_body: str | dict[str, Any] | None = None
        try:
            response_body = response.json()
        except json.JSONDecodeError:
            response_body = response.text[:500] if response.text else None

        if response.status_code == 401:
            raise AuthenticationError(
                "Invalid credentials. Check username, secret, and project_id.",
                status_code=response.status_code,
                response_body=response_body,
                request_method=request_method,
                request_url=request_url,
                request_params=request_params,
            )
        if response.status_code == 403:
            error_msg = "Permission denied"
            if isinstance(response_body, dict):
                error_msg = response_body.get("error", "Permission denied")
            elif isinstance(response_body, str):
                error_msg = response_body[:200] or "Permission denied"
            raise QueryError(
                error_msg,
                status_code=response.status_code,
                response_body=response_body,
                request_method=request_method,
                request_url=request_url,
                request_params=request_params,
                request_body=request_body,
            )
        if response.status_code == 400:
            error_msg = "Unknown error"
            if isinstance(response_body, dict):
                error_msg = response_body.get("error", "Unknown error")
            elif isinstance(response_body, str):
                error_msg = response_body[:200]
            raise QueryError(
                error_msg,
                status_code=response.status_code,
                response_body=response_body,
                request_method=request_method,
                request_url=request_url,
                request_params=request_params,
                request_body=request_body,
            )
        if response.status_code == 404:
            error_msg = "Resource not found"
            if isinstance(response_body, dict):
                error_msg = response_body.get("error", "Resource not found")
            elif isinstance(response_body, str):
                error_msg = response_body[:200] or "Resource not found"
            raise QueryError(
                error_msg,
                status_code=response.status_code,
                response_body=response_body,
                request_method=request_method,
                request_url=request_url,
                request_params=request_params,
                request_body=request_body,
            )
        if response.status_code == 412:
            # JQL script errors return 412 Precondition Failed
            if isinstance(response_body, dict):
                raw_error = response_body.get("error", "Unknown JQL error")
                request_path = response_body.get("request")
                raise JQLSyntaxError(
                    raw_error=raw_error,
                    script=script,
                    request_path=request_path,
                )
            else:
                raise QueryError(
                    f"JQL failed: {response_body[:200] if response_body else 'Unknown error'}",
                    status_code=response.status_code,
                    response_body=response_body,
                    request_method=request_method,
                    request_url=request_url,
                    request_body=request_body,
                )
        if response.status_code >= 500:
            # Extract error message from response body if available
            error_msg = f"Server error: {response.status_code}"
            if isinstance(response_body, dict) and "error" in response_body:
                error_msg = f"Server error: {response_body['error']}"
            elif isinstance(response_body, str) and response_body:
                error_msg = f"Server error: {response_body[:200]}"

            raise ServerError(
                error_msg,
                status_code=response.status_code,
                response_body=response_body,
                request_method=request_method,
                request_url=request_url,
                request_params=request_params,
                request_body=request_body,
            )
        response.raise_for_status()
        if response_body is not None and isinstance(response_body, dict | list):
            return response_body
        return response.json()

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter.

        Uses exponential backoff starting at 1 second, doubling each
        attempt up to a maximum of 60 seconds. Adds 0-10% random jitter
        to prevent thundering herd.

        Formula: min(1.0 * 2^attempt, 60.0) + random(0, delay * 0.1)

        Args:
            attempt: Zero-based attempt number (0, 1, 2, ...).

        Returns:
            Delay in seconds including jitter.
        """
        base = 1.0
        max_delay = 60.0
        delay: float = min(base * (2**attempt), max_delay)
        jitter: float = random.uniform(0, delay * 0.1)  # noqa: S311
        return delay + jitter

    def _execute_with_retry(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        headers: dict[str, str],
        timeout: float | None = None,
        script: str | None = None,
    ) -> Any:
        """Execute HTTP request with retry logic for rate limiting.

        This is the core request execution method used by both _request() and
        request(). Handles rate limiting with exponential backoff and error
        response parsing.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Full URL to request.
            params: Optional query parameters.
            json_data: Optional JSON request body.
            form_data: Optional form-encoded request body.
            headers: Request headers (must include Authorization).
            timeout: Optional request timeout in seconds.
            script: Optional JQL script for error context.

        Returns:
            Parsed JSON response.

        Raises:
            AuthenticationError: Invalid credentials (401).
            RateLimitError: Rate limit exceeded after max retries (429).
            QueryError: Invalid parameters (400).
            JQLSyntaxError: JQL script syntax/runtime error (412).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.
        """
        client = self._ensure_client()
        request_body = json_data or form_data
        if params is None:
            params = {}
        params["query_origin"] = "mixpanel-data-cli"

        for attempt in range(self._max_retries + 1):
            try:
                response = client.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    data=form_data,
                    headers=headers,
                    timeout=timeout or self._timeout,
                )

                if response.status_code == 429:
                    if attempt >= self._max_retries:
                        retry_after = self._parse_retry_after(response)
                        response_body: str | dict[str, Any] | None = None
                        try:
                            response_body = response.json()
                        except json.JSONDecodeError:
                            response_body = (
                                response.text[:500] if response.text else None
                            )
                        raise RateLimitError(
                            "Rate limit exceeded after max retries",
                            retry_after=retry_after,
                            status_code=response.status_code,
                            response_body=response_body,
                            request_method=method,
                            request_url=url,
                            request_params=params,
                        )
                    retry_after = self._parse_retry_after(response)
                    if retry_after is not None:
                        wait_time = float(retry_after)
                    else:
                        wait_time = self._calculate_backoff(attempt)
                    logger.warning(
                        "Rate limited, retrying in %.1f seconds (attempt %d/%d)",
                        wait_time,
                        attempt + 1,
                        self._max_retries,
                    )
                    time.sleep(wait_time)
                    continue

                return self._handle_response(
                    response,
                    request_method=method,
                    request_url=url,
                    request_params=params,
                    request_body=request_body,
                    script=script,
                )

            except httpx.HTTPError as e:
                raise MixpanelDataError(
                    f"HTTP error: {e}",
                    code="HTTP_ERROR",
                    details={
                        "error": str(e),
                        "request_method": method,
                        "request_url": url,
                        "request_params": params,
                    },
                ) from e

        # Should not reach here, but satisfy type checker
        raise RateLimitError(
            "Rate limit exceeded after max retries",
            request_method=method,
            request_url=url,
            request_params=params,
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        form_data: dict[str, Any] | None = None,
        timeout: float | None = None,
        script: str | None = None,
        inject_project_id: bool = True,
    ) -> Any:
        """Make an authenticated request with optional project_id injection.

        Used internally by API methods. Handles rate limiting with exponential
        backoff.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Full URL to request.
            params: Query parameters.
            data: Request body as JSON (for POST).
            form_data: Request body as form-encoded (for POST).
            timeout: Override default timeout (uses self._timeout if not specified).
            script: Optional JQL script for error context.
            inject_project_id: If True (default), automatically adds project_id
                to query params. Set to False for APIs where project_id is
                already in the URL path (e.g., Lexicon Schemas API).

        Returns:
            Parsed JSON response.

        Raises:
            AuthenticationError: Invalid credentials (401).
            RateLimitError: Rate limit exceeded after max retries (429).
            QueryError: Invalid parameters (400).
            JQLSyntaxError: JQL script syntax/runtime error (412).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.
        """
        if params is None:
            params = {}
        if inject_project_id:
            params["project_id"] = self._credentials.project_id

        logger.debug(
            "_request - method: %s, url: %s, final params: %s",
            method,
            url,
            params,
        )

        return self._execute_with_retry(
            method,
            url,
            params=params,
            json_data=data,
            form_data=form_data,
            headers={"Authorization": self._get_auth_header()},
            timeout=timeout,
            script=script,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Make an authenticated request to any Mixpanel API endpoint.

        This is the escape hatch for calling Mixpanel APIs not covered by the
        Workspace class. Authentication is handled automatically.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.).
            url: Full URL to request.
            params: Optional query parameters.
            json_body: Optional JSON request body.
            headers: Optional additional headers (Authorization is added automatically).
            timeout: Optional request timeout in seconds.

        Returns:
            Parsed JSON response.

        Raises:
            AuthenticationError: Invalid credentials (401).
            RateLimitError: Rate limit exceeded after max retries (429).
            QueryError: Invalid parameters (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            Get event schema from the Lexicon API::

                client = ws.api
                schema = client.request(
                    "GET",
                    f"https://mixpanel.com/api/app/projects/{client.project_id}/schemas/event/Purchase"
                )
        """
        request_headers = {"Authorization": self._get_auth_header()}
        if headers:
            request_headers.update(headers)

        return self._execute_with_retry(
            method,
            url,
            params=params,
            json_data=json_body,
            headers=request_headers,
            timeout=timeout,
        )

    @property
    def project_id(self) -> str:
        """Get the project ID from credentials.

        Useful when constructing URLs that require the project ID.

        Returns:
            The Mixpanel project ID.
        """
        return self._credentials.project_id

    @property
    def region(self) -> str:
        """Get the configured region.

        Useful when constructing regional URLs.

        Returns:
            The region code ('us', 'eu', or 'in').
        """
        return self._credentials.region

    def _parse_retry_after(self, response: httpx.Response) -> int | None:
        """Parse Retry-After header if present.

        Args:
            response: HTTP response.

        Returns:
            Seconds to wait, or None if header not present.
        """
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return int(retry_after)
            except ValueError:
                pass
        return None

    # =========================================================================
    # App API - OAuth/Bearer requests with workspace scoping
    # =========================================================================

    def app_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        _raw: bool = False,
    ) -> Any:
        """Make an authenticated request to the Mixpanel App API.

        Uses Bearer auth (OAuth) or Basic auth depending on credentials.
        Builds the URL from the ``app`` endpoint for the configured region.
        Unwraps the ``results`` field from the response JSON when present.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE, etc.).
            path: API path (e.g., ``/projects/12345/dashboards``).
            params: Optional query parameters.
            json_body: Optional JSON request body.
            _raw: If True, return the full response dict without unwrapping
                the ``results`` field. Useful for endpoints that include
                pagination metadata alongside results.

        Returns:
            The ``results`` field from the response JSON if present,
            otherwise the full response body. For 204 No Content responses,
            returns ``{"status": "ok"}``. When ``_raw`` is True, the full
            response dict is returned without unwrapping ``results``.

        Raises:
            AuthenticationError: Invalid credentials (401).
            RateLimitError: Rate limit exceeded after max retries (429).
            QueryError: Invalid parameters or resource not found (400, 404, 422).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            client = MixpanelAPIClient(oauth_credentials)
            with client:
                dashboards = client.app_request(
                    "GET", "/projects/12345/dashboards"
                )
            ```
        """
        url = self._build_url("app", path)
        auth_header = self._credentials.auth_header()
        headers = {"Authorization": auth_header}

        client = self._ensure_client()

        # Pass through caller-supplied params only (no query_origin —
        # some App API endpoints reject unknown query parameters).
        request_params: dict[str, str] = {}
        if params:
            request_params.update(params)

        for attempt in range(self._max_retries + 1):
            try:
                response = client.request(
                    method,
                    url,
                    params=request_params,
                    json=json_body,
                    headers=headers,
                    timeout=self._timeout,
                )

                # Handle 204 No Content
                if response.status_code == 204:
                    return {"status": "ok"}

                # Handle 429 rate limiting with retry
                if response.status_code == 429:
                    if attempt >= self._max_retries:
                        retry_after = self._parse_retry_after(response)
                        response_body: str | dict[str, Any] | None = None
                        try:
                            response_body = response.json()
                        except json.JSONDecodeError:
                            response_body = (
                                response.text[:500] if response.text else None
                            )
                        raise RateLimitError(
                            "Rate limit exceeded after max retries",
                            retry_after=retry_after,
                            status_code=response.status_code,
                            response_body=response_body,
                            request_method=method,
                            request_url=url,
                        )
                    retry_after = self._parse_retry_after(response)
                    if retry_after is not None:
                        wait_time = float(retry_after)
                    else:
                        wait_time = self._calculate_backoff(attempt)
                    logger.warning(
                        "Rate limited, retrying in %.1f seconds (attempt %d/%d)",
                        wait_time,
                        attempt + 1,
                        self._max_retries,
                    )
                    time.sleep(wait_time)
                    continue

                # Handle 422 as QueryError
                if response.status_code == 422:
                    err_body: str | dict[str, Any] | None = None
                    try:
                        err_body = response.json()
                    except json.JSONDecodeError:
                        err_body = response.text[:500] if response.text else None
                    error_msg = "Unprocessable entity"
                    if isinstance(err_body, dict):
                        error_msg = str(err_body.get("error", error_msg))
                    raise QueryError(
                        error_msg,
                        status_code=422,
                        response_body=err_body,
                        request_method=method,
                        request_url=url,
                        request_body=json_body,
                    )

                # Delegate other error codes to _handle_response
                result = self._handle_response(
                    response,
                    request_method=method,
                    request_url=url,
                    request_params=request_params,
                    request_body=json_body,
                )

                # Unwrap results field if present (unless _raw requested)
                if not _raw and isinstance(result, dict) and "results" in result:
                    return result["results"]
                return result

            except httpx.HTTPError as e:
                raise MixpanelDataError(
                    f"HTTP error: {e}",
                    code="HTTP_ERROR",
                    details={
                        "error": str(e),
                        "request_method": method,
                        "request_url": url,
                    },
                ) from e

        # Should not reach here, but satisfy type checker
        raise RateLimitError(
            "Rate limit exceeded after max retries",
            request_method=method,
            request_url=url,
        )

    @property
    def workspace_id(self) -> int | None:
        """Return the explicit workspace ID, if set.

        Returns:
            The workspace ID set via ``set_workspace_id()``, or None.
        """
        return self._workspace_id

    def set_workspace_id(self, workspace_id: int | None) -> None:
        """Set or clear the explicit workspace ID for scoped requests.

        When set, ``maybe_scoped_path()`` will use workspace-scoped paths.
        Setting to ``None`` clears both the explicit ID and the cached
        auto-discovered ID, reverting to project-scoped paths.

        Args:
            workspace_id: Workspace ID to use, or None to clear.

        Example:
            ```python
            client.set_workspace_id(789)
            path = client.maybe_scoped_path("dashboards")
            # "/workspaces/789/dashboards"

            client.set_workspace_id(None)
            path = client.maybe_scoped_path("dashboards")
            # "/projects/12345/dashboards"
            ```
        """
        self._workspace_id = workspace_id
        if workspace_id is None:
            self._cached_workspace_id = None

    def resolve_workspace_id(self) -> int:
        """Resolve the workspace ID to use for scoped requests.

        Resolution order:
        1. Explicit workspace ID (set via ``set_workspace_id()``)
        2. Cached auto-discovered workspace ID
        3. Auto-discover by calling ``list_workspaces()`` and finding
           the default workspace (``is_default=True``), falling back
           to the first workspace.

        Returns:
            The resolved workspace ID.

        Raises:
            WorkspaceScopeError: If no workspaces are found for the project.

        Example:
            ```python
            client.set_workspace_id(42)
            assert client.resolve_workspace_id() == 42

            # Or auto-discover:
            ws_id = client.resolve_workspace_id()
            ```
        """
        if self._workspace_id is not None:
            return self._workspace_id

        if self._cached_workspace_id is not None:
            return self._cached_workspace_id

        workspaces = self.list_workspaces()
        if not workspaces:
            raise WorkspaceScopeError(
                "No workspaces found for project "
                f"'{self._credentials.project_id}'. "
                "Ensure you have access to at least one workspace.",
                code="NO_WORKSPACES",
                details={"project_id": self._credentials.project_id},
            )

        # Prefer the default workspace
        for ws in workspaces:
            if ws.is_default:
                self._cached_workspace_id = ws.id
                return ws.id

        # Fall back to first workspace
        self._cached_workspace_id = workspaces[0].id
        return workspaces[0].id

    def maybe_scoped_path(self, domain_path: str) -> str:
        """Build an optionally workspace-scoped API path.

        If a workspace ID is set (via ``set_workspace_id()``), returns a
        workspace-scoped path. Otherwise returns a project-scoped path.

        Args:
            domain_path: Domain-relative path (e.g., ``"dashboards"``).

        Returns:
            Workspace-scoped path ``/workspaces/{wid}/{domain_path}`` if
            workspace is set, otherwise ``/projects/{pid}/{domain_path}``.

        Example:
            ```python
            # No workspace set:
            client.maybe_scoped_path("dashboards")
            # "/projects/12345/dashboards"

            # With workspace:
            client.set_workspace_id(789)
            client.maybe_scoped_path("dashboards")
            # "/workspaces/789/dashboards"
            ```
        """
        if self._workspace_id is not None:
            return f"/workspaces/{self._workspace_id}/{domain_path}"
        return f"/projects/{self._credentials.project_id}/{domain_path}"

    def require_scoped_path(self, domain_path: str) -> str:
        """Build a workspace-scoped API path, auto-discovering if needed.

        Always returns a path scoped to both project and workspace. If no
        workspace ID is set, auto-discovers one via ``resolve_workspace_id()``.

        Args:
            domain_path: Domain-relative path (e.g., ``"feature-flags"``).

        Returns:
            Path in format ``/projects/{pid}/workspaces/{wid}/{domain_path}``.

        Raises:
            WorkspaceScopeError: If no workspaces are found for the project.

        Example:
            ```python
            client.set_workspace_id(789)
            client.require_scoped_path("feature-flags")
            # "/projects/12345/workspaces/789/feature-flags"

            # Auto-discovers workspace if not set:
            client.require_scoped_path("experiments")
            # "/projects/12345/workspaces/100/experiments"
            ```
        """
        ws_id = self.resolve_workspace_id()
        pid = self._credentials.project_id
        return f"/projects/{pid}/workspaces/{ws_id}/{domain_path}"

    def list_workspaces(self) -> list[PublicWorkspace]:
        """List all public workspaces for the current project.

        Calls ``GET /api/app/projects/{pid}/workspaces/public``.

        Returns:
            List of PublicWorkspace models for the project.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400, 404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                workspaces = client.list_workspaces()
                for ws in workspaces:
                    print(f"{ws.name} (id={ws.id}, default={ws.is_default})")
            ```
        """
        pid = self._credentials.project_id
        path = f"/projects/{pid}/workspaces/public"
        results = self.app_request("GET", path)

        if not isinstance(results, list):
            raise MixpanelDataError(
                f"Unexpected response format from list_workspaces: "
                f"expected list, got {type(results).__name__}",
            )
        return [PublicWorkspace.model_validate(ws) for ws in results]

    # =========================================================================
    # Export API - Streaming
    # =========================================================================

    def export_events(
        self,
        from_date: str,
        to_date: str,
        *,
        events: list[str] | None = None,
        where: str | None = None,
        limit: int | None = None,
        on_batch: Callable[[int], None] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream events from the Export API.

        Streams events line by line from Mixpanel's JSONL export endpoint.
        Memory-efficient for large exports since events are yielded one at a time.

        Args:
            from_date: Start date (YYYY-MM-DD, inclusive).
            to_date: End date (YYYY-MM-DD, inclusive).
            events: Optional list of event names to filter.
            where: Optional filter expression.
            limit: Optional maximum number of events to return (max 100000).
            on_batch: Optional callback invoked with cumulative count every
                1000 events, and once at the end for any remaining events.

        Yields:
            Event dictionaries with 'event' and 'properties' keys.
            Malformed JSON lines are logged and skipped (not raised).

        Raises:
            AuthenticationError: Invalid credentials.
            RateLimitError: Rate limit exceeded after max retries.
            QueryError: Invalid parameters.
            ServerError: Server-side errors (5xx).
        """
        url = self._build_url("export", "/export")

        params: dict[str, Any] = {
            "project_id": self._credentials.project_id,
            "from_date": from_date,
            "to_date": to_date,
        }
        if events:
            params["event"] = json.dumps(events)
        if where:
            params["where"] = where
        if limit is not None:
            params["limit"] = limit

        client = self._ensure_client()
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept-Encoding": "gzip",
        }

        # Stream with retry logic
        for attempt in range(self._max_retries + 1):
            batch_count = 0  # Reset on each attempt
            try:
                with client.stream(
                    "GET",
                    url,
                    params=params,
                    headers=headers,
                    timeout=self._export_timeout,
                ) as response:
                    if response.status_code == 429:
                        if attempt >= self._max_retries:
                            retry_after = self._parse_retry_after(response)
                            raise RateLimitError(
                                "Rate limit exceeded after max retries",
                                retry_after=retry_after,
                                status_code=response.status_code,
                                request_method="GET",
                                request_url=url,
                                request_params=params,
                            )
                        retry_after = self._parse_retry_after(response)
                        if retry_after is not None:
                            wait_time = float(retry_after)
                        else:
                            wait_time = self._calculate_backoff(attempt)
                        time.sleep(wait_time)
                        continue

                    if response.status_code == 401:
                        raise AuthenticationError(
                            "Invalid credentials. Check username, secret, and project_id.",
                            status_code=response.status_code,
                            request_method="GET",
                            request_url=url,
                            request_params=params,
                        )
                    if response.status_code == 400:
                        # Need to read body for error
                        body = response.read()
                        response_body: str | dict[str, Any] | None = None
                        error_msg = "Unknown error"
                        try:
                            response_body = json.loads(body)
                            if isinstance(response_body, dict):
                                error_msg = response_body.get("error", "Unknown error")
                        except json.JSONDecodeError:
                            response_body = body.decode()[:500] if body else None
                            error_msg = body.decode()[:200] if body else "Unknown error"
                        raise QueryError(
                            error_msg,
                            status_code=response.status_code,
                            response_body=response_body,
                            request_method="GET",
                            request_url=url,
                            request_params=params,
                        )

                    response.raise_for_status()

                    # Use buffered JSONL reader instead of iter_lines().
                    # httpx iter_lines() can incorrectly split lines at gzip
                    # decompression chunk boundaries, causing JSON parse errors.
                    # See: _iter_jsonl_lines docstring for implementation details.
                    for line in _iter_jsonl_lines(response):
                        try:
                            event = json.loads(line)
                            yield event
                            batch_count += 1
                            if on_batch and batch_count % 1000 == 0:
                                on_batch(batch_count)
                        except json.JSONDecodeError:
                            logger.warning("Skipping malformed line: %s", line[:100])

                    # Call on_batch with final count if there was a partial batch
                    if on_batch and batch_count % 1000 != 0:
                        on_batch(batch_count)
                    return  # Success, exit retry loop

            except httpx.HTTPError as e:
                # Network/connection errors - retry if attempts remain
                if attempt >= self._max_retries:
                    raise MixpanelDataError(
                        f"HTTP error during export: {e}",
                        code="HTTP_ERROR",
                        details={"error": str(e)},
                    ) from e
                time.sleep(self._calculate_backoff(attempt))

    def export_profiles(
        self,
        *,
        where: str | None = None,
        cohort_id: str | None = None,
        output_properties: list[str] | None = None,
        on_batch: Callable[[int], None] | None = None,
        distinct_id: str | None = None,
        distinct_ids: list[str] | None = None,
        group_id: str | None = None,
        behaviors: list[dict[str, Any]] | None = None,
        as_of_timestamp: int | None = None,
        include_all_users: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """Stream profiles from the Engage API.

        Paginates through all user profiles using Mixpanel's session-based
        pagination. Each page is a separate API request.

        Args:
            where: Optional filter expression.
            cohort_id: Optional cohort ID to filter by. Only profiles that are
                members of this cohort will be returned.
            output_properties: Optional list of property names to include in
                the response. If None, all properties are returned.
            on_batch: Optional callback invoked with cumulative count after
                each page is processed.
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
            Profile dictionaries with '$distinct_id' and '$properties' keys.

        Raises:
            ValueError: If mutually exclusive parameters are provided together,
                or if include_all_users is used without cohort_id.
            AuthenticationError: Invalid credentials.
            RateLimitError: Rate limit exceeded after max retries.
            ServerError: Server-side errors (5xx).
        """
        # Validate mutually exclusive parameters
        if distinct_id is not None and distinct_ids is not None:
            raise ValueError(
                "distinct_id and distinct_ids are mutually exclusive. "
                "Provide only one to fetch specific profiles."
            )

        if behaviors is not None and cohort_id is not None:
            raise ValueError(
                "behaviors and cohort_id are mutually exclusive. "
                "Use behaviors for behavioral filtering or cohort_id for cohort membership."
            )

        if include_all_users and cohort_id is None:
            raise ValueError(
                "include_all_users requires cohort_id. "
                "This parameter is only valid for cohort membership queries."
            )

        # Validate behaviors type
        if behaviors is not None and not isinstance(behaviors, list):
            raise ValueError(
                "behaviors must be a list of behavioral filter dictionaries."
            )

        # Validate as_of_timestamp is not in the future
        if as_of_timestamp is not None:
            current_time = int(time.time())
            if as_of_timestamp > current_time:
                raise ValueError(
                    "as_of_timestamp cannot be in the future. "
                    "Provide a Unix timestamp in the past to query historical profile state."
                )

        # Handle empty distinct_ids list - return early without API call
        if distinct_ids is not None and len(distinct_ids) == 0:
            return

        # Deduplicate distinct_ids if provided
        if distinct_ids is not None:
            distinct_ids = list(dict.fromkeys(distinct_ids))  # Preserves order

        url = self._build_url("engage", "")

        session_id: str | None = None
        page = 0
        total_count = 0

        while True:
            params: dict[str, Any] = {
                "project_id": self._credentials.project_id,
                "page": page,
            }
            if session_id:
                params["session_id"] = session_id
            if where:
                params["where"] = where
            if cohort_id:
                params["filter_by_cohort"] = json.dumps({"id": cohort_id})
            if output_properties:
                params["output_properties"] = json.dumps(output_properties)
            if distinct_id:
                params["distinct_id"] = distinct_id
            if distinct_ids:
                params["distinct_ids"] = json.dumps(distinct_ids)
            if group_id:
                params["data_group_id"] = group_id
            if behaviors:
                params["behaviors"] = json.dumps(behaviors)
            if as_of_timestamp is not None:
                params["as_of_timestamp"] = as_of_timestamp
            # Only send include_all_users when cohort_id is set (it's meaningless otherwise)
            # Must send explicitly because API defaults to True
            if cohort_id:
                params["include_all_users"] = include_all_users

            response = self._request("POST", url, data=params)

            results = response.get("results", [])
            if not results:
                break

            for profile in results:
                yield profile
                total_count += 1

            if on_batch:
                on_batch(total_count)

            session_id = response.get("session_id")
            if not session_id:
                break
            page += 1

    def export_profiles_page(
        self,
        page: int,
        session_id: str | None = None,
        *,
        where: str | None = None,
        cohort_id: str | None = None,
        output_properties: list[str] | None = None,
        group_id: str | None = None,
        behaviors: list[dict[str, Any]] | None = None,
        as_of_timestamp: int | None = None,
        include_all_users: bool = False,
    ) -> ProfilePageResult:
        """Fetch a single page of profiles from the Engage API.

        This method fetches exactly one page from the Engage API, enabling
        parallel fetching of multiple pages. For sequential fetching of
        all profiles, use export_profiles() instead.

        Args:
            page: Zero-based page index to fetch.
            session_id: Session ID from previous page (None for first page).
            where: Filter expression (e.g., 'properties["plan"] == "premium"').
            cohort_id: Filter to specific cohort by ID.
            output_properties: Properties to include (None for all).
            group_id: Group analytics group identifier.
            behaviors: Behavioral filter definitions.
            as_of_timestamp: Unix timestamp for point-in-time query.
            include_all_users: Include non-members in cohort results.

        Returns:
            ProfilePageResult with profiles, session_id, page, and has_more.

        Raises:
            AuthenticationError: Invalid credentials.
            RateLimitError: API rate limit exceeded.
            APIError: Other API errors.

        Example:
            ```python
            # Fetch first page
            result = client.export_profiles_page(page=0)

            # Continue fetching if more pages
            while result.has_more:
                result = client.export_profiles_page(
                    page=result.page + 1,
                    session_id=result.session_id,
                )
            ```
        """
        url = self._build_url("engage", "")

        params: dict[str, Any] = {
            "project_id": self._credentials.project_id,
            "page": page,
        }
        if session_id:
            params["session_id"] = session_id
        if where:
            params["where"] = where
        if cohort_id:
            params["filter_by_cohort"] = json.dumps({"id": cohort_id})
        if output_properties:
            params["output_properties"] = json.dumps(output_properties)
        if group_id:
            params["data_group_id"] = group_id
        if behaviors:
            params["behaviors"] = json.dumps(behaviors)
        if as_of_timestamp is not None:
            params["as_of_timestamp"] = as_of_timestamp
        # Only send include_all_users when cohort_id is set (it's meaningless otherwise)
        # Must send explicitly because API defaults to True
        if cohort_id:
            params["include_all_users"] = include_all_users

        response = self._request("POST", url, data=params)

        profiles = response.get("results", [])
        returned_session_id = response.get("session_id")
        has_more = returned_session_id is not None

        # Extract pagination metadata for pre-computed page approach
        total = response.get("total", 0)
        page_size = response.get("page_size", 1000)

        return ProfilePageResult(
            profiles=profiles,
            session_id=returned_session_id,
            page=page,
            has_more=has_more,
            total=total,
            page_size=page_size,
        )

    # =========================================================================
    # Discovery API
    # =========================================================================

    def get_events(self) -> list[str]:
        """List all event names in the project.

        Returns:
            List of event name strings.

        Raises:
            AuthenticationError: Invalid credentials.
        """
        url = self._build_url("query", "/events/names")
        response = self._request("GET", url, params={"type": "general"})
        # Response is a list of event names
        if isinstance(response, list):
            return [str(e) for e in response]
        return []

    def get_event_properties(self, event: str) -> list[str]:
        """List properties for a specific event.

        Args:
            event: Event name.

        Returns:
            List of property name strings.

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid event name.
        """
        url = self._build_url("query", "/events/properties/top")
        response = self._request("GET", url, params={"event": event})
        # Response is a dict with property names as keys and counts as values
        if isinstance(response, dict):
            return list(response.keys())
        return []

    def get_property_values(
        self,
        property_name: str,
        *,
        event: str | None = None,
        limit: int = 255,
    ) -> list[str]:
        """List sample values for a property.

        Args:
            property_name: Property name.
            event: Optional event name to scope the property.
            limit: Maximum number of values to return.

        Returns:
            List of property value strings.

        Raises:
            AuthenticationError: Invalid credentials.
        """
        url = self._build_url("query", "/events/properties/values")
        params: dict[str, Any] = {
            "name": property_name,
            "limit": limit,
        }
        if event:
            params["event"] = event
        response = self._request("GET", url, params=params)
        if isinstance(response, list):
            return [str(v) for v in response]
        return []

    def list_funnels(self) -> list[dict[str, Any]]:
        """List all saved funnels in the project.

        Returns:
            List of funnel dictionaries with keys: funnel_id (int), name (str).

        Raises:
            AuthenticationError: Invalid credentials.
            RateLimitError: Rate limit exceeded after retries.
        """
        url = self._build_url("query", "/funnels/list")
        response = self._request("GET", url)
        if isinstance(response, list):
            return response
        return []

    def list_cohorts(self) -> list[dict[str, Any]]:
        """List all saved cohorts in the project.

        Returns:
            List of cohort dictionaries with keys:
            id (int), name (str), count (int), description (str),
            created (str), is_visible (int), project_id (int).

        Raises:
            AuthenticationError: Invalid credentials.
            RateLimitError: Rate limit exceeded after retries.
        """
        # Note: POST method is unusual for read-only, but per API spec
        url = self._build_url("query", "/cohorts/list")
        response = self._request("POST", url)
        if isinstance(response, list):
            return response
        return []

    def get_top_events(
        self,
        *,
        type: str = "general",
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Get today's top events with counts and trends.

        Args:
            type: Counting method - "general", "unique", or "average".
            limit: Maximum events to return (default: 100).

        Returns:
            Dictionary with keys:
            - events: list of {amount: int, event: str, percent_change: float}
            - type: str

        Raises:
            AuthenticationError: Invalid credentials.
            RateLimitError: Rate limit exceeded after retries.
        """
        url = self._build_url("query", "/events/top")
        params: dict[str, Any] = {"type": type}
        if limit is not None:
            params["limit"] = limit
        response = self._request("GET", url, params=params)
        if isinstance(response, dict):
            return response
        return {"events": [], "type": type}

    def event_counts(
        self,
        events: list[str],
        from_date: str,
        to_date: str,
        *,
        type: str = "general",
        unit: str = "day",
    ) -> dict[str, Any]:
        """Get aggregate counts for multiple events over time.

        Args:
            events: List of event names to query.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            type: Counting method - "general", "unique", or "average".
            unit: Time unit - "day", "week", or "month".

        Returns:
            Dictionary with keys:
            - data.series: list of date strings
            - data.values: {event_name: {date: count}}
            - legend_size: int

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid parameters.
            RateLimitError: Rate limit exceeded after retries.
        """
        url = self._build_url("query", "/events")
        params: dict[str, Any] = {
            "event": json.dumps(events),
            "type": type,
            "unit": unit,
            "from_date": from_date,
            "to_date": to_date,
        }
        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    def property_counts(
        self,
        event: str,
        property_name: str,
        from_date: str,
        to_date: str,
        *,
        type: str = "general",
        unit: str = "day",
        values: list[str] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Get aggregate counts by property values over time.

        Args:
            event: Event name to query.
            property_name: Property to segment by.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            type: Counting method - "general", "unique", or "average".
            unit: Time unit - "day", "week", or "month".
            values: Optional list of specific property values to include.
            limit: Maximum property values to return (default: 255).

        Returns:
            Dictionary with keys:
            - data.series: list of date strings
            - data.values: {property_value: {date: count}}
            - legend_size: int

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid parameters.
            RateLimitError: Rate limit exceeded after retries.
        """
        url = self._build_url("query", "/events/properties")
        params: dict[str, Any] = {
            "event": event,
            "name": property_name,
            "type": type,
            "unit": unit,
            "from_date": from_date,
            "to_date": to_date,
        }
        if values is not None:
            params["values"] = json.dumps(values)
        if limit is not None:
            params["limit"] = limit
        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    # =========================================================================
    # Query API - Raw Responses
    # =========================================================================

    def segmentation(
        self,
        event: str,
        from_date: str,
        to_date: str,
        *,
        on: str | None = None,
        unit: str = "day",
        type: str = "general",
        where: str | None = None,
    ) -> dict[str, Any]:
        """Run a segmentation query.

        Args:
            event: Event name to segment.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            on: Optional property to segment by.
            unit: Time unit (minute, hour, day, week, month).
            type: Aggregation type (general, unique, average).
            where: Optional filter expression.

        Returns:
            Raw API response dictionary.

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid query parameters.
            RateLimitError: Rate limit exceeded.
        """
        url = self._build_url("query", "/segmentation")
        params: dict[str, Any] = {
            "event": event,
            "from_date": from_date,
            "to_date": to_date,
            "unit": unit,
            "type": type,
        }
        if on:
            params["on"] = on
        if where:
            params["where"] = where
        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    def funnel(
        self,
        funnel_id: int,
        from_date: str,
        to_date: str,
        *,
        unit: str | None = None,
        on: str | None = None,
        where: str | None = None,
        length: int | None = None,
        length_unit: str | None = None,
    ) -> dict[str, Any]:
        """Run a funnel analysis query.

        Args:
            funnel_id: Funnel identifier.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            unit: Time unit for grouping.
            on: Optional property to segment by.
            where: Optional filter expression.
            length: Conversion window length.
            length_unit: Conversion window unit.

        Returns:
            Raw API response dictionary.

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid funnel ID or parameters.
            RateLimitError: Rate limit exceeded.
        """
        url = self._build_url("query", "/funnels")
        params: dict[str, Any] = {
            "funnel_id": funnel_id,
            "from_date": from_date,
            "to_date": to_date,
        }
        if unit:
            params["unit"] = unit
        if on:
            params["on"] = on
        if where:
            params["where"] = where
        if length is not None:
            params["length"] = length
        if length_unit:
            params["length_unit"] = length_unit
        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    def retention(
        self,
        born_event: str,
        event: str,
        from_date: str,
        to_date: str,
        *,
        retention_type: str = "birth",
        born_where: str | None = None,
        where: str | None = None,
        interval: int = 1,
        interval_count: int = 8,
        unit: str = "day",
    ) -> dict[str, Any]:
        """Run a retention analysis query.

        Args:
            born_event: Event that defines cohort membership.
            event: Event that defines return.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            retention_type: Retention type (birth, compounded).
            born_where: Optional filter for born event.
            where: Optional filter for return event.
            interval: Retention interval size.
            interval_count: Number of intervals to track.
            unit: Interval unit (day, week, month).

        Returns:
            Raw API response dictionary.

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid parameters.
            RateLimitError: Rate limit exceeded.
        """
        url = self._build_url("query", "/retention")
        params: dict[str, Any] = {
            "born_event": born_event,
            "event": event,
            "from_date": from_date,
            "to_date": to_date,
            "retention_type": retention_type,
            "interval_count": interval_count,
        }
        # Mixpanel API doesn't allow both 'unit' and 'interval' together.
        # Use 'interval' for custom intervals, 'unit' for standard periods.
        if interval != 1:
            params["interval"] = interval
        else:
            params["unit"] = unit
        if born_where:
            params["born_where"] = born_where
        if where:
            params["where"] = where
        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    def jql(
        self,
        script: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[Any]:
        """Execute a JQL (JavaScript Query Language) script.

        Args:
            script: JQL script code.
            params: Optional parameters to pass to the script.

        Returns:
            List of results from script execution.

        Raises:
            AuthenticationError: Invalid credentials.
            JQLSyntaxError: Script syntax or runtime error.
            RateLimitError: Rate limit exceeded.
        """
        url = self._build_url("query", "/jql")
        # JQL API expects form-encoded data with params as JSON string
        form: dict[str, Any] = {"script": script}
        if params:
            form["params"] = json.dumps(params)
        # Pass script for error context in case of JQL syntax errors
        response = self._request("POST", url, form_data=form, script=script)
        if isinstance(response, list):
            return response
        return []

    # =========================================================================
    # Phase 008: Query Service Enhancements
    # =========================================================================

    def activity_feed(
        self,
        distinct_ids: list[str],
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """Query activity feed for specific users.

        Args:
            distinct_ids: List of user identifiers to query.
            from_date: Optional start date (YYYY-MM-DD).
            to_date: Optional end date (YYYY-MM-DD).

        Returns:
            Raw API response with events under results.events.

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid parameters.
            RateLimitError: Rate limit exceeded.
        """
        url = self._build_url("query", "/stream/query")
        params: dict[str, Any] = {
            "distinct_ids": json.dumps(distinct_ids),
        }
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date
        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    def query_saved_report(
        self,
        bookmark_id: int,
        *,
        bookmark_type: Literal[
            "insights", "funnels", "retention", "flows"
        ] = "insights",
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """Query a saved report by bookmark type.

        Routes to the appropriate Mixpanel API endpoint based on bookmark_type
        and returns the raw API response.

        Args:
            bookmark_id: Saved report identifier (from Mixpanel URL or list_bookmarks).
            bookmark_type: Type of bookmark to query. Determines which API endpoint
                is called. Defaults to 'insights'.
            from_date: Start date (YYYY-MM-DD). Required for funnels, optional otherwise.
                If not provided for funnels, defaults to 30 days ago.
            to_date: End date (YYYY-MM-DD). Required for funnels, optional otherwise.
                If not provided for funnels, defaults to today.

        Returns:
            Raw API response with report data. Structure varies by bookmark_type:
            - insights: {headers, computed_at, date_range, series}
            - funnels: {computed_at, data, meta}
            - retention: {date: {first, counts, rates}}
            - flows: {computed_at, steps, breakdowns, overallConversionRate}

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid bookmark_id or report not found.
            RateLimitError: Rate limit exceeded.
        """
        if bookmark_type == "insights":
            url = self._build_url("query", "/insights")
            params: dict[str, Any] = {"bookmark_id": bookmark_id}
        elif bookmark_type == "funnels":
            url = self._build_url("query", "/funnels")
            # Funnels uses funnel_id instead of bookmark_id
            # Default to 30-day window, deriving missing date from the provided one
            if from_date is None and to_date is None:
                # Neither provided: use last 30 days from today
                to_date = datetime.now().strftime("%Y-%m-%d")
                from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            elif from_date is None and to_date is not None:
                # Only to_date provided: derive from_date as 30 days before to_date
                to_date_parsed = datetime.strptime(to_date, "%Y-%m-%d")
                from_date = (to_date_parsed - timedelta(days=30)).strftime("%Y-%m-%d")
            elif to_date is None and from_date is not None:
                # Only from_date provided: derive to_date as 30 days after from_date
                # but cap at today to avoid querying future dates
                from_date_parsed = datetime.strptime(from_date, "%Y-%m-%d")
                computed_to = from_date_parsed + timedelta(days=30)
                to_date = min(computed_to, datetime.now()).strftime("%Y-%m-%d")
            params = {
                "funnel_id": bookmark_id,
                "from_date": from_date,
                "to_date": to_date,
            }
        elif bookmark_type == "retention":
            url = self._build_url("query", "/retention")
            params = {"bookmark_id": bookmark_id}
        elif bookmark_type == "flows":
            url = self._build_url("query", "/arb_funnels")
            params = {
                "bookmark_id": bookmark_id,
                "query_type": "flows_sankey",
            }
        else:
            # This shouldn't happen due to Literal type, but handle gracefully
            url = self._build_url("query", "/insights")
            params = {"bookmark_id": bookmark_id}

        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    def list_bookmarks(
        self,
        bookmark_type: str | None = None,
    ) -> dict[str, Any]:
        """List all saved reports (bookmarks) in the project.

        Retrieves metadata for all saved Insights, Funnel, Retention, and
        Flows reports in the project.

        Args:
            bookmark_type: Optional filter by report type. Valid values are
                'insights', 'funnels', 'retention', 'flows', 'launch-analysis'.
                If None, returns all bookmark types.

        Returns:
            Raw API response with 'results' array containing bookmark metadata.

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Permission denied or invalid parameters.
            RateLimitError: Rate limit exceeded.
        """
        url = self._build_url(
            "app",
            f"/projects/{self._credentials.project_id}/bookmarks",
        )
        params: dict[str, Any] = {"v": "2"}
        if bookmark_type is not None:
            params["type"] = bookmark_type
        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    def query_flows(
        self,
        bookmark_id: int,
    ) -> dict[str, Any]:
        """Query a saved flows report by bookmark ID.

        Retrieves data from a saved Flows report using the arb_funnels
        endpoint with flows_sankey query type.

        Args:
            bookmark_id: Saved flows report identifier.

        Returns:
            Raw API response with steps, breakdowns, and conversion rate.

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid bookmark_id or report not found.
            RateLimitError: Rate limit exceeded.
        """
        url = self._build_url("query", "/arb_funnels")
        params: dict[str, Any] = {
            "bookmark_id": bookmark_id,
            "query_type": "flows_sankey",
        }
        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    def frequency(
        self,
        from_date: str,
        to_date: str,
        unit: str,
        addiction_unit: str,
        *,
        event: str | None = None,
        where: str | None = None,
        on: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Query event frequency distribution (addiction analysis).

        Args:
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            unit: Overall time period ("day", "week", "month").
            addiction_unit: Measurement granularity ("hour", "day").
            event: Optional event name to filter.
            where: Optional filter expression.
            on: Optional property to segment by.
            limit: Optional maximum segmentation values.

        Returns:
            Raw API response with frequency arrays in data key.

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid parameters.
            RateLimitError: Rate limit exceeded.
        """
        url = self._build_url("query", "/retention/addiction")
        params: dict[str, Any] = {
            "from_date": from_date,
            "to_date": to_date,
            "unit": unit,
            "addiction_unit": addiction_unit,
        }
        if event:
            params["event"] = event
        if where:
            params["where"] = where
        if on:
            params["on"] = on
        if limit is not None:
            params["limit"] = limit
        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    def segmentation_numeric(
        self,
        event: str,
        from_date: str,
        to_date: str,
        on: str,
        *,
        unit: str = "day",
        where: str | None = None,
        type: str = "general",
    ) -> dict[str, Any]:
        """Query events bucketed by numeric property ranges.

        Args:
            event: Event name to analyze.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            on: Numeric property expression to bucket.
            unit: Time aggregation unit ("hour", "day").
            where: Optional filter expression.
            type: Counting method ("general", "unique", "average").

        Returns:
            Raw API response with bucketed time-series in data.values.

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid parameters or non-numeric property.
            RateLimitError: Rate limit exceeded.
        """
        url = self._build_url("query", "/segmentation/numeric")
        params: dict[str, Any] = {
            "event": event,
            "from_date": from_date,
            "to_date": to_date,
            "on": on,
            "unit": unit,
            "type": type,
        }
        if where:
            params["where"] = where
        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    def segmentation_sum(
        self,
        event: str,
        from_date: str,
        to_date: str,
        on: str,
        *,
        unit: str = "day",
        where: str | None = None,
    ) -> dict[str, Any]:
        """Query sum of numeric property values.

        Args:
            event: Event name to analyze.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            on: Numeric property expression to sum.
            unit: Time aggregation unit ("hour", "day").
            where: Optional filter expression.

        Returns:
            Raw API response with sum values in results key.

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid parameters or non-numeric property.
            RateLimitError: Rate limit exceeded.
        """
        url = self._build_url("query", "/segmentation/sum")
        params: dict[str, Any] = {
            "event": event,
            "from_date": from_date,
            "to_date": to_date,
            "on": on,
            "unit": unit,
        }
        if where:
            params["where"] = where
        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    def segmentation_average(
        self,
        event: str,
        from_date: str,
        to_date: str,
        on: str,
        *,
        unit: str = "day",
        where: str | None = None,
    ) -> dict[str, Any]:
        """Query average of numeric property values.

        Args:
            event: Event name to analyze.
            from_date: Start date (YYYY-MM-DD).
            to_date: End date (YYYY-MM-DD).
            on: Numeric property expression to average.
            unit: Time aggregation unit ("hour", "day").
            where: Optional filter expression.

        Returns:
            Raw API response with average values in results key.

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Invalid parameters or non-numeric property.
            RateLimitError: Rate limit exceeded.
        """
        url = self._build_url("query", "/segmentation/average")
        params: dict[str, Any] = {
            "event": event,
            "from_date": from_date,
            "to_date": to_date,
            "on": on,
            "unit": unit,
        }
        if where:
            params["where"] = where
        result: dict[str, Any] = self._request("GET", url, params=params)
        return result

    # =========================================================================
    # Lexicon Schemas API
    # =========================================================================

    def get_schemas(
        self,
        *,
        entity_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all Lexicon schemas in the project.

        Retrieves documented event and profile property schemas from the
        Mixpanel Lexicon (data dictionary).

        Args:
            entity_type: Optional filter by type ("event", "profile", etc.).
                If None, returns all schemas.

        Returns:
            List of raw schema dictionaries from the API, each containing:
                - entityType: "event", "profile", "custom_event", etc.
                - name: Entity name
                - schemaJson: Full schema definition with properties and metadata

        Raises:
            AuthenticationError: Invalid credentials.
            RateLimitError: Rate limit exceeded after max retries.
        """
        # entity_type is a path parameter, not a query parameter
        # URL structure: /api/app/projects/{projectId}/schemas/{entity_type}
        if entity_type is not None:
            path = f"/projects/{self._credentials.project_id}/schemas/{entity_type}"
        else:
            path = f"/projects/{self._credentials.project_id}/schemas"

        url = self._build_url("app", path)

        logger.debug(
            "get_schemas request - URL: %s, entity_type filter: %s",
            url,
            entity_type,
        )

        result: dict[str, Any] = self._request("GET", url, inject_project_id=False)

        schemas: list[dict[str, Any]] = result.get("results", [])
        entity_types_returned = {s.get("entityType") for s in schemas}
        logger.debug(
            "get_schemas response - %d schemas returned, entity types: %s",
            len(schemas),
            entity_types_returned,
        )

        return schemas

    def get_schema(
        self,
        entity_type: str,
        name: str,
    ) -> dict[str, Any]:
        """Get a single Lexicon schema by entity type and name.

        Args:
            entity_type: Entity type ("event", "profile", "custom_event", etc.).
            name: Entity name.

        Returns:
            Schema dictionary normalized to match list response format:
                - entityType: The entity type from request
                - name: The entity name from request
                - schemaJson: Full schema definition with properties and metadata

        Raises:
            AuthenticationError: Invalid credentials.
            QueryError: Schema not found (404 mapped to QueryError).
            RateLimitError: Rate limit exceeded after max retries.
        """
        # URL structure: /api/app/projects/{projectId}/schemas/{entity_type}?entity_name={name}
        url = self._build_url(
            "app",
            f"/projects/{self._credentials.project_id}/schemas/{entity_type}",
        )
        params = {"entity_name": name}

        logger.debug(
            "get_schema request - URL: %s, entity_type: %s, name: %s",
            url,
            entity_type,
            name,
        )

        result: dict[str, Any] = self._request(
            "GET", url, params=params, inject_project_id=False
        )

        # Single schema response format is: {status: "ok", results: <schemaJson>}
        # Normalize to match list response format: {entityType, name, schemaJson}
        schema_json = result.get("results", result)
        return {
            "entityType": entity_type,
            "name": name,
            "schemaJson": schema_json,
        }

    # =========================================================================
    # Dashboard CRUD (Phase 024)
    # =========================================================================

    def list_dashboards(self, *, ids: list[int] | None = None) -> list[dict[str, Any]]:
        """List dashboards for the current project/workspace.

        Calls ``GET /api/app/projects/{pid}/dashboards`` (or workspace-scoped).

        Args:
            ids: Optional list of dashboard IDs to filter. When provided, only
                dashboards matching these IDs are returned.

        Returns:
            List of dashboard dictionaries. Each dictionary contains at minimum
            ``id``, ``title``, and ``created`` fields.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400, 404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                dashboards = client.list_dashboards()
                for d in dashboards:
                    print(f"{d['id']}: {d['title']}")
            ```
        """
        path = self.maybe_scoped_path("dashboards")
        params: dict[str, str] = {}
        if ids:
            params["ids"] = ",".join(str(i) for i in ids)
        result = self.app_request("GET", path, params=params if params else None)
        if not isinstance(result, list):
            raise MixpanelDataError(
                f"Unexpected response from list_dashboards: "
                f"expected list, got {type(result).__name__}",
            )
        return result

    def create_dashboard(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a new dashboard.

        Calls ``POST /api/app/projects/{pid}/dashboards`` (or workspace-scoped).

        Args:
            body: Dashboard creation payload. Must include ``title`` at minimum.
                May also include ``description``, ``layout``, and ``reports``.

        Returns:
            Dictionary representing the newly created dashboard, including
            its ``id`` and other metadata.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid payload or missing required fields (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                dashboard = client.create_dashboard({"title": "My Dashboard"})
                print(f"Created dashboard {dashboard['id']}")
            ```
        """
        path = self.maybe_scoped_path("dashboards")
        result = self.app_request("POST", path, json_body=body)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from create_dashboard: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def get_dashboard(self, dashboard_id: int) -> dict[str, Any]:
        """Get a single dashboard by ID.

        Calls ``GET /api/app/projects/{pid}/dashboards/{dashboard_id}``
        (or workspace-scoped).

        Args:
            dashboard_id: The numeric dashboard identifier.

        Returns:
            Dictionary representing the dashboard, including ``id``, ``title``,
            ``description``, ``layout``, and ``reports``.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404) or invalid ID (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                dashboard = client.get_dashboard(12345)
                print(dashboard["title"])
            ```
        """
        path = self.maybe_scoped_path(f"dashboards/{dashboard_id}")
        result = self.app_request("GET", path)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from get_dashboard: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def update_dashboard(
        self, dashboard_id: int, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing dashboard (partial update).

        Calls ``PATCH /api/app/projects/{pid}/dashboards/{dashboard_id}``
        (or workspace-scoped).

        Args:
            dashboard_id: The numeric dashboard identifier.
            body: Partial update payload. May include ``title``, ``description``,
                ``layout``, or other mutable dashboard fields.

        Returns:
            Dictionary representing the updated dashboard.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404) or invalid payload (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                updated = client.update_dashboard(12345, {"title": "New Title"})
                print(updated["title"])
            ```
        """
        path = self.maybe_scoped_path(f"dashboards/{dashboard_id}")
        result = self.app_request("PATCH", path, json_body=body)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from update_dashboard: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def delete_dashboard(self, dashboard_id: int) -> None:
        """Delete a single dashboard.

        Calls ``DELETE /api/app/projects/{pid}/dashboards/{dashboard_id}``
        (or workspace-scoped).

        Args:
            dashboard_id: The numeric dashboard identifier.

        Returns:
            None.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404) or invalid ID (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.delete_dashboard(12345)
            ```
        """
        path = self.maybe_scoped_path(f"dashboards/{dashboard_id}")
        self.app_request("DELETE", path)

    def bulk_delete_dashboards(self, ids: list[int]) -> None:
        """Delete multiple dashboards at once.

        Calls ``DELETE /api/app/projects/{pid}/dashboards``
        (or workspace-scoped) with a JSON body containing the IDs.

        Args:
            ids: List of dashboard IDs to delete.

        Returns:
            None.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid IDs or API error (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.bulk_delete_dashboards([111, 222, 333])
            ```
        """
        path = self.maybe_scoped_path("dashboards/bulk-delete")
        self.app_request("POST", path, json_body={"dashboard_ids": ids})

    def favorite_dashboard(self, dashboard_id: int) -> None:
        """Mark a dashboard as a favorite for the current user.

        Calls ``POST /api/app/projects/{pid}/dashboards/{dashboard_id}/favorites``
        (or workspace-scoped).

        Args:
            dashboard_id: The numeric dashboard identifier.

        Returns:
            None.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.favorite_dashboard(12345)
            ```
        """
        path = self.maybe_scoped_path(f"dashboards/{dashboard_id}/favorites")
        self.app_request("POST", path)

    def unfavorite_dashboard(self, dashboard_id: int) -> None:
        """Remove a dashboard from the current user's favorites.

        Calls ``DELETE /api/app/projects/{pid}/dashboards/{dashboard_id}/favorites``
        (or workspace-scoped).

        Args:
            dashboard_id: The numeric dashboard identifier.

        Returns:
            None.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.unfavorite_dashboard(12345)
            ```
        """
        path = self.maybe_scoped_path(f"dashboards/{dashboard_id}/favorites")
        self.app_request("DELETE", path)

    def pin_dashboard(self, dashboard_id: int) -> None:
        """Pin a dashboard for the current project/workspace.

        Calls ``POST /api/app/projects/{pid}/dashboards/{dashboard_id}/pin``
        (or workspace-scoped).

        Args:
            dashboard_id: The numeric dashboard identifier.

        Returns:
            None.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.pin_dashboard(12345)
            ```
        """
        path = self.maybe_scoped_path(f"dashboards/{dashboard_id}/pin")
        self.app_request("POST", path)

    def unpin_dashboard(self, dashboard_id: int) -> None:
        """Unpin a dashboard from the current project/workspace.

        Calls ``DELETE /api/app/projects/{pid}/dashboards/{dashboard_id}/pin``
        (or workspace-scoped).

        Args:
            dashboard_id: The numeric dashboard identifier.

        Returns:
            None.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.unpin_dashboard(12345)
            ```
        """
        path = self.maybe_scoped_path(f"dashboards/{dashboard_id}/pin")
        self.app_request("DELETE", path)

    def remove_report_from_dashboard(
        self, dashboard_id: int, bookmark_id: int
    ) -> dict[str, Any] | None:
        """Remove a report (bookmark) from a dashboard.

        Calls ``DELETE /api/app/projects/{pid}/dashboards/{dashboard_id}/reports/{bookmark_id}``
        (or workspace-scoped).

        Args:
            dashboard_id: The numeric dashboard identifier.
            bookmark_id: The numeric bookmark/report identifier to remove.

        Returns:
            Dictionary representing the updated dashboard after report removal,
            or None if the API returned 204 No Content.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard or report not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.remove_report_from_dashboard(12345, 67890)
            ```
        """
        path = self.maybe_scoped_path(f"dashboards/{dashboard_id}")
        body: dict[str, Any] = {
            "content": {
                "action": "delete",
                "content_type": "report",
                "content_id": bookmark_id,
            }
        }
        result = self.app_request("PATCH", path, json_body=body)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from remove_report_from_dashboard: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def list_blueprint_templates(
        self, *, include_reports: bool = False
    ) -> list[dict[str, Any]]:
        """List available dashboard blueprint templates.

        Calls ``GET /api/app/projects/{pid}/dashboards/blueprints``
        (or workspace-scoped).

        Args:
            include_reports: When True, include report details in each
                blueprint template. Defaults to False.

        Returns:
            List of blueprint template dictionaries, each containing
            ``template_type`` and template metadata.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                templates = client.list_blueprint_templates(include_reports=True)
                for t in templates:
                    print(t["template_type"])
            ```
        """
        path = self.maybe_scoped_path("dashboards/blueprints-all")
        params: dict[str, str] = {}
        if include_reports:
            params["include_reports"] = "true"
        result = self.app_request("GET", path, params=params if params else None)
        # The blueprints-all endpoint returns {"templates": {name: data, ...}}
        if isinstance(result, dict) and "templates" in result:
            templates = result["templates"]
            if isinstance(templates, dict):
                # Convert {name: data} to [{...data, "name": name}, ...]
                results: list[dict[str, Any]] = []
                for name, data in templates.items():
                    if isinstance(data, dict):
                        results.append({**data, "name": name})
                    else:
                        logger.warning(
                            "Skipping blueprint template %r: expected dict, got %s",
                            name,
                            type(data).__name__,
                        )
                return results
            if isinstance(templates, list):
                return templates
        if isinstance(result, list):
            return result
        raise MixpanelDataError(
            f"Unexpected response from list_blueprint_templates: "
            f"expected templates dict, got {type(result).__name__}",
        )

    def create_blueprint(self, template_type: str) -> dict[str, Any]:
        """Create a dashboard from a blueprint template.

        Calls ``POST /api/app/projects/{pid}/dashboards/blueprints``
        (or workspace-scoped).

        Args:
            template_type: The blueprint template type identifier
                (e.g., ``"company_kpis"``, ``"marketing"``).

        Returns:
            Dictionary representing the newly created dashboard from the
            blueprint, including its ``id`` and populated reports.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid template type (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                dashboard = client.create_blueprint("company_kpis")
                print(f"Created blueprint dashboard {dashboard['id']}")
            ```
        """
        path = self.maybe_scoped_path("dashboards/blueprints")
        result = self.app_request(
            "POST", path, json_body={"template_type": template_type}
        )
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from create_blueprint: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def get_blueprint_config(self, dashboard_id: int) -> dict[str, Any]:
        """Get the blueprint configuration for a dashboard.

        Calls ``GET /api/app/projects/{pid}/dashboards/{dashboard_id}/blueprint-config``
        (or workspace-scoped).

        Args:
            dashboard_id: The numeric dashboard identifier.

        Returns:
            Dictionary containing the blueprint configuration, including
            template type and customization settings.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found or not a blueprint (404/400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                config = client.get_blueprint_config(12345)
                print(config["template_type"])
            ```
        """
        path = self.maybe_scoped_path(f"dashboards/{dashboard_id}/blueprint-config")
        result = self.app_request("GET", path)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from get_blueprint_config: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def update_blueprint_cohorts(self, cohorts: list[dict[str, Any]]) -> None:
        """Update cohort mappings for blueprint dashboards.

        Calls ``PUT /api/app/projects/{pid}/dashboards/blueprints/cohorts``
        (or workspace-scoped).

        Args:
            cohorts: List of cohort mapping dictionaries. Each entry maps a
                blueprint cohort placeholder to an actual cohort ID.

        Returns:
            None.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid cohort mappings (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.update_blueprint_cohorts([
                    {"placeholder": "new_users", "cohort_id": 42}
                ])
            ```
        """
        path = self.maybe_scoped_path("dashboards/blueprints/cohorts")
        self.app_request("PUT", path, json_body={"cohorts": cohorts})

    def finalize_blueprint(self, body: dict[str, Any]) -> dict[str, Any]:
        """Finalize a blueprint dashboard after configuration.

        Calls ``POST /api/app/projects/{pid}/dashboards/blueprints/finish``
        (or workspace-scoped).

        Args:
            body: Finalization payload containing the blueprint dashboard ID
                and any final configuration overrides.

        Returns:
            Dictionary representing the finalized dashboard.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid payload or blueprint not found (400/404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                result = client.finalize_blueprint({"dashboard_id": 12345})
                print(f"Finalized: {result['id']}")
            ```
        """
        path = self.maybe_scoped_path("dashboards/blueprints/finish")
        result = self.app_request("POST", path, json_body=body)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from finalize_blueprint: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def create_rca_dashboard(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a root-cause-analysis (RCA) dashboard.

        Calls ``POST /api/app/projects/{pid}/dashboards/rca``
        (or workspace-scoped).

        Args:
            body: RCA dashboard creation payload, typically including the
                metric event, time range, and analysis parameters.

        Returns:
            Dictionary representing the newly created RCA dashboard.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid payload (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                rca = client.create_rca_dashboard({
                    "event": "purchase",
                    "from_date": "2025-01-01",
                    "to_date": "2025-01-31",
                })
                print(f"RCA dashboard: {rca['id']}")
            ```
        """
        path = self.maybe_scoped_path("dashboards/rca")
        result = self.app_request("POST", path, json_body=body)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from create_rca_dashboard: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def get_bookmark_dashboard_ids(self, bookmark_id: int) -> list[int]:
        """Get dashboard IDs that contain a specific bookmark/report.

        Calls ``GET /api/app/projects/{pid}/dashboards/bookmarks/{bookmark_id}/dashboard-ids``
        (or workspace-scoped).

        Args:
            bookmark_id: The numeric bookmark/report identifier.

        Returns:
            List of integer dashboard IDs that contain the specified bookmark.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Bookmark not found (404) or invalid ID (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                dashboard_ids = client.get_bookmark_dashboard_ids(67890)
                print(f"Report is on dashboards: {dashboard_ids}")
            ```
        """
        path = self.maybe_scoped_path(
            f"dashboards/bookmarks/{bookmark_id}/dashboard-ids"
        )
        result = self.app_request("GET", path)
        if not isinstance(result, list):
            raise MixpanelDataError(
                f"Unexpected response from get_bookmark_dashboard_ids: "
                f"expected list, got {type(result).__name__}",
            )
        return result

    def get_dashboard_erf(self, dashboard_id: int) -> dict[str, Any]:
        """Get ERF data for a dashboard.

        Calls ``GET /api/app/projects/{pid}/dashboards/{dashboard_id}/erf``
        (or workspace-scoped).

        Args:
            dashboard_id: The numeric dashboard identifier.

        Returns:
            Dictionary containing the ERF data for the dashboard, describing
            the ERF metrics for the dashboard.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard not found (404) or invalid ID (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                erf = client.get_dashboard_erf(12345)
                print(erf)
            ```
        """
        path = self.maybe_scoped_path(f"dashboards/{dashboard_id}/erf")
        result = self.app_request("GET", path)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from get_dashboard_erf: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def update_report_link(
        self, dashboard_id: int, report_link_id: int, body: dict[str, Any]
    ) -> None:
        """Update a report link on a dashboard.

        Calls ``PATCH /api/app/projects/{pid}/dashboards/{dashboard_id}/report-links/{report_link_id}``
        (or workspace-scoped).

        Args:
            dashboard_id: The numeric dashboard identifier.
            report_link_id: The numeric report link identifier.
            body: Partial update payload for the report link (e.g., position,
                size, or display settings).

        Returns:
            None.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard or report link not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.update_report_link(12345, 99, {"position": {"x": 0, "y": 1}})
            ```
        """
        path = self.maybe_scoped_path(
            f"dashboards/{dashboard_id}/report-links/{report_link_id}"
        )
        self.app_request("PATCH", path, json_body=body)

    def update_text_card(
        self, dashboard_id: int, text_card_id: int, body: dict[str, Any]
    ) -> None:
        """Update a text card on a dashboard.

        Calls ``PATCH /api/app/projects/{pid}/dashboards/{dashboard_id}/text-cards/{text_card_id}``
        (or workspace-scoped).

        Args:
            dashboard_id: The numeric dashboard identifier.
            text_card_id: The numeric text card identifier.
            body: Partial update payload for the text card (e.g., ``text``,
                ``position``, or ``size``).

        Returns:
            None.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Dashboard or text card not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.update_text_card(12345, 55, {"text": "Updated heading"})
            ```
        """
        path = self.maybe_scoped_path(
            f"dashboards/{dashboard_id}/text-cards/{text_card_id}"
        )
        self.app_request("PATCH", path, json_body=body)

    # =========================================================================
    # Bookmark/Report CRUD (Phase 024)
    # =========================================================================

    def list_bookmarks_v2(
        self,
        *,
        bookmark_type: str | None = None,
        ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """List bookmarks (saved reports) via the App API.

        Retrieves metadata for saved Insights, Funnels, Retention, Flows,
        and other report types. Supports filtering by type and by explicit
        bookmark IDs.

        Args:
            bookmark_type: Optional report-type filter (e.g., ``"insights"``,
                ``"funnels"``, ``"retention"``).
            ids: Optional list of bookmark IDs to retrieve.

        Returns:
            A list of bookmark dicts, each containing keys such as ``id``,
            ``name``, ``type``, and ``params``.

        Raises:
            AuthenticationError: Invalid or expired credentials (401).
            QueryError: Invalid parameters (400/403).
            RateLimitError: Rate limit exceeded after max retries (429).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                bookmarks = client.list_bookmarks_v2(bookmark_type="funnels")
            ```
        """
        path = self.maybe_scoped_path("bookmarks")
        params: dict[str, str] = {"v": "2"}
        if bookmark_type:
            params["type"] = bookmark_type
        if ids:
            params["ids"] = ",".join(str(i) for i in ids)
        result = self.app_request("GET", path, params=params)
        # v2 envelope: {"results": {"results": [...]}}
        if isinstance(result, dict) and "results" in result:
            inner = result["results"]
            if isinstance(inner, list):
                return inner
        if isinstance(result, list):
            return result
        raise MixpanelDataError(
            f"Unexpected response from list_bookmarks_v2: "
            f"expected list or v2 envelope, got {type(result).__name__}",
        )

    def create_bookmark(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a new bookmark (saved report).

        Args:
            body: Bookmark creation payload with ``name``, ``type``, and
                ``params`` fields.

        Returns:
            The newly created bookmark dict with assigned ``id``.

        Raises:
            AuthenticationError: Invalid or expired credentials (401).
            QueryError: Invalid payload (400/422).
            RateLimitError: Rate limit exceeded after max retries (429).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                bookmark = client.create_bookmark({
                    "name": "Daily Active Users",
                    "type": "insights",
                    "params": {"event": ["login"]},
                })
            ```
        """
        path = self.maybe_scoped_path("bookmarks")
        body_v2 = {**body, "v": 2}
        result = self.app_request("POST", path, json_body=body_v2)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from create_bookmark: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def get_bookmark(self, bookmark_id: int) -> dict[str, Any]:
        """Retrieve a single bookmark by ID.

        Args:
            bookmark_id: Unique identifier of the bookmark.

        Returns:
            Bookmark dict with ``id``, ``name``, ``type``, and ``params``.

        Raises:
            AuthenticationError: Invalid or expired credentials (401).
            QueryError: Bookmark not found (404).
            RateLimitError: Rate limit exceeded after max retries (429).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                bookmark = client.get_bookmark(12345)
            ```
        """
        path = self.maybe_scoped_path(f"bookmarks/{bookmark_id}")
        result = self.app_request("GET", path, params={"v": "2"})
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from get_bookmark: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def update_bookmark(self, bookmark_id: int, body: dict[str, Any]) -> dict[str, Any]:
        """Update an existing bookmark (partial update via PATCH).

        Args:
            bookmark_id: Unique identifier of the bookmark.
            body: Fields to update (e.g., ``name``, ``description``).

        Returns:
            The updated bookmark dict.

        Raises:
            AuthenticationError: Invalid or expired credentials (401).
            QueryError: Bookmark not found or invalid payload (400/404/422).
            RateLimitError: Rate limit exceeded after max retries (429).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                updated = client.update_bookmark(12345, {"name": "Renamed"})
            ```
        """
        path = self.maybe_scoped_path(f"bookmarks/{bookmark_id}")
        body_v2 = {**body, "v": 2}
        result = self.app_request("PATCH", path, json_body=body_v2)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from update_bookmark: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def delete_bookmark(self, bookmark_id: int) -> None:
        """Delete a bookmark (saved report).

        Args:
            bookmark_id: Unique identifier of the bookmark to delete.

        Raises:
            AuthenticationError: Invalid or expired credentials (401).
            QueryError: Bookmark not found (404).
            RateLimitError: Rate limit exceeded after max retries (429).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.delete_bookmark(12345)
            ```
        """
        path = self.maybe_scoped_path(f"bookmarks/{bookmark_id}")
        self.app_request("DELETE", path)

    def bulk_delete_bookmarks(self, ids: list[int]) -> None:
        """Delete multiple bookmarks in a single request.

        Args:
            ids: List of bookmark IDs to delete.

        Raises:
            AuthenticationError: Invalid or expired credentials (401).
            QueryError: One or more IDs not found (400/404).
            RateLimitError: Rate limit exceeded after max retries (429).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.bulk_delete_bookmarks([123, 456])
            ```
        """
        path = self.maybe_scoped_path("bookmarks/bulk-delete")
        self.app_request("POST", path, json_body={"bookmark_ids": ids})

    def bulk_update_bookmarks(self, entries: list[dict[str, Any]]) -> None:
        """Update multiple bookmarks in a single request.

        Args:
            entries: List of update dicts, each with ``id`` and fields to update.

        Raises:
            AuthenticationError: Invalid or expired credentials (401).
            QueryError: Invalid entries or IDs not found (400/404/422).
            RateLimitError: Rate limit exceeded after max retries (429).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.bulk_update_bookmarks([
                    {"id": 123, "name": "Updated Report"},
                ])
            ```
        """
        path = self.maybe_scoped_path("bookmarks/bulk-update")
        self.app_request("POST", path, json_body={"bookmarks": entries})

    def bookmark_linked_dashboard_ids(self, bookmark_id: int) -> list[int]:
        """Get dashboard IDs linked to a bookmark.

        Args:
            bookmark_id: Unique identifier of the bookmark.

        Returns:
            List of integer dashboard IDs. Empty list if not linked.

        Raises:
            AuthenticationError: Invalid or expired credentials (401).
            QueryError: Bookmark not found (404).
            RateLimitError: Rate limit exceeded after max retries (429).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                dash_ids = client.bookmark_linked_dashboard_ids(12345)
            ```
        """
        path = self.maybe_scoped_path(f"bookmarks/{bookmark_id}/linked-dashboard-ids")
        result = self.app_request("GET", path)
        if not isinstance(result, list):
            raise MixpanelDataError(
                f"Unexpected response from bookmark_linked_dashboard_ids: "
                f"expected list, got {type(result).__name__}",
            )
        return result

    def get_bookmark_history(
        self,
        bookmark_id: int,
        *,
        cursor: str | None = None,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """Get the change history for a bookmark.

        Args:
            bookmark_id: Unique identifier of the bookmark.
            cursor: Opaque pagination cursor from a previous call.
            page_size: Maximum entries per page.

        Returns:
            Dict with ``results`` (history entries) and ``pagination``.

        Raises:
            AuthenticationError: Invalid or expired credentials (401).
            QueryError: Bookmark not found (404).
            RateLimitError: Rate limit exceeded after max retries (429).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                page = client.get_bookmark_history(12345, page_size=10)
            ```
        """
        path = self.maybe_scoped_path(f"bookmarks/{bookmark_id}/history")
        params: dict[str, str] = {}
        if cursor:
            params["cursor"] = cursor
        if page_size is not None:
            params["page_size"] = str(page_size)
        result = self.app_request(
            "GET", path, params=params if params else None, _raw=True
        )
        if isinstance(result, dict):
            # The raw response is {"status": "ok", "results": <inner>}.
            # <inner> may be the history dict {"results": [...], "pagination": {...}}
            # or already a list if the API returns results directly.
            inner = result.get("results", result)
            if isinstance(inner, dict) and "results" in inner:
                # inner is {"results": [...], "pagination": {...}} — use as-is
                if "pagination" not in inner:
                    inner["pagination"] = None
                return inner
            if isinstance(inner, list):
                # Flat list of history entries — wrap with pagination
                return {"results": inner, "pagination": None}
            # Unexpected dict shape — return with defaults
            return {"results": inner, "pagination": None}
        if isinstance(result, list):
            return {"results": result, "pagination": None}
        raise MixpanelDataError(
            f"Unexpected response from get_bookmark_history: "
            f"expected dict, got {type(result).__name__}",
        )

    # =========================================================================
    # Cohort CRUD (Phase 024)
    # =========================================================================

    def list_cohorts_app(
        self,
        *,
        data_group_id: str | None = None,
        ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        """List cohorts via the App API.

        Args:
            data_group_id: Optional data group filter.
            ids: Optional list of cohort IDs to retrieve.

        Returns:
            List of cohort dictionaries with ``id``, ``name``, ``count``, etc.

        Raises:
            AuthenticationError: Invalid or missing credentials (401).
            RateLimitError: Rate limit exceeded after max retries (429).
            QueryError: Bad request (400/404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                cohorts = client.list_cohorts_app()
            ```
        """
        path = self.maybe_scoped_path("cohorts")
        params: dict[str, str] = {}
        if data_group_id:
            params["data_group_id"] = data_group_id
        if ids:
            params["ids"] = ",".join(str(i) for i in ids)
        result = self.app_request("GET", path, params=params if params else None)
        if not isinstance(result, list):
            raise MixpanelDataError(
                f"Unexpected response from list_cohorts_app: "
                f"expected list, got {type(result).__name__}",
            )
        return result

    def get_cohort(self, cohort_id: int) -> dict[str, Any]:
        """Get a single cohort by ID via the App API.

        Args:
            cohort_id: Numeric identifier of the cohort.

        Returns:
            Cohort dict with ``id``, ``name``, ``description``, ``count``, etc.

        Raises:
            AuthenticationError: Invalid or missing credentials (401).
            RateLimitError: Rate limit exceeded after max retries (429).
            QueryError: Cohort not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                cohort = client.get_cohort(12345)
            ```
        """
        path = self.maybe_scoped_path(f"cohorts/{cohort_id}")
        result = self.app_request("GET", path)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from get_cohort: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def create_cohort(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a new cohort via the App API.

        Args:
            body: Cohort definition with ``name`` and optional fields.

        Returns:
            The newly created cohort dict with assigned ``id``.

        Raises:
            AuthenticationError: Invalid or missing credentials (401).
            RateLimitError: Rate limit exceeded after max retries (429).
            QueryError: Invalid cohort definition (400).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                cohort = client.create_cohort({"name": "Power Users"})
            ```
        """
        path = self.maybe_scoped_path("cohorts")
        result = self.app_request("POST", path, json_body=body)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from create_cohort: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def update_cohort(self, cohort_id: int, body: dict[str, Any]) -> dict[str, Any]:
        """Update an existing cohort via the App API.

        Args:
            cohort_id: Numeric identifier of the cohort.
            body: Fields to update (e.g., ``name``, ``description``).

        Returns:
            The updated cohort dict.

        Raises:
            AuthenticationError: Invalid or missing credentials (401).
            RateLimitError: Rate limit exceeded after max retries (429).
            QueryError: Cohort not found or invalid update (400/404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                updated = client.update_cohort(12345, {"name": "Renamed"})
            ```
        """
        path = self.maybe_scoped_path(f"cohorts/{cohort_id}")
        result = self.app_request("PATCH", path, json_body=body)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from update_cohort: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def delete_cohort(self, cohort_id: int) -> None:
        """Delete a single cohort via the App API.

        Args:
            cohort_id: Numeric identifier of the cohort to delete.

        Raises:
            AuthenticationError: Invalid or missing credentials (401).
            RateLimitError: Rate limit exceeded after max retries (429).
            QueryError: Cohort not found (404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.delete_cohort(12345)
            ```
        """
        path = self.maybe_scoped_path(f"cohorts/{cohort_id}")
        self.app_request("DELETE", path)

    def bulk_delete_cohorts(self, ids: list[int]) -> None:
        """Delete multiple cohorts in a single request.

        Args:
            ids: List of cohort IDs to delete.

        Raises:
            AuthenticationError: Invalid or missing credentials (401).
            RateLimitError: Rate limit exceeded after max retries (429).
            QueryError: One or more IDs not found (400/404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.bulk_delete_cohorts([123, 456])
            ```
        """
        path = self.maybe_scoped_path("cohorts/bulk-delete")
        self.app_request("POST", path, json_body={"cohort_ids": ids})

    def bulk_update_cohorts(self, entries: list[dict[str, Any]]) -> None:
        """Update multiple cohorts in a single request.

        Args:
            entries: List of cohort update dicts, each with ``id`` and
                fields to update.

        Raises:
            AuthenticationError: Invalid or missing credentials (401).
            RateLimitError: Rate limit exceeded after max retries (429).
            QueryError: Invalid entries or IDs not found (400/404).
            ServerError: Server-side errors (5xx).

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.bulk_update_cohorts([
                    {"id": 123, "name": "Renamed Cohort"},
                ])
            ```
        """
        path = self.maybe_scoped_path("cohorts/bulk-update")
        self.app_request("POST", path, json_body={"cohorts": entries})

    # =========================================================================
    # Feature Flag CRUD (Phase 025)
    # =========================================================================

    def list_feature_flags(
        self, *, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        """List feature flags for the current project/workspace.

        Calls ``GET /api/app/projects/{pid}/workspaces/{wid}/feature-flags/``.

        Args:
            include_archived: When True, include archived flags in results.

        Returns:
            List of feature flag dictionaries.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400, 404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                flags = client.list_feature_flags()
            ```
        """
        path = self.require_scoped_path("feature-flags/")
        params: dict[str, str] = {}
        if include_archived:
            params["include_archived"] = "true"
        result = self.app_request("GET", path, params=params if params else None)
        if not isinstance(result, list):
            raise MixpanelDataError(
                f"Unexpected response from list_feature_flags: "
                f"expected list, got {type(result).__name__}",
            )
        return result

    def create_feature_flag(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a new feature flag.

        Calls ``POST /api/app/projects/{pid}/workspaces/{wid}/feature-flags/``.

        Args:
            body: Flag creation payload with ``name`` and ``key`` required.

        Returns:
            Dictionary representing the newly created flag.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Duplicate key or invalid payload (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                flag = client.create_feature_flag({"name": "X", "key": "x"})
            ```
        """
        path = self.require_scoped_path("feature-flags")
        result = self.app_request("POST", path, json_body=body)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from create_feature_flag: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def get_feature_flag(self, flag_id: str) -> dict[str, Any]:
        """Get a single feature flag by ID.

        Calls ``GET /api/app/projects/{pid}/workspaces/{wid}/feature-flags/{id}/``.

        Args:
            flag_id: Feature flag UUID.

        Returns:
            Dictionary representing the flag.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404) or invalid ID (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                flag = client.get_feature_flag("abc-123")
            ```
        """
        path = self.require_scoped_path(f"feature-flags/{flag_id}/")
        result = self.app_request("GET", path)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from get_feature_flag: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def update_feature_flag(self, flag_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Update a feature flag (full replacement).

        Calls ``PUT /api/app/projects/{pid}/workspaces/{wid}/feature-flags/{id}/``.

        Args:
            flag_id: Feature flag UUID.
            body: Complete flag configuration (PUT semantics).

        Returns:
            Dictionary representing the updated flag.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404) or invalid payload (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                updated = client.update_feature_flag("abc-123", body)
            ```
        """
        path = self.require_scoped_path(f"feature-flags/{flag_id}/")
        result = self.app_request("PUT", path, json_body=body)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from update_feature_flag: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def delete_feature_flag(self, flag_id: str) -> None:
        """Delete a feature flag.

        Calls ``DELETE /api/app/projects/{pid}/workspaces/{wid}/feature-flags/{id}/``.

        Args:
            flag_id: Feature flag UUID.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.delete_feature_flag("abc-123")
            ```
        """
        path = self.require_scoped_path(f"feature-flags/{flag_id}/")
        self.app_request("DELETE", path)

    def archive_feature_flag(self, flag_id: str) -> None:
        """Archive a feature flag (soft-delete).

        Calls ``POST /api/app/projects/{pid}/workspaces/{wid}/feature-flags/{id}/archive/``.

        Args:
            flag_id: Feature flag UUID.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.archive_feature_flag("abc-123")
            ```
        """
        path = self.require_scoped_path(f"feature-flags/{flag_id}/archive/")
        self.app_request("POST", path)

    def restore_feature_flag(self, flag_id: str) -> dict[str, Any]:
        """Restore an archived feature flag.

        Calls ``DELETE /api/app/projects/{pid}/workspaces/{wid}/feature-flags/{id}/archive/``.

        Args:
            flag_id: Feature flag UUID.

        Returns:
            Dictionary representing the restored flag.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                flag = client.restore_feature_flag("abc-123")
            ```
        """
        path = self.require_scoped_path(f"feature-flags/{flag_id}/archive/")
        result = self.app_request("DELETE", path)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from restore_feature_flag: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def duplicate_feature_flag(self, flag_id: str) -> dict[str, Any]:
        """Duplicate a feature flag.

        Calls ``POST /api/app/projects/{pid}/workspaces/{wid}/feature-flags/{id}/duplicate/``.

        Args:
            flag_id: Feature flag UUID.

        Returns:
            Dictionary representing the new duplicate flag.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                dup = client.duplicate_feature_flag("abc-123")
            ```
        """
        path = self.require_scoped_path(f"feature-flags/{flag_id}/duplicate/")
        result = self.app_request("POST", path)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from duplicate_feature_flag: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def set_flag_test_users(self, flag_id: str, body: dict[str, Any]) -> None:
        """Set test user variant overrides for a feature flag.

        Calls ``PUT /api/app/projects/{pid}/workspaces/{wid}/feature-flags/{id}/test-users/``.

        Args:
            flag_id: Feature flag UUID.
            body: Test user mapping (variant key → user distinct ID).

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404) or invalid payload (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.set_flag_test_users("abc-123", {"users": {"on": "uid"}})
            ```
        """
        path = self.require_scoped_path(f"feature-flags/{flag_id}/test-users/")
        self.app_request("PUT", path, json_body=body)

    def get_flag_history(
        self, flag_id: str, *, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Get change history for a feature flag.

        Calls ``GET /api/app/projects/{pid}/workspaces/{wid}/feature-flags/{id}/history/``.

        Args:
            flag_id: Feature flag UUID.
            params: Optional query parameters (page, page_size).

        Returns:
            Dictionary with ``events`` and ``count`` fields.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Flag not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                history = client.get_flag_history("abc-123")
            ```
        """
        path = self.require_scoped_path(f"feature-flags/{flag_id}/history/")
        result = self.app_request("GET", path, params=params)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from get_flag_history: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def get_flag_limits(self) -> dict[str, Any]:
        """Get account-level feature flag limits and usage.

        Calls ``GET /api/app/projects/{pid}/feature-flags/limits/``
        (uses maybe_scoped_path, not require_scoped_path).

        Returns:
            Dictionary with ``limit``, ``is_trial``, ``current_usage``,
            ``contract_status`` fields.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                limits = client.get_flag_limits()
            ```
        """
        path = self.maybe_scoped_path("feature-flags/limits/")
        result = self.app_request("GET", path)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from get_flag_limits: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    # =========================================================================
    # Experiment CRUD & Lifecycle (Phase 025)
    # =========================================================================

    def list_experiments(
        self, *, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        """List experiments for the current project.

        Calls ``GET /api/app/projects/{pid}/experiments/``
        (optionally workspace-scoped).

        Args:
            include_archived: When True, include archived experiments.

        Returns:
            List of experiment dictionaries.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400, 404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                experiments = client.list_experiments()
            ```
        """
        path = self.maybe_scoped_path("experiments/")
        params: dict[str, str] = {}
        if include_archived:
            params["include_archived"] = "true"
        result = self.app_request("GET", path, params=params if params else None)
        if not isinstance(result, list):
            raise MixpanelDataError(
                f"Unexpected response from list_experiments: "
                f"expected list, got {type(result).__name__}",
            )
        return result

    def create_experiment(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a new experiment.

        Calls ``POST /api/app/projects/{pid}/experiments/``
        (optionally workspace-scoped).

        Args:
            body: Experiment creation payload with ``name`` required.

        Returns:
            Dictionary representing the newly created experiment.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid payload (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                exp = client.create_experiment({"name": "Test"})
            ```
        """
        path = self.maybe_scoped_path("experiments/")
        result = self.app_request("POST", path, json_body=body)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from create_experiment: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def get_experiment(self, experiment_id: str) -> dict[str, Any]:
        """Get a single experiment by ID.

        Calls ``GET /api/app/projects/{pid}/experiments/{id}``
        (no trailing slash).

        Args:
            experiment_id: Experiment UUID.

        Returns:
            Dictionary representing the experiment.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Experiment not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                exp = client.get_experiment("xyz-456")
            ```
        """
        path = self.maybe_scoped_path(f"experiments/{experiment_id}")
        result = self.app_request("GET", path)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from get_experiment: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def update_experiment(
        self, experiment_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an experiment (partial update).

        Calls ``PATCH /api/app/projects/{pid}/experiments/{id}``
        (no trailing slash).

        Args:
            experiment_id: Experiment UUID.
            body: Partial update payload (PATCH semantics).

        Returns:
            Dictionary representing the updated experiment.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Experiment not found (404) or invalid payload (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                updated = client.update_experiment("xyz-456", {"name": "New"})
            ```
        """
        path = self.maybe_scoped_path(f"experiments/{experiment_id}")
        result = self.app_request("PATCH", path, json_body=body)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from update_experiment: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def delete_experiment(self, experiment_id: str) -> None:
        """Delete an experiment.

        Calls ``DELETE /api/app/projects/{pid}/experiments/{id}``
        (no trailing slash).

        Args:
            experiment_id: Experiment UUID.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Experiment not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.delete_experiment("xyz-456")
            ```
        """
        path = self.maybe_scoped_path(f"experiments/{experiment_id}")
        self.app_request("DELETE", path)

    def launch_experiment(self, experiment_id: str) -> dict[str, Any]:
        """Launch an experiment (Draft → Active).

        Calls ``PUT /api/app/projects/{pid}/experiments/{id}/launch``
        (no trailing slash).

        Args:
            experiment_id: Experiment UUID.

        Returns:
            Dictionary representing the launched experiment.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid state transition (400) or not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                launched = client.launch_experiment("xyz-456")
            ```
        """
        path = self.maybe_scoped_path(f"experiments/{experiment_id}/launch")
        result = self.app_request("PUT", path)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from launch_experiment: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def conclude_experiment(
        self, experiment_id: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Conclude an experiment (Active → Concluded).

        Always sends a JSON body (empty ``{}`` if no params provided).
        Calls ``PUT /api/app/projects/{pid}/experiments/{id}/force_conclude``
        (no trailing slash).

        Args:
            experiment_id: Experiment UUID.
            body: Optional conclude parameters. Defaults to empty dict.

        Returns:
            Dictionary representing the concluded experiment.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid state transition (400) or not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                concluded = client.conclude_experiment("xyz-456")
            ```
        """
        path = self.maybe_scoped_path(f"experiments/{experiment_id}/force_conclude")
        result = self.app_request("PUT", path, json_body=body or {})
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from conclude_experiment: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def decide_experiment(
        self, experiment_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """Record an experiment decision (Concluded → Success/Fail).

        Calls ``PATCH /api/app/projects/{pid}/experiments/{id}/decide``
        (no trailing slash).

        Args:
            experiment_id: Experiment UUID.
            body: Decision payload with ``success`` required.

        Returns:
            Dictionary representing the decided experiment.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Invalid state transition (400) or not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                decided = client.decide_experiment("xyz-456", {"success": True})
            ```
        """
        path = self.maybe_scoped_path(f"experiments/{experiment_id}/decide")
        result = self.app_request("PATCH", path, json_body=body)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from decide_experiment: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def archive_experiment(self, experiment_id: str) -> None:
        """Archive an experiment.

        Calls ``POST /api/app/projects/{pid}/experiments/{id}/archive``
        (no trailing slash).

        Args:
            experiment_id: Experiment UUID.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Experiment not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                client.archive_experiment("xyz-456")
            ```
        """
        path = self.maybe_scoped_path(f"experiments/{experiment_id}/archive")
        self.app_request("POST", path)

    def restore_experiment(self, experiment_id: str) -> dict[str, Any]:
        """Restore an archived experiment.

        Calls ``DELETE /api/app/projects/{pid}/experiments/{id}/archive``
        (no trailing slash).

        Args:
            experiment_id: Experiment UUID.

        Returns:
            Dictionary representing the restored experiment.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Experiment not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                exp = client.restore_experiment("xyz-456")
            ```
        """
        path = self.maybe_scoped_path(f"experiments/{experiment_id}/archive")
        result = self.app_request("DELETE", path)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from restore_experiment: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def duplicate_experiment(
        self, experiment_id: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Duplicate an experiment.

        Calls ``POST /api/app/projects/{pid}/experiments/{id}/duplicate``
        (no trailing slash).

        Args:
            experiment_id: Experiment UUID.
            body: Optional duplication parameters (e.g. new name).

        Returns:
            Dictionary representing the duplicated experiment.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: Experiment not found (404).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                dup = client.duplicate_experiment("xyz-456", {"name": "Copy"})
            ```
        """
        path = self.maybe_scoped_path(f"experiments/{experiment_id}/duplicate")
        result = self.app_request("POST", path, json_body=body if body else None)
        if not isinstance(result, dict):
            raise MixpanelDataError(
                f"Unexpected response from duplicate_experiment: "
                f"expected dict, got {type(result).__name__}",
            )
        return result

    def list_erf_experiments(self) -> list[dict[str, Any]]:
        """List experiments in ERF (Experiment Results Framework) format.

        Calls ``GET /api/app/projects/{pid}/experiments/erf/``
        (optionally workspace-scoped).

        Returns:
            List of experiment dictionaries in ERF format.

        Raises:
            AuthenticationError: Invalid credentials (401).
            QueryError: API error (400).
            ServerError: Server-side errors (5xx).
            MixpanelDataError: Network/connection errors.

        Example:
            ```python
            with MixpanelAPIClient(credentials) as client:
                erf = client.list_erf_experiments()
            ```
        """
        path = self.maybe_scoped_path("experiments/erf/")
        result = self.app_request("GET", path)
        if not isinstance(result, list):
            raise MixpanelDataError(
                f"Unexpected response from list_erf_experiments: "
                f"expected list, got {type(result).__name__}",
            )
        return result
