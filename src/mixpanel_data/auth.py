"""Public authentication and configuration module.

This module provides public access to credential management functionality.
It re-exports the ConfigManager and related types for public use.

Re-exported classes:
    ConfigManager: TOML-based account management (~/.mp/config.toml).
    Credentials: Immutable credential container with SecretStr for secrets.
    AccountInfo: Named account metadata (name, username, project_id, region).
    AuthMethod: Enum for authentication method selection (basic, oauth).
    AuthCredential: Standalone auth identity for v2 config (decoupled from project).
    CredentialType: Enum distinguishing service_account from oauth.
    ProjectContext: Project and optional workspace selection.
    ResolvedSession: Composition of AuthCredential + ProjectContext.
    AuthBridgeFile: Cowork credential bridge file model.
    detect_cowork: Detect Claude Cowork VM environment.
    load_bridge_file: Load and validate bridge credentials from disk.

For full documentation of these classes, see:
    mixpanel_data._internal.config, mixpanel_data._internal.auth_credential,
    mixpanel_data._internal.auth.bridge

Example usage:
    ```python
    from mixpanel_data.auth import ConfigManager, Credentials, AuthMethod

    config = ConfigManager()
    creds = config.resolve_credentials()

    # Cowork bridge
    from mixpanel_data.auth import AuthBridgeFile, detect_cowork, load_bridge_file

    if detect_cowork():
        bridge = load_bridge_file()
    ```
"""

from mixpanel_data._internal.auth.bridge import (
    AuthBridgeFile,
    detect_cowork,
    load_bridge_file,
)
from mixpanel_data._internal.auth_credential import (
    AuthCredential,
    CredentialType,
    ProjectContext,
    ResolvedSession,
)
from mixpanel_data._internal.config import (
    AccountInfo,
    AuthMethod,
    ConfigManager,
    Credentials,
)

__all__ = [
    "AccountInfo",
    "AuthBridgeFile",
    "AuthCredential",
    "AuthMethod",
    "ConfigManager",
    "Credentials",
    "CredentialType",
    "ProjectContext",
    "ResolvedSession",
    "detect_cowork",
    "load_bridge_file",
]
