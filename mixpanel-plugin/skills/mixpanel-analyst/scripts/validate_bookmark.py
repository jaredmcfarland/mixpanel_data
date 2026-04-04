#!/usr/bin/env python3
"""
Validate Mixpanel bookmark JSON against the canonical schema.

Enum values are extracted from the vendored bookmark JSON Schema
(schemas/bookmark.json) at load time.  If the schema file is missing,
hardcoded fallback values are used — behavior is identical either way.

Usage:
  python validate_bookmark.py <json_file_or_string> [--type TYPE]
  python validate_bookmark.py --stdin [--type TYPE]

Exit codes:
  0 = valid (or warnings only)
  1 = invalid (has errors)
  2 = usage error
"""

import argparse
import json
import sys
from difflib import get_close_matches
from pathlib import Path

# ---------------------------------------------------------------------------
# Schema loading — extract enum values from vendored bookmark.json
# ---------------------------------------------------------------------------


def _load_schema_enums(schema_path: Path | None = None) -> dict[str, set[str]]:
    """Extract enum values from the canonical bookmark JSON Schema.

    Returns a dict mapping logical name -> set of valid string values.
    Returns empty dict if schema file is missing or malformed.
    """
    if schema_path is None:
        schema_path = Path(__file__).resolve().parent / "schemas" / "bookmark.json"
    if not schema_path.is_file():
        return {}
    try:
        schema = json.loads(schema_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    defs = schema.get("definitions", {})

    def enum_values(name: str) -> set[str]:
        return set(defs.get(name, {}).get("enum", []))

    return {
        "chart_types": enum_values("ChartType"),
        "math_primitive": enum_values("PRIMITIVE_MATH_TYPES"),
        "math_xau": enum_values("XAU_MATH_TYPES"),
        "math_funnels": enum_values("FUNNELS_MATH_TYPES"),
        "math_retention": enum_values("RETENTION_MATH_TYPES"),
        "per_user_aggregations": enum_values("PER_USER_AGGREGATIONS"),
        "metric_types": enum_values("MetricType"),
        "resource_types": enum_values("InsightsResourceType"),
        "property_types": enum_values("PropertyType"),
        "time_units": (
            enum_values("BaseTimeUnit")
            | enum_values("ExtendedTimeUnit")
            | enum_values("NonStandardTimeUnit")
            | enum_values("SpecialTimeUnit")
        ),
        "funnel_order": enum_values("FunnelOrder"),
        "conversion_window_unit": enum_values("ConversionWindowUnit"),
        "retention_type": enum_values("RetentionType"),
        "retention_alignment_type": enum_values("RetentionAlignmentType"),
        "retention_unbounded_mode": enum_values("RetentionUnboundedModeType"),
        "filters_determiner": enum_values("FiltersDeterminer"),
    }


# ---------------------------------------------------------------------------
# Constants — schema-derived with hardcoded fallbacks
# ---------------------------------------------------------------------------

_SCHEMA = _load_schema_enums()

# Chart types: schema has 31+, fallback has the most common 13
VALID_CHART_TYPES_INSIGHTS = _SCHEMA.get(
    "chart_types",
    {
        "bar",
        "line",
        "column",
        "pie",
        "table",
        "insights-metric",
        "bar-stacked",
        "stacked-line",
        "stacked-column",
        "metric",
        "funnel-steps",
        "funnel-top-paths",
        "retention-curve",
    },
)
VALID_CHART_TYPES_FLOWS = {"sankey", "paths", "flows"}  # no flows schema

# Math types: context-dependent (insights vs funnels vs retention)
VALID_MATH_INSIGHTS = _SCHEMA.get(
    "math_primitive",
    {
        "total",
        "unique",
        "sessions",
        "average",
        "median",
        "p25",
        "p75",
        "p90",
        "p99",
        "custom_percentile",
        "min",
        "max",
        "cumulative_unique",
        "histogram",
        "unique_values",
        "most_frequent",
        "first_value",
        "multi_attribution",
        "numeric_summary",
    },
) | _SCHEMA.get("math_xau", {"dau", "wau", "mau"})

VALID_MATH_FUNNELS = _SCHEMA.get(
    "math_funnels",
    {
        "general",
        "unique",
        "session",
        "conversion_rate",
        "conversion_rate_unique",
        "conversion_rate_total",
        "conversion_rate_session",
        "total",
    },
)

VALID_MATH_RETENTION = _SCHEMA.get(
    "math_retention",
    {
        "unique",
        "retention_rate",
        "total",
        "average",
    },
)

# Semantic constraint: these math types require measurement.property
# (not in schema — hand-written)
MATH_REQUIRING_PROPERTY = {
    "average",
    "median",
    "min",
    "max",
    "p25",
    "p75",
    "p90",
    "p99",
    "custom_percentile",
}

# Behavior / metric types
VALID_METRIC_TYPES = _SCHEMA.get(
    "metric_types",
    {
        "cohort",
        "custom-event",
        "event",
        "formula",
        "funnel",
        "people",
        "retention",
        "retention-frequency",
        "saved-metric",
        "simple",
        "verified",
    },
)

VALID_RESOURCE_TYPES = _SCHEMA.get(
    "resource_types",
    {
        "all",
        "cohort",
        "cohorts",
        "event",
        "events",
        "formulas",
        "other",
        "people",
        "user",
    },
)

VALID_PROPERTY_TYPES = _SCHEMA.get(
    "property_types",
    {
        "boolean",
        "datetime",
        "list",
        "number",
        "string",
        "dimension",
        "object",
        "other",
        "unknown",
    },
)

VALID_TIME_UNITS = _SCHEMA.get(
    "time_units",
    {
        "second",
        "minute",
        "hour",
        "day",
        "week",
        "month",
        "quarter",
        "year",
        "session",
        "hour_of_day",
        "day_of_week",
    },
)

# Hand-written: schema types these as bare strings, not enums
VALID_DATE_RANGE_TYPES = {
    "in the last",
    "between",
    "since",
    "on",
    "relative_after",
}

VALID_FILTER_OPERATORS = {
    "equals",
    "does not equal",
    "contains",
    "does not contain",
    "is set",
    "is not set",
    "is defined",
    "is not defined",
    "is at least",
    "is equal to",
    "is not equal to",
    "is greater than",
    "is less than",
    "is at most",
    "is between",
    "was on",
    "was before",
    "was since",
    "was after",
    "true",
    "false",
}

# Schema-derived: new validation sets (empty fallback = no-op if schema missing)
VALID_FUNNEL_ORDER = _SCHEMA.get("funnel_order", set())
VALID_CONVERSION_WINDOW_UNIT = _SCHEMA.get("conversion_window_unit", set())
VALID_RETENTION_TYPE = _SCHEMA.get("retention_type", set())
VALID_RETENTION_ALIGNMENT_TYPE = _SCHEMA.get("retention_alignment_type", set())
VALID_RETENTION_UNBOUNDED_MODE = _SCHEMA.get("retention_unbounded_mode", set())
VALID_FILTERS_DETERMINER = _SCHEMA.get("filters_determiner", set())
VALID_PER_USER_AGGREGATIONS = _SCHEMA.get("per_user_aggregations", set())

# Bookmark type mapping (from Mixpanel's internal OpenAPI spec)
VALID_BOOKMARK_TYPES = {
    "addiction",
    "dashboard",
    "flows",
    "formulas",
    "funnel-query",
    "funnels",
    "insights",
    "jql-console",
    "launch-analysis",
    "retention",
    "revenue",
    "segmentation",
    "segmentation3",
    "users",
}

# Maps outer bookmark_type → structural params type for validation
BOOKMARK_TYPE_TO_PARAMS_TYPE = {
    "insights": "insights",
    "segmentation": "insights",
    "segmentation3": "insights",
    "revenue": "insights",
    "formulas": "insights",
    "launch-analysis": "insights",
    "funnels": "funnels",
    "funnel-query": "funnels",
    "retention": "retention",
    "addiction": "retention",
    "flows": "flows",
    # dashboard, jql-console, users — non-query types, no params validation
}


# ---------------------------------------------------------------------------
# Agent-optimized helpers
# ---------------------------------------------------------------------------


def _suggest(value: str, valid: set[str], n: int = 3, cutoff: float = 0.5) -> list[str]:
    """Return closest matches for a mistyped enum value."""
    return get_close_matches(value, sorted(valid), n=n, cutoff=cutoff)


def _enum_error(
    path: str, field: str, value: str, valid: set[str], severity: str = "error"
) -> "ValidationError":
    """Build an agent-friendly error for an invalid enum value."""
    matches = _suggest(value, valid)
    if matches:
        msg = f"Invalid {field} '{value}'"
        suggestion = matches
    else:
        sample = sorted(valid)[:5]
        msg = f"Invalid {field} '{value}'. Valid ({len(valid)} total): {sample}"
        suggestion = None
    return ValidationError(path, msg, severity=severity, suggestion=suggestion)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class ValidationError:
    def __init__(
        self,
        path: str,
        message: str,
        severity: str = "error",
        suggestion: list[str] | str | None = None,
        fix: dict | None = None,
    ):
        self.path = path
        self.message = message
        self.severity = severity  # "error" or "warning"
        self.suggestion = suggestion  # closest valid value(s)
        self.fix = fix  # JSON template to insert

    def __str__(self):
        prefix = "WARNING" if self.severity == "warning" else "ERROR"
        s = f"[{prefix}] {self.path}: {self.message}"
        if self.suggestion:
            if isinstance(self.suggestion, list) and self.suggestion:
                s += f" Did you mean '{self.suggestion[0]}'?"
            elif isinstance(self.suggestion, str):
                s += f" Did you mean '{self.suggestion}'?"
        if self.fix:
            s += f"\n  Fix: add {json.dumps(self.fix)}"
        return s


def validate_insights_bookmark(params: dict) -> list[ValidationError]:
    """Validate InsightsBookmarkParams structure."""
    errors = []

    # Required top-level fields
    if "displayOptions" not in params:
        errors.append(
            ValidationError("params", "Missing required field 'displayOptions'")
        )
    if "sections" not in params:
        errors.append(ValidationError("params", "Missing required field 'sections'"))
        return errors  # Can't validate further without sections

    # Validate displayOptions
    display = params.get("displayOptions", {})
    if not isinstance(display, dict):
        errors.append(ValidationError("displayOptions", "Must be a dict"))
    else:
        chart_type = display.get("chartType")
        if chart_type is None:
            errors.append(
                ValidationError("displayOptions", "Missing required 'chartType'")
            )
        elif chart_type not in VALID_CHART_TYPES_INSIGHTS:
            errors.append(
                _enum_error(
                    "displayOptions.chartType",
                    "chartType",
                    chart_type,
                    VALID_CHART_TYPES_INSIGHTS,
                )
            )

    # Validate sections
    sections = params.get("sections", {})
    if not isinstance(sections, dict):
        errors.append(ValidationError("sections", "Must be a dict"))
        return errors

    # Required sections fields
    show = sections.get("show")
    if show is None:
        errors.append(ValidationError("sections", "Missing required field 'show'"))
    elif not isinstance(show, list) or len(show) == 0:
        errors.append(ValidationError("sections.show", "Must be a non-empty list"))
    else:
        for i, clause in enumerate(show):
            errors.extend(validate_show_clause(clause, f"sections.show[{i}]"))

    time = sections.get("time")
    if time is None:
        errors.append(ValidationError("sections", "Missing required field 'time'"))
    elif not isinstance(time, list) or len(time) == 0:
        errors.append(ValidationError("sections.time", "Must be a non-empty list"))
    else:
        for i, t in enumerate(time):
            errors.extend(validate_time_clause(t, f"sections.time[{i}]"))

    # Optional sections
    filters = sections.get("filter", [])
    if filters and isinstance(filters, list):
        for i, f in enumerate(filters):
            errors.extend(validate_filter_clause(f, f"sections.filter[{i}]"))

    groups = sections.get("group", [])
    if groups and isinstance(groups, list):
        for i, g in enumerate(groups):
            errors.extend(validate_group_clause(g, f"sections.group[{i}]"))

    return errors


def validate_show_clause(clause: dict, path: str) -> list[ValidationError]:
    """Validate a single show clause (BehaviorShowClause or FormulaShowClause)."""
    errors = []
    if not isinstance(clause, dict):
        errors.append(ValidationError(path, "Must be a dict"))
        return errors

    clause_type = clause.get("type")

    # FormulaShowClause
    if clause_type == "formula" or "formula" in clause:
        if "formula" not in clause and "definition" not in clause:
            errors.append(
                ValidationError(path, "Formula clause needs 'formula' or 'definition'")
            )
        return errors

    # BehaviorShowClause
    behavior = clause.get("behavior")
    if behavior is None:
        errors.append(ValidationError(path, "Missing 'behavior' in metric show clause"))
        return errors

    if not isinstance(behavior, dict):
        errors.append(ValidationError(f"{path}.behavior", "Must be a dict"))
        return errors

    btype = behavior.get("type")
    if btype and btype not in VALID_METRIC_TYPES:
        errors.append(
            _enum_error(
                f"{path}.behavior.type",
                "behavior type",
                btype,
                VALID_METRIC_TYPES,
            )
        )

    # Check behavior.name for event types
    if btype in ("event", "simple", "custom-event") and not behavior.get("name"):
        errors.append(
            ValidationError(
                f"{path}.behavior.name",
                "Event-type behavior requires 'name'",
                fix={"name": "<EVENT_NAME>"},
            )
        )

    # Validate filtersDeterminer
    fd = behavior.get("filtersDeterminer")
    if fd and VALID_FILTERS_DETERMINER and fd not in VALID_FILTERS_DETERMINER:
        errors.append(
            _enum_error(
                f"{path}.behavior.filtersDeterminer",
                "filtersDeterminer",
                fd,
                VALID_FILTERS_DETERMINER,
                severity="warning",
            )
        )

    # Validate measurement
    measurement = clause.get("measurement")
    if measurement and isinstance(measurement, dict):
        math = measurement.get("math")
        if math:
            # Context-dependent math validation
            if btype == "funnel":
                valid = VALID_MATH_FUNNELS
            elif btype in ("retention", "retention-frequency"):
                valid = VALID_MATH_RETENTION
            else:
                valid = VALID_MATH_INSIGHTS
            if math not in valid:
                errors.append(
                    _enum_error(
                        f"{path}.measurement.math",
                        f"math (for behavior type '{btype}')",
                        math,
                        valid,
                    )
                )

            # Property-aggregation math types require measurement.property
            if math in MATH_REQUIRING_PROPERTY and not measurement.get("property"):
                errors.append(
                    ValidationError(
                        f"{path}.measurement.property",
                        f"Math type '{math}' requires 'measurement.property'",
                        severity="warning",
                        fix={
                            "name": "<PROPERTY_NAME>",
                            "defaultType": "number",
                            "type": "number",
                            "resourceType": "events",
                        },
                    )
                )

        # Validate perUserAggregation
        pua = measurement.get("perUserAggregation")
        if (
            pua
            and VALID_PER_USER_AGGREGATIONS
            and pua not in VALID_PER_USER_AGGREGATIONS
        ):
            errors.append(
                _enum_error(
                    f"{path}.measurement.perUserAggregation",
                    "perUserAggregation",
                    pua,
                    VALID_PER_USER_AGGREGATIONS,
                    severity="warning",
                )
            )

    # Validate per-metric behavior.filters[]
    bfilters = behavior.get("filters", [])
    if bfilters and isinstance(bfilters, list):
        for i, f in enumerate(bfilters):
            errors.extend(validate_filter_clause(f, f"{path}.behavior.filters[{i}]"))

    # Validate funnel-specific fields
    if btype == "funnel":
        behaviors = behavior.get("behaviors", [])
        if not behaviors or len(behaviors) < 2:
            errors.append(
                ValidationError(
                    f"{path}.behavior.behaviors",
                    "Funnel needs at least 2 sub-behaviors (steps)",
                )
            )

        fo = behavior.get("funnelOrder")
        if fo and VALID_FUNNEL_ORDER and fo not in VALID_FUNNEL_ORDER:
            errors.append(
                _enum_error(
                    f"{path}.behavior.funnelOrder",
                    "funnelOrder",
                    fo,
                    VALID_FUNNEL_ORDER,
                    severity="warning",
                )
            )

        cwu = behavior.get("conversionWindowUnit")
        if (
            cwu
            and VALID_CONVERSION_WINDOW_UNIT
            and cwu not in VALID_CONVERSION_WINDOW_UNIT
        ):
            errors.append(
                _enum_error(
                    f"{path}.behavior.conversionWindowUnit",
                    "conversionWindowUnit",
                    cwu,
                    VALID_CONVERSION_WINDOW_UNIT,
                    severity="warning",
                )
            )

    # Validate retention-specific fields
    if btype in ("retention", "retention-frequency"):
        behaviors = behavior.get("behaviors", [])
        if behaviors is not None and len(behaviors) != 2:
            errors.append(
                ValidationError(
                    f"{path}.behavior.behaviors",
                    "Retention needs exactly 2 sub-behaviors (born + return)",
                )
            )

        rt = behavior.get("retentionType")
        if rt and VALID_RETENTION_TYPE and rt not in VALID_RETENTION_TYPE:
            errors.append(
                _enum_error(
                    f"{path}.behavior.retentionType",
                    "retentionType",
                    rt,
                    VALID_RETENTION_TYPE,
                    severity="warning",
                )
            )

        rat = behavior.get("retentionAlignmentType")
        if (
            rat
            and VALID_RETENTION_ALIGNMENT_TYPE
            and rat not in VALID_RETENTION_ALIGNMENT_TYPE
        ):
            errors.append(
                _enum_error(
                    f"{path}.behavior.retentionAlignmentType",
                    "retentionAlignmentType",
                    rat,
                    VALID_RETENTION_ALIGNMENT_TYPE,
                    severity="warning",
                )
            )

        rum = behavior.get("retentionUnboundedMode")
        if (
            rum
            and VALID_RETENTION_UNBOUNDED_MODE
            and rum not in VALID_RETENTION_UNBOUNDED_MODE
        ):
            errors.append(
                _enum_error(
                    f"{path}.behavior.retentionUnboundedMode",
                    "retentionUnboundedMode",
                    rum,
                    VALID_RETENTION_UNBOUNDED_MODE,
                    severity="warning",
                )
            )

    return errors


def validate_time_clause(clause: dict, path: str) -> list[ValidationError]:
    """Validate a time clause."""
    errors = []
    if not isinstance(clause, dict):
        errors.append(ValidationError(path, "Must be a dict"))
        return errors

    # Must have unit
    unit = clause.get("unit")
    if unit and unit not in VALID_TIME_UNITS:
        errors.append(_enum_error(f"{path}.unit", "unit", unit, VALID_TIME_UNITS))

    # Must have dateRangeType or value
    drt = clause.get("dateRangeType")
    if drt and drt not in VALID_DATE_RANGE_TYPES:
        errors.append(
            _enum_error(
                f"{path}.dateRangeType",
                "dateRangeType",
                drt,
                VALID_DATE_RANGE_TYPES,
            )
        )

    # Validate window if present
    window = clause.get("window")
    if window and isinstance(window, dict):
        wunit = window.get("unit")
        if wunit and wunit not in VALID_TIME_UNITS:
            errors.append(
                _enum_error(
                    f"{path}.window.unit",
                    "window unit",
                    wunit,
                    VALID_TIME_UNITS,
                )
            )
        if "value" not in window:
            errors.append(ValidationError(f"{path}.window", "Missing 'value'"))

    return errors


def validate_filter_clause(clause: dict, path: str) -> list[ValidationError]:
    """Validate a filter clause."""
    errors = []
    if not isinstance(clause, dict):
        errors.append(ValidationError(path, "Must be a dict"))
        return errors

    # Must have property identification
    if not clause.get("value") and not clause.get("propertyName"):
        errors.append(
            ValidationError(
                path, "Missing property identifier ('value' or 'propertyName')"
            )
        )

    # Validate resourceType
    rt = clause.get("resourceType")
    if rt and rt not in VALID_RESOURCE_TYPES:
        errors.append(
            _enum_error(
                f"{path}.resourceType",
                "resourceType",
                rt,
                VALID_RESOURCE_TYPES,
            )
        )

    # Validate filterType
    ft = clause.get("filterType")
    if ft and ft not in VALID_PROPERTY_TYPES:
        errors.append(
            _enum_error(
                f"{path}.filterType",
                "filterType",
                ft,
                VALID_PROPERTY_TYPES,
            )
        )

    # Validate filterOperator
    fo = clause.get("filterOperator")
    if fo and fo not in VALID_FILTER_OPERATORS:
        errors.append(
            _enum_error(
                f"{path}.filterOperator",
                "filterOperator",
                fo,
                VALID_FILTER_OPERATORS,
                severity="warning",
            )
        )

    return errors


def validate_group_clause(clause: dict, path: str) -> list[ValidationError]:
    """Validate a group/breakdown clause."""
    errors = []
    if not isinstance(clause, dict):
        errors.append(ValidationError(path, "Must be a dict"))
        return errors

    # Should have propertyName for standard breakdowns
    if (
        not clause.get("propertyName")
        and not clause.get("behavior")
        and not clause.get("cohorts")
    ):
        errors.append(
            ValidationError(
                path,
                "Group clause needs 'propertyName', 'behavior', or 'cohorts'",
                severity="warning",
            )
        )

    pt = clause.get("propertyType")
    if pt and pt not in VALID_PROPERTY_TYPES:
        errors.append(
            _enum_error(
                f"{path}.propertyType",
                "propertyType",
                pt,
                VALID_PROPERTY_TYPES,
            )
        )

    return errors


def validate_flows_bookmark(params: dict) -> list[ValidationError]:
    """Validate FlowsBookmarkParams structure."""
    errors = []

    if "steps" not in params:
        errors.append(ValidationError("params", "Missing required 'steps' for flows"))
    elif not isinstance(params["steps"], list) or len(params["steps"]) == 0:
        errors.append(ValidationError("params.steps", "Must be a non-empty list"))
    else:
        for i, step in enumerate(params["steps"]):
            if not isinstance(step, dict):
                errors.append(ValidationError(f"params.steps[{i}]", "Must be a dict"))
                continue
            if not step.get("event") and not step.get("custom_event"):
                errors.append(
                    ValidationError(
                        f"params.steps[{i}]",
                        "Step needs 'event' or 'custom_event'",
                    )
                )

    if "date_range" not in params:
        errors.append(
            ValidationError("params", "Missing required 'date_range' for flows")
        )

    return errors


def detect_bookmark_type(params: dict) -> str:
    """Detect bookmark type from params structure."""
    if "steps" in params and "date_range" in params:
        return "flows"
    sections = params.get("sections", {})
    show = sections.get("show", [])
    if show and isinstance(show, list) and len(show) > 0:
        first = show[0]
        if isinstance(first, dict):
            behavior = first.get("behavior", {})
            if isinstance(behavior, dict):
                btype = behavior.get("type", "")
                if btype == "funnel":
                    return "funnels"
                elif btype in ("retention", "retention-frequency"):
                    return "retention"
    return "insights"


def validate_bookmark(
    params: dict, bookmark_type: str | None = None
) -> list[ValidationError]:
    """
    Validate bookmark params.

    Args:
        params: The bookmark params dict
        bookmark_type: Bookmark type — accepts both structural types
            (insights, funnels, retention, flows) and outer types
            (segmentation, funnel-query, addiction, etc.).
            Auto-detected from params structure if None.

    Returns:
        List of ValidationError objects (empty = valid)
    """
    errors = []

    # Resolve structural type from bookmark_type
    if bookmark_type and bookmark_type in BOOKMARK_TYPE_TO_PARAMS_TYPE:
        structural_type = BOOKMARK_TYPE_TO_PARAMS_TYPE[bookmark_type]
    elif bookmark_type and bookmark_type in {
        "insights",
        "funnels",
        "retention",
        "flows",
    }:
        structural_type = bookmark_type
    elif bookmark_type and bookmark_type not in VALID_BOOKMARK_TYPES:
        errors.append(
            ValidationError(
                "bookmark_type",
                f"Unknown bookmark type '{bookmark_type}'",
                severity="warning",
                suggestion=_suggest(bookmark_type, VALID_BOOKMARK_TYPES),
            )
        )
        structural_type = detect_bookmark_type(params)
    else:
        structural_type = detect_bookmark_type(params)

    if structural_type == "flows":
        errors.extend(validate_flows_bookmark(params))
    else:
        errors.extend(validate_insights_bookmark(params))

    return errors


def main():
    all_types = sorted(
        VALID_BOOKMARK_TYPES | {"insights", "funnels", "retention", "flows"}
    )

    parser = argparse.ArgumentParser(description="Validate Mixpanel bookmark JSON")
    parser.add_argument("input", nargs="?", help="JSON file path or inline JSON string")
    parser.add_argument("--stdin", action="store_true", help="Read JSON from stdin")
    parser.add_argument(
        "--type", choices=all_types, help="Bookmark type (auto-detected if omitted)"
    )
    parser.add_argument("--json", action="store_true", help="Output errors as JSON")
    args = parser.parse_args()

    if args.stdin:
        raw = sys.stdin.read()
    elif args.input:
        # Try as file path first (only if short enough to be a path)
        if len(args.input) < 260 and not args.input.startswith("{"):
            path = Path(args.input)
            raw = path.read_text() if path.is_file() else args.input
        else:
            raw = args.input
    else:
        parser.print_help()
        sys.exit(2)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Handle both {"params": {...}} wrapper and raw params
    if "params" in data and isinstance(data["params"], dict):
        params = data["params"]
    else:
        params = data

    errors = validate_bookmark(params, args.type)

    if errors:
        if args.json:
            out = []
            for e in errors:
                entry: dict = {
                    "path": e.path,
                    "message": e.message,
                    "severity": e.severity,
                }
                if e.suggestion:
                    entry["suggestion"] = e.suggestion
                if e.fix:
                    entry["fix"] = e.fix
                out.append(entry)
            print(json.dumps(out, indent=2))
        else:
            for e in errors:
                print(str(e), file=sys.stderr)
        real_errors = [e for e in errors if e.severity == "error"]
        sys.exit(1 if real_errors else 0)
    else:
        if args.json:
            print('{"valid": true}')
        else:
            print("Valid bookmark.")
        sys.exit(0)


if __name__ == "__main__":
    main()
