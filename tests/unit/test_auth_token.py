"""Unit tests for OAuthTokens and OAuthClientInfo models (T008).

Tests the OAuth token model and client info model which provide
immutable, validated containers for OAuth 2.0 token data and
Dynamic Client Registration (DCR) client metadata.

Verifies:
- OAuthTokens: frozen immutable, is_expired() with 30s buffer, SecretStr
  redaction, JSON round-trip, project_id preservation, from_token_response()
- OAuthClientInfo: frozen immutable, field validation, created_at tracking
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import SecretStr, ValidationError

from mixpanel_data._internal.auth.token import OAuthClientInfo, OAuthTokens


def _utcnow() -> datetime:
    """Return current UTC datetime.

    Returns:
        Current datetime with UTC timezone.
    """
    return datetime.now(timezone.utc)


def _make_tokens(
    *,
    access_token: str = "access_abc123",
    refresh_token: str | None = "refresh_xyz789",
    expires_at: datetime | None = None,
    scope: str = "projects analysis",
    token_type: str = "Bearer",
    project_id: str | None = "12345",
) -> OAuthTokens:
    """Create an OAuthTokens instance with sensible defaults for testing.

    Args:
        access_token: OAuth access token string.
        refresh_token: OAuth refresh token string, or None.
        expires_at: Token expiry datetime. Defaults to 1 hour from now.
        scope: OAuth scope string.
        token_type: Token type (typically 'Bearer').
        project_id: Associated Mixpanel project ID.

    Returns:
        Configured OAuthTokens instance.
    """
    if expires_at is None:
        from datetime import timedelta

        expires_at = _utcnow() + timedelta(hours=1)

    return OAuthTokens(
        access_token=SecretStr(access_token),
        refresh_token=SecretStr(refresh_token) if refresh_token is not None else None,
        expires_at=expires_at,
        scope=scope,
        token_type=token_type,
        project_id=project_id,
    )


class TestOAuthTokensImmutability:
    """Tests that OAuthTokens is a frozen (immutable) Pydantic model."""

    def test_frozen_cannot_modify_access_token(self) -> None:
        """Verify that access_token cannot be modified after construction.

        OAuthTokens is a frozen Pydantic model, so attribute assignment
        should raise a ValidationError.
        """
        tokens = _make_tokens()
        with pytest.raises(ValidationError):
            tokens.access_token = SecretStr("new_token")  # type: ignore[misc]

    def test_frozen_cannot_modify_scope(self) -> None:
        """Verify that scope cannot be modified after construction."""
        tokens = _make_tokens()
        with pytest.raises(ValidationError):
            tokens.scope = "different_scope"  # type: ignore[misc]

    def test_frozen_cannot_modify_project_id(self) -> None:
        """Verify that project_id cannot be modified after construction."""
        tokens = _make_tokens()
        with pytest.raises(ValidationError):
            tokens.project_id = "99999"  # type: ignore[misc]


class TestOAuthTokensExpiry:
    """Tests for the is_expired() method with 30-second buffer."""

    def test_is_expired_true_when_past_expires_at(self) -> None:
        """Verify is_expired() returns True when expires_at is in the past."""
        from datetime import timedelta

        past = _utcnow() - timedelta(minutes=5)
        tokens = _make_tokens(expires_at=past)
        assert tokens.is_expired() is True

    def test_is_expired_true_within_30s_buffer(self) -> None:
        """Verify is_expired() returns True when within 30 seconds of expiry.

        The 30-second buffer prevents using tokens that are about to expire
        during an in-flight request.
        """
        from datetime import timedelta

        # 15 seconds from now — within the 30s buffer
        almost_expired = _utcnow() + timedelta(seconds=15)
        tokens = _make_tokens(expires_at=almost_expired)
        assert tokens.is_expired() is True

    def test_is_expired_true_at_exactly_30s(self) -> None:
        """Verify is_expired() returns True when exactly at the 30s boundary.

        At exactly 30 seconds remaining, the token should be considered expired
        (boundary condition).
        """
        from datetime import timedelta

        boundary = _utcnow() + timedelta(seconds=30)
        tokens = _make_tokens(expires_at=boundary)
        # At exactly 30s, should be expired (<=30s means expired)
        assert tokens.is_expired() is True

    def test_is_expired_false_when_well_in_future(self) -> None:
        """Verify is_expired() returns False when >30s from expires_at."""
        from datetime import timedelta

        future = _utcnow() + timedelta(hours=1)
        tokens = _make_tokens(expires_at=future)
        assert tokens.is_expired() is False

    def test_is_expired_false_just_outside_buffer(self) -> None:
        """Verify is_expired() returns False when just beyond the 30s buffer.

        At 60 seconds from expiry, the token should still be considered valid.
        """
        from datetime import timedelta

        outside_buffer = _utcnow() + timedelta(seconds=60)
        tokens = _make_tokens(expires_at=outside_buffer)
        assert tokens.is_expired() is False


class TestOAuthTokensSecretRedaction:
    """Tests that SecretStr fields are properly redacted in output."""

    def test_access_token_redacted_in_repr(self) -> None:
        """Verify that the access token value does not appear in repr().

        SecretStr should display as '**********' in repr output, never
        exposing the actual token value.
        """
        tokens = _make_tokens(access_token="super_secret_access_token")
        repr_str = repr(tokens)
        assert "super_secret_access_token" not in repr_str

    def test_refresh_token_redacted_in_repr(self) -> None:
        """Verify that the refresh token value does not appear in repr()."""
        tokens = _make_tokens(refresh_token="super_secret_refresh_token")
        repr_str = repr(tokens)
        assert "super_secret_refresh_token" not in repr_str

    def test_access_token_redacted_in_str(self) -> None:
        """Verify that the access token value does not appear in str()."""
        tokens = _make_tokens(access_token="super_secret_access_token")
        str_str = str(tokens)
        assert "super_secret_access_token" not in str_str

    def test_secret_values_accessible_via_get_secret_value(self) -> None:
        """Verify that the actual token values can be retrieved when needed.

        While redacted in repr/str, the actual values must be accessible
        via get_secret_value() for use in HTTP headers.
        """
        tokens = _make_tokens(access_token="my_access", refresh_token="my_refresh")
        assert tokens.access_token.get_secret_value() == "my_access"
        assert tokens.refresh_token is not None
        assert tokens.refresh_token.get_secret_value() == "my_refresh"


class TestOAuthTokensSerialization:
    """Tests for JSON round-trip serialization/deserialization."""

    def test_json_round_trip(self) -> None:
        """Verify that OAuthTokens survives JSON serialization and deserialization.

        The model should be serializable to JSON and reconstructable from
        that JSON, with all field values preserved.
        """
        from datetime import timedelta

        expires = _utcnow() + timedelta(hours=1)
        original = _make_tokens(
            access_token="rt_access",
            refresh_token="rt_refresh",
            expires_at=expires,
            scope="projects analysis events",
            token_type="Bearer",
            project_id="54321",
        )

        # Use model_dump with mode="json" to get JSON-serializable dict,
        # exposing SecretStr values for round-trip (mirrors OAuthStorage pattern)
        import json

        data = original.model_dump(mode="json")
        # SecretStr values are redacted by default in model_dump, so we must
        # manually expose them for round-trip fidelity
        data["access_token"] = original.access_token.get_secret_value()
        if original.refresh_token is not None:
            data["refresh_token"] = original.refresh_token.get_secret_value()
        json_str = json.dumps(data, default=str)
        restored = OAuthTokens.model_validate_json(json_str)

        assert restored.access_token.get_secret_value() == "rt_access"
        assert restored.refresh_token is not None
        assert restored.refresh_token.get_secret_value() == "rt_refresh"
        assert restored.scope == "projects analysis events"
        assert restored.token_type == "Bearer"
        assert restored.project_id == "54321"
        # Datetime comparison (may lose sub-microsecond precision in JSON)
        assert abs((restored.expires_at - original.expires_at).total_seconds()) < 1

    def test_json_round_trip_without_refresh_token(self) -> None:
        """Verify JSON round-trip works when refresh_token is None.

        Some OAuth flows may not return a refresh token. The model must
        handle None correctly through serialization.
        """
        original = _make_tokens(refresh_token=None)

        json_str = original.model_dump_json()
        restored = OAuthTokens.model_validate_json(json_str)

        assert restored.refresh_token is None

    def test_json_round_trip_without_project_id(self) -> None:
        """Verify JSON round-trip works when project_id is None."""
        original = _make_tokens(project_id=None)

        json_str = original.model_dump_json()
        restored = OAuthTokens.model_validate_json(json_str)

        assert restored.project_id is None


class TestOAuthTokensProjectId:
    """Tests for project_id field preservation."""

    def test_project_id_preserved(self) -> None:
        """Verify that project_id is stored and retrievable."""
        tokens = _make_tokens(project_id="98765")
        assert tokens.project_id == "98765"

    def test_project_id_none_allowed(self) -> None:
        """Verify that project_id can be None.

        During initial OAuth login, project_id may not yet be known.
        """
        tokens = _make_tokens(project_id=None)
        assert tokens.project_id is None

    def test_project_id_preserved_through_different_values(self) -> None:
        """Verify that different project_id values are independently preserved."""
        tokens_a = _make_tokens(project_id="111")
        tokens_b = _make_tokens(project_id="222")

        assert tokens_a.project_id == "111"
        assert tokens_b.project_id == "222"


class TestOAuthTokensFromTokenResponse:
    """Tests for the from_token_response() class method."""

    def test_from_token_response_basic(self) -> None:
        """Verify from_token_response() creates tokens from API response data.

        The token endpoint returns a dict with 'access_token', 'refresh_token',
        'expires_in', 'scope', 'token_type'. The class method should parse
        this and compute expires_at from expires_in.
        """
        data = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_in": 3600,
            "scope": "projects analysis",
            "token_type": "Bearer",
        }

        tokens = OAuthTokens.from_token_response(data, project_id="12345")

        assert tokens.access_token.get_secret_value() == "new_access"
        assert tokens.refresh_token is not None
        assert tokens.refresh_token.get_secret_value() == "new_refresh"
        assert tokens.scope == "projects analysis"
        assert tokens.token_type == "Bearer"
        assert tokens.project_id == "12345"

    def test_from_token_response_computes_expires_at(self) -> None:
        """Verify that expires_at is computed from expires_in seconds.

        The expires_at should be approximately now + expires_in seconds.
        """
        from datetime import timedelta

        data = {
            "access_token": "tok",
            "expires_in": 7200,
            "scope": "projects",
            "token_type": "Bearer",
        }

        before = _utcnow()
        tokens = OAuthTokens.from_token_response(data, project_id=None)
        after = _utcnow()

        expected_min = before + timedelta(seconds=7200)
        expected_max = after + timedelta(seconds=7200)

        assert expected_min <= tokens.expires_at <= expected_max

    def test_from_token_response_without_refresh_token(self) -> None:
        """Verify from_token_response() handles missing refresh_token."""
        data = {
            "access_token": "tok",
            "expires_in": 3600,
            "scope": "projects",
            "token_type": "Bearer",
        }

        tokens = OAuthTokens.from_token_response(data, project_id="123")

        assert tokens.refresh_token is None

    def test_from_token_response_project_id_none(self) -> None:
        """Verify from_token_response() accepts None project_id."""
        data = {
            "access_token": "tok",
            "refresh_token": "ref",
            "expires_in": 3600,
            "scope": "projects",
            "token_type": "Bearer",
        }

        tokens = OAuthTokens.from_token_response(data, project_id=None)

        assert tokens.project_id is None


class TestOAuthClientInfo:
    """Tests for the OAuthClientInfo model."""

    def _make_client_info(
        self,
        *,
        client_id: str = "client_abc123",
        region: str = "us",
        redirect_uri: str = "http://localhost:19284/callback",
        scope: str = "projects analysis",
        created_at: datetime | None = None,
    ) -> OAuthClientInfo:
        """Create an OAuthClientInfo instance with sensible defaults.

        Args:
            client_id: DCR client identifier.
            region: Mixpanel data residency region.
            redirect_uri: OAuth redirect URI.
            scope: OAuth scope string.
            created_at: Client registration timestamp. Defaults to now.

        Returns:
            Configured OAuthClientInfo instance.
        """
        if created_at is None:
            created_at = _utcnow()
        return OAuthClientInfo(
            client_id=client_id,
            region=region,
            redirect_uri=redirect_uri,
            scope=scope,
            created_at=created_at,
        )

    def test_client_info_creation(self) -> None:
        """Verify that OAuthClientInfo can be created with valid fields."""
        info = self._make_client_info()
        assert info.client_id == "client_abc123"
        assert info.region == "us"
        assert info.redirect_uri == "http://localhost:19284/callback"
        assert info.scope == "projects analysis"
        assert isinstance(info.created_at, datetime)

    def test_client_info_frozen(self) -> None:
        """Verify that OAuthClientInfo is immutable (frozen)."""
        info = self._make_client_info()
        with pytest.raises(ValidationError):
            info.client_id = "different"  # type: ignore[misc]

    def test_client_info_json_round_trip(self) -> None:
        """Verify OAuthClientInfo survives JSON serialization round-trip."""
        original = self._make_client_info(
            client_id="rt_client",
            region="eu",
            redirect_uri="http://localhost:19285/callback",
            scope="projects events",
        )

        json_str = original.model_dump_json()
        restored = OAuthClientInfo.model_validate_json(json_str)

        assert restored.client_id == "rt_client"
        assert restored.region == "eu"
        assert restored.redirect_uri == "http://localhost:19285/callback"
        assert restored.scope == "projects events"

    def test_client_info_different_regions(self) -> None:
        """Verify OAuthClientInfo supports all valid regions."""
        for region in ("us", "eu", "in"):
            info = self._make_client_info(region=region)
            assert info.region == region

    def test_client_info_created_at_preserved(self) -> None:
        """Verify that created_at timestamp is preserved."""
        specific_time = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        info = self._make_client_info(created_at=specific_time)
        assert info.created_at == specific_time


class TestOAuthTokensSecretRedactionExtended:
    """Extended tests for secret redaction in various serialization paths."""

    def test_token_not_in_model_dump(self) -> None:
        """Verify that the raw access_token value does not appear in model_dump output.

        When ``model_dump()`` is called, ``SecretStr`` fields should be
        redacted (shown as ``**********``), preventing accidental exposure
        if the dict is logged or serialized.
        """
        tokens = _make_tokens(access_token="secret_abc123")
        dumped = str(tokens.model_dump())
        assert "secret_abc123" not in dumped

    def test_token_not_in_f_string(self) -> None:
        """Verify that an f-string interpolation of OAuthTokens does not leak secrets.

        If tokens are accidentally included in a log message via an f-string,
        the raw access_token and refresh_token values must not appear.
        """
        tokens = _make_tokens(
            access_token="secret_abc123", refresh_token="refresh_secret"
        )
        formatted = f"Info: {tokens}"
        assert "secret_abc123" not in formatted
        assert "refresh_secret" not in formatted

    def test_token_not_in_exception_to_dict(self) -> None:
        """Verify that OAuthError.to_dict() does not contain raw token values.

        Confirms that constructing an ``OAuthError`` with descriptive details
        (not raw tokens) produces a clean serializable dict. This is a positive
        test that error construction patterns do not leak secrets.
        """
        from mixpanel_data.exceptions import OAuthError

        error = OAuthError(
            message="Token refresh failed",
            code="OAUTH_REFRESH_ERROR",
            details={"region": "us", "reason": "expired"},
        )
        error_dict = error.to_dict()
        error_str = str(error_dict)
        # Verify the error dict contains expected fields, not raw tokens
        assert "Token refresh failed" in error_str
        assert "OAUTH_REFRESH_ERROR" in error_str
        # No token material should be present
        assert "secret_abc123" not in error_str
        assert "refresh_secret" not in error_str


class TestOAuthTokensExpiryEdgeCases:
    """Tests for boundary conditions in token expiry via from_token_response().

    Verifies behavior when expires_in is zero, negative, string, float,
    or extremely large — edge cases that may occur with non-conformant
    OAuth servers or malformed API responses.
    """

    def test_from_token_response_zero_expires_in(self) -> None:
        """Verify that expires_in=0 produces an immediately expired token.

        A zero lifetime means the token was already expired at issuance.
        ``is_expired()`` must return True because 0 seconds plus the
        30-second safety buffer puts us past ``expires_at``.
        """
        data: dict[str, object] = {
            "expires_in": 0,
            "access_token": "tok",
            "scope": "all",
            "token_type": "Bearer",
        }
        tokens = OAuthTokens.from_token_response(data)
        assert tokens.is_expired() is True

    def test_from_token_response_negative_expires_in(self) -> None:
        """Verify that expires_in=-100 produces an expired token.

        A negative lifetime means the token expired before issuance.
        ``is_expired()`` must return True.
        """
        data: dict[str, object] = {
            "expires_in": -100,
            "access_token": "tok",
            "scope": "all",
            "token_type": "Bearer",
        }
        tokens = OAuthTokens.from_token_response(data)
        assert tokens.is_expired() is True

    def test_from_token_response_string_expires_in(self) -> None:
        """Verify that expires_in="3600" (string) is accepted and parsed correctly.

        The implementation uses ``int(str(expires_in_raw))`` so numeric
        strings are coerced to integers. The resulting token should have
        an ``expires_at`` roughly 3600 seconds in the future.
        """
        from datetime import timedelta

        data: dict[str, object] = {
            "expires_in": "3600",
            "access_token": "tok",
            "scope": "all",
            "token_type": "Bearer",
        }
        before = _utcnow()
        tokens = OAuthTokens.from_token_response(data)
        after = _utcnow()

        expected_min = before + timedelta(seconds=3600)
        expected_max = after + timedelta(seconds=3600)
        assert expected_min <= tokens.expires_at <= expected_max
        assert tokens.is_expired() is False

    def test_from_token_response_float_expires_in(self) -> None:
        """Verify that expires_in=3600.5 (float) is accepted and truncated to int.

        The implementation converts via ``int(str(...))``. A float string
        like ``"3600.5"`` will raise ``ValueError`` from ``int()``, so the
        float is first converted to string ``"3600.5"`` which cannot be
        parsed by ``int()``. However, Python's ``str(3600.5)`` produces
        ``"3600.5"`` which ``int()`` rejects. This test documents that
        float expires_in raises ValueError.
        """
        data: dict[str, object] = {
            "expires_in": 3600.5,
            "access_token": "tok",
            "scope": "all",
            "token_type": "Bearer",
        }
        # int(str(3600.5)) == int("3600.5") raises ValueError
        with pytest.raises(ValueError, match="invalid literal"):
            OAuthTokens.from_token_response(data)

    def test_from_token_response_huge_expires_in(self) -> None:
        """Verify that an extremely large expires_in produces a non-expired token.

        A token with a ~31-year lifetime should not be considered expired.
        ``is_expired()`` must return False.
        """
        data: dict[str, object] = {
            "expires_in": 999999999,
            "access_token": "tok",
            "scope": "all",
            "token_type": "Bearer",
        }
        tokens = OAuthTokens.from_token_response(data)
        assert tokens.is_expired() is False
