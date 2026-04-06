"""Tests for build_segfilter_entry() — segfilter dict conversion.

Verifies that ``build_segfilter_entry()`` correctly converts ``Filter``
objects into the legacy segfilter dict format used by Mixpanel flow
per-step filters.  Each test validates the full output structure
including ``property``, ``type``, ``selected_property_type``, and
``filter`` sub-dicts.
"""

from __future__ import annotations

from mixpanel_data._internal.bookmark_builders import build_segfilter_entry
from mixpanel_data.types import Filter


class TestStringOperators:
    """Tests for string-typed filter operators in segfilter format."""

    def test_string_equals(self) -> None:
        """String equals produces operator '==' with operand list.

        Example:
            ```python
            f = Filter.equals("country", "US")
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operator"] == "=="
            ```
        """
        f = Filter.equals("country", "US")
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "country",
            "source": "properties",
            "type": "string",
        }
        assert entry["type"] == "string"
        assert entry["selected_property_type"] == "string"
        assert entry["filter"]["operator"] == "=="
        assert entry["filter"]["operand"] == ["US"]

    def test_string_does_not_equal(self) -> None:
        """String not-equals produces operator '!='.

        Example:
            ```python
            f = Filter.not_equals("country", "US")
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operator"] == "!="
            ```
        """
        f = Filter.not_equals("country", "US")
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "country",
            "source": "properties",
            "type": "string",
        }
        assert entry["type"] == "string"
        assert entry["selected_property_type"] == "string"
        assert entry["filter"]["operator"] == "!="
        assert entry["filter"]["operand"] == ["US"]

    def test_contains(self) -> None:
        """Contains maps to segfilter operator 'in' (not 'contains').

        Example:
            ```python
            f = Filter.contains("name", "john")
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operator"] == "in"
            ```
        """
        f = Filter.contains("name", "john")
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "name",
            "source": "properties",
            "type": "string",
        }
        assert entry["type"] == "string"
        assert entry["selected_property_type"] == "string"
        assert entry["filter"]["operator"] == "in"
        assert entry["filter"]["operand"] == "john"

    def test_does_not_contain(self) -> None:
        """Does-not-contain maps to segfilter operator 'not in'.

        Example:
            ```python
            f = Filter.not_contains("name", "john")
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operator"] == "not in"
            ```
        """
        f = Filter.not_contains("name", "john")
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "name",
            "source": "properties",
            "type": "string",
        }
        assert entry["type"] == "string"
        assert entry["selected_property_type"] == "string"
        assert entry["filter"]["operator"] == "not in"
        assert entry["filter"]["operand"] == "john"


class TestNumericOperators:
    """Tests for number-typed filter operators in segfilter format."""

    def test_greater_than(self) -> None:
        """Greater-than stringifies the numeric operand.

        Example:
            ```python
            f = Filter.greater_than("amount", 50)
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operand"] == "50"
            ```
        """
        f = Filter.greater_than("amount", 50)
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "amount",
            "source": "properties",
            "type": "number",
        }
        assert entry["type"] == "number"
        assert entry["selected_property_type"] == "number"
        assert entry["filter"]["operator"] == ">"
        assert entry["filter"]["operand"] == "50"

    def test_less_than(self) -> None:
        """Less-than stringifies the numeric operand.

        Example:
            ```python
            f = Filter.less_than("amount", 10)
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operand"] == "10"
            ```
        """
        f = Filter.less_than("amount", 10)
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "amount",
            "source": "properties",
            "type": "number",
        }
        assert entry["type"] == "number"
        assert entry["selected_property_type"] == "number"
        assert entry["filter"]["operator"] == "<"
        assert entry["filter"]["operand"] == "10"

    def test_between(self) -> None:
        """Between stringifies both endpoints into a two-element list.

        Example:
            ```python
            f = Filter.between("amount", 5, 10)
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operand"] == ["5", "10"]
            ```
        """
        f = Filter.between("amount", 5, 10)
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "amount",
            "source": "properties",
            "type": "number",
        }
        assert entry["type"] == "number"
        assert entry["selected_property_type"] == "number"
        assert entry["filter"]["operator"] == "><"
        assert entry["filter"]["operand"] == ["5", "10"]

    def test_greater_than_or_equal(self) -> None:
        """Greater-than-or-equal maps to '>=' with stringified operand.

        Uses direct Filter construction since no factory method exists
        for this operator.

        Example:
            ```python
            f = Filter(
                _property="amount", _operator="is greater than or equal to",
                _value=50, _property_type="number",
            )
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operator"] == ">="
            ```
        """
        f = Filter(
            _property="amount",
            _operator="is greater than or equal to",
            _value=50,
            _property_type="number",
        )
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "amount",
            "source": "properties",
            "type": "number",
        }
        assert entry["type"] == "number"
        assert entry["selected_property_type"] == "number"
        assert entry["filter"]["operator"] == ">="
        assert entry["filter"]["operand"] == "50"

    def test_less_than_or_equal(self) -> None:
        """Less-than-or-equal maps to '<=' with stringified operand.

        Uses direct Filter construction since no factory method exists
        for this operator.

        Example:
            ```python
            f = Filter(
                _property="amount", _operator="is less than or equal to",
                _value=10, _property_type="number",
            )
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operator"] == "<="
            ```
        """
        f = Filter(
            _property="amount",
            _operator="is less than or equal to",
            _value=10,
            _property_type="number",
        )
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "amount",
            "source": "properties",
            "type": "number",
        }
        assert entry["type"] == "number"
        assert entry["selected_property_type"] == "number"
        assert entry["filter"]["operator"] == "<="
        assert entry["filter"]["operand"] == "10"


class TestBooleanOperators:
    """Tests for boolean-typed filter operators in segfilter format."""

    def test_true(self) -> None:
        """Boolean true has no operator key, just operand 'true'.

        Example:
            ```python
            f = Filter.is_true("verified")
            entry = build_segfilter_entry(f)
            assert "operator" not in entry["filter"]
            assert entry["filter"]["operand"] == "true"
            ```
        """
        f = Filter.is_true("verified")
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "verified",
            "source": "properties",
            "type": "boolean",
        }
        assert entry["type"] == "boolean"
        assert entry["selected_property_type"] == "boolean"
        assert "operator" not in entry["filter"]
        assert entry["filter"]["operand"] == "true"

    def test_false(self) -> None:
        """Boolean false has no operator key, just operand 'false'.

        Example:
            ```python
            f = Filter.is_false("verified")
            entry = build_segfilter_entry(f)
            assert "operator" not in entry["filter"]
            assert entry["filter"]["operand"] == "false"
            ```
        """
        f = Filter.is_false("verified")
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "verified",
            "source": "properties",
            "type": "boolean",
        }
        assert entry["type"] == "boolean"
        assert entry["selected_property_type"] == "boolean"
        assert "operator" not in entry["filter"]
        assert entry["filter"]["operand"] == "false"


class TestExistenceOperators:
    """Tests for is_set / is_not_set operators in segfilter format."""

    def test_is_set_string(self) -> None:
        """String is_set maps to operator 'set' with empty operand.

        Example:
            ```python
            f = Filter.is_set("email")
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operator"] == "set"
            ```
        """
        f = Filter.is_set("email")
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "email",
            "source": "properties",
            "type": "string",
        }
        assert entry["type"] == "string"
        assert entry["selected_property_type"] == "string"
        assert entry["filter"]["operator"] == "set"
        assert entry["filter"]["operand"] == ""

    def test_is_not_set_string(self) -> None:
        """String is_not_set maps to operator 'not set' with empty operand.

        Example:
            ```python
            f = Filter.is_not_set("email")
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operator"] == "not set"
            ```
        """
        f = Filter.is_not_set("email")
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "email",
            "source": "properties",
            "type": "string",
        }
        assert entry["type"] == "string"
        assert entry["selected_property_type"] == "string"
        assert entry["filter"]["operator"] == "not set"
        assert entry["filter"]["operand"] == ""

    def test_is_set_number(self) -> None:
        """Number is_set maps to operator 'is set' (not 'set').

        Uses direct Filter construction to set property_type='number'
        since the is_set factory always produces string type.

        Example:
            ```python
            f = Filter(
                _property="amount", _operator="is set",
                _value=None, _property_type="number",
            )
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operator"] == "is set"
            ```
        """
        f = Filter(
            _property="amount",
            _operator="is set",
            _value=None,
            _property_type="number",
        )
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "amount",
            "source": "properties",
            "type": "number",
        }
        assert entry["type"] == "number"
        assert entry["selected_property_type"] == "number"
        assert entry["filter"]["operator"] == "is set"
        assert entry["filter"]["operand"] == ""

    def test_is_not_set_number(self) -> None:
        """Number is_not_set maps to operator 'is not set' (not 'not set').

        Uses direct Filter construction to set property_type='number'
        since the is_not_set factory always produces string type.

        Example:
            ```python
            f = Filter(
                _property="amount", _operator="is not set",
                _value=None, _property_type="number",
            )
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operator"] == "is not set"
            ```
        """
        f = Filter(
            _property="amount",
            _operator="is not set",
            _value=None,
            _property_type="number",
        )
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "amount",
            "source": "properties",
            "type": "number",
        }
        assert entry["type"] == "number"
        assert entry["selected_property_type"] == "number"
        assert entry["filter"]["operator"] == "is not set"
        assert entry["filter"]["operand"] == ""


class TestResourceTypeMapping:
    """Tests for resource_type to property source mapping."""

    def test_events_maps_to_properties(self) -> None:
        """Resource type 'events' maps to source 'properties'.

        Example:
            ```python
            f = Filter.equals("country", "US", resource_type="events")
            entry = build_segfilter_entry(f)
            assert entry["property"]["source"] == "properties"
            ```
        """
        f = Filter.equals("country", "US", resource_type="events")
        entry = build_segfilter_entry(f)

        assert entry["property"]["source"] == "properties"

    def test_people_maps_to_user(self) -> None:
        """Resource type 'people' maps to source 'user'.

        Example:
            ```python
            f = Filter.equals("country", "US", resource_type="people")
            entry = build_segfilter_entry(f)
            assert entry["property"]["source"] == "user"
            ```
        """
        f = Filter.equals("country", "US", resource_type="people")
        entry = build_segfilter_entry(f)

        assert entry["property"]["source"] == "user"


class TestDatetimeValues:
    """Tests for datetime value serialization in segfilter format."""

    def test_date_value_converted_to_mm_dd_yyyy(self) -> None:
        """ISO date (YYYY-MM-DD) is converted to MM/DD/YYYY for segfilter.

        Example:
            ```python
            f = Filter.on("created", "2025-01-15")
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operand"] == "01/15/2025"
            ```
        """
        f = Filter.on("created", "2025-01-15")
        entry = build_segfilter_entry(f)

        assert entry["property"] == {
            "name": "created",
            "source": "properties",
            "type": "datetime",
        }
        assert entry["type"] == "datetime"
        assert entry["selected_property_type"] == "datetime"
        assert entry["filter"]["operand"] == "01/15/2025"

    def test_date_range_both_converted(self) -> None:
        """Date range (between) converts both endpoints to MM/DD/YYYY.

        Example:
            ```python
            f = Filter.date_between("created", "2025-01-15", "2025-06-30")
            entry = build_segfilter_entry(f)
            assert entry["filter"]["operand"] == ["01/15/2025", "06/30/2025"]
            ```
        """
        f = Filter.date_between("created", "2025-01-15", "2025-06-30")
        entry = build_segfilter_entry(f)

        assert entry["filter"]["operand"] == ["01/15/2025", "06/30/2025"]
