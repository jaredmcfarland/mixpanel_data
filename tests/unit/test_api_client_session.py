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


class TestUseOAuthAtomicity:
    """``MixpanelAPIClient.use()`` MUST fail atomically when the new
    OAuth account has no usable token, preserving the prior session
    rather than committing the ``pending-login`` placeholder (R5)."""

    def test_use_to_oauth_account_without_token_raises_and_preserves_session(
        self, session_team: Session
    ) -> None:
        """Swap to a tokenless ``OAuthBrowserAccount`` raises, no commit."""
        from mixpanel_data._internal.auth.account import (
            OAuthBrowserAccount,
            TokenResolver,
        )
        from mixpanel_data.exceptions import OAuthError

        class _Failing(TokenResolver):
            """Always fails — simulates a tokenless OAuth account."""

            def get_browser_token(self, name: str, region: str) -> str:
                raise OAuthError("no tokens on disk")

            def get_static_token(self, account: object) -> str:
                raise OAuthError("no static token")

        client = MixpanelAPIClient(session=session_team, token_resolver=_Failing())
        prior_session = client.session
        prior_creds = client._credentials  # noqa: SLF001
        prior_header = client.current_auth_header

        oauth_account = OAuthBrowserAccount(name="oauth1", region="us")
        with pytest.raises(OAuthError):
            client.use(account=oauth_account)

        # Atomicity: the prior session/credentials/auth header all survive.
        assert client.session is prior_session
        assert client._credentials is prior_creds  # noqa: SLF001
        assert client.current_auth_header == prior_header

    def test_use_to_oauth_token_account_without_token_raises(
        self, session_team: Session
    ) -> None:
        """Swap to a tokenless ``OAuthTokenAccount`` raises and preserves state."""
        from mixpanel_data._internal.auth.account import (
            OAuthTokenAccount,
            TokenResolver,
        )
        from mixpanel_data.exceptions import OAuthError

        class _Failing(TokenResolver):
            def get_browser_token(self, name: str, region: str) -> str:
                raise OAuthError("not used")

            def get_static_token(self, account: object) -> str:
                raise OAuthError("env var unset")

        client = MixpanelAPIClient(session=session_team, token_resolver=_Failing())
        prior_session = client.session

        oauth_token_account = OAuthTokenAccount(
            name="ot1", region="us", token_env="MISSING_ENV_VAR"
        )
        with pytest.raises(OAuthError):
            client.use(account=oauth_token_account)
        assert client.session is prior_session


class TestSessionToCredentialsOAuthCacheIsolation:
    """``session_to_credentials`` MUST set ``username=account.name`` for
    OAuth shims so two OAuth accounts in the same region get distinct
    ``MeCache`` files (Finding 4)."""

    def test_oauth_browser_username_is_account_name(self) -> None:
        """OAuth browser shim carries the account name as ``username``."""
        from mixpanel_data._internal.api_client import session_to_credentials
        from mixpanel_data._internal.auth.account import OAuthBrowserAccount
        from mixpanel_data._internal.auth.account import (
            TokenResolver as _TR,
        )

        class _StaticToken(_TR):
            def get_browser_token(self, name: str, region: str) -> str:
                return "tok"

            def get_static_token(self, account: object) -> str:
                return "tok"

        s_a = Session(
            account=OAuthBrowserAccount(name="account_a", region="us"),
            project=Project(id="3713224"),
        )
        s_b = Session(
            account=OAuthBrowserAccount(name="account_b", region="us"),
            project=Project(id="3713224"),
        )
        creds_a = session_to_credentials(s_a, token_resolver=_StaticToken())
        creds_b = session_to_credentials(s_b, token_resolver=_StaticToken())
        assert creds_a.username == "account_a"
        assert creds_b.username == "account_b"
        # The whole point: distinct identity → MeCache scopes by this string.
        assert creds_a.username != creds_b.username

    def test_oauth_token_username_is_account_name(self) -> None:
        """OAuth static-token shim carries the account name as ``username``."""
        from mixpanel_data._internal.api_client import session_to_credentials
        from mixpanel_data._internal.auth.account import OAuthTokenAccount
        from mixpanel_data._internal.auth.account import (
            TokenResolver as _TR,
        )

        class _StaticToken(_TR):
            def get_browser_token(self, name: str, region: str) -> str:
                return "tok"

            def get_static_token(self, account: object) -> str:
                return "tok"

        s = Session(
            account=OAuthTokenAccount(
                name="my_token_account", region="us", token=SecretStr("xyz")
            ),
            project=Project(id="3713224"),
        )
        creds = session_to_credentials(s, token_resolver=_StaticToken())
        assert creds.username == "my_token_account"

    def test_session_to_credentials_strict_raises_oauth_error(self) -> None:
        """``strict=True`` propagates OAuthError instead of placeholder."""
        from mixpanel_data._internal.api_client import session_to_credentials
        from mixpanel_data._internal.auth.account import OAuthBrowserAccount
        from mixpanel_data._internal.auth.account import (
            TokenResolver as _TR,
        )
        from mixpanel_data.exceptions import OAuthError

        class _Failing(_TR):
            def get_browser_token(self, name: str, region: str) -> str:
                raise OAuthError("no tokens")

            def get_static_token(self, account: object) -> str:
                raise OAuthError("no token")

        s = Session(
            account=OAuthBrowserAccount(name="me", region="us"),
            project=Project(id="3713224"),
        )
        with pytest.raises(OAuthError):
            session_to_credentials(s, token_resolver=_Failing(), strict=True)
