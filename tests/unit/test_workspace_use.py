"""Unit tests for ``Workspace.use(...)`` per-axis switching (T033).

Per spec SC-006/SC-007/SC-008:
- ``use(workspace=N)`` is in-memory only (no API call, no config write)
- ``use(project=P)`` does NOT re-auth
- ``use(account=A)`` rebuilds auth header AND clears in-session project state (FR-033)
- HTTP transport (``id(ws._api_client._http)``) is preserved across all switches

Reference: specs/042-auth-architecture-redesign/contracts/python-api.md §3.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from mixpanel_data import accounts as accounts_ns
from mixpanel_data import targets as targets_ns
from mixpanel_data._internal.config_v3 import ConfigManager
from mixpanel_data.workspace import Workspace


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate $HOME and MP_CONFIG_PATH for hermetic tests."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MP_CONFIG_PATH", str(tmp_path / ".mp" / "config.toml"))


@pytest.fixture
def two_accounts() -> ConfigManager:
    """Seed two service accounts with different credentials."""
    cm = ConfigManager()
    accounts_ns.add(
        "team",
        type="service_account",
        region="us",
        username="team.sa",
        secret=SecretStr("team-secret"),
    )
    accounts_ns.add(
        "other",
        type="service_account",
        region="eu",
        username="other.sa",
        secret=SecretStr("other-secret"),
    )
    cm.set_active(account="team", project="3713224")
    return cm


class TestUseWorkspace:
    """``ws.use(workspace=N)`` is an in-memory field update."""

    def test_workspace_changes(self, two_accounts: ConfigManager) -> None:
        """``ws.use(workspace=N)`` updates ``ws.workspace.id``."""
        ws = Workspace(account="team", project="3713224")
        ws.use(workspace=42)
        assert ws.workspace is not None
        assert ws.workspace.id == 42

    def test_chain_returns_self(self, two_accounts: ConfigManager) -> None:
        """``use`` returns ``self`` for fluent chaining."""
        ws = Workspace(account="team", project="3713224")
        assert ws.use(workspace=42) is ws


class TestUseProject:
    """``ws.use(project=P)`` does NOT re-auth (no auth header rebuild)."""

    def test_project_changes(self, two_accounts: ConfigManager) -> None:
        """``use(project=P)`` updates ``ws.project.id``."""
        ws = Workspace(account="team", project="3713224")
        ws.use(project="9999999")
        assert ws.project.id == "9999999"

    def test_account_unchanged(self, two_accounts: ConfigManager) -> None:
        """``use(project=P)`` preserves the account."""
        ws = Workspace(account="team", project="3713224")
        before = ws.account
        ws.use(project="9999999")
        assert ws.account == before


class TestUseAccount:
    """``ws.use(account=A)`` rebuilds the auth header (FR-033)."""

    def test_account_changes(self, two_accounts: ConfigManager) -> None:
        """``use(account=A)`` swaps to the new account."""
        ws = Workspace(account="team", project="3713224")
        ws.use(account="other")
        assert ws.account.name == "other"

    def test_account_change_clears_in_session_project(
        self, two_accounts: ConfigManager
    ) -> None:
        """Per FR-033, switching account clears in-session project state.

        After ``use(account=A)`` without an explicit project, the next
        operation that needs a project re-resolves from ``[active]``
        rather than carrying over the previous account's project ID.
        """
        ws = Workspace(account="team", project="3018488")
        # Override the active project, then switch account-only.
        ws.use(account="other")
        # Account swap clears project — re-resolves from [active] = "3713224".
        assert ws.project.id == "3713224"


class TestHTTPTransportPreservation:
    """HTTP transport is preserved across all use() switches (R5)."""

    def test_http_client_id_preserved_across_workspace_switch(
        self, two_accounts: ConfigManager
    ) -> None:
        """Workspace switch does NOT recreate the underlying httpx.Client."""
        ws = Workspace(account="team", project="3713224")
        client = ws._api_client  # noqa: SLF001 — test introspection
        assert client is not None
        before = id(client._http)  # noqa: SLF001
        ws.use(workspace=42)
        assert id(client._http) == before  # noqa: SLF001

    def test_http_client_id_preserved_across_project_switch(
        self, two_accounts: ConfigManager
    ) -> None:
        """Project switch does NOT recreate the underlying httpx.Client."""
        ws = Workspace(account="team", project="3713224")
        client = ws._api_client  # noqa: SLF001
        assert client is not None
        before = id(client._http)  # noqa: SLF001
        ws.use(project="9999999")
        assert id(client._http) == before  # noqa: SLF001

    def test_http_client_id_preserved_across_account_switch(
        self, two_accounts: ConfigManager
    ) -> None:
        """Account switch does NOT recreate the underlying httpx.Client."""
        ws = Workspace(account="team", project="3713224")
        client = ws._api_client  # noqa: SLF001
        assert client is not None
        before = id(client._http)  # noqa: SLF001
        ws.use(account="other")
        assert id(client._http) == before  # noqa: SLF001


class TestTargetMutualExclusion:
    """``target=`` is mutually exclusive with ``account=``/``project=``/``workspace=``."""

    def test_target_with_account_raises(self, two_accounts: ConfigManager) -> None:
        """``use(target=T, account=A)`` raises ValueError."""
        targets_ns.add("ecom", account="team", project="3018488")
        ws = Workspace(account="team", project="3713224")
        with pytest.raises(ValueError):
            ws.use(target="ecom", account="other")

    def test_target_alone_applies_three_axes(self, two_accounts: ConfigManager) -> None:
        """``use(target=T)`` alone applies all three axes from the target."""
        targets_ns.add("ecom", account="other", project="3018488", workspace=42)
        ws = Workspace(account="team", project="3713224")
        ws.use(target="ecom")
        assert ws.account.name == "other"
        assert ws.project.id == "3018488"
        assert ws.workspace is not None
        assert ws.workspace.id == 42


class TestPersist:
    """``persist=True`` writes the new state to ``[active]``."""

    def test_persist_writes_active(self, two_accounts: ConfigManager) -> None:
        """``use(account=A, project=P, persist=True)`` writes to [active]."""
        ws = Workspace(account="team", project="3713224")
        ws.use(account="other", persist=True)
        assert two_accounts.get_active().account == "other"
