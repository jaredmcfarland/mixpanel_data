"""``mp config`` Typer command group (042 redesign).

Provides ``mp config convert`` for one-shot legacy → v3 migration.
Phase 5 ships the stub; Phase 10 (US10) lands the actual converter.

Reference: contracts/cli-commands.md §8.
"""

from __future__ import annotations

from typing import Annotated

import typer

from mixpanel_data.cli.utils import err_console, handle_errors

config_app = typer.Typer(
    name="config",
    help="Convert legacy configs to the v3 schema (042 redesign).",
    no_args_is_help=True,
)


@config_app.command("convert")
@handle_errors
def convert_config(
    ctx: typer.Context,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show actions without writing any files.",
        ),
    ] = False,
) -> None:
    """Convert ``~/.mp/config.toml`` from v1/v2 → v3 (Phase 10 stub).

    Args:
        ctx: Typer context.
        dry_run: When True, log actions without modifying disk.
    """
    err_console.print(
        "[yellow]`mp config convert` is implemented in Phase 10 (US10).[/yellow]"
    )
    raise typer.Exit(1)
