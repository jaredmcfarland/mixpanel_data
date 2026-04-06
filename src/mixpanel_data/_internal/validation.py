"""Bookmark validation engine for mixpanel_data.

Two validation layers:

- ``validate_query_args()``: Validates Python-level arguments before
  bookmark construction (Layer 1, rules V0-V27).
- ``validate_bookmark()``: Validates the bookmark JSON dict after
  construction (Layer 2, rules B1-B19).

Both return ``list[ValidationError]``. Callers decide whether to raise
``BookmarkValidationError``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from difflib import get_close_matches
from typing import Any, Literal

from mixpanel_data._internal.bookmark_enums import (
    _MAX_FUNNEL_STEPS,
    _MAX_HOLDING_CONSTANT,
    MATH_NO_PER_USER,
    MATH_PROPERTY_OPTIONAL,
    MATH_REQUIRING_PROPERTY,
    MAX_CONVERSION_WINDOW,
    VALID_CHART_TYPES,
    VALID_CONVERSION_WINDOW_UNITS,
    VALID_FILTER_OPERATORS,
    VALID_FILTERS_DETERMINER,
    VALID_MATH_FUNNELS,
    VALID_MATH_INSIGHTS,
    VALID_METRIC_TYPES,
    VALID_PER_USER_AGGREGATIONS,
    VALID_PROPERTY_TYPES,
    VALID_RESOURCE_TYPES,
    VALID_TIME_UNITS,
)
from mixpanel_data.exceptions import ValidationError

# Avoid circular imports — these are only needed for isinstance checks
# at runtime, so import the types module (not individual names from types.py)
from mixpanel_data.types import (
    Exclusion,
    Formula,
    FunnelStep,
    GroupBy,
    HoldingConstant,
    MathType,
    Metric,
    PerUserAggregation,
)

_SESSION_MATH: frozenset[str] = frozenset({"conversion_rate_session"})
"""Session-based math types requiring conversion_window_unit='session'."""

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FORMULA_POSITION_RE = re.compile(r"[A-Z]")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INVISIBLE_RE = re.compile(r"^[\s\u200b\u200c\u200d\ufeff\u00ad\u2060]*$")
_MAX_LAST_DAYS = 3650  # 10 years — generous but sane upper bound
_MAX_ROLLING = 365  # rolling window sanity cap


def _is_valid_date(date_str: str) -> bool:
    """Check if a YYYY-MM-DD string is a valid calendar date.

    Args:
        date_str: Date string in YYYY-MM-DD format (regex-validated).

    Returns:
        True if the date is a valid calendar date.
    """
    import datetime

    try:
        datetime.date.fromisoformat(date_str)
        return True
    except ValueError:
        return False


def _is_finite(value: int | float | None) -> bool:
    """Check if a numeric value is finite (not NaN, not Inf).

    Args:
        value: Numeric value to check.

    Returns:
        True if finite or None.
    """
    if value is None:
        return True
    if isinstance(value, float):
        import math as _math

        return _math.isfinite(value)
    return True


# =============================================================================
# Fuzzy matching helpers
# =============================================================================


def _suggest(
    value: str,
    valid: frozenset[str],
    n: int = 3,
    cutoff: float = 0.5,
) -> tuple[str, ...] | None:
    """Find closest matches for a mistyped enum value.

    Args:
        value: The invalid value to match against.
        valid: Set of valid values.
        n: Maximum number of suggestions.
        cutoff: Minimum similarity ratio (0.0-1.0).

    Returns:
        Tuple of closest matches, or None if no matches found.
    """
    matches = get_close_matches(value, sorted(valid), n=n, cutoff=cutoff)
    return tuple(matches) if matches else None


def _enum_error(
    path: str,
    field: str,
    value: str,
    valid: frozenset[str],
    code: str,
    severity: Literal["error", "warning"] = "error",
) -> ValidationError:
    """Build a validation error for an invalid enum value with suggestions.

    Args:
        path: JSONPath-like location.
        field: Human-readable field name.
        value: The invalid value.
        valid: Set of valid values.
        code: Machine-readable error code.
        severity: Error severity level.

    Returns:
        ValidationError with fuzzy-matched suggestions.
    """
    suggestion = _suggest(value, valid)
    if suggestion:
        msg = f"Invalid {field} '{value}'"
    else:
        sample = sorted(valid)[:5]
        msg = f"Invalid {field} '{value}'. Valid ({len(valid)} total): {sample}"
    return ValidationError(
        path=path,
        message=msg,
        code=code,
        severity=severity,
        suggestion=suggestion,
    )


# =============================================================================
# Reusable sub-validators (time, group-by)
# =============================================================================


def validate_time_args(
    *,
    from_date: str | None,
    to_date: str | None,
    last: int,
) -> list[ValidationError]:
    """Validate time-range arguments (rules V7-V10, V15, V20).

    Extracted from ``validate_query_args()`` so callers building
    non-Insights bookmark types can reuse the same date/last checks
    without pulling in the full query-arg validator.

    Args:
        from_date: Start date in YYYY-MM-DD format, or ``None``.
        to_date: End date in YYYY-MM-DD format, or ``None``.
        last: Number of days for a relative date range. The default
            value used by ``Workspace.query()`` is ``30``.

    Returns:
        List of validation errors. Empty list means all time
        arguments are valid.

    Example:
        ```python
        from mixpanel_data._internal.validation import validate_time_args

        errors = validate_time_args(
            from_date="2024-01-01",
            to_date="2024-01-31",
            last=30,
        )
        assert errors == []
        ```
    """
    errors: list[ValidationError] = []

    # V7: last must be positive
    if last <= 0:
        errors.append(
            ValidationError(
                path="last",
                message="last must be a positive integer",
                code="V7_LAST_POSITIVE",
            )
        )

    # V8: Date format and calendar validation
    if from_date is not None:
        if not _DATE_RE.match(from_date):
            errors.append(
                ValidationError(
                    path="from_date",
                    message=f"from_date must be YYYY-MM-DD format (got '{from_date}')",
                    code="V8_DATE_FORMAT",
                )
            )
        elif not _is_valid_date(from_date):
            errors.append(
                ValidationError(
                    path="from_date",
                    message=f"from_date '{from_date}' is not a valid calendar date",
                    code="V8_DATE_INVALID",
                )
            )
    if to_date is not None:
        if not _DATE_RE.match(to_date):
            errors.append(
                ValidationError(
                    path="to_date",
                    message=f"to_date must be YYYY-MM-DD format (got '{to_date}')",
                    code="V8_DATE_FORMAT",
                )
            )
        elif not _is_valid_date(to_date):
            errors.append(
                ValidationError(
                    path="to_date",
                    message=f"to_date '{to_date}' is not a valid calendar date",
                    code="V8_DATE_INVALID",
                )
            )

    # V9: to_date requires from_date
    if to_date is not None and from_date is None:
        errors.append(
            ValidationError(
                path="to_date",
                message="to_date requires from_date",
                code="V9_TO_REQUIRES_FROM",
            )
        )

    # V10: Cannot combine explicit dates with non-default last
    if from_date is not None and last != 30:
        errors.append(
            ValidationError(
                path="last",
                message=(
                    f"Cannot combine last={last} with explicit dates; "
                    f"use either last or from_date/to_date"
                ),
                code="V10_DATE_LAST_EXCLUSIVE",
            )
        )

    # V15: Date ordering — from_date must be <= to_date
    if (
        from_date is not None
        and to_date is not None
        and _DATE_RE.match(from_date)
        and _DATE_RE.match(to_date)
        and from_date > to_date
    ):
        errors.append(
            ValidationError(
                path="from_date",
                message=(
                    f"from_date '{from_date}' is after to_date '{to_date}'; "
                    f"dates must be in chronological order"
                ),
                code="V15_DATE_ORDER",
            )
        )

    # V20: last must not be absurdly large
    if last > _MAX_LAST_DAYS:
        errors.append(
            ValidationError(
                path="last",
                message=(
                    f"last={last} exceeds maximum of {_MAX_LAST_DAYS} days (~10 years)"
                ),
                code="V20_LAST_TOO_LARGE",
            )
        )

    return errors


def validate_group_by_args(
    *,
    group_by: str | GroupBy | list[str | GroupBy] | None,
) -> list[ValidationError]:
    """Validate group-by arguments (rules V11-V12, V18, V24).

    Extracted from ``validate_query_args()`` so callers building
    non-Insights bookmark types can reuse the same bucket checks
    without pulling in the full query-arg validator.

    Args:
        group_by: Breakdown specification — a property name string,
            a ``GroupBy`` object with optional bucket config, a list
            of either, or ``None`` for no breakdown.

    Returns:
        List of validation errors. Empty list means all group-by
        arguments are valid.

    Example:
        ```python
        from mixpanel_data._internal.validation import validate_group_by_args
        from mixpanel_data.types import GroupBy

        errors = validate_group_by_args(
            group_by=GroupBy(
                "revenue",
                property_type="number",
                bucket_size=50,
                bucket_min=0,
                bucket_max=500,
            ),
        )
        assert errors == []
        ```
    """
    errors: list[ValidationError] = []

    if group_by is None:
        return errors

    groups = group_by if isinstance(group_by, list) else [group_by]
    for i, g in enumerate(groups):
        if isinstance(g, GroupBy):
            gpath = f"group_by[{i}]" if len(groups) > 1 else "group_by"

            # V24: Bucket values must be finite (not NaN or Inf)
            for fname, fval in [
                ("bucket_size", g.bucket_size),
                ("bucket_min", g.bucket_min),
                ("bucket_max", g.bucket_max),
            ]:
                if not _is_finite(fval):
                    errors.append(
                        ValidationError(
                            path=gpath,
                            message=f"{fname} must be a finite number, got {fval}",
                            code="V24_BUCKET_NOT_FINITE",
                        )
                    )

            if (
                g.bucket_min is not None or g.bucket_max is not None
            ) and g.bucket_size is None:
                errors.append(
                    ValidationError(
                        path=gpath,
                        message="bucket_min/bucket_max require bucket_size",
                        code="V11_BUCKET_REQUIRES_SIZE",
                    )
                )
            if g.bucket_size is not None and g.bucket_size <= 0:
                errors.append(
                    ValidationError(
                        path=gpath,
                        message="bucket_size must be positive",
                        code="V12_BUCKET_SIZE_POSITIVE",
                    )
                )
            if g.bucket_size is not None and g.property_type != "number":
                errors.append(
                    ValidationError(
                        path=gpath,
                        message="bucket_size requires property_type='number'",
                        code="V12B_BUCKET_REQUIRES_NUMBER",
                    )
                )
            if g.bucket_size is not None and (
                g.bucket_min is None or g.bucket_max is None
            ):
                errors.append(
                    ValidationError(
                        path=gpath,
                        message="bucket_size requires both bucket_min and bucket_max",
                        code="V12C_BUCKET_REQUIRES_BOUNDS",
                    )
                )

            # V18: bucket_min must be < bucket_max
            if (
                g.bucket_min is not None
                and g.bucket_max is not None
                and g.bucket_min >= g.bucket_max
            ):
                errors.append(
                    ValidationError(
                        path=gpath,
                        message=(
                            f"bucket_min ({g.bucket_min}) must be less than "
                            f"bucket_max ({g.bucket_max})"
                        ),
                        code="V18_BUCKET_ORDER",
                    )
                )

    return errors


# =============================================================================
# Funnel argument validation (F1-F6)
# =============================================================================


def validate_funnel_args(
    *,
    steps: Sequence[str | FunnelStep],
    conversion_window: int,
    conversion_window_unit: str = "day",
    math: str = "conversion_rate_unique",
    math_property: str | None = None,
    exclusions: list[Exclusion] | None,
    holding_constant: Sequence[str | HoldingConstant] | None = None,
    from_date: str | None,
    to_date: str | None,
    last: int,
    group_by: str | GroupBy | list[str | GroupBy] | None,
) -> list[ValidationError]:
    """Validate funnel query arguments before bookmark construction (Layer 1).

    Implements funnel-specific validation rules F1-F11 plus reused
    time and group-by validators. Returns all errors found so callers
    can fix multiple issues in a single pass.

    Args:
        steps: Funnel step specifications (event names or FunnelStep objects).
        conversion_window: Conversion window size (must be positive).
        conversion_window_unit: Time unit for conversion window.
            Must be one of: second, minute, hour, day, week, month,
            session. Default: ``"day"``.
        math: Funnel aggregation function. Default:
            ``"conversion_rate_unique"``.
        math_property: Numeric property name for property-aggregation
            math types (average, median, min, max, p25, p75, p90, p99).
            Required when ``math`` is a property-aggregation type;
            must be ``None`` otherwise. Default: ``None``.
        exclusions: Events to exclude between steps, or ``None``.
        holding_constant: Properties to hold constant, or ``None``.
        from_date: Start date (YYYY-MM-DD) or ``None``.
        to_date: End date (YYYY-MM-DD) or ``None``.
        last: Number of days for relative date range.
        group_by: Breakdown specification.

    Returns:
        List of validation errors. Empty list means all arguments are valid.

    Example:
        ```python
        from mixpanel_data._internal.validation import validate_funnel_args

        errors = validate_funnel_args(
            steps=["Signup", "Purchase"],
            conversion_window=14,
            exclusions=None,
            from_date=None,
            to_date=None,
            last=30,
            group_by=None,
        )
        assert errors == []
        ```
    """
    errors: list[ValidationError] = []

    # F1: At least 2 steps required
    if len(steps) < 2:
        errors.append(
            ValidationError(
                path="steps",
                message=f"At least 2 steps are required (got {len(steps)})",
                code="F1_MIN_STEPS",
            )
        )

    # F1b: Maximum 100 steps
    if len(steps) > _MAX_FUNNEL_STEPS:
        errors.append(
            ValidationError(
                path="steps",
                message=(
                    f"Maximum {_MAX_FUNNEL_STEPS} steps allowed (got {len(steps)})"
                ),
                code="F1_MAX_STEPS",
            )
        )

    # F2: Each step event must be non-empty string, no control/invisible chars
    for i, step in enumerate(steps):
        event = step.event if isinstance(step, FunnelStep) else step
        if not isinstance(event, str) or not event.strip():
            errors.append(
                ValidationError(
                    path=f"steps[{i}]",
                    message="Step event name must be a non-empty string",
                    code="F2_EMPTY_STEP_EVENT",
                )
            )
            continue
        # F2b: No control characters
        if _CONTROL_CHAR_RE.search(event):
            errors.append(
                ValidationError(
                    path=f"steps[{i}]",
                    message=(f"Step event name contains control characters: {event!r}"),
                    code="F2_CONTROL_CHAR_STEP_EVENT",
                )
            )
        # F2c: No invisible-only names
        if _INVISIBLE_RE.match(event):
            errors.append(
                ValidationError(
                    path=f"steps[{i}]",
                    message="Step event name contains only invisible characters",
                    code="F2_INVISIBLE_STEP_EVENT",
                )
            )

    # F3: Positive integer conversion window
    _valid_window = isinstance(conversion_window, int) and not isinstance(
        conversion_window, bool
    )
    if not _valid_window:
        errors.append(
            ValidationError(
                path="conversion_window",
                message=(
                    f"conversion_window must be an integer, "
                    f"got {type(conversion_window).__name__}"
                ),
                code="F3_CONVERSION_WINDOW_TYPE",
            )
        )
    elif conversion_window <= 0:
        errors.append(
            ValidationError(
                path="conversion_window",
                message="conversion_window must be a positive integer",
                code="F3_CONVERSION_WINDOW_POSITIVE",
            )
        )

    # F3b: Maximum conversion window per unit (requires valid int)
    if (
        _valid_window
        and conversion_window_unit in MAX_CONVERSION_WINDOW
        and conversion_window > 0
    ):
        max_val = MAX_CONVERSION_WINDOW[conversion_window_unit]
        if conversion_window > max_val:
            errors.append(
                ValidationError(
                    path="conversion_window",
                    message=(
                        f"conversion_window={conversion_window} exceeds "
                        f"maximum of {max_val} for unit "
                        f"'{conversion_window_unit}'"
                    ),
                    code="F3_CONVERSION_WINDOW_MAX",
                )
            )

    # F7: Conversion window unit validation
    if conversion_window_unit not in VALID_CONVERSION_WINDOW_UNITS:
        errors.append(
            _enum_error(
                path="conversion_window_unit",
                field="conversion_window_unit",
                value=conversion_window_unit,
                valid=VALID_CONVERSION_WINDOW_UNITS,
                code="F7_INVALID_WINDOW_UNIT",
            )
        )

    if _valid_window:
        # F7b: Minimum conversion window per unit (second requires >=2)
        if conversion_window_unit == "second" and 0 < conversion_window < 2:
            errors.append(
                ValidationError(
                    path="conversion_window",
                    message=(
                        f"conversion_window must be at least 2 when "
                        f"conversion_window_unit='second' (got {conversion_window})"
                    ),
                    code="F7_SECOND_MIN_WINDOW",
                    suggestion=("2",),
                )
            )

        # F9: Session math requires session window
        if math in _SESSION_MATH and conversion_window_unit != "session":
            errors.append(
                ValidationError(
                    path="math",
                    message=(
                        f"math='{math}' requires conversion_window_unit='session'"
                    ),
                    code="F9_SESSION_MATH_REQUIRES_SESSION_WINDOW",
                )
            )
        if (
            conversion_window_unit == "session"
            and math not in _SESSION_MATH
            and conversion_window != 1
        ):
            errors.append(
                ValidationError(
                    path="conversion_window",
                    message=(
                        "conversion_window_unit='session' requires conversion_window=1"
                    ),
                    code="F9_SESSION_WINDOW_REQUIRES_ONE",
                )
            )

    # F10: Property math requires math_property
    if math in MATH_REQUIRING_PROPERTY and math_property is None:
        errors.append(
            ValidationError(
                path="math_property",
                message=(
                    f"math='{math}' requires a math_property "
                    f"(numeric property name to aggregate)"
                ),
                code="F10_MATH_MISSING_PROPERTY",
            )
        )

    # F11: Non-property math rejects math_property
    if (
        math not in MATH_REQUIRING_PROPERTY
        and math not in MATH_PROPERTY_OPTIONAL
        and math_property is not None
    ):
        valid = sorted(MATH_REQUIRING_PROPERTY | MATH_PROPERTY_OPTIONAL)
        errors.append(
            ValidationError(
                path="math_property",
                message=(
                    f"math='{math}' does not support math_property; "
                    f"valid math types for property aggregation: {valid}"
                ),
                code="F11_MATH_REJECTS_PROPERTY",
            )
        )

    # F4: Non-empty exclusion event names and step range validation
    if exclusions is not None:
        for i, ex in enumerate(exclusions):
            if not ex.event or not ex.event.strip():
                errors.append(
                    ValidationError(
                        path=f"exclusions[{i}]",
                        message="Exclusion event name must be a non-empty string",
                        code="F4_EMPTY_EXCLUSION_EVENT",
                    )
                )
            # F4 control char check on exclusion events
            elif _CONTROL_CHAR_RE.search(ex.event):
                errors.append(
                    ValidationError(
                        path=f"exclusions[{i}]",
                        message=(
                            f"Exclusion event name contains control "
                            f"characters: {ex.event!r}"
                        ),
                        code="F4_CONTROL_CHAR_EXCLUSION",
                    )
                )
            # F4e: from_step must be non-negative
            if ex.from_step < 0:
                errors.append(
                    ValidationError(
                        path=f"exclusions[{i}]",
                        message=(
                            f"Exclusion from_step must be >= 0 (got {ex.from_step})"
                        ),
                        code="F4_EXCLUSION_NEGATIVE_STEP",
                    )
                )
            # F4b: to_step must be > from_step (server requires strict from < to)
            if ex.to_step is not None and ex.to_step <= ex.from_step:
                errors.append(
                    ValidationError(
                        path=f"exclusions[{i}]",
                        message=(
                            f"Exclusion to_step ({ex.to_step}) must be > "
                            f"from_step ({ex.from_step})"
                        ),
                        code="F4_EXCLUSION_STEP_ORDER",
                    )
                )
            # F4c: to_step must not exceed step count
            if ex.to_step is not None and ex.to_step >= len(steps):
                errors.append(
                    ValidationError(
                        path=f"exclusions[{i}]",
                        message=(
                            f"Exclusion to_step ({ex.to_step}) exceeds "
                            f"step count ({len(steps)})"
                        ),
                        code="F4_EXCLUSION_STEP_BOUNDS",
                    )
                )
            # F4d: from_step must not exceed step count
            if ex.from_step >= len(steps):
                errors.append(
                    ValidationError(
                        path=f"exclusions[{i}]",
                        message=(
                            f"Exclusion from_step ({ex.from_step}) exceeds "
                            f"step count ({len(steps)})"
                        ),
                        code="F4_EXCLUSION_STEP_BOUNDS",
                    )
                )

    # F8: Holding constant validation
    if holding_constant is not None:
        # F8b: Each holding constant property must be a non-empty string
        for i, hc in enumerate(holding_constant):
            prop = hc.property if isinstance(hc, HoldingConstant) else hc
            if not isinstance(prop, str) or not prop.strip():
                errors.append(
                    ValidationError(
                        path=f"holding_constant[{i}]",
                        message="Holding constant property name must be a non-empty string",
                        code="F8_EMPTY_HOLDING_CONSTANT_PROPERTY",
                    )
                )

    if holding_constant is not None and len(holding_constant) > _MAX_HOLDING_CONSTANT:
        errors.append(
            ValidationError(
                path="holding_constant",
                message=(
                    f"Maximum {_MAX_HOLDING_CONSTANT} holding_constant "
                    f"properties allowed (got {len(holding_constant)})"
                ),
                code="F8_MAX_HOLDING_CONSTANT",
            )
        )

    # F5: Time argument validation (delegated)
    errors.extend(validate_time_args(from_date=from_date, to_date=to_date, last=last))

    # F6: GroupBy validation (delegated)
    errors.extend(validate_group_by_args(group_by=group_by))

    return errors


# =============================================================================
# Layer 1: Argument Validation (V0-V14)
# =============================================================================


def validate_query_args(
    *,
    events: Sequence[str | Metric],
    math: MathType,
    math_property: str | None,
    per_user: PerUserAggregation | None,
    percentile_value: int | float | None = None,
    from_date: str | None,
    to_date: str | None,
    last: int,
    has_formula: bool,
    rolling: int | None,
    cumulative: bool,
    group_by: str | GroupBy | list[str | GroupBy] | None,
    formulas: Sequence[Any] | None = None,
) -> list[ValidationError]:
    """Validate query arguments before bookmark construction (Layer 1).

    Implements validation rules V0-V27, delegating time (V7-V10, V15,
    V20) and group-by (V11-V12, V18, V24) to extracted helpers.
    Returns all errors found, not just the first, so callers can
    fix multiple issues in a single pass.

    Args:
        events: Event names or Metric objects.
        math: Top-level aggregation function.
        math_property: Property for property-based math.
        per_user: Per-user pre-aggregation.
        from_date: Start date (YYYY-MM-DD).
        to_date: End date (YYYY-MM-DD).
        last: Number of days for relative date range.
        has_formula: Whether any formula is present.
        rolling: Rolling window size.
        cumulative: Cumulative analysis mode.
        group_by: Breakdown specification.
        formulas: Resolved Formula objects (for expression validation).

    Returns:
        List of validation errors. Empty list means all arguments are valid.
    """
    errors: list[ValidationError] = []

    # V0: At least one event required
    if not events:
        errors.append(
            ValidationError(
                path="events",
                message="At least one event is required",
                code="V0_NO_EVENTS",
            )
        )

    # V17/V21/V22: Event validation — type, empty, control chars, invisible
    for idx, item in enumerate(events):
        epath = f"events[{idx}]"

        # V21: Type guard — must be str or Metric
        if not isinstance(item, (str, Metric)):
            errors.append(
                ValidationError(
                    path=epath,
                    message=(
                        f"Event must be a string or Metric, got {type(item).__name__}"
                    ),
                    code="V21_INVALID_EVENT_TYPE",
                )
            )
            continue

        name = item.event if isinstance(item, Metric) else item

        # V17: Non-empty after stripping whitespace
        if not name.strip():
            errors.append(
                ValidationError(
                    path=epath,
                    message="Event name must be a non-empty string",
                    code="V17_EMPTY_EVENT",
                )
            )
            continue

        # V22a: No control characters (null bytes, etc.)
        if _CONTROL_CHAR_RE.search(name):
            errors.append(
                ValidationError(
                    path=epath,
                    message=(
                        f"Event name contains control characters "
                        f"(e.g. null bytes): {name!r}"
                    ),
                    code="V22_CONTROL_CHAR_EVENT",
                )
            )

        # V22b: No invisible-only names (zero-width spaces, etc.)
        if _INVISIBLE_RE.match(name):
            errors.append(
                ValidationError(
                    path=epath,
                    message="Event name contains only invisible characters",
                    code="V22_INVISIBLE_EVENT",
                )
            )

    # V1: Property math requires property
    if math in MATH_REQUIRING_PROPERTY and math_property is None:
        errors.append(
            ValidationError(
                path="math",
                message=f"math='{math}' requires math_property to be set",
                code="V1_MATH_REQUIRES_PROPERTY",
            )
        )

    # V2: Non-property math rejects property
    if (
        math not in MATH_REQUIRING_PROPERTY
        and math not in MATH_PROPERTY_OPTIONAL
        and math_property is not None
    ):
        valid = sorted(MATH_REQUIRING_PROPERTY | MATH_PROPERTY_OPTIONAL)
        errors.append(
            ValidationError(
                path="math_property",
                message=(
                    f"math_property is only valid with property-based math types "
                    f"({', '.join(valid)}), not '{math}'"
                ),
                code="V2_MATH_REJECTS_PROPERTY",
            )
        )

    # V26: percentile math requires percentile_value
    if math == "percentile" and percentile_value is None:
        errors.append(
            ValidationError(
                path="percentile_value",
                message=("math='percentile' requires percentile_value to be set"),
                code="V26_PERCENTILE_REQUIRES_VALUE",
            )
        )

    # V27: histogram math requires per_user
    if math == "histogram" and per_user is None:
        errors.append(
            ValidationError(
                path="per_user",
                message=(
                    "math='histogram' requires per_user to be set "
                    "(e.g. per_user='total')"
                ),
                code="V27_HISTOGRAM_REQUIRES_PER_USER",
            )
        )

    # V3: per_user incompatible with DAU/WAU/MAU/unique
    if per_user is not None and math in MATH_NO_PER_USER:
        errors.append(
            ValidationError(
                path="per_user",
                message=f"per_user is incompatible with math='{math}'",
                code="V3_PER_USER_INCOMPATIBLE",
            )
        )

    # V3b: per_user requires a property
    if per_user is not None and math_property is None:
        errors.append(
            ValidationError(
                path="per_user",
                message="per_user requires math_property to be set",
                code="V3B_PER_USER_REQUIRES_PROPERTY",
            )
        )

    # V4: Formula requires 2+ events
    if has_formula and len(events) < 2:
        errors.append(
            ValidationError(
                path="formula",
                message=f"formula requires at least 2 events (got {len(events)})",
                code="V4_FORMULA_MIN_EVENTS",
            )
        )

    # V16/V19: Formula expression validation
    resolved = formulas or []
    for fi, f in enumerate(resolved):
        if isinstance(f, Formula):
            expr = f.expression
            fpath = f"formula[{fi}]" if len(resolved) > 1 else "formula"

            # V16: Formula must contain at least one position letter
            positions = set(_FORMULA_POSITION_RE.findall(expr))
            if not positions:
                errors.append(
                    ValidationError(
                        path=fpath,
                        message=(
                            f"Formula '{expr}' must reference at least one "
                            f"event position (A, B, C, ...)"
                        ),
                        code="V16_FORMULA_SYNTAX",
                    )
                )

            # V19: Position letters must not exceed event count
            if positions and events:
                max_letter = chr(ord("A") + len(events) - 1)
                out_of_bounds = {p for p in positions if p > max_letter}
                if out_of_bounds:
                    errors.append(
                        ValidationError(
                            path=fpath,
                            message=(
                                f"Formula references position(s) "
                                f"{sorted(out_of_bounds)} but only "
                                f"{len(events)} event(s) defined "
                                f"(A-{max_letter})"
                            ),
                            code="V19_FORMULA_BOUNDS",
                        )
                    )

    # V5: Rolling and cumulative are mutually exclusive
    if rolling is not None and cumulative:
        errors.append(
            ValidationError(
                path="rolling",
                message="rolling and cumulative are mutually exclusive",
                code="V5_ROLLING_CUMULATIVE_EXCLUSIVE",
            )
        )

    # V6: Rolling must be positive
    if rolling is not None and rolling <= 0:
        errors.append(
            ValidationError(
                path="rolling",
                message="rolling must be a positive integer",
                code="V6_ROLLING_POSITIVE",
            )
        )

    # V23: Rolling window sanity cap
    if rolling is not None and rolling > _MAX_ROLLING:
        errors.append(
            ValidationError(
                path="rolling",
                message=(
                    f"rolling={rolling} exceeds maximum of {_MAX_ROLLING} periods"
                ),
                code="V23_ROLLING_TOO_LARGE",
            )
        )

    # V7-V10, V15, V20: Time argument validation (delegated)
    errors.extend(validate_time_args(from_date=from_date, to_date=to_date, last=last))

    # V11-V12, V18, V24: GroupBy validation (delegated)
    errors.extend(validate_group_by_args(group_by=group_by))

    # V13-V14: Per-Metric validation
    for idx, item in enumerate(events):
        if isinstance(item, Metric):
            mpath = f"events[{idx}]"
            m_math = item.math
            m_prop = item.property
            m_per_user = item.per_user

            if m_math in MATH_REQUIRING_PROPERTY and m_prop is None:
                errors.append(
                    ValidationError(
                        path=mpath,
                        message=(
                            f"Metric('{item.event}'): math='{m_math}' "
                            f"requires property to be set"
                        ),
                        code="V13_METRIC_MATH_PROPERTY",
                    )
                )

            if (
                m_math not in MATH_REQUIRING_PROPERTY
                and m_math not in MATH_PROPERTY_OPTIONAL
                and m_prop is not None
            ):
                valid = sorted(MATH_REQUIRING_PROPERTY | MATH_PROPERTY_OPTIONAL)
                errors.append(
                    ValidationError(
                        path=mpath,
                        message=(
                            f"Metric('{item.event}'): property is only valid with "
                            f"property-based math types "
                            f"({', '.join(valid)}), not '{m_math}'"
                        ),
                        code="V14_METRIC_REJECTS_PROPERTY",
                    )
                )

            # V27: Per-Metric histogram requires per_user
            if m_math == "histogram" and m_per_user is None:
                errors.append(
                    ValidationError(
                        path=mpath,
                        message=(
                            f"Metric('{item.event}'): math='histogram' "
                            f"requires per_user to be set "
                            f"(e.g. per_user='total')"
                        ),
                        code="V27_HISTOGRAM_REQUIRES_PER_USER",
                    )
                )

            # V26: Per-Metric percentile requires percentile_value
            if m_math == "percentile" and item.percentile_value is None:
                errors.append(
                    ValidationError(
                        path=mpath,
                        message=(
                            f"Metric('{item.event}'): math='percentile' "
                            f"requires percentile_value to be set"
                        ),
                        code="V26_PERCENTILE_REQUIRES_VALUE",
                    )
                )

            if m_per_user is not None and m_math in MATH_NO_PER_USER:
                errors.append(
                    ValidationError(
                        path=mpath,
                        message=(
                            f"Metric('{item.event}'): per_user is incompatible "
                            f"with math='{m_math}'"
                        ),
                        code="V3_PER_USER_INCOMPATIBLE",
                    )
                )

            if m_per_user is not None and m_prop is None:
                errors.append(
                    ValidationError(
                        path=mpath,
                        message=(
                            f"Metric('{item.event}'): per_user requires "
                            f"property to be set"
                        ),
                        code="V3B_PER_USER_REQUIRES_PROPERTY",
                    )
                )

    return errors


# =============================================================================
# Layer 2: Bookmark Structure Validation (B1-B19)
# =============================================================================


def validate_bookmark(
    params: dict[str, Any],
    *,
    bookmark_type: str = "insights",
) -> list[ValidationError]:
    """Validate bookmark params dict after construction (Layer 2).

    Validates the structural integrity and enum values of a built
    bookmark params dict before it is sent to the Mixpanel API.
    Returns all errors found so callers can fix multiple issues at once.

    Args:
        params: The bookmark params dict (with ``sections`` and
            ``displayOptions`` keys).
        bookmark_type: The bookmark type context. Default ``"insights"``.
            Affects which math types are considered valid.

    Returns:
        List of validation errors. Empty list means the bookmark is valid.

    Example:
        ```python
        from mixpanel_data._internal.validation import validate_bookmark

        errors = validate_bookmark(my_params)
        if errors:
            for e in errors:
                print(e)
        ```
    """
    errors: list[ValidationError] = []

    # B1: Required top-level field: sections
    if "sections" not in params:
        errors.append(
            ValidationError(
                path="params",
                message="Missing required field 'sections'",
                code="B1_MISSING_SECTIONS",
            )
        )

    # B2: Required top-level field: displayOptions
    if "displayOptions" not in params:
        errors.append(
            ValidationError(
                path="params",
                message="Missing required field 'displayOptions'",
                code="B2_MISSING_DISPLAY_OPTIONS",
            )
        )

    # Can't validate further without sections
    if "sections" not in params:
        return errors

    sections = params["sections"]
    if not isinstance(sections, dict):
        errors.append(
            ValidationError(
                path="sections",
                message="'sections' must be a dict",
                code="B1_MISSING_SECTIONS",
            )
        )
        return errors

    # B3: Required sections field: show
    show = sections.get("show")
    if show is None:
        errors.append(
            ValidationError(
                path="sections",
                message="Missing required field 'show'",
                code="B3_MISSING_SHOW",
            )
        )
    elif not isinstance(show, list) or len(show) == 0:
        # B4: show must be non-empty list
        errors.append(
            ValidationError(
                path="sections.show",
                message="'show' must be a non-empty list",
                code="B4_SHOW_EMPTY",
            )
        )
    else:
        for i, clause in enumerate(show):
            errors.extend(_validate_show_clause(clause, i, bookmark_type))

    # Validate displayOptions
    display = params.get("displayOptions")
    if isinstance(display, dict):
        errors.extend(_validate_display_options(display))

    # Validate time section
    time_section = sections.get("time")
    if isinstance(time_section, list):
        for i, t in enumerate(time_section):
            errors.extend(_validate_time_clause(t, i))

    # Validate filter section
    filter_section = sections.get("filter")
    if isinstance(filter_section, list):
        for i, f in enumerate(filter_section):
            errors.extend(_validate_filter_clause(f, f"sections.filter[{i}]"))

    # Validate group section
    group_section = sections.get("group")
    if isinstance(group_section, list):
        for i, g in enumerate(group_section):
            errors.extend(_validate_group_clause(g, i))

    return errors


# =============================================================================
# Layer 2: Sub-validators
# =============================================================================


def _validate_show_clause(
    clause: dict[str, Any],
    index: int,
    bookmark_type: str,
) -> list[ValidationError]:
    """Validate a single sections.show[] entry.

    Handles both multi-metric (behavior+measurement) and formula show clauses.

    Args:
        clause: The show clause dict.
        index: Index in the show array.
        bookmark_type: Context for math type validation.

    Returns:
        List of validation errors for this clause.
    """
    errors: list[ValidationError] = []
    path = f"sections.show[{index}]"

    if not isinstance(clause, dict):
        errors.append(
            ValidationError(
                path=path,
                message="Show clause must be a dict",
                code="B6_MISSING_BEHAVIOR",
            )
        )
        return errors

    # Formula show clause — minimal validation
    if "formula" in clause or clause.get("type") == "formula":
        return errors

    # Multi-metric show clause: requires behavior
    behavior = clause.get("behavior")
    if behavior is None:
        # B6: Missing behavior
        errors.append(
            ValidationError(
                path=path,
                message="Show clause missing 'behavior'",
                code="B6_MISSING_BEHAVIOR",
            )
        )
        return errors

    if not isinstance(behavior, dict):
        errors.append(
            ValidationError(
                path=f"{path}.behavior",
                message="'behavior' must be a dict",
                code="B6_MISSING_BEHAVIOR",
            )
        )
        return errors

    # B7: Validate behavior.type
    btype = behavior.get("type")
    if btype is not None and btype not in VALID_METRIC_TYPES:
        errors.append(
            _enum_error(
                path=f"{path}.behavior.type",
                field="behavior type",
                value=str(btype),
                valid=VALID_METRIC_TYPES,
                code="B7_INVALID_BEHAVIOR_TYPE",
                severity="warning",
            )
        )

    # B8: Event behaviors need a name
    if btype in ("event", "simple", "custom-event"):
        value = behavior.get("value", {})
        has_name = (
            isinstance(value, dict) and value.get("name") is not None
        ) or behavior.get("name") is not None
        if not has_name:
            errors.append(
                ValidationError(
                    path=f"{path}.behavior",
                    message="Event behavior requires a 'name'",
                    code="B8_MISSING_EVENT_NAME",
                    fix={"value": {"name": "<EVENT_NAME>"}},
                )
            )

    # B19: Validate filtersDeterminer
    fd = behavior.get("filtersDeterminer")
    if fd is not None and fd not in VALID_FILTERS_DETERMINER:
        errors.append(
            _enum_error(
                path=f"{path}.behavior.filtersDeterminer",
                field="filtersDeterminer",
                value=str(fd),
                valid=VALID_FILTERS_DETERMINER,
                code="B19_INVALID_FILTERS_DETERMINER",
                severity="warning",
            )
        )

    # Validate per-metric behavior.filters[]
    bfilters = behavior.get("filters")
    if isinstance(bfilters, list):
        for fi, bf in enumerate(bfilters):
            errors.extend(_validate_filter_clause(bf, f"{path}.behavior.filters[{fi}]"))

    # Validate measurement
    measurement = clause.get("measurement")
    if isinstance(measurement, dict):
        errors.extend(_validate_measurement(measurement, path, bookmark_type))

    return errors


def _validate_measurement(
    measurement: dict[str, Any],
    show_path: str,
    bookmark_type: str = "insights",
) -> list[ValidationError]:
    """Validate a measurement block within a show clause.

    Args:
        measurement: The measurement dict.
        show_path: Parent show clause path for error reporting.
        bookmark_type: Context for math type validation. When
            ``"funnels"``, validates against funnel-specific math types;
            defaults to insights math types otherwise.

    Returns:
        List of validation errors for this measurement.
    """
    errors: list[ValidationError] = []
    path = f"{show_path}.measurement"

    # B9: Validate math type (context-dependent for funnel/retention)
    math = measurement.get("math")
    if math is not None:
        valid_math = (
            VALID_MATH_FUNNELS if bookmark_type == "funnels" else VALID_MATH_INSIGHTS
        )
        if math not in valid_math:
            errors.append(
                _enum_error(
                    path=f"{path}.math",
                    field="math",
                    value=str(math),
                    valid=valid_math,
                    code="B9_INVALID_MATH",
                )
            )

        # B10: Math requiring property
        if math in MATH_REQUIRING_PROPERTY and measurement.get("property") is None:
            errors.append(
                ValidationError(
                    path=f"{path}.property",
                    message=f"Math type '{math}' requires 'measurement.property'",
                    code="B10_MATH_MISSING_PROPERTY",
                    severity="warning",
                    fix={
                        "name": "<PROPERTY_NAME>",
                        "type": "number",
                        "resourceType": "events",
                    },
                )
            )

    # B11: Validate perUserAggregation
    per_user = measurement.get("perUserAggregation")
    if per_user is not None and per_user not in VALID_PER_USER_AGGREGATIONS:
        errors.append(
            _enum_error(
                path=f"{path}.perUserAggregation",
                field="perUserAggregation",
                value=str(per_user),
                valid=VALID_PER_USER_AGGREGATIONS,
                code="B11_INVALID_PER_USER",
            )
        )

    # Validate measurement.property if present
    prop = measurement.get("property")
    if isinstance(prop, dict):
        prop_type = prop.get("type")
        if prop_type is not None and prop_type not in VALID_PROPERTY_TYPES:
            errors.append(
                _enum_error(
                    path=f"{path}.property.type",
                    field="property type",
                    value=str(prop_type),
                    valid=VALID_PROPERTY_TYPES,
                    code="B17_INVALID_PROPERTY_TYPE",
                    severity="warning",
                )
            )
        prop_rt = prop.get("resourceType")
        if prop_rt is not None and prop_rt not in VALID_RESOURCE_TYPES:
            errors.append(
                _enum_error(
                    path=f"{path}.property.resourceType",
                    field="resourceType",
                    value=str(prop_rt),
                    valid=VALID_RESOURCE_TYPES,
                    code="B16_INVALID_RESOURCE_TYPE",
                    severity="warning",
                )
            )

    return errors


def _validate_display_options(
    display: dict[str, Any],
) -> list[ValidationError]:
    """Validate the displayOptions block.

    Args:
        display: The displayOptions dict.

    Returns:
        List of validation errors.
    """
    errors: list[ValidationError] = []

    # B5: chartType is required and must be valid
    chart_type = display.get("chartType")
    if chart_type is None:
        errors.append(
            ValidationError(
                path="displayOptions",
                message="Missing required 'chartType'",
                code="B5_INVALID_CHART_TYPE",
            )
        )
    elif chart_type not in VALID_CHART_TYPES:
        errors.append(
            _enum_error(
                path="displayOptions.chartType",
                field="chartType",
                value=str(chart_type),
                valid=VALID_CHART_TYPES,
                code="B5_INVALID_CHART_TYPE",
            )
        )

    return errors


def _validate_time_clause(
    clause: Any,
    index: int,
) -> list[ValidationError]:
    """Validate a single sections.time[] entry.

    Args:
        clause: The time clause (expected to be a dict).
        index: Index in the time array.

    Returns:
        List of validation errors for this clause.
    """
    errors: list[ValidationError] = []
    path = f"sections.time[{index}]"

    if not isinstance(clause, dict):
        errors.append(
            ValidationError(
                path=path,
                message="Time clause must be a dict",
                code="B12_INVALID_TIME_UNIT",
            )
        )
        return errors

    # B12: Validate unit
    unit = clause.get("unit")
    if unit is not None and unit not in VALID_TIME_UNITS:
        errors.append(
            _enum_error(
                path=f"{path}.unit",
                field="time unit",
                value=str(unit),
                valid=VALID_TIME_UNITS,
                code="B12_INVALID_TIME_UNIT",
            )
        )

    # B13: Validate dateRangeType
    drt = clause.get("dateRangeType")
    if drt is not None and drt not in {
        "in the last",
        "between",
        "since",
        "on",
        "relative_after",
    }:
        errors.append(
            ValidationError(
                path=f"{path}.dateRangeType",
                message=f"Invalid dateRangeType '{drt}'",
                code="B13_INVALID_DATE_RANGE_TYPE",
                severity="warning",
            )
        )

    return errors


def _validate_filter_clause(
    clause: Any,
    path: str,
) -> list[ValidationError]:
    """Validate a single filter clause.

    Args:
        clause: The filter clause (expected to be a dict).
        path: JSONPath-like location for error reporting.

    Returns:
        List of validation errors for this clause.
    """
    errors: list[ValidationError] = []

    if not isinstance(clause, dict):
        errors.append(
            ValidationError(
                path=path,
                message="Filter clause must be a dict",
                code="B14_INVALID_FILTER_TYPE",
            )
        )
        return errors

    # B18: Must have property identification
    if not clause.get("value") and not clause.get("propertyName"):
        errors.append(
            ValidationError(
                path=path,
                message="Filter missing property identifier ('value' or 'propertyName')",
                code="B18_MISSING_FILTER_PROPERTY",
            )
        )

    # B16: Validate resourceType
    rt = clause.get("resourceType")
    if rt is not None and rt not in VALID_RESOURCE_TYPES:
        errors.append(
            _enum_error(
                path=f"{path}.resourceType",
                field="resourceType",
                value=str(rt),
                valid=VALID_RESOURCE_TYPES,
                code="B16_INVALID_RESOURCE_TYPE",
                severity="warning",
            )
        )

    # B14: Validate filterType
    ft = clause.get("filterType")
    if ft is not None and ft not in VALID_PROPERTY_TYPES:
        errors.append(
            _enum_error(
                path=f"{path}.filterType",
                field="filterType",
                value=str(ft),
                valid=VALID_PROPERTY_TYPES,
                code="B14_INVALID_FILTER_TYPE",
            )
        )

    # B15: Validate filterOperator
    fo = clause.get("filterOperator")
    if fo is not None and fo not in VALID_FILTER_OPERATORS:
        errors.append(
            _enum_error(
                path=f"{path}.filterOperator",
                field="filterOperator",
                value=str(fo),
                valid=VALID_FILTER_OPERATORS,
                code="B15_INVALID_FILTER_OPERATOR",
                severity="warning",
            )
        )

    return errors


def _validate_group_clause(
    clause: Any,
    index: int,
) -> list[ValidationError]:
    """Validate a single sections.group[] entry.

    Args:
        clause: The group clause (expected to be a dict).
        index: Index in the group array.

    Returns:
        List of validation errors for this clause.
    """
    errors: list[ValidationError] = []
    path = f"sections.group[{index}]"

    if not isinstance(clause, dict):
        errors.append(
            ValidationError(
                path=path,
                message="Group clause must be a dict",
                code="B17_INVALID_PROPERTY_TYPE",
            )
        )
        return errors

    # B17: Validate propertyType
    pt = clause.get("propertyType")
    if pt is not None and pt not in VALID_PROPERTY_TYPES:
        errors.append(
            _enum_error(
                path=f"{path}.propertyType",
                field="propertyType",
                value=str(pt),
                valid=VALID_PROPERTY_TYPES,
                code="B17_INVALID_PROPERTY_TYPE",
                severity="warning",
            )
        )

    # B16: Validate resourceType
    rt = clause.get("resourceType")
    if rt is not None and rt not in VALID_RESOURCE_TYPES:
        errors.append(
            _enum_error(
                path=f"{path}.resourceType",
                field="resourceType",
                value=str(rt),
                valid=VALID_RESOURCE_TYPES,
                code="B16_INVALID_RESOURCE_TYPE",
                severity="warning",
            )
        )

    return errors
