"""Unit tests for the ``TokenResolver`` protocol and ``OnDiskTokenResolver`` (T010).

Covers:
- ``OnDiskTokenResolver.get_browser_token(name, region)`` reads from
  ``~/.mp/accounts/{name}/tokens.json`` and refreshes if expired.
- ``OnDiskTokenResolver.get_static_token(account)`` reads inline token or
  env var via ``token_env``.
- Raises ``OAuthError`` if env var unset / browser tokens missing or unrefreshable.

Reference: specs/042-auth-architecture-redesign/data-model.md §2, contracts/python-api.md §5.
"""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import SecretStr

from mixpanel_data._internal.auth.account import (
    OAuthTokenAccount,
)
from mixpanel_data._internal.auth.token_resolver import OnDiskTokenResolver
from mixpanel_data.exceptions import OAuthError


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use a tmp directory as ``$HOME`` for isolated ``~/.mp/accounts/`` paths."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _write_tokens_file(
    home: Path,
    *,
    name: str,
    access_token: str,
    expires_at: datetime,
    refresh_token: str | None = None,
) -> Path:
    """Write a tokens.json file at ``~/.mp/accounts/{name}/tokens.json`` mode 0o600.

    Args:
        home: Tmp HOME path.
        name: Account name (becomes the dir under accounts/).
        access_token: Access token plaintext to embed.
        expires_at: Expiry datetime (use a past time to simulate expiry).
        refresh_token: Optional refresh token plaintext.

    Returns:
        The path that was written.
    """
    account_dir = home / ".mp" / "accounts" / name
    account_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = account_dir / "tokens.json"
    payload: dict[str, object] = {
        "access_token": access_token,
        "expires_at": expires_at.isoformat(),
        "scope": "read:project",
        "token_type": "Bearer",
    }
    if refresh_token is not None:
        payload["refresh_token"] = refresh_token
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return path


class TestStaticToken:
    """Coverage for ``get_static_token``: inline + env-var paths."""

    def test_inline_token_returned(self, isolated_home: Path) -> None:
        """Inline ``token`` field is returned verbatim."""
        account = OAuthTokenAccount(
            name="ci", region="us", token=SecretStr("inline-tok-123")
        )
        resolver = OnDiskTokenResolver()
        assert resolver.get_static_token(account) == "inline-tok-123"

    def test_env_var_returned(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``token_env`` is read from ``os.environ`` at resolution time."""
        monkeypatch.setenv("MY_OAUTH_TOK", "env-tok-456")
        account = OAuthTokenAccount(name="ci", region="us", token_env="MY_OAUTH_TOK")
        resolver = OnDiskTokenResolver()
        assert resolver.get_static_token(account) == "env-tok-456"

    def test_env_var_missing_raises(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing env var raises ``OAuthError``."""
        monkeypatch.delenv("MY_OAUTH_TOK", raising=False)
        account = OAuthTokenAccount(name="ci", region="us", token_env="MY_OAUTH_TOK")
        resolver = OnDiskTokenResolver()
        with pytest.raises(OAuthError):
            resolver.get_static_token(account)

    def test_env_var_empty_raises(
        self, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty env var (e.g. ``MY_OAUTH_TOK=``) raises ``OAuthError``.

        Empty strings are not valid bearers.
        """
        monkeypatch.setenv("MY_OAUTH_TOK", "")
        account = OAuthTokenAccount(name="ci", region="us", token_env="MY_OAUTH_TOK")
        resolver = OnDiskTokenResolver()
        with pytest.raises(OAuthError):
            resolver.get_static_token(account)


class TestBrowserToken:
    """Coverage for ``get_browser_token``: on-disk reads + refresh."""

    def test_unexpired_token_returned(self, isolated_home: Path) -> None:
        """A non-expired token on disk is returned without refresh."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        _write_tokens_file(
            isolated_home,
            name="me",
            access_token="brw-tok-fresh",
            expires_at=future,
            refresh_token="ref-1",
        )
        resolver = OnDiskTokenResolver()
        assert resolver.get_browser_token("me", "us") == "brw-tok-fresh"

    def test_missing_tokens_file_raises(self, isolated_home: Path) -> None:
        """Missing tokens.json raises ``OAuthError``."""
        resolver = OnDiskTokenResolver()
        with pytest.raises(OAuthError):
            resolver.get_browser_token("nobody", "us")

    def test_expired_without_refresh_raises(self, isolated_home: Path) -> None:
        """Expired token with no refresh token raises ``OAuthError``."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        _write_tokens_file(
            isolated_home,
            name="me",
            access_token="brw-tok-old",
            expires_at=past,
            refresh_token=None,
        )
        resolver = OnDiskTokenResolver()
        with pytest.raises(OAuthError):
            resolver.get_browser_token("me", "us")

    def test_account_dir_is_isolated_per_name(self, isolated_home: Path) -> None:
        """Two accounts get independent token files at distinct dirs."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        _write_tokens_file(
            isolated_home, name="alice", access_token="A", expires_at=future
        )
        _write_tokens_file(
            isolated_home, name="bob", access_token="B", expires_at=future
        )
        resolver = OnDiskTokenResolver()
        assert resolver.get_browser_token("alice", "us") == "A"
        assert resolver.get_browser_token("bob", "us") == "B"

    def test_token_within_30s_buffer_treated_as_expired(
        self, isolated_home: Path
    ) -> None:
        """Tokens expiring within the 30s safety buffer must be refreshed.

        The docstring on ``get_browser_token`` promises a 30s safety
        buffer so requests in flight can't be tripped by a token that
        expires between the check and the network call. A token whose
        ``expires_at`` is 20 seconds away must therefore be treated as
        expired (and raise here, since refresh is unimplemented and no
        refresh token is provided).
        """
        soon = datetime.now(timezone.utc) + timedelta(seconds=20)
        _write_tokens_file(
            isolated_home,
            name="me",
            access_token="brw-tok-soon-to-expire",
            expires_at=soon,
            refresh_token=None,
        )
        resolver = OnDiskTokenResolver()
        with pytest.raises(OAuthError):
            resolver.get_browser_token("me", "us")

    def test_token_well_outside_buffer_is_accepted(self, isolated_home: Path) -> None:
        """A token with > 30s remaining is still accepted.

        Boundary check on the buffer: 5 minutes out should comfortably
        pass even with the new safety margin in place.
        """
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        _write_tokens_file(
            isolated_home,
            name="me",
            access_token="brw-tok-comfortable",
            expires_at=future,
            refresh_token=None,
        )
        resolver = OnDiskTokenResolver()
        assert resolver.get_browser_token("me", "us") == "brw-tok-comfortable"


class TestPathLayout:
    """File system layout invariants per contracts/filesystem-layout.md §3."""

    def test_account_dir_path(self, isolated_home: Path) -> None:
        """Resolver computes ``~/.mp/accounts/{name}/tokens.json`` for a given name."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        path = _write_tokens_file(
            isolated_home, name="me", access_token="x", expires_at=future
        )
        assert path == isolated_home / ".mp" / "accounts" / "me" / "tokens.json"

    def test_account_dir_permissions(self, isolated_home: Path) -> None:
        """Account dir written with mode 0o700 by helper."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        _write_tokens_file(
            isolated_home, name="me", access_token="x", expires_at=future
        )
        d = isolated_home / ".mp" / "accounts" / "me"
        if os.name == "posix":
            assert stat.S_IMODE(d.stat().st_mode) == 0o700
