"""``mp project`` Typer command group (042 redesign).

Replaces ``mp projects`` with the singular form. Three subcommands:
``list``, ``use``, ``show``. Reference: contracts/cli-commands.md §4.
"""

from __future__ import annotations

import json as _json
from typing import Annotated

import typer

from mixpanel_data import session as session_ns
from mixpanel_data._internal.config_v3 import ConfigManager
from mixpanel_data.cli.utils import console, err_console, handle_errors
from mixpanel_data.exceptions import ConfigError


project_app = typer.Typer(
    name="project",
    help="Manage active Mixpanel project (042 redesign).",
    no_args_is_help=True,
)


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
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Bypass /me cache and refetch."),
    ] = False,
) -> None:
    """List projects accessible by the active account.

    With ``--remote``, fetches the project list from ``/me`` (cached
    24 hours; ``--refresh`` to bypass). Without it, just prints the
    currently active project from ``[active]`` for a quick summary.

    Args:
        ctx: Typer context.
        remote: Whether to fetch the full /me project list.
        refresh: Whether to bypass the cache.
    """
    if not remote:
        active = session_ns.show()
        if active.project is None:
            console.print("(no active project)")
            return
        console.print(active.project)
        return
    err_console.print(
        "[yellow]`mp project list --remote` is wired alongside the /me service in Phase 5+.[/yellow]"
    )
    raise typer.Exit(1)


@project_app.command("use")
@handle_errors
def use_project(
    ctx: typer.Context,
    project_id: Annotated[
        str, typer.Argument(help="Numeric Mixpanel project ID.")
    ],
) -> None:
    """Set the active project ID.

    Args:
        ctx: Typer context.
        project_id: Mixpanel project ID (numeric string).
    """
    session_ns.use(project=project_id)
    console.print(f"Active project: {project_id}")


@project_app.command("show")
@handle_errors
def show_project(ctx: typer.Context) -> None:
    """Show the currently active project.

    Args:
        ctx: Typer context.
    """
    active = session_ns.show()
    if active.project is None:
        console.print("(no active project)")
    else:
        console.print(active.project)
