"""Unit tests for AuthCredential, ProjectContext, ResolvedSession, and CredentialType.

Tests cover:
- T007: CredentialType enum
- T008: AuthCredential model (construction, validation, auth_header)
- T009: ProjectContext model (construction, validation, optional fields)
- T010: ResolvedSession model (construction, properties, auth_header delegation)
"""

from __future__ import annotations

import base64

import pytest
from pydantic import SecretStr

from mixpanel_data._internal.auth_credential import (
    AuthCredential,
    CredentialType,
    ProjectContext,
    ResolvedSession,
)


class TestCredentialType:
    """T007: Tests for CredentialType enum."""

    def test_service_account_value(self) -> None:
        """Test service_account enum value."""
        assert CredentialType.service_account == "service_account"
        assert CredentialType.service_account.value == "service_account"

    def test_oauth_value(self) -> None:
        """Test oauth enum value."""
        assert CredentialType.oauth == "oauth"
        assert CredentialType.oauth.value == "oauth"

    def test_is_string_enum(self) -> None:
        """Test CredentialType is a string enum for TOML serialization."""
        assert isinstance(CredentialType.service_account, str)
        assert isinstance(CredentialType.oauth, str)

    def test_all_variants(self) -> None:
        """Test all expected variants exist."""
        values = {ct.value for ct in CredentialType}
        assert values == {"service_account", "oauth"}


class TestAuthCredential:
    """T008: Tests for AuthCredential model."""

    def test_construct_service_account(self) -> None:
        """Test constructing a service account credential."""
        cred = AuthCredential(
            name="demo-sa",
            type=CredentialType.service_account,
            region="us",
            username="sa-user.abc123.mp-service-account",
            secret=SecretStr("sa-secret-value"),
        )
        assert cred.name == "demo-sa"
        assert cred.type == CredentialType.service_account
        assert cred.region == "us"
        assert cred.username == "sa-user.abc123.mp-service-account"
        assert cred.secret is not None
        assert cred.secret.get_secret_value() == "sa-secret-value"

    def test_construct_oauth(self) -> None:
        """Test constructing an OAuth credential."""
        cred = AuthCredential(
            name="my-oauth",
            type=CredentialType.oauth,
            region="eu",
            oauth_access_token=SecretStr("bearer-token-xyz"),
        )
        assert cred.name == "my-oauth"
        assert cred.type == CredentialType.oauth
        assert cred.region == "eu"
        assert cred.oauth_access_token is not None
        assert cred.oauth_access_token.get_secret_value() == "bearer-token-xyz"

    def test_immutable(self) -> None:
        """Test AuthCredential is frozen/immutable."""
        cred = AuthCredential(
            name="demo",
            type=CredentialType.service_account,
            region="us",
            username="user",
            secret=SecretStr("secret"),
        )
        with pytest.raises(Exception):  # noqa: B017
            cred.name = "changed"  # type: ignore[misc]

    def test_name_required(self) -> None:
        """Test name cannot be empty."""
        with pytest.raises(ValueError, match="[Nn]ame"):
            AuthCredential(
                name="",
                type=CredentialType.service_account,
                region="us",
                username="user",
                secret=SecretStr("secret"),
            )

    def test_invalid_region(self) -> None:
        """Test invalid region is rejected."""
        with pytest.raises(ValueError, match="[Rr]egion"):
            AuthCredential(
                name="demo",
                type=CredentialType.service_account,
                region="invalid",
                username="user",
                secret=SecretStr("secret"),
            )

    def test_sa_requires_username(self) -> None:
        """Test service account requires username."""
        with pytest.raises(ValueError, match="[Uu]sername"):
            AuthCredential(
                name="demo",
                type=CredentialType.service_account,
                region="us",
                username="",
                secret=SecretStr("secret"),
            )

    def test_sa_requires_secret(self) -> None:
        """Test service account requires secret."""
        with pytest.raises(ValueError, match="[Ss]ecret"):
            AuthCredential(
                name="demo",
                type=CredentialType.service_account,
                region="us",
                username="user",
                secret=SecretStr(""),
            )

    def test_auth_header_basic(self) -> None:
        """Test auth_header returns Basic auth for service accounts."""
        cred = AuthCredential(
            name="demo",
            type=CredentialType.service_account,
            region="us",
            username="user",
            secret=SecretStr("secret"),
        )
        header = cred.auth_header()
        assert header.startswith("Basic ")
        decoded = base64.b64decode(header[6:]).decode("utf-8")
        assert decoded == "user:secret"

    def test_auth_header_oauth(self) -> None:
        """Test auth_header returns Bearer token for OAuth."""
        cred = AuthCredential(
            name="demo",
            type=CredentialType.oauth,
            region="us",
            oauth_access_token=SecretStr("my-token"),
        )
        assert cred.auth_header() == "Bearer my-token"

    def test_region_normalized_to_lowercase(self) -> None:
        """Test region is normalized to lowercase."""
        cred = AuthCredential(
            name="demo",
            type=CredentialType.service_account,
            region="US",
            username="user",
            secret=SecretStr("secret"),
        )
        assert cred.region == "us"

    def test_all_valid_regions(self) -> None:
        """Test all valid regions are accepted."""
        for region in ("us", "eu", "in"):
            cred = AuthCredential(
                name="demo",
                type=CredentialType.service_account,
                region=region,
                username="user",
                secret=SecretStr("secret"),
            )
            assert cred.region == region


class TestProjectContext:
    """T009: Tests for ProjectContext model."""

    def test_construct_minimal(self) -> None:
        """Test constructing with only required fields."""
        ctx = ProjectContext(project_id="3713224")
        assert ctx.project_id == "3713224"
        assert ctx.workspace_id is None
        assert ctx.project_name is None
        assert ctx.workspace_name is None

    def test_construct_full(self) -> None:
        """Test constructing with all fields."""
        ctx = ProjectContext(
            project_id="3713224",
            workspace_id=3448413,
            project_name="AI Demo",
            workspace_name="Default",
        )
        assert ctx.project_id == "3713224"
        assert ctx.workspace_id == 3448413
        assert ctx.project_name == "AI Demo"
        assert ctx.workspace_name == "Default"

    def test_immutable(self) -> None:
        """Test ProjectContext is frozen/immutable."""
        ctx = ProjectContext(project_id="123")
        with pytest.raises(Exception):  # noqa: B017
            ctx.project_id = "456"  # type: ignore[misc]

    def test_project_id_required(self) -> None:
        """Test project_id cannot be empty."""
        with pytest.raises(ValueError, match="[Pp]roject"):
            ProjectContext(project_id="")

    def test_workspace_id_must_be_positive(self) -> None:
        """Test workspace_id must be positive if provided."""
        with pytest.raises(ValueError, match="[Ww]orkspace"):
            ProjectContext(project_id="123", workspace_id=-1)

        with pytest.raises(ValueError, match="[Ww]orkspace"):
            ProjectContext(project_id="123", workspace_id=0)


class TestResolvedSession:
    """T010: Tests for ResolvedSession model."""

    @pytest.fixture
    def sa_credential(self) -> AuthCredential:
        """Create a service account credential for testing."""
        return AuthCredential(
            name="demo-sa",
            type=CredentialType.service_account,
            region="us",
            username="sa-user",
            secret=SecretStr("sa-secret"),
        )

    @pytest.fixture
    def project_context(self) -> ProjectContext:
        """Create a project context for testing."""
        return ProjectContext(
            project_id="3713224",
            workspace_id=3448413,
            project_name="AI Demo",
        )

    def test_construct(
        self, sa_credential: AuthCredential, project_context: ProjectContext
    ) -> None:
        """Test constructing a ResolvedSession."""
        session = ResolvedSession(auth=sa_credential, project=project_context)
        assert session.auth is sa_credential
        assert session.project is project_context

    def test_project_id_property(
        self, sa_credential: AuthCredential, project_context: ProjectContext
    ) -> None:
        """Test project_id delegates to project.project_id."""
        session = ResolvedSession(auth=sa_credential, project=project_context)
        assert session.project_id == "3713224"

    def test_region_property(
        self, sa_credential: AuthCredential, project_context: ProjectContext
    ) -> None:
        """Test region delegates to auth.region."""
        session = ResolvedSession(auth=sa_credential, project=project_context)
        assert session.region == "us"

    def test_auth_header_delegation(
        self, sa_credential: AuthCredential, project_context: ProjectContext
    ) -> None:
        """Test auth_header delegates to auth.auth_header()."""
        session = ResolvedSession(auth=sa_credential, project=project_context)
        header = session.auth_header()
        assert header.startswith("Basic ")
        decoded = base64.b64decode(header[6:]).decode("utf-8")
        assert decoded == "sa-user:sa-secret"

    def test_immutable(
        self, sa_credential: AuthCredential, project_context: ProjectContext
    ) -> None:
        """Test ResolvedSession is frozen/immutable."""
        session = ResolvedSession(auth=sa_credential, project=project_context)
        with pytest.raises(Exception):  # noqa: B017
            session.auth = sa_credential  # type: ignore[misc]

    def test_oauth_auth_header(self, project_context: ProjectContext) -> None:
        """Test auth_header with OAuth credential."""
        oauth_cred = AuthCredential(
            name="my-oauth",
            type=CredentialType.oauth,
            region="eu",
            oauth_access_token=SecretStr("oauth-token"),
        )
        session = ResolvedSession(auth=oauth_cred, project=project_context)
        assert session.auth_header() == "Bearer oauth-token"
        assert session.region == "eu"

    def test_workspace_id_property(self, sa_credential: AuthCredential) -> None:
        """Test workspace_id convenience property on ResolvedSession."""
        ctx_with_ws = ProjectContext(project_id="111", workspace_id=42)
        session = ResolvedSession(auth=sa_credential, project=ctx_with_ws)
        assert session.workspace_id == 42

        ctx_no_ws = ProjectContext(project_id="111")
        session2 = ResolvedSession(auth=sa_credential, project=ctx_no_ws)
        assert session2.workspace_id is None


class TestAuthCredentialOAuthValidation:
    """Tests for OAuth credential validation requiring token at construction."""

    def test_oauth_without_token_rejected(self) -> None:
        """OAuth credential with None token should raise ValueError."""
        with pytest.raises(ValueError, match="oauth_access_token is required"):
            AuthCredential(
                name="no-token",
                type=CredentialType.oauth,
                region="us",
            )

    def test_oauth_with_empty_token_rejected(self) -> None:
        """OAuth credential with empty string token should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            AuthCredential(
                name="empty-token",
                type=CredentialType.oauth,
                region="us",
                oauth_access_token=SecretStr(""),
            )

    def test_oauth_with_valid_token_accepted(self) -> None:
        """OAuth credential with a valid token should succeed."""
        cred = AuthCredential(
            name="good-oauth",
            type=CredentialType.oauth,
            region="us",
            oauth_access_token=SecretStr("my-token"),
        )
        assert cred.auth_header() == "Bearer my-token"

    def test_basic_auth_header_error_via_model_construct(self) -> None:
        """Test auth_header ValueError for Basic auth with missing fields.

        Uses model_construct to bypass validation and create an invalid state.
        """
        cred = AuthCredential.model_construct(
            name="broken",
            type=CredentialType.service_account,
            region="us",
            username=None,
            secret=None,
            oauth_access_token=None,
        )
        with pytest.raises(ValueError, match="Username and secret required"):
            cred.auth_header()
