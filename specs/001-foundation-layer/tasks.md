# Tasks: Foundation Layer

**Feature**: `001-foundation-layer`
**Generated**: 2025-12-19
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Task Legend

- `T###` - Task number
- `[P1/P2/P3]` - Priority level
- `[US#]` - User Story reference
- `[SETUP]` - Project setup task
- `[POLISH]` - Final polish/verification task

---

## Phase 0: Project Setup

> Prerequisite tasks before feature implementation.

- [ ] T001 [SETUP] Create package directory structure at `src/mixpanel_data/`
- [ ] T002 [SETUP] Create `src/mixpanel_data/__init__.py` with public API exports placeholder
- [ ] T003 [SETUP] Create `src/mixpanel_data/_internal/` directory with `__init__.py`
- [ ] T004 [SETUP] Create `src/mixpanel_data/py.typed` PEP 561 marker file
- [ ] T005 [SETUP] Create `pyproject.toml` with project metadata and dependencies:
  - Python 3.11+
  - pydantic>=2.0
  - tomli-w>=1.0
  - pandas>=2.0
  - Dev dependencies: pytest, pytest-cov, ruff, mypy
- [ ] T006 [SETUP] Create `tests/` directory with `conftest.py` and `unit/`, `integration/` subdirectories
- [ ] T007 [SETUP] Verify `pip install -e ".[dev]"` succeeds

---

## Phase 1: User Story 1 - Configure Mixpanel Credentials (P1)

> FR-001 to FR-007 | [config-manager.md](contracts/config-manager.md)

### Foundational Types

- [ ] T101 [P1] [US1] Create `Credentials` frozen Pydantic model at `src/mixpanel_data/_internal/config.py`
  - Fields: username, secret (SecretStr), project_id, region
  - Validate region in (us, eu, in)
  - Ensure `__repr__` and `__str__` redact secret
- [ ] T102 [P1] [US1] Create `AccountInfo` dataclass for account listing
  - Fields: name, username, project_id, region, is_default
  - Excludes secret intentionally

### ConfigManager Core

- [ ] T103 [P1] [US1] Implement `ConfigManager.__init__` with optional `config_path` parameter
  - Default path: `~/.mp/config.toml`
  - Support `MP_CONFIG_PATH` environment variable override
- [ ] T104 [P1] [US1] Implement `ConfigManager.add_account()` method
  - Create config directory if not exists
  - Validate region parameter
  - Raise `AccountExistsError` if name already exists (requires T201)
  - Write TOML using `tomli-w`
- [ ] T105 [P1] [US1] Implement `ConfigManager.list_accounts()` method
  - Return list of `AccountInfo` objects
  - Handle missing config file gracefully (return empty list)
- [ ] T106 [P1] [US1] Implement `ConfigManager.remove_account()` method
  - Raise `AccountNotFoundError` if name doesn't exist (requires T202)
  - Update TOML file
- [ ] T107 [P1] [US1] Implement `ConfigManager.set_default()` method
  - Raise `AccountNotFoundError` if name doesn't exist
  - Update `default` key in TOML
- [ ] T108 [P1] [US1] Implement `ConfigManager.get_account()` method
  - Return `AccountInfo` for named account
  - Raise `AccountNotFoundError` if not found

### Credential Resolution

- [ ] T109 [P1] [US1] Implement environment variable reading for credentials
  - Check: MP_USERNAME, MP_SECRET, MP_PROJECT_ID, MP_REGION
  - Return `Credentials` if all four are set
- [ ] T110 [P1] [US1] Implement `ConfigManager.resolve_credentials(account=None)` method
  - Priority order: env vars → named account → default account
  - Raise `ConfigError` if no credentials can be resolved
  - Return immutable `Credentials` object

### Unit Tests

- [ ] T111 [P1] [US1] Create `tests/unit/test_config.py` with fixtures
- [ ] T112 [P1] [US1] Test: add_account stores credentials correctly
- [ ] T113 [P1] [US1] Test: list_accounts returns empty list when no config
- [ ] T114 [P1] [US1] Test: resolve_credentials env vars take precedence
- [ ] T115 [P1] [US1] Test: resolve_credentials falls back to default account
- [ ] T116 [P1] [US1] Test: secret never appears in Credentials repr/str
- [ ] T117 [P1] [US1] Test: AccountNotFoundError lists available accounts

---

## Phase 2: User Story 2 - Receive Clear Error Messages (P2)

> FR-008 to FR-011 | [exceptions.md](contracts/exceptions.md)

### Base Exception

- [ ] T201 [P2] [US2] Create `MixpanelDataError` base exception at `src/mixpanel_data/exceptions.py`
  - Constructor: message, code="UNKNOWN_ERROR", details=None
  - Properties: code, details, message
  - Method: `to_dict()` returning JSON-serializable dictionary

### Configuration Exceptions

- [ ] T202 [P2] [US2] Create `ConfigError(MixpanelDataError)` with code="CONFIG_ERROR"
- [ ] T203 [P2] [US2] Create `AccountNotFoundError(ConfigError)` with code="ACCOUNT_NOT_FOUND"
  - Constructor: account_name, available_accounts=None
  - Include available_accounts in details
- [ ] T204 [P2] [US2] Create `AccountExistsError(ConfigError)` with code="ACCOUNT_EXISTS"
  - Constructor: account_name

### Operation Exceptions

- [ ] T205 [P2] [US2] Create `AuthenticationError(MixpanelDataError)` with code="AUTH_FAILED"
- [ ] T206 [P2] [US2] Create `RateLimitError(MixpanelDataError)` with code="RATE_LIMITED"
  - Constructor: message, retry_after=None
  - Property: retry_after (int or None)
  - Include retry_after in details
- [ ] T207 [P2] [US2] Create `QueryError(MixpanelDataError)` with code="QUERY_FAILED"

### Storage Exceptions

- [ ] T208 [P2] [US2] Create `TableExistsError(MixpanelDataError)` with code="TABLE_EXISTS"
  - Constructor: table_name
  - Include suggestion in details: "use drop() first"
- [ ] T209 [P2] [US2] Create `TableNotFoundError(MixpanelDataError)` with code="TABLE_NOT_FOUND"
  - Constructor: table_name

### Unit Tests

- [ ] T210 [P2] [US2] Create `tests/unit/test_exceptions.py`
- [ ] T211 [P2] [US2] Test: all exceptions inherit from MixpanelDataError
- [ ] T212 [P2] [US2] Test: to_dict() output is JSON serializable
- [ ] T213 [P2] [US2] Test: AccountNotFoundError includes available_accounts
- [ ] T214 [P2] [US2] Test: RateLimitError.retry_after property works
- [ ] T215 [P2] [US2] Test: error codes match expected values

---

## Phase 3: User Story 3 - Work with Structured Operation Results (P3)

> FR-012 to FR-015 | [result-types.md](contracts/result-types.md)

### FetchResult

- [ ] T301 [P3] [US3] Create `FetchResult` frozen dataclass at `src/mixpanel_data/types.py`
  - Fields: table, rows, type (events|profiles), duration_seconds, date_range, fetched_at
  - Property: `df` (lazy pandas DataFrame conversion)
  - Method: `to_dict()` (JSON serializable, datetime as ISO string)
- [ ] T302 [P3] [US3] Implement lazy DataFrame caching for FetchResult.df
  - Use `object.__setattr__` pattern for frozen dataclass caching

### SegmentationResult

- [ ] T303 [P3] [US3] Create `SegmentationResult` frozen dataclass
  - Fields: event, from_date, to_date, unit, segment_property, total, series
  - `series`: dict mapping segment names to time-series data (e.g., `{"US": {"2024-01-01": 100, ...}}`)
  - Property: `df` with columns: date, segment, count (derived from series)
  - Method: `to_dict()`

### FunnelResult

- [ ] T304 [P3] [US3] Create `FunnelStep` frozen dataclass
  - Fields: event, count, conversion_rate
- [ ] T305 [P3] [US3] Create `FunnelResult` frozen dataclass
  - Fields: funnel_id, funnel_name, from_date, to_date, conversion_rate, steps
  - Property: `df` with columns: step, event, count, conversion_rate
  - Method: `to_dict()`

### RetentionResult

- [ ] T306 [P3] [US3] Create `CohortInfo` frozen dataclass
  - Fields: date, size, retention (list of floats)
- [ ] T307 [P3] [US3] Create `RetentionResult` frozen dataclass
  - Fields: born_event, return_event, from_date, to_date, unit, cohorts
  - Property: `df` with columns: cohort_date, cohort_size, period_N
  - Method: `to_dict()`

### JQLResult

- [ ] T308 [P3] [US3] Create `JQLResult` frozen dataclass
  - Property: `df` (lazy conversion)
  - Property: `raw` (list of raw result data)
  - Method: `to_dict()`

### Unit Tests

- [ ] T309 [P3] [US3] Create `tests/unit/test_types.py`
- [ ] T310 [P3] [US3] Test: FetchResult is immutable (raises on modification)
- [ ] T311 [P3] [US3] Test: FetchResult.df returns pandas DataFrame
- [ ] T312 [P3] [US3] Test: to_dict() output is JSON serializable (datetime handling)
- [ ] T313 [P3] [US3] Test: SegmentationResult.df has expected columns
- [ ] T314 [P3] [US3] Test: FunnelResult.steps iteration works correctly

---

## Phase 4: Public API & Polish

> Final integration and quality verification.

### Public API Exports

- [ ] T401 [POLISH] Update `src/mixpanel_data/__init__.py` with public exports:
  - `MixpanelDataError` and all exception subclasses
  - `FetchResult`, `SegmentationResult`, `FunnelResult`, `RetentionResult`, `JQLResult`
  - `FunnelStep`, `CohortInfo`
- [ ] T402 [POLISH] Create `src/mixpanel_data/auth.py` with public auth functions:
  - Re-export ConfigManager functionality for public access

### Integration Tests

- [ ] T403 [POLISH] Create `tests/integration/test_config_file.py`
  - Test file I/O with temp directories
  - Test permission handling
  - Test malformed TOML handling
- [ ] T404 [POLISH] Create `tests/integration/test_foundation.py`
  - Full workflow test per [quickstart.md](quickstart.md)

### Quality Verification

- [ ] T405 [POLISH] Run `ruff check src/` and fix all issues
- [ ] T406 [POLISH] Run `mypy --strict src/` and fix all type errors
- [ ] T407 [POLISH] Run `pytest tests/unit/` - all tests pass
- [ ] T408 [POLISH] Run `pytest tests/integration/` - all tests pass
- [ ] T409 [POLISH] Verify code coverage >= 90% for foundation layer

### Documentation

- [ ] T410 [POLISH] Verify all public classes have docstrings
- [ ] T411 [POLISH] Update checklists with completion status

---

## Task Summary

| Phase | Tasks | Priority |
| ----- | ----- | -------- |
| Setup | T001-T007 | Pre-requisite |
| User Story 1 | T101-T117 | P1 (17 tasks) |
| User Story 2 | T201-T215 | P2 (15 tasks) |
| User Story 3 | T301-T314 | P3 (14 tasks) |
| Polish | T401-T411 | Final (11 tasks) |
| **Total** | **64 tasks** | - |

## Dependency Graph

```text
Setup (T001-T007)
    │
    ▼
Exceptions (T201-T215) ◄─────────────────┐
    │                                     │
    ▼                                     │ (uses exceptions)
ConfigManager (T101-T117) ───────────────┤
    │                                     │
    ▼                                     │
Result Types (T301-T314) ────────────────┘
    │
    ▼
Polish (T401-T411)
```

**Recommended Order**: Setup → Exceptions → ConfigManager → Result Types → Polish
