"""Shared fixtures for CLI integration tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from mixpanel_data._internal.config import AccountInfo
from mixpanel_data.types import (
    BlueprintConfig,
    BlueprintTemplate,
    Bookmark,
    BookmarkHistoryPagination,
    BookmarkHistoryResponse,
    Cohort,
    Dashboard,
    FetchResult,
    SegmentationResult,
    TableInfo,
    WorkspaceInfo,
)


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a CLI runner for testing commands."""
    return CliRunner()


@pytest.fixture
def mock_workspace() -> MagicMock:
    """Create a mock Workspace for testing commands."""
    workspace = MagicMock()

    # Set up common return values
    workspace.events.return_value = ["Event1", "Event2", "Event3"]
    workspace.properties.return_value = ["property1", "property2"]
    workspace.property_values.return_value = ["value1", "value2", "value3"]
    workspace.funnels.return_value = []
    workspace.cohorts.return_value = []
    workspace.top_events.return_value = []

    workspace.tables.return_value = [
        TableInfo(
            name="events",
            type="events",
            row_count=1000,
            fetched_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        ),
    ]

    workspace.info.return_value = WorkspaceInfo(
        path=Path("/tmp/workspace.db"),
        account="default",
        project_id="12345",
        region="us",
        tables=["events"],
        size_mb=1.5,
        created_at=None,
    )

    workspace.sql_rows.return_value = [{"count": 100}]
    workspace.sql_scalar.return_value = 100

    workspace.fetch_events.return_value = FetchResult(
        table="events",
        rows=1000,
        type="events",
        date_range=("2024-01-01", "2024-01-31"),
        duration_seconds=5.0,
        fetched_at=datetime(2024, 1, 31, 12, 0, 0, tzinfo=timezone.utc),
    )

    workspace.segmentation.return_value = SegmentationResult(
        event="Signup",
        from_date="2024-01-01",
        to_date="2024-01-31",
        unit="day",
        segment_property=None,
        total=500,
        series={"$overall": {"2024-01-01": 100}},
    )

    # Phase 024: Dashboard CRUD mocks
    mock_dash = Dashboard(id=1, title="Test Dashboard")
    workspace.list_dashboards.return_value = [mock_dash]
    workspace.create_dashboard.return_value = mock_dash
    workspace.get_dashboard.return_value = mock_dash
    workspace.update_dashboard.return_value = mock_dash
    workspace.delete_dashboard.return_value = None
    workspace.bulk_delete_dashboards.return_value = None
    workspace.favorite_dashboard.return_value = None
    workspace.unfavorite_dashboard.return_value = None
    workspace.pin_dashboard.return_value = None
    workspace.unpin_dashboard.return_value = None
    workspace.remove_report_from_dashboard.return_value = mock_dash
    workspace.list_blueprint_templates.return_value = [
        BlueprintTemplate(title_key="onboarding", description_key="Get started")
    ]
    workspace.create_blueprint.return_value = mock_dash
    workspace.get_blueprint_config.return_value = BlueprintConfig(
        variables={"event": "Signup"}
    )
    workspace.update_blueprint_cohorts.return_value = None
    workspace.finalize_blueprint.return_value = mock_dash
    workspace.create_rca_dashboard.return_value = mock_dash
    workspace.get_bookmark_dashboard_ids.return_value = [1, 2]
    workspace.get_dashboard_erf.return_value = {"metrics": []}
    workspace.update_report_link.return_value = None
    workspace.update_text_card.return_value = None

    # Phase 024: Bookmark/Report CRUD mocks
    mock_bookmark = Bookmark(
        id=1, name="Test Report", bookmark_type="insights", params={}
    )
    workspace.list_bookmarks_v2.return_value = [mock_bookmark]
    workspace.create_bookmark.return_value = mock_bookmark
    workspace.get_bookmark.return_value = mock_bookmark
    workspace.update_bookmark.return_value = mock_bookmark
    workspace.delete_bookmark.return_value = None
    workspace.bulk_delete_bookmarks.return_value = None
    workspace.bulk_update_bookmarks.return_value = None
    workspace.bookmark_linked_dashboard_ids.return_value = [10, 20]
    workspace.get_bookmark_history.return_value = BookmarkHistoryResponse(
        results=[],
        pagination=BookmarkHistoryPagination(page_size=20),
    )

    # Phase 024: Cohort CRUD mocks
    mock_cohort = Cohort(id=1, name="Power Users")
    workspace.list_cohorts_full.return_value = [mock_cohort]
    workspace.get_cohort.return_value = mock_cohort
    workspace.create_cohort.return_value = mock_cohort
    workspace.update_cohort.return_value = mock_cohort
    workspace.delete_cohort.return_value = None
    workspace.bulk_delete_cohorts.return_value = None
    workspace.bulk_update_cohorts.return_value = None

    return workspace


@pytest.fixture
def mock_config_manager() -> MagicMock:
    """Create a mock ConfigManager for testing auth commands."""
    config = MagicMock()

    config.list_accounts.return_value = [
        AccountInfo(
            name="production",
            username="user@example.com",
            project_id="12345",
            region="us",
            is_default=True,
        ),
        AccountInfo(
            name="staging",
            username="user@example.com",
            project_id="67890",
            region="eu",
            is_default=False,
        ),
    ]

    config.get_default.return_value = AccountInfo(
        name="production",
        username="user@example.com",
        project_id="12345",
        region="us",
        is_default=True,
    )

    config.get_account.return_value = AccountInfo(
        name="production",
        username="user@example.com",
        project_id="12345",
        region="us",
        is_default=True,
    )

    return config


@pytest.fixture
def patch_config_manager(mock_config_manager: MagicMock) -> Any:
    """Patch get_config to return mock ConfigManager."""
    with patch(
        "mixpanel_data.cli.commands.auth.get_config",
        return_value=mock_config_manager,
    ) as mock:
        yield mock
