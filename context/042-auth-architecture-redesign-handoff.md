# Session Handoff: 042 Auth Architecture Redesign

**Branch:** `042-auth-architecture-redesign` · **Last commit:** `9147b1d` · **PR:** [#126](https://github.com/jaredmcfarland/mixpanel_data/pull/126)
**Suite:** 5,942 pass / 91.40% coverage / mypy --strict + ruff clean · **Live QA:** 18 / 18 against real Mixpanel API
**Generated:** 2026-04-22 (post-C2 — bridge writer + CLI complete)

---

## TL;DR for the next session

🎉 **PR #126 review plan + A2 plugin rewrite + C2 bridge writer are complete.** All 35 of 35 review fixes plus the plugin / agent surface (Phase 9 / US9) plus the Cowork bridge writer (Phase 8 / US8) have landed across B1 (Workspace flatten + bridge/config legacy deletion), A1 (OAuth wiring trio — refresh + `mp account login` + per-request bearer), B2 (Phase 4 deferred deletions — T043 / T044 / T045 / T047 / T048 / T050), B3 (Fix 27 — public `mixpanel_data.auth_types` module), A2 (`478160f`) — `auth_manager.py` 727 → 257 LoC, plugin v5.0.0, JSON contract `schema_version: 1`, and **C2 (`9147b1d`) — `bridge.export_bridge` / `bridge.remove_bridge` + `mp account export-bridge` / `remove-bridge` CLI + `mp session --bridge` flag**. The auth subsystem, its plugin surface, and the Cowork courier story are all at target shape.

Open spec-level workstreams (not part of the PR #126 review): **C1** (cross-cutting iteration tests — Phase 7 / US7) and **D** (Phase 11 release polish — CLAUDE.md sweeps, library version bump to 0.4.0, release notes, mutation testing, security audit). Stay on this branch; do not start a 043 spec for the leftover work — it's all "finish what 042 left undone," not a new feature.

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
9147b1d feat(042): bridge writer + mp account export-bridge / remove-bridge (C2 / Phase 8)
668ceb4 docs(042): refresh trackers — A2 cluster (plugin rewrite) done
478160f feat(042): rewrite plugin auth_manager + bump v5.0.0 (A2 / Phase 9 / US9)
d20630e docs(042): fix mkdocs-strict build — replace removed AccountInfo with v3 Account types
07d55cf docs(042): refresh trackers — PR #126 review plan complete (B3 / Fix 27 done)
f18f1aa feat(042): add public mixpanel_data.auth_types module (B3 / Fix 27)
86e56d7 docs(042): refresh trackers for B2 cluster (T043/T044/T045/T047/T048/T050 done)
50ccd9d feat(042): delete auth_credential.py + thin auth.py re-export (B2 T047 / T048)
b1c7a74 feat(042): per-account me.json + flow.login persist=False default (B2 T043 / T045)
651bf66 feat(042): drop OAuthTokens.project_id legacy field (B2 T044)
3f74cd7 feat(042): delete deprecated Workspace methods (B2 T050 / FR-038)
cd044b7 docs(042): refresh trackers for A1 cluster (Fix 16 / 17 / 18 done)
4d21c3e feat(042): wire OAuth refresh + mp account login + per-request bearer (A1)
62befd1 docs(042): refresh trackers for B1 cluster (Fix 9 / 10 / 14 done)
18283b4 feat(042): merge legacy + v3 config modules into one (Fix 9)
024a291 feat(042): delete v1 AuthBridgeFile from bridge.py (Fix 14)
12471c6 feat(042): flatten Workspace dual-init to v3-only path (Fix 10)
787feea docs(042): refresh tracker docs to reflect post-5a6b876 reality
93e3081 fix(042): align live auth tests with tightened PR #126 behavior
5a6b876 feat(042): execute PR #126 review plan — 28 of 35 fixes (P0 + P1)
```

C2 cluster (`9147b1d`, +899 / −52 across 7 files):
- **T089 — `_internal/auth/bridge.py`** gained `export_bridge(account, *, to, project=None, workspace=None, headers=None, token_resolver=None) -> Path` (atomic 0o600 write via `atomic_write_bytes`; parent dir auto-created at 0o700; for `oauth_browser`, on-disk tokens read via `_read_browser_tokens()` and embedded under `tokens`) and `remove_bridge(*, at=None) -> bool` (resolves path the same way as `load_bridge`; returns False when already absent — idempotent). Private `_serialize_bridge()` projects `SecretStr` fields back to raw strings (B3 — bridge MUST carry usable credentials, redacted output would defeat the courier purpose).
- **T090 — `accounts.py`** wrappers replace the Phase-4 `NotImplementedError` stubs. `export_bridge(*, to, account=None, project=None, workspace=None)` resolves the account (defaults to active), pulls `[settings].custom_header` into `bridge.headers` (B5), and delegates. `remove_bridge(*, at=None)` delegates. Both exposed in `__all__`.
- **T091 — `cli/commands/account.py`** `mp account export-bridge` and `mp account remove-bridge` are now real Typer commands gained `@handle_errors`; the prior bare exit-1 stubs are gone.
- **T092 — `cli/commands/session.py`** added `--bridge` flag. Multi-line summary (path / account / project pin / workspace pin / headers) for text mode; JSON mode emits the bridge under a top-level `bridge` key (matches the plugin auth_manager contract for re-use by the slash command).
- **T086 — `tests/unit/test_bridge_export.py`** (15 tests). `bridge.export_bridge` for each Account variant + 0o600 file mode + parent-dir 0o700 creation + project/workspace/headers round-trip + idempotency; `bridge.remove_bridge` for existing / absent / search-path resolution; `mp.accounts` namespace wrappers (named / active / settings header propagation / removal).
- **T087 — `tests/unit/cli/test_bridge_cli.py`** (8 tests). `mp account export-bridge` (SA happy path + oauth_browser without/with tokens + project/workspace pins + secret-not-in-stdout guard); `mp account remove-bridge` (existing + idempotent absent); `mp session --bridge` (no bridge + bridge-present with full payload).
- **`tests/unit/test_accounts_namespace.py`** dropped the `TestStubs` class — coverage migrated to `test_bridge_export.py`.

A2 cluster (`478160f`, +834 / −829 across 6 files):
- **T095 / T100 — `mixpanel-plugin/skills/mixpanelyst/scripts/auth_manager.py`** rewritten 727 → **257 LoC**. Two-level argparse (group → action) dispatched through a `_DISPATCH: dict[(str, str | None), Handler]`; `_do(fn, *args, project_override=)` and `_with_workspace(extractor)` factor the repeated patterns; module-level `from mixpanel_data import Workspace, accounts, session as sess, targets` + `# fmt: skip` on a few dict literals keep the body inside the LoC budget. Zero `config_version` / `version >= 2` branches. JSON output exactly per `contracts/plugin-auth-manager.md` (`schema_version: 1` + state-discriminated `ok` / `needs_account` / `needs_project` / `error`); errors emit JSON to stdout with exit 0 so the slash command can `json.loads` unconditionally.
- **T094 — `tests/integration/test_plugin_auth_manager.py`** (15 subprocess-based tests). Covers `session` (3 states), `account list/add/use` (4 cases including missing-account error path), `target list/add/use` (3 cases — empty, populated, atomic apply), `bridge status` (absent + present), plus `TestStaticGuards` enforcing `wc -l ≤ 300` and zero version-branch tokens. Hermetic `_run()` helper sets a near-empty env (PATH + HOME + MP_CONFIG_PATH + PYTHONPATH + venv vars) so MP_* leakage from the developer shell can't pollute the subprocess.
- **T096 — `mixpanel-plugin/commands/auth.md`** rewritten around the discriminated `state` schema; routing per `account / project / workspace / target / bridge` subcommand groups. Security rule preserved (NEVER ask for secrets in conversation).
- **T097 — `mixpanel-plugin/skills/setup/SKILL.md`**: fresh-install walkthrough now `mp account add` → `mp account login` → `mp project use`. Cowork section points to `mp account export-bridge`.
- **T098 — `.claude-plugin/plugin.json` 4.1.0 → 5.0.0** + README "Breaking changes from 4.x" callout listing the slash-command vocabulary change, the JSON `schema_version: 1` contract, and the v2 bridge file format.

B3 cluster (`f18f1aa`, +165 / −23 across 4 files):
- New ``src/mixpanel_data/auth_types.py`` consolidates the v3 auth surface into one canonical re-export module: ``Account`` / variants / ``Region`` / ``Session`` / ``Project`` / ``WorkspaceRef`` / ``ActiveSession`` / ``OAuthTokens`` / ``OAuthClientInfo`` / ``TokenResolver`` / ``OnDiskTokenResolver`` / ``BridgeFile`` / ``load_bridge``.
- ``mixpanel_data.__init__`` re-exports from ``auth_types`` instead of reaching into ``_internal/auth/``; ``mp.Account`` etc. resolve to the same canonical objects.
- Deleted the ``_AccountTypeLiteral`` / ``_RegionLiteral`` mirrors in ``types.py`` — ``AccountSummary.type`` / ``AccountSummary.region`` now reference the canonical Literals from ``auth_types``, eliminating drift risk.
- ``tests/unit/test_auth_types_module.py`` pins the contract: every name in ``__all__`` is the same object as the underlying ``_internal`` definition.

B2 cluster (4 commits, ~+650 / −2,100 across ~20 files):
- **T050 (`3f74cd7`)** — Deleted deprecated `Workspace` methods: `set_workspace_id`, `switch_project`, `switch_workspace`, `current_credential`, `current_project` (per FR-038 / `contracts/python-api.md` §2/§4). Replacements: `ws.use(...)`, `ws.account/project/workspace`. ~310 LoC of test classes deleted with tombstone comments.
- **T044 (`651bf66`)** — Dropped `OAuthTokens.project_id` legacy field. The v3 layout binds tokens to `Account.default_project` via the per-account `~/.mp/accounts/{name}/tokens.json` path; threading project_id through the token model was dead weight risking drift. Cascades through `OAuthFlow.login` / `exchange_code` / `_post_token_request` and `OAuthStorage.save_tokens` / `load_tokens` signatures.
- **T043 + T045 (`b1c7a74`)** — `MeCache` is now per-account: `~/.mp/accounts/{name}/me.json`. API simplified — `MeCache(*, account_name, storage_dir=None, ttl_seconds=...)` with `get() / put(response) / invalidate()` (region kwarg dropped). `OAuthFlow.login` flipped default to `persist=False` since no v2 caller remains.
- **T047 + T048 (`50ccd9d`)** — Deleted `_internal/auth_credential.py` (the v2 `AuthCredential` / `CredentialType` / `ProjectContext` / `ResolvedSession` types are no longer reachable after T050). `RegionType` / `VALID_REGIONS` constants moved into `_internal/config.py`. `mixpanel_data.auth` is now a thin re-export of v3 surface (`ConfigManager`, `Credentials`, `AuthMethod`, `BridgeFile`, `load_bridge`).

A1 cluster (`4d21c3e`, +645 / −42 across 8 files):
- **Fix 16** — `OnDiskTokenResolver._refresh_and_persist`: when an on-disk token is within the 30s expiry buffer AND a refresh token is present, call `OAuthFlow.refresh_tokens(...)` and atomic-write the new payload back to `~/.mp/accounts/{name}/tokens.json`. Missing DCR client info surfaces `OAUTH_REFRESH_ERROR`. Previously this branch raised "refresh is not yet wired up".
- **Fix 17** — `accounts.login(name)` and `mp account login NAME` no longer stubs: full PKCE dance via `OAuthFlow.login(persist=False)` → `_persist_browser_tokens` → `/me` probe to capture user identity + backfill `account.default_project`. Returns `OAuthLoginResult`. CLI grew `--no-browser` flag (reserved for headless mode).
- **Fix 18** — `MixpanelAPIClient._get_auth_header` re-resolves OAuth bearers per request via the bound `TokenResolver`. SA sessions and the legacy `credentials=` path keep using cached `Credentials.auth_header()`. `current_auth_header` (public) routes through the same per-request path.

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

#### A1. OAuth wiring trio (Fix 16, 17, 18) — ✅ DONE

Landed in `4d21c3e`. `oauth_browser` is no longer degraded:
- Fix 16 — `OnDiskTokenResolver._refresh_and_persist` calls `OAuthFlow.refresh_tokens` and atomic-writes the new payload back to the per-account path.
- Fix 17 — `mp account login NAME` runs the full PKCE flow, persists tokens to `~/.mp/accounts/{name}/tokens.json`, probes `/me`, backfills `default_project` if absent. Returns `OAuthLoginResult`.
- Fix 18 — `MixpanelAPIClient._get_auth_header` re-resolves OAuth bearers per request via the bound `TokenResolver`.

`tests/live/conftest_042.py:copy_user_oauth_tokens_to_account` is no longer the only way to seed v3 OAuth tokens — `mp account login` works on a clean install. The helper remains as a non-interactive convenience for live tests (avoids triggering a browser per test run).

#### A2. Plugin rewrite (Phase 9 / US9, T094–T100) — ✅ DONE

Landed in `478160f`. See the "What landed" A2 cluster breakdown above. Verification gates met:
- `wc -l mixpanel-plugin/skills/mixpanelyst/scripts/auth_manager.py == 257` (≤ 300 budget).
- `grep -c "config_version\|version >= 2\|if version >=" mixpanel-plugin/skills/mixpanelyst/scripts/auth_manager.py == 0`.
- `tests/integration/test_plugin_auth_manager.py` — 15 / 15 pass.
- Plugin manifest at v5.0.0 with explicit "Breaking changes from 4.x" callout in README.

T099 (`mixpanelyst/SKILL.md` + `dashboard-expert/SKILL.md` vocabulary refresh) was deferred — neither file currently references legacy `mp auth ...` vocabulary, so there is nothing to rewrite. Recheck during the Cluster D doc sweep.

### Cluster B — Architectural cleanup

#### B1. Workspace flatten + legacy deletion (Fix 9, 10, 14) — ✅ DONE

Landed in three commits, B1 cluster (`12471c6` → `024a291` → `18283b4`). See "What landed" above for the full breakdown. Net −9,750 LoC.

#### B2. Phase 4 deferred deletions (T043–T053a) — ✅ DONE

Landed in four commits, B2 cluster (`3f74cd7` → `651bf66` → `b1c7a74` → `50ccd9d`). See "What landed" above for the per-T breakdown. T049 / T051 / T052 were absorbed by B1 already. T053a is mostly done; remaining fragments are picked up as future cleanup touches them.

#### B3. Public auth-types module (Fix 27) — ✅ DONE

Landed in `f18f1aa`. ``src/mixpanel_data/auth_types.py`` is the canonical re-export module — public callers can `from mixpanel_data.auth_types import Account, Session, BridgeFile, OAuthTokens, ...` without reaching into ``_internal``. Also drops the duplicate ``_AccountTypeLiteral`` / ``_RegionLiteral`` mirrors in ``types.py`` so ``AccountSummary`` references the canonical Literals.

The original B3 design notes (kept for reference, NOT what landed):
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

#### C2. Cowork bridge WRITER (Phase 8 / US8, T089–T093) — ✅ DONE

Landed in `9147b1d`. See the "What landed" C2 cluster breakdown above. Verification:
- `bridge.export_bridge` writes a v2 bridge file (0o600) embedding the full Account record; for `oauth_browser`, on-disk OAuth tokens are read directly and embedded under `tokens` so the bridge consumer authenticates without a fresh PKCE round.
- `bridge.remove_bridge` is idempotent (returns False on absent, never raises).
- `mp account export-bridge --to PATH [--account NAME] [--project ID] [--workspace ID]` and `mp account remove-bridge [--at PATH]` are wired through `@handle_errors`.
- `mp session --bridge` shows the bridge file source (path + account + project/workspace pins + headers) when present; "No bridge file found" otherwise. JSON mode matches the plugin contract.
- Tests: 15 unit (`test_bridge_export.py`) + 8 CLI (`test_bridge_cli.py`); the live test `F1_01_bridge_oauth_browser_authenticates` exercises the read path against a real bridge file.

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
2. ~~**A1 — OAuth wiring trio**~~ ✅ DONE (`4d21c3e`, +645 LoC, +8 unit tests)
3. ~~**B2 — Phase 4 deferred deletions**~~ ✅ DONE (4 commits, −2,100 LoC)
4. ~~**B3 — auth_types public module**~~ ✅ DONE (`f18f1aa`, +165 LoC, +7 unit tests)
5. ~~**A2 — plugin / auth_manager rewrite**~~ ✅ DONE (`478160f`, 727 → 257 LoC, +15 subprocess tests, plugin v5.0.0)
6. ~~**C2 — bridge writer**~~ ✅ DONE (`9147b1d`, +899 / −52 across 7 files, +23 tests)
7. **C1 — cross-cutting iteration tests** ← **next workstream** (pure test additions — capability is already live; just covering cross-project, cross-account, parallel-snapshot, and CLI shell-loop scenarios)
8. **D — Phase 11 polish** (CLAUDE.md sweeps, library version bump to 0.4.0, release notes, mutation testing, security audit)

**Remaining estimate:** ~1 focused day to 1.0-ready.

---

## Verify state on session start

```bash
# Confirm branch + HEAD
git status                    # should show branch=042-auth-architecture-redesign, clean tree
git log --oneline -16         # top should be 9147b1d (C2) / 668ceb4 / 478160f (A2) / d20630e / 07d55cf / f18f1aa / 86e56d7 / 50ccd9d / b1c7a74 / 651bf66 / 3f74cd7 / cd044b7 / 4d21c3e / 62befd1 / 18283b4 / 024a291

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

**conftest_042.py: `copy_user_oauth_tokens_to_account()` is now optional** — Fix 17 (A1) makes `mp account login NAME` work end-to-end. The helper is kept as a non-interactive shortcut for live-test runs (avoids spawning a browser on every test).

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
tests/live/conftest_042.py              # ← optional post-A1; helper kept for non-interactive live runs
```
