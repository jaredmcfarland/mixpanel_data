#!/usr/bin/env python3
"""Mixpanel authentication manager for the Claude Code plugin.

Provides JSON-formatted output for all auth operations, designed
to be called by the /mixpanel-data:auth command and setup skill.

Supports both v1 (account-based) and v2 (credential + project context)
config schemas. Detects the active schema version automatically.

Usage:
    python auth_manager.py status                    # Full auth dashboard
    python auth_manager.py list                      # List configured accounts/credentials
    python auth_manager.py test [account_name]       # Test credentials
    python auth_manager.py switch <account_name>     # Switch default account
    python auth_manager.py remove <account_name>     # Remove an account/credential
    python auth_manager.py oauth-login [--region R] [--project-id P]
    python auth_manager.py oauth-logout [--region R]
    python auth_manager.py migrate [--dry-run]       # Migrate v1 config to v2
    python auth_manager.py projects                  # List accessible projects
    python auth_manager.py context                   # Show active context
    python auth_manager.py switch-project <project_id> [--workspace-id W]
    python auth_manager.py cowork-status                # Check Cowork bridge file
"""

import argparse
import json
import os
import sys
from typing import Any


def _json_out(data: dict[str, Any]) -> None:
    """Print JSON to stdout."""
    print(json.dumps(data, indent=2, default=str))


def _json_error(error_type: str, message: str, **extra: Any) -> None:
    """Print error JSON to stdout and exit with code 1."""
    result: dict[str, Any] = {
        "error": True,
        "error_type": error_type,
        "message": message,
    }
    result.update(extra)
    _json_out(result)
    sys.exit(1)


def _get_config_manager() -> Any:
    """Import and return a ConfigManager instance."""
    from mixpanel_data.auth import ConfigManager

    return ConfigManager()


def _config_version(cm: Any) -> int:
    """Get config schema version (1 or 2)."""
    try:
        return cm.config_version()
    except Exception:
        return 1


def _env_status(names: list[str]) -> dict[str, Any]:
    """Return configured/partial/set/missing for a group of env vars."""
    present = [v for v in names if os.environ.get(v)]
    missing = [v for v in names if not os.environ.get(v)]
    return {
        "configured": len(missing) == 0,
        "partial": 0 < len(present) < len(names),
        "set": present,
        "missing": missing,
    }


def _check_env_vars() -> dict[str, Any]:
    """Check which MP_* environment variables are set.

    Top-level ``configured``/``partial``/``set``/``missing`` fields mirror
    the service-account block for backward compatibility with consumers of
    this JSON.
    """
    sa_block = _env_status(["MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"])
    oauth_block = _env_status(["MP_OAUTH_TOKEN", "MP_PROJECT_ID", "MP_REGION"])
    return {**sa_block, "service_account": sa_block, "oauth_token": oauth_block}


def _get_accounts(cm: Any) -> list[dict[str, Any]]:
    """Get all configured accounts as dicts (v1 config)."""
    try:
        accounts = cm.list_accounts()
        return [
            {
                "name": a.name,
                "username": a.username,
                "project_id": a.project_id,
                "region": a.region,
                "is_default": a.is_default,
            }
            for a in accounts
        ]
    except Exception:
        return []


def _get_credentials(cm: Any) -> list[dict[str, Any]]:
    """Get all configured credentials as dicts (v2 config)."""
    try:
        credentials = cm.list_credentials()
        return [
            {
                "name": c.name,
                "type": c.type,
                "region": c.region,
                "is_active": c.is_active,
            }
            for c in credentials
        ]
    except Exception:
        return []


def _get_active_context(cm: Any) -> dict[str, Any]:
    """Get the active context from v2 config."""
    try:
        ctx = cm.get_active_context()
        return {
            "credential": ctx.credential,
            "project_id": ctx.project_id,
            "workspace_id": ctx.workspace_id,
        }
    except Exception:
        return {
            "credential": None,
            "project_id": None,
            "workspace_id": None,
        }


def _get_project_aliases(cm: Any) -> list[dict[str, Any]]:
    """Get all project aliases from v2 config."""
    try:
        aliases = cm.list_project_aliases()
        return [
            {
                "name": a.name,
                "project_id": a.project_id,
                "credential": a.credential,
                "workspace_id": a.workspace_id,
            }
            for a in aliases
        ]
    except Exception:
        return []


def _check_oauth() -> list[dict[str, Any]]:
    """Check OAuth token status for all regions."""
    try:
        from mixpanel_data._internal.auth.storage import OAuthStorage

        storage = OAuthStorage()
        results = []
        for region in ["us", "eu", "in"]:
            tokens = storage.load_tokens(region)
            if tokens is not None:
                results.append(
                    {
                        "region": region,
                        "authenticated": True,
                        "expires_at": str(tokens.expires_at),
                        "is_expired": tokens.is_expired(),
                        "project_id": tokens.project_id,
                    }
                )
            else:
                results.append({"region": region, "authenticated": False})
        return results
    except Exception:
        return [{"region": r, "authenticated": False} for r in ["us", "eu", "in"]]


def _resolve_active(cm: Any, version: int) -> dict[str, Any]:
    """Determine the active authentication method.

    Returns one of: ``env_vars`` (the four service-account env vars),
    ``oauth_token_env`` (``MP_OAUTH_TOKEN`` env triple), ``oauth`` (PKCE
    storage or v2 OAuth credential), or ``service_account`` (stored
    service-account credential).

    On failure, returns ``active_method == "none"`` plus a
    ``resolution_error`` field carrying ``f"{type(e).__name__}: {e}"``
    so callers can surface the underlying reason instead of guessing.
    """
    try:
        creds = cm.resolve_credentials()
        from mixpanel_data.auth import AuthMethod

        sa_env_complete = all(
            os.environ.get(v)
            for v in ["MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"]
        )
        oauth_env_complete = all(
            os.environ.get(v) for v in ["MP_OAUTH_TOKEN", "MP_PROJECT_ID", "MP_REGION"]
        )

        if sa_env_complete:
            method = "env_vars"
        elif oauth_env_complete:
            method = "oauth_token_env"
        elif creds.auth_method == AuthMethod.oauth:
            method = "oauth"
        else:
            method = "service_account"

        # Find the active account/credential name
        active_account = None
        if version >= 2:
            ctx = _get_active_context(cm)
            active_account = ctx.get("credential")
        elif method == "service_account":
            for a in cm.list_accounts():
                if a.is_default:
                    active_account = a.name
                    break

        return {
            "active_method": method,
            "active_account": active_account,
            "active_project_id": creds.project_id,
            "active_region": creds.region,
        }
    except Exception as e:
        return {
            "active_method": "none",
            "active_account": None,
            "active_project_id": None,
            "active_region": None,
            "resolution_error": f"{type(e).__name__}: {e}",
        }


def _generate_suggestion(
    env: dict[str, Any],
    active: dict[str, Any],
    version: int,
) -> str:
    """Generate a human-readable suggestion based on auth state."""
    if active["active_method"] != "none":
        method_label = {
            "env_vars": "service-account environment variables",
            "oauth_token_env": "MP_OAUTH_TOKEN environment variables",
            "service_account": f"service account '{active['active_account']}'",
            "oauth": "OAuth",
        }.get(active["active_method"], active["active_method"])
        msg = f"Authenticated via {method_label} (project {active['active_project_id']}, {active['active_region']} region)."
        if version == 1:
            msg += " Config is v1 — run /mixpanel-data:auth migrate to upgrade to v2 for project switching."
        return msg

    sa_env = env.get("service_account", env)
    oauth_env = env.get("oauth_token", {})
    # Env vars complete but auth still resolved to "none" — the values are
    # syntactically present but produced a ConfigError (e.g., bad MP_REGION).
    if sa_env.get("configured") or oauth_env.get("configured"):
        err = active.get("resolution_error")
        if err:
            return f"Auth env vars are set but credentials could not be resolved: {err}"
        return "Auth env vars are set but credentials could not be resolved (likely an invalid value such as MP_REGION). Run /mixpanel-data:auth test for details."
    if sa_env.get("partial"):
        return f"Partial service-account env config — missing: {', '.join(sa_env['missing'])}. Set the rest, switch to MP_OAUTH_TOKEN + MP_PROJECT_ID + MP_REGION, or run /mixpanel-data:auth add."
    if oauth_env.get("partial"):
        return f"Partial OAuth-token env config — missing: {', '.join(oauth_env['missing'])}. Set the remaining variables or use /mixpanel-data:auth add / login."

    return "No credentials configured. Run /mixpanel-data:auth add (service account), /mixpanel-data:auth login (OAuth PKCE), or set MP_OAUTH_TOKEN + MP_PROJECT_ID + MP_REGION for bearer-token auth."


# --- Subcommand handlers ---


def cmd_status(_args: argparse.Namespace) -> None:
    """Full auth status dashboard."""
    cm = _get_config_manager()
    version = _config_version(cm)
    env = _check_env_vars()
    oauth = _check_oauth()
    active = _resolve_active(cm, version)
    suggestion = _generate_suggestion(env, active, version)

    result: dict[str, Any] = {
        "operation": "status",
        "config_version": version,
        "env_vars": env,
        "oauth": oauth,
        **active,
        "suggestion": suggestion,
    }

    if version >= 2:
        result["credentials"] = _get_credentials(cm)
        result["active_context"] = _get_active_context(cm)
        result["project_aliases"] = _get_project_aliases(cm)
    else:
        result["accounts"] = _get_accounts(cm)

    _json_out(result)


def cmd_list(_args: argparse.Namespace) -> None:
    """List configured accounts or credentials."""
    cm = _get_config_manager()
    version = _config_version(cm)

    if version >= 2:
        credentials = _get_credentials(cm)
        aliases = _get_project_aliases(cm)
        _json_out(
            {
                "operation": "list",
                "config_version": version,
                "credentials": credentials,
                "credential_count": len(credentials),
                "project_aliases": aliases,
                "alias_count": len(aliases),
            }
        )
    else:
        accounts = _get_accounts(cm)
        _json_out(
            {
                "operation": "list",
                "config_version": version,
                "accounts": accounts,
                "count": len(accounts),
            }
        )


def cmd_test(args: argparse.Namespace) -> None:
    """Test credentials."""
    try:
        from mixpanel_data import Workspace

        result = Workspace.test_credentials(account=args.account)
        _json_out({"operation": "test", **result})
    except Exception as e:
        _json_error(type(e).__name__, str(e))


def cmd_switch(args: argparse.Namespace) -> None:
    """Switch default account (v1) or active credential (v2)."""
    cm = _get_config_manager()
    version = _config_version(cm)

    if version >= 2:
        try:
            ctx = _get_active_context(cm)
            previous = ctx.get("credential")
            cm.set_active_context(credential=args.name)
            _json_out(
                {
                    "operation": "switch",
                    "config_version": version,
                    "previous_credential": previous,
                    "new_credential": args.name,
                }
            )
        except Exception as e:
            credentials = _get_credentials(cm)
            available = [c["name"] for c in credentials]
            _json_error(type(e).__name__, str(e), available_credentials=available)
    else:
        accounts = _get_accounts(cm)
        previous = next((a["name"] for a in accounts if a["is_default"]), None)
        try:
            cm.set_default(args.name)
            _json_out(
                {
                    "operation": "switch",
                    "config_version": version,
                    "previous_default": previous,
                    "new_default": args.name,
                }
            )
        except Exception as e:
            available = [a["name"] for a in accounts]
            _json_error(type(e).__name__, str(e), available_accounts=available)


def cmd_remove(args: argparse.Namespace) -> None:
    """Remove an account (v1) or credential (v2)."""
    cm = _get_config_manager()
    version = _config_version(cm)

    if version >= 2:
        try:
            orphaned = cm.remove_credential(args.name)
            remaining = _get_credentials(cm)
            active = next((c["name"] for c in remaining if c["is_active"]), None)
            result: dict[str, Any] = {
                "operation": "remove",
                "config_version": version,
                "removed": args.name,
                "remaining_count": len(remaining),
                "new_active": active,
            }
            if orphaned:
                result["orphaned_aliases"] = orphaned
            _json_out(result)
        except Exception as e:
            _json_error(type(e).__name__, str(e))
    else:
        try:
            cm.remove_account(args.name)
            remaining = _get_accounts(cm)
            new_default = next((a["name"] for a in remaining if a["is_default"]), None)
            _json_out(
                {
                    "operation": "remove",
                    "config_version": version,
                    "removed": args.name,
                    "remaining_count": len(remaining),
                    "new_default": new_default,
                }
            )
        except Exception as e:
            _json_error(type(e).__name__, str(e))


def cmd_oauth_login(args: argparse.Namespace) -> None:
    """Initiate OAuth PKCE browser login."""
    region = args.region or "us"
    project_id = args.project_id

    try:
        from mixpanel_data._internal.auth.flow import OAuthFlow

        print(f"Opening browser for OAuth login ({region} region)...", file=sys.stderr)
        flow = OAuthFlow(region=region)
        tokens = flow.login(project_id=project_id)
        _json_out(
            {
                "operation": "oauth-login",
                "success": True,
                "region": region,
                "expires_at": str(tokens.expires_at),
                "project_id": tokens.project_id,
                "scope": tokens.scope,
            }
        )
    except Exception as e:
        _json_error(type(e).__name__, str(e))


def cmd_oauth_logout(args: argparse.Namespace) -> None:
    """Remove OAuth tokens."""
    try:
        from mixpanel_data._internal.auth.storage import OAuthStorage

        storage = OAuthStorage()
        if args.region:
            storage.delete_tokens(args.region)
            _json_out({"operation": "oauth-logout", "removed": args.region})
        else:
            storage.delete_all()
            _json_out({"operation": "oauth-logout", "removed": "all"})
    except Exception as e:
        _json_error(type(e).__name__, str(e))


def cmd_migrate(args: argparse.Namespace) -> None:
    """Migrate v1 config to v2."""
    cm = _get_config_manager()
    version = _config_version(cm)

    if version >= 2:
        _json_out(
            {
                "operation": "migrate",
                "already_v2": True,
                "message": "Config is already v2. No migration needed.",
            }
        )
        return

    try:
        dry_run = args.dry_run
        result = cm.migrate_v1_to_v2(dry_run=dry_run)
        _json_out(
            {
                "operation": "migrate",
                "dry_run": dry_run,
                "credentials_created": result.credentials_created,
                "aliases_created": result.aliases_created,
                "backup_path": str(result.backup_path)
                if hasattr(result, "backup_path") and result.backup_path
                else None,
                "message": "Dry run complete — no changes written."
                if dry_run
                else "Migration complete. Config upgraded to v2.",
            }
        )
    except Exception as e:
        _json_error(type(e).__name__, str(e))


def cmd_projects(_args: argparse.Namespace) -> None:
    """List accessible projects via /me API."""
    try:
        from mixpanel_data import Workspace

        ws = Workspace()
        projects = ws.discover_projects()
        project_list = []
        for org_name, proj in projects:
            project_list.append(
                {
                    "organization": org_name,
                    "project_id": str(proj.id),
                    "name": proj.name,
                    "timezone": proj.timezone,
                }
            )
        ws.close()
        _json_out(
            {
                "operation": "projects",
                "projects": project_list,
                "count": len(project_list),
            }
        )
    except Exception as e:
        _json_error(type(e).__name__, str(e))


def cmd_context(_args: argparse.Namespace) -> None:
    """Show active context (v2 config)."""
    cm = _get_config_manager()
    version = _config_version(cm)

    if version < 2:
        active = _resolve_active(cm, version)
        _json_out(
            {
                "operation": "context",
                "config_version": version,
                **active,
                "suggestion": "Config is v1. Run /mixpanel-data:auth migrate to upgrade to v2 for project switching.",
            }
        )
        return

    ctx = _get_active_context(cm)
    active = _resolve_active(cm, version)
    _json_out(
        {
            "operation": "context",
            "config_version": version,
            **active,
            "active_context": ctx,
        }
    )


def cmd_switch_project(args: argparse.Namespace) -> None:
    """Switch active project (v2 config)."""
    cm = _get_config_manager()
    version = _config_version(cm)

    if version < 2:
        _json_error(
            "ConfigError",
            "Project switching requires v2 config. Run /mixpanel-data:auth migrate first.",
        )
        return

    try:
        workspace_id = int(args.workspace_id) if args.workspace_id else None
        cm.set_active_context(project_id=args.project_id, workspace_id=workspace_id)
        _json_out(
            {
                "operation": "switch-project",
                "project_id": args.project_id,
                "workspace_id": workspace_id,
            }
        )
    except Exception as e:
        _json_error(type(e).__name__, str(e))


def cmd_cowork_status(_args: argparse.Namespace) -> None:
    """Check Cowork bridge file status."""
    try:
        from mixpanel_data._internal.auth.bridge import (
            detect_cowork,
            find_bridge_file,
            load_bridge_file,
        )
    except ImportError:
        _json_error(
            "ImportError",
            "mixpanel_data is not installed or too old for Cowork support.",
        )
        return

    is_cowork = detect_cowork()
    path = find_bridge_file()
    bridge = load_bridge_file(path) if path else None

    result: dict[str, Any] = {
        "operation": "cowork-status",
        "is_cowork": is_cowork,
        "bridge_found": bridge is not None,
        "bridge_path": str(path) if path else None,
    }

    if bridge is not None:
        result["auth_method"] = bridge.auth_method
        result["region"] = bridge.region
        result["project_id"] = bridge.project_id
        result["workspace_id"] = bridge.workspace_id
        result["has_custom_header"] = bridge.custom_header is not None
        if bridge.oauth:
            result["token_expires_at"] = str(bridge.oauth.expires_at)
            result["token_expired"] = bridge.oauth.is_expired()
    else:
        result["suggestion"] = "Run 'mp auth cowork-setup' on your host machine."

    _json_out(result)


def main() -> None:
    """Parse arguments and dispatch to subcommand handler."""
    parser = argparse.ArgumentParser(
        description="Mixpanel authentication manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # status (default)
    subparsers.add_parser("status", help="Full auth status dashboard")

    # list
    subparsers.add_parser("list", help="List configured accounts/credentials")

    # test
    p_test = subparsers.add_parser("test", help="Test credentials")
    p_test.add_argument("account", nargs="?", default=None, help="Account name to test")

    # switch
    p_switch = subparsers.add_parser("switch", help="Switch default account/credential")
    p_switch.add_argument("name", help="Account or credential name")

    # remove
    p_remove = subparsers.add_parser("remove", help="Remove an account/credential")
    p_remove.add_argument("name", help="Account or credential name to remove")

    # oauth-login
    p_login = subparsers.add_parser("oauth-login", help="OAuth browser login")
    p_login.add_argument("--region", default=None, help="Region (us, eu, in)")
    p_login.add_argument("--project-id", default=None, help="Project ID")

    # oauth-logout
    p_logout = subparsers.add_parser("oauth-logout", help="Remove OAuth tokens")
    p_logout.add_argument(
        "--region", default=None, help="Region to logout (all if omitted)"
    )

    # migrate (v1 → v2)
    p_migrate = subparsers.add_parser("migrate", help="Migrate v1 config to v2")
    p_migrate.add_argument(
        "--dry-run", action="store_true", help="Preview without writing"
    )

    # projects (via /me API)
    subparsers.add_parser("projects", help="List accessible projects")

    # context (show active context)
    subparsers.add_parser("context", help="Show active context")

    # cowork-status
    subparsers.add_parser("cowork-status", help="Check Cowork bridge file status")

    # switch-project
    p_switch_proj = subparsers.add_parser(
        "switch-project", help="Switch active project"
    )
    p_switch_proj.add_argument("project_id", help="Project ID to switch to")
    p_switch_proj.add_argument(
        "--workspace-id", default=None, help="Workspace ID (optional)"
    )

    args = parser.parse_args()

    # Verify mixpanel_data is installed
    try:
        import mixpanel_data  # noqa: F401
    except ImportError:
        _json_error(
            "ImportError",
            "mixpanel_data is not installed. Run /mixpanel-data:setup first.",
        )

    # Route to handler (default to status)
    handlers = {
        "status": cmd_status,
        "list": cmd_list,
        "test": cmd_test,
        "switch": cmd_switch,
        "remove": cmd_remove,
        "oauth-login": cmd_oauth_login,
        "oauth-logout": cmd_oauth_logout,
        "migrate": cmd_migrate,
        "projects": cmd_projects,
        "context": cmd_context,
        "cowork-status": cmd_cowork_status,
        "switch-project": cmd_switch_project,
        None: cmd_status,
    }

    handler = handlers.get(args.command, cmd_status)
    handler(args)


if __name__ == "__main__":
    main()
