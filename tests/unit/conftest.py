"""Shared fixtures for query API unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from mixpanel_data._internal.config import Credentials


@pytest.fixture
def mock_credentials() -> Credentials:
    """Create mock credentials for testing."""
    return Credentials(
        username="test_user",
        secret=SecretStr("test_secret"),
        project_id="12345",
        region="us",
    )


@pytest.fixture
def mock_config_manager(mock_credentials: Credentials) -> MagicMock:
    """Create mock ConfigManager that returns credentials."""
    manager = MagicMock()
    manager.config_version.return_value = 1
    manager.resolve_credentials.return_value = mock_credentials
    return manager
