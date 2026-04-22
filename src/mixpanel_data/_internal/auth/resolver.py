"""Single-function resolver for ``Session`` construction.

Replaces the six-layer fallback chain in the legacy ``ConfigManager`` with
one pure-functional ``resolve_session`` that consults independent priority
axes:

    Account axis:    env → param → target → bridge → config[active]
    Project axis:    env → param → target → bridge → config[active]
    Workspace axis:  env → param → target → bridge → config[active]

Each axis is independent — perturbing one input never affects the others
(verified by Hypothesis property tests). The resolver does no I/O beyond
optionally reading the config and bridge file (both passed in by the
caller); never reads OAuth tokens (those are fetched lazily by
``MixpanelAPIClient`` at request time); never mutates ``os.environ``.

Per spec FR-024, when an axis cannot be resolved, the raised
``ConfigError`` lists every fix path the user can try.

Reference: specs/042-auth-architecture-redesign/contracts/python-api.md §1.
"""

from __future__ import annotations

import os

from pydantic import SecretStr, ValidationError

from mixpanel_data._internal.auth.account import (
    Account,
    OAuthTokenAccount,
    Region,
    ServiceAccount,
)
from mixpanel_data._internal.auth.bridge import BridgeFile, load_bridge
from mixpanel_data._internal.auth.session import (
    Project,
    Session,
    WorkspaceRef,
)
from mixpanel_data._internal.config_v3 import ConfigManager
from mixpanel_data.exceptions import ConfigError

_VALID_REGIONS: frozenset[str] = frozenset({"us", "eu", "in"})


def _env_region() -> Region | None:
    """Return ``MP_REGION`` if it's a valid region literal, else None."""
    val = os.environ.get("MP_REGION")
    if val and val in _VALID_REGIONS:
        return val  # type: ignore[return-value]
    return None


def _env_account_from_service_quad() -> Account | None:
    """Synthesize a ``ServiceAccount`` if the full SA env quad is present.

    The SA quad is ``MP_USERNAME`` + ``MP_SECRET`` + ``MP_PROJECT_ID`` +
    ``MP_REGION``. When all four are set, returns an in-memory
    ``ServiceAccount`` with a synthetic name; ``MP_PROJECT_ID`` itself is
    only used by the project axis (the account synthesis only needs region).

    Returns:
        A synthesized ``ServiceAccount``, or ``None`` if any quad member
        is missing or invalid.
    """
    username = os.environ.get("MP_USERNAME")
    secret = os.environ.get("MP_SECRET")
    project = os.environ.get("MP_PROJECT_ID")
    region = _env_region()
    if not username or not secret or not project or region is None:
        return None
    try:
        return ServiceAccount(
            name="env-service-account",
            region=region,
            username=username,
            secret=SecretStr(secret),
        )
    except ValidationError:  # pragma: no cover — defensive
        return None


def _env_account_from_oauth_token() -> Account | None:
    """Synthesize an ``OAuthTokenAccount`` from ``MP_OAUTH_TOKEN`` env.

    Requires ``MP_OAUTH_TOKEN`` + ``MP_PROJECT_ID`` + ``MP_REGION``. The
    SA quad takes precedence (per PR #125 — preserved by this resolver).

    Returns:
        A synthesized ``OAuthTokenAccount``, or ``None`` if any required
        env var is missing or invalid.
    """
    token = os.environ.get("MP_OAUTH_TOKEN")
    project = os.environ.get("MP_PROJECT_ID")
    region = _env_region()
    if not token or not project or region is None:
        return None
    try:
        return OAuthTokenAccount(
            name="env-oauth-token",
            region=region,
            token=SecretStr(token),
        )
    except ValidationError:  # pragma: no cover — defensive
        return None


def _resolve_account_axis(
    *,
    explicit: str | None,
    target_account_name: str | None,
    bridge: BridgeFile | None,
    config: ConfigManager,
) -> Account | None:
    """Resolve the account axis per the documented priority order.

    Order:
        1. Env: SA quad first (PR #125), then OAuth-token env.
        2. Explicit ``account=NAME`` param → load from config.
        3. ``--target NAME`` → load the target's referenced account.
        4. Bridge file's account.
        5. ``[active].account`` from config.

    Args:
        explicit: Value of ``account=`` kwarg (or env-var override).
        target_account_name: When ``--target NAME`` was applied, the
            account name from that target block.
        bridge: Loaded bridge file, if any.
        config: V3 ConfigManager (may have an empty ``[active]`` block).

    Returns:
        The resolved ``Account``, or ``None`` if no source produced a value.
    """
    sa = _env_account_from_service_quad()
    if sa is not None:
        return sa
    ot = _env_account_from_oauth_token()
    if ot is not None:
        return ot
    if explicit is not None:
        return config.get_account(explicit)
    if target_account_name is not None:
        return config.get_account(target_account_name)
    if bridge is not None:
        return bridge.account
    active = config.get_active()
    if active.account is not None:
        return config.get_account(active.account)
    return None


def _resolve_project_axis(
    *,
    explicit: str | None,
    target_project: str | None,
    bridge: BridgeFile | None,
    config: ConfigManager,
) -> str | None:
    """Resolve the project axis per the documented priority order.

    Order (per FR-017): env > param > target > bridge > config.

    Args:
        explicit: Value of ``project=`` kwarg.
        target_project: Project from ``--target NAME``, if applied.
        bridge: Loaded bridge file, if any.
        config: V3 ConfigManager.

    Returns:
        Project ID (digit string), or ``None`` if no source resolves.
    """
    env_val = os.environ.get("MP_PROJECT_ID")
    if env_val:
        return env_val
    if explicit is not None:
        return explicit
    if target_project is not None:
        return target_project
    if bridge is not None and bridge.project is not None:
        return bridge.project
    active = config.get_active()
    return active.project


def _resolve_workspace_axis(
    *,
    explicit: int | None,
    target_workspace: int | None,
    bridge: BridgeFile | None,
    config: ConfigManager,
) -> int | None:
    """Resolve the workspace axis per the documented priority order.

    ``None`` is a valid terminal value (lazy resolution on first
    workspace-scoped API call per FR-025).

    Args:
        explicit: Value of ``workspace=`` kwarg.
        target_workspace: Workspace from ``--target NAME``, if applied.
        bridge: Loaded bridge file, if any.
        config: V3 ConfigManager.

    Returns:
        Workspace ID, or ``None`` (lazy-resolve later).
    """
    env_val = os.environ.get("MP_WORKSPACE_ID")
    if env_val:
        try:
            parsed = int(env_val)
        except ValueError:
            parsed = 0
        if parsed > 0:
            return parsed
    if explicit is not None:
        return explicit
    if target_workspace is not None:
        return target_workspace
    if bridge is not None and bridge.workspace is not None:
        return bridge.workspace
    active = config.get_active()
    return active.workspace


def _resolve_headers(
    *, bridge: BridgeFile | None, config: ConfigManager
) -> dict[str, str]:
    """Collect custom HTTP headers from settings + bridge.

    ``[settings].custom_header`` contributes a single ``{name: value}``
    entry; the bridge contributes a multi-entry map. Bridge wins on
    collision (highest priority among header sources, matching the
    bridge's general "ephemeral override" role).

    Args:
        bridge: Loaded bridge file, if any.
        config: V3 ConfigManager.

    Returns:
        Headers map ready to attach to ``Session.headers``.
    """
    headers: dict[str, str] = {}
    setting = config.get_custom_header()
    if setting is not None:
        headers[setting[0]] = setting[1]
    if bridge is not None and bridge.headers:
        headers.update(bridge.headers)
    return headers


def _format_no_account_error() -> str:
    """Return the multi-line FR-024 error for an unresolvable account axis."""
    return (
        "No account configured.\n"
        "\n"
        "Fix one of the following:\n"
        "  - Set MP_USERNAME, MP_SECRET, MP_PROJECT_ID, MP_REGION\n"
        "  - Set MP_OAUTH_TOKEN, MP_PROJECT_ID, MP_REGION\n"
        "  - Run `mp account add NAME ...` then `mp account use NAME`\n"
        "  - Run `mp account login NAME` for OAuth\n"
        "  - Use `--account NAME` per command\n"
        "  - Use `--target NAME` per command\n"
    )


def _format_no_project_error() -> str:
    """Return the multi-line FR-024 error for an unresolvable project axis."""
    return (
        "No project configured.\n"
        "\n"
        "Fix one of the following:\n"
        "  - Set MP_PROJECT_ID\n"
        "  - Run `mp project use ID`\n"
        "  - Use `--project ID` per command\n"
        "  - Use `--target NAME` per command (target supplies project)\n"
    )


def resolve_session(
    *,
    account: str | None = None,
    project: str | None = None,
    workspace: int | None = None,
    target: str | None = None,
    config: ConfigManager | None = None,
    bridge: BridgeFile | None = None,
) -> Session:
    """Resolve a :class:`Session` from per-axis inputs and config sources.

    Per FR-016: the three axes resolve independently. Per FR-017: each
    axis consults env → param → target → bridge → config in priority
    order. The resolver is pure-functional: no token I/O, no env
    mutation, no network.

    Args:
        account: Explicit account name (e.g., from ``--account NAME``).
        project: Explicit project ID (e.g., from ``--project ID``).
        workspace: Explicit workspace ID (e.g., from ``--workspace ID``).
        target: Named target whose three axes apply (mutually exclusive
            with ``account=``/``project=``/``workspace=``).
        config: V3 ConfigManager. Defaults to a freshly constructed
            ``ConfigManager()`` reading ``MP_CONFIG_PATH`` or
            ``~/.mp/config.toml``.
        bridge: Pre-loaded bridge file. If ``None``, the resolver loads
            via :func:`load_bridge` (which honors ``MP_AUTH_FILE`` + the
            default search paths).

    Returns:
        A frozen :class:`Session` with account, project, optional
        workspace, and any custom headers attached.

    Raises:
        ValueError: ``target`` combined with any axis kwarg.
        ConfigError: An axis cannot be resolved or refers to an unknown
            account / target.
    """
    if target is not None and (
        account is not None or project is not None or workspace is not None
    ):
        raise ValueError(
            "`target=` is mutually exclusive with `account=`/`project=`/`workspace=`."
        )

    cfg = config if config is not None else ConfigManager()
    br = bridge if bridge is not None else load_bridge()

    target_account_name: str | None = None
    target_project: str | None = None
    target_workspace: int | None = None
    if target is not None:
        t = cfg.get_target(target)
        target_account_name = t.account
        target_project = t.project
        target_workspace = t.workspace

    account_obj = _resolve_account_axis(
        explicit=account,
        target_account_name=target_account_name,
        bridge=br,
        config=cfg,
    )
    if account_obj is None:
        raise ConfigError(_format_no_account_error())

    project_id = _resolve_project_axis(
        explicit=project,
        target_project=target_project,
        bridge=br,
        config=cfg,
    )
    if project_id is None:
        raise ConfigError(_format_no_project_error())
    try:
        project_obj = Project(id=project_id)
    except ValidationError as exc:
        raise ConfigError(
            f"Invalid project ID: {project_id!r}. Must match `^\\d+$`."
        ) from exc

    workspace_id = _resolve_workspace_axis(
        explicit=workspace,
        target_workspace=target_workspace,
        bridge=br,
        config=cfg,
    )
    workspace_obj: WorkspaceRef | None = None
    if workspace_id is not None:
        try:
            workspace_obj = WorkspaceRef(id=workspace_id)
        except ValidationError as exc:
            raise ConfigError(
                f"Invalid workspace ID: {workspace_id!r}. Must be > 0."
            ) from exc

    headers = _resolve_headers(bridge=br, config=cfg)

    return Session(
        account=account_obj,
        project=project_obj,
        workspace=workspace_obj,
        headers=headers,
    )


__all__ = [
    "resolve_session",
]
