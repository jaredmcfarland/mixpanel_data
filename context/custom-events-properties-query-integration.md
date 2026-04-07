# Custom Events & Custom Properties — Query Integration Design

**Date**: 2026-04-06
**Status**: Research Complete — Design Proposal
**Builds on**: `insights-query-api-design.md`, `unified-bookmark-query-design.md`
**Reference**: `analytics/` repo (Mixpanel canonical implementation)

---

## 1. Executive Summary

This document synthesizes deep research into Mixpanel's custom events and custom properties systems, analyzes their integration points with the bookmark query engine, and proposes a typed API design for first-class support in `mixpanel_data`'s query system (`query()`, `query_funnel()`, `query_retention()`, `query_flow()`).

### Key Findings

1. **Custom events are virtual event unions** — named groups of real events with optional per-event property filters. They are stored in the database and expanded at query time into constituent event selectors.

2. **Custom properties are virtual computed properties** — calculated at query time from raw properties using either a **formula** (text-based arb-selector expression language) or a **behavioral aggregation** (e.g., "total purchases in last 30 days").

3. **Inline custom properties are a first-class feature** — the Mixpanel query engine natively supports inline `customProperty` definitions in bookmark params alongside persisted `customPropertyId` references. This is not a hack; it's the primary path for "Apply without Save" in the UI.

4. **Inline custom events are NOT supported for insights/retention** — insights and retention queries resolve custom events by database ID only (`$custom_event:{id}`). Funnels have a partial inline path via the `alternatives` key in event selectors, but this is internal plumbing rather than a documented user-facing feature.

5. **The existing query system has clear extension points** — the `_build_*_params()` methods, `build_filter_entry()`, `build_group_section()`, and the `Metric`/`FunnelStep`/`RetentionEvent`/`FlowStep` types all have natural places to accept custom event references and custom property specifications.

### Design Recommendation

- **Custom events**: Reference-by-ID approach across all query types. Add `CustomEventRef` type. Inline custom events for funnels as a stretch goal.
- **Custom properties**: Dual-path approach — reference saved CPs by ID (`CustomPropertyRef`) AND define inline CPs with formulas (`InlineCustomProperty`). Both are natively supported by the query engine.
- **CRUD gap**: Add `create_custom_event()` and `get_custom_event()` to Workspace (currently missing) to complete the create-then-reference workflow.

---

## 2. Research Findings: Custom Events

### 2.1 What Custom Events Are

Custom events are **virtual/computed events** that do not exist in the raw event stream. A custom event is a **named union of one or more real events** (called "alternatives"), each optionally filtered by property conditions. They are sometimes called "event groups."

Key characteristics:
- Canonical name format: `$custom_event:{id}` (e.g., `$custom_event:42`)
- Stored in the `custom_events_customevent` and `custom_events_alternative` database tables
- At query time, expanded into constituent event selectors (a list of `{event, selector}` pairs)
- Can be **nested**: an alternative can reference another custom event via `$custom_event:{id}` as the event name
- Cycle detection prevents circular references
- Maximum 25 alternatives per custom event (`MAX_NUMBER_OF_ALTERNATIVES = 25`)

### 2.2 Data Model

**Django Models** (`analytics/webapp/custom_events/models.py`):

| Table | Key Fields |
|-------|-----------|
| `CustomEvent` | `id`, `name`, `project`, `workspace`, `creator`, `deleted` (soft), `is_visibility_restricted`, `is_modification_restricted` |
| `Alternative` | `custom_event` (FK), `event` (str), `serialized` (selector expression), `valid_segfilter` (JSON segfilter) |

**API JSON shape** (from `to_json()`):
```json
{
    "id": 42,
    "name": "Signup or Login",
    "deleted": 0,
    "project_id": 123,
    "alternatives": [
        {"event": "Signup"},
        {"event": "Login", "valid_segfilter": {"op": "and", "filters": [...]}},
        {"event": "$custom_event:10"}
    ],
    "is_collect_everything_event": false,
    "is_visibility_restricted": false,
    "user_id": 456
}
```

### 2.3 Custom Event Composition

| Composition Type | Example | Semantics |
|-----------------|---------|-----------|
| **Event union** | `[{"event": "Signup"}, {"event": "Register"}]` | Match ANY of these events (OR logic) |
| **Filtered event** | `[{"event": "Purchase", "valid_segfilter": {"op":"and","filters":[...]}}]` | Match event + property conditions |
| **Nesting** | `[{"event": "$custom_event:10"}, {"event": "Direct Signup"}]` | Include all events from another custom event |
| **All events with filter** | `[{"event": "$all_events", "valid_segfilter": {...}}]` | Match all events passing filter |

### 2.4 How Custom Events Appear in Bookmark Params

**In `sections.show[].behavior`:**
```json
{
    "behavior": {
        "type": "custom-event",
        "name": "$custom_event:42",
        "id": 42,
        "resourceType": "events",
        "filtersDeterminer": "all",
        "filters": [],
        "dataGroupId": null,
        "dataset": "$mixpanel"
    },
    "measurement": {
        "math": "total",
        "property": null
    }
}
```

**Differences from a regular event:**

| Field | Regular Event | Custom Event |
|-------|--------------|-------------|
| `behavior.type` | `"event"` | `"custom-event"` |
| `behavior.name` | `"Login"` | `"$custom_event:{id}"` |
| `behavior.id` | absent | integer DB ID |

**In funnel sub-behaviors** (steps referencing custom events):
```json
{
    "type": "event",
    "name": "$custom_event:42",
    "funnelOrder": "loose"
}
```
Note: funnel sub-behaviors use `type: "event"` with the `$custom_event:{id}` name pattern, not `type: "custom-event"`.

### 2.5 Query-Time Resolution

The expansion happens in `api/version_2_0/custom_events/util.py`:

```
Bookmark param: behavior.name = "$custom_event:42"
    ↓
process_event_selectors() detects $custom_event:\d+ regex
    ↓
get_custom_event(42) — DB lookup (cached)
    ↓
generate_custom_event_selectors() — recursive expansion
    ↓
Result: [{event: "Signup", selector: "..."}, {event: "Login", selector: "..."}]
```

Nested custom events are recursively resolved. Deleted custom events produce `{event: "$deleted_custom_event", selector: "false"}` (always-empty result).

### 2.6 Inline Custom Events — Capability Analysis

| Query Type | Inline Custom Events? | Mechanism |
|-----------|----------------------|-----------|
| **Insights** | **No** | Must be pre-created. `insights_query()` → `process_event_selectors()` resolves by DB ID only. |
| **Funnels** | **Partial** | `funnel_metric_params_util.py:72` passes `alternatives` through in event selectors. This is internal plumbing — the UI always creates/saves first. |
| **Retention** | **No** | Same insights endpoint, same resolution path. |
| **Flows** | **No** | `show_custom_events: True` displays saved custom events in flow graphs but doesn't define them inline. |

**Bottom line**: Custom events must be created and saved (via App API) before they can be used in queries. The reference-by-ID approach is the only reliable path across all query types.

---

## 3. Research Findings: Custom Properties

### 3.1 What Custom Properties Are

Custom properties are **virtual computed properties** that do not exist in raw event or profile data. They are calculated at query time from raw properties using one of two definition types:

1. **Formula-based** (`displayFormula` + `composedProperties`): A text expression in the arb-selector formula language that references raw properties via letter variables (A, B, C...).

2. **Behavior-based** (`behavior`): A behavioral aggregation that computes a value from a user's event stream (e.g., "total count of Login events in the last 30 days").

These two types are **mutually exclusive** — enforced by validation.

### 3.2 Data Model

**Django Model** (`analytics/webapp/custom_properties/models.py`):

| Field | Type | Purpose |
|-------|------|---------|
| `id` | int PK | Unique identifier (`customPropertyId` in API) |
| `name` | str(255) | Display name |
| `description` | str(255) | Optional description |
| `resource_type` | `"events"` or `"people"` | Which data domain (immutable after creation) |
| `property_type` | str | Inferred type: `"string"`, `"number"`, `"boolean"`, `"datetime"`, `"list"` |
| `definition` | JSON | Either `{displayFormula, composedProperties}` or `{behavior}` |
| `data_group_id` | int | For B2B group properties (immutable) |
| `active` | bool | Soft delete flag |
| `is_visible`, `is_locked` | bool | Visibility/lock controls |
| `referenced_custom_properties` | M2M self | Dependency graph (cycle prevention) |

### 3.3 Formula Language (arb-selector)

The formula language is a **text-based expression language** with spreadsheet-like syntax. It is NOT a JSON expression tree. Key capabilities:

| Category | Functions |
|----------|-----------|
| **Arithmetic** | `+`, `-`, `*`, `/`, `%`, `CEIL()`, `FLOOR()`, `ROUND()`, `MAX()`, `MIN()`, `NUMBER()` |
| **String** | `STRING()`, `UPPER()`, `LOWER()`, `LEFT()`, `RIGHT()`, `MID()`, `LEN()`, `SPLIT()`, `HAS_PREFIX()`, `HAS_SUFFIX()`, `REGEX_EXTRACT()`, `REGEX_MATCH()`, `REGEX_REPLACE()`, `PARSE_URL()` |
| **Conditional** | `IF()`, `IFS()` |
| **Boolean** | `AND`, `OR`, `NOT`, `AND()`, `OR()`, `TRUE`, `FALSE`, `IN` |
| **Type** | `BOOLEAN()`, `STRING()`, `NUMBER()`, `TYPEOF()`, `DEFINED()`, `UNDEFINED` |
| **Date/Time** | `TODAY()`, `DATEDIF()` |
| **List** | `ANY()`, `ALL()`, `MAP()`, `FILTER()`, `SUM()`, `LEN()` |
| **Variable** | `LET()` — assign intermediate values |
| **Comparison** | `==`, `!=`, `<`, `>`, `<=`, `>=` |

**Formula + composedProperties example:**
```json
{
    "displayFormula": "A * B",
    "composedProperties": {
        "A": {"resourceType": "event", "type": "number", "value": "price"},
        "B": {"resourceType": "event", "type": "number", "value": "quantity"}
    }
}
```

The letter variables (A, B, C...) in the formula map to entries in `composedProperties`. Each entry specifies the raw property name (`value`), its data type (`type`), and its resource domain (`resourceType`).

### 3.4 Behavior-Based Custom Properties

A behavioral property computes a value from a user's event history:

```json
{
    "behavior": {
        "aggregationOperator": "sum",
        "event": {"value": "Purchase"},
        "property": {"value": "amount"},
        "dateRange": {"type": "in the last", "window": {"unit": "day", "value": 30}},
        "filters": [],
        "filtersOperator": "and"
    }
}
```

| `aggregationOperator` | Output Type | Description |
|----------------------|-------------|-------------|
| `"total"` | number | Count of matching events |
| `"sum"` | number | Sum of property values |
| `"most_frequent"` | string | Most common property value |
| `"first_value"` | string | First occurrence of property value |
| `"first_event_time"` | datetime | Timestamp of first matching event |
| `"scd_value"` | varies | Slowly-changing dimension value |
| `"multi_attribution"` | varies | Attribution model (last touch, participation, etc.) |

### 3.5 Where Custom Properties Appear in Bookmark Params

Custom properties can appear in **three positions**:

**1. In `sections.group[]` (breakdowns):**
```json
{
    "group": [{
        "customPropertyId": 42,
        "customProperty": {"displayFormula": "A * B", "composedProperties": {...}},
        "propertyType": "number",
        "value": null
    }]
}
```

**2. In `sections.filter[]` (filters):**
```json
{
    "filter": [{
        "customPropertyId": "$temp-abc123",
        "customProperty": {"displayFormula": "A", "composedProperties": {...}, "propertyType": "string"},
        "filterOperator": "equals",
        "filterValue": ["Chrome"]
    }]
}
```

**3. In `sections.show[].measurement.property` (metric measurement):**
```json
{
    "measurement": {
        "math": "average",
        "property": {
            "name": "Revenue",
            "resourceType": "events",
            "customPropertyId": 42,
            "customProperty": {"displayFormula": "A * B", "composedProperties": {...}}
        }
    }
}
```

### 3.6 Inline Custom Properties — Capability Analysis

**Inline custom properties are a first-class, natively supported feature.** Evidence:

1. **Frontend `InlineCustomPropertiesStore`** (`iron/common/report/stores/inline-custom-properties-store.ts`): Dedicated store for inline/unsaved custom properties with temporary `$temp-*` IDs.

2. **Detection utilities** (`iron/common/widgets/custom-property-modal/util.ts`): `isPersistedCustomProperty()` (numeric ID) vs `isInlineCustomProperty()` (temp string ID).

3. **Query resolution** (`backend/util/arb_selector.py:630-643`): The `segment_to_arb_selector()` function first checks for `customPropertyId` (DB lookup), then falls through to the inline `customProperty` dict. Both paths produce identical arb-selector expansion.

4. **Internal usage**: Revenue change properties, SCD "any" queries, and experiment properties all dynamically construct inline `customProperty` definitions at query time — proving the inline path is production-grade.

5. **UI workflow**: "Apply without Save" → property is used inline with `$temp-*` ID. "Save" → property gets a real numeric ID. Either way, the query engine handles it identically.

| Query Type | Inline Custom Properties? | Mechanism |
|-----------|--------------------------|-----------|
| **Insights** | **Yes** | `customProperty` field in group/filter/measurement |
| **Funnels** | **Yes** | Same `customProperty` field |
| **Retention** | **Yes** | Same `customProperty` field |
| **Flows** | **No** | Flows use segfilter format; custom properties aren't supported in flows breakdowns |

### 3.7 Query-Time Resolution

For **formula-based** custom properties:
```
customProperty: {displayFormula: "A * B", composedProperties: {A: {value: "price"}, B: {value: "quantity"}}}
    ↓
segment_to_arb_selector() detects customPropertyId or customProperty
    ↓
_expand_formula_property() recursively expands composedProperties
    ↓
substitute_variables() (C parser) replaces A, B with arb-selector expressions
    ↓
Result: arb selector string computing the formula inline
```

For **behavior-based** custom properties:
```
customProperty: {behavior: {aggregationOperator: "sum", event: {value: "Purchase"}, ...}}
    ↓
_raw_behavior_to_arb_selector() converts to computed behavior
    ↓
Registers in QueryBehaviors, returns computed_event reference
    ↓
Result: behavior-backed arb selector
```

---

## 4. Current System Extension Points

### 4.1 Types That Need Extension

| Type | Current `event` Field | Custom Event Support |
|------|----------------------|---------------------|
| `Metric` | `event: str` | Accept `str \| CustomEventRef` |
| `FunnelStep` | `event: str` | Accept `str \| CustomEventRef` |
| `RetentionEvent` | `event: str` | Accept `str \| CustomEventRef` |
| `FlowStep` | `event: str` | Accept `str \| CustomEventRef` |

| Type | Current `property` Field | Custom Property Support |
|------|-------------------------|------------------------|
| `Metric` | `property: str \| None` | Accept `str \| CustomPropertyRef \| InlineCustomProperty \| None` |
| `GroupBy` | `property: str` | Accept `str \| CustomPropertyRef \| InlineCustomProperty` |
| `Filter` class methods | `property: str` (1st arg) | Accept `str \| CustomPropertyRef \| InlineCustomProperty` |

### 4.2 Builders That Need Extension

| Builder | Change Needed |
|---------|--------------|
| `_build_query_params()` | Emit `behavior.type = "custom-event"` and `behavior.id` when `Metric.event` is `CustomEventRef` |
| `_build_funnel_params()` | Emit `$custom_event:{id}` name in funnel sub-behaviors |
| `_build_retention_params()` | Emit `$custom_event:{id}` name in retention behaviors |
| `build_filter_entry()` | Emit `customPropertyId` / `customProperty` when filter uses CP |
| `build_group_section()` | Emit `customPropertyId` / `customProperty` in group clause |
| Metric measurement builder | Emit `customPropertyId` / `customProperty` in measurement.property |

### 4.3 Validation Already Supports `"custom-event"`

The `bookmark_enums.py` already includes `"custom-event"` in `VALID_METRIC_TYPES`:
```python
VALID_METRIC_TYPES = frozenset({
    "event", "simple", "custom-event", "cohort", "people",
    "funnel", "retention", "addiction", "formula", "metric",
})
```

And `validate_bookmark()` Layer 2 already handles it:
```python
if btype in ("event", "simple", "custom-event"):
    # validates behavior has a name
```

### 4.4 CRUD Gap

| Domain | Capability | Status |
|--------|-----------|--------|
| Custom Events | `list_custom_events()` | Exists (via Lexicon data-definitions) |
| Custom Events | `get_custom_event(id)` | **Missing** |
| Custom Events | `create_custom_event(name, alternatives)` | **Missing** |
| Custom Events | `update_custom_event()` | Partial — only Lexicon metadata, NOT alternatives |
| Custom Events | `delete_custom_event()` | Exists |
| Custom Properties | Full CRUD | Complete (`list`, `create`, `get`, `update`, `delete`, `validate`) |

The CRUD gap for custom events is a prerequisite for the reference-by-ID approach. Users need `create_custom_event()` to create the custom event before referencing it in queries.

---

## 5. Proposed Design

### 5.1 New Types

#### `CustomEventRef` — Reference a Saved Custom Event

```python
@dataclass(frozen=True)
class CustomEventRef:
    """Reference to a saved custom event for use in queries.

    Custom events are virtual events that combine multiple real events
    (with optional property filters) into a single queryable entity.
    They must be created first via ``create_custom_event()`` or the
    Mixpanel UI, then referenced by their integer ID.

    Attributes:
        id: The custom event's database ID (from ``create_custom_event()``
            response or ``list_custom_events()``).
        label: Optional display label for query results. If omitted,
            the custom event's saved name is used.

    Examples:
        ```python
        # Reference in a simple query
        result = ws.query(CustomEventRef(42))

        # Reference with aggregation settings
        result = ws.query(Metric(event=CustomEventRef(42), math="unique"))

        # In a funnel
        result = ws.query_funnel([CustomEventRef(42), "Purchase"])

        # In retention
        result = ws.query_retention(
            born_event=CustomEventRef(42),
            return_event="Login",
        )
        ```
    """

    id: int
    label: str | None = None
```

#### `CustomPropertyRef` — Reference a Saved Custom Property

```python
@dataclass(frozen=True)
class CustomPropertyRef:
    """Reference to a saved custom property by ID.

    Use when the custom property already exists in the project
    (created via ``create_custom_property()`` or the Mixpanel UI).
    The query engine fetches the definition by ID at execution time.

    Attributes:
        id: The custom property's ID (``customPropertyId``).
        label: Optional display label. If omitted, uses the saved name.

    Examples:
        ```python
        # As a breakdown dimension
        result = ws.query("Purchase", group_by=GroupBy(
            property=CustomPropertyRef(42)
        ))

        # As an aggregation property
        result = ws.query(Metric(
            "Purchase", math="average",
            property=CustomPropertyRef(42),
        ))

        # As a filter target
        result = ws.query("Purchase", where=Filter.greater_than(
            property=CustomPropertyRef(42), value=100,
        ))
        ```
    """

    id: int
    label: str | None = None
```

#### `PropertyInput` — Input Property for an Inline Custom Property Formula

```python
@dataclass(frozen=True)
class PropertyInput:
    """An input property reference for an inline custom property formula.

    Maps a letter variable in the formula to a raw event or user property.

    Attributes:
        name: The raw property name (e.g., ``"price"``, ``"$browser"``).
        type: Property data type. Default ``"string"``.
        resource_type: Property domain. ``"event"`` for event properties,
            ``"user"`` for user/people properties. Default ``"event"``.

    Examples:
        ```python
        PropertyInput("price", type="number")
        PropertyInput("$browser", type="string")
        PropertyInput("plan", type="string", resource_type="user")
        ```
    """

    name: str
    type: Literal["string", "number", "boolean", "datetime", "list"] = "string"
    resource_type: Literal["event", "user"] = "event"
```

#### `InlineCustomProperty` — Define an Ad-Hoc Computed Property Inline

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
        inputs: Mapping from letter variables to property references.
            Keys must be single uppercase letters A-Z matching the
            formula variables.
        property_type: Result type of the formula. If ``None``, the
            server infers it. Explicit typing improves validation.
        resource_type: Which data domain this property applies to.
            Default ``"events"``.

    Formula Language Reference:
        - Arithmetic: ``+``, ``-``, ``*``, ``/``, ``%``, ``CEIL()``,
          ``FLOOR()``, ``ROUND()``, ``NUMBER()``
        - String: ``UPPER()``, ``LOWER()``, ``LEFT()``, ``RIGHT()``,
          ``MID()``, ``LEN()``, ``SPLIT()``, ``REGEX_EXTRACT()``,
          ``REGEX_MATCH()``, ``REGEX_REPLACE()``, ``PARSE_URL()``
        - Conditional: ``IF(condition, then, else)``,
          ``IFS(c1, v1, c2, v2, ..., TRUE, default)``
        - Boolean: ``AND``, ``OR``, ``NOT``, ``TRUE``, ``FALSE``, ``IN``
        - Type: ``BOOLEAN()``, ``STRING()``, ``NUMBER()``, ``TYPEOF()``,
          ``DEFINED()``, ``UNDEFINED``
        - Date: ``TODAY()``, ``DATEDIF()``
        - List: ``ANY()``, ``ALL()``, ``MAP()``, ``FILTER()``, ``SUM()``

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

        # Use a user property
        InlineCustomProperty(
            formula="A",
            inputs={"A": PropertyInput("plan", type="string", resource_type="user")},
            property_type="string",
        )
        ```
    """

    formula: str
    inputs: dict[str, PropertyInput]
    property_type: Literal["string", "number", "boolean", "datetime"] | None = None
    resource_type: Literal["events", "people"] = "events"

    @classmethod
    def numeric(
        cls,
        formula: str,
        /,
        **properties: str,
    ) -> InlineCustomProperty:
        """Create a numeric formula from named properties.

        Convenience constructor where all inputs are numeric event properties.
        Property names are mapped to formula variables in the order provided.

        Args:
            formula: Formula expression using single-letter variables.
            **properties: Mapping of letter variable to property name.

        Returns:
            An InlineCustomProperty with all-numeric inputs.

        Examples:
            ```python
            # Revenue = price * quantity
            InlineCustomProperty.numeric("A * B", A="price", B="quantity")

            # Profit margin
            InlineCustomProperty.numeric(
                "(A - B) / A * 100", A="revenue", B="cost"
            )
            ```
        """
        return cls(
            formula=formula,
            inputs={k: PropertyInput(v, type="number") for k, v in properties.items()},
            property_type="number",
        )
```

### 5.2 Type Aliases

```python
# Union type for event specification in queries
EventSpec = str | CustomEventRef
"""An event specifier: either a plain event name string or a custom event reference."""

# Union type for property specification in queries
PropertySpec = str | CustomPropertyRef | InlineCustomProperty
"""A property specifier: plain name, saved custom property reference, or inline formula."""
```

### 5.3 Modified Types

#### `Metric` — Accept Custom Events and Custom Properties

```python
@dataclass(frozen=True)
class Metric:
    event: str | CustomEventRef          # CHANGED from str
    math: MathType = "total"
    property: str | CustomPropertyRef | InlineCustomProperty | None = None  # CHANGED from str | None
    per_user: PerUserAggregation | None = None
    percentile_value: int | float | None = None
    filters: list[Filter] | None = None
    filters_combinator: Literal["all", "any"] = "all"
```

**Backward-compatible**: `Metric("Login")` still works (str is in the union). New usage: `Metric(CustomEventRef(42), math="unique")`.

#### `FunnelStep` — Accept Custom Events

```python
@dataclass(frozen=True)
class FunnelStep:
    event: str | CustomEventRef          # CHANGED from str
    label: str | None = None
    filters: list[Filter] | None = None
    filters_combinator: Literal["all", "any"] = "all"
    order: Literal["loose", "any"] | None = None
```

#### `RetentionEvent` — Accept Custom Events

```python
@dataclass(frozen=True)
class RetentionEvent:
    event: str | CustomEventRef          # CHANGED from str
    filters: list[Filter] | None = None
    filters_combinator: Literal["all", "any"] = "all"
```

#### `FlowStep` — Accept Custom Events

```python
@dataclass(frozen=True)
class FlowStep:
    event: str | CustomEventRef          # CHANGED from str
    forward: int | None = None
    reverse: int | None = None
    label: str | None = None
    filters: list[Filter] | None = None
    filters_combinator: Literal["all", "any"] = "all"
```

#### `GroupBy` — Accept Custom Properties

```python
@dataclass(frozen=True)
class GroupBy:
    property: str | CustomPropertyRef | InlineCustomProperty  # CHANGED from str
    property_type: Literal["string", "number", "boolean", "datetime"] = "string"
    bucket_size: int | float | None = None
    bucket_min: int | float | None = None
    bucket_max: int | float | None = None
```

When `property` is a `CustomPropertyRef` or `InlineCustomProperty`, the `property_type` field is still used for bucketing decisions. For `InlineCustomProperty`, if `property_type` is set on the CP, it takes precedence.

#### `Filter` Class Methods — Accept Custom Properties

All `Filter` class methods change their first positional `property` parameter type:

```python
@classmethod
def equals(
    cls,
    property: str | CustomPropertyRef | InlineCustomProperty,  # CHANGED from str
    value: str | list[str],
    *,
    resource_type: Literal["events", "people"] = "events",
) -> Filter:
    """Property equals value (or any value in list)."""
    ...

# Same pattern for: not_equals, contains, not_contains, greater_than,
# less_than, between, is_set, is_not_set, is_true, is_false,
# on, not_on, before, since, in_the_last, not_in_the_last, date_between
```

**Internal storage change**: `_property` field changes from `str` to `str | CustomPropertyRef | InlineCustomProperty`. The builder (`build_filter_entry()`) detects the type and emits the appropriate JSON.

#### `query()` Method Signature — Accept Custom Events

```python
def query(
    self,
    events: str | Metric | CustomEventRef | Sequence[str | Metric | CustomEventRef],  # CHANGED
    *,
    # ... all other params unchanged
) -> QueryResult:
```

**Resolution rules update**:
- `str` → `Metric(event=str, math=<top-level math>, ...)` (unchanged)
- `Metric` → used as-is (unchanged)
- `CustomEventRef` → `Metric(event=CustomEventRef, math=<top-level math>, ...)` (new)

#### `query_funnel()` Method Signature

```python
def query_funnel(
    self,
    steps: Sequence[str | FunnelStep | CustomEventRef],  # CHANGED
    *,
    # ... all other params unchanged
) -> FunnelQueryResult:
```

#### `query_retention()` Method Signature

```python
def query_retention(
    self,
    born_event: str | RetentionEvent | CustomEventRef,   # CHANGED
    return_event: str | RetentionEvent | CustomEventRef,  # CHANGED
    *,
    # ... all other params unchanged
) -> RetentionQueryResult:
```

#### `query_flow()` Method Signature

```python
def query_flow(
    self,
    event: str | FlowStep | CustomEventRef | Sequence[str | FlowStep | CustomEventRef],  # CHANGED
    *,
    # ... all other params unchanged
) -> FlowQueryResult:
```

### 5.4 Bookmark Builder Changes

#### `_build_query_params()` — Custom Event Behavior Block

```python
# Current (regular event only):
behavior = {
    "type": "event",
    "name": event_name,
    "resourceType": "events",
    ...
}

# New (handles both):
if isinstance(resolved_event, CustomEventRef):
    behavior = {
        "type": "custom-event",
        "name": f"$custom_event:{resolved_event.id}",
        "id": resolved_event.id,
        "resourceType": "events",
        ...
    }
else:
    behavior = {
        "type": "event",
        "name": event_name,
        "resourceType": "events",
        ...
    }
```

#### `_build_funnel_params()` — Custom Event in Funnel Steps

```python
# Funnel sub-behaviors use "event" type with $custom_event:{id} name:
if isinstance(step_event, CustomEventRef):
    sub_behavior = {
        "type": "event",
        "name": f"$custom_event:{step_event.id}",
        "funnelOrder": order,
        ...
    }
```

#### `_build_retention_params()` — Custom Event in Retention Behaviors

Same pattern as funnels — use `$custom_event:{id}` as the behavior name.

#### `_build_flow_params()` — Custom Event in Flow Steps

```python
# Flows use flat event selectors:
if isinstance(step_event, CustomEventRef):
    step_dict = {
        "event": f"$custom_event:{step_event.id}",
        ...
    }
```

#### `build_filter_entry()` — Custom Property in Filters

```python
# Current:
entry = {
    "resourceType": f._resource_type,
    "filterType": f._property_type,
    "value": f._property,
    ...
}

# New (when _property is a CustomPropertyRef):
if isinstance(f._property, CustomPropertyRef):
    entry = {
        "customPropertyId": f._property.id,
        "filterType": f._property_type,
        ...
    }

# New (when _property is an InlineCustomProperty):
elif isinstance(f._property, InlineCustomProperty):
    entry = {
        "customProperty": {
            "displayFormula": f._property.formula,
            "composedProperties": _build_composed_properties(f._property.inputs),
            "propertyType": f._property.property_type,
        },
        "filterType": f._property.property_type or f._property_type,
        ...
    }
```

#### `build_group_section()` — Custom Property in Group-By

```python
# Current:
group_entry = {
    "value": g.property,
    "propertyName": g.property,
    "resourceType": "events",
    "propertyType": g.property_type,
    ...
}

# New (CustomPropertyRef):
if isinstance(g.property, CustomPropertyRef):
    group_entry = {
        "customPropertyId": g.property.id,
        "propertyType": g.property_type,
        ...
    }

# New (InlineCustomProperty):
elif isinstance(g.property, InlineCustomProperty):
    group_entry = {
        "customProperty": {
            "displayFormula": g.property.formula,
            "composedProperties": _build_composed_properties(g.property.inputs),
            "propertyType": g.property.property_type or g.property_type,
        },
        "propertyType": g.property.property_type or g.property_type,
        ...
    }
```

#### Measurement Property — Custom Property in Metric Aggregation

```python
# Current:
measurement = {
    "math": math,
    "property": {"name": prop_name, "resourceType": "events", "type": "number"},
    ...
}

# New (CustomPropertyRef):
if isinstance(metric.property, CustomPropertyRef):
    measurement = {
        "math": math,
        "property": {
            "customPropertyId": metric.property.id,
            "resourceType": "events",
        },
        ...
    }

# New (InlineCustomProperty):
elif isinstance(metric.property, InlineCustomProperty):
    measurement = {
        "math": math,
        "property": {
            "customProperty": {
                "displayFormula": metric.property.formula,
                "composedProperties": _build_composed_properties(metric.property.inputs),
            },
            "resourceType": metric.property.resource_type,
        },
        ...
    }
```

#### Shared Helper — `_build_composed_properties()`

```python
def _build_composed_properties(
    inputs: dict[str, PropertyInput],
) -> dict[str, dict[str, str]]:
    """Convert PropertyInput dict to bookmark composedProperties format.

    Args:
        inputs: Letter-variable to PropertyInput mapping.

    Returns:
        Bookmark-format composedProperties dict.
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

### 5.5 Validation Changes

#### Layer 1 — Argument Validation

New validation rules:

| Code | Rule | Message |
|------|------|---------|
| CE1 | `CustomEventRef.id` must be a positive integer | `custom event ID must be a positive integer` |
| CP1 | `CustomPropertyRef.id` must be a positive integer | `custom property ID must be a positive integer` |
| CP2 | `InlineCustomProperty.formula` must be non-empty | `inline custom property formula must be non-empty` |
| CP3 | `InlineCustomProperty.inputs` must be non-empty | `inline custom property must have at least one input` |
| CP4 | `InlineCustomProperty.inputs` keys must be single uppercase letters A-Z | `inline custom property input keys must be single uppercase letters (A-Z)` |
| CP5 | All formula variables must have matching inputs | `formula references variable '{var}' but no matching input was provided` |
| CP6 | Formula max length 20,000 characters | `formula exceeds maximum length of 20,000 characters` |

Modified validation rules:

| Code | Change |
|------|--------|
| V17 | Skip "event name must be a string" check when event is `CustomEventRef` |
| V22 | Skip "event name must be non-empty" check when event is `CustomEventRef` |

#### Layer 2 — Bookmark Structure Validation

- B7 already validates `behavior.type` against `VALID_METRIC_TYPES` which includes `"custom-event"` — no change needed.
- B8 already handles `"custom-event"` behavior type — validates name presence.
- Add: When `behavior.type == "custom-event"`, validate that `behavior.id` is present and is a positive integer.

---

## 6. Usage Examples

### 6.1 Custom Events in Insights

```python
# List available custom events
custom_events = ws.list_custom_events()
# [EventDefinition(name="All Signups", custom_event_id=42), ...]

# Simple query with a custom event
result = ws.query(CustomEventRef(42))

# Custom event with aggregation
result = ws.query(CustomEventRef(42), math="unique", last=90)

# Custom event as a Metric (per-event math control)
result = ws.query(Metric(
    event=CustomEventRef(42),
    math="unique",
))

# Multi-metric: custom event + regular event
result = ws.query([
    Metric(event=CustomEventRef(42), math="unique"),
    Metric("Purchase", math="unique"),
])

# Formula with custom event
result = ws.query(
    [CustomEventRef(42), "Purchase"],
    formula="(B / A) * 100",
    formula_label="Conversion Rate",
)

# Custom event with breakdown and filter
result = ws.query(
    CustomEventRef(42),
    math="unique",
    group_by="platform",
    where=[Filter.equals("country", "US")],
)
```

### 6.2 Custom Events in Funnels

```python
# Custom event as a funnel step
result = ws.query_funnel([
    CustomEventRef(42),  # "All Signups"
    "Add to Cart",
    "Purchase",
])

# Custom event with per-step filters
result = ws.query_funnel([
    FunnelStep(event=CustomEventRef(42)),
    FunnelStep("Purchase", filters=[Filter.greater_than("amount", 50)]),
])

# Mixed custom events and regular events
result = ws.query_funnel([
    CustomEventRef(42),   # "All Signups"
    CustomEventRef(43),   # "Engagement" (another custom event)
    "Purchase",
])
```

### 6.3 Custom Events in Retention

```python
# Custom event as born event
result = ws.query_retention(
    born_event=CustomEventRef(42),  # "All Signups"
    return_event="Login",
    retention_unit="week",
)

# Both events as custom events
result = ws.query_retention(
    born_event=CustomEventRef(42),
    return_event=CustomEventRef(43),
)
```

### 6.4 Custom Events in Flows

```python
# Custom event as flow anchor
result = ws.query_flow(CustomEventRef(42), forward=3, reverse=2)
```

### 6.5 Custom Properties — Saved Reference

```python
# As breakdown
result = ws.query("Purchase", group_by=GroupBy(
    property=CustomPropertyRef(99),
    property_type="number",
    bucket_size=100,
))

# As filter
result = ws.query("Purchase", where=Filter.greater_than(
    property=CustomPropertyRef(99),
    value=1000,
))

# As aggregation property
result = ws.query(Metric(
    "Purchase",
    math="average",
    property=CustomPropertyRef(99),
))
```

### 6.6 Custom Properties — Inline Formula

```python
# Revenue = price * quantity (breakdown by revenue bucket)
result = ws.query(
    "Purchase",
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
        bucket_size=100,
        bucket_min=0,
        bucket_max=1000,
    ),
)

# Using the convenience constructor
result = ws.query(
    "Purchase",
    group_by=GroupBy(
        property=InlineCustomProperty.numeric("A * B", A="price", B="quantity"),
        property_type="number",
        bucket_size=100,
    ),
)

# Extract email domain (filter by domain)
result = ws.query(
    "Signup",
    where=Filter.equals(
        property=InlineCustomProperty(
            formula='REGEX_EXTRACT(A, "@(.+)$")',
            inputs={"A": PropertyInput("email", type="string")},
            property_type="string",
        ),
        value="company.com",
    ),
)

# Tiered pricing breakdown
result = ws.query(
    "Purchase",
    group_by=GroupBy(
        property=InlineCustomProperty(
            formula='IFS(A > 1000, "Enterprise", A > 100, "Pro", TRUE, "Free")',
            inputs={"A": PropertyInput("amount", type="number")},
            property_type="string",
        ),
    ),
)

# Average of computed property
result = ws.query(Metric(
    "Purchase",
    math="average",
    property=InlineCustomProperty.numeric("A * B", A="price", B="quantity"),
))

# Inline CP in funnel breakdown
result = ws.query_funnel(
    ["Signup", "Purchase"],
    group_by=GroupBy(
        property=InlineCustomProperty(
            formula='IF(A == "mobile", "Mobile", "Desktop")',
            inputs={"A": PropertyInput("platform", type="string")},
            property_type="string",
        ),
    ),
)
```

### 6.7 Create-Then-Reference Workflow

```python
# Step 1: Create a custom event
ce = ws.create_custom_event(
    name="All Signups",
    alternatives=[
        EventAlternative("Signup"),
        EventAlternative("Register"),
        EventAlternative("OAuth Login", filters=[
            Filter.equals("provider", ["Google", "GitHub"]),
        ]),
    ],
)
# ce.id = 42

# Step 2: Use in queries
result = ws.query(CustomEventRef(ce.id), math="unique", last=90)

# Step 3: Create a custom property
cp = ws.create_custom_property(CreateCustomPropertyParams(
    name="Revenue per Item",
    resource_type="events",
    display_formula="A * B",
    composed_properties={
        "A": ComposedPropertyValue(resource_type="event", type="number", value="price"),
        "B": ComposedPropertyValue(resource_type="event", type="number", value="quantity"),
    },
))
# cp.custom_property_id = 99

# Step 4: Use in queries
result = ws.query("Purchase", group_by=GroupBy(
    property=CustomPropertyRef(cp.custom_property_id),
    property_type="number",
    bucket_size=100,
))
```

### 6.8 Combined: Custom Event + Custom Property

```python
# Query a custom event, broken down by an inline custom property,
# filtered by a saved custom property
result = ws.query(
    CustomEventRef(42),
    math="unique",
    group_by=GroupBy(
        property=InlineCustomProperty(
            formula='IF(A == "iOS", "Mobile", IF(A == "Android", "Mobile", "Desktop"))',
            inputs={"A": PropertyInput("platform", type="string")},
            property_type="string",
        ),
    ),
    where=Filter.greater_than(
        property=CustomPropertyRef(99),  # "Revenue per Item"
        value=50,
    ),
    last=30,
)
```

---

## 7. New CRUD Methods

### 7.1 `create_custom_event()`

```python
def create_custom_event(
    self,
    name: str,
    alternatives: Sequence[str | EventAlternative],
) -> CustomEventResult:
    """Create a custom event (virtual event union).

    A custom event combines multiple real events into a single queryable
    entity. Each alternative specifies an event name with optional
    property filters.

    Args:
        name: Display name for the custom event.
        alternatives: Event alternatives. Plain strings are shorthand
            for ``EventAlternative(event_name)`` with no filters.

    Returns:
        The created custom event with its assigned ID.

    Raises:
        APIError: If the custom event could not be created.
        ValueError: If fewer than 1 alternative or more than 25.

    Examples:
        ```python
        ce = ws.create_custom_event("All Signups", [
            "Signup",
            "Register",
            EventAlternative("OAuth Login", filters=[
                Filter.equals("provider", ["Google", "GitHub"]),
            ]),
        ])
        ```
    """
```

### 7.2 `get_custom_event()`

```python
def get_custom_event(
    self,
    custom_event_id: int,
) -> CustomEventResult:
    """Get a custom event by ID.

    Args:
        custom_event_id: The custom event's database ID.

    Returns:
        The custom event definition including all alternatives.

    Raises:
        APIError: If the custom event is not found or access is denied.
    """
```

### 7.3 Supporting Types

```python
@dataclass(frozen=True)
class EventAlternative:
    """An alternative event within a custom event definition.

    Each alternative specifies an event name to include in the custom
    event union, with optional property filters.

    Attributes:
        event: Event name to include. Can also be ``"$custom_event:{id}"``
            to nest another custom event.
        filters: Optional property filters for this alternative.
        filters_combinator: How filters combine. Default ``"all"`` (AND).

    Examples:
        ```python
        EventAlternative("Signup")
        EventAlternative("Purchase", filters=[
            Filter.greater_than("amount", 50),
        ])
        ```
    """

    event: str
    filters: list[Filter] | None = None
    filters_combinator: Literal["all", "any"] = "all"


@dataclass(frozen=True)
class CustomEventResult:
    """Result of a custom event CRUD operation.

    Attributes:
        id: Server-assigned custom event ID.
        name: Display name.
        alternatives: List of alternative event definitions.
        project_id: Project the custom event belongs to.
        deleted: Whether the custom event is soft-deleted.
    """

    id: int
    name: str
    alternatives: list[dict[str, Any]]
    project_id: int
    deleted: bool = False
```

---

## 8. Design Decisions and Rationale

### 8.1 Why Reference-by-ID for Custom Events Instead of Auto-Create

**Decision**: Custom events in queries are always referenced by their saved ID. No auto-creation.

**Alternatives considered**:
- (A) Accept inline `InlineCustomEvent` definitions, auto-create via App API, then reference by ID.
- (B) Accept inline definitions and pass them through to the query engine (if supported).

**Why (A) was rejected**: Auto-creation has hidden side effects — it creates persistent entities in the project. This violates the principle that `query()` should be a read-only operation. Users would accumulate orphaned custom events. Cleanup would require separate delete calls. The behavior is surprising for an LLM agent that expects `query()` to be idempotent.

**Why (B) was rejected**: The insights query engine does NOT support inline custom event definitions. The `process_event_selectors()` function always resolves `$custom_event:{id}` by database lookup. There is no inline expansion path for insights or retention. Funnels have a partial `alternatives` path, but it's internal plumbing, not a documented feature.

**Why reference-by-ID wins**: It's explicit, predictable, and works consistently across all query types. The create-then-reference workflow matches how custom events work in the Mixpanel UI. The minor friction of calling `create_custom_event()` first is offset by clarity and debuggability.

### 8.2 Why Inline Support for Custom Properties

**Decision**: Support both `CustomPropertyRef` (saved) and `InlineCustomProperty` (ad-hoc) in queries.

**Rationale**: Unlike custom events, inline custom properties are a **first-class, production-grade feature** of the Mixpanel query engine. The `segment_to_arb_selector()` function natively handles inline `customProperty` definitions. The UI's "Apply without Save" workflow relies on this. Revenue change properties, SCD queries, and experiment properties all use inline custom properties internally.

Supporting inline custom properties adds significant value for LLM agents:
- **No pre-creation step**: An agent can compute derived metrics in a single query call.
- **Exploration**: Try different formulas without creating persistent entities.
- **Composability**: Build complex analytics from raw properties without CRUD overhead.

### 8.3 Why `PropertyInput` Instead of Reusing `ComposedPropertyValue`

**Decision**: Introduce a new `PropertyInput` frozen dataclass instead of reusing the existing Pydantic `ComposedPropertyValue` model.

**Rationale**: `ComposedPropertyValue` is a Pydantic model designed for App API request/response serialization. It has `extra="allow"`, camelCase alias generation, and a loosely-typed `behavior: Any` field. For the query API, we want a tight, frozen dataclass with explicit typing and no extra baggage — consistent with the existing `Metric`, `Filter`, `GroupBy` pattern. The builder converts `PropertyInput` to the bookmark JSON format at build time.

### 8.4 Why Union Types on Existing Fields Instead of Separate Parameters

**Decision**: Extend `Metric.event` from `str` to `str | CustomEventRef`, and `GroupBy.property` from `str` to `str | CustomPropertyRef | InlineCustomProperty`.

**Alternatives considered**:
- (A) Add separate fields: `Metric.custom_event_id: int | None = None`, `GroupBy.custom_property_id: int | None = None`
- (B) Add separate parameters to query methods: `custom_events=`, `custom_properties=`
- (C) Use union types on existing fields

**Why (C) wins**: It's the most natural for LLMs and the most consistent with the progressive disclosure pattern already established. `Metric("Login")` and `Metric(CustomEventRef(42))` are analogous — both specify "which event to query." The field name `event` remains semantically correct for custom events (they ARE events, just virtual ones). Separate fields or parameters would create ambiguity: "Do I use `event` or `custom_event_id`? What if both are set?"

### 8.5 Why `CustomEventRef` Instead of String Convention

**Decision**: Use a typed `CustomEventRef(42)` instead of accepting `"$custom_event:42"` as a string.

**Rationale**: String conventions are fragile and error-prone. An LLM might write `"custom_event:42"` or `"$custom_event_42"` or `"ce:42"`. A typed class with an `id: int` field is unambiguous, self-documenting, and validated at construction time. It also enables IDE autocompletion and type-checker support.

### 8.6 Why Not Support Behavior-Based Inline Custom Properties (v1)

**Decision**: `InlineCustomProperty` supports formula-based definitions only. Behavior-based custom properties must be created and referenced by ID.

**Rationale**: Behavior-based custom properties (e.g., "total purchases in last 30 days") have a complex JSON structure with nested event references, date ranges, aggregation operators, and filter lists. Supporting them inline would require defining several additional types (`BehaviorSpec`, `BehaviorDateRange`, etc.) and significantly increase the API surface. The formula path covers the vast majority of inline use cases (arithmetic, string manipulation, conditionals). Behavior-based CPs are less common for ad-hoc queries and more naturally suited to pre-creation and reuse.

### 8.7 Why `InlineCustomProperty.numeric()` Convenience Constructor

**Decision**: Provide a `numeric()` classmethod for the most common formula pattern.

**Rationale**: Numeric arithmetic on two properties (revenue = price * quantity, margin = (revenue - cost) / revenue) is by far the most common custom property use case. The full constructor requires specifying `PropertyInput(name, type="number")` for each input, plus `property_type="number"`. The `numeric()` classmethod reduces this to a single line: `InlineCustomProperty.numeric("A * B", A="price", B="quantity")`. This is particularly valuable for LLM agents, which can generate this one-liner more reliably than the full constructor.

### 8.8 What Was Excluded and Why

| Excluded Feature | Reason |
|-----------------|--------|
| Inline custom events for insights | Not supported by query engine — always resolves by DB ID |
| Behavior-based inline custom properties | Complex JSON structure; formula covers 90% of inline use cases |
| Auto-create custom events on query | Hidden side effects; violates query idempotency |
| Custom property nesting in inline CPs | Adds complexity; composedProperties can reference other CPs by ID but this is rarely needed inline |
| Flows custom property breakdowns | Flows don't support custom properties in breakdowns (different query engine) |
| `InlineCustomEvent` for funnels | Partial internal support exists but isn't a documented feature; risks fragility |
| Formula validation (client-side) | The arb-selector formula language is parsed by a C implementation on the server; client-side validation would be incomplete and fragile |

---

## 9. Implementation Plan

### Phase 1: CRUD Gap — Custom Event Create/Get

**Goal**: Enable the create-then-reference workflow.

- Add `create_custom_event()` to Workspace (POST to `/api/app/workspaces/{wid}/custom_events/`)
- Add `get_custom_event()` to Workspace (GET by ID)
- Add `EventAlternative` and `CustomEventResult` types
- Add `update_custom_event_full()` — full update including alternatives (current `update_custom_event()` only updates Lexicon metadata)
- Tests: Unit + integration with wiremock mocks

**Estimated scope**: ~300 lines of implementation + ~300 lines of tests.

### Phase 2: New Query Types

**Goal**: Define the new types and type aliases.

- Add `CustomEventRef`, `CustomPropertyRef`, `PropertyInput`, `InlineCustomProperty` to `types.py`
- Add `EventSpec`, `PropertySpec` type aliases
- Add `InlineCustomProperty.numeric()` convenience constructor
- Validation for new types (CE1, CP1-CP6)
- Tests: Unit tests for type construction and validation

**Estimated scope**: ~200 lines of types + ~200 lines of tests.

### Phase 3: Custom Events in Queries

**Goal**: Support `CustomEventRef` across all query methods.

- Modify `Metric.event`, `FunnelStep.event`, `RetentionEvent.event`, `FlowStep.event` type annotations
- Update `_build_query_params()` — emit `behavior.type = "custom-event"` for `CustomEventRef`
- Update `_build_funnel_params()` — emit `$custom_event:{id}` in funnel sub-behaviors
- Update `_build_retention_params()` — emit `$custom_event:{id}` in retention behaviors
- Update `_build_flow_params()` — emit `$custom_event:{id}` in flow steps
- Update query method signatures to accept `CustomEventRef`
- Update resolution logic in `_resolve_and_build_params()` variants
- Relax validation rules V17/V22 for `CustomEventRef`
- Tests: Builder output tests, validation tests, PBT for type combinations

**Estimated scope**: ~400 lines of changes + ~500 lines of tests.

### Phase 4: Custom Properties in Queries

**Goal**: Support `CustomPropertyRef` and `InlineCustomProperty` in group-by, filter, and metric measurement.

- Modify `GroupBy.property` type annotation
- Modify `Filter._property` type annotation and all class methods
- Modify `Metric.property` type annotation
- Update `build_group_section()` — emit `customPropertyId` or `customProperty`
- Update `build_filter_entry()` — emit `customPropertyId` or `customProperty`
- Update measurement builder in `_build_query_params()` — emit custom property in measurement
- Add `_build_composed_properties()` helper
- Add custom property support to `_build_funnel_params()` and `_build_retention_params()` group/filter builders
- Tests: Builder output tests, validation tests, round-trip PBT

**Estimated scope**: ~500 lines of changes + ~600 lines of tests.

### Phase 5: Polish and Documentation

- Property-based tests (Hypothesis) for all new types
- Mutation testing on new validation rules
- Docstrings for all new types and methods
- Update `__init__.py` exports
- Integration testing with real Mixpanel API (if available)

---

## 10. Summary: API Surface

### New Public Types

| Type | Purpose |
|------|---------|
| `CustomEventRef` | Reference a saved custom event by ID |
| `CustomPropertyRef` | Reference a saved custom property by ID |
| `PropertyInput` | Input property for inline custom property formulas |
| `InlineCustomProperty` | Ad-hoc computed property defined inline in a query |
| `EventAlternative` | Alternative event within a custom event definition |
| `CustomEventResult` | Result of custom event CRUD operations |
| `EventSpec` | Type alias: `str \| CustomEventRef` |
| `PropertySpec` | Type alias: `str \| CustomPropertyRef \| InlineCustomProperty` |

### New Public Methods

| Method | Purpose |
|--------|---------|
| `create_custom_event(name, alternatives)` | Create a custom event (fills CRUD gap) |
| `get_custom_event(id)` | Get a custom event by ID (fills CRUD gap) |
| `update_custom_event_full(id, name, alternatives)` | Full update including alternatives |

### Modified Types

| Type | Field | Change |
|------|-------|--------|
| `Metric` | `event` | `str` → `str \| CustomEventRef` |
| `Metric` | `property` | `str \| None` → `str \| CustomPropertyRef \| InlineCustomProperty \| None` |
| `FunnelStep` | `event` | `str` → `str \| CustomEventRef` |
| `RetentionEvent` | `event` | `str` → `str \| CustomEventRef` |
| `FlowStep` | `event` | `str` → `str \| CustomEventRef` |
| `GroupBy` | `property` | `str` → `str \| CustomPropertyRef \| InlineCustomProperty` |
| `Filter` class methods | `property` param | `str` → `str \| CustomPropertyRef \| InlineCustomProperty` |

### Modified Method Signatures

| Method | Parameter | Change |
|--------|-----------|--------|
| `query()` | `events` | Accept `CustomEventRef` in union |
| `query_funnel()` | `steps` | Accept `CustomEventRef` in union |
| `query_retention()` | `born_event`, `return_event` | Accept `CustomEventRef` in union |
| `query_flow()` | `event` | Accept `CustomEventRef` in union |

---

## Appendix A: Bookmark JSON Examples

### A.1 Custom Event in Insights

```json
{
    "sections": {
        "show": [{
            "type": "metric",
            "behavior": {
                "type": "custom-event",
                "name": "$custom_event:42",
                "id": 42,
                "resourceType": "events",
                "filtersDeterminer": "all",
                "filters": [],
                "dataGroupId": null,
                "dataset": "$mixpanel"
            },
            "measurement": {
                "math": "unique",
                "property": null,
                "perUserAggregation": null
            },
            "isHidden": false
        }],
        "filter": [],
        "group": [],
        "time": [{"dateRangeType": "in the last", "unit": "day", "window": {"unit": "day", "value": 30}}],
        "formula": []
    },
    "displayOptions": {
        "chartType": "line",
        "plotStyle": "standard",
        "analysis": "linear"
    }
}
```

### A.2 Inline Custom Property in Group-By

```json
{
    "sections": {
        "show": [{
            "type": "metric",
            "behavior": {
                "type": "event",
                "name": "Purchase",
                "resourceType": "events"
            },
            "measurement": {"math": "total"}
        }],
        "filter": [],
        "group": [{
            "customProperty": {
                "displayFormula": "A * B",
                "composedProperties": {
                    "A": {"value": "price", "type": "number", "resourceType": "event"},
                    "B": {"value": "quantity", "type": "number", "resourceType": "event"}
                },
                "propertyType": "number"
            },
            "propertyType": "number",
            "customBucket": {"bucketSize": 100, "min": 0, "max": 1000},
            "isHidden": false
        }],
        "time": [{"dateRangeType": "in the last", "unit": "day", "window": {"unit": "day", "value": 30}}],
        "formula": []
    }
}
```

### A.3 Saved Custom Property in Filter

```json
{
    "sections": {
        "filter": [{
            "customPropertyId": 99,
            "filterType": "number",
            "filterOperator": "is greater than",
            "filterValue": 100,
            "determiner": "all",
            "isHidden": false
        }]
    }
}
```

### A.4 Custom Event in Funnel Sub-Behavior

```json
{
    "sections": {
        "show": [{
            "behavior": {
                "type": "funnel",
                "behaviors": [
                    {
                        "type": "event",
                        "name": "$custom_event:42",
                        "filters": [],
                        "filtersDeterminer": "all",
                        "funnelOrder": "loose"
                    },
                    {
                        "type": "event",
                        "name": "Purchase",
                        "filters": [],
                        "filtersDeterminer": "all",
                        "funnelOrder": "loose"
                    }
                ],
                "conversionWindowDuration": 14,
                "conversionWindowUnit": "day",
                "funnelOrder": "loose"
            },
            "measurement": {"math": "conversion_rate_unique"}
        }]
    }
}
```

### A.5 Inline Custom Property in Measurement

```json
{
    "sections": {
        "show": [{
            "type": "metric",
            "behavior": {
                "type": "event",
                "name": "Purchase",
                "resourceType": "events"
            },
            "measurement": {
                "math": "average",
                "property": {
                    "customProperty": {
                        "displayFormula": "A * B",
                        "composedProperties": {
                            "A": {"value": "price", "type": "number", "resourceType": "event"},
                            "B": {"value": "quantity", "type": "number", "resourceType": "event"}
                        }
                    },
                    "resourceType": "events"
                },
                "perUserAggregation": null
            }
        }]
    }
}
```

---

## Appendix B: Key Source Files in analytics/

| File | Purpose |
|------|---------|
| `webapp/custom_events/models.py` | Django models: `CustomEvent`, `Alternative` |
| `webapp/custom_events/views.py` | Custom event CRUD API |
| `webapp/custom_events/constants.py` | `MAX_NUMBER_OF_ALTERNATIVES = 25` |
| `api/version_2_0/custom_events/util.py` | Query expansion: `generate_custom_event_selectors()` |
| `api/version_2_0/segmentation/models.py` | `process_event_selectors()` — expansion entry point |
| `backend/app_helpers/projects.py` | `get_custom_event()`, `custom_property_from_id()` — DB lookups |
| `webapp/custom_properties/models.py` | Django model: `CustomProperty` |
| `webapp/app_api/projects/custom_properties/views.py` | Custom property CRUD API |
| `webapp/custom_properties/serialization.py` | API serialization |
| `backend/util/arb_selector.py` | Custom property resolution: `segment_to_arb_selector()`, `_expand_formula_property()` |
| `api/version_2_0/properties_util/__init__.py` | `populate_custom_property()` — hydrates CP definitions |
| `iron/common/types/reports/bookmark.ts` | TypeScript: `MetricType.CustomEvent`, `Behavior`, `GroupClause` |
| `iron/common/types/reports/query.ts` | TypeScript: `CustomProperty`, `Segmentation` |
| `iron/common/util/tern/definitions/arb-selector.json` | Formula language function catalog |
| `iron/common/report/stores/inline-custom-properties-store.ts` | Inline CP store |
| `iron/common/widgets/custom-property-modal/util.ts` | `isPersistedCustomProperty()`, `isInlineCustomProperty()` |
| `api/version_2_0/insights/funnel_metric_params_util.py` | Funnel step event selector passthrough (line 72) |
