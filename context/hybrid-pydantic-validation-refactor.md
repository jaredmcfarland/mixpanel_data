# Hybrid Pydantic Validation Refactor

> **Status**: Design Document (Pre-Implementation)  
> **Scope**: Migrate 14 frozen dataclasses to Pydantic BaseModel; consolidate dual validation channels; preserve agent-friendly error reporting and conformance suite compatibility.  
> **Date**: 2026-04-08

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Design Constraints](#3-design-constraints)
4. [Architecture Overview](#4-architecture-overview)
5. [Type Migration Strategy](#5-type-migration-strategy)
6. [Validation Rule Disposition](#6-validation-rule-disposition)
7. [Error Channel Unification](#7-error-channel-unification)
8. [Conformance Suite Compatibility](#8-conformance-suite-compatibility)
9. [Implementation Plan](#9-implementation-plan)
10. [Risk Assessment](#10-risk-assessment)
11. [Appendices](#11-appendices)

---

## 1. Executive Summary

The `mixpanel_data` validation system currently has **two independent error channels** that surface the same class of problems through incompatible mechanisms:

1. **`__post_init__` on frozen dataclasses** — raises raw `ValueError` at construction time, bypassing the structured error system entirely.
2. **`validation.py` functions** — returns `list[ValidationError]` with rich metadata (`code`, `path`, `severity`, `suggestion`, `fix`), collected non-fail-fast, wrapped in `BookmarkValidationError`.

This creates **15 duplicate validation rules** implemented in both places, **two different error formats** for callers to handle, and a fundamental incoherence: constructing `GroupBy("", bucket_size=-1)` raises a bare `ValueError`, but passing that same configuration through `validate_query_args()` would return structured errors with codes `V17_EMPTY_EVENT` and `V12_BUCKET_SIZE_POSITIVE`.

### The Hybrid Approach

Convert the 14 frozen dataclasses to Pydantic `BaseModel(frozen=True)`, moving single-field constraints into `@field_validator` methods that produce the project's native `ValidationError` objects. Keep `validation.py` for cross-field business rules and the query-level validation API. Eliminate the dual error channel.

### What Changes

| Before | After |
|--------|-------|
| 14 frozen dataclasses with `__post_init__` | 14 frozen Pydantic models with `@field_validator` |
| `ValueError` from construction | `PydanticValidationError` from construction (with structured details) |
| 15 duplicate rules across two systems | Single source of truth per rule |
| validation.py: 2,854 lines, 76 rules | validation.py: ~2,200 lines, ~55 rules (~15 redundant rules removed) |
| Two error channels for callers | One error channel: `BookmarkValidationError` everywhere |
| 3 types with no construction validation | All types validate invariants at construction |

### What Does NOT Change

| Preserved | Why |
|-----------|-----|
| All 100+ error codes | Stable public contract shared with TypeScript |
| All error paths | Machine-parseable locations for agent self-correction |
| All severity levels | Error (blocks) vs warning (informational) distinction |
| Fuzzy "did you mean?" suggestions | Agent-friendliness differentiator |
| `fix` suggestion dicts | Agent-friendliness differentiator |
| Non-fail-fast error accumulation | Critical for agent workflows (fix N issues in one pass) |
| validation.py public function signatures | Public API and harness compatibility |
| `BookmarkValidationError` exception type | Public API contract |
| `ValidationError` dataclass shape | Shared with TypeScript implementation |

**What adapts**: Conformance suite is regenerated from updated Python oracle. ~545 Python tests are updated per-phase to reflect structured errors replacing bare `ValueError`.

---

## 2. Problem Statement

### 2.1 Dual Error Channel

```
                    Caller (workspace.py / user code)
                    ┌──────────────────────────────────┐
                    │                                  │
            ┌───────┴───────┐              ┌───────────┴──────────┐
            │  ValueError   │              │ BookmarkValidation   │
            │  (unstructured)│              │ Error (structured)   │
            └───────┬───────┘              └───────────┬──────────┘
                    │                                  │
         ┌──────────┴──────────┐           ┌───────────┴──────────┐
         │ __post_init__       │           │ validation.py        │
         │ (10 dataclasses)    │           │ (9 public functions) │
         └─────────────────────┘           └──────────────────────┘
```

**Impact**: An LLM agent calling the Python API receives a bare `ValueError("GroupBy.bucket_size must be positive, got -1")` for construction errors but a rich `BookmarkValidationError` with error codes, suggestions, and fixes for query-level errors. The agent cannot programmatically distinguish error categories or apply automated fixes from the `ValueError` path.

### 2.2 Duplicate Rules

15 rules are implemented in both `__post_init__` (raising `ValueError`) and `validation.py` (returning `ValidationError`). These can diverge:

| Rule | `__post_init__` check | `validation.py` check | Divergence |
|------|----------------------|----------------------|------------|
| Exclusion step order | `to_step < from_step` (EX3) | `to_step <= from_step` (F4) | `>=` vs `>` — different boundary behavior |
| Event name empty | Raises `ValueError` immediately | Returns `ValidationError`, continues collecting | Fail-fast vs accumulate |
| Bucket size positive | Raises `ValueError` | Returns `ValidationError` with code | No code in ValueError |

The `>=` vs `>` divergence for exclusion step ordering is a real semantic difference — `__post_init__` allows `to_step == from_step` but `validation.py` does not.

### 2.3 Missed Validation in Dataclasses

Several types perform **no construction-time validation** despite having obvious invariants:

| Type | Missing validation |
|------|-------------------|
| `PropertyInput` | `name` can be empty string |
| `InlineCustomProperty` | `formula` can be empty, `inputs` can be empty dict, input keys can be lowercase |
| `CustomPropertyRef` | `id` can be 0 or negative |

These invariants are only checked by `_validate_custom_property()` in validation.py (rules CP1-CP6), meaning an `InlineCustomProperty(formula="", inputs={})` constructs successfully and silently, only failing later during query validation.

---

## 3. Design Constraints

### 3.1 Conformance Suite (Downstream Artifact)

The `conformance/` suite in `jaredmixpanel/mixpanel-bookmark` is **generated from the Python implementation** via `conformance/generate.py`. Python is the oracle — the suite is derived from the validators, not the other way around.

**This means the conformance suite is regenerated after refactoring, not preserved as-is.**

The suite's structural properties are worth preserving as design goals (not hard constraints):

1. **Error codes are stable** — 100+ codes like `V1_MATH_REQUIRES_PROPERTY`. Avoid unnecessary renames.
2. **Error paths are meaningful** — paths like `"math"`, `"events[0]"` provide machine-parseable locations.
3. **Severity levels distinguish blocking vs informational** — `"error"` vs `"warning"`.
4. **Non-fail-fast accumulation** — validators report ALL errors in a single pass.
5. **Suggestion presence** — fuzzy "did you mean?" for misspelled enum values.

After the refactor, the workflow is:
1. Update Python validators
2. Run `conformance/generate.py` to regenerate test fixtures from the updated oracle
3. Update TypeScript implementation to match any behavioral changes
4. Run `conformance/differential.py` to verify parity

### 3.2 Public API (Hard Constraints)

- All 14 types are exported from `__init__.py` and documented in `__all__`.
- **Positional-first construction is pervasive**: `Metric("Login")`, `GroupBy("country")`, `FunnelStep("Signup")`, `Exclusion("Logout")`, `CohortMetric(123, "Power Users")`.
- `Filter` uses class methods exclusively — never direct construction.
- `CohortDefinition` uses `init=False` with custom `__init__` and `object.__setattr__` for frozen fields.

### 3.3 Existing Pydantic Conventions (Soft Constraints)

The project already has ~105 Pydantic `BaseModel` subclasses with established patterns:

| Pattern | Usage |
|---------|-------|
| `ConfigDict(frozen=True, extra="allow")` | API response entities |
| `ConfigDict(frozen=True, extra="allow", populate_by_name=True)` | Response entities with aliases |
| No `model_config` | Simple mutation params |
| Only 1 `@field_validator` in the entire codebase | Very sparing use |
| Only 1 `@model_validator` in the entire codebase | Very sparing use |

### 3.4 TypeScript Parity (Soft Constraint)

The TypeScript implementation uses discriminated unions with a `kind` tag field (e.g., `kind: "metric"`). The Python types do not need this tag since Python has `isinstance()`, but any **behavioral** changes to validation must be reflected in both implementations (with Python as the oracle).

---

## 4. Architecture Overview

### 4.1 Current Architecture

```
┌─────────────────────────────────────────────────┐
│                  workspace.py                    │
│  ┌───────────────────────────────────────────┐   │
│  │ build_*_params() methods                  │   │
│  │                                           │   │
│  │  1. Pre-validation type guards            │   │
│  │  2. validate_*_args() → list[VErr]        │──▶│── validation.py (L1)
│  │  3. _build_*_params() → dict              │   │
│  │  4. validate_bookmark() → list[VErr]      │──▶│── validation.py (L2)
│  │  5. Raise BookmarkValidationError         │   │
│  └───────────────────────────────────────────┘   │
│                                                  │
│  User constructs types:                          │
│  ┌───────────────────────────────────────────┐   │
│  │ Metric("Login", math="average")           │   │
│  │ GroupBy("country", bucket_size=50)         │──▶│── __post_init__ → ValueError
│  │ Filter.equals("status", "active")         │   │
│  └───────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### 4.2 Target Architecture

```
┌─────────────────────────────────────────────────┐
│                  workspace.py                    │
│  ┌───────────────────────────────────────────┐   │
│  │ build_*_params() methods                  │   │
│  │                                           │   │
│  │  1. Pre-validation type guards            │   │
│  │  2. validate_*_args() → list[VErr]        │──▶│── validation.py (L1, cross-field only)
│  │  3. _build_*_params() → dict              │   │     delegates single-field to models
│  │  4. validate_bookmark() → list[VErr]      │──▶│── validation.py (L2, unchanged)
│  │  5. Raise BookmarkValidationError         │   │
│  └───────────────────────────────────────────┘   │
│                                                  │
│  User constructs types:                          │
│  ┌───────────────────────────────────────────┐   │
│  │ Metric("Login", math="average")           │   │
│  │ GroupBy("country", bucket_size=50)         │──▶│── Pydantic @field_validator
│  │ Filter.equals("status", "active")         │   │     → PydanticValidationError
│  └───────────────────────────────────────────┘   │     (with structured details)
└─────────────────────────────────────────────────┘
```

### 4.3 Key Architectural Decisions

**AD-1: Pydantic models validate at construction, validation.py validates at composition.**

Single-field invariants (non-empty event name, positive bucket_size, valid enum values) belong on the model — they are properties of the **type itself**. Cross-field rules (math requires property, formula references valid event positions, rolling and cumulative are mutually exclusive) belong in validation.py — they are properties of the **query composition**.

**AD-2: validation.py functions remain the conformance-facing API.**

The conformance harness calls `validate_query_args()`, `validate_funnel_args()`, etc. These functions continue to exist with identical signatures and return `list[ValidationError]`. Internally, they no longer re-check single-field rules that the Pydantic models already enforce — but this is invisible to the conformance suite because those rules cannot be triggered (the model would have already rejected the input at construction time).

**AD-3: Construction errors become structured.**

When a Pydantic model rejects input (e.g., `GroupBy("", bucket_size=-1)`), it raises `pydantic.ValidationError` with structured error details. The project provides a utility to convert this to `BookmarkValidationError` for callers who want the agent-friendly format. The raw Pydantic error is also useful on its own — it includes field paths and error types.

**AD-4: Filter keeps its class method factory pattern.**

`Filter` is unique among the 14 types: it's constructed exclusively via class methods (`Filter.equals(...)`, `Filter.between(...)`) that encode operator/type logic. Converting to Pydantic doesn't change this pattern — the class methods simply return `cls(...)` which triggers Pydantic validation instead of `__post_init__`.

**AD-5: CohortDefinition is deferred.**

`CohortDefinition` uses `init=False` with a custom `__init__` that accepts `*criteria` varargs and `object.__setattr__` to set frozen fields. This pattern is fundamentally incompatible with Pydantic's model initialization. `CohortDefinition` stays as a frozen dataclass in this refactor. It has no `__post_init__` validation duplication and no conformance issues.

---

## 5. Type Migration Strategy

### 5.1 Migration Template

Each frozen dataclass migrates to a Pydantic `BaseModel` following this template:

```python
from pydantic import BaseModel, ConfigDict, field_validator

class Metric(BaseModel):
    """Encapsulates a single event to query with its aggregation settings."""

    model_config = ConfigDict(frozen=True)

    event: str
    math: MathType = "total"
    property: str | CustomPropertyRef | InlineCustomProperty | None = None
    per_user: PerUserAggregation | None = None
    percentile_value: int | float | None = None
    filters: list[Filter] | None = None
    filters_combinator: FiltersCombinator = "all"

    @field_validator("event")
    @classmethod
    def _validate_event(cls, v: str) -> str:
        """M1: Event name must be non-empty with no control characters."""
        validate_event_name(v, "Metric")  # reuse shared helper
        return v
```

**Key differences from current frozen dataclass:**

| Aspect | Frozen Dataclass | Pydantic Model |
|--------|-----------------|----------------|
| Decorator | `@dataclass(frozen=True)` | `model_config = ConfigDict(frozen=True)` |
| Validation hook | `__post_init__` | `@field_validator` / `@model_validator` |
| Error type | `ValueError` | `pydantic.ValidationError` |
| Immutability | `frozen=True` on decorator | `frozen=True` in ConfigDict |
| Positional args | Supported natively | Requires explicit field ordering (Pydantic v2 preserves definition order) |
| `isinstance` check | Works naturally | Works naturally (BaseModel subclass) |

### 5.2 Migration Per Type

#### Tier 1: Simple Types (No Validation)

These types have no `__post_init__` and no class methods. Migration is mechanical.

| Type | Fields | Notes |
|------|--------|-------|
| `PropertyInput` | 3 | Add `@field_validator("name")` for CP6 (non-empty) |
| `CustomPropertyRef` | 1 | Add `@field_validator("id")` for CP1 (positive int) |

**PropertyInput gains validation it never had** — currently `PropertyInput("")` succeeds silently but fails later at CP6. After migration, it fails at construction.

#### Tier 2: Types with Simple Validation

These have `__post_init__` that calls `_validate_event_name()` and nothing else.

| Type | Current `__post_init__` | Migration |
|------|------------------------|-----------|
| `FunnelStep` | FS1: event name check | `@field_validator("event")` calling shared helper |
| `RetentionEvent` | RE1: event name check | `@field_validator("event")` calling shared helper |
| `HoldingConstant` | HC1: non-empty property | `@field_validator("property")` |
| `Formula` | FM1: non-empty expression | `@field_validator("expression")` |

#### Tier 3: Types with Multi-Field Validation

These have `__post_init__` checking relationships between fields.

| Type | Current `__post_init__` | Migration |
|------|------------------------|-----------|
| `Metric` | M1 (event name), M2 (math↔property), M3 (percentile↔value) | `@field_validator("event")` for M1; `@model_validator(mode="after")` for M2, M3 |
| `GroupBy` | GB1 (non-empty property), GB2 (bucket_size > 0), GB3 (bucket_min < bucket_max) | `@field_validator("property")` for GB1; `@field_validator("bucket_size")` for GB2; `@model_validator(mode="after")` for GB3 |
| `Exclusion` | EX1 (event name), EX2 (from_step >= 0), EX3 (to_step order) | `@field_validator("event")` for EX1; `@field_validator("from_step")` for EX2; `@model_validator(mode="after")` for EX3 |
| `FlowStep` | FL1 (event name), FL2 (forward/reverse range 0-5) | `@field_validator("event")` for FL1; `@field_validator("forward", "reverse")` for FL2 |
| `CohortBreakdown` | CB1/CB2 via `_validate_cohort_args` | `@model_validator(mode="after")` |
| `CohortMetric` | CM1/CM2 via `_validate_cohort_args`, CM5 (reject inline CohortDefinition) | `@model_validator(mode="after")` |

#### Tier 4: Types with Class Method Factories

| Type | Pattern | Migration |
|------|---------|-----------|
| `Filter` | 22 class methods, no `__post_init__`, underscore-prefixed fields | Class methods become `@classmethod` on BaseModel returning `cls(...)`. Internal field naming with underscore prefix preserved. Validation in class methods (date format, positive quantity, cohort args) stays in the class methods. |
| `InlineCustomProperty` | `numeric()` class method | Simple migration; add field validators for CP2-CP5 (formula non-empty, inputs non-empty, key format, formula length). **This type gains validation it never had.** |

#### Tier 5: Deferred

| Type | Reason |
|------|--------|
| `CohortDefinition` | `init=False` + custom `__init__` with `*criteria` varargs + `object.__setattr__`. Incompatible with Pydantic initialization. No validation duplication. Stays as frozen dataclass. |

### 5.3 Positional Construction Compatibility

Pydantic v2 supports positional construction **only if fields are defined in order without defaults before fields with defaults**. All 14 types already follow this pattern (required fields first, optional fields with defaults after). Verify:

| Type | Positional field(s) | Works with Pydantic? |
|------|---------------------|---------------------|
| `Metric("Login")` | `event` (first field) | Yes |
| `GroupBy("country")` | `property` (first field) | Yes |
| `FunnelStep("Signup")` | `event` (first field) | Yes |
| `Exclusion("Refund")` | `event` (first field) | Yes |
| `CohortMetric(123, "Power Users")` | `cohort`, `name` (first two) | Yes |
| `CohortBreakdown(123)` | `cohort` (first field) | Yes |
| `RetentionEvent("Login")` | `event` (first field) | Yes |
| `FlowStep("Purchase")` | `event` (first field) | Yes |
| `Formula("A + B")` | `expression` (first field) | Yes |
| `CustomPropertyRef(42)` | `id` (only field) | Yes |
| `PropertyInput("price")` | `name` (first field) | Yes |

**No compatibility issue.** Pydantic v2 BaseModel accepts positional args for fields defined before any field with a default value.

### 5.4 Serialization Compatibility

Current frozen dataclasses have hand-written `to_dict()` methods on **result types** (`SegmentationResult`, `FunnelResult`, etc.) but the 14 query-builder types do **not** have `to_dict()`. They are consumed internally by the bookmark builder which reads their attributes directly.

The migration to Pydantic adds `model_dump()` for free but does **not** require removing any existing methods. The bookmark builder code in `workspace.py` accesses fields via attribute access (e.g., `metric.event`, `group_by.bucket_size`), which works identically on Pydantic models.

**One concern**: `Filter` uses underscore-prefixed fields (`_property`, `_operator`, `_value`). Pydantic treats leading underscores as private by default. Solution: use `Field(alias="_property")` with `populate_by_name=True`, or rename to non-underscore fields. Recommended: **rename to non-underscore fields** since these fields are already accessed directly by the bookmark builder (e.g., `f._property`, `f._operator`). The underscore prefix was a convention choice, not a privacy requirement. The bookmark builder code that accesses these fields will need updating either way.

**Alternative for Filter**: Keep underscore-prefixed fields with `model_config = ConfigDict(frozen=True, populate_by_name=True)` and explicitly declare each field with `Field(alias="...")`. This preserves backward compatibility for any code accessing `filter._property` directly. Given that Filter is only constructed via class methods and consumed internally, the rename is cleaner.

---

## 6. Validation Rule Disposition

### 6.1 Rules That Move INTO Models (42 rules)

These rules become `@field_validator` or `@model_validator` on the Pydantic models. They are **removed from validation.py** because Pydantic enforces them at construction time — by the time validation.py sees the objects, these invariants are already guaranteed.

#### 6.1.1 String Sanity Checks → `@field_validator` (21 rules)

All use a shared `validate_event_name()` helper (already exists as `_validate_event_name` in types.py):

| Rules | Model | Field |
|-------|-------|-------|
| V17, V22, V22_INVISIBLE | `Metric` | `event` |
| F2, F2_CONTROL, F2_INVISIBLE | `FunnelStep` | `event` |
| F4, F4_CONTROL | `Exclusion` | `event` |
| F8_EMPTY | `HoldingConstant` | `property` |
| R1, R1_CONTROL, R1_INVISIBLE | `RetentionEvent` (via born_event path) | `event` |
| R2, R2_CONTROL, R2_INVISIBLE | `RetentionEvent` (via return_event path) | `event` |
| FL2, FL2_CONTROL, FL2_INVISIBLE | `FlowStep` | `event` |
| CP2 | `InlineCustomProperty` | `formula` |
| CP6 | `PropertyInput` | `name` |
| FM1 | `Formula` | `expression` |

#### 6.1.2 Single-Field Constraints → `@field_validator` (12 rules)

| Rule | Model | Field | Check |
|------|-------|-------|-------|
| V6 | (query-level, stays in validation.py) | `rolling` | positive |
| V12 / GB2 | `GroupBy` | `bucket_size` | positive when not None |
| V24 | `GroupBy` | `bucket_size`, `bucket_min`, `bucket_max` | finite (not NaN/Inf) |
| F3_TYPE | (query-level, stays) | `conversion_window` | must be int |
| F3_POSITIVE | (query-level, stays) | `conversion_window` | positive |
| F4_NEGATIVE_STEP / EX2 | `Exclusion` | `from_step` | >= 0 |
| FL3 / FL2 | `FlowStep` | `forward` | 0-5 range when not None |
| FL4 / FL2 | `FlowStep` | `reverse` | 0-5 range when not None |
| CP1 | `CustomPropertyRef` | `id` | positive integer |
| CP3 | `InlineCustomProperty` | `inputs` | non-empty dict |
| CP4 | `InlineCustomProperty` | `inputs` (keys) | single uppercase A-Z |
| CP5 | `InlineCustomProperty` | `formula` | max 20,000 chars |

#### 6.1.3 Cross-Field Checks Within a Single Model → `@model_validator` (9 rules)

| Rule | Model | Fields | Check |
|------|-------|--------|-------|
| V1/M2 | `Metric` | `math` + `property` | math requiring property |
| V26/M3 | `Metric` | `math` + `percentile_value` | percentile requires value |
| V18/GB3 | `GroupBy` | `bucket_min` + `bucket_max` | min < max |
| V11 | `GroupBy` | `bucket_min`/`bucket_max` + `bucket_size` | bounds require size |
| V12B | `GroupBy` | `bucket_size` + `property_type` | size requires number type |
| V12C | `GroupBy` | `bucket_size` + `bucket_min`/`bucket_max` | size requires bounds |
| EX3/F4_ORDER | `Exclusion` | `from_step` + `to_step` | order check |
| CB1/CB2 | `CohortBreakdown` | `cohort` + `name` | cohort args |
| CM1/CM2/CM5 | `CohortMetric` | `cohort` + `name` | cohort args + inline rejection |

### 6.2 Rules Removed from validation.py (~15 rules)

These rules only fire on **model instances** (guarded by `isinstance` checks), never on raw string/int inputs. Once the Pydantic models enforce these at construction, these checks become unreachable — the model would have rejected the input before the validator ever sees it.

| Rule | Model | Why redundant |
|------|-------|---------------|
| V13_METRIC_MATH_PROPERTY | `Metric` | Only fires on `isinstance(item, Metric)` — Metric's `@model_validator` enforces M2 |
| V14_METRIC_REJECTS_PROPERTY | `Metric` | Same — only fires on Metric instances |
| V26 (per-Metric percentile) | `Metric` | Same — Metric's `@model_validator` enforces M3 |
| V27 (per-Metric histogram per_user) | `Metric` | Same — checked per-Metric in the events loop |
| V3 (per-Metric per_user incompatible) | `Metric` | Same — per-Metric check in events loop |
| V3B (per-Metric per_user requires property) | `Metric` | Same — per-Metric check in events loop |
| V11/V12/V12B/V12C (GroupBy bucket deps) | `GroupBy` | Only fires on `isinstance(g, GroupBy)` — GroupBy's validators enforce |
| V18 (bucket ordering) | `GroupBy` | Same |
| V24 (bucket finite) | `GroupBy` | Same |
| CM5 (inline CohortDefinition) | `CohortMetric` | Only fires on `isinstance(item, CohortMetric)` |
| F4_EMPTY_EXCLUSION / F4_CONTROL | `Exclusion` | Always `Exclusion` instances — validated at construction |
| F4_NEGATIVE_STEP | `Exclusion` | Same |
| F4_STEP_ORDER | `Exclusion` | Same (within-Exclusion ordering; F4_STEP_BOUNDS stays — cross-collection) |
| F8_EMPTY (HoldingConstant path) | `HoldingConstant` | Only the `isinstance(hc, HoldingConstant)` branch; the `str` branch stays |

**Note**: Some rules like F8_EMPTY have a dual path — the `isinstance(hc, HoldingConstant)` branch is redundant but the `str` branch must stay.

### 6.3 Rules That Stay in validation.py (~55 rules)

These are **cross-field rules that span multiple objects**, **query-composition rules**, **raw-string input checks**, or **Layer 2 bookmark dict validation**:

#### Cross-field / query-level rules (34 rules)

| Rule | Why it stays |
|------|-------------|
| V0_NO_EVENTS | Collection-level: events list must be non-empty |
| V1_MATH_REQUIRES_PROPERTY | Top-level math↔math_property (applies to plain string events) |
| V2_MATH_REJECTS_PROPERTY | Top-level math↔math_property interaction |
| V3_PER_USER_INCOMPATIBLE | Top-level per_user↔math interaction |
| V3B_PER_USER_REQUIRES_PROPERTY | Top-level per_user↔math_property interaction |
| V4_FORMULA_MIN_EVENTS | Formula↔events count relationship |
| V5_ROLLING_CUMULATIVE | Rolling↔cumulative mutual exclusion |
| V7, V8, V9, V10, V15, V20 | Time range validation (from_date, to_date, last interactions) |
| V16/V19 | Formula expression↔events count referential integrity |
| V21 | Event type guard (str, Metric, or CohortMetric) |
| V23 | Rolling window sanity cap |
| F1 | Min/max step count (collection-level) |
| F3_MAX | Conversion window max per unit (cross-field) |
| F4_BOUNDS | Exclusion step indices vs total step count (cross-collection) |
| F7_SECOND_MIN | Second unit minimum window (cross-field) |
| F8_MAX | Holding constant max count (collection-level) |
| F9 | Session math↔session window (cross-field) |
| F10/F11 | Funnel math↔math_property (cross-field) |
| FL1 | At least one flow step (collection-level) |
| FL5 | Forward + reverse > 0 (cross-field) |
| FL6 | Cardinality range (query-level param) |
| FL7/FL7_MAX | Conversion window validation (query-level) |
| FL9/FL10 | Session count_type↔window (cross-field) |
| R5/R6 | Bucket sizes validation (list-internal ordering) |
| R7-R11 | Retention enum validation (query-level params, not model fields) |
| R12 | Group-by non-empty in retention context |
| CB3 | CohortBreakdown + GroupBy mutual exclusion in retention |

#### Raw-string input checks (~21 rules)

These checks apply to parameters that accept `str` directly (not model instances). The validator functions accept union types like `Sequence[str | Metric]` and `str | GroupBy`, so the string path needs its own validation:

| Rule | Validator | Why it stays |
|------|-----------|-------------|
| V17/V22/V22_INVISIBLE | `validate_query_args` | `events` accepts plain `str` |
| F2/F2_CONTROL/F2_INVISIBLE | `validate_funnel_args` | `steps` accepts plain `str` |
| R1/R1_CONTROL/R1_INVISIBLE | `validate_retention_args` | `born_event` is `str` directly |
| R2/R2_CONTROL/R2_INVISIBLE | `validate_retention_args` | `return_event` is `str` directly |
| FL2/FL2_CONTROL/FL2_INVISIBLE | `validate_flow_args` | `steps` is `list[str]` |
| R12_EMPTY_GROUP_BY | `validate_retention_args` | `group_by` accepts plain `str` |
| F8_EMPTY (str path) | `validate_funnel_args` | `holding_constant` accepts plain `str` |

#### Layer 2 bookmark dict validation (32 rules)

All B-series and FLB-series rules — these validate raw `dict[str, Any]` bookmark JSON, unchanged by this refactor.

### 6.4 Enum Rules: Dual Strategy

The 21 pure enum checks use `_enum_error()` which provides fuzzy "did you mean?" suggestions. These are the rules where Pydantic `Literal` types and the current behavior **differ most**:

| Approach | Behavior |
|----------|----------|
| Pydantic `Literal["day", "week", "month"]` | Rejects invalid value at construction with Pydantic's generic error message. No fuzzy suggestions. |
| Current `_enum_error()` + `_suggest()` | Returns `ValidationError` with `suggestion=("day", "week")` from `difflib.get_close_matches`. |

**Decision**: Use Pydantic `Literal` types on the models for **construction-time safety**. Enum checks in validation.py fall into two categories:

1. **Model field enums** (e.g., `Metric.math`, `FlowStep.filters_combinator`): These become unreachable in validation.py after the model enforces `Literal` at construction. **Remove these checks** from validation.py. The fuzzy suggestions are lost at the Pydantic level, but the error message from `Literal` rejection clearly lists valid values, and static type checkers catch these before runtime.

2. **Query-level parameter enums** (e.g., `conversion_window_unit`, `retention_unit`, `alignment`, `mode`): These are parameters to `validate_retention_args()` etc., not fields on models. **Keep these checks** in validation.py with fuzzy suggestions intact — they are the only validation layer for these values.

---

## 7. Error Channel Unification

### 7.1 Current State

| Channel | Error Type | Contains | Catchable As |
|---------|-----------|----------|-------------|
| `__post_init__` | `ValueError` | Message string only | `except ValueError` |
| validation.py | `BookmarkValidationError` | `list[ValidationError]` with code, path, severity, suggestion, fix | `except BookmarkValidationError` |

### 7.2 Target State

| Channel | Error Type | Contains | Catchable As |
|---------|-----------|----------|-------------|
| Pydantic construction | `pydantic.ValidationError` | Structured field errors with types and locations | `except pydantic.ValidationError` |
| validation.py | `BookmarkValidationError` | `list[ValidationError]` with code, path, severity, suggestion, fix | `except BookmarkValidationError` |

### 7.3 Bridging Pydantic Errors to BookmarkValidationError

For callers who want a **uniform error experience**, provide a utility that converts `pydantic.ValidationError` to `BookmarkValidationError`:

```python
# mixpanel_data/exceptions.py

def pydantic_to_validation_errors(
    exc: PydanticValidationError,
) -> list[ValidationError]:
    """Convert a pydantic.ValidationError to a list of ValidationError.

    Maps Pydantic's structured error format to the project's
    agent-friendly ValidationError with error codes and paths.

    Args:
        exc: The Pydantic validation error to convert.

    Returns:
        List of ValidationError objects with appropriate codes and paths.
    """
    errors: list[ValidationError] = []
    for err in exc.errors():
        path = ".".join(str(loc) for loc in err["loc"])
        # Map Pydantic error types to our error codes
        code = _pydantic_type_to_code(err["type"], path)
        errors.append(
            ValidationError(
                path=path,
                message=err["msg"],
                code=code,
                severity="error",
            )
        )
    return errors
```

**The `_pydantic_type_to_code` mapping** translates Pydantic error types to project error codes:

| Pydantic `type` | Context | Project Code |
|-----------------|---------|-------------|
| `string_too_short` | `Metric.event` | `M1_EMPTY_EVENT` |
| `value_error` | `GroupBy` model_validator | `GB3_BUCKET_ORDER` |
| `literal_error` | `Metric.math` | (Pydantic-specific, no legacy code) |
| `greater_than` | `Exclusion.from_step` | `EX2_NEGATIVE_STEP` |

**Important**: This bridge is a **convenience**, not a requirement. Callers who catch `pydantic.ValidationError` directly get Pydantic's native error format, which is also structured and machine-parseable. The bridge exists for callers who want the project-specific error codes.

### 7.4 workspace.py Error Handling Update

Currently workspace.py does not catch `ValueError` from `__post_init__`. After migration:

```python
# Before (current):
# GroupBy("", bucket_size=-1)  → raises ValueError (uncaught)
# validate_query_args(...)     → returns list[ValidationError]

# After (target):
# GroupBy("", bucket_size=-1)  → raises pydantic.ValidationError (structured)
# validate_query_args(...)     → returns list[ValidationError] (no change)
```

workspace.py does **not** need to change its validation flow. The Pydantic errors fire **before** workspace.py is even called — they fire when the user constructs the types. workspace.py's `build_*_params()` methods receive already-valid type instances.

---

## 8. Conformance Suite Compatibility

### 8.1 The Conformance Suite Is Downstream

The conformance suite is **generated from** the Python validators (`conformance/generate.py`). Python is the oracle. The workflow after refactoring:

1. Refactor Python validators (this design document).
2. Run `conformance/generate.py` to regenerate test fixtures from the updated oracle.
3. Update the TypeScript implementation to match any behavioral changes.
4. Run `conformance/differential.py` to verify cross-language parity.

The conformance suite **adapts to the refactor**, not the other way around.

### 8.2 What Changes for the Conformance Harness

The harness (`conformance/harness/run_python.py`) imports:

```python
from mixpanel_data._internal.validation import (
    validate_bookmark, validate_flow_args, validate_flow_bookmark,
    validate_funnel_args, validate_query_args, validate_retention_args,
    validate_time_args,
)
from mixpanel_data.exceptions import ValidationError
from mixpanel_data.types import Exclusion
```

All imports remain valid. The harness passes raw primitives (strings, ints, dicts) to the validator functions, not model instances. Validator function signatures and return types are unchanged.

The only type import is `Exclusion` (used to construct test inputs). After migration, `Exclusion` is a Pydantic model — construction behavior is identical for valid inputs.

### 8.3 Rules Removed from validation.py

~15 rules that only fire on model instances (guarded by `isinstance` checks) are removed from validation.py (see Section 6.2). The conformance harness never exercises these code paths because it passes raw primitives, so the removal has no conformance impact.

After removal, `generate.py` is re-run to produce updated fixtures. Any tests that previously exercised now-removed rules via model-instance inputs would need new test cases that construct the model directly (expecting `pydantic.ValidationError` instead of a `ValidationError` list entry).

### 8.4 Net Effect

| Before | After |
|--------|-------|
| `__post_init__` (ValueError) + validation.py (ValidationError) | Pydantic model (PydanticValidationError) + validation.py (ValidationError) |
| Two implementations, two error formats, one divergence (EX3) | One validation per rule, two structured error formats, zero divergence |
| 3 types with no construction validation | All types validate invariants at construction |
| ~15 redundant checks in validation.py | Removed — models enforce at construction |

The wins: **eliminate the unstructured error channel**, **unify semantics** (fix the EX3 divergence), **gain construction-time validation on 3 types**, and **remove ~15 genuinely redundant rules** from validation.py.

---

## 9. Implementation Plan

### Phase 1: Foundation (No Behavior Change)

**Goal**: Establish shared validation infrastructure without changing any types or behavior.

#### 1.1 Create `_internal/field_validators.py`

Extract reusable validation helpers that both Pydantic `@field_validator` methods and validation.py functions can call:

```python
# _internal/field_validators.py

def validate_event_name(value: str, class_name: str) -> str:
    """Validate and return an event name string.

    Reusable by both @field_validator (returns cleaned value)
    and validation.py (called for error checking).

    Raises:
        ValueError: If event name is empty, contains control
            characters, or consists only of invisible characters.
    """
    ...

def validate_positive_int(value: int, field_name: str) -> int:
    """Validate that an integer is positive."""
    ...

def validate_finite(value: int | float | None, field_name: str) -> int | float | None:
    """Validate that a numeric value is finite (not NaN/Inf)."""
    ...
```

This is the shared helper layer that both systems call — eliminating the risk of behavioral divergence.

#### 1.2 Create `exceptions.pydantic_to_validation_errors()`

Add the bridge utility (Section 7.3) to `exceptions.py`.

#### 1.3 Fix the EX3 Divergence

Align `Exclusion.__post_init__` (currently `to_step < from_step`) with validation.py's F4_EXCLUSION_STEP_ORDER (currently `to_step <= from_step`). The correct semantics is `to_step > from_step` (strict, matching validation.py). Fix in `__post_init__` now, before migration.

**Deliverables**: New `_internal/field_validators.py`, bridge utility in `exceptions.py`, EX3 fix.  
**Tests**: Unit tests for field validators, test for bridge utility, update EX3 test expectations.  
**Risk**: None — no public API change.

---

### Phase 2: Tier 1 Migration (Simple Types)

**Goal**: Migrate the simplest types to establish the pattern. 3 types, 4 fields total.

#### 2.1 Migrate `PropertyInput`

```python
# Before:
@dataclass(frozen=True)
class PropertyInput:
    name: str
    type: Literal["string", "number", "boolean", "datetime", "list"] = "string"
    resource_type: Literal["event", "user"] = "event"

# After:
class PropertyInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    type: Literal["string", "number", "boolean", "datetime", "list"] = "string"
    resource_type: Literal["event", "user"] = "event"

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("PropertyInput.name must be a non-empty string")
        return v
```

**Gains validation it never had** (CP6 at construction).

#### 2.2 Migrate `CustomPropertyRef`

```python
class CustomPropertyRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int  # noqa: A003

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(
                f"CustomPropertyRef.id must be a positive integer (got {v})"
            )
        return v
```

**Gains validation it never had** (CP1 at construction).

#### 2.3 Migrate `InlineCustomProperty`

```python
class InlineCustomProperty(BaseModel):
    model_config = ConfigDict(frozen=True)

    formula: str
    inputs: dict[str, PropertyInput]
    property_type: Literal["string", "number", "boolean", "datetime"] | None = None
    resource_type: Literal["events", "people"] = "events"

    @field_validator("formula")
    @classmethod
    def _validate_formula(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("InlineCustomProperty.formula must be non-empty")
        if len(v) > 20_000:
            raise ValueError(
                f"InlineCustomProperty.formula exceeds 20,000 char limit "
                f"(got {len(v)})"
            )
        return v

    @field_validator("inputs")
    @classmethod
    def _validate_inputs(cls, v: dict[str, PropertyInput]) -> dict[str, PropertyInput]:
        if len(v) == 0:
            raise ValueError(
                "InlineCustomProperty must have at least one input"
            )
        key_re = re.compile(r"^[A-Z]$")
        for key in v:
            if not key_re.match(key):
                raise ValueError(
                    f"Input keys must be single uppercase letters (A-Z), got {key!r}"
                )
        return v

    @classmethod
    def numeric(cls, formula: str, /, **properties: str) -> InlineCustomProperty:
        """Convenience constructor for all-numeric inputs."""
        inputs = {
            k.upper(): PropertyInput(name=v, type="number")
            for k, v in properties.items()
        }
        return cls(formula=formula, inputs=inputs, property_type="number")
```

**Gains validation it never had** (CP2-CP5 at construction).

**Deliverables**: 3 migrated types.  
**Tests**: Update all construction tests from dataclass to BaseModel behavior. Verify `isinstance` still works. Verify positional construction. Add new tests for gained validations.  
**Risk**: Low — these types are leaf nodes with no downstream dependencies except as fields on other types.

---

### Phase 3: Tier 2 Migration (Event Name Types)

**Goal**: Migrate the 4 types that only validate event names. Establish the `@field_validator` pattern for `_validate_event_name`.

#### 3.1 Migrate `Formula`, `FunnelStep`, `RetentionEvent`, `HoldingConstant`

All follow the same pattern — single `@field_validator` on the primary string field, calling the shared helper from Phase 1.

**Deliverables**: 4 migrated types.  
**Tests**: Update construction tests. Verify `isinstance`. Verify factory patterns (e.g., `FunnelStep` accepts `order`, `filters`, `filters_combinator`).  
**Risk**: Low — simple single-field validators.

---

### Phase 4: Tier 3 Migration (Multi-Field Types)

**Goal**: Migrate types with cross-field `@model_validator` relationships.

#### 4.1 Migrate `GroupBy`

Combines `@field_validator` (positive bucket_size, finite values, non-empty property) with `@model_validator(mode="after")` (bucket ordering, size↔bounds↔type dependencies).

#### 4.2 Migrate `Exclusion`

`@field_validator` (event name, non-negative from_step) + `@model_validator(mode="after")` (step ordering).

#### 4.3 Migrate `FlowStep`

`@field_validator` (event name, forward/reverse range).

#### 4.4 Migrate `CohortBreakdown`, `CohortMetric`

`@model_validator(mode="after")` calling shared cohort validation.

#### 4.5 Migrate `Metric`

Most complex: `@field_validator("event")` + `@model_validator(mode="after")` for math↔property, percentile↔value.

**Deliverables**: 6 migrated types.  
**Tests**: Update all construction tests. Update all test_validation_* files that test the `__post_init__` ValueError path to expect `pydantic.ValidationError`. Verify workspace.py integration (build_*_params still works).  
**Risk**: Medium — `Metric` is heavily used. Model validators must match exact semantics.

---

### Phase 5: Tier 4 Migration (Filter)

**Goal**: Migrate `Filter` — the most architecturally unique type.

#### 5.1 Decide on Field Naming

**Option A** (recommended): Rename `_property` → `prop`, `_operator` → `operator`, `_value` → `value`, `_property_type` → `property_type`, `_resource_type` → `resource_type`, `_date_unit` → `date_unit`. Update all bookmark builder code that accesses these fields.

**Option B**: Keep underscore names with `Field(alias="...")` and `populate_by_name=True`.

#### 5.2 Migrate Filter Class

```python
class Filter(BaseModel):
    model_config = ConfigDict(frozen=True)

    prop: str | CustomPropertyRef | InlineCustomProperty  # renamed from _property
    operator: str
    value: str | int | float | list[str] | list[int | float] | list[dict[str, Any]] | None
    property_type: FilterPropertyType = "string"
    resource_type: Literal["events", "people"] = "events"
    date_unit: FilterDateUnit | None = None

    @classmethod
    def equals(cls, property: str | CustomPropertyRef | InlineCustomProperty, ...) -> Filter:
        """Create an equality filter."""
        val = [value] if isinstance(value, str) else value
        return cls(prop=property, operator="equals", value=val, ...)

    # ... 21 more class methods (unchanged logic)
```

**Deliverables**: Migrated `Filter` type, updated bookmark builder field access.  
**Tests**: Comprehensive Filter test updates (22 factory methods × multiple input types).  
**Risk**: Medium-High — `Filter` is used everywhere. Field rename touches bookmark builder code.

---

### Phase 6: Cleanup and Verification

**Goal**: Remove dead code, run full test suites, verify conformance.

#### 6.1 Remove Dead Code

- Delete `_validate_event_name()` from types.py (moved to `_internal/field_validators.py`).
- Delete `_validate_cohort_args()` from types.py (logic now in model validators).
- Delete `_MATH_REQUIRING_PROPERTY` from types.py (already defined in `bookmark_enums.py`).
- Delete `_CONTROL_CHAR_RE` from types.py (moved to field_validators.py).

#### 6.2 Verification

```bash
# All must pass:
just check               # lint + typecheck + test
just test-ci             # thorough Hypothesis (200 examples)
just test-pbt            # property-based tests
just mutate-check        # mutation score >= 80%
```

#### 6.3 Conformance Suite Regeneration

```bash
# Regenerate conformance fixtures from updated Python oracle:
cd conformance && python generate.py

# Verify TypeScript implementation still passes:
cd conformance && npm test

# Run differential testing (Python vs TypeScript):
cd conformance && python differential.py  # zero divergences
```

If `differential.py` reports divergences, update the TypeScript implementation to match the Python oracle's new behavior (e.g., removed rules that are now enforced at model construction).

#### 6.3 Documentation

- Update `CLAUDE.md` type descriptions.
- Update `types.py` module CLAUDE.md.
- Update docstrings for migrated types (Pydantic-specific notes).

**Deliverables**: Clean codebase, passing CI, passing conformance.  
**Risk**: Low — this is verification, not implementation.

---

## 10. Risk Assessment

### 10.1 High Risk

| Risk | Mitigation |
|------|-----------|
| `isinstance` checks break | Pydantic BaseModel supports `isinstance` natively. Verify in Phase 2. |
| Positional construction breaks | Pydantic v2 supports positional args for ordered fields. Verify in Phase 2. |
| `frozen=True` behavior differs | Pydantic's `ConfigDict(frozen=True)` raises `ValidationError` on attribute assignment (vs dataclass's `FrozenInstanceError`). Callers catching `FrozenInstanceError` need updating. Search codebase for this. |
| Filter underscore fields | Addressed in Phase 5 with rename or alias strategy. |

### 10.2 Medium Risk

| Risk | Mitigation |
|------|-----------|
| Test count (545 tests, 6900 lines) | Phase-by-phase migration limits blast radius. Each phase has its own test verification. |
| Pydantic error message format | Callers catching `ValueError` from `__post_init__` now get `pydantic.ValidationError`. Different message format. Addressed by bridge utility. |
| `hash()` behavior change | Frozen dataclasses are hashable by default. Pydantic frozen models are also hashable. Verify. |
| `==` comparison behavior | Dataclass equality compares all fields. Pydantic model equality also compares all fields. Verify. |

### 10.3 Low Risk

| Risk | Mitigation |
|------|-----------|
| Conformance suite divergence | Suite is regenerated from Python oracle (Section 8). TypeScript implementation updated to match. |
| Performance regression | Pydantic v2 is compiled (Rust core). Construction may actually be faster. Benchmark if needed. |
| Serialization change | Query-builder types don't have `to_dict()`. Bookmark builder uses attribute access. No change needed. |

---

## 11. Appendices

### A. Complete Type Migration Matrix

| # | Type | Tier | Fields | Current `__post_init__` | `@field_validator` | `@model_validator` | New Validation Gained |
|---|------|------|--------|------------------------|-------------------|-------------------|----------------------|
| 1 | `PropertyInput` | 1 | 3 | None | name (CP6) | None | CP6 at construction |
| 2 | `CustomPropertyRef` | 1 | 1 | None | id (CP1) | None | CP1 at construction |
| 3 | `InlineCustomProperty` | 1 | 4 | None | formula (CP2,CP5), inputs (CP3,CP4) | None | CP2-CP5 at construction |
| 4 | `Formula` | 2 | 2 | FM1 | expression (FM1) | None | None (already validated) |
| 5 | `FunnelStep` | 2 | 5 | FS1 | event (FS1) | None | None |
| 6 | `RetentionEvent` | 2 | 3 | RE1 | event (RE1) | None | None |
| 7 | `HoldingConstant` | 2 | 2 | HC1 | property (HC1) | None | None |
| 8 | `GroupBy` | 3 | 5 | GB1,GB2,GB3 | property (GB1), bucket_size (GB2), buckets (V24 finite) | GB3 (ordering), V11/V12B/V12C (dependencies) | V24 finite check at construction |
| 9 | `Exclusion` | 3 | 3 | EX1,EX2,EX3 | event (EX1), from_step (EX2) | EX3 (step ordering) | None |
| 10 | `FlowStep` | 3 | 6 | FL1,FL2 | event (FL1), forward (FL2), reverse (FL2) | None | None |
| 11 | `CohortBreakdown` | 3 | 3 | CB1,CB2 | None | CB1/CB2 (cohort args) | None |
| 12 | `CohortMetric` | 3 | 2 | CM1,CM2,CM5 | None | CM1/CM2/CM5 (cohort args + inline rejection) | None |
| 13 | `Metric` | 3 | 7 | M1,M2,M3 | event (M1) | M2 (math↔property), M3 (percentile↔value) | None |
| 14 | `Filter` | 4 | 6 | None (class methods) | None (validation in class methods) | None | None |
| -- | `CohortDefinition` | Deferred | -- | None | -- | -- | -- |

### B. Validation Rule Count Summary

| Category | Count | Disposition |
|----------|-------|------------|
| Rules that move into models (single-field) | 33 | `@field_validator` on Pydantic models |
| Rules that move into models (cross-field, within model) | 9 | `@model_validator` on Pydantic models |
| Rules removed from validation.py (redundant — only fire on model instances) | ~15 | Covered by model validators above |
| Rules that stay in validation.py (cross-object/query-level) | 34 | No change |
| Rules that stay in validation.py (raw-string input checks) | ~21 | Needed for `str` input paths |
| Layer 2 rules (bookmark dict validation) | 32 | No change |
| **Total unique rules** | **108** | |

Note: The ~15 removed rules overlap with the 42 "move into models" rules — they are the subset where validation.py's check is genuinely unreachable because it only fires on model instances (guarded by `isinstance`). The remaining ~27 of the 42 "move into models" rules are **also** needed in validation.py for raw-string input paths, making them intentional defense-in-depth rather than duplication.

### C. Error Code Stability

All 100+ error codes remain stable in their semantics. ~15 codes are removed from validation.py (Section 6.2) because their checks become unreachable — the Pydantic model enforces the same invariant at construction. These codes continue to exist conceptually (the invariant is still enforced), but via Pydantic's error format rather than the project's `ValidationError`. The conformance suite is regenerated to reflect this.

### D. Files Modified Per Phase

| Phase | Files Modified | Files Created |
|-------|---------------|---------------|
| 1 | `exceptions.py`, types.py (EX3 fix only) | `_internal/field_validators.py` |
| 2 | `types.py` (3 types), test files | None |
| 3 | `types.py` (4 types), test files | None |
| 4 | `types.py` (6 types), test files | None |
| 5 | `types.py` (Filter), `workspace.py` (field access), `_internal/` builders, test files | None |
| 6 | `types.py` (dead code removal), CLAUDE.md files | None |

### E. Conformance Harness Compatibility

The conformance harness (`conformance/harness/run_python.py`) imports:

```python
from mixpanel_data._internal.validation import (
    validate_bookmark,
    validate_flow_args,
    validate_flow_bookmark,
    validate_funnel_args,
    validate_query_args,
    validate_retention_args,
    validate_time_args,
)
from mixpanel_data.exceptions import ValidationError
from mixpanel_data.types import Exclusion
```

**All imports remain valid.** The only type import is `Exclusion` (used to construct test inputs). After migration, `Exclusion` is a Pydantic model instead of a dataclass — construction behavior is identical for valid inputs.

After refactoring, run `conformance/generate.py` to regenerate the suite from the updated Python oracle. Tests that exercised now-removed rules (Section 6.2) may produce different results — the rule is enforced at model construction rather than via `validate_*_args()`. The generator handles this automatically since it derives expectations from the Python implementation.
