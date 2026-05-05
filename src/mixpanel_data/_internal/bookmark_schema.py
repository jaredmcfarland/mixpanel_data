"""Pydantic schema models mirroring Mixpanel's canonical bookmark schema.

These models validate the ``params`` dict passed to
``Workspace.create_bookmark()`` and ``Workspace.update_bookmark()``,
catching malformed shapes client-side before they reach Mixpanel. The
``POST /bookmarks`` endpoint accepts garbage and only rejects it later
at chart-render time (``GET /api/query/insights``); these models close
that gap.

**Source of truth**: the canonical Pydantic definitions in Mixpanel's
internal ``analytics`` repository under
``lib/common/mxpnl/report/bookmarks/`` (and the sibling
``mixpanel_mcp/mcp_server/types/reports/internal/`` package for flows).
Each model in this file carries a ``# Mirrors <repo-relative-path>:<line>``
comment naming its source. Drift detection against Mixpanel updates is a
``diff`` operation against that repo, not a production incident report.

The adapter ``validate_with_pydantic()`` translates Pydantic's structured
errors into the package's existing ``ValidationError`` stream so callers
keep getting the stable ``B*`` / ``S*`` error codes already documented for
agents.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic import ValidationError as PydanticValidationError
from pydantic.json_schema import SkipJsonSchema

from mixpanel_data.exceptions import ValidationError

# =============================================================================
# Shared model configuration
# =============================================================================

# Mirrors ``BasePydanticModel`` in
# ``analytics/lib/common/mxpnl/pydantic/base_pydantic_model.py:6`` —
# ``extra="forbid"`` matches the server's strict acceptance policy.
# ``populate_by_name=True`` lets us keep snake_case Python field names
# while accepting camelCase / kebab-case wire keys via ``alias=...``.
_BASE_CONFIG: ConfigDict = ConfigDict(
    populate_by_name=True,
    extra="forbid",
)

# =============================================================================
# Ignore[T] helper — tolerate legacy/compat fields without surfacing them
# =============================================================================

_T = TypeVar("_T")

# Mirrors ``Ignore[T]`` in
# ``analytics/lib/common/mxpnl/report/bookmarks/common/utils.py:1-31``.
# Used to declare fields the server tolerates (e.g. legacy keys still
# present on older saved bookmarks) without rejecting them and without
# exposing them in our typed surface. ``SkipJsonSchema`` keeps them out
# of generated schema artifacts; ``exclude=True`` keeps them out of
# ``model_dump()`` output. Pydantic still accepts them at parse time.
Ignore = Annotated[
    SkipJsonSchema[_T | None],
    Field(default=None, exclude=True),
]

# =============================================================================
# Pydantic-error → ValidationError adapter
# =============================================================================

# Maps Pydantic v2 ``error['type']`` strings to this package's stable
# ``B*`` / ``S*`` error codes. Unmapped types fall through to a generic
# ``"VALIDATION_ERROR"`` code with the original Pydantic message preserved.
#
# Pydantic error type reference:
# https://docs.pydantic.dev/latest/errors/validation_errors/
_DEFAULT_CODE_MAP: dict[str, str] = {
    # Missing required field
    "missing": "B0_MISSING_FIELD",
    # Extra (unexpected) field at a model with extra="forbid"
    "extra_forbidden": "S3_UNKNOWN_FIELD",
    # Wrong value at a Literal[...] / enum field
    "literal_error": "B0_INVALID_LITERAL",
    "enum": "B0_INVALID_LITERAL",
    # Wrong primitive type
    "string_type": "B0_WRONG_TYPE",
    "int_type": "B0_WRONG_TYPE",
    "int_parsing": "B0_WRONG_TYPE",
    "bool_type": "B0_WRONG_TYPE",
    "bool_parsing": "B0_WRONG_TYPE",
    "float_type": "B0_WRONG_TYPE",
    "float_parsing": "B0_WRONG_TYPE",
    "list_type": "B0_WRONG_TYPE",
    "dict_type": "B0_WRONG_TYPE",
    "model_type": "B0_WRONG_TYPE",
    # Discriminated-union failures (e.g. behavior.type missing/unknown)
    "union_tag_invalid": "B7_INVALID_BEHAVIOR_TYPE",
    "union_tag_not_found": "B7_INVALID_BEHAVIOR_TYPE",
    # Custom validator failure (raised by @field_validator / @model_validator)
    "value_error": "B0_VALIDATOR_ERROR",
}


def validate_with_pydantic(
    model_cls: type[BaseModel],
    raw: Any,
    *,
    code_map: dict[str, str] | None = None,
    path_prefix: str = "",
) -> list[ValidationError]:
    """Validate ``raw`` against ``model_cls`` and translate errors.

    Runs ``model_cls.model_validate(raw)`` and converts any
    ``pydantic.ValidationError`` into a list of this package's
    ``ValidationError`` instances with stable ``B*`` / ``S*`` codes.

    Args:
        model_cls: The Pydantic model class to validate against.
        raw: The raw dict (or any value) to validate.
        code_map: Optional override for Pydantic-error-type → package
            error-code mapping. Merged on top of ``_DEFAULT_CODE_MAP``.
        path_prefix: JSONPath-like prefix prepended to every error's
            ``path`` (e.g. ``"params"`` so leaves become
            ``"params.sections.show[0].behavior.type"``).

    Returns:
        Empty list if validation passed. Otherwise, one
        ``ValidationError`` per Pydantic error, with ``path`` translated
        from Pydantic's ``loc`` tuple to a dotted JSONPath.

    Example:
        ```python
        errors = validate_with_pydantic(
            SortByColumnsConfig,
            {"sortBy": "value"},
            path_prefix="sorting.bar",
        )
        # → [ValidationError(path="sorting.bar.sortBy",
        #                    code="B0_INVALID_LITERAL", ...)]
        ```
    """
    effective_codes = dict(_DEFAULT_CODE_MAP)
    if code_map:
        effective_codes.update(code_map)

    try:
        model_cls.model_validate(raw)
    except PydanticValidationError as exc:
        return [
            _translate_pydantic_error(dict(err), effective_codes, path_prefix)
            for err in exc.errors()
        ]
    return []


def _translate_pydantic_error(
    err: dict[str, Any],
    code_map: dict[str, str],
    path_prefix: str,
) -> ValidationError:
    """Convert one ``pydantic.ValidationError.errors()`` entry.

    Args:
        err: A single error dict from Pydantic's ``.errors()`` output
            (contains ``loc``, ``type``, ``msg``, ``input``).
        code_map: Pydantic-error-type → package-error-code mapping.
        path_prefix: JSONPath-like prefix to prepend to the translated path.

    Returns:
        A ``ValidationError`` with translated path and mapped code.
    """
    loc: tuple[Any, ...] = tuple(err.get("loc", ()))
    err_type: str = str(err.get("type", "validation_error"))
    msg: str = str(err.get("msg", "Validation failed"))

    path = _loc_to_jsonpath(loc, path_prefix)
    code = code_map.get(err_type, "VALIDATION_ERROR")

    return ValidationError(
        path=path,
        message=msg,
        code=code,
    )


def _loc_to_jsonpath(loc: tuple[Any, ...], prefix: str) -> str:
    """Convert a Pydantic ``loc`` tuple to a dotted JSONPath string.

    Pydantic represents nested paths as tuples of strings (field names)
    and ints (list indices). This helper renders them in the same dotted
    + bracketed style our existing ``ValidationError.path`` strings use,
    so error messages from the Pydantic layer and the legacy manual
    sub-validators look indistinguishable to callers and to the
    ``_suggest()`` fuzzy matcher.

    Args:
        loc: Pydantic location tuple (e.g. ``("sections", "show", 0,
            "behavior", "type")``).
        prefix: Optional dotted prefix to prepend (without trailing dot).

    Returns:
        A dotted JSONPath string (e.g.
        ``"sections.show[0].behavior.type"``).

    Example:
        ```python
        _loc_to_jsonpath(("sorting", "bar", "sortBy"), "")
        # → "sorting.bar.sortBy"
        _loc_to_jsonpath(("show", 0, "behavior", "type"), "sections")
        # → "sections.show[0].behavior.type"
        ```
    """
    parts: list[str] = []
    if prefix:
        parts.append(prefix)
    for item in loc:
        if isinstance(item, int):
            if not parts:
                parts.append(f"[{item}]")
            else:
                parts[-1] = f"{parts[-1]}[{item}]"
        else:
            parts.append(str(item))
    return ".".join(parts)


# =============================================================================
# Root model dispatch table
# =============================================================================


# Maps ``CreateBookmarkParams.bookmark_type`` strings to the root Pydantic
# model that validates the bookmark's ``params`` dict. ``None`` means we
# don't yet have a canonical schema for that type (currently: user
# bookmarks, which hit the ``engage`` API directly and don't share the
# bookmark shape we explored). ``validate_bookmark()`` will skip schema
# validation in that case.
#
# Populated incrementally as model classes land — subsequent commits in
# the schema rollout will replace these ``None`` entries with concrete
# model classes.
def get_root_model_for_bookmark_type(
    bookmark_type: str,
) -> type[BaseModel] | None:
    """Return the root Pydantic model for a given ``bookmark_type``.

    Funnels and Retention reuse ``InsightsBookmarkParams`` — the
    discriminator lives on ``Behavior.type`` (``funnel`` / ``retention``),
    not on the top-level params shape. User bookmarks have no canonical
    schema in the analytics source we mirror; the dispatch returns
    ``None`` so ``validate_bookmark()`` no-ops cleanly.

    Args:
        bookmark_type: The ``CreateBookmarkParams.bookmark_type`` value
            (one of ``"insights"``, ``"funnels"``, ``"retention"``,
            ``"flows"``, ``"user"``).

    Returns:
        The Pydantic model class to validate ``params`` against, or
        ``None`` if no canonical schema exists for that type.
    """
    return {
        "insights": InsightsBookmarkParams,
        "funnels": InsightsBookmarkParams,
        "retention": InsightsBookmarkParams,
        "flows": FlowsBookmarkParams,
        "user": None,
    }.get(bookmark_type)


# =============================================================================
# Sorting models
#
# Mirrors ``analytics/lib/common/mxpnl/report/bookmarks/insights/sorting.py``
# in the upstream ``analytics`` repository. Diff against that file when
# bumping schema versions.
# =============================================================================


# Mirrors sorting.py:19 ``SortOrder``.
SortOrderLiteral = Literal["asc", "desc"]

# Mirrors sorting.py:12 ``SortBy``. The discriminated unions below pin
# specific values per variant; this alias names the full set for the
# rare consumer that needs the union directly.
SortByLiteral = Literal["value", "label", "column", "liftComparisonValue"]


class FlatLabelSortConfig(BaseModel):
    """Mirrors sorting.py:36 ``FlatLabelSortConfig``.

    Used inside ``colSortAttrs`` lists to sort a column by its label.
    """

    model_config = _BASE_CONFIG

    sortBy: Literal["label"]
    sortOrder: SortOrderLiteral
    valueField: str | None = None
    viewNLimit: int | None = None


class FlatValueSortConfig(BaseModel):
    """Mirrors sorting.py:43 ``FlatValueSortConfig``.

    Used inside ``colSortAttrs`` lists to sort a column by value.
    Accepts the deprecated ``"liftComparisonValue"`` alongside ``"value"``.
    """

    model_config = _BASE_CONFIG

    sortBy: Literal["value", "liftComparisonValue"]
    sortOrder: SortOrderLiteral
    valueField: str | None = Field(
        default=None,
        description=(
            "valueField required when sorting by value (sortBy='value') "
            "and there is > 1 valueField. Used for data tables."
        ),
    )
    viewNLimit: int | None = None


# Mirrors sorting.py:56 ``FlatSortConfig`` — discriminated by ``sortBy``.
FlatSortConfig = Annotated[
    FlatLabelSortConfig | FlatValueSortConfig,
    Field(discriminator="sortBy"),
]


class SortByColumnsConfig(BaseModel):
    """Mirrors sorting.py:61 ``SortByColumnsConfig``.

    Sort by segment columns (segment-grouped sort). Tolerates legacy
    ``sortOrder`` and ``viewNLimit`` keys via ``Ignore[T]`` — these are
    accepted at parse time but excluded from output.
    """

    model_config = _BASE_CONFIG

    sortBy: Literal["column"]
    valueField: str | None = Field(
        default=None,
        description="value field to specify which value to sort secondarily on",
    )
    colSortAttrs: list[FlatSortConfig]

    # Tolerated legacy fields (Ignore[T] in source).
    sortOrder: Ignore[JsonValue]
    viewNLimit: Ignore[JsonValue]


class SortByValueConfig(BaseModel):
    """Mirrors sorting.py:74 ``SortByValueConfig``.

    Sort by a single value column (flat sort). ``colSortAttrs`` is still
    persisted so that switching back to ``SortByColumnsConfig`` preserves
    the prior per-column sorts.
    """

    model_config = _BASE_CONFIG

    sortBy: Literal["value", "liftComparisonValue"]
    sortOrder: SortOrderLiteral | None = None
    valueField: str | None = Field(
        default=None,
        description=(
            "valueField required when sorting by value (sortBy='value') "
            "and there is > 1 valueField. Used for data tables."
        ),
    )
    colSortAttrs: list[FlatSortConfig]
    viewNLimit: int | None = None


# Mirrors sorting.py:93 ``SortConfig`` — discriminated by ``sortBy``.
SortConfig = Annotated[
    SortByColumnsConfig | SortByValueConfig,
    Field(discriminator="sortBy"),
]


class OldTableSortByValue(BaseModel):
    """Mirrors sorting.py:100 ``OldTableSortByValue``.

    Legacy table-sort variant kept on ``InsightsBookmarkSortConfig.table``
    for back-compat. Same as ``SortByValueConfig`` but uses ``sortColumn``
    instead of ``valueField`` and only allows ``FlatLabelSortConfig`` in
    ``colSortAttrs``.
    """

    model_config = _BASE_CONFIG

    sortBy: Literal["value"]
    sortOrder: SortOrderLiteral
    sortColumn: Literal["Linear", "sum", "value"]
    colSortAttrs: list[FlatSortConfig]


# Union of FlatSortConfig and SortConfig for the ``line`` field on
# ``InsightsBookmarkSortConfig`` (line charts can carry either the old
# flat sort or the new column/value sort).
FlatOrColumnSortConfig = (
    FlatLabelSortConfig | FlatValueSortConfig | SortByColumnsConfig | SortByValueConfig
)


class InsightsBookmarkSortConfig(BaseModel):
    """Mirrors sorting.py:115 ``InsightsBookmarkSortConfig``.

    The wrapper at ``params['sorting']``. Keys are chart-type strings in
    kebab-case wire form (``funnel-steps``, ``retention-curve``,
    ``insights-metric``); Python field names use snake_case via
    ``alias_generator`` so ``populate_by_name`` accepts both forms.
    """

    # Mirrors sorting.py:118 — kebab-case wire keys, snake_case Python.
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        alias_generator=lambda field_name: field_name.replace("_", "-"),
    )

    bar: SortConfig | None = None
    table: SortByColumnsConfig | SortByValueConfig | OldTableSortByValue | None = None
    line: FlatOrColumnSortConfig | None = Field(
        default=None,
        description=(
            "In the bookmark, line chart can either have the old "
            "FlatSortConfig or the new SortConfig format"
        ),
    )
    insights_metric: SortConfig | None = None
    pie: SortConfig | None = None
    retention_curve: SortConfig | None = Field(
        default=None,
        description="Retention specific",
    )
    funnel_steps: SortConfig | None = None


# =============================================================================
# Behavior tree
#
# Mirrors ``analytics/lib/common/mxpnl/report/bookmarks/insights/show.py``
# in the upstream ``analytics`` repository (~400 LOC of nested classes).
# Long-tail metadata models (MetricDisplay, Statsig, SRM, etc.) are
# mirrored faithfully but their internals use ``JsonValue`` where the
# canonical source itself does — this matches the ``filter.py`` /
# ``time.py`` placeholder pattern used in the canonical tree.
# =============================================================================


# Mirrors show.py:27 ``FiltersDeterminer``.
FiltersDeterminerLiteral = Literal["all", "any"]

# Mirrors show.py:32 ``ConversionWindowUnit``.
ConversionWindowUnitLiteral = Literal[
    "second", "minute", "hour", "day", "week", "month", "session"
]

# Mirrors show.py:42 ``FunnelReentryModeType``.
FunnelReentryModeLiteral = Literal["default", "basic", "aggressive", "optimized"]

# Mirrors show.py:49 ``FunnelOrder``.
FunnelOrderLiteral = Literal["loose", "any"]

# Mirrors show.py:54 ``RetentionType``.
RetentionTypeLiteral = Literal["compounded", "birth", "addiction"]

# Mirrors show.py:61 ``RetentionAlignmentType``.
RetentionAlignmentLiteral = Literal["birth", "interval_start"]

# Mirrors show.py:66 ``RetentionUnboundedModeType``.
RetentionUnboundedModeLiteral = Literal[
    "none", "carry_back", "carry_forward", "consecutive_forward"
]

# Mirrors show.py:73 ``COUNT_USERS_ONCE_TYPE`` (segmentMethod values).
SegmentMethodLiteral = Literal["all", "first", "last"]

# Mirrors show.py:79 ``MultiAttributionType``.
MultiAttributionTypeLiteral = Literal[
    "first_touch",
    "last_touch",
    "linear",
    "participation",
    "time_decay",
    "u_shaped",
    "j_shaped",
    "inverse_j_shaped",
    "custom",
    "session_replay_last",
]

# Mirrors show.py:124 ``START_END_TYPE``.
StartEndLiteral = Literal["start", "end"]

# Mirrors show.py:129 ``FiltersOperator``.
FiltersOperatorLiteral = Literal["and", "or", "or_all", "and_any", "then"]

# Mirrors show.py:170 ``AxisAssignment``.
AxisAssignmentLiteral = Literal["primary", "secondary"]

# Mirrors common/definitions.py:9 ``MetricType``.
MetricTypeLiteral = Literal[
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
    # Legacy values still observed in older bookmarks
    "addiction",
    "metric",
]

# Mirrors common/definitions.py:89 ``TopLevelMetricType`` persisted values
# (``new-metric-entry`` / ``new-formula-entry`` are UI-only and excluded).
TopLevelMetricTypeLiteral = Literal["metric", "formula", "metric-entry"]

# Mirrors insights/definitions.py:23 ``InsightsResourceType``.
InsightsResourceTypeLiteral = Literal[
    "all",
    "cohort",
    "cohorts",
    "event",
    "events",
    "formulas",
    "other",
    "people",
    "user",
]

# Mirrors common/definitions.py:84 ``TimeUnit``.
TimeUnitLiteral = Literal[
    "hour",
    "day",
    "week",
    "month",
    "second",
    "minute",
    "quarter",
    "year",
    "session",
    "hour_of_day",
    "day_of_week",
]


class RollingMeasurement(BaseModel):
    """Mirrors show.py:92 ``RollingMeasurement``."""

    model_config = _BASE_CONFIG

    rollingWindowSize: int | None = None


class MultiAttributionWeights(BaseModel):
    """Mirrors show.py:96 ``MultiAttributionWeights``."""

    model_config = _BASE_CONFIG

    first: int
    middle: int
    last: int


class CustomMultiAttribution(BaseModel):
    """Mirrors show.py:102 ``CustomMultiAttribution``."""

    model_config = _BASE_CONFIG

    type: Literal["custom"]
    name: str
    weights: MultiAttributionWeights


class PredefinedMultiAttribution(BaseModel):
    """Mirrors show.py:110 ``PredefinedMultiAttribution``."""

    model_config = _BASE_CONFIG

    type: MultiAttributionTypeLiteral
    name: str | None = None
    weights: MultiAttributionWeights | None = None
    step_index: int | None = None


class StepRange(BaseModel):
    """Mirrors show.py:161 ``StepRange``.

    Uses ``from_step`` / ``to_step`` as Python field names with aliases
    ``from`` / ``to`` because ``from`` is a Python keyword.
    """

    model_config = _BASE_CONFIG

    from_step: int | None = Field(default=None, alias="from")
    to_step: int | None = Field(default=None, alias="to")


class FunnelStep(BaseModel):
    """Mirrors show.py:137 ``FunnelStep``.

    Used inside ``Behavior.exclusions``. Tolerates legacy keys via
    ``Ignore[T]``.
    """

    model_config = _BASE_CONFIG

    bool_op: FiltersOperatorLiteral | None = None
    property_filter_params_list: list[JsonValue] | None = None
    event: str | None = None
    event_id: int | None = None
    custom_event: int | None = None
    custom_event_name: str | None = None
    step_label: str | None = None
    session_event: StartEndLiteral | None = None
    forward: int | None = None
    reverse: int | None = None

    # Tolerated legacy fields.
    dropdown_tab_index: Ignore[JsonValue]
    filter: Ignore[JsonValue]
    property: Ignore[JsonValue]
    selected_property_type: Ignore[JsonValue]
    serialized: Ignore[JsonValue]
    type: Ignore[JsonValue]


class ExclusionFunnelStep(FunnelStep):
    """Mirrors show.py:166 ``ExclusionFunnelStep``."""

    steps: StepRange


class MetricDisplay(BaseModel):
    """Mirrors show.py:175 ``MetricDisplay``."""

    model_config = _BASE_CONFIG

    abbrev: bool | None = None
    axis: AxisAssignmentLiteral | None = None
    direction: Literal["up", "down"] | None = None
    hideTrendline: bool | None = None
    precision: Literal[0, 1, 2, 3, 4, 5, 6, 7, 8] | None = None
    prefix: str | None = None
    suffix: str | None = None
    trendline: bool | None = None


class Bucket(BaseModel):
    """Mirrors insights/definitions.py:77 ``Bucket``."""

    model_config = _BASE_CONFIG

    bucketSize: float | None = None
    disabled: bool | None = None
    groups: list[float] | None = None
    max: float | None = None
    min: float | None = None
    offset: int | None = None
    unit: str | None = None


class Winsorization(BaseModel):
    """Mirrors show.py:304 ``Winsorization``."""

    model_config = _BASE_CONFIG

    enabled: bool | None = None
    lower_percentile: float | None = None
    upper_percentile: float | None = None


class Statsig(BaseModel):
    """Mirrors show.py:310 ``Statsig``."""

    model_config = _BASE_CONFIG

    confidence: float | None = None
    control_key: str
    sequential_testing_adjustment: JsonValue | None = None
    pre_exposure_date_range: list[str] | None = None
    winsorization: Winsorization | None = None
    math: str | None = None
    exposures: dict[str, int | dict[str, int]] | None = None
    version: str | None = None


class SRM(BaseModel):
    """Mirrors show.py:322 ``SRM``."""

    model_config = _BASE_CONFIG

    expectedRatios: dict[str, float]


class Goal(BaseModel):
    """Mirrors common/definitions.py:185 ``Goal``."""

    model_config = _BASE_CONFIG

    id: str
    label: str
    checkpoints: list[tuple[str, float]]
    target_type: Literal["absolute", "relative"] = "absolute"
    target_input: float | None = None
    # Deprecated fields, excluded from output.
    unit: Ignore[JsonValue]
    direction: Ignore[JsonValue]


class SubBehavior(BaseModel):
    """Mirrors show.py:186 ``SubBehavior``.

    Used inside ``Behavior.behaviors`` for funnel-step nesting.
    Constrained ``type`` to event/custom-event/funnel.
    """

    model_config = _BASE_CONFIG

    type: Literal["event", "custom-event", "funnel"] | None = None
    id: int | None = None
    name: str | None = None
    renamed: str | None = None
    # FilterClause = JsonValue in source. Use default_factory to avoid the
    # mutable-default smell while preserving ``| None`` for null-tolerance
    # (older bookmarks send ``"filters": null``).
    filters: list[JsonValue] | None = Field(default_factory=list)
    filtersDeterminer: FiltersDeterminerLiteral | None = "all"
    funnelOrder: FunnelOrderLiteral | None = None
    behaviors: list[SubBehavior] | None = Field(default_factory=list)
    display: MetricDisplay | None = None
    customEventSet: bool | None = None


class Behavior(BaseModel):
    """Mirrors show.py:209 ``Behavior``.

    Single class with ``type`` field that selects the variant. The
    canonical source treats this as one wide model rather than a
    discriminated union — we follow that for fidelity.
    """

    model_config = _BASE_CONFIG

    # Common fields
    type: MetricTypeLiteral | None = None
    id: int | None = None
    name: str | None = None
    renamed: str | None = None
    dataGroupId: str | None = None

    # Deprecated singular ``filter``, retained as Ignore[T].
    filter: Ignore[JsonValue]
    filters: list[JsonValue] | None = None
    filtersDeterminer: FiltersDeterminerLiteral | None = None

    resourceType: InsightsResourceTypeLiteral | None = None

    behaviors: list[SubBehavior] | None = Field(default_factory=list)

    # Inline cohort
    raw_cohort: JsonValue | None = None

    # Insights
    customBucket: Bucket | None = None

    # Funnel
    conversionWindowDuration: int | None = None
    conversionWindowUnit: ConversionWindowUnitLiteral | None = None
    funnelReentryMode: FunnelReentryModeLiteral | None = None
    funnelOrder: FunnelOrderLiteral | None = None
    exclusions: list[ExclusionFunnelStep] | None = None
    aggregateBy: list[JsonValue] | None = None

    # Retention
    retentionType: RetentionTypeLiteral | None = None
    retentionAlignmentType: RetentionAlignmentLiteral | None = None
    retentionUnit: TimeUnitLiteral | None = None
    retentionUnbounded: bool | None = None
    retentionUnboundedMode: RetentionUnboundedModeLiteral | None = None
    retentionCustomBucketSizes: list[int] | None = None
    segmentationEvent: str | None = None

    # Deprecated / back-compat
    unsavedId: str | None = None
    search: str | None = None
    profileType: str | None = None
    dataset: str | None = None
    datasetId: str | None = None
    projectId: int | None = None

    display: MetricDisplay | None = None
    disableCohortize: bool | None = None
    customEventSet: bool | None = None

    hasUnsavedChanges: bool | None = False


# Discriminated multi-attribution union mirroring show.py:274.
MultiAttribution = PredefinedMultiAttribution | CustomMultiAttribution


class BehaviorMeasurement(BaseModel):
    """Mirrors show.py:277 ``BehaviorMeasurement``."""

    model_config = _BASE_CONFIG

    dataGroupId: str | None = None
    math: str | None = None  # MATH_TYPE union — kept loose to allow drift
    property: JsonValue | None = None
    cumulative: bool | None = None
    perUserAggregation: str | None = None
    rolling: RollingMeasurement | None = None

    segmentMethod: SegmentMethodLiteral | None = None
    multiAttribution: MultiAttribution | None = None

    stepIndex: int | None = None
    actionMode: str | None = None
    actionStep: int | None = None

    retentionBucketIndex: int | None = None
    retentionCumulative: bool | None = None
    retentionSegmentationEvent: JsonValue | None = None
    percentile: float | None = None

    # Tolerated legacy fields.
    id: Ignore[JsonValue]
    type: Ignore[JsonValue]


class FormulaMeasurement(BaseModel):
    """Mirrors show.py:326 ``FormulaMeasurement``."""

    model_config = _BASE_CONFIG

    cumulative: bool | None = None
    rolling: RollingMeasurement | None = None
    multiAttribution: MultiAttribution | None = None


class BehaviorShowClause(BaseModel):
    """Mirrors show.py:332 ``BehaviorShowClause``.

    Discriminator: ``type=Literal["metric"]``. Selected by
    ``show_clause_discriminator`` when ``type == "metric"`` and no
    ``formula`` key present.
    """

    model_config = _BASE_CONFIG

    idx: str | None = Field(default=None, alias="_idx")
    type: Literal["metric"] | None = None
    id: int | None = None

    userNamed: bool | None = None
    name: str | None = None

    behavior: Behavior | None = None
    measurement: BehaviorMeasurement | None = None

    statsig: Statsig | None = None
    srm: SRM | None = None

    comparisons: list[JsonValue] | None = Field(default_factory=list)

    display: MetricDisplay | None = None
    isHidden: bool | None = None
    isExpanded: bool | None = None
    labelPrefix: str | None = None
    formulaLabel: str | None = None
    showClauseIndex: int | None = None
    hasUnsavedChanges: bool | None = False
    goals: list[Goal] | None = None
    overrides: dict[str, Any] | None = None


class FormulaShowClause(BaseModel):
    """Mirrors show.py:364 ``FormulaShowClause``.

    Discriminator: presence of ``formula`` key OR
    ``type == "formula"``. Selected by ``show_clause_discriminator``.
    """

    model_config = _BASE_CONFIG

    idx: str | None = Field(default=None, alias="_idx")
    type: Literal["formula"] | None = None
    formula: JsonValue | None = None
    measurement: FormulaMeasurement | None = None
    statsig: Statsig | None = None

    display: MetricDisplay | None = None
    isHidden: bool | None = None
    isExpanded: bool | None = None
    userNamed: bool | None = None

    comparisons: list[JsonValue] | None = Field(default_factory=list)

    id: int | None = None
    definition: str | None = None
    name: str | None = None
    referencedMetrics: list[BehaviorShowClause] | None = None

    hasUnsavedChanges: bool | None = False
    overrides: dict[str, Any] | None = None
    goals: list[Goal] | None = None


def _show_clause_discriminator(v: Any) -> str:
    """Mirrors show.py:394 ``show_clause_discriminator``.

    Selects the ``ShowClause`` variant based on the ``type`` value or
    the presence of a ``formula`` key.
    """
    if isinstance(v, dict):
        clause_type = v.get("type")
        has_formula = "formula" in v
    else:
        clause_type = getattr(v, "type", None)
        has_formula = hasattr(v, "formula")
    return (
        "FormulaShowClause"
        if clause_type == "formula" or has_formula
        else "BehaviorShowClause"
    )


# Mirrors show.py:409 ``ShowClause`` discriminated union.
from pydantic import Discriminator, Tag  # noqa: E402  (after model defs)

ShowClause = Annotated[
    Annotated[FormulaShowClause, Tag("FormulaShowClause")]
    | Annotated[BehaviorShowClause, Tag("BehaviorShowClause")],
    Discriminator(_show_clause_discriminator),
]


# =============================================================================
# Sections
#
# Mirrors ``analytics/lib/common/mxpnl/report/bookmarks/insights/sections.py:15``
# in the upstream ``analytics`` repository.
# ``filter`` and ``time`` are typed as ``JsonValue`` in the canonical
# source itself (see ``filter.py`` / ``time.py`` placeholders) — we
# follow that.
# =============================================================================


class Sections(BaseModel):
    """Mirrors sections.py:15 ``Sections``.

    ``show`` and ``time`` are required. All other fields optional.
    Uses ``JsonValue`` for filter/time/group/cohort lists pending the
    canonical source promoting them from placeholders to real models.
    """

    model_config = _BASE_CONFIG

    cohorts: list[JsonValue] | None = None
    filter: list[JsonValue] | None = None
    formula: list[JsonValue] | None = None  # deprecated per source
    globalDataGroupId: str | None = None
    group: list[JsonValue] | None = None
    group_by: list[JsonValue] | None = None
    metricLevelDataGroups: bool | None = None
    show: list[ShowClause]
    time: list[JsonValue]


# =============================================================================
# DisplayOptions
#
# Mirrors ``analytics/lib/common/mxpnl/report/bookmarks/insights/display_options.py``
# in the upstream ``analytics`` repository.
# =============================================================================


# Mirrors display_options.py:36 ``ChartPlotStyle``.
ChartPlotStyleLiteral = Literal["standard", "stacked"]

# Mirrors display_options.py:41 ``AnalysisType``.
AnalysisTypeLiteral = Literal["linear", "logarithmic", "rolling", "cumulative"]

# Mirrors display_options.py:48 ``ValueRepresentationType``.
ValueRepresentationLiteral = Literal["absolute", "relative"]

# Mirrors display_options.py:53 ``TableSummaryAggregation``.
TableSummaryAggregationLiteral = Literal["average", "sum", "min", "max", "median"]

# Mirrors display_options.py:17 ``InsightsChartType`` — the constrained
# subset of ``ChartType`` accepted on insights bookmarks. Wider chart
# types still surface on funnels / retention / flows, so this is kept
# permissive as a regular string here; the dispatch layer enforces the
# narrower per-type constraint.
ChartTypeLiteral = str  # keep loose; per-type roots can tighten later


class AnnotationOptions(BaseModel):
    """Mirrors display_options.py:66 ``AnnotationOptions``."""

    model_config = _BASE_CONFIG

    tagFilterIds: list[int] | None = None
    showUntagged: bool | None = None
    sortOrder: SortOrderLiteral | None = None
    hideAnnotations: bool | None = None
    creatorFilterIds: list[int] | None = None


class CommentOptions(BaseModel):
    """Mirrors display_options.py:74 ``CommentOptions``."""

    model_config = _BASE_CONFIG

    commentsDisabled: bool | None = None


class SegmentId(BaseModel):
    """Mirrors display_options.py:78 ``SegmentId``."""

    model_config = _BASE_CONFIG

    prop: str
    propName: str | None = None
    cohortDesc: JsonValue | None = None


class FunnelStepsSelectedTableColumns(BaseModel):
    """Mirrors display_options.py:96 ``FunnelStepsSelectedTableColumns``.

    Kebab-case wire keys (``conv-first-step``) map to snake_case Python
    fields (``conv_first_step``) via ``alias_generator``.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        alias_generator=lambda field_name: field_name.replace("_", "-"),
    )

    conv_first_step: bool = False
    conv_prev_step: bool = False
    count: bool = False
    stat_sig: bool = False
    time_first_step: bool = False
    time_prev_step: bool = False


class DisplayOptions(BaseModel):
    """Mirrors display_options.py:110 ``DisplayOptions``.

    ``chartType`` is required. All other fields optional. ``axisAssignments``
    is tolerated via ``Ignore[T]``.
    """

    model_config = _BASE_CONFIG

    chartType: str  # InsightsChartType in source; loose here to span query types
    plotStyle: ChartPlotStyleLiteral | None = None
    analysis: AnalysisTypeLiteral | None = None
    value: ValueRepresentationLiteral | None = None
    rollingWindowSize: int | None = None
    timeUnit: TimeUnitLiteral | None = None
    primaryYAxisOptions: JsonValue | None = None
    secondaryYAxisOptions: JsonValue | None = None
    theme: JsonValue | None = None
    xAxisOptions: JsonValue | None = None
    annotationOptions: AnnotationOptions | None = None
    commentOptions: CommentOptions | None = None
    queryTimeSampling: bool | None = None
    tableSummaryAggregation: TableSummaryAggregationLiteral | None = None
    statSigControl: list[SegmentId] | None = None
    funnelStepsSelectedTableColumns: FunnelStepsSelectedTableColumns | None = None

    # Tolerated legacy fields.
    axisAssignments: Ignore[JsonValue]


# =============================================================================
# InsightsBookmarkParams root
#
# Mirrors ``analytics/lib/common/mxpnl/report/bookmarks/insights/bookmark.py:25``
# in the upstream ``analytics`` repository.
#
# Long-tail dependent models (ColumnWidths, ForecastComparison,
# InsightsLegend, LiftComparison, ExecutedMigration) are typed as
# ``JsonValue`` here pending later mirroring; in practice they're rarely
# touched by client-side bookmark construction.
# =============================================================================


class InsightsBookmarkParams(BaseModel):
    """Mirrors bookmark.py:25 ``InsightsBookmarkParams``.

    Root model for insights / funnels / retention bookmarks. Includes
    the 27 ``Ignore[T]`` legacy fields from the source so older bookmarks
    pass validation.
    """

    model_config = _BASE_CONFIG

    columnWidths: JsonValue | None = None
    displayOptions: DisplayOptions
    forecastComparison: JsonValue | None = None
    legend: JsonValue | None = None
    liftComparison: JsonValue | None = None
    name: str | None = None
    sections: Sections
    sorting: InsightsBookmarkSortConfig | None = None
    timeComparison: JsonValue | None = None
    versions: list[str] | None = None
    executedMigrations: list[JsonValue] | None = None

    # Tolerated legacy fields (mirrors bookmark.py:45-76, 27 entries).
    alignment: Ignore[JsonValue]
    anchor_position: Ignore[JsonValue]
    anchorPosition: Ignore[JsonValue]
    cardinality: Ignore[JsonValue]
    cardinality_threshold: Ignore[JsonValue]
    chart_type: Ignore[JsonValue]
    chartType: Ignore[JsonValue]
    count_type: Ignore[JsonValue]
    date_range: Ignore[JsonValue]
    error: Ignore[JsonValue]
    exclusions: Ignore[JsonValue]
    fields: Ignore[JsonValue]
    filter_by_cohort: Ignore[JsonValue]
    filter_by_event: Ignore[JsonValue]
    global_access_type: Ignore[JsonValue]
    graph_sort_priority: Ignore[JsonValue]
    group_by: Ignore[JsonValue]
    hidden_events: Ignore[JsonValue]
    icon: Ignore[str]
    id: Ignore[int]
    isNewQBEnabled: Ignore[bool]
    modified: Ignore[JsonValue]
    segments: Ignore[JsonValue]
    smartHub: Ignore[JsonValue]
    steps: Ignore[JsonValue]
    title: Ignore[str]
    trend_unit: Ignore[JsonValue]
    trendType: Ignore[JsonValue]
    ttcVizType: Ignore[JsonValue]
    use_query_sampling: Ignore[JsonValue]
    user: Ignore[JsonValue]
    user_id: Ignore[JsonValue]


# =============================================================================
# Flows tree
#
# Mirrors ``analytics/mixpanel_mcp/mcp_server/types/reports/internal/bookmark.py:408-459``
# in the upstream ``analytics`` repository. Flat shape (no `sections`
# wrapper).
# =============================================================================


class FlowsBookmarkStep(BaseModel):
    """Mirrors mixpanel_mcp/.../bookmark.py:408 ``FlowsBookmarkStep``."""

    model_config = _BASE_CONFIG

    event: str | None = None
    event_id: int | None = None
    custom_event: int | None = None
    session_event: StartEndLiteral | None = None
    step_label: str | None = None
    forward: int = 0
    reverse: int = 0
    bool_op: str = "and"
    property_filter_params_list: list[JsonValue] = Field(default_factory=list)


class FlowsBookmarkParams(BaseModel):
    """Mirrors mixpanel_mcp/.../bookmark.py:422 ``FlowsBookmarkParams``."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")
    # NOTE: Flows bookmarks in the wild carry many UI-only fields not
    # documented in the canonical mirror. Use ``extra="allow"`` here
    # rather than ``extra="forbid"`` to avoid false-rejection of valid
    # bookmarks. The MCP source itself uses ``MixpanelBaseModel`` which
    # does NOT default to ``extra="forbid"``.

    steps: list[FlowsBookmarkStep]
    date_range: dict[str, Any]
    flows_merge_type: str = "graph"
    count_type: str = "unique"
    cardinality_threshold: int = 10
    version: int = 2
    conversion_window: dict[str, Any] = Field(
        default_factory=lambda: {"unit": "day", "value": 7}
    )
    anchor_position: int = 1
    alignment: list[int] = Field(default_factory=lambda: [1, 0])
    collapse_repeated: bool = False
    show_custom_events: bool = True
    hidden_events: list[str] = Field(default_factory=list)

    exclusions: list[JsonValue] | None = None
    filter_by_cohort: JsonValue | None = None
    filter_by_event: JsonValue | None = None
    group_by: list[JsonValue] | None = None
    aggregate_by: list[JsonValue] | None = None
    data_group_id: str | None = None
    segments: list[JsonValue] | None = None
    time_percentiles_enabled: bool | None = None

    # UI compatibility
    chartType: str | None = None
