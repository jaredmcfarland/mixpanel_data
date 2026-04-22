"""``mp session`` Typer command.

Flat command (no subcommand by default — ``mp session`` prints the
active session state). With ``--bridge``, prints the bridge file source
(if any) instead.

Reference: contracts/cli-commands.md §7.
"""

from __future__ import annotations

import json as _json
from typing import Annotated

import typer

from mixpanel_data import session as session_ns
from mixpanel_data.cli.utils import console, handle_errors

session_app = typer.Typer(
    name="session",
    help="Show / update the active session.",
    invoke_without_command=True,
)


def _print_bridge_status(format: str) -> None:
    """Print bridge file source per § 7 of the CLI contract.

    Resolves the bridge via :func:`load_bridge` (honors ``MP_AUTH_FILE``
    + the default search paths) and prints either a one-line "no bridge
    found" message or a multi-line bridge summary (path, account,
    project/workspace pins, headers).

    Args:
        format: Output format; ``json`` emits the parsed bridge payload.
    """
    import os

    from mixpanel_data._internal.auth.bridge import (
        default_bridge_search_paths,
        load_bridge,
    )

    bridge = load_bridge()
    if bridge is None:
        if format == "json":
            console.print(_json.dumps({"bridge": None}, indent=2))
            return
        console.print("No bridge file found.")
        return

    candidates = (
        [os.environ["MP_AUTH_FILE"]] if os.environ.get("MP_AUTH_FILE") else []
    ) + [str(p) for p in default_bridge_search_paths()]
    path = next((p for p in candidates if os.path.exists(p)), None)

    if format == "json":
        console.print(
            _json.dumps(
                {
                    "bridge": {
                        "path": path,
                        "version": bridge.version,
                        "account": {
                            "name": bridge.account.name,
                            "type": bridge.account.type,
                            "region": bridge.account.region,
                        },
                        "project": bridge.project,
                        "workspace": bridge.workspace,
                        "headers": dict(bridge.headers),
                    }
                },
                indent=2,
            )
        )
        return
    parts = [
        f"Bridge:    {path}",
        f"Account:   {bridge.account.name} ({bridge.account.type}, "
        f"{bridge.account.region}, source: bridge)",
        f"Project:   {bridge.project or '(from config/env)'}",
        f"Workspace: {bridge.workspace if bridge.workspace is not None else '(auto)'}",
    ]
    if bridge.headers:
        parts.append("Headers:")
        for k, v in sorted(bridge.headers.items()):
            parts.append(f"  {k}: {v}")
    console.print("\n".join(parts))


@session_app.callback()
@handle_errors
def session_command(
    ctx: typer.Context,
    bridge: Annotated[
        bool,
        typer.Option("--bridge", help="Show bridge file source (Cowork)."),
    ] = False,
    format: Annotated[  # noqa: A002
        str,
        typer.Option("--format", "-f", help="Output format: text | json"),
    ] = "text",
) -> None:
    """Print the persisted ``[active]`` session, or bridge state with ``--bridge``.

    Args:
        ctx: Typer context.
        bridge: When True, show the bridge file source instead of ``[active]``.
        format: Output format.
    """
    if ctx.invoked_subcommand is not None:
        return  # let subcommands handle it (none currently)
    if bridge:
        _print_bridge_status(format)
        return
    active = session_ns.show()
    # Resolve the active account's default_project for display (project lives
    # on the account in v3, not in [active]).
    project_display = "(none)"
    if active.account is not None:
        from mixpanel_data._internal.config import ConfigManager
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
