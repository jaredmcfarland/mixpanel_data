"""Auth bridge for Claude Cowork credential transfer.

Provides a JSON-based credential bridge that allows ``mixpanel_data``
to authenticate inside Claude Cowork VMs. Credentials are exported
from the host machine to ``~/.claude/mixpanel/auth.json``, which is
bindfs-mounted into the Cowork VM.

The bridge supports both OAuth 2.0 and service account credentials,
optional custom HTTP headers, and automatic OAuth token refresh
(no browser required — uses HTTP POST with refresh token).

Bridge file search order:
    1. ``MP_AUTH_FILE`` environment variable (explicit path)
    2. ``mixpanel_auth.json`` in current working directory (Cowork workspace)
    3. ``~/.claude/mixpanel/auth.json`` (standard location)
    4. ``~/.claude/mixpanel_auth.json`` (flat file alternative)
    5. ``~/mnt/{folder}/mixpanel_auth.json`` (Cowork bindfs mount)

Example:
    ```python
    from mixpanel_data._internal.auth.bridge import (
        load_bridge_file,
        bridge_to_credentials,
        detect_cowork,
    )

    if detect_cowork():
        bridge = load_bridge_file()
        if bridge is not None:
            creds = bridge_to_credentials(bridge)
    ```
"""

from __future__ import annotations

import json
import logging
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator, model_validator

from mixpanel_data._internal.auth.flow import OAuthFlow
from mixpanel_data._internal.auth.token import OAuthTokens
from mixpanel_data._internal.auth_credential import (
    VALID_REGIONS,
    AuthCredential,
    CredentialType,
    ProjectContext,
    RegionType,
    ResolvedSession,
)
from mixpanel_data._internal.config import AuthMethod, Credentials
from mixpanel_data.exceptions import OAuthError

logger = logging.getLogger(__name__)

# Sentinel path for Cowork detection
_COWORK_SESSIONS_PATH = Path("/sessions")

# Default bridge file location
_BRIDGE_FILENAME = "auth.json"
_BRIDGE_DIR_NAME = "mixpanel"
_CLAUDE_DIR_NAME = ".claude"
# Flat file alternative (for Cowork where subdirectories may not be visible)
FLAT_BRIDGE_FILENAME = "mixpanel_auth.json"


class BridgeCustomHeader(BaseModel):
    """Custom HTTP header to include in all API requests.

    Both name and value must be provided. The value is stored as a
    ``SecretStr`` to prevent accidental exposure in logs.

    Attributes:
        name: HTTP header name (e.g., ``X-Custom-Auth``).
        value: HTTP header value (redacted in output).
    """

    model_config = ConfigDict(frozen=True)

    name: str
    """HTTP header name."""

    value: SecretStr
    """HTTP header value (redacted in output)."""


class BridgeOAuth(BaseModel):
    """OAuth 2.0 token data stored in the bridge file.

    Contains everything needed for Bearer auth and token refresh
    without a browser.

    Attributes:
        access_token: OAuth access token (redacted in output).
        refresh_token: OAuth refresh token for silent renewal.
        expires_at: UTC datetime when access_token expires.
        scope: Space-separated granted scopes.
        token_type: Token type, typically ``"Bearer"``.
        client_id: OAuth client ID for token refresh requests.
    """

    model_config = ConfigDict(frozen=True)

    access_token: SecretStr
    """OAuth access token (redacted in output)."""

    refresh_token: SecretStr | None = None
    """OAuth refresh token for silent renewal."""

    expires_at: datetime
    """UTC datetime when access_token expires."""

    scope: str
    """Space-separated granted scopes."""

    token_type: str
    """Token type, typically ``'Bearer'``."""

    client_id: str
    """OAuth client ID for token refresh requests."""

    def is_expired(self) -> bool:
        """Check whether the access token is expired or about to expire.

        Uses a 30-second safety buffer to avoid sending tokens that
        expire during in-flight requests.

        Returns:
            True if the token is expired or will expire within 30 seconds.
        """
        return datetime.now(timezone.utc) + timedelta(seconds=30) >= self.expires_at


class BridgeServiceAccount(BaseModel):
    """Service account credentials stored in the bridge file.

    Attributes:
        username: Service account username.
        secret: Service account secret (redacted in output).
    """

    model_config = ConfigDict(frozen=True)

    username: str
    """Service account username."""

    secret: SecretStr
    """Service account secret (redacted in output)."""


class AuthBridgeFile(BaseModel):
    """Complete auth bridge file model.

    Represents the JSON structure at ``~/.claude/mixpanel/auth.json``.
    Contains credentials (OAuth or service account), project context,
    and optional custom headers for Mixpanel API access.

    Attributes:
        version: Bridge file format version (must be 1).
        auth_method: Authentication method (``"oauth"`` or ``"service_account"``).
        region: Mixpanel data residency region.
        project_id: Mixpanel project identifier.
        workspace_id: Optional workspace ID for App API scoping.
        custom_header: Optional custom HTTP header for all requests.
        oauth: OAuth token data (required when auth_method is ``"oauth"``).
        service_account: SA credentials (required when auth_method is ``"service_account"``).
    """

    model_config = ConfigDict(frozen=True)

    version: Literal[1]
    """Bridge file format version (must be 1)."""

    auth_method: Literal["oauth", "service_account"]
    """Authentication method."""

    region: RegionType
    """Mixpanel data residency region (us, eu, or in)."""

    project_id: str
    """Mixpanel project identifier."""

    workspace_id: int | None = None
    """Optional workspace ID for App API scoping."""

    custom_header: BridgeCustomHeader | None = None
    """Optional custom HTTP header for all requests."""

    oauth: BridgeOAuth | None = None
    """OAuth token data (required when auth_method is 'oauth')."""

    service_account: BridgeServiceAccount | None = None
    """SA credentials (required when auth_method is 'service_account')."""

    @field_validator("region", mode="before")
    @classmethod
    def validate_region(cls, v: str) -> str:
        """Validate and normalize region to lowercase.

        Args:
            v: Raw region string.

        Returns:
            Lowercased, validated region string.

        Raises:
            ValueError: If region is not one of ``us``, ``eu``, ``in``.
        """
        if not isinstance(v, str):
            raise ValueError(f"Region must be a string. Got: {type(v).__name__}")
        v_lower = v.lower()
        if v_lower not in VALID_REGIONS:
            valid = ", ".join(VALID_REGIONS)
            raise ValueError(f"Region must be one of: {valid}. Got: {v}")
        return v_lower

    @model_validator(mode="after")
    def validate_auth_sections(self) -> AuthBridgeFile:
        """Validate that the correct credential section is present.

        Raises:
            ValueError: If ``auth_method`` does not match the provided
                credential section (e.g., ``"oauth"`` without ``oauth``).
        """
        if self.auth_method == "oauth" and self.oauth is None:
            raise ValueError("auth_method='oauth' requires 'oauth' section")
        if self.auth_method == "service_account" and self.service_account is None:
            raise ValueError(
                "auth_method='service_account' requires 'service_account' section"
            )
        return self


def detect_cowork() -> bool:
    """Detect if running inside a Claude Cowork VM.

    Checks two indicators:
    1. ``CLAUDE_COWORK`` environment variable is set (reliable)
    2. ``/sessions/`` mount point exists (heuristic — may false-positive
       on systems with a ``/sessions`` directory unrelated to Cowork)

    This function is used for informational purposes (CLI output,
    plugin guidance). Bridge file discovery (``find_bridge_file()``)
    runs unconditionally and does not depend on this function.

    Returns:
        True if running inside a Cowork VM.

    Example:
        ```python
        if detect_cowork():
            print("Running inside Claude Cowork")
        ```
    """
    if os.environ.get("CLAUDE_COWORK"):
        return True
    return _COWORK_SESSIONS_PATH.is_dir()


def default_bridge_path() -> Path:
    """Return the default bridge file path.

    Returns:
        Path to ``~/.claude/mixpanel/auth.json``.
    """
    return Path.home() / _CLAUDE_DIR_NAME / _BRIDGE_DIR_NAME / _BRIDGE_FILENAME


def find_bridge_file() -> Path | None:
    """Find the auth bridge file using the search order.

    Search order:
        1. ``MP_AUTH_FILE`` environment variable (explicit path)
        2. ``mixpanel_auth.json`` in current working directory (Cowork workspace)
        3. ``~/.claude/mixpanel/auth.json`` (standard location)
        4. ``~/.claude/mixpanel_auth.json`` (flat file alternative)
        5. ``~/mnt/{folder}/mixpanel_auth.json`` (Cowork bindfs mount)

    Returns:
        Path to the bridge file if found, None otherwise.

    Example:
        ```python
        path = find_bridge_file()
        if path is not None:
            bridge = load_bridge_file(path)
        ```
    """
    # Priority 1: Explicit env var
    env_path = os.environ.get("MP_AUTH_FILE")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
        logger.debug("MP_AUTH_FILE set but file not found: %s", env_path)
        return None

    # Priority 2: Bridge file in CWD (workspace root)
    # In Cowork, the workspace IS mounted — this is the primary Cowork path
    cwd_bridge = Path.cwd() / FLAT_BRIDGE_FILENAME
    if cwd_bridge.is_file():
        logger.debug("Found bridge file in workspace: %s", cwd_bridge)
        return cwd_bridge

    # Priority 3: Default location (~/.claude/mixpanel/auth.json)
    default = default_bridge_path()
    if default.is_file():
        return default

    # Priority 4: Flat file (~/.claude/mixpanel_auth.json)
    flat = Path.home() / _CLAUDE_DIR_NAME / FLAT_BRIDGE_FILENAME
    if flat.is_file():
        logger.debug("Found flat bridge file: %s", flat)
        return flat

    # Priority 5: Cowork workspace mount (~/mnt/{folder}/mixpanel_auth.json)
    # In Cowork, the workspace is at $HOME/mnt/{folder}/
    mnt_base = Path.home() / "mnt"
    if mnt_base.is_dir():
        for child in mnt_base.iterdir():
            if not child.is_dir():
                continue
            cowork_path = child / FLAT_BRIDGE_FILENAME
            if cowork_path.is_file():
                logger.debug("Found bridge file at Cowork mount: %s", cowork_path)
                return cowork_path

    return None


def load_bridge_file(path: Path | None = None) -> AuthBridgeFile | None:
    """Load and validate a bridge file.

    Args:
        path: Explicit path to the bridge file. If None, uses
            ``find_bridge_file()`` to locate it.

    Returns:
        Validated AuthBridgeFile if found and valid, None otherwise.
        Returns None (does not raise) for missing files, invalid JSON,
        or schema validation failures.

    Example:
        ```python
        bridge = load_bridge_file()
        if bridge is not None:
            creds = bridge_to_credentials(bridge)
        ```
    """
    if path is None:
        path = find_bridge_file()
    if path is None:
        return None
    if not path.is_file():
        return None

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return AuthBridgeFile.model_validate(data)
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("Failed to read bridge file %s: %s", path, exc)
        return None
    except Exception as exc:
        logger.debug("Failed to validate bridge file %s: %s", path, exc)
        return None


def write_bridge_file(bridge: AuthBridgeFile, path: Path) -> None:
    """Write a bridge file with secure permissions.

    Creates the parent directory if needed. Sets directory permissions
    to ``0o700`` and file permissions to ``0o600``.

    Args:
        bridge: The bridge file model to write.
        path: Destination file path.

    Raises:
        OSError: If the file cannot be written.

    Example:
        ```python
        bridge = AuthBridgeFile(...)
        write_bridge_file(bridge, Path.home() / ".claude/mixpanel/auth.json")
        ```
    """
    dir_existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not dir_existed:
        try:
            os.chmod(path.parent, stat.S_IRWXU)  # 0o700
        except OSError:
            logger.warning("Could not set directory permissions on %s", path.parent)

    data = bridge_to_json_dict(bridge)
    raw = json.dumps(data, indent=2, default=str)
    path.write_text(raw, encoding="utf-8")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except OSError:
        logger.warning("Could not set file permissions on %s", path)


def bridge_to_json_dict(bridge: AuthBridgeFile) -> dict[str, Any]:
    """Serialize an AuthBridgeFile to a JSON-compatible dict.

    Unwraps ``SecretStr`` fields to plain strings for JSON output.

    Args:
        bridge: The bridge file model to serialize.

    Returns:
        JSON-serializable dictionary with all secrets unwrapped.
    """
    d: dict[str, Any] = {
        "version": bridge.version,
        "auth_method": bridge.auth_method,
        "region": bridge.region,
        "project_id": bridge.project_id,
        "workspace_id": bridge.workspace_id,
        "custom_header": None,
        "oauth": None,
        "service_account": None,
    }
    if bridge.custom_header is not None:
        d["custom_header"] = {
            "name": bridge.custom_header.name,
            "value": bridge.custom_header.value.get_secret_value(),
        }
    if bridge.oauth is not None:
        d["oauth"] = {
            "access_token": bridge.oauth.access_token.get_secret_value(),
            "refresh_token": bridge.oauth.refresh_token.get_secret_value()
            if bridge.oauth.refresh_token
            else None,
            "expires_at": bridge.oauth.expires_at.isoformat(),
            "scope": bridge.oauth.scope,
            "token_type": bridge.oauth.token_type,
            "client_id": bridge.oauth.client_id,
        }
    if bridge.service_account is not None:
        d["service_account"] = {
            "username": bridge.service_account.username,
            "secret": bridge.service_account.secret.get_secret_value(),
        }
    return d


def bridge_to_credentials(bridge: AuthBridgeFile) -> Credentials:
    """Convert an AuthBridgeFile to a legacy Credentials object.

    Creates a ``Credentials`` instance suitable for passing to
    ``MixpanelAPIClient``.

    Args:
        bridge: The bridge file to convert.

    Returns:
        Credentials configured for the bridge's auth method.

    Raises:
        ValueError: If auth_method is ``"oauth"`` but no OAuth data
            is present, or ``"service_account"`` but no SA data.

    Example:
        ```python
        bridge = load_bridge_file()
        creds = bridge_to_credentials(bridge)
        client = MixpanelAPIClient(creds)
        ```
    """
    if bridge.auth_method == "oauth":
        if bridge.oauth is None:
            raise ValueError("OAuth bridge file missing 'oauth' section")
        return Credentials(
            username="",
            secret=SecretStr(""),
            project_id=bridge.project_id,
            region=bridge.region,
            auth_method=AuthMethod.oauth,
            oauth_access_token=bridge.oauth.access_token,
        )

    if bridge.service_account is None:
        raise ValueError(
            "Service account bridge file missing 'service_account' section"
        )
    return Credentials(
        username=bridge.service_account.username,
        secret=bridge.service_account.secret,
        project_id=bridge.project_id,
        region=bridge.region,
        auth_method=AuthMethod.basic,
    )


def bridge_to_resolved_session(bridge: AuthBridgeFile) -> ResolvedSession:
    """Convert an AuthBridgeFile to a v2 ResolvedSession.

    Creates an ``AuthCredential`` and ``ProjectContext`` from the
    bridge file data.

    Args:
        bridge: The bridge file to convert.

    Returns:
        ResolvedSession with auth and project context.

    Raises:
        ValueError: If auth_method is ``"oauth"`` but no OAuth data
            is present, or ``"service_account"`` but no SA data.

    Example:
        ```python
        bridge = load_bridge_file()
        session = bridge_to_resolved_session(bridge)
        # session.project_id, session.auth_header()
        ```
    """
    if bridge.auth_method == "oauth":
        if bridge.oauth is None:
            raise ValueError("OAuth bridge file missing 'oauth' section")
        auth = AuthCredential(
            name="cowork-bridge",
            type=CredentialType.oauth,
            region=bridge.region,
            oauth_access_token=bridge.oauth.access_token,
        )
    else:
        if bridge.service_account is None:
            raise ValueError("SA bridge file missing 'service_account' section")
        auth = AuthCredential(
            name="cowork-bridge",
            type=CredentialType.service_account,
            region=bridge.region,
            username=bridge.service_account.username,
            secret=bridge.service_account.secret,
        )

    project = ProjectContext(
        project_id=bridge.project_id,
        workspace_id=bridge.workspace_id,
    )
    return ResolvedSession(auth=auth, project=project)


def apply_bridge_custom_header(bridge: AuthBridgeFile) -> None:
    """Set custom header env vars from bridge file.

    Sets ``MP_CUSTOM_HEADER_NAME`` and ``MP_CUSTOM_HEADER_VALUE``
    environment variables if the bridge file contains a custom header
    and the env vars are not already set.

    This allows the existing ``MixpanelAPIClient._ensure_client()``
    to pick up custom headers without code changes.

    Args:
        bridge: The bridge file containing optional custom header.

    Example:
        ```python
        bridge = load_bridge_file()
        apply_bridge_custom_header(bridge)
        # Now MP_CUSTOM_HEADER_* env vars are set if bridge has a header
        ```
    """
    if bridge.custom_header is None:
        return

    # Don't override existing env vars
    if os.environ.get("MP_CUSTOM_HEADER_NAME") and os.environ.get(
        "MP_CUSTOM_HEADER_VALUE"
    ):
        logger.debug("MP_CUSTOM_HEADER_* already set, skipping bridge custom header")
        return

    os.environ["MP_CUSTOM_HEADER_NAME"] = bridge.custom_header.name
    os.environ["MP_CUSTOM_HEADER_VALUE"] = bridge.custom_header.value.get_secret_value()
    logger.debug(
        "Applied custom header from bridge file: %s", bridge.custom_header.name
    )


def refresh_bridge_token(
    bridge: AuthBridgeFile,
    bridge_path: Path,
) -> AuthBridgeFile:
    """Refresh an expired OAuth token in the bridge file.

    If the bridge uses service account auth or the OAuth token is not
    expired, returns the bridge unchanged. Otherwise, uses the refresh
    token to obtain a new access token via HTTP POST (no browser needed).

    Attempts to write the updated bridge file back to disk. Write
    failures are silently ignored (e.g., read-only mount in Cowork).

    Args:
        bridge: The bridge file to check and potentially refresh.
        bridge_path: Path to the bridge file for write-back.

    Returns:
        The original bridge if no refresh needed, or a new
        AuthBridgeFile with updated OAuth tokens.

    Raises:
        OAuthError: If the refresh token is missing or the refresh
            request fails (e.g., revoked token).

    Example:
        ```python
        bridge = load_bridge_file(path)
        bridge = refresh_bridge_token(bridge, path)
        creds = bridge_to_credentials(bridge)
        ```
    """
    # SA credentials don't expire
    if bridge.auth_method != "oauth" or bridge.oauth is None:
        return bridge

    # Check if token is expired
    if not bridge.oauth.is_expired():
        return bridge

    logger.info("Bridge OAuth token expired, attempting refresh...")

    if bridge.oauth.refresh_token is None:
        raise OAuthError(
            "Cannot refresh: no refresh token in bridge file. "
            "Re-run 'mp auth cowork-setup' on your host machine.",
            code="OAUTH_REFRESH_ERROR",
        )

    # Build OAuthTokens for the refresh call
    old_tokens = OAuthTokens(
        access_token=bridge.oauth.access_token,
        refresh_token=bridge.oauth.refresh_token,
        expires_at=bridge.oauth.expires_at,
        scope=bridge.oauth.scope,
        token_type=bridge.oauth.token_type,
        project_id=bridge.project_id,
    )

    # Refresh via HTTP POST (no browser needed)
    flow = OAuthFlow(region=bridge.region)
    new_tokens = flow.refresh_tokens(
        tokens=old_tokens, client_id=bridge.oauth.client_id
    )

    # Build updated bridge
    new_oauth = BridgeOAuth(
        access_token=new_tokens.access_token,
        refresh_token=new_tokens.refresh_token or bridge.oauth.refresh_token,
        expires_at=new_tokens.expires_at,
        scope=new_tokens.scope or bridge.oauth.scope,
        token_type=new_tokens.token_type,
        client_id=bridge.oauth.client_id,
    )

    updated = AuthBridgeFile(
        version=bridge.version,
        auth_method=bridge.auth_method,
        region=bridge.region,
        project_id=bridge.project_id,
        workspace_id=bridge.workspace_id,
        custom_header=bridge.custom_header,
        oauth=new_oauth,
        service_account=bridge.service_account,
    )

    # Try to write back (ignore errors for read-only mounts)
    try:
        write_bridge_file(updated, bridge_path)
        logger.info("Updated bridge file with refreshed token")
    except OSError:
        logger.debug("Could not write refreshed token to bridge file (read-only?)")

    return updated


# =============================================================================
# v2 Bridge Schema (042-auth-architecture-redesign)
# =============================================================================
# The v2 bridge embeds a full Account discriminated-union record (with secrets
# inline by design — Cowork crosses a trust boundary). It coexists with the
# AuthBridgeFile model above during the transitional Phase 3-4 window. The
# v2 resolver consumes BridgeFile via load_bridge(); writers come in Phase 8.
#
# Reference: specs/042-auth-architecture-redesign/contracts/config-schema.md §2.

from typing import (  # noqa: E402  # below v1 class defs by design
    Annotated as _Annotated,
)

from pydantic import (  # noqa: E402
    Field as _Field,
)
from pydantic import (  # noqa: E402
    PositiveInt as _PositiveInt,
)
from pydantic import (  # noqa: E402
    TypeAdapter as _TypeAdapter,
)
from pydantic import (  # noqa: E402
    ValidationError as _ValidationError,
)

from mixpanel_data._internal.auth.account import Account as _AccountUnion  # noqa: E402
from mixpanel_data.exceptions import ConfigError as _ConfigError  # noqa: E402


class BridgeFile(BaseModel):
    """Cowork credential bridge file — v2 schema.

    Embeds a full :class:`~mixpanel_data._internal.auth.account.Account`
    record (with secrets inline) plus optional project / workspace pinning
    and a custom-headers map. Loaded as a synthetic config source by
    :func:`~mixpanel_data._internal.auth.resolver.resolve_session`; written
    by ``mp account export-bridge`` (deferred to Phase 8).

    Example:
        ```json
        {
          "version": 2,
          "account": {"type": "oauth_browser", "name": "personal", "region": "us"},
          "tokens": {"access_token": "...", "refresh_token": "...",
                     "expires_at": "2026-04-22T12:00:00Z",
                     "token_type": "Bearer", "scope": "read"},
          "project": "3713224",
          "workspace": 3448413,
          "headers": {"X-Mixpanel-Cluster": "internal-1"}
        }
        ```
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[2] = 2
    """Bridge schema version — always ``2``."""

    account: _AccountUnion
    """Full Account discriminated-union record (with secrets inline by design)."""

    tokens: OAuthTokens | None = None
    """OAuth tokens — required iff ``account.type == "oauth_browser"``."""

    project: _Annotated[str | None, _Field(default=None, pattern=r"^\d+$")] = None
    """Optional pinned project ID (numeric string)."""

    workspace: _PositiveInt | None = None
    """Optional pinned workspace ID."""

    headers: dict[str, str] = {}
    """Custom HTTP headers attached to outbound requests at resolution time."""

    @model_validator(mode="after")
    def _validate_oauth_browser_has_tokens(self) -> BridgeFile:
        """Enforce that ``oauth_browser`` accounts include their tokens.

        Returns:
            The validated instance.

        Raises:
            ValueError: If ``account.type == "oauth_browser"`` and ``tokens``
                is missing.
        """
        if self.account.type == "oauth_browser" and self.tokens is None:
            raise ValueError("BridgeFile with oauth_browser account requires `tokens`.")
        return self


_DEFAULT_BRIDGE_PATHS: tuple[Path, ...] = (
    Path.home() / ".claude" / "mixpanel" / "auth.json",
)


def default_bridge_search_paths() -> tuple[Path, ...]:
    """Return the default bridge file paths consulted in priority order.

    Returns:
        Tuple of candidate paths (default Cowork location first, then
        a ``mixpanel_auth.json`` in the current working directory). The
        ``MP_AUTH_FILE`` env var, if set, is consulted by callers BEFORE
        any default path.
    """
    return (
        Path.home() / ".claude" / "mixpanel" / "auth.json",
        Path.cwd() / "mixpanel_auth.json",
    )


_bridge_adapter: _TypeAdapter[BridgeFile] = _TypeAdapter(BridgeFile)


def load_bridge(path: Path | None = None) -> BridgeFile | None:
    """Load and validate a v2 bridge file from disk.

    Resolves the path in this order:

    1. Argument ``path`` (if not None).
    2. ``$MP_AUTH_FILE`` env var (if set).
    3. Default search paths (``~/.claude/mixpanel/auth.json``, then
       ``<cwd>/mixpanel_auth.json``) — first existing file wins.

    Args:
        path: Optional explicit bridge path.

    Returns:
        The parsed :class:`BridgeFile`, or ``None`` if no candidate
        path exists.

    Raises:
        ConfigError: If a candidate file exists but is malformed or fails
            schema validation.
    """
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path)
    elif "MP_AUTH_FILE" in os.environ and os.environ["MP_AUTH_FILE"]:
        candidates.append(Path(os.environ["MP_AUTH_FILE"]))
    else:
        candidates.extend(default_bridge_search_paths())

    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise _ConfigError(
                f"Could not read bridge file at {candidate}: {exc}",
                details={"path": str(candidate)},
            ) from exc
        try:
            return _bridge_adapter.validate_python(payload)
        except _ValidationError as exc:
            raise _ConfigError(
                f"Invalid bridge file at {candidate}: "
                f"{exc.errors(include_url=False)[0]['msg']}",
                details={"path": str(candidate)},
            ) from exc
    return None
