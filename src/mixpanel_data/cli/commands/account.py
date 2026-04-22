"""``mp account`` Typer command group (042 redesign).

Replaces ``mp auth`` with a single source of truth for account CRUD,
switching, and probing across the three account types
(``service_account`` / ``oauth_browser`` / ``oauth_token``).

Reference: specs/042-auth-architecture-redesign/contracts/cli-commands.md §3.
"""

from __future__ import annotations

import json as _json
import os
from pathlib import Path
from typing import Annotated

import typer
from pydantic import SecretStr

from mixpanel_data import accounts as accounts_ns
from mixpanel_data.cli.utils import (
    ExitCode,
    console,
    err_console,
    handle_errors,
)
from mixpanel_data.exceptions import (
    AccountInUseError,
)
from mixpanel_data.types import AccountSummary

account_app = typer.Typer(
    name="account",
    help="Manage Mixpanel accounts (042 redesign).",
    no_args_is_help=True,
)


def _format_summary_table(summaries: list[AccountSummary]) -> str:
    """Render a compact table for ``mp account list`` (no Rich dependency).

    Args:
        summaries: List of AccountSummary records.

    Returns:
        Multi-line string ready for stdout.
    """
    if not summaries:
        return "(no accounts configured)"
    lines = ["NAME            TYPE              REGION  ACTIVE"]
    for s in summaries:
        active = "*" if s.is_active else ""
        lines.append(f"{s.name:<15} {s.type:<17} {s.region:<7} {active}")
    return "\n".join(lines)


@account_app.command("list")
@handle_errors
def list_accounts(
    ctx: typer.Context,
    format: Annotated[  # noqa: A002
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: table | json | jsonl.",
        ),
    ] = "table",
) -> None:
    """List all configured accounts.

    Shows the active account marker and any targets that reference each
    account (per FR-045, the first account auto-promotes to active).

    Args:
        ctx: Typer context.
        format: Output format.
    """
    summaries = accounts_ns.list()
    if format == "json":
        console.print(
            _json.dumps([s.model_dump(mode="json") for s in summaries], indent=2)
        )
    elif format == "jsonl":
        for s in summaries:
            console.print(_json.dumps(s.model_dump(mode="json")))
    else:
        console.print(_format_summary_table(summaries))


@account_app.command("add")
@handle_errors
def add_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Account name (alphanumeric, _, -)")],
    type: Annotated[  # noqa: A002
        str,
        typer.Option(
            "--type",
            help="One of: service_account | oauth_browser | oauth_token",
        ),
    ],
    region: Annotated[
        str,
        typer.Option("--region", help="Mixpanel region: us | eu | in"),
    ],
    username: Annotated[
        str | None,
        typer.Option("--username", help="Username (service_account)"),
    ] = None,
    secret_stdin: Annotated[
        bool,
        typer.Option(
            "--secret-stdin",
            help="Read secret from stdin (service_account; agent-friendly).",
        ),
    ] = False,
    token_env: Annotated[
        str | None,
        typer.Option(
            "--token-env",
            help="Env-var name holding the bearer (oauth_token).",
        ),
    ] = None,
) -> None:
    """Add a new account.

    For ``service_account``, ``--username`` is required and the secret is
    read from stdin (when ``--secret-stdin`` is set) or from ``MP_SECRET``.
    For ``oauth_token``, supply ``--token-env`` (recommended) or set
    ``MP_OAUTH_TOKEN`` and we'll capture it inline.

    Args:
        ctx: Typer context.
        name: Account name (alphanumeric, ``_``, ``-``).
        type: ``service_account`` | ``oauth_browser`` | ``oauth_token``.
        region: ``us`` | ``eu`` | ``in``.
        username: Required for ``service_account``.
        secret_stdin: Read secret from stdin instead of env.
        token_env: Env var holding the bearer for ``oauth_token``.
    """
    if type not in ("service_account", "oauth_browser", "oauth_token"):
        err_console.print(
            f"[red]Invalid --type: {type!r}[/red] (use service_account / oauth_browser / oauth_token)"
        )
        raise typer.Exit(ExitCode.INVALID_ARGS)
    if region not in ("us", "eu", "in"):
        err_console.print(f"[red]Invalid --region: {region!r}[/red] (use us / eu / in)")
        raise typer.Exit(ExitCode.INVALID_ARGS)

    secret: SecretStr | None = None
    token: SecretStr | None = None
    if type == "service_account":
        if not username:
            err_console.print("[red]--username is required for service_account[/red]")
            raise typer.Exit(ExitCode.INVALID_ARGS)
        if secret_stdin:
            secret_value = os.read(0, 4096).decode().rstrip("\n")
        else:
            env_secret = os.environ.get("MP_SECRET")
            if not env_secret:
                err_console.print(
                    "[red]Set MP_SECRET or use --secret-stdin to provide the secret.[/red]"
                )
                raise typer.Exit(ExitCode.INVALID_ARGS)
            secret_value = env_secret
        if not secret_value:
            err_console.print("[red]Secret is empty.[/red]")
            raise typer.Exit(ExitCode.INVALID_ARGS)
        secret = SecretStr(secret_value)
    elif type == "oauth_token":
        if token_env is None:
            env_value = os.environ.get("MP_OAUTH_TOKEN")
            if not env_value:
                err_console.print(
                    "[red]Provide --token-env NAME or set MP_OAUTH_TOKEN.[/red]"
                )
                raise typer.Exit(ExitCode.INVALID_ARGS)
            token = SecretStr(env_value)

    summary = accounts_ns.add(
        name,
        type=type,  # type: ignore[arg-type]
        region=region,  # type: ignore[arg-type]
        username=username,
        secret=secret,
        token=token,
        token_env=token_env,
    )
    console.print(f"Added account '{summary.name}' ({summary.type}, {summary.region})")
    if summary.is_active:
        console.print("(promoted to active)")


@account_app.command("use")
@handle_errors
def use_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Account name to make active.")],
) -> None:
    """Set the active account.

    Per FR-033, this updates ``[active].account`` only; project and
    workspace remain untouched.

    Args:
        ctx: Typer context.
        name: Account to activate.
    """
    accounts_ns.use(name)
    console.print(f"Active account: {name}")


@account_app.command("show")
@handle_errors
def show_account(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Account name (defaults to active)"),
    ] = None,
    format: Annotated[  # noqa: A002
        str, typer.Option("--format", "-f", help="Output: table | json")
    ] = "table",
) -> None:
    """Show one account's summary (active by default).

    Args:
        ctx: Typer context.
        name: Account name; ``None`` shows the active account.
        format: Output format.
    """
    summary = accounts_ns.show(name)
    if format == "json":
        console.print(_json.dumps(summary.model_dump(mode="json"), indent=2))
    else:
        console.print(_format_summary_table([summary]))


@account_app.command("remove")
@handle_errors
def remove_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Account name to remove.")],
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Remove even if referenced by targets (orphans them).",
        ),
    ] = False,
) -> None:
    """Remove an account.

    Without ``--force``, raises if any target references the account.

    Args:
        ctx: Typer context.
        name: Account to remove.
        force: When ``True``, remove and orphan any referencing targets.
    """
    try:
        orphans = accounts_ns.remove(name, force=force)
    except AccountInUseError as exc:
        err_console.print(f"[red]{exc.message}[/red]")
        raise typer.Exit(ExitCode.GENERAL_ERROR) from None
    console.print(f"Removed account '{name}'")
    if orphans:
        console.print(f"Orphaned targets: {', '.join(orphans)}")


@account_app.command("token")
@handle_errors
def token_command(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Account name (defaults to active)"),
    ] = None,
) -> None:
    """Print the current bearer token for an OAuth account.

    Returns ``N/A`` for service accounts (no bearer).

    Args:
        ctx: Typer context.
        name: Account name; ``None`` uses the active account.
    """
    result = accounts_ns.token(name)
    console.print(result if result is not None else "N/A")


@account_app.command("test")
@handle_errors
def test_account(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Account to test (defaults to active)"),
    ] = None,
) -> None:
    """Probe ``/me`` for the named (or active) account.

    Phase 4 returns a stubbed result; full ``/me`` integration arrives
    later in the rollout. Never raises — failure is captured in the
    result's ``error`` field.

    Args:
        ctx: Typer context.
        name: Account to test.
    """
    result = accounts_ns.test(name)
    console.print(_json.dumps(result.model_dump(mode="json"), indent=2))


@account_app.command("login")
def login_account(
    name: Annotated[str, typer.Argument(help="OAuth browser account name.")],
) -> None:
    """Run the OAuth browser flow (Phase 5+ wiring — currently a stub)."""
    err_console.print(
        "[yellow]`mp account login` is a stub in Phase 5; OAuth wiring lands later.[/yellow]"
    )
    raise typer.Exit(ExitCode.GENERAL_ERROR)


@account_app.command("logout")
@handle_errors
def logout_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Account name to log out.")],
) -> None:
    """Remove the on-disk OAuth tokens for an ``oauth_browser`` account.

    Args:
        ctx: Typer context.
        name: Account name.
    """
    accounts_ns.logout(name)
    console.print(f"Removed tokens for '{name}'")


@account_app.command("export-bridge")
def export_bridge_command(
    name: Annotated[
        str | None,
        typer.Option("--account", help="Account to export (defaults to active)"),
    ] = None,
    to: Annotated[
        Path,
        typer.Option("--to", help="Destination bridge file path."),
    ] = Path("./mixpanel_auth.json"),
) -> None:
    """Export the named account as a v2 bridge file (Phase 8 stub)."""
    err_console.print(
        "[yellow]`mp account export-bridge` is implemented in Phase 8 (US8).[/yellow]"
    )
    raise typer.Exit(ExitCode.GENERAL_ERROR)


@account_app.command("remove-bridge")
def remove_bridge_command(
    at: Annotated[
        Path | None,
        typer.Option("--at", help="Bridge file path (defaults to standard search)."),
    ] = None,
) -> None:
    """Remove the v2 bridge file (Phase 8 stub)."""
    err_console.print(
        "[yellow]`mp account remove-bridge` is implemented in Phase 8 (US8).[/yellow]"
    )
    raise typer.Exit(ExitCode.GENERAL_ERROR)
