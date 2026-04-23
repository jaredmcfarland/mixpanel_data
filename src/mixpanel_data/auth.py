"""Public ``mixpanel_data.auth`` namespace — thin re-export of the v3 surface.

The 042 auth redesign moved the canonical types into focused
``_internal`` modules; this file exposes the public ones to callers who
built against the historical ``from mixpanel_data.auth import …`` import
path. New code should prefer the dedicated
:mod:`mixpanel_data.auth_types` module for the v3 surface
(``Account``, ``Session``, ``OAuthTokens``, …); this module is kept as a
compatibility shim for legacy callers.

Re-exported classes:
    ConfigManager: v3 TOML-based account/target/active management.
    Credentials: Legacy immutable credential container (api_client shim).
    AuthMethod: Legacy enum for authentication method selection.
    BridgeFile: v2 Cowork credential bridge schema.
    load_bridge: Load and validate a bridge file from disk.
"""

from mixpanel_data._internal.auth.bridge import (
    BridgeFile,
    load_bridge,
)
from mixpanel_data._internal.config import (
    AuthMethod,
    ConfigManager,
    Credentials,
)

__all__ = [
    "AuthMethod",
    "BridgeFile",
    "ConfigManager",
    "Credentials",
    "load_bridge",
]
