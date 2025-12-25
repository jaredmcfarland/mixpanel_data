"""Unit tests for Workspace introspection methods.

Tests cover:
- sample() - Random sampling from tables
- summarize() - Statistical summary of columns
- event_breakdown() - Event distribution analysis
- property_keys() - JSON property key discovery
- column_stats() - Deep column analysis
"""
# ruff: noqa: ARG002  # Pytest fixtures appear as unused arguments

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pydantic import SecretStr

from mixpanel_data import QueryError, TableNotFoundError, Workspace
from mixpanel_data._internal.config import ConfigManager, Credentials
from mixpanel_data._internal.storage import StorageEngine
from mixpanel_data.types import (
    ColumnStatsResult,
    ColumnSummary,
    EventBreakdownResult,
    EventStats,
    SummaryResult,
    TableMetadata,
)

# =============================================================================
# Fixtures
# =============================================================================


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
def storage() -> StorageEngine:
    """Create ephemeral storage for testing."""
    return StorageEngine.ephemeral()


@pytest.fixture
def workspace(storage: StorageEngine, mock_config_manager: MagicMock) -> Workspace:
    """Create workspace with ephemeral storage and mocked credentials."""
    return Workspace(_storage=storage, _config_manager=mock_config_manager)


@pytest.fixture
def events_table(storage: StorageEngine) -> None:
    """Create and populate an events table for testing."""
    events = [
        {
            "event_name": "Page View",
            "event_time": datetime(2024, 1, 1, 10, 0, 0),
            "distinct_id": "user_1",
            "insert_id": "id_1",
            "properties": {"page": "/home", "country": "US"},
        },
        {
            "event_name": "Page View",
            "event_time": datetime(2024, 1, 1, 11, 0, 0),
            "distinct_id": "user_2",
            "insert_id": "id_2",
            "properties": {"page": "/about", "country": "UK"},
        },
        {
            "event_name": "Sign Up",
            "event_time": datetime(2024, 1, 2, 9, 0, 0),
            "distinct_id": "user_1",
            "insert_id": "id_3",
            "properties": {"plan": "free", "country": "US"},
        },
        {
            "event_name": "Purchase",
            "event_time": datetime(2024, 1, 3, 14, 0, 0),
            "distinct_id": "user_3",
            "insert_id": "id_4",
            "properties": {"amount": 99.99, "currency": "USD"},
        },
        {
            "event_name": "Page View",
            "event_time": datetime(2024, 1, 4, 8, 0, 0),
            "distinct_id": "user_1",
            "insert_id": "id_5",
            "properties": {"page": "/pricing", "country": "US"},
        },
    ]
    metadata = TableMetadata(type="events", fetched_at=datetime.now(UTC))
    storage.create_events_table("events", iter(events), metadata)


@pytest.fixture
def empty_events_table(storage: StorageEngine) -> None:
    """Create an empty events table for edge case testing."""
    metadata = TableMetadata(type="events", fetched_at=datetime.now(UTC))
    storage.create_events_table("empty_events", iter([]), metadata)


@pytest.fixture
def numeric_table(storage: StorageEngine) -> None:
    """Create a table with numeric columns for testing."""
    # Use SQL to create table with numeric columns
    storage.connection.execute("""
        CREATE TABLE numeric_data (
            id INTEGER,
            value DOUBLE,
            count INTEGER,
            label VARCHAR
        )
    """)
    storage.connection.execute("""
        INSERT INTO numeric_data VALUES
            (1, 10.5, 100, 'A'),
            (2, 20.3, 200, 'B'),
            (3, 15.7, 150, 'A'),
            (4, NULL, NULL, 'C'),
            (5, 25.1, 250, 'B')
    """)


# =============================================================================
# Sample Tests
# =============================================================================


class TestSample:
    """Tests for Workspace.sample() method."""

    def test_sample_returns_dataframe(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """sample() returns a pandas DataFrame."""
        result = workspace.sample("events")
        assert isinstance(result, pd.DataFrame)

    def test_sample_respects_n_parameter(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """sample() returns at most n rows."""
        result = workspace.sample("events", n=2)
        assert len(result) <= 2

    def test_sample_default_n_is_10(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """sample() defaults to n=10."""
        # With only 5 events, we get all 5
        result = workspace.sample("events")
        assert len(result) == 5

    def test_sample_returns_all_columns(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """sample() returns all columns from the table."""
        result = workspace.sample("events", n=1)
        expected_columns = {"event_name", "event_time", "distinct_id", "properties"}
        assert expected_columns.issubset(set(result.columns))

    def test_sample_table_not_found(self, workspace: Workspace) -> None:
        """sample() raises TableNotFoundError for nonexistent table."""
        with pytest.raises(TableNotFoundError):
            workspace.sample("nonexistent_table")

    def test_sample_empty_table(
        self, workspace: Workspace, empty_events_table: None
    ) -> None:
        """sample() returns empty DataFrame for empty table."""
        result = workspace.sample("empty_events")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0


# =============================================================================
# Summarize Tests
# =============================================================================


class TestSummarize:
    """Tests for Workspace.summarize() method."""

    def test_summarize_returns_summary_result(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """summarize() returns a SummaryResult."""
        result = workspace.summarize("events")
        assert isinstance(result, SummaryResult)

    def test_summarize_includes_table_name(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """SummaryResult includes the table name."""
        result = workspace.summarize("events")
        assert result.table == "events"

    def test_summarize_includes_row_count(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """SummaryResult includes correct row count."""
        result = workspace.summarize("events")
        assert result.row_count == 5

    def test_summarize_includes_column_summaries(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """SummaryResult includes ColumnSummary for each column."""
        result = workspace.summarize("events")
        assert len(result.columns) > 0
        assert all(isinstance(col, ColumnSummary) for col in result.columns)

    def test_summarize_column_summary_fields(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """ColumnSummary includes required statistical fields."""
        result = workspace.summarize("events")
        col = result.columns[0]

        # Check all required fields exist
        assert hasattr(col, "column_name")
        assert hasattr(col, "column_type")
        assert hasattr(col, "min")
        assert hasattr(col, "max")
        assert hasattr(col, "approx_unique")
        assert hasattr(col, "count")
        assert hasattr(col, "null_percentage")

    def test_summarize_df_property(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """SummaryResult.df returns a DataFrame."""
        result = workspace.summarize("events")
        df = result.df
        assert isinstance(df, pd.DataFrame)
        assert len(df) == len(result.columns)

    def test_summarize_to_dict(self, workspace: Workspace, events_table: None) -> None:
        """SummaryResult.to_dict() returns serializable dict."""
        result = workspace.summarize("events")
        d = result.to_dict()
        assert "table" in d
        assert "row_count" in d
        assert "columns" in d

    def test_summarize_table_not_found(self, workspace: Workspace) -> None:
        """summarize() raises TableNotFoundError for nonexistent table."""
        with pytest.raises(TableNotFoundError):
            workspace.summarize("nonexistent_table")

    def test_summarize_empty_table(
        self, workspace: Workspace, empty_events_table: None
    ) -> None:
        """summarize() works on empty table."""
        result = workspace.summarize("empty_events")
        assert result.row_count == 0


# =============================================================================
# Event Breakdown Tests
# =============================================================================


class TestEventBreakdown:
    """Tests for Workspace.event_breakdown() method."""

    def test_event_breakdown_returns_result(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """event_breakdown() returns an EventBreakdownResult."""
        result = workspace.event_breakdown("events")
        assert isinstance(result, EventBreakdownResult)

    def test_event_breakdown_includes_table_name(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """EventBreakdownResult includes the table name."""
        result = workspace.event_breakdown("events")
        assert result.table == "events"

    def test_event_breakdown_total_events(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """EventBreakdownResult includes correct total_events."""
        result = workspace.event_breakdown("events")
        assert result.total_events == 5

    def test_event_breakdown_total_users(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """EventBreakdownResult includes correct total_users."""
        result = workspace.event_breakdown("events")
        assert result.total_users == 3  # user_1, user_2, user_3

    def test_event_breakdown_date_range(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """EventBreakdownResult includes correct date_range."""
        result = workspace.event_breakdown("events")
        assert isinstance(result.date_range, tuple)
        assert len(result.date_range) == 2
        assert result.date_range[0] <= result.date_range[1]

    def test_event_breakdown_per_event_stats(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """EventBreakdownResult includes per-event statistics."""
        result = workspace.event_breakdown("events")
        assert len(result.events) == 3  # Page View, Sign Up, Purchase

        # Check EventStats structure
        for event in result.events:
            assert isinstance(event, EventStats)
            assert hasattr(event, "event_name")
            assert hasattr(event, "count")
            assert hasattr(event, "unique_users")
            assert hasattr(event, "first_seen")
            assert hasattr(event, "last_seen")
            assert hasattr(event, "pct_of_total")

    def test_event_breakdown_sorted_by_count(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """EventBreakdownResult events are sorted by count descending."""
        result = workspace.event_breakdown("events")
        counts = [event.count for event in result.events]
        assert counts == sorted(counts, reverse=True)

    def test_event_breakdown_page_view_stats(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """EventBreakdownResult correctly counts Page View events."""
        result = workspace.event_breakdown("events")
        page_view = next(e for e in result.events if e.event_name == "Page View")
        assert page_view.count == 3
        assert page_view.unique_users == 2  # user_1 and user_2

    def test_event_breakdown_pct_of_total(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """EventBreakdownResult pct_of_total sums to 100."""
        result = workspace.event_breakdown("events")
        total_pct = sum(event.pct_of_total for event in result.events)
        assert abs(total_pct - 100.0) < 0.1  # Allow for rounding

    def test_event_breakdown_df_property(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """EventBreakdownResult.df returns a DataFrame."""
        result = workspace.event_breakdown("events")
        df = result.df
        assert isinstance(df, pd.DataFrame)
        assert len(df) == len(result.events)

    def test_event_breakdown_to_dict(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """EventBreakdownResult.to_dict() returns serializable dict."""
        result = workspace.event_breakdown("events")
        d = result.to_dict()
        assert "table" in d
        assert "total_events" in d
        assert "total_users" in d
        assert "date_range" in d
        assert "events" in d

    def test_event_breakdown_table_not_found(self, workspace: Workspace) -> None:
        """event_breakdown() raises TableNotFoundError for nonexistent table."""
        with pytest.raises(TableNotFoundError):
            workspace.event_breakdown("nonexistent_table")

    def test_event_breakdown_missing_columns(
        self, workspace: Workspace, numeric_table: None
    ) -> None:
        """event_breakdown() raises QueryError if required columns missing."""
        with pytest.raises(QueryError) as exc_info:
            workspace.event_breakdown("numeric_data")
        assert "event_name" in str(exc_info.value) or "missing" in str(exc_info.value)

    def test_event_breakdown_empty_table(
        self, workspace: Workspace, empty_events_table: None
    ) -> None:
        """event_breakdown() handles empty table gracefully."""
        result = workspace.event_breakdown("empty_events")
        assert result.total_events == 0
        assert result.total_users == 0
        assert len(result.events) == 0


# =============================================================================
# Property Keys Tests
# =============================================================================


class TestPropertyKeys:
    """Tests for Workspace.property_keys() method."""

    def test_property_keys_returns_list(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """property_keys() returns a list of strings."""
        result = workspace.property_keys("events")
        assert isinstance(result, list)
        assert all(isinstance(k, str) for k in result)

    def test_property_keys_finds_all_keys(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """property_keys() discovers all JSON property keys."""
        result = workspace.property_keys("events")
        expected_keys = {"page", "country", "plan", "amount", "currency"}
        assert expected_keys.issubset(set(result))

    def test_property_keys_sorted_alphabetically(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """property_keys() returns keys in alphabetical order."""
        result = workspace.property_keys("events")
        assert result == sorted(result)

    def test_property_keys_with_event_filter(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """property_keys() filters by event when provided."""
        result = workspace.property_keys("events", event="Purchase")
        assert "amount" in result
        assert "currency" in result
        # Keys from other events should not be present
        assert "page" not in result
        assert "plan" not in result

    def test_property_keys_table_not_found(self, workspace: Workspace) -> None:
        """property_keys() raises TableNotFoundError for nonexistent table."""
        with pytest.raises(TableNotFoundError):
            workspace.property_keys("nonexistent_table")

    def test_property_keys_missing_properties_column(
        self, workspace: Workspace, numeric_table: None
    ) -> None:
        """property_keys() raises QueryError if no properties column."""
        with pytest.raises(QueryError) as exc_info:
            workspace.property_keys("numeric_data")
        assert "properties" in str(exc_info.value)

    def test_property_keys_empty_table(
        self, workspace: Workspace, empty_events_table: None
    ) -> None:
        """property_keys() returns empty list for empty table."""
        result = workspace.property_keys("empty_events")
        assert result == []


# =============================================================================
# Column Stats Tests
# =============================================================================


class TestColumnStats:
    """Tests for Workspace.column_stats() method."""

    def test_column_stats_returns_result(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """column_stats() returns a ColumnStatsResult."""
        result = workspace.column_stats("events", "event_name")
        assert isinstance(result, ColumnStatsResult)

    def test_column_stats_includes_table_and_column(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """ColumnStatsResult includes table and column info."""
        result = workspace.column_stats("events", "event_name")
        assert result.table == "events"
        assert result.column == "event_name"

    def test_column_stats_count(self, workspace: Workspace, events_table: None) -> None:
        """ColumnStatsResult includes correct count."""
        result = workspace.column_stats("events", "event_name")
        assert result.count == 5

    def test_column_stats_null_count(
        self, workspace: Workspace, numeric_table: None
    ) -> None:
        """ColumnStatsResult includes correct null_count."""
        result = workspace.column_stats("numeric_data", "value")
        assert result.null_count == 1

    def test_column_stats_null_pct(
        self, workspace: Workspace, numeric_table: None
    ) -> None:
        """ColumnStatsResult includes correct null_pct."""
        result = workspace.column_stats("numeric_data", "value")
        assert result.null_pct == 20.0  # 1 of 5 is NULL

    def test_column_stats_unique_count(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """ColumnStatsResult includes approximate unique count."""
        result = workspace.column_stats("events", "event_name")
        assert result.unique_count == 3  # Page View, Sign Up, Purchase

    def test_column_stats_top_values(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """ColumnStatsResult includes top values with counts."""
        result = workspace.column_stats("events", "event_name", top_n=3)
        assert len(result.top_values) <= 3
        assert all(isinstance(v, tuple) and len(v) == 2 for v in result.top_values)

        # Check Page View is most frequent
        top_value, top_count = result.top_values[0]
        assert top_value == "Page View"
        assert top_count == 3

    def test_column_stats_top_n_parameter(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """column_stats() respects top_n parameter."""
        result = workspace.column_stats("events", "event_name", top_n=1)
        assert len(result.top_values) == 1

    def test_column_stats_numeric_stats(
        self, workspace: Workspace, numeric_table: None
    ) -> None:
        """ColumnStatsResult includes numeric stats for numeric columns."""
        result = workspace.column_stats("numeric_data", "value")
        assert result.min is not None
        assert result.max is not None
        assert result.mean is not None

    def test_column_stats_no_numeric_stats_for_varchar(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """ColumnStatsResult has None for numeric stats on VARCHAR columns."""
        result = workspace.column_stats("events", "event_name")
        assert result.min is None
        assert result.max is None
        assert result.mean is None

    def test_column_stats_df_property(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """ColumnStatsResult.df returns top values as DataFrame."""
        result = workspace.column_stats("events", "event_name")
        df = result.df
        assert isinstance(df, pd.DataFrame)
        assert "value" in df.columns
        assert "count" in df.columns

    def test_column_stats_to_dict(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """ColumnStatsResult.to_dict() returns serializable dict."""
        result = workspace.column_stats("events", "event_name")
        d = result.to_dict()
        assert "table" in d
        assert "column" in d
        assert "count" in d
        assert "top_values" in d

    def test_column_stats_table_not_found(self, workspace: Workspace) -> None:
        """column_stats() raises TableNotFoundError for nonexistent table."""
        with pytest.raises(TableNotFoundError):
            workspace.column_stats("nonexistent_table", "col")

    def test_column_stats_invalid_column(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """column_stats() raises QueryError for invalid column expression."""
        with pytest.raises(QueryError):
            workspace.column_stats("events", "nonexistent_column")

    def test_column_stats_json_path_expression(
        self, workspace: Workspace, events_table: None
    ) -> None:
        """column_stats() works with JSON path expressions."""
        result = workspace.column_stats("events", "properties->>'$.country'")
        assert result.column == "properties->>'$.country'"
        # Should find US and UK
        values = [v[0] for v in result.top_values]
        assert "US" in values


# =============================================================================
# Type Serialization Tests
# =============================================================================


class TestTypeSerialization:
    """Tests for result type serialization methods."""

    def test_column_summary_to_dict(
        self,
        workspace: Workspace,
        events_table: None,  # noqa: ARG002
    ) -> None:
        """ColumnSummary.to_dict() includes all fields."""
        result = workspace.summarize("events")
        col_dict = result.columns[0].to_dict()

        expected_keys = {
            "column_name",
            "column_type",
            "min",
            "max",
            "approx_unique",
            "avg",
            "std",
            "q25",
            "q50",
            "q75",
            "count",
            "null_percentage",
        }
        assert expected_keys == set(col_dict.keys())

    def test_event_stats_to_dict_datetime_format(
        self,
        workspace: Workspace,
        events_table: None,  # noqa: ARG002
    ) -> None:
        """EventStats.to_dict() formats datetimes as ISO strings."""
        result = workspace.event_breakdown("events")
        event_dict = result.events[0].to_dict()

        assert isinstance(event_dict["first_seen"], str)
        assert isinstance(event_dict["last_seen"], str)
        # Should be valid ISO format
        datetime.fromisoformat(event_dict["first_seen"])
        datetime.fromisoformat(event_dict["last_seen"])

    def test_event_breakdown_result_to_dict_date_range(
        self,
        workspace: Workspace,
        events_table: None,  # noqa: ARG002
    ) -> None:
        """EventBreakdownResult.to_dict() formats date_range as ISO strings."""
        result = workspace.event_breakdown("events")
        d = result.to_dict()

        assert isinstance(d["date_range"], list)
        assert len(d["date_range"]) == 2
        # Should be valid ISO format
        datetime.fromisoformat(d["date_range"][0])
        datetime.fromisoformat(d["date_range"][1])

    def test_column_stats_result_top_values_format(
        self,
        workspace: Workspace,
        events_table: None,  # noqa: ARG002
    ) -> None:
        """ColumnStatsResult.to_dict() formats top_values as lists."""
        result = workspace.column_stats("events", "event_name")
        d = result.to_dict()

        # top_values should be list of [value, count] pairs
        assert isinstance(d["top_values"], list)
        for pair in d["top_values"]:
            assert isinstance(pair, list)
            assert len(pair) == 2
