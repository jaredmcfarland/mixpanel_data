"""Public ``mp.accounts`` namespace.

Thin wrapper around :class:`~mixpanel_data._internal.config.ConfigManager`
exposing account CRUD, switching, and probing operations as the canonical
Python API for ``mp account ...`` CLI commands and the plugin's
``auth_manager.py``.

Reference: specs/042-auth-architecture-redesign/contracts/python-api.md §5.
"""

from __future__ import annotations

import builtins
from pathlib import Path

from pydantic import SecretStr

from mixpanel_data._internal.auth.account import (
    AccountType,
    OAuthBrowserAccount,
    OAuthTokenAccount,
    ProjectId,
    Region,
    ServiceAccount,
)
from mixpanel_data._internal.auth.storage import account_dir, ensure_account_dir
from mixpanel_data._internal.auth.token import OAuthTokens, token_payload_bytes
from mixpanel_data._internal.auth.token_resolver import OnDiskTokenResolver
from mixpanel_data._internal.config import ConfigManager
from mixpanel_data._internal.io_utils import atomic_write_bytes
from mixpanel_data.exceptions import ConfigError, OAuthError
from mixpanel_data.types import (
    AccountSummary,
    AccountTestResult,
    MeUserInfo,
    OAuthLoginResult,
)


def _config() -> ConfigManager:
    """Return a fresh ConfigManager honoring ``MP_CONFIG_PATH`` / ``$HOME``."""
    return ConfigManager()


def list() -> builtins.list[AccountSummary]:  # noqa: A001 — public namespace shadow
    """Return all configured accounts as ``AccountSummary`` records.

    Returns:
        Sorted-by-name list of summaries.
    """
    return _config().list_accounts()


def add(
    name: str,
    *,
    type: AccountType,  # noqa: A002 — matches contracts/python-api.md
    region: Region,
    default_project: str | None = None,
    username: str | None = None,
    secret: SecretStr | str | None = None,
    token: SecretStr | str | None = None,
    token_env: str | None = None,
) -> AccountSummary:
    """Add a new account.

    Per FR-004, ``default_project`` is required at add-time for
    ``service_account`` and ``oauth_token``. For ``oauth_browser`` it is
    OPTIONAL — the value gets backfilled by ``login(name)`` after the PKCE
    flow completes via a ``/me`` lookup.

    Per FR-045, the first account added auto-promotes to
    ``[active].account``. Subsequent accounts do not.

    Args:
        name: Account name (must match ``^[a-zA-Z0-9_-]{1,64}$``).
        type: One of ``service_account`` / ``oauth_browser`` / ``oauth_token``.
        region: One of ``us`` / ``eu`` / ``in``.
        default_project: Numeric project ID. Required for SA / oauth_token;
            optional for oauth_browser (backfilled by ``login()``).
        username: Required for ``service_account``.
        secret: Required for ``service_account``.
        token: For ``oauth_token`` (mutually exclusive with ``token_env``).
        token_env: For ``oauth_token`` (mutually exclusive with ``token``).

    Returns:
        :class:`AccountSummary` for the new account.

    Raises:
        ConfigError: Validation failure or duplicate name.
    """
    cm = _config()
    # Compose the add-and-promote-as-active sequence in a single _mutate()
    # transaction so a fresh process never sees the new account without its
    # promoted [active].account when it was the first account added.
    with cm._mutate() as raw:
        is_first = not (raw.get("accounts") or {})
        cm._apply_add_account(
            raw,
            name,
            type=type,
            region=region,
            default_project=default_project,
            username=username,
            secret=secret,
            token=token,
            token_env=token_env,
        )
        if is_first:
            cm._apply_set_active(raw, account=name)
    return show(name)


def update(
    name: str,
    *,
    region: Region | None = None,
    default_project: str | None = None,
    username: str | None = None,
    secret: SecretStr | str | None = None,
    token: SecretStr | str | None = None,
    token_env: str | None = None,
) -> AccountSummary:
    """Update fields on an existing account in place.

    Type cannot be changed via this function (remove + re-add for that).
    Type-incompatible fields raise ``ConfigError``.

    Args:
        name: Account to update.
        region: New region.
        default_project: New ``default_project`` (digit string).
        username: New username (service_account only).
        secret: New secret (service_account only).
        token: New inline token (oauth_token only).
        token_env: New env-var name (oauth_token only).

    Returns:
        Updated :class:`AccountSummary`.

    Raises:
        ConfigError: Account not found, type-incompatible field, or
            validation failure.
    """
    _config().update_account(
        name,
        region=region,
        default_project=default_project,
        username=username,
        secret=secret,
        token=token,
        token_env=token_env,
    )
    return show(name)


def remove(name: str, *, force: bool = False) -> builtins.list[str]:
    """Remove an account.

    Args:
        name: Account name.
        force: When ``True``, remove even if referenced by targets.

    Returns:
        List of orphaned target names (empty unless ``force=True`` and
        the account had references).

    Raises:
        ConfigError: Missing account.
        AccountInUseError: Referenced and ``force=False``.
    """
    return _config().remove_account(name, force=force)


def use(name: str) -> None:
    """Switch the active account, clearing any prior workspace pin.

    The new account becomes ``[active].account`` and any prior
    ``[active].workspace`` is dropped — workspaces are project-scoped, so
    a leftover workspace ID from a different account would resolve to a
    foreign workspace (or a 404) on the next ``Workspace()`` construction.
    Project lives on the account itself as
    :attr:`Account.default_project`, so it travels with the new account
    automatically — no separate project axis to reset.

    Both writes happen in a single ``_mutate()`` transaction so the
    next process never sees a half-swapped state.

    Args:
        name: Account to make active.

    Raises:
        ConfigError: Account does not exist.
    """
    cm = _config()
    with cm._mutate() as raw:
        cm._apply_set_active(raw, account=name)
        cm._apply_clear_active(raw, workspace=True)


def show(name: str | None = None) -> AccountSummary:
    """Return the named account summary, or the active one if no name given.

    Args:
        name: Account name; if ``None``, the active account is shown.

    Returns:
        :class:`AccountSummary`.

    Raises:
        ConfigError: Account not found OR no active account configured.
    """
    cm = _config()
    if name is None:
        active = cm.get_active().account
        if not active:
            raise ConfigError("No active account configured.")
        name = active
    summaries = {s.name: s for s in cm.list_accounts()}
    if name not in summaries:
        raise ConfigError(f"Account '{name}' not found.")
    return summaries[name]


def test(name: str | None = None) -> AccountTestResult:
    """Probe ``/me`` for the named account and return the structured result.

    Resolves the named account (or active account when ``name`` is None),
    constructs a short-lived :class:`MixpanelAPIClient` against ``/me``,
    and reports whether the credentials are accepted plus the
    authenticated user identity / accessible-project count from the
    response body.

    Never raises — every failure mode (account not found, missing
    credentials, OAuth refresh failure, HTTP error) is captured in
    ``result.error`` so the CLI can render a structured failure message
    and downstream tooling can color accounts as
    ``needs_login`` / ``needs_token`` based on the error string.

    Args:
        name: Account to test; ``None`` means the active account.

    Returns:
        :class:`AccountTestResult` — ``ok=True`` with ``user`` populated
        on success, or ``ok=False`` with ``error`` describing the failure.
    """
    try:
        summary = show(name)
    except ConfigError as exc:
        return AccountTestResult(
            account_name=name or "(none)", ok=False, error=str(exc)
        )

    cm = _config()
    try:
        account = cm.get_account(summary.name)
    except ConfigError as exc:  # pragma: no cover — show() already validated
        return AccountTestResult(account_name=summary.name, ok=False, error=str(exc))

    # Lazy imports to keep import-time cheap (httpx + threading pull in lots).
    from mixpanel_data._internal.api_client import MixpanelAPIClient
    from mixpanel_data._internal.auth.session import Project, Session
    from mixpanel_data._internal.me import MeResponse

    # ``MixpanelAPIClient`` requires a project to construct a Session even
    # though ``/me`` itself is project-agnostic. Use the account's default
    # when present, falling back to ``"0"`` so probes still work for fresh
    # ``oauth_browser`` accounts that have not yet been login'd.
    placeholder_project = account.default_project or "0"
    probe_session = Session(
        account=account,
        project=Project(id=placeholder_project),
    )

    api_client = MixpanelAPIClient(session=probe_session)
    try:
        try:
            me_raw = api_client.me()
        except Exception as exc:  # noqa: BLE001 — capture every failure mode
            return AccountTestResult(
                account_name=summary.name,
                ok=False,
                error=f"/me probe failed: {exc}",
            )
        try:
            me_resp = MeResponse.model_validate(me_raw)
        except Exception as exc:  # noqa: BLE001 — malformed payload
            return AccountTestResult(
                account_name=summary.name,
                ok=False,
                error=f"/me response could not be parsed: {exc}",
            )
        user: MeUserInfo | None = None
        if me_resp.user_id is not None and me_resp.user_email is not None:
            user = MeUserInfo(id=me_resp.user_id, email=me_resp.user_email)
        project_count = len(me_resp.projects) if me_resp.projects else 0
        return AccountTestResult(
            account_name=summary.name,
            ok=True,
            user=user,
            accessible_project_count=project_count,
        )
    finally:
        api_client.close()


def login(
    name: str,
    *,
    open_browser: bool = True,
) -> OAuthLoginResult:
    """Run the OAuth browser flow for an ``oauth_browser`` account.

    Drives the full PKCE login dance:

    1. Validate ``name`` resolves to an ``oauth_browser`` account.
    2. Run :meth:`OAuthFlow.login` (PKCE + browser callback + token exchange).
    3. Persist the resulting tokens atomically to
       ``~/.mp/accounts/{name}/tokens.json``.
    4. Probe ``/me`` to capture the authenticated user identity and
       (when missing) backfill ``account.default_project`` with the first
       accessible project.

    The browser is opened by default; pass ``open_browser=False`` to
    skip the call (useful for headless environments where the user copies
    the authorization URL manually).

    Args:
        name: Account name (must be ``oauth_browser`` type).
        open_browser: Whether to launch the system browser. When False,
            the authorize URL is printed to stderr for manual copy
            (CLI flag: ``mp account login NAME --no-browser``).

    Returns:
        An :class:`OAuthLoginResult` describing the persistence paths,
        token expiry, and (best-effort) authenticated user identity.

    Raises:
        ConfigError: ``name`` is not configured or is not ``oauth_browser``.
        OAuthError: Any leg of the PKCE flow fails (registration, browser,
            callback, token exchange).
    """
    cm = _config()
    account = cm.get_account(name)
    if not isinstance(account, OAuthBrowserAccount):
        raise ConfigError(
            f"`mp account login` is only valid for oauth_browser accounts; "
            f"'{name}' is type '{account.type}'."
        )

    # Lazy imports — pull in OAuthFlow / Workspace only when actually logging in.
    from mixpanel_data._internal.api_client import MixpanelAPIClient
    from mixpanel_data._internal.auth.flow import OAuthFlow
    from mixpanel_data._internal.auth.session import Project, Session
    from mixpanel_data._internal.me import MeResponse

    flow = OAuthFlow(region=account.region)
    # ``persist=False`` skips the v2 ``~/.mp/oauth/tokens_{region}.json``
    # write — v3 owns ``~/.mp/accounts/{name}/tokens.json`` exclusively.
    tokens = flow.login(persist=False, open_browser=open_browser)

    tokens_path = _persist_browser_tokens(name, tokens)

    # /me probe: validates the freshly minted bearer + backfills the
    # account's default_project on first login.
    user: MeUserInfo | None = None
    chosen_project = account.default_project
    placeholder_project = chosen_project or "0"
    probe_session = Session(
        account=account,
        project=Project(id=placeholder_project),
    )
    api_client = MixpanelAPIClient(session=probe_session)
    try:
        try:
            me_raw = api_client.me()
            me_resp = MeResponse.model_validate(me_raw)
        except Exception as exc:  # noqa: BLE001 — re-raise as OAuthError below
            raise OAuthError(
                f"Login succeeded but `/me` probe failed: {exc}",
                code="OAUTH_TOKEN_ERROR",
                details={"account_name": name, "region": account.region},
            ) from exc
        if me_resp.user_id is not None and me_resp.user_email is not None:
            user = MeUserInfo(id=me_resp.user_id, email=me_resp.user_email)
        if chosen_project is None and me_resp.projects:
            # ``me_resp.projects`` keys are str at runtime; cast to ProjectId
            # to satisfy the typed contract on ``Account.default_project``.
            chosen_project = ProjectId(next(iter(sorted(me_resp.projects))))
            cm.update_account(name, default_project=chosen_project)
    finally:
        api_client.close()

    return OAuthLoginResult(
        account_name=name,
        user=user,
        expires_at=tokens.expires_at,
        tokens_path=tokens_path,
        client_path=_client_info_path(account.region),
    )


def _persist_browser_tokens(name: str, tokens: OAuthTokens) -> Path:
    """Write ``tokens`` to the per-account ``tokens.json`` atomically (mode 0o600).

    Args:
        name: Account name (locates ``~/.mp/accounts/{name}/``).
        tokens: A :class:`OAuthTokens` instance just returned from
            :meth:`OAuthFlow.login`.

    Returns:
        The path that was written.
    """
    path = ensure_account_dir(name) / "tokens.json"
    atomic_write_bytes(path, token_payload_bytes(tokens))
    return path


def _client_info_path(region: Region) -> Path:
    """Return where ``OAuthFlow`` cached the DCR client info for ``region``.

    The v3 layout still shares DCR client metadata across accounts in the
    same region (every Mixpanel ``oauth_browser`` account speaks to the
    same authorization server, so there is one DCR client per region).
    Recorded for ``OAuthLoginResult.client_path`` so callers can find it.

    Args:
        region: Mixpanel data residency region.

    Returns:
        Absolute path to the client info JSON (may not exist yet).
    """
    return Path.home() / ".mp" / "oauth" / f"client_{region}.json"


def logout(name: str) -> None:
    """Remove the on-disk OAuth tokens for an ``oauth_browser`` account.

    Args:
        name: Account name.

    Raises:
        ConfigError: Account not found.
    """
    summary = show(name)  # raises if missing
    tokens_path = account_dir(summary.name) / "tokens.json"
    if tokens_path.exists():
        tokens_path.unlink()


def token(name: str | None = None) -> str | None:
    """Return the current bearer token for an OAuth account.

    Args:
        name: Account name; ``None`` means the active account.

    Returns:
        For ``service_account``: ``None`` (no bearer).
        For ``oauth_browser``: the on-disk access token (raises ``OAuthError``
        via the resolver if unavailable).
        For ``oauth_token``: the inline / env-resolved token.

    Raises:
        ConfigError: Account not found.
        OAuthError: OAuth token cannot be resolved (missing tokens, missing
            env var, etc.).
    """
    cm = _config()
    summary = show(name)
    account = cm.get_account(summary.name)
    resolver = OnDiskTokenResolver()
    if isinstance(account, ServiceAccount):
        return None
    if isinstance(account, OAuthBrowserAccount):
        return resolver.get_browser_token(account.name, account.region)
    if isinstance(account, OAuthTokenAccount):
        return resolver.get_static_token(account)
    raise ConfigError(  # pragma: no cover — Literal exhaustiveness
        f"Unknown account type for {summary.name!r}"
    )


def export_bridge(
    *,
    to: Path,
    account: str | None = None,
    project: str | None = None,
    workspace: int | None = None,
) -> Path:
    """Export the named (or active) account as a v2 bridge file.

    Resolves the account, attaches any ``[settings].custom_header`` as
    ``bridge.headers`` (B5 — header attaches in memory at resolution time
    for the consumer), and writes a 0o600 file at ``to`` via
    :func:`bridge.export_bridge`.

    Args:
        to: Destination path for the bridge file.
        account: Account to export; ``None`` means the active account.
        project: Optional pinned project ID. ``None`` omits the field.
        workspace: Optional pinned workspace ID. ``None`` omits the field.

    Returns:
        The path that was written (same as ``to``).

    Raises:
        ConfigError: Account not found, no active account, or
            ``BridgeFile`` validation failure.
        OAuthError: ``account.type == "oauth_browser"`` but no on-disk
            tokens are available.
    """
    from mixpanel_data._internal.auth.bridge import (
        export_bridge as _bridge_export,
    )

    cm = _config()
    name = account or cm.get_active().account
    if name is None:
        raise ConfigError("No account specified and no active account configured.")
    acct = cm.get_account(name)
    header = cm.get_custom_header()
    headers = {header[0]: header[1]} if header is not None else None
    return _bridge_export(
        acct,
        to=to,
        project=project,
        workspace=workspace,
        headers=headers,
        token_resolver=OnDiskTokenResolver(),
    )


def remove_bridge(*, at: Path | None = None) -> bool:
    """Remove the v2 bridge file at ``at`` (or the default path).

    Args:
        at: Bridge file path; ``None`` means ``MP_AUTH_FILE`` then the
            default search paths.

    Returns:
        ``True`` if a file was deleted; ``False`` if none was found.
    """
    from mixpanel_data._internal.auth.bridge import (
        remove_bridge as _bridge_remove,
    )

    return _bridge_remove(at=at)


__all__ = [
    "add",
    "export_bridge",
    "list",
    "login",
    "logout",
    "remove",
    "remove_bridge",
    "show",
    "test",
    "token",
    "update",
    "use",
]
