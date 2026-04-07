# Custom Properties in Queries — Design, Specification & Implementation Plan

**Date**: 2026-04-06
**Status**: Design Complete — Ready for TDD Implementation
**Builds on**: `insights-query-api-design.md`, `unified-bookmark-query-design.md`, `custom-events-properties-query-integration.md`
**Reference**: `analytics/backend/util/arb_selector.py`, `analytics/iron/common/types/reports/bookmark.ts`

---

## 1. Scope & Goals

### What This Document Covers

First-class support for **custom properties** (both saved and inline/ad-hoc) in the unified query system: `query()`, `query_funnel()`, `query_retention()`, and their `build_*_params()` counterparts. Custom properties can appear in three positions:

1. **Breakdown** (`group_by=`) — Segment results by a computed property
2. **Filter** (`where=`) — Filter events by a computed property value
3. **Metric measurement** (`Metric.property=`) — Aggregate on a computed property (e.g., average of price * quantity)

### What This Document Does NOT Cover

- Custom **events** (`CustomEventRef`) — separate implementation phase
- Behavior-based inline custom properties — v2 enhancement
- Flows query custom property support — flows use segfilter format and don't support custom properties in breakdowns
- Custom property CRUD — already implemented (`create_custom_property()`, etc.)

### Design Principles

1. **Backward-compatible** — All changes add union members to existing types; existing code is unaffected
2. **Progressive disclosure** — Plain strings for simple cases, typed objects for advanced
3. **Fail-fast** — Client-side validation catches mistakes before API calls
4. **Consistent with existing patterns** — Follows the `Metric`/`Filter`/`GroupBy` frozen dataclass pattern
5. **LLM-friendly** — Self-documenting types, keyword arguments, clear error messages

---

## 2. New Types

### 2.1 `PropertyInput`

Represents a single raw property that feeds into an inline custom property formula. Maps to one entry in the bookmark's `composedProperties` dict.

```python
@dataclass(frozen=True)
class PropertyInput:
    """An input property reference for an inline custom property formula.

    Maps a letter variable (A, B, C...) in the formula to a raw event
    or user property. Each PropertyInput becomes one entry in the
    bookmark's ``composedProperties`` dict.

    Attributes:
        name: The raw property name (e.g., ``"price"``, ``"$browser"``).
            This is the Mixpanel property name as it appears in event data.
        type: Property data type. Determines how the query engine
            interprets the property value. Default ``"string"``.
        resource_type: Property domain. ``"event"`` for event properties
            (the common case), ``"user"`` for user/people profile properties.
            Default ``"event"``.

    Examples:
        ```python
        PropertyInput("price", type="number")
        PropertyInput("$browser", type="string")
        PropertyInput("plan", type="string", resource_type="user")
        PropertyInput("created_at", type="datetime")
        ```
    """

    name: str
    type: Literal["string", "number", "boolean", "datetime", "list"] = "string"
    resource_type: Literal["event", "user"] = "event"
```

**Bookmark JSON mapping:**
```python
PropertyInput("price", type="number", resource_type="event")
# → composedProperties entry:
{"value": "price", "type": "number", "resourceType": "event"}
```

**Field mapping:**

| `PropertyInput` field | Bookmark JSON field | Notes |
|----------------------|--------------------|----|
| `name` | `value` | The property name — called `value` in Mixpanel's schema |
| `type` | `type` | Direct passthrough |
| `resource_type` | `resourceType` | `"event"` maps to `"event"`, `"user"` maps to `"user"` |

### 2.2 `InlineCustomProperty`

Defines an ad-hoc computed property directly in a query using the arb-selector formula language. Not saved to the project — computed at query time.

```python
@dataclass(frozen=True)
class InlineCustomProperty:
    """An inline (ephemeral) custom property defined directly in a query.

    Defines a computed property using the arb-selector formula language.
    The formula uses single-letter variables (A, B, C...) that map to
    entries in ``inputs``. The property is computed at query time without
    being saved to the project.

    This is a first-class Mixpanel feature — the query engine natively
    supports inline custom property definitions in bookmark params.

    Attributes:
        formula: Expression in arb-selector formula language. Uses
            single-letter variables (A, B, C...) referencing ``inputs``.
            Maximum 20,000 characters.
        inputs: Mapping from letter variables to property references.
            Keys must be single uppercase letters A-Z matching the
            formula variables. At least one input is required.
        property_type: Result type of the formula. Determines how the
            computed value is interpreted (e.g., for bucketing in
            group-by, or for comparison in filters). If ``None``, the
            server infers the type. Explicit typing is recommended.
        resource_type: Which data domain this property applies to.
            ``"events"`` for event properties (default),
            ``"people"`` for user profile properties.

    Formula Language Reference:
        - Arithmetic: ``A + B``, ``A - B``, ``A * B``, ``A / B``,
          ``A % B``, ``CEIL(A)``, ``FLOOR(A)``, ``ROUND(A, 2)``,
          ``NUMBER(A)``
        - String: ``UPPER(A)``, ``LOWER(A)``, ``LEFT(A, 3)``,
          ``RIGHT(A, 3)``, ``MID(A, 2, 5)``, ``LEN(A)``,
          ``SPLIT(A, ",")``, ``REGEX_EXTRACT(A, pattern)``,
          ``REGEX_MATCH(A, pattern)``, ``REGEX_REPLACE(A, pattern, repl)``,
          ``PARSE_URL(A)``
        - Conditional: ``IF(cond, then_val, else_val)``,
          ``IFS(c1, v1, c2, v2, ..., TRUE, default)``
        - Boolean: ``AND``, ``OR``, ``NOT``, ``TRUE``, ``FALSE``, ``IN``
        - Type checking: ``DEFINED(A)``, ``TYPEOF(A)``, ``UNDEFINED``
        - Type casting: ``BOOLEAN(A)``, ``STRING(A)``, ``NUMBER(A)``
        - Date: ``TODAY()``, ``DATEDIF(A, B, "D")``
        - List: ``ANY(A, x, x > 0)``, ``ALL(A, x, x > 0)``,
          ``MAP(A, x, x * 2)``, ``FILTER(A, x, x > 0)``, ``SUM(A)``

    Examples:
        ```python
        # Revenue = price * quantity
        InlineCustomProperty(
            formula="A * B",
            inputs={
                "A": PropertyInput("price", type="number"),
                "B": PropertyInput("quantity", type="number"),
            },
            property_type="number",
        )

        # Extract email domain
        InlineCustomProperty(
            formula='REGEX_EXTRACT(A, "@(.+)$")',
            inputs={"A": PropertyInput("email", type="string")},
            property_type="string",
        )

        # Tiered pricing
        InlineCustomProperty(
            formula='IFS(A > 1000, "Enterprise", A > 100, "Pro", TRUE, "Free")',
            inputs={"A": PropertyInput("amount", type="number")},
            property_type="string",
        )
        ```
    """

    formula: str
    inputs: dict[str, PropertyInput]
    property_type: Literal["string", "number", "boolean", "datetime"] | None = None
    resource_type: Literal["events", "people"] = "events"
```

**Convenience constructor:**

```python
    @classmethod
    def numeric(
        cls,
        formula: str,
        /,
        **properties: str,
    ) -> InlineCustomProperty:
        """Create a numeric formula from named properties.

        Convenience constructor where all inputs are numeric event
        properties. Keyword argument names are used as formula variables
        and values as property names.

        Args:
            formula: Formula expression using single-letter variables
                (A, B, C...) that match the keyword argument names.
            **properties: Mapping of formula variable (single uppercase
                letter) to raw property name. All are typed as
                ``"number"`` with ``resource_type="event"``.

        Returns:
            An InlineCustomProperty with all-numeric inputs and
            ``property_type="number"``.

        Examples:
            ```python
            # Revenue = price * quantity
            InlineCustomProperty.numeric("A * B", A="price", B="quantity")

            # Profit margin percentage
            InlineCustomProperty.numeric(
                "(A - B) / A * 100", A="revenue", B="cost"
            )

            # Simple property reference as number
            InlineCustomProperty.numeric("A", A="amount")
            ```
        """
        return cls(
            formula=formula,
            inputs={
                k: PropertyInput(v, type="number")
                for k, v in properties.items()
            },
            property_type="number",
        )
```

### 2.3 `CustomPropertyRef`

Reference to a saved (persisted) custom property by its integer ID.

```python
@dataclass(frozen=True)
class CustomPropertyRef:
    """Reference to a saved custom property by ID.

    Use when the custom property already exists in the project (created
    via ``create_custom_property()`` or the Mixpanel UI). The query
    engine fetches the full definition from the database at execution
    time using this ID.

    Attributes:
        id: The custom property's ID (``customPropertyId`` in API
            responses). Obtain from ``create_custom_property()``
            return value or ``list_custom_properties()``.

    Examples:
        ```python
        # As a breakdown dimension
        ws.query("Purchase", group_by=GroupBy(
            property=CustomPropertyRef(42)
        ))

        # As a filter target
        ws.query("Purchase", where=Filter.greater_than(
            property=CustomPropertyRef(42), value=100,
        ))

        # As aggregation property
        ws.query(Metric("Purchase", math="average",
                        property=CustomPropertyRef(42)))
        ```
    """

    id: int
```

### 2.4 Type Alias

```python
PropertySpec = str | CustomPropertyRef | InlineCustomProperty
"""A property specifier: plain name, saved custom property ref, or inline formula.

Used as the type for ``property`` fields in ``Metric``, ``GroupBy``, and
``Filter`` to accept any of the three property specification forms.
"""
```

---

## 3. Modified Types — Exact Diffs

### 3.1 `Metric.property` Field

**File**: `src/mixpanel_data/types.py`, `Metric` class

**Before** (line ~6924):
```python
property: str | None = None
"""Property name for property-based math ..."""
```

**After**:
```python
property: str | CustomPropertyRef | InlineCustomProperty | None = None
"""Property for property-based math.

Plain string for raw properties. ``CustomPropertyRef`` for saved
custom properties. ``InlineCustomProperty`` for ad-hoc formulas.
Required when math is average/median/min/max/p25/p75/p90/p99.
"""
```

### 3.2 `GroupBy.property` Field

**File**: `src/mixpanel_data/types.py`, `GroupBy` class

**Before** (line ~7599):
```python
property: str
```

**After**:
```python
property: str | CustomPropertyRef | InlineCustomProperty
"""Property to break down by.

Plain string for raw properties. ``CustomPropertyRef`` for saved
custom properties. ``InlineCustomProperty`` for ad-hoc formulas.
"""
```

### 3.3 `Filter` Internal Storage and Class Methods

**File**: `src/mixpanel_data/types.py`, `Filter` class

**Before** (line ~7029):
```python
_property: str
"""Property name to filter on."""
```

**After**:
```python
_property: str | CustomPropertyRef | InlineCustomProperty
"""Property to filter on.

Plain string for raw properties. ``CustomPropertyRef`` for saved
custom properties. ``InlineCustomProperty`` for ad-hoc formulas.
"""
```

**All 18 class methods** (`equals`, `not_equals`, `contains`, `not_contains`, `greater_than`, `less_than`, `between`, `is_set`, `is_not_set`, `is_true`, `is_false`, `on`, `not_on`, `before`, `since`, `in_the_last`, `not_in_the_last`, `date_between`) change their first positional parameter:

**Before** (example — `equals`):
```python
@classmethod
def equals(
    cls,
    property: str,
    value: str | list[str],
    *,
    resource_type: Literal["events", "people"] = "events",
) -> Filter:
```

**After**:
```python
@classmethod
def equals(
    cls,
    property: str | CustomPropertyRef | InlineCustomProperty,
    value: str | list[str],
    *,
    resource_type: Literal["events", "people"] = "events",
) -> Filter:
```

**Backward-compatible**: All existing calls pass `str`, which is still in the union.

---

## 4. Builder Changes — Exact Specifications

### 4.1 `build_filter_entry()` — Custom Property in Filters

**File**: `src/mixpanel_data/_internal/bookmark_builders.py`

**Current implementation** (line 220-253):
```python
def build_filter_entry(f: Filter) -> dict[str, Any]:
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
```

**New implementation**:
```python
def build_filter_entry(f: Filter) -> dict[str, Any]:
    """Convert a Filter object to a bookmark filter dict.

    Handles three property types:
    - ``str``: Raw property name → standard filter entry
    - ``CustomPropertyRef``: Saved CP → adds ``customPropertyId``
    - ``InlineCustomProperty``: Ad-hoc CP → adds ``customProperty`` dict

    Args:
        f: A ``Filter`` object constructed via its class methods.

    Returns:
        Bookmark filter dict.
    """
    entry: dict[str, Any] = {
        "filterType": f._property_type,
        "defaultType": f._property_type,
        "filterValue": f._value,
        "filterOperator": f._operator,
    }

    prop = f._property
    if isinstance(prop, CustomPropertyRef):
        entry["customPropertyId"] = prop.id
        entry["resourceType"] = f._resource_type
    elif isinstance(prop, InlineCustomProperty):
        cp_type = prop.property_type or f._property_type
        entry["customProperty"] = {
            "displayFormula": prop.formula,
            "composedProperties": _build_composed_properties(prop.inputs),
            "propertyType": cp_type,
            "resourceType": prop.resource_type,
        }
        entry["filterType"] = cp_type
        entry["defaultType"] = cp_type
        entry["resourceType"] = prop.resource_type
    else:
        # Plain string property
        entry["value"] = prop
        entry["resourceType"] = f._resource_type

    if f._date_unit is not None:
        entry["filterDateUnit"] = f._date_unit
    return entry
```

**Bookmark JSON output — plain string** (unchanged):
```json
{
    "resourceType": "events",
    "filterType": "number",
    "defaultType": "number",
    "value": "amount",
    "filterValue": 100,
    "filterOperator": "is greater than"
}
```

**Bookmark JSON output — `CustomPropertyRef(42)`**:
```json
{
    "customPropertyId": 42,
    "resourceType": "events",
    "filterType": "number",
    "defaultType": "number",
    "filterValue": 100,
    "filterOperator": "is greater than"
}
```

**Bookmark JSON output — `InlineCustomProperty`**:
```json
{
    "customProperty": {
        "displayFormula": "A * B",
        "composedProperties": {
            "A": {"value": "price", "type": "number", "resourceType": "event"},
            "B": {"value": "quantity", "type": "number", "resourceType": "event"}
        },
        "propertyType": "number",
        "resourceType": "events"
    },
    "resourceType": "events",
    "filterType": "number",
    "defaultType": "number",
    "filterValue": 100,
    "filterOperator": "is greater than"
}
```

### 4.2 `build_group_section()` — Custom Property in Group-By

**File**: `src/mixpanel_data/_internal/bookmark_builders.py`

**Current `GroupBy` branch** (line 194-210):
```python
elif isinstance(g, GroupBy):
    group_entry: dict[str, Any] = {
        "value": g.property,
        "propertyName": g.property,
        "resourceType": "events",
        "propertyType": g.property_type,
        "propertyDefaultType": g.property_type,
    }
    if g.bucket_size is not None:
        group_entry["customBucket"] = {"bucketSize": g.bucket_size}
        if g.bucket_min is not None:
            group_entry["customBucket"]["min"] = g.bucket_min
        if g.bucket_max is not None:
            group_entry["customBucket"]["max"] = g.bucket_max
    group_section.append(group_entry)
```

**New `GroupBy` branch**:
```python
elif isinstance(g, GroupBy):
    prop = g.property

    if isinstance(prop, CustomPropertyRef):
        group_entry: dict[str, Any] = {
            "customPropertyId": prop.id,
            "propertyType": g.property_type,
            "propertyDefaultType": g.property_type,
            "isHidden": False,
        }
    elif isinstance(prop, InlineCustomProperty):
        cp_type = prop.property_type or g.property_type
        group_entry = {
            "customProperty": {
                "displayFormula": prop.formula,
                "composedProperties": _build_composed_properties(
                    prop.inputs
                ),
                "propertyType": cp_type,
                "resourceType": prop.resource_type,
            },
            "propertyType": cp_type,
            "propertyDefaultType": cp_type,
            "isHidden": False,
        }
    else:
        # Plain string property
        group_entry = {
            "value": prop,
            "propertyName": prop,
            "resourceType": "events",
            "propertyType": g.property_type,
            "propertyDefaultType": g.property_type,
        }

    # Bucketing applies to all property types
    if g.bucket_size is not None:
        group_entry["customBucket"] = {"bucketSize": g.bucket_size}
        if g.bucket_min is not None:
            group_entry["customBucket"]["min"] = g.bucket_min
        if g.bucket_max is not None:
            group_entry["customBucket"]["max"] = g.bucket_max

    group_section.append(group_entry)
```

**Bookmark JSON output — plain string** (unchanged):
```json
{
    "value": "country",
    "propertyName": "country",
    "resourceType": "events",
    "propertyType": "string",
    "propertyDefaultType": "string"
}
```

**Bookmark JSON output — `CustomPropertyRef(42)`**:
```json
{
    "customPropertyId": 42,
    "propertyType": "number",
    "propertyDefaultType": "number",
    "isHidden": false
}
```

**Bookmark JSON output — `InlineCustomProperty` with bucketing**:
```json
{
    "customProperty": {
        "displayFormula": "A * B",
        "composedProperties": {
            "A": {"value": "price", "type": "number", "resourceType": "event"},
            "B": {"value": "quantity", "type": "number", "resourceType": "event"}
        },
        "propertyType": "number",
        "resourceType": "events"
    },
    "propertyType": "number",
    "propertyDefaultType": "number",
    "isHidden": false,
    "customBucket": {"bucketSize": 100, "min": 0, "max": 1000}
}
```

### 4.3 Measurement Property — Custom Property in Metric Aggregation

**File**: `src/mixpanel_data/workspace.py`, `_build_query_params()` method

**Current measurement property construction** (line ~1727-1732):
```python
measurement: dict[str, Any] = {"math": bookmark_math}
if item_prop is not None:
    measurement["property"] = {
        "name": item_prop,
        "resourceType": "events",
    }
```

**New measurement property construction**:
```python
measurement: dict[str, Any] = {"math": bookmark_math}
if item_prop is not None:
    if isinstance(item_prop, CustomPropertyRef):
        measurement["property"] = {
            "customPropertyId": item_prop.id,
            "resourceType": "events",
        }
    elif isinstance(item_prop, InlineCustomProperty):
        measurement["property"] = {
            "customProperty": {
                "displayFormula": item_prop.formula,
                "composedProperties": _build_composed_properties(
                    item_prop.inputs
                ),
                "propertyType": item_prop.property_type,
            },
            "resourceType": item_prop.resource_type,
        }
    else:
        # Plain string property
        measurement["property"] = {
            "name": item_prop,
            "resourceType": "events",
        }
```

**Same pattern applies to** `_build_funnel_params()` (line ~2321-2331) measurement block.

**Bookmark JSON output — plain string** (unchanged):
```json
{
    "math": "average",
    "property": {"name": "amount", "resourceType": "events"}
}
```

**Bookmark JSON output — `CustomPropertyRef(42)`**:
```json
{
    "math": "average",
    "property": {"customPropertyId": 42, "resourceType": "events"}
}
```

**Bookmark JSON output — `InlineCustomProperty`**:
```json
{
    "math": "average",
    "property": {
        "customProperty": {
            "displayFormula": "A * B",
            "composedProperties": {
                "A": {"value": "price", "type": "number", "resourceType": "event"},
                "B": {"value": "quantity", "type": "number", "resourceType": "event"}
            },
            "propertyType": "number"
        },
        "resourceType": "events"
    }
}
```

### 4.4 Shared Helper — `_build_composed_properties()`

**File**: `src/mixpanel_data/_internal/bookmark_builders.py` (new function)

```python
def _build_composed_properties(
    inputs: dict[str, PropertyInput],
) -> dict[str, dict[str, str]]:
    """Convert PropertyInput dict to bookmark composedProperties format.

    Each ``PropertyInput`` is mapped to its bookmark JSON representation
    with field name translation: ``name`` → ``value``,
    ``resource_type`` → ``resourceType``.

    Args:
        inputs: Letter-variable to PropertyInput mapping.
            Keys must be single uppercase letters (A-Z).

    Returns:
        Dict mapping letter variables to bookmark-format property dicts.

    Example:
        ```python
        result = _build_composed_properties({
            "A": PropertyInput("price", type="number"),
            "B": PropertyInput("quantity", type="number"),
        })
        # {"A": {"value": "price", "type": "number", "resourceType": "event"},
        #  "B": {"value": "quantity", "type": "number", "resourceType": "event"}}
        ```
    """
    return {
        letter: {
            "value": prop_input.name,
            "type": prop_input.type,
            "resourceType": prop_input.resource_type,
        }
        for letter, prop_input in inputs.items()
    }
```

### 4.5 Import Updates

**File**: `src/mixpanel_data/_internal/bookmark_builders.py` — import line

**Before**:
```python
from mixpanel_data.types import Filter, GroupBy
```

**After**:
```python
from mixpanel_data.types import (
    CustomPropertyRef,
    Filter,
    GroupBy,
    InlineCustomProperty,
    PropertyInput,
)
```

**File**: `src/mixpanel_data/workspace.py` — import from types

Add `CustomPropertyRef`, `InlineCustomProperty`, `PropertyInput` to the existing import block.

**File**: `src/mixpanel_data/__init__.py` — public exports

Add to the existing import and `__all__`:
```python
from mixpanel_data.types import (
    # ... existing imports ...
    CustomPropertyRef,
    InlineCustomProperty,
    PropertyInput,
)
```

---

## 5. Validation Rules

### 5.1 New Rules — Layer 1 (Argument Validation)

All rules raise `ValueError` via `BookmarkValidationError` with a descriptive message at call time, before any API request.

| Code | Rule | Condition | Message |
|------|------|-----------|---------|
| CP1 | CustomPropertyRef.id must be positive | `isinstance(prop, CustomPropertyRef) and prop.id <= 0` | `custom property ID must be a positive integer (got {id})` |
| CP2 | InlineCustomProperty.formula must be non-empty | `isinstance(prop, InlineCustomProperty) and not prop.formula.strip()` | `inline custom property formula must be non-empty` |
| CP3 | InlineCustomProperty.inputs must be non-empty | `isinstance(prop, InlineCustomProperty) and not prop.inputs` | `inline custom property must have at least one input` |
| CP4 | InlineCustomProperty.inputs keys must be single uppercase A-Z | `any(not (len(k) == 1 and k.isupper() and k.isalpha()) for k in prop.inputs)` | `inline custom property input keys must be single uppercase letters (A-Z), got '{key}'` |
| CP5 | Formula max length 20,000 chars | `len(prop.formula) > 20_000` | `inline custom property formula exceeds maximum length of 20,000 characters (got {len})` |
| CP6 | PropertyInput.name must be non-empty | `any(not pi.name.strip() for pi in prop.inputs.values())` | `inline custom property input '{key}' has an empty property name` |

### 5.2 Where Validation Is Applied

Custom property validation must run in **all** resolve-and-build pipelines:

| Pipeline | Where CPs Can Appear | Validation Applied |
|----------|---------------------|--------------------|
| `_resolve_and_build_params()` | `Metric.property`, `group_by`, `where` | CP1-CP6 for each CP found |
| `_resolve_and_build_funnel_params()` | `group_by`, `where` | CP1-CP6 for each CP found |
| `_resolve_and_build_retention_params()` | `group_by`, `where` | CP1-CP6 for each CP found |

### 5.3 Validation Implementation

**File**: `src/mixpanel_data/_internal/validation.py`

Add a new shared helper:

```python
def _validate_custom_property(
    prop: CustomPropertyRef | InlineCustomProperty,
    context: str,
) -> list[ValidationError]:
    """Validate a custom property specification.

    Args:
        prop: The custom property to validate.
        context: Human-readable location (e.g., "group_by[0]",
            "where[1]", "events[0].property").

    Returns:
        List of validation errors (may be empty).
    """
    errors: list[ValidationError] = []

    if isinstance(prop, CustomPropertyRef):
        if prop.id <= 0:
            errors.append(ValidationError(
                path=context,
                message=(
                    f"custom property ID must be a positive integer "
                    f"(got {prop.id})"
                ),
                code="CP1",
                severity="error",
            ))

    elif isinstance(prop, InlineCustomProperty):
        if not prop.formula.strip():
            errors.append(ValidationError(
                path=context,
                message="inline custom property formula must be non-empty",
                code="CP2",
                severity="error",
            ))

        if not prop.inputs:
            errors.append(ValidationError(
                path=context,
                message=(
                    "inline custom property must have at least one input"
                ),
                code="CP3",
                severity="error",
            ))

        for key in prop.inputs:
            if not (len(key) == 1 and key.isupper() and key.isalpha()):
                errors.append(ValidationError(
                    path=f"{context}.inputs",
                    message=(
                        f"inline custom property input keys must be "
                        f"single uppercase letters (A-Z), got '{key}'"
                    ),
                    code="CP4",
                    severity="error",
                ))

        if len(prop.formula) > 20_000:
            errors.append(ValidationError(
                path=context,
                message=(
                    f"inline custom property formula exceeds maximum "
                    f"length of 20,000 characters "
                    f"(got {len(prop.formula)})"
                ),
                code="CP5",
                severity="error",
            ))

        for key, pi in prop.inputs.items():
            if not pi.name.strip():
                errors.append(ValidationError(
                    path=f"{context}.inputs[{key}]",
                    message=(
                        f"inline custom property input '{key}' has "
                        f"an empty property name"
                    ),
                    code="CP6",
                    severity="error",
                ))

    return errors
```

This helper is called from `validate_query_args()`, `validate_funnel_args()`, and `validate_retention_args()` for each custom property found in `group_by`, `where`, or `Metric.property`.

### 5.4 Validation Integration Points

**In `validate_query_args()`** — add after existing group_by/filter validation:

```python
# Validate custom properties in group_by
if group_by is not None:
    groups = group_by if isinstance(group_by, list) else [group_by]
    for i, g in enumerate(groups):
        if isinstance(g, GroupBy) and isinstance(
            g.property, (CustomPropertyRef, InlineCustomProperty)
        ):
            errors.extend(
                _validate_custom_property(g.property, f"group_by[{i}]")
            )

# Validate custom properties in where
if where is not None:
    filters = where if isinstance(where, list) else [where]
    for i, f in enumerate(filters):
        if isinstance(f._property, (CustomPropertyRef, InlineCustomProperty)):
            errors.extend(
                _validate_custom_property(f._property, f"where[{i}]")
            )

# Validate custom properties in Metric.property
for i, item in enumerate(events_list):
    if isinstance(item, Metric) and isinstance(
        item.property, (CustomPropertyRef, InlineCustomProperty)
    ):
        errors.extend(
            _validate_custom_property(
                item.property, f"events[{i}].property"
            )
        )
```

Same pattern for `validate_funnel_args()` and `validate_retention_args()`.

### 5.5 Modified Existing Rules

| Code | Current Rule | Change |
|------|-------------|--------|
| V1 | `math` in `PROPERTY_MATH_TYPES` and `math_property` is `None` | Also check `Metric.property` — allow `CustomPropertyRef` or `InlineCustomProperty` as valid alternatives to `math_property` string |
| V2 | `math_property is not None` and `math` not in `PROPERTY_MATH_TYPES` | Also apply when `Metric.property` is a `CustomPropertyRef` or `InlineCustomProperty` |

---

## 6. Test Specifications (TDD-First)

Tests are organized by implementation phase. **Write all tests in a phase BEFORE implementing the code.**

### 6.1 Test File Structure

```
tests/
├── unit/
│   ├── test_custom_property_types.py     # Phase 1: Type construction & validation
│   ├── test_custom_property_builders.py  # Phase 2: Builder output verification
│   ├── test_custom_property_query.py     # Phase 3: End-to-end query method tests
│   └── test_custom_property_pbt.py       # Phase 4: Property-based tests
```

### 6.2 Phase 1 Tests — Type Construction & Validation

**File**: `tests/unit/test_custom_property_types.py`

```python
"""Tests for custom property types: PropertyInput, InlineCustomProperty, CustomPropertyRef.

TDD Phase 1: Type construction, field defaults, validation rules CP1-CP6.
"""


class TestPropertyInput:
    """PropertyInput construction and field defaults."""

    def test_minimal_construction(self) -> None:
        """PropertyInput with just name uses string/event defaults."""
        pi = PropertyInput("browser")
        assert pi.name == "browser"
        assert pi.type == "string"
        assert pi.resource_type == "event"

    def test_numeric_type(self) -> None:
        """PropertyInput with explicit number type."""
        pi = PropertyInput("price", type="number")
        assert pi.type == "number"

    def test_user_resource_type(self) -> None:
        """PropertyInput with user resource type for profile properties."""
        pi = PropertyInput("plan", resource_type="user")
        assert pi.resource_type == "user"

    def test_all_valid_types(self) -> None:
        """All five property types are accepted."""
        for t in ("string", "number", "boolean", "datetime", "list"):
            pi = PropertyInput("x", type=t)
            assert pi.type == t

    def test_frozen(self) -> None:
        """PropertyInput is immutable."""
        pi = PropertyInput("x")
        with pytest.raises(FrozenInstanceError):
            pi.name = "y"


class TestInlineCustomProperty:
    """InlineCustomProperty construction and convenience methods."""

    def test_minimal_construction(self) -> None:
        """Formula + single input, defaults for property_type and resource_type."""
        cp = InlineCustomProperty(
            formula="A",
            inputs={"A": PropertyInput("browser")},
        )
        assert cp.formula == "A"
        assert cp.property_type is None
        assert cp.resource_type == "events"

    def test_full_construction(self) -> None:
        """All fields explicitly set."""
        cp = InlineCustomProperty(
            formula="A * B",
            inputs={
                "A": PropertyInput("price", type="number"),
                "B": PropertyInput("quantity", type="number"),
            },
            property_type="number",
            resource_type="events",
        )
        assert cp.formula == "A * B"
        assert len(cp.inputs) == 2
        assert cp.property_type == "number"

    def test_numeric_convenience_constructor(self) -> None:
        """InlineCustomProperty.numeric() creates all-number inputs."""
        cp = InlineCustomProperty.numeric("A * B", A="price", B="quantity")
        assert cp.formula == "A * B"
        assert cp.property_type == "number"
        assert cp.inputs["A"].name == "price"
        assert cp.inputs["A"].type == "number"
        assert cp.inputs["A"].resource_type == "event"
        assert cp.inputs["B"].name == "quantity"

    def test_numeric_single_property(self) -> None:
        """numeric() works with a single property reference."""
        cp = InlineCustomProperty.numeric("A", A="amount")
        assert cp.formula == "A"
        assert len(cp.inputs) == 1

    def test_frozen(self) -> None:
        """InlineCustomProperty is immutable."""
        cp = InlineCustomProperty(
            formula="A", inputs={"A": PropertyInput("x")}
        )
        with pytest.raises(FrozenInstanceError):
            cp.formula = "B"


class TestCustomPropertyRef:
    """CustomPropertyRef construction."""

    def test_construction(self) -> None:
        """CustomPropertyRef stores integer ID."""
        ref = CustomPropertyRef(42)
        assert ref.id == 42

    def test_frozen(self) -> None:
        """CustomPropertyRef is immutable."""
        ref = CustomPropertyRef(42)
        with pytest.raises(FrozenInstanceError):
            ref.id = 99


class TestCustomPropertyValidation:
    """Validation rules CP1-CP6 for custom properties."""

    def test_cp1_ref_id_must_be_positive(self, ws: Workspace) -> None:
        """CP1: CustomPropertyRef.id <= 0 raises validation error."""
        with pytest.raises(BookmarkValidationError, match="positive integer"):
            ws.build_params(
                "Login",
                group_by=GroupBy(property=CustomPropertyRef(0)),
            )

    def test_cp1_ref_negative_id(self, ws: Workspace) -> None:
        """CP1: Negative ID also fails."""
        with pytest.raises(BookmarkValidationError, match="positive integer"):
            ws.build_params(
                "Login",
                group_by=GroupBy(property=CustomPropertyRef(-1)),
            )

    def test_cp2_empty_formula(self, ws: Workspace) -> None:
        """CP2: Empty formula string raises validation error."""
        with pytest.raises(BookmarkValidationError, match="non-empty"):
            ws.build_params(
                "Login",
                group_by=GroupBy(
                    property=InlineCustomProperty(
                        formula="",
                        inputs={"A": PropertyInput("x")},
                    )
                ),
            )

    def test_cp2_whitespace_only_formula(self, ws: Workspace) -> None:
        """CP2: Whitespace-only formula fails."""
        with pytest.raises(BookmarkValidationError, match="non-empty"):
            ws.build_params(
                "Login",
                group_by=GroupBy(
                    property=InlineCustomProperty(
                        formula="   ",
                        inputs={"A": PropertyInput("x")},
                    )
                ),
            )

    def test_cp3_empty_inputs(self, ws: Workspace) -> None:
        """CP3: Empty inputs dict raises validation error."""
        with pytest.raises(BookmarkValidationError, match="at least one input"):
            ws.build_params(
                "Login",
                group_by=GroupBy(
                    property=InlineCustomProperty(formula="A", inputs={})
                ),
            )

    def test_cp4_lowercase_key(self, ws: Workspace) -> None:
        """CP4: Lowercase input key raises validation error."""
        with pytest.raises(BookmarkValidationError, match="uppercase"):
            ws.build_params(
                "Login",
                group_by=GroupBy(
                    property=InlineCustomProperty(
                        formula="a",
                        inputs={"a": PropertyInput("x")},
                    )
                ),
            )

    def test_cp4_multi_char_key(self, ws: Workspace) -> None:
        """CP4: Multi-character input key raises validation error."""
        with pytest.raises(BookmarkValidationError, match="uppercase"):
            ws.build_params(
                "Login",
                group_by=GroupBy(
                    property=InlineCustomProperty(
                        formula="AB",
                        inputs={"AB": PropertyInput("x")},
                    )
                ),
            )

    def test_cp4_numeric_key(self, ws: Workspace) -> None:
        """CP4: Numeric input key raises validation error."""
        with pytest.raises(BookmarkValidationError, match="uppercase"):
            ws.build_params(
                "Login",
                group_by=GroupBy(
                    property=InlineCustomProperty(
                        formula="1",
                        inputs={"1": PropertyInput("x")},
                    )
                ),
            )

    def test_cp5_formula_too_long(self, ws: Workspace) -> None:
        """CP5: Formula exceeding 20,000 chars raises validation error."""
        with pytest.raises(BookmarkValidationError, match="20,000"):
            ws.build_params(
                "Login",
                group_by=GroupBy(
                    property=InlineCustomProperty(
                        formula="A" * 20_001,
                        inputs={"A": PropertyInput("x")},
                    )
                ),
            )

    def test_cp6_empty_property_name(self, ws: Workspace) -> None:
        """CP6: Empty property name in input raises validation error."""
        with pytest.raises(BookmarkValidationError, match="empty property name"):
            ws.build_params(
                "Login",
                group_by=GroupBy(
                    property=InlineCustomProperty(
                        formula="A",
                        inputs={"A": PropertyInput("")},
                    )
                ),
            )

    def test_valid_inline_cp_passes(self, ws: Workspace) -> None:
        """Valid InlineCustomProperty passes validation."""
        # Should not raise
        ws.build_params(
            "Login",
            group_by=GroupBy(
                property=InlineCustomProperty(
                    formula="A * B",
                    inputs={
                        "A": PropertyInput("price", type="number"),
                        "B": PropertyInput("quantity", type="number"),
                    },
                    property_type="number",
                ),
                property_type="number",
            ),
        )

    def test_valid_ref_passes(self, ws: Workspace) -> None:
        """Valid CustomPropertyRef passes validation."""
        ws.build_params(
            "Login",
            group_by=GroupBy(property=CustomPropertyRef(42)),
        )

    # --- Position-specific validation ---

    def test_cp_validation_in_where(self, ws: Workspace) -> None:
        """CP validation runs on Filter custom properties."""
        with pytest.raises(BookmarkValidationError, match="positive integer"):
            ws.build_params(
                "Login",
                where=Filter.greater_than(
                    property=CustomPropertyRef(0), value=100,
                ),
            )

    def test_cp_validation_in_metric_property(self, ws: Workspace) -> None:
        """CP validation runs on Metric.property custom properties."""
        with pytest.raises(BookmarkValidationError, match="positive integer"):
            ws.build_params(
                Metric("Login", math="average",
                       property=CustomPropertyRef(-5)),
            )

    def test_cp_validation_in_funnel_group_by(self, ws: Workspace) -> None:
        """CP validation runs in query_funnel group_by."""
        with pytest.raises(BookmarkValidationError, match="non-empty"):
            ws.build_funnel_params(
                ["Signup", "Purchase"],
                group_by=GroupBy(
                    property=InlineCustomProperty(formula="", inputs={"A": PropertyInput("x")}),
                ),
            )

    def test_cp_validation_in_retention_where(self, ws: Workspace) -> None:
        """CP validation runs in query_retention where."""
        with pytest.raises(BookmarkValidationError, match="positive integer"):
            ws.build_retention_params(
                "Signup", "Login",
                where=Filter.equals(
                    property=CustomPropertyRef(0), value="x",
                ),
            )
```

### 6.3 Phase 2 Tests — Builder Output Verification

**File**: `tests/unit/test_custom_property_builders.py`

```python
"""Tests for custom property bookmark JSON output.

TDD Phase 2: Verify build_filter_entry, build_group_section, and
measurement builder produce correct bookmark JSON for custom properties.
"""


class TestBuildFilterEntryCustomProperty:
    """build_filter_entry() with custom property inputs."""

    def test_plain_string_unchanged(self) -> None:
        """Plain string filter produces unchanged output (backward compat)."""
        f = Filter.equals("country", "US")
        entry = build_filter_entry(f)
        assert entry["value"] == "country"
        assert "customPropertyId" not in entry
        assert "customProperty" not in entry

    def test_custom_property_ref(self) -> None:
        """CustomPropertyRef emits customPropertyId in filter entry."""
        f = Filter.greater_than(
            property=CustomPropertyRef(42), value=100,
        )
        entry = build_filter_entry(f)
        assert entry["customPropertyId"] == 42
        assert "value" not in entry
        assert entry["filterOperator"] == "is greater than"
        assert entry["filterValue"] == 100

    def test_inline_custom_property(self) -> None:
        """InlineCustomProperty emits customProperty dict in filter entry."""
        f = Filter.greater_than(
            property=InlineCustomProperty.numeric("A * B", A="price", B="qty"),
            value=1000,
        )
        entry = build_filter_entry(f)
        assert "customProperty" in entry
        cp = entry["customProperty"]
        assert cp["displayFormula"] == "A * B"
        assert "A" in cp["composedProperties"]
        assert cp["composedProperties"]["A"]["value"] == "price"
        assert cp["composedProperties"]["B"]["value"] == "qty"
        assert cp["propertyType"] == "number"
        assert "value" not in entry
        assert entry["filterValue"] == 1000

    def test_inline_cp_filter_type_uses_cp_property_type(self) -> None:
        """When InlineCustomProperty has property_type, filter uses it."""
        f = Filter.equals(
            property=InlineCustomProperty(
                formula='REGEX_EXTRACT(A, "@(.+)$")',
                inputs={"A": PropertyInput("email")},
                property_type="string",
            ),
            value="company.com",
        )
        entry = build_filter_entry(f)
        assert entry["filterType"] == "string"
        assert entry["customProperty"]["propertyType"] == "string"

    def test_ref_preserves_resource_type(self) -> None:
        """CustomPropertyRef preserves the Filter's resource_type."""
        f = Filter.equals(
            property=CustomPropertyRef(42),
            value="Pro",
            resource_type="people",
        )
        entry = build_filter_entry(f)
        assert entry["resourceType"] == "people"

    def test_inline_cp_uses_its_own_resource_type(self) -> None:
        """InlineCustomProperty's resource_type is used."""
        f = Filter.equals(
            property=InlineCustomProperty(
                formula="A",
                inputs={"A": PropertyInput("plan", resource_type="user")},
                resource_type="people",
            ),
            value="Pro",
        )
        entry = build_filter_entry(f)
        assert entry["resourceType"] == "people"


class TestBuildGroupSectionCustomProperty:
    """build_group_section() with custom property inputs."""

    def test_plain_string_unchanged(self) -> None:
        """Plain string group-by produces unchanged output."""
        section = build_group_section("country")
        assert section[0]["value"] == "country"
        assert section[0]["propertyName"] == "country"
        assert "customPropertyId" not in section[0]

    def test_groupby_plain_property_unchanged(self) -> None:
        """GroupBy with plain string property produces unchanged output."""
        section = build_group_section(
            GroupBy("country", property_type="string")
        )
        assert section[0]["value"] == "country"
        assert "customPropertyId" not in section[0]

    def test_groupby_custom_property_ref(self) -> None:
        """GroupBy with CustomPropertyRef emits customPropertyId."""
        section = build_group_section(
            GroupBy(property=CustomPropertyRef(42), property_type="number")
        )
        entry = section[0]
        assert entry["customPropertyId"] == 42
        assert entry["propertyType"] == "number"
        assert "value" not in entry
        assert "propertyName" not in entry

    def test_groupby_inline_custom_property(self) -> None:
        """GroupBy with InlineCustomProperty emits customProperty dict."""
        section = build_group_section(
            GroupBy(
                property=InlineCustomProperty.numeric(
                    "A * B", A="price", B="quantity"
                ),
                property_type="number",
            )
        )
        entry = section[0]
        assert "customProperty" in entry
        cp = entry["customProperty"]
        assert cp["displayFormula"] == "A * B"
        assert cp["composedProperties"]["A"]["value"] == "price"
        assert entry["propertyType"] == "number"
        assert "value" not in entry
        assert "propertyName" not in entry

    def test_groupby_inline_cp_with_bucketing(self) -> None:
        """Bucketing works with inline custom property."""
        section = build_group_section(
            GroupBy(
                property=InlineCustomProperty.numeric("A", A="revenue"),
                property_type="number",
                bucket_size=100,
                bucket_min=0,
                bucket_max=1000,
            )
        )
        entry = section[0]
        assert "customProperty" in entry
        assert entry["customBucket"]["bucketSize"] == 100
        assert entry["customBucket"]["min"] == 0
        assert entry["customBucket"]["max"] == 1000

    def test_groupby_ref_with_bucketing(self) -> None:
        """Bucketing works with CustomPropertyRef."""
        section = build_group_section(
            GroupBy(
                property=CustomPropertyRef(42),
                property_type="number",
                bucket_size=50,
            )
        )
        entry = section[0]
        assert entry["customPropertyId"] == 42
        assert entry["customBucket"]["bucketSize"] == 50

    def test_inline_cp_property_type_overrides_groupby_type(self) -> None:
        """InlineCustomProperty.property_type takes precedence over GroupBy.property_type."""
        section = build_group_section(
            GroupBy(
                property=InlineCustomProperty(
                    formula='IF(A > 100, "High", "Low")',
                    inputs={"A": PropertyInput("amount", type="number")},
                    property_type="string",
                ),
                property_type="number",  # GroupBy says number
            )
        )
        entry = section[0]
        # CP's property_type ("string") should win
        assert entry["propertyType"] == "string"
        assert entry["customProperty"]["propertyType"] == "string"

    def test_multiple_groups_mixed_types(self) -> None:
        """List of mixed plain/ref/inline groups all build correctly."""
        section = build_group_section([
            "country",
            GroupBy(property=CustomPropertyRef(42), property_type="number"),
            GroupBy(
                property=InlineCustomProperty.numeric("A", A="revenue"),
                property_type="number",
            ),
        ])
        assert len(section) == 3
        assert section[0]["value"] == "country"
        assert section[1]["customPropertyId"] == 42
        assert "customProperty" in section[2]


class TestMeasurementPropertyCustomProperty:
    """Measurement property in _build_query_params() with custom properties."""

    def test_plain_string_property_unchanged(self, ws: Workspace) -> None:
        """Plain string math_property produces unchanged measurement."""
        params = ws._build_query_params(
            events=[Metric("Purchase", math="average", property="amount")],
            math="total", math_property=None, per_user=None,
            from_date=None, to_date=None, last=30, unit="day",
            group_by=None, where=None, formulas=[], rolling=None,
            cumulative=False, mode="timeseries",
        )
        prop = params["sections"]["show"][0]["measurement"]["property"]
        assert prop["name"] == "amount"
        assert prop["resourceType"] == "events"
        assert "customPropertyId" not in prop

    def test_custom_property_ref_in_measurement(self, ws: Workspace) -> None:
        """CustomPropertyRef in Metric.property emits customPropertyId."""
        params = ws._build_query_params(
            events=[Metric("Purchase", math="average",
                           property=CustomPropertyRef(42))],
            math="total", math_property=None, per_user=None,
            from_date=None, to_date=None, last=30, unit="day",
            group_by=None, where=None, formulas=[], rolling=None,
            cumulative=False, mode="timeseries",
        )
        prop = params["sections"]["show"][0]["measurement"]["property"]
        assert prop["customPropertyId"] == 42
        assert prop["resourceType"] == "events"
        assert "name" not in prop

    def test_inline_cp_in_measurement(self, ws: Workspace) -> None:
        """InlineCustomProperty in Metric.property emits customProperty dict."""
        params = ws._build_query_params(
            events=[Metric(
                "Purchase", math="average",
                property=InlineCustomProperty.numeric(
                    "A * B", A="price", B="quantity",
                ),
            )],
            math="total", math_property=None, per_user=None,
            from_date=None, to_date=None, last=30, unit="day",
            group_by=None, where=None, formulas=[], rolling=None,
            cumulative=False, mode="timeseries",
        )
        prop = params["sections"]["show"][0]["measurement"]["property"]
        assert "customProperty" in prop
        assert prop["customProperty"]["displayFormula"] == "A * B"
        assert prop["resourceType"] == "events"
        assert "name" not in prop

    def test_top_level_math_property_str_unchanged(self, ws: Workspace) -> None:
        """Top-level math_property as str still works (backward compat)."""
        params = ws._build_query_params(
            events=["Purchase"],
            math="average", math_property="amount", per_user=None,
            from_date=None, to_date=None, last=30, unit="day",
            group_by=None, where=None, formulas=[], rolling=None,
            cumulative=False, mode="timeseries",
        )
        prop = params["sections"]["show"][0]["measurement"]["property"]
        assert prop["name"] == "amount"


class TestBuildComposedProperties:
    """_build_composed_properties() helper."""

    def test_single_input(self) -> None:
        """Single input produces single-entry dict."""
        result = _build_composed_properties({
            "A": PropertyInput("browser", type="string"),
        })
        assert result == {
            "A": {"value": "browser", "type": "string", "resourceType": "event"},
        }

    def test_multiple_inputs(self) -> None:
        """Multiple inputs produce multi-entry dict."""
        result = _build_composed_properties({
            "A": PropertyInput("price", type="number"),
            "B": PropertyInput("quantity", type="number"),
        })
        assert len(result) == 2
        assert result["A"]["value"] == "price"
        assert result["B"]["value"] == "quantity"

    def test_user_resource_type(self) -> None:
        """User resource type is preserved."""
        result = _build_composed_properties({
            "A": PropertyInput("plan", type="string", resource_type="user"),
        })
        assert result["A"]["resourceType"] == "user"
```

### 6.4 Phase 3 Tests — End-to-End Query Method Tests

**File**: `tests/unit/test_custom_property_query.py`

```python
"""End-to-end tests for custom properties in query(), query_funnel(), query_retention().

TDD Phase 3: Verify the full pipeline from public API → build_params → bookmark JSON.
"""


class TestQueryWithCustomPropertyGroupBy:
    """query()/build_params() with custom properties in group_by."""

    def test_build_params_with_ref_group_by(self, ws: Workspace) -> None:
        """build_params() accepts CustomPropertyRef in group_by."""
        params = ws.build_params(
            "Purchase",
            group_by=GroupBy(property=CustomPropertyRef(42), property_type="number"),
        )
        group = params["sections"]["group"][0]
        assert group["customPropertyId"] == 42

    def test_build_params_with_inline_cp_group_by(self, ws: Workspace) -> None:
        """build_params() accepts InlineCustomProperty in group_by."""
        params = ws.build_params(
            "Purchase",
            group_by=GroupBy(
                property=InlineCustomProperty.numeric("A * B", A="price", B="qty"),
                property_type="number",
                bucket_size=100,
            ),
        )
        group = params["sections"]["group"][0]
        assert "customProperty" in group
        assert group["customBucket"]["bucketSize"] == 100


class TestQueryWithCustomPropertyFilter:
    """query()/build_params() with custom properties in where."""

    def test_build_params_with_ref_filter(self, ws: Workspace) -> None:
        """build_params() accepts CustomPropertyRef in where."""
        params = ws.build_params(
            "Purchase",
            where=Filter.greater_than(
                property=CustomPropertyRef(42), value=100,
            ),
        )
        filt = params["sections"]["filter"][0]
        assert filt["customPropertyId"] == 42

    def test_build_params_with_inline_cp_filter(self, ws: Workspace) -> None:
        """build_params() accepts InlineCustomProperty in where."""
        params = ws.build_params(
            "Purchase",
            where=Filter.greater_than(
                property=InlineCustomProperty.numeric("A * B", A="price", B="qty"),
                value=1000,
            ),
        )
        filt = params["sections"]["filter"][0]
        assert "customProperty" in filt


class TestQueryWithCustomPropertyMeasurement:
    """query()/build_params() with custom properties in Metric.property."""

    def test_build_params_with_ref_metric_property(self, ws: Workspace) -> None:
        """build_params() accepts CustomPropertyRef in Metric.property."""
        params = ws.build_params(
            Metric("Purchase", math="average", property=CustomPropertyRef(42)),
        )
        measurement = params["sections"]["show"][0]["measurement"]
        assert measurement["property"]["customPropertyId"] == 42

    def test_build_params_with_inline_cp_metric_property(self, ws: Workspace) -> None:
        """build_params() accepts InlineCustomProperty in Metric.property."""
        params = ws.build_params(
            Metric(
                "Purchase", math="average",
                property=InlineCustomProperty.numeric("A * B", A="price", B="qty"),
            ),
        )
        measurement = params["sections"]["show"][0]["measurement"]
        assert "customProperty" in measurement["property"]


class TestFunnelWithCustomPropertyGroupBy:
    """query_funnel()/build_funnel_params() with custom properties."""

    def test_build_funnel_params_with_ref_group_by(self, ws: Workspace) -> None:
        """build_funnel_params() accepts CustomPropertyRef in group_by."""
        params = ws.build_funnel_params(
            ["Signup", "Purchase"],
            group_by=GroupBy(property=CustomPropertyRef(42), property_type="number"),
        )
        group = params["sections"]["group"][0]
        assert group["customPropertyId"] == 42

    def test_build_funnel_params_with_inline_cp_group_by(self, ws: Workspace) -> None:
        """build_funnel_params() accepts InlineCustomProperty in group_by."""
        params = ws.build_funnel_params(
            ["Signup", "Purchase"],
            group_by=GroupBy(
                property=InlineCustomProperty.numeric("A", A="revenue"),
                property_type="number",
            ),
        )
        group = params["sections"]["group"][0]
        assert "customProperty" in group


class TestRetentionWithCustomPropertyGroupBy:
    """query_retention()/build_retention_params() with custom properties."""

    def test_build_retention_params_with_ref_group_by(self, ws: Workspace) -> None:
        """build_retention_params() accepts CustomPropertyRef in group_by."""
        params = ws.build_retention_params(
            "Signup", "Login",
            group_by=GroupBy(property=CustomPropertyRef(42)),
        )
        group = params["sections"]["group"][0]
        assert group["customPropertyId"] == 42


class TestCombinedCustomProperties:
    """Multiple custom properties in different positions."""

    def test_ref_in_group_and_inline_in_filter(self, ws: Workspace) -> None:
        """CustomPropertyRef in group_by + InlineCustomProperty in where."""
        params = ws.build_params(
            "Purchase",
            group_by=GroupBy(property=CustomPropertyRef(42), property_type="number"),
            where=Filter.greater_than(
                property=InlineCustomProperty.numeric("A * B", A="price", B="qty"),
                value=100,
            ),
        )
        assert params["sections"]["group"][0]["customPropertyId"] == 42
        assert "customProperty" in params["sections"]["filter"][0]

    def test_all_three_positions(self, ws: Workspace) -> None:
        """Custom properties in group_by, where, AND Metric.property."""
        params = ws.build_params(
            Metric("Purchase", math="average", property=CustomPropertyRef(99)),
            group_by=GroupBy(
                property=InlineCustomProperty.numeric("A", A="revenue"),
                property_type="number",
            ),
            where=Filter.equals(
                property=CustomPropertyRef(42),
                value="Premium",
            ),
        )
        assert params["sections"]["show"][0]["measurement"]["property"]["customPropertyId"] == 99
        assert "customProperty" in params["sections"]["group"][0]
        assert params["sections"]["filter"][0]["customPropertyId"] == 42
```

### 6.5 Phase 4 Tests — Property-Based Tests (Hypothesis)

**File**: `tests/unit/test_custom_property_pbt.py`

```python
"""Property-based tests for custom property types.

TDD Phase 4: Verify invariants across randomly generated inputs.
"""

from hypothesis import given, strategies as st


# Strategy for valid PropertyInput
valid_property_input = st.builds(
    PropertyInput,
    name=st.text(min_size=1, max_size=50).filter(lambda s: s.strip()),
    type=st.sampled_from(["string", "number", "boolean", "datetime", "list"]),
    resource_type=st.sampled_from(["event", "user"]),
)

# Strategy for valid input letter keys (A-Z)
valid_input_key = st.sampled_from(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))

# Strategy for valid inputs dict (1-5 entries)
valid_inputs = st.dictionaries(
    keys=valid_input_key,
    values=valid_property_input,
    min_size=1,
    max_size=5,
)


class TestPropertyInputPBT:
    """Property-based tests for PropertyInput."""

    @given(
        name=st.text(min_size=1, max_size=100),
        type_=st.sampled_from(["string", "number", "boolean", "datetime", "list"]),
        resource_type=st.sampled_from(["event", "user"]),
    )
    def test_round_trip_fields(self, name: str, type_: str, resource_type: str) -> None:
        """All field values survive construction."""
        pi = PropertyInput(name=name, type=type_, resource_type=resource_type)
        assert pi.name == name
        assert pi.type == type_
        assert pi.resource_type == resource_type


class TestInlineCustomPropertyPBT:
    """Property-based tests for InlineCustomProperty."""

    @given(
        formula=st.text(min_size=1, max_size=100),
        inputs=valid_inputs,
    )
    def test_construction_preserves_fields(
        self, formula: str, inputs: dict[str, PropertyInput]
    ) -> None:
        """Construction preserves formula and inputs."""
        cp = InlineCustomProperty(formula=formula, inputs=inputs)
        assert cp.formula == formula
        assert cp.inputs == inputs


class TestBuildComposedPropertiesPBT:
    """Property-based tests for _build_composed_properties."""

    @given(inputs=valid_inputs)
    def test_output_keys_match_input_keys(
        self, inputs: dict[str, PropertyInput]
    ) -> None:
        """Output dict has exactly the same keys as input dict."""
        result = _build_composed_properties(inputs)
        assert set(result.keys()) == set(inputs.keys())

    @given(inputs=valid_inputs)
    def test_output_values_have_required_fields(
        self, inputs: dict[str, PropertyInput]
    ) -> None:
        """Each output entry has value, type, resourceType fields."""
        result = _build_composed_properties(inputs)
        for key, entry in result.items():
            assert "value" in entry
            assert "type" in entry
            assert "resourceType" in entry
            assert entry["value"] == inputs[key].name
            assert entry["type"] == inputs[key].type
            assert entry["resourceType"] == inputs[key].resource_type
```

---

## 7. Implementation Phases

Each phase follows strict TDD: write tests first, then implement until green, then refactor.

### Phase 1: New Types (Estimated: ~150 lines impl, ~200 lines tests)

**Tests first**: `tests/unit/test_custom_property_types.py` — `TestPropertyInput`, `TestInlineCustomProperty`, `TestCustomPropertyRef`

**Then implement** in `src/mixpanel_data/types.py`:
1. Add `PropertyInput` frozen dataclass (after existing type aliases, before `Metric`)
2. Add `InlineCustomProperty` frozen dataclass with `numeric()` classmethod
3. Add `CustomPropertyRef` frozen dataclass
4. Add `PropertySpec` type alias

**Verify**: All type construction and field-default tests pass. Freeze tests pass.

### Phase 2: Modified Types (Estimated: ~50 lines changes, ~100 lines tests)

**Tests first**: `tests/unit/test_custom_property_types.py` — `TestCustomPropertyValidation` (at least the tests that verify `build_params` accepts the new types — these will fail until builders are updated, so mark them `@pytest.mark.skip` initially and unskip in Phase 4)

**Then implement** type signature changes:
1. `Metric.property`: `str | None` → `str | CustomPropertyRef | InlineCustomProperty | None`
2. `GroupBy.property`: `str` → `str | CustomPropertyRef | InlineCustomProperty`
3. `Filter._property`: `str` → `str | CustomPropertyRef | InlineCustomProperty`
4. All 18 `Filter` class methods: `property: str` → `property: str | CustomPropertyRef | InlineCustomProperty`

**Verify**: `just typecheck` passes (mypy). Existing tests still pass (backward-compatible).

### Phase 3: Builders (Estimated: ~150 lines impl, ~250 lines tests)

**Tests first**: `tests/unit/test_custom_property_builders.py` — all builder output tests

**Then implement** in `src/mixpanel_data/_internal/bookmark_builders.py`:
1. Add `_build_composed_properties()` helper function
2. Update `build_filter_entry()` — three-branch isinstance dispatch
3. Update `build_group_section()` — three-branch isinstance dispatch in `GroupBy` case
4. Update imports

**Then implement** in `src/mixpanel_data/workspace.py`:
5. Update measurement property construction in `_build_query_params()` — three-branch isinstance dispatch
6. Update measurement property construction in `_build_funnel_params()` — same pattern
7. Update imports

**Verify**: All builder output tests pass. Existing builder tests still pass.

### Phase 4: Validation (Estimated: ~100 lines impl, ~200 lines tests)

**Tests first**: Unskip validation tests from Phase 2. Add remaining validation tests.

**Then implement** in `src/mixpanel_data/_internal/validation.py`:
1. Add `_validate_custom_property()` helper function
2. Add custom property validation calls in `validate_query_args()`
3. Add custom property validation calls in `validate_funnel_args()`
4. Add custom property validation calls in `validate_retention_args()`
5. Update imports

**Verify**: All validation tests (CP1-CP6) pass. All position-specific validation tests pass.

### Phase 5: End-to-End & Exports (Estimated: ~30 lines impl, ~200 lines tests)

**Tests first**: `tests/unit/test_custom_property_query.py` — all end-to-end tests

**Then implement**:
1. Update `src/mixpanel_data/__init__.py` — add exports
2. Verify `_resolve_and_build_params()` type guards accept the new union types (may need to update isinstance checks)
3. Same for `_resolve_and_build_funnel_params()` and `_resolve_and_build_retention_params()`

**Verify**: All end-to-end tests pass. All existing tests still pass. `just check` green.

### Phase 6: PBT & Polish (Estimated: ~150 lines tests)

**Implement**: `tests/unit/test_custom_property_pbt.py` — all Hypothesis tests

**Then**:
1. Run `just test-pbt` — verify PBT passes
2. Run `just test-cov` — verify coverage >= 90%
3. Run `just mutate` on new code — target 80%+ mutation score
4. Final `just check` — all green

---

## 8. Dependency Graph

```
Phase 1: New Types
    │
    ├─── Phase 2: Modified Types (depends on Phase 1 types)
    │        │
    │        └─── Phase 4: Validation (depends on modified types)
    │
    └─── Phase 3: Builders (depends on Phase 1 types)
             │
             └─── Phase 5: E2E & Exports (depends on builders + validation)
                      │
                      └─── Phase 6: PBT & Polish (depends on everything)
```

Phases 2 and 3 can proceed in parallel after Phase 1 is complete.

---

## 9. Files Changed Summary

| File | Change Type | Scope |
|------|------------|-------|
| `src/mixpanel_data/types.py` | **Modified** | Add 3 new types, 1 type alias; modify `Metric.property`, `GroupBy.property`, `Filter._property` + 18 class methods |
| `src/mixpanel_data/_internal/bookmark_builders.py` | **Modified** | Add `_build_composed_properties()`; modify `build_filter_entry()`, `build_group_section()`; update imports |
| `src/mixpanel_data/workspace.py` | **Modified** | Modify measurement property builder in `_build_query_params()` and `_build_funnel_params()`; update imports |
| `src/mixpanel_data/_internal/validation.py` | **Modified** | Add `_validate_custom_property()`; add CP validation calls in 3 validate functions |
| `src/mixpanel_data/__init__.py` | **Modified** | Add exports: `CustomPropertyRef`, `InlineCustomProperty`, `PropertyInput` |
| `tests/unit/test_custom_property_types.py` | **New** | ~400 lines |
| `tests/unit/test_custom_property_builders.py` | **New** | ~300 lines |
| `tests/unit/test_custom_property_query.py` | **New** | ~200 lines |
| `tests/unit/test_custom_property_pbt.py` | **New** | ~100 lines |

**Total implementation**: ~480 lines of production code
**Total tests**: ~1,000 lines of test code

---

## 10. Acceptance Criteria

- [ ] `PropertyInput`, `InlineCustomProperty`, `CustomPropertyRef` types are frozen dataclasses
- [ ] `InlineCustomProperty.numeric()` convenience constructor works
- [ ] `Metric.property` accepts `str | CustomPropertyRef | InlineCustomProperty | None`
- [ ] `GroupBy.property` accepts `str | CustomPropertyRef | InlineCustomProperty`
- [ ] All 18 `Filter` class methods accept `str | CustomPropertyRef | InlineCustomProperty` as first arg
- [ ] `build_filter_entry()` emits correct JSON for all 3 property types
- [ ] `build_group_section()` emits correct JSON for all 3 property types
- [ ] Measurement property in `_build_query_params()` emits correct JSON for all 3 property types
- [ ] Measurement property in `_build_funnel_params()` emits correct JSON for all 3 property types
- [ ] Validation rules CP1-CP6 catch all invalid inputs with descriptive messages
- [ ] Validation runs in `validate_query_args()`, `validate_funnel_args()`, `validate_retention_args()`
- [ ] All existing tests pass unchanged (backward compatibility)
- [ ] `just check` passes (lint + typecheck + test)
- [ ] Coverage >= 90%
- [ ] New types exported from `mixpanel_data.__init__`
- [ ] All docstrings complete with examples
