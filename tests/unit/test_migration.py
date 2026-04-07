"""Unit tests for v1 to v2 config migration.

Tests cover:
- T080: migrate_v1_to_v2() (credential grouping, alias creation, backup, active context)
- T081: Migration edge cases (already v2, empty config, single account)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomli_w

from mixpanel_data._internal.config import (
    ConfigManager,
    MigrationResult,
)
from mixpanel_data.exceptions import ConfigError

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Return path for a temporary config file."""
    return tmp_path / "config.toml"


@pytest.fixture
def cm(config_path: Path) -> ConfigManager:
    """Create a ConfigManager with a temporary config file."""
    return ConfigManager(config_path=config_path)


def _write_v1_config(config_path: Path, config: dict[str, object]) -> None:
    """Write a v1 config to disk.

    Args:
        config_path: Path to write config file.
        config: V1 config dictionary.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("wb") as f:
        tomli_w.dump(config, f)


# ── T080: migrate_v1_to_v2() ──────────────────────────────────────────


class TestMigrateV1ToV2:
    """T080: Tests for migrate_v1_to_v2() credential grouping and alias creation."""

    def test_migrate_groups_shared_credentials(
        self, config_path: Path, cm: ConfigManager
    ) -> None:
        """Test that accounts sharing the same SA are grouped into one credential."""
        v1: dict[str, object] = {
            "default": "acct_a",
            "accounts": {
                "acct_a": {
                    "username": "shared_user",
                    "secret": "shared_secret",
                    "project_id": "1001",
                    "region": "us",
                },
                "acct_b": {
                    "username": "shared_user",
                    "secret": "shared_secret",
                    "project_id": "2002",
                    "region": "us",
                },
            },
        }
        _write_v1_config(config_path, v1)

        result = cm.migrate_v1_to_v2()

        assert isinstance(result, MigrationResult)
        assert result.credentials_created == 1  # deduplicated
        assert result.aliases_created == 2  # one per account

    def test_migrate_creates_alias_per_account(
        self, config_path: Path, cm: ConfigManager
    ) -> None:
        """Test that every v1 account becomes a project alias in v2."""
        v1: dict[str, object] = {
            "default": "prod",
            "accounts": {
                "prod": {
                    "username": "u1",
                    "secret": "s1",
                    "project_id": "100",
                    "region": "us",
                },
                "staging": {
                    "username": "u2",
                    "secret": "s2",
                    "project_id": "200",
                    "region": "eu",
                },
                "dev": {
                    "username": "u3",
                    "secret": "s3",
                    "project_id": "300",
                    "region": "us",
                },
            },
        }
        _write_v1_config(config_path, v1)

        result = cm.migrate_v1_to_v2()

        assert result.aliases_created == 3
        assert result.credentials_created == 3  # all unique SAs

    def test_migrate_sets_active_context_from_default(
        self, config_path: Path, cm: ConfigManager
    ) -> None:
        """Test that v1 default account becomes the v2 active context."""
        v1: dict[str, object] = {
            "default": "main",
            "accounts": {
                "main": {
                    "username": "main_user",
                    "secret": "main_secret",
                    "project_id": "9999",
                    "region": "eu",
                },
                "alt": {
                    "username": "alt_user",
                    "secret": "alt_secret",
                    "project_id": "8888",
                    "region": "us",
                },
            },
        }
        _write_v1_config(config_path, v1)

        result = cm.migrate_v1_to_v2()

        assert result.active_credential is not None
        assert result.active_project_id == "9999"

    def test_migrate_creates_backup_file(
        self, config_path: Path, cm: ConfigManager
    ) -> None:
        """Test that migration creates a .v1.bak backup file."""
        v1: dict[str, object] = {
            "default": "demo",
            "accounts": {
                "demo": {
                    "username": "user",
                    "secret": "secret",
                    "project_id": "123",
                    "region": "us",
                },
            },
        }
        _write_v1_config(config_path, v1)

        result = cm.migrate_v1_to_v2()

        assert result.backup_path is not None
        assert result.backup_path.exists()
        assert result.backup_path.suffix == ".bak"

    def test_migrate_writes_v2_config(
        self, config_path: Path, cm: ConfigManager
    ) -> None:
        """Test that migration writes a valid v2 config to disk."""
        v1: dict[str, object] = {
            "default": "demo",
            "accounts": {
                "demo": {
                    "username": "user",
                    "secret": "secret",
                    "project_id": "123",
                    "region": "us",
                },
            },
        }
        _write_v1_config(config_path, v1)

        cm.migrate_v1_to_v2()

        assert cm.config_version() == 2
        creds = cm.list_credentials()
        assert len(creds) == 1
        assert creds[0].name == "demo"
        assert creds[0].type == "service_account"

    def test_migrate_dry_run_no_write(
        self, config_path: Path, cm: ConfigManager
    ) -> None:
        """Test dry-run mode computes result without writing to disk."""
        v1: dict[str, object] = {
            "default": "demo",
            "accounts": {
                "demo": {
                    "username": "user",
                    "secret": "secret",
                    "project_id": "123",
                    "region": "us",
                },
            },
        }
        _write_v1_config(config_path, v1)

        result = cm.migrate_v1_to_v2(dry_run=True)

        assert result.credentials_created == 1
        assert result.aliases_created == 1
        assert result.backup_path is None
        # Config should still be v1
        assert cm.config_version() == 1

    def test_migrate_project_aliases_accessible(
        self, config_path: Path, cm: ConfigManager
    ) -> None:
        """Test that migrated project aliases are listed correctly."""
        v1: dict[str, object] = {
            "default": "prod",
            "accounts": {
                "prod": {
                    "username": "user",
                    "secret": "secret",
                    "project_id": "1001",
                    "region": "us",
                },
                "staging": {
                    "username": "user",
                    "secret": "secret",
                    "project_id": "2002",
                    "region": "us",
                },
            },
        }
        _write_v1_config(config_path, v1)

        cm.migrate_v1_to_v2()

        aliases = cm.list_project_aliases()
        alias_names = {a.name for a in aliases}
        assert alias_names == {"prod", "staging"}
        alias_pids = {a.project_id for a in aliases}
        assert alias_pids == {"1001", "2002"}

    def test_migrate_distinct_credentials_not_grouped(
        self, config_path: Path, cm: ConfigManager
    ) -> None:
        """Test that accounts with different SAs produce separate credentials."""
        v1: dict[str, object] = {
            "default": "a",
            "accounts": {
                "a": {
                    "username": "user_a",
                    "secret": "secret_a",
                    "project_id": "1",
                    "region": "us",
                },
                "b": {
                    "username": "user_b",
                    "secret": "secret_b",
                    "project_id": "2",
                    "region": "us",
                },
            },
        }
        _write_v1_config(config_path, v1)

        result = cm.migrate_v1_to_v2()

        assert result.credentials_created == 2


# ── T081: Migration edge cases ────────────────────────────────────────


class TestMigrateEdgeCases:
    """T081: Tests for migration edge cases."""

    def test_already_v2_raises_config_error(
        self, config_path: Path, cm: ConfigManager
    ) -> None:
        """Test that migrating an already-v2 config raises ConfigError."""
        v2: dict[str, object] = {
            "config_version": 2,
            "credentials": {},
        }
        _write_v1_config(config_path, v2)

        with pytest.raises(ConfigError, match="already v2"):
            cm.migrate_v1_to_v2()

    def test_empty_config_migrates_to_empty_v2(
        self, config_path: Path, cm: ConfigManager
    ) -> None:
        """Test that an empty config migrates to empty v2 (no credentials/aliases)."""
        _write_v1_config(config_path, {})

        result = cm.migrate_v1_to_v2()

        assert result.credentials_created == 0
        assert result.aliases_created == 0
        assert cm.config_version() == 2

    def test_single_account_migration(
        self, config_path: Path, cm: ConfigManager
    ) -> None:
        """Test migrating a single-account v1 config."""
        v1: dict[str, object] = {
            "default": "only",
            "accounts": {
                "only": {
                    "username": "user",
                    "secret": "secret",
                    "project_id": "42",
                    "region": "in",
                },
            },
        }
        _write_v1_config(config_path, v1)

        result = cm.migrate_v1_to_v2()

        assert result.credentials_created == 1
        assert result.aliases_created == 1
        assert result.active_credential == "only"
        assert result.active_project_id == "42"

    def test_no_default_falls_back_to_first(
        self, config_path: Path, cm: ConfigManager
    ) -> None:
        """Test migration without a default account uses first credential."""
        v1: dict[str, object] = {
            "accounts": {
                "first": {
                    "username": "user1",
                    "secret": "secret1",
                    "project_id": "111",
                    "region": "us",
                },
            },
        }
        _write_v1_config(config_path, v1)

        result = cm.migrate_v1_to_v2()

        assert result.active_credential is not None

    def test_config_not_on_disk_migrates(self, cm: ConfigManager) -> None:
        """Test migrating when no config file exists on disk."""
        result = cm.migrate_v1_to_v2()

        assert result.credentials_created == 0
        assert result.aliases_created == 0
