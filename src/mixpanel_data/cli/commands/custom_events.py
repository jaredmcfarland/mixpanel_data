"""Custom event management commands.

This module provides commands for managing Mixpanel custom events:

- list: List all custom events
- update: Update a custom event definition
- delete: Delete a custom event
"""

from __future__ import annotations

from typing import Annotated, Any

import typer

from mixpanel_data.cli.options import FormatOption, JqOption
from mixpanel_data.cli.utils import (
    err_console,
    get_workspace,
    handle_errors,
    output_result,
    status_spinner,
)

custom_events_app = typer.Typer(
    name="custom-events",
    help="Manage custom events.",
    no_args_is_help=True,
)


@custom_events_app.command("list")
@handle_errors
def custom_events_list(
    ctx: typer.Context,
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """List all custom events for the current project.

    Retrieves all custom event definitions in the project.

    Args:
        ctx: Typer context with global options.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Fetching custom events..."):
        result = workspace.list_custom_events()
    output_result(
        ctx,
        [e.model_dump() for e in result],
        format=format,
        jq_filter=jq_filter,
    )


@custom_events_app.command("update")
@handle_errors
def custom_events_update(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Option("--name", help="Custom event name (required)."),
    ],
    hidden: Annotated[
        bool | None,
        typer.Option("--hidden/--no-hidden", help="Hide or show the event."),
    ] = None,
    dropped: Annotated[
        bool | None,
        typer.Option("--dropped/--no-dropped", help="Drop or undrop the event."),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option("--description", help="New event description."),
    ] = None,
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Update a custom event definition.

    Updates the specified custom event. Only provided fields are changed.

    Args:
        ctx: Typer context with global options.
        name: Custom event name.
        hidden: Hide or show the event.
        dropped: Drop or undrop the event.
        description: New event description.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    from mixpanel_data.types import UpdateEventDefinitionParams

    kwargs: dict[str, Any] = {}
    if hidden is not None:
        kwargs["hidden"] = hidden
    if dropped is not None:
        kwargs["dropped"] = dropped
    if description is not None:
        kwargs["description"] = description

    params = UpdateEventDefinitionParams(**kwargs)
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Updating custom event..."):
        result = workspace.update_custom_event(name, params)
    output_result(ctx, result.model_dump(), format=format, jq_filter=jq_filter)


@custom_events_app.command("delete")
@handle_errors
def custom_events_delete(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Option("--name", help="Custom event name (required)."),
    ],
) -> None:
    """Delete a custom event.

    Permanently deletes a custom event by name. This action cannot be undone.

    Args:
        ctx: Typer context with global options.
        name: Custom event name.
    """
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Deleting custom event..."):
        workspace.delete_custom_event(name)
    err_console.print(f"[green]Deleted custom event '{name}'.[/green]")
