"""OAuth 2.0 PKCE flow orchestrator for Mixpanel.

Coordinates the full OAuth 2.0 Authorization Code + PKCE flow:
1. Dynamic Client Registration (via ``ensure_client_registered``)
2. PKCE challenge generation
3. Browser-based authorization
4. Local callback server to receive the authorization code
5. Token exchange
6. Token refresh

Example:
    ```python
    from mixpanel_data._internal.auth.flow import OAuthFlow

    flow = OAuthFlow(region="us")
    tokens = flow.login(project_id="12345")
    print(f"Access token: {tokens.access_token.get_secret_value()[:8]}...")
    ```
"""

from __future__ import annotations

import json
import secrets
import socket
import threading
import time
import webbrowser
from urllib.parse import urlencode

import httpx

from mixpanel_data._internal.auth.callback_server import (
    CALLBACK_PORTS,
    CallbackResult,
    start_callback_server,
)
from mixpanel_data._internal.auth.client_registration import (
    OAUTH_BASE_URLS,
    ensure_client_registered,
)
from mixpanel_data._internal.auth.pkce import PkceChallenge
from mixpanel_data._internal.auth.storage import OAuthStorage
from mixpanel_data._internal.auth.token import OAuthTokens
from mixpanel_data.exceptions import OAuthError


class OAuthFlow:
    """Orchestrator for the OAuth 2.0 Authorization Code + PKCE flow.

    Manages the full interactive login sequence: client registration,
    PKCE challenge generation, browser authorization, callback handling,
    and token exchange. Also supports token refresh.

    Attributes:
        region: Mixpanel data residency region (``us``, ``eu``, or ``in``).

    Example:
        ```python
        flow = OAuthFlow(region="us")
        tokens = flow.login(project_id="12345")
        # Later, refresh tokens:
        new_tokens = flow.refresh_tokens(tokens, client_id="my-client")
        ```
    """

    def __init__(
        self,
        region: str = "us",
        *,
        storage: OAuthStorage | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Initialize the OAuth flow orchestrator.

        Args:
            region: Mixpanel data residency region (default ``"us"``).
                Must be one of ``"us"``, ``"eu"``, or ``"in"``.
            storage: OAuthStorage instance for caching tokens and client info.
                Uses the default storage location if not provided.
            http_client: httpx.Client for making HTTP requests. A default
                client is created if not provided.

        Example:
            ```python
            flow = OAuthFlow(region="eu")
            flow = OAuthFlow(region="us", storage=OAuthStorage(Path("/tmp")))
            ```
        """
        if region not in OAUTH_BASE_URLS:
            raise OAuthError(
                f"Unknown region: {region!r}. Must be one of: "
                f"{', '.join(sorted(OAUTH_BASE_URLS.keys()))}",
                code="OAUTH_CONFIG_ERROR",
            )
        self._region = region
        self._storage = storage or OAuthStorage()
        self._http_client = http_client or httpx.Client()
        self._base_url = OAUTH_BASE_URLS[region]

    @property
    def region(self) -> str:
        """Mixpanel data residency region.

        Returns:
            The region string (``us``, ``eu``, or ``in``).
        """
        return self._region

    def get_valid_token(self, region: str) -> str:
        """Return a valid access token, refreshing if expired.

        Loads tokens from storage, checks if expired, auto-refreshes if
        needed, persists refreshed tokens, and returns the access token string.

        Args:
            region: Mixpanel data residency region (``us``, ``eu``, or ``in``).

        Returns:
            A valid OAuth access token string.

        Raises:
            OAuthError: If no tokens exist (``OAUTH_TOKEN_ERROR``),
                no client info exists for refresh (``OAUTH_REFRESH_ERROR``),
                or the refresh request fails (``OAUTH_REFRESH_ERROR``).

        Example:
            ```python
            flow = OAuthFlow(region="us")
            token = flow.get_valid_token(region="us")
            headers = {"Authorization": f"Bearer {token}"}
            ```
        """
        tokens = self._storage.load_tokens(region=region)
        if tokens is None:
            raise OAuthError(
                "No OAuth tokens found. Please log in first with `mp auth login`.",
                code="OAUTH_TOKEN_ERROR",
            )

        if not tokens.is_expired():
            return tokens.access_token.get_secret_value()

        # Token is expired — refresh it
        client_info = self._storage.load_client_info(region=region)
        if client_info is None:
            raise OAuthError(
                "No OAuth client info found for refresh. "
                "Please log in again with `mp auth login`.",
                code="OAUTH_REFRESH_ERROR",
            )

        new_tokens = self.refresh_tokens(tokens=tokens, client_id=client_info.client_id)
        self._storage.save_tokens(new_tokens, region=region)
        return new_tokens.access_token.get_secret_value()

    def login(
        self, project_id: str | None = None, *, persist: bool = True
    ) -> OAuthTokens:
        """Execute the full interactive OAuth PKCE login flow.

        Performs the following steps:
        1. Register (or load cached) OAuth client via DCR
        2. Generate PKCE challenge
        3. Start local callback server
        4. Open browser to Mixpanel authorization URL
        5. Wait for callback with authorization code
        6. Exchange code for tokens
        7. Save tokens to local storage (when ``persist`` is True)

        Args:
            project_id: Optional Mixpanel project ID to associate with tokens.
            persist: When True (default), the resulting :class:`OAuthTokens`
                are written to the configured :class:`OAuthStorage` at
                ``~/.mp/oauth/tokens_{region}.json``. v3 callers
                (``mp.accounts.login``) opt out and persist to the
                per-account ``~/.mp/accounts/{name}/tokens.json`` path
                themselves.

        Returns:
            The obtained OAuthTokens with access and optional refresh tokens.

        Raises:
            OAuthError: If any step of the flow fails (registration, browser,
                callback, token exchange).

        Example:
            ```python
            flow = OAuthFlow(region="us")
            tokens = flow.login(project_id="12345")
            print(tokens.access_token.get_secret_value()[:8])
            ```
        """
        # Step 1: Generate PKCE challenge and state
        pkce = PkceChallenge.generate()
        state = secrets.token_urlsafe(32)

        # Step 2: Find an available callback port by probing before binding
        bound_port = _find_available_port()
        if bound_port is None:
            raise OAuthError(
                f"All OAuth callback ports ({CALLBACK_PORTS}) are busy.",
                code="OAUTH_PORT_ERROR",
            )

        redirect_uri = f"http://localhost:{bound_port}/callback"

        # Step 3: Ensure client registration
        client_info = ensure_client_registered(
            http_client=self._http_client,
            region=self._region,
            redirect_uri=redirect_uri,
            storage=self._storage,
        )

        # Step 4: Build authorize URL and open browser
        authorize_url = self._build_authorize_url(
            client_id=client_info.client_id,
            redirect_uri=redirect_uri,
            challenge=pkce.challenge,
            state=state,
        )

        # Step 5: Start callback server in background, then open browser
        callback_result_holder: list[tuple[CallbackResult, int]] = []
        callback_error_holder: list[Exception] = []

        def _run_callback() -> None:
            """Run the callback server in a thread."""
            try:
                result = start_callback_server(
                    state=state, timeout=300.0, port=bound_port
                )
                callback_result_holder.append(result)
            except Exception as exc:
                callback_error_holder.append(exc)

        callback_thread = threading.Thread(target=_run_callback, daemon=True)
        callback_thread.start()

        # Small delay to ensure server is listening before opening browser
        time.sleep(0.1)

        # Open browser
        try:
            webbrowser.open(authorize_url)
        except Exception as exc:
            raise OAuthError(
                f"Could not open browser for authorization: {exc}",
                code="OAUTH_BROWSER_ERROR",
                details={"authorize_url": authorize_url},
            ) from exc

        # Step 6: Wait for callback
        callback_thread.join(timeout=310.0)

        if callback_error_holder:
            err = callback_error_holder[0]
            if isinstance(err, OAuthError):
                raise err
            raise OAuthError(
                f"Callback server error: {err}",
                code="OAUTH_TOKEN_ERROR",
            ) from err

        if not callback_result_holder:
            raise OAuthError(
                "Callback server did not receive a response.",
                code="OAUTH_TIMEOUT",
            )

        callback_result, _ = callback_result_holder[0]

        # Step 7: Exchange code for tokens
        tokens = self.exchange_code(
            code=callback_result.code,
            verifier=pkce.verifier,
            client_id=client_info.client_id,
            redirect_uri=redirect_uri,
            project_id=project_id,
        )

        # Step 8: Save tokens (v2 layout) when the caller opts in.
        if persist:
            self._storage.save_tokens(tokens, region=self._region)

        return tokens

    def exchange_code(
        self,
        code: str,
        verifier: str,
        client_id: str,
        redirect_uri: str,
        project_id: str | None = None,
    ) -> OAuthTokens:
        """Exchange an authorization code for OAuth tokens.

        Sends a POST request to the token endpoint with the authorization
        code and PKCE verifier.

        Args:
            code: The authorization code from the callback.
            verifier: The PKCE code verifier.
            client_id: The registered OAuth client ID.
            redirect_uri: The redirect URI used in the authorization request.
            project_id: Optional Mixpanel project ID to associate with tokens.

        Returns:
            The obtained OAuthTokens.

        Raises:
            OAuthError: If the token exchange fails (``OAUTH_TOKEN_ERROR``).

        Example:
            ```python
            tokens = flow.exchange_code(
                code="auth-code",
                verifier="pkce-verifier",
                client_id="my-client",
                redirect_uri="http://localhost:19284/callback",
            )
            ```
        """
        form_data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        }
        return self._post_token_request(
            form_data,
            operation="Token exchange",
            error_code="OAUTH_TOKEN_ERROR",
            project_id=project_id,
        )

    def refresh_tokens(
        self,
        tokens: OAuthTokens,
        client_id: str,
    ) -> OAuthTokens:
        """Refresh OAuth tokens using a refresh token.

        Sends a POST request to the token endpoint with the refresh token
        to obtain new access and refresh tokens.

        Args:
            tokens: Current OAuthTokens containing the refresh token.
            client_id: The OAuth client ID.

        Returns:
            New OAuthTokens with a fresh access token.

        Raises:
            OAuthError: If no refresh token is available
                (``OAUTH_REFRESH_ERROR``) or the refresh request fails.

        Example:
            ```python
            new_tokens = flow.refresh_tokens(tokens, client_id="my-client")
            ```
        """
        if tokens.refresh_token is None:
            raise OAuthError(
                "Cannot refresh: no refresh token available. Please log in again.",
                code="OAUTH_REFRESH_ERROR",
            )

        form_data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": tokens.refresh_token.get_secret_value(),
            "client_id": client_id,
        }
        return self._post_token_request(
            form_data,
            operation="Token refresh",
            error_code="OAUTH_REFRESH_ERROR",
            project_id=tokens.project_id,
        )

    def _post_token_request(
        self,
        form_data: dict[str, str],
        *,
        operation: str,
        error_code: str,
        project_id: str | None = None,
    ) -> OAuthTokens:
        """POST form data to the token endpoint and parse the response.

        Shared implementation for both token exchange and token refresh
        requests, which follow the same request/response pattern.

        Args:
            form_data: Form-encoded body to POST.
            operation: Human-readable name for error messages
                (e.g., ``"Token exchange"`` or ``"Token refresh"``).
            error_code: OAuthError code to use on failure.
            project_id: Optional project ID to attach to the returned tokens.

        Returns:
            Parsed OAuthTokens from the token endpoint response.

        Raises:
            OAuthError: If the request fails, returns a non-200 status,
                returns non-JSON, or is missing required fields.
        """
        token_url = f"{self._base_url}token/"

        try:
            response = self._http_client.post(token_url, data=form_data)
        except httpx.HTTPError as exc:
            raise OAuthError(
                f"{operation} request failed: {exc}",
                code=error_code,
                details={"url": token_url},
            ) from exc

        if response.status_code != 200:
            raise OAuthError(
                f"{operation} failed with status {response.status_code}: "
                f"{response.text}",
                code=error_code,
                details={
                    "status_code": response.status_code,
                    "response_body": response.text,
                },
            )

        try:
            data: dict[str, object] = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise OAuthError(
                f"{operation} returned non-JSON response: "
                f"{response.headers.get('content-type', 'unknown')}",
                code=error_code,
                details={"response_body": response.text},
            ) from exc

        try:
            return OAuthTokens.from_token_response(data, project_id=project_id)
        except (KeyError, TypeError, ValueError) as exc:
            raise OAuthError(
                f"{operation} response missing required fields: {exc}",
                code=error_code,
                details={"response_data": str(data)},
            ) from exc

    def _build_authorize_url(
        self,
        client_id: str,
        redirect_uri: str,
        challenge: str,
        state: str,
    ) -> str:
        """Build the OAuth authorization URL with PKCE parameters.

        Args:
            client_id: The registered OAuth client ID.
            redirect_uri: The callback redirect URI.
            challenge: The PKCE code challenge.
            state: The CSRF state parameter.

        Returns:
            The full authorization URL to open in the browser.
        """
        # scope intentionally omitted — DCR creates apps with an empty scope
        # field, so Django OAuth Toolkit defaults to ["__all__"], granting
        # every scope in OAUTH2_PROVIDER["SCOPES"] (~63 total).
        # See: mixpanel_data_rust/docs/016-webapp-oauth-plan.md
        params: dict[str, str] = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{self._base_url}authorize/?{urlencode(params)}"


def _find_available_port() -> int | None:
    """Probe CALLBACK_PORTS to find one that is not currently in use.

    Binds and immediately releases each candidate port on 127.0.0.1.
    Returns the first available port, or None if all are occupied.

    Returns:
        An available port number, or None.
    """
    for port in CALLBACK_PORTS:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_sock:
                test_sock.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
    return None
