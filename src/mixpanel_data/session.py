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
from mixpanel_data._internal.config_v3 import ConfigManager


def _config() -> ConfigManager:
    """Return a fresh ConfigManager honoring ``MP_CONFIG_PATH``."""
    return ConfigManager()


def show() -> ActiveSession:
    """Return the persisted ``[active]`` block.

    Returns:
        ``ActiveSession`` with ``account``, ``project``, ``workspace``
        fields (each may be None).
    """
    return _config().get_active()


def use(
    *,
    account: str | None = None,
    project: str | None = None,
    workspace: int | None = None,
    target: str | None = None,
) -> None:
    """Update one or more axes in the persisted ``[active]`` block.

    ``target=`` is mutually exclusive with the per-axis kwargs.

    Args:
        account: New active account name.
        project: New active project ID (digit string).
        workspace: New active workspace ID.
        target: Apply this target's three axes atomically.

    Raises:
        ValueError: ``target=`` combined with any axis kwarg.
        ConfigError: Referenced account or target not found.
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
    cm.set_active(account=account, project=project, workspace=workspace)


__all__ = ["show", "use"]
