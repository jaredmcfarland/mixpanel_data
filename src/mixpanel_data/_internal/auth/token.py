"""OAuth token and client info models.

Immutable Pydantic models for OAuth 2.0 token management and
Dynamic Client Registration (DCR) client metadata.

Example:
    ```python
    from mixpanel_data._internal.auth.token import OAuthTokens, OAuthClientInfo

    tokens = OAuthTokens.from_token_response(
        {"access_token": "abc", "refresh_token": "def", "expires_in": 3600,
         "scope": "read", "token_type": "Bearer"},
        project_id="12345",
    )
    if tokens.is_expired():
        print("Token needs refresh")
    ```
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, SecretStr


class OAuthTokens(BaseModel):
    """Immutable OAuth 2.0 token set with expiry tracking.

    Stores access and optional refresh tokens along with metadata
    from the token response. The ``is_expired`` method includes a
    30-second safety buffer to avoid using tokens that are about to expire.

    Attributes:
        access_token: The OAuth access token (redacted in output).
        refresh_token: The OAuth refresh token, if provided (redacted in output).
        expires_at: UTC datetime when the access token expires.
        scope: Space-separated list of granted scopes.
        token_type: Token type, typically ``"Bearer"``.
        project_id: Associated Mixpanel project ID, if known.
    """

    model_config = ConfigDict(frozen=True)

    access_token: SecretStr
    """The OAuth access token (redacted in output)."""

    refresh_token: SecretStr | None = None
    """The OAuth refresh token, if provided (redacted in output)."""

    expires_at: datetime
    """UTC datetime when the access token expires."""

    scope: str
    """Space-separated list of granted scopes."""

    token_type: str
    """Token type, typically ``'Bearer'``."""

    project_id: str | None = None
    """Associated Mixpanel project ID, if known."""

    def is_expired(self) -> bool:
        """Check whether the access token is expired or about to expire.

        Uses a 30-second safety buffer to avoid sending tokens that are
        about to expire during in-flight requests.

        Returns:
            True if the token is expired or will expire within 30 seconds.

        Example:
            ```python
            tokens = OAuthTokens.from_token_response(
                {"access_token": "x", "expires_in": 10,
                 "scope": "read", "token_type": "Bearer"}
            )
            assert tokens.is_expired()  # 10s < 30s buffer
            ```
        """
        return datetime.now(timezone.utc) + timedelta(seconds=30) >= self.expires_at

    @classmethod
    def from_token_response(
        cls,
        data: dict[str, object],
        project_id: str | None = None,
    ) -> OAuthTokens:
        """Create an OAuthTokens instance from a raw token endpoint response.

        Computes ``expires_at`` by adding the ``expires_in`` value (in seconds)
        to the current UTC time.

        Args:
            data: Raw JSON response from the token endpoint. Must contain
                ``access_token``, ``expires_in``, ``scope``, and ``token_type``.
                May contain ``refresh_token``.
            project_id: Optional Mixpanel project ID to associate with the tokens.

        Returns:
            A new frozen OAuthTokens instance.

        Raises:
            KeyError: If required keys are missing from ``data``.
            ValueError: If ``expires_in`` cannot be converted to an int.

        Example:
            ```python
            response = {
                "access_token": "eyJ...",
                "refresh_token": "dGhp...",
                "expires_in": 3600,
                "scope": "read:project",
                "token_type": "Bearer",
            }
            tokens = OAuthTokens.from_token_response(response, project_id="123")
            ```
        """
        expires_in_raw = data["expires_in"]
        expires_in = int(str(expires_in_raw))
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        raw_refresh = data.get("refresh_token")
        refresh_token: SecretStr | None = None
        if raw_refresh is not None:
            refresh_token = SecretStr(str(raw_refresh))

        return cls(
            access_token=SecretStr(str(data["access_token"])),
            refresh_token=refresh_token,
            expires_at=expires_at,
            scope=str(data.get("scope", "")),
            token_type=str(data["token_type"]),
            project_id=project_id,
        )


class OAuthClientInfo(BaseModel):
    """Immutable OAuth client registration metadata.

    Stores client information from Dynamic Client Registration (RFC 7591)
    for reuse across sessions without re-registering.

    Attributes:
        client_id: The OAuth client identifier.
        region: Mixpanel data residency region (``us``, ``eu``, or ``in``).
        redirect_uri: The redirect URI registered with the authorization server.
        scope: Space-separated list of requested scopes.
        created_at: UTC datetime when the client was registered.
    """

    model_config = ConfigDict(frozen=True)

    client_id: str
    """The OAuth client identifier."""

    region: str
    """Mixpanel data residency region (``us``, ``eu``, or ``in``)."""

    redirect_uri: str
    """The redirect URI registered with the authorization server."""

    scope: str
    """Space-separated list of requested scopes."""

    created_at: datetime
    """UTC datetime when the client was registered."""
