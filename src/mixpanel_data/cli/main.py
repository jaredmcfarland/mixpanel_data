"""CLI entry point for mixpanel_data.

This module provides the `mp` command-line interface, the main entry
point for the CLI. It defines global options and registers command
groups.

Usage:
    mp [OPTIONS] COMMAND [ARGS]...

Examples:
    mp --help
    mp auth list
    mp --account staging query segmentation -e "Sign Up" --from 2024-01-01 --to 2024-01-31
"""

from __future__ import annotations

import signal
import sys
from typing import Annotated, Literal

import typer

import mixpanel_data
from mixpanel_data.cli.utils import ExitCode, err_console


def _get_rich_markup_mode() -> Literal["markdown", "rich"] | None:
    """Determine rich_markup_mode based on terminal detection.

    Returns "markdown" for interactive terminals to provide rich formatting,
    or None for non-TTY contexts (pipes, AI agents) to minimize token usage.

    Returns:
        "markdown" if stdout is a TTY, None otherwise.
    """
    import os

    # MP_PLAIN=1 forces plain output even in TTY
    if os.environ.get("MP_PLAIN", "").lower() in ("1", "true", "yes"):
        return None
    # Use rich formatting only in interactive terminals
    return "markdown" if sys.stdout.isatty() else None


# Create main application
app = typer.Typer(
    name="mp",
    help="Mixpanel data CLI - discover, query, and manage analytics data.",
    epilog="""Discover your schema, run live analytics, and manage Mixpanel entities.

Workflow: mp inspect events → mp query segmentation → mp dashboards list""",
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode=_get_rich_markup_mode(),
)


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        print(f"mp version {mixpanel_data.__version__}")
        raise typer.Exit()


def _handle_interrupt(_signum: int, _frame: object) -> None:
    """Handle SIGINT (Ctrl+C) gracefully."""
    err_console.print("\n[yellow]Interrupted[/yellow]")
    sys.exit(ExitCode.INTERRUPTED)


# Set up signal handler for Ctrl+C
signal.signal(signal.SIGINT, _handle_interrupt)


@app.callback()
def main(
    ctx: typer.Context,
    account: Annotated[
        str | None,
        typer.Option(
            "--account",
            "-a",
            help="Account name to use (overrides default).",
            envvar="MP_ACCOUNT",
        ),
    ] = None,
    credential: Annotated[
        str | None,
        typer.Option(
            "--credential",
            "-c",
            help="Credential name to use (v2 config).",
            envvar="MP_CREDENTIAL",
        ),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            "-p",
            help="Project ID to use (overrides active context).",
            envvar="MP_PROJECT_ID",
        ),
    ] = None,
    workspace_id: Annotated[
        int | None,
        typer.Option(
            "--workspace-id",
            envvar="MP_WORKSPACE_ID",
            help="Workspace ID for App API operations.",
        ),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress progress output.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable debug output.",
        ),
    ] = False,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Mixpanel data CLI - discover, query, and manage analytics data.

    Designed for AI coding agents. Discover schema, run live analytics,
    and manage Mixpanel entities programmatically.
    """
    ctx.ensure_object(dict)

    if account is not None and credential is not None:
        err_console.print(
            "[red]--account and --credential are mutually exclusive.[/red]"
        )
        raise typer.Exit(3)

    ctx.obj["account"] = account
    ctx.obj["credential"] = credential
    ctx.obj["project"] = project
    ctx.obj["workspace_id"] = workspace_id
    ctx.obj["quiet"] = quiet
    ctx.obj["verbose"] = verbose
    ctx.obj["workspace"] = None
    ctx.obj["config"] = None


# Import and register command groups
# These imports are done here to avoid circular imports
def _register_commands() -> None:
    """Register all command groups with the main app."""
    from mixpanel_data.cli.commands.alerts import alerts_app
    from mixpanel_data.cli.commands.annotations import annotations_app
    from mixpanel_data.cli.commands.auth import auth_app
    from mixpanel_data.cli.commands.cohorts import cohorts_app
    from mixpanel_data.cli.commands.context import context_app
    from mixpanel_data.cli.commands.custom_events import custom_events_app
    from mixpanel_data.cli.commands.custom_properties import custom_properties_app
    from mixpanel_data.cli.commands.dashboards import dashboards_app
    from mixpanel_data.cli.commands.drop_filters import drop_filters_app
    from mixpanel_data.cli.commands.experiments import experiments_app
    from mixpanel_data.cli.commands.flags import flags_app
    from mixpanel_data.cli.commands.inspect import inspect_app
    from mixpanel_data.cli.commands.lexicon import lexicon_app
    from mixpanel_data.cli.commands.lookup_tables import lookup_tables_app
    from mixpanel_data.cli.commands.projects import projects_app
    from mixpanel_data.cli.commands.query import query_app
    from mixpanel_data.cli.commands.reports import reports_app
    from mixpanel_data.cli.commands.schemas import schemas_app
    from mixpanel_data.cli.commands.webhooks import webhooks_app
    from mixpanel_data.cli.commands.workspaces_cmd import workspaces_app

    app.add_typer(auth_app, name="auth", help="Manage authentication and accounts.")
    app.add_typer(query_app, name="query", help="Query Mixpanel data.")
    app.add_typer(inspect_app, name="inspect", help="Inspect Mixpanel project schema.")
    app.add_typer(dashboards_app, name="dashboards", help="Manage Mixpanel dashboards.")
    app.add_typer(
        reports_app, name="reports", help="Manage Mixpanel reports (bookmarks)."
    )
    app.add_typer(cohorts_app, name="cohorts", help="Manage Mixpanel cohorts.")
    app.add_typer(
        experiments_app,
        name="experiments",
        help="Manage Mixpanel experiments.",
    )
    app.add_typer(flags_app, name="flags", help="Manage Mixpanel feature flags.")
    app.add_typer(alerts_app, name="alerts", help="Manage Mixpanel custom alerts.")
    app.add_typer(
        annotations_app, name="annotations", help="Manage timeline annotations."
    )
    app.add_typer(webhooks_app, name="webhooks", help="Manage project webhooks.")
    app.add_typer(lexicon_app, name="lexicon", help="Manage Lexicon data definitions.")
    app.add_typer(
        schemas_app, name="schemas", help="Manage schema registry definitions."
    )
    app.add_typer(drop_filters_app, name="drop-filters", help="Manage drop filters.")
    app.add_typer(
        custom_properties_app,
        name="custom-properties",
        help="Manage custom properties.",
    )
    app.add_typer(custom_events_app, name="custom-events", help="Manage custom events.")
    app.add_typer(
        lookup_tables_app,
        name="lookup-tables",
        help="Manage lookup tables.",
    )
    app.add_typer(
        projects_app,
        name="projects",
        help="Discover and switch Mixpanel projects.",
    )
    app.add_typer(
        workspaces_app,
        name="workspaces",
        help="Discover and switch Mixpanel workspaces.",
    )
    app.add_typer(
        context_app,
        name="context",
        help="View and switch the active session context.",
    )


# Register commands when module is imported
_register_commands()


if __name__ == "__main__":
    app()
