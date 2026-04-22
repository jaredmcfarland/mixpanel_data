"""``mp session`` Typer command (042 redesign).

Replaces ``mp context`` with a flat command (no subcommand by default —
``mp session`` prints the active state; ``mp session --bridge`` shows
bridge status when wired in Phase 8).

Reference: contracts/cli-commands.md §7.
"""

from __future__ import annotations

import json as _json
from typing import Annotated

import typer

from mixpanel_data import session as session_ns
from mixpanel_data.cli.utils import console, err_console, handle_errors

session_app = typer.Typer(
    name="session",
    help="Show / update the active session (042 redesign).",
    invoke_without_command=True,
)


@session_app.callback()
@handle_errors
def session_command(
    ctx: typer.Context,
    bridge: Annotated[
        bool,
        typer.Option(
            "--bridge",
            help="Show bridge file status (Phase 8 wiring).",
        ),
    ] = False,
    format: Annotated[  # noqa: A002
        str,
        typer.Option("--format", "-f", help="Output format: text | json"),
    ] = "text",
) -> None:
    """Print the persisted ``[active]`` session.

    Args:
        ctx: Typer context.
        bridge: When True, show bridge file status (Phase 8).
        format: Output format.
    """
    if ctx.invoked_subcommand is not None:
        return  # let subcommands handle it (none currently)
    if bridge:
        err_console.print(
            "[yellow]`mp session --bridge` is implemented in Phase 8 (US8).[/yellow]"
        )
        raise typer.Exit(0)
    active = session_ns.show()
    # Resolve the active account's default_project for display (project lives
    # on the account in v3, not in [active]).
    project_display = "(none)"
    if active.account is not None:
        from mixpanel_data._internal.config_v3 import ConfigManager
        from mixpanel_data.exceptions import ConfigError

        try:
            account = ConfigManager().get_account(active.account)
            project_display = account.default_project or "(unset)"
        except ConfigError:
            project_display = "(unknown)"
    if format == "json":
        payload = active.model_dump(mode="json")
        payload["project"] = (
            project_display
            if project_display not in ("(none)", "(unset)", "(unknown)")
            else None
        )
        console.print(_json.dumps(payload, indent=2))
        return
    parts: list[str] = []
    parts.append(f"account:   {active.account or '(none)'}")
    parts.append(f"project:   {project_display}")
    parts.append(
        f"workspace: {active.workspace if active.workspace is not None else '(auto)'}"
    )
    console.print("\n".join(parts))
