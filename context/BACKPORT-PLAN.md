# Backport Plan: TypeScript Feature Parity → Python mixpanel_data

## Context

The TypeScript `@mixpanel-data/bookmark` library has added several features that originated from `mixpanel-power-tools` but don't yet exist in the Python `mixpanel_data` library. This plan backports them to Python to maintain cross-language parity.

## Features to Backport

| # | Feature | TS Source | Python Target |
|---|---------|-----------|---------------|
| 1 | Funnel reentry mode | `build-funnel-params.ts` | `workspace.py:query_funnel()` |
| 2 | Retention unbounded mode | `build-retention-params.ts` | `workspace.py:query_retention()` |
| 3 | Time comparison | `build-params.ts`, `build-funnel-params.ts`, `build-retention-params.ts` | All query methods |
| 4 | Frequency breakdowns | `build-helpers.ts`, `filter-factories.ts` | `workspace.py:query()` |
| 5 | Display formatting | `types.ts` (Metric.display, Formula.display) | `types.py:Metric`, `types.py:Formula` |
| 6 | Y-axis, lift, value mode | `build-params.ts` | `workspace.py:query()` |
| 7 | Legend pass-through | All builders | All query methods |

---

## Feature 1: Funnel Reentry Mode

### Type Alias
**File**: `src/mixpanel_data/_literal_types.py`
```python
FunnelReentryMode = Literal["default", "basic", "aggressive", "optimized"]
```

### Validation Constant
**File**: `src/mixpanel_data/_internal/bookmark_enums.py`
```python
VALID_FUNNEL_REENTRY_MODES: frozenset[str] = frozenset({
    "default", "basic", "aggressive", "optimized",
})
```

### Validation Rule
**File**: `src/mixpanel_data/_internal/validation.py` (in `validate_funnel_args()`)
```python
# F12: reentry_mode must be valid
if reentry_mode not in VALID_FUNNEL_REENTRY_MODES:
    errors.append(validation_error(
        "reentry_mode", "reentryMode", reentry_mode,
        VALID_FUNNEL_REENTRY_MODES, "F12_INVALID_REENTRY_MODE",
    ))
```

### Public API
**File**: `src/mixpanel_data/workspace.py`

Add to `query_funnel()` (line ~2622):
```python
def query_funnel(
    self,
    steps: list[str | FunnelStep],
    *,
    # ... existing params ...
    reentry_mode: FunnelReentryMode = "default",  # NEW
) -> FunnelQueryResult:
```

Add to `_build_funnel_params()` (line ~2338):
```python
# In the behavior dict construction:
behavior["funnelReentryMode"] = reentry_mode
```

Pass through `_resolve_and_build_funnel_params()` (line ~2501).

### Export
**File**: `src/mixpanel_data/__init__.py`
```python
from ._literal_types import FunnelReentryMode
```

### Tests
**File**: `tests/unit/test_funnel_params.py` (or existing test file)
- Test each valid mode produces correct `behavior.funnelReentryMode`
- Test invalid mode triggers `F12_INVALID_REENTRY_MODE`
- Test default is `"default"`

---

## Feature 2: Retention Unbounded Mode

### Type Alias
**File**: `src/mixpanel_data/_literal_types.py`
```python
RetentionUnboundedMode = Literal["none", "carry_back", "carry_forward", "consecutive_forward"]
```

### Validation Constant
**File**: `src/mixpanel_data/_internal/bookmark_enums.py`
```python
VALID_RETENTION_UNBOUNDED_MODES: frozenset[str] = frozenset({
    "none", "carry_back", "carry_forward", "consecutive_forward",
})
```

### Validation Rule
**File**: `src/mixpanel_data/_internal/validation.py` (in `validate_retention_args()`)
```python
# R13: unbounded_mode must be valid
if unbounded_mode not in VALID_RETENTION_UNBOUNDED_MODES:
    errors.append(validation_error(
        "unbounded_mode", "unboundedMode", unbounded_mode,
        VALID_RETENTION_UNBOUNDED_MODES, "R13_INVALID_UNBOUNDED_MODE",
    ))
```

### Public API
**File**: `src/mixpanel_data/workspace.py`

Add to `query_retention()` (line ~3618):
```python
def query_retention(
    self,
    born_event: str | RetentionEvent,
    return_event: str | RetentionEvent,
    *,
    # ... existing params ...
    unbounded_mode: RetentionUnboundedMode = "none",  # NEW
) -> RetentionQueryResult:
```

Add to `_build_retention_params()` (line ~2853):
```python
# In the retention behavior dict:
retention_behavior["retentionUnboundedMode"] = unbounded_mode
```

Pass through `_resolve_and_build_retention_params()` (line ~3509).

### Export
**File**: `src/mixpanel_data/__init__.py`
```python
from ._literal_types import RetentionUnboundedMode
```

### Tests
- Test each valid mode
- Test invalid mode triggers `R13_INVALID_UNBOUNDED_MODE`
- Test default is `"none"`

---

## Feature 3: Time Comparison

### Dataclass
**File**: `src/mixpanel_data/types.py`
```python
@dataclass(frozen=True)
class RelativeTimeComparison:
    """Compare to same period in previous time unit."""
    type: Literal["relative"] = "relative"
    unit: Literal["day", "week", "month", "quarter", "year"] = "week"

@dataclass(frozen=True)
class AbsoluteTimeComparison:
    """Compare to a specific date range."""
    type: Literal["absolute-start", "absolute-end"]
    date: str  # YYYY-MM-DD

TimeComparison = RelativeTimeComparison | AbsoluteTimeComparison
```

### Public API
**File**: `src/mixpanel_data/workspace.py`

Add to `query()`, `query_funnel()`, `query_retention()`:
```python
time_comparison: TimeComparison | None = None,  # NEW
```

In each `_build_*_params()`, after assembling params:
```python
if time_comparison is not None:
    params["timeComparison"] = {
        "type": time_comparison.type,
        **({"unit": time_comparison.unit} if isinstance(time_comparison, RelativeTimeComparison) else {"date": time_comparison.date}),
    }
```

### Export
```python
from .types import RelativeTimeComparison, AbsoluteTimeComparison, TimeComparison
```

### Tests
- Test relative comparison with each unit
- Test absolute-start and absolute-end with dates
- Test None (omitted) produces no `timeComparison` key

---

## Feature 4: Frequency Breakdowns

### Dataclass
**File**: `src/mixpanel_data/types.py`
```python
@dataclass(frozen=True)
class FrequencyBreakdown:
    """Break down by event frequency (how many times users performed an event)."""
    event: str
    window_length: int = 7
    window_length_unit: Literal["day", "week", "month"] = "day"
    custom_bucket: FrequencyCustomBucket | None = None

@dataclass(frozen=True)
class FrequencyCustomBucket:
    """Custom bucketing for frequency breakdowns."""
    bucket_size: int = 1
    min: int = 0
    max: int = 10
    groups: list[int] | None = None
```

### Builder
**File**: `src/mixpanel_data/_internal/bookmark_builders.py`
```python
def _build_frequency_group_entry(fb: FrequencyBreakdown) -> dict[str, Any]:
    group = {
        "dataset": "$mixpanel",
        "behavior": {
            "aggregationOperator": "total",
            "event": {"label": fb.event, "value": fb.event},
            "filters": [],
            "filtersOperator": "and",
            "dateRange": None,
            "behaviorType": "$frequency",
            "windowLength": fb.window_length,
            "windowLengthUnit": fb.window_length_unit,
        },
        "value": f"{fb.event} Frequency",
        "resourceType": "people",
        "profileType": None,
        "search": "",
        "dataGroupId": None,
        "propertyType": "number",
        "typeCast": None,
        "unit": None,
        "isHidden": False,
    }
    if fb.custom_bucket is not None:
        group["customBucket"] = {
            "bucketSize": fb.custom_bucket.bucket_size,
            "min": fb.custom_bucket.min,
            "max": fb.custom_bucket.max,
            "offset": None,
            "disabled": False,
            "groups": list(fb.custom_bucket.groups) if fb.custom_bucket.groups else None,
            "unit": None,
        }
    return group
```

Integrate into `build_group_section()`:
```python
elif isinstance(g, FrequencyBreakdown):
    group_section.append(_build_frequency_group_entry(g))
```

### Public API
Extend `group_by` parameter type in `query()`:
```python
group_by: str | GroupBy | CohortBreakdown | FrequencyBreakdown | list[str | GroupBy | CohortBreakdown | FrequencyBreakdown] | None = None,
```

### Frequency Filter
Add `Filter.by_frequency()` class method to `types.py`:
```python
@classmethod
def by_frequency(
    cls,
    event: str,
    *,
    operator: str = "is at least",
    value: int = 1,
    aggregation: str = "total",
    date_range: dict[str, Any] | None = None,
    event_filters: list[Filter] | None = None,
) -> Filter:
    """Create a frequency filter (users who did event N times)."""
```

### Export
```python
from .types import FrequencyBreakdown, FrequencyCustomBucket
```

### Tests
- Test breakdown produces correct `behavior.behaviorType: "$frequency"`
- Test custom bucket
- Test frequency filter with operator/value options

---

## Feature 5: Display Formatting

### Dataclass
**File**: `src/mixpanel_data/types.py`
```python
@dataclass(frozen=True)
class DisplayFormatting:
    """Per-metric display formatting options."""
    prefix: str | None = None
    suffix: str | None = None
    direction: str | None = None
    precision: int | None = None
```

### Type Changes
Add optional `display` field to `Metric` (line ~6999) and `Formula` (line ~7078):
```python
@dataclass(frozen=True)
class Metric:
    # ... existing fields ...
    display: DisplayFormatting | None = None  # NEW

@dataclass(frozen=True)
class Formula:
    # ... existing fields ...
    display: DisplayFormatting | None = None  # NEW
```

### Builder
**File**: `src/mixpanel_data/workspace.py` (in `_build_query_params()`)
When building show clauses, if `metric.display` is not None:
```python
if hasattr(item, 'display') and item.display is not None:
    entry["display"] = {
        k: v for k, v in {
            "prefix": item.display.prefix,
            "suffix": item.display.suffix,
            "direction": item.display.direction,
            "precision": item.display.precision,
        }.items() if v is not None
    }
```

### Export
```python
from .types import DisplayFormatting
```

### Tests
- Test metric with `display=DisplayFormatting(prefix="$")` produces `show[].display.prefix`
- Test formula with `display=DisplayFormatting(suffix="%")`
- Test None display is omitted

---

## Feature 6: Y-Axis, Lift, Value Mode

### Dataclass
**File**: `src/mixpanel_data/types.py`
```python
@dataclass(frozen=True)
class YAxisOptions:
    """Y-axis configuration options."""
    min: float | None = None
    max: float | None = None
    log_scale: bool | None = None
```

### Public API
**File**: `src/mixpanel_data/workspace.py`

Add to `query()`:
```python
def query(
    self,
    events: ...,
    *,
    # ... existing params ...
    y_axis_options: YAxisOptions | None = None,  # NEW
    lift_comparison: dict[str, Any] | None = None,  # NEW
    value_mode: Literal["absolute", "relative"] = "absolute",  # NEW
) -> QueryResult:
```

In `_build_query_params()`:
```python
if y_axis_options is not None:
    display_options["primaryYAxisOptions"] = {
        k: v for k, v in {
            "min": y_axis_options.min,
            "max": y_axis_options.max,
            "logScale": y_axis_options.log_scale,
        }.items() if v is not None
    }
if lift_comparison is not None:
    display_options["liftComparison"] = lift_comparison
if value_mode == "relative":
    display_options["value"] = "relative"
```

### Export
```python
from .types import YAxisOptions
```

### Tests
- Test y_axis_options produces `displayOptions.primaryYAxisOptions`
- Test lift_comparison pass-through
- Test value_mode="relative" sets `displayOptions.value`

---

## Feature 7: Legend Pass-Through

### Public API
**File**: `src/mixpanel_data/workspace.py`

Add to `query()`, `query_funnel()`, `query_retention()`:
```python
legend: dict[str, Any] | None = None,  # NEW
```

In each `_build_*_params()`:
```python
if legend is not None:
    params["legend"] = legend
```

### Tests
- Test legend dict is passed through to params
- Test None legend is omitted

---

## Implementation Order

1. Features 1 + 2 (funnel reentry + retention unbounded) — smallest, independent, good warmup
2. Feature 3 (time comparison) — touches multiple query methods
3. Feature 4 (frequency breakdowns) — new type + builder + group_by extension
4. Features 5 + 6 + 7 (display/formatting) — simple pass-throughs, batch together

## Files Modified (Summary)

| File | Changes |
|------|---------|
| `_literal_types.py` | Add `FunnelReentryMode`, `RetentionUnboundedMode` |
| `_internal/bookmark_enums.py` | Add `VALID_FUNNEL_REENTRY_MODES`, `VALID_RETENTION_UNBOUNDED_MODES` |
| `_internal/validation.py` | Add `F12_INVALID_REENTRY_MODE`, `R13_INVALID_UNBOUNDED_MODE` rules |
| `_internal/bookmark_builders.py` | Add `_build_frequency_group_entry()`, integrate in `build_group_section()` |
| `types.py` | Add `TimeComparison`, `FrequencyBreakdown`, `FrequencyCustomBucket`, `DisplayFormatting`, `YAxisOptions` dataclasses. Add `display` field to `Metric` and `Formula`. |
| `workspace.py` | Add keyword params to `query()`, `query_funnel()`, `query_retention()` and internal `_build_*_params()` / `_resolve_and_build_*_params()` methods |
| `__init__.py` | Export new types and literals |

## Validation Error Codes (must match TypeScript)

| Code | Rule | Feature |
|------|------|---------|
| `F12_INVALID_REENTRY_MODE` | Funnel reentry mode must be in valid set | #1 |
| `R13_INVALID_UNBOUNDED_MODE` | Retention unbounded mode must be in valid set | #2 |

## Testing Strategy

- Unit tests in `tests/unit/` for each new parameter
- Bookmark output tests comparing Python output against TypeScript output for identical inputs
- Conformance test cases in `conformance/suites/` that run against both implementations
- `uv run pytest tests/` + `uv run mypy src/` must pass
