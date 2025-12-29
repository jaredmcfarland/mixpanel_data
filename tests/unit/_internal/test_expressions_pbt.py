"""Property-based tests for expression normalization using Hypothesis."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from mixpanel_data._internal.expressions import normalize_on_expression

# Strategy for bare property names (no accessor patterns)
bare_property_names = st.text(min_size=1).filter(
    lambda s: 'properties["' not in s and 'user["' not in s and 'event["' not in s
)

# Strategy for valid expressions (contain at least one accessor)
valid_expressions = st.sampled_from(
    [
        'properties["Source"]',
        'user["email"]',
        'event["name"]',
        'properties["x"] == "y"',
        'defined(properties["z"])',
    ]
)


class TestNormalizeOnExpressionProperties:
    """Property-based tests for normalize_on_expression."""

    @given(name=bare_property_names)
    def test_bare_names_get_wrapped(self, name: str) -> None:
        """Any bare property name should be wrapped in properties[] accessor.

        Invariant: If input contains no accessor patterns, output wraps it.

        Args:
            name: A string that does not contain any filter expression accessors.
        """
        result = normalize_on_expression(name)
        assert result == f'properties["{name}"]'

    @given(expr=valid_expressions)
    def test_expressions_pass_through(self, expr: str) -> None:
        """Expressions with accessor patterns should pass through unchanged.

        Invariant: If input contains accessor pattern, output equals input.

        Args:
            expr: A valid filter expression containing at least one accessor.
        """
        assert normalize_on_expression(expr) == expr

    @given(name=st.text())
    def test_idempotent(self, name: str) -> None:
        """Normalizing twice should equal normalizing once.

        Invariant: normalize(normalize(x)) == normalize(x)

        Args:
            name: Any string input (bare name or expression).
        """
        once = normalize_on_expression(name)
        twice = normalize_on_expression(once)
        assert once == twice

    @given(name=st.text())
    def test_output_always_has_accessor(self, name: str) -> None:
        """Output should always contain at least one accessor pattern.

        Invariant: Every normalized expression contains a valid accessor.

        Args:
            name: Any string input (bare name or expression).
        """
        result = normalize_on_expression(name)
        accessors = ('properties["', 'user["', 'event["')
        assert any(accessor in result for accessor in accessors)
