#!/usr/bin/env python3
"""Plugin auth manager — JSON wrapper around the v3 mixpanel_data namespaces.

Subcommands map 1:1 to ``mp account / project / workspace / target /
session / bridge`` per
``specs/042-auth-architecture-redesign/contracts/plugin-auth-manager.md``.
Every response carries ``schema_version: 1`` and a discriminated
``state`` (``ok`` | ``needs_account`` | ``needs_project`` | ``error``).
Errors emit JSON to stdout (exit 0) so the slash command can ``json.loads``
unconditionally.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from typing import Any

from mixpanel_data import Workspace, accounts, targets
from mixpanel_data import session as sess
from mixpanel_data._internal.auth.bridge import (
    default_bridge_search_paths,
    load_bridge,
)
from mixpanel_data._internal.config import ConfigManager

SCHEMA_VERSION = 1

# fmt: off
_ONBOARDING = [
    {"command": "mp account add personal --type oauth_browser --region us", "label": "OAuth (recommended)"},  # noqa: E501
    {"command": "mp account add team --type service_account --username '<service-account-username>' --region us", "label": "Service account"},  # noqa: E501
    {"command": "export MP_OAUTH_TOKEN=<bearer> MP_REGION=us MP_PROJECT_ID=<id>", "label": "Static bearer (CI)"},  # noqa: E501
]
_PROJECT_NEXT = [
    {"command": "mp project list", "label": "List accessible projects"},
    {"command": "mp project use <id>", "label": "Select a project"},
]
# fmt: on


def _emit(payload: dict[str, Any]) -> None:
    """Write ``payload`` as pretty-printed JSON to stdout."""
    print(json.dumps(payload, indent=2, default=str))


def _ok(**fields: Any) -> dict[str, Any]:
    """Return a baseline ``state="ok"`` response with ``fields`` merged in."""
    return {"schema_version": SCHEMA_VERSION, "state": "ok", **fields}


def _err(exc: BaseException, *, actionable: bool = False) -> dict[str, Any]:
    """Wrap ``exc`` as a contracted ``state="error"`` envelope (P3)."""
    err = {"code": type(exc).__name__, "message": str(exc), "actionable": actionable}
    return {"schema_version": SCHEMA_VERSION, "state": "error", "error": err}


def _account_record(account: Any) -> dict[str, Any]:
    """Render an Account → contract record (P5 — name/type/region required)."""
    return {"name": account.name, "type": account.type, "region": account.region}


def _has_env_auth() -> bool:
    """Return True when env vars alone can resolve a session."""
    sa = ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION")
    oauth = ("MP_OAUTH_TOKEN", "MP_PROJECT_ID", "MP_REGION")
    return all(os.environ.get(v) for v in sa) or all(os.environ.get(v) for v in oauth)


def _active_block(project_override: str | None = None) -> dict[str, Any]:
    """Read ``[active]`` and return the contract's ``active`` block (§ 4.3)."""
    cm = ConfigManager()
    active = cm.get_active()
    proj = project_override
    if proj is None and active.account:
        try:
            proj = cm.get_account(active.account).default_project
        except Exception:  # noqa: BLE001 — best-effort enrichment
            proj = None
    return {"account": active.account, "project": proj, "workspace": active.workspace}


def _do(fn: Callable[..., Any], *args: Any, project_override: str | None = None, **kwargs: Any) -> dict[str, Any]:  # noqa: E501  # fmt: skip
    """Run ``fn`` then emit the contract's ``active`` block per § 4.3."""
    fn(*args, **kwargs)
    return _ok(active=_active_block(project_override=project_override))


def _with_workspace(extractor: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
    """Open Workspace, run ``extractor(ws)``, close, and emit the result."""
    ws = Workspace()
    try:
        return extractor(ws)
    finally:
        ws.close()


def cmd_session(_args: argparse.Namespace) -> dict[str, Any]:
    """Resolve the persisted session into a discriminated state response."""
    cm = ConfigManager()
    active = cm.get_active()
    if active.account is None and not _has_env_auth():
        return {"schema_version": SCHEMA_VERSION, "state": "needs_account", "next": _ONBOARDING}  # noqa: E501  # fmt: skip
    if active.account is None:
        return _ok(account=None, project=None, workspace=None, source={"account": "env"})  # noqa: E501  # fmt: skip
    account = cm.get_account(active.account)
    if account.default_project is None and not os.environ.get("MP_PROJECT_ID"):
        return {"schema_version": SCHEMA_VERSION, "state": "needs_project", "account": _account_record(account), "next": _PROJECT_NEXT}  # noqa: E501  # fmt: skip
    project_id = account.default_project or os.environ["MP_PROJECT_ID"]
    workspace = {"id": active.workspace} if active.workspace is not None else None
    source = {"account": "config", "project": "config" if account.default_project else "env", "workspace": "config" if active.workspace is not None else "unset"}  # noqa: E501  # fmt: skip
    return _ok(account=_account_record(account), project={"id": project_id}, workspace=workspace, source=source)  # noqa: E501  # fmt: skip


def cmd_account_list(_args: argparse.Namespace) -> dict[str, Any]:
    """List configured accounts; empty config also includes onboarding hints."""
    items = [s.model_dump(mode="json") for s in accounts.list()]
    payload = _ok(items=items)
    if not items:
        payload["next"] = _ONBOARDING
    return payload


def cmd_account_add(args: argparse.Namespace) -> dict[str, Any]:
    """Add a new account from a JSON record on stdin (per § 4.1)."""
    if not args.from_stdin:
        raise SystemExit("auth_manager.py: account add requires --from-stdin (security: never pass secrets on the command line)")  # noqa: E501  # fmt: skip
    r = json.loads(sys.stdin.read())
    summary = accounts.add(r["name"], type=r["type"], region=r["region"], default_project=r.get("default_project"), username=r.get("username"), secret=r.get("secret"), token=r.get("token"), token_env=r.get("token_env"))  # noqa: E501  # fmt: skip
    return _ok(added=summary.model_dump(mode="json"))


def cmd_account_login(args: argparse.Namespace) -> dict[str, Any]:
    """Run the OAuth PKCE flow for an oauth_browser account (per § 4.4)."""
    result = accounts.login(args.name)
    user = result.user.model_dump(mode="json") if result.user else None
    expires = result.expires_at.isoformat() if result.expires_at else None
    return _ok(logged_in_as={"name": result.account_name, "user": user, "expires_at": expires})  # noqa: E501  # fmt: skip


def cmd_account_test(args: argparse.Namespace) -> dict[str, Any]:
    """Probe ``/me`` for an account; never raises — captures errors in result."""
    return _ok(result=accounts.test(args.name).model_dump(mode="json"))


def cmd_project_list(_args: argparse.Namespace) -> dict[str, Any]:
    """Enumerate accessible projects via the live ``/me`` API."""

    def _extract(ws: Any) -> dict[str, Any]:
        active_id = ws.session.project.id
        return _ok(items=[{"id": pid, "name": info.name, "organization_id": info.organization_id, "is_active": pid == active_id} for pid, info in ws.discover_projects()])  # noqa: E501  # fmt: skip

    return _with_workspace(_extract)


def cmd_workspace_list(_args: argparse.Namespace) -> dict[str, Any]:
    """List workspaces for the active project via ``/me``."""

    def _extract(ws: Any) -> dict[str, Any]:
        project = {"id": ws.session.project.id, "name": ws.session.project.name}
        return _ok(project=project, items=[{"id": info.id, "name": info.name, "is_default": info.is_default, "is_active": info.id == ws.session.workspace_id} for info in ws.discover_workspaces()])  # noqa: E501  # fmt: skip

    return _with_workspace(_extract)


def cmd_target_add(args: argparse.Namespace) -> dict[str, Any]:
    """Add a new target block referencing an existing account."""
    workspace = int(args.workspace) if args.workspace else None
    target = targets.add(args.name, account=args.account, project=args.project, workspace=workspace)  # noqa: E501  # fmt: skip
    return _ok(added=target.model_dump(mode="json"))


def cmd_bridge_status(_args: argparse.Namespace) -> dict[str, Any]:
    """Report Cowork bridge file presence + parsed metadata (per § 5)."""
    bridge = load_bridge()
    if bridge is None:
        return _ok(bridge=None)
    candidates = ([os.environ["MP_AUTH_FILE"]] if os.environ.get("MP_AUTH_FILE") else []) + [str(p) for p in default_bridge_search_paths()]  # noqa: E501  # fmt: skip
    path = next((p for p in candidates if os.path.exists(p)), None)
    return _ok(bridge={"path": path, "version": bridge.version, "account": _account_record(bridge.account), "project": bridge.project, "workspace": bridge.workspace, "headers": dict(bridge.headers)})  # noqa: E501  # fmt: skip


def _target_use(args: argparse.Namespace) -> dict[str, Any]:
    """Apply target then emit active block with the target's project pin."""
    target = targets.show(args.name)
    return _do(targets.use, args.name, project_override=target.project)


_Handler = Callable[[argparse.Namespace], dict[str, Any]]
_DISPATCH: dict[tuple[str, str | None], _Handler] = {
    ("session", None): cmd_session,
    ("account", "list"): cmd_account_list,
    ("account", "add"): cmd_account_add,
    ("account", "use"): lambda a: _do(accounts.use, a.name),
    ("account", "login"): cmd_account_login,
    ("account", "test"): cmd_account_test,
    ("project", "list"): cmd_project_list,
    ("project", "use"): lambda a: _do(
        sess.use, project=a.project_id, project_override=a.project_id
    ),  # noqa: E501  # fmt: skip
    ("workspace", "list"): cmd_workspace_list,
    ("workspace", "use"): lambda a: _do(sess.use, workspace=int(a.workspace_id)),
    ("target", "list"): lambda _a: _ok(
        items=[t.model_dump(mode="json") for t in targets.list()]
    ),  # noqa: E501  # fmt: skip
    ("target", "add"): cmd_target_add,
    ("target", "use"): _target_use,
    ("bridge", "status"): cmd_bridge_status,
}


def _build_parser() -> argparse.ArgumentParser:
    """Construct the two-level argparse tree (group → action)."""
    parser = argparse.ArgumentParser(prog="auth_manager.py")
    sub = parser.add_subparsers(dest="group", required=True)
    sub.add_parser("session")
    acct = sub.add_parser("account").add_subparsers(dest="action", required=True)
    acct.add_parser("list")
    acct.add_parser("add").add_argument("--from-stdin", action="store_true")
    for verb in ("use", "login", "test"):
        acct.add_parser(verb).add_argument("name")
    proj = sub.add_parser("project").add_subparsers(dest="action", required=True)
    proj.add_parser("list").add_argument("--remote", action="store_true")
    proj.add_parser("use").add_argument("project_id")
    wsp = sub.add_parser("workspace").add_subparsers(dest="action", required=True)
    wsp.add_parser("list")
    wsp.add_parser("use").add_argument("workspace_id")
    tgt = sub.add_parser("target").add_subparsers(dest="action", required=True)
    tgt.add_parser("list")
    tgt_add = tgt.add_parser("add")
    tgt_add.add_argument("name")
    tgt_add.add_argument("--account", required=True)
    tgt_add.add_argument("--project", required=True)
    tgt_add.add_argument("--workspace")
    tgt.add_parser("use").add_argument("name")
    sub.add_parser("bridge").add_subparsers(dest="action", required=True).add_parser("status")  # noqa: E501  # fmt: skip
    return parser


def main() -> None:
    """Parse args, dispatch, emit JSON; never let exceptions escape."""
    args = _build_parser().parse_args()
    handler = _DISPATCH.get((args.group, getattr(args, "action", None)))
    if handler is None:  # pragma: no cover — argparse already enforces choices
        _emit(_err(SystemExit(f"Unknown subcommand: {args.group}")))
        return
    try:
        _emit(handler(args))
    except Exception as exc:  # noqa: BLE001 — exit-0 contract
        _emit(_err(exc))


if __name__ == "__main__":
    main()
