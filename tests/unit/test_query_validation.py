"""Unit tests for query argument validation rules.

Tests validation rules V7-V11 (time range) for US1,
V1-V3 (aggregation) for US2, V13-V14 (per-Metric) for US2,
V4 (formula) for US5, V5-V6 (analysis mode) for US6.

Validation is tested via Workspace._validate_query_args() private method.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from mixpanel_data import Workspace
from mixpanel_data._internal.config import ConfigManager, Credentials

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
def ws(mock_config_manager: MagicMock) -> Workspace:
    """Create Workspace with mocked dependencies for validation testing."""
    return Workspace(_config_manager=mock_config_manager)


# =============================================================================
# T007: Time range validation rules (V7-V11)
# =============================================================================


class TestTimeRangeValidation:
    """Tests for time range validation rules V7-V11."""

    def test_v7_last_must_be_positive(self, ws: Workspace) -> None:
        """V7: last must be a positive integer."""
        with pytest.raises(ValueError, match="last must be a positive integer"):
            ws.query("Login", last=0)

    def test_v7_last_negative(self, ws: Workspace) -> None:
        """V7: negative last raises ValueError."""
        with pytest.raises(ValueError, match="last must be a positive integer"):
            ws.query("Login", last=-5)

    def test_v8_from_date_format(self, ws: Workspace) -> None:
        """V8: from_date must be YYYY-MM-DD format."""
        with pytest.raises(ValueError, match="from_date must be YYYY-MM-DD format"):
            ws.query("Login", from_date="01/01/2024")

    def test_v8_to_date_format(self, ws: Workspace) -> None:
        """V8: to_date must also be YYYY-MM-DD format."""
        with pytest.raises(ValueError, match="to_date must be YYYY-MM-DD format"):
            ws.query("Login", from_date="2024-01-01", to_date="Jan 31 2024")

    def test_v9_to_date_requires_from_date(self, ws: Workspace) -> None:
        """V9: to_date without from_date raises ValueError."""
        with pytest.raises(ValueError, match="to_date requires from_date"):
            ws.query("Login", to_date="2024-01-31")

    def test_v10_last_with_explicit_dates(self, ws: Workspace) -> None:
        """V10: Cannot combine non-default last with explicit dates."""
        with pytest.raises(
            ValueError, match="Cannot combine last=.*with explicit dates"
        ):
            ws.query("Login", last=7, from_date="2024-01-01", to_date="2024-01-31")

    def test_v10_default_last_with_dates_ok(self, ws: Workspace) -> None:
        """V10: Default last (30) with explicit dates is OK (last is ignored)."""
        # This should NOT raise — default last=30 is overridden by explicit dates
        # Will fail because query() doesn't exist yet, but validation shouldn't raise
        try:
            ws.query("Login", from_date="2024-01-01", to_date="2024-01-31")
        except ValueError:
            pytest.fail("Default last with explicit dates should not raise ValueError")
        except Exception:
            # Other exceptions (e.g., API errors) are OK — validation passed
            pass

    def test_valid_date_range_passes(self, ws: Workspace) -> None:
        """Valid from_date/to_date passes validation."""
        try:
            ws.query("Login", from_date="2024-01-01", to_date="2024-01-31")
        except ValueError:
            pytest.fail("Valid date range should not raise ValueError")
        except Exception:
            pass

    def test_valid_last_passes(self, ws: Workspace) -> None:
        """Valid positive last passes validation."""
        try:
            ws.query("Login", last=7)
        except ValueError:
            pytest.fail("Positive last should not raise ValueError")
        except Exception:
            pass


# =============================================================================
# T016: Aggregation validation rules V1-V3 (US2)
# =============================================================================


class TestAggregationValidation:
    """Tests for aggregation validation rules V1-V3."""

    def test_v1_property_math_requires_property(self, ws: Workspace) -> None:
        """V1: Property-based math requires math_property."""
        with pytest.raises(ValueError, match="requires math_property"):
            ws.query("Purchase", math="average")

    def test_v1_all_property_math_types(self, ws: Workspace) -> None:
        """V1: All property math types require math_property."""
        for math_type in (
            "average",
            "median",
            "min",
            "max",
            "sum",
            "p25",
            "p75",
            "p90",
            "p99",
        ):
            with pytest.raises(ValueError, match="requires math_property"):
                ws.query("Purchase", math=math_type)

    def test_v2_non_property_math_rejects_property(self, ws: Workspace) -> None:
        """V2: Non-property math with math_property raises ValueError."""
        with pytest.raises(ValueError, match="math_property is only valid"):
            ws.query("Login", math="total", math_property="amount")

    def test_v2_unique_rejects_property(self, ws: Workspace) -> None:
        """V2: 'unique' math rejects math_property."""
        with pytest.raises(ValueError, match="math_property is only valid"):
            ws.query("Login", math="unique", math_property="amount")

    def test_v3_per_user_incompatible_with_dau(self, ws: Workspace) -> None:
        """V3: per_user is incompatible with DAU."""
        with pytest.raises(ValueError, match="per_user is incompatible"):
            ws.query("Login", math="dau", per_user="average")

    def test_v3_per_user_incompatible_with_wau(self, ws: Workspace) -> None:
        """V3: per_user is incompatible with WAU."""
        with pytest.raises(ValueError, match="per_user is incompatible"):
            ws.query("Login", math="wau", per_user="total")

    def test_v3_per_user_incompatible_with_mau(self, ws: Workspace) -> None:
        """V3: per_user is incompatible with MAU."""
        with pytest.raises(ValueError, match="per_user is incompatible"):
            ws.query("Login", math="mau", per_user="min")

    def test_valid_property_math_with_property(self, ws: Workspace) -> None:
        """Valid property math with math_property passes validation."""
        try:
            ws.query("Purchase", math="average", math_property="amount")
        except ValueError:
            pytest.fail("Property math with math_property should not raise")
        except Exception:
            pass

    def test_valid_per_user_with_total(self, ws: Workspace) -> None:
        """Valid per_user with non-DAU math passes validation."""
        try:
            ws.query("Purchase", math="total", per_user="average")
        except ValueError:
            pytest.fail("per_user with total should not raise")
        except Exception:
            pass


# =============================================================================
# T018: Per-Metric validation V13-V14 (US2)
# =============================================================================


class TestPerMetricValidation:
    """Tests for per-Metric validation rules V13-V14."""

    def test_v13_metric_property_math_requires_property(self, ws: Workspace) -> None:
        """V13: Metric with property math requires property."""
        from mixpanel_data import Metric

        with pytest.raises(ValueError, match="requires property"):
            ws.query(Metric("Purchase", math="average"))

    def test_v14_metric_non_property_math_rejects_property(self, ws: Workspace) -> None:
        """V14: Metric with non-property math rejects property."""
        from mixpanel_data import Metric

        with pytest.raises(ValueError, match="property is only valid"):
            ws.query(Metric("Login", math="total", property="amount"))

    def test_metric_per_user_with_dau(self, ws: Workspace) -> None:
        """Per-Metric per_user incompatible with DAU."""
        from mixpanel_data import Metric

        with pytest.raises(ValueError, match="per_user is incompatible"):
            ws.query(Metric("Login", math="dau", per_user="average"))


# =============================================================================
# T035: Formula validation V4 (US5)
# =============================================================================


class TestFormulaValidation:
    """Tests for formula validation rule V4."""

    def test_v4_formula_requires_two_events(self, ws: Workspace) -> None:
        """V4: Formula requires at least 2 events."""
        with pytest.raises(ValueError, match="formula requires at least 2 events"):
            ws.query("Login", formula="A * 100")

    def test_v4_formula_with_two_events_ok(self, ws: Workspace) -> None:
        """V4: Formula with 2 events passes validation."""
        try:
            ws.query(["Login", "Signup"], formula="(B / A) * 100")
        except ValueError:
            pytest.fail("Formula with 2 events should not raise")
        except Exception:
            pass


# =============================================================================
# T040: Analysis mode validation V5-V6 (US6)
# =============================================================================


class TestAnalysisModeValidation:
    """Tests for analysis mode validation rules V5-V6."""

    def test_v5_rolling_and_cumulative_exclusive(self, ws: Workspace) -> None:
        """V5: Rolling and cumulative are mutually exclusive."""
        with pytest.raises(ValueError, match="mutually exclusive"):
            ws.query("Login", rolling=7, cumulative=True)

    def test_v6_rolling_must_be_positive(self, ws: Workspace) -> None:
        """V6: Rolling must be a positive integer."""
        with pytest.raises(ValueError, match="rolling must be a positive integer"):
            ws.query("Login", rolling=0)

    def test_v6_rolling_negative(self, ws: Workspace) -> None:
        """V6: Negative rolling raises ValueError."""
        with pytest.raises(ValueError, match="rolling must be a positive integer"):
            ws.query("Login", rolling=-3)


# =============================================================================
# GroupBy validation V11-V12 (US3)
# =============================================================================


class TestGroupByValidation:
    """Tests for GroupBy validation rules V11-V12."""

    def test_v11_bucket_min_requires_bucket_size(self, ws: Workspace) -> None:
        """V11: bucket_min requires bucket_size."""
        from mixpanel_data import GroupBy

        with pytest.raises(
            ValueError, match="bucket_min/bucket_max require bucket_size"
        ):
            ws.query("Purchase", group_by=GroupBy("amount", bucket_min=0))

    def test_v11_bucket_max_requires_bucket_size(self, ws: Workspace) -> None:
        """V11: bucket_max requires bucket_size."""
        from mixpanel_data import GroupBy

        with pytest.raises(
            ValueError, match="bucket_min/bucket_max require bucket_size"
        ):
            ws.query("Purchase", group_by=GroupBy("amount", bucket_max=100))

    def test_v12_bucket_size_must_be_positive(self, ws: Workspace) -> None:
        """V12: bucket_size must be positive."""
        from mixpanel_data import GroupBy

        with pytest.raises(ValueError, match="bucket_size must be positive"):
            ws.query("Purchase", group_by=GroupBy("amount", bucket_size=0))

    def test_v12_bucket_size_negative(self, ws: Workspace) -> None:
        """V12: Negative bucket_size raises ValueError."""
        from mixpanel_data import GroupBy

        with pytest.raises(ValueError, match="bucket_size must be positive"):
            ws.query("Purchase", group_by=GroupBy("amount", bucket_size=-10))
