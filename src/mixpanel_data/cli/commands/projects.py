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

import logging
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
from mixpanel_data.exceptions import ConfigError

logger = logging.getLogger(__name__)

projects_app = typer.Typer(
    name="projects",
    help="Discover and switch Mixpanel projects.",
    no_args_is_help=True,
)

_PROJECT_COLUMNS = [
    "project_id",
    "name",
    "organization_id",
    "timezone",
    "has_workspaces",
]


def _projects_to_dicts(
    projects: list[tuple[str, Any]],
) -> list[dict[str, Any]]:
    """Convert project tuples to serializable dicts.

    Args:
        projects: List of ``(project_id, MeProjectInfo)`` tuples.

    Returns:
        List of dicts with project fields.
    """
    return [
        {
            "project_id": pid,
            "name": info.name,
            "organization_id": info.organization_id,
            "timezone": info.timezone,
            "has_workspaces": info.has_workspaces,
        }
        for pid, info in projects
    ]


def _discover_projects_via_oauth() -> list[dict[str, Any]] | None:
    """Discover projects by calling /me directly with OAuth tokens.

    This is a fallback for when no project is configured yet (e.g.,
    after ``mp auth login`` with multiple projects). Scans OAuth
    storage for a valid token and calls ``/me`` directly.

    Returns:
        List of project dicts if discovery succeeds, None otherwise.
    """
    import os

    import httpx

    from mixpanel_data._internal.api_client import ENDPOINTS
    from mixpanel_data._internal.auth.storage import OAuthStorage
    from mixpanel_data._internal.auth_credential import VALID_REGIONS
    from mixpanel_data._internal.me import MeCache, MeProjectInfo, MeResponse

    storage = OAuthStorage()

    # Propagate custom headers from env or config (once, outside loop)
    custom_name = os.environ.get("MP_CUSTOM_HEADER_NAME")
    custom_value = os.environ.get("MP_CUSTOM_HEADER_VALUE")
    if not (custom_name and custom_value):
        from mixpanel_data._internal.config import ConfigManager

        ConfigManager().apply_config_custom_header()
        custom_name = os.environ.get("MP_CUSTOM_HEADER_NAME")
        custom_value = os.environ.get("MP_CUSTOM_HEADER_VALUE")

    # Find a valid token across all regions
    for region in VALID_REGIONS:
        tokens = storage.load_tokens(region)
        if tokens is None or tokens.is_expired():
            continue

        access_token = tokens.access_token.get_secret_value()
        app_base = ENDPOINTS[region]["app"]
        me_url = f"{app_base}/me"
        headers: dict[str, str] = {"Authorization": f"Bearer {access_token}"}
        if custom_name and custom_value:
            headers[custom_name] = custom_value

        try:
            with httpx.Client(timeout=60) as http:
                resp = http.get(me_url, headers=headers)
                if resp.status_code != 200:
                    continue

                me_raw = resp.json()
                me_data = me_raw.get("results", me_raw)

                # Cache for subsequent commands
                try:
                    me_response = MeResponse.model_validate(me_data)
                    MeCache().put(region, me_response)
                except (ValueError, OSError) as exc:
                    logger.debug("Failed to cache /me response: %s", exc)

                # Parse projects
                projects_raw: dict[str, Any] = me_data.get("projects", {})
                result: list[dict[str, Any]] = []
                for pid, pdata in sorted(
                    projects_raw.items(),
                    key=lambda x: (
                        x[1].get("name", "").lower() if isinstance(x[1], dict) else ""
                    ),
                ):
                    if isinstance(pdata, dict):
                        try:
                            info = MeProjectInfo.model_validate(pdata)
                            result.append(
                                {
                                    "project_id": pid,
                                    "name": info.name,
                                    "organization_id": info.organization_id,
                                    "timezone": info.timezone,
                                    "has_workspaces": info.has_workspaces,
                                }
                            )
                        except (ValueError, TypeError) as exc:
                            logger.debug("Failed to parse project %s: %s", pid, exc)
                            result.append(
                                {
                                    "project_id": pid,
                                    "name": pdata.get("name", ""),
                                    "organization_id": pdata.get(
                                        "organization_id", None
                                    ),
                                    "timezone": pdata.get("timezone", None),
                                    "has_workspaces": pdata.get("has_workspaces", None),
                                }
                            )
                return result
        except (httpx.HTTPError, OSError, ValueError, KeyError) as exc:
            logger.debug("OAuth /me fallback failed for region %s: %s", region, exc)
            continue

    return None


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

    Works even before a project is selected — falls back to direct
    OAuth token usage for discovery.

    Args:
        ctx: Typer context with global options.
        refresh: If True, bypass the cache and fetch fresh data.
        format: Output format.
    """
    try:
        workspace = get_workspace(ctx)

        with status_spinner(ctx, "Fetching projects..."):
            if refresh:
                workspace.me(force_refresh=True)
            projects = workspace.discover_projects()

        data = _projects_to_dicts(projects)
    except ConfigError as exc:
        # Re-raise subclass errors (e.g. AccountNotFoundError) for
        # proper handling by @handle_errors decorator
        from mixpanel_data.exceptions import AccountNotFoundError

        if isinstance(exc, AccountNotFoundError):
            raise

        # No project configured yet — fall back to direct OAuth /me call
        with status_spinner(ctx, "Discovering projects via OAuth..."):
            data_or_none = _discover_projects_via_oauth()

        if data_or_none is None:
            err_console.print(
                "[red]No valid credentials found.[/red] Run 'mp auth login' first."
            )
            raise typer.Exit(1) from None

        data = data_or_none

    output_result(ctx, data, columns=_PROJECT_COLUMNS, format=format)


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
    try:
        workspace = get_workspace(ctx)

        with status_spinner(ctx, "Refreshing /me cache..."):
            workspace.me(force_refresh=True)
            projects = workspace.discover_projects()

        data = _projects_to_dicts(projects)
    except ConfigError as exc:
        from mixpanel_data.exceptions import AccountNotFoundError

        if isinstance(exc, AccountNotFoundError):
            raise

        with status_spinner(ctx, "Discovering projects via OAuth..."):
            data_or_none = _discover_projects_via_oauth()

        if data_or_none is None:
            err_console.print(
                "[red]No valid credentials found.[/red] Run 'mp auth login' first."
            )
            raise typer.Exit(1) from None

        data = data_or_none

    err_console.print(f"[green]Refreshed.[/green] Found {len(data)} projects.")
    output_result(ctx, data, columns=_PROJECT_COLUMNS, format=format)


# =============================================================================
# Context Switching
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
# Project Aliases
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
