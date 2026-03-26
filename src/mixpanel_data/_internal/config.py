"""Configuration management for mixpanel_data.

Handles credential storage, resolution, and account management.
Configuration is stored in TOML format at ~/.mp/config.toml by default.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from enum import Enum

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]
from pathlib import Path
from typing import Any, Literal, cast

import tomli_w
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator, model_validator

from mixpanel_data.exceptions import (
    AccountExistsError,
    AccountNotFoundError,
    ConfigError,
)

# Valid regions for Mixpanel data residency
VALID_REGIONS = ("us", "eu", "in")
RegionType = Literal["us", "eu", "in"]


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

        import base64

        raw = f"{self.username}:{self.secret.get_secret_value()}"
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        return f"Basic {encoded}"

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


class ConfigManager:
    """Manages Mixpanel project credentials and configuration.

    Handles:
    - Adding, removing, and listing project accounts
    - Setting the default account
    - Resolving credentials from environment variables or config file

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

        Resolution order:
        1. Environment variables (MP_USERNAME, MP_SECRET, MP_PROJECT_ID, MP_REGION)
        2. OAuth tokens from local storage (if no explicit account requested)
        3. Named account from config file (if account parameter provided)
        4. Default account from config file

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
        # Priority 1: Environment variables (all four must be set)
        env_creds = self._resolve_from_env()
        if env_creds is not None:
            return env_creds

        # Priority 2: OAuth tokens (only when no explicit account requested)
        if account is None:
            oauth_creds = self._resolve_from_oauth(
                _oauth_storage_dir=_oauth_storage_dir,
            )
            if oauth_creds is not None:
                return oauth_creds

        # Priority 3 & 4: Config file (named account or default)
        config = self._read_config()
        accounts = config.get("accounts", {})

        if not accounts:
            raise ConfigError(
                "No credentials configured. "
                "Set MP_USERNAME, MP_SECRET, MP_PROJECT_ID, MP_REGION environment variables, "
                "or add an account with add_account()."
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
        region, project_id = self._resolve_region_and_project_for_oauth()
        if region is None:
            return None

        storage = OAuthStorage(storage_dir=_oauth_storage_dir)
        tokens = storage.load_tokens(region)
        if tokens is None:
            return None

        # Skip expired tokens
        if tokens.is_expired():
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
    ) -> tuple[str | None, str | None]:
        """Determine region and project_id for OAuth token lookup.

        Checks in order:
        1. ``MP_REGION`` / ``MP_PROJECT_ID`` environment variables
        2. Default account from config file

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
        if not accounts:
            return None, None

        default_name = config.get("default")
        if default_name and isinstance(default_name, str) and default_name in accounts:
            account_data = accounts[default_name]
            return account_data.get("region"), account_data.get("project_id")

        # Use first account as fallback
        first_account = next(iter(accounts.values()))
        return first_account.get("region"), first_account.get("project_id")

    def _resolve_from_env(self) -> Credentials | None:
        """Attempt to resolve credentials from environment variables.

        Returns:
            Credentials if all env vars are set, None otherwise.
        """
        username = os.environ.get("MP_USERNAME")
        secret = os.environ.get("MP_SECRET")
        project_id = os.environ.get("MP_PROJECT_ID")
        region = os.environ.get("MP_REGION")

        # All four must be set to use env vars
        if username and secret and project_id and region:
            if region not in VALID_REGIONS:
                raise ConfigError(
                    f"Invalid MP_REGION: '{region}'. Must be 'us', 'eu', or 'in'."
                )
            return Credentials(
                username=username,
                secret=SecretStr(secret),
                project_id=project_id,
                region=cast(RegionType, region),
            )
        return None

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
