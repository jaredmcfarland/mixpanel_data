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
from mixpanel_data.types import (
    CohortBreakdown,
    CustomPropertyRef,
    Filter,
    GroupBy,
    InlineCustomProperty,
    PropertyInput,
    _sanitize_raw_cohort,
)


def _build_composed_properties(
    inputs: dict[str, PropertyInput],
) -> dict[str, dict[str, str]]:
    """Convert a PropertyInput mapping to bookmark composedProperties format.

    Transforms the user-facing ``inputs`` dict (letter → PropertyInput)
    into the JSON structure expected by Mixpanel's ``customProperty``
    bookmark schema.

    Args:
        inputs: Mapping from single uppercase letters (A-Z) to
            ``PropertyInput`` objects.

    Returns:
        Dict mapping each letter to a dict with ``value``, ``type``,
        and ``resourceType`` keys.

    Example:
        ```python
        from mixpanel_data._internal.bookmark_builders import (
            _build_composed_properties,
        )
        from mixpanel_data.types import PropertyInput

        result = _build_composed_properties({
            "A": PropertyInput("price", type="number"),
        })
        # {"A": {"value": "price", "type": "number", "resourceType": "event"}}
        ```
    """
    return {
        key: {
            "value": prop.name,
            "type": prop.type,
            "resourceType": prop.resource_type,
        }
        for key, prop in inputs.items()
    }


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
    group_by: str
    | GroupBy
    | CohortBreakdown
    | list[str | GroupBy | CohortBreakdown]
    | None,
) -> list[dict[str, Any]]:
    """Build the ``sections.group`` array for bookmark params.

    Converts group-by specifications into the list-of-dicts format
    expected by the Mixpanel bookmark API. Supports strings (simple
    property name), ``GroupBy`` objects (with optional bucketing),
    ``CohortBreakdown`` objects (cohort-based segmentation), and
    lists mixing all three.

    Args:
        group_by: Group-by specification. ``None`` means no grouping.
            Strings produce default string-typed entries. ``GroupBy``
            objects allow custom property types and numeric bucketing.
            ``CohortBreakdown`` objects produce cohort group entries.

    Returns:
        List of group entry dicts (may be empty).

    Raises:
        TypeError: If any element is not ``str``, ``GroupBy``, or
            ``CohortBreakdown``.

    Example:
        ```python
        groups = build_group_section(CohortBreakdown(123, "Power Users"))
        # [{"value": ["Power Users", "Not In Power Users"],
        #   "resourceType": "events", ...}]
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
            prop = g.property
            if isinstance(prop, CustomPropertyRef):
                group_entry: dict[str, Any] = {
                    "customPropertyId": prop.id,
                    "value": None,
                    "resourceType": "events",
                    "profileType": None,
                    "search": "",
                    "dataGroupId": None,
                    "dataset": "$mixpanel",
                    "propertyType": g.property_type,
                    "typeCast": None,
                    "unit": None,
                    "isHidden": False,
                }
            elif isinstance(prop, InlineCustomProperty):
                effective_type = (
                    prop.property_type
                    if prop.property_type is not None
                    else g.property_type
                )
                composed = _build_composed_properties(prop.inputs)
                group_entry = {
                    "customProperty": {
                        "displayFormula": prop.formula,
                        "composedProperties": composed,
                        "name": "",
                        "description": "",
                        "propertyType": effective_type,
                        "resourceType": prop.resource_type,
                    },
                    "value": None,
                    "resourceType": prop.resource_type,
                    "profileType": None,
                    "search": "",
                    "dataGroupId": None,
                    "dataset": "$mixpanel",
                    "propertyType": effective_type,
                    "typeCast": None,
                    "unit": None,
                    "isHidden": False,
                }
            else:
                group_entry = {
                    "value": prop,
                    "propertyName": prop,
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
        elif isinstance(g, CohortBreakdown):
            group_section.append(_build_cohort_group_entry(g))
        else:
            raise TypeError(
                f"group_by elements must be str, GroupBy, or CohortBreakdown, "
                f"got {type(g).__name__}: {g!r}"
            )

    return group_section


def _build_cohort_group_entry(cb: CohortBreakdown) -> dict[str, Any]:
    """Build a single cohort group entry for sections.group[].

    Produces the cohort-specific group dict with ``cohorts`` array
    containing one or two entries (with/without negated) depending
    on ``include_negated``.

    Args:
        cb: CohortBreakdown specification.

    Returns:
        Group entry dict with ``cohorts`` array.

    Example:
        ```python
        entry = _build_cohort_group_entry(CohortBreakdown(123, "PU"))
        # {"value": ["PU", "Not In PU"], "cohorts": [...], ...}
        ```
    """
    name = cb.name or ""

    # Build cohort entries — saved vs inline use different API schemas:
    # Schema 1 (saved): allows groups, count, description, etc.
    # Schema 2 (inline): allows raw_cohort, dataset, but NOT groups
    base_cohort: dict[str, Any] = {
        "name": name,
        "negated": False,
        "data_group_id": None,
    }
    if isinstance(cb.cohort, int):
        base_cohort["id"] = cb.cohort
        base_cohort["groups"] = []
    else:
        base_cohort["raw_cohort"] = _sanitize_raw_cohort(cb.cohort.to_dict())

    cohorts: list[dict[str, Any]] = [base_cohort]
    value_labels: list[str] = [name]

    if cb.include_negated:
        cohorts.append({**base_cohort, "negated": True})
        value_labels.append(f"Not In {name}")

    return {
        "value": value_labels,
        "resourceType": "events",
        "profileType": None,
        "search": "",
        "dataGroupId": None,
        "propertyType": None,
        "typeCast": None,
        "cohorts": cohorts,
        "isHidden": False,
    }


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
    prop = f._property
    entry: dict[str, Any] = {
        "resourceType": f._resource_type,
        "filterType": f._property_type,
        "defaultType": f._property_type,
        "filterValue": f._value,
        "filterOperator": f._operator,
    }
    if isinstance(prop, CustomPropertyRef):
        entry["customPropertyId"] = prop.id
        entry["dataset"] = "$mixpanel"
    elif isinstance(prop, InlineCustomProperty):
        effective_type = (
            prop.property_type if prop.property_type is not None else f._property_type
        )
        entry["customProperty"] = {
            "displayFormula": prop.formula,
            "composedProperties": _build_composed_properties(prop.inputs),
            "name": "",
            "description": "",
            "propertyType": effective_type,
            "resourceType": prop.resource_type,
        }
        entry["filterType"] = effective_type
        entry["defaultType"] = effective_type
        entry["dataset"] = "$mixpanel"
    else:
        entry["value"] = prop
    if f._date_unit is not None:
        entry["filterDateUnit"] = f._date_unit
    return entry


def build_flow_cohort_filter(
    where: Filter | list[Filter],
) -> dict[str, Any] | None:
    """Build the ``filter_by_cohort`` dict for flow bookmark params.

    Flows use a legacy ``filter_by_cohort`` top-level key rather than
    the ``sections.filter`` array used by insights/funnels/retention.
    Only cohort filters (``Filter.in_cohort`` / ``Filter.not_in_cohort``)
    are accepted; non-cohort filters raise ``ValueError``.

    Args:
        where: A single cohort ``Filter`` or list of cohort ``Filter``
            objects. Only the first cohort filter is used (flows
            support a single cohort filter).

    Returns:
        Dict with cohort filter structure for the ``filter_by_cohort``
        key, or ``None`` if ``where`` is empty.

    Raises:
        ValueError: If any filter is not a cohort filter
            (``_property != "$cohorts"``).

    Example:
        ```python
        fbc = build_flow_cohort_filter(Filter.in_cohort(123, "PU"))
        # {"id": 123, "name": "PU", "negated": False}
        ```
    """
    filters = where if isinstance(where, list) else [where]
    if not filters:
        return None

    for f in filters:
        if f._property != "$cohorts":
            raise ValueError(
                "query_flow where= only accepts cohort filters "
                "(Filter.in_cohort/not_in_cohort)"
            )

    if len(filters) > 1:
        raise ValueError(
            f"query_flow supports a single cohort filter, but {len(filters)} "
            "were provided. Pass only one Filter.in_cohort/not_in_cohort."
        )

    f = filters[0]
    # Extract from the _value structure: [{"cohort": {...}}]
    cohort_value = f._value
    if not isinstance(cohort_value, list) or len(cohort_value) == 0:
        raise ValueError(
            "Internal error: cohort filter _value must be a non-empty list; "
            f"got {type(cohort_value).__name__}. This indicates a bug in "
            "Filter._build_cohort_filter."
        )
    first_item = cohort_value[0]
    if not isinstance(first_item, dict):
        raise ValueError(
            "Internal error: cohort filter _value[0] is not a dict; "
            f"got {type(first_item).__name__}. This indicates a bug in "
            "Filter._build_cohort_filter."
        )
    cohort_data = first_item.get("cohort")
    if not isinstance(cohort_data, dict):
        raise ValueError(
            "Internal error: cohort filter _value[0] is missing 'cohort' key; "
            f"got keys {list(first_item.keys())}. This indicates a bug in "
            "Filter._build_cohort_filter."
        )
    result: dict[str, Any] = {
        "name": cohort_data.get("name", ""),
        "negated": f._operator == "does not contain",
    }
    if "id" in cohort_data:
        result["id"] = cohort_data["id"]
    if "raw_cohort" in cohort_data:
        result["raw_cohort"] = cohort_data["raw_cohort"]
    return result
