"""Public ``mp.session`` namespace.

Thin wrapper around :class:`~mixpanel_data._internal.config_v3.ConfigManager`
exposing the persisted ``[active]`` session and per-axis updates.

Note: this module shadows the :class:`Session` value type. Public
callers access via ``import mixpanel_data; mp.session.show()`` (module)
or ``import mixpanel_data; mp.Session(...)`` (the type).

Reference: specs/042-auth-architecture-redesign/contracts/python-api.md §7.
"""

from __future__ import annotations

from mixpanel_data._internal.auth.session import ActiveSession
from mixpanel_data._internal.config import ConfigManager


def _config() -> ConfigManager:
    """Return a fresh ConfigManager honoring ``MP_CONFIG_PATH``."""
    return ConfigManager()


def show() -> ActiveSession:
    """Return the persisted ``[active]`` block.

    Returns:
        ``ActiveSession`` with ``account`` and ``workspace`` (each may be
        None). Project lives on the active account as
        ``account.default_project`` — to read it, fetch the account.
    """
    return _config().get_active()


def use(
    *,
    account: str | None = None,
    project: str | None = None,
    workspace: int | None = None,
    target: str | None = None,
) -> None:
    """Update one or more axes in the persisted config.

    ``account=`` and ``workspace=`` are written to ``[active]``.
    ``project=`` is written to the **active account's** ``default_project``
    (project lives on the account, not in ``[active]``). ``target=`` is
    mutually exclusive with the per-axis kwargs and applies all three
    axes atomically (writing project to the target account's
    ``default_project``).

    Args:
        account: New active account name.
        project: New project ID (digit string) for the active account.
        workspace: New active workspace ID.
        target: Apply this target's three axes atomically.

    Raises:
        ValueError: ``target=`` combined with any axis kwarg.
        ConfigError: Referenced account or target not found, or
            ``project=`` supplied with no active account configured.
    """
    if target is not None and (
        account is not None or project is not None or workspace is not None
    ):
        raise ValueError(
            "`target=` is mutually exclusive with `account=`/`project=`/`workspace=`."
        )
    cm = _config()
    if target is not None:
        cm.apply_target(target)
        return
    # account / workspace go to [active]; project goes to the active account.
    # Both are written inside one _mutate() transaction so the on-disk state
    # never reflects a partial swap (e.g., new account but stale project).
    with cm._mutate() as raw:
        if account is not None or workspace is not None:
            cm._apply_set_active(raw, account=account, workspace=workspace)
        if project is not None:
            from mixpanel_data.exceptions import ConfigError

            active_block = raw.get("active", {}) or {}
            active_account = active_block.get("account")
            if account is not None:
                target_account = account
            elif isinstance(active_account, str):
                target_account = active_account
            else:
                raise ConfigError(
                    "Cannot set project: no active account. "
                    "Run `mp account use NAME` first, or pass `account=NAME` "
                    "together with `project=`."
                )
            cm._apply_update_account(raw, target_account, default_project=project)


__all__ = ["show", "use"]
