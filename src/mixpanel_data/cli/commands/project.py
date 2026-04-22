"""``mp project`` Typer command group.

Replaces ``mp projects`` with the singular form. Three subcommands:
``list``, ``use``, ``show``. Note: project lives on the active account as
``Account.default_project`` (FR-012); ``mp project use ID`` updates that
field rather than writing to ``[active]``. Reference:
contracts/cli-commands.md §4.
"""

from __future__ import annotations

from typing import Annotated

import typer

from mixpanel_data import session as session_ns
from mixpanel_data._internal.config_v3 import ConfigManager
from mixpanel_data.cli.utils import (
    ExitCode,
    console,
    err_console,
    handle_errors,
)
from mixpanel_data.exceptions import ConfigError

project_app = typer.Typer(
    name="project",
    help="Manage active Mixpanel project.",
    no_args_is_help=True,
)


def _active_account_default_project() -> tuple[str | None, str | None]:
    """Return ``(active_account_name, default_project)`` or ``(None, None)``.

    Returns:
        Tuple of (active account name, the account's default_project).
        Each element is ``None`` when not configured.
    """
    active = session_ns.show()
    if active.account is None:
        return (None, None)
    try:
        account = ConfigManager().get_account(active.account)
    except ConfigError:
        return (active.account, None)
    return (active.account, account.default_project)


@project_app.command("list")
@handle_errors
def list_projects(
    ctx: typer.Context,
    remote: Annotated[
        bool,
        typer.Option(
            "--remote",
            help="Fetch projects from /me (cached). Default: print active.",
        ),
    ] = False,
) -> None:
    """List projects accessible by the active account.

    With ``--remote``, fetches the project list from ``/me``. Without
    it, just prints the active account's ``default_project`` for a
    quick summary.

    Args:
        ctx: Typer context.
        remote: Whether to fetch the full /me project list.
    """
    if not remote:
        _account, project = _active_account_default_project()
        if project is None:
            console.print("(no active project)")
            return
        console.print(project)
        return
    err_console.print("[yellow]`mp project list --remote` is not yet wired.[/yellow]")
    raise typer.Exit(1)


@project_app.command("use")
@handle_errors
def use_project(
    ctx: typer.Context,
    project_id: Annotated[str, typer.Argument(help="Numeric Mixpanel project ID.")],
) -> None:
    """Update the active account's ``default_project``.

    Project lives on the account, not in ``[active]``. This command is
    equivalent to ``mp account update <active-account> --project ID``.

    Args:
        ctx: Typer context.
        project_id: Mixpanel project ID (numeric string).
    """
    active = session_ns.show()
    if active.account is None:
        err_console.print(
            "[red]No active account configured.[/red] Run `mp account use NAME` first."
        )
        raise typer.Exit(ExitCode.NOT_FOUND)
    ConfigManager().update_account(active.account, default_project=project_id)
    console.print(
        f"Set default_project for account '{active.account}' to '{project_id}'"
    )


@project_app.command("show")
@handle_errors
def show_project(ctx: typer.Context) -> None:
    """Show the currently active project (active account's ``default_project``).

    Args:
        ctx: Typer context.
    """
    _account, project = _active_account_default_project()
    if project is None:
        console.print("(no active project)")
    else:
        console.print(project)
