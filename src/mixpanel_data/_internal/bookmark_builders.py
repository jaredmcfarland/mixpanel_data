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
