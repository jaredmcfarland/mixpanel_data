"""Unit tests for ``src/mixpanel_data/_internal/bookmark_schema.py`` models.

Each model in ``bookmark_schema.py`` mirrors a canonical Pydantic class
in ``/Users/jaredmcfarland/Developer/analytics/lib/common/mxpnl/report/
bookmarks/`` (and its sibling MCP package). These tests verify, for
each model:

- valid input passes without errors
- required fields rejected when missing
- extra fields rejected (``extra="forbid"`` mirrors server)
- legacy ``Ignore[T]`` fields tolerated (don't reject; don't surface)
- discriminated unions select the right variant
- enum-like Literal fields reject invalid values

Each test class names the canonical source file + line in its docstring
for drift-tracking.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

# =============================================================================
# Sorting models — mirrors
# /Users/jaredmcfarland/Developer/analytics/lib/common/mxpnl/report/
# bookmarks/insights/sorting.py
# =============================================================================


class TestSortByColumnsConfig:
    """Tests mirroring sorting.py:61 ``SortByColumnsConfig``.

    Discriminator ``sortBy=Literal["column"]``, requires ``colSortAttrs``,
    tolerates legacy ``sortOrder`` and ``viewNLimit`` via ``Ignore[T]``.
    """

    def test_valid_minimal_passes(self) -> None:
        """Minimal valid config: sortBy=column + empty colSortAttrs."""
        from mixpanel_data._internal.bookmark_schema import SortByColumnsConfig

        m = SortByColumnsConfig.model_validate({"sortBy": "column", "colSortAttrs": []})
        assert m.sortBy == "column"
        assert m.colSortAttrs == []

    def test_with_value_field_passes(self) -> None:
        """``valueField`` is optional and accepted when provided."""
        from mixpanel_data._internal.bookmark_schema import SortByColumnsConfig

        m = SortByColumnsConfig.model_validate(
            {"sortBy": "column", "colSortAttrs": [], "valueField": "averageValue"}
        )
        assert m.valueField == "averageValue"

    def test_missing_col_sort_attrs_rejected(self) -> None:
        """``colSortAttrs`` is required."""
        from mixpanel_data._internal.bookmark_schema import SortByColumnsConfig

        with pytest.raises(PydanticValidationError) as exc:
            SortByColumnsConfig.model_validate({"sortBy": "column"})
        errs = exc.value.errors()
        assert any(e["type"] == "missing" and "colSortAttrs" in e["loc"] for e in errs)

    def test_wrong_sort_by_rejected(self) -> None:
        """``sortBy`` must be the literal ``"column"`` for this variant."""
        from mixpanel_data._internal.bookmark_schema import SortByColumnsConfig

        with pytest.raises(PydanticValidationError):
            SortByColumnsConfig.model_validate({"sortBy": "value", "colSortAttrs": []})

    def test_legacy_sort_order_tolerated(self) -> None:
        """``sortOrder`` is ``Ignore[T]`` on this variant — tolerated, hidden."""
        from mixpanel_data._internal.bookmark_schema import SortByColumnsConfig

        m = SortByColumnsConfig.model_validate(
            {"sortBy": "column", "colSortAttrs": [], "sortOrder": "asc"}
        )
        # Field was accepted but excluded from output
        assert "sortOrder" not in m.model_dump()

    def test_legacy_view_n_limit_tolerated(self) -> None:
        """``viewNLimit`` is ``Ignore[T]`` on this variant — tolerated, hidden."""
        from mixpanel_data._internal.bookmark_schema import SortByColumnsConfig

        m = SortByColumnsConfig.model_validate(
            {"sortBy": "column", "colSortAttrs": [], "viewNLimit": 50}
        )
        assert "viewNLimit" not in m.model_dump()

    def test_unknown_field_rejected(self) -> None:
        """Truly unknown fields rejected (mirrors server ``extra='forbid'``)."""
        from mixpanel_data._internal.bookmark_schema import SortByColumnsConfig

        with pytest.raises(PydanticValidationError) as exc:
            SortByColumnsConfig.model_validate(
                {
                    "sortBy": "column",
                    "colSortAttrs": [],
                    "segmentation": "value",
                }
            )
        assert any(e["type"] == "extra_forbidden" for e in exc.value.errors())


class TestSortByValueConfig:
    """Tests mirroring sorting.py:74 ``SortByValueConfig``.

    Discriminator ``sortBy=Literal["value", "liftComparisonValue"]``;
    ``colSortAttrs`` required, ``sortOrder`` optional. Deprecated
    ``"liftComparisonValue"`` retained for input compatibility.
    """

    def test_valid_minimal_passes(self) -> None:
        """Minimal valid config: sortBy=value + empty colSortAttrs."""
        from mixpanel_data._internal.bookmark_schema import SortByValueConfig

        m = SortByValueConfig.model_validate({"sortBy": "value", "colSortAttrs": []})
        assert m.sortBy == "value"

    def test_missing_col_sort_attrs_rejected(self) -> None:
        """``colSortAttrs`` is required."""
        from mixpanel_data._internal.bookmark_schema import SortByValueConfig

        with pytest.raises(PydanticValidationError):
            SortByValueConfig.model_validate({"sortBy": "value"})

    def test_sort_order_optional(self) -> None:
        """``sortOrder`` is optional on this variant (canonical:
        ``Optional[SortOrder] = None``)."""
        from mixpanel_data._internal.bookmark_schema import SortByValueConfig

        m = SortByValueConfig.model_validate({"sortBy": "value", "colSortAttrs": []})
        assert m.sortOrder is None

    def test_sort_order_when_provided_validated(self) -> None:
        """``sortOrder`` must be ``"asc"``/``"desc"`` when provided."""
        from mixpanel_data._internal.bookmark_schema import SortByValueConfig

        with pytest.raises(PydanticValidationError):
            SortByValueConfig.model_validate(
                {"sortBy": "value", "sortOrder": "ascending", "colSortAttrs": []}
            )

    def test_deprecated_lift_comparison_value_accepted(self) -> None:
        """``"liftComparisonValue"`` is deprecated but still accepted as
        ``sortBy`` per canonical model."""
        from mixpanel_data._internal.bookmark_schema import SortByValueConfig

        m = SortByValueConfig.model_validate(
            {"sortBy": "liftComparisonValue", "colSortAttrs": []}
        )
        assert m.sortBy == "liftComparisonValue"

    def test_extra_segmentation_field_rejected(self) -> None:
        """The ``segmentation`` field that triggered the production
        incident must be rejected client-side."""
        from mixpanel_data._internal.bookmark_schema import SortByValueConfig

        with pytest.raises(PydanticValidationError) as exc:
            SortByValueConfig.model_validate(
                {
                    "sortBy": "value",
                    "sortOrder": "asc",
                    "colSortAttrs": [],
                    "segmentation": "value",
                }
            )
        assert any(
            e["type"] == "extra_forbidden" and "segmentation" in e["loc"]
            for e in exc.value.errors()
        )


class TestFlatSortConfigs:
    """Tests for ``FlatLabelSortConfig`` and ``FlatValueSortConfig``
    mirroring sorting.py:36-58.

    These appear inside ``colSortAttrs`` lists on both column and value
    sort configs. Discriminator on ``sortBy``: ``"label"`` vs
    ``"value"``/``"liftComparisonValue"``.
    """

    def test_flat_label_valid(self) -> None:
        """Label variant: requires sortOrder, valueField/viewNLimit optional."""
        from mixpanel_data._internal.bookmark_schema import FlatLabelSortConfig

        m = FlatLabelSortConfig.model_validate({"sortBy": "label", "sortOrder": "asc"})
        assert m.sortBy == "label"
        assert m.sortOrder == "asc"

    def test_flat_value_valid(self) -> None:
        """Value variant: requires sortOrder, valueField optional."""
        from mixpanel_data._internal.bookmark_schema import FlatValueSortConfig

        m = FlatValueSortConfig.model_validate(
            {
                "sortBy": "value",
                "sortOrder": "desc",
                "valueField": "averageValue",
            }
        )
        assert m.valueField == "averageValue"

    def test_flat_label_missing_sort_order_rejected(self) -> None:
        """``sortOrder`` is required on ``FlatLabelSortConfig``."""
        from mixpanel_data._internal.bookmark_schema import FlatLabelSortConfig

        with pytest.raises(PydanticValidationError):
            FlatLabelSortConfig.model_validate({"sortBy": "label"})


class TestInsightsBookmarkSortConfig:
    """Tests mirroring sorting.py:115 ``InsightsBookmarkSortConfig``.

    The wrapper at ``params['sorting']`` — keys are chart-type strings
    (kebab-case wire form, snake_case Python field). Each key holds an
    optional ``SortConfig`` (discriminated union).
    """

    def test_empty_passes(self) -> None:
        """Empty sorting block is valid (no per-chart-type overrides)."""
        from mixpanel_data._internal.bookmark_schema import (
            InsightsBookmarkSortConfig,
        )

        m = InsightsBookmarkSortConfig.model_validate({})
        assert m.bar is None

    def test_bar_with_columns_config_passes(self) -> None:
        """Canonical valid bar config: sortBy=column + colSortAttrs."""
        from mixpanel_data._internal.bookmark_schema import (
            InsightsBookmarkSortConfig,
        )

        m = InsightsBookmarkSortConfig.model_validate(
            {"bar": {"sortBy": "column", "colSortAttrs": []}}
        )
        assert m.bar is not None
        assert m.bar.sortBy == "column"

    def test_funnel_steps_kebab_alias_accepted(self) -> None:
        """``funnel-steps`` (kebab-case wire) maps to ``funnel_steps`` field."""
        from mixpanel_data._internal.bookmark_schema import (
            InsightsBookmarkSortConfig,
        )

        m = InsightsBookmarkSortConfig.model_validate(
            {"funnel-steps": {"sortBy": "column", "colSortAttrs": []}}
        )
        assert m.funnel_steps is not None

    def test_retention_curve_kebab_alias_accepted(self) -> None:
        """``retention-curve`` kebab alias works."""
        from mixpanel_data._internal.bookmark_schema import (
            InsightsBookmarkSortConfig,
        )

        m = InsightsBookmarkSortConfig.model_validate(
            {"retention-curve": {"sortBy": "column", "colSortAttrs": []}}
        )
        assert m.retention_curve is not None

    def test_unknown_chart_type_rejected(self) -> None:
        """Unknown top-level keys (e.g. typo ``"barz"``) rejected."""
        from mixpanel_data._internal.bookmark_schema import (
            InsightsBookmarkSortConfig,
        )

        with pytest.raises(PydanticValidationError):
            InsightsBookmarkSortConfig.model_validate(
                {"barz": {"sortBy": "column", "colSortAttrs": []}}
            )

    def test_my_actual_bug_caught(self) -> None:
        """Reproduces the production incident from the dashboard render
        failure: ``{bar: {sortBy: 'value', segmentation: 'value'}}`` —
        missing ``colSortAttrs`` AND extra ``segmentation`` field.
        """
        from mixpanel_data._internal.bookmark_schema import (
            InsightsBookmarkSortConfig,
        )

        bad: dict[str, Any] = {
            "bar": {
                "sortBy": "value",
                "sortOrder": "asc",
                "segmentation": "value",
            },
            "funnel-steps": {
                "sortBy": "value",
                "sortOrder": "asc",
                "segmentation": "value",
            },
        }
        with pytest.raises(PydanticValidationError) as exc:
            InsightsBookmarkSortConfig.model_validate(bad)
        errs = exc.value.errors()
        # Missing colSortAttrs on both bar and funnel-steps
        missing = [e for e in errs if e["type"] == "missing"]
        assert len(missing) >= 2
        # Extra segmentation field on both
        extras = [
            e
            for e in errs
            if e["type"] == "extra_forbidden" and "segmentation" in e["loc"]
        ]
        assert len(extras) >= 2
