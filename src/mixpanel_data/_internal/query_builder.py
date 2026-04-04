"""Pure-function builder for insights bookmark params.

Transforms typed query arguments (Metric, Filter, Breakdown, Formula)
into the nested JSON structure expected by Mixpanel's bookmark API.

This module has no API dependencies and is fully unit-testable.

Example:
    ```python
    from mixpanel_data.types import Metric, Filter
    from mixpanel_data._internal.query_builder import build_insights_params

    params = build_insights_params(
        metrics=[Metric(event="Login", math="unique")],
        formulas=[],
        where=[Filter(property="$browser", operator="equals", value=["Chrome"])],
        group_by=[],
        time_unit="day",
        last=30,
        from_date=None,
        to_date=None,
        chart_type="line",
    )
    ```
"""

from __future__ import annotations

from typing import Any

from mixpanel_data.types import (
    Breakdown,
    Filter,
    Formula,
    Metric,
)


def build_insights_params(
    *,
    metrics: list[Metric],
    formulas: list[Formula],
    where: list[Filter],
    group_by: list[Breakdown],
    time_unit: str,
    last: int | None,
    from_date: str | None,
    to_date: str | None,
    chart_type: str,
) -> dict[str, Any]:
    """Build complete insights bookmark params from typed arguments.

    Produces the nested JSON structure that the Mixpanel bookmark API
    expects. The output is suitable for passing to
    ``CreateBookmarkParams(params=...)``.

    Args:
        metrics: List of metrics (show clauses) to compute.
        formulas: List of formulas referencing metrics by letter.
        where: Global filters applied to all metrics.
        group_by: Breakdown dimensions.
        time_unit: Time granularity (hour, day, week, month, quarter).
        last: Relative date range — last N time_units.
        from_date: Absolute start date (YYYY-MM-DD).
        to_date: Absolute end date (YYYY-MM-DD).
        chart_type: Visualization type (line, bar, table, etc.).

    Returns:
        Complete bookmark params dict ready for the API.
    """
    show_section: list[dict[str, Any]] = [
        _build_show_clause(metric) for metric in metrics
    ]

    for formula in formulas:
        show_section.append(_build_formula_clause(formula))

    return {
        "displayOptions": {
            "chartType": chart_type,
            "plotStyle": "standard",
            "analysis": "linear",
            "value": "absolute",
        },
        "sections": {
            "show": show_section,
            "time": [_build_time_clause(time_unit, last, from_date, to_date)],
            "filter": [_build_filter_clause(f) for f in where],
            "group": [_build_group_clause(b) for b in group_by],
        },
    }


def _build_show_clause(metric: Metric) -> dict[str, Any]:
    """Build a single show clause from a Metric.

    Args:
        metric: Metric definition.

    Returns:
        Show clause dict with behavior and measurement.
    """
    behavior: dict[str, Any] = {
        "type": "event",
        "name": metric.event,
        "resourceType": "events",
        "filtersDeterminer": metric.filters_combinator,
        "filters": [_build_filter_clause(f) for f in (metric.filters or [])],
    }

    measurement: dict[str, Any] = {
        "math": metric.math,
    }

    if metric.property is not None:
        measurement["property"] = {
            "name": metric.property,
            "resourceType": "events",
            "type": "number",
            "defaultType": "number",
            "dataset": "mixpanel",
        }

    if metric.per_user is not None:
        measurement["perUserAggregation"] = metric.per_user

    clause: dict[str, Any] = {
        "type": "metric",
        "behavior": behavior,
        "measurement": measurement,
    }

    if metric.hidden:
        clause["isHidden"] = True

    return clause


def _build_formula_clause(formula: Formula) -> dict[str, Any]:
    """Build a formula show clause from a Formula.

    Args:
        formula: Formula definition.

    Returns:
        Formula show clause dict.
    """
    return {
        "type": "formula",
        "name": formula.name or formula.expression,
        "definition": formula.expression,
        "measurement": {},
        "referencedMetrics": [],
    }


def _build_filter_clause(f: Filter) -> dict[str, Any]:
    """Build a filter section entry from a Filter.

    Args:
        f: Filter definition.

    Returns:
        Filter clause dict matching bookmark params schema.
    """
    return {
        "resourceType": f.resource_type,
        "filterType": f.property_type,
        "defaultType": f.property_type,
        "value": f.property,
        "filterOperator": f.operator,
        "filterValue": f.value,
    }


def _build_group_clause(b: Breakdown) -> dict[str, Any]:
    """Build a group section entry from a Breakdown.

    Args:
        b: Breakdown definition.

    Returns:
        Group clause dict matching bookmark params schema.
    """
    clause: dict[str, Any] = {
        "resourceType": b.resource_type,
        "propertyType": b.property_type,
        "propertyDefaultType": b.property_type,
        "propertyName": b.property,
        "value": b.property,
    }

    if b.bucket is not None:
        clause["customBucket"] = {
            "bucketSize": b.bucket.size,
            "min": b.bucket.min,
            "max": b.bucket.max,
        }

    return clause


def _build_time_clause(
    unit: str,
    last: int | None,
    from_date: str | None,
    to_date: str | None,
) -> dict[str, Any]:
    """Build a time section entry from date arguments.

    Args:
        unit: Time granularity.
        last: Relative date range — last N units.
        from_date: Absolute start date.
        to_date: Absolute end date.

    Returns:
        Time clause dict matching bookmark params schema.
    """
    if last is not None:
        return {
            "dateRangeType": "in the last",
            "unit": unit,
            "window": {
                "unit": unit,
                "value": last,
            },
        }

    return {
        "dateRangeType": "between",
        "unit": unit,
        "value": [from_date, to_date],
    }
