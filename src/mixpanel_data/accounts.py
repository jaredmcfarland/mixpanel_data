"""Public ``mp.accounts`` namespace.

Thin wrapper around :class:`~mixpanel_data._internal.config_v3.ConfigManager`
exposing account CRUD, switching, and probing operations as the canonical
Python API for ``mp account ...`` CLI commands and the plugin's
``auth_manager.py``.

Bridge functions (``export_bridge`` / ``remove_bridge``) are stubs in
Phase 4 and raise :class:`NotImplementedError`. They land in Phase 8 with
the v2 bridge writer.

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
    Region,
    ServiceAccount,
)
from mixpanel_data._internal.auth.token_resolver import OnDiskTokenResolver
from mixpanel_data._internal.config import ConfigManager
from mixpanel_data.exceptions import ConfigError
from mixpanel_data.types import AccountSummary, AccountTestResult


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

    Phase 4 stub: returns a placeholder result indicating ``probe deferred``;
    full ``/me`` integration arrives in Phase 5 along with the CLI wiring.
    Never raises — captures errors in ``result.error``.

    Args:
        name: Account to test; ``None`` means the active account.

    Returns:
        :class:`AccountTestResult`.
    """
    try:
        summary = show(name)
    except ConfigError as exc:
        return AccountTestResult(
            account_name=name or "(none)", ok=False, error=str(exc)
        )
    return AccountTestResult(
        account_name=summary.name,
        ok=False,
        error=(
            "test() probe is not yet wired up; this is a Phase 4 stub. "
            "Use `mp account login` (oauth_browser) or set MP_OAUTH_TOKEN to verify."
        ),
    )


def login(name: str, *, open_browser: bool = True) -> object:
    """Run the OAuth browser flow for an ``oauth_browser`` account.

    Phase 4 stub: full PKCE wiring lands in Phase 5 along with the CLI
    command. For now, raises :class:`NotImplementedError` instructing the
    caller to use the CLI.

    Args:
        name: Account name (must be ``oauth_browser`` type).
        open_browser: Whether to launch the system browser.

    Raises:
        NotImplementedError: Phase 4 stub.
    """
    raise NotImplementedError(
        f"`mp.accounts.login({name!r})` is wired in Phase 5 with the CLI."
    )


def logout(name: str) -> None:
    """Remove the on-disk OAuth tokens for an ``oauth_browser`` account.

    Args:
        name: Account name.

    Raises:
        ConfigError: Account not found.
    """
    summary = show(name)  # raises if missing
    tokens_path = Path.home() / ".mp" / "accounts" / summary.name / "tokens.json"
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


def export_bridge(*, to: Path, account: str | None = None) -> Path:
    """Export the named (or active) account as a v2 bridge file.

    Phase 4 stub — full writer lands in Phase 8.

    Args:
        to: Destination path for the bridge file.
        account: Account to export; ``None`` means the active account.

    Raises:
        NotImplementedError: Phase 4 stub.
    """
    raise NotImplementedError(
        "`mp.accounts.export_bridge` is implemented in Phase 8 (US8)."
    )


def remove_bridge(*, at: Path | None = None) -> bool:
    """Remove the v2 bridge file at ``at`` (or the default path).

    Phase 4 stub — full implementation lands in Phase 8.

    Args:
        at: Bridge file path; ``None`` means the default search path.

    Raises:
        NotImplementedError: Phase 4 stub.
    """
    raise NotImplementedError(
        "`mp.accounts.remove_bridge` is implemented in Phase 8 (US8)."
    )


# Note: ``login``, ``test``, ``export_bridge``, and ``remove_bridge`` are
# defined above as stubs but intentionally NOT exported. They become public
# in __all__ once the underlying OAuth/PKCE/bridge writer wiring lands. This
# keeps `from mixpanel_data import accounts; accounts.<TAB>` from advertising
# functions that immediately raise ``NotImplementedError``.
__all__ = [
    "add",
    "list",
    "logout",
    "remove",
    "show",
    "token",
    "update",
    "use",
]
