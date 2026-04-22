"""Unit tests for ``Workspace`` constructor with new keyword paths (T034).

The new constructor accepts ``account``, ``project``, ``workspace``,
``target``, ``session`` (all keyword-only). With ``session=``, the
constructor bypasses the resolver and uses the supplied Session
directly.

Reference: specs/042-auth-architecture-redesign/contracts/python-api.md §1, §2.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from mixpanel_data import accounts as accounts_ns
from mixpanel_data import targets as targets_ns
from mixpanel_data._internal.auth.account import (
    Account,
    ServiceAccount,
)
from mixpanel_data._internal.auth.session import (
    Project,
    Session,
)
from mixpanel_data._internal.config_v3 import ConfigManager
from mixpanel_data.workspace import Workspace


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate $HOME and MP_CONFIG_PATH."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MP_CONFIG_PATH", str(tmp_path / ".mp" / "config.toml"))


@pytest.fixture
def two_accounts() -> ConfigManager:
    """Seed two service accounts with active=team."""
    cm = ConfigManager()
    accounts_ns.add(
        "team",
        type="service_account",
        region="us",
        username="u",
        secret=SecretStr("s"),
    )
    accounts_ns.add("other", type="oauth_browser", region="eu")
    cm.set_active(account="team", project="3713224")
    return cm


class TestActiveResolution:
    """``Workspace()`` with no args resolves the active session."""

    def test_no_args_uses_active(self, two_accounts: ConfigManager) -> None:
        """No args → ws.account/project come from ``[active]``."""
        ws = Workspace()
        assert ws.account.name == "team"
        assert ws.project.id == "3713224"


class TestExplicitOverrides:
    """Explicit kwargs override ``[active]``."""

    def test_account_override(self, two_accounts: ConfigManager) -> None:
        """``Workspace(account="other")`` switches account."""
        ws = Workspace(account="other")
        assert ws.account.name == "other"

    def test_project_override(self, two_accounts: ConfigManager) -> None:
        """``Workspace(project=ID)`` switches project."""
        ws = Workspace(project="9999999")
        assert ws.project.id == "9999999"

    def test_account_and_project(self, two_accounts: ConfigManager) -> None:
        """Both kwargs together switch both axes."""
        ws = Workspace(account="other", project="9999999")
        assert ws.account.name == "other"
        assert ws.project.id == "9999999"


class TestTarget:
    """``Workspace(target=T)`` applies all three axes from the target."""

    def test_target_resolves(self, two_accounts: ConfigManager) -> None:
        """``Workspace(target=T)`` applies target's account/project/workspace."""
        targets_ns.add("ecom", account="other", project="3018488", workspace=42)
        ws = Workspace(target="ecom")
        assert ws.account.name == "other"
        assert ws.project.id == "3018488"
        assert ws.workspace is not None
        assert ws.workspace.id == 42

    def test_target_with_axis_raises(self, two_accounts: ConfigManager) -> None:
        """``target=`` combined with any axis kwarg raises ValueError."""
        targets_ns.add("ecom", account="other", project="3018488")
        with pytest.raises(ValueError):
            Workspace(target="ecom", account="team")


class TestSessionBypass:
    """``Workspace(session=S)`` bypasses the resolver."""

    def test_session_bypass(self, two_accounts: ConfigManager) -> None:
        """A pre-built Session is used as-is, ignoring config."""
        sa: Account = ServiceAccount(
            name="custom",
            region="in",
            username="bypass",
            secret=SecretStr("bs"),
        )
        sess = Session(account=sa, project=Project(id="11111"))
        ws = Workspace(session=sess)
        assert ws.account.name == "custom"
        assert ws.project.id == "11111"

    def test_session_use_chain_equivalence(self, two_accounts: ConfigManager) -> None:
        """``Workspace().use(...)`` matches ``Workspace(session=Session(...))``.

        Per SC-010, the use-chain is interchangeable with session= bypass
        for the same (account, project, workspace) triple.
        """
        sa: Account = ServiceAccount(
            name="team",
            region="us",
            username="u",
            secret=SecretStr("s"),
        )
        ws_chain = Workspace().use(account="team", project="3713224")
        ws_session = Workspace(
            session=Session(account=sa, project=Project(id="3713224"))
        )
        assert ws_chain.account.name == ws_session.account.name
        assert ws_chain.project.id == ws_session.project.id


class TestReadOnlyProperties:
    """The new properties are read-only (assignment raises)."""

    def test_account_property_readonly(self, two_accounts: ConfigManager) -> None:
        """Assignment to ``ws.account`` raises AttributeError."""
        ws = Workspace()
        with pytest.raises(AttributeError):
            ws.account = ws.account  # type: ignore[misc]

    def test_project_property_readonly(self, two_accounts: ConfigManager) -> None:
        """Assignment to ``ws.project`` raises AttributeError."""
        ws = Workspace()
        with pytest.raises(AttributeError):
            ws.project = ws.project  # type: ignore[misc]
