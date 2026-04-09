"""Unit tests for custom header support in config.toml.

Tests the [settings] section with custom_header_name/value
in ConfigManager.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import tomli_w

from mixpanel_data._internal.config import ConfigManager


def _write_config_with_header(
    config_path: Path,
    *,
    header_name: str = "X-Config-Header",
    header_value: str = "config-value",
) -> None:
    """Write a v2 config with custom header settings.

    Args:
        config_path: Path to write the config.
        header_name: Custom header name.
        header_value: Custom header value.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = {
        "config_version": 2,
        "settings": {
            "custom_header_name": header_name,
            "custom_header_value": header_value,
        },
        "credentials": {
            "test-sa": {
                "type": "service_account",
                "username": "sa-user",
                "secret": "sa-secret",
                "region": "us",
            }
        },
        "active": {
            "credential": "test-sa",
            "project_id": "12345",
        },
    }
    config_path.write_bytes(tomli_w.dumps(config).encode())


def _write_config_without_header(config_path: Path) -> None:
    """Write a v2 config without custom header settings.

    Args:
        config_path: Path to write the config.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = {
        "config_version": 2,
        "credentials": {
            "test-sa": {
                "type": "service_account",
                "username": "sa-user",
                "secret": "sa-secret",
                "region": "us",
            }
        },
        "active": {
            "credential": "test-sa",
            "project_id": "12345",
        },
    }
    config_path.write_bytes(tomli_w.dumps(config).encode())


class TestGetCustomHeader:
    """Tests for ConfigManager.get_custom_header()."""

    def test_returns_header_when_configured(self, tmp_path: Path) -> None:
        """Test returning custom header from [settings]."""
        config_path = tmp_path / "config.toml"
        _write_config_with_header(config_path)

        cm = ConfigManager(config_path=config_path)
        header = cm.get_custom_header()

        assert header is not None
        assert header == ("X-Config-Header", "config-value")

    def test_returns_none_when_not_configured(self, tmp_path: Path) -> None:
        """Test returning None when no [settings] section."""
        config_path = tmp_path / "config.toml"
        _write_config_without_header(config_path)

        cm = ConfigManager(config_path=config_path)
        header = cm.get_custom_header()

        assert header is None

    def test_returns_none_when_partial(self, tmp_path: Path) -> None:
        """Test returning None when only name is set."""
        config_path = tmp_path / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config: dict[str, Any] = {
            "settings": {"custom_header_name": "X-Test"},
        }
        config_path.write_bytes(tomli_w.dumps(config).encode())

        cm = ConfigManager(config_path=config_path)
        assert cm.get_custom_header() is None

    def test_returns_none_for_empty_config(self, tmp_path: Path) -> None:
        """Test returning None when config file doesn't exist."""
        cm = ConfigManager(config_path=tmp_path / "nonexistent.toml")
        assert cm.get_custom_header() is None


class TestApplyConfigCustomHeader:
    """Tests for ConfigManager.apply_config_custom_header()."""

    def test_sets_env_vars(self, tmp_path: Path) -> None:
        """Test that custom header sets env vars."""
        config_path = tmp_path / "config.toml"
        _write_config_with_header(config_path)

        cm = ConfigManager(config_path=config_path)
        with patch.dict(os.environ, {}, clear=True):
            cm.apply_config_custom_header()
            assert os.environ.get("MP_CUSTOM_HEADER_NAME") == "X-Config-Header"
            assert os.environ.get("MP_CUSTOM_HEADER_VALUE") == "config-value"

    def test_does_not_override_existing(self, tmp_path: Path) -> None:
        """Test that existing env vars are preserved."""
        config_path = tmp_path / "config.toml"
        _write_config_with_header(config_path)

        cm = ConfigManager(config_path=config_path)
        with patch.dict(
            os.environ,
            {
                "MP_CUSTOM_HEADER_NAME": "X-Existing",
                "MP_CUSTOM_HEADER_VALUE": "existing",
            },
        ):
            cm.apply_config_custom_header()
            assert os.environ["MP_CUSTOM_HEADER_NAME"] == "X-Existing"

    def test_noop_when_no_header(self, tmp_path: Path) -> None:
        """Test noop when no header in config."""
        config_path = tmp_path / "config.toml"
        _write_config_without_header(config_path)

        cm = ConfigManager(config_path=config_path)
        with patch.dict(os.environ, {}, clear=True):
            cm.apply_config_custom_header()
            assert "MP_CUSTOM_HEADER_NAME" not in os.environ
