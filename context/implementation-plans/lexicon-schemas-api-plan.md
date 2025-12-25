# Implementation Plan: Lexicon Schemas API (Read Operations)

**Phase**: Discovery Service Enhancement
**Status**: Ready for Implementation
**Created**: 2025-12-24
**Updated**: 2025-12-24 (revised with Lexicon-prefixed type names, app endpoint, table_schema rename)
**Input**: Add read-only Lexicon Schemas API support to DiscoveryService
**Spec**: See `/specs/012-lexicon-schemas/` for complete specification artifacts

---

## Overview

This implementation plan extends the Discovery Service to support Mixpanel's Lexicon Schemas API for retrieving data dictionary definitions. The Lexicon API enables AI agents and users to:

1. **Explore event/profile schemas** — Retrieve schema definitions including descriptions, property types, and metadata
2. **Filter by entity type** — List only event schemas or only profile schemas
3. **Get specific schemas** — Retrieve a single schema by entity type and name

**Important Distinction**: The Lexicon Schemas API returns only events/properties that have explicit schemas defined (via API, CSV import, or UI metadata additions). It does NOT return all events visible in the Lexicon UI, which also shows events transmitted in the last 30 days.

**Breaking Change**: This feature includes renaming existing `Workspace.schema(table)` to `Workspace.table_schema(table)` to avoid naming confusion with the new Lexicon schema methods.

---

## API Endpoint Coverage

### Read Endpoints (Scope of This Plan)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/projects/{projectId}/schemas` | GET | List all schemas in project |
| `/projects/{projectId}/schemas/{entityType}` | GET | List schemas for entity type |
| `/projects/{projectId}/schemas/{entityType}/{name}` | GET | Get schema for specific entity |

### Write Endpoints (Out of Scope)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/projects/{projectId}/schemas` | POST | Create/replace multiple schemas |
| `/projects/{projectId}/schemas` | DELETE | Delete all schemas |
| `/projects/{projectId}/schemas/{entityType}` | DELETE | Delete schemas by entity type |
| `/projects/{projectId}/schemas/{entityType}/{name}` | POST | Create/replace single schema |
| `/projects/{projectId}/schemas/{entityType}/{name}` | DELETE | Delete specific schema |

---

## API Details

### Base URL

The Lexicon API uses a different base path than the Query API:

| Region | Base URL |
|--------|----------|
| US | `https://mixpanel.com/api/app` |
| EU | `https://eu.mixpanel.com/api/app` |
| IN | `https://in.mixpanel.com/api/app` |

**Note**: This requires adding a new `"app"` endpoint type to the `ENDPOINTS` configuration (named after the base path, as multiple Mixpanel APIs use `/api/app`).

### Authentication

Service Account authentication via HTTP Basic Auth (same as other APIs).

### Rate Limits

- **5 requests per minute** (significantly lower than Query API)
- Max 4,000 events/properties per minute
- Applies to the Lexicon API as a whole

### Entity Types

The `entityType` path parameter accepts two values:
- `"event"` — Event schemas
- `"profile"` — User profile property schemas

---

## Response Structures

### List All Schemas / List by Entity Type

```json
{
  "results": [
    {
      "entityType": "event",
      "name": "Purchase",
      "schemaJson": {
        "description": "User completes a purchase",
        "properties": {
          "amount": {
            "type": "number",
            "description": "Purchase amount in USD"
          },
          "product_id": {
            "type": "string"
          }
        },
        "metadata": {
          "com.mixpanel": {
            "$source": "api",
            "displayName": "Purchase Event",
            "tags": ["core", "revenue"],
            "hidden": false,
            "dropped": false,
            "contacts": ["owner@company.com"],
            "teamContacts": ["Analytics Team"]
          }
        }
      }
    }
  ],
  "status": "ok"
}
```

### Get Single Schema

```json
{
  "results": {
    "entityType": "event",
    "name": "Purchase",
    "schemaJson": { ... }
  },
  "status": "ok"
}
```

### Schema Property Types

Valid JSON Schema types for properties:
- `"string"`
- `"number"`
- `"boolean"`
- `"array"`
- `"object"`
- `"integer"`
- `"null"`

---

## User Scenarios & Acceptance Criteria

### US-1: List All Schemas (P1)

**As** an AI coding agent or analyst, **I want** to list all schemas in a project **so that** I can understand the documented data structure.

**Acceptance Criteria:**
1. **Given** valid credentials, **When** I call `ws.lexicon_schemas()`, **Then** I receive a list of `LexiconSchema` objects.
2. **Given** a project with no schemas, **When** I call `ws.lexicon_schemas()`, **Then** I receive an empty list (not an error).
3. **Given** valid credentials, **When** I call `ws.lexicon_schemas()` multiple times, **Then** subsequent calls return cached results without additional network requests.
4. **Given** each `LexiconSchema`, **Then** it contains `entity_type` (Literal["event", "profile"]), `name` (str), and `schema_json` (LexiconDefinition).

**Testable Independently:** Yes — mock API response, verify transformation and caching.

---

### US-2: List Schemas by Entity Type (P1)

**As** an AI coding agent or analyst, **I want** to list schemas filtered by entity type **so that** I can focus on either events or profile properties.

**Acceptance Criteria:**
1. **Given** valid credentials and entity_type="event", **When** I call `ws.lexicon_schemas(entity_type="event")`, **Then** I receive only event schemas.
2. **Given** entity_type="profile", **When** I call `ws.lexicon_schemas(entity_type="profile")`, **Then** I receive only profile schemas.
3. **Given** an entity type with no schemas, **When** I call `ws.lexicon_schemas()`, **Then** I receive an empty list.
4. **Given** different entity_type values, **When** I call `ws.lexicon_schemas()`, **Then** results are cached separately per entity_type.

**Testable Independently:** Yes — mock API response, verify filtering and separate caching.

---

### US-3: Get Single Schema (P2)

**As** an AI coding agent or analyst, **I want** to get a specific schema by entity type and name **so that** I can inspect its detailed structure.

**Acceptance Criteria:**
1. **Given** valid credentials and existing schema, **When** I call `ws.lexicon_schema("event", "Purchase")`, **Then** I receive a single `LexiconSchema` object.
2. **Given** a non-existent schema, **When** I call `ws.lexicon_schema()`, **Then** I receive `None` (not an error).
3. **Given** valid credentials, **When** I call `ws.lexicon_schema()` multiple times with same parameters, **Then** subsequent calls return cached results.
4. **Given** different (entity_type, name) combinations, **Then** each is cached separately.

**Testable Independently:** Yes — mock API response, verify transformation and caching.

---

## Key Entities (Data Model)

### EntityType (Type Alias)

```python
EntityType = Literal["event", "profile"]
```

### LexiconMetadata

```python
LexiconMetadata
├── source: str | None           # "$source" field (e.g., "api")
├── display_name: str | None     # Human-readable display name
├── tags: list[str]              # Categorization tags
├── hidden: bool                 # Whether hidden in Mixpanel UI
├── dropped: bool                # Whether data is dropped/ignored
├── contacts: list[str]          # Owner email addresses
├── team_contacts: list[str]     # Team ownership
```

### LexiconProperty

```python
LexiconProperty
├── type: str                    # JSON Schema type (string, number, etc.)
├── description: str | None      # Property description
├── metadata: LexiconMetadata | None  # Mixpanel-specific metadata
```

### LexiconDefinition

```python
LexiconDefinition
├── description: str | None                  # Entity description
├── properties: dict[str, LexiconProperty]   # Property definitions
├── metadata: LexiconMetadata | None         # Entity-level metadata
```

### LexiconSchema

```python
LexiconSchema
├── entity_type: EntityType      # "event" or "profile"
├── name: str                    # Event/property name
├── schema_json: LexiconDefinition  # Full schema definition
```

---

## Component Architecture

### Endpoint Configuration Change

```python
ENDPOINTS: dict[str, dict[str, str]] = {
    "us": {
        "query": "https://mixpanel.com/api/query",
        "export": "https://data.mixpanel.com/api/2.0",
        "engage": "https://mixpanel.com/api/2.0/engage",
        "app": "https://mixpanel.com/api/app",  # NEW (for Lexicon and other /api/app APIs)
    },
    "eu": {
        "query": "https://eu.mixpanel.com/api/query",
        "export": "https://data-eu.mixpanel.com/api/2.0",
        "engage": "https://eu.mixpanel.com/api/2.0/engage",
        "app": "https://eu.mixpanel.com/api/app",  # NEW
    },
    "in": {
        "query": "https://in.mixpanel.com/api/query",
        "export": "https://data-in.mixpanel.com/api/2.0",
        "engage": "https://in.mixpanel.com/api/2.0/engage",
        "app": "https://in.mixpanel.com/api/app",  # NEW
    },
}
```

### API Client Methods

```
MixpanelAPIClient (api_client.py)
├── Discovery Section
│   ├── get_events()               # Existing
│   ├── get_event_properties()     # Existing
│   ├── get_property_values()      # Existing
│   ├── get_top_events()           # Existing
│   ├── list_funnels()             # Existing
│   ├── list_cohorts()             # Existing
│   ├── list_schemas()             # NEW: GET /projects/{id}/schemas
│   ├── list_schemas_for_entity()  # NEW: GET /projects/{id}/schemas/{entityType}
│   └── get_schema()               # NEW: GET /projects/{id}/schemas/{entityType}/{name}
```

### DiscoveryService Methods

```
DiscoveryService (discovery.py)
├── list_events()                 # Existing
├── list_properties(event)        # Existing
├── list_property_values(...)     # Existing
├── list_funnels()                # Existing
├── list_cohorts()                # Existing
├── list_top_events(...)          # Existing
├── list_schemas()                # NEW: All schemas (cached)
├── list_schemas(entity_type)     # NEW: By entity type (cached separately)
├── get_schema(entity_type, name) # NEW: Single schema (cached)
└── clear_cache()                 # Existing (clears all)
```

### Workspace Public API

```
Workspace (workspace.py)
├── events()                           # Existing
├── properties(event)                  # Existing
├── property_values(...)               # Existing
├── funnels()                          # Existing
├── cohorts()                          # Existing
├── top_events(...)                    # Existing
├── table_schema(table)                # RENAMED from schema() - local DuckDB table schema
├── lexicon_schemas(entity_type=None)  # NEW: List Lexicon schemas
├── lexicon_schema(entity_type, name)  # NEW: Get single Lexicon schema
└── clear_discovery_cache()            # Existing
```

---

## Service Placement & Caching

| Method | Characteristic | Service | Caching |
|--------|---------------|---------|---------|
| list_schemas() | Static definitions | DiscoveryService | ✅ Cached |
| list_schemas(entity_type) | Static definitions | DiscoveryService | ✅ Cached (per type) |
| get_schema(type, name) | Static definition | DiscoveryService | ✅ Cached (per pair) |

**Caching Rationale:**
- Schemas are relatively static (updated via API, CSV import, or manual UI edits)
- Matches existing caching pattern for funnels/cohorts
- Cache keys: `("list_schemas",)`, `("list_schemas", entity_type)`, `("get_schema", entity_type, name)`

---

## Success Criteria

| ID | Metric | Target |
|----|--------|--------|
| SC-1 | All 3 new DiscoveryService methods implemented | 100% |
| SC-2 | All 3 new API client methods implemented | 100% |
| SC-3 | Workspace facade exposes lexicon_schemas()/lexicon_schema() | 100% |
| SC-4 | New types created: LexiconSchema, LexiconDefinition, LexiconProperty, LexiconMetadata | 100% |
| SC-5 | Cached methods make single API call per session | Verify in tests |
| SC-6 | All result types have `.to_dict()` serialization | 100% |
| SC-7 | Unit test coverage for new code | ≥90% |
| SC-8 | mypy --strict passes | Zero errors |
| SC-9 | ruff check passes | Zero errors |
| SC-10 | Existing schema() renamed to table_schema() | 100% |

---

## Dependencies

- **Phase 001** (Foundation): Result types, exception hierarchy
- **Phase 002** (API Client): HTTP client, regional endpoints, Basic auth
- **Phase 004** (Discovery): Existing DiscoveryService class and caching pattern

---

## Assumptions

- **A-1:** Schema definitions are relatively stable within a session (safe to cache).
- **A-2:** The India (`in`) region follows the same `/api/app` pattern as US/EU.
- **A-3:** Non-existent schema returns an error response that can be mapped to `None`.
- **A-4:** The `entityType` parameter is case-sensitive and must be lowercase.
- **A-5:** Schema names with special characters should be URL-encoded by httpx.

---

## Out of Scope

- **Schema creation/modification** — Write operations are intentionally excluded
- **Schema deletion** — Delete operations are intentionally excluded
- **Schema validation** — We store the schema structure, not validate incoming data against it
- **Annotations API** — Separate API with different use case
- **GDPR Compliance API** — Data privacy operations, not analytics

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/mixpanel_data/types.py` | Add 4 types: `LexiconMetadata`, `LexiconProperty`, `LexiconDefinition`, `LexiconSchema`; add `EntityType` type alias |
| `src/mixpanel_data/_internal/api_client.py` | Add `"app"` to ENDPOINTS; add 3 methods: `list_schemas()`, `list_schemas_for_entity()`, `get_schema()` |
| `src/mixpanel_data/_internal/services/discovery.py` | Add 2 methods: `list_schemas()`, `get_schema()`; add parser helper functions |
| `src/mixpanel_data/workspace.py` | Rename `schema()` → `table_schema()`; add 2 methods: `lexicon_schemas()`, `lexicon_schema()` |
| `src/mixpanel_data/__init__.py` | Export new types: `LexiconSchema`, `LexiconDefinition`, `LexiconProperty`, `LexiconMetadata` |
| `src/mixpanel_data/cli/commands/inspect.py` | Add `lexicon` command with `--entity-type` and `--name` options |
| `tests/unit/test_discovery.py` | Tests for new discovery methods |
| `tests/unit/test_api_client.py` | Tests for new API client methods |
| `tests/unit/test_workspace.py` | Tests for `table_schema()` rename and new Lexicon methods |
| `docs/guide/discovery.md` | Add "Lexicon Schemas" section with examples |
| `docs/api/types.md` | Add LexiconSchema type references |
| `docs/api/workspace.md` | Document `lexicon_schemas()` and `lexicon_schema()` methods |
| `README.md` | Update CLI reference table |

---

## Documentation Updates

The following documentation files require updates after implementation:

| Document | Updates Required |
|----------|------------------|
| `docs/guide/discovery.md` | Add "Lexicon Schemas" section with Python and CLI examples |
| `docs/api/types.md` | Add new types under "Discovery Types" section |
| `docs/api/workspace.md` | Document `lexicon_schemas()` and `lexicon_schema()` methods; update `schema()` → `table_schema()` |
| `README.md` | Add `lexicon` to `mp inspect` command list |

### docs/guide/discovery.md Updates

Add a new section after "Saved Cohorts" documenting schema discovery:

```markdown
## Lexicon Schemas

Retrieve data dictionary schemas for events and profile properties. Schemas include descriptions, property types, and metadata defined in Mixpanel's Lexicon.

!!! note "Schema Coverage"
    The Lexicon API returns only events/properties with explicit schemas (defined via API, CSV import, or UI). It does not return all events visible in Lexicon's UI.

=== "Python"

    ```python
    # List all schemas
    schemas = ws.lexicon_schemas()
    for s in schemas:
        print(f"{s.entity_type}: {s.name}")

    # Filter by entity type
    event_schemas = ws.lexicon_schemas(entity_type="event")
    profile_schemas = ws.lexicon_schemas(entity_type="profile")

    # Get a specific schema
    schema = ws.lexicon_schema("event", "Purchase")
    if schema:
        print(schema.schema_json.description)
        for prop, info in schema.schema_json.properties.items():
            print(f"  {prop}: {info.type}")
    ```

=== "CLI"

    ```bash
    mp inspect lexicon
    mp inspect lexicon --entity-type event
    mp inspect lexicon --entity-type profile
    mp inspect lexicon --entity-type event --name Purchase
    ```

### LexiconSchema

```python
s.entity_type           # "event" or "profile"
s.name                  # "Purchase"
s.schema_json           # LexiconDefinition object
```

### LexiconDefinition

```python
s.schema_json.description                # "User completes a purchase"
s.schema_json.properties                 # dict[str, LexiconProperty]
s.schema_json.metadata                   # LexiconMetadata or None
```

### LexiconProperty

```python
prop = s.schema_json.properties["amount"]
prop.type                                # "number"
prop.description                         # "Purchase amount in USD"
prop.metadata                            # LexiconMetadata or None
```

### LexiconMetadata

```python
meta = s.schema_json.metadata
meta.display_name       # "Purchase Event"
meta.tags               # ["core", "revenue"]
meta.hidden             # False
meta.dropped            # False
meta.contacts           # ["owner@company.com"]
meta.team_contacts      # ["Analytics Team"]
```

!!! warning "Rate Limit"
    The Lexicon API has a strict rate limit of **5 requests per minute**. Schema results are cached for the session to minimize API calls.
```

### docs/api/types.md Updates

Add new types under the "Discovery Types" section:

```markdown
::: mixpanel_data.LexiconSchema
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.LexiconDefinition
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.LexiconProperty
    options:
      show_root_heading: true
      show_root_toc_entry: true

::: mixpanel_data.LexiconMetadata
    options:
      show_root_heading: true
      show_root_toc_entry: true
```

### README.md Updates

Update the CLI reference table to include lexicon commands:

```markdown
| `mp inspect` | `events`, `properties`, `values`, `funnels`, `cohorts`, `top-events`, `lexicon`, `info`, `tables`, `schema`, `drop` |
```

### CLI Commands to Add

If CLI support is included in scope:

| Command | Description |
|---------|-------------|
| `mp inspect lexicon` | List all Lexicon schemas |
| `mp inspect lexicon --entity-type event` | List event schemas only |
| `mp inspect lexicon --entity-type profile` | List profile schemas only |
| `mp inspect lexicon --entity-type event --name Purchase` | Get specific schema |

---

## Implementation Tasks

### Task 1: Add App Endpoint Configuration
- Add `"app"` key to `ENDPOINTS` dict for all three regions (US, EU, IN)
- Verify URL pattern matches Mixpanel documentation (`/api/app` base path)

### Task 2: Create Lexicon Types
- Create `LexiconMetadata` frozen dataclass
- Create `LexiconProperty` frozen dataclass
- Create `LexiconDefinition` frozen dataclass
- Create `LexiconSchema` frozen dataclass
- Add `EntityType` type alias (`Literal["event", "profile"]`)
- All types must have `to_dict()` methods

### Task 3: Add API Client Methods
- `list_schemas()` → GET `/projects/{project_id}/schemas`
- `list_schemas_for_entity(entity_type)` → GET `/projects/{project_id}/schemas/{entityType}`
- `get_schema(entity_type, name)` → GET `/projects/{project_id}/schemas/{entityType}/{name}`
- Handle response parsing and error mapping (404 → None)

### Task 4: Add DiscoveryService Methods
- Add parser helper functions: `_parse_lexicon_metadata()`, `_parse_lexicon_property()`, `_parse_lexicon_definition()`, `_parse_lexicon_schema()`
- `list_schemas(entity_type=None)` with caching
- `get_schema(entity_type, name)` with caching
- Update cache key documentation in docstring

### Task 5: Refactor Existing Schema Method (Breaking Change)
- Rename `Workspace.schema(table)` → `Workspace.table_schema(table)`
- Update any tests that reference the old method name

### Task 6: Add Workspace Facade Methods
- `lexicon_schemas(entity_type=None)` → List Lexicon schemas
- `lexicon_schema(entity_type, name)` → Get single Lexicon schema
- Delegate to DiscoveryService

### Task 7: Export Types
- Add new types to `__init__.py` exports: `LexiconSchema`, `LexiconDefinition`, `LexiconProperty`, `LexiconMetadata`

### Task 8: Write Tests
- Unit tests for API client methods (mock HTTP)
- Unit tests for DiscoveryService (mock API client)
- Unit tests for Workspace facade methods (including `table_schema()` rename)
- Verify caching behavior
- Verify empty/error handling

### Task 9: Add CLI Commands
- Add `mp inspect lexicon` command to `inspect.py`
- Support `--entity-type` option (event/profile)
- Support `--name` option for single schema lookup
- Support all output formats (json, jsonl, table, csv, plain)

### Task 10: Update Documentation
- Add "Lexicon Schemas" section to `docs/guide/discovery.md`
- Add new types to `docs/api/types.md`
- Document `lexicon_schemas()` and `lexicon_schema()` methods in `docs/api/workspace.md`
- Update `schema()` → `table_schema()` in `docs/api/workspace.md`
- Update CLI reference in `README.md`

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Rate limit (5/min) causes issues | Medium | Medium | Document rate limit clearly; consider exponential backoff |
| Response format differs from docs | Medium | Low | Parse defensively with defaults for optional fields |
| India region URL pattern differs | Low | Low | Test against real API if available |
| Schema name URL encoding issues | Medium | Low | Rely on httpx default encoding; add test cases |
| Non-existent schema error handling | Medium | Medium | Handle 404 gracefully, return None |

---

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| Project has no schemas | Return empty list `[]`, not error |
| Entity type has no schemas | Return empty list `[]`, not error |
| Schema name doesn't exist | Return `None` from `get_schema()` |
| Schema name with special chars | URL-encode automatically (httpx handles) |
| Invalid entity type | Raise `QueryError` (API returns 400) |
| Invalid credentials | Raise `AuthenticationError` |
| Rate limit exceeded | Automatic retry with backoff, then `RateLimitError` |

---

## Design Decisions

### Decision 1: Single `list_schemas()` Method with Optional Parameter

Instead of separate `list_schemas()` and `list_schemas_for_entity()` methods in DiscoveryService, we use a single method:

```python
def list_schemas(self, entity_type: EntityType | None = None) -> list[LexiconSchema]:
```

**Rationale:** Simpler API surface, matches pattern of other optional filtering parameters.

### Decision 2: Return `None` for Non-Existent Schema

Instead of raising an exception for `get_schema()` when schema doesn't exist:

```python
def get_schema(self, entity_type: EntityType, name: str) -> LexiconSchema | None:
```

**Rationale:** Non-existence is not exceptional; allows easy conditional logic without try/except.

### Decision 3: Nested Dataclasses for Schema Structure

Use composition of frozen dataclasses rather than nested dicts:

```python
LexiconSchema(
    entity_type="event",
    name="Purchase",
    schema_json=LexiconDefinition(
        description="...",
        properties={"amount": LexiconProperty(type="number", ...)},
        metadata=LexiconMetadata(...)
    )
)
```

**Rationale:** Type safety, IDE completion, consistent with existing types pattern.

### Decision 4: Cache All Schema Queries

Cache `list_schemas()`, `list_schemas(entity_type)`, and `get_schema()` calls.

**Rationale:** Schemas are infrequently updated (unlike real-time event data); users can call `clear_cache()` if needed.

### Decision 5: Rename `schema()` to `table_schema()` (Breaking Change)

Rename existing `Workspace.schema(table)` method to `Workspace.table_schema(table)` to avoid naming confusion:

- `ws.table_schema("events")` → Local DuckDB table schema (existing, renamed)
- `ws.lexicon_schema("event", "Purchase")` → Remote Mixpanel Lexicon schema (new)

**Rationale:** Clear disambiguation between local database introspection and remote API operations. Acceptable as library is pre-release.

---

*This implementation plan is ready for test-first (TDD) spec-driven development.*
