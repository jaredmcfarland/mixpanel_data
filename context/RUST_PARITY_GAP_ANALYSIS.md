# Python–Rust Parity Gap Analysis

> Generated 2026-03-25 — `mixpanel_data` (Python) vs `mixpanel_data_rust` (Rust)
>
> All Rust file references are relative to `mixpanel_data_rust/crates/`

---

## Executive Summary

| Metric | Python | Rust | Gap |
|--------|--------|------|-----|
| Workspace methods | 67 | 165 | **~98** |
| API client methods | ~30 | ~167 | **~137** |
| CLI command groups | 4 | 19 | **15** |
| CLI subcommands | ~45 | ~130 | **~85** |
| Domain type files | 1 (`types.py`) | 18 | — |
| Auth methods | Basic Auth | Basic + OAuth PKCE | **OAuth PKCE** |
| Workspace scoping | None | All App API domains | **Full** |

**Coverage: Python implements ~35% of Rust's API surface.**

The Python library is a read-only analytics client. The Rust port expands it to full CRUD across 15+ entity types with OAuth 2.0 PKCE authentication and workspace-scoped endpoints. Bridging this gap requires:
- 1 new auth module (OAuth PKCE, 7 files)
- App API infrastructure (request method, pagination, workspace scoping)
- ~98 new Workspace methods
- ~137 new API client methods
- 15 new CLI command groups (~85 subcommands)
- ~54 new Pydantic types

---

## Shared Capabilities (Already in Both)

| Capability | Python | Rust |
|-----------|--------|------|
| Basic Auth (service accounts) | `Credentials` in `_internal/config.py` | `Credentials` in `config.rs` |
| Regional endpoints (US/EU/IN) | `ENDPOINTS` dict in `api_client.py:87` | `Region` enum in `literal_types.rs` |
| Config management (TOML) | `ConfigManager` in `_internal/config.py` | `ConfigManager` in `config.rs` |
| Event discovery | `events()`, `properties()`, etc. | Same methods |
| Data export (events) | `fetch_events()`, `stream_events()` | Same + parallel variants |
| Data export (profiles) | `fetch_profiles()`, `stream_profiles()` | Same + parallel variants |
| Analytics queries (12 types) | segmentation, funnel, retention, JQL, etc. | Same queries |
| JQL discovery (5 types) | property_distribution, numeric_summary, etc. | Same queries |
| Local DuckDB storage + SQL | `sql()`, `sql_scalar()`, `tables()`, etc. | Same methods |
| CLI: auth, fetch, query, inspect | 4 command groups | Same + 15 more |

---

## Gap Inventory by Domain

### Domain 0a: OAuth 2.0 PKCE Authentication

**Summary**: Full OAuth 2.0 Authorization Code flow with PKCE (RFC 7636) for accessing App API endpoints. Required prerequisite for all CRUD operations.

**Complexity**: L | **Dependencies**: None (prerequisite for everything else)

#### Rust Auth Module (`mixpanel_data/src/auth/`)

| Component | Rust File | Line | Description |
|-----------|-----------|------|-------------|
| `OAuthClientInfo` | `auth/mod.rs` | 27 | Client registration metadata |
| `PkceChallenge` | `auth/pkce.rs` | 8 | S256 challenge/verifier pair |
| `PkceChallenge::generate()` | `auth/pkce.rs` | 31 | 64 random bytes → base64url verifier → SHA-256 challenge |
| `OAuthTokens` | `auth/token.rs` | 54 | Access/refresh tokens with SecretString, expiry tracking |
| `OAuthTokens::is_expired()` | `auth/token.rs` | 88 | 30-second expiry buffer |
| `OAuthStorage` | `auth/storage.rs` | 11 | JSON file persistence at `~/.mp/oauth/` |
| `OAuthStorage::new()` | `auth/storage.rs` | 20 | Uses `MP_OAUTH_STORAGE_DIR` env or default path, 0o700 perms |
| `OAuthStorage::load_tokens()` | `auth/storage.rs` | ~60 | Load tokens from JSON file |
| `OAuthStorage::save_tokens()` | `auth/storage.rs` | ~75 | Save tokens with 0o600 perms |
| `CallbackResult` | `auth/callback_server.rs` | 5 | OAuth redirect callback data |
| `CALLBACK_PORTS` | `auth/callback_server.rs` | 11 | `[19284, 19285, 19286, 19287]` |
| `start_callback_server()` | `auth/callback_server.rs` | 180 | Bind + wait for redirect |
| `ensure_client_registered()` | `auth/client_registration.rs` | 43 | Dynamic Client Registration (RFC 7591) |
| `DEFAULT_SCOPES` | `auth/client_registration.rs` | 38 | OAuth scope string |
| `OAuthFlow` | `auth/flow.rs` | 44 | Flow orchestrator |
| `OAuthFlow::login()` | `auth/flow.rs` | 109 | Full interactive PKCE flow |
| `OAuthFlow::exchange_code()` | `auth/flow.rs` | 195 | Code → tokens exchange |
| `OAuthFlow::refresh_tokens()` | `auth/flow.rs` | 217 | Refresh expired tokens |
| `OAuthFlow::get_valid_token()` | `auth/flow.rs` | 235 | Auto-refresh if expired |

#### Python Implementation Target

| Python File | What to Add |
|-------------|-------------|
| `_internal/auth/__init__.py` | Module re-exports |
| `_internal/auth/pkce.py` | `PkceChallenge` class (stdlib `hashlib`, `secrets`, `base64`) |
| `_internal/auth/token.py` | `OAuthTokens` Pydantic model with `SecretStr` |
| `_internal/auth/storage.py` | `OAuthStorage` class (JSON files, Unix perms) |
| `_internal/auth/callback_server.py` | Ephemeral HTTP server (stdlib `http.server` + `threading`) |
| `_internal/auth/client_registration.py` | DCR via `httpx` POST |
| `_internal/auth/flow.py` | `OAuthFlow` orchestrator |
| `_internal/config.py` | `AuthMethod` enum, extended `Credentials` |
| `exceptions.py` | `OAuthError` exception class |

#### CLI Commands to Add

| Command | Rust Reference | Line |
|---------|---------------|------|
| `mp auth login` | `mp_cli/src/commands/auth.rs` | 52 |
| `mp auth logout` | `mp_cli/src/commands/auth.rs` | 56 |
| `mp auth status` | — (new, Rust has implicit) | — |
| `mp auth token` | `mp_cli/src/commands/auth.rs` | 58 |

---

### Domain 0b: App API Infrastructure

**Summary**: Generic HTTP request infrastructure for `/api/app/...` endpoints with Bearer auth, cursor-based pagination, and workspace scoping.

**Complexity**: M | **Dependencies**: Domain 0a (OAuth)

#### Rust References

| Component | Rust File | Line | Description |
|-----------|-----------|------|-------------|
| `ApiCategory::App` | `internal/api_client.rs` | ~302 | App API category enum |
| `app_api_request()` | `internal/api_client.rs` | ~400 | Generic App API request with workspace scoping |
| `app_api_request_raw()` | `internal/api_client.rs` | ~450 | Raw variant for multipart/binary |
| `maybe_scoped_path()` | `internal/api_client.rs` | ~500 | Optional workspace scoping (top-level pattern) |
| `require_scoped_path()` | `internal/api_client.rs` | ~530 | Required workspace scoping (project-nested pattern) |
| `build_raw_app_url()` | `internal/api_client.rs` | ~560 | URL builder for raw requests |
| `set_workspace_id()` | `internal/api_client.rs` | 370 | Workspace ID setter |
| `PaginatedResponse<T>` | `types/pagination.rs` | 8 | Generic cursor pagination wrapper |
| `CursorPagination` | `types/pagination.rs` | 44 | Cursor-based pagination fields |
| `PublicWorkspace` | `types/common.rs` | 334 | Workspace metadata type |
| `list_workspaces()` | `workspace.rs` | 309 | List project workspaces |
| `resolve_workspace_id()` | `workspace.rs` | 304 | Auto-discover or use explicit workspace ID |

#### Python Implementation Target

| Python File | What to Add |
|-------------|-------------|
| `_internal/api_client.py` | `app_request()` method, Bearer auth header, workspace scoping logic |
| `_internal/pagination.py` (new) | `PaginatedResponse`, `CursorPagination` Pydantic models, `paginate_all()` helper |
| `workspace.py` | `list_workspaces()`, `resolve_workspace_id()`, `workspace_id` property |
| `cli/main.py` | `--workspace-id` global option |
| `types.py` | `PublicWorkspace` Pydantic model |

**Key insight**: Python's `api_client.py:87-106` already has `"app"` URLs in the `ENDPOINTS` dict for all regions. The `_build_url("app", path)` call will work — just need to add Bearer auth header support alongside existing Basic Auth.

---

### Domain 1: Dashboards

**Summary**: Full CRUD for Mixpanel dashboards including favorites, pins, bulk operations, blueprint templates, RCA dashboards, and ERF metrics.

**Complexity**: L | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `list_dashboards(ids)` | `workspace.rs` | 407 | List dashboards, optionally filtered by IDs |
| `create_dashboard(params)` | `workspace.rs` | 412 | Create new dashboard |
| `get_dashboard(id)` | `workspace.rs` | 417 | Get dashboard by ID |
| `update_dashboard(id, params)` | `workspace.rs` | 422 | Update dashboard |
| `delete_dashboard(id)` | `workspace.rs` | 431 | Delete dashboard |
| `bulk_delete_dashboards(ids)` | `workspace.rs` | 436 | Bulk delete |
| `favorite_dashboard(id)` | `workspace.rs` | 441 | Mark as favorite |
| `unfavorite_dashboard(id)` | `workspace.rs` | 446 | Remove from favorites |
| `pin_dashboard(id)` | `workspace.rs` | 451 | Pin dashboard |
| `unpin_dashboard(id)` | `workspace.rs` | 456 | Unpin dashboard |
| `remove_report_from_dashboard(dashboard_id, bookmark_id)` | `workspace.rs` | 464 | Remove report card |
| `get_bookmark_dashboard_ids(bookmark_id)` | `workspace.rs` | 1227 | Get dashboards containing bookmark |
| `get_dashboard_erf(dashboard_id)` | `workspace.rs` | 1234 | ERF metrics |
| `update_report_link(dashboard_id, report_link_id, params)` | `workspace.rs` | 1239 | Update report link |
| `update_text_card(dashboard_id, text_card_id, params)` | `workspace.rs` | 1251 | Update text card |
| `create_rca_dashboard(params)` | `workspace.rs` | 1219 | Create RCA dashboard |
| `list_blueprint_templates(include_reports)` | `workspace.rs` | 1192 | List blueprint templates |
| `create_blueprint(template_type)` | `workspace.rs` | 1199 | Create blueprint from template |
| `get_blueprint_config(dashboard_id)` | `workspace.rs` | 1204 | Get blueprint config |
| `update_blueprint_cohorts(cohorts)` | `workspace.rs` | 1209 | Update blueprint cohorts |
| `finalize_blueprint(params)` | `workspace.rs` | 1214 | Finalize blueprint dashboard |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `list_dashboards()` | GET | `dashboards/` | `api_client.rs` | 1160 |
| `create_dashboard()` | POST | `dashboards/` | `api_client.rs` | 1174 |
| `get_dashboard()` | GET | `dashboards/{id}/` | `api_client.rs` | 1183 |
| `update_dashboard()` | PATCH | `dashboards/{id}/` | `api_client.rs` | 1189 |
| `delete_dashboard()` | DELETE | `dashboards/{id}/` | `api_client.rs` | 1204 |
| `bulk_delete_dashboards()` | POST | `dashboards/bulk-delete/` | `api_client.rs` | 1211 |
| `favorite_dashboard()` | POST | `dashboards/{id}/favorites/` | `api_client.rs` | 1230 |
| `unfavorite_dashboard()` | DELETE | `dashboards/{id}/favorites/` | `api_client.rs` | 1236 |
| `pin_dashboard()` | POST | `dashboards/{id}/pin/` | `api_client.rs` | 1243 |
| `unpin_dashboard()` | DELETE | `dashboards/{id}/pin/` | `api_client.rs` | 1249 |
| `remove_report_from_dashboard()` | PATCH | `dashboards/{id}/` | `api_client.rs` | 1259 |
| `list_blueprint_templates()` | GET | `dashboards/blueprints-all/` | `api_client.rs` | 2634 |
| `create_blueprint()` | GET | `dashboards/blueprints/` | `api_client.rs` | 2649 |
| `get_blueprint_config()` | GET | `dashboards/{id}/blueprints-config/` | `api_client.rs` | 2661 |
| `update_blueprint_cohorts()` | PATCH | `dashboards/blueprints-cohorts/` | `api_client.rs` | 2667 |
| `finalize_blueprint()` | PATCH | `dashboards/blueprints-finish/` | `api_client.rs` | 2675 |
| `create_rca_dashboard()` | POST | `dashboards/create-rca-dashboard/` | `api_client.rs` | 2685 |
| `get_bookmark_dashboard_ids()` | GET | `dashboards/bookmarks/{id}/dashboard-ids/` | `api_client.rs` | 2711 |
| `get_dashboard_erf()` | GET | `dashboards/{id}/erf/` | `api_client.rs` | 2719 |
| `update_report_link()` | PATCH | `dashboards/{id}/report-links/{id}/` | `api_client.rs` | 2727 |
| `update_text_card()` | PATCH | `dashboards/{id}/textcard/{id}/` | `api_client.rs` | 2742 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `Dashboard` | `types/dashboard.rs` | 11 | id, title, description, is_private, creator_id/name/email, created, modified, is_favorited, pinned_date, layout_version, filters, breakdowns, time_filter |
| `CreateDashboardParams` | `types/dashboard.rs` | 94 | title, description, is_private, is_restricted, filters, breakdowns, time_filter, duplicate |
| `UpdateDashboardParams` | `types/dashboard.rs` | 114 | title, description, is_private, is_restricted, filters, breakdowns, time_filter, layout, content |
| `BlueprintTemplate` | `types/dashboard.rs` | 139 | title_key, description_key, number_of_reports |
| `BlueprintConfig` | `types/dashboard.rs` | 150 | variables |
| `BlueprintFinishParams` | `types/dashboard.rs` | 173 | dashboard_id, cards |
| `CreateRcaDashboardParams` | `types/dashboard.rs` | 180 | rca_source_id, rca_source_data |
| `UpdateReportLinkParams` | `types/dashboard.rs` | 198 | link_type |
| `UpdateTextCardParams` | `types/dashboard.rs` | 205 | markdown |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp dashboards list` | `commands/dashboards.rs` | 25 |
| `mp dashboards create` | `commands/dashboards.rs` | 29 |
| `mp dashboards get` | `commands/dashboards.rs` | 33 |
| `mp dashboards update` | `commands/dashboards.rs` | 39 |
| `mp dashboards delete` | `commands/dashboards.rs` | 45 |
| `mp dashboards bulk-delete` | `commands/dashboards.rs` | 52 |
| `mp dashboards favorite` | `commands/dashboards.rs` | 56 |
| `mp dashboards unfavorite` | `commands/dashboards.rs` | 60 |
| `mp dashboards pin` | `commands/dashboards.rs` | 66 |
| `mp dashboards unpin` | `commands/dashboards.rs` | 70 |
| `mp dashboards remove-report` | `commands/dashboards.rs` | 78 |
| `mp dashboards blueprints` | `commands/dashboards.rs` | 85 |
| `mp dashboards blueprint-create` | `commands/dashboards.rs` | 92 |
| `mp dashboards rca` | `commands/dashboards.rs` | 99 |
| `mp dashboards erf` | `commands/dashboards.rs` | 103 |
| `mp dashboards update-report-link` | `commands/dashboards.rs` | 110 |
| `mp dashboards update-text-card` | `commands/dashboards.rs` | 117 |

---

### Domain 2: Reports/Bookmarks

**Summary**: Full CRUD for saved reports (bookmarks) including bulk operations, history, and linked dashboard tracking.

**Complexity**: M | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `list_bookmarks_v2(type, ids)` | `workspace.rs` | 481 | List bookmarks (v2, paginated) |
| `create_bookmark(params)` | `workspace.rs` | 492 | Create new bookmark |
| `get_bookmark(id)` | `workspace.rs` | 497 | Get bookmark by ID |
| `update_bookmark(id, params)` | `workspace.rs` | 502 | Update bookmark |
| `delete_bookmark(id)` | `workspace.rs` | 511 | Delete bookmark |
| `bulk_delete_bookmarks(ids)` | `workspace.rs` | 516 | Bulk delete |
| `bulk_update_bookmarks(entries)` | `workspace.rs` | 521 | Bulk update |
| `bookmark_linked_dashboard_ids(id)` | `workspace.rs` | 529 | Get linked dashboards |
| `get_bookmark_history(id, cursor, page_size)` | `workspace.rs` | 1283 | Change history |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `list_bookmarks_v2()` | GET | `bookmarks/` | `api_client.rs` | 1283 |
| `create_bookmark()` | POST | `bookmarks/` | `api_client.rs` | 1316 |
| `get_bookmark()` | GET | `bookmarks/{id}/` | `api_client.rs` | 1326 |
| `update_bookmark()` | PATCH | `bookmarks/{id}/` | `api_client.rs` | 1333 |
| `delete_bookmark()` | DELETE | `bookmarks/{id}/` | `api_client.rs` | 1349 |
| `bulk_delete_bookmarks()` | POST | `bookmarks/bulk-delete/` | `api_client.rs` | 1356 |
| `bulk_update_bookmarks()` | POST | `bookmarks/bulk-update/` | `api_client.rs` | 1375 |
| `bookmark_linked_dashboard_ids()` | GET | `bookmarks/{id}/linked-dashboard-ids/` | `api_client.rs` | 1399 |
| `get_bookmark_history()` | GET | `bookmarks/{id}/history/` | `api_client.rs` | 2787 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `Bookmark` | `types/bookmark.rs` | 12 | id, project_id, name, bookmark_type, description, params, creator_id/name/email, created, modified, metadata |
| `CreateBookmarkParams` | `types/bookmark.rs` | 89 | name, bookmark_type, params, description, dashboard_id |
| `UpdateBookmarkParams` | `types/bookmark.rs` | 108 | name, params, description, deleted |
| `BulkUpdateBookmarkEntry` | `types/bookmark.rs` | 129 | id, name, params, description |
| `BookmarkHistoryResponse` | `types/bookmark.rs` | 149 | results, pagination |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp reports list` | `commands/reports.rs` | 20 |
| `mp reports create` | `commands/reports.rs` | 24 |
| `mp reports get` | `commands/reports.rs` | 28 |
| `mp reports update` | `commands/reports.rs` | 34 |
| `mp reports delete` | `commands/reports.rs` | 40 |
| `mp reports bulk-delete` | `commands/reports.rs` | 47 |
| `mp reports bulk-update` | `commands/reports.rs` | 54 |
| `mp reports linked-dashboards` | `commands/reports.rs` | 61 |
| `mp reports dashboard-ids` | `commands/reports.rs` | 68 |
| `mp reports history` | `commands/reports.rs` | 72 |

---

### Domain 3: Cohorts (CRUD Extension)

**Summary**: Extend existing read-only cohort listing to full CRUD. Python already has `cohorts()` for discovery; this adds get, create, update, delete, and bulk operations via the App API.

**Complexity**: M | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `list_cohorts_full(data_group_id, ids)` | `workspace.rs` | 542 | Full list via App API (vs discovery `cohorts()`) |
| `get_cohort(id)` | `workspace.rs` | 553 | Get cohort by ID |
| `create_cohort(params)` | `workspace.rs` | 558 | Create behavioral or static cohort |
| `update_cohort(id, params)` | `workspace.rs` | 563 | Update cohort |
| `delete_cohort(id)` | `workspace.rs` | 568 | Delete cohort |
| `bulk_delete_cohorts(ids)` | `workspace.rs` | 573 | Bulk delete |
| `bulk_update_cohorts(entries)` | `workspace.rs` | 578 | Bulk update |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `list_cohorts_app()` | GET | `cohorts/` | `api_client.rs` | 1409 |
| `get_cohort()` | GET | `cohorts/{id}/` | `api_client.rs` | 1434 |
| `create_cohort()` | POST | `cohorts/` | `api_client.rs` | 1440 |
| `update_cohort()` | PATCH | `cohorts/{id}/` | `api_client.rs` | 1449 |
| `delete_cohort()` | DELETE | `cohorts/{id}/` | `api_client.rs` | 1460 |
| `bulk_delete_cohorts()` | POST | `cohorts/bulk-delete/` | `api_client.rs` | 1469 |
| `bulk_update_cohorts()` | POST | `cohorts/bulk-update/` | `api_client.rs` | 1491 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `Cohort` | `types/cohorts.rs` | 14 | id, name, description, count, is_visible, is_locked, data_group_id, created_by, permissions |
| `CreateCohortParams` | `types/cohorts.rs` | 72 | name, description, data_group_id, definition |
| `UpdateCohortParams` | `types/cohorts.rs` | 94 | name, description, definition |
| `BulkUpdateCohortEntry` | `types/cohorts.rs` | 114 | id, name, description, definition |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp cohorts list` | `commands/cohorts.rs` | 22 |
| `mp cohorts create` | `commands/cohorts.rs` | 26 |
| `mp cohorts get` | `commands/cohorts.rs` | 30 |
| `mp cohorts update` | `commands/cohorts.rs` | 36 |
| `mp cohorts delete` | `commands/cohorts.rs` | 42 |
| `mp cohorts bulk-delete` | `commands/cohorts.rs` | 49 |
| `mp cohorts bulk-update` | `commands/cohorts.rs` | 56 |

---

### Domain 4: Feature Flags

**Summary**: Full CRUD with lifecycle management (archive, restore, duplicate), test user overrides, change history, and account limits. Uses workspace-scoped (project-nested) URL pattern.

**Complexity**: L | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `list_feature_flags(include_archived)` | `workspace.rs` | 592 | List flags |
| `create_feature_flag(params)` | `workspace.rs` | 599 | Create flag |
| `get_feature_flag(id)` | `workspace.rs` | 607 | Get by UUID |
| `update_feature_flag(id, params)` | `workspace.rs` | 612 | Update (PUT, full replacement) |
| `delete_feature_flag(id)` | `workspace.rs` | 621 | Delete |
| `archive_feature_flag(id)` | `workspace.rs` | 626 | Archive (soft delete) |
| `restore_feature_flag(id)` | `workspace.rs` | 631 | Restore from archive |
| `duplicate_feature_flag(id)` | `workspace.rs` | 636 | Duplicate |
| `set_flag_test_users(id, params)` | `workspace.rs` | 641 | Set test user overrides |
| `get_flag_history(id, params)` | `workspace.rs` | 650 | Change history |
| `get_flag_limits()` | `workspace.rs` | 659 | Account limits |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `list_feature_flags()` | GET | `workspaces/{wid}/feature-flags/` | `api_client.rs` | 1528 |
| `create_feature_flag()` | POST | `workspaces/{wid}/feature-flags/` | `api_client.rs` | 1540 |
| `get_feature_flag()` | GET | `workspaces/{wid}/feature-flags/{id}/` | `api_client.rs` | 1553 |
| `update_feature_flag()` | PUT | `workspaces/{wid}/feature-flags/{id}/` | `api_client.rs` | 1559 |
| `delete_feature_flag()` | DELETE | `workspaces/{wid}/feature-flags/{id}/` | `api_client.rs` | 1573 |
| `archive_feature_flag()` | POST | `workspaces/{wid}/feature-flags/{id}/archive/` | `api_client.rs` | 1580 |
| `restore_feature_flag()` | DELETE | `workspaces/{wid}/feature-flags/{id}/archive/` | `api_client.rs` | 1586 |
| `duplicate_feature_flag()` | POST | `workspaces/{wid}/feature-flags/{id}/duplicate/` | `api_client.rs` | 1593 |
| `set_flag_test_users()` | PUT | `workspaces/{wid}/feature-flags/{id}/test-users/` | `api_client.rs` | 1601 |
| `get_flag_history()` | GET | `workspaces/{wid}/feature-flags/{id}/history/` | `api_client.rs` | 1615 |
| `get_flag_limits()` | GET | `feature-flags/limits/` | `api_client.rs` | 1638 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `FeatureFlag` | `types/feature_flags.rs` | 46 | id, project_id, name, key, description, status, tags, serving_method, ruleset, hash_salt |
| `FeatureFlagStatus` | `types/feature_flags.rs` | 11 | Enabled, Disabled, Archived |
| `ServingMethod` | `types/feature_flags.rs` | 21 | Client, Server, RemoteOrLocal, RemoteOnly |
| `FlagRuleset` | `types/feature_flags.rs` | 105 | variants, rollout, test |
| `FlagVariant` | `types/feature_flags.rs` | 116 | key, value, description, is_control, split |
| `FlagRollout` | `types/feature_flags.rs` | 155 | name, cohort_definition, rollout_percentage, variant_splits |
| `CreateFeatureFlagParams` | `types/feature_flags.rs` | 181 | name, key, description, status, tags, ruleset |
| `UpdateFeatureFlagParams` | `types/feature_flags.rs` | 210 | name, key, description, status, tags, ruleset |
| `SetTestUsersParams` | `types/feature_flags.rs` | 230 | users |
| `FlagHistoryParams` | `types/feature_flags.rs` | 240 | page, page_size |
| `FlagHistoryResponse` | `types/feature_flags.rs` | 249 | events, count |
| `FlagLimitsResponse` | `types/feature_flags.rs` | 256 | limit, is_trial, current_usage |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp flags list` | `commands/flags.rs` | 20 |
| `mp flags create` | `commands/flags.rs` | 24 |
| `mp flags get` | `commands/flags.rs` | 28 |
| `mp flags update` | `commands/flags.rs` | 34 |
| `mp flags delete` | `commands/flags.rs` | 40 |
| `mp flags archive` | `commands/flags.rs` | 44 |
| `mp flags restore` | `commands/flags.rs` | 48 |
| `mp flags duplicate` | `commands/flags.rs` | 52 |
| `mp flags set-test-users` | `commands/flags.rs` | 58 |
| `mp flags history` | `commands/flags.rs` | 63 |
| `mp flags limits` | `commands/flags.rs` | 67 |

---

### Domain 5: Experiments

**Summary**: Full A/B experiment lifecycle — create, launch, conclude, decide winner, archive, restore, duplicate.

**Complexity**: L | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `list_experiments(include_archived)` | `workspace.rs` | 670 | List experiments |
| `create_experiment(params)` | `workspace.rs` | 675 | Create experiment |
| `get_experiment(id)` | `workspace.rs` | 680 | Get by UUID |
| `update_experiment(id, params)` | `workspace.rs` | 685 | Update (PATCH) |
| `delete_experiment(id)` | `workspace.rs` | 694 | Delete |
| `launch_experiment(id)` | `workspace.rs` | 699 | Launch (DRAFT→ACTIVE) |
| `conclude_experiment(id, params)` | `workspace.rs` | 704 | Force-conclude |
| `decide_experiment(id, params)` | `workspace.rs` | 713 | Decide winner |
| `archive_experiment(id)` | `workspace.rs` | 722 | Archive |
| `restore_experiment(id)` | `workspace.rs` | 727 | Restore |
| `duplicate_experiment(id, params)` | `workspace.rs` | 732 | Duplicate |
| `list_erf_experiments()` | `workspace.rs` | 1278 | List ERF experiments |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `list_experiments()` | GET | `experiments/` | `api_client.rs` | 1646 |
| `create_experiment()` | POST | `experiments/` | `api_client.rs` | 1658 |
| `get_experiment()` | GET | `experiments/{id}` | `api_client.rs` | 1667 |
| `update_experiment()` | PATCH | `experiments/{id}` | `api_client.rs` | 1674 |
| `delete_experiment()` | DELETE | `experiments/{id}` | `api_client.rs` | 1689 |
| `launch_experiment()` | PUT | `experiments/{id}/launch` | `api_client.rs` | 1696 |
| `conclude_experiment()` | PUT | `experiments/{id}/force_conclude` | `api_client.rs` | 1702 |
| `decide_experiment()` | PATCH | `experiments/{id}/decide` | `api_client.rs` | 1719 |
| `archive_experiment()` | POST | `experiments/{id}/archive` | `api_client.rs` | 1731 |
| `restore_experiment()` | DELETE | `experiments/{id}/archive` | `api_client.rs` | 1737 |
| `duplicate_experiment()` | POST | `experiments/{id}/duplicate` | `api_client.rs` | 1744 |
| `list_erf_experiments()` | GET | `experiments/erf/` | `api_client.rs` | 2779 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `Experiment` | `types/experiments.rs` | 38 | id, name, description, hypothesis, status, variants, metrics, settings, start_date, end_date, creator |
| `ExperimentStatus` | `types/experiments.rs` | 11 | Draft, Active, Concluded, Success, Fail |
| `CreateExperimentParams` | `types/experiments.rs` | 92 | name, description, hypothesis, settings |
| `UpdateExperimentParams` | `types/experiments.rs` | 113 | name, description, variants, metrics, settings, status |
| `ExperimentDecideParams` | `types/experiments.rs` | 150 | success, variant, message |
| `ExperimentConcludeParams` | `types/experiments.rs` | 160 | end_date |
| `DuplicateExperimentParams` | `types/experiments.rs` | 144 | name |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp experiments list` | `commands/experiments.rs` | 20 |
| `mp experiments create` | `commands/experiments.rs` | 24 |
| `mp experiments get` | `commands/experiments.rs` | 28 |
| `mp experiments update` | `commands/experiments.rs` | 34 |
| `mp experiments delete` | `commands/experiments.rs` | 40 |
| `mp experiments launch` | `commands/experiments.rs` | 46 |
| `mp experiments conclude` | `commands/experiments.rs` | 50 |
| `mp experiments decide` | `commands/experiments.rs` | 56 |
| `mp experiments archive` | `commands/experiments.rs` | 62 |
| `mp experiments restore` | `commands/experiments.rs` | 66 |
| `mp experiments duplicate` | `commands/experiments.rs` | 70 |
| `mp experiments erf` | `commands/experiments.rs` | 74 |

---

### Domain 6: Alerts

**Summary**: Custom alert CRUD with history, testing, screenshots, bookmark validation, and bulk operations.

**Complexity**: L | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `list_alerts(bookmark_id, skip_user_filter)` | `workspace.rs` | 743 | List alerts |
| `create_alert(params)` | `workspace.rs` | 754 | Create alert |
| `get_alert(id)` | `workspace.rs` | 759 | Get by ID |
| `update_alert(id, params)` | `workspace.rs` | 764 | Update |
| `delete_alert(id)` | `workspace.rs` | 769 | Delete |
| `bulk_delete_alerts(ids)` | `workspace.rs` | 774 | Bulk delete |
| `get_alert_count(alert_type)` | `workspace.rs` | 779 | Count and limits |
| `get_alert_history(id, ...)` | `workspace.rs` | 784 | Trigger history |
| `test_alert(params)` | `workspace.rs` | 797 | Test alert config |
| `get_alert_screenshot_url(gcs_key)` | `workspace.rs` | 1263 | Screenshot URL |
| `validate_alerts_for_bookmark(params)` | `workspace.rs` | 1268 | Validate alerts |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `list_alerts()` | GET | `alerts/custom/` | `api_client.rs` | 2896 |
| `create_alert()` | POST | `alerts/custom/` | `api_client.rs` | 2917 |
| `get_alert()` | GET | `alerts/custom/{id}/` | `api_client.rs` | 2926 |
| `update_alert()` | PATCH | `alerts/custom/{id}/` | `api_client.rs` | 2932 |
| `delete_alert()` | DELETE | `alerts/custom/{id}/` | `api_client.rs` | 2943 |
| `bulk_delete_alerts()` | POST | `alerts/custom/bulk-delete/` | `api_client.rs` | 2950 |
| `get_alert_count()` | GET | `alerts/custom/alert-count/` | `api_client.rs` | 2969 |
| `get_alert_history()` | GET | `alerts/custom/{id}/history/` | `api_client.rs` | 2985 |
| `test_alert()` | POST | `alerts/custom/test/` | `api_client.rs` | 3034 |
| `get_alert_screenshot_url()` | GET | `alerts/custom/screenshot/` | `api_client.rs` | 2759 |
| `validate_alerts_for_bookmark()` | POST | `alerts/custom/validate-alerts-for-bookmark/` | `api_client.rs` | 2766 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `CustomAlert` | `types/alerts.rs` | 25 | id, name, bookmark, condition, frequency, paused, subscriptions, creator |
| `CreateAlertParams` | `types/alerts.rs` | 83 | bookmark_id, name, condition, frequency, paused, subscriptions |
| `UpdateAlertParams` | `types/alerts.rs` | 97 | name, bookmark_id, condition, frequency, paused |
| `AlertCount` | `types/alerts.rs` | 116 | anomaly_alerts_count, alert_limit, is_below_limit |
| `AlertHistoryResponse` | `types/alerts.rs` | 127 | results, pagination |
| `AlertFrequencyPreset` | `types/alerts.rs` | 147 | Hourly, Daily, Weekly |
| `AlertScreenshotResponse` | `types/alerts.rs` | 206 | signed_url |
| `ValidateAlertsForBookmarkParams` | `types/alerts.rs` | 212 | alert_ids, bookmark_type |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp alerts list` | `commands/alerts.rs` | 26 |
| `mp alerts create` | `commands/alerts.rs` | 32 |
| `mp alerts get` | `commands/alerts.rs` | 36 |
| `mp alerts update` | `commands/alerts.rs` | 42 |
| `mp alerts delete` | `commands/alerts.rs` | 48 |
| `mp alerts bulk-delete` | `commands/alerts.rs` | 55 |
| `mp alerts count` | `commands/alerts.rs` | 59 |
| `mp alerts history` | `commands/alerts.rs` | 63 |
| `mp alerts test` | `commands/alerts.rs` | 67 |
| `mp alerts screenshot` | `commands/alerts.rs` | 73 |
| `mp alerts validate` | `commands/alerts.rs` | 79 |

---

### Domain 7: Annotations

**Summary**: Timeline annotation CRUD with tag management.

**Complexity**: M | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `list_annotations(from_date, to_date, tags)` | `workspace.rs` | 804 | List annotations |
| `create_annotation(params)` | `workspace.rs` | 816 | Create annotation |
| `get_annotation(id)` | `workspace.rs` | 822 | Get by ID |
| `update_annotation(id, params)` | `workspace.rs` | 827 | Update |
| `delete_annotation(id)` | `workspace.rs` | 835 | Delete |
| `list_annotation_tags()` | `workspace.rs` | 840 | List tags |
| `create_annotation_tag(params)` | `workspace.rs` | 845 | Create tag |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `list_annotations()` | GET | `annotations/` | `api_client.rs` | 3044 |
| `create_annotation()` | POST | `annotations/` | `api_client.rs` | 3078 |
| `get_annotation()` | GET | `annotations/{id}/` | `api_client.rs` | 3087 |
| `update_annotation()` | PATCH | `annotations/{id}/` | `api_client.rs` | 3093 |
| `delete_annotation()` | DELETE | `annotations/{id}/` | `api_client.rs` | 3105 |
| `list_annotation_tags()` | GET | `annotations/tags/` | `api_client.rs` | 3112 |
| `create_annotation_tag()` | POST | `annotations/tags/` | `api_client.rs` | 3118 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `Annotation` | `types/annotations.rs` | 11 | id, project_id, date, description, user, tags |
| `AnnotationUser` | `types/annotations.rs` | 27 | id, first_name, last_name |
| `AnnotationTag` | `types/annotations.rs` | 38 | id, name, project_id |
| `CreateAnnotationParams` | `types/annotations.rs` | 52 | date, description, tags, user_id |
| `UpdateAnnotationParams` | `types/annotations.rs` | 63 | description, tags |
| `CreateAnnotationTagParams` | `types/annotations.rs` | 72 | name |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp annotations list` | `commands/annotations.rs` | 25 |
| `mp annotations create` | `commands/annotations.rs` | 29 |
| `mp annotations get` | `commands/annotations.rs` | 33 |
| `mp annotations update` | `commands/annotations.rs` | 39 |
| `mp annotations delete` | `commands/annotations.rs` | 45 |
| `mp annotations tags list` | `commands/annotations.rs` | 125 |
| `mp annotations tags create` | `commands/annotations.rs` | 131 |

---

### Domain 8: Webhooks

**Summary**: Project webhook CRUD with endpoint connectivity testing.

**Complexity**: S | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `list_webhooks()` | `workspace.rs` | 859 | List webhooks |
| `create_webhook(params)` | `workspace.rs` | 864 | Create webhook |
| `update_webhook(id, params)` | `workspace.rs` | 872 | Update |
| `delete_webhook(id)` | `workspace.rs` | 881 | Delete |
| `test_webhook(params)` | `workspace.rs` | 886 | Test connectivity |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `list_webhooks()` | GET | `webhooks/` | `api_client.rs` | 1760 |
| `create_webhook()` | POST | `webhooks/` | `api_client.rs` | 1766 |
| `update_webhook()` | PATCH | `webhooks/{id}/` | `api_client.rs` | 1784 |
| `delete_webhook()` | DELETE | `webhooks/{id}/` | `api_client.rs` | 1815 |
| `test_webhook()` | POST | `webhooks/test/` | `api_client.rs` | 1822 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `ProjectWebhook` | `types/webhooks.rs` | 20 | id, name, url, is_enabled, auth_type, created, modified |
| `WebhookAuthType` | `types/webhooks.rs` | 11 | Basic, Unknown |
| `CreateWebhookParams` | `types/webhooks.rs` | 42 | name, url, auth_type, username, password |
| `UpdateWebhookParams` | `types/webhooks.rs` | 78 | name, url, auth_type, is_enabled |
| `WebhookTestParams` | `types/webhooks.rs` | 130 | url, name, auth_type |
| `WebhookTestResult` | `types/webhooks.rs` | 167 | success, status_code, message |
| `WebhookMutationResult` | `types/webhooks.rs` | 181 | id, name |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp webhooks list` | `commands/webhooks.rs` | 22 |
| `mp webhooks create` | `commands/webhooks.rs` | 26 |
| `mp webhooks update` | `commands/webhooks.rs` | 32 |
| `mp webhooks delete` | `commands/webhooks.rs` | 38 |
| `mp webhooks test` | `commands/webhooks.rs` | 42 |

---

### Domain 9: Data Definitions / Lexicon (Write Operations)

**Summary**: Write operations for event/property definitions, tags, export, tracking metadata, and definition history. Python already reads schemas via discovery; this adds mutation support.

**Complexity**: L | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `get_event_definitions(names)` | `workspace.rs` | 897 | Get event definitions |
| `update_event_definition(name, params)` | `workspace.rs` | 902 | Update event def |
| `delete_event_definition(name)` | `workspace.rs` | 913 | Delete event def |
| `get_property_definitions(names, resource_type)` | `workspace.rs` | 918 | Get property definitions |
| `update_property_definition(name, params)` | `workspace.rs` | 929 | Update property def |
| `list_lexicon_tags()` | `workspace.rs` | 940 | List tags |
| `create_lexicon_tag(params)` | `workspace.rs` | 945 | Create tag |
| `update_lexicon_tag(id, params)` | `workspace.rs` | 950 | Update tag |
| `delete_lexicon_tag(name)` | `workspace.rs` | 958 | Delete tag |
| `bulk_update_event_definitions(params)` | `workspace.rs` | 995 | Bulk update events |
| `bulk_update_property_definitions(params)` | `workspace.rs` | 1005 | Bulk update properties |
| `get_tracking_metadata(event_name)` | `workspace.rs` | 1108 | Tracking metadata |
| `get_event_history(event_name)` | `workspace.rs` | 1113 | Event change history |
| `get_property_history(property_name, entity_type)` | `workspace.rs` | 1118 | Property change history |
| `export_lexicon(export_types)` | `workspace.rs` | 1451 | Export definitions |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `get_event_definitions()` | GET | `data-definitions/events/` | `api_client.rs` | 1881 |
| `update_event_definition()` | PATCH | `data-definitions/events/` | `api_client.rs` | 1893 |
| `delete_event_definition()` | DELETE | `data-definitions/events/` | `api_client.rs` | 1917 |
| `get_property_definitions()` | GET | `data-definitions/properties/` | `api_client.rs` | 1925 |
| `update_property_definition()` | PATCH | `data-definitions/properties/` | `api_client.rs` | 1944 |
| `bulk_update_event_definitions()` | PATCH | `data-definitions/events/` | `api_client.rs` | 2270 |
| `bulk_update_property_definitions()` | PATCH | `data-definitions/properties/` | `api_client.rs` | 2281 |
| `list_lexicon_tags()` | GET | `data-definitions/tags/` | `api_client.rs` | 1966 |
| `create_lexicon_tag()` | POST | `data-definitions/tags/` | `api_client.rs` | 1972 |
| `update_lexicon_tag()` | PATCH | `data-definitions/tags/{id}/` | `api_client.rs` | 1981 |
| `delete_lexicon_tag()` | POST | `data-definitions/tags/` | `api_client.rs` | 1997 |
| `get_tracking_metadata()` | GET | `data-definitions/events/tracking-metadata/` | `api_client.rs` | 2485 |
| `get_event_history()` | GET | `data-definitions/events/{name}/history/` | `api_client.rs` | 2497 |
| `get_property_history()` | GET | `data-definitions/properties/{name}/history/` | `api_client.rs` | 2504 |
| `export_lexicon()` | GET | `data-definitions/export/` | `api_client.rs` | 2820 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `EventDefinition` | `types/data_definitions.rs` | 41 | id, name, display_name, description, hidden, dropped, tags |
| `PropertyDefinition` | `types/data_definitions.rs` | 100 | id, name, resource_type, description, hidden, dropped |
| `UpdateEventDefinitionParams` | `types/data_definitions.rs` | 132 | hidden, dropped, merged, verified, tags, description |
| `UpdatePropertyDefinitionParams` | `types/data_definitions.rs` | 149 | hidden, dropped, merged, sensitive, description |
| `LexiconTag` | `types/data_definitions.rs` | 164 | id, name |
| `CreateTagParams` | `types/data_definitions.rs` | 171 | name |
| `UpdateTagParams` | `types/data_definitions.rs` | 177 | name |
| `BulkUpdateEventsParams` | `types/data_definitions.rs` | 338 | events |
| `BulkUpdatePropertiesParams` | `types/data_definitions.rs` | 367 | properties |
| `TrackingMetadata` | `types/data_definitions.rs` | 580 | tracking metadata fields |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp lexicon events get` | `commands/lexicon.rs` | 60 |
| `mp lexicon events update` | `commands/lexicon.rs` | 60 |
| `mp lexicon events delete` | `commands/lexicon.rs` | 60 |
| `mp lexicon events bulk-update` | `commands/lexicon.rs` | 60 |
| `mp lexicon properties get` | `commands/lexicon.rs` | 80 |
| `mp lexicon properties update` | `commands/lexicon.rs` | 80 |
| `mp lexicon properties bulk-update` | `commands/lexicon.rs` | 80 |
| `mp lexicon tags list/create/update/delete` | `commands/lexicon.rs` | 98 |
| `mp lexicon export` | `commands/lexicon.rs` | 30 |
| `mp lexicon event-history` | `commands/lexicon.rs` | 42 |
| `mp lexicon property-history` | `commands/lexicon.rs` | 45 |
| `mp lexicon tracking-metadata` | `commands/lexicon.rs` | 48 |

---

### Domain 10: Custom Properties

**Summary**: Custom computed property CRUD with validation.

**Complexity**: M | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `list_custom_properties()` | `workspace.rs` | 1462 | List custom properties |
| `create_custom_property(params)` | `workspace.rs` | 1467 | Create |
| `get_custom_property(id)` | `workspace.rs` | 1475 | Get by ID |
| `update_custom_property(id, params)` | `workspace.rs` | 1480 | Update (PUT) |
| `delete_custom_property(id)` | `workspace.rs` | 1489 | Delete |
| `validate_custom_property(params)` | `workspace.rs` | 1494 | Validate formula |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `list_custom_properties()` | GET | `custom_properties/` | `api_client.rs` | 2835 |
| `create_custom_property()` | POST | `custom_properties/` | `api_client.rs` | 2841 |
| `get_custom_property()` | GET | `custom_properties/{id}/` | `api_client.rs` | 2854 |
| `update_custom_property()` | PUT | `custom_properties/{id}/` | `api_client.rs` | 2860 |
| `delete_custom_property()` | DELETE | `custom_properties/{id}/` | `api_client.rs` | 2875 |
| `validate_custom_property()` | POST | `custom_properties/validate/` | `api_client.rs` | 2882 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `CustomProperty` | `types/custom_properties.rs` | 47 | custom_property_id, name, description, resource_type, display_formula, composed_properties |
| `CustomPropertyResourceType` | `types/custom_properties.rs` | 31 | Events, UserProfiles, GroupProfiles |
| `CreateCustomPropertyParams` | `types/custom_properties.rs` | 91 | name, resource_type, display_formula, composed_properties, behavior |
| `UpdateCustomPropertyParams` | `types/custom_properties.rs` | 161 | name, description, display_formula, composed_properties |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp custom-properties list` | `commands/custom_properties.rs` | 21 |
| `mp custom-properties get` | `commands/custom_properties.rs` | 23 |
| `mp custom-properties create` | `commands/custom_properties.rs` | 25 |
| `mp custom-properties update` | `commands/custom_properties.rs` | 27 |
| `mp custom-properties delete` | `commands/custom_properties.rs` | 29 |
| `mp custom-properties validate` | `commands/custom_properties.rs` | 31 |

---

### Domain 11: Custom Events

**Summary**: Custom event management (list, update, delete). Read through discovery; this adds mutation.

**Complexity**: S | **Dependencies**: Domain 0a, 0b

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| Uses data-definitions endpoints for custom events — custom events are managed through event definitions with `custom_event_id` field |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp custom-events list` | `commands/custom_events.rs` | 21 |
| `mp custom-events update` | `commands/custom_events.rs` | 23 |
| `mp custom-events delete` | `commands/custom_events.rs` | 25 |

---

### Domain 12: Drop Filters

**Summary**: Event drop filter CRUD with account limits.

**Complexity**: S | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `list_drop_filters()` | `workspace.rs` | 964 | List drop filters |
| `create_drop_filter(params)` | `workspace.rs` | 969 | Create filter |
| `update_drop_filter(params)` | `workspace.rs` | 977 | Update filter |
| `delete_drop_filter(id)` | `workspace.rs` | 985 | Delete filter |
| `get_drop_filter_limits()` | `workspace.rs` | 990 | Account limits |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `list_drop_filters()` | GET | `data-definitions/events/drop-filters/` | `api_client.rs` | 2228 |
| `create_drop_filter()` | POST | `data-definitions/events/drop-filters/` | `api_client.rs` | 2234 |
| `update_drop_filter()` | PATCH | `data-definitions/events/drop-filters/` | `api_client.rs` | 2245 |
| `delete_drop_filter()` | DELETE | `data-definitions/events/drop-filters/` | `api_client.rs` | 2256 |
| `get_drop_filter_limits()` | GET | `data-definitions/events/drop-filters/limits/` | `api_client.rs` | 2264 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `DropFilter` | `types/data_definitions.rs` | 295 | id, event_name, filters, active, display_name |
| `CreateDropFilterParams` | `types/data_definitions.rs` | 313 | event_name, filters |
| `UpdateDropFilterParams` | `types/data_definitions.rs` | 320 | id, event_name, filters, active |
| `DropFilterLimitsResponse` | `types/data_definitions.rs` | 332 | filter_limit |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp drop-filters list` | `commands/drop_filters.rs` | 18 |
| `mp drop-filters create` | `commands/drop_filters.rs` | 20 |
| `mp drop-filters update` | `commands/drop_filters.rs` | 22 |
| `mp drop-filters delete` | `commands/drop_filters.rs` | 24 |

---

### Domain 13: Lookup Tables

**Summary**: Lookup table CRUD with 3-step CSV upload (get URL → upload to GCS → mark ready) and download.

**Complexity**: M | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `list_lookup_tables(data_group_id)` | `workspace.rs` | 1295 | List tables |
| `mark_lookup_table_ready(params)` | `workspace.rs` | 1300 | Mark uploaded table ready |
| `update_lookup_table(data_group_id, params)` | `workspace.rs` | 1308 | Update table |
| `delete_lookup_tables(data_group_ids)` | `workspace.rs` | 1319 | Delete tables |
| `get_lookup_upload_url(content_type)` | `workspace.rs` | 1326 | Get signed upload URL |
| `get_lookup_upload_status(upload_id)` | `workspace.rs` | 1331 | Check upload status |
| `upload_lookup_table(params)` | `workspace.rs` | 1344 | Full 3-step upload flow |
| `download_lookup_table(data_group_id, ...)` | `workspace.rs` | 1433 | Download as CSV bytes |
| `get_lookup_download_url(data_group_id)` | `workspace.rs` | 1129 | Get download URL |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `list_lookup_tables()` | GET | `data-definitions/lookup-tables/` | `api_client.rs` | 2007 |
| `mark_lookup_table_ready()` | POST | `data-definitions/lookup-tables/` | `api_client.rs` | 2020 |
| `update_lookup_table()` | PATCH | `data-definitions/lookup-tables/` | `api_client.rs` | 2035 |
| `delete_lookup_tables()` | DELETE | `data-definitions/lookup-tables/` | `api_client.rs` | 2057 |
| `get_lookup_upload_url()` | GET | `data-definitions/lookup-tables/upload-url/` | `api_client.rs` | 2071 |
| `get_lookup_upload_status()` | GET | `data-definitions/lookup-tables/upload-status/` | `api_client.rs` | 2079 |
| `upload_to_signed_url()` | PUT | `{signed_gcs_url}` (external) | `api_client.rs` | 2090 |
| `register_lookup_table()` | POST | `data-definitions/lookup-tables/` (form) | `api_client.rs` | 2117 |
| `download_lookup_table()` | GET | `data-definitions/lookup-tables/download/` | `api_client.rs` | 2181 |
| `get_lookup_download_url()` | GET | `data-definitions/lookup-tables/download-url/` | `api_client.rs` | 2524 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `LookupTable` | `types/data_definitions.rs` | 188 | id, name, token, created_at, has_mapped_properties |
| `UploadLookupTableParams` | `types/data_definitions.rs` | 245 | name, file_path, data_group_id |
| `MarkLookupTableReadyParams` | `types/data_definitions.rs` | 259 | name, key, data_group_id |
| `LookupTableUploadUrl` | `types/data_definitions.rs` | 285 | url, path, key |
| `UpdateLookupTableParams` | `types/data_definitions.rs` | 278 | name |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp lookup-tables list` | `commands/lookup_tables.rs` | 24 |
| `mp lookup-tables create` | `commands/lookup_tables.rs` | 32 |
| `mp lookup-tables update` | `commands/lookup_tables.rs` | 36 |
| `mp lookup-tables delete` | `commands/lookup_tables.rs` | 41 |
| `mp lookup-tables upload-url` | `commands/lookup_tables.rs` | 48 |
| `mp lookup-tables download` | `commands/lookup_tables.rs` | 52 |
| `mp lookup-tables download-url` | `commands/lookup_tables.rs` | 59 |

---

### Domain 14: Schema Registry

**Summary**: Schema registry CRUD for data governance (create, update, delete schemas with bulk variants).

**Complexity**: M | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `list_schema_registry(entity_type)` | `workspace.rs` | 1136 | List schemas |
| `create_schema(entity_type, entity_name, schema_json)` | `workspace.rs` | 1141 | Create schema |
| `create_schemas_bulk(params)` | `workspace.rs` | 1153 | Bulk create |
| `update_schema(entity_type, entity_name, schema_json)` | `workspace.rs` | 1161 | Update schema |
| `update_schemas_bulk(params)` | `workspace.rs` | 1173 | Bulk update |
| `delete_schemas(entity_type, entity_name)` | `workspace.rs` | 1181 | Delete schemas |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `list_schema_registry()` | GET | `schemas/` | `api_client.rs` | 2538 |
| `create_schema()` | POST | `schemas/{type}/{name}/` | `api_client.rs` | 2550 |
| `create_schemas_bulk()` | POST | `schemas/` | `api_client.rs` | 2566 |
| `update_schema()` | PATCH | `schemas/{type}/{name}/` | `api_client.rs` | 2577 |
| `update_schemas_bulk()` | PATCH | `schemas/` | `api_client.rs` | 2593 |
| `delete_schemas()` | DELETE | `schemas/` | `api_client.rs` | 2604 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `SchemaEntity` | `types/discovery.rs` | 66 | entity_type, name, schema_json |
| `SchemaEntry` | `types/discovery.rs` | 75 | name, entity_type, version, schema_json |
| `BulkCreateSchemasParams` | `types/discovery.rs` | 86 | truncate, entity_type, entries |
| `BulkCreateSchemasResponse` | `types/discovery.rs` | 96 | added, deleted |
| `DeleteSchemasResponse` | `types/discovery.rs` | 118 | delete_count |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp schemas list` | `commands/schemas.rs` | 18 |
| `mp schemas create` | `commands/schemas.rs` | 20 |
| `mp schemas update` | `commands/schemas.rs` | 24 |
| `mp schemas delete` | `commands/schemas.rs` | 28 |

---

### Domain 15: Schema Enforcement & Data Governance

**Summary**: Schema enforcement configuration, data audit, volume anomalies, and event deletion requests.

**Complexity**: M | **Dependencies**: Domain 0a, 0b

#### Rust Workspace Methods

| Method | Rust File | Line | Description |
|--------|-----------|------|-------------|
| `get_schema_enforcement(fields)` | `workspace.rs` | 1015 | Get enforcement config |
| `init_schema_enforcement(params)` | `workspace.rs` | 1023 | Initialize enforcement |
| `update_schema_enforcement(params)` | `workspace.rs` | 1031 | Partial update |
| `replace_schema_enforcement(params)` | `workspace.rs` | 1039 | Full replacement |
| `delete_schema_enforcement()` | `workspace.rs` | 1047 | Delete enforcement |
| `run_audit()` | `workspace.rs` | 1052 | Full data audit |
| `run_audit_events_only()` | `workspace.rs` | 1057 | Events-only audit |
| `list_data_volume_anomalies(query_params)` | `workspace.rs` | 1062 | List anomalies |
| `update_anomaly(params)` | `workspace.rs` | 1072 | Update anomaly status |
| `bulk_update_anomalies(params)` | `workspace.rs` | 1077 | Bulk update anomalies |
| `list_deletion_requests()` | `workspace.rs` | 1082 | List deletion requests |
| `create_deletion_request(params)` | `workspace.rs` | 1087 | Create deletion request |
| `cancel_deletion_request(id)` | `workspace.rs` | 1095 | Cancel pending deletion |
| `preview_deletion_filters(params)` | `workspace.rs` | 1100 | Preview deletion filters |

#### Rust API Client Methods

| Method | HTTP | Endpoint | Rust File | Line |
|--------|------|----------|-----------|------|
| `get_schema_enforcement()` | GET | `data-definitions/schema/` | `api_client.rs` | 2294 |
| `init_schema_enforcement()` | POST | `data-definitions/schema/` | `api_client.rs` | 2305 |
| `update_schema_enforcement()` | PATCH | `data-definitions/schema/` | `api_client.rs` | 2316 |
| `replace_schema_enforcement()` | PUT | `data-definitions/schema/` | `api_client.rs` | 2327 |
| `delete_schema_enforcement()` | DELETE | `data-definitions/schema/` | `api_client.rs` | 2338 |
| `run_audit()` | GET | `data-definitions/audit/` | `api_client.rs` | 2347 |
| `run_audit_events_only()` | GET | `data-definitions/audit-events-only/` | `api_client.rs` | 2356 |
| `list_data_volume_anomalies()` | GET | `data-definitions/data-volume-anomalies/` | `api_client.rs` | 2404 |
| `update_anomaly()` | PATCH | `data-definitions/data-volume-anomalies/` | `api_client.rs` | 2428 |
| `bulk_update_anomalies()` | PATCH | `data-definitions/data-volume-anomalies/bulk/` | `api_client.rs` | 2436 |
| `list_deletion_requests()` | GET | `data-definitions/events/deletion-requests/` | `api_client.rs` | 2446 |
| `create_deletion_request()` | POST | `data-definitions/events/deletion-requests/` | `api_client.rs` | 2452 |
| `cancel_deletion_request()` | DELETE | `data-definitions/events/deletion-requests/` | `api_client.rs` | 2463 |
| `preview_deletion_filters()` | POST | `data-definitions/events/deletion-requests/preview-filters/` | `api_client.rs` | 2471 |

#### Rust Types to Port

| Type | Rust File | Line | Key Fields |
|------|-----------|------|------------|
| `SchemaEnforcementConfig` | `types/data_definitions.rs` | 392 | enforcement config fields |
| `InitSchemaEnforcementParams` | `types/data_definitions.rs` | 425 | init params |
| `UpdateSchemaEnforcementParams` | `types/data_definitions.rs` | 432 | update params |
| `ReplaceSchemaEnforcementParams` | `types/data_definitions.rs` | 446 | replace params |
| `AuditResponse` | `types/data_definitions.rs` | 458 | audit violations |
| `DataVolumeAnomaly` | `types/data_definitions.rs` | 484 | anomaly details |
| `UpdateAnomalyParams` | `types/data_definitions.rs` | 517 | status update params |
| `BulkUpdateAnomalyParams` | `types/data_definitions.rs` | 525 | bulk update params |
| `EventDeletionRequest` | `types/data_definitions.rs` | 543 | deletion request details |
| `CreateDeletionRequestParams` | `types/data_definitions.rs` | 560 | creation params |
| `PreviewDeletionFiltersParams` | `types/data_definitions.rs` | 570 | preview params |

#### CLI Commands

| Command | Rust File | Line |
|---------|-----------|------|
| `mp lexicon enforcement get/init/update/replace/delete` | `commands/lexicon.rs` | 247 |
| `mp lexicon audit` | `commands/lexicon.rs` | 34 |
| `mp lexicon anomalies list/update/bulk-update` | `commands/lexicon.rs` | 305 |
| `mp lexicon deletion-requests list/create/cancel/preview` | `commands/lexicon.rs` | 349 |

---

## Implementation Phases

### Phase 0: Architectural Prerequisites (OAuth + App API Infrastructure)
**Domains**: 0a + 0b | **Est. LOC**: ~1,500 impl + ~1,500 tests

| File (Python) | Action | Rust Reference |
|---------------|--------|----------------|
| `_internal/auth/__init__.py` | Create | `auth/mod.rs` |
| `_internal/auth/pkce.py` | Create | `auth/pkce.rs` |
| `_internal/auth/token.py` | Create | `auth/token.rs:54` |
| `_internal/auth/storage.py` | Create | `auth/storage.rs:11` |
| `_internal/auth/callback_server.py` | Create | `auth/callback_server.rs` |
| `_internal/auth/client_registration.py` | Create | `auth/client_registration.rs:43` |
| `_internal/auth/flow.py` | Create | `auth/flow.rs:44` |
| `_internal/config.py` | Modify — add `AuthMethod` enum, extend `Credentials` | `config.rs` |
| `_internal/api_client.py` | Modify — add `app_request()`, Bearer auth, workspace scoping | `api_client.rs:302-560` |
| `_internal/pagination.py` | Create | `types/pagination.rs:8-44` |
| `types.py` | Add `PublicWorkspace` | `types/common.rs:334` |
| `workspace.py` | Add `list_workspaces()`, `resolve_workspace_id()` | `workspace.rs:304-309` |
| `exceptions.py` | Add `OAuthError` | — |
| `cli/main.py` | Add `--workspace-id` global option | `cli.rs:47` |
| `cli/commands/auth.py` | Add `login`, `logout`, `status`, `token` subcommands | `commands/auth.rs:52-58` |

### Phase 1: Core Entity CRUD (Dashboards + Reports + Cohorts)
**Domains**: 1 + 2 + 3 | **Est. LOC**: ~2,500 impl + ~2,500 tests

| File (Python) | Action | Rust Reference |
|---------------|--------|----------------|
| `types.py` | Add Dashboard, Bookmark, Cohort types (~14 models) | `types/dashboard.rs`, `types/bookmark.rs`, `types/cohorts.rs` |
| `_internal/api_client.py` | Add ~35 API methods | `api_client.rs:1160-1510` |
| `workspace.py` | Add ~27 methods | `workspace.rs:407-578` |
| `cli/commands/dashboards.py` | Create (17 subcommands) | `commands/dashboards.rs` |
| `cli/commands/reports.py` | Create (10 subcommands) | `commands/reports.rs` |
| `cli/commands/cohorts.py` | Create (7 subcommands) | `commands/cohorts.rs` |

### Phase 2: Feature Management (Flags + Experiments)
**Domains**: 4 + 5 | **Est. LOC**: ~2,000 impl + ~2,000 tests

| File (Python) | Action | Rust Reference |
|---------------|--------|----------------|
| `types.py` | Add FeatureFlag, Experiment types (~19 models) | `types/feature_flags.rs`, `types/experiments.rs` |
| `_internal/api_client.py` | Add ~23 API methods | `api_client.rs:1528-1760` |
| `workspace.py` | Add ~23 methods | `workspace.rs:592-732` |
| `cli/commands/flags.py` | Create (11 subcommands) | `commands/flags.rs` |
| `cli/commands/experiments.py` | Create (12 subcommands) | `commands/experiments.rs` |

### Phase 3: Operational Tooling (Alerts + Annotations + Webhooks)
**Domains**: 6 + 7 + 8 | **Est. LOC**: ~1,800 impl + ~1,800 tests

| File (Python) | Action | Rust Reference |
|---------------|--------|----------------|
| `types.py` | Add Alert, Annotation, Webhook types (~20 models) | `types/alerts.rs`, `types/annotations.rs`, `types/webhooks.rs` |
| `_internal/api_client.py` | Add ~23 API methods | `api_client.rs:2759-3130` |
| `workspace.py` | Add ~23 methods | `workspace.rs:743-886` |
| `cli/commands/alerts.py` | Create (11 subcommands) | `commands/alerts.rs` |
| `cli/commands/annotations.py` | Create (7 subcommands) | `commands/annotations.rs` |
| `cli/commands/webhooks.py` | Create (5 subcommands) | `commands/webhooks.rs` |

### Phase 4: Data Governance (Lexicon + Custom + Drop Filters + Lookup Tables)
**Domains**: 9 + 10 + 11 + 12 + 13 | **Est. LOC**: ~2,500 impl + ~2,500 tests

| File (Python) | Action | Rust Reference |
|---------------|--------|----------------|
| `types.py` | Add definitions, custom property, drop filter, lookup table types (~25 models) | `types/data_definitions.rs`, `types/custom_properties.rs` |
| `_internal/api_client.py` | Add ~38 API methods | `api_client.rs:1881-2530` |
| `workspace.py` | Add ~38 methods | `workspace.rs:897-1462` |
| `cli/commands/lexicon.py` | Create (15+ subcommands) | `commands/lexicon.rs` |
| `cli/commands/custom_properties.py` | Create (6 subcommands) | `commands/custom_properties.rs` |
| `cli/commands/custom_events.py` | Create (3 subcommands) | `commands/custom_events.rs` |
| `cli/commands/drop_filters.py` | Create (4 subcommands) | `commands/drop_filters.rs` |
| `cli/commands/lookup_tables.py` | Create (7 subcommands) | `commands/lookup_tables.rs` |

### Phase 5: Schema & Advanced (Schema Registry + Governance + Workspaces)
**Domains**: 14 + 15 | **Est. LOC**: ~1,200 impl + ~1,200 tests

| File (Python) | Action | Rust Reference |
|---------------|--------|----------------|
| `types.py` | Add schema, governance types (~16 models) | `types/discovery.rs:66-118`, `types/data_definitions.rs:392-580` |
| `_internal/api_client.py` | Add ~20 API methods | `api_client.rs:2294-2620` |
| `workspace.py` | Add ~20 methods | `workspace.rs:1015-1181` |
| `cli/commands/schemas.py` | Create (4 subcommands) | `commands/schemas.rs` |
| `cli/commands/lexicon.py` | Add enforcement + governance subcommands | `commands/lexicon.rs:247-410` |

---

## Architectural Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | OAuth as `_internal/auth/` module (7 files) | Mirrors Rust's `auth/` module structure; isolates complexity |
| 2 | Synchronous API (`httpx.Client`) | Python library is synchronous; OAuth callback server uses `threading` |
| 3 | Extend `MixpanelAPIClient` (not new class) | `"app"` URLs already in `ENDPOINTS` dict (`api_client.py:92-104`) |
| 4 | Credential resolution: env > OAuth > named > default | Extends existing order; OAuth becomes preferred when available |
| 5 | Types stay in `types.py` until split needed | Start with single file; split to `types/` package if >5000 lines |
| 6 | One CLI file per domain | `cli/commands/{domain}.py` — mirrors Rust's `commands/` structure |
| 7 | `respx` for HTTP mocking | Python equivalent of Rust's `wiremock`; transport-level mocking for `httpx` |
| 8 | Frozen Pydantic BaseModel for new types | Matches existing pattern in `types.py` for immutable result types |

---

## Cross-Cutting Concerns

### Testing Strategy (per phase)
- **Unit tests**: `tests/test_{module}.py` with `respx` mocks
- **Integration tests**: End-to-end with mock transport
- **CLI tests**: `subprocess` + `assert` (matches existing pattern)
- **Property-based tests**: Hypothesis for type round-trips (serde equivalence)
- **Coverage target**: 90% per `just test-cov`

### Type Conventions
- Frozen Pydantic `BaseModel` with `ConfigDict(frozen=True)`
- `SecretStr` for sensitive fields (OAuth tokens, webhook passwords)
- Optional `.to_dict()` for JSON serialization
- Optional `.df` property for DataFrame conversion (query results only)
- `Extra.allow` via `extra` HashMap catch-all for forward compatibility

### Error Handling
- New: `OAuthError(MixpanelDataError)` for auth failures
- New: `WorkspaceScopeError(MixpanelDataError)` for workspace resolution failures
- Existing `APIError` hierarchy handles 4xx/5xx from App API endpoints

### Output Formatting
- All 5 existing formatters (json, jsonl, table, csv, plain) apply to new commands
- No new formatters needed

---

## Reference File Mapping

| Rust Source | Python Target |
|-------------|---------------|
| `mixpanel_data/src/auth/` (7 files) | `_internal/auth/` (7 files, new) |
| `mixpanel_data/src/types/dashboard.rs` | `types.py` (Dashboard models) |
| `mixpanel_data/src/types/bookmark.rs` | `types.py` (Bookmark models) |
| `mixpanel_data/src/types/cohorts.rs` | `types.py` (Cohort models) |
| `mixpanel_data/src/types/feature_flags.rs` | `types.py` (FeatureFlag models) |
| `mixpanel_data/src/types/experiments.rs` | `types.py` (Experiment models) |
| `mixpanel_data/src/types/alerts.rs` | `types.py` (Alert models) |
| `mixpanel_data/src/types/annotations.rs` | `types.py` (Annotation models) |
| `mixpanel_data/src/types/webhooks.rs` | `types.py` (Webhook models) |
| `mixpanel_data/src/types/custom_properties.rs` | `types.py` (CustomProperty models) |
| `mixpanel_data/src/types/data_definitions.rs` | `types.py` (Lexicon/governance models) |
| `mixpanel_data/src/types/pagination.rs` | `_internal/pagination.py` (new) |
| `mixpanel_data/src/types/common.rs` | `types.py` (PublicWorkspace, Permissions) |
| `mixpanel_data/src/internal/api_client.rs` | `_internal/api_client.py` |
| `mixpanel_data/src/workspace.rs` | `workspace.py` |
| `mp_cli/src/commands/dashboards.rs` | `cli/commands/dashboards.py` (new) |
| `mp_cli/src/commands/reports.rs` | `cli/commands/reports.py` (new) |
| `mp_cli/src/commands/cohorts.rs` | `cli/commands/cohorts.py` (new) |
| `mp_cli/src/commands/flags.rs` | `cli/commands/flags.py` (new) |
| `mp_cli/src/commands/experiments.rs` | `cli/commands/experiments.py` (new) |
| `mp_cli/src/commands/alerts.rs` | `cli/commands/alerts.py` (new) |
| `mp_cli/src/commands/annotations.rs` | `cli/commands/annotations.py` (new) |
| `mp_cli/src/commands/webhooks.rs` | `cli/commands/webhooks.py` (new) |
| `mp_cli/src/commands/lexicon.rs` | `cli/commands/lexicon.py` (new) |
| `mp_cli/src/commands/custom_properties.rs` | `cli/commands/custom_properties.py` (new) |
| `mp_cli/src/commands/custom_events.rs` | `cli/commands/custom_events.py` (new) |
| `mp_cli/src/commands/drop_filters.rs` | `cli/commands/drop_filters.py` (new) |
| `mp_cli/src/commands/lookup_tables.rs` | `cli/commands/lookup_tables.py` (new) |
| `mp_cli/src/commands/schemas.rs` | `cli/commands/schemas.py` (new) |

---

## Totals

| Category | Count |
|----------|-------|
| New Workspace methods | ~98 |
| New API client methods | ~137 |
| New Pydantic types | ~54 |
| New CLI command groups | 15 |
| New CLI subcommands | ~85 |
| New Python files | ~24 (7 auth + 1 pagination + 15 CLI commands + 1 test fixtures) |
| Modified Python files | ~5 (api_client.py, config.py, workspace.py, types.py, exceptions.py, cli/main.py) |
| Est. implementation LOC | ~11,500 |
| Est. test LOC | ~11,500 |
| **Est. total LOC** | **~23,000** |
