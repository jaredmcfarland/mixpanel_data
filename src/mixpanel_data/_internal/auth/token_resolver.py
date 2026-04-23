"""Concrete :class:`TokenResolver` implementations.

The redesigned auth subsystem decouples ``Account`` (which knows what kind
of credentials it represents) from token *materialization* (which knows
where and how to fetch the bearer). This module ships
:class:`OnDiskTokenResolver`, the default implementation that reads OAuth
browser tokens from ``~/.mp/accounts/{name}/tokens.json`` and static
tokens from inline ``SecretStr`` fields or environment variables.

Browser-token refresh delegates to
:meth:`mixpanel_data._internal.auth.flow.OAuthFlow.refresh_tokens` and
persists the new payload back to the per-account path atomically (Fix 16
of the 042 plan).

Reference: ``specs/042-auth-architecture-redesign/data-model.md``,
``contracts/python-api.md`` §5.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from mixpanel_data._internal.auth.account import (
    OAuthTokenAccount,
    Region,
    TokenResolver,
)
from mixpanel_data._internal.auth.storage import account_dir
from mixpanel_data._internal.io_utils import atomic_write_bytes
from mixpanel_data.exceptions import OAuthError


def _account_tokens_path(name: str) -> Path:
    """Return ``<account-dir>/tokens.json`` for the given account name.

    Routes through :func:`account_dir` so the
    ``MP_OAUTH_STORAGE_DIR`` env-var override is honored — hard-coding
    ``~/.mp/accounts/`` here would silently bypass test isolation and
    custom-deployment overrides.

    Args:
        name: Account name (validated upstream by the ``Account`` model).

    Returns:
        Absolute path to the per-account tokens file.
    """
    return account_dir(name) / "tokens.json"


class OnDiskTokenResolver(TokenResolver):
    """Default resolver: tokens live on disk per account.

    Reads OAuth browser tokens from ``~/.mp/accounts/{name}/tokens.json``
    written by :class:`OAuthFlow`. Reads static tokens from either the
    inline ``token`` field on the account or the environment variable
    named in ``token_env``.

    The resolver is intentionally I/O-light: the only side effect is
    reading files that already exist; refresh is delegated to the OAuth
    flow code (a future wire-up). All failures surface as
    :class:`OAuthError` so callers can give actionable error messages.
    """

    def get_browser_token(self, name: str, region: Region) -> str:
        """Return a fresh access token for an :class:`OAuthBrowserAccount`.

        Reads ``~/.mp/accounts/{name}/tokens.json``, checks the recorded
        ``expires_at`` (with a 30s safety buffer), and returns the token
        if not expired. If expired, attempts to refresh via the existing
        OAuth flow (deferred); for now, an expired token without a refresh
        token raises directly.

        Args:
            name: Account name (used to locate the tokens file).
            region: Mixpanel region (kept for parity with the protocol;
                used by some refresh paths).

        Returns:
            The current access token (no ``Bearer`` prefix).

        Raises:
            OAuthError: If the tokens file is missing, malformed, expired
                without a refresh token, or refresh fails.
        """
        path = _account_tokens_path(name)
        if not path.exists():
            raise OAuthError(
                (
                    f"No OAuth tokens found for account '{name}'. "
                    f"Run `mp account login {name}` to authenticate."
                ),
                code="OAUTH_TOKEN_ERROR",
                details={"account_name": name, "path": str(path)},
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OAuthError(
                (
                    f"Could not read OAuth tokens for account '{name}' from "
                    f"{path}: {exc}"
                ),
                code="OAUTH_TOKEN_ERROR",
                details={"account_name": name, "path": str(path)},
            ) from exc

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise OAuthError(
                (
                    f"OAuth tokens for account '{name}' are missing "
                    f"`access_token`. Re-run `mp account login {name}`."
                ),
                code="OAUTH_TOKEN_ERROR",
                details={"account_name": name, "path": str(path)},
            )

        expires_raw = payload.get("expires_at")
        if not isinstance(expires_raw, str) or not expires_raw:
            raise OAuthError(
                (
                    f"OAuth tokens for account '{name}' are missing "
                    f"`expires_at`. A token without a known expiry would "
                    f"silently be treated as valid forever; re-run "
                    f"`mp account login {name}` to refresh."
                ),
                code="OAUTH_TOKEN_ERROR",
                details={"account_name": name, "path": str(path)},
            )
        try:
            expires_at = datetime.fromisoformat(expires_raw)
        except ValueError as exc:
            raise OAuthError(
                (
                    f"OAuth tokens for account '{name}' have an invalid "
                    f"`expires_at` value: {expires_raw!r}."
                ),
                code="OAUTH_TOKEN_ERROR",
                details={"account_name": name, "path": str(path)},
            ) from exc
        now = datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now + timedelta(seconds=30):
            refresh = payload.get("refresh_token")
            if not isinstance(refresh, str) or not refresh:
                raise OAuthError(
                    (
                        f"OAuth access token for account '{name}' has "
                        f"expired and no refresh token is available. "
                        f"Re-run `mp account login {name}`."
                    ),
                    code="OAUTH_TOKEN_ERROR",
                    details={
                        "account_name": name,
                        "region": region,
                        "path": str(path),
                    },
                )
            return self._refresh_and_persist(
                name=name,
                region=region,
                path=path,
                payload=payload,
                refresh_token=refresh,
                expires_at=expires_at,
            )

        return access_token

    def _refresh_and_persist(
        self,
        *,
        name: str,
        region: Region,
        path: Path,
        payload: dict[str, Any],
        refresh_token: str,
        expires_at: datetime,
    ) -> str:
        """Refresh an expired browser token and rewrite the per-account file atomically.

        Loads the cached DCR client info for ``region`` (shared with the
        legacy v2 OAuth layout — same client across accounts), POSTs the
        refresh request via :class:`OAuthFlow`, and writes the new
        payload back to ``path`` with mode ``0o600``. The refreshed
        access token is returned so the in-flight HTTP request can use it.

        Args:
            name: Account name (for error messages and the account dir).
            region: Mixpanel region (selects the DCR base URL).
            path: Per-account ``tokens.json`` to rewrite on success.
            payload: Currently-on-disk payload (used to preserve scope /
                token_type if the refresh response omits them).
            refresh_token: The (still-valid) refresh token to spend.
            expires_at: Stale ``expires_at`` from disk, included on the
                outbound :class:`OAuthTokens` so :func:`refresh_tokens`
                has a complete model to pass.

        Returns:
            The freshly minted access token (no ``Bearer`` prefix).

        Raises:
            OAuthError: ``OAUTH_REFRESH_ERROR`` for any leg of the
                refresh — missing client info, network failure,
                malformed response.
        """
        # Lazy imports so this module stays cheap to import at
        # collection time (OAuthFlow pulls in httpx + threading).
        from mixpanel_data._internal.auth.flow import OAuthFlow
        from mixpanel_data._internal.auth.storage import OAuthStorage
        from mixpanel_data._internal.auth.token import OAuthTokens

        storage = OAuthStorage()
        client_info = storage.load_client_info(region=region)
        if client_info is None:
            raise OAuthError(
                (
                    f"OAuth client info for region '{region}' is missing; "
                    f"cannot refresh tokens for account '{name}'. "
                    f"Re-run `mp account login {name}`."
                ),
                code="OAUTH_REFRESH_ERROR",
                details={
                    "account_name": name,
                    "region": region,
                    "path": str(path),
                },
            )

        current = OAuthTokens(
            access_token=SecretStr(payload["access_token"]),
            refresh_token=SecretStr(refresh_token),
            expires_at=expires_at,
            scope=payload.get("scope"),
            token_type=payload.get("token_type", "Bearer"),
        )
        flow = OAuthFlow(region=region, storage=storage)
        new_tokens = flow.refresh_tokens(
            tokens=current, client_id=client_info.client_id
        )

        new_payload: dict[str, Any] = {
            "access_token": new_tokens.access_token.get_secret_value(),
            "expires_at": new_tokens.expires_at.isoformat(),
            "token_type": new_tokens.token_type,
        }
        if new_tokens.scope is not None:
            new_payload["scope"] = new_tokens.scope
        # Refresh tokens may rotate; if the IdP returns no new refresh token
        # we keep the existing one to preserve future refresh capability.
        if new_tokens.refresh_token is not None:
            new_payload["refresh_token"] = new_tokens.refresh_token.get_secret_value()
        else:
            new_payload["refresh_token"] = refresh_token

        atomic_write_bytes(path, json.dumps(new_payload).encode("utf-8"))
        return new_tokens.access_token.get_secret_value()

    def get_static_token(self, account: OAuthTokenAccount) -> str:
        """Return the static bearer for an :class:`OAuthTokenAccount`.

        Resolves the bearer from the inline ``token`` field if present;
        otherwise reads the environment variable named in ``token_env``.

        Args:
            account: The account whose ``token`` or ``token_env`` to resolve.

        Returns:
            The bearer token (no ``Bearer`` prefix).

        Raises:
            OAuthError: If ``token_env`` is set but the env var is unset
                or empty.
        """
        if account.token is not None:
            return account.token.get_secret_value()
        env_name = account.token_env
        # The Account validator guarantees one of the two is set.
        assert env_name is not None
        value = os.environ.get(env_name)
        if not value:
            raise OAuthError(
                (
                    f"OAuth account '{account.name}' references env var "
                    f"`{env_name}`, but it is not set or is empty."
                ),
                code="OAUTH_TOKEN_ERROR",
                details={"account_name": account.name, "env_var": env_name},
            )
        return value


__all__ = [
    "OnDiskTokenResolver",
]
