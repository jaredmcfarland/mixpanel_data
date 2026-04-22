"""Unit tests for the ``mp.accounts`` public namespace (T030).

The namespace mirrors the spec ``contracts/python-api.md §5``:
``list``, ``add``, ``remove``, ``use``, ``show``, ``test``, ``login``,
``logout``, ``token``, ``export_bridge``, ``remove_bridge``.

Tests focus on the wiring + delegation behavior; the underlying
``ConfigManager`` is exercised in ``test_config_v3.py``.

Reference: specs/042-auth-architecture-redesign/contracts/python-api.md §5.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from mixpanel_data import accounts as accounts_ns
from mixpanel_data._internal.config_v3 import ConfigManager
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
    """``mp.accounts.add(name, *, type, region, ...)`` writes accounts."""

    def test_service_account(self, cm: ConfigManager) -> None:
        """Adding a service account writes [accounts.NAME] with the new shape."""
        result = accounts_ns.add(
            "team",
            type="service_account",
            region="us",
            username="u",
            secret=SecretStr("s"),
        )
        assert isinstance(result, AccountSummary)
        assert result.name == "team"
        assert result.type == "service_account"

    def test_oauth_browser(self, cm: ConfigManager) -> None:
        """Adding an oauth_browser account writes only name + region."""
        result = accounts_ns.add("personal", type="oauth_browser", region="eu")
        assert result.type == "oauth_browser"

    def test_oauth_token_inline(self, cm: ConfigManager) -> None:
        """Adding an oauth_token account with inline token works."""
        result = accounts_ns.add(
            "ci", type="oauth_token", region="us", token=SecretStr("ey.x")
        )
        assert result.type == "oauth_token"

    def test_oauth_token_env(self, cm: ConfigManager) -> None:
        """Adding an oauth_token account with token_env works."""
        result = accounts_ns.add(
            "agent",
            type="oauth_token",
            region="us",
            token_env="MP_OAUTH_TOKEN",
        )
        assert result.type == "oauth_token"

    def test_first_account_auto_active(self, cm: ConfigManager) -> None:
        """Per FR-045, the first account auto-promotes to ``[active].account``."""
        accounts_ns.add(
            "first",
            type="service_account",
            region="us",
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
            username="u",
            secret=SecretStr("s"),
        )
        with pytest.raises(ConfigError):
            accounts_ns.add("x", type="oauth_browser", region="us")


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
            username="u",
            secret=SecretStr("s"),
        )
        accounts_ns.add("second", type="oauth_browser", region="us")
        accounts_ns.use("second")
        assert cm.get_active().account == "second"

    def test_use_does_not_touch_project_or_workspace(self, cm: ConfigManager) -> None:
        """Per FR-033, ``accounts.use`` updates only the account axis."""
        accounts_ns.add(
            "first",
            type="service_account",
            region="us",
            username="u",
            secret=SecretStr("s"),
        )
        cm.set_active(project="3713224", workspace=42)
        accounts_ns.add("other", type="oauth_browser", region="us")
        accounts_ns.use("other")
        active = cm.get_active()
        assert active.account == "other"
        assert active.project == "3713224"
        assert active.workspace == 42


class TestShow:
    """``mp.accounts.show()`` returns the active or named account summary."""

    def test_show_named(self, cm: ConfigManager) -> None:
        """``show(name)`` returns that account's summary."""
        accounts_ns.add(
            "team",
            type="service_account",
            region="us",
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
            token=SecretStr("ey.tok-123"),
        )
        result = accounts_ns.token("ci")
        assert result == "ey.tok-123"


class TestStubs:
    """Bridge functions are stubs in Phase 4 — they raise NotImplementedError."""

    def test_export_bridge_stub(self, cm: ConfigManager, tmp_path: Path) -> None:
        """``export_bridge`` is a stub until Phase 8."""
        accounts_ns.add(
            "team",
            type="service_account",
            region="us",
            username="u",
            secret=SecretStr("s"),
        )
        with pytest.raises(NotImplementedError):
            accounts_ns.export_bridge(to=tmp_path / "bridge.json")

    def test_remove_bridge_stub(self, cm: ConfigManager) -> None:
        """``remove_bridge`` is a stub until Phase 8."""
        with pytest.raises(NotImplementedError):
            accounts_ns.remove_bridge()
