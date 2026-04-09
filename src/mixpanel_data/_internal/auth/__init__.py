"""OAuth 2.0 PKCE authentication and Cowork bridge module.

Implements the OAuth 2.0 Authorization Code + PKCE flow for Mixpanel,
including Dynamic Client Registration (RFC 7591), token management,
secure local storage, and a JSON-based credential bridge for Claude
Cowork VMs.

Components:
- PkceChallenge: PKCE verifier/challenge generation (RFC 7636)
- OAuthTokens: Immutable token model with expiry tracking
- OAuthClientInfo: Cached DCR client registration info
- OAuthStorage: Secure JSON file storage for tokens and client info
- OAuthFlow: Flow orchestrator (login, token exchange, refresh)
- CallbackResult: Authorization callback result model
- ensure_client_registered: Dynamic Client Registration helper
- AuthBridgeFile: Cowork credential bridge file model
- detect_cowork: Detect Claude Cowork VM environment
- load_bridge_file: Load and validate bridge credentials
- find_bridge_file: Locate bridge file on disk
- write_bridge_file: Write bridge file with secure permissions
- bridge_to_credentials: Convert bridge to legacy Credentials
- bridge_to_resolved_session: Convert bridge to v2 ResolvedSession
- apply_bridge_custom_header: Set custom header env vars from bridge
- refresh_bridge_token: Refresh expired OAuth tokens in bridge

Example:
    ```python
    from mixpanel_data._internal.auth import (
        PkceChallenge,
        OAuthTokens,
        OAuthClientInfo,
        OAuthStorage,
        OAuthFlow,
        CallbackResult,
        AuthBridgeFile,
        detect_cowork,
        load_bridge_file,
    )

    challenge = PkceChallenge.generate()
    storage = OAuthStorage()
    flow = OAuthFlow(region="us", storage=storage)

    if detect_cowork():
        bridge = load_bridge_file()
    ```
"""

from mixpanel_data._internal.auth.bridge import (
    AuthBridgeFile,
    BridgeCustomHeader,
    BridgeOAuth,
    BridgeServiceAccount,
    apply_bridge_custom_header,
    bridge_to_credentials,
    bridge_to_resolved_session,
    detect_cowork,
    find_bridge_file,
    load_bridge_file,
    refresh_bridge_token,
    write_bridge_file,
)
from mixpanel_data._internal.auth.callback_server import CallbackResult
from mixpanel_data._internal.auth.client_registration import ensure_client_registered
from mixpanel_data._internal.auth.flow import OAuthFlow
from mixpanel_data._internal.auth.pkce import PkceChallenge
from mixpanel_data._internal.auth.storage import OAuthStorage
from mixpanel_data._internal.auth.token import OAuthClientInfo, OAuthTokens

__all__ = [
    "AuthBridgeFile",
    "BridgeCustomHeader",
    "BridgeOAuth",
    "BridgeServiceAccount",
    "CallbackResult",
    "OAuthFlow",
    "OAuthClientInfo",
    "OAuthStorage",
    "OAuthTokens",
    "PkceChallenge",
    "apply_bridge_custom_header",
    "bridge_to_credentials",
    "bridge_to_resolved_session",
    "detect_cowork",
    "ensure_client_registered",
    "find_bridge_file",
    "load_bridge_file",
    "refresh_bridge_token",
    "write_bridge_file",
]
