# Cohort Behaviors in the Unified Query System — Design Document

**Date**: 2026-04-07 (revised 2026-04-07)
**Status**: Research Complete — Design Proposed (v2: with Cohort Definition Builder)
**Builds on**: `insights-query-api-design.md`, `unified-bookmark-query-design.md`
**Reference**: `analytics/` repo (Mixpanel canonical implementation)

---

## 1. Executive Summary

This document specifies the design for adding cohort behavior support to `mixpanel_data`'s typed query system. Cohort behaviors are the final missing piece from the original `unified-bookmark-query-design.md` roadmap.

The research reveals that "cohort behaviors" is not a single feature — it is **three orthogonal capabilities** that each integrate differently with the existing query infrastructure:

| Capability | What It Does | Which Query Methods | Integration Point |
|-----------|-------------|--------------------|--------------------|
| **Cohort as Metric** | Track cohort size over time | `query()` only | New `CohortMetric` type in `events=` parameter |
| **Cohort as Filter** | Restrict queries to users in/not in cohort(s) | `query()`, `query_funnel()`, `query_retention()` | Extend `Filter` with cohort class methods |
| **Cohort as Breakdown** | Segment results by cohort membership | `query()`, `query_funnel()`, `query_retention()` | New `CohortBreakdown` type in `group_by=` parameter |

### Why Not a New `query_cohort()` Method?

Unlike funnels, retention, and flows — which have structurally different `behavior` blocks, different API routing, and different response formats — cohort capabilities are **cross-cutting enhancements** to the existing query methods. A separate `query_cohort()` would only cover "cohort as metric" (insights-only) and would leave cohort filtering and breakdowns stranded.

The correct architecture is to extend the shared infrastructure so that all three existing query methods (`query()`, `query_funnel()`, `query_retention()`) gain cohort capabilities simultaneously.

### Design Principles

1. **Cohort builder first** — A typed `CohortDefinition` builder is the foundation. It produces valid JSON for both cohort CRUD and inline query references.
2. **Cross-cutting, not siloed** — Cohort filter and breakdown capabilities are shared infrastructure that benefits all query types simultaneously.
3. **Saved AND inline** — Every cohort integration point accepts both `int` (saved cohort ID) and `CohortDefinition` (inline ad-hoc cohort).
4. **Progressive disclosure** — `Filter.in_cohort(123)` is as simple as `Filter.equals("browser", "Chrome")`. Inline cohorts add one level of composition.
5. **Type-safe** — No raw dict construction. `CohortCriteria` class methods produce validated building blocks.
6. **Fail-fast** — Client-side validation catches invalid definitions before API calls.
7. **Debuggable** — `result.params` includes the generated cohort JSON for inspection. `CohortDefinition.to_dict()` enables standalone inspection.

---

## 2. Research Findings: How Cohorts Work in Mixpanel

### 2.1 Three Mechanisms, Three JSON Structures

The Mixpanel analytics codebase reveals that cohorts interact with the bookmark query system through three completely different mechanisms, each with its own JSON representation, API routing, and response format.

#### Mechanism 1: Cohort as a Metric ("Cohorts Over Time")

A cohort can be a **metric** in a show clause, tracking how the cohort's size changes over time. This is the "Cohorts Over Time" report type in the Mixpanel UI.

**Bookmark JSON:**
```json
{
  "sections": {
    "show": [{
      "type": "metric",
      "behavior": {
        "type": "cohort",
        "resourceType": "cohorts",
        "name": "Power Users",
        "dataGroupId": null,
        "dataset": "$mixpanel"
      },
      "measurement": {
        "math": "unique",
        "property": null,
        "perUserAggregation": null
      },
      "isHidden": false
    }]
  }
}
```

**Key characteristics:**
- `behavior.type: "cohort"` — the discriminator
- `behavior.resourceType: "cohorts"` (plural) — distinguishes from event metrics
- References a saved cohort by `behavior.id` (integer) or an inline cohort by `behavior.raw_cohort` (dict)
- Only valid `math` type is `"unique"` — you can only count unique users in a cohort
- **Insights only** — funnels, retention, and flows do not support cohort metrics in show clauses

**API routing** (from `analytics/api/version_2_0/insights/params.py:2475`):
```python
@staticmethod
def _is_cohorts_metric(clause):
    return get_behavior_value_from_show_clause(clause, "resourceType") == "cohorts"
```

When detected, the insights API routes the query to `cohorts_size_over_time()` (in `insights/cohorts.py`), which queries the **engage binaries** (user profile storage), NOT the event binaries. This is fundamentally different from event metrics.

**Response format:**
```json
{
  "series": {
    "Power Users [Unique Users]": {
      "2024-01-01T00:00:00-07:00": 1234,
      "2024-01-02T00:00:00-07:00": 1256
    }
  }
}
```

The response is structurally identical to an insights event metric response — same `series` shape, same `computed_at`, `date_range`, `headers`, `meta` fields. This means our existing `QueryResult` type and `_transform_query_result()` parser can handle it without modification.

#### Mechanism 2: Cohort as a Filter

A cohort can **filter** any query to include only users who are in (or not in) specified cohort(s). This works across insights, funnels, and retention.

**Modern bookmark JSON** (in `sections.filter[]`):
```json
{
  "dataset": "$mixpanel",
  "value": "$cohorts",
  "resourceType": "events",
  "filterType": "list",
  "filterOperator": "contains",
  "filterValue": [
    {
      "cohort": {
        "id": 123,
        "name": "Power Users",
        "negated": false
      }
    }
  ],
  "propertyObjectKey": null,
  "dataGroupId": null
}
```

**Key characteristics:**
- Identified by the magic property name `value: "$cohorts"` (constant `INSIGHTS_COHORT_TYPE` in the frontend)
- `filterType: "list"` — cohorts are treated as List property filters
- `filterOperator: "contains"` for inclusion, `"does not contain"` for exclusion
- `filterValue` is an array of `{cohort: {id, name, negated}}` objects — NOT scalar values
- `resourceType` is `"events"` at the insights level (not `"cohort"`)
- Multiple cohort entries in `filterValue` combine with OR logic (user is in ANY of these cohorts)
- Multiple cohort filter entries in `sections.filter[]` combine with AND logic (user is in ALL specified cohort groups)

**Two negation mechanisms:**
1. `filterOperator: "does not contain"` — negates the entire filter
2. `cohort.negated: true` — per-cohort negation flag (used internally, the operator is the primary mechanism)

**Legacy format** (funnels/retention v0 bookmarks use `filter_by_cohort`):
```json
{
  "filter_by_cohort": {
    "operator": "or",
    "children": [
      {"cohort": {"id": 123, "name": "Power Users", "negated": false}}
    ]
  }
}
```

The bookmark parser converts between these formats. Our implementation should only generate the modern `sections.filter[]` format.

**Source references:**
- `analytics/iron/common/report/insights/models/filter-clause.ts:67-78` — `FilterClause.defaultCohortsAttrs()`
- `analytics/iron/common/widgets/property-filter-menu/models/insights-filter.ts:76` — `INSIGHTS_COHORT_TYPE = "$cohorts"`
- `analytics/bookmark_parser/common/property_filter/utils.py:1-15` — `convert_cohort_property_filter_to_tree_filter()`
- `analytics/api/version_2_0/insights/params_util.py:156-157` — `is_cohort_filter()`

#### Mechanism 3: Cohort as a Breakdown (Group By)

A cohort can serve as a **breakdown dimension**, segmenting results by cohort membership. Users are bucketed into "in cohort" and "not in cohort" groups.

**Modern bookmark JSON** (in `sections.group[]`):
```json
{
  "value": [
    "Power Users",
    "Not In Power Users"
  ],
  "resourceType": "events",
  "propertyType": null,
  "typeCast": null,
  "cohorts": [
    {
      "id": 123,
      "name": "Power Users",
      "negated": false,
      "data_group_id": null,
      "groups": []
    },
    {
      "id": 123,
      "name": "Power Users",
      "negated": true,
      "data_group_id": null,
      "groups": []
    }
  ]
}
```

**Key characteristics:**
- Identified by the presence of a `cohorts` array in the group entry
- `value` is an array of display labels (one per cohort entry, including negated variants)
- Each cohort in the array can be negated independently — a single cohort ID produces TWO segments: "in" and "not in"
- The `cohorts` array contains full cohort metadata (not just IDs)
- `propertyType` is `null` (not a property breakdown)

**How it's processed** (from `analytics/api/version_2_0/insights/segmentation_arb.py:427-445`):

When a group entry has a `cohorts` key, the backend calls `get_behaviors_and_individual_selectors_for_cohort_list()` to resolve cohort definitions into ARB selectors, then wraps the query with `segment_by_cohorts_action()`:

```python
segment_by_cohorts(inner_action, {
    "Power Users": selector_for_cohort_123,
    "Not In Power Users": not(selector_for_cohort_123)
})
```

**Retention restriction** (from `analytics/api/version_2_0/retention/util.py:270-271`):
```python
if ("on" in arb_params or "born_on" in arb_params) and "group_by_cohorts" in arb_params:
    raise ApiError("cohorts are not supported in segmented retention")
```

Retention does NOT support simultaneous property breakdowns and cohort breakdowns. They are mutually exclusive.

**Source references:**
- `analytics/iron/common/report/insights/models/group-clause.ts:81` — `GroupClause.cohorts` field
- `analytics/iron/common/types/reports/bookmark.ts:288-304` — `GroupByCohort` interface
- `analytics/api/version_2_0/cohorts/selector.py:4-23` — `segment_by_cohorts_action()`
- `analytics/api/version_2_0/insights/util.py:387-415` — `get_all_segments_from_groups_and_cohorts()`

### 2.2 Report Type Support Matrix

| Capability | Insights | Funnels | Retention | Flows |
|-----------|----------|---------|-----------|-------|
| Cohort as Metric | Yes | No | No | No |
| Cohort as Filter | Yes | Yes | Yes | Yes (legacy `filter_by_cohort` format) |
| Cohort as Breakdown | Yes | Yes | Partial* | No |

\* Retention supports cohort breakdowns but they are **mutually exclusive** with property breakdowns (`group_by`). The API raises an error if both are specified.

### 2.3 Cohort Identification

Cohorts can be referenced in two ways:

1. **Saved cohort** — by integer `id` (and optional `name` for display)
2. **Inline cohort** — by `raw_cohort` dict containing the full cohort definition

For our API, we will only support **saved cohort references** (by ID) in v1. Inline cohorts are complex to construct correctly and are rarely needed programmatically. Users who need inline cohorts can use `build_params()` and modify the dict.

### 2.4 The `dataGroupId` / `data_group_id` Field

This field appears throughout cohort-related structures. It is the **entity group identifier** for Mixpanel's B2B/Group Analytics feature. It scopes a query to a specific group type (e.g., "Company", "Account").

- Stored as `BigIntegerField(null=True)` in the Django model
- Serialized as a **string** in JSON responses (e.g., `"123"`, not `123`)
- When a cohort's `data_group_id` differs from the query's global `dataGroupId`, it creates a "cross-join" scenario requiring special handling

For v1, we set `dataGroupId: null` (default Mixpanel project, no B2B groups). B2B group analytics support can be added later.

---

## 3. Cohort Definition Builder (Phase 0 Prerequisite)

### 3.1 Why a Builder is Required

Every cohort integration point — filters, breakdowns, and metrics — needs to reference a cohort. While saved cohorts (by ID) cover the simple case, full cohort power requires **inline ad-hoc cohort definitions**. Without a typed builder, users would construct raw dicts — error-prone, undiscoverable, and hostile to LLM agents.

The builder is a Phase 0 prerequisite because it:
1. Produces valid JSON for `create_cohort()` (the `definition` field)
2. Produces valid `raw_cohort` dicts for inline query references
3. Is the single source of truth for cohort definition construction
4. Enables agent-friendly progressive disclosure

### 3.2 Cohort Definition Formats in Mixpanel

The Mixpanel API accepts two cohort definition formats:

**Legacy format (`selector` + `behaviors`)** — an expression tree combined with a behavior dictionary:
```json
{
  "selector": {
    "operator": "and",
    "children": [
      {"property": "behaviors", "value": "bhvr_1", "operator": ">=", "operand": 1}
    ]
  },
  "behaviors": {
    "bhvr_1": {
      "count": {
        "event_selector": {"event": "Purchase", "selector": null},
        "type": "absolute"
      },
      "window": {"unit": "day", "value": 30}
    }
  }
}
```

**Modern format (`groups`)** — an array of group entries with property filters and behavioral filters:
```json
{
  "groups": [
    {
      "type": "cohort_group",
      "filters": [/* PropertyFilter objects */],
      "behavioralFilters": [/* behavioral PropertyFilter objects */],
      "behavioralFiltersOperator": "and",
      "filtersOperator": "and",
      "groupingOperator": "and"
    }
  ]
}
```

**Our builder generates the legacy `selector` + `behaviors` format** because:
1. It works everywhere — both `create_cohort()` and `raw_cohort` in inline queries
2. The backend parses it natively without conversion
3. It's more explicit — each behavior is a named entry with clear semantics
4. The `groups` format is a UI abstraction that the backend converts to `selector` + `behaviors` anyway

### 3.3 `CohortCriteria` — Building Blocks

Each class method produces one atomic condition for cohort membership.

```python
@dataclass(frozen=True)
class CohortCriteria:
    """A single criterion for cohort membership.

    Construct via class methods — do not instantiate directly.
    Each method produces one condition that can be combined
    with AND/OR logic via CohortDefinition.

    Examples:
        ```python
        # User did event at least N times
        CohortCriteria.did_event("Purchase", at_least=3, within_days=30)

        # User has a specific property value
        CohortCriteria.has_property("plan", "premium")

        # User is in another cohort
        CohortCriteria.in_cohort(456)
        ```
    """

    _selector_node: dict
    _behavior_key: str | None = None
    _behavior: dict | None = None

    # ─── Behavioral criteria ───────────────────────────────────

    @classmethod
    def did_event(
        cls,
        event: str,
        *,
        at_least: int | None = None,
        at_most: int | None = None,
        exactly: int | None = None,
        within_days: int | None = None,
        within_weeks: int | None = None,
        within_months: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        where: Filter | list[Filter] | None = None,
    ) -> CohortCriteria:
        """User performed event matching frequency and time constraints.

        Exactly one frequency param (at_least, at_most, exactly) must
        be set. Exactly one time constraint (within_* or from_date)
        must be set.

        Args:
            event: Mixpanel event name.
            at_least: Minimum event count (>=).
            at_most: Maximum event count (<=).
            exactly: Exact event count (==).
            within_days: Rolling window in days.
            within_weeks: Rolling window in weeks.
            within_months: Rolling window in months.
            from_date: Absolute start date (YYYY-MM-DD).
            to_date: Absolute end date (YYYY-MM-DD). Required with from_date.
            where: Event property filters applied to the counted events.

        Examples:
            ```python
            # Purchased at least 3 times in the last 30 days
            CohortCriteria.did_event("Purchase", at_least=3, within_days=30)

            # Did not purchase in the last 7 days
            CohortCriteria.did_event("Purchase", exactly=0, within_days=7)

            # Purchased premium items at least once this quarter
            CohortCriteria.did_event(
                "Purchase",
                at_least=1,
                from_date="2024-01-01",
                to_date="2024-03-31",
                where=Filter.equals("plan", "premium"),
            )
            ```
        """
        ...

    @classmethod
    def did_not_do_event(
        cls,
        event: str,
        *,
        within_days: int | None = None,
        within_weeks: int | None = None,
        within_months: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> CohortCriteria:
        """Shorthand for did_event(event, exactly=0, ...).

        Example:
            ```python
            CohortCriteria.did_not_do_event("Login", within_days=30)
            ```
        """
        ...

    # ─── Property criteria ─────────────────────────────────────

    @classmethod
    def has_property(
        cls,
        property: str,
        value: str | int | float | bool | list[str],
        *,
        operator: Literal[
            "equals", "not_equals", "contains", "not_contains",
            "greater_than", "less_than", "is_set", "is_not_set",
        ] = "equals",
        property_type: Literal["string", "number", "boolean", "datetime", "list"] = "string",
    ) -> CohortCriteria:
        """User profile has a property matching a condition.

        Args:
            property: User profile property name.
            value: Value to compare against.
            operator: Comparison operator. Default "equals".
            property_type: Data type of the property. Default "string".

        Examples:
            ```python
            CohortCriteria.has_property("plan", "premium")
            CohortCriteria.has_property("age", 18, operator="greater_than",
                                        property_type="number")
            CohortCriteria.has_property("email", "@company.com",
                                        operator="contains")
            ```
        """
        ...

    @classmethod
    def property_is_set(cls, property: str) -> CohortCriteria:
        """User profile has the property defined (non-null)."""
        ...

    @classmethod
    def property_is_not_set(cls, property: str) -> CohortCriteria:
        """User profile does not have the property defined."""
        ...

    # ─── Cohort membership criteria ───────────────────────────

    @classmethod
    def in_cohort(cls, cohort_id: int) -> CohortCriteria:
        """User is a member of the specified saved cohort.

        Example:
            ```python
            CohortCriteria.in_cohort(456)
            ```
        """
        ...

    @classmethod
    def not_in_cohort(cls, cohort_id: int) -> CohortCriteria:
        """User is NOT a member of the specified saved cohort."""
        ...
```

### 3.4 `CohortDefinition` — Composing Criteria

Combines one or more `CohortCriteria` with AND/OR logic. Produces the `selector` + `behaviors` dict.

```python
@dataclass(frozen=True)
class CohortDefinition:
    """A typed cohort definition that produces valid Mixpanel JSON.

    Combines CohortCriteria with AND/OR logic. Supports nesting
    for complex boolean expressions.

    Use directly for single-criterion cohorts, or use all_of() / any_of()
    for multi-criterion definitions.

    Args:
        criteria: One or more CohortCriteria to combine with AND logic.

    Examples:
        ```python
        # Single criterion
        cohort = CohortDefinition(
            CohortCriteria.did_event("Purchase", at_least=1, within_days=30)
        )

        # Multiple criteria with AND (all must match)
        cohort = CohortDefinition.all_of(
            CohortCriteria.has_property("plan", "premium"),
            CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
        )

        # Multiple criteria with OR (any can match)
        cohort = CohortDefinition.any_of(
            CohortCriteria.did_event("Signup", at_least=1, within_days=7),
            CohortCriteria.in_cohort(456),
        )

        # Nested: (A AND B) OR C
        cohort = CohortDefinition.any_of(
            CohortDefinition.all_of(
                CohortCriteria.has_property("plan", "premium"),
                CohortCriteria.did_event("Login", at_least=5, within_days=30),
            ),
            CohortCriteria.in_cohort(789),
        )
        ```
    """

    _criteria: tuple[CohortCriteria | CohortDefinition, ...]
    _operator: Literal["and", "or"] = "and"

    def __init__(self, *criteria: CohortCriteria) -> None:
        """Create a definition from one or more criteria (AND logic)."""
        ...

    @classmethod
    def all_of(
        cls, *criteria: CohortCriteria | CohortDefinition,
    ) -> CohortDefinition:
        """Combine criteria with AND logic (all must match)."""
        ...

    @classmethod
    def any_of(
        cls, *criteria: CohortCriteria | CohortDefinition,
    ) -> CohortDefinition:
        """Combine criteria with OR logic (any can match)."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Produce the selector + behaviors dict for the API.

        Returns a dict with ``selector`` (expression tree) and
        ``behaviors`` (behavior dictionary) keys. This dict can be:
        - Passed as ``definition`` to ``CreateCohortParams``
        - Used as ``raw_cohort`` in inline cohort references
        - Inspected for debugging

        Example:
            ```python
            cohort = CohortDefinition(
                CohortCriteria.did_event("Purchase", at_least=1, within_days=30)
            )
            print(cohort.to_dict())
            # {
            #   "selector": {"operator": "and", "children": [...]},
            #   "behaviors": {"bhvr_0": {"count": {...}, "window": {...}}}
            # }
            ```
        """
        ...
```

### 3.5 Selector Expression Tree Format

The `selector` field is a recursive expression tree. Our builder constructs these programmatically.

**Behavioral criterion** (references a behavior in the `behaviors` dict):
```json
{
  "property": "behaviors",
  "value": "bhvr_0",
  "operator": ">=",
  "operand": 3
}
```

Frequency operators:
- `at_least=N` → `"operator": ">="`, `"operand": N`
- `at_most=N` → `"operator": "<="`, `"operand": N`
- `exactly=N` → `"operator": "=="`, `"operand": N`
- `exactly=0` → `"operator": "=="`, `"operand": 0` (equivalent to "did not do")

**Property criterion** (user profile property):
```json
{
  "property": "user",
  "value": "plan",
  "operator": "==",
  "operand": "premium",
  "type": "string"
}
```

Operator mapping:
| `CohortCriteria` operator | Selector `operator` |
|---------------------------|---------------------|
| `"equals"` | `"=="` |
| `"not_equals"` | `"!="` |
| `"contains"` | `"in"` |
| `"not_contains"` | `"not in"` |
| `"greater_than"` | `">"` |
| `"less_than"` | `"<"` |
| `"is_set"` | `"defined"` |
| `"is_not_set"` | `"not defined"` |

**Cohort reference criterion**:
```json
{
  "property": "cohort",
  "value": 456,
  "operator": "in"
}
```

Negated: `"operator": "not in"`.

**Combining with AND/OR:**
```json
{
  "operator": "and",
  "children": [
    {"property": "behaviors", "value": "bhvr_0", "operator": ">=", "operand": 1},
    {"property": "user", "value": "plan", "operator": "==", "operand": "premium", "type": "string"}
  ]
}
```

### 3.6 Behavior Dictionary Format

Each behavioral criterion produces an entry in the `behaviors` dict.

**Event count with rolling window:**
```json
{
  "bhvr_0": {
    "count": {
      "event_selector": {
        "event": "Purchase",
        "selector": null
      },
      "type": "absolute"
    },
    "window": {"unit": "day", "value": 30}
  }
}
```

**Event count with absolute date range:**
```json
{
  "bhvr_0": {
    "count": {
      "event_selector": {
        "event": "Purchase",
        "selector": null
      },
      "type": "absolute"
    },
    "from_date": "2024-01-01",
    "to_date": "2024-03-31"
  }
}
```

**Event count with event property filters:**

When `where=` is provided, the `event_selector.selector` contains an expression tree filtering the events:
```json
{
  "bhvr_0": {
    "count": {
      "event_selector": {
        "event": "Purchase",
        "selector": {
          "operator": "and",
          "children": [
            {"property": "event", "value": "amount", "operator": ">", "operand": 50, "type": "number"}
          ]
        }
      },
      "type": "absolute"
    },
    "window": {"unit": "day", "value": 30}
  }
}
```

**Behavior count type:**
- `"absolute"` — total event count across the window (default)
- `"day"` — per-day event count (used for frequency-based criteria like "at least 3 times per day")

### 3.7 Validation Rules (Phase 0)

| Code | Rule | Message |
|------|------|---------|
| CD1 | `did_event`: exactly one frequency param required | `exactly one of at_least, at_most, exactly must be set` |
| CD2 | `did_event`: frequency param must be non-negative | `frequency value must be >= 0` |
| CD3 | `did_event`: exactly one time constraint required | `exactly one time constraint required (within_days/weeks/months or from_date+to_date)` |
| CD4 | `did_event`: `event` must be non-empty | `event name must be non-empty` |
| CD5 | `did_event`: `from_date` requires `to_date` | `from_date requires to_date` |
| CD6 | `did_event`: dates must be YYYY-MM-DD | `dates must be YYYY-MM-DD format` |
| CD7 | `has_property`: `property` must be non-empty | `property name must be non-empty` |
| CD8 | `in_cohort`/`not_in_cohort`: `cohort_id` must be positive int | `cohort_id must be a positive integer` |
| CD9 | `CohortDefinition`: at least one criterion required | `CohortDefinition requires at least one criterion` |
| CD10 | `CohortDefinition.to_dict()`: all behavior keys must be unique | Internal invariant |

### 3.8 Integration with Existing `CreateCohortParams`

The builder integrates seamlessly with the existing cohort CRUD:

```python
# Build a cohort definition
cohort_def = CohortDefinition.all_of(
    CohortCriteria.has_property("plan", "premium"),
    CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
)

# Create a saved cohort via CRUD
ws.create_cohort(CreateCohortParams(
    name="Premium Purchasers",
    definition=cohort_def.to_dict(),
))

# Or use inline in queries (no saving required)
result = ws.query(
    "Login",
    where=Filter.in_cohort(cohort_def, name="Premium Purchasers"),
)
```

### 3.9 Example Definitions

**Simple behavioral:**
```python
# Users who logged in at least once in the last 7 days
CohortDefinition(
    CohortCriteria.did_event("Login", at_least=1, within_days=7)
)
```

**Simple property:**
```python
# Users on the premium plan
CohortDefinition(
    CohortCriteria.has_property("plan", "premium")
)
```

**Combined AND:**
```python
# Premium users who purchased 3+ times in 30 days
CohortDefinition.all_of(
    CohortCriteria.has_property("plan", "premium"),
    CohortCriteria.did_event("Purchase", at_least=3, within_days=30),
)
```

**Combined OR:**
```python
# Users who signed up recently OR are in the Power Users cohort
CohortDefinition.any_of(
    CohortCriteria.did_event("Signup", at_least=1, within_days=7),
    CohortCriteria.in_cohort(456),
)
```

**Nested boolean:**
```python
# (Premium AND active) OR Enterprise cohort
CohortDefinition.any_of(
    CohortDefinition.all_of(
        CohortCriteria.has_property("plan", "premium"),
        CohortCriteria.did_event("Login", at_least=5, within_days=30),
    ),
    CohortCriteria.in_cohort(789),  # Enterprise cohort
)
```

**With event property filters:**
```python
# Users who made high-value purchases
CohortDefinition(
    CohortCriteria.did_event(
        "Purchase",
        at_least=1,
        within_days=90,
        where=Filter.greater_than("amount", 100),
    )
)
```

**Inactive users (did NOT do):**
```python
# Users who haven't logged in for 30 days
CohortDefinition(
    CohortCriteria.did_not_do_event("Login", within_days=30)
)
```

---

## 4. Current Infrastructure State (Unchanged from v1)

### 4.1 What Already Exists

The unified query system already has most of the infrastructure needed:

| Component | Status | Extension Needed |
|-----------|--------|-----------------|
| `VALID_METRIC_TYPES` | `"cohort"` already included | None |
| `VALID_RESOURCE_TYPES` | `"cohorts"` already included | None |
| `Filter` class | 18 class methods for property filters | Add `in_cohort()`, `not_in_cohort()` |
| `GroupBy` class | Property breakdowns with bucketing | N/A — new `CohortBreakdown` type |
| `_build_filter_entry()` | Builds `sections.filter[]` dicts | Extend for cohort filter structure |
| `validate_bookmark()` L2 | Validates `behavior.type` against `VALID_METRIC_TYPES` | Add cohort-specific validation branch |
| `_validate_show_clause()` | Checks `behavior.name` for event types | Add branch for `behavior.type == "cohort"` checking `behavior.id` |
| `_transform_query_result()` | Parses insights response | Compatible as-is (cohort response has same shape) |
| Cohort CRUD | `list_cohorts_full()`, `get_cohort()`, etc. | Can validate cohort IDs exist |

### 4.2 Shared Infrastructure Used By All Query Types

These shared components will gain cohort capabilities:

```
Filter.in_cohort()          ─→  _build_filter_entry()     ─→  sections.filter[]
                                  (extended for cohort format)

CohortBreakdown             ─→  _build_group_section()    ─→  sections.group[]
                                  (extended for cohort format)

CohortMetric                ─→  _build_query_params()     ─→  sections.show[]
                                  (extended for cohort behavior)
```

---

## 5. API Design

### 5.1 Cohort as Filter: `Filter.in_cohort()` / `Filter.not_in_cohort()`

The simplest and most broadly useful capability. Works with all three query methods via the existing `where=` parameter. Accepts both saved cohort IDs and inline `CohortDefinition` objects.

```python
@classmethod
def in_cohort(
    cls,
    cohort: int | CohortDefinition,
    name: str | None = None,
) -> Filter:
    """Filter to users who are members of the specified cohort.

    Args:
        cohort: Saved cohort ID (integer) or inline CohortDefinition.
        name: Display name for the cohort. Required for inline
            definitions; optional for saved cohorts (API resolves).

    Examples:
        ```python
        # Saved cohort by ID
        result = ws.query(
            "Purchase",
            where=Filter.in_cohort(123, "Power Users"),
        )

        # Inline cohort definition (ad-hoc)
        result = ws.query(
            "Purchase",
            where=Filter.in_cohort(
                CohortDefinition(
                    CohortCriteria.did_event("Purchase", at_least=3, within_days=30)
                ),
                name="Frequent Buyers",
            ),
        )

        # Combine with property filters
        result = ws.query(
            "Purchase",
            where=[
                Filter.in_cohort(123),
                Filter.equals("platform", "iOS"),
            ],
        )

        # Also works with funnels and retention
        result = ws.query_funnel(
            ["Signup", "Purchase"],
            where=Filter.in_cohort(456, "Organic Users"),
        )
        ```
    """
    ...

@classmethod
def not_in_cohort(
    cls,
    cohort: int | CohortDefinition,
    name: str | None = None,
) -> Filter:
    """Filter to users who are NOT members of the specified cohort.

    Args:
        cohort: Saved cohort ID (integer) or inline CohortDefinition.
        name: Display name for the cohort.

    Examples:
        ```python
        # Exclude saved bot cohort
        result = ws.query(
            "Login",
            where=Filter.not_in_cohort(789, "Bots"),
        )

        # Exclude ad-hoc inactive users
        result = ws.query(
            "Login",
            where=Filter.not_in_cohort(
                CohortDefinition(
                    CohortCriteria.did_not_do_event("Login", within_days=30)
                ),
                name="Inactive Users",
            ),
        )
        ```
    """
    ...
```

**Implementation detail:** These class methods produce a `Filter` with special internal fields:

```python
Filter(
    _property="$cohorts",
    _operator="contains",          # or "does not contain"
    _value=[{"cohort": {"id": cohort_id, "name": name or "", "negated": False}}],
    _property_type="list",
    _resource_type="events",
)
```

The `_build_filter_entry()` method detects `_property == "$cohorts"` and generates the cohort-specific filter JSON (which differs from property filter JSON in the `filterValue` structure).

### 5.2 Cohort as Breakdown: `CohortBreakdown`

A new type that can be passed alongside `GroupBy` in the `group_by=` parameter. Accepts both saved cohort IDs and inline definitions.

```python
@dataclass(frozen=True)
class CohortBreakdown:
    """Break down query results by cohort membership.

    Segments users into "in cohort" and "not in cohort" groups.
    Multiple CohortBreakdown entries produce independent segmentation
    dimensions.

    Args:
        cohort: Saved cohort ID (integer) or inline CohortDefinition.
        name: Display name for the cohort. Required for inline
            definitions; optional for saved cohorts.
        include_negated: Whether to include a "Not In" segment.
            Default True. When False, only shows users IN the cohort.

    Examples:
        ```python
        # Saved cohort breakdown
        result = ws.query(
            "Purchase",
            group_by=CohortBreakdown(123, "Power Users"),
        )

        # Inline cohort breakdown
        result = ws.query(
            "Purchase",
            group_by=CohortBreakdown(
                CohortDefinition(
                    CohortCriteria.did_event("Purchase", at_least=5, within_days=30)
                ),
                name="Frequent Buyers",
            ),
        )

        # Mix cohort and property breakdowns (insights/funnels only)
        result = ws.query(
            "Purchase",
            group_by=[
                CohortBreakdown(123, "Power Users"),
                GroupBy("platform"),
            ],
        )

        # Funnel segmented by cohort
        result = ws.query_funnel(
            ["Signup", "Purchase"],
            group_by=CohortBreakdown(456, "Organic Users"),
        )
        ```
    """

    cohort: int | CohortDefinition
    name: str | None = None
    include_negated: bool = True
```

**`group_by` parameter type expansion:**

The existing `group_by` parameter on `query()`, `query_funnel()`, and `query_retention()` changes from:
```python
group_by: str | GroupBy | list[str | GroupBy] | None = None
```
to:
```python
group_by: str | GroupBy | CohortBreakdown | list[str | GroupBy | CohortBreakdown] | None = None
```

### 5.3 Cohort as Metric: `CohortMetric`

A new type that can be passed in the `events=` parameter of `query()`, enabling "Cohorts Over Time" queries. Accepts both saved cohort IDs and inline definitions.

```python
@dataclass(frozen=True)
class CohortMetric:
    """A cohort size metric for Workspace.query().

    Tracks the size of a cohort over time. Can be mixed with event
    Metric objects and Formula objects in the same query.

    The only valid math type for cohort metrics is "unique" — you
    can only count unique users in a cohort at each time point.

    Args:
        cohort: Saved cohort ID (integer) or inline CohortDefinition.
        name: Display name for the cohort. Used as the series label.
            Required for inline definitions; optional for saved cohorts.

    Examples:
        ```python
        # Saved cohort size over time
        result = ws.query(
            CohortMetric(123, "Power Users"),
            last=90,
        )

        # Inline cohort — track ad-hoc segment size
        result = ws.query(
            CohortMetric(
                CohortDefinition.all_of(
                    CohortCriteria.has_property("plan", "premium"),
                    CohortCriteria.did_event("Purchase", at_least=1, within_days=30),
                ),
                name="Active Premium Users",
            ),
            last=90,
            unit="week",
        )

        # Compare saved and inline cohorts
        result = ws.query([
            CohortMetric(123, "Power Users"),
            CohortMetric(
                CohortDefinition(
                    CohortCriteria.has_property("plan", "enterprise")
                ),
                name="Enterprise Users",
            ),
        ])

        # Mix cohort and event metrics with a formula
        result = ws.query(
            [
                CohortMetric(123, "Active Users"),
                Metric("Purchase", math="unique"),
            ],
            formula="(B / A) * 100",
            formula_label="Purchase Rate",
            unit="week",
        )

        # Cohort size as a KPI
        result = ws.query(
            CohortMetric(123, "Power Users"),
            mode="total",
        )
        total = result.df["count"].iloc[0]
        ```
    """

    cohort: int | CohortDefinition
    name: str | None = None
```

**`events` parameter type expansion** (on `query()` only):

From:
```python
events: str | Metric | Formula | Sequence[str | Metric | Formula]
```
to:
```python
events: str | Metric | CohortMetric | Formula | Sequence[str | Metric | CohortMetric | Formula]
```

**Constraint:** `CohortMetric` is only valid in `query()`, NOT in `query_funnel()`, `query_retention()`, or `query_flow()`. This is enforced by the type system (those methods don't accept `CohortMetric` in their signatures) and by validation.

---

## 6. Bookmark JSON Mapping

### 6.1 Cohort Filter → `sections.filter[]`

```python
# Filter.in_cohort(123, "Power Users")
# generates:
{
    "dataset": "$mixpanel",
    "value": "$cohorts",
    "resourceType": "events",
    "profileType": null,
    "search": "",
    "dataGroupId": null,
    "filterType": "list",
    "filterOperator": "contains",
    "filterValue": [
        {
            "cohort": {
                "id": 123,
                "name": "Power Users",
                "negated": false
            }
        }
    ],
    "propertyObjectKey": null,
    "isHidden": false,
    "determiner": "all"
}
```

```python
# Filter.not_in_cohort(789, "Bots")
# generates:
{
    "dataset": "$mixpanel",
    "value": "$cohorts",
    "resourceType": "events",
    "profileType": null,
    "search": "",
    "dataGroupId": null,
    "filterType": "list",
    "filterOperator": "does not contain",
    "filterValue": [
        {
            "cohort": {
                "id": 789,
                "name": "Bots",
                "negated": false
            }
        }
    ],
    "propertyObjectKey": null,
    "isHidden": false,
    "determiner": "all"
}
```

### 6.2 Cohort Breakdown → `sections.group[]`

```python
# CohortBreakdown(123, "Power Users")
# generates:
{
    "value": ["Power Users", "Not In Power Users"],
    "resourceType": "events",
    "profileType": null,
    "search": "",
    "dataGroupId": null,
    "propertyType": null,
    "typeCast": null,
    "cohorts": [
        {
            "id": 123,
            "name": "Power Users",
            "negated": false,
            "data_group_id": null,
            "groups": []
        },
        {
            "id": 123,
            "name": "Power Users",
            "negated": true,
            "data_group_id": null,
            "groups": []
        }
    ],
    "isHidden": false
}
```

```python
# CohortBreakdown(123, "Power Users", include_negated=False)
# generates only the "in" segment:
{
    "value": ["Power Users"],
    "cohorts": [
        {
            "id": 123,
            "name": "Power Users",
            "negated": false,
            "data_group_id": null,
            "groups": []
        }
    ],
    ...
}
```

### 6.3 Cohort Metric → `sections.show[]`

```python
# CohortMetric(123, "Power Users")
# generates:
{
    "type": "metric",
    "behavior": {
        "type": "cohort",
        "name": "Power Users",
        "id": 123,
        "resourceType": "cohorts",
        "dataGroupId": null,
        "dataset": "$mixpanel",
        "filtersDeterminer": "all",
        "filters": []
    },
    "measurement": {
        "math": "unique",
        "property": null,
        "perUserAggregation": null
    },
    "isHidden": false
}
```

---

## 7. Validation Rules

### 7.1 Cohort Filter Validation (Layer 1)

| Code | Rule | Message |
|------|------|---------|
| CF1 | `cohort_id` must be a positive integer | `cohort_id must be a positive integer (got {value})` |
| CF2 | `name`, if provided, must be non-empty | `cohort name must be non-empty when provided` |

These rules are enforced in the `Filter.in_cohort()` and `Filter.not_in_cohort()` class methods.

### 7.2 Cohort Breakdown Validation (Layer 1)

| Code | Rule | Message |
|------|------|---------|
| CB1 | `cohort_id` must be a positive integer | `CohortBreakdown cohort_id must be a positive integer` |
| CB2 | `name`, if provided, must be non-empty | `CohortBreakdown name must be non-empty when provided` |
| CB3 | Retention: `CohortBreakdown` is mutually exclusive with `GroupBy` | `query_retention does not support mixing CohortBreakdown with property GroupBy` |

### 7.3 Cohort Metric Validation (Layer 1)

| Code | Rule | Message |
|------|------|---------|
| CM1 | `cohort_id` must be a positive integer | `CohortMetric cohort_id must be a positive integer` |
| CM2 | `name`, if provided, must be non-empty | `CohortMetric name must be non-empty when provided` |
| CM3 | `CohortMetric` cannot use `math`/`math_property`/`per_user` top-level params | `math/math_property/per_user parameters are not applicable to CohortMetric (cohorts always use math="unique")` |
| CM4 | `CohortMetric` is only valid in `query()`, not other query methods | Enforced by type signature |

### 7.4 Bookmark Structure Validation (Layer 2 Extension)

| Code | Rule | Message |
|------|------|---------|
| B22 | Cohort behavior requires `behavior.id` (positive integer) | `cohort behavior requires a positive integer id` |
| B23 | Cohort behavior `resourceType` must be `"cohorts"` | `cohort behavior resourceType must be "cohorts"` |
| B24 | Cohort behavior `math` must be `"unique"` | `cohort behavior only supports math="unique"` |
| B25 | Cohort filter `value` must be `"$cohorts"` | (structural check in `_build_filter_entry`) |
| B26 | Cohort group entry must have non-empty `cohorts` array | `cohort group_by requires at least one cohort entry` |

---

## 8. Implementation Architecture

### 8.1 Changes to Shared Infrastructure

#### `types.py` — New Types

```python
# New input types
CohortMetric        # frozen dataclass — cohort_id, name
CohortBreakdown     # frozen dataclass — cohort_id, name, include_negated

# Type alias updates
CohortGroupBy = str | GroupBy | CohortBreakdown
CohortGroupByParam = CohortGroupBy | list[CohortGroupBy] | None
```

#### `_build_filter_entry()` — Extended for Cohort Filters

The existing method detects `filter._property == "$cohorts"` and generates the cohort-specific JSON structure instead of the standard property filter structure.

Key difference: cohort filters use `filterValue: [{cohort: {id, name, negated}}]` (array of cohort objects) instead of `filterValue: [scalar_value]`.

#### `_build_group_section()` — Extended for Cohort Breakdowns

When a `CohortBreakdown` is encountered in the `group_by` list, the builder generates a `sections.group[]` entry with:
- `cohorts` array (with optional negated entry)
- `value` array of display labels
- `propertyType: null` (not a property)

When a `GroupBy` or string is encountered, existing behavior is preserved.

#### `_build_query_params()` — Extended for Cohort Metrics

When a `CohortMetric` is encountered in the resolved events list, the builder generates a `sections.show[]` entry with:
- `behavior.type: "cohort"` and `behavior.resourceType: "cohorts"`
- `behavior.id` (integer cohort ID) instead of `behavior.name` (event name)
- `measurement.math: "unique"` (always, ignoring top-level `math` param)

### 8.2 Changes Per Query Method

| Method | Cohort Filter | Cohort Breakdown | Cohort Metric |
|--------|-------------|-----------------|---------------|
| `query()` | `where=Filter.in_cohort(...)` | `group_by=CohortBreakdown(...)` | `events=CohortMetric(...)` |
| `query_funnel()` | `where=Filter.in_cohort(...)` | `group_by=CohortBreakdown(...)` | N/A |
| `query_retention()` | `where=Filter.in_cohort(...)` | `group_by=CohortBreakdown(...)` (exclusive with `GroupBy`) | N/A |
| `query_flow()` | `where=Filter.in_cohort(...)` | N/A | N/A |

#### `query_flow()` Cohort Filter — Special Handling

Flows use the legacy `filter_by_cohort` format (tree structure) rather than `sections.filter[]`. When a `Filter.in_cohort()` is detected in `query_flow()`'s `where=` parameter, it is converted to the flows-specific `filter_by_cohort` tree via a new `_build_flow_cohort_filter()` helper:

```python
# Filter.in_cohort(123, "Power Users") in query_flow()
# generates (at top level of flow params, not in sections):
{
    "filter_by_cohort": {
        "operator": "or",
        "children": [
            {
                "cohort": {
                    "id": 123,
                    "name": "Power Users",
                    "negated": false
                }
            }
        ]
    }
}
```

### 8.3 Validation Changes

#### `validate_query_args()` — Extended

- Detect `CohortMetric` entries in the events list
- Skip `math`/`math_property`/`per_user` validation for `CohortMetric` entries (they always use `math="unique"`)
- Validate `CohortMetric.cohort_id` is a positive integer

#### `validate_funnel_args()` / `validate_retention_args()` — Extended

- Validate `CohortBreakdown` entries in `group_by`
- Retention: reject mixed `CohortBreakdown` + `GroupBy` in same `group_by` list (CB3)

#### `validate_bookmark()` Layer 2 — Extended

- Add B22-B26 rules for cohort behavior validation
- When `behavior.type == "cohort"`, check `behavior.id` instead of `behavior.name`
- Validate `measurement.math == "unique"` for cohort behaviors

### 8.4 No Response Format Changes

All three cohort capabilities produce responses that are structurally compatible with existing result types:

- **Cohort metric**: Same `series` format as event metrics → `QueryResult` handles it
- **Cohort filter**: Same response shape, just filtered data → no result type changes
- **Cohort breakdown**: Series keys include cohort labels → DataFrame columns naturally accommodate this

---

## 9. Example Calls

### 9.1 Cohort Filter — Insights

```python
# "How many purchases did Power Users make last 30 days?"
result = ws.query(
    "Purchase",
    where=Filter.in_cohort(123, "Power Users"),
)

# "Purchases by non-bot users on iOS"
result = ws.query(
    "Purchase",
    where=[
        Filter.not_in_cohort(789, "Bots"),
        Filter.equals("platform", "iOS"),
    ],
)
```

### 9.2 Cohort Filter — Funnels

```python
# "Signup → Purchase funnel for organic users only"
result = ws.query_funnel(
    ["Signup", "Purchase"],
    where=Filter.in_cohort(456, "Organic Users"),
    conversion_window=14,
)
```

### 9.3 Cohort Filter — Retention

```python
# "Week-over-week retention for premium users"
result = ws.query_retention(
    "Login", "Login",
    where=Filter.in_cohort(123, "Premium Users"),
    retention_unit="week",
    last=90,
)
```

### 9.4 Cohort Breakdown — Insights

```python
# "Compare purchases between Power Users and everyone else"
result = ws.query(
    "Purchase",
    group_by=CohortBreakdown(123, "Power Users"),
)

# "Purchases broken down by cohort AND platform"
result = ws.query(
    "Purchase",
    group_by=[
        CohortBreakdown(123, "Power Users"),
        GroupBy("platform"),
    ],
)
```

### 9.5 Cohort Breakdown — Funnels

```python
# "How does funnel conversion differ for Enterprise vs. everyone?"
result = ws.query_funnel(
    ["Signup", "Add to Cart", "Purchase"],
    group_by=CohortBreakdown(456, "Enterprise"),
)
```

### 9.6 Cohort Breakdown — Retention (Exclusive)

```python
# "Retention curve segmented by cohort"
result = ws.query_retention(
    "Signup", "Login",
    group_by=CohortBreakdown(123, "Power Users"),
    retention_unit="week",
)

# ERROR: Cannot mix CohortBreakdown with GroupBy in retention
result = ws.query_retention(
    "Signup", "Login",
    group_by=[CohortBreakdown(123), GroupBy("platform")],  # raises ValueError
)
```

### 9.7 Cohort Metric — Cohorts Over Time

```python
# "How is the Power Users cohort growing?"
result = ws.query(
    CohortMetric(123, "Power Users"),
    last=90,
    unit="week",
)

# "Compare two cohort sizes over time"
result = ws.query([
    CohortMetric(123, "Power Users"),
    CohortMetric(456, "Enterprise Users"),
])

# "What percentage of active users are Power Users?"
result = ws.query(
    [
        Metric("Login", math="unique"),
        CohortMetric(123, "Power Users"),
    ],
    formula="(B / A) * 100",
    formula_label="Power User %",
    unit="week",
)
```

### 9.8 Persisting Cohort Queries

```python
# Build params and save as a bookmark
result = ws.query(
    "Purchase",
    where=Filter.in_cohort(123, "Power Users"),
    group_by=CohortBreakdown(456, "Enterprise"),
)

ws.create_bookmark(CreateBookmarkParams(
    name="Enterprise Purchases (Power Users)",
    bookmark_type="insights",
    params=result.params,
))
```

---

## 10. Scope Boundaries

### In Scope

- `CohortCriteria` — typed building blocks for cohort definitions (behavioral, property, cohort-membership criteria)
- `CohortDefinition` — composable AND/OR builder producing valid `selector` + `behaviors` JSON
- `Filter.in_cohort(cohort, name)` and `Filter.not_in_cohort(cohort, name)` — cohort membership filters
- `CohortBreakdown(cohort, name, include_negated)` — cohort-based breakdowns
- `CohortMetric(cohort, name)` — cohort size over time metrics
- **Both saved cohort references (by `int` ID) AND inline definitions (via `CohortDefinition`)** — all three integration points accept `int | CohortDefinition`
- All three capabilities in `query()` (insights)
- Cohort filter and breakdown in `query_funnel()` and `query_retention()`
- Cohort filter in `query_flow()` (via `filter_by_cohort` legacy format)
- Client-side validation (CD1-CD10, CF1-CF2, CB1-CB3, CM1-CM3, B22-B26)
- `.params` on results includes generated cohort JSON for debugging
- `CohortDefinition.to_dict()` for standalone definition inspection
- Integration with `CreateCohortParams(definition=cohort_def.to_dict())` for saving ad-hoc cohorts
- `build_params()`, `build_funnel_params()`, `build_retention_params()`, `build_flow_params()` all support cohort capabilities

### Could Be Added Later (v2+)

| Feature | Complexity | Trigger |
|---------|-----------|---------|
| Multi-cohort filters (multiple cohort IDs in one `Filter`) | Low | `Filter.in_cohorts([id1, id2])` |
| `data_group_id` / B2B group scoping | Medium | B2B analytics users need entity-group scoping |
| Cohort breakdown in `query_flow()` | Medium | Flows breakdown uses different top-level structure |
| Validate cohort ID exists via API | Low | `ws.get_cohort(id)` before query; opt-in |
| Funnel-based cohort criteria | Medium | `CohortCriteria.completed_funnel(steps=[...])` |
| Report-based cohort criteria | Medium | `CohortCriteria.from_retention_report(bookmark_id=...)` |
| Per-day frequency criteria | Low | `CohortCriteria.did_event(..., count_type="day")` |

### Explicitly Out of Scope

| Feature | Reason |
|---------|--------|
| Creating/modifying cohorts via query API | Separate concern — use existing cohort CRUD methods |
| `data_group_id` / B2B groups | Adds complexity for a niche use case; `null` works for standard projects |
| Cohort metrics in funnels/retention/flows | Not supported by Mixpanel's API (cohort metric is insights-only) |
| `sections.cohorts[]` legacy format | Always generate modern `sections.group[]` format for breakdowns |
| Report-based cohort definitions (funnel_report, retention_report, addiction_report, flows_report) | Complex internal structures; v2+ with dedicated builder methods |
| `groups` (modern) format generation | Legacy `selector`+`behaviors` format works everywhere; `groups` is a UI abstraction |

---

## 11. Implementation Plan

### Phase 0: Cohort Definition Builder (Prerequisite)

The foundation for all subsequent phases. Produces valid JSON for both CRUD and inline queries.

1. Add `CohortCriteria` frozen dataclass to `types.py`
   - `did_event()`, `did_not_do_event()` — behavioral criteria with frequency + time window
   - `has_property()`, `property_is_set()`, `property_is_not_set()` — user profile property criteria
   - `in_cohort()`, `not_in_cohort()` — cohort membership criteria
   - Internal `_selector_node`, `_behavior_key`, `_behavior` fields
2. Add `CohortDefinition` frozen dataclass to `types.py`
   - `__init__(*criteria)` — single or AND-combined criteria
   - `all_of()`, `any_of()` — class methods for explicit AND/OR
   - `to_dict()` — produces `{"selector": {...}, "behaviors": {...}}`
   - Recursive nesting support for `(A AND B) OR C` patterns
3. Add `_build_selector_tree()` — constructs expression tree from criteria
4. Add `_build_event_selector()` — converts `Filter` objects to event selector expressions
5. Add validation rules CD1-CD10
6. Tests (TDD): definition construction, serialization round-trip, nested boolean logic, validation edge cases
7. Property-based tests (Hypothesis) for `CohortDefinition`
8. Exports in `__init__.py`: `CohortCriteria`, `CohortDefinition`

### Phase 1: Cohort Filters (Shared Infrastructure)

The highest-value query integration. Immediately useful across all query types. Now accepts `int | CohortDefinition`.

1. Add `Filter.in_cohort()` and `Filter.not_in_cohort()` — accept `int | CohortDefinition`
2. Extend `_build_filter_entry()` to detect `_property == "$cohorts"` and generate cohort filter JSON
   - For `int` cohort: `filterValue: [{cohort: {id, name, negated: false}}]`
   - For `CohortDefinition`: `filterValue: [{cohort: {raw_cohort: def.to_dict(), name, negated: false}}]`
3. Add `_build_flow_cohort_filter()` for flows-specific `filter_by_cohort` tree
4. Add validation rules CF1-CF2
5. Extend `_build_flow_params()` to extract cohort filters into `filter_by_cohort`
6. Tests (TDD): saved + inline filter construction, bookmark validation, flow cohort filter

### Phase 2: Cohort Breakdowns

1. Add `CohortBreakdown` frozen dataclass — `cohort: int | CohortDefinition`
2. Update `group_by` parameter type on `query()`, `query_funnel()`, `query_retention()`
3. Extend `_build_group_section()` to handle `CohortBreakdown` entries
   - For `int`: `cohorts: [{id, name, negated, data_group_id: null, groups: []}]`
   - For `CohortDefinition`: `cohorts: [{raw_cohort: def.to_dict(), name, negated, ...}]`
4. Add validation rules CB1-CB3 (including retention mutual exclusivity)
5. Extend Layer 2 `validate_bookmark()` with B26
6. Tests (TDD): saved + inline group construction, retention exclusivity, mixed groups

### Phase 3: Cohort Metrics

1. Add `CohortMetric` frozen dataclass — `cohort: int | CohortDefinition`
2. Update `events` parameter type on `query()` to accept `CohortMetric`
3. Extend `_resolve_and_build_params()` to handle `CohortMetric` in events list
4. Extend `_build_query_params()` to generate `behavior.type: "cohort"` show entries
   - For `int`: `behavior.id = cohort_id`
   - For `CohortDefinition`: `behavior.raw_cohort = def.to_dict()`
5. Add validation rules CM1-CM3, B22-B24
6. Tests (TDD): saved + inline show clause construction, formula interaction, validation

### Phase 4: Polish

- Property-based tests (Hypothesis) for all new types including `CohortDefinition` ↔ query integration
- Mutation testing on new validation rules (CD1-CD10, CF1-CF2, CB1-CB3, CM1-CM3, B22-B26)
- Documentation: docstrings, examples in context docs
- Exports in `__init__.py`

---

## 12. Design Rationale

### 12.1 Why a Cohort Definition Builder as Phase 0

**Decision:** Build `CohortCriteria` + `CohortDefinition` before any query integration.

**Rationale:** Every cohort integration point (filter, breakdown, metric) needs to reference a cohort. Supporting only saved cohort IDs would be a half-measure — LLM agents cannot create saved cohorts interactively. The builder enables:
1. **Inline ad-hoc cohorts** in queries without pre-saving
2. **Programmatic cohort creation** via `create_cohort(definition=def.to_dict())`
3. **Type-safe construction** — no raw dict guessing
4. **Composability** — combine criteria with AND/OR, nest arbitrarily

Without Phase 0, agents would need a two-step workflow (create cohort, then query) for every ad-hoc segment. With Phase 0, inline cohorts are a single expression.

### 12.2 Why the Legacy `selector` + `behaviors` Format

**Decision:** Generate the legacy expression tree format, not the modern `groups` format.

**Alternatives considered:**
- (A) Generate `groups` format (modern UI format)
- (B) Generate `selector` + `behaviors` format (legacy backend format)

**Why (B) wins:**
1. **Universal compatibility** — works in `create_cohort()` AND `raw_cohort` in inline query references. The `groups` format is not accepted in `raw_cohort` by all code paths.
2. **Direct backend mapping** — the backend parses `selector` + `behaviors` natively. The `groups` format requires a conversion step (UI → selector/behaviors).
3. **Explicit semantics** — each behavior is a named, inspectable entry. The `groups` format bundles behaviors inside `PropertyFilter.customProperty` objects.
4. **Simpler construction** — expression trees are straightforward to build programmatically. The `groups` format requires constructing `PropertyFilter` UI model objects.

### 12.3 Why `Filter.in_cohort()` Instead of a Separate `cohort_filter=` Parameter

**Decision:** Add class methods to the existing `Filter` type.

**Why:** Cohort membership filtering is semantically the same operation as property filtering — restricting which users are included. The `where=` parameter already accepts `Filter | list[Filter]`. Adding `Filter.in_cohort()` lets users combine cohort and property filters naturally:

```python
where=[Filter.in_cohort(123), Filter.equals("platform", "iOS")]
```

### 12.4 Why `CohortBreakdown` Instead of Extending `GroupBy`

**Decision:** A new `CohortBreakdown` type, accepted alongside `GroupBy` in `group_by=`.

**Why:** Cohort breakdowns and property breakdowns have fundamentally different JSON structures. `GroupBy` produces `{propertyName, propertyType, value, customBucket}`. A cohort breakdown produces `{cohorts: [...], value: ["name", "Not In name"]}`. A union type keeps each type focused.

### 12.5 Why `CohortMetric` Instead of Extending `Metric`

**Decision:** A new `CohortMetric` type, accepted alongside `Metric` in `events=`.

**Why:** `Metric` wraps an event name with aggregation settings. `CohortMetric` wraps a cohort reference — no event name, no math choice (always `"unique"`), no property. Zero field overlap. A shared type would have mostly-inapplicable fields.

### 12.6 Why `int | CohortDefinition` on All Integration Points

**Decision:** Every cohort parameter accepts both `int` (saved) and `CohortDefinition` (inline).

**Rationale:** This is the core design upgrade from v1. The type union provides:
1. **Maximum flexibility** — use saved cohorts when they exist, inline when they don't
2. **Uniform API** — callers don't need separate methods for saved vs. inline
3. **Agent-friendly** — an LLM can construct an inline cohort in a single expression without a multi-step save-then-reference workflow
4. **Progressive disclosure** — `Filter.in_cohort(123)` for the simple case, `Filter.in_cohort(CohortDefinition(...))` for the powerful case

### 12.7 Why `name` is Optional for Saved Cohorts, Required for Inline

**Decision:** `name` is optional when referencing saved cohorts (by ID), but effectively required for inline `CohortDefinition` objects.

**Rationale:** Saved cohorts have names in the database — the API resolves them from IDs. Inline cohorts have no stored name, so the caller must provide one for meaningful series labels and bookmark display. The parameter is typed as `str | None` for uniformity, but validation warns when an inline cohort lacks a name.

---

## Appendix A: Source Code References

### Analytics Codebase (Canonical Implementation)

| Area | File | Key Lines | What |
|------|------|-----------|------|
| MetricType enum | `iron/common/types/reports/bookmark.ts` | 882-894 | `MetricType.Cohort = "cohort"` |
| InsightsResourceType | `iron/common/types/reports/bookmark.ts` | 819-829 | `Cohort = "cohort"`, `Cohorts = "cohorts"` |
| Behavior interface | `iron/common/types/reports/bookmark.ts` | 517-552 | `type`, `id`, `name`, `dataGroupId`, `raw_cohort` |
| GroupByCohort interface | `iron/common/types/reports/bookmark.ts` | 288-304 | Cohort breakdown entry type |
| CohortsClause | `iron/common/report/insights/models/cohorts-clause.ts` | 9-16 | `id`, `name`, `negated`, `raw_cohort`, `data_group_id` |
| Cohort filter default | `iron/common/report/insights/models/filter-clause.ts` | 67-78 | `defaultCohortsAttrs()` |
| `$cohorts` constant | `iron/common/widgets/property-filter-menu/models/insights-filter.ts` | 76 | `INSIGHTS_COHORT_TYPE = "$cohorts"` |
| Cohort metric detection | `api/version_2_0/insights/params.py` | 2475-2476 | `_is_cohorts_metric()` |
| Cohort filter detection | `api/version_2_0/insights/params_util.py` | 156-157 | `is_cohort_filter()` |
| Cohort query execution | `api/version_2_0/insights/cohorts.py` | 250 | `cohorts_size_over_time()` |
| Segment by cohorts ARB | `api/version_2_0/cohorts/selector.py` | 4-23 | `segment_by_cohorts_action()` |
| Cohort group-by processing | `api/version_2_0/insights/segmentation_arb.py` | 427-445 | ARB group action with cohorts |
| Retention cohort restriction | `api/version_2_0/retention/util.py` | 270-271 | Mutual exclusivity with property breakdowns |
| Cohort filter → tree | `bookmark_parser/common/property_filter/utils.py` | 1-15 | `convert_cohort_property_filter_to_tree_filter()` |
| Django Cohort model | `engage/models.py` | 195-355 | `id: int`, `data_group_id: BigIntegerField` |

### mixpanel_data Codebase (Our Implementation)

| Area | File | Key Lines | What |
|------|------|-----------|------|
| `VALID_METRIC_TYPES` | `_internal/bookmark_enums.py` | 242-255 | Already includes `"cohort"` |
| `VALID_RESOURCE_TYPES` | `_internal/bookmark_enums.py` | 224-234 | Already includes `"cohorts"`, `"cohort"` |
| `_validate_show_clause()` | `_internal/validation.py` | 1936+ | Needs cohort branch for `behavior.id` check |
| `_build_filter_entry()` | `workspace.py` | varies | Needs cohort filter extension |
| `_build_query_params()` | `workspace.py` | 1659+ | Needs cohort behavior generation |
| Cohort CRUD | `workspace.py` | 4499-4669 | `list_cohorts_full()`, `get_cohort()`, etc. |
| `Cohort` type | `types.py` | 3325+ | Pydantic model for CRUD, not query |
| `CreateCohortParams` | `types.py` | 3427+ | Accepts `definition` dict (target for `CohortDefinition.to_dict()`) |

### Cohort Definition Builder References (Phase 0)

| Area | File | Key Lines | What |
|------|------|-----------|------|
| Cohort model (TS) | `iron/common/query-builder/cohorts-query-builder/models/cohort.ts` | 81-648 | `Cohort` class with `serialize()` producing `selector`+`behaviors` or `groups` |
| Behavior model (TS) | `iron/common/query-builder/cohorts-query-builder/models/behaviors/behavior.ts` | 32-285 | `Behavior` class: `count`, `funnel`, `report`, `window`, `from_date`/`to_date` |
| BehaviorCount (TS) | `iron/common/query-builder/cohorts-query-builder/models/behaviors/behavior-count.ts` | 10-50 | `BehaviorCount`: `event_selector` + `type` (absolute/day) |
| EventSelector (TS) | `iron/common/query-builder/cohorts-query-builder/models/behaviors/event-selector.ts` | 4-18 | `EventSelector`: `event` + `selector` (expression tree) |
| Expression enums (TS) | `iron/common/query-builder/cohorts-query-builder/models/enums/expression-enums.ts` | 1-51 | `ArithmeticOperator`, `BehaviorCountType`, `Property` enums |
| Serialized types (TS) | `iron/common/query-builder/cohorts-query-builder/models/types/serialized-cohort-types.ts` | 29-55 | `SerializedCohort`, `SerializedBehavior`, `RawCohort` interfaces |
| CohortGroupEntry (TS) | `iron/common/query-builder/query-entry-section/types.ts` | 508-512 | Modern `groups` format entry type |
| FiltersOperator (TS) | `iron/common/query-builder/query-entry-section/types.ts` | 299 | AND/OR/Then operators for group combining |
| Report-based cohorts (TS) | `iron/common/query-builder/cohorts-query-builder/models/types/serialized-cohort-types.ts` | 100-105 | `ReportBasedCohorts` enum: Addiction, Flows, Funnels, Retention |
| Cohort Django model | `engage/models.py` | 195-355 | DB schema: `definition` (JSON text), `data_group_id` |
