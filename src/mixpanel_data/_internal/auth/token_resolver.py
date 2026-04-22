"""Concrete :class:`TokenResolver` implementations.

The redesigned auth subsystem decouples ``Account`` (which knows what kind
of credentials it represents) from token *materialization* (which knows
where and how to fetch the bearer). This module ships
:class:`OnDiskTokenResolver`, the default implementation that reads OAuth
browser tokens from ``~/.mp/accounts/{name}/tokens.json`` and static
tokens from inline ``SecretStr`` fields or environment variables.

Refresh logic for browser tokens delegates to existing
:class:`mixpanel_data._internal.auth.flow.OAuthFlow` machinery (deferred —
filled in during Phase 4 of the rollout). For now, an expired browser
token without a refresh token raises :class:`OAuthError` directly.

Reference: ``specs/042-auth-architecture-redesign/data-model.md``,
``contracts/python-api.md`` §5.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from mixpanel_data._internal.auth.account import (
    OAuthTokenAccount,
    Region,
    TokenResolver,
)
from mixpanel_data.exceptions import OAuthError

if TYPE_CHECKING:
    pass


def _account_tokens_path(name: str) -> Path:
    """Return ``~/.mp/accounts/{name}/tokens.json`` for the given account name.

    Args:
        name: Account name (validated upstream by the ``Account`` model).

    Returns:
        Absolute path to the per-account tokens file.
    """
    return Path.home() / ".mp" / "accounts" / name / "tokens.json"


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
        if isinstance(expires_raw, str) and expires_raw:
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
                # Refresh path — delegated to OAuthFlow in a later phase.
                raise OAuthError(
                    (
                        f"OAuth access token for account '{name}' has "
                        f"expired. Token refresh is not yet wired up; re-run "
                        f"`mp account login {name}` to obtain a fresh token."
                    ),
                    code="OAUTH_REFRESH_ERROR",
                    details={
                        "account_name": name,
                        "region": region,
                        "path": str(path),
                    },
                )

        return access_token

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
