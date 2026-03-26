"""Unit tests for OAuthFlow orchestrator (T019).

Tests the OAuthFlow class which orchestrates the full OAuth 2.0 PKCE
authorization flow for Mixpanel.

Verifies:
- Full login sequence (mock all external deps)
- Token exchange POST with correct form params
- Handles missing refresh_token
- Preserves project_id through flow
- Region-specific OAuth base URLs (us/eu/in)
"""
# ruff: noqa: ARG001, ARG005

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from mixpanel_data._internal.auth.callback_server import CallbackResult
from mixpanel_data._internal.auth.flow import OAuthFlow
from mixpanel_data._internal.auth.storage import OAuthStorage
from mixpanel_data._internal.auth.token import OAuthClientInfo, OAuthTokens
from mixpanel_data.exceptions import OAuthError


def _make_token_response(
    *,
    access_token: str = "access-tok-123",
    refresh_token: str | None = "refresh-tok-456",
    expires_in: int = 3600,
    scope: str = "projects analysis",
    token_type: str = "Bearer",
) -> dict[str, object]:
    """Create a mock token endpoint response dict.

    Args:
        access_token: Access token value.
        refresh_token: Refresh token value, or None to omit.
        expires_in: Token lifetime in seconds.
        scope: Granted scopes.
        token_type: Token type string.

    Returns:
        Dictionary matching the OAuth token endpoint response shape.
    """
    data: dict[str, object] = {
        "access_token": access_token,
        "expires_in": expires_in,
        "scope": scope,
        "token_type": token_type,
    }
    if refresh_token is not None:
        data["refresh_token"] = refresh_token
    return data


def _make_client_info(
    *,
    client_id: str = "test-client-id",
    region: str = "us",
    redirect_uri: str = "http://localhost:19284/callback",
) -> OAuthClientInfo:
    """Create an OAuthClientInfo fixture.

    Args:
        client_id: Client identifier.
        region: Mixpanel region.
        redirect_uri: Registered redirect URI.

    Returns:
        Configured OAuthClientInfo instance.
    """
    return OAuthClientInfo(
        client_id=client_id,
        region=region,
        redirect_uri=redirect_uri,
        scope="projects analysis",
        created_at=datetime.now(timezone.utc),
    )


class TestOAuthFlowLogin:
    """Tests for OAuthFlow.login() full sequence."""

    @patch("mixpanel_data._internal.auth.flow.webbrowser")
    @patch("mixpanel_data._internal.auth.flow.start_callback_server")
    @patch("mixpanel_data._internal.auth.flow.ensure_client_registered")
    def test_full_login_sequence(
        self,
        mock_register: MagicMock,
        mock_callback: MagicMock,
        mock_browser: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify the full login flow: register -> browser -> callback -> exchange.

        Mocks client registration, callback server, browser open, and token exchange.
        """
        # Setup mocks
        client_info = _make_client_info()
        mock_register.return_value = client_info
        mock_callback.return_value = (
            CallbackResult(code="auth-code-xyz", state="any"),
            19284,
        )
        mock_browser.open.return_value = True

        token_response = _make_token_response()

        def handle_request(request: httpx.Request) -> httpx.Response:
            """Handle token exchange request.

            Args:
                request: The incoming HTTP request.

            Returns:
                Mock token response.
            """
            return httpx.Response(200, json=token_response)

        transport = httpx.MockTransport(handle_request)
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        tokens = flow.login(project_id="12345")

        assert tokens.access_token.get_secret_value() == "access-tok-123"
        assert tokens.refresh_token is not None
        assert tokens.refresh_token.get_secret_value() == "refresh-tok-456"
        assert tokens.project_id == "12345"
        mock_browser.open.assert_called_once()

    @patch("mixpanel_data._internal.auth.flow.webbrowser")
    @patch("mixpanel_data._internal.auth.flow.start_callback_server")
    @patch("mixpanel_data._internal.auth.flow.ensure_client_registered")
    def test_preserves_project_id(
        self,
        mock_register: MagicMock,
        mock_callback: MagicMock,
        mock_browser: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify that project_id is passed through to the resulting tokens."""
        mock_register.return_value = _make_client_info()
        mock_callback.return_value = (
            CallbackResult(code="code1", state="s"),
            19284,
        )
        mock_browser.open.return_value = True

        transport = httpx.MockTransport(
            lambda _req: httpx.Response(200, json=_make_token_response())
        )
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        tokens = flow.login(project_id="proj-999")

        assert tokens.project_id == "proj-999"

    @patch("mixpanel_data._internal.auth.flow.webbrowser")
    @patch("mixpanel_data._internal.auth.flow.start_callback_server")
    @patch("mixpanel_data._internal.auth.flow.ensure_client_registered")
    def test_handles_missing_refresh_token(
        self,
        mock_register: MagicMock,
        mock_callback: MagicMock,
        mock_browser: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify login succeeds when the token response has no refresh_token."""
        mock_register.return_value = _make_client_info()
        mock_callback.return_value = (
            CallbackResult(code="code1", state="s"),
            19284,
        )
        mock_browser.open.return_value = True

        token_resp = _make_token_response(refresh_token=None)
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(200, json=token_resp)
        )
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        tokens = flow.login()

        assert tokens.access_token.get_secret_value() == "access-tok-123"
        assert tokens.refresh_token is None


class TestOAuthFlowTokenExchange:
    """Tests for the token exchange step."""

    def test_exchange_posts_correct_form_params(self, tmp_path: Path) -> None:
        """Verify the token exchange POST contains the correct form parameters.

        Must include grant_type, code, redirect_uri, client_id, code_verifier.
        """
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            """Capture request and return token response.

            Args:
                request: The incoming request.

            Returns:
                Mock token response.
            """
            captured_requests.append(request)
            return httpx.Response(200, json=_make_token_response())

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        flow.exchange_code(
            code="auth-code",
            verifier="test-verifier-string",
            client_id="my-client",
            redirect_uri="http://localhost:19284/callback",
        )

        assert len(captured_requests) == 1
        req = captured_requests[0]
        assert req.method == "POST"
        # Parse form body
        body = req.content.decode("utf-8")
        assert "grant_type=authorization_code" in body
        assert "code=auth-code" in body
        assert "client_id=my-client" in body
        assert "code_verifier=test-verifier-string" in body
        assert "redirect_uri=" in body

    def test_exchange_uses_correct_url_for_region(self, tmp_path: Path) -> None:
        """Verify the token exchange URL is region-specific."""
        captured_urls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            """Capture URL and return token response.

            Args:
                request: The incoming request.

            Returns:
                Mock token response.
            """
            captured_urls.append(str(request.url))
            return httpx.Response(200, json=_make_token_response())

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(transport=transport)

        for region, expected_host in [
            ("us", "mixpanel.com"),
            ("eu", "eu.mixpanel.com"),
            ("in", "in.mixpanel.com"),
        ]:
            captured_urls.clear()
            storage = OAuthStorage(storage_dir=tmp_path / region)
            flow = OAuthFlow(region=region, storage=storage, http_client=http_client)
            flow.exchange_code(
                code="c",
                verifier="v",
                client_id="cid",
                redirect_uri="http://localhost:19284/callback",
            )
            assert expected_host in captured_urls[0]
            assert (
                "/oauth/token/" in captured_urls[0]
                or "/oauth/token" in captured_urls[0]
            )

    def test_exchange_error_raises_oauth_error(self, tmp_path: Path) -> None:
        """Verify that a failed token exchange raises OAuthError."""
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(
                400, json={"error": "invalid_grant", "error_description": "Bad code"}
            )
        )
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        with pytest.raises(OAuthError) as exc_info:
            flow.exchange_code(
                code="bad-code",
                verifier="v",
                client_id="cid",
                redirect_uri="http://localhost:19284/callback",
            )
        assert exc_info.value.code == "OAUTH_TOKEN_ERROR"


class TestOAuthFlowRefresh:
    """Tests for OAuthFlow.refresh_tokens()."""

    def test_refresh_posts_correct_params(self, tmp_path: Path) -> None:
        """Verify the refresh POST contains grant_type=refresh_token and client_id."""
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            """Capture request and return token response.

            Args:
                request: The incoming request.

            Returns:
                Mock token response.
            """
            captured_requests.append(request)
            return httpx.Response(200, json=_make_token_response())

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        tokens = OAuthTokens(
            access_token=SecretStr("old-access"),
            refresh_token=SecretStr("old-refresh"),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scope="projects",
            token_type="Bearer",
            project_id="123",
        )

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        new_tokens = flow.refresh_tokens(tokens=tokens, client_id="cid")

        assert len(captured_requests) == 1
        body = captured_requests[0].content.decode("utf-8")
        assert "grant_type=refresh_token" in body
        assert "refresh_token=old-refresh" in body
        assert "client_id=cid" in body
        assert new_tokens.access_token.get_secret_value() == "access-tok-123"

    def test_refresh_error_raises_oauth_error(self, tmp_path: Path) -> None:
        """Verify that a failed refresh raises OAuthError with OAUTH_REFRESH_ERROR."""
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(400, json={"error": "invalid_grant"})
        )
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        tokens = OAuthTokens(
            access_token=SecretStr("old"),
            refresh_token=SecretStr("bad-refresh"),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scope="projects",
            token_type="Bearer",
        )

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        with pytest.raises(OAuthError) as exc_info:
            flow.refresh_tokens(tokens=tokens, client_id="cid")
        assert exc_info.value.code == "OAUTH_REFRESH_ERROR"

    def test_refresh_without_refresh_token_raises(self, tmp_path: Path) -> None:
        """Verify that refreshing without a refresh_token raises OAuthError."""
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(200, json=_make_token_response())
        )
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        tokens = OAuthTokens(
            access_token=SecretStr("old"),
            refresh_token=None,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scope="projects",
            token_type="Bearer",
        )

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        with pytest.raises(OAuthError) as exc_info:
            flow.refresh_tokens(tokens=tokens, client_id="cid")
        assert exc_info.value.code == "OAUTH_REFRESH_ERROR"


class TestOAuthFlowGetValidToken:
    """Tests for OAuthFlow.get_valid_token() token lifecycle management."""

    def test_returns_current_token_if_not_expired(self, tmp_path: Path) -> None:
        """Verify that a non-expired token is returned immediately without refresh."""
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(500, text="should not be called")
        )
        http_client = httpx.Client(transport=transport)

        storage = OAuthStorage(storage_dir=tmp_path)
        valid_tokens = OAuthTokens(
            access_token=SecretStr("valid-access-token"),
            refresh_token=SecretStr("valid-refresh-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scope="projects analysis",
            token_type="Bearer",
            project_id="12345",
        )
        client_info = _make_client_info()
        storage.save_tokens(valid_tokens, region="us")
        storage.save_client_info(client_info)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        result = flow.get_valid_token(region="us")

        assert result == "valid-access-token"

    def test_auto_refreshes_expired_token(self, tmp_path: Path) -> None:
        """Verify that an expired token triggers a refresh and returns the new token."""
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(200, json=_make_token_response())
        )
        http_client = httpx.Client(transport=transport)

        storage = OAuthStorage(storage_dir=tmp_path)
        expired_tokens = OAuthTokens(
            access_token=SecretStr("expired-access"),
            refresh_token=SecretStr("valid-refresh"),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scope="projects analysis",
            token_type="Bearer",
            project_id="12345",
        )
        client_info = _make_client_info()
        storage.save_tokens(expired_tokens, region="us")
        storage.save_client_info(client_info)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        result = flow.get_valid_token(region="us")

        assert result == "access-tok-123"

    def test_persists_refreshed_tokens(self, tmp_path: Path) -> None:
        """Verify that refreshed tokens are saved back to storage."""
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(200, json=_make_token_response())
        )
        http_client = httpx.Client(transport=transport)

        storage = OAuthStorage(storage_dir=tmp_path)
        expired_tokens = OAuthTokens(
            access_token=SecretStr("expired-access"),
            refresh_token=SecretStr("valid-refresh"),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scope="projects analysis",
            token_type="Bearer",
            project_id="12345",
        )
        client_info = _make_client_info()
        storage.save_tokens(expired_tokens, region="us")
        storage.save_client_info(client_info)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        flow.get_valid_token(region="us")

        # Verify the new token was persisted
        reloaded = storage.load_tokens(region="us")
        assert reloaded is not None
        assert reloaded.access_token.get_secret_value() == "access-tok-123"

    def test_raises_oauth_error_if_refresh_fails(self, tmp_path: Path) -> None:
        """Verify that a failed refresh raises OAuthError with OAUTH_REFRESH_ERROR."""
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(400, json={"error": "invalid_grant"})
        )
        http_client = httpx.Client(transport=transport)

        storage = OAuthStorage(storage_dir=tmp_path)
        expired_tokens = OAuthTokens(
            access_token=SecretStr("expired-access"),
            refresh_token=SecretStr("bad-refresh"),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scope="projects analysis",
            token_type="Bearer",
        )
        client_info = _make_client_info()
        storage.save_tokens(expired_tokens, region="us")
        storage.save_client_info(client_info)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        with pytest.raises(OAuthError) as exc_info:
            flow.get_valid_token(region="us")
        assert exc_info.value.code == "OAUTH_REFRESH_ERROR"

    def test_raises_oauth_error_if_no_tokens_exist(self, tmp_path: Path) -> None:
        """Verify that missing tokens raises OAuthError with OAUTH_TOKEN_ERROR."""
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(500, text="should not be called")
        )
        http_client = httpx.Client(transport=transport)

        storage = OAuthStorage(storage_dir=tmp_path)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        with pytest.raises(OAuthError) as exc_info:
            flow.get_valid_token(region="us")
        assert exc_info.value.code == "OAUTH_TOKEN_ERROR"

    def test_raises_oauth_error_if_no_client_info_for_refresh(
        self, tmp_path: Path
    ) -> None:
        """Verify error when tokens are expired but no client info exists for refresh."""
        transport = httpx.MockTransport(
            lambda _req: httpx.Response(200, json=_make_token_response())
        )
        http_client = httpx.Client(transport=transport)

        storage = OAuthStorage(storage_dir=tmp_path)
        expired_tokens = OAuthTokens(
            access_token=SecretStr("expired-access"),
            refresh_token=SecretStr("valid-refresh"),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scope="projects analysis",
            token_type="Bearer",
        )
        storage.save_tokens(expired_tokens, region="us")
        # Intentionally NOT saving client_info

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        with pytest.raises(OAuthError) as exc_info:
            flow.get_valid_token(region="us")
        assert exc_info.value.code == "OAUTH_REFRESH_ERROR"


class TestOAuthFlowRegionUrls:
    """Tests for region-specific OAuth base URLs."""

    @patch("mixpanel_data._internal.auth.flow.webbrowser")
    @patch("mixpanel_data._internal.auth.flow.start_callback_server")
    @patch("mixpanel_data._internal.auth.flow.ensure_client_registered")
    def test_eu_region_authorize_url(
        self,
        mock_register: MagicMock,
        mock_callback: MagicMock,
        mock_browser: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify the EU region uses eu.mixpanel.com for the authorize URL."""
        mock_register.return_value = _make_client_info(region="eu")
        mock_callback.return_value = (
            CallbackResult(code="c", state="s"),
            19284,
        )
        mock_browser.open.return_value = True

        opened_urls: list[str] = []

        def _capture_url(url: str) -> bool:
            """Capture opened URL and return True to indicate success."""
            opened_urls.append(url)
            return True

        mock_browser.open.side_effect = _capture_url

        transport = httpx.MockTransport(
            lambda _req: httpx.Response(200, json=_make_token_response())
        )
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        flow = OAuthFlow(region="eu", storage=storage, http_client=http_client)
        flow.login()

        assert len(opened_urls) == 1
        assert "eu.mixpanel.com" in opened_urls[0]


class TestOAuthFlowNetworkErrors:
    """Tests for network error handling in exchange_code and refresh_tokens."""

    def test_exchange_code_timeout(self, tmp_path: Path) -> None:
        """Verify exchange_code raises OAuthError on timeout.

        A network timeout during token exchange should be wrapped in
        OAuthError with OAUTH_TOKEN_ERROR code.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            """Raise TimeoutException.

            Args:
                request: The incoming request.

            Returns:
                Never returns.

            Raises:
                httpx.TimeoutException: Always.
            """
            raise httpx.TimeoutException("test timeout")

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        with pytest.raises(OAuthError) as exc_info:
            flow.exchange_code(
                code="c",
                verifier="v",
                client_id="cid",
                redirect_uri="http://localhost:19284/callback",
            )
        assert exc_info.value.code == "OAUTH_TOKEN_ERROR"

    def test_exchange_code_connection_error(self, tmp_path: Path) -> None:
        """Verify exchange_code raises OAuthError on connection failure.

        A connection error (e.g. DNS resolution failure) should be wrapped
        in OAuthError with OAUTH_TOKEN_ERROR code.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            """Raise ConnectError.

            Args:
                request: The incoming request.

            Returns:
                Never returns.

            Raises:
                httpx.ConnectError: Always.
            """
            raise httpx.ConnectError("test connection error")

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        with pytest.raises(OAuthError) as exc_info:
            flow.exchange_code(
                code="c",
                verifier="v",
                client_id="cid",
                redirect_uri="http://localhost:19284/callback",
            )
        assert exc_info.value.code == "OAUTH_TOKEN_ERROR"

    def test_exchange_code_non_json_response(self, tmp_path: Path) -> None:
        """Verify exchange_code raises OAuthError for non-JSON 200 response.

        A proxy or misconfigured server might return HTML on success.
        The function should raise OAuthError, not a raw exception.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            """Return HTML body.

            Args:
                request: The incoming request.

            Returns:
                HTML response.
            """
            return httpx.Response(
                200,
                content=b"<html>error</html>",
                headers={"content-type": "text/html"},
            )

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        with pytest.raises(OAuthError) as exc_info:
            flow.exchange_code(
                code="c",
                verifier="v",
                client_id="cid",
                redirect_uri="http://localhost:19284/callback",
            )
        assert exc_info.value.code == "OAUTH_TOKEN_ERROR"

    def test_exchange_code_missing_access_token_in_response(
        self, tmp_path: Path
    ) -> None:
        """Verify exchange_code raises OAuthError when access_token is missing.

        A valid JSON response missing ``access_token`` should raise
        OAuthError, not a raw KeyError.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            """Return JSON with missing access_token.

            Args:
                request: The incoming request.

            Returns:
                JSON response without access_token.
            """
            return httpx.Response(200, json={"scope": "x"})

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        with pytest.raises(OAuthError) as exc_info:
            flow.exchange_code(
                code="c",
                verifier="v",
                client_id="cid",
                redirect_uri="http://localhost:19284/callback",
            )
        assert exc_info.value.code == "OAUTH_TOKEN_ERROR"

    def test_refresh_tokens_timeout(self, tmp_path: Path) -> None:
        """Verify refresh_tokens raises OAuthError on timeout.

        A network timeout during token refresh should be wrapped in
        OAuthError with OAUTH_REFRESH_ERROR code.
        """

        def handler(request: httpx.Request) -> httpx.Response:
            """Raise TimeoutException.

            Args:
                request: The incoming request.

            Returns:
                Never returns.

            Raises:
                httpx.TimeoutException: Always.
            """
            raise httpx.TimeoutException("test timeout")

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(transport=transport)
        storage = OAuthStorage(storage_dir=tmp_path)

        tokens = OAuthTokens(
            access_token=SecretStr("old"),
            refresh_token=SecretStr("old-refresh"),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scope="projects",
            token_type="Bearer",
        )

        flow = OAuthFlow(region="us", storage=storage, http_client=http_client)
        with pytest.raises(OAuthError) as exc_info:
            flow.refresh_tokens(tokens=tokens, client_id="cid")
        assert exc_info.value.code == "OAUTH_REFRESH_ERROR"
