"""Lexicon data-definition management commands.

This module provides commands for managing Mixpanel Lexicon data definitions:

Event definitions:
- events get: Get event definitions by name
- events update: Update a single event definition
- events delete: Delete an event definition
- events bulk-update: Bulk-update event definitions

Property definitions:
- properties get: Get property definitions by name
- properties update: Update a single property definition
- properties bulk-update: Bulk-update property definitions

Tags:
- tags list: List all Lexicon tags
- tags create: Create a new tag
- tags update: Update an existing tag
- tags delete: Delete a tag

Top-level:
- tracking-metadata: Get tracking metadata for an event
- event-history: Get change history for an event definition
- property-history: Get change history for a property definition
- export: Export Lexicon data definitions
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import typer

from mixpanel_data.cli.options import FormatOption, JqOption
from mixpanel_data.cli.utils import (
    ExitCode,
    err_console,
    get_workspace,
    handle_errors,
    output_result,
    status_spinner,
)

lexicon_app = typer.Typer(
    name="lexicon",
    help="Manage Lexicon data definitions.",
    no_args_is_help=True,
)

events_app = typer.Typer(
    name="events",
    help="Manage event definitions.",
    no_args_is_help=True,
)
lexicon_app.add_typer(events_app, name="events")

properties_app = typer.Typer(
    name="properties",
    help="Manage property definitions.",
    no_args_is_help=True,
)
lexicon_app.add_typer(properties_app, name="properties")

tags_app = typer.Typer(
    name="tags",
    help="Manage Lexicon tags.",
    no_args_is_help=True,
)
lexicon_app.add_typer(tags_app, name="tags")


# =============================================================================
# Event Definitions
# =============================================================================


@events_app.command("get")
@handle_errors
def events_get(
    ctx: typer.Context,
    names: Annotated[
        str,
        typer.Option("--names", help="Comma-separated event names."),
    ],
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Get event definitions by name.

    Retrieves metadata (description, tags, visibility, etc.) for the
    specified events from the Mixpanel Lexicon.

    Args:
        ctx: Typer context with global options.
        names: Comma-separated event names.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    workspace = get_workspace(ctx)
    name_list = [n.strip() for n in names.split(",")]
    with status_spinner(ctx, "Fetching event definitions..."):
        result = workspace.get_event_definitions(names=name_list)
    output_result(
        ctx,
        [r.model_dump() for r in result],
        format=format,
        jq_filter=jq_filter,
    )


@events_app.command("update")
@handle_errors
def events_update(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Option("--name", help="Event name to update."),
    ],
    hidden: Annotated[
        bool | None,
        typer.Option("--hidden/--no-hidden", help="Hide or unhide event."),
    ] = None,
    dropped: Annotated[
        bool | None,
        typer.Option("--dropped/--no-dropped", help="Drop or undrop event data."),
    ] = None,
    verified: Annotated[
        bool | None,
        typer.Option(
            "--verified/--no-verified", help="Mark event as verified or unverified."
        ),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option("--description", help="New event description."),
    ] = None,
    tags: Annotated[
        str | None,
        typer.Option("--tags", help="Comma-separated tag names to assign."),
    ] = None,
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Update an event definition (PATCH semantics).

    Only fields provided will be updated. Use boolean flags like
    ``--hidden/--no-hidden`` to toggle visibility.

    Args:
        ctx: Typer context with global options.
        name: Event name to update.
        hidden: Whether to hide the event.
        dropped: Whether to drop event data at ingestion.
        verified: Whether to mark the event as verified.
        description: New description text.
        tags: Comma-separated tag names to assign.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    from mixpanel_data.types import UpdateEventDefinitionParams

    kwargs: dict[str, Any] = {}
    if hidden is not None:
        kwargs["hidden"] = hidden
    if dropped is not None:
        kwargs["dropped"] = dropped
    if verified is not None:
        kwargs["verified"] = verified
    if description is not None:
        kwargs["description"] = description
    if tags is not None:
        kwargs["tags"] = [t.strip() for t in tags.split(",")]

    params = UpdateEventDefinitionParams(**kwargs)
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Updating event definition..."):
        result = workspace.update_event_definition(name, params)
    output_result(ctx, result.model_dump(), format=format, jq_filter=jq_filter)


@events_app.command("delete")
@handle_errors
def events_delete(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Option("--name", help="Event name to delete."),
    ],
) -> None:
    """Delete an event definition from Lexicon.

    Permanently removes the event definition. This action cannot be undone.

    Args:
        ctx: Typer context with global options.
        name: Event name to delete.
    """
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Deleting event definition..."):
        workspace.delete_event_definition(name)
    err_console.print(f"[green]Deleted event definition '{name}'.[/green]")


@events_app.command("bulk-update")
@handle_errors
def events_bulk_update(
    ctx: typer.Context,
    data: Annotated[
        str,
        typer.Option(
            "--data",
            help="Bulk update payload as JSON string (list of event updates).",
        ),
    ],
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Bulk-update event definitions.

    Accepts a JSON string with a list of event updates. Each entry
    should include ``name`` and any fields to change.

    Args:
        ctx: Typer context with global options.
        data: JSON string containing bulk update payload.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    from mixpanel_data.types import BulkUpdateEventsParams

    try:
        parsed: dict[str, Any] = json.loads(data)
    except json.JSONDecodeError as exc:
        err_console.print(f"[red]Invalid JSON for --data:[/red] {exc}")
        raise typer.Exit(code=ExitCode.INVALID_ARGS) from None

    params = BulkUpdateEventsParams(**parsed)
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Bulk-updating event definitions..."):
        result = workspace.bulk_update_event_definitions(params)
    output_result(
        ctx,
        [r.model_dump() for r in result],
        format=format,
        jq_filter=jq_filter,
    )


# =============================================================================
# Property Definitions
# =============================================================================


@properties_app.command("get")
@handle_errors
def properties_get(
    ctx: typer.Context,
    names: Annotated[
        str,
        typer.Option("--names", help="Comma-separated property names."),
    ],
    resource_type: Annotated[
        str | None,
        typer.Option(
            "--resource-type",
            help="Resource type filter (event, user, groupprofile).",
        ),
    ] = None,
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Get property definitions by name.

    Retrieves metadata (description, tags, visibility, etc.) for the
    specified properties from the Mixpanel Lexicon.

    Args:
        ctx: Typer context with global options.
        names: Comma-separated property names.
        resource_type: Optional resource type filter.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    workspace = get_workspace(ctx)
    name_list = [n.strip() for n in names.split(",")]
    kwargs: dict[str, Any] = {"names": name_list}
    if resource_type is not None:
        kwargs["resource_type"] = resource_type
    with status_spinner(ctx, "Fetching property definitions..."):
        result = workspace.get_property_definitions(**kwargs)
    output_result(
        ctx,
        [r.model_dump() for r in result],
        format=format,
        jq_filter=jq_filter,
    )


@properties_app.command("update")
@handle_errors
def properties_update(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Option("--name", help="Property name to update."),
    ],
    hidden: Annotated[
        bool | None,
        typer.Option("--hidden/--no-hidden", help="Hide or unhide property."),
    ] = None,
    dropped: Annotated[
        bool | None,
        typer.Option("--dropped/--no-dropped", help="Drop or undrop property data."),
    ] = None,
    sensitive: Annotated[
        bool | None,
        typer.Option(
            "--sensitive/--no-sensitive", help="Mark property as PII sensitive."
        ),
    ] = None,
    description: Annotated[
        str | None,
        typer.Option("--description", help="New property description."),
    ] = None,
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Update a property definition (PATCH semantics).

    Only fields provided will be updated. Use boolean flags like
    ``--hidden/--no-hidden`` to toggle visibility.

    Args:
        ctx: Typer context with global options.
        name: Property name to update.
        hidden: Whether to hide the property.
        dropped: Whether to drop property data.
        sensitive: Whether to mark the property as PII sensitive.
        description: New description text.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    from mixpanel_data.types import UpdatePropertyDefinitionParams

    kwargs: dict[str, Any] = {}
    if hidden is not None:
        kwargs["hidden"] = hidden
    if dropped is not None:
        kwargs["dropped"] = dropped
    if sensitive is not None:
        kwargs["sensitive"] = sensitive
    if description is not None:
        kwargs["description"] = description

    params = UpdatePropertyDefinitionParams(**kwargs)
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Updating property definition..."):
        result = workspace.update_property_definition(name, params)
    output_result(ctx, result.model_dump(), format=format, jq_filter=jq_filter)


@properties_app.command("bulk-update")
@handle_errors
def properties_bulk_update(
    ctx: typer.Context,
    data: Annotated[
        str,
        typer.Option(
            "--data",
            help="Bulk update payload as JSON string (list of property updates).",
        ),
    ],
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Bulk-update property definitions.

    Accepts a JSON string with a list of property updates. Each entry
    should include ``name`` and any fields to change.

    Args:
        ctx: Typer context with global options.
        data: JSON string containing bulk update payload.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    from mixpanel_data.types import BulkUpdatePropertiesParams

    try:
        parsed: dict[str, Any] = json.loads(data)
    except json.JSONDecodeError as exc:
        err_console.print(f"[red]Invalid JSON for --data:[/red] {exc}")
        raise typer.Exit(code=ExitCode.INVALID_ARGS) from None

    params = BulkUpdatePropertiesParams(**parsed)
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Bulk-updating property definitions..."):
        result = workspace.bulk_update_property_definitions(params)
    output_result(
        ctx,
        [r.model_dump() for r in result],
        format=format,
        jq_filter=jq_filter,
    )


# =============================================================================
# Tags
# =============================================================================


@tags_app.command("list")
@handle_errors
def tags_list(
    ctx: typer.Context,
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """List all Lexicon tags.

    Retrieves all tags available for categorizing event and property
    definitions.

    Args:
        ctx: Typer context with global options.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Fetching tags..."):
        result = workspace.list_lexicon_tags()
    output_result(
        ctx,
        result,
        format=format,
        jq_filter=jq_filter,
    )


@tags_app.command("create")
@handle_errors
def tags_create(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Option("--name", help="Tag name to create."),
    ],
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Create a new Lexicon tag.

    Creates a tag that can be assigned to event and property definitions.

    Args:
        ctx: Typer context with global options.
        name: Tag name to create.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    from mixpanel_data.types import CreateTagParams

    params = CreateTagParams(name=name)
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Creating tag..."):
        result = workspace.create_lexicon_tag(params)
    output_result(ctx, result.model_dump(), format=format, jq_filter=jq_filter)


@tags_app.command("update")
@handle_errors
def tags_update(
    ctx: typer.Context,
    id: Annotated[
        int,
        typer.Option("--id", help="Tag ID to update."),
    ],
    name: Annotated[
        str,
        typer.Option("--name", help="New tag name."),
    ],
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Update an existing Lexicon tag.

    Renames an existing tag by its ID.

    Args:
        ctx: Typer context with global options.
        id: Tag ID (integer).
        name: New tag name.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    from mixpanel_data.types import UpdateTagParams

    params = UpdateTagParams(name=name)
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Updating tag..."):
        result = workspace.update_lexicon_tag(id, params)
    output_result(ctx, result.model_dump(), format=format, jq_filter=jq_filter)


@tags_app.command("delete")
@handle_errors
def tags_delete(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Option("--name", help="Tag name to delete."),
    ],
) -> None:
    """Delete a Lexicon tag by name.

    Permanently removes the tag. This action cannot be undone.

    Args:
        ctx: Typer context with global options.
        name: Tag name to delete.
    """
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Deleting tag..."):
        workspace.delete_lexicon_tag(name)
    err_console.print(f"[green]Deleted tag '{name}'.[/green]")


# =============================================================================
# Top-level Commands
# =============================================================================


@lexicon_app.command("tracking-metadata")
@handle_errors
def tracking_metadata(
    ctx: typer.Context,
    event_name: Annotated[
        str,
        typer.Option("--event-name", help="Event name to get metadata for."),
    ],
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Get tracking metadata for an event.

    Retrieves information about how an event is being tracked
    (sources, SDKs, volume, etc.).

    Args:
        ctx: Typer context with global options.
        event_name: Event name.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Fetching tracking metadata..."):
        result = workspace.get_tracking_metadata(event_name)
    output_result(ctx, result, format=format, jq_filter=jq_filter)


@lexicon_app.command("event-history")
@handle_errors
def event_history(
    ctx: typer.Context,
    event_name: Annotated[
        str,
        typer.Option("--event-name", help="Event name to get history for."),
    ],
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Get change history for an event definition.

    Retrieves a chronological list of changes made to the event
    definition over time.

    Args:
        ctx: Typer context with global options.
        event_name: Event name.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Fetching event history..."):
        result = workspace.get_event_history(event_name)
    output_result(ctx, result, format=format, jq_filter=jq_filter)


@lexicon_app.command("property-history")
@handle_errors
def property_history(
    ctx: typer.Context,
    property_name: Annotated[
        str,
        typer.Option("--property-name", help="Property name to get history for."),
    ],
    entity_type: Annotated[
        str,
        typer.Option("--entity-type", help="Entity type (event, user, group)."),
    ],
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Get change history for a property definition.

    Retrieves a chronological list of changes made to the property
    definition over time.

    Args:
        ctx: Typer context with global options.
        property_name: Property name.
        entity_type: Entity type (event, user, group).
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    workspace = get_workspace(ctx)
    with status_spinner(ctx, "Fetching property history..."):
        result = workspace.get_property_history(property_name, entity_type)
    output_result(ctx, result, format=format, jq_filter=jq_filter)


@lexicon_app.command("export")
@handle_errors
def lexicon_export(
    ctx: typer.Context,
    types: Annotated[
        str | None,
        typer.Option(
            "--types",
            help="Comma-separated export types (events, event_properties, user_properties).",
        ),
    ] = None,
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """Export Lexicon data definitions.

    Exports event and property definitions, optionally filtered by type.

    Args:
        ctx: Typer context with global options.
        types: Comma-separated export types to include.
        format: Output format.
        jq_filter: Optional jq filter expression.
    """
    workspace = get_workspace(ctx)
    kwargs: dict[str, Any] = {}
    if types is not None:
        kwargs["export_types"] = [t.strip() for t in types.split(",")]
    with status_spinner(ctx, "Exporting Lexicon definitions..."):
        result = workspace.export_lexicon(**kwargs)
    output_result(ctx, result, format=format, jq_filter=jq_filter)
