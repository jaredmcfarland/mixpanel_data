---

description: "Task list for Authentication Architecture Redesign (042)"
---

# Tasks: Authentication Architecture Redesign (Account → Project → Workspace)

**Input**: Design documents from `/specs/042-auth-architecture-redesign/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)
**Source design**: [`context/auth-architecture-redesign.md`](../../context/auth-architecture-redesign.md)
**Branch**: `042-auth-architecture-redesign`
**Supersedes**: 038-auth-project-workspace-redesign

## Status (as of 2026-04-22 — post A1 cluster `4d21c3e`)

| Phase | Status | Tests | Notes |
|-------|--------|-------|-------|
| 1 — Setup | ✅ DONE (5/5) | infra | branch, fixtures, conftest, just recipe |
| 2 — Foundational types | ✅ DONE (13/13) | 89 | Account union, Session, Project, WorkspaceRef, TokenResolver, OnDiskTokenResolver |
| 3 — Schema + Resolver (US2 + US3) | ✅ DONE (12/12) | 79 | `_internal/config.py` (formerly `config_v3.py`) + `_internal/auth/resolver.py` + `BridgeFile` v2 |
| 4 — Account model + Workspace.use (US1 + US4) | ✅ MOSTLY DONE (B1 cleared the dual-init blocker; A1 wired the OAuth trio) | 71 | mp.accounts/.targets/.session namespaces; Workspace.use() chain; api_client session support; `mp.accounts.login` end-to-end PKCE; OAuth refresh in OnDiskTokenResolver; per-request bearer in api_client. **B2 sweeps remaining** (T043 / T044 / T045 / T047 / T048 / T050 / T053a): per-account `me.json` paths, `OAuthTokens.project_id` removal, `auth.py` thin re-export, deprecated `Workspace` methods (`switch_project`, `switch_workspace`, `set_workspace_id`, `current_credential`, `current_project`), `auth_credential.py` deletion. |
| 5 — CLI surface (US5) | ✅ DONE (additive → cleanup landed in `5a6b876` and tightened in B1: legacy `--credential` / `--workspace-id` globals removed; A1 wired `mp account login NAME --no-browser`) | 17 | `mp account/project/workspace/session/target` groups + `--account`/`--project`/`--workspace`/`--target` globals; legacy command groups gone |
| 6 — Targets (US6) | ✅ DONE (`5a6b876`) | +10 | `mp target add/use/list/show/remove` + 10 smoke tests |
| 7 — Cross-cutting iteration (US7) | ⬜ PENDING (Cluster C1) | — | integration tests for cross-project / cross-account / parallel-snapshot — capability is live, dedicated tests deferred |
| 8 — Cowork bridge (US8) | ⚠️ PARTIAL — read path live, **export side pending (Cluster C2)** | live F1.01 | `BridgeFile` v2 loader integrated into resolver; `mp account export-bridge` / `remove-bridge` writers still TODO |
| 9 — Plugin / agent surface (US9) | ⬜ PENDING (Cluster A2) — now unblocked by A1 | — | `auth_manager.py` rewrite; plugin v5.0.0 — A1 made the public Python API final (no more `NotImplementedError` stubs) |
| 10 — Conversion script (US10) | ❌ DROPPED (alpha "free to break") | — | Legacy detection deleted in `5a6b876`; legacy `ConfigManager` + `AccountInfo` + v1 `AuthBridgeFile` fully removed in B1 (`18283b4` / `024a291`); no migration path needed |
| 11 — Polish & cleanup (Cluster D) | ⚠️ MOSTLY DONE in `5a6b876` (atomicity, validation, type design, comment-rot scrub, PBT, real-`~/.mp/` write guard); **still pending**: B3 (`mixpanel_data.auth_types` public module — Fix 27), Phase 11 release polish — see `pr-126-review-plan.md` § Execution Status | — | docs, mutation tests, version bump |

**Full test suite (HEAD `4d21c3e`)**: 5,956 passed @ 90.85% coverage; mypy --strict + ruff clean. (B1 dropped from 6,261 to 5,948 by removing dead legacy tests; A1 added 8 unit tests covering refresh / login / per-request bearer.)
**Live QA (`tests/live/test_042_auth_redesign_live.py`)**: 18 / 18 pass against real Mixpanel API at HEAD `4d21c3e`.
**Net diff for B1+A1**: +2,472 / −11,619 across 141 files (4 commits — Fix 10 / Fix 14 / Fix 9 / Fix 16+17+18).

### Pragmatic deviation from the original phase plan (history)

Phases 4-5 originally landed **additively** (new code beside legacy code) so the suite stayed green during rollout. The B1 cluster (`12471c6` / `024a291` / `18283b4`) **collapsed the additive layer**:

- `_internal/config.py` now IS the v3 ConfigManager (the legacy ConfigManager + AccountInfo / CredentialInfo / ActiveContext / ProjectAlias / MigrationResult dataclasses are gone).
- `_internal/auth/bridge.py` only carries the v2 `BridgeFile` schema (v1 `AuthBridgeFile` + 9 helpers + `# noqa: E402` import block deleted).
- `Workspace.__init__` is keyword-only — `account=`, `project=`, `workspace=`, `target=`, `session=` per `contracts/python-api.md` §1; legacy positional callers no longer compile.
- `MixpanelAPIClient` still accepts either `credentials=` (built by the v3 shim `session_to_credentials(sess)`) or `session=` directly — Cluster A1 (Fix 18) finishes that consolidation.
- The legacy `mp auth` / `mp projects` / `mp workspaces` / `mp context` CLI groups were already deleted in `5a6b876`; B1 also retired the `--credential` and `--workspace-id` global flags.

### Remaining `[-]` deferred tasks (post-B1)

The B1 cluster cleared Fix 9 / 10 / 14 outright. These T-IDs are still deferred and form the **B2 sweep** (Cluster B2 in the handoff doc):

- T043, T044, T045 — `me.py` per-account `me.json`, `OAuthTokens.project_id` removal, per-account paths for `flow.py` / `client_registration.py`.
- T047 — Rewrite `src/mixpanel_data/auth.py` as a thin re-export module.
- T048 — DELETE `src/mixpanel_data/_internal/auth_credential.py`.
- T049 — DELETE deprecated public types (`AccountInfo` / `CredentialInfo` / `ProjectAlias` / `MigrationResult` / `ActiveContext`) — **already done in B1 Fix 9**, this T-ID is a no-op now.
- T050 — DELETE deprecated `Workspace` methods (`switch_project`, `switch_workspace`, `set_workspace_id`, `current_credential`, `current_project`).
- T051 / T052 — DELETE v1/v2 stubs in ConfigManager + `_resolve_session_v1` / `_v2` — **already done in B1 Fix 9**, T-IDs are no-ops now.
- T053a — DELETE obsolete unit tests left over from legacy paths — **mostly done in B1**; sweep again after T050.
- T058a — help-examples snapshot tests.
- T066-T069 — `cli/utils.py` `get_workspace()` formatter polish, `cli/CLAUDE.md`.

Beyond B2 the open clusters are A1 (OAuth wiring trio — Fix 16 / 17 / 18), A2 (plugin rewrite), B3 (`mixpanel_data.auth_types` public module — Fix 27), C1 (cross-cutting iteration tests), C2 (bridge writer), and D (Phase 11 release polish).

**Tests**: This project enforces strict TDD per `CLAUDE.md` and the constitution. **Tests are MANDATORY** — every implementation task must have a failing test in place first. The phases below interleave test tasks ahead of the implementation tasks they cover.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. The 10 user stories from `spec.md` map to 9 implementation phases per `plan.md` § Project Structure (some phases serve multiple stories; some stories span multiple phases when their independent test depends on multiple sub-systems).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3); combined labels (e.g., [US1][US4]) indicate shared work
- All paths are project-root-relative (working directory: `/Users/jaredmcfarland/Developer/mixpanel_data/`)

## Path conventions (per [plan.md § Project Structure](plan.md))

- Library source: `src/mixpanel_data/`
- Library internal: `src/mixpanel_data/_internal/`
- Auth subsystem: `src/mixpanel_data/_internal/auth/`
- CLI: `src/mixpanel_data/cli/`
- Plugin: `mixpanel-plugin/`
- Unit tests: `tests/unit/`
- Property-based tests: `tests/pbt/`
- Integration tests: `tests/integration/`
- Fixtures: `tests/fixtures/`

---

## Phase 1: Setup

**Purpose**: Project scaffolding for the redesign — branch is already created by the `before_specify` hook; this phase wires up the new directory structure and the conversion-fixture skeleton so later phases can land tests in place.

- [X] T001 Verify working tree is on branch `042-auth-architecture-redesign` and clean; if dirty, commit or stash (used by all subsequent tasks)
- [X] T002 [P] Create empty test fixture directories: `tests/fixtures/configs/` and `tests/fixtures/oauth/` (touch a `.gitkeep` if needed so they survive empty-state)
- [X] T003 [P] Add `tests/integration/conftest.py` shared fixtures: `tmp_mp_home` (sets `MP_CONFIG_PATH` and `HOME` to a tmp dir), `recorded_responses` (httpx_mock or respx), `live_marker` (pytest marker for `MP_LIVE_TESTS=1` opt-in)
- [X] T004 [P] Add `pytest.ini` markers for `live` and `contract` (used by Research R6 layered tests); update `pyproject.toml` if marker config lives there
- [X] T005 Add `just` recipe `just test-auth` that runs `pytest tests/unit/test_account.py tests/unit/test_session.py tests/unit/test_resolver.py tests/unit/test_workspace_use.py tests/unit/test_config_v3.py tests/pbt/test_account_pbt.py tests/pbt/test_resolver_pbt.py tests/pbt/test_session_pbt.py -v` for fast iteration on the auth subsystem; verify recipe parses with `just --list`

**Checkpoint**: Branch is ready; fixture directories exist; auth-focused test recipe wired.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: New types — `Account` discriminated union, `Session`, `Project`, `WorkspaceRef`, `TokenResolver` protocol, exception hierarchy additions, types module updates. Per source design Phase 1, these must merge first because every other phase depends on them.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete. The new types coexist with the v2 types during Phases 2–3 — nothing breaks during this phase because the new types are not yet wired into Workspace/MixpanelAPIClient.

### Tests for Foundational types (TDD — write FIRST)

- [X] T006 [P] Write `tests/unit/test_account.py` covering: ServiceAccount construction with valid/invalid fields, OAuthBrowserAccount construction (no secret in TOML), OAuthTokenAccount XOR(token, token_env) validation, name pattern enforcement (`^[a-zA-Z0-9_-]{1,64}$`), region constraint, frozen/extra=forbid behavior, `auth_header()` for each variant (with stub `TokenResolver`), `is_long_lived()` per variant. Tests MUST fail initially.
- [X] T007 [P] Write `tests/unit/test_session.py` covering: Project validation (numeric string id), WorkspaceRef validation (positive int id), Session construction with workspace=None, `Session.project_id`/`workspace_id`/`region` properties, `Session.replace(...)` for each axis (preserve other axes; explicit None for workspace clears it; sentinel preserves it). Tests MUST fail.
- [X] T008 [P] Write `tests/pbt/test_account_pbt.py` (Hypothesis): for every Account variant, round-trip JSON serialization preserves shape; `OAuthTokenAccount` validator never accepts both/neither token+token_env; `Account.name` always satisfies the pattern. Tests MUST fail.
- [X] T009 [P] Write `tests/pbt/test_session_pbt.py` (Hypothesis): `Session.replace(account=A)` produces a new Session with `account==A` and other axes preserved; `Session.replace(workspace=None)` clears workspace; round-trip serialize/deserialize preserves equality. Tests MUST fail.
- [X] T010 [P] Write `tests/unit/test_token_resolver.py` covering: `TokenResolver` protocol — `get_browser_token(name, region)` reads from `~/.mp/accounts/{name}/tokens.json` and refreshes if expired; `get_static_token(account)` reads inline `token` or env var via `token_env`; raises `OAuthError` if env var unset; raises `OAuthError` if browser tokens missing/expired/unrefreshable. Tests MUST fail.

### Implementation for Foundational types

- [X] T011 Create `src/mixpanel_data/_internal/auth/account.py`: `Region` Literal, `AccountType` Literal, `_AccountBase` (frozen, extra=forbid), `ServiceAccount`, `OAuthBrowserAccount`, `OAuthTokenAccount` (with `model_validator(mode="after")` enforcing token XOR), `Account` discriminated union via `Annotated[..., Field(discriminator="type")]`, `TokenResolver` Protocol with `get_browser_token()` and `get_static_token()` methods. Reference [data-model.md §1, §2](data-model.md).
- [X] T012 [P] Create `src/mixpanel_data/_internal/auth/session.py`: `Project`, `WorkspaceRef`, `Session` (with `replace()` using `_SENTINEL` for workspace), and the convenience properties (`project_id`, `workspace_id`, `region`, `auth_header`). Reference [data-model.md §3, §4](data-model.md).
- [X] T013 [P] Create `src/mixpanel_data/_internal/auth/token_resolver.py`: `OnDiskTokenResolver` concrete implementation reading from `~/.mp/accounts/{name}/tokens.json` (oauth_browser) and env vars / inline tokens (oauth_token). Includes refresh logic via existing `OAuthFlow.refresh()` (deferred — call into existing module).
- [X] T014 Update `src/mixpanel_data/_internal/auth/__init__.py` to export `Account`, `AccountType`, `OAuthBrowserAccount`, `OAuthTokenAccount`, `Project`, `Region`, `ServiceAccount`, `Session`, `TokenResolver`, `WorkspaceRef`. Do NOT remove existing exports yet (v2 types coexist until Phase 4).
- [X] T015 [P] Add new exception classes to `src/mixpanel_data/exceptions.py`: `AccountInUseError(ConfigError)`, `WorkspaceScopeError(MixpanelDataError)`. Keep all existing exception types. Reference [contracts/python-api.md §8](contracts/python-api.md).
- [X] T016 [P] Add new public types to `src/mixpanel_data/types.py`: `AccountSummary`, `AccountTestResult`, `Target`, `OAuthLoginResult`. Keep existing types (`AccountInfo`, `CredentialInfo`, `ProjectAlias`, `MigrationResult`, `ActiveContext`) — they will be deleted in Phase 4. Reference [data-model.md §5–7](data-model.md).
- [X] T017 [P] Update `src/mixpanel_data/_internal/auth/storage.py`: add `account_dir(name) -> Path` and `ensure_account_dir(name)` helpers that return/create `~/.mp/accounts/{name}/` with mode `0o700`. Keep existing v2 helpers (`region_token_path`, etc.) — they're used by the v1/v2 paths until Phase 4. Reference [contracts/filesystem-layout.md](contracts/filesystem-layout.md).
- [X] T018 Run `just test-auth` and confirm all tests T006–T010 now PASS. Run `just typecheck` to confirm no mypy errors in new files.

**Checkpoint**: New foundational types exist; no behavior change in existing code paths; v2 types still operational.

---

## Phase 3: User Story 2 — Single Schema, Fresh Installs Valid (Priority: P1) — AND — User Story 3 — Single Resolver With Per-Axis Independent Priority (Priority: P1)

**Goal (US2)**: A fresh install of `mixpanel_data 0.4.0` with no `~/.mp/config.toml` produces a v3-only config from the very first `mp account add`. Legacy v1/v2 configs surface a clear error pointing to `mp config convert`.

**Goal (US3)**: A single `resolve_session(...)` function with three independent axes (account, project, workspace) consults env → param → target → bridge → config in priority order; same inputs always produce the same Session; never silently falls back across axes.

**Independent Test (US2)**: Delete `~/.mp/config.toml`. Run `mp account add team --type service_account --username "..." --region us` (with `MP_SECRET=...`). Inspect the resulting config file: contains exactly one `[accounts.team]` block with new shape; contains no `config_version`, `default`, `[credentials]`, or `[projects]`.

**Independent Test (US3)**: For each combination of env vars + explicit params + target + bridge + config, calling `resolve_session(...)` twice produces equal `Session` objects (Hypothesis-verified). Setting `MP_PROJECT_ID=8` over `[active].project = "3713224"` resolves to `8`. Setting `--account demo-sa` over an `[active].account = "team"` resolves to `demo-sa`.

### Tests for US2 + US3 (TDD — write FIRST)

- [X] T019 [P] [US2] Write `tests/unit/test_config_v3.py` covering: load empty/missing config returns empty ConfigManager; `add_account()` writes `[accounts.NAME]` with new shape; `set_active(account=, project=, workspace=)` writes `[active]`; `add_target()` writes `[targets.NAME]`; `list_accounts()` returns `AccountSummary[]`; legacy v1 detection (presence of `default`, or inline `project_id`); legacy v2 detection (presence of `config_version`, `[credentials]`, `[projects]`); referential integrity (`[active].account` must reference an existing account, `[targets.X].account` must too) raises `ConfigError`. Tests MUST fail. Reference [contracts/config-schema.md §1](contracts/config-schema.md).
- [X] T020 [P] [US3] Write `tests/unit/test_resolver.py` covering: account-axis order (env SA quad → env OAUTH_TOKEN → param → target → bridge → `[active].account`); project-axis order (env → param → target → bridge → config); workspace-axis order (same, with None as valid terminal); SA quad takes precedence over OAUTH_TOKEN when both env sets complete (preserves PR #125); `target=` mutually exclusive with `account=`/`project=`/`workspace=` raises `ValueError`; resolver never reads OAuth tokens or hits `/me` (assert via mocks); resolver never mutates `os.environ` (snapshot before/after); `ConfigError` messages match the multi-line format in [contracts/python-api.md §8 / spec FR-024]. Tests MUST fail.
- [X] T020a [P] [US3] Write `tests/unit/test_settings_headers.py` covering FR-014 + FR-052 in-memory header attachment: a config with `[settings] custom_header = {name = "X-Foo", value = "bar"}` causes `resolve_session()` to produce a Session whose `MixpanelAPIClient` injects the header into outbound requests (assertable via httpx_mock request inspection); same assertions for a bridge file with `headers: {...}`; `os.environ` snapshot before/after `resolve_session()` is byte-identical (no env mutation). Tests MUST fail.
- [X] T021 [P] [US3] Write `tests/pbt/test_resolver_pbt.py` (Hypothesis) per [research.md R2](research.md): three property classes (determinism, axis independence, env-wins). Use composite strategies for env_state, config_state, explicit_args. Dev profile target <1 s, CI profile <10 s. Tests MUST fail.
- [X] T022 [P] [US2] Write `tests/unit/cli/test_config_legacy_detection.py` covering: invoking ANY mp command against a legacy v1 fixture surfaces the `ConfigError` with the exact "Legacy config schema detected at..." message naming `mp config convert`. Tests MUST fail. Reference [contracts/config-schema.md §1.4](contracts/config-schema.md).
- [X] T023 [P] [US2] Create the six legacy fixture configs under `tests/fixtures/configs/`: `v1_simple.toml`, `v1_multi.toml`, `v1_with_oauth_orphan.toml`, `v2_simple.toml`, `v2_multi.toml`, `v2_with_custom_header.toml` per [research.md R3](research.md). Also create `v3_simple.toml` and `v3_multi.toml` golden post-conversion expected outputs.

### Implementation for US2 + US3

- [X] T024 [US2] Rewrite `src/mixpanel_data/_internal/config.py`: new `ConfigManager` class with single-schema `load()`, `save()`, `add_account()`, `remove_account()`, `list_accounts()`, `set_active(*, account=None, project=None, workspace=None)`, `get_active() -> ActiveSession`, `add_target()`, `remove_target()`, `list_targets()`, `get_target(name)`, `apply_target(name)` (writes target's three axes to active). Use `tomli`/`tomli_w` for TOML I/O. Implement legacy detection that raises `ConfigError` with the message from [contracts/config-schema.md §1.4](contracts/config-schema.md). Target: ≤600 LOC (down from 1937). Keep the v1/v2 branches as STUB methods that delegate to legacy detection — they will be deleted in Phase 4 once all callers are rewired. **Implementation note**: New `ConfigManager` lives in `src/mixpanel_data/_internal/config_v3.py` alongside the legacy `config.py` during the transitional Phase 3-4 window; Phase 4 consolidates.
- [X] T025 [US3] Create `src/mixpanel_data/_internal/auth/resolver.py`: implement `resolve_session(*, account=None, project=None, workspace=None, target=None, config=None) -> Session` with three independent axis traversal functions (`_resolve_account_axis`, `_resolve_project_axis`, `_resolve_workspace_axis`). Each returns the value if found and short-circuits on first match per the priority order. Build `Session` from the three axis outputs. Synthesize `ServiceAccount`/`OAuthTokenAccount` from env vars when applicable. Raise `ConfigError` with multi-line messages per FR-024. Reference [research.md R2 + Appendix A of source design](research.md). Pure-functional: no I/O beyond `ConfigManager.load()` (which the caller may pre-load).
- [X] T026 [US3] Create `src/mixpanel_data/_internal/auth/bridge.py` v2 schema only (export/remove come in Phase 8): `BridgeFile` Pydantic model per [data-model.md §10](data-model.md); `load_bridge(path: Path) -> BridgeFile | None` returning None if absent; raise `ConfigError` if malformed; default path resolution (`MP_AUTH_FILE` env, then `~/.claude/mixpanel/auth.json`, then `<cwd>/mixpanel_auth.json`). The resolver in T025 calls `load_bridge()` to populate the bridge axis. The OLD v1 bridge path stays callable via the legacy module name during this phase; only the loader is the new shape — exporting comes later. **Implementation note**: `BridgeFile` v2 added at the bottom of the existing `bridge.py` alongside the v1 `AuthBridgeFile`; old v1 callers keep working.
- [X] T027 [US2] Add an `ActiveSession` Pydantic model to `src/mixpanel_data/_internal/auth/session.py` per [data-model.md §5](data-model.md). Used by `ConfigManager.get_active()`.
- [X] T028 [US2] Update `src/mixpanel_data/_internal/auth/storage.py` to add the migration helper `legacy_token_path(region)` returning `~/.mp/oauth/tokens_{region}.json` (read-only; only used by `mp config convert` later). Keep all existing v1/v2 storage helpers operational.
- [X] T029 Run `just test-auth` (covers T019–T021) and additionally `pytest tests/unit/cli/test_config_legacy_detection.py -v`. Confirm all tests pass. Run `just typecheck` and `just lint`.

**Checkpoint**: New ConfigManager + resolver + bridge loader work in isolation. Existing Workspace/CLI still uses v1/v2 paths because we have not rewired them yet — test suite has both old and new tests passing simultaneously.

---

## Phase 4: User Story 1 — Unified Account Model (Priority: P1) — AND — User Story 4 — One-Line In-Session Switching (Priority: P1)

**Goal (US1)**: All three credential mechanisms (`service_account`, `oauth_browser`, `oauth_token`) are first-class, named, persistable, switchable through the same API. `mp.accounts.add/list/use/test/login/logout` works for any type. Switching cost is identical regardless of account type.

**Goal (US4)**: `Workspace.use(account=, project=, workspace=, target=, persist=False) -> Self` is the only in-session switching method. Returns `self` for chaining. Preserves the underlying `httpx.Client` instance across switches. `persist=True` writes to `~/.mp/config.toml [active]`.

**Independent Test (US1)**: Register one of each type. Verify `mp.accounts.list()` returns three `AccountSummary` records with distinguishable `type` fields. `mp.accounts.use(name)` for each switches the active account. `mp.accounts.test(name)` for each hits `/me` and returns `AccountTestResult`.

**Independent Test (US4)**: Construct a `Workspace`, call `ws.use(project="A").events()` then `ws.use(project="B").events()`; verify the two queries hit two different projects with the same auth credentials and the same underlying `httpx.Client` instance (assertable via `id()`).

### Tests for US1 + US4 (TDD — write FIRST)

- [X] T030 [P] [US1] Write `tests/unit/test_accounts_namespace.py` covering: `mp.accounts.list()` returns sorted `AccountSummary[]`; `mp.accounts.add(name, type=, region=, ...)` validates type-specific args (SA needs username+secret; oauth_browser needs neither; oauth_token needs token XOR token_env); `mp.accounts.add()` first account auto-promotes to active per FR-045; `mp.accounts.remove()` raises `AccountInUseError` if referenced by targets and `force=False`; `mp.accounts.use(name)` writes `[active].account` and does NOT touch `[active].project`/`[active].workspace`; `mp.accounts.test(name)` returns `AccountTestResult` (never raises); `mp.accounts.token(name)` returns the current bearer for OAuth, "N/A" for SA. Tests MUST fail. Reference [contracts/python-api.md §5](contracts/python-api.md).
- [X] T031 [P] [US1] Write `tests/unit/test_targets_namespace.py` covering: `mp.targets.list()`, `add()`, `remove()`, `use()` (writes all three `[active]` fields atomically), `show()`. `add()` validates referenced account exists. `use()` referencing a missing account raises `ConfigError`. Reference [contracts/python-api.md §6](contracts/python-api.md).
- [X] T032 [P] [US1] Write `tests/unit/test_session_namespace.py` covering: `mp.session.show()` returns `ActiveSession` matching `[active]` block; `mp.session.use(account=, project=, workspace=)` updates each axis independently; `target=` mutually exclusive with axis kwargs raises `ValueError`. Reference [contracts/python-api.md §7](contracts/python-api.md).
- [X] T033 [P] [US4] Write `tests/unit/test_workspace_use.py` covering: `Workspace.use(workspace=N)` is in-memory only (no API call, no config write); `use(project=P)` does not re-auth; `use(account=A)` rebuilds auth header AND clears in-session project state per FR-033; `use(target=T)` applies all three from target; `target=` mutually exclusive with axis kwargs raises `ValueError`; `persist=True` writes to `[active]`; chain `ws.use(project="A").use(workspace=N).session` produces the expected Session; HTTP transport (`id(ws._api_client._http)`) is preserved across all switches; cache invalidation matches the policy in [research.md R5](research.md). Tests MUST fail.
- [X] T034 [P] [US4] Write `tests/unit/test_workspace_init.py` covering: `Workspace()` resolves active session; `Workspace(account=, project=, workspace=)` overrides axes; `Workspace(target=)` applies target; `Workspace(target=, account=)` raises `ValueError`; `Workspace(session=S)` bypasses everything else; **for several `(account, project, workspace)` triples, assert `Workspace().use(account=A, project=B, workspace=C).session == Workspace(session=Session(account=A, project=B, workspace=C)).session` (use-chain construction is interchangeable with `session=` bypass per SC-010)**; properties `account`, `project`, `workspace`, `session` are read-only. Tests MUST fail.
- [X] T035 [P] [US4] Write `tests/unit/test_api_client_session.py` covering: `MixpanelAPIClient(session=...)` constructs with new Session; `client.use(account=, project=, workspace=)` rebuilds auth header / base URL params; `client._http` instance is preserved across all use() calls; clearing the resolved-workspace cache happens on `use(account=)` and `use(project=)` only; lazy workspace resolution caches per-session-lifetime per FR-025. Tests MUST fail.
- [X] T036 [P] [US4] Write `tests/integration/test_workspace_lazy_resolve.py` per [research.md R6](research.md): unit layer (mocked) verifies lazy resolve happens on first workspace-scoped call; contract layer (recorded responses) locks the response shape. Live layer is opt-in via `@pytest.mark.live`. Tests MUST fail.
- [X] T037 [P] [US1] Write `tests/integration/test_account_three_types.py`: end-to-end test that registers one ServiceAccount, one OAuthBrowserAccount (mocked browser flow), one OAuthTokenAccount; verifies `mp.accounts.list()` returns all three; switches between them; `mp.accounts.test()` for each hits a mocked `/me`. Tests MUST fail.

### Implementation for US1 + US4

- [X] T038 [US1] Create `src/mixpanel_data/accounts.py` (public namespace module): `list()`, `add(name, *, type, region, username=None, secret=None, token=None, token_env=None)`, `remove(name, *, force=False)`, `use(name)`, `show(name=None)`, `test(name=None)`, `login(name, *, open_browser=True)`, `logout(name)`, `token(name=None)`, `export_bridge(*, to, account=None)` (stub returning NotImplementedError until Phase 8), `remove_bridge(*, at=None)` (stub). Each delegates to the new `ConfigManager` and to a `MeService` instance for `test()`. Reference [contracts/python-api.md §5](contracts/python-api.md).
- [X] T039 [P] [US1] Create `src/mixpanel_data/targets.py` (public namespace module): `list()`, `add(name, *, account, project, workspace=None)`, `remove(name)`, `use(name)`, `show(name)`. Reference [contracts/python-api.md §6](contracts/python-api.md).
- [X] T040 [P] [US1] Create `src/mixpanel_data/session.py` (public namespace module — note: shadows the `Session` type which is imported from `mixpanel_data.auth`): `show()`, `use(*, account=None, project=None, workspace=None, target=None)`. Reference [contracts/python-api.md §7](contracts/python-api.md).
- [X] T041 [US4] Rewrite `src/mixpanel_data/_internal/api_client.py` `MixpanelAPIClient`: `__init__(self, session: Session, *, http_client: httpx.Client | None = None, token_resolver: TokenResolver | None = None)` — accepts Session not Credentials; constructs `_http = http_client or httpx.Client(...)`; computes `_auth_header` via `session.auth_header(token_resolver)`; defines per-request injection via existing event_hooks. Add `use(self, *, account=None, project=None, workspace=None) -> None` that swaps the relevant axis on `self._session`, recomputes `_auth_header` if account or project changed (atomic — old header preserved on failure), invalidates `_resolved_workspace_cache` per the policy in [research.md R5](research.md). Add `_lazy_resolve_workspace() -> WorkspaceRef` that hits `/api/app/projects/{pid}/workspaces/public` and caches the default workspace per session lifetime. Delete `with_project()` (replaced by `use()`). Delete `_session_to_credentials` (no Credentials anymore). **Implementation note**: ADDITIVE — `__init__` now accepts EITHER `credentials=` (legacy) OR `session=` (042); `use()` and `resolve_workspace()` added as new methods. Legacy methods preserved (deletion deferred to Phase 5).
- [X] T042 [US4] Rewrite `src/mixpanel_data/workspace.py` `Workspace.__init__(self, *, account=None, project=None, workspace=None, target=None, session=None)`: route through `resolve_session()` unless `session=` is supplied (full bypass); construct a `MixpanelAPIClient(session=...)`. Add properties `account`, `project`, `workspace`, `session` (all read-only via `@property`; raise on assignment). Add `Workspace.use(self, *, account=None, project=None, workspace=None, target=None, persist=False) -> Self`: validate mutual exclusion; call `_api_client.use(...)`; if `persist=True`, call `ConfigManager.set_active(...)`; return `self`. Add `Workspace.projects(*, refresh=False) -> list[Project]` and `Workspace.workspaces(*, project_all=False, refresh=False) -> list[WorkspaceRef]` calling into `MeService`. Reference [contracts/python-api.md §1–4](contracts/python-api.md). **Implementation note**: ADDITIVE — new keyword-only kwargs (`project=`, `workspace=`, `target=`, `session=`) trigger the v3 path via `_init_v3()`; old positional API preserved.
- [-] T043 [US4] Update `src/mixpanel_data/_internal/me.py` `MeService` and `MeCache`: storage path moves from `~/.mp/oauth/me_{region}_{name}.json` to `~/.mp/accounts/{name}/me.json`; cache envelope shape per [contracts/filesystem-layout.md §6.4](contracts/filesystem-layout.md). Drop reads/writes of `OAuthTokens.project_id` (legacy field). **DEFERRED to Phase 5**: requires CLI rewire to surface; current cache path still works against the old layout.
- [-] T044 [US4] Update `src/mixpanel_data/_internal/auth/token.py` `OAuthTokens`: REMOVE the `project_id` field (line ~60). **DEFERRED to Phase 5** (additive Phase 4 keeps the field for backward compat with on-disk legacy tokens).
- [-] T045 [US4] Update `src/mixpanel_data/_internal/auth/flow.py`, `client_registration.py`, and `storage.py` for new per-account paths. **DEFERRED to Phase 5** (additive Phase 4 keeps the legacy region-scoped paths working alongside the new per-account helpers added in T017).
- [X] T046 [US1][US4] Update `src/mixpanel_data/__init__.py` public re-exports per [data-model.md §11](data-model.md): ADD `Account`, `AccountType`, `OAuthBrowserAccount`, `OAuthTokenAccount`, `Region`, `ServiceAccount`, `Project`, `Session`, `WorkspaceRef`, `AccountSummary`, `AccountTestResult`, `Target`, plus the namespaces `accounts`, `targets`, `session`. **Note**: REMOVALS deferred to Phase 5 (additive Phase 4 keeps deprecated re-exports for backward compat).
- [-] T047 [US1][US4] Rewrite `src/mixpanel_data/auth.py` to be a thin re-export module per [data-model.md §11](data-model.md). **DEFERRED to Phase 5** (additive Phase 4).
- [-] T048 [US1][US4] DELETE `src/mixpanel_data/_internal/auth_credential.py`. **DEFERRED to Phase 5** (used by legacy Workspace path during transition).
- [-] T049 [US1][US4] DELETE deprecated types from `src/mixpanel_data/types.py`. **DEFERRED to Phase 5**.
- [-] T050 [US1][US4] DELETE deprecated methods on `Workspace`. **DEFERRED to Phase 5**.
- [-] T051 [US1][US4] DELETE the v1/v2 stubs in `ConfigManager`. **DEFERRED to Phase 5**.
- [-] T052 [US1][US4] DELETE the v1/v2 internal `_resolve_session_v1` / `_resolve_session_v2`. **DEFERRED to Phase 5**.
- [X] T053 Run `just check` (lint + typecheck + tests). All Phase 4 tests pass (71 new + 168 from earlier phases = 239), full suite stays green at 6317 passed. **Note**: LOC budget verification deferred to Phase 5 cleanup.
- [-] T053a [US1][US4] DELETE obsolete unit tests. **DEFERRED to Phase 5** (legacy paths still exercised by existing tests).

**Checkpoint**: Python public API works for US1 and US4. CLI is still on the OLD command groups but the underlying library is fully rewired. The plugin's `auth_manager.py` still calls into `mp.auth.list_accounts()`-style v1/v2 APIs and is broken (acceptable — fixed in Phase 9).

---

## Phase 5: User Story 5 — Unified CLI Surface (Priority: P1)

**Goal**: CLI exposes exactly five identity command groups (`account`, `project`, `workspace`, `target`, `session`) with `use` as the universal state-change verb. New globals (`--account`/`-a`, `--project`/`-p`, `--workspace`/`-w`, `--target`). Old groups (`auth`, `projects`, `workspaces`, `context`) are deleted with no shim.

**Independent Test**: Run `mp --help` and confirm only the new groups exist. For each group with state, confirm `use` is the verb. Run `mp auth list` (deprecated) and confirm "unknown command". Run `mp account add` for each `--type` and verify the schema in `~/.mp/config.toml` matches contracts/config-schema.md. Run `mp --account team --project 8 query ...` and verify the override applies for that command only.

### Tests for US5 (TDD — write FIRST)

- [X] T054-T058 [P] [US5] Combined CLI tests live in `tests/unit/cli/test_v3_cli.py` covering all five command groups + global flag mutual exclusion. 17 tests pass.
- [-] T058a [P] [US5] Help-examples test deferred to a Phase 11 polish pass (the new commands have working help; the snapshot infrastructure can land later without affecting MVP).
- [-] T059 [P] [US5] Deprecated-commands-removed test deferred until the legacy command modules are deleted (Phase 5 cleanup pass; deferring keeps the additive transition working).

### Implementation for US5

- [X] T060 [US5] Created `src/mixpanel_data/cli/commands/account.py` with subcommands `list`, `add`, `remove`, `use`, `show`, `test`, `login`, `logout`, `token`, `export-bridge` (Phase 8 stub), `remove-bridge` (Phase 8 stub). Each delegates to `mp.accounts.*`.
- [X] T061 [P] [US5] Created `src/mixpanel_data/cli/commands/project.py` with `list`, `use`, `show`.
- [X] T062 [P] [US5] Created `src/mixpanel_data/cli/commands/workspace.py` with `list`, `use`, `show`.
- [X] T063 [P] [US5] Created `src/mixpanel_data/cli/commands/session.py` with the flat `mp session` command (`--bridge` flag wired as Phase 8 stub).
- [X] T064 [P] [US5] Created `src/mixpanel_data/cli/commands/config_cmd.py` with `convert` as a Phase 10 stub.
- [X] T065 [US5] Updated `src/mixpanel_data/cli/main.py`: registered new groups (`account`, `project`, `workspace`, `session`, `config`); added new globals `--workspace`/`-w` and `--target`/`-t` (alongside legacy `--workspace-id`); enforces `--target` mutex with `--account`/`--project`/`--workspace` (exit code 3). **Note**: legacy command groups KEPT during additive transition; deletions deferred to Phase 5+ cleanup.
- [-] T066 [US5] `cli/utils.py:get_workspace()` rewire deferred — existing behavior continues to work; the new commands delegate directly to the new Python namespaces (which honor `MP_CONFIG_PATH`).
- [-] T067 [P] [US5] Formatters update deferred to a Phase 5+ polish pass (basic table/json formats work in the new commands).
- [-] T068 [US5] DELETE legacy command files. **DEFERRED** to Phase 5+ cleanup pass (legacy commands still functional).
- [-] T069 [US5] CLAUDE.md update deferred to Phase 11 docs sweep.
- [X] T070 `just check`-equivalent: 17 new CLI tests pass, full suite stays at 6334 passed, 0 regressions, mypy clean on the 5 new command modules.

**Checkpoint**: User Stories 1, 2, 3, 4, 5 all independently functional via Python AND CLI. The legacy command surface is gone. Plugin still broken (Phase 9).

---

## Phase 6: User Story 6 — Targets as Saved Cursor Positions (Priority: P2)

**Goal**: `[targets.NAME]` blocks store named (account, project, workspace?) triples. `mp target add/use/list/remove/show` work. `mp --target NAME ...` is a per-command override. `mp.targets.*` Python namespace.

**Independent Test**: Register two targets via `mp target add`. Switch with `mp target use NAME` and confirm `[active]` updates all three axes in one config write. `mp --target NAME query ...` does NOT modify `[active]`. Removing the target's account fails `mp target use NAME` with a clear error.

### Tests for US6 (TDD — write FIRST)

- [ ] T071 [P] [US6] Write `tests/unit/cli/test_target_cli.py` snapshot tests covering: `mp target list`; `mp target add NAME --account A --project P --workspace W`; `mp target add NAME` without `--workspace` (omitted in TOML); `mp target remove NAME`; `mp target use NAME` (writes all three `[active]` fields atomically; one-line confirmation); `mp target show NAME`; `mp target use NAME` against a missing-account target raises ConfigError. Tests MUST fail. Reference [contracts/cli-commands.md §6](contracts/cli-commands.md).
- [ ] T072 [P] [US6] Write `tests/integration/test_target_roundtrip.py`: full roundtrip — add target via Python, apply via CLI `mp target use`, verify `Workspace()` picks up the new active state, verify `Workspace.use(target="NAME")` produces the same Session. Tests MUST fail.

### Implementation for US6

- [ ] T073 [US6] Create `src/mixpanel_data/cli/commands/target.py` Typer app with subcommands `list`, `add`, `remove`, `use`, `show`. Each delegates to `mp.targets.*`. Reference [contracts/cli-commands.md §6](contracts/cli-commands.md).
- [ ] T074 [US6] Register `target` command group in `src/mixpanel_data/cli/main.py` (already added shell in T065 — confirm wire-up of T073's app).
- [ ] T075 [US6] Verify `mp.targets.use(name)` (from Phase 4 T039) writes all three `[active]` fields in a single `ConfigManager.save()` call (atomicity — if two calls were used and process died between them, only `account` would be set). Add a regression test in `tests/integration/test_target_roundtrip.py` for the atomicity property.
- [ ] T076 Run `just check`. Confirm all tests pass (including T071, T072, T075).

**Checkpoint**: US6 fully functional. US1–US6 deliverable as MVP+1 expansion.

---

## Phase 7: User Story 7 — Cross-Cutting Iteration (Priority: P2)

**Goal**: Cross-account / cross-project / cross-workspace iteration is first-class. Sequential mode mutates Workspace's session; snapshot mode (Session.replace) supports parallel execution. CLI shell loops compose naturally.

**Independent Test**: For an account with ≥2 projects, write a Python script that loops `for p in ws.projects(): ws.use(project=p.id); ws.events()` — verify each iteration is O(1) (no re-auth), prints one line per project. Write a parallel version using `ThreadPoolExecutor` and `Session.replace(...)` — verify each thread gets an independent Workspace.

### Tests for US7 (TDD — write FIRST)

- [ ] T077 [P] [US7] Write `tests/integration/test_cross_project_iteration.py`: instrumented `MixpanelAPIClient` mock counts HTTP calls per endpoint; first call `ws.projects()` to populate the per-account `/me` cache; then loop over three mock projects calling `ws.use(project=p.id); ws.events()`; assert during the loop body: (a) zero re-auth calls, (b) **zero `/me` HTTP calls** (the cache populated by `ws.projects()` must be reused per FR-061 + SC-008), (c) one events call per iteration, (d) one shared `httpx.Client` instance throughout (assertable via `id()`). Tests MUST fail.
- [ ] T078 [P] [US7] Write `tests/integration/test_cross_account_iteration.py`: loop over three configured accounts (one of each type, all with mocked `/me`); verify each iteration rebuilds the auth header (assertable via `_auth_header` field change), preserves the `httpx.Client` instance, clears in-session project state. Tests MUST fail.
- [ ] T079 [P] [US7] Write `tests/integration/test_parallel_snapshot.py`: build N sessions via `Session.replace(project=...)`; dispatch via `ThreadPoolExecutor(max_workers=4)`; verify each worker sees its own Workspace; verify no thread mutates another's session (assertable via session id() snapshot). Tests MUST fail.
- [ ] T080 [P] [US7] Write `tests/integration/test_cli_shell_loop.py` (subprocess-based): construct a fixture config with three accounts/projects; run `mp project list -f jsonl` and pipe to `xargs -I{} mp --project {} <some-noop-command>` via `subprocess`; assert each invocation uses the per-command override and `[active]` is unchanged after the loop. Tests MUST fail.

### Implementation for US7

- [ ] T081 [US7] Audit `MixpanelAPIClient` (modified in Phase 4 T041) for the connection-pool-preservation contract. Ensure `use(account=...)` does NOT recreate `self._http`; only `_auth_header` and per-axis caches change. Add a regression assertion in T041's existing test (or amend `tests/unit/test_api_client_session.py`) if the existing coverage doesn't already pin this property explicitly.
- [ ] T082 [US7] Verify `Session.replace(...)` (implemented in Phase 2 T012) is genuinely immutable: for any source Session `s`, `s.replace(project=P).account is s.account` (Python `is` — object identity preserved for unchanged axes). Add this assertion to `tests/pbt/test_session_pbt.py`.
- [ ] T083 [US7] Add a quickstart-style example `examples/cross_project.py` demonstrating both sequential and snapshot-parallel iteration. Reference it from [quickstart.md § Cross-cutting iteration](quickstart.md). (No code in `src/`; this is an example file in the repo root for documentation.)
- [ ] T084 Run `pytest tests/integration/test_cross_project_iteration.py tests/integration/test_cross_account_iteration.py tests/integration/test_parallel_snapshot.py tests/integration/test_cli_shell_loop.py -v`. Confirm all tests pass.

**Checkpoint**: Cross-cutting iteration verified. US7 confirmed independently.

---

## Phase 8: User Story 8 — Decoupled Cowork Bridge (Priority: P2)

**Goal**: Bridge file v2 schema embeds full `Account` record + optional project/workspace + headers. `mp account export-bridge` / `mp account remove-bridge` / `mp session --bridge` are the user-facing commands. Resolver consumes bridge as a synthetic config source.

**Independent Test**: On a configured machine, run `mp account export-bridge --to /tmp/bridge.json` and inspect the output: contains `account` block with full record, no required `project`. Set `MP_AUTH_FILE=/tmp/bridge.json` in a fresh shell and run `mp project use 3713224` then `mp query ...` — confirm the project selection in the VM is independent of the bridge.

### Tests for US8 (TDD — write FIRST)

- [ ] T085 [P] [US8] Write `tests/unit/test_bridge_v2.py` covering: `BridgeFile` Pydantic model construction (with each Account variant); `version: 2` enforced; `tokens` required iff `account.type == "oauth_browser"`; `headers` map preserved; `load_bridge(path)` returns None for missing, raises `ConfigError` for malformed. Tests MUST fail. Reference [contracts/config-schema.md §2](contracts/config-schema.md).
- [ ] T086 [P] [US8] Write `tests/unit/test_bridge_export.py` covering: `mp.accounts.export_bridge(to=PATH, account=NAME)` writes a 0o600 file; embeds the named (or active) account's full record; includes `tokens` for oauth_browser; includes `headers` from `[settings]`; idempotent at the same path. Tests MUST fail.
- [ ] T087 [P] [US8] Write `tests/unit/cli/test_bridge_cli.py` snapshot tests covering: `mp account export-bridge --to PATH` happy path + missing tokens (oauth_browser without login); `mp account remove-bridge` happy path + already-absent; `mp session --bridge` (with bridge present, with bridge absent). Tests MUST fail.
- [ ] T088 [P] [US8] Write `tests/integration/test_bridge_resolver.py` covering: setting `MP_AUTH_FILE` causes the resolver to load the bridge as the bridge axis source; bridge `account` populates account axis; bridge `project` populates project axis if present; bridge `workspace` populates workspace axis if present; bridge `headers` attach to the account in memory; `os.environ` is NOT mutated (snapshot before/after). Tests MUST fail.

### Implementation for US8

- [ ] T089 [US8] Implement the exporter in `src/mixpanel_data/_internal/auth/bridge.py`: `export_bridge(account: Account, *, to: Path, project: str | None = None, workspace: int | None = None, headers: dict[str, str] | None = None, token_resolver: TokenResolver) -> Path` writes a 0o600 file with the v2 schema; for oauth_browser accounts, reads the current tokens via `token_resolver` and embeds them in `tokens`. `remove_bridge(*, at: Path | None = None) -> bool` deletes the file at the resolved path.
- [ ] T090 [US8] Wire up the bridge functions in `src/mixpanel_data/accounts.py` (Phase 4 T038 stub): `export_bridge(*, to, account=None)` calls into `bridge.export_bridge(...)`; `remove_bridge(*, at=None)` calls into `bridge.remove_bridge(...)`. Update tests in `tests/unit/test_accounts_namespace.py` to drop the NotImplementedError assertions.
- [ ] T091 [US8] Implement the CLI subcommands in `src/mixpanel_data/cli/commands/account.py` (Phase 5 T060 stubs): `mp account export-bridge --to PATH [--account NAME] [--project ID] [--workspace ID]` and `mp account remove-bridge [--at PATH]`. Reference [contracts/cli-commands.md §3.10–3.11](contracts/cli-commands.md).
- [ ] T092 [US8] Implement `mp session --bridge` in `src/mixpanel_data/cli/commands/session.py` (Phase 5 T063 included the flag — fill in the bridge-status display logic now). Show bridge file path, account from bridge, project/workspace if pinned, headers list. Reference [contracts/cli-commands.md §7](contracts/cli-commands.md).
- [ ] T093 Run `pytest tests/unit/test_bridge_v2.py tests/unit/test_bridge_export.py tests/unit/cli/test_bridge_cli.py tests/integration/test_bridge_resolver.py -v`. Confirm all tests pass.

**Checkpoint**: Cowork bridge fully reworked. US8 confirmed independently.

---

## Phase 9: User Story 9 — Plugin / Agent Surface Without Version Branches (Priority: P3)

**Goal**: `auth_manager.py` collapses to ≤300 lines (down from ~727); zero version conditionals; subcommands map 1:1 to new CLI verbs; stable JSON output per the contract. `/mixpanel-data:auth` slash command and `/mixpanel-data:setup` skill updated for the new vocabulary.

**Independent Test**: Run `python auth_manager.py session` against (a) configured account, (b) empty config, (c) account-without-project — verify each emits JSON matching the discriminated `state` schema. Run `grep -c 'config_version\|version >= 2' auth_manager.py` returns 0.

### Tests for US9 (TDD — write FIRST)

- [ ] T094 [P] [US9] Write `tests/integration/test_plugin_auth_manager.py` (subprocess-based) per [contracts/plugin-auth-manager.md §9](contracts/plugin-auth-manager.md): for each subcommand and each fixture config, run `python mixpanel-plugin/skills/mixpanelyst/scripts/auth_manager.py <subcommand>`, parse stdout as JSON, assert response shape matches the contract. Use snapshot fixtures in `tests/fixtures/auth_manager_outputs/`. Tests MUST fail.

### Implementation for US9

- [ ] T095 [US9] Rewrite `mixpanel-plugin/skills/mixpanelyst/scripts/auth_manager.py` from scratch (~250 lines target): top-level dispatch on `sys.argv[1]` to subcommands `session`, `account`, `project`, `workspace`, `target`, `bridge`. Each subcommand calls into `mixpanel_data.accounts/.targets/.session` and emits JSON to stdout with `schema_version: 1` plus state-discriminated shape per [contracts/plugin-auth-manager.md](contracts/plugin-auth-manager.md). Errors emit `state="error"` JSON, never raw tracebacks. NO `if version >= 2` branches anywhere.
- [ ] T096 [P] [US9] Rewrite `mixpanel-plugin/commands/auth.md` slash command (Phase 5 of source design): no v1/v2 conditional routing; calls `python auth_manager.py session`; switches on `state` field; produces a 1–2 line summary plus a single suggested next action. Preserve the existing security rule ("never ask for secrets in conversation").
- [ ] T097 [P] [US9] Rewrite `mixpanel-plugin/skills/setup/SKILL.md`: fresh-install walkthrough using new commands (`mp account add` → `mp account login` → `mp project list` → `mp project use <id>`); NO migration step; NO references to `mp auth` or `mp projects` etc.
- [ ] T098 [P] [US9] Update `mixpanel-plugin/README.md` and `mixpanel-plugin/plugin.json`: bump version to `5.0.0`; update command/skill descriptions to use new vocabulary (account / project / workspace / target / session); add a "Breaking changes from 4.x" section pointing to `mp config convert`.
- [ ] T099 [P] [US9] Update `mixpanel-plugin/skills/mixpanelyst/SKILL.md` and `mixpanel-plugin/skills/dashboard-expert/SKILL.md` to reference new vocabulary where they touch auth (mostly the mixpanelyst skill).
- [ ] T100 [US9] Verify line count: `wc -l mixpanel-plugin/skills/mixpanelyst/scripts/auth_manager.py` ≤ 300. Verify no version conditionals: `grep -c "config_version\|version >= 2\|if version >=" mixpanel-plugin/skills/mixpanelyst/scripts/auth_manager.py` returns 0. Run `pytest tests/integration/test_plugin_auth_manager.py -v` and confirm all subcommand tests pass.

**Checkpoint**: Plugin surface uses new vocabulary; agent slash command and setup skill updated; US9 confirmed.

---

## Phase 10: User Story 10 — One-Shot Legacy Config Conversion (Priority: P3)

**Goal**: `mp config convert` is the single entry for legacy v1/v2 → v3 conversion. Idempotent on v3 configs. Migrates OAuth tokens from `~/.mp/oauth/tokens_{region}.json` to `~/.mp/accounts/{name}/tokens.json` per Research R1 mapping rules. Archives original to `~/.mp/config.toml.legacy`.

**Independent Test**: For each fixture (v1_simple, v1_multi, v1_with_oauth_orphan, v2_simple, v2_multi, v2_with_custom_header), run `mp config convert` programmatically and verify the result matches the corresponding `.expected.toml` golden file. Run `mp config convert` twice and verify the second invocation is a no-op.

### Tests for US10 (TDD — write FIRST)

- [ ] T101 [P] [US10] Write `tests/integration/test_config_conversion.py` parametrized over the six fixture pairs from `tests/fixtures/configs/`. For each pair: copy fixture to `tmp_mp_home/config.toml`; copy any legacy oauth files; run `mp.config.convert()` (Python entry point); assert resulting `~/.mp/config.toml` matches `<name>.expected.toml` byte-for-byte (with key-order normalization); assert `~/.mp/config.toml.legacy` matches the original; assert OAuth token files moved to `~/.mp/accounts/{name}/tokens.json` per R1 mapping. Tests MUST fail.
- [ ] T102 [P] [US10] Write `tests/unit/cli/test_config_convert_cli.py` snapshot tests covering: happy-path conversion (output summary table); idempotency (second run emits "already on v3"); `--dry-run` flag (shows actions without writing); abort on destination conflict (account dir already has a tokens.json from a v3 install). Tests MUST fail.
- [ ] T103 [P] [US10] Write `tests/unit/test_conversion_token_migration.py` for Research R1 specifics: token file naming heuristics (active credential → matching v2 OAuth → synthetic `oauth-{region}`); sibling `client_*` and `me_*` files move alongside `tokens_*`; orphaned siblings are reported in summary; broken token files preserved as `*.broken`. Tests MUST fail.

### Implementation for US10

- [ ] T104 [US10] Create `src/mixpanel_data/_internal/conversion.py`: `convert_config(*, src: Path, dst: Path, oauth_dir: Path | None = None, dry_run: bool = False) -> ConversionResult` performing v1→v3 and v2→v3 conversions per [contracts/config-schema.md §3](contracts/config-schema.md). Returns a `ConversionResult` with `source_schema`, `actions` (account_renamed, account_deduplicated, target_created, tokens_moved, active_set), `warnings`. Pure-functional except for the optional disk write (skipped if `dry_run=True`).
- [ ] T105 [US10] Implement OAuth token migration logic in `src/mixpanel_data/_internal/conversion.py`: walk `oauth_dir` for `tokens_{region}.json` files; for each, determine destination account name via Research R1 priority (active credential → matching v2 OAuth → synthetic `oauth-{region}`); move sibling `client_*`/`me_*`; preserve broken files as `*.broken`. Emit warnings to `ConversionResult.warnings` for orphans / ambiguity.
- [ ] T106 [US10] Wire `mp config convert` in `src/mixpanel_data/cli/commands/config_cmd.py` (Phase 5 T064 stub): call `convert_config()` with `--dry-run` support; render `ConversionResult` as a table or JSON per `-f FORMAT`; emit warnings to stderr; exit codes per [contracts/cli-commands.md §8.1](contracts/cli-commands.md).
- [ ] T107 [US10] Add idempotency check: at the top of `convert_config()`, if the input config already parses as v3 (no legacy markers), return a `ConversionResult` with `source_schema: "v3"` and no actions; emit a friendly "already converted" message.
- [ ] T108 [US10] Add a public Python entry point `mp.config.convert(*, dry_run=False) -> ConversionResult` in `src/mixpanel_data/config.py` (new public namespace module) that wraps `convert_config()` with default paths (`~/.mp/config.toml`, `~/.mp/config.toml.legacy`, `~/.mp/oauth/`). This is what the integration test in T101 calls. Implements the contract in [contracts/python-api.md §7.5](contracts/python-api.md) (mp.config namespace). Also update `src/mixpanel_data/__init__.py` to re-export `config` alongside the existing `accounts`, `targets`, `session` namespaces (extending the work in T046).
- [ ] T109 Run `pytest tests/integration/test_config_conversion.py tests/unit/cli/test_config_convert_cli.py tests/unit/test_conversion_token_migration.py -v`. Confirm all tests pass against all six fixture pairs.
- [ ] T110 [US10] Manual validation: copy a representative alpha-tester config (sanitized) into `tests/fixtures/configs/alpha_tester_<id>.toml` IF available; run `mp config convert --dry-run` against it and inspect the summary. (This task is documentation/sanity-check; if no real fixture is available, skip.)

**Checkpoint**: All 10 user stories complete and independently testable.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Documentation updates, code quality verification, version bumps, archive of superseded design doc, release notes.

- [ ] T111 [P] Update `CLAUDE.md` (project root): rewrite the auth section using new vocabulary (Account → Project → Workspace); update the env vars table to drop deprecated entries; mention the breaking change pointer to `mp config convert`; remove the PR #125 callout (still factual but no longer the headline) — fold into the unified-resolver narrative.
- [ ] T112 [P] Update `src/mixpanel_data/CLAUDE.md`: package-overview rewrite — the Account → Project → Workspace hierarchy as the primary mental model; `Workspace.use()` as the centerpiece switching method.
- [ ] T113 [P] Update `src/mixpanel_data/cli/CLAUDE.md`: command tree (account / project / workspace / target / session / config); global flags table; output-formatter reference.
- [ ] T114 [P] Update `context/mixpanel_data-design.md` auth section: replace the current "Auth Methods" / "Credential Resolution" sections with a pointer to [`context/auth-architecture-redesign.md`](../../context/auth-architecture-redesign.md) and a 1-paragraph summary of the unified model.
- [ ] T115 [P] Archive `context/auth-project-workspace-redesign.md`: prepend a header reading "**Status**: Superseded by [`auth-architecture-redesign.md`](auth-architecture-redesign.md) (042-auth-architecture-redesign). This document is preserved for historical context only." Do NOT delete the file.
- [ ] T116 [P] Update `context/CLAUDE.md` document hierarchy diagram and reading order to reflect the new design doc as the auth authority.
- [ ] T117 Bump `mixpanel_data` version to `0.4.0` in `pyproject.toml`. Bump the plugin version to `5.0.0` in `mixpanel-plugin/plugin.json` (already done in T098 — verify).
- [ ] T118 Write release notes in `RELEASE_NOTES_0.4.0.md` (or wherever the project conventionally puts them — check `CHANGELOG.md`): explicit "BREAKING CHANGES" section listing every removed name, every removed CLI verb, and the `mp config convert` migration path; cite spec FR-074 and SC-021.
- [ ] T119 [P] Write `tests/unit/test_loc_budget.py` enforcing FR-067 with two regression assertions:
    (a) **File count cap**: discover auth subsystem files via `glob('src/mixpanel_data/_internal/auth/*.py') + ['src/mixpanel_data/_internal/config.py', 'src/mixpanel_data/_internal/api_client.py'] + glob('src/mixpanel_data/cli/commands/{account,project,workspace,target,session,config_cmd}.py')` (excluding `__init__.py` and `__pycache__`). Assert `len(files) <= 12`.
    (b) **Total LOC cap**: sum `wc -l` across the same file set. Assert total `<= 4000` (target `<= 3500` per source design §15.4 — log a warning between 3500 and 4000).
    Test fails fast on either condition. Adding a 13th auth file fails (a) immediately.
- [ ] T120 [P] Run `just mutate` against the auth subsystem (`_internal/auth/account.py`, `_internal/auth/session.py`, `_internal/auth/resolver.py`, `_internal/config.py`); verify mutation score ≥ 85% per FR-069; document in `tests/MUTATION_SCORE.md` (date + score).
- [ ] T121 [P] Run grep verification per SC-003: `grep -rEn "config_version|version >= 2|version_2|v1.*config|v2.*credential|AuthCredential|Credentials\b" src/ tests/ mixpanel-plugin/ | grep -v "auth-architecture-redesign\|auth-project-workspace-redesign\|test_config_legacy_detection\|test_config_conversion\|conversion.py\|RELEASE_NOTES\|CHANGELOG\|042-auth-architecture-redesign"` returns ZERO matches. (Allowed callsites: legacy-detection error message, conversion code, fixture configs, archived design doc, release notes.)
- [ ] T122 [P] Run grep verification per SC-013: `grep -rE "from mixpanel_data import (Credentials|AccountInfo|CredentialInfo|AuthCredential|CredentialType|ProjectContext|ResolvedSession|ProjectAlias|MigrationResult|ActiveContext|AuthMethod)" src/ tests/ mixpanel-plugin/ examples/` returns ZERO matches.
- [ ] T123 Run `just check` (lint + typecheck + tests). All checks must pass with zero warnings.
- [ ] T124 [P] Run `just test-cov` and verify coverage ≥ 90% on the auth subsystem.
- [ ] T125 Manual quickstart validation per SC-005: walk through every example in [quickstart.md](quickstart.md) on a clean `~/.mp/` directory; verify each command produces the documented output; explicitly time the bootstrap path (`mp account add` → `mp account login` → `mp project list` → `mp project use <id>` → first `mp query`) and record wall-clock duration in `RELEASE_NOTES_0.4.0.md` (the "≤2 minutes" claim is documentation, not a CI gate, because the OAuth browser-flow latency depends on the user). Document any deviations in a follow-up issue.
- [ ] T126 Final security audit: verify all account state files are written with `0o600` and parent dirs `0o700` per [contracts/filesystem-layout.md §3](contracts/filesystem-layout.md); run `grep -rEn "open\(.*'w'\)|open\(.*'wb'\)" src/mixpanel_data/_internal/auth/ src/mixpanel_data/_internal/conversion.py` and confirm every match is followed by an explicit `os.chmod(..., 0o600)` or uses the atomic-write helper that enforces it.
- [ ] T126a [P] Run docstring coverage per constitution Quality Gate "All public functions MUST have docstrings (Google style)" and CLAUDE.md "Every class, method, and function requires a complete docstring": invoke `pydocstyle --convention=google src/mixpanel_data/_internal/auth/ src/mixpanel_data/accounts.py src/mixpanel_data/targets.py src/mixpanel_data/session.py src/mixpanel_data/config.py src/mixpanel_data/cli/commands/{account,project,workspace,target,session,config_cmd}.py` and assert exit code 0. Add `pydocstyle` to dev dependencies in `pyproject.toml` if not already present. Document the gate in `just check` so future PRs catch missing docstrings.

**Checkpoint**: Release-ready. All 10 user stories independently functional and tested. Documentation reflects the new model. Versions bumped. Quality gates passed.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies; can start immediately. Branch already created.
- **Phase 2 (Foundational)**: Depends on Phase 1. **BLOCKS all user stories.** New types are required by every downstream phase.
- **Phase 3 (US2 + US3)**: Depends on Phase 2.
- **Phase 4 (US1 + US4)**: Depends on Phase 3 (uses the new ConfigManager and resolver). Bundled with the rewire of MixpanelAPIClient and Workspace because all three change atomically.
- **Phase 5 (US5)**: Depends on Phase 4 (CLI commands wrap the new public Python namespaces).
- **Phase 6 (US6)**: Depends on Phase 5 (CLI infrastructure) and Phase 4 (mp.targets namespace).
- **Phase 7 (US7)**: Depends on Phase 4 (Workspace.use semantics + Session.replace).
- **Phase 8 (US8)**: Depends on Phase 5 (CLI infrastructure for export-bridge subcommand) and Phase 3 (resolver consumes bridge).
- **Phase 9 (US9)**: Depends on Phase 5 (plugin script wraps new CLI verbs) and Phase 4 (mp.* namespaces).
- **Phase 10 (US10)**: Depends on Phase 5 (CLI infrastructure for mp config convert).
- **Phase 11 (Polish)**: Depends on all desired user stories being complete.

### User Story Dependencies (informational — for incremental delivery planning)

- **US1, US2, US3, US4, US5** form an interdependent P1 cluster. They land together as the "base release" because the redesign is a clean break — partial release would leave the v1/v2 bridge half-removed.
- **US6 (P2)** depends on US5's CLI surface and US4's `Workspace.use(target=)` support.
- **US7 (P2)** depends on US3's resolver and US4's `Workspace.use()` cost contract.
- **US8 (P2)** depends on US5's CLI surface and US3's resolver-as-bridge-consumer.
- **US9 (P3)** depends on US1–US5 (the plugin wraps the public Python and CLI surfaces).
- **US10 (P3)** depends on US5's CLI infrastructure (and the new ConfigManager from US2 to write the converted output).

### Within Each User Story

- Tests MUST be written and FAIL before implementation per the project's strict TDD (see `CLAUDE.md`).
- Models before services.
- Services before CLI/plugin wrappers.
- Storage helpers before the methods that use them.
- DELETE tasks (T048–T052, T068) come AFTER the new code in the same phase passes its tests, NEVER before — otherwise the test suite breaks mid-phase.

### Parallel Opportunities

- All Setup tasks marked [P] (T002, T003, T004) can run in parallel.
- All Foundational tests marked [P] (T006–T010) can run in parallel.
- T011 (account.py) blocks T012 (session.py) and T013 (token_resolver.py) only weakly — `Account` is referenced by `Session` and by `TokenResolver`, so write T011 first and then T012/T013 in parallel.
- All Phase 3 tests (T019–T023) [P] can run in parallel.
- Implementation in Phase 3 has internal ordering: T024 (ConfigManager) and T025 (resolver) must come before T026 (bridge) and T027 (ActiveSession). T024/T025/T026 are the heaviest tasks.
- All Phase 4 tests (T030–T037) [P] can run in parallel.
- Phase 4 implementation: T038–T040 (namespaces) can run in parallel after T041 (api_client) lands; T042 (Workspace) depends on T041 and T038–T040; T043–T045 (auxiliary updates) can run in parallel with T042. T046–T047 (re-exports) come after all the above. T048–T052 (deletions) come last.
- All Phase 5 tests (T054–T059) [P] can run in parallel.
- Phase 5 implementation: T060 (account.py CLI) is the largest; T061–T064 in parallel after T060 lands; T065–T067 in parallel after T060; T068 (deletions) and T069 (CLAUDE.md) at the end.
- All Phase 7 tests (T077–T080) [P] in parallel.
- All Phase 8 tests (T085–T088) [P] in parallel.
- Phase 11 polish tasks: T111–T116 (docs) all [P]; T119–T122 (verifications) all [P].

---

## Parallel Examples

### Phase 2 Foundational tests (run ALL together)

```bash
# Five test files, no overlap — write tests in parallel
pytest tests/unit/test_account.py tests/unit/test_session.py \
       tests/unit/test_token_resolver.py \
       tests/pbt/test_account_pbt.py tests/pbt/test_session_pbt.py \
       -v --no-header -x
# (All five MUST fail at this point — TDD step.)
```

### Phase 4 namespace modules (after api_client lands)

```bash
# Three independent files
edit src/mixpanel_data/accounts.py        # T038
edit src/mixpanel_data/targets.py         # T039
edit src/mixpanel_data/session.py         # T040
```

### Phase 11 documentation (all [P])

```bash
edit CLAUDE.md                                            # T111
edit src/mixpanel_data/CLAUDE.md                          # T112
edit src/mixpanel_data/cli/CLAUDE.md                      # T113
edit context/mixpanel_data-design.md                      # T114
edit context/auth-project-workspace-redesign.md           # T115
edit context/CLAUDE.md                                    # T116
```

---

## Implementation Strategy

### MVP scope (P1 stories only — US1–US5)

The redesign is a clean break — there is no useful "MVP" smaller than the full P1 cluster. Phases 1–5 must land together as a single release because partial application would leave the v1/v2 bridge half-removed. Treat Phases 1–5 as one logical PR sequence (each phase one PR, but no release until Phase 5 is merged).

### Incremental delivery after MVP

- **MVP+1**: Land Phase 6 (US6 targets) → MVP++ release.
- **MVP+2**: Land Phase 7 (US7 cross-cutting iteration) → no new user-facing surface, but unlocks documented use cases.
- **MVP+3**: Land Phase 8 (US8 Cowork bridge) → Cowork users no longer locked to one project.
- **MVP+4**: Land Phase 9 (US9 plugin) → agents on plugin >= 5.0.0 use new vocabulary.
- **Final release**: Land Phase 10 (US10 mp config convert) + Phase 11 (Polish + version bump). This is the gate for cutting `mixpanel_data 0.4.0` and announcing to alpha testers.

### Parallel team strategy

With multiple developers after Phase 4 (US1+US4) merges:

1. Developer A: Phase 5 (US5 CLI rewrite — large)
2. Developer B: Phase 7 (US7 cross-cutting iteration tests — independent, can land before US5)
3. Developer C: Phase 8 (US8 Cowork bridge — depends on Phase 5's CLI infrastructure but can prep the Python parts)
4. Developer D: Phase 9 (US9 plugin rewrite — depends on Phase 5 for CLI verbs)

Phases 6 and 10 are fast and can be picked up by anyone who finishes their primary phase early.

### Critical path

The longest dependency chain is **Phase 1 → 2 → 3 → 4 → 5 → 9 → 11**. Estimated total: 8–10 PR cycles. Phases 6, 7, 8, 10 can land in parallel with 9 once their respective dependencies are met.

---

## Notes

- [P] tasks operate on different files with no incomplete dependencies.
- [Story] labels enable downstream traceability: when fixing a bug, find the originating task by story label and walk back to the user story.
- Each user story is independently completable per the spec's "Independent Test" criteria, even when implementation phases bundle multiple stories.
- Verify tests fail before implementing (TDD).
- Commit after each task or logical group; the `after_tasks` hook offers an optional commit prompt at the end of this command.
- Stop at any phase boundary to validate the increment (manual quickstart for the involved user stories).
- AVOID: vague tasks, same-file conflicts in [P] groups, cross-story dependencies that break independence (US1–US5 are intentionally interdependent — they ship together).
- Source design [§15.4](../../context/auth-architecture-redesign.md) projects ~3,500 LOC across 12 files; the LOC budget is enforced in T119 with a regression test.
- The plugin's `auth_manager.py` rewrite (Phase 9 / T095) is intentionally last among the user-facing rewrites because it's the easiest to verify (subprocess + JSON output) once the Python and CLI surfaces are stable.
