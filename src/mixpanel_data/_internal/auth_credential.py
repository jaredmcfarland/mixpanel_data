"""Authentication credential models for the v2 config system.

Provides the foundational types that decouple authentication identity
from project context:

- ``AuthCredential``: A standalone authentication identity ("who you are").
- ``ProjectContext``: What you're working on (project + optional workspace).
- ``ResolvedSession``: The composition of auth + project, consumed by the API client.
- ``CredentialType``: Enum distinguishing service accounts from OAuth.

These types are re-exported via ``mixpanel_data.auth`` for public use.
"""

from __future__ import annotations

import base64
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator, model_validator

# Canonical RegionType definition — imported by config.py and other modules
RegionType = Literal["us", "eu", "in"]
VALID_REGIONS = ("us", "eu", "in")


class CredentialType(str, Enum):
    """Type of authentication credential.

    Distinguishes between service account (Basic Auth) and OAuth 2.0
    Bearer token authentication.

    Note: ``service_account`` corresponds to ``AuthMethod.basic`` in the
    legacy v1 config system.

    Example:
        ```python
        ct = CredentialType.service_account
        assert ct.value == "service_account"
        assert isinstance(ct, str)
        ```
    """

    service_account = "service_account"
    """HTTP Basic Auth with service account credentials."""

    oauth = "oauth"
    """OAuth 2.0 Bearer token authentication."""


class AuthCredential(BaseModel):
    """A standalone authentication identity — "who you are".

    Decoupled from any project binding. Immutable after construction.

    For service accounts: ``username`` and ``secret`` are required.
    For OAuth: ``oauth_access_token`` is required.

    Args:
        name: Unique identifier within config (e.g., "demo-sa").
        type: Authentication type (service_account or oauth).
        region: Data residency region (us, eu, or in).
        username: Service account username (SA only).
        secret: Service account secret, redacted in output (SA only).
        oauth_access_token: Bearer token, redacted in output (OAuth only).

    Example:
        ```python
        cred = AuthCredential(
            name="demo-sa",
            type=CredentialType.service_account,
            region="us",
            username="sa-user.abc.mp-service-account",
            secret=SecretStr("my-secret"),
        )
        header = cred.auth_header()  # "Basic <base64>"
        ```
    """

    model_config = ConfigDict(frozen=True)

    name: str
    """Unique identifier within config."""

    type: CredentialType
    """Authentication type."""

    region: RegionType
    """Data residency region."""

    username: str | None = None
    """Service account username (SA only)."""

    secret: SecretStr | None = None
    """Service account secret (SA only)."""

    oauth_access_token: SecretStr | None = None
    """OAuth 2.0 access token (OAuth only)."""

    @field_validator("region", mode="before")
    @classmethod
    def validate_region(cls, v: str) -> str:
        """Validate and normalize region to lowercase.

        Args:
            v: Region value to validate.

        Returns:
            Lowercase region string.

        Raises:
            ValueError: If region is not one of us, eu, in.
        """
        if not isinstance(v, str):
            raise ValueError(f"Region must be a string. Got: {type(v).__name__}")
        v_lower = v.lower()
        if v_lower not in VALID_REGIONS:
            valid = ", ".join(VALID_REGIONS)
            raise ValueError(f"Region must be one of: {valid}. Got: {v}")
        return v_lower

    @model_validator(mode="after")
    def validate_credential(self) -> AuthCredential:
        """Validate credential fields based on type.

        Returns:
            The validated AuthCredential instance.

        Raises:
            ValueError: If required fields are missing for the credential type.
        """
        if not self.name or not self.name.strip():
            raise ValueError("Name cannot be empty")

        if self.type == CredentialType.service_account:
            if not self.username or not self.username.strip():
                raise ValueError(
                    "Username cannot be empty for service account credentials"
                )
            if self.secret is None or not self.secret.get_secret_value():
                raise ValueError(
                    "Secret cannot be empty for service account credentials"
                )
        elif self.type == CredentialType.oauth:
            if self.oauth_access_token is None:
                raise ValueError("oauth_access_token is required for OAuth credentials")
            if not self.oauth_access_token.get_secret_value():
                raise ValueError("OAuth access token cannot be empty when provided")
        return self

    def auth_header(self) -> str:
        """Build the Authorization header value for API requests.

        Returns:
            For service accounts: ``"Basic <base64(username:secret)>"``.
            For OAuth: ``"Bearer <access_token>"``.

        Raises:
            ValueError: If required credentials are missing.

        Example:
            ```python
            cred = AuthCredential(
                name="sa", type=CredentialType.service_account,
                region="us", username="user", secret=SecretStr("pass"),
            )
            assert cred.auth_header().startswith("Basic ")
            ```
        """
        if self.type == CredentialType.oauth:
            if self.oauth_access_token is None:
                raise ValueError("No OAuth access token available")
            return f"Bearer {self.oauth_access_token.get_secret_value()}"

        if self.username is None or self.secret is None:
            raise ValueError("Username and secret required for Basic auth")
        raw = f"{self.username}:{self.secret.get_secret_value()}"
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        return f"Basic {encoded}"


class ProjectContext(BaseModel):
    """What you're working on — a project with an optional workspace selection.

    Immutable after construction.

    Args:
        project_id: Mixpanel project identifier (required, non-empty).
        workspace_id: Workspace within the project (optional, must be positive).
        project_name: Human-readable name from /me cache (optional).
        workspace_name: Human-readable name from /me cache (optional).

    Example:
        ```python
        ctx = ProjectContext(
            project_id="3713224",
            workspace_id=3448413,
            project_name="AI Demo",
        )
        ```
    """

    model_config = ConfigDict(frozen=True)

    project_id: str
    """Mixpanel project identifier."""

    workspace_id: int | None = None
    """Workspace within the project."""

    project_name: str | None = None
    """Human-readable project name."""

    workspace_name: str | None = None
    """Human-readable workspace name."""

    @model_validator(mode="after")
    def validate_project_context(self) -> ProjectContext:
        """Validate project context fields.

        Returns:
            The validated ProjectContext instance.

        Raises:
            ValueError: If project_id is empty or workspace_id is non-positive.
        """
        if not self.project_id or not self.project_id.strip():
            raise ValueError("Project ID cannot be empty")
        if self.workspace_id is not None and self.workspace_id <= 0:
            raise ValueError("Workspace ID must be a positive integer")
        return self


class ResolvedSession(BaseModel):
    """Fully resolved session: authentication + project context.

    The composition that the API client uses to make requests.
    Created by ``ConfigManager.resolve_session()`` or constructed directly.

    Args:
        auth: Authentication identity (AuthCredential).
        project: Project and workspace selection (ProjectContext).

    Example:
        ```python
        session = ResolvedSession(auth=cred, project=ctx)
        header = session.auth_header()
        pid = session.project_id
        ```
    """

    model_config = ConfigDict(frozen=True)

    auth: AuthCredential
    """Authentication identity."""

    project: ProjectContext
    """Project and workspace selection."""

    @property
    def project_id(self) -> str:
        """Shortcut to project.project_id.

        Returns:
            The project ID from the project context.
        """
        return self.project.project_id

    @property
    def region(self) -> RegionType:
        """Shortcut to auth.region.

        Returns:
            The region from the auth credential.
        """
        return self.auth.region

    @property
    def workspace_id(self) -> int | None:
        """Shortcut to project.workspace_id.

        Returns:
            The workspace ID from the project context, or None.
        """
        return self.project.workspace_id

    def auth_header(self) -> str:
        """Delegate to auth.auth_header().

        Returns:
            The Authorization header value.

        Raises:
            ValueError: If auth credentials are invalid.
        """
        return self.auth.auth_header()
