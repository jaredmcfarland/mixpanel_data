# Session Handoff: 042 Auth Architecture Redesign

**Branch:** `042-auth-architecture-redesign` · **Last commit:** `18283b4` · **PR:** [#126](https://github.com/jaredmcfarland/mixpanel_data/pull/126)
**Suite:** 5,948 pass / 90.85% coverage / mypy --strict + ruff clean · **Live QA:** 18 / 18 against real Mixpanel API
**Generated:** 2026-04-22 (post-B1)

---

## TL;DR for the next session

The 042 auth-redesign feature is ~88% done. **B1 (the Workspace flatten + bridge/config legacy deletion keystone) just landed in three commits — `12471c6` / `024a291` / `18283b4`.** Net −9,750 LoC. Four PR #126 fixes still deferred (16 / 17 / 18 OAuth wiring + 27 public auth-types module) plus B2 sweeps + Phase 9 plugin rewrite + Phase 11 release polish. Stay on this branch; do not start a 043 spec for the leftover work — it's all "finish what 042 left undone," not a new feature. **Next workstream is A1 — the OAuth wiring trio.** Without Fix 17, `mp account login NAME` is still a `NotImplementedError` stub, which means new oauth_browser accounts cannot be created from a clean install.

---

## Operating context

- **Pre-1.0 alpha** with a handful of internal testers. Reframed mid-PR as "free to break" — no migration constraints, no public-API stability constraints, deletions preferred over shims.
- **`mp config convert` (Phase 10 / US10) is intentionally dropped** — legacy detection deleted in `5a6b876`. v1/v2 configs now fail at Pydantic validation with an honest "unexpected key" error. Acceptable for alpha.
- **Spec Kit "one spec = one PR" pattern preserved** by finishing the deferred work on this same branch rather than splitting into 043.
- **Plugin (`mixpanel-plugin/`)** still points at v1/v2 `mp.auth.*` APIs and is broken — not yet rewritten.

---

## Authoritative trackers (read these first)

| Doc | Purpose |
|-----|---------|
| `specs/042-auth-architecture-redesign/pr-126-review-plan.md` | **Source of truth for the PR #126 review.** New "Execution Status" section near top maps Group A–G fixes to done/deferred. |
| `specs/042-auth-architecture-redesign/tasks.md` | **T-ID granularity.** Status table reflects post-`5a6b876` reality. `[X]` = done, `[-]` = deferred, `[ ]` = pending. |
| `specs/042-auth-architecture-redesign/spec.md` | User stories, FRs, success criteria. |
| `specs/042-auth-architecture-redesign/contracts/` | Frozen contracts for `python-api.md`, `cli-commands.md`, `config-schema.md`, `filesystem-layout.md`, `plugin-auth-manager.md`. |
| `context/auth-architecture-redesign.md` | Source design doc — Appendix A (resolution decision tree) and Appendix B (vocabulary mapping old → new) are load-bearing. |

---

## What landed (recent commits, newest first)

```
18283b4 feat(042): merge legacy + v3 config modules into one (Fix 9)
024a291 feat(042): delete v1 AuthBridgeFile from bridge.py (Fix 14)
12471c6 feat(042): flatten Workspace dual-init to v3-only path (Fix 10)
787feea docs(042): refresh tracker docs to reflect post-5a6b876 reality
93e3081 fix(042): align live auth tests with tightened PR #126 behavior
5a6b876 feat(042): execute PR #126 review plan — 28 of 35 fixes (P0 + P1)
41645d4 fix(042): address second Codex review — auto-detect, use(), OAuth atomicity, CLI globals
dbe10a1 fix(042): address Codex review — workspace pin, Session.headers, persist clear, Target.workspace
acee076 feat(042): account-as-source-of-truth for project + PR #126 fixes
c497843 fix(042): tomli mypy ignore tolerant of py3.10 vs py3.11+
```

The B1 cluster (3 commits, +1,827 / −11,577 across 133 files) finished Group B (legacy elimination) by:
- **Fix 10 (`12471c6`)** — `Workspace.__init__` is now keyword-only `(account, project, workspace, target, session)` per `contracts/python-api.md` §1; `_init_v3` / `_has_v3_config` / `_resolved_session` / 5× `hasattr(_v3_session)` guards / `_session_to_credentials` helper / legacy `--credential` and `--workspace-id` CLI globals all gone. ~85 `_config_manager=` test sites migrated to `session=_TEST_SESSION`; 13 legacy-only test classes / 1 dead integration file deleted with rationale comments.
- **Fix 14 (`024a291`)** — v1 `AuthBridgeFile` schema + 9 helpers (`load_bridge_file` / `write_bridge_file` / `find_bridge_file` / `default_bridge_path` / `detect_cowork` / `bridge_to_credentials` / `bridge_to_resolved_session` / `apply_bridge_custom_header` / `refresh_bridge_token`) deleted; v2 imports promoted to module top (no more `# noqa: E402` block). `ConfigManager._resolve_*_from_bridge` chain deleted. `tests/unit/test_auth_bridge.py` and `tests/unit/test_config_bridge_resolution.py` deleted.
- **Fix 9 (`18283b4`)** — `_internal/config_v3.py` merged into `_internal/config.py` (then deleted); legacy `ConfigManager` class (`resolve_credentials`, `resolve_session`, `add_account(project_id=, region=)`, `set_default`, `add_credential`, `add_project_alias`, `migrate_v1_to_v2`) gone; `AccountInfo` / `CredentialInfo` / `ActiveContext` / `ProjectAlias` / `MigrationResult` dataclasses gone; `Credentials.from_oauth_token` / `to_resolved_session` factories gone; `Workspace.test_credentials` static method gone (FR-038 routes through `mp.accounts.test`). 22 import sites bulk-rewritten; 10 dead-legacy test files deleted; `MagicMock(spec=ConfigManager)` relaxed to plain `MagicMock()` across 29 files.

Earlier (`5a6b876`, 51 files, −7,001 LoC) completed:
- **Group A** atomicity & security (8/8): atomic_write_bytes, _mutate ctx mgr, per-request headers, `accounts.use(NAME)` clears workspace, immutable Session.headers, strict OAuth default + `_OAUTH_TOKEN_PENDING` deletion, MP_OAUTH_STORAGE_DIR routing, account_dir traversal tests
- **Group B** legacy elimination (early portion): deleted `cli/commands/{auth,context,projects,workspaces_cmd,config_cmd}.py` + v1/v2 fixtures + legacy detection (rest finished by B1 above)
- **Group C** behavior gaps (1/4): `mp target` CLI (5 commands + 10 smoke tests)
- **Group D** cleanup (4/4): DEFAULT_STORAGE_DIR shim, AccountAccessError, `--refresh`/`--bridge` unwired flags
- **Group E** input validation (3/3): MP_REGION/MP_WORKSPACE_ID/MP_PROJECT_ID strict, expires_at validation, `--secret-stdin` 64 KiB
- **Group F** type design (3/4): Account.match() exhaustiveness, AccountTestResult/OAuthLoginResult tightening, promoted resolver helpers
- **Group G** test/doc hygiene (5/5): comment-rot scrub, `current_auth_header` docstring, ConfigManager + Session PBT, atomic-write resilience tests, real-`~/.mp/` write guard fixture

---

## Remaining work — by cluster

### Cluster A — Functional 1.0 blockers

#### A1. OAuth wiring trio (Fix 16, 17, 18) — HIGH IMPACT

Without these, `oauth_browser` is degraded:
- **Fix 16** (`src/mixpanel_data/_internal/auth/token_resolver.py:140-165`) — currently raises `OAUTH_REFRESH_ERROR`; replace with real `OAuthFlow.refresh_tokens(refresh_token)` call, persist via `atomic_write_bytes`, mirror `bridge.refresh_bridge_token` error semantics.
- **Fix 17** (`src/mixpanel_data/cli/commands/account.py:434-441` + `src/mixpanel_data/accounts.py:237-253`) — `mp account login NAME` is a `NotImplementedError` stub. Wire `OAuthFlow` (PKCE + browser callback + `/me` probe to backfill `default_project`). **Users currently cannot add an oauth_browser account from a clean install** — they have to manually copy v2 tokens. The live-test conftest (`tests/live/conftest_042.py:copy_user_oauth_tokens_to_account`) literally exists as a workaround for this gap.
- **Fix 18** (`src/mixpanel_data/_internal/api_client.py`) — depends on Fix 16. For OAuth accounts, `_get_auth_header()` should call `TokenResolver.get_browser_token(...)` per request instead of reading from a `Credentials` shim built once. Service-account path keeps existing per-request basic auth.

Estimated: ~1 day for the trio.

#### A2. Plugin rewrite (Phase 9 / US9, T094–T100)
- Rewrite `mixpanel-plugin/skills/mixpanelyst/scripts/auth_manager.py` from ~727 → ≤300 lines, zero `if version >= 2` branches, JSON output per `contracts/plugin-auth-manager.md`
- Update `mixpanel-plugin/commands/auth.md`, `mixpanel-plugin/skills/setup/SKILL.md`, `mixpanel-plugin/README.md`, `mixpanel-plugin/plugin.json` (bump → 5.0.0)
- New integration test: `tests/integration/test_plugin_auth_manager.py` (subprocess-based)
- Verification gates: `wc -l auth_manager.py ≤ 300` and `grep -c "config_version\|version >= 2" == 0`

Estimated: ~1 day. Should land AFTER A1 + B3 so the public Python surface is final.

### Cluster B — Architectural cleanup

#### B1. Workspace flatten + legacy deletion (Fix 9, 10, 14) — ✅ DONE

Landed in three commits, B1 cluster (`12471c6` → `024a291` → `18283b4`). See "What landed" above for the full breakdown. Net −9,750 LoC.

#### B2. Phase 4 deferred deletions (T043–T053a) — partially absorbed by B1; rest still open

| T-ID | Status | Description |
|------|--------|-------------|
| T043 | ⬜ pending | `MeService` cache path: `~/.mp/oauth/me_{region}_{name}.json` → `~/.mp/accounts/{name}/me.json` |
| T044 | ⬜ pending | Remove `OAuthTokens.project_id` legacy field (`src/mixpanel_data/_internal/auth/token.py:~60`) |
| T045 | ⬜ pending | Update `flow.py` / `client_registration.py` / `storage.py` for per-account paths |
| T047 | ⬜ pending | Rewrite `src/mixpanel_data/auth.py` as thin re-export module (currently still re-exports the legacy `Credentials` / `AuthMethod` shim — Fix 18 will retire those) |
| T048 | ⬜ pending | DELETE `src/mixpanel_data/_internal/auth_credential.py` |
| T049 | ✅ done in B1 (`18283b4`) | `AccountInfo` / `CredentialInfo` / `ProjectAlias` / `MigrationResult` / `ActiveContext` already gone |
| T050 | ⬜ pending | DELETE deprecated `Workspace` methods (`switch_project`, `switch_workspace`, `set_workspace_id`, `current_credential`, `current_project`) |
| T051 / T052 | ✅ done in B1 (`18283b4`) | v1/v2 ConfigManager stubs already gone |
| T053a | ⚠️ partial — B1 deleted ~14 dead-legacy test files | Final sweep needed once T050 lands |

Estimated remaining: ~half day.

#### B3. Public auth-types module (Fix 27)
- Create `src/mixpanel_data/auth_types.py` (or extend `types.py` if it stays sub-2000 lines)
- Move canonical defs: `Account`, `OAuthBrowserAccount`, `OAuthTokenAccount`, `ServiceAccount`, `AccountType`, `Region`, `Project`, `Session`, `WorkspaceRef`, `ActiveSession`, `TokenResolver`, `OnDiskTokenResolver`, `BridgeFile`, `OAuthTokens`
- Flip import direction: `_internal/auth/...` becomes thin re-exporters that import from the public module
- Drop duplicate `_RegionLiteral` / `_AccountTypeLiteral` in `types.py` — single source of truth eliminates drift risk
- `__init__.py` re-exports cleanly from `mixpanel_data.auth_types`

Standalone refactor, can land any time after B1. Estimated: ~half day.

### Cluster C — Optional features (P2/P3 from spec)

#### C1. Cross-cutting iteration tests (Phase 7 / US7, T077–T084) — P2

**Capability is already live** (Workspace.use + Session.replace). Missing dedicated integration tests:
- `tests/integration/test_cross_project_iteration.py` — assert zero re-auth, zero `/me` calls, one `httpx.Client` instance throughout
- `tests/integration/test_cross_account_iteration.py` — auth header rebuild + httpx.Client preserved
- `tests/integration/test_parallel_snapshot.py` — `Session.replace` + `ThreadPoolExecutor`
- `tests/integration/test_cli_shell_loop.py` — subprocess + `xargs`
- `examples/cross_project.py` documentation example

Pure test additions. Land any time. Estimated: ~half day.

#### C2. Cowork bridge WRITER (Phase 8 / US8, T089–T093) — P2

**Read path ✅ done** (resolver + live test F1.01). Missing the export side:
- `_internal/auth/bridge.py:export_bridge(account, *, to, project=None, workspace=None, headers=None, token_resolver) -> Path` — writes 0o600 v2 schema; for `oauth_browser`, reads tokens via resolver and embeds them
- `_internal/auth/bridge.py:remove_bridge(*, at=None) -> bool`
- Wire into `mp.accounts.export_bridge()` / `remove_bridge()` (currently `NotImplementedError` stubs in `accounts.py`)
- CLI commands: `mp account export-bridge --to PATH [--account NAME] [--project ID] [--workspace ID]`, `mp account remove-bridge [--at PATH]`
- `mp session --bridge` flag display logic in `cli/commands/session.py`

Necessary for Cowork VM users to export credentials from host → guest. Estimated: ~half day.

#### C3. Phase 5 leftover polish
- T058a: help-examples snapshot tests
- T066: `cli/utils.py:get_workspace()` rewire (works via new namespaces today; cleanup item)
- T067: formatter consistency polish across new commands
- T069: `cli/CLAUDE.md` update

### Cluster D — Release prep (Phase 11)

| Item | T-ID | Notes |
|------|------|-------|
| Project root `CLAUDE.md` auth section rewrite | T111 | Drop deprecated env-var entries; pointer to `mp config convert` becomes "schema break — wipe `~/.mp/config.toml`" |
| `src/mixpanel_data/CLAUDE.md` rewrite | T112 | Account → Project → Workspace as primary mental model; `Workspace.use()` as centerpiece |
| `src/mixpanel_data/cli/CLAUDE.md` rewrite | T113 | Command tree (account/project/workspace/target/session); global flags table |
| `context/mixpanel_data-design.md` auth section pointer | T114 | 1-paragraph summary + pointer to `auth-architecture-redesign.md` |
| Archive `context/auth-project-workspace-redesign.md` | T115 | Prepend "Status: Superseded by …"; do NOT delete |
| `context/CLAUDE.md` hierarchy diagram update | T116 | Note `auth-architecture-redesign.md` as the auth authority |
| Bump versions | T117 | `pyproject.toml` → 0.4.0; `mixpanel-plugin/plugin.json` → 5.0.0 |
| Release notes | T118 | `RELEASE_NOTES_0.4.0.md` with explicit BREAKING CHANGES section |
| LoC budget enforcement | T119 | `tests/unit/test_loc_budget.py`: ≤12 auth files, ≤4000 LoC total. B1 reduced auth subsystem by ~9,750 LoC; should now be in budget but not yet enforced by a test. |
| Mutation score | T120 | `just mutate` against auth subsystem; target ≥85% |
| Grep verifications | T121, T122 | Zero v1/v2 references; zero deprecated re-exports |
| Manual quickstart walkthrough | T125 | Walk every example in `quickstart.md` on clean `~/.mp/` |
| Security audit | T126 | All account state files 0o600, parent dirs 0o700 |
| Docstring coverage gate | T126a | `pydocstyle --convention=google` on auth subsystem |

---

## Recommended sequencing

1. ~~**B1 — Workspace flatten cluster**~~ ✅ DONE (3 commits, −9,750 LoC)
2. **A1 — OAuth wiring trio** ← **next workstream** (Fix 18 already easier post-flatten)
3. **B2 — Phase 4 deferred deletions** (mechanical sweeps; T049 / T051 / T052 already absorbed by B1)
4. **B3 — auth_types public module** (small standalone refactor)
5. **A2 — plugin / auth_manager rewrite** (depends on public Python API being final)
6. **C2 — bridge writer** (small, well-specified)
7. **C1 — cross-cutting iteration tests** (pure test additions)
8. **D — Phase 11 polish** (last; depends on everything above)

**Remaining estimate:** ~3–5 focused days to 1.0-ready.

---

## Verify state on session start

```bash
# Confirm branch + HEAD
git status                    # should show branch=042-auth-architecture-redesign, clean tree
git log --oneline -4          # top three should be 18283b4 / 024a291 / 12471c6

# Confirm test suite green (slow — ~3-5 min)
just check

# Confirm live tests still passing (requires MP_LIVE_* env vars in ~/.zshrc)
MP_LIVE_TESTS=1 uv run pytest tests/live/test_042_auth_redesign_live.py -v -m live
```

---

## Live test setup (gotcha)

The live tests at `tests/live/test_042_auth_redesign_live.py` require:

```bash
# Service account (Cat A)
MP_LIVE_SA_USERNAME, MP_LIVE_SA_SECRET, MP_LIVE_SA_PROJECT_ID, MP_LIVE_SA_REGION

# OAuth browser (Cat B) — uses real ~/.mp/oauth/tokens_us.json (no env var)
# Requires a prior `mp auth login` (legacy v2 — Fix 17 will replace this with `mp account login`)

# Static OAuth token (Cat C)
MP_LIVE_OAUTH_TOKEN, MP_LIVE_PROJECT_ID, MP_LIVE_REGION
```

The `MP_LIVE_*` prefix dodges the autouse env-var cleanup in `tests/conftest.py` (which scrubs `MP_USERNAME` / `MP_SECRET` / `MP_OAUTH_TOKEN` / etc. before each test runs). Live tests opt back in via `monkeypatch.setenv` inside the test body.

**conftest_042.py: `copy_user_oauth_tokens_to_account()` is a workaround for the missing Fix 17.** Once `mp account login NAME` works, the helper can be replaced with a real login flow.

---

## Decisions already made (don't relitigate)

- **Stay on `042-auth-architecture-redesign` branch.** Don't run `/specify` for 043. The deferred work is "finish 042," not a new feature.
- **No backward compat.** Alpha "free to break" — delete legacy paths, don't shim.
- **Phase 10 / `mp config convert` dropped.** Legacy detection deleted. v1/v2 configs fail at Pydantic validation.
- **`mp target` CLI (Phase 6 / US6) shipped** in `5a6b876` (5 commands + 10 smoke tests).
- **Workspace factory split (Fix 10)** is the recommended approach per the source plan — `Workspace.from_session(s)` / `from_credentials(...)` / `from_config(account=, target=)`. Verify with the user before committing to this if it changes the public API shape they expect.
- **`93e3081` baked current behavior into 5 live tests** (A1.03 requires --project, B1.03 raises at construction, D1.01 requires default_project, F1.01 needs tokens at on-disk path, G1.04 strict ConfigError). If you change product behavior in Cluster A or B, update those tests.

---

## Key file map

```
src/mixpanel_data/
├── workspace.py                        # ← Fix 10 lives here
├── accounts.py                         # ← Fix 17 wiring; bridge writer (C2)
├── auth.py                             # ← T047 thin re-export
├── auth_types.py                       # ← Fix 27 NEW MODULE
├── _internal/
│   ├── config.py                       # ← Fix 9 DELETE (rename config_v3.py to this)
│   ├── config_v3.py                    # ← becomes config.py post-Fix 9
│   ├── api_client.py                   # ← Fix 18 per-request bearer
│   ├── auth_credential.py              # ← T048 DELETE
│   └── auth/
│       ├── bridge.py                   # ← Fix 14 delete v1; C2 add export
│       ├── token_resolver.py           # ← Fix 16 OAuth refresh
│       ├── flow.py                     # ← T045 per-account paths
│       └── client_registration.py      # ← T045 per-account paths

mixpanel-plugin/                        # ← A2 plugin rewrite (entire dir)

tests/live/test_042_auth_redesign_live.py
tests/live/conftest_042.py              # ← can simplify post-Fix 17
```
