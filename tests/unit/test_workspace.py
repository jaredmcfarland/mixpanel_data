"""Unit tests for Workspace facade."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from mixpanel_data import (
    ConfigError,
    Workspace,
)
from mixpanel_data._internal.config import AuthMethod, ConfigManager, Credentials
from mixpanel_data.types import (
    ActivityFeedResult,
    EventCountsResult,
    FrequencyResult,
    FunnelInfo,
    FunnelResult,
    JQLResult,
    LexiconDefinition,
    LexiconSchema,
    NumericAverageResult,
    NumericBucketResult,
    NumericSumResult,
    PropertyCountsResult,
    RetentionResult,
    SavedCohort,
    SavedReportResult,
    SegmentationResult,
    TopEvent,
)

if TYPE_CHECKING:
    from collections.abc import Callable


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
    manager.config_version.return_value = 1
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


# =============================================================================
# Phase 3: US5 Credential Resolution Tests
# =============================================================================


class TestCredentialResolution:
    """Tests for credential resolution (T014-T017)."""

    def test_env_var_credential_resolution(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """T014: Test env var credential resolution."""
        # Set environment variables
        monkeypatch.setenv("MP_USERNAME", "env_user")
        monkeypatch.setenv("MP_SECRET", "env_secret")
        monkeypatch.setenv("MP_PROJECT_ID", "99999")
        monkeypatch.setenv("MP_REGION", "eu")

        with Workspace() as ws:
            assert ws._credentials is not None
            assert ws._credentials.username == "env_user"
            assert ws._credentials.project_id == "99999"
            assert ws._credentials.region == "eu"

    def test_named_account_credential_resolution(
        self,
        temp_dir: Path,
    ) -> None:
        """T015: Test named account credential resolution."""
        # Create config with named account
        config_path = temp_dir / "config.toml"
        config_manager = ConfigManager(config_path=config_path)
        config_manager.add_account(
            name="test_account",
            username="named_user",
            secret="named_secret",
            project_id="11111",
            region="us",
        )

        with Workspace(
            account="test_account",
            _config_manager=config_manager,
        ) as ws:
            assert ws._credentials is not None
            assert ws._credentials.username == "named_user"
            assert ws._credentials.project_id == "11111"
            assert ws._account_name == "test_account"

    def test_default_account_credential_resolution(
        self,
        temp_dir: Path,
    ) -> None:
        """T016: Test default account credential resolution."""
        # Create config with default account
        config_path = temp_dir / "config.toml"
        config_manager = ConfigManager(config_path=config_path)
        config_manager.add_account(
            name="default_account",
            username="default_user",
            secret="default_secret",
            project_id="22222",
            region="in",
        )

        with Workspace(
            _config_manager=config_manager,
        ) as ws:
            assert ws._credentials is not None
            assert ws._credentials.username == "default_user"
            assert ws._credentials.region == "in"

    def test_config_error_when_no_credentials(
        self,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """T017: Test ConfigError when no credentials available."""
        # Clear env vars
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)
        monkeypatch.delenv("MP_PROJECT_ID", raising=False)
        monkeypatch.delenv("MP_REGION", raising=False)

        # Empty config + isolated OAuth dir so real tokens don't leak in
        config_path = temp_dir / "empty_config.toml"
        config_manager = ConfigManager(config_path=config_path)
        monkeypatch.setattr(config_manager, "_resolve_from_oauth", lambda **_kw: None)

        with pytest.raises(ConfigError):
            Workspace(_config_manager=config_manager)

    def test_project_id_override(
        self,
        mock_config_manager: MagicMock,
    ) -> None:
        """Test that project_id parameter overrides credentials."""
        ws = Workspace(
            project_id="override_project",
            _config_manager=mock_config_manager,
        )
        try:
            assert ws._credentials is not None
            assert ws._credentials.project_id == "override_project"
            # Original username should be preserved
            assert ws._credentials.username == "test_user"
        finally:
            ws.close()

    def test_region_override(
        self,
        mock_config_manager: MagicMock,
    ) -> None:
        """Test that region parameter overrides credentials."""
        ws = Workspace(
            region="eu",
            _config_manager=mock_config_manager,
        )
        try:
            assert ws._credentials is not None
            assert ws._credentials.region == "eu"
            # Original project_id should be preserved
            assert ws._credentials.project_id == "12345"
        finally:
            ws.close()

    def test_both_overrides(
        self,
        mock_config_manager: MagicMock,
    ) -> None:
        """Test that both project_id and region can be overridden."""
        ws = Workspace(
            project_id="new_project",
            region="in",
            _config_manager=mock_config_manager,
        )
        try:
            assert ws._credentials is not None
            assert ws._credentials.project_id == "new_project"
            assert ws._credentials.region == "in"
        finally:
            ws.close()


# =============================================================================
# Phase 6: US3 Live Query Tests
# =============================================================================


class TestLiveQueries:
    """Tests for live query methods (T043-T066)."""

    def test_segmentation_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T043: Test segmentation() delegation."""
        ws = workspace_factory()
        try:
            mock_live_query = MagicMock()
            mock_live_query.segmentation.return_value = SegmentationResult(
                event="Test",
                from_date="2024-01-01",
                to_date="2024-01-31",
                unit="day",
                segment_property=None,
                total=100,
                series={},
            )
            ws._live_query = mock_live_query

            result = ws.segmentation(
                "Test",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

            assert result.total == 100
            mock_live_query.segmentation.assert_called_once()
        finally:
            ws.close()

    def test_funnel_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T044: Test funnel() delegation."""
        ws = workspace_factory()
        try:
            mock_live_query = MagicMock()
            mock_live_query.funnel.return_value = FunnelResult(
                funnel_id=123,
                funnel_name="Test Funnel",
                from_date="2024-01-01",
                to_date="2024-01-31",
                conversion_rate=0.5,
                steps=[],
            )
            ws._live_query = mock_live_query

            result = ws.funnel(
                123,
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

            assert result.funnel_id == 123
            mock_live_query.funnel.assert_called_once()
        finally:
            ws.close()

    def test_retention_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T045: Test retention() delegation."""
        ws = workspace_factory()
        try:
            mock_live_query = MagicMock()
            mock_live_query.retention.return_value = RetentionResult(
                born_event="Sign Up",
                return_event="Purchase",
                from_date="2024-01-01",
                to_date="2024-01-31",
                unit="day",
                cohorts=[],
            )
            ws._live_query = mock_live_query

            result = ws.retention(
                born_event="Sign Up",
                return_event="Purchase",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

            assert result.born_event == "Sign Up"
            mock_live_query.retention.assert_called_once()
        finally:
            ws.close()

    def test_jql_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T046: Test jql() delegation."""
        ws = workspace_factory()
        try:
            mock_live_query = MagicMock()
            mock_live_query.jql.return_value = JQLResult(_raw=[{"count": 42}])
            ws._live_query = mock_live_query

            result = ws.jql("function main() { return 42; }")

            assert result.raw == [{"count": 42}]
            mock_live_query.jql.assert_called_once()
        finally:
            ws.close()

    def test_event_counts_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T047: Test event_counts() delegation."""
        ws = workspace_factory()
        try:
            mock_live_query = MagicMock()
            mock_live_query.event_counts.return_value = EventCountsResult(
                events=["A", "B"],
                from_date="2024-01-01",
                to_date="2024-01-31",
                unit="day",
                type="general",
                series={},
            )
            ws._live_query = mock_live_query

            result = ws.event_counts(
                ["A", "B"],
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

            assert result.events == ["A", "B"]
            mock_live_query.event_counts.assert_called_once()
        finally:
            ws.close()

    def test_property_counts_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T048: Test property_counts() delegation."""
        ws = workspace_factory()
        try:
            mock_live_query = MagicMock()
            mock_live_query.property_counts.return_value = PropertyCountsResult(
                event="Test",
                property_name="country",
                from_date="2024-01-01",
                to_date="2024-01-31",
                unit="day",
                type="general",
                series={},
            )
            ws._live_query = mock_live_query

            result = ws.property_counts(
                "Test",
                "country",
                from_date="2024-01-01",
                to_date="2024-01-31",
            )

            assert result.property_name == "country"
            mock_live_query.property_counts.assert_called_once()
        finally:
            ws.close()

    def test_activity_feed_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T049: Test activity_feed() delegation."""
        ws = workspace_factory()
        try:
            mock_live_query = MagicMock()
            mock_live_query.activity_feed.return_value = ActivityFeedResult(
                distinct_ids=["user1"],
                from_date=None,
                to_date=None,
                events=[],
            )
            ws._live_query = mock_live_query

            result = ws.activity_feed(["user1"])

            assert result.distinct_ids == ["user1"]
            mock_live_query.activity_feed.assert_called_once()
        finally:
            ws.close()

    def test_query_saved_report_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """Test query_saved_report() delegation."""
        ws = workspace_factory()
        try:
            mock_live_query = MagicMock()
            mock_live_query.query_saved_report.return_value = SavedReportResult(
                bookmark_id=12345,
                computed_at="2024-01-01",
                from_date="2024-01-01",
                to_date="2024-01-31",
                headers=[],
                series={},
            )
            ws._live_query = mock_live_query

            result = ws.query_saved_report(12345)

            assert result.bookmark_id == 12345
            mock_live_query.query_saved_report.assert_called_once()
        finally:
            ws.close()

    def test_frequency_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T051: Test frequency() delegation."""
        ws = workspace_factory()
        try:
            mock_live_query = MagicMock()
            mock_live_query.frequency.return_value = FrequencyResult(
                event=None,
                from_date="2024-01-01",
                to_date="2024-01-31",
                unit="day",
                addiction_unit="hour",
                data={},
            )
            ws._live_query = mock_live_query

            result = ws.frequency(from_date="2024-01-01", to_date="2024-01-31")

            assert result.unit == "day"
            mock_live_query.frequency.assert_called_once()
        finally:
            ws.close()

    def test_segmentation_numeric_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T052: Test segmentation_numeric() delegation."""
        ws = workspace_factory()
        try:
            mock_live_query = MagicMock()
            mock_live_query.segmentation_numeric.return_value = NumericBucketResult(
                event="Purchase",
                from_date="2024-01-01",
                to_date="2024-01-31",
                property_expr='properties["amount"]',
                unit="day",
                series={},
            )
            ws._live_query = mock_live_query

            result = ws.segmentation_numeric(
                "Purchase",
                from_date="2024-01-01",
                to_date="2024-01-31",
                on='properties["amount"]',
            )

            assert result.event == "Purchase"
            mock_live_query.segmentation_numeric.assert_called_once()
        finally:
            ws.close()

    def test_segmentation_sum_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T053: Test segmentation_sum() delegation."""
        ws = workspace_factory()
        try:
            mock_live_query = MagicMock()
            mock_live_query.segmentation_sum.return_value = NumericSumResult(
                event="Purchase",
                from_date="2024-01-01",
                to_date="2024-01-31",
                property_expr='properties["amount"]',
                unit="day",
                results={},
            )
            ws._live_query = mock_live_query

            result = ws.segmentation_sum(
                "Purchase",
                from_date="2024-01-01",
                to_date="2024-01-31",
                on='properties["amount"]',
            )

            assert result.event == "Purchase"
            mock_live_query.segmentation_sum.assert_called_once()
        finally:
            ws.close()

    def test_segmentation_average_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T054: Test segmentation_average() delegation."""
        ws = workspace_factory()
        try:
            mock_live_query = MagicMock()
            mock_live_query.segmentation_average.return_value = NumericAverageResult(
                event="Purchase",
                from_date="2024-01-01",
                to_date="2024-01-31",
                property_expr='properties["amount"]',
                unit="day",
                results={},
            )
            ws._live_query = mock_live_query

            result = ws.segmentation_average(
                "Purchase",
                from_date="2024-01-01",
                to_date="2024-01-31",
                on='properties["amount"]',
            )

            assert result.event == "Purchase"
            mock_live_query.segmentation_average.assert_called_once()
        finally:
            ws.close()


# =============================================================================
# Phase 7: US4 Discovery Tests
# =============================================================================


class TestDiscovery:
    """Tests for discovery methods (T067-T080)."""

    def test_events_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T067: Test events() delegation and caching."""
        ws = workspace_factory()
        try:
            mock_discovery = MagicMock()
            mock_discovery.list_events.return_value = ["Event A", "Event B"]
            ws._discovery = mock_discovery

            result = ws.events()

            assert result == ["Event A", "Event B"]
            mock_discovery.list_events.assert_called_once()
        finally:
            ws.close()

    def test_properties_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T068: Test properties() delegation."""
        ws = workspace_factory()
        try:
            mock_discovery = MagicMock()
            mock_discovery.list_properties.return_value = ["prop_a", "prop_b"]
            ws._discovery = mock_discovery

            result = ws.properties("Event A")

            assert result == ["prop_a", "prop_b"]
            mock_discovery.list_properties.assert_called_once_with("Event A")
        finally:
            ws.close()

    def test_property_values_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T069: Test property_values() delegation."""
        ws = workspace_factory()
        try:
            mock_discovery = MagicMock()
            mock_discovery.list_property_values.return_value = ["val1", "val2"]
            ws._discovery = mock_discovery

            result = ws.property_values("country", event="Purchase", limit=50)

            assert result == ["val1", "val2"]
            mock_discovery.list_property_values.assert_called_once_with(
                "country", event="Purchase", limit=50
            )
        finally:
            ws.close()

    def test_funnels_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T070: Test funnels() delegation."""
        ws = workspace_factory()
        try:
            mock_discovery = MagicMock()
            mock_discovery.list_funnels.return_value = [
                FunnelInfo(funnel_id=1, name="Funnel 1")
            ]
            ws._discovery = mock_discovery

            result = ws.funnels()

            assert len(result) == 1
            assert result[0].funnel_id == 1
            mock_discovery.list_funnels.assert_called_once()
        finally:
            ws.close()

    def test_cohorts_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T071: Test cohorts() delegation."""
        ws = workspace_factory()
        try:
            mock_discovery = MagicMock()
            mock_discovery.list_cohorts.return_value = [
                SavedCohort(
                    id=1,
                    name="Cohort 1",
                    count=100,
                    description="",
                    created="2024-01-01",
                    is_visible=True,
                )
            ]
            ws._discovery = mock_discovery

            result = ws.cohorts()

            assert len(result) == 1
            assert result[0].id == 1
            mock_discovery.list_cohorts.assert_called_once()
        finally:
            ws.close()

    def test_top_events_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T072: Test top_events() delegation (not cached)."""
        ws = workspace_factory()
        try:
            mock_discovery = MagicMock()
            mock_discovery.list_top_events.return_value = [
                TopEvent(event="Event A", count=100, percent_change=0.1)
            ]
            ws._discovery = mock_discovery

            result = ws.top_events(type="general", limit=10)

            assert len(result) == 1
            mock_discovery.list_top_events.assert_called_once_with(
                type="general", limit=10
            )
        finally:
            ws.close()

    def test_clear_discovery_cache(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """T073: Test clear_discovery_cache()."""
        ws = workspace_factory()
        try:
            mock_discovery = MagicMock()
            ws._discovery = mock_discovery

            ws.clear_discovery_cache()

            mock_discovery.clear_cache.assert_called_once()
        finally:
            ws.close()

    def test_lexicon_schemas_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """Test lexicon_schemas() delegates to discovery service."""
        ws = workspace_factory()
        try:
            mock_discovery = MagicMock()
            mock_discovery.list_schemas.return_value = [
                LexiconSchema(
                    entity_type="event",
                    name="Purchase",
                    schema_json=LexiconDefinition(
                        description="User made a purchase",
                        properties={},
                        metadata=None,
                    ),
                ),
                LexiconSchema(
                    entity_type="event",
                    name="Sign Up",
                    schema_json=LexiconDefinition(
                        description="User signed up",
                        properties={},
                        metadata=None,
                    ),
                ),
            ]
            ws._discovery = mock_discovery

            result = ws.lexicon_schemas()

            assert len(result) == 2
            assert result[0].name == "Purchase"
            assert result[1].name == "Sign Up"
            mock_discovery.list_schemas.assert_called_once_with(entity_type=None)
        finally:
            ws.close()

    def test_lexicon_schemas_with_entity_type_filter(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """Test lexicon_schemas() passes entity_type filter to discovery service."""
        ws = workspace_factory()
        try:
            mock_discovery = MagicMock()
            mock_discovery.list_schemas.return_value = [
                LexiconSchema(
                    entity_type="profile",
                    name="Plan",
                    schema_json=LexiconDefinition(
                        description="User subscription plan",
                        properties={},
                        metadata=None,
                    ),
                ),
            ]
            ws._discovery = mock_discovery

            result = ws.lexicon_schemas(entity_type="profile")

            assert len(result) == 1
            assert result[0].entity_type == "profile"
            mock_discovery.list_schemas.assert_called_once_with(entity_type="profile")
        finally:
            ws.close()

    def test_lexicon_schema_delegation(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """Test lexicon_schema() delegates to discovery service."""
        ws = workspace_factory()
        try:
            mock_discovery = MagicMock()
            mock_discovery.get_schema.return_value = LexiconSchema(
                entity_type="event",
                name="Purchase",
                schema_json=LexiconDefinition(
                    description="User made a purchase",
                    properties={},
                    metadata=None,
                ),
            )
            ws._discovery = mock_discovery

            result = ws.lexicon_schema("event", "Purchase")

            assert result.entity_type == "event"
            assert result.name == "Purchase"
            assert result.schema_json.description == "User made a purchase"
            mock_discovery.get_schema.assert_called_once_with("event", "Purchase")
        finally:
            ws.close()


# =============================================================================
# Context Manager Tests
# =============================================================================


class TestContextManager:
    """Tests for context manager protocol."""

    def test_context_manager_enter_returns_self(
        self,
        workspace_factory: Callable[..., Workspace],
    ) -> None:
        """Test __enter__ returns self."""
        ws = workspace_factory()
        with ws as entered:
            assert entered is ws

    def test_close_calls_api_client_close(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """Test that close() calls api_client.close()."""
        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        ws.close()
        mock_api_client.close.assert_called_once()


# =============================================================================
# Test Credentials Tests
# =============================================================================


class TestTestCredentials:
    """Tests for Workspace.test_credentials() static method."""

    def test_test_credentials_with_env_vars(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test test_credentials() with environment variables."""
        # Mock the API client
        from unittest.mock import patch

        monkeypatch.setenv("MP_USERNAME", "test_user")
        monkeypatch.setenv("MP_SECRET", "test_secret")
        monkeypatch.setenv("MP_PROJECT_ID", "12345")
        monkeypatch.setenv("MP_REGION", "us")

        mock_api_client = MagicMock()
        mock_api_client.get_events.return_value = ["event1", "event2", "event3"]

        with patch("mixpanel_data.workspace.MixpanelAPIClient") as MockAPIClient:
            MockAPIClient.return_value = mock_api_client

            result = Workspace.test_credentials()

            assert result["success"] is True
            assert result["project_id"] == "12345"
            assert result["region"] == "us"
            assert result["events_found"] == 3
            mock_api_client.close.assert_called_once()

    def test_test_credentials_with_named_account(
        self,
        temp_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test test_credentials() with a named account."""
        from unittest.mock import patch

        # Clear env vars
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)
        monkeypatch.delenv("MP_PROJECT_ID", raising=False)
        monkeypatch.delenv("MP_REGION", raising=False)

        # Create config with named account
        config_path = temp_dir / "config.toml"
        config_manager = ConfigManager(config_path=config_path)
        config_manager.add_account(
            name="prod",
            username="prod_user",
            secret="prod_secret",
            project_id="99999",
            region="eu",
        )

        mock_api_client = MagicMock()
        mock_api_client.get_events.return_value = ["event1"]

        with (
            patch("mixpanel_data.workspace.MixpanelAPIClient") as MockAPIClient,
            patch("mixpanel_data.workspace.ConfigManager") as MockConfigManager,
        ):
            MockAPIClient.return_value = mock_api_client
            MockConfigManager.return_value = config_manager

            result = Workspace.test_credentials("prod")

            assert result["success"] is True
            assert result["account"] == "prod"
            assert result["project_id"] == "99999"
            assert result["region"] == "eu"
            assert result["events_found"] == 1

    def test_test_credentials_returns_account_none_for_env_vars(
        self,
        monkeypatch: pytest.MonkeyPatch,
        temp_dir: Path,
    ) -> None:
        """Test that test_credentials() returns account=None when using env vars."""
        from unittest.mock import patch

        # Clear env first and use a config without default account
        monkeypatch.delenv("MP_USERNAME", raising=False)
        monkeypatch.delenv("MP_SECRET", raising=False)
        monkeypatch.delenv("MP_PROJECT_ID", raising=False)
        monkeypatch.delenv("MP_REGION", raising=False)

        # Set env vars
        monkeypatch.setenv("MP_USERNAME", "env_user")
        monkeypatch.setenv("MP_SECRET", "env_secret")
        monkeypatch.setenv("MP_PROJECT_ID", "12345")
        monkeypatch.setenv("MP_REGION", "us")

        # Empty config (no accounts)
        config_path = temp_dir / "config.toml"
        config_manager = ConfigManager(config_path=config_path)

        mock_api_client = MagicMock()
        mock_api_client.get_events.return_value = []

        with (
            patch("mixpanel_data.workspace.MixpanelAPIClient") as MockAPIClient,
            patch("mixpanel_data.workspace.ConfigManager") as MockConfigManager,
        ):
            MockAPIClient.return_value = mock_api_client
            MockConfigManager.return_value = config_manager

            result = Workspace.test_credentials()

            assert result["success"] is True
            assert result["account"] is None  # No named account used


# =============================================================================
# Limit Validation Tests
# =============================================================================


class TestLimitValidation:
    """Tests for limit parameter validation on stream_events."""

    def test_stream_events_rejects_limit_over_100000(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """stream_events should raise ValueError if limit exceeds 100000."""
        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        try:
            with pytest.raises(ValueError, match="limit must be at most 100000"):
                # Need to consume iterator to trigger validation
                list(
                    ws.stream_events(
                        from_date="2024-01-01",
                        to_date="2024-01-31",
                        limit=100001,
                    )
                )
        finally:
            ws.close()

    def test_stream_events_rejects_limit_zero_or_negative(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """stream_events should raise ValueError if limit is zero or negative."""
        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        try:
            with pytest.raises(ValueError, match="limit must be at least 1"):
                list(
                    ws.stream_events(
                        from_date="2024-01-01",
                        to_date="2024-01-31",
                        limit=0,
                    )
                )
        finally:
            ws.close()


# =============================================================================
# Phase 6: Workspace Discovery (T064-T065b)
# =============================================================================


class TestDiscoverWorkspaces:
    """T064-T065b: Tests for Workspace.discover_workspaces()."""

    def test_discover_workspaces_delegates_to_me_svc(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """discover_workspaces should delegate to _me_svc.list_workspaces."""
        from mixpanel_data._internal.me import MeWorkspaceInfo

        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        expected = [
            MeWorkspaceInfo(id=1, name="Default", project_id=12345, is_default=True),
            MeWorkspaceInfo(id=2, name="Staging", project_id=12345, is_default=False),
        ]
        mock_me_svc = MagicMock()
        mock_me_svc.list_workspaces.return_value = expected
        ws._me_service = mock_me_svc

        result = ws.discover_workspaces()

        # Should use current project_id from credentials
        mock_me_svc.list_workspaces.assert_called_once_with(project_id="12345")
        assert result == expected

    def test_discover_workspaces_with_explicit_project(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """discover_workspaces with explicit project_id passes it through."""
        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        mock_me_svc = MagicMock()
        mock_me_svc.list_workspaces.return_value = []
        ws._me_service = mock_me_svc

        ws.discover_workspaces(project_id="9999999")

        mock_me_svc.list_workspaces.assert_called_once_with(project_id="9999999")


# =============================================================================
# Phase 7: Switch Project / Workspace (T071-T078)
# =============================================================================


class TestSwitchProject:
    """T071-T074: Tests for Workspace.switch_project()."""

    def test_switch_project_creates_new_api_client(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """switch_project should create a new API client via with_project."""
        new_mock_client = MagicMock()
        new_mock_client._credentials = Credentials(
            username="test_user",
            secret=SecretStr("test_secret"),
            project_id="9999999",
            region="us",
        )
        mock_api_client.with_project.return_value = new_mock_client

        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        ws.switch_project("9999999")

        mock_api_client.with_project.assert_called_once_with(
            "9999999", workspace_id=None
        )
        assert ws._api_client is new_mock_client

    def test_switch_project_with_workspace_id(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """switch_project should pass workspace_id to with_project."""
        new_mock_client = MagicMock()
        new_mock_client._credentials = Credentials(
            username="test_user",
            secret=SecretStr("test_secret"),
            project_id="9999999",
            region="us",
        )
        mock_api_client.with_project.return_value = new_mock_client

        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        ws.switch_project("9999999", workspace_id=42)

        mock_api_client.with_project.assert_called_once_with("9999999", workspace_id=42)

    def test_switch_project_clears_discovery_cache(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """switch_project should clear discovery and me caches."""
        new_mock_client = MagicMock()
        new_mock_client._credentials = Credentials(
            username="test_user",
            secret=SecretStr("test_secret"),
            project_id="9999999",
            region="us",
        )
        mock_api_client.with_project.return_value = new_mock_client

        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        # Pre-populate caches
        ws._discovery = MagicMock()
        ws._live_query = MagicMock()
        ws._me_service = MagicMock()

        ws.switch_project("9999999")

        assert ws._discovery is None
        assert ws._live_query is None
        assert ws._me_service is None

    def test_switch_project_updates_credentials(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """switch_project should update _credentials to match new client."""
        new_creds = Credentials(
            username="test_user",
            secret=SecretStr("test_secret"),
            project_id="9999999",
            region="us",
        )
        new_mock_client = MagicMock()
        new_mock_client._credentials = new_creds
        mock_api_client.with_project.return_value = new_mock_client

        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        ws.switch_project("9999999")

        assert ws._credentials is not None
        assert ws._credentials.project_id == "9999999"


class TestSwitchWorkspace:
    """T072: Tests for Workspace.switch_workspace()."""

    def test_switch_workspace_delegates_to_set_workspace_id(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """switch_workspace should call set_workspace_id on the API client."""
        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        ws.switch_workspace(3448413)

        mock_api_client.set_workspace_id.assert_called_with(3448413)


class TestCurrentProject:
    """T074: Tests for Workspace.current_project property."""

    def test_current_project_returns_project_context(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """current_project should return a ProjectContext with project_id."""
        from mixpanel_data._internal.auth_credential import ProjectContext

        mock_api_client.workspace_id = None
        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        # Set up me_svc mock to avoid API calls
        mock_me_svc = MagicMock()
        mock_me_svc.find_project.return_value = None
        ws._me_service = mock_me_svc

        ctx = ws.current_project
        assert isinstance(ctx, ProjectContext)
        assert ctx.project_id == "12345"
        assert ctx.workspace_id is None

    def test_current_project_with_workspace_id(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """current_project should include workspace_id when set."""
        from mixpanel_data._internal.auth_credential import ProjectContext

        mock_api_client.workspace_id = 42
        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        mock_me_svc = MagicMock()
        mock_me_svc.find_project.return_value = None
        mock_me_svc.list_workspaces.return_value = []
        ws._me_service = mock_me_svc

        ctx = ws.current_project
        assert isinstance(ctx, ProjectContext)
        assert ctx.workspace_id == 42

    def test_current_project_enriches_names(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """current_project should include names from /me when available."""
        from mixpanel_data._internal.me import MeProjectInfo, MeWorkspaceInfo

        mock_api_client.workspace_id = 100

        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        mock_me_svc = MagicMock()
        mock_me_svc.find_project.return_value = MeProjectInfo(
            name="AI Demo", organization_id=1
        )
        mock_me_svc.list_workspaces.return_value = [
            MeWorkspaceInfo(id=100, name="Default", project_id=12345),
        ]
        ws._me_service = mock_me_svc

        ctx = ws.current_project
        assert ctx.project_name == "AI Demo"
        assert ctx.workspace_name == "Default"

    def test_current_project_no_credentials_raises(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """current_project should raise ConfigError with no credentials."""
        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        ws._credentials = None

        with pytest.raises(ConfigError, match="No credentials"):
            _ = ws.current_project


class TestCurrentCredential:
    """T074: Tests for Workspace.current_credential property."""

    def test_current_credential_legacy_path(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """current_credential should build AuthCredential from Credentials."""
        from mixpanel_data._internal.auth_credential import (
            AuthCredential,
            CredentialType,
        )

        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )

        cred = ws.current_credential
        assert isinstance(cred, AuthCredential)
        assert cred.type == CredentialType.service_account
        assert cred.region == "us"
        assert cred.username == "test_user"
        assert cred.name == "default"

    def test_current_credential_with_account_name(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """current_credential should use account name when provided."""
        ws = Workspace(
            account="staging",
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )

        cred = ws.current_credential
        assert cred.name == "staging"

    def test_current_credential_v2_path(
        self,
        mock_api_client: MagicMock,
    ) -> None:
        """current_credential should return session auth for v2 path."""
        from mixpanel_data._internal.auth_credential import (
            AuthCredential,
            CredentialType,
            ProjectContext,
            ResolvedSession,
        )

        mock_cm = MagicMock()
        auth = AuthCredential(
            name="demo-sa",
            type=CredentialType.service_account,
            region="us",
            username="sa-user",
            secret=SecretStr("secret"),
        )
        project = ProjectContext(project_id="3713224")
        session = ResolvedSession(auth=auth, project=project)
        mock_cm.resolve_session.return_value = session

        ws = Workspace(
            credential="demo-sa",
            project_id="3713224",
            _config_manager=mock_cm,
            _api_client=mock_api_client,
        )

        cred = ws.current_credential
        assert cred is auth
        assert cred.name == "demo-sa"

    def test_current_credential_no_credentials_raises(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """current_credential should raise ConfigError with no credentials."""
        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )
        ws._credentials = None
        ws._resolved_session = None

        with pytest.raises(ConfigError, match="No credentials"):
            _ = ws.current_credential


# =============================================================================
# Codex Review Fixes — Regression Tests
# =============================================================================


class TestOAuthProjectOverridePreservation:
    """Tests for Fix 1: OAuth credentials preserved on project/region override."""

    def test_oauth_auth_method_preserved_on_project_override(
        self,
        mock_api_client: MagicMock,
    ) -> None:
        """OAuth auth_method is preserved when project_id overrides credentials."""
        oauth_creds = Credentials(
            username="",
            secret=SecretStr(""),
            project_id="original",
            region="us",
            auth_method=AuthMethod.oauth,
            oauth_access_token=SecretStr("test-token"),
        )
        manager = MagicMock(spec=ConfigManager)
        manager.resolve_credentials.return_value = oauth_creds
        manager.config_version.return_value = 1

        ws = Workspace(
            project_id="override-project",
            _config_manager=manager,
            _api_client=mock_api_client,
        )

        assert ws._credentials is not None
        assert ws._credentials.auth_method == AuthMethod.oauth
        assert ws._credentials.oauth_access_token is not None
        assert ws._credentials.oauth_access_token.get_secret_value() == "test-token"
        assert ws._credentials.project_id == "override-project"

    def test_oauth_auth_method_preserved_on_region_override(
        self,
        mock_api_client: MagicMock,
    ) -> None:
        """OAuth auth_method is preserved when region overrides credentials."""
        oauth_creds = Credentials(
            username="",
            secret=SecretStr(""),
            project_id="12345",
            region="us",
            auth_method=AuthMethod.oauth,
            oauth_access_token=SecretStr("test-token"),
        )
        manager = MagicMock(spec=ConfigManager)
        manager.resolve_credentials.return_value = oauth_creds
        manager.config_version.return_value = 1

        ws = Workspace(
            region="eu",
            _config_manager=manager,
            _api_client=mock_api_client,
        )

        assert ws._credentials is not None
        assert ws._credentials.auth_method == AuthMethod.oauth
        assert ws._credentials.region == "eu"

    def test_basic_auth_still_works_on_project_override(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """Basic auth credentials still work with project override (regression)."""
        mock_config_manager.config_version.return_value = 1

        ws = Workspace(
            project_id="override-project",
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )

        assert ws._credentials is not None
        assert ws._credentials.auth_method == AuthMethod.basic
        assert ws._credentials.project_id == "override-project"
        assert ws._credentials.username == "test_user"


class TestCurrentCredentialOAuth:
    """Tests for Fix 2: current_credential handles OAuth legacy path."""

    def test_current_credential_returns_oauth_type_for_oauth_creds(
        self,
        mock_api_client: MagicMock,
    ) -> None:
        """current_credential returns CredentialType.oauth for OAuth sessions."""
        from mixpanel_data._internal.auth_credential import CredentialType

        oauth_creds = Credentials(
            username="",
            secret=SecretStr(""),
            project_id="12345",
            region="us",
            auth_method=AuthMethod.oauth,
            oauth_access_token=SecretStr("test-token"),
        )
        manager = MagicMock(spec=ConfigManager)
        manager.resolve_credentials.return_value = oauth_creds
        manager.config_version.return_value = 1

        ws = Workspace(
            _config_manager=manager,
            _api_client=mock_api_client,
        )

        cred = ws.current_credential
        assert cred.type == CredentialType.oauth
        assert cred.oauth_access_token is not None
        assert cred.oauth_access_token.get_secret_value() == "test-token"

    def test_current_credential_returns_service_account_for_basic_auth(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """current_credential returns CredentialType.service_account for basic auth."""
        from mixpanel_data._internal.auth_credential import CredentialType

        mock_config_manager.config_version.return_value = 1

        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )

        cred = ws.current_credential
        assert cred.type == CredentialType.service_account
        assert cred.username == "test_user"


class TestV2ConfigAutoDetection:
    """Tests for Fix 3: v2 config auto-detected when credential is None."""

    def test_v2_config_uses_resolve_session_without_credential_param(
        self,
        mock_api_client: MagicMock,
    ) -> None:
        """Workspace() with v2 config routes to resolve_session, not resolve_credentials."""
        from mixpanel_data._internal.auth_credential import (
            AuthCredential,
            CredentialType,
            ProjectContext,
            ResolvedSession,
        )

        session = ResolvedSession(
            auth=AuthCredential(
                name="demo-sa",
                type=CredentialType.service_account,
                region="us",
                username="sa_user",
                secret=SecretStr("sa_secret"),
            ),
            project=ProjectContext(project_id="99999"),
        )

        manager = MagicMock(spec=ConfigManager)
        manager.config_version.return_value = 2
        manager.resolve_session.return_value = session

        ws = Workspace(
            _config_manager=manager,
            _api_client=mock_api_client,
        )

        # Should call resolve_session, NOT resolve_credentials
        manager.resolve_session.assert_called_once_with(
            credential=None,
            project_id=None,
            workspace_id=None,
        )
        manager.resolve_credentials.assert_not_called()
        assert ws._resolved_session is session
        assert ws._credentials is not None
        assert ws._credentials.project_id == "99999"

    def test_v1_config_still_uses_resolve_credentials(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """Workspace() with v1 config still uses legacy resolve_credentials."""
        mock_config_manager.config_version.return_value = 1

        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )

        mock_config_manager.resolve_credentials.assert_called_once()
        assert ws._resolved_session is None
        assert ws._credentials is not None


class TestWorkspaceIdPropagation:
    """Tests for Fix 4: workspace_id from resolved session propagated."""

    def test_session_workspace_id_propagated_when_param_is_none(
        self,
        mock_api_client: MagicMock,
    ) -> None:
        """workspace_id from session propagates to _initial_workspace_id."""
        from mixpanel_data._internal.auth_credential import (
            AuthCredential,
            CredentialType,
            ProjectContext,
            ResolvedSession,
        )

        session = ResolvedSession(
            auth=AuthCredential(
                name="demo-sa",
                type=CredentialType.service_account,
                region="us",
                username="sa_user",
                secret=SecretStr("sa_secret"),
            ),
            project=ProjectContext(project_id="99999", workspace_id=42),
        )

        manager = MagicMock(spec=ConfigManager)
        manager.config_version.return_value = 2
        manager.resolve_session.return_value = session

        ws = Workspace(
            _config_manager=manager,
            _api_client=mock_api_client,
        )

        assert ws._initial_workspace_id == 42
        mock_api_client.set_workspace_id.assert_called_once_with(42)

    def test_explicit_workspace_id_overrides_session(
        self,
        mock_api_client: MagicMock,
    ) -> None:
        """Explicit workspace_id param takes priority over session."""
        from mixpanel_data._internal.auth_credential import (
            AuthCredential,
            CredentialType,
            ProjectContext,
            ResolvedSession,
        )

        session = ResolvedSession(
            auth=AuthCredential(
                name="demo-sa",
                type=CredentialType.service_account,
                region="us",
                username="sa_user",
                secret=SecretStr("sa_secret"),
            ),
            project=ProjectContext(project_id="99999", workspace_id=42),
        )

        manager = MagicMock(spec=ConfigManager)
        manager.config_version.return_value = 2
        manager.resolve_session.return_value = session

        ws = Workspace(
            workspace_id=999,
            _config_manager=manager,
            _api_client=mock_api_client,
        )

        assert ws._initial_workspace_id == 999
        mock_api_client.set_workspace_id.assert_called_once_with(999)

    def test_no_session_no_workspace_id_stays_none(
        self,
        mock_config_manager: MagicMock,
        mock_api_client: MagicMock,
    ) -> None:
        """Without session or explicit param, workspace_id stays None."""
        mock_config_manager.config_version.return_value = 1

        ws = Workspace(
            _config_manager=mock_config_manager,
            _api_client=mock_api_client,
        )

        assert ws._initial_workspace_id is None
        mock_api_client.set_workspace_id.assert_not_called()
