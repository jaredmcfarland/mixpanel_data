"""Workspace discovery and switching commands.

This module provides commands for discovering accessible Mixpanel workspaces
and switching the active workspace context:

Discovery:
- list: List all accessible workspaces for a project via /me API

Context switching:
- switch: Set the active workspace within the current project
- show: Show the current workspace context
"""

from __future__ import annotations

from typing import Annotated, Any

import typer

from mixpanel_data.cli.options import FormatOption
from mixpanel_data.cli.utils import (
    err_console,
    get_config,
    get_workspace,
    handle_errors,
    output_result,
    status_spinner,
)

workspaces_app = typer.Typer(
    name="workspaces",
    help="Discover and switch Mixpanel workspaces.",
    no_args_is_help=True,
)


# =============================================================================
# Discovery
# =============================================================================


@workspaces_app.command("list")
@handle_errors
def workspaces_list(
    ctx: typer.Context,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            "-p",
            help="Project ID to list workspaces for (defaults to current project).",
        ),
    ] = None,
    format: FormatOption = "json",
) -> None:
    """List all accessible workspaces for a project via the /me API.

    Retrieves workspace information from the Mixpanel /me endpoint
    (cached for 24 hours). Defaults to the current project if
    ``--project`` is not specified.

    Args:
        ctx: Typer context with global options.
        project: Optional project ID to filter by.
        format: Output format.
    """
    workspace = get_workspace(ctx)

    with status_spinner(ctx, "Fetching workspaces..."):
        workspaces = workspace.discover_workspaces(project_id=project)

    data: list[dict[str, Any]] = [
        {
            "id": ws.id,
            "name": ws.name,
            "project_id": ws.project_id,
            "is_default": ws.is_default,
        }
        for ws in workspaces
    ]

    output_result(
        ctx,
        data,
        columns=["id", "name", "project_id", "is_default"],
        format=format,
    )


# =============================================================================
# Context Switching
# =============================================================================


@workspaces_app.command("switch")
@handle_errors
def workspaces_switch(
    ctx: typer.Context,
    workspace_id: Annotated[
        int,
        typer.Argument(help="Workspace ID to switch to."),
    ],
    format: FormatOption = "json",
) -> None:
    """Set the active workspace within the current project.

    Persists the workspace selection to ``~/.mp/config.toml`` so
    subsequent commands use this workspace by default.

    Args:
        ctx: Typer context with global options.
        workspace_id: The workspace ID to switch to.
        format: Output format.
    """
    config = get_config(ctx)
    active = config.get_active_context()

    project_id = active.project_id
    config.set_active_project(project_id or "", workspace_id=workspace_id)

    result: dict[str, Any] = {
        "status": "ok",
        "active_workspace_id": workspace_id,
    }
    if project_id is not None:
        result["active_project_id"] = project_id

    err_console.print(f"[green]Switched to workspace {workspace_id}.[/green]")
    output_result(ctx, result, format=format)


@workspaces_app.command("show")
@handle_errors
def workspaces_show(
    ctx: typer.Context,
    format: FormatOption = "json",
) -> None:
    """Show the current workspace context.

    Displays the active workspace ID and project ID from
    the configuration file.

    Args:
        ctx: Typer context with global options.
        format: Output format.
    """
    config = get_config(ctx)
    active = config.get_active_context()

    result: dict[str, Any] = {
        "project_id": active.project_id,
        "workspace_id": active.workspace_id,
    }

    output_result(ctx, result, format=format)
