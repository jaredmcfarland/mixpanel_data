"""Project discovery and switching commands.

This module provides commands for discovering accessible Mixpanel projects
and switching the active project context:

Discovery:
- list: List all accessible projects via /me API
- refresh: Force-refresh the /me cache and list projects

Context switching:
- switch: Set the active project (and optionally workspace)
- show: Show the current active project context

Aliases:
- alias add: Create a named project alias for quick switching
- alias remove: Remove a project alias
- alias list: List all project aliases
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

projects_app = typer.Typer(
    name="projects",
    help="Discover and switch Mixpanel projects.",
    no_args_is_help=True,
)


# =============================================================================
# Discovery
# =============================================================================


@projects_app.command("list")
@handle_errors
def projects_list(
    ctx: typer.Context,
    refresh: Annotated[
        bool,
        typer.Option(
            "--refresh",
            help="Force refresh the /me cache before listing.",
        ),
    ] = False,
    format: FormatOption = "json",
) -> None:
    """List all accessible projects via the /me API.

    Retrieves the authenticated user's accessible projects from the
    Mixpanel /me endpoint (cached for 24 hours). Use ``--refresh``
    to force a fresh API call.

    Args:
        ctx: Typer context with global options.
        refresh: If True, bypass the cache and fetch fresh data.
        format: Output format.
    """
    workspace = get_workspace(ctx)

    with status_spinner(ctx, "Fetching projects..."):
        if refresh:
            workspace.me(force_refresh=True)
        projects = workspace.discover_projects()

    data: list[dict[str, Any]] = [
        {
            "project_id": pid,
            "name": info.name,
            "organization_id": info.organization_id,
            "timezone": info.timezone,
            "has_workspaces": info.has_workspaces,
        }
        for pid, info in projects
    ]

    output_result(
        ctx,
        data,
        columns=["project_id", "name", "organization_id", "timezone", "has_workspaces"],
        format=format,
    )


@projects_app.command("refresh")
@handle_errors
def projects_refresh(
    ctx: typer.Context,
    format: FormatOption = "json",
) -> None:
    """Force-refresh the /me cache and list projects.

    Bypasses the 24-hour cache and fetches fresh data from the
    Mixpanel /me API.

    Args:
        ctx: Typer context with global options.
        format: Output format.
    """
    workspace = get_workspace(ctx)

    with status_spinner(ctx, "Refreshing /me cache..."):
        workspace.me(force_refresh=True)
        projects = workspace.discover_projects()

    data: list[dict[str, Any]] = [
        {
            "project_id": pid,
            "name": info.name,
            "organization_id": info.organization_id,
            "timezone": info.timezone,
            "has_workspaces": info.has_workspaces,
        }
        for pid, info in projects
    ]

    err_console.print(f"[green]Refreshed.[/green] Found {len(data)} projects.")
    output_result(
        ctx,
        data,
        columns=["project_id", "name", "organization_id", "timezone", "has_workspaces"],
        format=format,
    )


# =============================================================================
# Context Switching (Phase 5)
# =============================================================================


@projects_app.command("switch")
@handle_errors
def projects_switch(
    ctx: typer.Context,
    project_id: Annotated[
        str,
        typer.Argument(help="Project ID to switch to."),
    ],
    workspace_id: Annotated[
        int | None,
        typer.Option(
            "--workspace-id",
            "-w",
            help="Workspace ID within the project.",
        ),
    ] = None,
    format: FormatOption = "json",
) -> None:
    """Set the active project (and optionally workspace).

    Persists the selection to ``~/.mp/config.toml`` so subsequent
    commands use this project by default.

    Args:
        ctx: Typer context with global options.
        project_id: The project ID to switch to.
        workspace_id: Optional workspace ID to set.
        format: Output format.
    """
    config = get_config(ctx)
    config.set_active_project(project_id, workspace_id=workspace_id)

    result: dict[str, Any] = {
        "status": "ok",
        "active_project_id": project_id,
    }
    if workspace_id is not None:
        result["active_workspace_id"] = workspace_id

    err_console.print(f"[green]Switched to project {project_id}.[/green]")
    output_result(ctx, result, format=format)


@projects_app.command("show")
@handle_errors
def projects_show(
    ctx: typer.Context,
    format: FormatOption = "json",
) -> None:
    """Show the current active project context.

    Displays the active credential, project ID, and workspace ID
    from the configuration file.

    Args:
        ctx: Typer context with global options.
        format: Output format.
    """
    config = get_config(ctx)
    active = config.get_active_context()

    result: dict[str, Any] = {
        "credential": active.credential,
        "project_id": active.project_id,
        "workspace_id": active.workspace_id,
    }

    output_result(ctx, result, format=format)


# =============================================================================
# Project Aliases (Phase 10)
# =============================================================================

alias_app = typer.Typer(
    name="alias",
    help="Manage project aliases.",
    no_args_is_help=True,
)
projects_app.add_typer(alias_app)


@alias_app.command("add")
@handle_errors
def alias_add(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Argument(help="Alias name (e.g., 'ecom', 'ai-demo')."),
    ],
    project: Annotated[
        str,
        typer.Option("--project", "-p", help="Project ID to alias."),
    ],
    credential: Annotated[
        str | None,
        typer.Option(
            "--credential",
            "-c",
            help="Credential name to use with this alias.",
        ),
    ] = None,
    workspace: Annotated[
        int | None,
        typer.Option(
            "--workspace",
            "-w",
            help="Default workspace ID for this alias.",
        ),
    ] = None,
    format: FormatOption = "json",
) -> None:
    """Create a named project alias for quick switching.

    Aliases map a friendly name to a project ID with optional
    credential and workspace overrides. Use ``mp context switch``
    to activate an alias.

    Args:
        ctx: Typer context with global options.
        name: Alias name (e.g., 'ecom', 'ai-demo').
        project: Project ID to alias.
        credential: Credential name to use with this alias.
        workspace: Default workspace ID for this alias.
        format: Output format.
    """
    config = get_config(ctx)
    config.add_project_alias(
        name, project, credential=credential, workspace_id=workspace
    )

    result: dict[str, Any] = {
        "status": "ok",
        "alias": name,
        "project_id": project,
    }
    if credential is not None:
        result["credential"] = credential
    if workspace is not None:
        result["workspace_id"] = workspace

    err_console.print(f"[green]Added alias '{name}'.[/green]")
    output_result(ctx, result, format=format)


@alias_app.command("remove")
@handle_errors
def alias_remove(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Argument(help="Alias name to remove."),
    ],
    format: FormatOption = "json",
) -> None:
    """Remove a project alias.

    Deletes the named project alias from the configuration file.

    Args:
        ctx: Typer context with global options.
        name: Alias name to remove.
        format: Output format.
    """
    config = get_config(ctx)
    config.remove_project_alias(name)

    err_console.print(f"[green]Removed alias '{name}'.[/green]")
    output_result(ctx, {"status": "ok", "removed": name}, format=format)


@alias_app.command("list")
@handle_errors
def alias_list(
    ctx: typer.Context,
    format: FormatOption = "json",
) -> None:
    """List all project aliases.

    Shows configured project aliases with their project IDs,
    credential bindings, and workspace defaults.

    Args:
        ctx: Typer context with global options.
        format: Output format.
    """
    config = get_config(ctx)
    aliases = config.list_project_aliases()

    data: list[dict[str, Any]] = [
        {
            "name": a.name,
            "project_id": a.project_id,
            "credential": a.credential,
            "workspace_id": a.workspace_id,
        }
        for a in aliases
    ]

    output_result(
        ctx,
        data,
        columns=["name", "project_id", "credential", "workspace_id"],
        format=format,
    )
