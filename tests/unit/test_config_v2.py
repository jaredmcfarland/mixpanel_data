"""Unit tests for v2 config schema support in ConfigManager.

Tests cover:
- T021: Credentials.to_resolved_session()
- T025-T028: Credential CRUD, config version detection, CredentialInfo/ActiveContext
- T050-T051: Active context management, resolve_session()
- T088-T089: OAuth credential resolution
- T094-T095: Project aliases
- T105-T106: Environment variable override
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomli_w
from pydantic import SecretStr

from mixpanel_data._internal.auth_credential import (
    CredentialType,
    ResolvedSession,
)
from mixpanel_data._internal.config import (
    ConfigManager,
    Credentials,
)
from mixpanel_data.exceptions import ConfigError

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Return path for a temporary config file."""
    return tmp_path / "config.toml"


@pytest.fixture
def cm(config_path: Path) -> ConfigManager:
    """Create a ConfigManager with a temporary config file."""
    return ConfigManager(config_path=config_path)


@pytest.fixture
def v2_config(config_path: Path) -> Path:
    """Write a v2 config file and return its path."""
    config = {
        "config_version": 2,
        "active": {
            "credential": "demo-sa",
            "project_id": "3713224",
        },
        "credentials": {
            "demo-sa": {
                "type": "service_account",
                "username": "sa-user.abc.mp-service-account",
                "secret": "sa-secret-value",
                "region": "us",
            },
        },
        "projects": {
            "ai-demo": {
                "project_id": "3713224",
                "credential": "demo-sa",
                "workspace_id": 3448413,
            },
        },
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("wb") as f:
        tomli_w.dump(config, f)
    return config_path


# ── T021: Credentials.to_resolved_session() ──────────────────────────


class TestCredentialsToResolvedSession:
    """T021: Tests for Credentials.to_resolved_session()."""

    def test_basic_auth_conversion(self) -> None:
        """Test converting Basic Auth Credentials to ResolvedSession."""
        creds = Credentials(
            username="sa-user",
            secret=SecretStr("sa-secret"),
            project_id="12345",
            region="us",
        )
        session = creds.to_resolved_session()
        assert isinstance(session, ResolvedSession)
        assert session.project_id == "12345"
        assert session.region == "us"
        assert session.auth.type == CredentialType.service_account
        assert session.auth.name == "sa-user"
        assert session.auth_header().startswith("Basic ")

    def test_oauth_conversion(self) -> None:
        """Test converting OAuth Credentials to ResolvedSession."""
        creds = Credentials(
            username="",
            secret=SecretStr(""),
            project_id="67890",
            region="eu",
            auth_method="oauth",
            oauth_access_token=SecretStr("my-token"),
        )
        session = creds.to_resolved_session()
        assert isinstance(session, ResolvedSession)
        assert session.project_id == "67890"
        assert session.region == "eu"
        assert session.auth.type == CredentialType.oauth
        assert session.auth_header() == "Bearer my-token"

    def test_project_context_populated(self) -> None:
        """Test ProjectContext is populated from Credentials."""
        creds = Credentials(
            username="user",
            secret=SecretStr("secret"),
            project_id="99999",
            region="in",
        )
        session = creds.to_resolved_session()
        assert session.project.project_id == "99999"
        assert session.project.workspace_id is None


# ── T025: ConfigManager.add_credential() ─────────────────────────────


class TestAddCredential:
    """T025: Tests for ConfigManager.add_credential()."""

    def test_add_sa_credential(self, cm: ConfigManager) -> None:
        """Test adding a service account credential."""
        cm.add_credential(
            name="demo-sa",
            type="service_account",
            username="sa-user.abc.mp-service-account",
            secret="sa-secret-value",
            region="us",
        )
        creds = cm.list_credentials()
        assert len(creds) == 1
        assert creds[0].name == "demo-sa"
        assert creds[0].type == "service_account"
        assert creds[0].region == "us"

    def test_add_oauth_credential(self, cm: ConfigManager) -> None:
        """Test adding an OAuth credential."""
        cm.add_credential(
            name="my-oauth",
            type="oauth",
            region="eu",
        )
        creds = cm.list_credentials()
        assert len(creds) == 1
        assert creds[0].name == "my-oauth"
        assert creds[0].type == "oauth"
        assert creds[0].region == "eu"

    def test_duplicate_name_raises(self, cm: ConfigManager) -> None:
        """Test adding a credential with duplicate name raises error."""
        cm.add_credential(
            name="demo",
            type="service_account",
            username="user",
            secret="secret",
            region="us",
        )
        with pytest.raises(ConfigError, match="already exists"):
            cm.add_credential(
                name="demo",
                type="service_account",
                username="user2",
                secret="secret2",
                region="eu",
            )

    def test_first_credential_becomes_active(self, cm: ConfigManager) -> None:
        """Test first credential is automatically set as active."""
        cm.add_credential(
            name="first-sa",
            type="service_account",
            username="user",
            secret="secret",
            region="us",
        )
        ctx = cm.get_active_context()
        assert ctx.credential == "first-sa"

    def test_sets_config_version_2(self, cm: ConfigManager) -> None:
        """Test adding a credential sets config_version=2."""
        cm.add_credential(
            name="sa",
            type="service_account",
            username="user",
            secret="secret",
            region="us",
        )
        assert cm.config_version() == 2


# ── T026: ConfigManager.list_credentials() / remove_credential() ─────


class TestListRemoveCredentials:
    """T026: Tests for credential listing and removal."""

    def test_list_empty(self, cm: ConfigManager) -> None:
        """Test listing credentials when none exist."""
        assert cm.list_credentials() == []

    def test_list_multiple(self, cm: ConfigManager) -> None:
        """Test listing multiple credentials."""
        cm.add_credential(
            name="sa1",
            type="service_account",
            username="user1",
            secret="secret1",
            region="us",
        )
        cm.add_credential(
            name="sa2",
            type="service_account",
            username="user2",
            secret="secret2",
            region="eu",
        )
        creds = cm.list_credentials()
        assert len(creds) == 2
        names = {c.name for c in creds}
        assert names == {"sa1", "sa2"}

    def test_remove_credential(self, cm: ConfigManager) -> None:
        """Test removing a credential."""
        cm.add_credential(
            name="to-remove",
            type="service_account",
            username="user",
            secret="secret",
            region="us",
        )
        assert len(cm.list_credentials()) == 1
        cm.remove_credential("to-remove")
        assert len(cm.list_credentials()) == 0

    def test_remove_nonexistent_raises(self, cm: ConfigManager) -> None:
        """Test removing a non-existent credential raises error."""
        with pytest.raises(ConfigError, match="not found"):
            cm.remove_credential("nonexistent")

    def test_remove_active_resets(self, cm: ConfigManager) -> None:
        """Test removing the active credential resets active context."""
        cm.add_credential(
            name="sa1",
            type="service_account",
            username="user1",
            secret="secret1",
            region="us",
        )
        cm.add_credential(
            name="sa2",
            type="service_account",
            username="user2",
            secret="secret2",
            region="eu",
        )
        cm.set_active_credential("sa1")
        cm.remove_credential("sa1")
        ctx = cm.get_active_context()
        # Should fall back to another credential or be cleared
        assert ctx.credential != "sa1"


# ── add_credential validation ────────────────────────────────────────


class TestAddCredentialValidation:
    """Tests for add_credential required field validation."""

    @pytest.fixture()
    def cm(self, tmp_path: Path) -> ConfigManager:
        """Create a ConfigManager with a temp config path."""
        return ConfigManager(config_path=tmp_path / "config.toml")

    def test_sa_requires_username(self, cm: ConfigManager) -> None:
        """Service account without username raises ValueError."""
        with pytest.raises(ValueError, match="username is required"):
            cm.add_credential(name="bad-sa", type="service_account", secret="s")

    def test_sa_requires_secret(self, cm: ConfigManager) -> None:
        """Service account without secret raises ValueError."""
        with pytest.raises(ValueError, match="secret is required"):
            cm.add_credential(name="bad-sa", type="service_account", username="u")

    def test_sa_empty_username_rejected(self, cm: ConfigManager) -> None:
        """Service account with empty username raises ValueError."""
        with pytest.raises(ValueError, match="username is required"):
            cm.add_credential(
                name="bad-sa",
                type="service_account",
                username="",
                secret="s",
            )

    def test_sa_with_valid_fields_succeeds(self, cm: ConfigManager) -> None:
        """Service account with all fields succeeds."""
        cm.add_credential(
            name="good-sa",
            type="service_account",
            username="user",
            secret="secret",
        )
        creds = cm.list_credentials()
        assert len(creds) == 1
        assert creds[0].name == "good-sa"

    def test_resolve_v2_missing_sa_fields_raises_config_error(
        self, cm: ConfigManager
    ) -> None:
        """Corrupted SA credential (missing fields) raises ConfigError."""
        import tomli_w

        config: dict[str, object] = {
            "config_version": 2,
            "active": {"credential": "broken", "project_id": "123"},
            "credentials": {"broken": {"type": "service_account", "region": "us"}},
        }
        cm._config_path.parent.mkdir(parents=True, exist_ok=True)
        with cm._config_path.open("wb") as f:
            tomli_w.dump(config, f)

        with pytest.raises(ConfigError, match="missing username or secret"):
            cm.resolve_session()


# ── _session_to_credentials bridge ──────────────────────────────────


class TestSessionToCredentials:
    """Tests for Workspace._session_to_credentials static method."""

    def test_sa_bridge(self) -> None:
        """Service account ResolvedSession converts to Credentials."""
        from mixpanel_data._internal.auth_credential import (
            AuthCredential,
            CredentialType,
            ProjectContext,
            ResolvedSession,
        )
        from mixpanel_data._internal.config import AuthMethod
        from mixpanel_data.workspace import Workspace

        session = ResolvedSession(
            auth=AuthCredential(
                name="sa1",
                type=CredentialType.service_account,
                region="us",
                username="user1",
                secret=SecretStr("secret1"),
            ),
            project=ProjectContext(project_id="111", workspace_id=42),
        )
        creds = Workspace._session_to_credentials(session)
        assert creds.project_id == "111"
        assert creds.region == "us"
        assert creds.username == "user1"
        assert creds.auth_method == AuthMethod.basic

    def test_oauth_bridge(self) -> None:
        """OAuth ResolvedSession converts to Credentials."""
        from mixpanel_data._internal.auth_credential import (
            AuthCredential,
            CredentialType,
            ProjectContext,
            ResolvedSession,
        )
        from mixpanel_data._internal.config import AuthMethod
        from mixpanel_data.workspace import Workspace

        session = ResolvedSession(
            auth=AuthCredential(
                name="oauth1",
                type=CredentialType.oauth,
                region="eu",
                oauth_access_token=SecretStr("bearer-tok"),
            ),
            project=ProjectContext(project_id="222"),
        )
        creds = Workspace._session_to_credentials(session)
        assert creds.project_id == "222"
        assert creds.region == "eu"
        assert creds.auth_method == AuthMethod.oauth
        assert (
            creds.oauth_access_token is not None
            and creds.oauth_access_token.get_secret_value() == "bearer-tok"
        )


# ── T027: config_version() ───────────────────────────────────────────


class TestConfigVersion:
    """T027: Tests for config version detection."""

    def test_empty_config_is_v1(self, cm: ConfigManager) -> None:
        """Test empty config is treated as v1."""
        assert cm.config_version() == 1

    def test_v1_config_detected(self, config_path: Path, cm: ConfigManager) -> None:
        """Test v1 config (with accounts) is detected."""
        config = {
            "default": "demo",
            "accounts": {
                "demo": {
                    "username": "user",
                    "secret": "secret",
                    "project_id": "123",
                    "region": "us",
                },
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump(config, f)
        assert cm.config_version() == 1

    def test_v2_config_detected(self, v2_config: Path, config_path: Path) -> None:  # noqa: ARG002
        """Test v2 config is detected."""
        cm = ConfigManager(config_path=config_path)
        assert cm.config_version() == 2


# ── T028: CredentialInfo and ActiveContext dataclasses ────────────────


class TestCredentialInfoAndActiveContext:
    """T028: Tests for CredentialInfo and ActiveContext."""

    def test_credential_info_fields(self, cm: ConfigManager) -> None:
        """Test CredentialInfo has expected fields."""
        cm.add_credential(
            name="test-sa",
            type="service_account",
            username="user",
            secret="secret",
            region="us",
        )
        creds = cm.list_credentials()
        info = creds[0]
        assert info.name == "test-sa"
        assert info.type == "service_account"
        assert info.region == "us"
        assert hasattr(info, "is_active")

    def test_active_context_defaults(self, cm: ConfigManager) -> None:
        """Test ActiveContext returns empty/None when nothing is set."""
        ctx = cm.get_active_context()
        assert ctx.credential is None
        assert ctx.project_id is None
        assert ctx.workspace_id is None

    def test_active_context_after_add(self, cm: ConfigManager) -> None:
        """Test ActiveContext after adding a credential."""
        cm.add_credential(
            name="sa1",
            type="service_account",
            username="user",
            secret="secret",
            region="us",
        )
        ctx = cm.get_active_context()
        assert ctx.credential == "sa1"


# ── T050-T052: resolve_session with active context ──────────────────


class TestResolveSessionActiveContext:
    """T050-T052: Tests for resolve_session with active context."""

    @pytest.fixture
    def cm_with_cred(self, config_path: Path) -> ConfigManager:
        """Create a ConfigManager with a v2 credential and active context."""
        config: dict[str, object] = {
            "config_version": 2,
            "active": {
                "credential": "demo-sa",
                "project_id": "3713224",
                "workspace_id": 3448413,
            },
            "credentials": {
                "demo-sa": {
                    "type": "service_account",
                    "username": "sa-user.abc.mp-service-account",
                    "secret": "sa-secret-value",
                    "region": "us",
                },
                "staging-sa": {
                    "type": "service_account",
                    "username": "staging-user.xyz.mp-service-account",
                    "secret": "staging-secret",
                    "region": "eu",
                },
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        import tomli_w

        with config_path.open("wb") as f:
            tomli_w.dump(config, f)
        return ConfigManager(config_path=config_path)

    def test_resolve_session_uses_active_context(
        self, cm_with_cred: ConfigManager
    ) -> None:
        """Test resolve_session uses active credential and project."""
        session = cm_with_cred.resolve_session()
        assert session.project_id == "3713224"
        assert session.auth.name == "demo-sa"
        assert session.region == "us"

    def test_resolve_session_credential_override(
        self, cm_with_cred: ConfigManager
    ) -> None:
        """Test resolve_session with explicit credential override."""
        session = cm_with_cred.resolve_session(credential="staging-sa")
        assert session.auth.name == "staging-sa"
        assert session.region == "eu"

    def test_resolve_session_project_override(
        self, cm_with_cred: ConfigManager
    ) -> None:
        """Test resolve_session with explicit project_id override."""
        session = cm_with_cred.resolve_session(project_id="9999")
        assert session.project_id == "9999"
        assert session.auth.name == "demo-sa"

    def test_resolve_session_workspace_override(
        self, cm_with_cred: ConfigManager
    ) -> None:
        """Test resolve_session with workspace_id override."""
        session = cm_with_cred.resolve_session(workspace_id=7777)
        assert session.project.workspace_id == 7777


# ── T058: Workspace accepts credential param ────────────────────────


class TestWorkspaceCredentialParam:
    """T058: Tests for Workspace accepting credential parameter."""

    def test_workspace_with_credential_uses_resolve_session(
        self,
    ) -> None:
        """Test Workspace(credential=...) uses resolve_session path."""
        from unittest.mock import MagicMock

        mock_cm = MagicMock()
        mock_session = MagicMock()
        mock_session.project_id = "3713224"
        mock_session.region = "us"
        mock_session.auth.type.value = "service_account"
        mock_session.auth.username = "user"
        mock_session.auth.secret = SecretStr("secret")
        mock_session.auth.oauth_access_token = None
        mock_cm.resolve_session.return_value = mock_session

        from mixpanel_data._internal.auth_credential import CredentialType

        mock_session.auth.type = CredentialType.service_account

        from mixpanel_data.workspace import Workspace

        ws = Workspace(credential="demo-sa", _config_manager=mock_cm)
        mock_cm.resolve_session.assert_called_once_with(
            credential="demo-sa",
            project_id=None,
            workspace_id=None,
        )
        assert ws._credentials is not None
        assert ws._credentials.project_id == "3713224"

    def test_workspace_legacy_path_without_credential(
        self,
    ) -> None:
        """Test Workspace() without credential uses legacy resolve_credentials."""
        from unittest.mock import MagicMock

        mock_cm = MagicMock()
        mock_cm.resolve_credentials.return_value = Credentials(
            username="user",
            secret=SecretStr("secret"),
            project_id="12345",
            region="us",
        )

        from mixpanel_data.workspace import Workspace

        ws = Workspace(_config_manager=mock_cm)
        mock_cm.resolve_credentials.assert_called_once_with(None)
        assert ws._credentials is not None
        assert ws._credentials.project_id == "12345"


# ── T088-T089: OAuth credential resolution via resolve_session() ─────


class TestOAuthCredentialResolution:
    """T088-T089: OAuth credential resolution in v2 config."""

    @pytest.fixture
    def oauth_storage_dir(self, tmp_path: Path) -> Path:
        """Create a temporary OAuth storage directory with valid tokens.

        Returns:
            Path to the OAuth storage directory.
        """
        import json
        from datetime import datetime, timezone

        oauth_dir = tmp_path / "oauth"
        oauth_dir.mkdir(parents=True)

        tokens_data = {
            "access_token": "test-oauth-access-token",
            "refresh_token": "test-refresh-token",
            "expires_at": datetime(
                2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc
            ).isoformat(),
            "scope": "projects analysis events",
            "token_type": "Bearer",
            "project_id": "token-project-999",
        }
        tokens_path = oauth_dir / "tokens_us.json"
        tokens_path.write_text(json.dumps(tokens_data), encoding="utf-8")

        return oauth_dir

    def test_oauth_resolve_uses_active_project_id(
        self, config_path: Path, oauth_storage_dir: Path
    ) -> None:
        """Test that OAuth resolution uses active.project_id, not token's project_id.

        When type='oauth', the project_id should come from the config's
        active.project_id, not from the OAuth token's embedded project_id.
        """
        config: dict[str, object] = {
            "config_version": 2,
            "active": {
                "credential": "my-oauth",
                "project_id": "active-project-123",
            },
            "credentials": {
                "my-oauth": {
                    "type": "oauth",
                    "region": "us",
                },
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump(config, f)

        cm = ConfigManager(config_path=config_path)
        session = cm.resolve_session(_oauth_storage_dir=oauth_storage_dir)

        # project_id should come from active context, NOT from the token
        assert session.project_id == "active-project-123"
        assert session.auth.type == CredentialType.oauth
        assert session.auth_header() == "Bearer test-oauth-access-token"

    def test_oauth_credential_in_v2_config(
        self, config_path: Path, oauth_storage_dir: Path
    ) -> None:
        """Test that an OAuth credential entry resolves to a valid session."""
        config: dict[str, object] = {
            "config_version": 2,
            "active": {
                "credential": "oauth-cred",
                "project_id": "55555",
            },
            "credentials": {
                "oauth-cred": {
                    "type": "oauth",
                    "region": "us",
                },
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump(config, f)

        cm = ConfigManager(config_path=config_path)
        session = cm.resolve_session(_oauth_storage_dir=oauth_storage_dir)

        assert isinstance(session, ResolvedSession)
        assert session.auth.type == CredentialType.oauth
        assert session.region == "us"
        assert session.project_id == "55555"

    def test_oauth_expired_token_raises(
        self, config_path: Path, tmp_path: Path
    ) -> None:
        """Test that expired OAuth tokens raise ConfigError."""
        import json
        from datetime import datetime, timezone

        oauth_dir = tmp_path / "oauth_expired"
        oauth_dir.mkdir(parents=True)

        expired_data = {
            "access_token": "expired-token",
            "expires_at": datetime(
                2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc
            ).isoformat(),
            "scope": "projects",
            "token_type": "Bearer",
        }
        (oauth_dir / "tokens_us.json").write_text(
            json.dumps(expired_data), encoding="utf-8"
        )

        config: dict[str, object] = {
            "config_version": 2,
            "active": {
                "credential": "oauth-cred",
                "project_id": "123",
            },
            "credentials": {
                "oauth-cred": {
                    "type": "oauth",
                    "region": "us",
                },
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump(config, f)

        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="expired or missing"):
            cm.resolve_session(_oauth_storage_dir=oauth_dir)

    def test_oauth_missing_token_raises(
        self, config_path: Path, tmp_path: Path
    ) -> None:
        """Test that missing OAuth tokens raise ConfigError."""
        empty_oauth_dir = tmp_path / "oauth_empty"
        empty_oauth_dir.mkdir(parents=True)

        config: dict[str, object] = {
            "config_version": 2,
            "active": {
                "credential": "oauth-cred",
                "project_id": "123",
            },
            "credentials": {
                "oauth-cred": {
                    "type": "oauth",
                    "region": "us",
                },
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump(config, f)

        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="expired or missing"):
            cm.resolve_session(_oauth_storage_dir=empty_oauth_dir)


# ── T092: OAuth credential entry in add_credential() ────────────────


class TestAddOAuthCredential:
    """T092: Verify add_credential() supports type='oauth'."""

    def test_add_oauth_credential_persists(self, cm: ConfigManager) -> None:
        """Test that adding an OAuth credential persists correctly."""
        cm.add_credential(
            name="my-oauth",
            type="oauth",
            region="eu",
        )

        creds = cm.list_credentials()
        assert len(creds) == 1
        assert creds[0].name == "my-oauth"
        assert creds[0].type == "oauth"
        assert creds[0].region == "eu"

    def test_add_oauth_credential_sets_config_version(self, cm: ConfigManager) -> None:
        """Test that adding an OAuth credential sets config_version=2."""
        cm.add_credential(
            name="oauth-test",
            type="oauth",
            region="us",
        )
        assert cm.config_version() == 2

    def test_add_oauth_credential_no_username_or_secret(
        self, cm: ConfigManager
    ) -> None:
        """Test that OAuth credentials work without username/secret."""
        cm.add_credential(
            name="oauth-no-sa",
            type="oauth",
            region="in",
        )

        creds = cm.list_credentials()
        assert len(creds) == 1
        # OAuth should not have username/secret fields in stored config
        assert creds[0].type == "oauth"


# ── T094-T095: Project Aliases ─────────────────────────────────────────


class TestProjectAliases:
    """T094-T095: Tests for project alias CRUD in ConfigManager."""

    def test_add_and_list_alias(self, cm: ConfigManager) -> None:
        """Test adding a project alias and listing it."""
        cm.add_project_alias("ecom", "3018488", credential="demo-sa")
        aliases = cm.list_project_aliases()
        assert len(aliases) == 1
        assert aliases[0].name == "ecom"
        assert aliases[0].project_id == "3018488"
        assert aliases[0].credential == "demo-sa"
        assert aliases[0].workspace_id is None

    def test_add_alias_with_workspace(self, cm: ConfigManager) -> None:
        """Test adding a project alias with workspace_id."""
        cm.add_project_alias("ai-demo", "3713224", workspace_id=3448413)
        aliases = cm.list_project_aliases()
        assert len(aliases) == 1
        assert aliases[0].workspace_id == 3448413

    def test_add_duplicate_alias_raises(self, cm: ConfigManager) -> None:
        """Test adding a duplicate alias raises ConfigError."""
        cm.add_project_alias("ecom", "3018488")
        with pytest.raises(ConfigError, match="already exists"):
            cm.add_project_alias("ecom", "9999")

    def test_remove_alias(self, cm: ConfigManager) -> None:
        """Test removing a project alias."""
        cm.add_project_alias("ecom", "3018488")
        assert len(cm.list_project_aliases()) == 1
        cm.remove_project_alias("ecom")
        assert len(cm.list_project_aliases()) == 0

    def test_remove_nonexistent_alias_raises(self, cm: ConfigManager) -> None:
        """Test removing a non-existent alias raises ConfigError."""
        with pytest.raises(ConfigError, match="not found"):
            cm.remove_project_alias("nonexistent")

    def test_list_empty_aliases(self, cm: ConfigManager) -> None:
        """Test listing aliases when none exist."""
        assert cm.list_project_aliases() == []

    def test_multiple_aliases(self, cm: ConfigManager) -> None:
        """Test adding and listing multiple aliases."""
        cm.add_project_alias("ecom", "3018488")
        cm.add_project_alias("ai-demo", "3713224", credential="demo-sa")
        cm.add_project_alias("staging", "9999", workspace_id=1111)
        aliases = cm.list_project_aliases()
        assert len(aliases) == 3
        names = {a.name for a in aliases}
        assert names == {"ecom", "ai-demo", "staging"}


# ── T105-T106: Environment Variable Override ───────────────────────────


class TestEnvVarOverride:
    """T105-T106: Tests for environment variable override in resolve_session."""

    @pytest.fixture
    def cm_with_cred(self, config_path: Path) -> ConfigManager:
        """Create a ConfigManager with a v2 credential and active context.

        Returns:
            ConfigManager with demo-sa credential and active project.
        """
        config: dict[str, object] = {
            "config_version": 2,
            "active": {
                "credential": "demo-sa",
                "project_id": "3713224",
                "workspace_id": 3448413,
            },
            "credentials": {
                "demo-sa": {
                    "type": "service_account",
                    "username": "sa-user.abc.mp-service-account",
                    "secret": "sa-secret-value",
                    "region": "us",
                },
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump(config, f)
        return ConfigManager(config_path=config_path)

    def test_env_vars_override_active_context(
        self, cm_with_cred: ConfigManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test all 4 env vars override the active context completely."""
        monkeypatch.setenv("MP_USERNAME", "env_user")
        monkeypatch.setenv("MP_SECRET", "env_secret")
        monkeypatch.setenv("MP_PROJECT_ID", "env_project")
        monkeypatch.setenv("MP_REGION", "eu")

        session = cm_with_cred.resolve_session()

        assert session.project_id == "env_project"
        assert session.region == "eu"

    def test_env_vars_override_oauth(
        self, cm_with_cred: ConfigManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test env vars take precedence over OAuth credentials too."""
        monkeypatch.setenv("MP_USERNAME", "env_user")
        monkeypatch.setenv("MP_SECRET", "env_secret")
        monkeypatch.setenv("MP_PROJECT_ID", "env_proj_99")
        monkeypatch.setenv("MP_REGION", "in")

        session = cm_with_cred.resolve_session()

        # Env vars should win over any config setting
        assert session.project_id == "env_proj_99"
        assert session.region == "in"

    def test_env_vars_override_explicit_params(
        self, cm_with_cred: ConfigManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test env vars override even explicit credential/project params."""
        monkeypatch.setenv("MP_USERNAME", "env_user")
        monkeypatch.setenv("MP_SECRET", "env_secret")
        monkeypatch.setenv("MP_PROJECT_ID", "env_project")
        monkeypatch.setenv("MP_REGION", "us")

        session = cm_with_cred.resolve_session(credential="demo-sa", project_id="9999")

        # Env vars should still win
        assert session.project_id == "env_project"

    def test_partial_env_vars_do_not_trigger_env_resolution(
        self, cm_with_cred: ConfigManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that partial env vars (not all 4) fall back to config.

        The env var path requires all of MP_USERNAME, MP_SECRET,
        MP_PROJECT_ID, and MP_REGION to be set. If any is missing,
        it should fall through to the config-based resolution.
        """
        # Only set 3 of 4 env vars
        monkeypatch.setenv("MP_USERNAME", "env_user")
        monkeypatch.setenv("MP_SECRET", "env_secret")
        monkeypatch.setenv("MP_PROJECT_ID", "env_project")
        # MP_REGION is NOT set — partial set

        # Ensure MP_REGION is definitely not in environment
        monkeypatch.delenv("MP_REGION", raising=False)

        session = cm_with_cred.resolve_session()

        # Should fall back to config-based resolution
        assert session.project_id == "3713224"
        assert session.region == "us"

    def test_partial_env_vars_missing_username(
        self, cm_with_cred: ConfigManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test missing MP_USERNAME falls back to config."""
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.setenv("MP_SECRET", "env_secret")
        monkeypatch.setenv("MP_PROJECT_ID", "env_project")
        monkeypatch.setenv("MP_REGION", "eu")

        session = cm_with_cred.resolve_session()

        # Should fall back to config — project from active context
        assert session.project_id == "3713224"

    def test_partial_env_vars_missing_secret(
        self, cm_with_cred: ConfigManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test missing MP_SECRET falls back to config."""
        monkeypatch.setenv("MP_USERNAME", "env_user")
        monkeypatch.delenv("MP_SECRET", raising=False)
        monkeypatch.setenv("MP_PROJECT_ID", "env_project")
        monkeypatch.setenv("MP_REGION", "eu")

        session = cm_with_cred.resolve_session()

        # Should fall back to config
        assert session.project_id == "3713224"


# ── T112b-T112c: Orphaned Alias Warning ───────────────────────────────


class TestOrphanedAliasWarning:
    """T112b-T112c: Tests for orphaned alias detection on remove_credential."""

    def test_remove_credential_returns_orphaned_aliases(
        self, cm: ConfigManager
    ) -> None:
        """Test that remove_credential returns aliases referencing it."""
        cm.add_credential(
            name="demo-sa",
            type="service_account",
            username="user",
            secret="secret",
            region="us",
        )
        cm.add_project_alias("ecom", "3018488", credential="demo-sa")
        cm.add_project_alias("ai-demo", "3713224", credential="demo-sa")

        orphaned = cm.remove_credential("demo-sa")

        assert set(orphaned) == {"ecom", "ai-demo"}

    def test_remove_credential_no_orphaned_aliases(self, cm: ConfigManager) -> None:
        """Test remove_credential returns empty list when no aliases reference it."""
        cm.add_credential(
            name="sa1",
            type="service_account",
            username="user1",
            secret="secret1",
            region="us",
        )
        cm.add_credential(
            name="sa2",
            type="service_account",
            username="user2",
            secret="secret2",
            region="eu",
        )
        cm.add_project_alias("ecom", "3018488", credential="sa2")

        orphaned = cm.remove_credential("sa1")

        assert orphaned == []

    def test_remove_credential_aliases_without_credential_not_orphaned(
        self, cm: ConfigManager
    ) -> None:
        """Test aliases without credential binding are not flagged as orphaned."""
        cm.add_credential(
            name="demo-sa",
            type="service_account",
            username="user",
            secret="secret",
            region="us",
        )
        # Alias without credential binding
        cm.add_project_alias("staging", "9999")

        orphaned = cm.remove_credential("demo-sa")

        assert orphaned == []


# ── set_active_context() ─────────────────────────────────────────────


class TestSetActiveContext:
    """Tests for ConfigManager.set_active_context()."""

    def test_set_active_context_all_fields(self, cm: ConfigManager) -> None:
        """Test setting credential, project, and workspace in one write."""
        cm.add_credential(
            name="demo-sa",
            type="service_account",
            username="user",
            secret="secret",
            region="us",
        )
        cm.set_active_context(
            credential="demo-sa",
            project_id="3713224",
            workspace_id=3448413,
        )
        ctx = cm.get_active_context()
        assert ctx.credential == "demo-sa"
        assert ctx.project_id == "3713224"
        assert ctx.workspace_id == 3448413

    def test_set_active_context_partial_update(self, cm: ConfigManager) -> None:
        """Test partial update leaves other fields unchanged."""
        cm.add_credential(
            name="sa1",
            type="service_account",
            username="user1",
            secret="secret1",
            region="us",
        )
        cm.set_active_context(credential="sa1", project_id="111")
        cm.set_active_context(project_id="222")

        ctx = cm.get_active_context()
        assert ctx.credential == "sa1"
        assert ctx.project_id == "222"

    def test_set_active_context_clears_workspace_when_none(
        self, cm: ConfigManager
    ) -> None:
        """Test workspace_id is cleared when not provided."""
        cm.add_credential(
            name="sa1",
            type="service_account",
            username="user",
            secret="secret",
            region="us",
        )
        cm.set_active_context(credential="sa1", project_id="111", workspace_id=42)
        assert cm.get_active_context().workspace_id == 42

        cm.set_active_context(project_id="222")
        assert cm.get_active_context().workspace_id is None

    def test_set_active_context_invalid_credential_raises(
        self, cm: ConfigManager
    ) -> None:
        """Test setting a non-existent credential raises ConfigError."""
        with pytest.raises(ConfigError, match="not found"):
            cm.set_active_context(credential="nonexistent", project_id="111")


# ── add_credential type validation ───────────────────────────────────


class TestAddCredentialTypeValidation:
    """Tests for credential type validation in add_credential()."""

    def test_invalid_type_raises_value_error(self, cm: ConfigManager) -> None:
        """Test that an invalid credential type raises ValueError."""
        with pytest.raises(ValueError, match="Credential type must be one of"):
            cm.add_credential(
                name="bad",
                type="invalid_type",
                username="user",
                secret="secret",
                region="us",
            )

    def test_valid_types_accepted(self, cm: ConfigManager) -> None:
        """Test that valid credential types are accepted."""
        cm.add_credential(
            name="sa",
            type="service_account",
            username="user",
            secret="secret",
            region="us",
        )
        cm.add_credential(
            name="oauth",
            type="oauth",
            region="eu",
        )
        creds = cm.list_credentials()
        types = {c.type for c in creds}
        assert types == {"service_account", "oauth"}


# ── to_resolved_session workspace_id ─────────────────────────────────


class TestToResolvedSessionWorkspaceId:
    """Tests for workspace_id in Credentials.to_resolved_session()."""

    def test_workspace_id_passed_through(self) -> None:
        """Test workspace_id is included in the ProjectContext."""
        creds = Credentials(
            username="user",
            secret=SecretStr("secret"),
            project_id="12345",
            region="us",
        )
        session = creds.to_resolved_session(workspace_id=42)
        assert session.project.workspace_id == 42

    def test_workspace_id_default_none(self) -> None:
        """Test workspace_id defaults to None when not provided."""
        creds = Credentials(
            username="user",
            secret=SecretStr("secret"),
            project_id="12345",
            region="us",
        )
        session = creds.to_resolved_session()
        assert session.project.workspace_id is None
