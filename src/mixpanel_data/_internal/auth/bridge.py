"""Auth bridge for Claude Cowork credential transfer (042 redesign — v2 schema).

The bridge is a JSON credential file that lets ``mixpanel_data``
authenticate inside a Claude Cowork VM by reading credentials a host
process exported. It embeds a full :class:`Account` discriminated-union
record (with secrets inline by design — Cowork crosses a trust
boundary), optional project / workspace pinning, and a custom-headers
map. Loaded as a synthetic config source by
:func:`~mixpanel_data._internal.auth.resolver.resolve_session`; the
writer side ships in Phase 8 (Cluster C2 of the 042 plan).

Bridge file search order (first existing file wins):
    1. Argument ``path`` to :func:`load_bridge` (if not None).
    2. ``MP_AUTH_FILE`` env var (if set).
    3. ``~/.claude/mixpanel/auth.json`` (default Cowork location).
    4. ``<cwd>/mixpanel_auth.json`` (workspace-mount fallback).

Reference: ``specs/042-auth-architecture-redesign/contracts/config-schema.md`` §2.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from mixpanel_data._internal.auth.account import Account
from mixpanel_data._internal.auth.token import OAuthTokens
from mixpanel_data.exceptions import ConfigError

logger = logging.getLogger(__name__)


class BridgeFile(BaseModel):
    """Cowork credential bridge file — v2 schema.

    Embeds a full :class:`~mixpanel_data._internal.auth.account.Account`
    record (with secrets inline) plus optional project / workspace pinning
    and a custom-headers map.

    Example:
        ```json
        {
          "version": 2,
          "account": {"type": "oauth_browser", "name": "personal", "region": "us"},
          "tokens": {"access_token": "...", "refresh_token": "...",
                     "expires_at": "2026-04-22T12:00:00Z",
                     "token_type": "Bearer", "scope": "read"},
          "project": "3713224",
          "workspace": 3448413,
          "headers": {"X-Mixpanel-Cluster": "internal-1"}
        }
        ```
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: Literal[2] = 2
    """Bridge schema version — always ``2``."""

    account: Account
    """Full Account discriminated-union record (with secrets inline by design)."""

    tokens: OAuthTokens | None = None
    """OAuth tokens — required iff ``account.type == "oauth_browser"``."""

    project: Annotated[str | None, Field(default=None, pattern=r"^\d+$")] = None
    """Optional pinned project ID (numeric string)."""

    workspace: PositiveInt | None = None
    """Optional pinned workspace ID."""

    headers: dict[str, str] = Field(default_factory=dict)
    """Custom HTTP headers attached to outbound requests at resolution time."""

    @model_validator(mode="after")
    def _validate_oauth_browser_has_tokens(self) -> BridgeFile:
        """Enforce that ``oauth_browser`` accounts include their tokens.

        Returns:
            The validated instance.

        Raises:
            ValueError: If ``account.type == "oauth_browser"`` and ``tokens``
                is missing.
        """
        if self.account.type == "oauth_browser" and self.tokens is None:
            raise ValueError("BridgeFile with oauth_browser account requires `tokens`.")
        return self


def default_bridge_search_paths() -> tuple[Path, ...]:
    """Return the default bridge file paths consulted in priority order.

    Returns:
        Tuple of candidate paths (default Cowork location first, then
        a ``mixpanel_auth.json`` in the current working directory). The
        ``MP_AUTH_FILE`` env var, if set, is consulted by callers BEFORE
        any default path.
    """
    return (
        Path.home() / ".claude" / "mixpanel" / "auth.json",
        Path.cwd() / "mixpanel_auth.json",
    )


_bridge_adapter: TypeAdapter[BridgeFile] = TypeAdapter(BridgeFile)


def load_bridge(path: Path | None = None) -> BridgeFile | None:
    """Load and validate a v2 bridge file from disk.

    Resolves the path in this order:

    1. Argument ``path`` (if not None).
    2. ``$MP_AUTH_FILE`` env var (if set).
    3. Default search paths (``~/.claude/mixpanel/auth.json``, then
       ``<cwd>/mixpanel_auth.json``) — first existing file wins.

    Args:
        path: Optional explicit bridge path.

    Returns:
        The parsed :class:`BridgeFile`, or ``None`` if no candidate
        path exists.

    Raises:
        ConfigError: If a candidate file exists but is malformed or fails
            schema validation.
    """
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path)
    elif "MP_AUTH_FILE" in os.environ and os.environ["MP_AUTH_FILE"]:
        candidates.append(Path(os.environ["MP_AUTH_FILE"]))
    else:
        candidates.extend(default_bridge_search_paths())

    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(
                f"Could not read bridge file at {candidate}: {exc}",
                details={"path": str(candidate)},
            ) from exc
        try:
            return _bridge_adapter.validate_python(payload)
        except ValidationError as exc:
            raise ConfigError(
                f"Invalid bridge file at {candidate}: "
                f"{exc.errors(include_url=False)[0]['msg']}",
                details={"path": str(candidate)},
            ) from exc
    return None


__all__ = [
    "BridgeFile",
    "default_bridge_search_paths",
    "load_bridge",
]
