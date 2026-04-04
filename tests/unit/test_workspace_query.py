"""Tests for Workspace.query() method.

Tests the inline insights query with optional bookmark saving.
Follows patterns from test_workspace_bookmarks.py.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from mixpanel_data import Workspace
from mixpanel_data._internal.config import ConfigManager, Credentials
from mixpanel_data.types import (
    Bookmark,
    Filter,
    Formula,
    InsightsResult,
    Metric,
)


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
    manager = MagicMock(spec=ConfigManager)
    manager.resolve_credentials.return_value = mock_credentials
    return manager


@pytest.fixture
def mock_api_client() -> MagicMock:
    """Create mock API client for testing."""
    from mixpanel_data._internal.api_client import MixpanelAPIClient

    client = MagicMock(spec=MixpanelAPIClient)
    client.close = MagicMock()
    return client


@pytest.fixture
def workspace_factory(
    mock_config_manager: MagicMock,
    mock_api_client: MagicMock,
) -> Callable[..., Workspace]:
    """Factory for creating Workspace instances with mocked dependencies."""

    def factory(**kwargs: Any) -> Workspace:
        defaults: dict[str, Any] = {
            "_config_manager": mock_config_manager,
            "_api_client": mock_api_client,
        }
        defaults.update(kwargs)
        return Workspace(**defaults)

    return factory


_MOCK_INSIGHTS_RESPONSE: dict[str, Any] = {
    "headers": ["$event"],
    "computed_at": "2025-01-01T00:00:00+00:00",
    "date_range": {
        "from_date": "2025-01-01T00:00:00+00:00",
        "to_date": "2025-01-31T00:00:00+00:00",
    },
    "series": {"Login [Total Events]": {"2025-01-01": 100}},
}


def _make_mock_bookmark(bookmark_id: int = 999) -> Bookmark:
    """Create a mock Bookmark response."""
    return Bookmark(
        id=bookmark_id,
        name="test_query",
        bookmark_type="insights",
        params={"sections": {"show": []}},
    )


class TestQueryBasicLifecycle:
    """Test the inline query lifecycle."""

    def test_query_uses_inline_api(
        self,
        workspace_factory: Callable[..., Workspace],
        mock_api_client: MagicMock,
    ) -> None:
        """query() should call query_insights_inline, not create_bookmark."""
        ws = workspace_factory()
        try:
            mock_api_client.query_insights_inline.return_value = (
                _MOCK_INSIGHTS_RESPONSE.copy()
            )

            result = ws.query("Login", last=30)

            assert isinstance(result, InsightsResult)
            mock_api_client.query_insights_inline.assert_called_once()
            mock_api_client.create_bookmark.assert_not_called()
            mock_api_client.delete_bookmark.assert_not_called()
        finally:
            ws.close()

    def test_query_save_true_creates_bookmark(
        self,
        workspace_factory: Callable[..., Workspace],
        mock_api_client: MagicMock,
    ) -> None:
        """save=True should also create a bookmark after querying."""
        ws = workspace_factory()
        try:
            mock_api_client.query_insights_inline.return_value = (
                _MOCK_INSIGHTS_RESPONSE.copy()
            )
            mock_api_client.create_bookmark.return_value = _make_mock_bookmark()

            result = ws.query("Login", last=30, save=True)

            assert result.bookmark_id == 999
            mock_api_client.query_insights_inline.assert_called_once()
            mock_api_client.create_bookmark.assert_called_once()
        finally:
            ws.close()

    def test_query_error_propagates(
        self,
        workspace_factory: Callable[..., Workspace],
        mock_api_client: MagicMock,
    ) -> None:
        """Errors from the insights API should propagate."""
        ws = workspace_factory()
        try:
            mock_api_client.query_insights_inline.side_effect = RuntimeError(
                "query failed"
            )

            with pytest.raises(RuntimeError, match="query failed"):
                ws.query("Login", last=30)
        finally:
            ws.close()


class TestQueryInputNormalization:
    """Test that string shorthands are properly normalized."""

    def test_string_metric_normalized(
        self,
        workspace_factory: Callable[..., Workspace],
        mock_api_client: MagicMock,
    ) -> None:
        """A plain string should be wrapped in a Metric."""
        ws = workspace_factory()
        try:
            mock_api_client.query_insights_inline.return_value = (
                _MOCK_INSIGHTS_RESPONSE.copy()
            )

            ws.query("Login", last=30)

            call_args = mock_api_client.query_insights_inline.call_args
            params = call_args[0][0]
            assert params["sections"]["show"][0]["behavior"]["name"] == "Login"
        finally:
            ws.close()

    def test_metric_object_used_directly(
        self,
        workspace_factory: Callable[..., Workspace],
        mock_api_client: MagicMock,
    ) -> None:
        """A Metric object should be used as-is."""
        ws = workspace_factory()
        try:
            mock_api_client.query_insights_inline.return_value = (
                _MOCK_INSIGHTS_RESPONSE.copy()
            )

            ws.query(Metric(event="Purchase", math="unique"), last=30)

            call_args = mock_api_client.query_insights_inline.call_args
            params = call_args[0][0]
            show = params["sections"]["show"][0]
            assert show["behavior"]["name"] == "Purchase"
            assert show["measurement"]["math"] == "unique"
        finally:
            ws.close()

    def test_list_of_mixed_metrics(
        self,
        workspace_factory: Callable[..., Workspace],
        mock_api_client: MagicMock,
    ) -> None:
        """A list mixing strings, Metrics, and Formulas should work."""
        ws = workspace_factory()
        try:
            mock_api_client.query_insights_inline.return_value = (
                _MOCK_INSIGHTS_RESPONSE.copy()
            )

            ws.query(
                [
                    "Sign Up",
                    Metric(event="Purchase", math="unique"),
                    Formula(expression="(B / A) * 100"),
                ],
                last=30,
            )

            call_args = mock_api_client.query_insights_inline.call_args
            params = call_args[0][0]
            show = params["sections"]["show"]
            assert len(show) == 3
            assert show[0]["behavior"]["name"] == "Sign Up"
            assert show[1]["behavior"]["name"] == "Purchase"
            assert show[2]["type"] == "formula"
        finally:
            ws.close()

    def test_string_group_by_normalized(
        self,
        workspace_factory: Callable[..., Workspace],
        mock_api_client: MagicMock,
    ) -> None:
        """A string group_by should be wrapped in a Breakdown."""
        ws = workspace_factory()
        try:
            mock_api_client.query_insights_inline.return_value = (
                _MOCK_INSIGHTS_RESPONSE.copy()
            )

            ws.query("Login", last=30, group_by="$browser")

            call_args = mock_api_client.query_insights_inline.call_args
            params = call_args[0][0]
            groups = params["sections"]["group"]
            assert len(groups) == 1
            assert groups[0]["value"] == "$browser"
        finally:
            ws.close()

    def test_single_filter_normalized_to_list(
        self,
        workspace_factory: Callable[..., Workspace],
        mock_api_client: MagicMock,
    ) -> None:
        """A single Filter should be wrapped in a list."""
        ws = workspace_factory()
        try:
            mock_api_client.query_insights_inline.return_value = (
                _MOCK_INSIGHTS_RESPONSE.copy()
            )

            ws.query(
                "Login",
                last=30,
                where=Filter(property="$browser", operator="equals", value=["Chrome"]),
            )

            call_args = mock_api_client.query_insights_inline.call_args
            params = call_args[0][0]
            assert len(params["sections"]["filter"]) == 1
        finally:
            ws.close()


class TestQueryDateValidation:
    """Test date argument validation."""

    def test_last_and_from_date_raises(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """Cannot provide both 'last' and 'from_date'."""
        ws = workspace_factory()
        try:
            with pytest.raises(ValueError, match="Cannot specify both"):
                ws.query("Login", last=30, from_date="2025-01-01")
        finally:
            ws.close()

    def test_no_date_args_raises(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """Must provide either 'last' or 'from_date'/'to_date'."""
        ws = workspace_factory()
        try:
            with pytest.raises(ValueError, match="Must specify either"):
                ws.query("Login")
        finally:
            ws.close()

    def test_from_without_to_raises(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """from_date without to_date should raise."""
        ws = workspace_factory()
        try:
            with pytest.raises(ValueError, match="Both 'from_date' and 'to_date'"):
                ws.query("Login", from_date="2025-01-01")
        finally:
            ws.close()


class TestQueryResult:
    """Test InsightsResult structure."""

    def test_result_has_params(
        self,
        workspace_factory: Callable[..., Workspace],
        mock_api_client: MagicMock,
    ) -> None:
        """Result should contain the generated params for debugging."""
        ws = workspace_factory()
        try:
            mock_api_client.query_insights_inline.return_value = (
                _MOCK_INSIGHTS_RESPONSE.copy()
            )

            result = ws.query("Login", last=30)

            assert "sections" in result.params
            assert "displayOptions" in result.params
        finally:
            ws.close()

    def test_result_bookmark_id_none_when_not_saved(
        self,
        workspace_factory: Callable[..., Workspace],
        mock_api_client: MagicMock,
    ) -> None:
        """bookmark_id should be None when save=False (default)."""
        ws = workspace_factory()
        try:
            mock_api_client.query_insights_inline.return_value = (
                _MOCK_INSIGHTS_RESPONSE.copy()
            )

            result = ws.query("Login", last=30)

            assert result.bookmark_id is None
        finally:
            ws.close()

    def test_result_bookmark_id_set_when_saved(
        self,
        workspace_factory: Callable[..., Workspace],
        mock_api_client: MagicMock,
    ) -> None:
        """bookmark_id should be set when save=True."""
        ws = workspace_factory()
        try:
            mock_api_client.query_insights_inline.return_value = (
                _MOCK_INSIGHTS_RESPONSE.copy()
            )
            mock_api_client.create_bookmark.return_value = _make_mock_bookmark()

            result = ws.query("Login", last=30, save=True)

            assert result.bookmark_id == 999
        finally:
            ws.close()
