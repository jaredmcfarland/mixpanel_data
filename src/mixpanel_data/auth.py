"""Public authentication and configuration module.

This module provides public access to credential management functionality.
It re-exports the ConfigManager and related types for public use.

Re-exported classes:
    ConfigManager: TOML-based account management (~/.mp/config.toml).
    Credentials: Immutable credential container with SecretStr for secrets.
    AccountInfo: Named account metadata (name, username, project_id, region).

For full documentation of these classes, see:
    mixpanel_data._internal.config

Example usage:
    from mixpanel_data.auth import ConfigManager, Credentials

    config = ConfigManager()
    creds = config.resolve_credentials()
"""

from mixpanel_data._internal.config import (
    AccountInfo,
    ConfigManager,
    Credentials,
)

__all__ = [
    "ConfigManager",
    "Credentials",
    "AccountInfo",
]
