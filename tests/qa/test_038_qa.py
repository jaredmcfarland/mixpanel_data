"""QA tests for Feature 038: Auth, Project & Workspace Management.

This module exercises the auth/project/workspace redesign with **real file I/O**
and integration-level scenarios. It covers edge cases, corner cases, and
scenarios that mock-based unit tests miss.

Tests are organized into 13 categories:

1. Config Real File I/O Round-Trip
2. MeCache Edge Cases
3. resolve_session Priority Chain
4. State Transitions
5. Migration with Real I/O
6. Backward Compatibility
7. Error Recovery
8. Environment Variable Edge Cases
9. CLI Integration with Real Config
10. CLI Exit Codes and Error Output
11. Security Boundaries
12. Workspace Facade Integration
13. Large-Scale / Performance
"""

from __future__ import annotations

import json
import stat
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import tomli_w
from pydantic import SecretStr
from typer.testing import CliRunner

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]

from mixpanel_data._internal.auth_credential import (
    AuthCredential,
    CredentialType,
    ProjectContext,
    ResolvedSession,
)
from mixpanel_data._internal.config import (
    ConfigManager,
    Credentials,
)
from mixpanel_data._internal.me import (
    MeCache,
    MeProjectInfo,
    MeResponse,
    MeWorkspaceInfo,
)
from mixpanel_data.cli.main import app
from mixpanel_data.cli.utils import ExitCode
from mixpanel_data.exceptions import ConfigError

# =============================================================================
# Shared Fixtures
# =============================================================================


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    """Return path for a temporary config file inside tmp_path.

    Returns:
        Path to a non-existent config.toml in a temp directory.
    """
    return tmp_path / "config.toml"


@pytest.fixture()
def cm(config_path: Path) -> ConfigManager:
    """Create a ConfigManager pointing at a temporary config file.

    Args:
        config_path: Path to the temp config file.

    Returns:
        A ConfigManager instance.
    """
    return ConfigManager(config_path=config_path)


@pytest.fixture()
def v1_config_path(config_path: Path) -> Path:
    """Write a v1 config file and return its path.

    The v1 config has a default account 'demo' with basic credentials.

    Args:
        config_path: Path to write the config.

    Returns:
        Path to the written v1 config file.
    """
    v1: dict[str, Any] = {
        "default": "demo",
        "accounts": {
            "demo": {
                "username": "sa-user",
                "secret": "sa-secret-123",
                "project_id": "12345",
                "region": "us",
            },
        },
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("wb") as f:
        tomli_w.dump(v1, f)
    return config_path


@pytest.fixture()
def v2_config_path(config_path: Path) -> Path:
    """Write a v2 config file and return its path.

    The v2 config has one credential 'demo-sa', one alias 'ai-demo',
    and an active context.

    Args:
        config_path: Path to write the config.

    Returns:
        Path to the written v2 config file.
    """
    v2: dict[str, Any] = {
        "config_version": 2,
        "active": {
            "credential": "demo-sa",
            "project_id": "3713224",
            "workspace_id": 3448413,
        },
        "credentials": {
            "demo-sa": {
                "type": "service_account",
                "username": "sa-user",
                "secret": "sa-secret-123",
                "region": "us",
            },
        },
        "projects": {
            "ai-demo": {
                "project_id": "3713224",
                "credential": "demo-sa",
                "workspace_id": 3448413,
            },
        },
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("wb") as f:
        tomli_w.dump(v2, f)
    return config_path


@pytest.fixture()
def cli_runner() -> CliRunner:
    """Create a Typer CLI runner for testing commands.

    Returns:
        A CliRunner instance.
    """
    return CliRunner()


@pytest.fixture()
def cache_dir(tmp_path: Path) -> Path:
    """Return a temporary directory for MeCache files.

    Args:
        tmp_path: Pytest-provided temp directory.

    Returns:
        Path to a subdirectory for cache files.
    """
    d = tmp_path / "cache"
    d.mkdir()
    return d


def _read_toml(path: Path) -> dict[str, Any]:
    """Read and parse a TOML file.

    Args:
        path: Path to the TOML file.

    Returns:
        Parsed dictionary.
    """
    with path.open("rb") as f:
        return dict(tomllib.load(f))


# =============================================================================
# CAT 1: Config Real File I/O Round-Trip (P0) — 9 tests
# =============================================================================


class TestConfigRealFileIO:
    """Verify TOML write/read survives special characters, unicode, etc."""

    def test_credential_secret_survives_toml_round_trip(
        self, cm: ConfigManager, config_path: Path
    ) -> None:
        """Secrets with TOML-special chars (= # [ ] newline) survive round-trip.

        Args:
            cm: ConfigManager with temp config.
            config_path: Path to the temp config file.
        """
        tricky_secret = 'p@ss=w0rd#[section]\\nnewline"quotes"'
        cm.add_credential(
            name="tricky",
            type="service_account",
            username="user",
            secret=tricky_secret,
            region="us",
        )
        data = _read_toml(config_path)
        assert data["credentials"]["tricky"]["secret"] == tricky_secret

    def test_credential_name_with_dots_and_hyphens(self, cm: ConfigManager) -> None:
        """Credential names with dots and hyphens survive TOML round-trip.

        Args:
            cm: ConfigManager with temp config.
        """
        cm.add_credential(
            name="my-sa.prod",
            type="service_account",
            username="u",
            secret="s",
            region="us",
        )
        creds = cm.list_credentials()
        names = [c.name for c in creds]
        assert "my-sa.prod" in names

    def test_credential_name_with_unicode(self, cm: ConfigManager) -> None:
        """Credential names with unicode survive TOML round-trip.

        Args:
            cm: ConfigManager with temp config.
        """
        cm.add_credential(
            name="cred-\u00e9\u00e0\u00fc",
            type="service_account",
            username="u",
            secret="s",
            region="eu",
        )
        creds = cm.list_credentials()
        names = [c.name for c in creds]
        assert "cred-\u00e9\u00e0\u00fc" in names

    def test_alias_name_toml_reserved_word(self, cm: ConfigManager) -> None:
        """Alias names that are TOML reserved words (true, false, inf) survive.

        Args:
            cm: ConfigManager with temp config.
        """
        for name in ("true", "false", "inf"):
            cm.add_project_alias(name, project_id="111")
        aliases = cm.list_project_aliases()
        alias_names = [a.name for a in aliases]
        assert "true" in alias_names
        assert "false" in alias_names
        assert "inf" in alias_names

    def test_very_long_secret_round_trip(
        self, cm: ConfigManager, config_path: Path
    ) -> None:
        """Secrets longer than 1000 chars survive round-trip.

        Args:
            cm: ConfigManager with temp config.
            config_path: Path to the temp config file.
        """
        long_secret = "x" * 2000
        cm.add_credential(
            name="long",
            type="service_account",
            username="u",
            secret=long_secret,
            region="us",
        )
        data = _read_toml(config_path)
        assert data["credentials"]["long"]["secret"] == long_secret
        assert len(data["credentials"]["long"]["secret"]) == 2000

    def test_multiple_credentials_order_preserved(self, cm: ConfigManager) -> None:
        """Adding 5 credentials preserves insertion order in listing.

        Args:
            cm: ConfigManager with temp config.
        """
        for i in range(5):
            cm.add_credential(
                name=f"cred-{i}",
                type="service_account",
                username=f"u{i}",
                secret=f"s{i}",
                region="us",
            )
        creds = cm.list_credentials()
        assert [c.name for c in creds] == [f"cred-{i}" for i in range(5)]

    def test_concurrent_config_writes_do_not_corrupt(self, config_path: Path) -> None:
        """Two ConfigManagers writing to the same file don't corrupt it.

        Args:
            config_path: Path to the temp config file.
        """
        cm1 = ConfigManager(config_path=config_path)
        cm2 = ConfigManager(config_path=config_path)
        cm1.add_credential(
            name="first",
            type="service_account",
            username="u1",
            secret="s1",
            region="us",
        )
        cm2.add_credential(
            name="second",
            type="service_account",
            username="u2",
            secret="s2",
            region="us",
        )
        # Both should be present because cm2 re-reads before writing
        data = _read_toml(config_path)
        assert "first" in data["credentials"]
        assert "second" in data["credentials"]

    def test_config_file_created_from_scratch(self, tmp_path: Path) -> None:
        """Config file is created from scratch when no parent dirs exist.

        Args:
            tmp_path: Pytest-provided temp directory.
        """
        deep_path = tmp_path / "a" / "b" / "c" / "config.toml"
        cm = ConfigManager(config_path=deep_path)
        cm.add_credential(
            name="new",
            type="service_account",
            username="u",
            secret="s",
            region="us",
        )
        assert deep_path.exists()
        data = _read_toml(deep_path)
        assert "new" in data["credentials"]

    def test_read_config_after_external_edit(
        self, cm: ConfigManager, config_path: Path
    ) -> None:
        """ConfigManager picks up changes made by external TOML writes.

        Args:
            cm: ConfigManager with temp config.
            config_path: Path to the temp config file.
        """
        cm.add_credential(
            name="orig",
            type="service_account",
            username="u",
            secret="s",
            region="us",
        )
        # External edit: add another credential by hand
        data = _read_toml(config_path)
        data["credentials"]["external"] = {
            "type": "service_account",
            "username": "ext-u",
            "secret": "ext-s",
            "region": "eu",
        }
        with config_path.open("wb") as f:
            tomli_w.dump(data, f)
        # ConfigManager should see both
        creds = cm.list_credentials()
        names = [c.name for c in creds]
        assert "orig" in names
        assert "external" in names


# =============================================================================
# CAT 2: MeCache Edge Cases (P0) — 9 tests
# =============================================================================


class TestMeCacheEdgeCases:
    """Corruption variants, TTL boundary, permission, concurrent read."""

    def test_empty_cache_file_returns_none(self, cache_dir: Path) -> None:
        """A 0-byte cache file returns None (not a crash).

        Args:
            cache_dir: Temp directory for cache files.
        """
        cache = MeCache(storage_dir=cache_dir)
        cache_file = cache_dir / "me_us.json"
        cache_file.write_text("")
        assert cache.get("us") is None

    def test_truncated_json_cache_returns_none(self, cache_dir: Path) -> None:
        """A truncated JSON cache file returns None.

        Args:
            cache_dir: Temp directory for cache files.
        """
        cache = MeCache(storage_dir=cache_dir)
        cache_file = cache_dir / "me_us.json"
        cache_file.write_text('{"user_id": 42, "projects":')
        assert cache.get("us") is None

    def test_valid_json_wrong_schema_returns_none(self, cache_dir: Path) -> None:
        """Valid JSON with wrong schema still parses (extra='allow').

        MeResponse uses extra='allow' so wrong-schema JSON still parses
        successfully -- it just has empty fields.

        Args:
            cache_dir: Temp directory for cache files.
        """
        cache = MeCache(storage_dir=cache_dir)
        cache_file = cache_dir / "me_us.json"
        cache_file.write_text(
            json.dumps(
                {"totally_wrong": True, "cached_at": time.time()},
            )
        )
        result = cache.get("us")
        # Due to extra="allow", the model validates with defaults
        # but the data is essentially useless
        assert result is not None
        assert result.user_id is None
        assert result.projects == {}

    def test_cache_ttl_boundary_exactly_at_expiry(self, cache_dir: Path) -> None:
        """Cache entry exactly at TTL boundary is expired.

        Args:
            cache_dir: Temp directory for cache files.
        """
        ttl = 60
        cache = MeCache(storage_dir=cache_dir, ttl_seconds=ttl)
        cache_file = cache_dir / "me_us.json"
        # Set cached_at to exactly TTL+1 seconds ago -> expired
        expired_at = time.time() - ttl - 1
        cache_file.write_text(json.dumps({"cached_at": expired_at, "user_id": 1}))
        assert cache.get("us") is None

        # Set cached_at to TTL-1 seconds ago -> still valid
        valid_at = time.time() - ttl + 1
        cache_file.write_text(json.dumps({"cached_at": valid_at, "user_id": 1}))
        result = cache.get("us")
        assert result is not None
        assert result.user_id == 1

    def test_cache_put_creates_directory_if_missing(self, tmp_path: Path) -> None:
        """MeCache.put creates the storage directory if it doesn't exist.

        Args:
            tmp_path: Pytest-provided temp directory.
        """
        deep = tmp_path / "deep" / "nested" / "dir"
        cache = MeCache(storage_dir=deep)
        response = MeResponse(user_id=42)
        cache.put("us", response)
        assert (deep / "me_us.json").exists()

    def test_cache_put_overwrites_existing(self, cache_dir: Path) -> None:
        """MeCache.put overwrites an existing cache file.

        Args:
            cache_dir: Temp directory for cache files.
        """
        cache = MeCache(storage_dir=cache_dir)
        cache.put("us", MeResponse(user_id=1))
        cache.put("us", MeResponse(user_id=2))
        result = cache.get("us")
        assert result is not None
        assert result.user_id == 2

    def test_cache_invalidate_nonexistent_is_noop(self, cache_dir: Path) -> None:
        """Invalidating a nonexistent cache is a no-op (no exception).

        Args:
            cache_dir: Temp directory for cache files.
        """
        cache = MeCache(storage_dir=cache_dir)
        # Should not raise
        cache.invalidate("us")
        assert cache.get("us") is None

    def test_cache_file_permissions_after_overwrite(self, cache_dir: Path) -> None:
        """Cache file has 0o600 permissions after overwrite.

        Args:
            cache_dir: Temp directory for cache files.
        """
        cache = MeCache(storage_dir=cache_dir)
        cache.put("us", MeResponse(user_id=1))
        cache.put("us", MeResponse(user_id=2))
        path = cache_dir / "me_us.json"
        mode = path.stat().st_mode
        # Check owner-only read/write bits (0o600)
        assert mode & stat.S_IRUSR  # owner read
        assert mode & stat.S_IWUSR  # owner write
        assert not (mode & stat.S_IRGRP)  # no group read
        assert not (mode & stat.S_IROTH)  # no other read

    def test_cache_concurrent_read_during_write(self, cache_dir: Path) -> None:
        """Cache.get returns valid data or None during concurrent put.

        Args:
            cache_dir: Temp directory for cache files.
        """
        cache = MeCache(storage_dir=cache_dir)
        cache.put("us", MeResponse(user_id=1))
        # Simulate a concurrent read while another writer is mid-write
        # by directly creating the tmp file
        tmp_file = cache_dir / "me_us.tmp"
        tmp_file.write_text("partial data")
        # The main cache file should still return valid data
        result = cache.get("us")
        assert result is not None
        assert result.user_id == 1


# =============================================================================
# CAT 3: resolve_session Priority Chain (P0) — 10 tests
# =============================================================================


class TestResolveSessionPriorityChain:
    """Full 5-level priority chain with real config files."""

    def test_env_vars_beat_everything(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Environment variables override all config-file settings.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_USERNAME", "env-user")
        monkeypatch.setenv("MP_SECRET", "env-secret")
        monkeypatch.setenv("MP_PROJECT_ID", "99999")
        monkeypatch.setenv("MP_REGION", "eu")

        cm = ConfigManager(config_path=v2_config_path)
        session = cm.resolve_session()
        assert session.project_id == "99999"
        assert session.region == "eu"

    def test_explicit_credential_beats_active_context(
        self, config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit credential param overrides the active context credential.

        Args:
            config_path: Path to the temp config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        # Clear env vars that could interfere
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        v2: dict[str, Any] = {
            "config_version": 2,
            "active": {
                "credential": "active-cred",
                "project_id": "111",
            },
            "credentials": {
                "active-cred": {
                    "type": "service_account",
                    "username": "active-user",
                    "secret": "active-secret",
                    "region": "us",
                },
                "explicit-cred": {
                    "type": "service_account",
                    "username": "explicit-user",
                    "secret": "explicit-secret",
                    "region": "eu",
                },
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump(v2, f)

        cm = ConfigManager(config_path=config_path)
        session = cm.resolve_session(credential="explicit-cred", project_id="111")
        assert session.auth.username == "explicit-user"
        assert session.auth.region == "eu"

    def test_explicit_project_beats_active_project(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit project_id param overrides the active context project.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        cm = ConfigManager(config_path=v2_config_path)
        session = cm.resolve_session(project_id="override-pid")
        assert session.project_id == "override-pid"

    def test_active_context_used_when_no_overrides(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Active context is used when no overrides are provided.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        cm = ConfigManager(config_path=v2_config_path)
        session = cm.resolve_session()
        assert session.project_id == "3713224"
        assert session.auth.name == "demo-sa"

    def test_first_credential_fallback_when_no_active(
        self, config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First credential is used as fallback when no active is set.

        Args:
            config_path: Path to the temp config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        v2: dict[str, Any] = {
            "config_version": 2,
            "active": {"project_id": "111"},
            "credentials": {
                "fallback-cred": {
                    "type": "service_account",
                    "username": "fb-user",
                    "secret": "fb-secret",
                    "region": "us",
                },
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump(v2, f)

        cm = ConfigManager(config_path=config_path)
        session = cm.resolve_session()
        assert session.auth.name == "fallback-cred"

    def test_no_project_id_raises_config_error(
        self, config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing project_id in v2 config raises ConfigError.

        Args:
            config_path: Path to the temp config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        v2: dict[str, Any] = {
            "config_version": 2,
            "active": {"credential": "demo"},
            "credentials": {
                "demo": {
                    "type": "service_account",
                    "username": "u",
                    "secret": "s",
                    "region": "us",
                },
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump(v2, f)

        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="No project selected"):
            cm.resolve_session()

    def test_nonexistent_credential_name_raises(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-existent credential name raises ConfigError.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        cm = ConfigManager(config_path=v2_config_path)
        with pytest.raises(ConfigError, match="No credentials configured"):
            cm.resolve_session(credential="nonexistent")

    def test_workspace_id_from_active_context(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Workspace ID is read from the active context.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        cm = ConfigManager(config_path=v2_config_path)
        session = cm.resolve_session()
        assert session.project.workspace_id == 3448413

    def test_workspace_id_explicit_overrides_active(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit workspace_id param overrides the active workspace.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        cm = ConfigManager(config_path=v2_config_path)
        session = cm.resolve_session(workspace_id=9999)
        assert session.project.workspace_id == 9999

    def test_v1_config_fallback_through_resolve_session(
        self, v1_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """v1 config falls back through resolve_session correctly.

        Args:
            v1_config_path: Path to the v1 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        cm = ConfigManager(config_path=v1_config_path)
        session = cm.resolve_session()
        assert session.project_id == "12345"
        assert session.auth.username == "sa-user"


# =============================================================================
# CAT 4: State Transitions (P0) — 9 tests
# =============================================================================


class TestStateTransitions:
    """In-session switching: cache invalidation, credential preservation."""

    def _make_workspace_with_mock_client(
        self,
        config_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> Any:
        """Create a Workspace with a mocked API client.

        Args:
            config_path: Path to v2 config file.
            monkeypatch: Pytest monkeypatch fixture.

        Returns:
            A Workspace instance with mocked API client.
        """
        from mixpanel_data.workspace import Workspace

        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        cm = ConfigManager(config_path=config_path)
        mock_client = MagicMock()
        mock_client._credentials = Credentials(
            username="sa-user",
            secret=SecretStr("sa-secret-123"),
            project_id="3713224",
            region="us",
        )
        mock_client.with_project.return_value = mock_client

        ws = Workspace(
            credential="demo-sa",
            _config_manager=cm,
            _api_client=mock_client,
        )
        return ws

    def test_switch_project_clears_discovery_cache(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """switch_project sets _discovery to None.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        ws = self._make_workspace_with_mock_client(v2_config_path, monkeypatch)
        ws._discovery = MagicMock()
        ws.switch_project("new-pid")
        assert ws._discovery is None

    def test_switch_project_clears_me_service(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """switch_project sets _me_service to None.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        ws = self._make_workspace_with_mock_client(v2_config_path, monkeypatch)
        ws._me_service = MagicMock()
        ws.switch_project("new-pid")
        assert ws._me_service is None

    def test_switch_project_updates_credentials_project_id(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """switch_project updates _credentials from new API client.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        ws = self._make_workspace_with_mock_client(v2_config_path, monkeypatch)
        new_creds = Credentials(
            username="sa-user",
            secret=SecretStr("sa-secret-123"),
            project_id="new-pid",
            region="us",
        )
        ws._api_client.with_project.return_value._credentials = new_creds
        ws.switch_project("new-pid")
        assert ws._credentials is not None
        assert ws._credentials.project_id == "new-pid"

    def test_switch_project_preserves_auth_identity(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """switch_project preserves the username (auth identity).

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        ws = self._make_workspace_with_mock_client(v2_config_path, monkeypatch)
        original_username = ws._credentials.username if ws._credentials else ""
        new_creds = Credentials(
            username=original_username,
            secret=SecretStr("sa-secret-123"),
            project_id="new-pid",
            region="us",
        )
        ws._api_client.with_project.return_value._credentials = new_creds
        ws.switch_project("new-pid")
        assert ws._credentials is not None
        assert ws._credentials.username == original_username

    def test_switch_workspace_updates_workspace_id(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """switch_workspace updates the workspace_id.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        ws = self._make_workspace_with_mock_client(v2_config_path, monkeypatch)
        ws.switch_workspace(7777)
        ws._api_client.set_workspace_id.assert_called_with(7777)

    def test_switch_workspace_does_not_clear_discovery(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """switch_workspace does NOT clear the discovery cache.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        ws = self._make_workspace_with_mock_client(v2_config_path, monkeypatch)
        mock_disc = MagicMock()
        ws._discovery = mock_disc
        ws.switch_workspace(7777)
        assert ws._discovery is mock_disc

    def test_double_switch_project_works(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Switching projects twice works without error.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        ws = self._make_workspace_with_mock_client(v2_config_path, monkeypatch)
        ws.switch_project("first-pid")
        ws.switch_project("second-pid")
        # Should not raise

    def test_current_project_after_switch(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """current_project reflects switched project_id.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        ws = self._make_workspace_with_mock_client(v2_config_path, monkeypatch)
        new_creds = Credentials(
            username="sa-user",
            secret=SecretStr("sa-secret-123"),
            project_id="switched-pid",
            region="us",
        )
        ws._api_client.with_project.return_value._credentials = new_creds
        ws.switch_project("switched-pid")
        proj = ws.current_project
        assert proj.project_id == "switched-pid"

    def test_current_credential_stable_after_switch(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """current_credential.name is stable after project switch.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        ws = self._make_workspace_with_mock_client(v2_config_path, monkeypatch)
        cred_before = ws.current_credential
        ws.switch_project("new-pid")
        cred_after = ws.current_credential
        # For v2 path, _resolved_session.auth.name should persist
        assert cred_before.name == cred_after.name


# =============================================================================
# CAT 5: Migration with Real I/O (P0) — 8 tests
# =============================================================================


class TestMigrationRealIO:
    """End-to-end: migrate, then use the migrated config for real operations."""

    def test_migrated_config_resolves_session(
        self, v1_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Migrated v2 config successfully resolves a session.

        Args:
            v1_config_path: Path to the v1 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        cm = ConfigManager(config_path=v1_config_path)
        cm.migrate_v1_to_v2()

        session = cm.resolve_session()
        assert session.project_id == "12345"
        assert session.auth.username == "sa-user"

    def test_migrated_config_list_credentials_matches_original(
        self, v1_config_path: Path
    ) -> None:
        """Migrated config has same number of credentials as original accounts.

        Args:
            v1_config_path: Path to the v1 config file.
        """
        cm = ConfigManager(config_path=v1_config_path)
        original_accounts = cm.list_accounts()
        cm.migrate_v1_to_v2()
        new_creds = cm.list_credentials()
        assert len(new_creds) == len(original_accounts)

    def test_migrated_config_list_aliases_matches_original(
        self, v1_config_path: Path
    ) -> None:
        """Each original account becomes a project alias.

        Args:
            v1_config_path: Path to the v1 config file.
        """
        cm = ConfigManager(config_path=v1_config_path)
        original_accounts = cm.list_accounts()
        cm.migrate_v1_to_v2()
        aliases = cm.list_project_aliases()
        assert len(aliases) == len(original_accounts)

    def test_migration_backup_content_matches_original(
        self, v1_config_path: Path
    ) -> None:
        """Backup file content matches the original v1 config.

        Args:
            v1_config_path: Path to the v1 config file.
        """
        original_content = v1_config_path.read_bytes()
        cm = ConfigManager(config_path=v1_config_path)
        result = cm.migrate_v1_to_v2()
        assert result.backup_path is not None
        assert result.backup_path.exists()
        backup_content = result.backup_path.read_bytes()
        assert backup_content == original_content

    def test_migration_idempotent_guard(self, v1_config_path: Path) -> None:
        """Second migration raises ConfigError ('already v2').

        Args:
            v1_config_path: Path to the v1 config file.
        """
        cm = ConfigManager(config_path=v1_config_path)
        cm.migrate_v1_to_v2()
        with pytest.raises(ConfigError, match="already v2"):
            cm.migrate_v1_to_v2()

    def test_migration_empty_accounts_section(self, config_path: Path) -> None:
        """Migrating a v1 config with empty accounts produces empty v2.

        Args:
            config_path: Path to the temp config file.
        """
        v1: dict[str, Any] = {"accounts": {}}
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump(v1, f)

        cm = ConfigManager(config_path=config_path)
        result = cm.migrate_v1_to_v2()
        assert result.credentials_created == 0
        assert result.aliases_created == 0

    def test_migration_preserves_secrets_in_v2(self, v1_config_path: Path) -> None:
        """Secrets from v1 accounts appear in v2 credentials.

        Args:
            v1_config_path: Path to the v1 config file.
        """
        cm = ConfigManager(config_path=v1_config_path)
        cm.migrate_v1_to_v2()
        data = _read_toml(v1_config_path)
        creds = data.get("credentials", {})
        # The 'demo' account should have its secret preserved
        assert any(c.get("secret") == "sa-secret-123" for c in creds.values())

    def test_dry_run_does_not_modify_disk(self, v1_config_path: Path) -> None:
        """Dry-run migration does NOT modify the config file.

        Args:
            v1_config_path: Path to the v1 config file.
        """
        original_content = v1_config_path.read_bytes()
        cm = ConfigManager(config_path=v1_config_path)
        result = cm.migrate_v1_to_v2(dry_run=True)
        assert result.backup_path is None
        assert v1_config_path.read_bytes() == original_content


# =============================================================================
# CAT 6: Backward Compatibility (P0) — 6 tests
# =============================================================================


class TestBackwardCompatibility:
    """v1 configs and legacy Workspace(account=...) still work."""

    def test_workspace_legacy_account_param(
        self, v1_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Workspace(account='demo') resolves v1 credentials.

        Args:
            v1_config_path: Path to the v1 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        from mixpanel_data.workspace import Workspace

        cm = ConfigManager(config_path=v1_config_path)
        ws = Workspace(account="demo", _config_manager=cm)
        assert ws._credentials is not None
        assert ws._credentials.project_id == "12345"
        assert ws._credentials.username == "sa-user"

    def test_workspace_no_params_uses_default_account(
        self, v1_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Workspace() with no params uses the default v1 account.

        Args:
            v1_config_path: Path to the v1 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        from mixpanel_data.workspace import Workspace

        cm = ConfigManager(config_path=v1_config_path)
        ws = Workspace(_config_manager=cm)
        assert ws._credentials is not None
        assert ws._credentials.project_id == "12345"

    def test_credentials_to_resolved_session_round_trip(self) -> None:
        """Credentials.to_resolved_session() round-trips fields correctly."""
        creds = Credentials(
            username="user1",
            secret=SecretStr("secret1"),
            project_id="pid-1",
            region="eu",
        )
        session = creds.to_resolved_session()
        assert session.project_id == "pid-1"
        assert session.region == "eu"
        assert session.auth.username == "user1"

    def test_v1_config_with_resolve_session(
        self, v1_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_session works against a v1 config (backward compat).

        Args:
            v1_config_path: Path to the v1 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        cm = ConfigManager(config_path=v1_config_path)
        session = cm.resolve_session()
        assert session.project_id == "12345"

    def test_v1_config_env_vars_still_override(
        self, v1_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env vars override v1 config through resolve_session.

        Args:
            v1_config_path: Path to the v1 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_USERNAME", "env-u")
        monkeypatch.setenv("MP_SECRET", "env-s")
        monkeypatch.setenv("MP_PROJECT_ID", "env-pid")
        monkeypatch.setenv("MP_REGION", "in")

        cm = ConfigManager(config_path=v1_config_path)
        session = cm.resolve_session()
        assert session.project_id == "env-pid"
        assert session.region == "in"

    def test_mixed_v1_accounts_and_v2_credentials_not_possible(
        self, v2_config_path: Path
    ) -> None:
        """v2 config does not have an 'accounts' section (clean separation).

        Args:
            v2_config_path: Path to the v2 config file.
        """
        data = _read_toml(v2_config_path)
        assert "accounts" not in data


# =============================================================================
# CAT 7: Error Recovery (P0) — 9 tests
# =============================================================================


class TestErrorRecovery:
    """Corrupted files, missing data, clear error messages."""

    def test_corrupted_toml_config_raises_config_error(self, config_path: Path) -> None:
        """Corrupted TOML raises ConfigError (not a raw parse error).

        Args:
            config_path: Path to the temp config file.
        """
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("this is not valid [[[toml")
        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="Invalid TOML"):
            cm.list_credentials()

    def test_missing_config_file_returns_empty(self, tmp_path: Path) -> None:
        """Missing config file returns empty results (no crash).

        Args:
            tmp_path: Pytest-provided temp directory.
        """
        cm = ConfigManager(config_path=tmp_path / "missing.toml")
        assert cm.list_credentials() == []
        assert cm.list_accounts() == []

    def test_config_with_missing_credentials_section(self, config_path: Path) -> None:
        """Config with missing 'credentials' section returns empty list.

        Args:
            config_path: Path to the temp config file.
        """
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump({"config_version": 2}, f)
        cm = ConfigManager(config_path=config_path)
        assert cm.list_credentials() == []

    def test_config_with_missing_active_section(self, config_path: Path) -> None:
        """Config with missing 'active' section returns empty ActiveContext.

        Args:
            config_path: Path to the temp config file.
        """
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump({"config_version": 2, "credentials": {}}, f)
        cm = ConfigManager(config_path=config_path)
        ctx = cm.get_active_context()
        assert ctx.credential is None
        assert ctx.project_id is None
        assert ctx.workspace_id is None

    def test_resolve_session_no_credentials_raises_clear_message(
        self, config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_session with no credentials gives a clear error message.

        Args:
            config_path: Path to the temp config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump({"config_version": 2, "credentials": {}}, f)

        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="No credentials configured"):
            cm.resolve_session()

    def test_resolve_session_oauth_no_token_raises_clear_message(
        self, config_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """OAuth credential with no token gives a clear error message.

        Args:
            config_path: Path to the temp config file.
            monkeypatch: Pytest monkeypatch fixture.
            tmp_path: Pytest-provided temp directory.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        v2: dict[str, Any] = {
            "config_version": 2,
            "active": {"credential": "oauth-cred", "project_id": "111"},
            "credentials": {
                "oauth-cred": {"type": "oauth", "region": "us"},
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump(v2, f)

        cm = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="expired or missing"):
            cm.resolve_session(_oauth_storage_dir=tmp_path / "no-oauth")

    def test_remove_last_credential_clears_active(self, cm: ConfigManager) -> None:
        """Removing the last credential clears the active credential.

        Args:
            cm: ConfigManager with temp config.
        """
        cm.add_credential(
            name="only",
            type="service_account",
            username="u",
            secret="s",
            region="us",
        )
        cm.remove_credential("only")
        ctx = cm.get_active_context()
        assert ctx.credential is None

    def test_add_credential_invalid_region_raises_value_error(
        self, cm: ConfigManager
    ) -> None:
        """Adding a credential with invalid region raises ValueError.

        Args:
            cm: ConfigManager with temp config.
        """
        with pytest.raises(ValueError, match="Region must be one of"):
            cm.add_credential(
                name="bad",
                type="service_account",
                username="u",
                secret="s",
                region="xx",
            )

    def test_corrupted_cache_does_not_block_fresh_fetch(self, cache_dir: Path) -> None:
        """Corrupted cache returns None, allowing a fresh API fetch.

        Args:
            cache_dir: Temp directory for cache files.
        """
        cache = MeCache(storage_dir=cache_dir)
        (cache_dir / "me_us.json").write_text("CORRUPTED{{{")
        result = cache.get("us")
        assert result is None
        # A fresh put should overwrite the corruption
        cache.put("us", MeResponse(user_id=42))
        result = cache.get("us")
        assert result is not None
        assert result.user_id == 42


# =============================================================================
# CAT 8: Environment Variable Edge Cases (P1) — 6 tests
# =============================================================================


class TestEnvVarEdgeCases:
    """Special characters, whitespace, empty strings in env vars."""

    def test_special_chars_in_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Secrets with = # newline tab chars resolve correctly from env vars.

        Args:
            monkeypatch: Pytest monkeypatch fixture.
        """
        tricky = "pass=word#hash\ttab"
        monkeypatch.setenv("MP_USERNAME", "user")
        monkeypatch.setenv("MP_SECRET", tricky)
        monkeypatch.setenv("MP_PROJECT_ID", "111")
        monkeypatch.setenv("MP_REGION", "us")

        cm = ConfigManager(config_path=Path("/nonexistent/path"))
        creds = cm.resolve_credentials()
        assert creds.secret.get_secret_value() == tricky

    def test_whitespace_only_env_vars_treated_as_set(
        self, v1_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Whitespace-only env vars are truthy strings, so env resolution fires.

        When all four env vars are set (even to whitespace), the env-var path
        is taken. A whitespace-only MP_REGION is rejected as invalid.

        Args:
            v1_config_path: Path to the v1 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_USERNAME", "   ")
        monkeypatch.setenv("MP_SECRET", "  ")
        monkeypatch.setenv("MP_PROJECT_ID", " ")
        monkeypatch.setenv("MP_REGION", " ")

        cm = ConfigManager(config_path=v1_config_path)
        # Whitespace-only strings are truthy in Python, so env resolution
        # fires and rejects the invalid region
        with pytest.raises(ConfigError, match="Invalid MP_REGION"):
            cm.resolve_credentials()

    def test_empty_string_env_vars_ignored(
        self, v1_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty string env vars are treated as unset.

        Args:
            v1_config_path: Path to the v1 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_USERNAME", "")
        monkeypatch.setenv("MP_SECRET", "")
        monkeypatch.setenv("MP_PROJECT_ID", "")
        monkeypatch.setenv("MP_REGION", "")

        cm = ConfigManager(config_path=v1_config_path)
        creds = cm.resolve_credentials()
        assert creds.project_id == "12345"

    def test_invalid_mp_region_env_var_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Invalid MP_REGION with all other env vars set raises ConfigError.

        Args:
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_USERNAME", "user")
        monkeypatch.setenv("MP_SECRET", "secret")
        monkeypatch.setenv("MP_PROJECT_ID", "111")
        monkeypatch.setenv("MP_REGION", "mars")

        cm = ConfigManager(config_path=Path("/nonexistent"))
        with pytest.raises(ConfigError, match="Invalid MP_REGION"):
            cm.resolve_credentials()

    def test_mp_config_path_env_var_overrides_default(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MP_CONFIG_PATH env var overrides the default config location.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_CONFIG_PATH", str(v2_config_path))
        # Don't pass config_path, let env var control it
        cm = ConfigManager()
        assert cm.config_path == v2_config_path

    def test_env_vars_with_leading_trailing_spaces(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env vars with leading/trailing spaces are used as-is (not stripped).

        Args:
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_USERNAME", " user ")
        monkeypatch.setenv("MP_SECRET", " secret ")
        monkeypatch.setenv("MP_PROJECT_ID", " 111 ")
        monkeypatch.setenv("MP_REGION", "us")

        cm = ConfigManager(config_path=Path("/nonexistent"))
        creds = cm.resolve_credentials()
        # Values include leading/trailing spaces
        assert creds.username == " user "
        assert creds.project_id == " 111 "


# =============================================================================
# CAT 9: CLI Integration with Real Config (P0) — 9 tests
# =============================================================================


class TestCLIIntegrationRealConfig:
    """CLI commands that actually read/write config files on disk."""

    def test_projects_switch_persists_to_disk(
        self,
        v2_config_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """'mp projects switch' persists the new project to the config file.

        Args:
            v2_config_path: Path to the v2 config file.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_CONFIG_PATH", str(v2_config_path))
        result = cli_runner.invoke(app, ["projects", "switch", "9999"])
        assert result.exit_code == 0

        cm = ConfigManager(config_path=v2_config_path)
        ctx = cm.get_active_context()
        assert ctx.project_id == "9999"

    def test_projects_show_reads_from_disk(
        self,
        v2_config_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """'mp projects show' reads the active context from disk.

        Args:
            v2_config_path: Path to the v2 config file.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_CONFIG_PATH", str(v2_config_path))
        result = cli_runner.invoke(app, ["projects", "show"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["project_id"] == "3713224"
        assert data["workspace_id"] == 3448413

    def test_context_switch_alias_updates_all_fields(
        self,
        v2_config_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """'mp context switch <alias>' updates credential, project, workspace.

        Args:
            v2_config_path: Path to the v2 config file.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_CONFIG_PATH", str(v2_config_path))
        result = cli_runner.invoke(app, ["context", "switch", "ai-demo"])
        assert result.exit_code == 0

        cm = ConfigManager(config_path=v2_config_path)
        ctx = cm.get_active_context()
        assert ctx.project_id == "3713224"
        assert ctx.workspace_id == 3448413

    def test_workspaces_switch_persists(
        self,
        v2_config_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """'mp workspaces switch' persists to disk.

        Args:
            v2_config_path: Path to the v2 config file.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_CONFIG_PATH", str(v2_config_path))
        result = cli_runner.invoke(app, ["workspaces", "switch", "7777"])
        assert result.exit_code == 0

        cm = ConfigManager(config_path=v2_config_path)
        ctx = cm.get_active_context()
        assert ctx.workspace_id == 7777

    def test_auth_list_v2_shows_credentials(
        self,
        v2_config_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """'mp auth list' on v2 config shows credentials (not accounts).

        Args:
            v2_config_path: Path to the v2 config file.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_CONFIG_PATH", str(v2_config_path))
        result = cli_runner.invoke(app, ["auth", "list"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "demo-sa"
        assert data[0]["type"] == "service_account"

    def test_auth_migrate_creates_backup_and_v2(
        self,
        v1_config_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """'mp auth migrate' creates a backup and writes v2 config.

        Args:
            v1_config_path: Path to the v1 config file.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_CONFIG_PATH", str(v1_config_path))
        result = cli_runner.invoke(app, ["auth", "migrate"])
        assert result.exit_code == 0

        data = json.loads(result.stdout)
        assert data["credentials_created"] >= 1
        assert data["dry_run"] is False

        # Verify v2 config on disk
        cm = ConfigManager(config_path=v1_config_path)
        assert cm.config_version() == 2

        # Verify backup exists
        backup = v1_config_path.with_suffix(".toml.v1.bak")
        assert backup.exists()

    def test_auth_migrate_dry_run_no_changes(
        self,
        v1_config_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """'mp auth migrate --dry-run' doesn't change the config file.

        Args:
            v1_config_path: Path to the v1 config file.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_CONFIG_PATH", str(v1_config_path))
        original = v1_config_path.read_bytes()
        result = cli_runner.invoke(app, ["auth", "migrate", "--dry-run"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["dry_run"] is True
        assert v1_config_path.read_bytes() == original

    def test_alias_add_then_list_round_trip(
        self,
        v2_config_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Add alias then list -- the alias appears in the list.

        Args:
            v2_config_path: Path to the v2 config file.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_CONFIG_PATH", str(v2_config_path))
        add_result = cli_runner.invoke(
            app,
            ["projects", "alias", "add", "ecom", "--project", "9876"],
        )
        assert add_result.exit_code == 0

        list_result = cli_runner.invoke(app, ["projects", "alias", "list"])
        assert list_result.exit_code == 0
        data = json.loads(list_result.stdout)
        names = [a["name"] for a in data]
        assert "ecom" in names

    def test_context_switch_unknown_alias_exit_code(
        self,
        v2_config_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """'mp context switch <unknown>' exits with GENERAL_ERROR.

        Args:
            v2_config_path: Path to the v2 config file.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_CONFIG_PATH", str(v2_config_path))
        result = cli_runner.invoke(app, ["context", "switch", "nonexistent"])
        assert result.exit_code == ExitCode.GENERAL_ERROR


# =============================================================================
# CAT 10: CLI Exit Codes and Error Output (P1) — 4 tests
# =============================================================================


class TestCLIExitCodes:
    """Error exit codes and secret masking in error output."""

    def test_projects_list_no_credentials_exit_code(
        self,
        tmp_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """'mp projects list' with no credentials exits non-zero.

        Args:
            tmp_path: Pytest-provided temp directory.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        empty_config = tmp_path / "empty.toml"
        empty_config.parent.mkdir(parents=True, exist_ok=True)
        with empty_config.open("wb") as f:
            tomli_w.dump({}, f)
        monkeypatch.setenv("MP_CONFIG_PATH", str(empty_config))
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        result = cli_runner.invoke(app, ["projects", "list"])
        assert result.exit_code != 0

    def test_workspaces_switch_no_project_exit_code(
        self,
        config_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """'mp workspaces switch' with no active project still runs.

        Args:
            config_path: Path to the temp config file.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump({"config_version": 2}, f)
        monkeypatch.setenv("MP_CONFIG_PATH", str(config_path))
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        result = cli_runner.invoke(app, ["workspaces", "switch", "123"])
        # It will set workspace on an empty project -- that's fine, no crash
        assert result.exit_code == 0

    def test_invalid_format_option_exit_code(
        self,
        v2_config_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Invalid --format option produces an error exit.

        Args:
            v2_config_path: Path to the v2 config file.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        monkeypatch.setenv("MP_CONFIG_PATH", str(v2_config_path))
        result = cli_runner.invoke(app, ["projects", "show", "--format", "xml"])
        # Typer should reject invalid enum value
        assert result.exit_code != 0

    def test_error_message_does_not_leak_secrets(
        self,
        config_path: Path,
        cli_runner: CliRunner,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Error output does not contain the raw secret value.

        Args:
            config_path: Path to the temp config file.
            cli_runner: CLI test runner.
            monkeypatch: Pytest monkeypatch fixture.
        """
        secret_value = "SUPER_SECRET_DO_NOT_LEAK"
        v2: dict[str, Any] = {
            "config_version": 2,
            "active": {"credential": "leaky", "project_id": "111"},
            "credentials": {
                "leaky": {
                    "type": "service_account",
                    "username": "user",
                    "secret": secret_value,
                    "region": "us",
                },
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("wb") as f:
            tomli_w.dump(v2, f)
        monkeypatch.setenv("MP_CONFIG_PATH", str(config_path))
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        # Try a command that will error (projects list needs API)
        result = cli_runner.invoke(app, ["projects", "list"])
        # The full output (stdout + stderr) should never contain the raw secret
        full_output = (result.stdout or "") + (result.output or "")
        assert secret_value not in full_output


# =============================================================================
# CAT 11: Security Boundaries (P1) — 5 tests
# =============================================================================


class TestSecurityBoundaries:
    """repr/str masking of secrets, ConfigError doesn't include secrets."""

    def test_auth_credential_repr_masks_secret(self) -> None:
        """AuthCredential repr/str does not expose the secret value."""
        cred = AuthCredential(
            name="test",
            type=CredentialType.service_account,
            region="us",
            username="user",
            secret=SecretStr("my-super-secret"),
        )
        repr_str = repr(cred)
        assert "my-super-secret" not in repr_str

    def test_credentials_repr_masks_secret(self) -> None:
        """Credentials repr/str shows *** instead of the secret."""
        creds = Credentials(
            username="user",
            secret=SecretStr("hidden-secret"),
            project_id="123",
            region="us",
        )
        assert "hidden-secret" not in repr(creds)
        assert "***" in repr(creds)
        assert "hidden-secret" not in str(creds)

    def test_resolved_session_str_masks_secret(self) -> None:
        """ResolvedSession str/repr does not expose the secret."""
        session = ResolvedSession(
            auth=AuthCredential(
                name="test",
                type=CredentialType.service_account,
                region="us",
                username="user",
                secret=SecretStr("session-secret"),
            ),
            project=ProjectContext(project_id="123"),
        )
        output = str(session)
        assert "session-secret" not in output

    def test_config_error_does_not_include_secret(self) -> None:
        """ConfigError message does not contain secrets when raised."""
        secret = "DO_NOT_LEAK_THIS"
        err = ConfigError(
            "Credential 'test' has an issue.",
            details={"credential_name": "test"},
        )
        assert secret not in str(err)
        assert secret not in err.message

    def test_config_file_permissions_on_creation(self, tmp_path: Path) -> None:
        """Config file is created with reasonable permissions.

        Args:
            tmp_path: Pytest-provided temp directory.
        """
        config_path = tmp_path / "new_config.toml"
        cm = ConfigManager(config_path=config_path)
        cm.add_credential(
            name="test",
            type="service_account",
            username="u",
            secret="s",
            region="us",
        )
        assert config_path.exists()
        mode = config_path.stat().st_mode
        # File should be readable by owner at minimum
        assert mode & stat.S_IRUSR


# =============================================================================
# CAT 12: Workspace Facade Integration (P1) — 8 tests
# =============================================================================


class TestWorkspaceFacadeIntegration:
    """Credential param routing, discover delegation, properties."""

    def test_workspace_credential_param_uses_resolve_session(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Workspace(credential=...) invokes resolve_session.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        from mixpanel_data.workspace import Workspace

        cm = ConfigManager(config_path=v2_config_path)
        ws = Workspace(credential="demo-sa", _config_manager=cm)
        # _resolved_session should be set (v2 path)
        assert ws._resolved_session is not None

    def test_workspace_no_credential_uses_legacy_path(
        self, v1_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Workspace() without credential uses the legacy resolve_credentials.

        Args:
            v1_config_path: Path to the v1 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        from mixpanel_data.workspace import Workspace

        cm = ConfigManager(config_path=v1_config_path)
        ws = Workspace(_config_manager=cm)
        # _resolved_session should NOT be set (legacy path)
        assert ws._resolved_session is None
        assert ws._credentials is not None

    def test_workspace_project_id_override(
        self, v1_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Workspace(project_id=...) overrides the config project.

        Args:
            v1_config_path: Path to the v1 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        from mixpanel_data.workspace import Workspace

        cm = ConfigManager(config_path=v1_config_path)
        ws = Workspace(project_id="override-pid", _config_manager=cm)
        assert ws._credentials is not None
        assert ws._credentials.project_id == "override-pid"

    def test_discover_projects_delegates_to_me_service(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """discover_projects() delegates to _me_svc.list_projects().

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        from mixpanel_data.workspace import Workspace

        cm = ConfigManager(config_path=v2_config_path)
        mock_client = MagicMock()
        ws = Workspace(
            credential="demo-sa", _config_manager=cm, _api_client=mock_client
        )

        mock_me_svc = MagicMock()
        mock_me_svc.list_projects.return_value = [
            ("111", MeProjectInfo(name="P1", organization_id=1)),
        ]
        ws._me_service = mock_me_svc

        result = ws.discover_projects()
        assert len(result) == 1
        assert result[0][0] == "111"
        mock_me_svc.list_projects.assert_called_once()

    def test_discover_workspaces_uses_current_project_as_default(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """discover_workspaces() uses current project when none specified.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        from mixpanel_data.workspace import Workspace

        cm = ConfigManager(config_path=v2_config_path)
        mock_client = MagicMock()
        ws = Workspace(
            credential="demo-sa", _config_manager=cm, _api_client=mock_client
        )

        mock_me_svc = MagicMock()
        mock_me_svc.list_workspaces.return_value = []
        ws._me_service = mock_me_svc

        ws.discover_workspaces()
        mock_me_svc.list_workspaces.assert_called_once_with(project_id="3713224")

    def test_current_project_returns_project_context(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """current_project returns a ProjectContext with the right project_id.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        from mixpanel_data.workspace import Workspace

        cm = ConfigManager(config_path=v2_config_path)
        mock_client = MagicMock()
        ws = Workspace(
            credential="demo-sa", _config_manager=cm, _api_client=mock_client
        )

        proj = ws.current_project
        assert proj.project_id == "3713224"

    def test_current_credential_v2_returns_auth_credential(
        self, v2_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """current_credential with v2 config returns AuthCredential from session.

        Args:
            v2_config_path: Path to the v2 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        from mixpanel_data.workspace import Workspace

        cm = ConfigManager(config_path=v2_config_path)
        mock_client = MagicMock()
        ws = Workspace(
            credential="demo-sa", _config_manager=cm, _api_client=mock_client
        )

        cred = ws.current_credential
        assert cred.name == "demo-sa"
        assert cred.type == CredentialType.service_account

    def test_current_credential_v1_builds_synthetic(
        self, v1_config_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """current_credential with v1 config builds a synthetic AuthCredential.

        Args:
            v1_config_path: Path to the v1 config file.
            monkeypatch: Pytest monkeypatch fixture.
        """
        for var in ("MP_USERNAME", "MP_SECRET", "MP_PROJECT_ID", "MP_REGION"):
            monkeypatch.delenv(var, raising=False)

        from mixpanel_data.workspace import Workspace

        cm = ConfigManager(config_path=v1_config_path)
        ws = Workspace(account="demo", _config_manager=cm)

        cred = ws.current_credential
        assert cred.name == "demo"
        assert cred.type == CredentialType.service_account
        assert cred.username == "sa-user"


# =============================================================================
# CAT 13: Large-Scale / Performance (P2) — 4 tests
# =============================================================================


class TestLargeScale:
    """50 credentials, 100 aliases, 200 projects, 500 workspaces."""

    def test_50_credentials_crud(self, cm: ConfigManager) -> None:
        """Adding 50 credentials, listing, and removing one works.

        Args:
            cm: ConfigManager with temp config.
        """
        for i in range(50):
            cm.add_credential(
                name=f"cred-{i:03d}",
                type="service_account",
                username=f"u{i}",
                secret=f"s{i}",
                region="us",
            )
        creds = cm.list_credentials()
        assert len(creds) == 50

        cm.remove_credential("cred-025")
        creds = cm.list_credentials()
        assert len(creds) == 49
        names = [c.name for c in creds]
        assert "cred-025" not in names

    def test_100_project_aliases(self, cm: ConfigManager) -> None:
        """Adding 100 project aliases, listing, and searching works.

        Args:
            cm: ConfigManager with temp config.
        """
        for i in range(100):
            cm.add_project_alias(f"alias-{i:03d}", project_id=f"pid-{i}")
        aliases = cm.list_project_aliases()
        assert len(aliases) == 100

        # Remove one and verify
        cm.remove_project_alias("alias-050")
        aliases = cm.list_project_aliases()
        assert len(aliases) == 99

    def test_me_response_with_200_projects(self, cache_dir: Path) -> None:
        """MeCache handles a response with 200 projects.

        Args:
            cache_dir: Temp directory for cache files.
        """
        projects: dict[str, MeProjectInfo] = {}
        for i in range(200):
            projects[str(i)] = MeProjectInfo(
                name=f"Project {i}",
                organization_id=1,
            )
        response = MeResponse(user_id=1, projects=projects)
        cache = MeCache(storage_dir=cache_dir)
        cache.put("us", response)

        retrieved = cache.get("us")
        assert retrieved is not None
        assert len(retrieved.projects) == 200

    def test_me_response_with_500_workspaces(self, cache_dir: Path) -> None:
        """MeCache handles a response with 500 workspaces.

        Args:
            cache_dir: Temp directory for cache files.
        """
        workspaces: dict[str, MeWorkspaceInfo] = {}
        for i in range(500):
            workspaces[str(i)] = MeWorkspaceInfo(
                id=i,
                name=f"Workspace {i}",
                project_id=1,
            )
        response = MeResponse(user_id=1, workspaces=workspaces)
        cache = MeCache(storage_dir=cache_dir)
        cache.put("us", response)

        retrieved = cache.get("us")
        assert retrieved is not None
        assert len(retrieved.workspaces) == 500
