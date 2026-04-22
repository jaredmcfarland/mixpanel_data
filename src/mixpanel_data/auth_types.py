"""Public auth-types module — single source of truth for the v3 auth surface.

Consolidates the stable types from the ``_internal/auth/*`` package into
one importable module so callers can ``from mixpanel_data.auth_types
import Account, Session, ...`` without reaching into ``_internal``.

The actual class definitions still live under ``_internal/auth/`` because
they need to share helper functions and a mature module structure;
``auth_types`` re-exports them so the public surface is one focused
import path. ``mixpanel_data.__init__`` imports from here too, which
keeps the top-level ``mp.Account`` / ``mp.Session`` / etc. names backed
by the same single source.

Reference: ``specs/042-auth-architecture-redesign/contracts/python-api.md``,
PR #126 review Fix 27.
"""

from mixpanel_data._internal.auth.account import (
    Account,
    AccountType,
    OAuthBrowserAccount,
    OAuthTokenAccount,
    Region,
    ServiceAccount,
    TokenResolver,
)
from mixpanel_data._internal.auth.bridge import BridgeFile, load_bridge
from mixpanel_data._internal.auth.session import (
    ActiveSession,
    Project,
    Session,
    WorkspaceRef,
)
from mixpanel_data._internal.auth.token import OAuthClientInfo, OAuthTokens
from mixpanel_data._internal.auth.token_resolver import OnDiskTokenResolver

__all__ = [
    # Discriminated-union account type + variants
    "Account",
    "AccountType",
    "OAuthBrowserAccount",
    "OAuthTokenAccount",
    "ServiceAccount",
    "Region",
    # Session + axes
    "ActiveSession",
    "Project",
    "Session",
    "WorkspaceRef",
    # OAuth token plumbing
    "OAuthClientInfo",
    "OAuthTokens",
    "TokenResolver",
    "OnDiskTokenResolver",
    # Cowork bridge
    "BridgeFile",
    "load_bridge",
]
