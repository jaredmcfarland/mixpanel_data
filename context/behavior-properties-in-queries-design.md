# Behavior-Based Custom Properties in Queries — v2 Supplement

**Date**: 2026-04-06
**Status**: Design Complete — Ready for TDD Implementation
**Prerequisite**: `custom-properties-in-queries-design.md` (v1) must be implemented first
**Reference**: `analytics/backend/util/behaviors/count.py`, `analytics/backend/util/arb_selector.py`

---

## 1. Scope & Goals

### What This Document Covers

Extension of the custom properties query system (v1) to support **behavior-based custom properties** — virtual computed properties that aggregate a user's event history over a time window. These can be defined **inline** (ad-hoc, per-query) or **referenced by ID** (saved via `create_custom_property()`).

Behavior properties answer questions like:
- "How many purchases has each user made in the last 30 days?"
- "What is each user's average order value this month?"
- "What browser does each user use most frequently?"
- "When did each user first perform this event?"

They can appear in the same three positions as formula-based custom properties:
1. **Breakdown** (`group_by=`) — Segment by a behavioral metric
2. **Filter** (`where=`) — Filter to users whose behavior meets a threshold
3. **Metric measurement** (`Metric.property=`) — Aggregate on a behavioral metric

### What This Document Does NOT Cover

- Multi-attribution models (`multi_attribution` aggregation) — extremely complex config with 10+ attribution types, weights, and offset semantics. Users can create these via `create_custom_property()` and reference by ID.
- Slowly-changing dimension properties (`scd_value`) — internal/specialized
- Session replay properties (`session_replay_id_value`) — internal
- Borrowed properties — these are formula-based CPs with a synthetic behavior at query time; already coverable via `CustomPropertyRef`
- Flows query support — flows don't support custom properties in breakdowns

### Design Principles

Same as v1, plus:
- **Consistent with formula CPs** — Same union-typed positions, same builder dispatch pattern
- **Mirrors Mixpanel UI** — Exposes the same 5 aggregation operators the UI shows, plus 5 additional useful operators
- **Inferred output types** — Output type is auto-inferred from aggregation operator (matching server behavior), with explicit override available

---

## 2. How Behavior Properties Work

### 2.1 Conceptual Model

A behavior property performs a **per-user aggregation** over an event stream within a time window. At query time, for each user (or each row), the engine:

1. Finds all events matching `event` name + `filters` within `dateRange`
2. Applies the `aggregation` operator to those events (optionally on a specific `property`)
3. Returns the computed value as a virtual property

This is fundamentally different from formula-based CPs, which operate on the current event's properties:

| Aspect | Formula CP (v1) | Behavior CP (v2) |
|--------|----------------|------------------|
| Input | Current event's properties | A user's event history |
| Operation | Per-event computation | Per-user aggregation |
| Time dimension | None | Has a lookback window |
| SQL analogy | `SELECT price * qty` | `SELECT (SELECT COUNT(*) FROM events WHERE ...)` |
| Example | `"price * quantity"` | `"Total purchases in last 30 days"` |

### 2.2 Query-Time Resolution

```
BehaviorProperty in bookmark params
    ↓
segment_to_arb_selector() detects customProperty.behavior
    ↓
_raw_behavior_to_arb_selector():
  1. Parse dateRange → DateRange object
  2. Create EventSelector from event + filters
  3. Register CohortCountBehavior in QueryBehaviors
  4. Return selector: behaviors["beh_<sha256_hash>"]
    ↓
ARB query engine executes the behavior aggregation
    ↓
Result: computed value per user/row
```

### 2.3 Aggregation Operators

The Mixpanel backend defines aggregation operators in `_per_user_agg_info` (`count.py:84-117`). The v2 scope covers 10 of these:

**Tier 1 — UI-exposed (the 5 operators shown in the Mixpanel custom property modal):**

| Operator | ARB Action | Output Type | Requires Property? | Description |
|----------|-----------|-------------|-------------------|-------------|
| `"total"` | `per_user_count` or `per_user_sum` | `"number"` | No (count) / Yes (sum) | Without property: count of matching events. With property: sum of property values. |
| `"average"` | `per_user_average` | `"number"` | Yes | Average of property values per user |
| `"unique_values"` | `per_user_count_unique` | `"number"` | Yes | Count of distinct property values per user |
| `"most_frequent"` | `per_user_most_frequent` | `"string"` | Yes | Most common property value per user |
| `"first_value"` | `per_user_first_value` | `"string"` | Yes | Value from the user's earliest matching event |

**Tier 2 — Additional useful operators:**

| Operator | ARB Action | Output Type | Requires Property? | Description |
|----------|-----------|-------------|-------------------|-------------|
| `"min"` | `per_user_min` | `"number"` | Yes | Minimum property value per user |
| `"max"` | `per_user_max` | `"number"` | Yes | Maximum property value per user |
| `"last_value"` | `per_user_last_value` | `"string"` | Yes | Value from the user's most recent matching event |
| `"first_event_time"` | `per_user_first_event_time` | `"number"` | No | Timestamp of user's first matching event |
| `"last_event_time"` | `per_user_last_event_time` | `"number"` | No | Timestamp of user's last matching event |

**Output type inference** (mirrors `_behavior_type()` in `views.py:278-283`):
```python
def _infer_behavior_output_type(aggregation: str) -> str:
    return "string" if aggregation in {"most_frequent", "first_value"} else "number"
```

Note: `last_value` returns `"number"` per the server's inference function, not `"string"`. This is a server-side simplification; the actual output type depends on the input property type. Users can override via `property_type`.

### 2.4 Date Range Formats

The behavior's `dateRange` supports three shapes:

| Mode | JSON Shape | User API |
|------|-----------|----------|
| **Relative** (default) | `{"type": "in the last", "window": {"unit": "day", "value": 30}}` | `last=30, last_unit="day"` |
| **Absolute** | `{"type": "between", "from": "2024-01-01", "to": "2024-12-31"}` | `from_date="2024-01-01", to_date="2024-12-31"` |
| **Since** | `{"type": "since", "from": "2024-01-01"}` | `since="2024-01-01"` |

Valid `last_unit` values: `"day"`, `"week"`, `"month"` (backend also supports `"minute"`, `"hour"`, `"quarter"`, `"year"` but these are uncommon for behavior CPs).

---

## 3. New Types

### 3.1 `BehaviorAggregation` — Type Alias

```python
BehaviorAggregation = Literal[
    # Tier 1: UI-exposed
    "total",            # Count of events (or sum if property set)
    "average",          # Average of property per user
    "unique_values",    # Count of distinct property values per user
    "most_frequent",    # Most common property value → string
    "first_value",      # First value seen → string

    # Tier 2: Additional useful operators
    "min",              # Minimum property value per user
    "max",              # Maximum property value per user
    "last_value",       # Last value seen
    "first_event_time", # Timestamp of first matching event
    "last_event_time",  # Timestamp of last matching event
]
"""Valid aggregation operators for behavior-based custom properties."""
```

**Operators that require a `property` field:**
```python
BEHAVIOR_PROPERTY_REQUIRED: frozenset[str] = frozenset({
    "average", "min", "max", "unique_values",
    "most_frequent", "first_value", "last_value",
})
"""Aggregation operators that require a property field."""
```

**Operators that never use a `property` field:**
```python
BEHAVIOR_NO_PROPERTY: frozenset[str] = frozenset({
    "first_event_time", "last_event_time",
})
"""Aggregation operators where property is not applicable."""
```

**Operators that optionally use a `property` field:**
- `"total"` — Without property: count of events. With property: sum of property values.

### 3.2 `BehaviorDateRange` — Type Alias

```python
BehaviorDateRangeUnit = Literal["day", "week", "month"]
"""Valid time units for behavior property lookback windows."""
```

### 3.3 `BehaviorProperty` — The Main Type

```python
@dataclass(frozen=True)
class BehaviorProperty:
    """A behavior-based custom property that aggregates a user's event history.

    Computes a virtual property by aggregating events matching the
    specified criteria over a time window. For each user (or row),
    the query engine finds matching events, applies the aggregation
    operator, and returns the computed value.

    This is a first-class Mixpanel feature — the query engine natively
    supports inline behavior-based custom property definitions in
    bookmark params.

    Attributes:
        event: Event name to aggregate. Only events with this name
            are included in the aggregation.
        aggregation: How to aggregate the matching events. See
            ``BehaviorAggregation`` for all valid values and their
            semantics.
        property: Property to aggregate on. Required for operators like
            ``"average"``, ``"most_frequent"``, ``"first_value"``.
            Optional for ``"total"`` (without property = event count;
            with property = sum of property values). Not applicable
            for ``"first_event_time"`` and ``"last_event_time"``.
        property_type: Data type of the aggregation property.
            Required when ``property`` is set. Default ``"number"``.
        last: Relative lookback window size. Used when ``from_date``
            is not set. Default 30.
        last_unit: Time unit for the lookback window.
            Default ``"day"``.
        from_date: Absolute start date (YYYY-MM-DD). When set with
            ``to_date``, uses an absolute date range instead of
            relative lookback.
        to_date: Absolute end date (YYYY-MM-DD). Required if
            ``from_date`` is set.
        since: Start date for "since" range (YYYY-MM-DD). Aggregates
            from this date to now. Mutually exclusive with
            ``from_date``/``to_date`` and ``last``.
        filters: Optional filters on the events within the behavior.
            Only events passing these filters are included in the
            aggregation. Reuses the same ``Filter`` type as query
            filters.
        filters_combinator: How behavior filters combine.
            ``"all"`` = AND logic, ``"any"`` = OR logic. Default
            ``"all"``.
        property_type_override: Explicit output type override. If
            ``None``, inferred from ``aggregation`` (``"string"``
            for most_frequent/first_value, ``"number"`` for others).
            Use when the inferred type doesn't match your needs.
        resource_type: Which data domain. Default ``"events"``.

    Examples:
        ```python
        # Count of purchases in the last 30 days
        BehaviorProperty(
            event="Purchase",
            aggregation="total",
        )

        # Average order value in the last 90 days
        BehaviorProperty(
            event="Purchase",
            aggregation="average",
            property="amount",
            property_type="number",
            last=90,
        )

        # Most frequently used browser
        BehaviorProperty(
            event="Page View",
            aggregation="most_frequent",
            property="$browser",
            property_type="string",
        )

        # When the user first signed up
        BehaviorProperty(
            event="Signup",
            aggregation="first_event_time",
            since="2020-01-01",
        )

        # Total spend in Q1 2024
        BehaviorProperty(
            event="Purchase",
            aggregation="total",
            property="amount",
            property_type="number",
            from_date="2024-01-01",
            to_date="2024-03-31",
        )

        # Users with more than 5 logins this week
        BehaviorProperty(
            event="Login",
            aggregation="total",
            last=7,
            last_unit="day",
        )

        # Total purchases of premium items only
        BehaviorProperty(
            event="Purchase",
            aggregation="total",
            filters=[Filter.equals("plan", "premium")],
        )
        ```
    """

    event: str
    aggregation: BehaviorAggregation
    property: str | None = None
    property_type: Literal["string", "number", "boolean", "datetime"] = "number"
    last: int = 30
    last_unit: BehaviorDateRangeUnit = "day"
    from_date: str | None = None
    to_date: str | None = None
    since: str | None = None
    filters: list[Filter] | None = None
    filters_combinator: Literal["all", "any"] = "all"
    property_type_override: Literal["string", "number", "boolean", "datetime"] | None = None
    resource_type: Literal["events", "people"] = "events"

    @property
    def output_type(self) -> str:
        """Infer the output type of this behavior property.

        Returns ``property_type_override`` if set, otherwise infers
        from the aggregation operator:
        - ``"string"`` for ``most_frequent`` and ``first_value``
        - ``"number"`` for everything else

        Returns:
            The effective output type string.
        """
        if self.property_type_override is not None:
            return self.property_type_override
        if self.aggregation in ("most_frequent", "first_value"):
            return "string"
        return "number"
```

**Convenience constructors:**

```python
    @classmethod
    def count(
        cls,
        event: str,
        *,
        last: int = 30,
        last_unit: BehaviorDateRangeUnit = "day",
        filters: list[Filter] | None = None,
    ) -> BehaviorProperty:
        """Count of events per user (most common use case).

        Shorthand for ``BehaviorProperty(event, aggregation="total")``.

        Args:
            event: Event name to count.
            last: Lookback window. Default 30.
            last_unit: Window unit. Default ``"day"``.
            filters: Optional event filters.

        Returns:
            A BehaviorProperty counting event occurrences.

        Examples:
            ```python
            BehaviorProperty.count("Login")
            BehaviorProperty.count("Purchase", last=90)
            BehaviorProperty.count("Login", filters=[
                Filter.equals("platform", "iOS"),
            ])
            ```
        """
        return cls(
            event=event,
            aggregation="total",
            last=last,
            last_unit=last_unit,
            filters=filters,
        )

    @classmethod
    def aggregate(
        cls,
        event: str,
        aggregation: BehaviorAggregation,
        property: str,
        *,
        property_type: Literal["string", "number", "boolean", "datetime"] = "number",
        last: int = 30,
        last_unit: BehaviorDateRangeUnit = "day",
        filters: list[Filter] | None = None,
    ) -> BehaviorProperty:
        """Aggregate a property across a user's events.

        Shorthand for common property aggregations. Use this when you
        need to aggregate a specific property (average, sum, min, max,
        etc.).

        Args:
            event: Event name.
            aggregation: Aggregation operator.
            property: Property to aggregate.
            property_type: Property data type. Default ``"number"``.
            last: Lookback window. Default 30.
            last_unit: Window unit. Default ``"day"``.
            filters: Optional event filters.

        Returns:
            A BehaviorProperty aggregating the specified property.

        Examples:
            ```python
            # Average order value
            BehaviorProperty.aggregate(
                "Purchase", "average", "amount",
            )

            # Most used browser
            BehaviorProperty.aggregate(
                "Page View", "most_frequent", "$browser",
                property_type="string",
            )
            ```
        """
        return cls(
            event=event,
            aggregation=aggregation,
            property=property,
            property_type=property_type,
            last=last,
            last_unit=last_unit,
            filters=filters,
        )
```

---

## 4. Modified Types — Exact Diffs

### 4.1 `PropertySpec` Type Alias

**Before** (from v1):
```python
PropertySpec = str | CustomPropertyRef | InlineCustomProperty
```

**After**:
```python
PropertySpec = str | CustomPropertyRef | InlineCustomProperty | BehaviorProperty
"""A property specifier: plain name, saved CP ref, inline formula, or behavioral aggregation."""
```

### 4.2 `Metric.property`

**Before** (from v1):
```python
property: str | CustomPropertyRef | InlineCustomProperty | None = None
```

**After**:
```python
property: str | CustomPropertyRef | InlineCustomProperty | BehaviorProperty | None = None
```

### 4.3 `GroupBy.property`

**Before** (from v1):
```python
property: str | CustomPropertyRef | InlineCustomProperty
```

**After**:
```python
property: str | CustomPropertyRef | InlineCustomProperty | BehaviorProperty
```

### 4.4 `Filter._property` and Class Methods

**Before** (from v1):
```python
_property: str | CustomPropertyRef | InlineCustomProperty
```

**After**:
```python
_property: str | CustomPropertyRef | InlineCustomProperty | BehaviorProperty
```

All 18 class method `property` parameters expand accordingly.

---

## 5. Builder Changes — Exact Specifications

### 5.1 Shared Helper — `_build_behavior_dict()`

**File**: `src/mixpanel_data/_internal/bookmark_builders.py` (new function)

```python
def _build_behavior_dict(bp: BehaviorProperty) -> dict[str, Any]:
    """Convert a BehaviorProperty to the bookmark behavior JSON format.

    Produces the ``behavior`` dict that goes inside a
    ``customProperty`` definition. Handles date range construction,
    property specification, and filter conversion.

    Args:
        bp: A ``BehaviorProperty`` specification.

    Returns:
        Behavior dict ready for embedding in ``customProperty``.

    Example:
        ```python
        result = _build_behavior_dict(BehaviorProperty(
            event="Purchase", aggregation="total", last=30,
        ))
        # {"event": {"value": "Purchase"}, "aggregationOperator": "total",
        #  "dateRange": {"type": "in the last", "window": {"unit": "day", "value": 30}},
        #  "filters": [], "filtersOperator": "and", "property": null}
        ```
    """
    # Build event reference
    event_ref: dict[str, Any] = {"value": bp.event}

    # Build date range
    if bp.from_date is not None and bp.to_date is not None:
        date_range: dict[str, Any] = {
            "type": "between",
            "from": bp.from_date,
            "to": bp.to_date,
        }
    elif bp.since is not None:
        date_range = {
            "type": "since",
            "from": bp.since,
        }
    else:
        date_range = {
            "type": "in the last",
            "window": {"unit": bp.last_unit, "value": bp.last},
        }

    # Build property reference (if applicable)
    prop_ref: dict[str, Any] | None = None
    if bp.property is not None:
        prop_ref = {
            "value": bp.property,
            "type": bp.property_type,
            "resourceType": "event",
        }

    # Build filters
    behavior_filters: list[dict[str, Any]] = []
    if bp.filters:
        behavior_filters = [build_filter_entry(f) for f in bp.filters]

    # Map combinator
    filters_operator = "and" if bp.filters_combinator == "all" else "or"

    return {
        "event": event_ref,
        "aggregationOperator": bp.aggregation,
        "dateRange": date_range,
        "filters": behavior_filters,
        "filtersOperator": filters_operator,
        "property": prop_ref,
    }
```

### 5.2 `build_filter_entry()` — Add BehaviorProperty Branch

**Addition to the existing function** (after the `InlineCustomProperty` branch from v1):

```python
elif isinstance(prop, BehaviorProperty):
    output_type = prop.output_type
    entry["customProperty"] = {
        "behavior": _build_behavior_dict(prop),
        "propertyType": output_type,
        "resourceType": prop.resource_type,
    }
    entry["filterType"] = output_type
    entry["defaultType"] = output_type
    entry["resourceType"] = prop.resource_type
```

**Bookmark JSON output — `BehaviorProperty` in filter**:
```json
{
    "customProperty": {
        "behavior": {
            "event": {"value": "Purchase"},
            "aggregationOperator": "total",
            "dateRange": {"type": "in the last", "window": {"unit": "day", "value": 30}},
            "filters": [],
            "filtersOperator": "and",
            "property": null
        },
        "propertyType": "number",
        "resourceType": "events"
    },
    "resourceType": "events",
    "filterType": "number",
    "defaultType": "number",
    "filterValue": 5,
    "filterOperator": "is greater than"
}
```

### 5.3 `build_group_section()` — Add BehaviorProperty Branch

**Addition to the existing function** (after the `InlineCustomProperty` branch from v1):

```python
elif isinstance(prop, BehaviorProperty):
    output_type = prop.output_type
    group_entry = {
        "customProperty": {
            "behavior": _build_behavior_dict(prop),
            "propertyType": output_type,
            "resourceType": prop.resource_type,
        },
        "propertyType": output_type,
        "propertyDefaultType": output_type,
        "isHidden": False,
    }
```

**Bookmark JSON output — `BehaviorProperty` in group_by with bucketing**:
```json
{
    "customProperty": {
        "behavior": {
            "event": {"value": "Purchase"},
            "aggregationOperator": "total",
            "dateRange": {"type": "in the last", "window": {"unit": "day", "value": 30}},
            "filters": [],
            "filtersOperator": "and",
            "property": null
        },
        "propertyType": "number",
        "resourceType": "events"
    },
    "propertyType": "number",
    "propertyDefaultType": "number",
    "isHidden": false,
    "customBucket": {"bucketSize": 5, "min": 0, "max": 50}
}
```

### 5.4 Measurement Property — Add BehaviorProperty Branch

**Addition to `_build_query_params()` and `_build_funnel_params()`** (after the `InlineCustomProperty` branch from v1):

```python
elif isinstance(item_prop, BehaviorProperty):
    measurement["property"] = {
        "customProperty": {
            "behavior": _build_behavior_dict(item_prop),
            "propertyType": item_prop.output_type,
        },
        "resourceType": item_prop.resource_type,
    }
```

**Bookmark JSON output — `BehaviorProperty` in measurement**:
```json
{
    "math": "average",
    "property": {
        "customProperty": {
            "behavior": {
                "event": {"value": "Purchase"},
                "aggregationOperator": "total",
                "dateRange": {"type": "in the last", "window": {"unit": "day", "value": 30}},
                "filters": [],
                "filtersOperator": "and",
                "property": null
            },
            "propertyType": "number"
        },
        "resourceType": "events"
    }
}
```

### 5.5 Import Updates

**File**: `src/mixpanel_data/_internal/bookmark_builders.py`:

Add `BehaviorProperty` to the import from `mixpanel_data.types`.

**File**: `src/mixpanel_data/__init__.py`:

Add to exports: `BehaviorProperty`, `BehaviorAggregation`.

---

## 6. Validation Rules

### 6.1 New Rules — Layer 1

| Code | Rule | Condition | Message |
|------|------|-----------|---------|
| BP1 | Event name must be non-empty | `not bp.event.strip()` | `behavior property event name must be non-empty` |
| BP2 | Property required for some operators | `bp.aggregation in BEHAVIOR_PROPERTY_REQUIRED and bp.property is None` | `aggregation '{agg}' requires a property (e.g., property="amount")` |
| BP3 | Property not applicable for some operators | `bp.aggregation in BEHAVIOR_NO_PROPERTY and bp.property is not None` | `aggregation '{agg}' does not use a property` |
| BP4 | last must be positive | `bp.last <= 0` | `behavior property last must be a positive integer (got {last})` |
| BP5 | from_date requires to_date | `bp.from_date is not None and bp.to_date is None` | `behavior property from_date requires to_date` |
| BP6 | to_date requires from_date | `bp.to_date is not None and bp.from_date is None` | `behavior property to_date requires from_date` |
| BP7 | since is mutually exclusive with from_date/to_date | `bp.since is not None and (bp.from_date is not None or bp.to_date is not None)` | `behavior property since is mutually exclusive with from_date/to_date` |
| BP8 | Date format validation | `from_date` or `to_date` or `since` fails YYYY-MM-DD parse | `behavior property {field} must be YYYY-MM-DD format (got '{value}')` |
| BP9 | Property name must be non-empty when set | `bp.property is not None and not bp.property.strip()` | `behavior property property name must be non-empty` |
| BP10 | Property type must be non-empty when property set | `bp.property is not None and not bp.property_type` | `behavior property property_type is required when property is set` |

### 6.2 Validation Implementation

**File**: `src/mixpanel_data/_internal/validation.py`

Add a new helper alongside `_validate_custom_property()`:

```python
def _validate_behavior_property(
    bp: BehaviorProperty,
    context: str,
) -> list[ValidationError]:
    """Validate a behavior-based custom property specification.

    Args:
        bp: The behavior property to validate.
        context: Human-readable location (e.g., "group_by[0]",
            "where[1]", "events[0].property").

    Returns:
        List of validation errors (may be empty).
    """
    errors: list[ValidationError] = []

    # BP1: Event name
    if not bp.event.strip():
        errors.append(ValidationError(
            path=context,
            message="behavior property event name must be non-empty",
            code="BP1",
            severity="error",
        ))

    # BP2: Property required
    if bp.aggregation in BEHAVIOR_PROPERTY_REQUIRED and bp.property is None:
        errors.append(ValidationError(
            path=context,
            message=(
                f"aggregation '{bp.aggregation}' requires a property "
                f"(e.g., property=\"amount\")"
            ),
            code="BP2",
            severity="error",
        ))

    # BP3: Property not applicable
    if bp.aggregation in BEHAVIOR_NO_PROPERTY and bp.property is not None:
        errors.append(ValidationError(
            path=context,
            message=(
                f"aggregation '{bp.aggregation}' does not use a property"
            ),
            code="BP3",
            severity="error",
        ))

    # BP4: last must be positive
    if bp.last <= 0:
        errors.append(ValidationError(
            path=context,
            message=(
                f"behavior property last must be a positive integer "
                f"(got {bp.last})"
            ),
            code="BP4",
            severity="error",
        ))

    # BP5/BP6: from_date/to_date pairing
    if bp.from_date is not None and bp.to_date is None:
        errors.append(ValidationError(
            path=context,
            message="behavior property from_date requires to_date",
            code="BP5",
            severity="error",
        ))
    if bp.to_date is not None and bp.from_date is None:
        errors.append(ValidationError(
            path=context,
            message="behavior property to_date requires from_date",
            code="BP6",
            severity="error",
        ))

    # BP7: since exclusivity
    if bp.since is not None and (
        bp.from_date is not None or bp.to_date is not None
    ):
        errors.append(ValidationError(
            path=context,
            message=(
                "behavior property since is mutually exclusive "
                "with from_date/to_date"
            ),
            code="BP7",
            severity="error",
        ))

    # BP8: Date format validation
    for field_name, field_value in [
        ("from_date", bp.from_date),
        ("to_date", bp.to_date),
        ("since", bp.since),
    ]:
        if field_value is not None:
            try:
                datetime.strptime(field_value, "%Y-%m-%d")
            except ValueError:
                errors.append(ValidationError(
                    path=f"{context}.{field_name}",
                    message=(
                        f"behavior property {field_name} must be "
                        f"YYYY-MM-DD format (got '{field_value}')"
                    ),
                    code="BP8",
                    severity="error",
                ))

    # BP9: Property name
    if bp.property is not None and not bp.property.strip():
        errors.append(ValidationError(
            path=context,
            message="behavior property property name must be non-empty",
            code="BP9",
            severity="error",
        ))

    return errors
```

### 6.3 Validation Integration

In `validate_query_args()`, `validate_funnel_args()`, `validate_retention_args()` — extend the existing CP validation to also dispatch on `BehaviorProperty`:

```python
# Alongside the existing _validate_custom_property() calls:
if isinstance(prop, BehaviorProperty):
    errors.extend(_validate_behavior_property(prop, context))
```

---

## 7. Test Specifications (TDD-First)

### 7.1 Test File Structure

```
tests/unit/
├── test_behavior_property_types.py     # Phase 1: Type construction & validation
├── test_behavior_property_builders.py  # Phase 2: Builder output verification
├── test_behavior_property_query.py     # Phase 3: End-to-end query method tests
└── test_behavior_property_pbt.py       # Phase 4: Property-based tests
```

### 7.2 Phase 1 Tests — Type Construction & Validation

**File**: `tests/unit/test_behavior_property_types.py`

```python
"""Tests for BehaviorProperty type construction and validation rules BP1-BP10."""


class TestBehaviorPropertyConstruction:
    """BehaviorProperty construction and field defaults."""

    def test_minimal_construction(self) -> None:
        """Minimal: event + aggregation, all defaults."""
        bp = BehaviorProperty(event="Purchase", aggregation="total")
        assert bp.event == "Purchase"
        assert bp.aggregation == "total"
        assert bp.property is None
        assert bp.property_type == "number"
        assert bp.last == 30
        assert bp.last_unit == "day"
        assert bp.from_date is None
        assert bp.to_date is None
        assert bp.since is None
        assert bp.filters is None
        assert bp.filters_combinator == "all"
        assert bp.property_type_override is None
        assert bp.resource_type == "events"

    def test_full_construction(self) -> None:
        """All fields explicitly set."""
        bp = BehaviorProperty(
            event="Purchase",
            aggregation="average",
            property="amount",
            property_type="number",
            last=90,
            last_unit="day",
            filters=[Filter.equals("country", "US")],
            filters_combinator="all",
        )
        assert bp.property == "amount"
        assert bp.last == 90
        assert len(bp.filters) == 1

    def test_absolute_date_range(self) -> None:
        """from_date + to_date for absolute range."""
        bp = BehaviorProperty(
            event="Purchase",
            aggregation="total",
            from_date="2024-01-01",
            to_date="2024-12-31",
        )
        assert bp.from_date == "2024-01-01"
        assert bp.to_date == "2024-12-31"

    def test_since_date_range(self) -> None:
        """since for open-ended start."""
        bp = BehaviorProperty(
            event="Signup",
            aggregation="first_event_time",
            since="2020-01-01",
        )
        assert bp.since == "2020-01-01"

    def test_frozen(self) -> None:
        """BehaviorProperty is immutable."""
        bp = BehaviorProperty(event="Login", aggregation="total")
        with pytest.raises(FrozenInstanceError):
            bp.event = "Signup"


class TestBehaviorPropertyOutputType:
    """BehaviorProperty.output_type inference."""

    def test_total_infers_number(self) -> None:
        bp = BehaviorProperty(event="X", aggregation="total")
        assert bp.output_type == "number"

    def test_average_infers_number(self) -> None:
        bp = BehaviorProperty(event="X", aggregation="average", property="p")
        assert bp.output_type == "number"

    def test_most_frequent_infers_string(self) -> None:
        bp = BehaviorProperty(event="X", aggregation="most_frequent", property="p")
        assert bp.output_type == "string"

    def test_first_value_infers_string(self) -> None:
        bp = BehaviorProperty(event="X", aggregation="first_value", property="p")
        assert bp.output_type == "string"

    def test_min_infers_number(self) -> None:
        bp = BehaviorProperty(event="X", aggregation="min", property="p")
        assert bp.output_type == "number"

    def test_first_event_time_infers_number(self) -> None:
        bp = BehaviorProperty(event="X", aggregation="first_event_time")
        assert bp.output_type == "number"

    def test_override_takes_precedence(self) -> None:
        bp = BehaviorProperty(
            event="X", aggregation="total",
            property_type_override="string",
        )
        assert bp.output_type == "string"


class TestBehaviorPropertyConvenienceConstructors:
    """BehaviorProperty.count() and .aggregate() convenience constructors."""

    def test_count_minimal(self) -> None:
        bp = BehaviorProperty.count("Login")
        assert bp.event == "Login"
        assert bp.aggregation == "total"
        assert bp.property is None
        assert bp.last == 30

    def test_count_with_options(self) -> None:
        bp = BehaviorProperty.count(
            "Purchase", last=90, last_unit="day",
            filters=[Filter.equals("plan", "pro")],
        )
        assert bp.last == 90
        assert len(bp.filters) == 1

    def test_aggregate_average(self) -> None:
        bp = BehaviorProperty.aggregate(
            "Purchase", "average", "amount",
        )
        assert bp.event == "Purchase"
        assert bp.aggregation == "average"
        assert bp.property == "amount"
        assert bp.property_type == "number"

    def test_aggregate_most_frequent(self) -> None:
        bp = BehaviorProperty.aggregate(
            "Page View", "most_frequent", "$browser",
            property_type="string",
        )
        assert bp.property_type == "string"


class TestBehaviorPropertyValidation:
    """Validation rules BP1-BP10."""

    def test_bp1_empty_event(self, ws: Workspace) -> None:
        """BP1: Empty event name raises."""
        with pytest.raises(BookmarkValidationError, match="non-empty"):
            ws.build_params(
                "Login",
                group_by=GroupBy(property=BehaviorProperty(
                    event="", aggregation="total",
                )),
            )

    def test_bp2_average_requires_property(self, ws: Workspace) -> None:
        """BP2: average without property raises."""
        with pytest.raises(BookmarkValidationError, match="requires a property"):
            ws.build_params(
                "Login",
                group_by=GroupBy(property=BehaviorProperty(
                    event="Purchase", aggregation="average",
                )),
            )

    def test_bp2_most_frequent_requires_property(self, ws: Workspace) -> None:
        """BP2: most_frequent without property raises."""
        with pytest.raises(BookmarkValidationError, match="requires a property"):
            ws.build_params(
                "Login",
                group_by=GroupBy(property=BehaviorProperty(
                    event="Purchase", aggregation="most_frequent",
                )),
            )

    def test_bp3_first_event_time_rejects_property(self, ws: Workspace) -> None:
        """BP3: first_event_time with property raises."""
        with pytest.raises(BookmarkValidationError, match="does not use"):
            ws.build_params(
                "Login",
                group_by=GroupBy(property=BehaviorProperty(
                    event="Login", aggregation="first_event_time",
                    property="x",
                )),
            )

    def test_bp4_negative_last(self, ws: Workspace) -> None:
        """BP4: Negative last raises."""
        with pytest.raises(BookmarkValidationError, match="positive integer"):
            ws.build_params(
                "Login",
                group_by=GroupBy(property=BehaviorProperty(
                    event="Purchase", aggregation="total", last=-1,
                )),
            )

    def test_bp5_from_without_to(self, ws: Workspace) -> None:
        """BP5: from_date without to_date raises."""
        with pytest.raises(BookmarkValidationError, match="requires to_date"):
            ws.build_params(
                "Login",
                group_by=GroupBy(property=BehaviorProperty(
                    event="Purchase", aggregation="total",
                    from_date="2024-01-01",
                )),
            )

    def test_bp6_to_without_from(self, ws: Workspace) -> None:
        """BP6: to_date without from_date raises."""
        with pytest.raises(BookmarkValidationError, match="requires from_date"):
            ws.build_params(
                "Login",
                group_by=GroupBy(property=BehaviorProperty(
                    event="Purchase", aggregation="total",
                    to_date="2024-12-31",
                )),
            )

    def test_bp7_since_with_from_date(self, ws: Workspace) -> None:
        """BP7: since with from_date raises."""
        with pytest.raises(BookmarkValidationError, match="mutually exclusive"):
            ws.build_params(
                "Login",
                group_by=GroupBy(property=BehaviorProperty(
                    event="Purchase", aggregation="total",
                    since="2024-01-01", from_date="2024-01-01",
                    to_date="2024-12-31",
                )),
            )

    def test_bp8_bad_date_format(self, ws: Workspace) -> None:
        """BP8: Invalid date format raises."""
        with pytest.raises(BookmarkValidationError, match="YYYY-MM-DD"):
            ws.build_params(
                "Login",
                group_by=GroupBy(property=BehaviorProperty(
                    event="Purchase", aggregation="total",
                    from_date="01/01/2024", to_date="12/31/2024",
                )),
            )

    def test_bp9_empty_property_name(self, ws: Workspace) -> None:
        """BP9: Empty property name raises."""
        with pytest.raises(BookmarkValidationError, match="non-empty"):
            ws.build_params(
                "Login",
                group_by=GroupBy(property=BehaviorProperty(
                    event="Purchase", aggregation="average",
                    property="  ",
                )),
            )

    def test_total_without_property_valid(self, ws: Workspace) -> None:
        """total without property is valid (count mode)."""
        # Should not raise
        ws.build_params(
            "Login",
            group_by=GroupBy(property=BehaviorProperty(
                event="Purchase", aggregation="total",
            )),
        )

    def test_total_with_property_valid(self, ws: Workspace) -> None:
        """total with property is valid (sum mode)."""
        ws.build_params(
            "Login",
            group_by=GroupBy(property=BehaviorProperty(
                event="Purchase", aggregation="total",
                property="amount", property_type="number",
            )),
        )
```

### 7.3 Phase 2 Tests — Builder Output Verification

**File**: `tests/unit/test_behavior_property_builders.py`

```python
"""Tests for BehaviorProperty bookmark JSON output."""


class TestBuildBehaviorDict:
    """_build_behavior_dict() helper."""

    def test_relative_date_range(self) -> None:
        """Default relative date range → in the last."""
        bp = BehaviorProperty(event="Purchase", aggregation="total")
        result = _build_behavior_dict(bp)
        assert result["dateRange"]["type"] == "in the last"
        assert result["dateRange"]["window"]["unit"] == "day"
        assert result["dateRange"]["window"]["value"] == 30

    def test_absolute_date_range(self) -> None:
        """from_date + to_date → between."""
        bp = BehaviorProperty(
            event="Purchase", aggregation="total",
            from_date="2024-01-01", to_date="2024-12-31",
        )
        result = _build_behavior_dict(bp)
        assert result["dateRange"]["type"] == "between"
        assert result["dateRange"]["from"] == "2024-01-01"
        assert result["dateRange"]["to"] == "2024-12-31"

    def test_since_date_range(self) -> None:
        """since → since type."""
        bp = BehaviorProperty(
            event="Signup", aggregation="first_event_time",
            since="2020-01-01",
        )
        result = _build_behavior_dict(bp)
        assert result["dateRange"]["type"] == "since"
        assert result["dateRange"]["from"] == "2020-01-01"

    def test_event_ref(self) -> None:
        """Event name → event.value."""
        bp = BehaviorProperty(event="Purchase", aggregation="total")
        result = _build_behavior_dict(bp)
        assert result["event"]["value"] == "Purchase"

    def test_aggregation_operator(self) -> None:
        """aggregation → aggregationOperator."""
        bp = BehaviorProperty(event="X", aggregation="average", property="p")
        result = _build_behavior_dict(bp)
        assert result["aggregationOperator"] == "average"

    def test_property_null_when_none(self) -> None:
        """No property → property: null."""
        bp = BehaviorProperty(event="X", aggregation="total")
        result = _build_behavior_dict(bp)
        assert result["property"] is None

    def test_property_present(self) -> None:
        """Property set → property dict with value/type/resourceType."""
        bp = BehaviorProperty(
            event="X", aggregation="average",
            property="amount", property_type="number",
        )
        result = _build_behavior_dict(bp)
        assert result["property"]["value"] == "amount"
        assert result["property"]["type"] == "number"
        assert result["property"]["resourceType"] == "event"

    def test_no_filters(self) -> None:
        """No filters → empty list, filtersOperator and."""
        bp = BehaviorProperty(event="X", aggregation="total")
        result = _build_behavior_dict(bp)
        assert result["filters"] == []
        assert result["filtersOperator"] == "and"

    def test_with_filters(self) -> None:
        """Filters → converted via build_filter_entry."""
        bp = BehaviorProperty(
            event="Purchase", aggregation="total",
            filters=[Filter.equals("country", "US")],
        )
        result = _build_behavior_dict(bp)
        assert len(result["filters"]) == 1
        assert result["filters"][0]["value"] == "country"

    def test_or_combinator(self) -> None:
        """filters_combinator='any' → filtersOperator='or'."""
        bp = BehaviorProperty(
            event="X", aggregation="total",
            filters=[Filter.equals("a", "b")],
            filters_combinator="any",
        )
        result = _build_behavior_dict(bp)
        assert result["filtersOperator"] == "or"

    def test_custom_last_unit(self) -> None:
        """Custom last_unit → window.unit."""
        bp = BehaviorProperty(
            event="X", aggregation="total",
            last=12, last_unit="month",
        )
        result = _build_behavior_dict(bp)
        assert result["dateRange"]["window"]["unit"] == "month"
        assert result["dateRange"]["window"]["value"] == 12


class TestBuildGroupSectionBehaviorProperty:
    """build_group_section() with BehaviorProperty."""

    def test_emits_custom_property_with_behavior(self) -> None:
        """BehaviorProperty emits customProperty.behavior dict."""
        section = build_group_section(
            GroupBy(property=BehaviorProperty(
                event="Purchase", aggregation="total",
            ))
        )
        entry = section[0]
        assert "customProperty" in entry
        assert "behavior" in entry["customProperty"]
        assert entry["customProperty"]["behavior"]["aggregationOperator"] == "total"
        assert entry["propertyType"] == "number"

    def test_string_output_type(self) -> None:
        """most_frequent → propertyType string."""
        section = build_group_section(
            GroupBy(property=BehaviorProperty(
                event="X", aggregation="most_frequent",
                property="browser", property_type="string",
            ))
        )
        entry = section[0]
        assert entry["propertyType"] == "string"
        assert entry["customProperty"]["propertyType"] == "string"

    def test_with_bucketing(self) -> None:
        """Bucketing works with BehaviorProperty."""
        section = build_group_section(
            GroupBy(
                property=BehaviorProperty(
                    event="Purchase", aggregation="total",
                ),
                property_type="number",
                bucket_size=5,
                bucket_min=0,
                bucket_max=50,
            )
        )
        entry = section[0]
        assert entry["customBucket"]["bucketSize"] == 5


class TestBuildFilterEntryBehaviorProperty:
    """build_filter_entry() with BehaviorProperty."""

    def test_emits_custom_property_with_behavior(self) -> None:
        """BehaviorProperty in filter emits customProperty.behavior."""
        f = Filter.greater_than(
            property=BehaviorProperty(
                event="Purchase", aggregation="total",
            ),
            value=5,
        )
        entry = build_filter_entry(f)
        assert "customProperty" in entry
        assert "behavior" in entry["customProperty"]
        assert entry["filterValue"] == 5
        assert entry["filterOperator"] == "is greater than"
        assert entry["filterType"] == "number"

    def test_no_value_field(self) -> None:
        """BehaviorProperty filter has no 'value' key (property name)."""
        f = Filter.greater_than(
            property=BehaviorProperty(
                event="Purchase", aggregation="total",
            ),
            value=5,
        )
        entry = build_filter_entry(f)
        assert "value" not in entry


class TestMeasurementBehaviorProperty:
    """Measurement property in _build_query_params() with BehaviorProperty."""

    def test_emits_custom_property_with_behavior(self, ws: Workspace) -> None:
        """BehaviorProperty in Metric.property emits customProperty.behavior."""
        params = ws._build_query_params(
            events=[Metric(
                "Login", math="average",
                property=BehaviorProperty(
                    event="Purchase", aggregation="total",
                ),
            )],
            math="total", math_property=None, per_user=None,
            from_date=None, to_date=None, last=30, unit="day",
            group_by=None, where=None, formulas=[], rolling=None,
            cumulative=False, mode="timeseries",
        )
        prop = params["sections"]["show"][0]["measurement"]["property"]
        assert "customProperty" in prop
        assert "behavior" in prop["customProperty"]
```

### 7.4 Phase 3 Tests — End-to-End

**File**: `tests/unit/test_behavior_property_query.py`

```python
"""End-to-end tests for BehaviorProperty in query(), query_funnel(), query_retention()."""


class TestQueryWithBehaviorPropertyGroupBy:

    def test_build_params_count_group_by(self, ws: Workspace) -> None:
        """BehaviorProperty.count() in group_by."""
        params = ws.build_params(
            "Login",
            group_by=GroupBy(
                property=BehaviorProperty.count("Purchase"),
                property_type="number",
                bucket_size=5,
            ),
        )
        group = params["sections"]["group"][0]
        assert "customProperty" in group
        beh = group["customProperty"]["behavior"]
        assert beh["event"]["value"] == "Purchase"
        assert beh["aggregationOperator"] == "total"

    def test_build_params_aggregate_group_by(self, ws: Workspace) -> None:
        """BehaviorProperty.aggregate() in group_by."""
        params = ws.build_params(
            "Login",
            group_by=GroupBy(
                property=BehaviorProperty.aggregate(
                    "Purchase", "most_frequent", "$browser",
                    property_type="string",
                ),
            ),
        )
        group = params["sections"]["group"][0]
        assert group["propertyType"] == "string"


class TestQueryWithBehaviorPropertyFilter:

    def test_build_params_count_filter(self, ws: Workspace) -> None:
        """Filter users by purchase count > 5."""
        params = ws.build_params(
            "Login",
            where=Filter.greater_than(
                property=BehaviorProperty.count("Purchase"),
                value=5,
            ),
        )
        filt = params["sections"]["filter"][0]
        assert filt["customProperty"]["behavior"]["aggregationOperator"] == "total"
        assert filt["filterValue"] == 5


class TestFunnelWithBehaviorPropertyGroupBy:

    def test_build_funnel_params_with_behavior_group_by(self, ws: Workspace) -> None:
        """BehaviorProperty in funnel group_by."""
        params = ws.build_funnel_params(
            ["Signup", "Purchase"],
            group_by=GroupBy(
                property=BehaviorProperty.count("Login", last=90),
                property_type="number",
                bucket_size=10,
            ),
        )
        group = params["sections"]["group"][0]
        assert "customProperty" in group
        assert group["customProperty"]["behavior"]["dateRange"]["window"]["value"] == 90


class TestCombinedWithFormulaCP:

    def test_formula_group_behavior_filter(self, ws: Workspace) -> None:
        """InlineCustomProperty in group_by + BehaviorProperty in filter."""
        params = ws.build_params(
            "Purchase",
            group_by=GroupBy(
                property=InlineCustomProperty.numeric("A * B", A="price", B="qty"),
                property_type="number",
            ),
            where=Filter.greater_than(
                property=BehaviorProperty.count("Purchase"),
                value=3,
            ),
        )
        assert "customProperty" in params["sections"]["group"][0]
        assert "displayFormula" in params["sections"]["group"][0]["customProperty"]
        assert "customProperty" in params["sections"]["filter"][0]
        assert "behavior" in params["sections"]["filter"][0]["customProperty"]
```

### 7.5 Phase 4 Tests — PBT

**File**: `tests/unit/test_behavior_property_pbt.py`

```python
"""Property-based tests for BehaviorProperty."""

from hypothesis import given, strategies as st

valid_aggregation = st.sampled_from([
    "total", "average", "unique_values", "most_frequent", "first_value",
    "min", "max", "last_value", "first_event_time", "last_event_time",
])

valid_last_unit = st.sampled_from(["day", "week", "month"])


class TestBehaviorPropertyPBT:

    @given(
        event=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
        aggregation=valid_aggregation,
        last=st.integers(min_value=1, max_value=365),
        last_unit=valid_last_unit,
    )
    def test_construction_preserves_fields(
        self, event: str, aggregation: str, last: int, last_unit: str,
    ) -> None:
        """All field values survive construction."""
        bp = BehaviorProperty(
            event=event, aggregation=aggregation,
            last=last, last_unit=last_unit,
        )
        assert bp.event == event
        assert bp.aggregation == aggregation
        assert bp.last == last
        assert bp.last_unit == last_unit

    @given(aggregation=valid_aggregation)
    def test_output_type_is_string_or_number(self, aggregation: str) -> None:
        """Output type is always string or number."""
        bp = BehaviorProperty(event="X", aggregation=aggregation)
        assert bp.output_type in ("string", "number")


class TestBuildBehaviorDictPBT:

    @given(
        event=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
        last=st.integers(min_value=1, max_value=365),
    )
    def test_output_has_required_keys(self, event: str, last: int) -> None:
        """Builder output always has required keys."""
        bp = BehaviorProperty(event=event, aggregation="total", last=last)
        result = _build_behavior_dict(bp)
        assert "event" in result
        assert "aggregationOperator" in result
        assert "dateRange" in result
        assert "filters" in result
        assert "filtersOperator" in result
        assert "property" in result
```

---

## 8. Usage Examples

### 8.1 Group-By — Segment by User Behavior

```python
# "Login events, segmented by how many purchases each user made"
result = ws.query(
    "Login",
    group_by=GroupBy(
        property=BehaviorProperty.count("Purchase"),
        property_type="number",
        bucket_size=5,
        bucket_min=0,
        bucket_max=50,
    ),
)

# "Signups, broken down by each user's most-used browser"
result = ws.query(
    "Signup",
    group_by=GroupBy(
        property=BehaviorProperty.aggregate(
            "Page View", "most_frequent", "$browser",
            property_type="string",
        ),
    ),
)

# "Purchases, segmented by average order value tier"
result = ws.query(
    "Purchase",
    group_by=GroupBy(
        property=BehaviorProperty.aggregate(
            "Purchase", "average", "amount", last=90,
        ),
        property_type="number",
        bucket_size=50,
    ),
)
```

### 8.2 Filter — Users Meeting Behavioral Thresholds

```python
# "Logins from users who made 5+ purchases in the last 30 days"
result = ws.query(
    "Login",
    where=Filter.greater_than(
        property=BehaviorProperty.count("Purchase"),
        value=5,
    ),
)

# "Signups from users who never logged in (0 logins in 90 days)"
result = ws.query(
    "Signup",
    where=Filter.equals(
        property=BehaviorProperty.count("Login", last=90),
        value=0,
    ),
)

# "Purchases from users whose average order value exceeds $100"
result = ws.query(
    "Purchase",
    where=Filter.greater_than(
        property=BehaviorProperty.aggregate(
            "Purchase", "average", "amount",
        ),
        value=100,
    ),
)
```

### 8.3 Metric Measurement — Aggregate on Behavior

```python
# "Average purchase count per user, by week"
result = ws.query(
    Metric(
        "Login",
        math="average",
        property=BehaviorProperty.count("Purchase"),
    ),
    unit="week",
)
```

### 8.4 Combined — Behavior + Formula + Regular

```python
# "Purchases from power users (5+ purchases), broken down by
#  revenue bucket (price * quantity)"
result = ws.query(
    "Purchase",
    group_by=GroupBy(
        property=InlineCustomProperty.numeric("A * B", A="price", B="quantity"),
        property_type="number",
        bucket_size=100,
    ),
    where=Filter.greater_than(
        property=BehaviorProperty.count("Purchase"),
        value=5,
    ),
)
```

### 8.5 Funnel — Behavioral Segmentation

```python
# "Signup → Purchase funnel, segmented by prior login frequency"
result = ws.query_funnel(
    ["Signup", "Purchase"],
    group_by=GroupBy(
        property=BehaviorProperty.count("Login", last=90),
        property_type="number",
        bucket_size=10,
    ),
)
```

### 8.6 With Behavior Filters

```python
# "Total iOS purchases in Q1, from users who spent $100+ this year"
result = ws.query(
    "Purchase",
    where=[
        Filter.equals("platform", "iOS"),
        Filter.greater_than(
            property=BehaviorProperty(
                event="Purchase",
                aggregation="total",
                property="amount",
                property_type="number",
                from_date="2024-01-01",
                to_date="2024-12-31",
            ),
            value=100,
        ),
    ],
    from_date="2024-01-01",
    to_date="2024-03-31",
)
```

---

## 9. Implementation Phases

Each phase follows strict TDD. **Prerequisite**: v1 (`custom-properties-in-queries-design.md`) is fully implemented.

### Phase 1: New Types (Estimated: ~120 lines impl, ~250 lines tests)

**Tests first**: `tests/unit/test_behavior_property_types.py` — construction, output_type, convenience constructors, validation

**Then implement** in `src/mixpanel_data/types.py`:
1. Add `BehaviorAggregation` type alias
2. Add `BEHAVIOR_PROPERTY_REQUIRED` and `BEHAVIOR_NO_PROPERTY` frozensets
3. Add `BehaviorDateRangeUnit` type alias
4. Add `BehaviorProperty` frozen dataclass with `output_type` property
5. Add `count()` and `aggregate()` classmethods
6. Update `PropertySpec` type alias to include `BehaviorProperty`

**Verify**: All type construction and validation tests pass.

### Phase 2: Modified Types (Estimated: ~20 lines changes)

**Implement** type signature changes:
1. `Metric.property` — add `BehaviorProperty` to union
2. `GroupBy.property` — add `BehaviorProperty` to union
3. `Filter._property` — add `BehaviorProperty` to union
4. All 18 `Filter` class methods — add `BehaviorProperty` to `property` param union

**Verify**: `just typecheck` passes. All existing tests still pass.

### Phase 3: Builders (Estimated: ~100 lines impl, ~200 lines tests)

**Tests first**: `tests/unit/test_behavior_property_builders.py` — all builder output tests

**Then implement** in `src/mixpanel_data/_internal/bookmark_builders.py`:
1. Add `_build_behavior_dict()` helper function
2. Add `BehaviorProperty` branch to `build_filter_entry()`
3. Add `BehaviorProperty` branch to `build_group_section()`
4. Update imports

**Then implement** in `src/mixpanel_data/workspace.py`:
5. Add `BehaviorProperty` branch to measurement builder in `_build_query_params()`
6. Add `BehaviorProperty` branch to measurement builder in `_build_funnel_params()`
7. Update imports

**Verify**: All builder output tests pass.

### Phase 4: Validation (Estimated: ~80 lines impl, ~150 lines tests)

**Tests first**: Enable all BP1-BP10 validation tests

**Then implement** in `src/mixpanel_data/_internal/validation.py`:
1. Add `_validate_behavior_property()` helper function
2. Add `BehaviorProperty` dispatch in `validate_query_args()`
3. Add `BehaviorProperty` dispatch in `validate_funnel_args()`
4. Add `BehaviorProperty` dispatch in `validate_retention_args()`

**Verify**: All validation tests pass.

### Phase 5: E2E, Exports & PBT (Estimated: ~30 lines impl, ~150 lines tests)

**Tests**: `test_behavior_property_query.py` + `test_behavior_property_pbt.py`

**Implement**:
1. Update `__init__.py` exports
2. Verify `_resolve_and_build_*_params()` type guards handle `BehaviorProperty`

**Verify**: `just check` green. Coverage >= 90%. PBT passes.

---

## 10. Dependency Graph

```
v1 Complete (custom-properties-in-queries-design.md)
    │
    └── Phase 1: BehaviorProperty type
            │
            ├── Phase 2: Modified type unions
            │       │
            │       └── Phase 4: Validation (depends on types)
            │
            └── Phase 3: Builders (depends on type)
                    │
                    └── Phase 5: E2E + Exports + PBT
```

---

## 11. Files Changed Summary

| File | Change Type | Scope |
|------|------------|-------|
| `src/mixpanel_data/types.py` | **Modified** | Add `BehaviorProperty`, `BehaviorAggregation`, `BehaviorDateRangeUnit`, `BEHAVIOR_PROPERTY_REQUIRED`, `BEHAVIOR_NO_PROPERTY`; update `PropertySpec`, `Metric.property`, `GroupBy.property`, `Filter._property` + 18 class methods |
| `src/mixpanel_data/_internal/bookmark_builders.py` | **Modified** | Add `_build_behavior_dict()`; add `BehaviorProperty` branches in `build_filter_entry()` and `build_group_section()` |
| `src/mixpanel_data/workspace.py` | **Modified** | Add `BehaviorProperty` branch in measurement builders |
| `src/mixpanel_data/_internal/validation.py` | **Modified** | Add `_validate_behavior_property()`; add dispatch in 3 validate functions |
| `src/mixpanel_data/__init__.py` | **Modified** | Add exports |
| `tests/unit/test_behavior_property_types.py` | **New** | ~350 lines |
| `tests/unit/test_behavior_property_builders.py` | **New** | ~250 lines |
| `tests/unit/test_behavior_property_query.py` | **New** | ~150 lines |
| `tests/unit/test_behavior_property_pbt.py` | **New** | ~80 lines |

**Total implementation**: ~350 lines of production code
**Total tests**: ~830 lines of test code

---

## 12. Acceptance Criteria

- [ ] `BehaviorProperty` is a frozen dataclass with `output_type` property
- [ ] `BehaviorProperty.count()` and `.aggregate()` convenience constructors work
- [ ] `BehaviorAggregation` Literal covers all 10 operators
- [ ] `PropertySpec` union includes `BehaviorProperty`
- [ ] `Metric.property`, `GroupBy.property`, `Filter._property` accept `BehaviorProperty`
- [ ] `_build_behavior_dict()` produces correct JSON for relative, absolute, and since date ranges
- [ ] `_build_behavior_dict()` produces correct JSON for property and no-property aggregations
- [ ] `_build_behavior_dict()` converts behavior filters via `build_filter_entry()`
- [ ] `build_filter_entry()` emits correct JSON for `BehaviorProperty`
- [ ] `build_group_section()` emits correct JSON for `BehaviorProperty` with bucketing
- [ ] Measurement builder emits correct JSON for `BehaviorProperty`
- [ ] Validation rules BP1-BP10 catch all invalid inputs
- [ ] `BehaviorProperty` works alongside `InlineCustomProperty` and `CustomPropertyRef` in the same query
- [ ] All existing tests pass unchanged (backward compatibility)
- [ ] `just check` passes
- [ ] Coverage >= 90%
- [ ] New types exported from `mixpanel_data.__init__`
