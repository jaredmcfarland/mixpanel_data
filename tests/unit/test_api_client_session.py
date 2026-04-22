"""Unit tests for ``MixpanelAPIClient`` with the new ``Session`` constructor (T035).

Tests cover:
- Construction with ``session=``
- ``use(account=, project=, workspace=)`` rebuilds auth header / region URL
- HTTP transport (``_http``) preserved across all ``use()`` calls
- Cache invalidation policy per Research R5

Reference: specs/042-auth-architecture-redesign/research.md R5.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from mixpanel_data._internal.api_client import MixpanelAPIClient
from mixpanel_data._internal.auth.account import (
    ServiceAccount,
)
from mixpanel_data._internal.auth.session import (
    Project,
    Session,
    WorkspaceRef,
)


@pytest.fixture
def session_team() -> Session:
    """Return a Session for a fictional 'team' SA."""
    return Session(
        account=ServiceAccount(
            name="team",
            region="us",
            username="team.sa",
            secret=SecretStr("team-secret"),
        ),
        project=Project(id="3713224"),
    )


@pytest.fixture
def session_other() -> Session:
    """Return a Session for a fictional 'other' SA in eu region."""
    return Session(
        account=ServiceAccount(
            name="other",
            region="eu",
            username="other.sa",
            secret=SecretStr("other-secret"),
        ),
        project=Project(id="9999999"),
    )


class TestConstruction:
    """``MixpanelAPIClient(session=...)`` constructs from a Session."""

    def test_construct_with_session(self, session_team: Session) -> None:
        """The client is constructible with just a Session."""
        client = MixpanelAPIClient(session=session_team)
        assert client.session.account.name == "team"
        assert client.session.project.id == "3713224"

    def test_auth_header_basic(self, session_team: Session) -> None:
        """ServiceAccount session yields a Basic-auth header."""
        client = MixpanelAPIClient(session=session_team)
        assert client.current_auth_header.startswith("Basic ")


class TestUse:
    """``client.use(account=, project=, workspace=)`` swaps axes."""

    def test_use_workspace(self, session_team: Session) -> None:
        """``use(workspace=N)`` updates the workspace field."""
        client = MixpanelAPIClient(session=session_team)
        client.use(workspace=42)
        assert client.session.workspace == WorkspaceRef(id=42)

    def test_use_project(self, session_team: Session) -> None:
        """``use(project=P)`` updates the project field."""
        client = MixpanelAPIClient(session=session_team)
        client.use(project=Project(id="11111"))
        assert client.session.project.id == "11111"

    def test_use_account_rebuilds_auth_header(
        self, session_team: Session, session_other: Session
    ) -> None:
        """``use(account=A)`` rebuilds the auth header for the new account."""
        client = MixpanelAPIClient(session=session_team)
        before = client.current_auth_header
        client.use(account=session_other.account)
        assert client.current_auth_header != before
        assert client.session.account.name == "other"


class TestTransportPreservation:
    """HTTP transport (``_http``) survives every ``use()`` call (R5)."""

    def test_workspace_switch(self, session_team: Session) -> None:
        """Workspace swap preserves ``_http`` instance identity."""
        client = MixpanelAPIClient(session=session_team)
        before = id(client._http)  # noqa: SLF001 — test introspection
        client.use(workspace=42)
        assert id(client._http) == before

    def test_project_switch(self, session_team: Session) -> None:
        """Project swap preserves ``_http`` instance identity."""
        client = MixpanelAPIClient(session=session_team)
        before = id(client._http)  # noqa: SLF001
        client.use(project=Project(id="11111"))
        assert id(client._http) == before

    def test_account_switch(
        self, session_team: Session, session_other: Session
    ) -> None:
        """Account swap preserves ``_http`` instance identity."""
        client = MixpanelAPIClient(session=session_team)
        before = id(client._http)  # noqa: SLF001
        client.use(account=session_other.account)
        assert id(client._http) == before


class TestUseClearsStaleWorkspaceId:
    """``use(account=...)`` and ``use(project=...)`` MUST drop ``_workspace_id``.

    Regression: ``use()`` previously cleared ``_resolved_workspace`` and
    ``_cached_workspace_id`` on account/project swap but left
    ``self._workspace_id`` (the explicit pin) untouched. Subsequent calls
    to ``maybe_scoped_path()`` still emitted ``/workspaces/<old>/…``,
    routing requests to a workspace that may not exist under the new
    project/account.
    """

    def test_account_swap_clears_workspace_id(
        self, session_team: Session, session_other: Session
    ) -> None:
        """Pin a workspace via Session, swap account; the pin must drop."""
        team_with_ws = session_team.replace(workspace=WorkspaceRef(id=42))
        client = MixpanelAPIClient(session=team_with_ws)
        assert client._workspace_id == 42  # noqa: SLF001
        client.use(account=session_other.account)
        assert client._workspace_id is None  # noqa: SLF001

    def test_project_swap_clears_workspace_id(self, session_team: Session) -> None:
        """Pin a workspace via Session, swap project; the pin must drop."""
        team_with_ws = session_team.replace(workspace=WorkspaceRef(id=42))
        client = MixpanelAPIClient(session=team_with_ws)
        assert client._workspace_id == 42  # noqa: SLF001
        client.use(project=Project(id="11111"))
        assert client._workspace_id is None  # noqa: SLF001

    def test_account_swap_then_scoped_path_does_not_leak_old_workspace(
        self, session_team: Session, session_other: Session
    ) -> None:
        """End-to-end: scoped paths after account swap must not reference old ws."""
        team_with_ws = session_team.replace(workspace=WorkspaceRef(id=42))
        client = MixpanelAPIClient(session=team_with_ws)
        client.use(account=session_other.account)
        path = client.maybe_scoped_path("dashboards")
        assert "/workspaces/42/" not in path
        # Project-scoped (not workspace-scoped) is the expected fallback.
        assert path.startswith("/projects/")
