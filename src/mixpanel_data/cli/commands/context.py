"""Context management commands.

This module provides commands for viewing and switching the active
session context (credential + project + workspace):

- show: Display the current active context
- switch: Switch to a named project alias
"""

from __future__ import annotations

from typing import Any

import typer

from mixpanel_data.cli.options import FormatOption
from mixpanel_data.cli.utils import (
    err_console,
    get_config,
    handle_errors,
    output_result,
)

context_app = typer.Typer(
    name="context",
    help="View and switch the active session context.",
    no_args_is_help=True,
)


@context_app.command("show")
@handle_errors
def show_context(
    ctx: typer.Context,
    format: FormatOption = "json",
) -> None:
    """Display the current active context.

    Shows the active credential, project ID, and workspace ID
    from the configuration file.

    Args:
        ctx: Typer context with global options.
        format: Output format.
    """
    config = get_config(ctx)
    active = config.get_active_context()

    data: dict[str, Any] = {
        "credential": active.credential,
        "project_id": active.project_id,
        "workspace_id": active.workspace_id,
    }

    output_result(ctx, data, format=format)


@context_app.command("switch")
@handle_errors
def switch_context(
    ctx: typer.Context,
    alias: str = typer.Argument(help="Project alias name to switch to."),
    format: FormatOption = "json",
) -> None:
    """Switch to a named project alias.

    Looks up the alias and sets the active credential, project ID,
    and workspace ID from the alias definition. All three active
    fields are updated in a single config write.

    If the alias has no workspace_id, the active workspace is cleared.

    Args:
        ctx: Typer context with global options.
        alias: Project alias name to switch to.
        format: Output format.
    """
    from mixpanel_data.exceptions import ConfigError

    config = get_config(ctx)
    aliases = config.list_project_aliases()

    match = next((a for a in aliases if a.name == alias), None)

    if match is None:
        available = [a.name for a in aliases]
        available_str = ", ".join(f"'{n}'" for n in available) if available else "none"
        raise ConfigError(
            f"Project alias '{alias}' not found. Available: {available_str}",
            details={"alias_name": alias, "available": available},
        )

    # Update active context from alias in a single write
    config.set_active_context(
        credential=match.credential,
        project_id=match.project_id,
        workspace_id=match.workspace_id,
    )

    result: dict[str, Any] = {
        "status": "ok",
        "alias": alias,
        "credential": match.credential,
        "project_id": match.project_id,
        "workspace_id": match.workspace_id,
    }

    err_console.print(f"[green]Switched to alias '{alias}'.[/green]")
    output_result(ctx, result, format=format)
