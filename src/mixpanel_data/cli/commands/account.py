"""``mp account`` Typer command group.

Replaces ``mp auth`` with a single source of truth for account CRUD,
switching, and probing across the three account types
(``service_account`` / ``oauth_browser`` / ``oauth_token``).

Reference: specs/042-auth-architecture-redesign/contracts/cli-commands.md §3.
"""

from __future__ import annotations

import json as _json
import os
import sys
import typing
from pathlib import Path
from typing import Annotated

import typer
from pydantic import SecretStr

from mixpanel_data import accounts as accounts_ns
from mixpanel_data._internal.auth.account import AccountType as _AccountTypeLiteral
from mixpanel_data._internal.auth.account import Region
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

# Cap stdin reads at 64 KiB. Real service-account secrets are < 1 KiB
# and OAuth tokens are < 8 KiB; anything larger is almost certainly the
# wrong file being piped in (a key bundle, a JSON dump, etc.). Reject
# loudly rather than silently swallowing it.
_STDIN_SECRET_MAX_BYTES = 64 * 1024


def _read_secret_from_stdin() -> str:
    """Read a single secret value from stdin (up to 64 KiB).

    Replaces the prior 4096-byte ``os.read(0, 4096)`` which silently
    truncated long OAuth tokens / passwords piped from password
    managers. Reads ALL bytes, strips trailing whitespace (which
    ``pass``, ``cat``, etc. typically append), and rejects payloads
    larger than ``_STDIN_SECRET_MAX_BYTES`` instead of returning a
    quietly-corrupted prefix.

    Returns:
        The decoded secret string (whitespace-stripped).

    Raises:
        typer.Exit: When stdin is empty or exceeds the cap.
    """
    raw = sys.stdin.buffer.read(_STDIN_SECRET_MAX_BYTES + 1)
    if len(raw) > _STDIN_SECRET_MAX_BYTES:
        err_console.print(
            f"[red]stdin payload exceeds {_STDIN_SECRET_MAX_BYTES} bytes; "
            f"refusing to truncate. Pipe a single secret, not a key bundle.[/red]"
        )
        raise typer.Exit(ExitCode.INVALID_ARGS)
    value = raw.decode("utf-8", errors="strict").strip()
    if not value:
        err_console.print("[red]Secret is empty.[/red]")
        raise typer.Exit(ExitCode.INVALID_ARGS)
    return value


account_app = typer.Typer(
    name="account",
    help="Manage Mixpanel accounts.",
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
    from mixpanel_data.cli.formatters import emit_records

    emit_records(
        accounts_ns.list(),
        format=format,
        console=console,
        to_dict=lambda s: s.model_dump(mode="json"),
        table_renderer=lambda items: _format_summary_table(list(items)),
    )


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
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help=(
                "Numeric project ID (default_project). REQUIRED for "
                "service_account and oauth_token; optional for oauth_browser "
                "(backfilled by `mp account login`). Falls back to "
                "MP_PROJECT_ID when omitted."
            ),
        ),
    ] = None,
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

    For ``service_account``, ``--username`` is required, ``--project`` is
    required, and the secret is read from stdin (when ``--secret-stdin``
    is set) or from ``MP_SECRET``. For ``oauth_token``, ``--project`` is
    required; supply ``--token-env`` (recommended) or set
    ``MP_OAUTH_TOKEN`` and we'll capture it inline. For ``oauth_browser``,
    ``--project`` is optional and gets backfilled by ``mp account login``.

    Args:
        ctx: Typer context.
        name: Account name (alphanumeric, ``_``, ``-``).
        type: ``service_account`` | ``oauth_browser`` | ``oauth_token``.
        region: ``us`` | ``eu`` | ``in``.
        project: Numeric project ID (becomes the account's default_project).
        username: Required for ``service_account``.
        secret_stdin: Read secret from stdin instead of env.
        token_env: Env var holding the bearer for ``oauth_token``.
    """
    # Catch the two most common CLI typos (--type / --region) here so the
    # exit code is the semantic ``INVALID_ARGS`` (3) rather than the generic
    # ``GENERAL_ERROR`` (1) that ``@handle_errors`` maps the deeper Pydantic
    # ``ConfigError`` to. Both layers enforce the same set — the model is the
    # authoritative source of truth; this is a UX shim for the CLI surface.
    valid_types = typing.get_args(_AccountTypeLiteral)
    valid_regions = typing.get_args(Region)
    if type not in valid_types:
        err_console.print(
            f"[red]Invalid --type: {type!r}[/red] (use {' / '.join(valid_types)})"
        )
        raise typer.Exit(ExitCode.INVALID_ARGS)
    if region not in valid_regions:
        err_console.print(
            f"[red]Invalid --region: {region!r}[/red] (use {' / '.join(valid_regions)})"
        )
        raise typer.Exit(ExitCode.INVALID_ARGS)

    # Fall back to MP_PROJECT_ID env var when --project not provided.
    if project is None:
        project = os.environ.get("MP_PROJECT_ID") or None

    secret: SecretStr | None = None
    token: SecretStr | None = None
    if type == "service_account":
        if not username:
            err_console.print("[red]--username is required for service_account[/red]")
            raise typer.Exit(ExitCode.INVALID_ARGS)
        if not project:
            err_console.print(
                "[red]--project is required for service_account[/red] "
                "(or set MP_PROJECT_ID)"
            )
            raise typer.Exit(ExitCode.INVALID_ARGS)
        if secret_stdin:
            secret_value = _read_secret_from_stdin()
        else:
            env_secret = os.environ.get("MP_SECRET")
            if env_secret:
                secret_value = env_secret
            elif sys.stdin.isatty():
                # Per contracts/cli-commands.md §12 line 569, this is the
                # one command that may interactively prompt — only when
                # ``--secret-stdin`` is unset, ``MP_SECRET`` is unset, and
                # stdin is a TTY (otherwise we'd hang in CI / piped runs).
                # ``getpass.getpass`` writes the prompt to stderr and
                # reads from ``/dev/tty`` so the secret never echoes and
                # never appears in shell history.
                import getpass

                try:
                    secret_value = getpass.getpass("Service account secret: ")
                except (EOFError, OSError):
                    err_console.print(
                        "[red]Could not read secret interactively (no TTY available).[/red]"
                    )
                    raise typer.Exit(ExitCode.INVALID_ARGS) from None
            else:
                err_console.print(
                    "[red]Set MP_SECRET or use --secret-stdin to provide the secret.[/red]"
                )
                raise typer.Exit(ExitCode.INVALID_ARGS)
        if not secret_value:
            err_console.print("[red]Secret is empty.[/red]")
            raise typer.Exit(ExitCode.INVALID_ARGS)
        secret = SecretStr(secret_value)
    elif type == "oauth_token":
        if not project:
            err_console.print(
                "[red]--project is required for oauth_token[/red] "
                "(or set MP_PROJECT_ID)"
            )
            raise typer.Exit(ExitCode.INVALID_ARGS)
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
        default_project=project,
        username=username,
        secret=secret,
        token=token,
        token_env=token_env,
    )
    console.print(f"Added account '{summary.name}' ({summary.type}, {summary.region})")
    if summary.is_active:
        console.print("(promoted to active)")


@account_app.command("update")
@handle_errors
def update_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Account name to update.")],
    region: Annotated[
        str | None,
        typer.Option("--region", help="New region: us | eu | in"),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option(
            "--project",
            help="New default_project (numeric project ID).",
        ),
    ] = None,
    username: Annotated[
        str | None,
        typer.Option("--username", help="New username (service_account only)."),
    ] = None,
    secret_stdin: Annotated[
        bool,
        typer.Option(
            "--secret-stdin",
            help="Read new secret from stdin (service_account only).",
        ),
    ] = False,
    token_env: Annotated[
        str | None,
        typer.Option(
            "--token-env",
            help="New env-var name (oauth_token only).",
        ),
    ] = None,
) -> None:
    """Update fields on an existing account in place.

    Only supplied flags are changed. Type cannot be changed via this
    command (remove + re-add for that). Type-incompatible flags raise an
    error.

    Args:
        ctx: Typer context.
        name: Account name to update.
        region: New region.
        project: New default_project.
        username: New username (service_account only).
        secret_stdin: Read a new secret from stdin (service_account only).
        token_env: New env-var name (oauth_token only).
    """
    # See ``add_account`` — same UX shim for INVALID_ARGS exit code.
    if region is not None and region not in typing.get_args(Region):
        err_console.print(
            f"[red]Invalid --region: {region!r}[/red] "
            f"(use {' / '.join(typing.get_args(Region))})"
        )
        raise typer.Exit(ExitCode.INVALID_ARGS)

    secret: SecretStr | None = None
    if secret_stdin:
        secret = SecretStr(_read_secret_from_stdin())

    summary = accounts_ns.update(
        name,
        region=region,  # type: ignore[arg-type]
        default_project=project,
        username=username,
        secret=secret,
        token_env=token_env,
    )
    changed: list[str] = []
    if region is not None:
        changed.append(f"region={summary.region}")
    if project is not None:
        changed.append(f"default_project={project}")
    if username is not None:
        changed.append("username")
    if secret_stdin:
        changed.append("secret")
    if token_env is not None:
        changed.append(f"token_env={token_env}")
    summary_text = ", ".join(changed) if changed else "no changes"
    console.print(f"Updated account '{summary.name}' ({summary_text})")


@account_app.command("use")
@handle_errors
def use_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Account name to make active.")],
) -> None:
    """Set the active account, clearing any prior workspace pin.

    Project travels with the account via ``Account.default_project``, but
    workspace IDs are project-scoped — a workspace ID set under the prior
    account would resolve to a foreign workspace (or 404) under the new
    one, so it's dropped on every account swap.

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

    Never raises — failure is captured in the result's ``error`` field.

    Args:
        ctx: Typer context.
        name: Account to test.
    """
    result = accounts_ns.test(name)
    console.print(_json.dumps(result.model_dump(mode="json"), indent=2))


@account_app.command("login")
@handle_errors
def login_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="OAuth browser account name.")],
    no_browser: Annotated[
        bool,
        typer.Option(
            "--no-browser",
            help="Skip launching the system browser (headless / SSH).",
        ),
    ] = False,
) -> None:
    """Run the OAuth browser flow for an ``oauth_browser`` account.

    Drives the PKCE login dance, persists tokens to
    ``~/.mp/accounts/{name}/tokens.json``, and probes ``/me`` to backfill
    the account's ``default_project`` on first login. Prints a JSON
    :class:`OAuthLoginResult` so scripts and the plugin can consume the
    structured outcome.

    Args:
        ctx: Typer context.
        name: Account name (must be ``oauth_browser`` type).
        no_browser: Skip browser launch (manual URL copy).
    """
    result = accounts_ns.login(name, open_browser=not no_browser)
    console.print(_json.dumps(result.model_dump(mode="json"), indent=2))


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
@handle_errors
def export_bridge_command(
    name: Annotated[
        str | None,
        typer.Option("--account", help="Account to export (defaults to active)"),
    ] = None,
    to: Annotated[
        Path,
        typer.Option("--to", help="Destination bridge file path."),
    ] = Path("./mixpanel_auth.json"),
    project: Annotated[
        str | None,
        typer.Option("--project", help="Pin a project ID into the bridge."),
    ] = None,
    workspace: Annotated[
        int | None,
        typer.Option("--workspace", help="Pin a workspace ID into the bridge."),
    ] = None,
) -> None:
    """Export the named (or active) account as a v2 bridge file at ``--to``.

    For ``oauth_browser`` accounts, embeds the on-disk OAuth tokens so the
    consumer side (typically a Cowork VM) authenticates without re-running
    PKCE. Settings-side ``[settings].custom_header`` propagates into the
    bridge's ``headers`` block.
    """
    written = accounts_ns.export_bridge(
        to=to, account=name, project=project, workspace=workspace
    )
    console.print(f"Wrote bridge file to {written}")


@account_app.command("remove-bridge")
@handle_errors
def remove_bridge_command(
    at: Annotated[
        Path | None,
        typer.Option("--at", help="Bridge file path (defaults to standard search)."),
    ] = None,
) -> None:
    """Delete the bridge file at ``--at`` (or the resolved default path).

    Idempotent — no error if the bridge is already absent (exit 0 either way).
    """
    removed = accounts_ns.remove_bridge(at=at)
    console.print("Removed bridge file." if removed else "No bridge file to remove.")
