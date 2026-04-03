"""Unit tests for Workspace OAuth integration (T034).

Integration tests for Workspace construction with OAuth tokens and
workspace management methods (list_workspaces, resolve_workspace_id,
set_workspace_id, workspace_id property).

Verifies:
- Workspace construction with OAuth credentials
- list_workspaces() delegates to api_client
- resolve_workspace_id() delegates to api_client
- set_workspace_id() delegates to api_client
- workspace_id property returns current workspace id
- Backward compatibility with Basic Auth Workspace usage
"""
# ruff: noqa: ARG001, ARG005

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from mixpanel_data._internal.api_client import MixpanelAPIClient
from mixpanel_data._internal.auth.storage import OAuthStorage
from mixpanel_data._internal.auth.token import OAuthTokens
from mixpanel_data._internal.config import (
    AuthMethod,
    ConfigManager,
    Credentials,
)
from mixpanel_data.types import PublicWorkspace
from mixpanel_data.workspace import Workspace


def _make_oauth_credentials(
    project_id: str = "12345",
    region: str = "us",
    access_token: str = "test-oauth-token",
) -> Credentials:
    """Create OAuth Credentials for testing.

    Args:
        project_id: Mixpanel project ID.
        region: Data residency region.
        access_token: OAuth access token.

    Returns:
        A Credentials instance with auth_method=oauth.
    """
    return Credentials(
        username="",
        secret=SecretStr(""),
        project_id=project_id,
        region=region,
        auth_method=AuthMethod.oauth,
        oauth_access_token=SecretStr(access_token),
    )


def _make_basic_credentials(
    project_id: str = "12345",
    region: str = "us",
) -> Credentials:
    """Create Basic Auth Credentials for testing.

    Args:
        project_id: Mixpanel project ID.
        region: Data residency region.

    Returns:
        A Credentials instance with auth_method=basic.
    """
    return Credentials(
        username="test_user",
        secret=SecretStr("test_secret"),
        project_id=project_id,
        region=region,
    )


def _workspaces_json() -> list[dict[str, Any]]:
    """Return a sample list of workspace dicts for mock responses.

    Returns:
        List of workspace dictionaries matching the Mixpanel API format.
    """
    return [
        {
            "id": 100,
            "name": "Default Workspace",
            "project_id": 12345,
            "is_default": True,
            "description": "The default workspace",
            "is_global": False,
            "is_restricted": False,
            "is_visible": True,
            "created_iso": "2024-01-01T00:00:00Z",
            "creator_name": "Admin",
        },
        {
            "id": 200,
            "name": "Dev Workspace",
            "project_id": 12345,
            "is_default": False,
            "description": "Development workspace",
            "is_global": False,
            "is_restricted": False,
            "is_visible": True,
            "created_iso": "2024-02-01T00:00:00Z",
            "creator_name": "Dev",
        },
    ]


def _make_workspace_handler() -> Callable[[httpx.Request], httpx.Response]:
    """Create a mock HTTP handler that returns workspace list responses.

    Returns:
        A handler function for httpx.MockTransport.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        """Handle mock HTTP requests for workspace endpoints.

        Args:
            request: The incoming HTTP request.

        Returns:
            Mock response with workspace data for workspace paths,
            404 for unrecognized paths.
        """
        url_path = request.url.path
        if "workspaces/public" in url_path:
            return httpx.Response(
                200,
                json={"results": _workspaces_json(), "status": "ok"},
            )
        return httpx.Response(404, json={"error": "not found"})

    return handler


def _setup_config_with_account(temp_dir: Path) -> ConfigManager:
    """Create a ConfigManager with a dummy account for credential resolution.

    Args:
        temp_dir: Temporary directory for the config file.

    Returns:
        ConfigManager with a test account configured.
    """
    cm = ConfigManager(config_path=temp_dir / "config.toml")
    cm.add_account(
        name="test",
        username="test_user",
        secret="test_secret",
        project_id="12345",
        region="us",
    )
    return cm


class TestWorkspaceConstructionWithOAuth:
    """Tests for Workspace construction with OAuth credentials."""

    def test_workspace_with_oauth_credentials(
        self,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Workspace can be constructed with OAuth credentials.

        Uses OAuth tokens stored on disk and partial env vars to resolve
        OAuth credentials during Workspace construction.
        """
        # Set up OAuth tokens on disk
        oauth_dir = temp_dir / "oauth"
        oauth_storage = OAuthStorage(storage_dir=oauth_dir)
        tokens = OAuthTokens(
            access_token=SecretStr("test-oauth-token"),
            refresh_token=SecretStr("test-refresh"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scope="read:project",
            token_type="Bearer",
            project_id="12345",
        )
        oauth_storage.save_tokens(tokens, region="us")

        # Use partial env vars (project_id + region but NO username/secret)
        # and point OAuth storage to our temp dir
        monkeypatch.setenv("MP_PROJECT_ID", "12345")
        monkeypatch.setenv("MP_REGION", "us")
        monkeypatch.setenv("MP_OAUTH_STORAGE_DIR", str(oauth_dir))

        oauth_creds = _make_oauth_credentials()
        transport = httpx.MockTransport(_make_workspace_handler())
        client = MixpanelAPIClient(oauth_creds, _transport=transport)
        cm = ConfigManager(config_path=temp_dir / "config.toml")
        ws = Workspace(
            _config_manager=cm,
            _api_client=client,
        )

        # The workspace should have resolved OAuth credentials
        assert ws._credentials is not None
        assert ws._credentials.auth_method == AuthMethod.oauth

    def test_workspace_backward_compat_basic_auth(
        self,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Workspace still works with Basic Auth credentials (regression)."""
        # Isolate OAuth storage so real tokens on the machine are not found
        oauth_dir = temp_dir / "empty_oauth"
        oauth_dir.mkdir()
        monkeypatch.setenv("MP_OAUTH_STORAGE_DIR", str(oauth_dir))

        basic_creds = _make_basic_credentials()
        transport = httpx.MockTransport(lambda _r: httpx.Response(200, json=[]))
        client = MixpanelAPIClient(basic_creds, _transport=transport)
        cm = _setup_config_with_account(temp_dir)

        ws = Workspace(
            _config_manager=cm,
            _api_client=client,
        )

        assert ws._credentials is not None
        assert ws._credentials.auth_method == AuthMethod.basic
        assert ws._credentials.username == "test_user"


class TestWorkspaceListWorkspaces:
    """Tests for Workspace.list_workspaces()."""

    def test_list_workspaces_returns_workspace_models(
        self,
        temp_dir: Path,
    ) -> None:
        """list_workspaces() returns a list of PublicWorkspace objects."""
        oauth_creds = _make_oauth_credentials()
        transport = httpx.MockTransport(_make_workspace_handler())
        client = MixpanelAPIClient(oauth_creds, _transport=transport)
        ws = Workspace(
            _config_manager=_setup_config_with_account(temp_dir),
            _api_client=client,
        )

        workspaces = ws.list_workspaces()

        assert len(workspaces) == 2
        assert isinstance(workspaces[0], PublicWorkspace)
        assert workspaces[0].name == "Default Workspace"
        assert workspaces[0].id == 100
        assert workspaces[0].is_default is True
        assert workspaces[1].id == 200

    def test_list_workspaces_empty(
        self,
        temp_dir: Path,
    ) -> None:
        """list_workspaces() returns empty list when no workspaces exist."""

        def handler(request: httpx.Request) -> httpx.Response:
            """Return empty workspace list.

            Args:
                _request: The HTTP request (unused).

            Returns:
                Response with empty results.
            """
            return httpx.Response(
                200,
                json={"results": [], "status": "ok"},
            )

        oauth_creds = _make_oauth_credentials()
        transport = httpx.MockTransport(handler)
        client = MixpanelAPIClient(oauth_creds, _transport=transport)
        ws = Workspace(
            _config_manager=_setup_config_with_account(temp_dir),
            _api_client=client,
        )

        workspaces = ws.list_workspaces()
        assert workspaces == []


class TestWorkspaceResolveWorkspaceId:
    """Tests for Workspace.resolve_workspace_id()."""

    def test_resolve_workspace_id_returns_default(
        self,
        temp_dir: Path,
    ) -> None:
        """resolve_workspace_id() returns the default workspace ID."""
        oauth_creds = _make_oauth_credentials()
        transport = httpx.MockTransport(_make_workspace_handler())
        client = MixpanelAPIClient(oauth_creds, _transport=transport)
        ws = Workspace(
            _config_manager=_setup_config_with_account(temp_dir),
            _api_client=client,
        )

        ws_id = ws.resolve_workspace_id()
        assert ws_id == 100  # The default workspace


class TestWorkspaceSetWorkspaceId:
    """Tests for Workspace.set_workspace_id() and workspace_id property."""

    def test_set_and_get_workspace_id(
        self,
        temp_dir: Path,
    ) -> None:
        """set_workspace_id() sets the workspace_id readable from property."""
        oauth_creds = _make_oauth_credentials()
        transport = httpx.MockTransport(_make_workspace_handler())
        client = MixpanelAPIClient(oauth_creds, _transport=transport)
        ws = Workspace(
            _config_manager=_setup_config_with_account(temp_dir),
            _api_client=client,
        )

        ws.set_workspace_id(42)
        assert ws.workspace_id == 42

    def test_workspace_id_initially_none(
        self,
        temp_dir: Path,
    ) -> None:
        """workspace_id is None before any workspace is set."""
        oauth_creds = _make_oauth_credentials()
        transport = httpx.MockTransport(_make_workspace_handler())
        client = MixpanelAPIClient(oauth_creds, _transport=transport)
        ws = Workspace(
            _config_manager=_setup_config_with_account(temp_dir),
            _api_client=client,
        )

        assert ws.workspace_id is None

    def test_clear_workspace_id(
        self,
        temp_dir: Path,
    ) -> None:
        """set_workspace_id(None) clears the workspace_id."""
        oauth_creds = _make_oauth_credentials()
        transport = httpx.MockTransport(_make_workspace_handler())
        client = MixpanelAPIClient(oauth_creds, _transport=transport)
        ws = Workspace(
            _config_manager=_setup_config_with_account(temp_dir),
            _api_client=client,
        )

        ws.set_workspace_id(42)
        assert ws.workspace_id == 42

        ws.set_workspace_id(None)
        assert ws.workspace_id is None

    def test_workspace_id_constructor_param(
        self,
        temp_dir: Path,
    ) -> None:
        """Workspace constructor accepts workspace_id parameter."""
        oauth_creds = _make_oauth_credentials()
        transport = httpx.MockTransport(_make_workspace_handler())
        client = MixpanelAPIClient(oauth_creds, _transport=transport)
        ws = Workspace(
            _config_manager=_setup_config_with_account(temp_dir),
            _api_client=client,
            workspace_id=999,
        )

        assert ws.workspace_id == 999
