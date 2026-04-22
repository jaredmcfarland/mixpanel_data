"""Session, Project, and WorkspaceRef value types.

A :class:`Session` is the in-memory representation of "who am I and what
am I working on" — an ``Account`` plus a ``Project`` and an optional
``WorkspaceRef``. Frozen and immutable; switching axes uses
:meth:`Session.replace`.

The naming distinction matters: :class:`WorkspaceRef` is the data type
held inside a Session, while ``mixpanel_data.Workspace`` (in the public
API) is the facade class. Renaming avoids the collision.

Reference: ``specs/042-auth-architecture-redesign/data-model.md`` §3, §4, §5.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from mixpanel_data._internal.auth.account import (
    Account,
    Region,
    TokenResolver,
)


class Project(BaseModel):
    """Mixpanel project reference.

    Project IDs come from the Mixpanel API as numeric strings. ``timezone``
    and ``organization_id`` are populated when the resolver has access to
    a ``/me`` response; both are optional.
    """

    model_config = ConfigDict(frozen=True)

    id: Annotated[str, Field(min_length=1, pattern=r"^\d+$")]
    """Numeric project ID (Mixpanel's wire format is a digit string)."""

    name: str | None = None
    """Display name from ``/me``, when known."""

    organization_id: int | None = None
    """Owning organization ID from ``/me``, when known."""

    timezone: str | None = None
    """Project timezone (e.g. ``"US/Pacific"``) from ``/me``, when known."""


class WorkspaceRef(BaseModel):
    """Mixpanel workspace reference (cohort/dashboard scoping unit).

    The data model is named ``WorkspaceRef`` to avoid colliding with the
    public ``Workspace`` facade class. Public re-export keeps the
    ``WorkspaceRef`` name.
    """

    model_config = ConfigDict(frozen=True)

    id: PositiveInt
    """Positive integer workspace ID assigned by Mixpanel."""

    name: str | None = None
    """Display name from ``/me`` or ``/projects/{pid}/workspaces/public``."""

    is_default: bool | None = None
    """Whether this is the project's default workspace, when known."""


class _SentinelType:
    """Singleton type used as a default marker in :meth:`Session.replace`.

    A sentinel is required for fields where ``None`` is a valid replacement
    value. Currently used for ``workspace`` (``None`` clears, omission
    preserves) and ``headers`` (``{}`` clears, omission preserves).
    """

    _instance: _SentinelType | None = None

    def __new__(cls) -> _SentinelType:
        """Return the singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        """Return a human-readable marker for debugging output."""
        return "<UNSET>"


_SENTINEL = _SentinelType()


class Session(BaseModel):
    """Immutable in-memory tuple of (Account, Project, optional WorkspaceRef).

    Holds the resolved auth/scope state for a single chain of API calls.
    Switching to a different account, project, or workspace produces a new
    Session via :meth:`replace`; the original is never mutated.

    Workspace is optional: a session with ``workspace=None`` lazy-resolves
    on the first workspace-scoped API call (per FR-025).
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    account: Account
    """Resolved account (one of the three discriminated variants)."""

    project: Project
    """Resolved Mixpanel project."""

    workspace: WorkspaceRef | None = None
    """Resolved workspace; ``None`` triggers lazy resolution on first use."""

    headers: dict[str, str] = Field(default_factory=dict)
    """Custom HTTP headers attached at resolution time.

    Populated from ``[settings].custom_header`` and/or ``bridge.headers``.
    Never read from ``os.environ`` after Session construction (per FR-014).
    """

    @property
    def project_id(self) -> str:
        """Return the project's numeric string ID.

        Returns:
            ``self.project.id``.
        """
        return self.project.id

    @property
    def workspace_id(self) -> int | None:
        """Return the workspace ID if set, else ``None``.

        Returns:
            ``self.workspace.id`` or ``None``.
        """
        return self.workspace.id if self.workspace is not None else None

    @property
    def region(self) -> Region:
        """Return the account's region.

        Returns:
            ``self.account.region``.
        """
        return self.account.region

    def auth_header(self, *, token_resolver: TokenResolver | None) -> str:
        """Return the ``Authorization`` header for HTTP requests.

        Args:
            token_resolver: Required for OAuth accounts; ignored for
                ``ServiceAccount``.

        Returns:
            The header value (``Basic ...`` or ``Bearer ...``).
        """
        # Only OAuth variants need a resolver; type-narrowed by the discriminator.
        if self.account.type == "service_account":
            return self.account.auth_header(token_resolver=token_resolver)
        if token_resolver is None:
            raise TypeError(
                "TokenResolver is required to compute auth_header for OAuth accounts"
            )
        return self.account.auth_header(token_resolver=token_resolver)

    def replace(
        self,
        *,
        account: Account | None = None,
        project: Project | None = None,
        workspace: WorkspaceRef | None | _SentinelType = _SENTINEL,
        headers: dict[str, str] | _SentinelType = _SENTINEL,
    ) -> Session:
        """Return a new Session with the supplied axes swapped in.

        Workspace and headers use a sentinel because ``None`` (resp. ``{}``)
        is a valid replacement value, semantically distinct from "do not
        touch this axis".

        Args:
            account: Replacement account; omitted preserves the current value.
            project: Replacement project; omitted preserves the current value.
            workspace: Replacement workspace; ``None`` clears the workspace
                (re-triggering lazy resolution); omitting the kwarg preserves
                the current value.
            headers: Replacement headers map; ``{}`` clears all custom headers;
                omitting the kwarg preserves the current value.

        Returns:
            A new :class:`Session` instance; the original is unchanged.
        """
        update: dict[str, Any] = {}
        if account is not None:
            update["account"] = account
        if project is not None:
            update["project"] = project
        if workspace is not _SENTINEL:
            update["workspace"] = workspace
        if headers is not _SENTINEL:
            update["headers"] = headers
        return self.model_copy(update=update)


class ActiveSession(BaseModel):
    """Persisted shape of the ``[active]`` block in ``~/.mp/config.toml``.

    Only ``account`` and ``workspace`` live in ``[active]``. Project lives
    on the account itself as ``Account.default_project`` — switching
    accounts implicitly switches projects (per FR-033). Any legacy
    ``[active].project`` field is rejected by ``extra="forbid"`` to surface
    the migration loudly.

    Both fields are optional — environment variables or per-command flags
    can supply each one independently.
    """

    model_config = ConfigDict(extra="forbid")

    account: str | None = None
    """Local config name of the active account (must reference ``[accounts.NAME]``)."""

    workspace: int | None = None
    """Active workspace ID (positive int) or ``None`` for lazy resolution."""


__all__ = [
    "ActiveSession",
    "Project",
    "Session",
    "WorkspaceRef",
    "_SENTINEL",
    "_SentinelType",
]
