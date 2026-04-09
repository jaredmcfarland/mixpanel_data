"""Authentication and account management commands.

This module provides commands for managing Mixpanel accounts:
- list: List configured accounts
- add: Add a new account
- remove: Remove an account
- switch: Set default account
- show: Display account details
- test: Test account credentials
- login: OAuth 2.0 PKCE login
- logout: Remove OAuth tokens
- status: Show OAuth auth state
- token: Output raw access token
"""

from __future__ import annotations

import os
import sys
from typing import Annotated

import typer

from mixpanel_data._internal.auth.flow import OAuthFlow
from mixpanel_data._internal.auth.storage import OAuthStorage
from mixpanel_data._internal.config import AccountInfo, ConfigManager
from mixpanel_data.cli.options import FormatOption
from mixpanel_data.cli.utils import (
    err_console,
    get_config,
    handle_errors,
    output_result,
)
from mixpanel_data.exceptions import AccountNotFoundError, ConfigError

auth_app = typer.Typer(
    name="auth",
    help="Manage authentication and accounts.",
    no_args_is_help=True,
    rich_markup_mode="markdown",
)


@auth_app.command("list")
@handle_errors
def list_accounts(
    ctx: typer.Context,
    format: FormatOption = "json",
) -> None:
    """List configured credentials (v2) or accounts (v1).

    Shows credentials with name, type, region, and active status
    when using v2 config. Falls back to showing legacy accounts
    (name, username, project_id, region, is_default) for v1 config.

    Examples:

        mp auth list
        mp auth list --format table
    """
    config = get_config(ctx)

    if config.config_version() >= 2:
        # v2 path: show credentials
        creds = config.list_credentials()
        data = [
            {
                "name": c.name,
                "type": c.type,
                "region": c.region,
                "is_active": c.is_active,
            }
            for c in creds
        ]
        output_result(
            ctx,
            data,
            columns=["name", "type", "region", "is_active"],
            format=format,
        )
    else:
        # v1 path: show legacy accounts
        accounts = config.list_accounts()
        data = [
            {
                "name": acc.name,
                "username": acc.username,
                "project_id": acc.project_id,
                "region": acc.region,
                "is_default": acc.is_default,
            }
            for acc in accounts
        ]
        output_result(
            ctx,
            data,
            columns=["name", "username", "project_id", "region", "is_default"],
            format=format,
        )


@auth_app.command("add")
@handle_errors
def add_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Account name (identifier).")],
    username: Annotated[
        str | None,
        typer.Option("--username", "-u", help="Service account username."),
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="Project ID."),
    ] = None,
    region: Annotated[
        str,
        typer.Option("--region", "-r", help="Region: us, eu, or in."),
    ] = "us",
    default: Annotated[
        bool,
        typer.Option("--default", "-d", help="Set as default account."),
    ] = False,
    interactive: Annotated[
        bool,
        typer.Option("--interactive", "-i", help="Prompt for all credentials."),
    ] = False,
    secret_stdin: Annotated[
        bool,
        typer.Option("--secret-stdin", help="Read secret from stdin."),
    ] = False,
    format: FormatOption = "json",
) -> None:
    """Add a new account to the configuration.

    The secret can be provided via:
    - Interactive prompt (default, hidden input)
    - MP_SECRET environment variable (for CI/CD)
    - --secret-stdin flag to read from stdin

    Examples:

        mp auth add production -u myuser -p 12345
        MP_SECRET=abc123 mp auth add production -u myuser -p 12345  # inline env var
        echo "$SECRET" | mp auth add production -u myuser -p 12345 --secret-stdin
        mp auth add staging -u myuser -p 12345 -r eu --default
    """
    secret: str | None = None

    # Handle interactive mode for all fields
    if interactive:
        if username is None:
            username = typer.prompt("Service account username")
        if project is None:
            project = typer.prompt("Project ID")
        # Secret is always prompted with hidden input in interactive mode
        secret = typer.prompt("Service account secret", hide_input=True)
    else:
        # Secret resolution priority:
        # 1. --secret-stdin: read from stdin
        # 2. MP_SECRET env var
        # 3. Interactive prompt (always hidden)
        if secret_stdin:
            # Read secret from stdin
            if sys.stdin.isatty():
                err_console.print(
                    "[red]Error:[/red] --secret-stdin requires piped input"
                )
                err_console.print("Example: echo $SECRET | mp auth add ...")
                raise typer.Exit(3)
            secret = sys.stdin.read().strip()
            if not secret:
                err_console.print("[red]Error:[/red] No secret provided via stdin")
                raise typer.Exit(3)
        elif os.environ.get("MP_SECRET"):
            secret = os.environ["MP_SECRET"]
        else:
            # Prompt for secret with hidden input (secure by default)
            secret = typer.prompt("Service account secret", hide_input=True)

    # Validate required fields
    if not username:
        err_console.print("[red]Error:[/red] --username is required")
        raise typer.Exit(3)
    if not secret:
        err_console.print("[red]Error:[/red] Secret is required")
        raise typer.Exit(3)
    if not project:
        err_console.print("[red]Error:[/red] --project is required")
        raise typer.Exit(3)
    if region not in ("us", "eu", "in"):
        err_console.print(
            f"[red]Error:[/red] Invalid region: {region}. Use us, eu, or in."
        )
        raise typer.Exit(3)

    config = get_config(ctx)
    config.add_account(
        name=name,
        username=username,
        secret=secret,
        project_id=project,
        region=region,
    )

    # Set as default if requested
    if default:
        config.set_default(name)

    output_result(ctx, {"added": name, "is_default": default}, format=format)


@auth_app.command("remove")
@handle_errors
def remove_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Account name to remove.")],
    force: Annotated[
        bool,
        typer.Option("--force", help="Skip confirmation prompt."),
    ] = False,
    format: FormatOption = "json",
) -> None:
    """Remove an account from the configuration.

    Deletes the account credentials from local config. Use --force
    to skip the confirmation prompt.

    Examples:

        mp auth remove staging
        mp auth remove old_account --force
    """
    if not force:
        confirm = typer.confirm(f"Remove account '{name}'?")
        if not confirm:
            err_console.print("[yellow]Cancelled[/yellow]")
            raise typer.Exit(2)

    config = get_config(ctx)
    config.remove_account(name)

    output_result(ctx, {"removed": name}, format=format)


@auth_app.command("switch")
@handle_errors
def switch_account(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Account name to set as default.")],
    format: FormatOption = "json",
) -> None:
    """Set an account as the default.

    The default account is used when --account is not specified.

    Examples:

        mp auth switch production
        mp auth switch staging
    """
    config = get_config(ctx)
    config.set_default(name)

    output_result(ctx, {"default": name}, format=format)


def _find_default_account(config: ConfigManager) -> AccountInfo | None:
    """Find the account marked as default in the configuration.

    Iterates through all configured accounts and returns the one
    with is_default=True.

    Args:
        config: ConfigManager instance to query for accounts.

    Returns:
        The default AccountInfo if one exists, None if no default is set.
    """
    accounts = config.list_accounts()
    for acc in accounts:
        if acc.is_default:
            return acc
    return None


@auth_app.command("show")
@handle_errors
def show_account(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Account name (default if omitted)."),
    ] = None,
    format: FormatOption = "json",
) -> None:
    """Show account details (secret is redacted).

    Displays configuration for the named account or default if omitted.

    Examples:

        mp auth show
        mp auth show production
        mp auth show --format table
    """
    config = get_config(ctx)

    account: AccountInfo
    if name is None:
        # Get default account
        default_account = _find_default_account(config)
        if default_account is None:
            err_console.print("[red]Error:[/red] No default account configured.")
            raise typer.Exit(1)
        account = default_account
    else:
        account = config.get_account(name)

    data = {
        "name": account.name,
        "username": account.username,
        "secret": "********",
        "project_id": account.project_id,
        "region": account.region,
        "is_default": account.is_default,
    }

    output_result(ctx, data, format=format)


@auth_app.command("test")
@handle_errors
def test_account(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Account name to test (default if omitted)."),
    ] = None,
    format: FormatOption = "json",
) -> None:
    """Test account credentials by pinging the API.

    Verifies that the credentials are valid and can access the project.

    Examples:

        mp auth test
        mp auth test production
    """
    from mixpanel_data.workspace import Workspace

    # Delegate to Workspace.test_credentials() which handles credential resolution
    # and API testing. Exceptions are handled by @handle_errors decorator.
    result = Workspace.test_credentials(name)
    output_result(ctx, result, format=format)


def _resolve_region(ctx: typer.Context, region: str | None) -> str:
    """Resolve the region from option, config default account, or fallback.

    Priority order:
    1. Explicit ``--region`` option
    2. Default account's region from config
    3. ``"us"`` fallback

    Args:
        ctx: Typer context with global options in obj dict.
        region: Explicit region from ``--region`` option, or None.

    Returns:
        Resolved region string (``us``, ``eu``, or ``in``).
    """
    if region is not None:
        return region
    try:
        config = get_config(ctx)
        default_account = _find_default_account(config)
        if default_account is not None:
            return default_account.region
    except (ConfigError, AccountNotFoundError) as exc:
        err_console.print(
            f"[red]Error:[/red] Could not determine region from config: {exc}. "
            "Use --region to specify explicitly."
        )
        raise typer.Exit(code=1) from None
    except OSError as exc:
        err_console.print(
            f"[red]Error:[/red] Could not read config file: {exc}. "
            "Use --region to specify explicitly."
        )
        raise typer.Exit(code=1) from None
    return "us"


@auth_app.command("login")
@handle_errors
def login(
    ctx: typer.Context,
    region: Annotated[
        str | None,
        typer.Option("--region", help="Region (us, eu, in)."),
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option(
            "--project-id", help="Mixpanel project ID to associate with tokens."
        ),
    ] = None,
    format: FormatOption = "json",
) -> None:
    """Log in via OAuth 2.0 PKCE flow.

    Opens a browser for Mixpanel authorization. After approving,
    tokens are saved locally for subsequent API calls. Invalidates
    the /me cache for the region after successful login.

    Examples:

        mp auth login
        mp auth login --region eu
        mp auth login --project-id 12345
    """
    resolved_region = _resolve_region(ctx, region)
    flow = OAuthFlow(region=resolved_region)
    tokens = flow.login(project_id=project_id)

    # Invalidate /me cache after successful login so stale user/project
    # data doesn't persist from a previous session.
    from mixpanel_data._internal.me import MeCache

    MeCache().invalidate(resolved_region)

    output_result(
        ctx,
        {
            "status": "login_success",
            "region": resolved_region,
            "scope": tokens.scope,
            "expires_at": tokens.expires_at.isoformat(),
        },
        format=format,
    )


@auth_app.command("logout")
@handle_errors
def logout(
    ctx: typer.Context,
    region: Annotated[
        str | None,
        typer.Option("--region", help="Region (us, eu, in)."),
    ] = None,
    format: FormatOption = "json",
) -> None:
    """Remove stored OAuth tokens.

    With ``--region``, removes tokens for that region only. Without
    ``--region``, removes all stored tokens and client info.

    Examples:

        mp auth logout
        mp auth logout --region us
    """
    storage = OAuthStorage()
    if region is not None:
        storage.delete_tokens(region)
        output_result(
            ctx,
            {"status": "logout_success", "region": region, "removed": "tokens"},
            format=format,
        )
    else:
        storage.delete_all()
        output_result(
            ctx,
            {"status": "logout_success", "region": "all", "removed": "all"},
            format=format,
        )


@auth_app.command("status")
@handle_errors
def auth_status(
    ctx: typer.Context,
    format: FormatOption = "json",
) -> None:
    """Show authentication state including active context.

    Displays the active credential/project/workspace context and
    OAuth token status across all regions (us, eu, in).

    Examples:

        mp auth status
        mp auth status --format table
    """
    storage = OAuthStorage()
    regions: list[str] = ["us", "eu", "in"]

    # Build active context section (gracefully handle missing config)
    active_context: dict[str, object] = {
        "config_version": None,
        "credential": None,
        "project_id": None,
        "workspace_id": None,
    }
    try:
        config = get_config(ctx)
        version = config.config_version()
        active_context["config_version"] = version
        if version >= 2:
            active = config.get_active_context()
            active_context["credential"] = active.credential
            active_context["project_id"] = active.project_id
            active_context["workspace_id"] = active.workspace_id
    except ConfigError as exc:
        err_console.print(f"[yellow]Warning:[/yellow] Could not read config: {exc}")
    except OSError as exc:
        err_console.print(
            f"[yellow]Warning:[/yellow] Could not read config file: {exc}"
        )

    # Build OAuth token statuses
    oauth_statuses: list[dict[str, object]] = []
    for rgn in regions:
        tokens = storage.load_tokens(region=rgn)
        if tokens is not None:
            is_expired = tokens.is_expired()
            oauth_statuses.append(
                {
                    "region": rgn,
                    "authenticated": True,
                    "token_type": tokens.token_type,
                    "scope": tokens.scope,
                    "expires_at": tokens.expires_at.isoformat(),
                    "is_expired": is_expired,
                    "project_id": tokens.project_id,
                }
            )
        else:
            oauth_statuses.append(
                {
                    "region": rgn,
                    "authenticated": False,
                    "token_type": None,
                    "scope": None,
                    "expires_at": None,
                    "is_expired": None,
                    "project_id": None,
                }
            )

    result: dict[str, object] = {
        "active_context": active_context,
        "oauth": oauth_statuses,
    }

    output_result(ctx, result, format=format)


@auth_app.command("token")
@handle_errors
def auth_token(
    ctx: typer.Context,
    region: Annotated[
        str | None,
        typer.Option("--region", help="Region (us, eu, in)."),
    ] = None,
) -> None:
    """Output a valid OAuth access token to stdout.

    Loads the stored token, refreshes if expired, and prints the
    raw access token string. Suitable for piping to other tools.

    Exit code 2 if no valid token is available.

    Examples:

        mp auth token
        mp auth token --region eu
        curl -H "Authorization: Bearer $(mp auth token)" https://...
    """
    resolved_region = _resolve_region(ctx, region)
    flow = OAuthFlow(region=resolved_region)
    token = flow.get_valid_token(region=resolved_region)
    print(token)


@auth_app.command("migrate")
@handle_errors
def migrate_config(
    ctx: typer.Context,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview migration without writing."),
    ] = False,
    format: FormatOption = "json",
) -> None:
    """Migrate v1 config to v2 format.

    Converts the legacy account-based config (v1) to the new
    credential + project alias format (v2). Accounts with identical
    service account credentials are deduplicated into a single
    credential entry. Each account becomes a project alias.

    A backup of the original config is created at
    ``~/.mp/config.toml.v1.bak``.

    Use ``--dry-run`` to preview what would change without writing.

    Examples:

        mp auth migrate
        mp auth migrate --dry-run
        mp auth migrate --format table
    """
    config = get_config(ctx)
    result = config.migrate_v1_to_v2(dry_run=dry_run)

    data: dict[str, object] = {
        "credentials_created": result.credentials_created,
        "aliases_created": result.aliases_created,
        "active_credential": result.active_credential,
        "active_project_id": result.active_project_id,
        "dry_run": dry_run,
    }
    if result.backup_path is not None:
        data["backup_path"] = str(result.backup_path)

    output_result(ctx, data, format=format)


@auth_app.command("cowork-setup")
@handle_errors
def cowork_setup(
    ctx: typer.Context,
    credential: Annotated[
        str | None,
        typer.Option("--credential", help="Named credential to export."),
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option("--project-id", help="Mixpanel project ID."),
    ] = None,
    workspace_id: Annotated[
        int | None,
        typer.Option("--workspace-id", help="Workspace ID for App API scoping."),
    ] = None,
    dir: Annotated[
        str | None,
        typer.Option(
            "--dir",
            help="Write bridge file to this directory (e.g. your Cowork workspace folder).",
        ),
    ] = None,
    format: FormatOption = "json",
) -> None:
    """Export credentials to a bridge file for Claude Cowork VMs.

    Resolves the current credentials and writes them to a bridge file
    so that ``mixpanel_data`` running inside a Cowork VM can authenticate
    without browser access.

    By default writes to ``~/.claude/mixpanel/auth.json``. Use ``--dir``
    to write to your Cowork workspace folder instead (recommended, since
    the workspace folder is always mounted into Cowork).

    For OAuth credentials, includes the refresh token so the VM can
    silently renew expired access tokens.

    For service accounts, includes username and secret.

    Custom headers from env vars or config ``[settings]`` are also
    included if present.

    After writing, tests the credentials with a lightweight API call.

    Examples:

        mp auth cowork-setup
        mp auth cowork-setup --credential demo-sa --project-id 12345
        mp auth cowork-setup --workspace-id 3448413
    """
    from pathlib import Path as _Path

    from pydantic import SecretStr

    from mixpanel_data._internal.auth.bridge import (
        _FLAT_BRIDGE_FILENAME,
        AuthBridgeFile,
        BridgeCustomHeader,
        BridgeOAuth,
        BridgeServiceAccount,
        _default_bridge_path,
        write_bridge_file,
    )
    from mixpanel_data._internal.auth.storage import OAuthStorage
    from mixpanel_data._internal.config import AuthMethod as _AuthMethod

    config = get_config(ctx)
    if dir is not None:
        bridge_path = _Path(dir) / _FLAT_BRIDGE_FILENAME
    else:
        bridge_path = _default_bridge_path()

    # Resolve credentials via the standard priority chain
    creds = config.resolve_credentials(account=credential)

    # Determine workspace_id from env or config if not explicitly provided
    resolved_workspace_id = workspace_id
    if resolved_workspace_id is None:
        env_ws = os.environ.get("MP_WORKSPACE_ID")
        if env_ws:
            import contextlib

            with contextlib.suppress(ValueError):
                resolved_workspace_id = int(env_ws)

    # Override project_id if explicitly provided
    resolved_project_id = project_id or creds.project_id

    # Gather custom header from env vars or config [settings]
    custom_header: BridgeCustomHeader | None = None
    env_header_name = os.environ.get("MP_CUSTOM_HEADER_NAME")
    env_header_value = os.environ.get("MP_CUSTOM_HEADER_VALUE")
    if env_header_name and env_header_value:
        custom_header = BridgeCustomHeader(
            name=env_header_name,
            value=SecretStr(env_header_value),
        )
    else:
        config_header = config.get_custom_header()
        if config_header is not None:
            header_name, header_value = config_header
            custom_header = BridgeCustomHeader(
                name=header_name,
                value=SecretStr(header_value),
            )

    # Build auth-method-specific sections
    oauth_section: BridgeOAuth | None = None
    sa_section: BridgeServiceAccount | None = None
    auth_method_str: str

    if creds.auth_method == _AuthMethod.oauth:
        auth_method_str = "oauth"
        # Load full token data from OAuthStorage for refresh capability
        storage = OAuthStorage()
        region = creds.region
        tokens = storage.load_tokens(region)
        if tokens is None:
            err_console.print(
                "[red]Error:[/red] OAuth tokens not found in local storage. "
                "Run 'mp auth login' first."
            )
            raise typer.Exit(1)

        # Load client info for client_id
        client_info = storage.load_client_info(region)
        client_id = client_info.client_id if client_info else "unknown"

        oauth_section = BridgeOAuth(
            access_token=SecretStr(tokens.access_token.get_secret_value()),
            refresh_token=SecretStr(tokens.refresh_token.get_secret_value())
            if tokens.refresh_token
            else None,
            expires_at=tokens.expires_at,
            scope=tokens.scope,
            token_type=tokens.token_type,
            client_id=client_id,
        )
    else:
        auth_method_str = "service_account"
        sa_section = BridgeServiceAccount(
            username=creds.username,
            secret=SecretStr(creds.secret.get_secret_value()),
        )

    # Build and write the bridge file
    bridge = AuthBridgeFile(
        version=1,
        auth_method=auth_method_str,
        region=creds.region,
        project_id=resolved_project_id,
        workspace_id=resolved_workspace_id,
        custom_header=custom_header,
        oauth=oauth_section,
        service_account=sa_section,
    )
    write_bridge_file(bridge, bridge_path)

    # When using default path, also write flat file at ~/.claude/mixpanel_auth.json
    if dir is None:
        import contextlib as _contextlib

        flat_path = bridge_path.parent.parent / _FLAT_BRIDGE_FILENAME
        with _contextlib.suppress(OSError):
            write_bridge_file(bridge, flat_path)

    # Test credentials with a lightweight API call
    test_ok = False
    try:
        from mixpanel_data.workspace import Workspace

        test_result = Workspace.test_credentials(credential)
        test_ok = bool(test_result.get("success", False))
    except Exception:
        pass

    data: dict[str, object] = {
        "status": "cowork_setup_complete",
        "bridge_path": str(bridge_path),
        "auth_method": auth_method_str,
        "region": creds.region,
        "project_id": resolved_project_id,
        "workspace_id": resolved_workspace_id,
        "has_custom_header": custom_header is not None,
        "credentials_valid": test_ok,
    }
    output_result(ctx, data, format=format)


@auth_app.command("cowork-teardown")
@handle_errors
def cowork_teardown(
    ctx: typer.Context,
    format: FormatOption = "json",
) -> None:
    """Remove the Cowork auth bridge file.

    Deletes ``~/.claude/mixpanel/auth.json`` if it exists. This
    revokes Cowork VM access to Mixpanel credentials exported by
    ``cowork-setup``.

    Examples:

        mp auth cowork-teardown
    """
    from mixpanel_data._internal.auth.bridge import (
        _default_bridge_path,
    )

    bridge_path = _default_bridge_path()

    if bridge_path.is_file():
        bridge_path.unlink()
        output_result(
            ctx,
            {
                "status": "cowork_teardown_complete",
                "bridge_path": str(bridge_path),
                "removed": True,
            },
            format=format,
        )
    else:
        output_result(
            ctx,
            {
                "status": "cowork_teardown_complete",
                "bridge_path": str(bridge_path),
                "removed": False,
                "message": "Bridge file did not exist.",
            },
            format=format,
        )


@auth_app.command("cowork-status")
@handle_errors
def cowork_status(
    ctx: typer.Context,
    format: FormatOption = "json",
) -> None:
    """Show the status of the Cowork auth bridge file.

    Checks whether ``~/.claude/mixpanel/auth.json`` exists and, if
    so, displays its auth method, project, region, token expiry, and
    custom header status.

    If the bridge file does not exist, suggests running
    ``cowork-setup``.

    Examples:

        mp auth cowork-status
        mp auth cowork-status --format table
    """
    from mixpanel_data._internal.auth.bridge import (
        _default_bridge_path,
        load_bridge_file,
    )

    bridge_path = _default_bridge_path()

    if not bridge_path.is_file():
        data: dict[str, object] = {
            "exists": False,
            "bridge_path": str(bridge_path),
            "message": "No bridge file found. Run 'mp auth cowork-setup' to create one.",
        }
        output_result(ctx, data, format=format)
        return

    bridge = load_bridge_file(bridge_path)
    if bridge is None:
        data = {
            "exists": True,
            "valid": False,
            "bridge_path": str(bridge_path),
            "message": "Bridge file exists but is invalid. "
            "Run 'mp auth cowork-setup' to recreate it.",
        }
        output_result(ctx, data, format=format)
        return

    # Build status info
    data = {
        "exists": True,
        "valid": True,
        "bridge_path": str(bridge_path),
        "auth_method": bridge.auth_method,
        "region": bridge.region,
        "project_id": bridge.project_id,
        "workspace_id": bridge.workspace_id,
        "has_custom_header": bridge.custom_header is not None,
    }

    if bridge.oauth is not None:
        data["oauth_expires_at"] = bridge.oauth.expires_at.isoformat()
        data["oauth_is_expired"] = bridge.oauth.is_expired()
        data["oauth_scope"] = bridge.oauth.scope

    if bridge.service_account is not None:
        data["sa_username"] = bridge.service_account.username

    output_result(ctx, data, format=format)
