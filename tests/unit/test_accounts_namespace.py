"""Unit tests for the ``mp.accounts`` public namespace (T030).

The namespace mirrors the spec ``contracts/python-api.md §5``:
``list``, ``add``, ``update``, ``remove``, ``use``, ``show``, ``test``,
``login``, ``logout``, ``token``, ``export_bridge``, ``remove_bridge``.

Tests focus on the wiring + delegation behavior; the underlying
``ConfigManager`` is exercised in ``test_config_v3.py``.

Reference: specs/042-auth-architecture-redesign/contracts/python-api.md §5.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from mixpanel_data import accounts as accounts_ns
from mixpanel_data._internal.config import ConfigManager
from mixpanel_data.exceptions import (
    AccountInUseError,
    ConfigError,
)
from mixpanel_data.types import AccountSummary


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate $HOME so the namespace's default ConfigManager hits tmp paths."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MP_CONFIG_PATH", str(tmp_path / ".mp" / "config.toml"))


@pytest.fixture
def cm() -> ConfigManager:
    """Return a ConfigManager pointing at the tmp config path."""
    return ConfigManager()


class TestAdd:
    """``mp.accounts.add(name, *, type, region, default_project, ...)``."""

    def test_service_account(self, cm: ConfigManager) -> None:
        """Adding a service account writes [accounts.NAME] with default_project."""
        result = accounts_ns.add(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        assert isinstance(result, AccountSummary)
        assert result.name == "team"
        assert result.type == "service_account"
        assert cm.get_account("team").default_project == "3713224"

    def test_service_account_without_default_project_raises(
        self, cm: ConfigManager
    ) -> None:
        """SA must provide ``default_project`` per FR-004."""
        with pytest.raises(ConfigError):
            accounts_ns.add(
                "team",
                type="service_account",
                region="us",
                username="u",
                secret=SecretStr("s"),
            )

    def test_oauth_browser_without_default_project_ok(self, cm: ConfigManager) -> None:
        """``oauth_browser`` may omit ``default_project`` — backfilled at login."""
        result = accounts_ns.add("personal", type="oauth_browser", region="eu")
        assert result.type == "oauth_browser"
        assert cm.get_account("personal").default_project is None

    def test_oauth_browser_with_default_project_ok(self, cm: ConfigManager) -> None:
        """``oauth_browser`` may also pre-set ``default_project``."""
        result = accounts_ns.add(
            "personal", type="oauth_browser", region="eu", default_project="12345"
        )
        assert result.type == "oauth_browser"
        assert cm.get_account("personal").default_project == "12345"

    def test_oauth_token_inline(self, cm: ConfigManager) -> None:
        """Adding an oauth_token account with inline token + default_project works."""
        result = accounts_ns.add(
            "ci",
            type="oauth_token",
            region="us",
            default_project="3713224",
            token=SecretStr("ey.x"),
        )
        assert result.type == "oauth_token"

    def test_oauth_token_env(self, cm: ConfigManager) -> None:
        """Adding an oauth_token account with token_env + default_project works."""
        result = accounts_ns.add(
            "agent",
            type="oauth_token",
            region="us",
            default_project="3713224",
            token_env="MP_OAUTH_TOKEN",
        )
        assert result.type == "oauth_token"

    def test_oauth_token_without_default_project_raises(
        self, cm: ConfigManager
    ) -> None:
        """oauth_token must provide ``default_project`` per FR-004."""
        with pytest.raises(ConfigError):
            accounts_ns.add(
                "agent",
                type="oauth_token",
                region="us",
                token=SecretStr("ey.x"),
            )

    def test_first_account_auto_active(self, cm: ConfigManager) -> None:
        """Per FR-045, the first account auto-promotes to ``[active].account``."""
        accounts_ns.add(
            "first",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        assert cm.get_active().account == "first"

    def test_subsequent_account_does_not_auto_active(self, cm: ConfigManager) -> None:
        """A second account does NOT replace the active selection."""
        accounts_ns.add(
            "first",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        accounts_ns.add("second", type="oauth_browser", region="us")
        assert cm.get_active().account == "first"

    def test_duplicate_name_raises(self, cm: ConfigManager) -> None:
        """Adding an existing name raises ConfigError."""
        accounts_ns.add(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        with pytest.raises(ConfigError):
            accounts_ns.add("x", type="oauth_browser", region="us")


class TestUpdate:
    """``mp.accounts.update(name, ...)`` mutates fields in place."""

    def test_update_default_project(self, cm: ConfigManager) -> None:
        """Updating ``default_project`` rewrites the account block."""
        accounts_ns.add(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        accounts_ns.update("team", default_project="9999999")
        assert cm.get_account("team").default_project == "9999999"

    def test_update_region(self, cm: ConfigManager) -> None:
        """Updating ``region`` works for any account type."""
        accounts_ns.add("personal", type="oauth_browser", region="us")
        accounts_ns.update("personal", region="eu")
        assert cm.get_account("personal").region == "eu"

    def test_update_missing_account_raises(self, cm: ConfigManager) -> None:
        """Updating a non-existent account raises."""
        with pytest.raises(ConfigError):
            accounts_ns.update("ghost", default_project="1")

    def test_update_type_incompatible_field_raises(self, cm: ConfigManager) -> None:
        """``username=`` on an oauth_browser account raises."""
        accounts_ns.add("personal", type="oauth_browser", region="us")
        with pytest.raises(ConfigError):
            accounts_ns.update("personal", username="bad")


class TestList:
    """``mp.accounts.list()`` returns AccountSummary records."""

    def test_empty(self, cm: ConfigManager) -> None:
        """No accounts → empty list."""
        assert accounts_ns.list() == []

    def test_returns_summaries(self, cm: ConfigManager) -> None:
        """Each entry is an AccountSummary."""
        accounts_ns.add(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        result = accounts_ns.list()
        assert len(result) == 1
        assert isinstance(result[0], AccountSummary)


class TestUse:
    """``mp.accounts.use(name)`` writes ``[active].account``."""

    def test_use_writes_active_account(self, cm: ConfigManager) -> None:
        """``use(name)`` sets ``[active].account``."""
        accounts_ns.add(
            "first",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        accounts_ns.add("second", type="oauth_browser", region="us")
        accounts_ns.use("second")
        assert cm.get_active().account == "second"

    def test_use_clears_prior_workspace(self, cm: ConfigManager) -> None:
        """``accounts.use(NAME)`` drops any prior ``[active].workspace``.

        Workspaces are project-scoped, so a workspace ID set by the prior
        account would resolve to a foreign workspace (or 404) under the new
        account's project. Project itself travels with the account via
        :attr:`Account.default_project` — no separate axis to reset.
        """
        accounts_ns.add(
            "first",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.set_active(workspace=42)
        accounts_ns.add(
            "other",
            type="service_account",
            region="us",
            default_project="9999999",
            username="o",
            secret=SecretStr("o"),
        )
        accounts_ns.use("other")
        active = cm.get_active()
        assert active.account == "other"
        assert active.workspace is None
        # Project travels with the account.
        assert cm.get_account("other").default_project == "9999999"


class TestShow:
    """``mp.accounts.show()`` returns the active or named account summary."""

    def test_show_named(self, cm: ConfigManager) -> None:
        """``show(name)`` returns that account's summary."""
        accounts_ns.add(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        result = accounts_ns.show("team")
        assert result.name == "team"

    def test_show_active_when_no_name(self, cm: ConfigManager) -> None:
        """``show()`` (no arg) returns the active account."""
        accounts_ns.add(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        result = accounts_ns.show()
        assert result.name == "team"

    def test_show_missing_raises(self, cm: ConfigManager) -> None:
        """``show("ghost")`` raises ConfigError."""
        with pytest.raises(ConfigError):
            accounts_ns.show("ghost")


class TestRemove:
    """``mp.accounts.remove`` mirrors ConfigManager semantics."""

    def test_remove_unused(self, cm: ConfigManager) -> None:
        """An unreferenced account removes cleanly."""
        accounts_ns.add(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        orphans = accounts_ns.remove("x")
        assert orphans == []
        assert accounts_ns.list() == []

    def test_remove_referenced_without_force(self, cm: ConfigManager) -> None:
        """Without ``force``, removing a referenced account raises."""
        accounts_ns.add(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.add_target("ecom", account="x", project="3018488")
        with pytest.raises(AccountInUseError):
            accounts_ns.remove("x")


class TestToken:
    """``mp.accounts.token(name)`` returns the bearer for OAuth accounts."""

    def test_token_for_service_account_returns_none(self, cm: ConfigManager) -> None:
        """ServiceAccount has no bearer → returns None or 'N/A'."""
        accounts_ns.add(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        result = accounts_ns.token("team")
        assert result is None or result == "N/A"

    def test_token_for_oauth_token_inline(self, cm: ConfigManager) -> None:
        """OAuthTokenAccount with inline token returns the plaintext bearer."""
        accounts_ns.add(
            "ci",
            type="oauth_token",
            region="us",
            default_project="3713224",
            token=SecretStr("ey.tok-123"),
        )
        result = accounts_ns.token("ci")
        assert result == "ey.tok-123"


# Cluster C2 (T089 / T090) replaced the Phase-4 stubs with real bridge
# writers. Functional coverage now lives in tests/unit/test_bridge_export.py
# (15 tests across the standalone bridge.export_bridge / remove_bridge
# functions plus the mp.accounts wrappers).


class TestTest:
    """``mp.accounts.test(name)`` runs a real ``/me`` probe and reports outcome."""

    def test_missing_account_returns_not_found(self, cm: ConfigManager) -> None:
        """Unknown account → ``ok=False`` with a helpful error string."""
        result = accounts_ns.test("ghost")
        assert result.ok is False
        assert result.error is not None
        assert "ghost" in result.error.lower() or "not found" in result.error.lower()

    def test_no_active_account_returns_error(self, cm: ConfigManager) -> None:
        """No name + no active account → ``ok=False``."""
        result = accounts_ns.test()
        assert result.ok is False
        assert result.error is not None

    def test_successful_probe_populates_user_and_project_count(
        self, cm: ConfigManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successful ``/me`` probe → ``ok=True`` with user identity + project count."""
        accounts_ns.add(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        from mixpanel_data._internal import api_client as api_client_mod

        def _fake_me(self: object) -> dict[str, object]:
            """Return canned /me payload with two projects + a user."""
            return {
                "user_id": 42,
                "user_email": "team@example.com",
                "projects": {
                    "3713224": {"name": "Alpha", "organization_id": 1},
                    "3018488": {"name": "Beta", "organization_id": 1},
                },
            }

        monkeypatch.setattr(api_client_mod.MixpanelAPIClient, "me", _fake_me)
        result = accounts_ns.test("team")
        assert result.ok is True
        assert result.error is None
        assert result.user is not None
        assert result.user.id == 42
        assert result.user.email == "team@example.com"
        assert result.accessible_project_count == 2

    def test_probe_failure_captured_in_error(
        self, cm: ConfigManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the underlying ``/me`` call raises, the failure is captured (never re-raised)."""
        accounts_ns.add(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        from mixpanel_data._internal import api_client as api_client_mod
        from mixpanel_data.exceptions import AuthenticationError

        def _fail_me(self: object) -> dict[str, object]:
            """Raise a 401 to simulate stale credentials."""
            raise AuthenticationError("invalid credentials")

        monkeypatch.setattr(api_client_mod.MixpanelAPIClient, "me", _fail_me)
        result = accounts_ns.test("team")
        assert result.ok is False
        assert result.error is not None
        assert "invalid credentials" in result.error or "/me" in result.error

    def test_active_account_used_when_name_omitted(
        self, cm: ConfigManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``test()`` with no name probes the active account."""
        accounts_ns.add(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        # First-account auto-promote → "team" is now [active].account
        from mixpanel_data._internal import api_client as api_client_mod

        def _fake_me(self: object) -> dict[str, object]:
            """Minimal /me payload — just enough to succeed."""
            return {"user_id": 1, "user_email": "x@example.com", "projects": {}}

        monkeypatch.setattr(api_client_mod.MixpanelAPIClient, "me", _fake_me)
        result = accounts_ns.test()
        assert result.ok is True
        assert result.account_name == "team"


class TestLogin:
    """Coverage for Fix 17 — ``mp.accounts.login(name)``."""

    def test_login_rejects_non_oauth_browser_account(self, cm: ConfigManager) -> None:
        """``login`` raises ConfigError for service_account / oauth_token types."""
        accounts_ns.add(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        with pytest.raises(ConfigError, match="oauth_browser"):
            accounts_ns.login("team")

    def test_login_missing_account_raises(self, cm: ConfigManager) -> None:
        """``login`` raises ConfigError if the account is not configured."""
        with pytest.raises(ConfigError, match="not found"):
            accounts_ns.login("ghost")

    def test_login_persists_tokens_and_backfills_default_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        cm: ConfigManager,
    ) -> None:
        """Successful PKCE flow writes per-account tokens.json and backfills default_project."""
        from datetime import datetime, timedelta, timezone

        from mixpanel_data._internal.auth import flow as flow_mod
        from mixpanel_data._internal.auth.token import OAuthTokens

        accounts_ns.add("personal", type="oauth_browser", region="us")

        new_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        captured: dict[str, object] = {}

        def _fake_login(
            self: object, project_id: str | None = None, *, persist: bool = True
        ) -> OAuthTokens:
            """Stub OAuthFlow.login — record the persist kwarg, return tokens."""
            captured["project_id"] = project_id
            captured["persist"] = persist
            return OAuthTokens(
                access_token=SecretStr("brw-tok-fresh"),
                refresh_token=SecretStr("brw-refresh-fresh"),
                expires_at=new_expires,
                scope="read:project",
                token_type="Bearer",
            )

        monkeypatch.setattr(flow_mod.OAuthFlow, "login", _fake_login)

        # Stub the /me probe to return a single project.
        from mixpanel_data._internal import api_client as api_client_mod

        def _fake_me(self: object) -> dict[str, object]:
            """Return canned /me payload with one project + a user."""
            return {
                "user_id": 7,
                "user_email": "alice@example.com",
                "projects": {"3713224": {"name": "Demo", "organization_id": 1}},
            }

        monkeypatch.setattr(api_client_mod.MixpanelAPIClient, "me", _fake_me)

        result = accounts_ns.login("personal")

        assert captured["persist"] is False
        assert captured["project_id"] is None  # account had no default_project
        # Tokens persisted to per-account v3 path
        tokens_path = tmp_path / ".mp" / "accounts" / "personal" / "tokens.json"
        assert tokens_path.exists()
        payload = json.loads(tokens_path.read_text(encoding="utf-8"))
        assert payload["access_token"] == "brw-tok-fresh"
        assert payload["refresh_token"] == "brw-refresh-fresh"
        # File mode preserved at 0o600.
        assert (tokens_path.stat().st_mode & 0o777) == 0o600
        # default_project backfilled from /me probe
        refreshed = cm.get_account("personal")
        assert refreshed.default_project == "3713224"
        # OAuthLoginResult shape
        assert result.account_name == "personal"
        assert result.user is not None
        assert result.user.email == "alice@example.com"
        assert result.expires_at == new_expires
        assert result.tokens_path == tokens_path
