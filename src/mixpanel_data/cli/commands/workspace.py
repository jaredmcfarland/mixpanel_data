"""``mp workspace`` Typer command group.

Replaces ``mp workspaces`` with the singular form. Reference:
contracts/cli-commands.md §5.
"""

from __future__ import annotations

import json as _json
from typing import Annotated

import typer

from mixpanel_data import session as session_ns
from mixpanel_data.cli.utils import console, handle_errors

workspace_app = typer.Typer(
    name="workspace",
    help="Manage active Mixpanel workspace.",
    no_args_is_help=True,
)


@workspace_app.command("list")
@handle_errors
def list_workspaces(
    ctx: typer.Context,
    project: Annotated[
        str | None,
        typer.Option(
            "--project", "-p", help="Project ID (defaults to active project)."
        ),
    ] = None,
    format: Annotated[  # noqa: A002
        str,
        typer.Option("--format", "-f", help="Output format: table | json | jsonl."),
    ] = "table",
) -> None:
    """List workspaces in the current (or specified) project via /me.

    Constructs a short-lived :class:`Workspace` against the resolved
    session, then pulls the workspace list from the cached ``/me``
    response (24h TTL) for ``--project`` (or the active project when
    ``--project`` is omitted).

    Args:
        ctx: Typer context.
        project: Project to query (defaults to the active project).
        format: Output format (``table`` / ``json`` / ``jsonl``).
    """
    from mixpanel_data.workspace import Workspace

    with Workspace(project=project) as ws:
        workspaces = ws.workspaces(project_id=project)
    if format == "json":
        console.print(
            _json.dumps(
                [
                    {"id": w.id, "name": w.name, "is_default": w.is_default}
                    for w in workspaces
                ],
                indent=2,
            )
        )
        return
    if format == "jsonl":
        for w in workspaces:
            console.print(
                _json.dumps({"id": w.id, "name": w.name, "is_default": w.is_default})
            )
        return
    if not workspaces:
        console.print("(no workspaces accessible via /me)")
        return
    lines = ["ID              NAME                              DEFAULT"]
    for w in workspaces:
        marker = "*" if w.is_default else ""
        name = (w.name or "")[:33]
        lines.append(f"{w.id:<15} {name:<33} {marker}")
    console.print("\n".join(lines))


@workspace_app.command("use")
@handle_errors
def use_workspace(
    ctx: typer.Context,
    workspace_id: Annotated[
        int, typer.Argument(help="Numeric workspace ID (positive int).")
    ],
) -> None:
    """Set the active workspace ID.

    Args:
        ctx: Typer context.
        workspace_id: Mixpanel workspace ID (positive int).
    """
    session_ns.use(workspace=workspace_id)
    console.print(f"Active workspace: {workspace_id}")


@workspace_app.command("show")
@handle_errors
def show_workspace(ctx: typer.Context) -> None:
    """Show the currently active workspace.

    When the active workspace is unset, prints
    ``(workspace will be auto-resolved on first use)``.

    Args:
        ctx: Typer context.
    """
    active = session_ns.show()
    if active.workspace is None:
        console.print("(workspace will be auto-resolved on first use)")
    else:
        console.print(str(active.workspace))
