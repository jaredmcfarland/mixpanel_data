"""Reusable builder functions for bookmark JSON sections.

Extracted from ``Workspace._build_query_params()`` to enable reuse across
insights, funnels, retention, and flows query builders. Each function
produces a fragment of the Mixpanel bookmark ``params`` JSON structure.

These are internal helpers — import from ``mixpanel_data._internal.bookmark_builders``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from mixpanel_data._literal_types import QueryTimeUnit
from mixpanel_data.types import Filter, GroupBy


def build_time_section(
    *,
    from_date: str | None,
    to_date: str | None,
    last: int,
    unit: QueryTimeUnit,
) -> list[dict[str, Any]]:
    """Build the ``sections.time`` array for bookmark params.

    Produces a single-element list containing one time entry dict.
    Three cases are handled:

    - **Absolute range**: both ``from_date`` and ``to_date`` set.
    - **From-only range**: only ``from_date`` set; ``to_date`` is filled
      with today's date.
    - **Relative range**: neither date set; uses ``last`` days.

    Args:
        from_date: Start date (YYYY-MM-DD) or ``None``.
        to_date: End date (YYYY-MM-DD) or ``None``.
        last: Number of days for relative range (used when no dates given).
        unit: Time granularity (``"hour"``, ``"day"``, ``"week"``,
            ``"month"``, ``"quarter"``).

    Returns:
        Single-element list with one time entry dict. Structure varies
        by case:

        - Absolute: ``{"dateRangeType": "between", "unit": ..., "value": [from, to]}``
        - From-only: same as absolute with ``to_date`` = today
        - Relative: ``{"dateRangeType": "in the last", "unit": ..., "window": {...}}``

    Example:
        ```python
        time = build_time_section(
            from_date="2025-01-01", to_date="2025-01-31",
            last=30, unit="day",
        )
        # [{"dateRangeType": "between", "unit": "day",
        #   "value": ["2025-01-01", "2025-01-31"]}]
        ```
    """
    if from_date is not None:
        effective_to = to_date if to_date is not None else date.today().isoformat()
        time_entry: dict[str, Any] = {
            "dateRangeType": "between",
            "unit": unit,
            "value": [from_date, effective_to],
        }
    else:
        time_entry = {
            "dateRangeType": "in the last",
            "unit": unit,
            "window": {"unit": "day", "value": last},
        }
    return [time_entry]


def build_date_range(
    *,
    from_date: str | None,
    to_date: str | None,
    last: int,
) -> dict[str, Any]:
    """Build a flat date range dict for flows (non-sections format).

    Flows use a flat ``date_range`` object rather than the sections-based
    ``sections.time`` array used by insights.

    Args:
        from_date: Start date (YYYY-MM-DD) or ``None``.
        to_date: End date (YYYY-MM-DD) or ``None``.
        last: Number of days for relative range.

    Returns:
        Date range dict. Structure varies by case:

        - Absolute: ``{"type": "between", "from_date": ..., "to_date": ...}``
        - Relative: ``{"type": "in the last", "from_date": {"unit": "day", "value": N}, "to_date": "$now"}``

    Example:
        ```python
        dr = build_date_range(from_date=None, to_date=None, last=30)
        # {"type": "in the last",
        #  "from_date": {"unit": "day", "value": 30},
        #  "to_date": "$now"}
        ```
    """
    if from_date is not None and to_date is not None:
        return {
            "type": "between",
            "from_date": from_date,
            "to_date": to_date,
        }
    return {
        "type": "in the last",
        "from_date": {"unit": "day", "value": last},
        "to_date": "$now",
    }


def build_filter_section(
    where: Filter | list[Filter] | None,
) -> list[dict[str, Any]]:
    """Build the ``sections.filter`` array for bookmark params.

    Converts ``None``, a single ``Filter``, or a list of ``Filter`` objects
    into the list-of-dicts format expected by the Mixpanel bookmark API.

    Args:
        where: Filter specification. ``None`` means no filters,
            a single ``Filter`` is wrapped in a list, a list is
            processed element-by-element.

    Returns:
        List of filter entry dicts (may be empty).

    Example:
        ```python
        filters = build_filter_section(Filter.equals("country", "US"))
        # [{"resourceType": "events", "filterType": "string", ...}]
        ```
    """
    if where is None:
        return []
    filters_list = where if isinstance(where, list) else [where]
    return [build_filter_entry(f) for f in filters_list]


def build_group_section(
    group_by: str | GroupBy | list[str | GroupBy] | None,
) -> list[dict[str, Any]]:
    """Build the ``sections.group`` array for bookmark params.

    Converts group-by specifications into the list-of-dicts format
    expected by the Mixpanel bookmark API. Supports strings (simple
    property name), ``GroupBy`` objects (with optional bucketing),
    and lists mixing both.

    Args:
        group_by: Group-by specification. ``None`` means no grouping.
            Strings produce default string-typed entries. ``GroupBy``
            objects allow custom property types and numeric bucketing.

    Returns:
        List of group entry dicts (may be empty).

    Raises:
        TypeError: If any element is not ``str`` or ``GroupBy``.

    Example:
        ```python
        groups = build_group_section("country")
        # [{"value": "country", "propertyName": "country",
        #   "resourceType": "events", "propertyType": "string",
        #   "propertyDefaultType": "string"}]
        ```
    """
    if group_by is None:
        return []

    groups = group_by if isinstance(group_by, list) else [group_by]
    group_section: list[dict[str, Any]] = []

    for g in groups:
        if isinstance(g, str):
            group_section.append(
                {
                    "value": g,
                    "propertyName": g,
                    "resourceType": "events",
                    "propertyType": "string",
                    "propertyDefaultType": "string",
                }
            )
        elif isinstance(g, GroupBy):
            group_entry: dict[str, Any] = {
                "value": g.property,
                "propertyName": g.property,
                "resourceType": "events",
                "propertyType": g.property_type,
                "propertyDefaultType": g.property_type,
            }
            if g.bucket_size is not None:
                group_entry["customBucket"] = {
                    "bucketSize": g.bucket_size,
                }
                if g.bucket_min is not None:
                    group_entry["customBucket"]["min"] = g.bucket_min
                if g.bucket_max is not None:
                    group_entry["customBucket"]["max"] = g.bucket_max
            group_section.append(group_entry)
        else:
            raise TypeError(
                f"group_by elements must be str or GroupBy, "
                f"got {type(g).__name__}: {g!r}"
            )

    return group_section


def build_filter_entry(f: Filter) -> dict[str, Any]:
    """Convert a Filter object to a bookmark filter dict.

    Maps the internal Filter fields to the key names expected by the
    Mixpanel bookmark API. Includes ``filterDateUnit`` only for
    relative date filters that have a date unit set.

    Args:
        f: A ``Filter`` object constructed via its class methods.

    Returns:
        Bookmark filter dict with keys: ``resourceType``, ``filterType``,
        ``defaultType``, ``value``, ``filterValue``, ``filterOperator``,
        and optionally ``filterDateUnit``.

    Example:
        ```python
        entry = build_filter_entry(Filter.equals("country", "US"))
        # {"resourceType": "events", "filterType": "string",
        #  "defaultType": "string", "value": "country",
        #  "filterValue": ["US"], "filterOperator": "equals"}
        ```
    """
    entry: dict[str, Any] = {
        "resourceType": f._resource_type,
        "filterType": f._property_type,
        "defaultType": f._property_type,
        "value": f._property,
        "filterValue": f._value,
        "filterOperator": f._operator,
    }
    if f._date_unit is not None:
        entry["filterDateUnit"] = f._date_unit
    return entry


# ---------------------------------------------------------------------------
# Operator mapping: bookmark operator → segfilter operator
# ---------------------------------------------------------------------------
_SEGFILTER_OPERATOR_MAP: dict[str, str] = {
    "equals": "==",
    "does not equal": "!=",
    "contains": "in",
    "does not contain": "not in",
    "is greater than": ">",
    "is less than": "<",
    "is greater than or equal to": ">=",
    "is less than or equal to": "<=",
    "is between": "><",
    "is not between": "!><",
    # Date operators reuse the same symbols
    "was on": "==",
    "was not on": "!=",
    "was before": "<",
    "was since": ">=",
    "was between": "><",
}

# ---------------------------------------------------------------------------
# Resource type → segfilter property source
# ---------------------------------------------------------------------------
_SEGFILTER_SOURCE_MAP: dict[str, str] = {
    "events": "properties",
    "people": "user",
}


def _is_iso_date(value: object) -> bool:
    """Check whether *value* looks like a ``YYYY-MM-DD`` date string.

    Args:
        value: The object to test.

    Returns:
        ``True`` when *value* is a string matching the ISO-8601 date
        pattern ``YYYY-MM-DD``; ``False`` otherwise.
    """
    if not isinstance(value, str):
        return False
    parts = value.split("-")
    return len(parts) == 3 and all(p.isdigit() for p in parts) and len(parts[0]) == 4


def _iso_to_mdy(date_str: str) -> str:
    """Convert an ISO date string to ``MM/DD/YYYY`` format.

    Args:
        date_str: Date in ``YYYY-MM-DD`` format.

    Returns:
        Date formatted as ``MM/DD/YYYY``.
    """
    yyyy, mm, dd = date_str.split("-")
    return f"{mm}/{dd}/{yyyy}"


def _serialize_segfilter_value(
    value: str | int | float | list[str] | list[int | float] | None,
    prop_type: str,
    operator: str,
) -> str | list[str]:
    """Serialize a Filter value into the segfilter operand format.

    Applies type-specific conversions:

    - **is_set / is_not_set**: empty string regardless of value.
    - **Numbers**: stringified (``50`` becomes ``"50"``).
    - **Number ranges** (between): each element stringified.
    - **Booleans** (true/false): ``"true"`` or ``"false"``.
    - **Dates** (``YYYY-MM-DD``): converted to ``MM/DD/YYYY``.
    - **Date ranges**: each element converted.
    - **Strings**: kept as-is.

    Args:
        value: The raw filter value from a ``Filter`` object.
        prop_type: The property type (``"string"``, ``"number"``,
            ``"boolean"``, ``"datetime"``).
        operator: The *bookmark* operator string (before segfilter
            mapping), used to detect set/not-set and boolean operators.

    Returns:
        Serialized operand — a single string or a list of strings.
    """
    # Existence checks always use empty string
    if operator in ("is set", "is not set"):
        return ""

    # Boolean filters
    if operator == "true":
        return "true"
    if operator == "false":
        return "false"

    # List values (equals, not-equals, between, date_between)
    if isinstance(value, list):
        result: list[str] = []
        for v in value:
            if isinstance(v, (int, float)):
                result.append(str(int(v)) if isinstance(v, int) else str(v))
            elif isinstance(v, str) and _is_iso_date(v):
                result.append(_iso_to_mdy(v))
            else:
                result.append(str(v))
        return result

    # Scalar numeric
    if isinstance(value, (int, float)):
        return str(int(value)) if isinstance(value, int) else str(value)

    # Scalar datetime
    if isinstance(value, str) and prop_type == "datetime" and _is_iso_date(value):
        return _iso_to_mdy(value)

    # Scalar string (or anything else)
    if value is None:
        return ""
    return str(value)


def build_segfilter_entry(f: Filter) -> dict[str, Any]:
    """Convert a ``Filter`` object to a legacy segfilter dict.

    Flows per-step filters use a "segfilter" format that differs from
    the bookmark-style filter format used by insights, funnels, and
    retention.  This function bridges the two representations.

    Args:
        f: A ``Filter`` object constructed via its class methods or
            direct instantiation.

    Returns:
        Segfilter dict with the following structure::

            {
                "property": {"name": ..., "source": ..., "type": ...},
                "type": <property_type>,
                "selected_property_type": <property_type>,
                "filter": {"operator": ..., "operand": ...},
            }

        For boolean filters (``"true"`` / ``"false"`` operators) the
        ``"operator"`` key is omitted from the ``filter`` sub-dict.

    Example:
        ```python
        from mixpanel_data import Filter
        from mixpanel_data._internal.bookmark_builders import build_segfilter_entry

        entry = build_segfilter_entry(Filter.equals("country", "US"))
        # {
        #     "property": {"name": "country", "source": "properties", "type": "string"},
        #     "type": "string",
        #     "selected_property_type": "string",
        #     "filter": {"operator": "==", "operand": ["US"]},
        # }
        ```
    """
    prop_type: str = f._property_type
    source: str = _SEGFILTER_SOURCE_MAP.get(f._resource_type, f._resource_type)
    operator: str = f._operator

    # Validate operator is known before building segfilter
    _valid_segfilter_operators = set(_SEGFILTER_OPERATOR_MAP.keys()) | {
        "is set",
        "is not set",
        "true",
        "false",
    }
    if operator not in _valid_segfilter_operators:
        msg = (
            f"Unknown filter operator {operator!r} for segfilter conversion. "
            f"Use Filter factory methods (e.g. Filter.equals()) instead of "
            f"direct construction."
        )
        raise ValueError(msg)

    operand = _serialize_segfilter_value(f._value, prop_type, operator)

    # Build the filter sub-dict — boolean filters omit the operator key
    if operator in ("true", "false"):
        filter_dict: dict[str, Any] = {"operand": operand}
    else:
        # Existence operators differ by property type
        if operator in ("is set", "is not set") and prop_type == "string":
            segfilter_op = "set" if operator == "is set" else "not set"
        else:
            segfilter_op = _SEGFILTER_OPERATOR_MAP.get(operator, operator)
        filter_dict = {"operator": segfilter_op, "operand": operand}

    return {
        "property": {"name": f._property, "source": source, "type": prop_type},
        "type": prop_type,
        "selected_property_type": prop_type,
        "filter": filter_dict,
    }
