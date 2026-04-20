"""Configuration management for mixpanel_data.

Handles credential storage, resolution, and account management.
Configuration is stored in TOML format at ~/.mp/config.toml by default.
"""

from __future__ import annotations

import base64
import logging
import os
import stat
import sys
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mixpanel_data._internal.auth.bridge import AuthBridgeFile
    from mixpanel_data._internal.auth_credential import ResolvedSession

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]
from pathlib import Path
from typing import Any, cast

import tomli_w
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator, model_validator

from mixpanel_data._internal.auth_credential import VALID_REGIONS, RegionType
from mixpanel_data.exceptions import (
    AccountExistsError,
    AccountNotFoundError,
    ConfigError,
)

logger = logging.getLogger(__name__)


class AuthMethod(str, Enum):
    """Authentication method for Mixpanel API requests.

    Determines how the ``Authorization`` header is constructed:

    - ``basic``: Uses HTTP Basic Auth with service account username/secret.
    - ``oauth``: Uses OAuth 2.0 Bearer token.

    Example:
        ```python
        method = AuthMethod.basic
        assert method.value == "basic"

        method = AuthMethod.oauth
        assert method.value == "oauth"
        ```
    """

    basic = "basic"
    """HTTP Basic Auth with service account credentials."""

    oauth = "oauth"
    """OAuth 2.0 Bearer token authentication."""


class Credentials(BaseModel):
    """Immutable credentials for Mixpanel API authentication.

    This is a frozen Pydantic model that ensures:
    - All fields are validated on construction
    - The secret is never exposed in repr/str output
    - The object cannot be modified after creation

    Supports both Basic Auth (service account) and OAuth 2.0 Bearer token
    authentication. When ``auth_method`` is ``oauth``, the ``username`` and
    ``secret`` fields may be empty strings.
    """

    model_config = ConfigDict(frozen=True)

    username: str
    """Service account username (may be empty for OAuth)."""

    secret: SecretStr
    """Service account secret (redacted in output; may be empty for OAuth)."""

    project_id: str
    """Mixpanel project identifier."""

    region: RegionType
    """Data residency region (us, eu, or in)."""

    auth_method: AuthMethod = AuthMethod.basic
    """Authentication method (basic or oauth). Defaults to basic."""

    oauth_access_token: SecretStr | None = None
    """OAuth 2.0 access token, required when auth_method is oauth."""

    @field_validator("region", mode="before")
    @classmethod
    def validate_region(cls, v: str) -> str:
        """Validate and normalize region to lowercase."""
        if not isinstance(v, str):
            raise ValueError(f"Region must be a string. Got: {type(v).__name__}")
        v_lower = v.lower()
        if v_lower not in VALID_REGIONS:
            valid = ", ".join(VALID_REGIONS)
            raise ValueError(f"Region must be one of: {valid}. Got: {v}")
        return v_lower

    @model_validator(mode="after")
    def validate_credentials(self) -> Credentials:
        """Validate credential fields based on auth method.

        For basic auth, username and project_id must be non-empty.
        For OAuth, username may be empty but project_id must still be non-empty,
        and oauth_access_token must be provided.

        Returns:
            The validated Credentials instance.

        Raises:
            ValueError: If required fields are missing for the auth method.
        """
        if not self.project_id or not self.project_id.strip():
            raise ValueError("project_id cannot be empty")

        if self.auth_method == AuthMethod.basic:
            if not self.username or not self.username.strip():
                raise ValueError("username cannot be empty for basic auth")
            if not self.secret.get_secret_value():
                raise ValueError("secret cannot be empty for basic auth")
        elif self.auth_method == AuthMethod.oauth:
            if self.oauth_access_token is None:
                raise ValueError(
                    "oauth_access_token is required when auth_method is oauth"
                )
            if not self.oauth_access_token.get_secret_value():
                raise ValueError("oauth_access_token cannot be empty for oauth auth")
        return self

    def auth_header(self) -> str:
        """Build the Authorization header value for API requests.

        Returns:
            For basic auth: ``"Basic <base64(username:secret)>"``.
            For OAuth: ``"Bearer <access_token>"``.

        Raises:
            ValueError: If auth_method is oauth but no access token is set.

        Example:
            ```python
            creds = Credentials(
                username="sa-user", secret=SecretStr("sa-secret"),
                project_id="123", region="us",
            )
            assert creds.auth_header().startswith("Basic ")

            oauth_creds = Credentials(
                username="", secret=SecretStr(""),
                project_id="123", region="us",
                auth_method=AuthMethod.oauth,
                oauth_access_token=SecretStr("my-token"),
            )
            assert oauth_creds.auth_header() == "Bearer my-token"
            ```
        """
        if self.auth_method == AuthMethod.oauth:
            if self.oauth_access_token is None:
                raise ValueError("No OAuth access token available")
            return f"Bearer {self.oauth_access_token.get_secret_value()}"

        raw = f"{self.username}:{self.secret.get_secret_value()}"
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        return f"Basic {encoded}"

    @classmethod
    def from_oauth_token(
        cls,
        token: str,
        project_id: str,
        region: RegionType,
    ) -> Credentials:
        """Build OAuth-method ``Credentials`` from a pre-obtained bearer token.

        Skips the PKCE browser flow — for callers who already hold an
        OAuth 2.0 access token.

        Args:
            token: The OAuth 2.0 bearer token.
            project_id: Mixpanel project identifier.
            region: Data residency region (``"us"``, ``"eu"``, or ``"in"``).

        Returns:
            Immutable OAuth-method ``Credentials``.

        Raises:
            ValueError: If ``token`` or ``project_id`` is empty, or
                ``region`` is invalid.

        Example:
            ```python
            from mixpanel_data import Workspace
            from mixpanel_data.auth import Credentials

            creds = Credentials.from_oauth_token(
                token="my-bearer-token",
                project_id="12345",
                region="us",
            )
            ws = Workspace(credentials=creds)
            ```
        """
        # Strip whitespace defensively — shell exports / copy-paste often
        # introduce trailing newlines that would corrupt the Bearer header.
        return cls(
            username="",
            secret=SecretStr(""),
            project_id=project_id,
            region=region,
            auth_method=AuthMethod.oauth,
            oauth_access_token=SecretStr(token.strip()),
        )

    def to_resolved_session(self, workspace_id: int | None = None) -> ResolvedSession:
        """Convert legacy Credentials to a ResolvedSession.

        Creates an ``AuthCredential`` and ``ProjectContext`` from this
        ``Credentials`` instance, bridging the v1 and v2 auth systems.

        Args:
            workspace_id: Optional workspace ID to include in the
                ``ProjectContext``. Defaults to ``None``.

        Returns:
            A ``ResolvedSession`` wrapping this credential's auth and project.

        Example:
            ```python
            creds = config.resolve_credentials()
            session = creds.to_resolved_session()
            # session.project_id == creds.project_id
            # session.auth_header() == creds.auth_header()
            ```
        """
        from mixpanel_data._internal.auth_credential import (
            AuthCredential,
            CredentialType,
            ProjectContext,
            ResolvedSession,
        )

        if self.auth_method == AuthMethod.oauth:
            auth = AuthCredential(
                name=self.username or "oauth",
                type=CredentialType.oauth,
                region=self.region,
                oauth_access_token=self.oauth_access_token,
            )
        else:
            auth = AuthCredential(
                name=self.username,
                type=CredentialType.service_account,
                region=self.region,
                username=self.username,
                secret=self.secret,
            )

        project = ProjectContext(project_id=self.project_id, workspace_id=workspace_id)
        return ResolvedSession(auth=auth, project=project)

    def __repr__(self) -> str:
        """Return string representation with redacted secret."""
        return (
            f"Credentials(username={self.username!r}, secret=***, "
            f"project_id={self.project_id!r}, region={self.region!r})"
        )

    def __str__(self) -> str:
        """Return string representation with redacted secret."""
        return self.__repr__()


@dataclass(frozen=True)
class AccountInfo:
    """Information about a configured account (without secret).

    Used for listing accounts without exposing sensitive credentials.
    """

    name: str
    """Account display name."""

    username: str
    """Service account username."""

    project_id: str
    """Mixpanel project identifier."""

    region: str
    """Data residency region."""

    is_default: bool
    """Whether this is the default account."""


@dataclass(frozen=True)
class CredentialInfo:
    """Information about a configured credential (v2 config, without secret).

    Used for listing credentials without exposing sensitive data.
    """

    name: str
    """Credential display name."""

    type: str
    """Credential type (service_account or oauth)."""

    region: str
    """Data residency region."""

    is_active: bool
    """Whether this is the currently active credential."""


@dataclass(frozen=True)
class ActiveContext:
    """The currently selected credential + project + workspace from config.

    All fields are optional to allow partial configuration.
    """

    credential: str | None = None
    """Active credential name."""

    project_id: str | None = None
    """Active project ID."""

    workspace_id: int | None = None
    """Active workspace ID."""


@dataclass(frozen=True)
class ProjectAlias:
    """A named shortcut for quick context switching.

    Maps a friendly name to a project_id with optional credential
    and workspace overrides.
    """

    name: str
    """Alias name (e.g., 'ecom', 'ai-demo')."""

    project_id: str
    """Target project ID."""

    credential: str | None = None
    """Credential name to use (defaults to active)."""

    workspace_id: int | None = None
    """Default workspace for this alias."""


@dataclass(frozen=True)
class MigrationResult:
    """Result of migrating v1 config to v2 format.

    Provides a summary of what was migrated for user display.
    """

    credentials_created: int
    """Number of credentials created."""

    aliases_created: int
    """Number of project aliases created."""

    active_credential: str | None
    """Name of the credential set as active."""

    active_project_id: str | None
    """Project ID set as active."""

    backup_path: Path | None
    """Path to the backup file, or None if dry-run."""


class ConfigManager:
    """Manages Mixpanel project credentials and configuration.

    Supports both legacy account-based config (v1) and the newer
    credential + project alias format (v2).

    Handles:
    - Adding, removing, and listing project accounts (v1)
    - Credential CRUD: add, remove, list credentials (v2)
    - Active context management: credential, project, workspace (v2)
    - Project aliases for quick context switching (v2)
    - Session resolution: env vars → active context → fallback (v2)
    - Setting the default account (v1)
    - Resolving credentials from environment variables or config file
    - v1 → v2 config migration with backup

    Config file location (in priority order):
    1. Explicit config_path parameter
    2. MP_CONFIG_PATH environment variable
    3. Default: ~/.mp/config.toml
    """

    DEFAULT_CONFIG_PATH = Path.home() / ".mp" / "config.toml"

    def __init__(self, config_path: Path | None = None) -> None:
        """Initialize ConfigManager.

        Args:
            config_path: Override config file location.
                         Default: ~/.mp/config.toml
        """
        if config_path is not None:
            self._config_path = config_path
        elif "MP_CONFIG_PATH" in os.environ:
            self._config_path = Path(os.environ["MP_CONFIG_PATH"])
        else:
            self._config_path = self.DEFAULT_CONFIG_PATH

    @property
    def config_path(self) -> Path:
        """Return the config file path."""
        return self._config_path

    def _read_config(self) -> dict[str, Any]:
        """Read and parse the config file.

        Returns:
            Parsed config dictionary, or empty dict if file doesn't exist.
        """
        if not self._config_path.exists():
            return {}

        try:
            with self._config_path.open("rb") as f:
                return dict(tomllib.load(f))
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(
                f"Invalid TOML in config file: {e}",
                details={"path": str(self._config_path)},
            ) from e

    def _write_config(self, config: dict[str, Any]) -> None:
        """Write config to file, creating directory if needed.

        Args:
            config: Configuration dictionary to write.
        """
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with self._config_path.open("wb") as f:
            tomli_w.dump(config, f)
        try:
            os.chmod(self._config_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        except OSError:
            logger.warning(
                "Could not set permissions on config file %s",
                self._config_path,
            )

    def _get_available_account_names(self) -> list[str]:
        """Get list of configured account names."""
        config = self._read_config()
        accounts = config.get("accounts", {})
        return list(accounts.keys())

    def resolve_credentials(
        self,
        account: str | None = None,
        *,
        _oauth_storage_dir: Path | None = None,
    ) -> Credentials:
        """Resolve credentials using priority order.

        Resolution order when ``account`` is None:

        1. Environment variables — either the service-account env vars
           (``MP_USERNAME`` + ``MP_SECRET`` + ``MP_PROJECT_ID`` + ``MP_REGION``)
           or the OAuth-token env vars (``MP_OAUTH_TOKEN`` + ``MP_PROJECT_ID``
           + ``MP_REGION``). Service-account env vars take precedence when
           both sets are complete.
        2. Auth bridge file (MP_AUTH_FILE or ~/.claude/mixpanel/auth.json)
        3. OAuth tokens from local storage (if valid and not expired)
        4. Default account from config file

        Resolution order when ``account`` is provided:

        1. Environment variables (one complete set must be present)
        2. Named account from config file (bridge and OAuth are skipped)

        For OAuth resolution, the region and project_id are determined from:
        - ``MP_PROJECT_ID`` / ``MP_REGION`` env vars (partial env mode), or
        - The default account in the config file.

        Expired OAuth tokens are skipped, falling through to config file
        resolution.

        Args:
            account: Optional account name to use instead of default.
                When provided, OAuth resolution is skipped.
            _oauth_storage_dir: Override OAuth storage directory for testing.
                If ``None``, uses the default ``OAuthStorage`` directory.

        Returns:
            Immutable Credentials object.

        Raises:
            ConfigError: If no credentials can be resolved.
            AccountNotFoundError: If named account doesn't exist.

        Example:
            ```python
            config = ConfigManager()
            creds = config.resolve_credentials()
            print(creds.auth_method)  # AuthMethod.basic or AuthMethod.oauth
            ```
        """
        # Apply custom headers from config [settings] section early —
        # they should be available regardless of which resolution path succeeds.
        self.apply_config_custom_header()

        # Priority 1: Environment variables (all four must be set)
        env_creds = self._resolve_from_env()
        if env_creds is not None:
            return env_creds

        # Priority 2: Auth bridge file (only when no explicit account requested)
        if account is None:
            bridge_creds = self._resolve_from_bridge()
            if bridge_creds is not None:
                return bridge_creds

        # Priority 3: OAuth tokens (only when no explicit account requested)
        if account is None:
            oauth_creds = self._resolve_from_oauth(
                _oauth_storage_dir=_oauth_storage_dir,
            )
            if oauth_creds is not None:
                return oauth_creds

        # Priority 4: Config file (named account or default)

        config = self._read_config()
        accounts = config.get("accounts", {})

        if not accounts:
            raise ConfigError(
                "No credentials configured. "
                "Run 'mp auth login' to authenticate via OAuth, "
                "set MP_USERNAME + MP_SECRET + MP_PROJECT_ID + MP_REGION "
                "for service-account auth, or set MP_OAUTH_TOKEN + "
                "MP_PROJECT_ID + MP_REGION to use a pre-obtained bearer token."
            )

        # Determine which account to use
        account_name: str
        if account is not None:
            account_name = account
        else:
            default_account = config.get("default")
            if default_account is not None and isinstance(default_account, str):
                account_name = default_account
            else:
                # Use the first account if no default set
                account_name = next(iter(accounts.keys()))

        if account_name not in accounts:
            raise AccountNotFoundError(
                account_name,
                available_accounts=list(accounts.keys()),
            )

        account_data = accounts[account_name]
        return Credentials(
            username=account_data["username"],
            secret=SecretStr(account_data["secret"]),
            project_id=account_data["project_id"],
            region=account_data["region"],
        )

    def _resolve_from_oauth(
        self,
        *,
        _oauth_storage_dir: Path | None = None,
    ) -> Credentials | None:
        """Attempt to resolve credentials from stored OAuth tokens.

        Checks for valid (non-expired) OAuth tokens in local storage.
        The region for token lookup is determined from ``MP_REGION`` env var
        or the default account in the config file.

        Args:
            _oauth_storage_dir: Override OAuth storage directory for testing.

        Returns:
            Credentials with ``auth_method=AuthMethod.oauth`` if valid tokens
            are found, ``None`` otherwise.
        """
        from mixpanel_data._internal.auth.storage import OAuthStorage

        # Determine region and project_id for token lookup
        region, project_id = self._resolve_region_and_project_for_oauth(
            _oauth_storage_dir=_oauth_storage_dir,
        )
        if region is None:
            return None

        storage = OAuthStorage(storage_dir=_oauth_storage_dir)
        tokens = storage.load_tokens(region)
        if tokens is None:
            return None

        # Skip expired tokens — fall through to config file resolution
        if tokens.is_expired():
            logger.debug(
                "OAuth token for region '%s' is expired. "
                "Run 'mp auth login' to refresh.",
                region,
            )
            return None

        # Use project_id from token if available, otherwise from config/env
        resolved_project_id = tokens.project_id or project_id
        if resolved_project_id is None:
            return None

        return Credentials(
            username="",
            secret=SecretStr(""),
            project_id=resolved_project_id,
            region=cast(RegionType, region),
            auth_method=AuthMethod.oauth,
            oauth_access_token=SecretStr(tokens.access_token.get_secret_value()),
        )

    def _resolve_region_and_project_for_oauth(
        self,
        *,
        _oauth_storage_dir: Path | None = None,
    ) -> tuple[str | None, str | None]:
        """Determine region and project_id for OAuth token lookup.

        Checks in order:
        1. ``MP_REGION`` / ``MP_PROJECT_ID`` environment variables
        2. Default account from config file
        3. v2 credentials and active context
        4. Scan OAuth storage for any valid token

        Args:
            _oauth_storage_dir: Override OAuth storage directory for testing.

        Returns:
            Tuple of ``(region, project_id)``. Either or both may be
            ``None`` if not determinable.
        """
        # Check env vars first (partial env mode)
        env_region = os.environ.get("MP_REGION")
        env_project_id = os.environ.get("MP_PROJECT_ID")

        if env_region and env_region in VALID_REGIONS:
            return env_region, env_project_id

        # Fall back to config file default account
        config = self._read_config()
        accounts = config.get("accounts", {})

        if accounts:
            default_name = config.get("default")
            if (
                default_name
                and isinstance(default_name, str)
                and default_name in accounts
            ):
                account_data = accounts[default_name]
                return account_data.get("region"), account_data.get("project_id")

            # Use first account as fallback
            first_account = next(iter(accounts.values()))
            return first_account.get("region"), first_account.get("project_id")

        # v2 config: check active context for project_id
        active = config.get("active", {})
        active_project_id = active.get("project_id")

        # Check credentials for region
        credentials = config.get("credentials", {})
        active_cred_name = active.get("credential")
        if active_cred_name and active_cred_name in credentials:
            cred_data = credentials[active_cred_name]
            return cred_data.get("region", "us"), active_project_id
        if credentials:
            first_cred = next(iter(credentials.values()))
            return first_cred.get("region", "us"), active_project_id

        # Last resort: scan OAuth storage for any valid token
        from mixpanel_data._internal.auth.storage import OAuthStorage

        storage = OAuthStorage(storage_dir=_oauth_storage_dir)
        for region_candidate in VALID_REGIONS:
            tokens = storage.load_tokens(region_candidate)
            if tokens is not None and not tokens.is_expired():
                # Prefer token's project_id, fall back to active context
                return region_candidate, tokens.project_id or active_project_id
        return None, None

    def _load_and_refresh_bridge(self) -> AuthBridgeFile | None:
        """Load, refresh, and apply custom headers from a bridge file.

        Finds the bridge file, loads it, applies custom headers to env
        vars, and refreshes expired OAuth tokens. Returns the ready-to-use
        bridge model, or ``None`` if no valid bridge is found.

        Bridge resolution is only attempted when:
        - ``MP_AUTH_FILE`` environment variable is explicitly set, OR
        - Running inside a Cowork VM (detected via ``detect_cowork()``)

        This prevents host-side auth lockout after running
        ``mp auth cowork-setup``, which writes a bridge file that would
        otherwise shadow normal credential resolution.

        Returns:
            An ``AuthBridgeFile`` instance if a valid bridge file is found
            and ready, ``None`` otherwise.
        """
        from mixpanel_data._internal.auth.bridge import (
            apply_bridge_custom_header,
            detect_cowork,
            find_bridge_file,
            load_bridge_file,
            refresh_bridge_token,
        )

        # Only consult bridge files when explicitly requested (MP_AUTH_FILE)
        # or when running inside a Cowork VM.  On the host, bridge files
        # written by cowork-setup must not shadow normal auth resolution.
        if not os.environ.get("MP_AUTH_FILE") and not detect_cowork():
            return None

        path = find_bridge_file()
        if path is None:
            return None

        bridge = load_bridge_file(path)
        if bridge is None:
            return None

        # Apply custom headers to env vars
        apply_bridge_custom_header(bridge)

        # Refresh expired OAuth tokens
        if (
            bridge.auth_method == "oauth"
            and bridge.oauth is not None
            and bridge.oauth.is_expired()
        ):
            try:
                bridge = refresh_bridge_token(bridge, path)
            except Exception as exc:
                if type(exc).__name__ == "OAuthError":
                    logger.warning("Bridge token refresh failed: %s", exc)
                else:
                    logger.warning(
                        "Bridge token refresh failed (%s): %s. "
                        "Falling back to other auth methods.",
                        type(exc).__name__,
                        exc,
                    )
                return None

        return bridge

    def _resolve_from_bridge(self) -> Credentials | None:
        """Attempt to resolve credentials from an auth bridge file.

        Loads the bridge file from ``MP_AUTH_FILE`` env var or the
        default location (``~/.claude/mixpanel/auth.json``). If the
        bridge contains an expired OAuth token, attempts to refresh it.

        Also applies custom headers from the bridge file to env vars.

        Returns:
            Credentials if a valid bridge file is found, None otherwise.
        """
        bridge = self._load_and_refresh_bridge()
        if bridge is None:
            return None
        from mixpanel_data._internal.auth.bridge import bridge_to_credentials

        return bridge_to_credentials(bridge)

    def _resolve_session_from_bridge(self) -> ResolvedSession | None:
        """Attempt to resolve a session from an auth bridge file.

        Loads the bridge file and converts it to a ``ResolvedSession``.
        If the bridge contains an expired OAuth token, attempts to
        refresh it. Also applies custom headers.

        Returns:
            ResolvedSession if a valid bridge file is found, None otherwise.
        """
        bridge = self._load_and_refresh_bridge()
        if bridge is None:
            return None
        from mixpanel_data._internal.auth.bridge import bridge_to_resolved_session

        return bridge_to_resolved_session(bridge)

    def _resolve_from_env(self) -> Credentials | None:
        """Attempt to resolve credentials from environment variables.

        Accepts either the service-account env vars (``MP_USERNAME`` +
        ``MP_SECRET`` + ``MP_PROJECT_ID`` + ``MP_REGION``) or the OAuth
        env vars (``MP_OAUTH_TOKEN`` + ``MP_PROJECT_ID`` + ``MP_REGION``).
        Service-account wins when both sets are complete.

        Returns:
            Credentials if either set is complete, ``None`` otherwise.

        Raises:
            ConfigError: If a complete env-var set is present and
                ``MP_REGION`` is invalid. ``MP_REGION`` is only validated
                when the rest of its set is also present.
        """
        username = os.environ.get("MP_USERNAME")
        secret = os.environ.get("MP_SECRET")
        project_id = os.environ.get("MP_PROJECT_ID")
        region = os.environ.get("MP_REGION")
        oauth_token = os.environ.get("MP_OAUTH_TOKEN")

        if username and secret and project_id and region:
            normalized_region = self._validate_env_region(region)
            return Credentials(
                username=username,
                secret=SecretStr(secret),
                project_id=project_id,
                region=cast(RegionType, normalized_region),
            )

        if oauth_token and project_id and region:
            normalized_region = self._validate_env_region(region)
            return Credentials.from_oauth_token(
                token=oauth_token,
                project_id=project_id,
                region=cast(RegionType, normalized_region),
            )
        return None

    @staticmethod
    def _validate_env_region(region: str) -> str:
        """Normalize ``MP_REGION`` to lowercase and validate the value.

        Args:
            region: Raw ``MP_REGION`` env-var value.

        Returns:
            The lowercased region string.

        Raises:
            ConfigError: If the region is not one of ``us``, ``eu``, ``in``.
        """
        normalized = region.strip().lower()
        if normalized not in VALID_REGIONS:
            raise ConfigError(
                f"Invalid MP_REGION: '{normalized}'. Must be 'us', 'eu', or 'in'."
            )
        return normalized

    def list_accounts(self) -> list[AccountInfo]:
        """List all configured accounts.

        Returns:
            List of AccountInfo objects (secrets not included).
        """
        config = self._read_config()
        accounts = config.get("accounts", {})
        default_name = config.get("default")

        result: list[AccountInfo] = []
        for name, data in accounts.items():
            result.append(
                AccountInfo(
                    name=name,
                    username=data.get("username", ""),
                    project_id=data.get("project_id", ""),
                    region=data.get("region", ""),
                    is_default=(name == default_name),
                )
            )

        return result

    def add_account(
        self,
        name: str,
        username: str,
        secret: str,
        project_id: str,
        region: str,
    ) -> None:
        """Add a new account configuration.

        Args:
            name: Display name for the account.
            username: Service account username.
            secret: Service account secret.
            project_id: Mixpanel project ID.
            region: Data residency region (us, eu, in).

        Raises:
            AccountExistsError: If account name already exists.
            ValueError: If region is invalid.
        """
        # Validate region
        region_lower = region.lower()
        if region_lower not in VALID_REGIONS:
            valid = ", ".join(VALID_REGIONS)
            raise ValueError(f"Region must be one of: {valid}. Got: {region}")

        config = self._read_config()
        accounts = config.setdefault("accounts", {})

        if name in accounts:
            raise AccountExistsError(name)

        accounts[name] = {
            "username": username,
            "secret": secret,
            "project_id": project_id,
            "region": region_lower,
        }

        # If this is the first account, make it the default
        if "default" not in config:
            config["default"] = name

        self._write_config(config)

    def remove_account(self, name: str) -> None:
        """Remove an account configuration.

        Args:
            name: Account name to remove.

        Raises:
            AccountNotFoundError: If account doesn't exist.
        """
        config = self._read_config()
        accounts = config.get("accounts", {})

        if name not in accounts:
            raise AccountNotFoundError(name, available_accounts=list(accounts.keys()))

        del accounts[name]

        # If we removed the default, clear it or set to another account
        if config.get("default") == name:
            if accounts:
                config["default"] = next(iter(accounts.keys()))
            else:
                config.pop("default", None)

        self._write_config(config)

    def set_default(self, name: str) -> None:
        """Set the default account.

        Args:
            name: Account name to set as default.

        Raises:
            AccountNotFoundError: If account doesn't exist.
        """
        config = self._read_config()
        accounts = config.get("accounts", {})

        if name not in accounts:
            raise AccountNotFoundError(name, available_accounts=list(accounts.keys()))

        config["default"] = name
        self._write_config(config)

    def get_account(self, name: str) -> AccountInfo:
        """Get information about a specific account.

        Args:
            name: Account name.

        Returns:
            AccountInfo object (secret not included).

        Raises:
            AccountNotFoundError: If account doesn't exist.
        """
        config = self._read_config()
        accounts = config.get("accounts", {})

        if name not in accounts:
            raise AccountNotFoundError(name, available_accounts=list(accounts.keys()))

        data = accounts[name]
        default_name = config.get("default")

        return AccountInfo(
            name=name,
            username=data.get("username", ""),
            project_id=data.get("project_id", ""),
            region=data.get("region", ""),
            is_default=(name == default_name),
        )

    # ── V2 Config Methods ────────────────────────────────────────────

    def config_version(self) -> int:
        """Detect the config schema version.

        Returns:
            2 if ``config_version = 2`` is present, else 1.

        Example:
            ```python
            cm = ConfigManager()
            version = cm.config_version()  # 1 or 2
            ```
        """
        config = self._read_config()
        return int(config.get("config_version", 1))

    def get_custom_header(self) -> tuple[str, str] | None:
        """Return custom header from config ``[settings]`` section.

        Looks for ``custom_header_name`` and ``custom_header_value``
        keys in the ``[settings]`` table. Both must be present and
        non-empty to return a result.

        Returns:
            Tuple of ``(name, value)`` if both are configured,
            ``None`` otherwise.

        Example:
            ```python
            cm = ConfigManager()
            header = cm.get_custom_header()
            if header:
                name, value = header
            ```
        """
        config = self._read_config()
        settings = config.get("settings", {})
        if not isinstance(settings, dict):
            return None
        name = settings.get("custom_header_name")
        value = settings.get("custom_header_value")
        if name and value and isinstance(name, str) and isinstance(value, str):
            return (name, value)
        return None

    def apply_config_custom_header(self) -> None:
        """Apply custom header from config to env vars.

        Sets ``MP_CUSTOM_HEADER_NAME`` and ``MP_CUSTOM_HEADER_VALUE``
        if the config ``[settings]`` section has both values and the
        env vars are not already set.

        This allows the existing ``MixpanelAPIClient._ensure_client()``
        to pick up custom headers from config.toml.
        """
        if os.environ.get("MP_CUSTOM_HEADER_NAME") and os.environ.get(
            "MP_CUSTOM_HEADER_VALUE"
        ):
            return

        header = self.get_custom_header()
        if header is None:
            return

        name, value = header
        os.environ["MP_CUSTOM_HEADER_NAME"] = name
        os.environ["MP_CUSTOM_HEADER_VALUE"] = value
        logger.debug("Applied custom header from config: %s", name)

    def _write_config_atomic(self, config: dict[str, Any]) -> None:
        """Write config atomically via temp file + os.replace().

        Args:
            config: Configuration dictionary to write.
        """
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._config_path.with_suffix(".tmp")
        try:
            with tmp_path.open("wb") as f:
                tomli_w.dump(config, f)
            os.replace(tmp_path, self._config_path)
            try:
                os.chmod(self._config_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
            except OSError:
                logger.warning(
                    "Could not set permissions on config file %s",
                    self._config_path,
                )
        except OSError:
            tmp_path.unlink(missing_ok=True)
            raise

    # ── Credential CRUD (v2) ─────────────────────────────────────────

    def add_credential(
        self,
        name: str,
        type: str,
        username: str | None = None,
        secret: str | None = None,
        region: str = "us",
    ) -> None:
        """Add a new credential to v2 config.

        Args:
            name: Unique credential name.
            type: Credential type ("service_account" or "oauth").
            username: Service account username (SA only).
            secret: Service account secret (SA only).
            region: Data residency region (us, eu, in).

        Raises:
            ConfigError: If credential name already exists.
            ValueError: If region is invalid.

        Example:
            ```python
            cm = ConfigManager()
            cm.add_credential(
                name="demo-sa", type="service_account",
                username="user", secret="secret", region="us",
            )
            ```
        """
        from mixpanel_data._internal.auth_credential import CredentialType

        valid_types = {ct.value for ct in CredentialType}
        if type not in valid_types:
            raise ValueError(
                f"Credential type must be one of: "
                f"{', '.join(sorted(valid_types))}. Got: {type}"
            )

        region_lower = region.lower()
        if region_lower not in VALID_REGIONS:
            valid = ", ".join(VALID_REGIONS)
            raise ValueError(f"Region must be one of: {valid}. Got: {region}")

        config = self._read_config()
        config["config_version"] = 2
        credentials = config.setdefault("credentials", {})

        if name in credentials:
            raise ConfigError(
                f"Credential '{name}' already exists.",
                details={"credential_name": name},
            )

        entry: dict[str, str] = {"type": type, "region": region_lower}
        if type == "service_account":
            if not username:
                raise ValueError("username is required for service_account credentials")
            if not secret:
                raise ValueError("secret is required for service_account credentials")
            entry["username"] = username
            entry["secret"] = secret

        credentials[name] = entry

        # First credential becomes active
        active = config.setdefault("active", {})
        if not active.get("credential"):
            active["credential"] = name

        self._write_config_atomic(config)

    def list_credentials(self) -> list[CredentialInfo]:
        """List all configured credentials (v2 config).

        Returns:
            List of CredentialInfo objects (secrets not included).

        Example:
            ```python
            cm = ConfigManager()
            for cred in cm.list_credentials():
                print(f"{cred.name}: {cred.type} ({cred.region})")
            ```
        """
        config = self._read_config()
        credentials = config.get("credentials", {})
        active_name = config.get("active", {}).get("credential")

        result: list[CredentialInfo] = []
        for name, data in credentials.items():
            cred_type = data.get("type")
            if cred_type is None:
                logger.warning(
                    "Credential '%s' missing 'type' field, defaulting to "
                    "service_account",
                    name,
                )
                cred_type = "service_account"
            cred_region = data.get("region")
            if cred_region is None:
                logger.warning(
                    "Credential '%s' missing 'region' field, defaulting to us",
                    name,
                )
                cred_region = "us"
            result.append(
                CredentialInfo(
                    name=name,
                    type=cred_type,
                    region=cred_region,
                    is_active=(name == active_name),
                )
            )
        return result

    def remove_credential(self, name: str) -> list[str]:
        """Remove a credential from v2 config.

        If the removed credential is the active one, the active credential
        is reset to the first remaining credential (or cleared).

        Checks for project aliases that reference the removed credential
        and returns their names as orphaned aliases. Callers should warn
        the user about orphaned aliases.

        Args:
            name: Credential name to remove.

        Returns:
            List of project alias names that referenced the removed
            credential (orphaned aliases). Empty if none.

        Raises:
            ConfigError: If credential doesn't exist.

        Example:
            ```python
            cm = ConfigManager()
            orphaned = cm.remove_credential("old-sa")
            if orphaned:
                print(f"Warning: aliases still reference 'old-sa': {orphaned}")
            ```
        """
        config = self._read_config()
        credentials = config.get("credentials", {})

        if name not in credentials:
            available = list(credentials.keys())
            raise ConfigError(
                f"Credential '{name}' not found. "
                f"Available: {', '.join(available) if available else 'none'}",
                details={"credential_name": name, "available": available},
            )

        del credentials[name]

        # Reset active credential if needed
        active = config.get("active", {})
        if active.get("credential") == name:
            if credentials:
                active["credential"] = next(iter(credentials.keys()))
            else:
                active.pop("credential", None)

        # Find orphaned aliases
        projects = config.get("projects", {})
        orphaned: list[str] = [
            alias_name
            for alias_name, alias_data in projects.items()
            if alias_data.get("credential") == name
        ]

        self._write_config_atomic(config)
        return orphaned

    # ── Active Context (v2) ──────────────────────────────────────────

    def get_active_context(self) -> ActiveContext:
        """Get the current active context from config.

        Returns:
            ActiveContext with credential, project_id, workspace_id.

        Example:
            ```python
            cm = ConfigManager()
            ctx = cm.get_active_context()
            print(f"Credential: {ctx.credential}, Project: {ctx.project_id}")
            ```
        """
        config = self._read_config()
        active = config.get("active", {})
        workspace_id_raw = active.get("workspace_id")
        return ActiveContext(
            credential=active.get("credential"),
            project_id=active.get("project_id"),
            workspace_id=int(workspace_id_raw)
            if workspace_id_raw is not None
            else None,
        )

    def set_active_credential(self, name: str) -> None:
        """Set the active credential.

        Args:
            name: Credential name to set as active.

        Raises:
            ConfigError: If credential doesn't exist.

        Example:
            ```python
            cm = ConfigManager()
            cm.set_active_credential("demo-sa")
            ```
        """
        config = self._read_config()
        credentials = config.get("credentials", {})

        if name not in credentials:
            available = list(credentials.keys())
            raise ConfigError(
                f"Credential '{name}' not found.",
                details={"credential_name": name, "available": available},
            )

        active = config.setdefault("active", {})
        active["credential"] = name
        self._write_config_atomic(config)

    def set_active_project(
        self, project_id: str, workspace_id: int | None = None
    ) -> None:
        """Set the active project (and optionally workspace).

        Args:
            project_id: Project ID to set as active.
            workspace_id: Optional workspace ID to set.

        Example:
            ```python
            cm = ConfigManager()
            cm.set_active_project("3713224", workspace_id=3448413)
            ```
        """
        config = self._read_config()
        active = config.setdefault("active", {})
        active["project_id"] = project_id
        if workspace_id is not None:
            active["workspace_id"] = workspace_id
        elif "workspace_id" in active:
            del active["workspace_id"]
        self._write_config_atomic(config)

    def set_active_context(
        self,
        credential: str | None = None,
        project_id: str | None = None,
        workspace_id: int | None = None,
    ) -> None:
        """Set the active credential, project, and workspace in one write.

        Performs a single read-modify-write cycle so that all three active
        fields are updated together, avoiding partial-update windows.

        Args:
            credential: Credential name to set as active. If ``None``,
                the active credential is left unchanged.
            project_id: Project ID to set as active. If ``None``, the
                active project is left unchanged.
            workspace_id: Workspace ID to set. If ``None``, the active
                workspace is cleared. Note: unlike ``credential`` and
                ``project_id``, passing ``None`` here *clears* the workspace
                rather than leaving it unchanged.

        Example:
            ```python
            cm = ConfigManager()
            cm.set_active_context(
                credential="demo-sa",
                project_id="3713224",
                workspace_id=3448413,
            )
            ```
        """
        config = self._read_config()
        active = config.setdefault("active", {})

        if credential is not None:
            # Validate credential exists
            credentials = config.get("credentials", {})
            if credential not in credentials:
                available = list(credentials.keys())
                raise ConfigError(
                    f"Credential '{credential}' not found.",
                    details={"credential_name": credential, "available": available},
                )
            active["credential"] = credential

        if project_id is not None:
            active["project_id"] = project_id

        if workspace_id is not None:
            active["workspace_id"] = workspace_id
        elif "workspace_id" in active:
            del active["workspace_id"]

        self._write_config_atomic(config)

    def set_active_workspace(self, workspace_id: int) -> None:
        """Set the active workspace.

        Args:
            workspace_id: Workspace ID to set.

        Example:
            ```python
            cm = ConfigManager()
            cm.set_active_workspace(3448413)
            ```
        """
        config = self._read_config()
        active = config.setdefault("active", {})
        active["workspace_id"] = workspace_id
        self._write_config_atomic(config)

    # ── Project Aliases (v2) ─────────────────────────────────────────

    def list_project_aliases(self) -> list[ProjectAlias]:
        """List all project aliases.

        Returns:
            List of ProjectAlias objects.

        Example:
            ```python
            cm = ConfigManager()
            for alias in cm.list_project_aliases():
                print(f"{alias.name} -> {alias.project_id}")
            ```
        """
        config = self._read_config()
        projects = config.get("projects", {})

        result: list[ProjectAlias] = []
        for name, data in projects.items():
            ws_id_raw = data.get("workspace_id")
            result.append(
                ProjectAlias(
                    name=name,
                    project_id=data.get("project_id", ""),
                    credential=data.get("credential"),
                    workspace_id=int(ws_id_raw) if ws_id_raw is not None else None,
                )
            )
        return result

    def add_project_alias(
        self,
        name: str,
        project_id: str,
        credential: str | None = None,
        workspace_id: int | None = None,
    ) -> None:
        """Create a named project alias for quick switching.

        Args:
            name: Alias name (e.g., "ecom", "ai-demo").
            project_id: Target project ID.
            credential: Credential name to use (optional).
            workspace_id: Default workspace for this alias (optional).

        Raises:
            ConfigError: If alias name already exists.

        Example:
            ```python
            cm = ConfigManager()
            cm.add_project_alias("ecom", "3018488", credential="demo-sa")
            ```
        """
        config = self._read_config()
        config["config_version"] = 2
        projects = config.setdefault("projects", {})

        if name in projects:
            raise ConfigError(
                f"Project alias '{name}' already exists.",
                details={"alias_name": name},
            )

        entry: dict[str, Any] = {"project_id": project_id}
        if credential is not None:
            entry["credential"] = credential
        if workspace_id is not None:
            entry["workspace_id"] = workspace_id

        projects[name] = entry
        self._write_config_atomic(config)

    def remove_project_alias(self, name: str) -> None:
        """Remove a project alias.

        Args:
            name: Alias name to remove.

        Raises:
            ConfigError: If alias doesn't exist.

        Example:
            ```python
            cm = ConfigManager()
            cm.remove_project_alias("old-alias")
            ```
        """
        config = self._read_config()
        projects = config.get("projects", {})

        if name not in projects:
            available = list(projects.keys())
            raise ConfigError(
                f"Project alias '{name}' not found.",
                details={"alias_name": name, "available": available},
            )

        del projects[name]
        self._write_config_atomic(config)

    # ── Session Resolution (v2) ──────────────────────────────────────

    def resolve_session(
        self,
        credential: str | None = None,
        project_id: str | None = None,
        workspace_id: int | None = None,
        *,
        _oauth_storage_dir: Path | None = None,
    ) -> ResolvedSession:
        """Resolve a complete session using the v2 priority chain.

        Priority order:
        1. ENV VARS — service-account env vars (MP_USERNAME + MP_SECRET +
           MP_PROJECT_ID + MP_REGION) OR OAuth-token env vars
           (MP_OAUTH_TOKEN + MP_PROJECT_ID + MP_REGION). Service-account
           wins when both sets are complete.
        2. AUTH BRIDGE FILE (MP_AUTH_FILE or ~/.claude/mixpanel/auth.json)
        3. EXPLICIT PARAMS (credential + project_id + workspace_id)
        4. ACTIVE CONTEXT (config [active] section)
        5. OAUTH FALLBACK (valid token + active.project_id)
        6. FIRST AVAILABLE (first credential + first known project)

        Works with both v1 and v2 configs.

        Args:
            credential: Override credential name.
            project_id: Override project ID.
            workspace_id: Override workspace ID.
            _oauth_storage_dir: Override OAuth storage directory for testing.

        Returns:
            Fully resolved ResolvedSession.

        Raises:
            ConfigError: If no session can be resolved.

        Example:
            ```python
            cm = ConfigManager()
            session = cm.resolve_session()
            # session.project_id, session.auth_header(), session.region
            ```
        """
        # Apply custom headers from config [settings] section early —
        # they should be available regardless of which resolution path succeeds.
        self.apply_config_custom_header()

        # Priority 1: Environment variables
        env_creds = self._resolve_from_env()
        if env_creds is not None:
            return env_creds.to_resolved_session()

        # Priority 2: Auth bridge file (only when no explicit credential requested)
        if credential is None:
            bridge_session = self._resolve_session_from_bridge()
            if bridge_session is not None:
                # Apply overrides if provided
                if project_id is not None or workspace_id is not None:
                    from mixpanel_data._internal.auth_credential import (
                        ProjectContext,
                        ResolvedSession,
                    )

                    bridge_session = ResolvedSession(
                        auth=bridge_session.auth,
                        project=ProjectContext(
                            project_id=project_id or bridge_session.project_id,
                            workspace_id=workspace_id
                            if workspace_id is not None
                            else bridge_session.workspace_id,
                        ),
                    )
                return bridge_session

        config = self._read_config()
        version = int(config.get("config_version", 1))

        if version == 1:
            return self._resolve_session_v1(
                config,
                credential,
                project_id,
                workspace_id,
                _oauth_storage_dir=_oauth_storage_dir,
            )

        return self._resolve_session_v2(
            config,
            credential,
            project_id,
            workspace_id,
            _oauth_storage_dir=_oauth_storage_dir,
        )

    def _resolve_session_v1(
        self,
        _config: dict[str, Any],
        credential: str | None,
        project_id: str | None,
        workspace_id: int | None,
        *,
        _oauth_storage_dir: Path | None = None,
    ) -> ResolvedSession:
        """Resolve session from v1 config (backward compatibility).

        Treats v1 accounts as combined credential+project entries.

        Args:
            _config: Parsed config dictionary (unused in v1; kept for
                signature parity with ``_resolve_session_v2``).
            credential: Override account/credential name.
            project_id: Override project ID.
            workspace_id: Override workspace ID.
            _oauth_storage_dir: Override OAuth storage directory.

        Returns:
            ResolvedSession from v1 config.

        Raises:
            ConfigError: If no session can be resolved.
        """
        # Use existing resolve_credentials for v1
        creds = self.resolve_credentials(
            account=credential, _oauth_storage_dir=_oauth_storage_dir
        )
        session = creds.to_resolved_session()

        # Apply overrides
        if project_id is not None or workspace_id is not None:
            from mixpanel_data._internal.auth_credential import (
                ProjectContext,
                ResolvedSession,
            )

            session = ResolvedSession(
                auth=session.auth,
                project=ProjectContext(
                    project_id=project_id or session.project_id,
                    workspace_id=workspace_id
                    if workspace_id is not None
                    else session.project.workspace_id,
                ),
            )
        return session

    def _resolve_session_v2(
        self,
        config: dict[str, Any],
        credential_name: str | None,
        project_id: str | None,
        workspace_id: int | None,
        *,
        _oauth_storage_dir: Path | None = None,
    ) -> ResolvedSession:
        """Resolve session from v2 config.

        Args:
            config: Parsed config dictionary.
            credential_name: Override credential name.
            project_id: Override project ID.
            workspace_id: Override workspace ID.
            _oauth_storage_dir: Override OAuth storage directory.

        Returns:
            ResolvedSession from v2 config.

        Raises:
            ConfigError: If no session can be resolved.
        """
        from mixpanel_data._internal.auth_credential import (
            AuthCredential,
            CredentialType,
            ProjectContext,
            ResolvedSession,
        )

        credentials = config.get("credentials", {})
        active = config.get("active", {})

        # Resolve credential name
        cred_name = credential_name or active.get("credential")
        if not cred_name and credentials:
            cred_name = next(iter(credentials.keys()))

        # Fallback: check if name is a project alias (e.g. migrated v1 account)
        if cred_name and cred_name not in credentials:
            projects = config.get("projects", {})
            if cred_name in projects:
                alias = projects[cred_name]
                alias_cred = alias.get("credential")
                if alias_cred and alias_cred in credentials:
                    if project_id is None:
                        project_id = alias.get("project_id")
                    cred_name = alias_cred

        if not cred_name or cred_name not in credentials:
            raise ConfigError(
                "No credentials configured. "
                "Run 'mp auth login' to authenticate via OAuth, "
                "set MP_USERNAME + MP_SECRET + MP_PROJECT_ID + MP_REGION "
                "for service-account auth, or set MP_OAUTH_TOKEN + "
                "MP_PROJECT_ID + MP_REGION to use a pre-obtained bearer token.",
            )

        cred_data = credentials[cred_name]
        cred_type = cred_data.get("type", "service_account")

        if cred_type == "oauth":
            # Try to load OAuth token
            from mixpanel_data._internal.auth.storage import OAuthStorage

            region = cred_data.get("region", "us")
            storage = OAuthStorage(storage_dir=_oauth_storage_dir)
            tokens = storage.load_tokens(region)
            if tokens is None or tokens.is_expired():
                raise ConfigError(
                    f"OAuth token for credential '{cred_name}' is expired or missing. "
                    "Run 'mp auth login' to refresh.",
                )
            auth = AuthCredential(
                name=cred_name,
                type=CredentialType.oauth,
                region=region,
                oauth_access_token=SecretStr(tokens.access_token.get_secret_value()),
            )
        else:
            sa_username = cred_data.get("username", "")
            sa_secret = cred_data.get("secret", "")
            if not sa_username or not sa_secret:
                raise ConfigError(
                    f"Credential '{cred_name}' is missing username or secret. "
                    f"Re-add it with add_credential() or edit {self._config_path}.",
                    details={"credential_name": cred_name},
                )
            auth = AuthCredential(
                name=cred_name,
                type=CredentialType.service_account,
                region=cred_data.get("region", "us"),
                username=sa_username,
                secret=SecretStr(sa_secret),
            )

        # Resolve project
        resolved_project_id = project_id or active.get("project_id")
        resolved_workspace_id = workspace_id
        if resolved_workspace_id is None:
            ws_raw = active.get("workspace_id")
            if ws_raw is not None:
                resolved_workspace_id = int(ws_raw)

        if not resolved_project_id:
            raise ConfigError(
                "No project selected. "
                "Run 'mp projects list' to see available projects, then "
                "'mp projects switch <id>' to select one, "
                "or pass --project for a one-off override.",
            )

        project = ProjectContext(
            project_id=resolved_project_id,
            workspace_id=resolved_workspace_id,
        )

        return ResolvedSession(auth=auth, project=project)

    # ── Migration (v1 → v2) ──────────────────────────────────────────

    def migrate_v1_to_v2(self, *, dry_run: bool = False) -> MigrationResult:
        """Migrate v1 config to v2 format.

        Groups accounts by unique (username, secret, region) to create
        deduplicated credentials. Each original account becomes a project
        alias. The v1 default account determines the active context.

        Args:
            dry_run: If True, compute the result without writing.

        Returns:
            MigrationResult with summary of changes.

        Raises:
            ConfigError: If config is already v2 or migration fails.

        Example:
            ```python
            cm = ConfigManager()
            result = cm.migrate_v1_to_v2(dry_run=True)
            print(f"Would create {result.credentials_created} credentials")
            ```
        """
        config = self._read_config()

        if int(config.get("config_version", 1)) == 2:
            raise ConfigError("Config is already v2 format.")

        accounts = config.get("accounts", {})
        default_name = config.get("default")

        # Group accounts by unique credentials
        # Key: (username, secret, region) → credential name
        cred_map: dict[tuple[str, str, str], str] = {}
        new_credentials: dict[str, dict[str, str]] = {}
        new_projects: dict[str, dict[str, Any]] = {}

        for acct_name, acct_data in accounts.items():
            username = acct_data.get("username", "")
            secret = acct_data.get("secret", "")
            region = acct_data.get("region", "us")
            project_id = acct_data.get("project_id", "")

            key = (username, secret, region)

            if key not in cred_map:
                # First occurrence: use this account's name as credential name
                cred_name = acct_name
                cred_map[key] = cred_name
                new_credentials[cred_name] = {
                    "type": "service_account",
                    "username": username,
                    "secret": secret,
                    "region": region,
                }
            else:
                cred_name = cred_map[key]

            # Every account becomes a project alias
            alias_entry: dict[str, Any] = {
                "project_id": project_id,
                "credential": cred_name,
            }
            new_projects[acct_name] = alias_entry

        # Determine active context
        active_credential: str | None = None
        active_project_id: str | None = None

        if default_name and default_name in accounts:
            default_data = accounts[default_name]
            key = (
                default_data.get("username", ""),
                default_data.get("secret", ""),
                default_data.get("region", "us"),
            )
            active_credential = cred_map.get(key)
            active_project_id = default_data.get("project_id")
        elif new_credentials:
            active_credential = next(iter(new_credentials.keys()))

        backup_path: Path | None = None
        if not dry_run:
            # Backup
            backup_path = self._config_path.with_suffix(".toml.v1.bak")
            if self._config_path.exists():
                import shutil

                shutil.copy2(self._config_path, backup_path)

            # Write v2 config
            new_config: dict[str, Any] = {"config_version": 2}
            active: dict[str, Any] = {}
            if active_credential:
                active["credential"] = active_credential
            if active_project_id:
                active["project_id"] = active_project_id
            if active:
                new_config["active"] = active
            new_config["credentials"] = new_credentials
            new_config["projects"] = new_projects
            self._write_config_atomic(new_config)

        return MigrationResult(
            credentials_created=len(new_credentials),
            aliases_created=len(new_projects),
            active_credential=active_credential,
            active_project_id=active_project_id,
            backup_path=backup_path,
        )
