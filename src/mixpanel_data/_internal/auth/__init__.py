"""OAuth 2.0 PKCE authentication module.

Implements the OAuth 2.0 Authorization Code + PKCE flow for Mixpanel,
including Dynamic Client Registration (RFC 7591), token management,
and secure local storage.

Components:
- PkceChallenge: PKCE verifier/challenge generation (RFC 7636)
- OAuthTokens: Immutable token model with expiry tracking
- OAuthClientInfo: Cached DCR client registration info
- OAuthStorage: Secure JSON file storage for tokens and client info
- OAuthFlow: Flow orchestrator (login, token exchange, refresh)
- CallbackResult: Authorization callback result model
- ensure_client_registered: Dynamic Client Registration helper

Example:
    ```python
    from mixpanel_data._internal.auth import (
        PkceChallenge,
        OAuthTokens,
        OAuthClientInfo,
        OAuthStorage,
        OAuthFlow,
        CallbackResult,
    )

    challenge = PkceChallenge.generate()
    storage = OAuthStorage()
    flow = OAuthFlow(region="us", storage=storage)
    ```
"""

from mixpanel_data._internal.auth.callback_server import CallbackResult
from mixpanel_data._internal.auth.client_registration import ensure_client_registered
from mixpanel_data._internal.auth.flow import OAuthFlow
from mixpanel_data._internal.auth.pkce import PkceChallenge
from mixpanel_data._internal.auth.storage import OAuthStorage
from mixpanel_data._internal.auth.token import OAuthClientInfo, OAuthTokens

__all__ = [
    "CallbackResult",
    "OAuthFlow",
    "OAuthClientInfo",
    "OAuthStorage",
    "OAuthTokens",
    "PkceChallenge",
    "ensure_client_registered",
]
