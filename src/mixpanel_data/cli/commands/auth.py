"""Authentication and account management commands.

This module provides commands for managing Mixpanel accounts:
- list: List configured accounts
- add: Add a new account
- remove: Remove an account
- switch: Set default account
- show: Display account details
- test: Test account credentials
"""

from __future__ import annotations

import os
import sys
from typing import Annotated

import typer

from mixpanel_data._internal.config import AccountInfo, ConfigManager
from mixpanel_data.cli.options import FormatOption
from mixpanel_data.cli.utils import (
    err_console,
    get_config,
    handle_errors,
    output_result,
)

auth_app = typer.Typer(
    name="auth",
    help="Manage authentication and accounts.",
    no_args_is_help=True,
    rich_markup_mode="markdown",
)


@auth_app.command("list")
@handle_errors
def list_accounts(
    ctx: typer.Context,
    format: FormatOption = "json",
) -> None:
    """List all configured accounts.

    Shows account name, username, project ID, region, and default status.

    Examples:

        mp auth list
        mp auth list --format table
    """
    config = get_config(ctx)
    accounts = config.list_accounts()

    data = [
        {
            "name": acc.name,
            "username": acc.username,
            "project_id": acc.project_id,
            "region": acc.region,
            "is_default": acc.is_default,
        }
        for acc in accounts
    ]

    output_result(
        ctx,
        data,
        columns=["name", "username", "project_id", "region", "is_default"],
        format=format,
    )


@auth_app.command("add")
@handle_errors
def add_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Account name (identifier).")],
    username: Annotated[
        str | None,
        typer.Option("--username", "-u", help="Service account username."),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="Project ID."),
    ] = None,
    region: Annotated[
        str,
        typer.Option("--region", "-r", help="Region: us, eu, or in."),
    ] = "us",
    default: Annotated[
        bool,
        typer.Option("--default", "-d", help="Set as default account."),
    ] = False,
    interactive: Annotated[
        bool,
        typer.Option("--interactive", "-i", help="Prompt for all credentials."),
    ] = False,
    secret_stdin: Annotated[
        bool,
        typer.Option("--secret-stdin", help="Read secret from stdin."),
    ] = False,
    format: FormatOption = "json",
) -> None:
    """Add a new account to the configuration.

    The secret can be provided via:
    - Interactive prompt (default, hidden input)
    - MP_SECRET environment variable (for CI/CD)
    - --secret-stdin flag to read from stdin

    Examples:

        mp auth add production -u myuser -p 12345
        MP_SECRET=abc123 mp auth add production -u myuser -p 12345  # inline env var
        echo "$SECRET" | mp auth add production -u myuser -p 12345 --secret-stdin
        mp auth add staging -u myuser -p 12345 -r eu --default
    """
    secret: str | None = None

    # Handle interactive mode for all fields
    if interactive:
        if username is None:
            username = typer.prompt("Service account username")
        if project is None:
            project = typer.prompt("Project ID")
        # Secret is always prompted with hidden input in interactive mode
        secret = typer.prompt("Service account secret", hide_input=True)
    else:
        # Secret resolution priority:
        # 1. --secret-stdin: read from stdin
        # 2. MP_SECRET env var
        # 3. Interactive prompt (always hidden)
        if secret_stdin:
            # Read secret from stdin
            if sys.stdin.isatty():
                err_console.print(
                    "[red]Error:[/red] --secret-stdin requires piped input"
                )
                err_console.print("Example: echo $SECRET | mp auth add ...")
                raise typer.Exit(3)
            secret = sys.stdin.read().strip()
            if not secret:
                err_console.print("[red]Error:[/red] No secret provided via stdin")
                raise typer.Exit(3)
        elif os.environ.get("MP_SECRET"):
            secret = os.environ["MP_SECRET"]
        else:
            # Prompt for secret with hidden input (secure by default)
            secret = typer.prompt("Service account secret", hide_input=True)

    # Validate required fields
    if not username:
        err_console.print("[red]Error:[/red] --username is required")
        raise typer.Exit(3)
    if not secret:
        err_console.print("[red]Error:[/red] Secret is required")
        raise typer.Exit(3)
    if not project:
        err_console.print("[red]Error:[/red] --project is required")
        raise typer.Exit(3)
    if region not in ("us", "eu", "in"):
        err_console.print(
            f"[red]Error:[/red] Invalid region: {region}. Use us, eu, or in."
        )
        raise typer.Exit(3)

    config = get_config(ctx)
    config.add_account(
        name=name,
        username=username,
        secret=secret,
        project_id=project,
        region=region,
    )

    # Set as default if requested
    if default:
        config.set_default(name)

    output_result(ctx, {"added": name, "is_default": default}, format=format)


@auth_app.command("remove")
@handle_errors
def remove_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Account name to remove.")],
    force: Annotated[
        bool,
        typer.Option("--force", help="Skip confirmation prompt."),
    ] = False,
    format: FormatOption = "json",
) -> None:
    """Remove an account from the configuration.

    Deletes the account credentials from local config. Use --force
    to skip the confirmation prompt.

    Examples:

        mp auth remove staging
        mp auth remove old_account --force
    """
    if not force:
        confirm = typer.confirm(f"Remove account '{name}'?")
        if not confirm:
            err_console.print("[yellow]Cancelled[/yellow]")
            raise typer.Exit(2)

    config = get_config(ctx)
    config.remove_account(name)

    output_result(ctx, {"removed": name}, format=format)


@auth_app.command("switch")
@handle_errors
def switch_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Account name to set as default.")],
    format: FormatOption = "json",
) -> None:
    """Set an account as the default.

    The default account is used when --account is not specified.

    Examples:

        mp auth switch production
        mp auth switch staging
    """
    config = get_config(ctx)
    config.set_default(name)

    output_result(ctx, {"default": name}, format=format)


def _find_default_account(config: ConfigManager) -> AccountInfo | None:
    """Find the account marked as default in the configuration.

    Iterates through all configured accounts and returns the one
    with is_default=True.

    Args:
        config: ConfigManager instance to query for accounts.

    Returns:
        The default AccountInfo if one exists, None if no default is set.
    """
    accounts = config.list_accounts()
    for acc in accounts:
        if acc.is_default:
            return acc
    return None


@auth_app.command("show")
@handle_errors
def show_account(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Account name (default if omitted)."),
    ] = None,
    format: FormatOption = "json",
) -> None:
    """Show account details (secret is redacted).

    Displays configuration for the named account or default if omitted.

    Examples:

        mp auth show
        mp auth show production
        mp auth show --format table
    """
    config = get_config(ctx)

    account: AccountInfo
    if name is None:
        # Get default account
        default_account = _find_default_account(config)
        if default_account is None:
            err_console.print("[red]Error:[/red] No default account configured.")
            raise typer.Exit(1)
        account = default_account
    else:
        account = config.get_account(name)

    data = {
        "name": account.name,
        "username": account.username,
        "secret": "********",
        "project_id": account.project_id,
        "region": account.region,
        "is_default": account.is_default,
    }

    output_result(ctx, data, format=format)


@auth_app.command("test")
@handle_errors
def test_account(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Account name to test (default if omitted)."),
    ] = None,
    format: FormatOption = "json",
) -> None:
    """Test account credentials by pinging the API.

    Verifies that the credentials are valid and can access the project.

    Examples:

        mp auth test
        mp auth test production
    """
    from mixpanel_data.workspace import Workspace

    # Delegate to Workspace.test_credentials() which handles credential resolution
    # and API testing. Exceptions are handled by @handle_errors decorator.
    result = Workspace.test_credentials(name)
    output_result(ctx, result, format=format)
