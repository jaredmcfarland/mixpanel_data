#!/usr/bin/env python3
"""Mixpanel authentication manager for the Claude Code plugin.

Provides JSON-formatted output for all auth operations, designed
to be called by the /mp-auth command and setup skill.

Usage:
    python auth_manager.py status                    # Full auth dashboard
    python auth_manager.py list                      # List configured accounts
    python auth_manager.py test [account_name]       # Test credentials
    python auth_manager.py switch <account_name>     # Switch default account
    python auth_manager.py remove <account_name>     # Remove an account
    python auth_manager.py oauth-login [--region R] [--project-id P]
    python auth_manager.py oauth-logout [--region R]
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


def _check_env_vars() -> dict[str, Any]:
    """Check which MP_* environment variables are set."""
    required = ["MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"]
    set_vars = [v for v in required if os.environ.get(v)]
    missing = [v for v in required if not os.environ.get(v)]
    return {
        "configured": len(missing) == 0,
        "partial": 0 < len(set_vars) < len(required),
        "set": set_vars,
        "missing": missing,
    }


def _get_accounts(cm: Any) -> list[dict[str, Any]]:
    """Get all configured accounts as dicts."""
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


def _resolve_active(cm: Any) -> dict[str, Any]:
    """Determine the active authentication method."""
    try:
        creds = cm.resolve_credentials()
        from mixpanel_data.auth import AuthMethod

        if all(
            os.environ.get(v)
            for v in ["MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"]
        ):
            method = "env_vars"
        elif creds.auth_method == AuthMethod.oauth:
            method = "oauth"
        else:
            method = "service_account"

        # Find the active account name
        active_account = None
        if method == "service_account":
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
    except Exception:
        return {
            "active_method": "none",
            "active_account": None,
            "active_project_id": None,
            "active_region": None,
        }


def _generate_suggestion(
    env: dict[str, Any],
    active: dict[str, Any],
) -> str:
    """Generate a human-readable suggestion based on auth state."""
    if active["active_method"] != "none":
        method_label = {
            "env_vars": "environment variables",
            "service_account": f"service account '{active['active_account']}'",
            "oauth": "OAuth",
        }.get(active["active_method"], active["active_method"])
        return f"Authenticated via {method_label} (project {active['active_project_id']}, {active['active_region']} region)."

    if env["partial"]:
        return f"Partial environment config — missing: {', '.join(env['missing'])}. Set all 4 variables or run /mp-auth add."

    return "No credentials configured. Run /mp-auth add (service account) or /mp-auth login (OAuth)."


# --- Subcommand handlers ---


def cmd_status(_args: argparse.Namespace) -> None:
    """Full auth status dashboard."""
    cm = _get_config_manager()
    env = _check_env_vars()
    accounts = _get_accounts(cm)
    oauth = _check_oauth()
    active = _resolve_active(cm)
    suggestion = _generate_suggestion(env, active)

    _json_out(
        {
            "operation": "status",
            "env_vars": env,
            "accounts": accounts,
            "oauth": oauth,
            **active,
            "suggestion": suggestion,
        }
    )


def cmd_list(_args: argparse.Namespace) -> None:
    """List configured accounts."""
    cm = _get_config_manager()
    accounts = _get_accounts(cm)
    _json_out({"operation": "list", "accounts": accounts, "count": len(accounts)})


def cmd_test(args: argparse.Namespace) -> None:
    """Test credentials."""
    try:
        from mixpanel_data import Workspace

        result = Workspace.test_credentials(account=args.account)
        _json_out({"operation": "test", **result})
    except Exception as e:
        _json_error(type(e).__name__, str(e))


def cmd_switch(args: argparse.Namespace) -> None:
    """Switch default account."""
    cm = _get_config_manager()
    accounts = _get_accounts(cm)
    previous = next((a["name"] for a in accounts if a["is_default"]), None)

    try:
        cm.set_default(args.name)
        _json_out(
            {
                "operation": "switch",
                "previous_default": previous,
                "new_default": args.name,
            }
        )
    except Exception as e:
        available = [a["name"] for a in accounts]
        _json_error(type(e).__name__, str(e), available_accounts=available)


def cmd_remove(args: argparse.Namespace) -> None:
    """Remove an account."""
    cm = _get_config_manager()
    try:
        cm.remove_account(args.name)
        remaining = _get_accounts(cm)
        new_default = next((a["name"] for a in remaining if a["is_default"]), None)
        _json_out(
            {
                "operation": "remove",
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
    subparsers.add_parser("list", help="List configured accounts")

    # test
    p_test = subparsers.add_parser("test", help="Test credentials")
    p_test.add_argument("account", nargs="?", default=None, help="Account name to test")

    # switch
    p_switch = subparsers.add_parser("switch", help="Switch default account")
    p_switch.add_argument("name", help="Account name to make default")

    # remove
    p_remove = subparsers.add_parser("remove", help="Remove an account")
    p_remove.add_argument("name", help="Account name to remove")

    # oauth-login
    p_login = subparsers.add_parser("oauth-login", help="OAuth browser login")
    p_login.add_argument("--region", default=None, help="Region (us, eu, in)")
    p_login.add_argument("--project-id", default=None, help="Project ID")

    # oauth-logout
    p_logout = subparsers.add_parser("oauth-logout", help="Remove OAuth tokens")
    p_logout.add_argument(
        "--region", default=None, help="Region to logout (all if omitted)"
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
        None: cmd_status,
    }

    handler = handlers.get(args.command, cmd_status)
    handler(args)


if __name__ == "__main__":
    main()
