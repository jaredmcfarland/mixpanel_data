"""Integration tests for Workspace facade.

Verifies that Workspace correctly threads credentials through the
v1 ``resolve_credentials`` path under ``MP_OAUTH_TOKEN``-based env auth.
"""

from __future__ import annotations

import pytest

from mixpanel_data import Workspace
from mixpanel_data._internal.config import AuthMethod, ConfigManager


class TestWorkspaceOAuthEnv:
    """Workspace integration with the ``MP_OAUTH_TOKEN`` env-var path."""

    def test_workspace_uses_oauth_env_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
        config_manager: ConfigManager,
    ) -> None:
        """Workspace resolves MP_OAUTH_TOKEN env vars and surfaces a Bearer header.

        Pins the end-to-end flow: env-var detection in
        ``ConfigManager._resolve_from_env`` → OAuth ``Credentials`` →
        Workspace. ``_credentials.auth_method`` MUST stay ``oauth``.
        """
        monkeypatch.setenv("MP_OAUTH_TOKEN", "ws-bearer-token")
        monkeypatch.setenv("MP_PROJECT_ID", "1234")
        monkeypatch.setenv("MP_REGION", "us")

        ws = Workspace(_config_manager=config_manager)

        assert ws._credentials is not None
        assert ws._credentials.auth_method == AuthMethod.oauth
        assert ws._credentials.project_id == "1234"
        assert ws._credentials.region == "us"
        assert ws._credentials.auth_header() == "Bearer ws-bearer-token"

    def test_workspace_oauth_env_with_project_override(
        self,
        monkeypatch: pytest.MonkeyPatch,
        config_manager: ConfigManager,
    ) -> None:
        """A ``project_id`` override must NOT downgrade OAuth to Basic Auth.

        Pins the override-reconstruction block in ``Workspace.__init__``
        (the v1 branch that builds a fresh ``Credentials`` carrying
        ``auth_method`` and ``oauth_access_token``). A regression that
        defaults the new ``Credentials`` to Basic Auth would be silent
        without this test.
        """
        monkeypatch.setenv("MP_OAUTH_TOKEN", "override-bearer")
        monkeypatch.setenv("MP_PROJECT_ID", "original-pid")
        monkeypatch.setenv("MP_REGION", "us")

        ws = Workspace(_config_manager=config_manager, project_id="override-pid")

        assert ws._credentials is not None
        assert ws._credentials.auth_method == AuthMethod.oauth
        assert ws._credentials.project_id == "override-pid"
        assert ws._credentials.auth_header() == "Bearer override-bearer"
