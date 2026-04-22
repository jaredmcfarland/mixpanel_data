"""Unit tests for the ``ConfigManager``.

The ConfigManager operates on a single TOML schema with three sections:
``[active]``, ``[accounts.NAME]``, ``[targets.NAME]``, plus optional
``[settings]``. The ``[active]`` block holds only ``account`` and
``workspace`` — project lives on the account as ``default_project``.

Reference: specs/042-auth-architecture-redesign/contracts/config-schema.md §1.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from mixpanel_data._internal.auth.account import (
    OAuthBrowserAccount,
    OAuthTokenAccount,
    ServiceAccount,
)
from mixpanel_data._internal.auth.session import ActiveSession
from mixpanel_data._internal.config_v3 import ConfigManager
from mixpanel_data.exceptions import ConfigError
from mixpanel_data.types import AccountSummary, Target

# Path to the fixture corpus (constructed from project root).
_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "configs"


@pytest.fixture
def empty_config_path(tmp_path: Path) -> Path:
    """Return a path to a non-existent config file (test load-from-missing)."""
    return tmp_path / "config.toml"


@pytest.fixture
def cm(empty_config_path: Path) -> ConfigManager:
    """Return a fresh v3 ConfigManager pointing at a tmp empty path."""
    return ConfigManager(config_path=empty_config_path)


class TestLoadEmptyOrMissing:
    """``load`` over an empty or missing file returns a clean state."""

    def test_load_missing_file(self, cm: ConfigManager) -> None:
        """No config file → empty accounts/targets, empty active."""
        assert cm.list_accounts() == []
        assert cm.list_targets() == []
        active = cm.get_active()
        assert active == ActiveSession()

    def test_load_empty_file(self, tmp_path: Path) -> None:
        """An empty TOML file is also valid (no sections) — no errors."""
        p = tmp_path / "config.toml"
        p.write_text("", encoding="utf-8")
        cm = ConfigManager(config_path=p)
        assert cm.list_accounts() == []
        assert cm.list_targets() == []
        assert cm.get_active() == ActiveSession()


class TestAddAccount:
    """``add_account`` writes ``[accounts.NAME]`` blocks."""

    def test_service_account(self, cm: ConfigManager) -> None:
        """ServiceAccount round-trips through the file (with default_project)."""
        cm.add_account(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="sa.user",
            secret=SecretStr("super-secret"),
        )
        cm2 = ConfigManager(config_path=cm.config_path)
        accounts = cm2.list_accounts()
        assert len(accounts) == 1
        assert accounts[0].name == "team"
        assert accounts[0].type == "service_account"
        assert accounts[0].region == "us"
        loaded = cm2.get_account("team")
        assert isinstance(loaded, ServiceAccount)
        assert loaded.username == "sa.user"
        assert loaded.secret.get_secret_value() == "super-secret"
        assert loaded.default_project == "3713224"

    def test_oauth_browser_account(self, cm: ConfigManager) -> None:
        """OAuthBrowserAccount has no inline secret — only name+region (+optional default_project)."""
        cm.add_account("personal", type="oauth_browser", region="eu")
        cm2 = ConfigManager(config_path=cm.config_path)
        loaded = cm2.get_account("personal")
        assert isinstance(loaded, OAuthBrowserAccount)
        assert loaded.region == "eu"
        assert loaded.default_project is None

    def test_oauth_token_with_inline(self, cm: ConfigManager) -> None:
        """OAuthTokenAccount with inline token + default_project round-trips."""
        cm.add_account(
            "ci",
            type="oauth_token",
            region="us",
            default_project="3713224",
            token=SecretStr("ey.tok"),
        )
        cm2 = ConfigManager(config_path=cm.config_path)
        loaded = cm2.get_account("ci")
        assert isinstance(loaded, OAuthTokenAccount)
        assert loaded.token is not None
        assert loaded.token.get_secret_value() == "ey.tok"
        assert loaded.token_env is None
        assert loaded.default_project == "3713224"

    def test_oauth_token_with_env(self, cm: ConfigManager) -> None:
        """OAuthTokenAccount with token_env + default_project round-trips."""
        cm.add_account(
            "agent",
            type="oauth_token",
            region="eu",
            default_project="3713224",
            token_env="MP_OAUTH_TOKEN",
        )
        cm2 = ConfigManager(config_path=cm.config_path)
        loaded = cm2.get_account("agent")
        assert isinstance(loaded, OAuthTokenAccount)
        assert loaded.token is None
        assert loaded.token_env == "MP_OAUTH_TOKEN"

    def test_service_account_without_default_project_raises(
        self, cm: ConfigManager
    ) -> None:
        """SA without ``default_project`` raises (FR-004)."""
        with pytest.raises(ConfigError):
            cm.add_account(
                "team",
                type="service_account",
                region="us",
                username="u",
                secret=SecretStr("s"),
            )

    def test_oauth_token_without_default_project_raises(
        self, cm: ConfigManager
    ) -> None:
        """oauth_token without ``default_project`` raises (FR-004)."""
        with pytest.raises(ConfigError):
            cm.add_account(
                "ci",
                type="oauth_token",
                region="us",
                token=SecretStr("ey.tok"),
            )

    def test_duplicate_name_raises(self, cm: ConfigManager) -> None:
        """Adding an existing name raises ConfigError."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        with pytest.raises(ConfigError):
            cm.add_account("x", type="oauth_browser", region="us")

    def test_invalid_name_raises(self, cm: ConfigManager) -> None:
        """Names violating the pattern raise ConfigError."""
        with pytest.raises((ConfigError, ValueError)):
            cm.add_account(
                "bad name",  # space is invalid
                type="service_account",
                region="us",
                default_project="3713224",
                username="u",
                secret=SecretStr("s"),
            )


class TestUpdateAccount:
    """``update_account`` mutates fields in place."""

    def test_update_default_project(self, cm: ConfigManager) -> None:
        """Updating ``default_project`` rewrites the account's home project."""
        cm.add_account(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.update_account("team", default_project="9999999")
        loaded = cm.get_account("team")
        assert loaded.default_project == "9999999"

    def test_update_region(self, cm: ConfigManager) -> None:
        """Region updates work for any account type."""
        cm.add_account("personal", type="oauth_browser", region="us")
        cm.update_account("personal", region="eu")
        assert cm.get_account("personal").region == "eu"

    def test_update_missing_account_raises(self, cm: ConfigManager) -> None:
        """Updating a non-existent account raises."""
        with pytest.raises(ConfigError):
            cm.update_account("ghost", default_project="1")

    def test_update_username_on_browser_raises(self, cm: ConfigManager) -> None:
        """``username=`` on an oauth_browser account raises."""
        cm.add_account("personal", type="oauth_browser", region="us")
        with pytest.raises(ConfigError):
            cm.update_account("personal", username="u")


class TestSetActive:
    """``set_active`` writes ``[active]`` (account + workspace only)."""

    def test_set_account_only(self, cm: ConfigManager) -> None:
        """Setting account axis writes only that key."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.set_active(account="x")
        assert cm.get_active() == ActiveSession(account="x")

    def test_set_workspace_only(self, cm: ConfigManager) -> None:
        """Setting workspace axis writes only that key."""
        cm.set_active(workspace=8)
        assert cm.get_active() == ActiveSession(workspace=8)

    def test_set_both(self, cm: ConfigManager) -> None:
        """Setting both axes in one call."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.set_active(account="x", workspace=8)
        active = cm.get_active()
        assert active.account == "x"
        assert active.workspace == 8

    def test_account_must_exist(self, cm: ConfigManager) -> None:
        """Setting active.account to a missing account raises ConfigError."""
        with pytest.raises(ConfigError):
            cm.set_active(account="nonexistent")

    def test_workspace_must_be_positive(self, cm: ConfigManager) -> None:
        """``workspace`` axis must be > 0."""
        with pytest.raises(ConfigError):
            cm.set_active(workspace=0)
        with pytest.raises(ConfigError):
            cm.set_active(workspace=-5)

    def test_partial_update_preserves_other_axis(self, cm: ConfigManager) -> None:
        """``set_active(workspace=...)`` does NOT touch existing account."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.set_active(account="x")
        cm.set_active(workspace=8)
        active = cm.get_active()
        assert active.account == "x"
        assert active.workspace == 8


class TestTargets:
    """``add_target`` / ``list_targets`` / ``get_target`` / ``apply_target``."""

    def test_add_target_minimal(self, cm: ConfigManager) -> None:
        """Target with no workspace omits the workspace key."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.add_target("ecom", account="x", project="3018488")
        targets = cm.list_targets()
        assert len(targets) == 1
        assert targets[0] == Target(name="ecom", account="x", project="3018488")

    def test_add_target_with_workspace(self, cm: ConfigManager) -> None:
        """Target with workspace persists all three fields."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.add_target("ecom", account="x", project="3018488", workspace=42)
        t = cm.get_target("ecom")
        assert t.workspace == 42

    def test_add_target_referencing_missing_account_raises(
        self, cm: ConfigManager
    ) -> None:
        """Adding a target that references a non-existent account raises."""
        with pytest.raises(ConfigError):
            cm.add_target("ecom", account="nonexistent", project="3018488")

    def test_remove_target(self, cm: ConfigManager) -> None:
        """``remove_target`` deletes the entry; subsequent get_target raises."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.add_target("ecom", account="x", project="3018488")
        cm.remove_target("ecom")
        with pytest.raises(ConfigError):
            cm.get_target("ecom")

    def test_apply_target_writes_account_workspace_and_default_project(
        self, cm: ConfigManager
    ) -> None:
        """``apply_target`` writes account+workspace to ``[active]`` AND
        sets the target account's ``default_project`` to the target's project.
        """
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.add_target("ecom", account="x", project="3018488", workspace=8)
        cm.apply_target("ecom")
        active = cm.get_active()
        assert active.account == "x"
        assert active.workspace == 8
        # Project went onto the account, not into [active].
        assert cm.get_account("x").default_project == "3018488"

    def test_apply_target_missing_workspace_clears_workspace(
        self, cm: ConfigManager
    ) -> None:
        """Applying a target with no workspace clears any prior workspace."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.set_active(account="x", workspace=99)
        cm.add_target("nows", account="x", project="3018488")
        cm.apply_target("nows")
        active = cm.get_active()
        assert active.workspace is None
        # Project goes to the account.
        assert cm.get_account("x").default_project == "3018488"

    def test_apply_missing_target_raises(self, cm: ConfigManager) -> None:
        """``apply_target`` against an unknown target raises ConfigError."""
        with pytest.raises(ConfigError):
            cm.apply_target("ghost")


class TestListAccounts:
    """``list_accounts`` returns ``AccountSummary`` records."""

    def test_returns_summary_objects(self, cm: ConfigManager) -> None:
        """Every entry is an AccountSummary with the right fields."""
        cm.add_account(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.add_account("personal", type="oauth_browser", region="eu")
        summaries = cm.list_accounts()
        assert all(isinstance(a, AccountSummary) for a in summaries)
        names = sorted(a.name for a in summaries)
        assert names == ["personal", "team"]

    def test_is_active_flag(self, cm: ConfigManager) -> None:
        """``is_active`` reflects ``[active].account``."""
        cm.add_account(
            "team",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.add_account("personal", type="oauth_browser", region="us")
        cm.set_active(account="team")
        by_name = {a.name: a for a in cm.list_accounts()}
        assert by_name["team"].is_active is True
        assert by_name["personal"].is_active is False

    def test_referenced_by_targets(self, cm: ConfigManager) -> None:
        """``referenced_by_targets`` lists target names referencing the account."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.add_target("ecom", account="x", project="3018488")
        cm.add_target("ai", account="x", project="3713224")
        summary = next(a for a in cm.list_accounts() if a.name == "x")
        assert sorted(summary.referenced_by_targets) == ["ai", "ecom"]


class TestRemoveAccount:
    """``remove_account`` raises ``AccountInUseError`` when targets depend on it."""

    def test_remove_unused(self, cm: ConfigManager) -> None:
        """An unreferenced account is removable without force."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        orphans = cm.remove_account("x")
        assert orphans == []
        assert cm.list_accounts() == []

    def test_remove_referenced_without_force_raises(self, cm: ConfigManager) -> None:
        """Removing a referenced account without ``force`` raises."""
        from mixpanel_data.exceptions import AccountInUseError

        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.add_target("ecom", account="x", project="3018488")
        with pytest.raises(AccountInUseError):
            cm.remove_account("x")

    def test_remove_with_force_returns_orphans(self, cm: ConfigManager) -> None:
        """``remove_account(force=True)`` returns the names of orphaned targets."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.add_target("ecom", account="x", project="3018488")
        cm.add_target("ai", account="x", project="3713224")
        orphans = cm.remove_account("x", force=True)
        assert sorted(orphans) == ["ai", "ecom"]

    def test_remove_active_account_clears_active_block(self, cm: ConfigManager) -> None:
        """Removing the active account also clears `[active].account/.workspace`.

        Otherwise `session.show()` keeps printing the deleted name and a
        fresh `Workspace()` resolves through `get_active().account` into
        ``ConfigError("Account 'X' not found.")``.
        """
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u",
            secret=SecretStr("s"),
        )
        cm.set_active(account="x", workspace=42)
        assert cm.get_active() == ActiveSession(account="x", workspace=42)

        cm.remove_account("x")

        # Both fields cleared (workspace is project-scoped; meaningless
        # without the account).
        assert cm.get_active() == ActiveSession()

    def test_remove_non_active_account_preserves_active_block(
        self, cm: ConfigManager
    ) -> None:
        """Removing a non-active account leaves `[active]` untouched."""
        cm.add_account(
            "active_one",
            type="service_account",
            region="us",
            default_project="3713224",
            username="u1",
            secret=SecretStr("s"),
        )
        cm.add_account(
            "other",
            type="service_account",
            region="us",
            default_project="3018488",
            username="u2",
            secret=SecretStr("s"),
        )
        cm.set_active(account="active_one", workspace=42)

        cm.remove_account("other")

        assert cm.get_active() == ActiveSession(account="active_one", workspace=42)


class TestV3FixtureLoad:
    """The v3 golden fixtures load cleanly with the expected shape."""

    def test_v3_simple(self, tmp_path: Path) -> None:
        """``v3_simple.toml`` loads with project on the account, workspace in [active]."""
        src = _FIXTURE_DIR / "v3_simple.toml"
        dst = tmp_path / "config.toml"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        cm = ConfigManager(config_path=dst)
        accounts = cm.list_accounts()
        assert len(accounts) == 1
        assert accounts[0].name == "demo-sa"
        active = cm.get_active()
        assert active.account == "demo-sa"
        assert active.workspace == 3448413
        loaded = cm.get_account("demo-sa")
        assert loaded.default_project == "3713224"

    def test_v3_multi(self, tmp_path: Path) -> None:
        """``v3_multi.toml`` loads three accounts of distinct types + two targets."""
        src = _FIXTURE_DIR / "v3_multi.toml"
        dst = tmp_path / "config.toml"
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        cm = ConfigManager(config_path=dst)
        accounts = {a.name: a for a in cm.list_accounts()}
        assert accounts["team"].type == "service_account"
        assert accounts["personal"].type == "oauth_browser"
        assert accounts["ci"].type == "oauth_token"
        targets = {t.name: t for t in cm.list_targets()}
        assert targets["ecom"].workspace == 3448414
        assert targets["ai"].workspace is None


class TestSettingsCustomHeader:
    """``[settings].custom_header`` round-trips through ``ConfigManager``."""

    def test_custom_header_round_trip(self, cm: ConfigManager) -> None:
        """``set_custom_header`` and ``get_custom_header`` are inverses."""
        cm.set_custom_header(name="X-Mixpanel-Cluster", value="internal-1")
        cm2 = ConfigManager(config_path=cm.config_path)
        header = cm2.get_custom_header()
        assert header == ("X-Mixpanel-Cluster", "internal-1")

    def test_get_custom_header_when_absent(self, cm: ConfigManager) -> None:
        """``get_custom_header`` returns None when no header is set."""
        assert cm.get_custom_header() is None


class TestMutateTransaction:
    """``_mutate()`` collapses N read-modify-write cycles into one transaction."""

    def test_single_write_per_transaction(self, cm: ConfigManager) -> None:
        """A multi-call _mutate() block performs exactly one disk write."""
        # Seed the file so subsequent writes go through atomic_write_bytes.
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="123",
            username="u",
            secret=SecretStr("s"),
        )

        from unittest.mock import patch

        with patch(
            "mixpanel_data._internal.config_v3.atomic_write_bytes"
        ) as mock_write:
            with cm._mutate() as raw:
                cm._apply_set_active(raw, account="x", workspace=42)
                cm._apply_update_account(raw, "x", default_project="456")
            assert mock_write.call_count == 1

    def test_aborted_transaction_does_not_write(self, cm: ConfigManager) -> None:
        """An exception inside the body skips the write entirely."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="123",
            username="u",
            secret=SecretStr("s"),
        )
        original = cm.config_path.read_bytes()

        with pytest.raises(RuntimeError, match="boom"), cm._mutate() as raw:
            cm._apply_set_active(raw, account="x", workspace=42)
            raise RuntimeError("boom")

        # Disk state preserved — no partial mutation reached the file.
        assert cm.config_path.read_bytes() == original
        assert cm.get_active() == ActiveSession()

    def test_multi_call_atomicity_on_validation_failure(
        self, cm: ConfigManager
    ) -> None:
        """A failed step late in a transaction discards earlier mutations."""
        cm.add_account(
            "x",
            type="service_account",
            region="us",
            default_project="123",
            username="u",
            secret=SecretStr("s"),
        )

        with (
            pytest.raises(ConfigError, match="not configured"),
            cm._mutate() as raw,
        ):
            cm._apply_update_account(raw, "x", default_project="999")
            # This raises — the prior _apply_update_account must NOT persist.
            cm._apply_set_active(raw, account="missing-account")

        # default_project unchanged on disk.
        cm2 = ConfigManager(config_path=cm.config_path)
        account = cm2.get_account("x")
        assert account.default_project == "123"
