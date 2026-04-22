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
        typer.Option(
            "--format", "-f", help="Output format: text | json"
        ),
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
    if format == "json":
        console.print(_json.dumps(active.model_dump(mode="json"), indent=2))
        return
    parts: list[str] = []
    parts.append(f"account:   {active.account or '(none)'}")
    parts.append(f"project:   {active.project or '(none)'}")
    parts.append(
        f"workspace: {active.workspace if active.workspace is not None else '(auto)'}"
    )
    console.print("\n".join(parts))
