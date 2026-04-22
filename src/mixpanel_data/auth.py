"""Public authentication and configuration module.

Re-exports the legacy ``ConfigManager`` / ``Credentials`` types and
the v2 :class:`BridgeFile` for callers that built against the
``mixpanel_data.auth`` namespace. Scheduled for narrowing in
T047 (B2): the canonical surface will move to
``mixpanel_data.auth_types`` per
``contracts/python-api.md``.

Re-exported classes:
    ConfigManager: Legacy TOML-based account management.
    Credentials: Legacy immutable credential container.
    AccountInfo: Legacy named-account metadata.
    AuthMethod: Legacy enum for authentication method selection.
    AuthCredential: v2 standalone auth identity.
    CredentialType: v2 enum distinguishing service_account from oauth.
    ProjectContext: v2 project + workspace selection.
    ResolvedSession: v2 composition of AuthCredential + ProjectContext.
    BridgeFile: v2 Cowork credential bridge schema.
    load_bridge: Load and validate a bridge file from disk.
"""

from mixpanel_data._internal.auth.bridge import (
    BridgeFile,
    load_bridge,
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
    "AuthCredential",
    "AuthMethod",
    "BridgeFile",
    "ConfigManager",
    "CredentialType",
    "Credentials",
    "ProjectContext",
    "ResolvedSession",
    "load_bridge",
]
