"""Public authentication and configuration module.

Re-exports the v3 :class:`ConfigManager`, the legacy
:class:`Credentials` / :class:`AuthMethod` shim types, and the v2
:class:`BridgeFile` for callers that built against the
``mixpanel_data.auth`` namespace. Scheduled for narrowing in T047
(B2): the canonical surface moves to ``mixpanel_data.auth_types`` per
``contracts/python-api.md``.

Re-exported classes:
    ConfigManager: v3 TOML-based account/target/active management.
    Credentials: Legacy immutable credential container (api_client shim).
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
    AuthMethod,
    ConfigManager,
    Credentials,
)

__all__ = [
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
