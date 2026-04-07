"""Tests for bookmark builder functions.

Verifies that the extracted builder functions in bookmark_builders.py
produce the correct bookmark JSON structures for time sections,
date ranges, filter sections, group sections, and filter entries.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

import pytest

from mixpanel_data._internal.bookmark_builders import (
    build_date_range,
    build_filter_entry,
    build_filter_section,
    build_group_section,
    build_time_section,
    patch_custom_property_filters_for_transform,
)
from mixpanel_data.types import (
    CohortBreakdown,
    CustomPropertyRef,
    Filter,
    GroupBy,
    InlineCustomProperty,
    PropertyInput,
)


class TestBuildTimeSection:
    """Tests for build_time_section() — sections.time array building."""

    def test_absolute_range_from_and_to(self) -> None:
        """Both from_date and to_date produce a 'between' entry with value list."""
        result = build_time_section(
            from_date="2025-01-01",
            to_date="2025-01-31",
            last=30,
            unit="day",
        )
        assert len(result) == 1
        entry = result[0]
        assert entry["dateRangeType"] == "between"
        assert entry["unit"] == "day"
        assert entry["value"] == ["2025-01-01", "2025-01-31"]
        assert "window" not in entry

    def test_from_only_fills_today(self) -> None:
        """Only from_date fills to_date with today's date."""
        with patch("mixpanel_data._internal.bookmark_builders.date") as mock_date:
            mock_date.today.return_value = date(2025, 6, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            result = build_time_section(
                from_date="2025-01-01",
                to_date=None,
                last=30,
                unit="week",
            )
        assert len(result) == 1
        entry = result[0]
        assert entry["dateRangeType"] == "between"
        assert entry["unit"] == "week"
        assert entry["value"] == ["2025-01-01", "2025-06-15"]

    def test_relative_range_last_n(self) -> None:
        """Neither from_date nor to_date produces 'in the last' entry."""
        result = build_time_section(
            from_date=None,
            to_date=None,
            last=30,
            unit="day",
        )
        assert len(result) == 1
        entry = result[0]
        assert entry["dateRangeType"] == "in the last"
        assert entry["unit"] == "day"
        assert entry["window"] == {"unit": "day", "value": 30}
        assert "value" not in entry

    def test_relative_range_custom_last(self) -> None:
        """Relative range with custom last value and unit."""
        result = build_time_section(
            from_date=None,
            to_date=None,
            last=7,
            unit="hour",
        )
        entry = result[0]
        assert entry["dateRangeType"] == "in the last"
        assert entry["unit"] == "hour"
        assert entry["window"]["value"] == 7

    def test_returns_single_element_list(self) -> None:
        """Result is always a list with exactly one element."""
        for kwargs in [
            {
                "from_date": "2025-01-01",
                "to_date": "2025-01-31",
                "last": 30,
                "unit": "day",
            },
            {"from_date": "2025-01-01", "to_date": None, "last": 30, "unit": "day"},
            {"from_date": None, "to_date": None, "last": 30, "unit": "day"},
        ]:
            result = build_time_section(**kwargs)  # type: ignore[arg-type]
            assert isinstance(result, list)
            assert len(result) == 1


class TestBuildDateRange:
    """Tests for build_date_range() — flat date range for flows."""

    def test_relative_last_n(self) -> None:
        """Neither date produces 'in the last' type with $now."""
        result = build_date_range(
            from_date=None,
            to_date=None,
            last=30,
        )
        assert result["type"] == "in the last"
        assert result["from_date"] == {"unit": "day", "value": 30}
        assert result["to_date"] == "$now"

    def test_absolute_range(self) -> None:
        """Both dates produce 'between' type with raw date strings."""
        result = build_date_range(
            from_date="2025-01-01",
            to_date="2025-03-31",
            last=30,
        )
        assert result["type"] == "between"
        assert result["from_date"] == "2025-01-01"
        assert result["to_date"] == "2025-03-31"

    def test_relative_custom_last(self) -> None:
        """Custom last value in relative range."""
        result = build_date_range(
            from_date=None,
            to_date=None,
            last=7,
        )
        assert result["from_date"]["value"] == 7
        assert result["from_date"]["unit"] == "day"


class TestBuildFilterSection:
    """Tests for build_filter_section() — sections.filter array building."""

    def test_none_returns_empty(self) -> None:
        """None where clause returns empty list."""
        result = build_filter_section(None)
        assert result == []

    def test_single_filter(self) -> None:
        """Single Filter produces one-element list."""
        f = Filter.equals("country", "US")
        result = build_filter_section(f)
        assert len(result) == 1
        assert result[0]["value"] == "country"
        assert result[0]["filterOperator"] == "equals"

    def test_multiple_filters(self) -> None:
        """List of Filters produces matching-length list."""
        filters = [
            Filter.equals("country", "US"),
            Filter.greater_than("age", 18),
        ]
        result = build_filter_section(filters)
        assert len(result) == 2
        assert result[0]["value"] == "country"
        assert result[0]["filterOperator"] == "equals"
        assert result[1]["value"] == "age"
        assert result[1]["filterOperator"] == "is greater than"

    def test_single_filter_entry_structure(self) -> None:
        """Filter entry has all required keys."""
        f = Filter.equals("country", "US")
        result = build_filter_section(f)
        entry = result[0]
        assert "resourceType" in entry
        assert "filterType" in entry
        assert "defaultType" in entry
        assert "value" in entry
        assert "filterValue" in entry
        assert "filterOperator" in entry


class TestBuildGroupSection:
    """Tests for build_group_section() — sections.group array building."""

    def test_none_returns_empty(self) -> None:
        """None group_by returns empty list."""
        result = build_group_section(None)
        assert result == []

    def test_string_group_by(self) -> None:
        """String group_by produces standard group entry."""
        result = build_group_section("country")
        assert len(result) == 1
        entry = result[0]
        assert entry["value"] == "country"
        assert entry["propertyName"] == "country"
        assert entry["resourceType"] == "events"
        assert entry["propertyType"] == "string"
        assert entry["propertyDefaultType"] == "string"

    def test_groupby_object(self) -> None:
        """GroupBy object produces entry with correct property type."""
        g = GroupBy("revenue", property_type="number")
        result = build_group_section(g)
        assert len(result) == 1
        entry = result[0]
        assert entry["value"] == "revenue"
        assert entry["propertyName"] == "revenue"
        assert entry["propertyType"] == "number"
        assert entry["propertyDefaultType"] == "number"

    def test_groupby_with_buckets(self) -> None:
        """GroupBy with bucket_size produces customBucket entry."""
        g = GroupBy(
            "amount",
            property_type="number",
            bucket_size=10,
            bucket_min=0,
            bucket_max=100,
        )
        result = build_group_section(g)
        entry = result[0]
        assert "customBucket" in entry
        assert entry["customBucket"]["bucketSize"] == 10
        assert entry["customBucket"]["min"] == 0
        assert entry["customBucket"]["max"] == 100

    def test_groupby_bucket_size_only(self) -> None:
        """GroupBy with bucket_size but no min/max omits min/max keys."""
        g = GroupBy("amount", property_type="number", bucket_size=10)
        result = build_group_section(g)
        entry = result[0]
        assert "customBucket" in entry
        assert entry["customBucket"]["bucketSize"] == 10
        assert "min" not in entry["customBucket"]
        assert "max" not in entry["customBucket"]

    def test_multiple_groups_mixed(self) -> None:
        """List of mixed strings and GroupBy produces correct entries."""
        groups: list[str | GroupBy | CohortBreakdown] = [
            "country",
            GroupBy("revenue", property_type="number"),
        ]
        result = build_group_section(groups)
        assert len(result) == 2
        assert result[0]["value"] == "country"
        assert result[0]["propertyType"] == "string"
        assert result[1]["value"] == "revenue"
        assert result[1]["propertyType"] == "number"

    def test_invalid_type_raises_typeerror(self) -> None:
        """Invalid group_by element type raises TypeError."""
        with pytest.raises(
            TypeError,
            match="group_by elements must be str, GroupBy, or CohortBreakdown",
        ):
            build_group_section(123)  # type: ignore[arg-type]

    def test_invalid_element_in_list_raises_typeerror(self) -> None:
        """Invalid element inside list raises TypeError."""
        with pytest.raises(
            TypeError,
            match="group_by elements must be str, GroupBy, or CohortBreakdown",
        ):
            build_group_section(["country", 42])  # type: ignore[list-item]


class TestBuildFilterEntry:
    """Tests for build_filter_entry() — individual filter dict conversion."""

    def test_string_filter(self) -> None:
        """String equals filter produces correct entry."""
        f = Filter.equals("country", "US")
        entry = build_filter_entry(f)
        assert entry["resourceType"] == "events"
        assert entry["filterType"] == "string"
        assert entry["defaultType"] == "string"
        assert entry["value"] == "country"
        assert entry["filterValue"] == ["US"]
        assert entry["filterOperator"] == "equals"
        assert "filterDateUnit" not in entry

    def test_number_filter(self) -> None:
        """Numeric greater-than filter produces correct entry."""
        f = Filter.greater_than("age", 18)
        entry = build_filter_entry(f)
        assert entry["filterType"] == "number"
        assert entry["defaultType"] == "number"
        assert entry["value"] == "age"
        assert entry["filterValue"] == 18
        assert entry["filterOperator"] == "is greater than"
        assert "filterDateUnit" not in entry

    def test_boolean_filter(self) -> None:
        """Boolean true filter produces correct entry."""
        f = Filter.is_true("verified")
        entry = build_filter_entry(f)
        assert entry["filterType"] == "boolean"
        assert entry["defaultType"] == "boolean"
        assert entry["value"] == "verified"
        assert entry["filterValue"] is None
        assert entry["filterOperator"] == "true"
        assert "filterDateUnit" not in entry

    def test_datetime_filter_with_date_unit(self) -> None:
        """Relative date filter includes filterDateUnit."""
        f = Filter.in_the_last("$time", 7, "day")
        entry = build_filter_entry(f)
        assert entry["filterType"] == "datetime"
        assert entry["defaultType"] == "datetime"
        assert entry["value"] == "$time"
        assert entry["filterValue"] == 7
        assert entry["filterOperator"] == "was in the"
        assert entry["filterDateUnit"] == "day"

    def test_datetime_filter_without_date_unit(self) -> None:
        """Absolute date filter does not include filterDateUnit."""
        f = Filter.on("created", "2025-01-15")
        entry = build_filter_entry(f)
        assert entry["filterType"] == "datetime"
        assert entry["filterOperator"] == "was on"
        assert "filterDateUnit" not in entry

    def test_people_resource_type(self) -> None:
        """Filter with resource_type='people' sets resourceType correctly."""
        f = Filter.equals("plan", "premium", resource_type="people")
        entry = build_filter_entry(f)
        assert entry["resourceType"] == "people"

    def test_custom_property_ref_omits_value(self) -> None:
        """CustomPropertyRef filter does not include 'value' by default."""
        ref = CustomPropertyRef(90553)
        f = Filter.is_set(ref)
        entry = build_filter_entry(f)
        assert entry["customPropertyId"] == 90553
        assert "value" not in entry
        assert entry["dataset"] == "$mixpanel"

    def test_inline_custom_property_omits_value(self) -> None:
        """InlineCustomProperty filter does not include 'value' by default."""
        icp = InlineCustomProperty(
            formula="A",
            inputs={"A": PropertyInput(name="price", type="number")},
            property_type="number",
        )
        f = Filter.greater_than(icp, 1000)
        entry = build_filter_entry(f)
        assert "customProperty" in entry
        assert "value" not in entry
        assert entry["dataset"] == "$mixpanel"


class TestPatchCustomPropertyFiltersForTransform:
    """Tests for the server-compat sentinel injection.

    The server's ``transform_insights_filters_to_funnels()`` crashes
    with ``KeyError`` on custom property filters that lack ``"value"``.
    ``patch_custom_property_filters_for_transform()`` adds
    ``"value": None`` so the transform survives.
    """

    def test_adds_value_to_custom_property_ref(self) -> None:
        """Adds 'value': None for customPropertyId entries."""
        entries = [{"customPropertyId": 90553, "filterOperator": "is set"}]
        result = patch_custom_property_filters_for_transform(entries)
        assert result[0]["value"] is None

    def test_adds_value_to_inline_custom_property(self) -> None:
        """Adds 'value': None for customProperty entries."""
        entries = [{"customProperty": {"formula": "A"}, "filterOperator": ">"}]
        result = patch_custom_property_filters_for_transform(entries)
        assert result[0]["value"] is None

    def test_does_not_overwrite_existing_value(self) -> None:
        """Does not touch entries that already have 'value'."""
        entries = [{"value": "country", "filterOperator": "equals"}]
        patch_custom_property_filters_for_transform(entries)
        assert entries[0]["value"] == "country"

    def test_leaves_regular_filters_alone(self) -> None:
        """Regular property filters (with 'value') are untouched."""
        entries: list[dict[str, Any]] = [
            {"value": "country", "filterOperator": "equals"},
            {"customPropertyId": 42, "filterOperator": "is set"},
        ]
        patch_custom_property_filters_for_transform(entries)
        assert entries[0]["value"] == "country"
        assert entries[1]["value"] is None

    def test_empty_list(self) -> None:
        """Empty list returns empty list."""
        assert patch_custom_property_filters_for_transform([]) == []
