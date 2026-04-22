"""``mp workspace`` Typer command group (042 redesign).

Replaces ``mp workspaces`` with the singular form. Reference:
contracts/cli-commands.md §5.
"""

from __future__ import annotations

from typing import Annotated

import typer

from mixpanel_data import session as session_ns
from mixpanel_data.cli.utils import console, err_console, handle_errors


workspace_app = typer.Typer(
    name="workspace",
    help="Manage active Mixpanel workspace (042 redesign).",
    no_args_is_help=True,
)


@workspace_app.command("list")
@handle_errors
def list_workspaces(
    ctx: typer.Context,
    project: Annotated[
        str | None,
        typer.Option(
            "--project", "-p", help="Project ID (defaults to active project)."
        ),
    ] = None,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Bypass cache.")
    ] = False,
) -> None:
    """List workspaces in the current project.

    Phase 5 stub — full /me wiring lands with the CLI integration tests.

    Args:
        ctx: Typer context.
        project: Project to query (defaults to active).
        refresh: Bypass cache.
    """
    err_console.print(
        "[yellow]`mp workspace list` is a Phase 5+ stub.[/yellow]"
    )
    raise typer.Exit(1)


@workspace_app.command("use")
@handle_errors
def use_workspace(
    ctx: typer.Context,
    workspace_id: Annotated[
        int, typer.Argument(help="Numeric workspace ID (positive int).")
    ],
) -> None:
    """Set the active workspace ID.

    Args:
        ctx: Typer context.
        workspace_id: Mixpanel workspace ID (positive int).
    """
    session_ns.use(workspace=workspace_id)
    console.print(f"Active workspace: {workspace_id}")


@workspace_app.command("show")
@handle_errors
def show_workspace(ctx: typer.Context) -> None:
    """Show the currently active workspace.

    When the active workspace is unset, prints
    ``(workspace will be auto-resolved on first use)``.

    Args:
        ctx: Typer context.
    """
    active = session_ns.show()
    if active.workspace is None:
        console.print("(workspace will be auto-resolved on first use)")
    else:
        console.print(str(active.workspace))
