"""V3 ``ConfigManager`` — single-schema TOML config CRUD.

The redesigned config has three primary sections — ``[active]``,
``[accounts.NAME]``, ``[targets.NAME]`` — plus optional ``[settings]``.
There is no ``config_version`` field; legacy v1/v2 configs are detected
and rejected with a precise multi-line ``ConfigError`` pointing at
``mp config convert``.

This module lives alongside the legacy ``config.py`` during the
transitional Phase 3-4 window. Phase 4 (T051/T052) deletes the legacy
v1/v2 paths and Phase 5 wires the CLI through this module exclusively.

Reference:
    ``specs/042-auth-architecture-redesign/contracts/config-schema.md`` §1.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - py3.10 fallback
    import tomli as tomllib  # type: ignore[import-not-found]

import tomli_w
from pydantic import SecretStr, TypeAdapter, ValidationError

from mixpanel_data._internal.auth.account import (
    Account,
    AccountType,
    OAuthBrowserAccount,
    OAuthTokenAccount,
    Region,
    ServiceAccount,
)
from mixpanel_data._internal.auth.session import ActiveSession
from mixpanel_data.exceptions import (
    AccountInUseError,
    ConfigError,
)
from mixpanel_data.types import AccountSummary, Target

if TYPE_CHECKING:
    pass


_LEGACY_DETECTED_MESSAGE = (
    "Legacy config schema detected at {path}.\n"
    "\n"
    "This version of mixpanel_data uses a single unified schema. Convert "
    "your config:\n"
    "\n"
    "  mp config convert\n"
    "\n"
    "After conversion, your old config will be archived as {path}.legacy."
)


_DEFAULT_CONFIG_PATH = Path.home() / ".mp" / "config.toml"


_account_adapter: TypeAdapter[Account] = TypeAdapter(Account)


def _is_legacy(raw: dict[str, Any]) -> bool:
    """Return True if the parsed TOML carries any v1 or v2 marker.

    Markers (any one triggers detection):
        - root key ``config_version`` (v2 marker)
        - root key ``default`` (v1 marker)
        - root section ``[credentials]`` (v2 marker)
        - root section ``[projects]`` (v2 marker)
        - inside any ``[accounts.X]``: a ``project_id`` key (v1 marker)

    Args:
        raw: Parsed TOML as a dict.

    Returns:
        ``True`` if any legacy marker is present.
    """
    if "config_version" in raw:
        return True
    if "default" in raw:
        return True
    if "credentials" in raw and isinstance(raw["credentials"], dict):
        return True
    if "projects" in raw and isinstance(raw["projects"], dict):
        return True
    accounts = raw.get("accounts")
    if isinstance(accounts, dict):
        for block in accounts.values():
            if isinstance(block, dict) and "project_id" in block:
                return True
    return False


def _account_from_block(name: str, block: dict[str, Any]) -> Account:
    """Construct an Account variant from a parsed ``[accounts.NAME]`` block.

    Args:
        name: Account name (matches the TOML block key).
        block: Parsed block contents.

    Returns:
        A frozen ``Account`` instance.

    Raises:
        ConfigError: On validation failure (missing required field, bad type,
            etc.); the wrapped Pydantic error is included for debuggability.
    """
    try:
        return _account_adapter.validate_python({"name": name, **block})
    except ValidationError as exc:
        raise ConfigError(
            f"Invalid [accounts.{name}] block: {exc.errors(include_url=False)[0]['msg']}"
        ) from exc


def _account_to_block(account: Account) -> dict[str, Any]:
    """Serialize an Account variant to a TOML-ready dict (excludes ``name``).

    Args:
        account: Frozen ``Account`` to serialize.

    Returns:
        Plain dict with ``type``, ``region``, and type-specific fields. Secrets
        are unwrapped to plain strings (TOML cannot store opaque ``SecretStr``).
    """
    out: dict[str, Any] = {"type": account.type, "region": account.region}
    if isinstance(account, ServiceAccount):
        out["username"] = account.username
        out["secret"] = account.secret.get_secret_value()
    elif isinstance(account, OAuthTokenAccount):
        if account.token is not None:
            out["token"] = account.token.get_secret_value()
        else:
            assert account.token_env is not None
            out["token_env"] = account.token_env
    # OAuthBrowserAccount has no extra fields.
    return out


class ConfigManager:
    """V3 single-schema configuration manager.

    Wraps a single ``~/.mp/config.toml`` file (or ``MP_CONFIG_PATH`` override).
    All operations re-read the file from disk, so concurrent edits are safe
    in the "last write wins" sense (no file locking — single-user workflow
    by design).

    Notes:
        - File creation enforces mode ``0o600`` and parent dir ``0o700``.
        - Legacy v1/v2 configs are detected on read and raise ``ConfigError``.
    """

    def __init__(self, *, config_path: Path | None = None) -> None:
        """Initialize the manager.

        Args:
            config_path: Path to the TOML config file. Defaults to
                ``$MP_CONFIG_PATH`` if set, else ``~/.mp/config.toml``.
        """
        if config_path is not None:
            self._path = config_path
        elif "MP_CONFIG_PATH" in os.environ:
            self._path = Path(os.environ["MP_CONFIG_PATH"])
        else:
            self._path = _DEFAULT_CONFIG_PATH

    @property
    def config_path(self) -> Path:
        """Return the path of the on-disk TOML config."""
        return self._path

    # ---- internals ---------------------------------------------------

    def _read_raw(self) -> dict[str, Any]:
        """Parse the TOML file and reject legacy schemas.

        Returns:
            Raw parsed dict. Empty dict if file does not exist.

        Raises:
            ConfigError: Malformed TOML or legacy schema detected.
        """
        if not self._path.exists():
            return {}
        try:
            raw: dict[str, Any] = tomllib.loads(
                self._path.read_text(encoding="utf-8")
            )
        except (tomllib.TOMLDecodeError, OSError) as exc:
            raise ConfigError(
                f"Could not parse config at {self._path}: {exc}"
            ) from exc
        if _is_legacy(raw):
            raise ConfigError(
                _LEGACY_DETECTED_MESSAGE.format(path=self._path),
                details={"path": str(self._path), "schema": "legacy"},
            )
        return raw

    def _write_raw(self, raw: dict[str, Any]) -> None:
        """Serialize ``raw`` to the config file with restrictive permissions.

        Creates parent dirs (``~/.mp/``) with mode ``0o700`` and writes the
        file with mode ``0o600``.

        Args:
            raw: Dict to serialize as TOML.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Tighten parent dir permissions in case it pre-existed with 0o755.
        try:
            self._path.parent.chmod(stat.S_IRWXU)
        except OSError:
            pass
        old_umask = os.umask(0o177)
        try:
            self._path.write_bytes(tomli_w.dumps(raw).encode("utf-8"))
        finally:
            os.umask(old_umask)
        try:
            self._path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    # ---- accounts ----------------------------------------------------

    def list_accounts(self) -> list[AccountSummary]:
        """Return a sorted list of ``AccountSummary`` for every configured account.

        Returns:
            Sorted-by-name list of summaries. Each summary's ``is_active``
            is ``True`` iff ``[active].account == summary.name``;
            ``referenced_by_targets`` lists target names that reference it.
        """
        raw = self._read_raw()
        accounts_block = raw.get("accounts", {}) or {}
        targets_block = raw.get("targets", {}) or {}
        active_block = raw.get("active", {}) or {}
        active_account = active_block.get("account")

        # Build account → referencing-target list.
        refs: dict[str, list[str]] = {}
        for tname, tblock in sorted(targets_block.items()):
            if isinstance(tblock, dict):
                acct = tblock.get("account")
                if isinstance(acct, str):
                    refs.setdefault(acct, []).append(tname)

        out: list[AccountSummary] = []
        for name in sorted(accounts_block):
            block = accounts_block[name]
            if not isinstance(block, dict):
                continue
            account = _account_from_block(name, block)
            out.append(
                AccountSummary(
                    name=account.name,
                    type=account.type,
                    region=account.region,
                    is_active=(active_account == account.name),
                    referenced_by_targets=refs.get(account.name, []),
                )
            )
        return out

    def get_account(self, name: str) -> Account:
        """Return the ``Account`` for ``name`` (raises if missing).

        Args:
            name: Account name.

        Returns:
            The frozen ``Account`` variant.

        Raises:
            ConfigError: If ``name`` is not configured.
        """
        raw = self._read_raw()
        accounts_block = raw.get("accounts", {}) or {}
        block = accounts_block.get(name)
        if not isinstance(block, dict):
            raise ConfigError(f"Account '{name}' not found.")
        return _account_from_block(name, block)

    def add_account(
        self,
        name: str,
        *,
        type: AccountType,
        region: Region,
        username: str | None = None,
        secret: SecretStr | str | None = None,
        token: SecretStr | str | None = None,
        token_env: str | None = None,
    ) -> Account:
        """Add an account block to the config.

        Args:
            name: Account name (must match ``^[a-zA-Z0-9_-]{1,64}$``).
            type: One of ``service_account`` / ``oauth_browser`` / ``oauth_token``.
            region: One of ``us`` / ``eu`` / ``in``.
            username: Required for ``service_account``.
            secret: Required for ``service_account``.
            token: For ``oauth_token`` (mutually exclusive with ``token_env``).
            token_env: For ``oauth_token`` (mutually exclusive with ``token``).

        Returns:
            The constructed ``Account``.

        Raises:
            ConfigError: Duplicate name, validation failure, or referential
                integrity violation.
        """
        raw = self._read_raw()
        accounts_block = raw.setdefault("accounts", {})
        if name in accounts_block:
            raise ConfigError(f"Account '{name}' already exists.")

        # Build a clean block by type.
        block: dict[str, Any] = {"type": type, "region": region}
        if type == "service_account":
            if username is None or secret is None:
                raise ConfigError(
                    "ServiceAccount requires `username` and `secret`."
                )
            block["username"] = username
            block["secret"] = (
                secret.get_secret_value()
                if isinstance(secret, SecretStr)
                else secret
            )
        elif type == "oauth_browser":
            # No extra fields.
            pass
        elif type == "oauth_token":
            if (token is None) == (token_env is None):
                raise ConfigError(
                    "OAuthTokenAccount requires exactly one of `token` or `token_env`."
                )
            if token is not None:
                block["token"] = (
                    token.get_secret_value()
                    if isinstance(token, SecretStr)
                    else token
                )
            else:
                assert token_env is not None
                block["token_env"] = token_env
        else:  # pragma: no cover — Literal exhaustiveness
            raise ConfigError(f"Unknown account type: {type!r}")

        # Validate via the Account model so we catch bad name/region.
        try:
            account = _account_adapter.validate_python({"name": name, **block})
        except ValidationError as exc:
            raise ConfigError(
                f"Invalid account fields for '{name}': "
                f"{exc.errors(include_url=False)[0]['msg']}"
            ) from exc

        accounts_block[name] = _account_to_block(account)
        self._write_raw(raw)
        return account

    def remove_account(
        self, name: str, *, force: bool = False
    ) -> list[str]:
        """Remove an account.

        Args:
            name: Account to remove.
            force: When ``True``, remove the account even if it's referenced
                by targets; the orphaned target names are returned. When
                ``False``, raises ``AccountInUseError`` if any target
                references the account.

        Returns:
            Sorted list of target names that referenced the account (empty
            unless the account was referenced).

        Raises:
            ConfigError: If the account does not exist.
            AccountInUseError: If the account is referenced and ``force=False``.
        """
        raw = self._read_raw()
        accounts_block = raw.get("accounts", {}) or {}
        if name not in accounts_block:
            raise ConfigError(f"Account '{name}' not found.")
        targets_block = raw.get("targets", {}) or {}
        referenced = sorted(
            tname
            for tname, tblock in targets_block.items()
            if isinstance(tblock, dict) and tblock.get("account") == name
        )
        if referenced and not force:
            raise AccountInUseError(name, referenced_by=referenced)
        del accounts_block[name]
        self._write_raw(raw)
        return referenced

    # ---- active ------------------------------------------------------

    def get_active(self) -> ActiveSession:
        """Return the persisted ``[active]`` block as an ``ActiveSession``.

        Returns:
            ``ActiveSession`` with the three optional fields. Missing block
            yields an empty ``ActiveSession()``.

        Raises:
            ConfigError: If a referenced account does not exist.
        """
        raw = self._read_raw()
        active_block = raw.get("active", {}) or {}
        try:
            return ActiveSession.model_validate(active_block)
        except ValidationError as exc:
            raise ConfigError(
                f"Invalid [active] block: {exc.errors(include_url=False)[0]['msg']}"
            ) from exc

    def set_active(
        self,
        *,
        account: str | None = None,
        project: str | None = None,
        workspace: int | None = None,
    ) -> ActiveSession:
        """Update one or more axes in the ``[active]`` block.

        Each kwarg is independent: passing only ``project=X`` updates that
        axis and leaves the other two untouched. Passing ``None`` for an
        axis leaves it untouched (use ``clear_active`` to remove keys).

        Args:
            account: New active account name (must reference an existing
                ``[accounts.X]``).
            project: New active project ID (must match ``^\\d+$``).
            workspace: New active workspace ID (positive int).

        Returns:
            The updated ``ActiveSession``.

        Raises:
            ConfigError: Validation failure or referential integrity violation.
        """
        raw = self._read_raw()
        active_block = raw.setdefault("active", {})

        if account is not None:
            accounts_block = raw.get("accounts", {}) or {}
            if account not in accounts_block:
                raise ConfigError(
                    f"Cannot set active account: '{account}' is not configured."
                )
            active_block["account"] = account
        if project is not None:
            self._validate_project_id(project)
            active_block["project"] = project
        if workspace is not None:
            self._validate_workspace_id(workspace)
            active_block["workspace"] = workspace

        self._write_raw(raw)
        return self.get_active()

    def clear_active(
        self,
        *,
        account: bool = False,
        project: bool = False,
        workspace: bool = False,
    ) -> ActiveSession:
        """Remove specific axes from the ``[active]`` block.

        Args:
            account: Drop ``account`` axis if True.
            project: Drop ``project`` axis if True.
            workspace: Drop ``workspace`` axis if True.

        Returns:
            The updated ``ActiveSession`` after removals.
        """
        raw = self._read_raw()
        active_block = raw.get("active", {}) or {}
        if account and "account" in active_block:
            del active_block["account"]
        if project and "project" in active_block:
            del active_block["project"]
        if workspace and "workspace" in active_block:
            del active_block["workspace"]
        if active_block:
            raw["active"] = active_block
        else:
            raw.pop("active", None)
        self._write_raw(raw)
        return self.get_active()

    # ---- targets -----------------------------------------------------

    def list_targets(self) -> list[Target]:
        """Return a sorted-by-name list of ``Target`` records.

        Returns:
            All configured targets.

        Raises:
            ConfigError: If a target block fails validation.
        """
        raw = self._read_raw()
        targets_block = raw.get("targets", {}) or {}
        out: list[Target] = []
        for name in sorted(targets_block):
            block = targets_block[name]
            if not isinstance(block, dict):
                continue
            try:
                out.append(Target(name=name, **block))
            except ValidationError as exc:
                raise ConfigError(
                    f"Invalid [targets.{name}] block: "
                    f"{exc.errors(include_url=False)[0]['msg']}"
                ) from exc
        return out

    def get_target(self, name: str) -> Target:
        """Return the ``Target`` for ``name`` (raises if missing).

        Args:
            name: Target name.

        Returns:
            The frozen ``Target`` instance.

        Raises:
            ConfigError: If ``name`` is not configured.
        """
        raw = self._read_raw()
        targets_block = raw.get("targets", {}) or {}
        block = targets_block.get(name)
        if not isinstance(block, dict):
            raise ConfigError(f"Target '{name}' not found.")
        try:
            return Target(name=name, **block)
        except ValidationError as exc:
            raise ConfigError(
                f"Invalid [targets.{name}] block: "
                f"{exc.errors(include_url=False)[0]['msg']}"
            ) from exc

    def add_target(
        self,
        name: str,
        *,
        account: str,
        project: str,
        workspace: int | None = None,
    ) -> Target:
        """Add a target block to the config.

        Args:
            name: Target name (block key).
            account: Referenced account name (must exist).
            project: Project ID (digit string).
            workspace: Optional workspace ID (positive int).

        Returns:
            The constructed ``Target``.

        Raises:
            ConfigError: Duplicate name, missing account, or validation failure.
        """
        raw = self._read_raw()
        accounts_block = raw.get("accounts", {}) or {}
        if account not in accounts_block:
            raise ConfigError(
                f"Cannot create target '{name}': account '{account}' is not configured."
            )
        targets_block = raw.setdefault("targets", {})
        if name in targets_block:
            raise ConfigError(f"Target '{name}' already exists.")

        try:
            target = Target(
                name=name, account=account, project=project, workspace=workspace
            )
        except ValidationError as exc:
            raise ConfigError(
                f"Invalid target fields for '{name}': "
                f"{exc.errors(include_url=False)[0]['msg']}"
            ) from exc

        block: dict[str, Any] = {"account": account, "project": project}
        if workspace is not None:
            block["workspace"] = workspace
        targets_block[name] = block
        self._write_raw(raw)
        return target

    def remove_target(self, name: str) -> None:
        """Remove a target block from the config.

        Args:
            name: Target name to remove.

        Raises:
            ConfigError: If the target does not exist.
        """
        raw = self._read_raw()
        targets_block = raw.get("targets", {}) or {}
        if name not in targets_block:
            raise ConfigError(f"Target '{name}' not found.")
        del targets_block[name]
        self._write_raw(raw)

    def apply_target(self, name: str) -> ActiveSession:
        """Write the target's three axes to ``[active]`` in a single save.

        Args:
            name: Target to apply.

        Returns:
            The updated ``ActiveSession``.

        Raises:
            ConfigError: If the target does not exist OR its referenced
                account is no longer configured.
        """
        target = self.get_target(name)
        raw = self._read_raw()
        accounts_block = raw.get("accounts", {}) or {}
        if target.account not in accounts_block:
            raise ConfigError(
                f"Cannot apply target '{name}': account '{target.account}' "
                f"is not configured."
            )
        active_block: dict[str, Any] = {
            "account": target.account,
            "project": target.project,
        }
        if target.workspace is not None:
            active_block["workspace"] = target.workspace
        # apply_target is a single atomic write: replace [active] wholesale
        # so a target with no workspace clears any prior workspace.
        raw["active"] = active_block
        self._write_raw(raw)
        return self.get_active()

    # ---- settings ----------------------------------------------------

    def get_custom_header(self) -> tuple[str, str] | None:
        """Return ``(name, value)`` for ``[settings].custom_header`` if present.

        Returns:
            Tuple ``(name, value)`` or ``None``.

        Raises:
            ConfigError: If the block is malformed (missing keys, wrong types).
        """
        raw = self._read_raw()
        settings = raw.get("settings", {}) or {}
        header = settings.get("custom_header")
        if header is None:
            return None
        if not isinstance(header, dict):
            raise ConfigError(
                "[settings].custom_header must be an inline table {name=, value=}."
            )
        name = header.get("name")
        value = header.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise ConfigError(
                "[settings].custom_header requires `name` and `value` strings."
            )
        return (name, value)

    def set_custom_header(self, *, name: str, value: str) -> None:
        """Write the custom HTTP header to ``[settings].custom_header``.

        Args:
            name: Header name (e.g., ``X-Mixpanel-Cluster``).
            value: Header value.
        """
        raw = self._read_raw()
        settings = raw.setdefault("settings", {})
        settings["custom_header"] = {"name": name, "value": value}
        self._write_raw(raw)

    # ---- validators --------------------------------------------------

    @staticmethod
    def _validate_project_id(project: str) -> None:
        """Validate a project ID matches Mixpanel's wire format (digit string).

        Args:
            project: Candidate ID.

        Raises:
            ConfigError: If ``project`` is not a non-empty digit string.
        """
        if not project or not project.isdigit():
            raise ConfigError(
                f"Invalid project ID: {project!r}. Must match `^\\d+$`."
            )

    @staticmethod
    def _validate_workspace_id(workspace: int) -> None:
        """Validate a workspace ID is positive.

        Args:
            workspace: Candidate ID.

        Raises:
            ConfigError: If ``workspace`` is not a positive integer.
        """
        if not isinstance(workspace, int) or workspace <= 0:
            raise ConfigError(
                f"Invalid workspace ID: {workspace!r}. Must be a positive integer."
            )


__all__ = [
    "ConfigManager",
]
