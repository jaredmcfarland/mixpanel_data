# ruff: noqa: ARG001, ARG005
"""Integration tests for the OAuth flow, credential resolution, and workspace scoping.

Tests cover end-to-end OAuth login with mocked HTTP, credential resolution
priority (OAuth vs Basic Auth fallthrough), backward-compatibility of
Basic Auth env vars, and workspace resolution with scoped paths.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from mixpanel_data._internal.auth.callback_server import CallbackResult
from mixpanel_data._internal.auth.flow import OAuthFlow
from mixpanel_data._internal.auth.storage import OAuthStorage
from mixpanel_data._internal.auth.token import OAuthClientInfo, OAuthTokens
from mixpanel_data._internal.config import AuthMethod, ConfigManager, Credentials


def _make_token_response(
    access_token: str = "new-access-token",
    refresh_token: str = "new-refresh-token",
    expires_in: int = 3600,
    scope: str = "projects analysis events",
    token_type: str = "Bearer",
) -> dict[str, Any]:
    """Build a mock OAuth token endpoint response.

    Args:
        access_token: The access token value.
        refresh_token: The refresh token value.
        expires_in: Token lifetime in seconds.
        scope: Space-separated scopes.
        token_type: Token type string.

    Returns:
        Dictionary matching the OAuth token endpoint response schema.
    """
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "scope": scope,
        "token_type": token_type,
    }


def _make_registration_response(client_id: str = "test-client-id") -> dict[str, Any]:
    """Build a mock DCR registration response.

    Args:
        client_id: The client identifier to return.

    Returns:
        Dictionary matching the OAuth registration endpoint response schema.
    """
    return {
        "client_id": client_id,
        "redirect_uris": ["http://localhost:19284/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }


class TestFullOAuthFlowEndToEnd:
    """End-to-end integration test for the OAuth flow with mocked HTTP."""

    @patch("mixpanel_data._internal.auth.flow.webbrowser")
    @patch("mixpanel_data._internal.auth.flow.start_callback_server")
    def test_full_oauth_flow_end_to_end(
        self,
        mock_start_callback: MagicMock,
        mock_webbrowser: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Full chain: register, login, save, expire, refresh.

        1. Create OAuthStorage with temp_dir.
        2. Create httpx.MockTransport for registration and token exchange.
        3. Create OAuthFlow with mocked HTTP and storage.
        4. Mock start_callback_server to return a CallbackResult.
        5. Mock webbrowser.open to do nothing.
        6. Call flow.login(project_id="12345").
        7. Verify tokens saved in storage.
        8. Verify tokens have correct project_id.
        9. Create expired tokens, save to storage.
        10. Save client_info to storage.
        11. Mock a refresh token response.
        12. Call flow.get_valid_token(region="us").
        13. Verify auto-refresh happened.
        """
        storage = OAuthStorage(storage_dir=tmp_path)

        # Track which URLs are hit
        request_log: list[str] = []

        def mock_handler(request: httpx.Request) -> httpx.Response:
            """Handle HTTP requests for registration and token exchange.

            Args:
                request: The outgoing HTTP request.

            Returns:
                Mocked response for registration or token endpoints.
            """
            request_log.append(str(request.url))
            url = str(request.url)

            if "mcp/register/" in url:
                return httpx.Response(
                    201,
                    json=_make_registration_response("test-client-abc"),
                )
            if "token/" in url:
                return httpx.Response(
                    200,
                    json=_make_token_response(
                        access_token="fresh-access-token",
                        refresh_token="fresh-refresh-token",
                    ),
                )
            return httpx.Response(404, text="Not found")

        transport = httpx.MockTransport(mock_handler)
        http_client = httpx.Client(transport=transport)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)

        # Mock callback server to return immediately with an auth code
        mock_start_callback.return_value = (
            CallbackResult(code="auth-code-123", state="ignored"),
            19284,
        )
        mock_webbrowser.open.return_value = True

        # Step 6: Call login
        tokens = flow.login(project_id="12345")

        # Step 7: Verify tokens saved
        loaded = storage.load_tokens(region="us")
        assert loaded is not None
        assert loaded.access_token.get_secret_value() == "fresh-access-token"

        # Step 8: Verify project_id
        assert loaded.project_id == "12345"
        assert tokens.project_id == "12345"

        # Step 9: Create expired tokens and save
        expired_tokens = OAuthTokens(
            access_token=SecretStr("expired-access-token"),
            refresh_token=SecretStr("old-refresh-token"),
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            scope="projects analysis events",
            token_type="Bearer",
            project_id="12345",
        )
        storage.save_tokens(expired_tokens, region="us")

        # Step 10: Save client_info
        client_info = OAuthClientInfo(
            client_id="test-client-abc",
            region="us",
            redirect_uri="http://localhost:19284/callback",
            scope="projects analysis events",
            created_at=datetime.now(timezone.utc),
        )
        storage.save_client_info(client_info)

        # Step 11: The mock_handler already handles refresh via token/ endpoint
        # Clear request_log to track only the refresh call
        request_log.clear()

        # Step 12: Call get_valid_token — should auto-refresh
        new_token = flow.get_valid_token(region="us")

        # Step 13: Verify auto-refresh happened
        assert new_token == "fresh-access-token"
        token_requests = [u for u in request_log if "token/" in u]
        assert len(token_requests) >= 1, "Expected a token refresh request"

        # Verify refreshed tokens are persisted
        refreshed = storage.load_tokens(region="us")
        assert refreshed is not None
        assert refreshed.access_token.get_secret_value() == "fresh-access-token"


class TestCredentialResolutionOAuthFallthrough:
    """Tests for OAuth-to-Basic credential fallthrough."""

    def test_credential_resolution_oauth_fallthrough(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """OAuth tokens are preferred; when removed, falls through to config.

        1. Create temp config dir and temp oauth storage dir.
        2. Store valid OAuth tokens with project_id="99999".
        3. Set MP_PROJECT_ID=99999, MP_REGION=us.
        4. Create ConfigManager with temp config path.
        5. Add a basic auth account to config.
        6. Call resolve_credentials() — assert OAuth.
        7. Remove token files.
        8. Call resolve_credentials() again — assert Basic.
        """
        config_path = tmp_path / "config" / "config.toml"
        oauth_dir = tmp_path / "oauth"
        oauth_dir.mkdir(parents=True, exist_ok=True)

        # Step 2: Store valid OAuth tokens
        storage = OAuthStorage(storage_dir=oauth_dir)
        tokens = OAuthTokens(
            access_token=SecretStr("my-oauth-token"),
            refresh_token=SecretStr("my-refresh-token"),
            expires_at=datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
            scope="projects analysis events",
            token_type="Bearer",
            project_id="99999",
        )
        storage.save_tokens(tokens, region="us")

        # Step 3: Set env vars (partial — no MP_USERNAME/MP_SECRET)
        monkeypatch.setenv("MP_PROJECT_ID", "99999")
        monkeypatch.setenv("MP_REGION", "us")
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)
        monkeypatch.delenv("MP_CONFIG_PATH", raising=False)

        # Step 4-5: Create ConfigManager and add basic account
        config = ConfigManager(config_path=config_path)
        config.add_account(
            name="default",
            username="sa-user",
            secret="sa-secret",
            project_id="99999",
            region="us",
        )

        # Step 6: Resolve credentials — expect OAuth
        creds = config.resolve_credentials(_oauth_storage_dir=oauth_dir)
        assert creds.auth_method == AuthMethod.oauth
        assert creds.project_id == "99999"

        # Step 7: Remove token files
        for f in oauth_dir.glob("*.json"):
            f.unlink()

        # Step 8: Resolve credentials again — expect Basic
        creds2 = config.resolve_credentials(_oauth_storage_dir=oauth_dir)
        assert creds2.auth_method == AuthMethod.basic
        assert creds2.project_id == "99999"


class TestBackwardCompatBasicAuthUnaffected:
    """Verifies that Basic Auth env vars take priority over stored OAuth tokens."""

    def test_backward_compat_basic_auth_unaffected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Env-var-based Basic Auth takes priority even when OAuth tokens exist.

        1. Set all 4 env vars: MP_USERNAME, MP_SECRET, MP_PROJECT_ID, MP_REGION.
        2. Store OAuth tokens (to verify env vars take priority).
        3. Call resolve_credentials().
        4. Assert auth_method == AuthMethod.basic.
        5. Assert auth_header() starts with "Basic ".
        """
        # Step 1: Set all env vars
        monkeypatch.setenv("MP_USERNAME", "env-user")
        monkeypatch.setenv("MP_SECRET", "env-secret")
        monkeypatch.setenv("MP_PROJECT_ID", "77777")
        monkeypatch.setenv("MP_REGION", "us")
        monkeypatch.delenv("MP_CONFIG_PATH", raising=False)

        # Step 2: Store OAuth tokens
        oauth_dir = tmp_path / "oauth"
        oauth_dir.mkdir(parents=True, exist_ok=True)
        storage = OAuthStorage(storage_dir=oauth_dir)
        tokens = OAuthTokens(
            access_token=SecretStr("should-not-be-used"),
            expires_at=datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
            scope="projects",
            token_type="Bearer",
            project_id="77777",
        )
        storage.save_tokens(tokens, region="us")

        # Step 3: Resolve credentials
        config = ConfigManager(config_path=tmp_path / "config.toml")
        creds = config.resolve_credentials(_oauth_storage_dir=oauth_dir)

        # Step 4: Assert Basic Auth
        assert creds.auth_method == AuthMethod.basic

        # Step 5: Assert auth_header starts with "Basic "
        assert creds.auth_header().startswith("Basic ")


class TestWorkspaceResolvePlusScopedPath:
    """Tests workspace resolution and scoped path building."""

    def test_workspace_resolve_plus_scoped_path(self) -> None:
        """Resolve workspace ID and build scoped path.

        1. Create mock credentials (OAuth).
        2. Create MixpanelAPIClient with MockTransport.
        3. Mock list_workspaces to return one workspace (id=42, is_default=True).
        4. Call client.resolve_workspace_id().
        5. Assert returns 42.
        6. Call client.maybe_scoped_path("dashboards").
        7. Assert path contains /workspaces/42/dashboards.
        """
        from mixpanel_data._internal.api_client import MixpanelAPIClient

        creds = Credentials(
            username="",
            secret=SecretStr(""),
            project_id="12345",
            region="us",
            auth_method=AuthMethod.oauth,
            oauth_access_token=SecretStr("test-oauth-token"),
        )

        def mock_handler(request: httpx.Request) -> httpx.Response:
            """Handle workspace listing requests.

            Args:
                request: The outgoing HTTP request.

            Returns:
                Mocked response with a single default workspace.
            """
            url = str(request.url)
            if "workspaces/public" in url:
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "id": 42,
                                "name": "Default Workspace",
                                "project_id": 12345,
                                "is_default": True,
                                "description": "",
                                "is_global": False,
                                "is_restricted": False,
                                "is_visible": True,
                            }
                        ]
                    },
                )
            return httpx.Response(404, text="Not found")

        transport = httpx.MockTransport(mock_handler)

        client = MixpanelAPIClient(creds, _transport=transport)
        client.__enter__()

        try:
            # Step 4-5: Resolve workspace
            ws_id = client.resolve_workspace_id()
            assert ws_id == 42

            # Step 6-7: Now set the workspace_id and check scoped path
            client.set_workspace_id(42)
            path = client.maybe_scoped_path("dashboards")
            assert "/workspaces/42/dashboards" in path
        finally:
            client.__exit__(None, None, None)
