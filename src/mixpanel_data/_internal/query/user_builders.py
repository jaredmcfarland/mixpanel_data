"""Filter-to-selector translation for the Engage API.

Converts ``Filter`` objects to engage API selector strings. This is the
third translation path alongside ``bookmark_builders.build_filter_entry()``
(bookmark dicts for insights/funnels/retention) and
``segfilter.build_segfilter_entry()`` (segfilter entries for flows).

The engage API uses selector strings like ``properties["plan"] == "premium"``
rather than bookmark filter dicts or segfilter entries.

Functions:
    filter_to_selector: Convert a single Filter to a selector string.
    filters_to_selector: Convert multiple Filters to an AND-combined selector.
    extract_cohort_filter: Extract cohort filter from a Filter list.
"""

from __future__ import annotations

from mixpanel_data.types import Filter


def _format_value(value: str | int | float) -> str:
    """Format a scalar value for use in a selector expression.

    Strings are wrapped in double quotes (with internal quotes escaped).
    Numbers are rendered without quotes.

    Args:
        value: The scalar value to format.

    Returns:
        Formatted string suitable for embedding in a selector expression.
    """
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return str(value)


def _prop_ref(f: Filter) -> str:
    """Build the ``properties["name"]`` reference for a Filter.

    Args:
        f: Filter whose property name to reference.

    Returns:
        String of the form ``properties["<name>"]``.
    """
    return f'properties["{f._property}"]'


def _is_cohort_filter(f: Filter) -> bool:
    """Return True if *f* is a cohort filter (in_cohort / not_in_cohort).

    Cohort filters store their value as a list of dicts, unlike regular
    filters which use str, number, list-of-str, or None.

    Args:
        f: Filter to test.

    Returns:
        True when the filter's ``_value`` is a non-empty list of dicts.
    """
    val = f._value
    return isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict)


def filter_to_selector(f: Filter) -> str:
    """Convert a single Filter to an engage API selector string.

    Translates the Filter's internal operator to the equivalent engage
    selector syntax. Each operator maps to a specific selector pattern.

    Args:
        f: A Filter object (constructed via class methods like
            ``Filter.equals()``, ``Filter.greater_than()``, etc.).

    Returns:
        Selector string for the engage API ``where`` parameter.

    Raises:
        ValueError: If the Filter has an unsupported operator.

    Example:
        ```python
        from mixpanel_data.types import Filter
        from mixpanel_data._internal.query.user_builders import filter_to_selector

        selector = filter_to_selector(Filter.equals("plan", "premium"))
        # 'properties["plan"] == "premium"'
        ```
    """
    op = f._operator
    prop = _prop_ref(f)
    value = f._value

    if op == "equals":
        assert isinstance(value, list)
        parts = [
            f"{prop} == {_format_value(v)}"
            for v in value
            if isinstance(v, (str, int, float))
        ]
        return " or ".join(parts)

    if op == "does not equal":
        assert isinstance(value, list)
        parts = [
            f"{prop} != {_format_value(v)}"
            for v in value
            if isinstance(v, (str, int, float))
        ]
        return " and ".join(parts)

    if op == "contains":
        assert isinstance(value, str)
        return f"{_format_value(value)} in {prop}"

    if op == "does not contain":
        assert isinstance(value, str)
        return f"not {_format_value(value)} in {prop}"

    if op == "is greater than":
        assert isinstance(value, (int, float))
        return f"{prop} > {_format_value(value)}"

    if op == "is less than":
        assert isinstance(value, (int, float))
        return f"{prop} < {_format_value(value)}"

    if op == "is between":
        assert isinstance(value, list) and len(value) == 2
        lo, hi = value[0], value[1]
        assert isinstance(lo, (str, int, float))
        assert isinstance(hi, (str, int, float))
        return f"{prop} >= {_format_value(lo)} and {prop} <= {_format_value(hi)}"

    if op == "is set":
        return f"defined({prop})"

    if op == "is not set":
        return f"not defined({prop})"

    if op == "true":
        return f"{prop} == true"

    if op == "false":
        return f"{prop} == false"

    raise ValueError(f"Unsupported filter operator: {op!r}")


def filters_to_selector(filters: list[Filter]) -> str:
    """Convert multiple Filters to an AND-combined selector string.

    Each Filter is translated individually via ``filter_to_selector()``,
    then combined with `` and `` operators.

    Args:
        filters: List of Filter objects to AND-combine.

    Returns:
        AND-combined selector string. Returns empty string if list is empty.

    Example:
        ```python
        from mixpanel_data.types import Filter
        from mixpanel_data._internal.query.user_builders import filters_to_selector

        selector = filters_to_selector([
            Filter.equals("plan", "premium"),
            Filter.is_set("email"),
        ])
        # 'properties["plan"] == "premium" and defined(properties["email"])'
        ```
    """
    if not filters:
        return ""
    return " and ".join(filter_to_selector(f) for f in filters)


def extract_cohort_filter(
    filters: list[Filter],
) -> tuple[list[Filter], Filter | None]:
    """Extract a cohort filter from a list of Filters.

    Separates ``Filter.in_cohort()`` entries from regular property filters.
    At most one cohort filter is expected (validated by U13).

    Args:
        filters: List of Filter objects, possibly containing a cohort filter.

    Returns:
        Tuple of (remaining_filters, cohort_filter_or_none).

    Example:
        ```python
        from mixpanel_data.types import Filter
        from mixpanel_data._internal.query.user_builders import extract_cohort_filter

        filters = [
            Filter.equals("plan", "premium"),
            Filter.in_cohort(123),
        ]
        remaining, cohort = extract_cohort_filter(filters)
        # remaining = [Filter.equals("plan", "premium")]
        # cohort = Filter.in_cohort(123)
        ```
    """
    remaining: list[Filter] = []
    cohort: Filter | None = None
    for f in filters:
        if _is_cohort_filter(f):
            if cohort is None:
                cohort = f
        else:
            remaining.append(f)
    return remaining, cohort
