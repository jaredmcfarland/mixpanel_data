# Mixpanel HTTP API Specification

Comprehensive specification of Mixpanel's HTTP APIs for programmatic access to analytics data.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Authentication](#2-authentication)
3. [Data Residency](#3-data-residency)
4. [Event Export API](#4-event-export-api)
5. [Query API](#5-query-api)
6. [Ingestion API](#6-ingestion-api)
7. [Identity API](#7-identity-api)
8. [Lexicon Schemas API](#8-lexicon-schemas-api)
9. [GDPR Compliance API](#9-gdpr-compliance-api)
10. [Annotations API](#10-annotations-api)
11. [Feature Flags API](#11-feature-flags-api)
12. [Service Accounts API](#12-service-accounts-api)
13. [Data Pipelines API](#13-data-pipelines-api-deprecated)
14. [Warehouse Connectors API](#14-warehouse-connectors-api)
15. [Rate Limits Summary](#15-rate-limits-summary)
16. [HTTP Response Codes](#16-http-response-codes)
17. [Common Pitfalls](#17-common-pitfalls)

---

## 1. Overview

Mixpanel provides a suite of HTTP APIs for:
- **Event Export**: Download raw event data as JSONL
- **Query**: Run live analytics queries (segmentation, funnels, retention, JQL)
- **Ingestion**: Track events and manage user/group profiles
- **Identity**: Link anonymous and known user identities
- **Discovery**: Retrieve schema definitions from Lexicon
- **Compliance**: GDPR/CCPA data retrieval and deletion
- **Management**: Annotations, feature flags, service accounts, data pipelines

### Related Documentation

- **Query Expression Language**: See `mixpanel-query-expression-language.md` for WHERE clause syntax
- **JQL Reference**: See `jql.md` for JavaScript Query Language documentation

---

## 2. Authentication

Mixpanel uses four authentication methods depending on the API:

### 2.1 Service Account (Recommended)

HTTP Basic Auth with service account credentials.

```
Authorization: Basic <base64(username:secret)>
```

**Used by**: Query API, Export API, Lexicon API, Service Accounts API, Annotations API, Data Pipelines API

**Example**:
```bash
curl -u "SERVICE_ACCOUNT_USERNAME:SERVICE_ACCOUNT_SECRET" \
  "https://data.mixpanel.com/api/2.0/export?from_date=2024-01-01&to_date=2024-01-31"
```

### 2.2 Project Token

URL parameter or request body field for client-side tracking.

```
?token=PROJECT_TOKEN
# or in request body
{"properties": {"token": "PROJECT_TOKEN"}}
```

**Used by**: Ingestion API (/track), Identity API, Feature Flags API, GDPR API

**Note**: Project tokens are public and safe to embed in client-side code. They cannot read data.

### 2.3 Project Secret (Legacy)

HTTP Basic Auth with project secret only (no username).

```
Authorization: Basic <base64(PROJECT_SECRET:)>
```

**Used by**: Some Export API endpoints, Feature Flags API

**Note**: Deprecated in favor of Service Accounts.

### 2.4 OAuth Token

Bearer token for privacy compliance operations.

```
Authorization: Bearer <OAUTH_TOKEN>
```

**Used by**: GDPR API (data retrieval and deletion)

---

## 3. Data Residency

Mixpanel supports three regional deployments. Use the correct endpoints based on your project's data residency setting.

### Regional Endpoints

| Region | Ingestion | Query | Export |
|--------|-----------|-------|--------|
| **US** (default) | `api.mixpanel.com` | `mixpanel.com/api` | `data.mixpanel.com/api/2.0` |
| **EU** | `api-eu.mixpanel.com` | `eu.mixpanel.com/api` | `data-eu.mixpanel.com/api/2.0` |
| **India** | `api-in.mixpanel.com` | `in.mixpanel.com/api` | `data-in.mixpanel.com/api/2.0` |

### App API (Lexicon, Annotations, Service Accounts, GDPR)

| Region | Base URL |
|--------|----------|
| **US** | `https://mixpanel.com/api/app` |
| **EU** | `https://eu.mixpanel.com/api/app` |

### Feature Flags API

| Region | Base URL |
|--------|----------|
| **US** | `https://api.mixpanel.com/flags` |
| **EU** | `https://api-eu.mixpanel.com/flags` |
| **India** | `https://api-in.mixpanel.com/flags` |

---

## 4. Event Export API

Download raw event data as newline-delimited JSON (JSONL).

### Base URL

- US: `https://data.mixpanel.com/api/2.0`
- EU: `https://data-eu.mixpanel.com/api/2.0`

### Authentication

Service Account or Project Secret (Basic Auth)

### Endpoints

#### GET /export

Download raw events within a date range.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `from_date` | string | Yes | Start date (YYYY-MM-DD, inclusive, UTC) |
| `to_date` | string | Yes | End date (YYYY-MM-DD, inclusive, UTC) |
| `project_id` | integer | Conditional | Required for service account auth |
| `event` | string[] | No | JSON array of event names to filter |
| `where` | string | No | Expression filter (see query expression docs) |
| `limit` | integer | No | Max events to return (max 100,000) |
| `time_in_ms` | boolean | No | Return timestamps in milliseconds (default: false) |

**Headers**:
- `Accept-Encoding: gzip` - Enable gzip compression (recommended)

**Response**: JSONL format (one JSON object per line)

```jsonl
{"event": "Login", "properties": {"distinct_id": "user123", "time": 1704067200, "$browser": "Chrome"}}
{"event": "Purchase", "properties": {"distinct_id": "user123", "time": 1704067260, "amount": 99.99}}
```

**Rate Limits**:
- 60 queries per hour
- 3 queries per second
- Max 100 concurrent queries
- Max 100 days per request

**Example**:
```bash
curl -u "SERVICE_ACCOUNT:SECRET" \
  "https://data.mixpanel.com/api/2.0/export?project_id=12345&from_date=2024-01-01&to_date=2024-01-31&event=%5B%22Login%22%5D"
```

---

## 5. Query API

Execute live analytics queries against Mixpanel data.

### Base URL

- US: `https://mixpanel.com/api/2.0`
- EU: `https://eu.mixpanel.com/api/2.0`

### Authentication

Service Account (Basic Auth)

### Rate Limits

- 60 queries per hour
- Max 5 concurrent queries
- 10 second query timeout

---

### 5.1 Segmentation

Time-series event counts with optional property segmentation.

#### GET /segmentation

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `event` | string | Yes | Event name to analyze |
| `from_date` | string | Yes | Start date (YYYY-MM-DD) |
| `to_date` | string | Yes | End date (YYYY-MM-DD) |
| `type` | string | No | `general` (total), `unique` (users), `average` |
| `unit` | string | No | `minute`, `hour`, `day`, `week`, `month` |
| `on` | string | No | Property to segment by |
| `where` | string | No | Filter expression |
| `limit` | integer | No | Max segments to return |

**Response**:
```json
{
  "data": {
    "series": ["2024-01-01", "2024-01-02"],
    "values": {
      "Login": {"2024-01-01": 100, "2024-01-02": 150}
    }
  }
}
```

#### GET /segmentation/numeric

Bucket events by numeric property ranges.

**Additional Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `on` | string | Yes | Numeric property to bucket |
| `buckets` | integer | No | Number of buckets |

#### GET /segmentation/sum

Calculate sum of a numeric property over time.

**Parameters**: Same as /segmentation, `on` specifies the numeric property.

#### GET /segmentation/average

Calculate average of a numeric property over time.

**Parameters**: Same as /segmentation, `on` specifies the numeric property.

---

### 5.2 Funnels

Analyze step-by-step conversion funnels.

#### GET /funnels

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `funnel_id` | integer | Yes | Saved funnel ID |
| `from_date` | string | Yes | Start date (YYYY-MM-DD) |
| `to_date` | string | Yes | End date (YYYY-MM-DD) |
| `length` | integer | No | Conversion window in units |
| `length_unit` | string | No | `second`, `minute`, `hour`, `day`, `week`, `month` |
| `interval` | integer | No | Number of days per data point |
| `unit` | string | No | `day`, `week`, `month` |
| `on` | string | No | Property to segment by |
| `where` | string | No | Filter expression |
| `limit` | integer | No | Max segments |

**Response**:
```json
{
  "data": {
    "2024-01-01": [
      {"count": 1000, "step": 0, "name": "Signup Started"},
      {"count": 800, "step": 1, "name": "Email Verified"},
      {"count": 600, "step": 2, "name": "Profile Completed"}
    ]
  }
}
```

#### GET /funnels/list

List all saved funnels.

**Response**:
```json
[
  {"funnel_id": 123, "name": "Signup Flow"},
  {"funnel_id": 456, "name": "Purchase Flow"}
]
```

---

### 5.3 Retention

Cohort-based retention analysis.

#### GET /retention

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `from_date` | string | Yes | Start date (YYYY-MM-DD) |
| `to_date` | string | Yes | End date (YYYY-MM-DD) |
| `retention_type` | string | No | `birth` or `compounded` |
| `born_event` | string | No | Initial cohort event |
| `event` | string | No | Return event |
| `born_where` | string | No | Filter for born event |
| `where` | string | No | Filter for return event |
| `interval` | integer | No | Interval in days |
| `interval_count` | integer | No | Number of intervals |
| `unit` | string | No | `day`, `week`, `month` |
| `on` | string | No | Property to segment by |
| `limit` | integer | No | Max segments |

**Response**:
```json
{
  "data": {
    "2024-01-01": {
      "counts": [1000, 800, 600, 400],
      "percents": [100, 80, 60, 40]
    }
  }
}
```

#### GET /retention/addiction

Event frequency distribution (how often users perform an event).

**Parameters**: Similar to retention, plus `addiction_unit` for frequency bucket size.

---

### 5.4 Events

Aggregate event counts and discovery.

#### GET /events

Multi-event time series counts.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `event` | string[] | Yes | JSON array of event names |
| `from_date` | string | Yes | Start date |
| `to_date` | string | Yes | End date |
| `type` | string | No | `general`, `unique`, `average` |
| `unit` | string | No | Time unit |

#### GET /events/top

Today's top events with percent change from yesterday.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `type` | string | No | `general` or `unique` |
| `limit` | integer | No | Max events to return |

**Response**:
```json
{
  "events": [
    {"event": "Page View", "amount": 50000},
    {"event": "Login", "amount": 12000}
  ]
}
```

#### GET /events/names

List all event names (from last 31 days).

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `type` | string | No | `general` or `unique` |
| `limit` | integer | No | Max events |

**Response**:
```json
["Login", "Signup", "Purchase", "Page View"]
```

#### GET /events/properties

Property value counts for an event.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `event` | string | Yes | Event name |
| `name` | string | Yes | Property name |
| `type` | string | No | `general` or `unique` |
| `unit` | string | No | Time unit |
| `values` | string[] | No | Property values to filter |
| `limit` | integer | No | Max values |

#### GET /events/properties/top

Top property names for an event (by usage percentage).

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `event` | string | Yes | Event name |
| `limit` | integer | No | Max properties |

**Response**:
```json
{
  "$browser": 95.2,
  "$os": 94.8,
  "plan": 78.3
}
```

#### GET /events/properties/values

Sample values for a property.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `event` | string | Yes | Event name |
| `name` | string | Yes | Property name |
| `limit` | integer | No | Max values |

**Response**:
```json
["Chrome", "Firefox", "Safari", "Edge"]
```

---

### 5.5 User Profiles (Engage)

Query and manage user profiles.

#### POST /engage

Query user profiles with filtering and pagination.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `distinct_id` | string | No | Single user ID |
| `distinct_ids` | string[] | No | Array of user IDs |
| `where` | string | No | Filter expression |
| `output_properties` | string[] | No | Properties to include |
| `session_id` | string | No | Pagination session |
| `page` | integer | No | Page number |
| `page_size` | integer | No | Results per page (max 1000) |
| `filter_by_cohort` | string | No | Cohort ID to filter by |
| `as_of_timestamp` | integer | No | Point-in-time query |

**Response**:
```json
{
  "results": [
    {
      "$distinct_id": "user123",
      "$properties": {
        "$name": "John Doe",
        "$email": "john@example.com",
        "plan": "premium"
      }
    }
  ],
  "page": 0,
  "page_size": 1000,
  "session_id": "session123",
  "total": 5000
}
```

---

### 5.6 Cohorts

List saved cohorts.

#### POST /cohorts/list

**Response**:
```json
[
  {
    "id": "cohort123",
    "name": "Power Users",
    "count": 5000,
    "description": "Users with 10+ sessions",
    "created": "2024-01-01",
    "is_visible": true
  }
]
```

---

### 5.7 Insights

Query saved Insights reports.

#### GET /insights

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project_id` | integer | Yes | Project ID |
| `workspace_id` | integer | Yes | Workspace ID |
| `bookmark_id` | integer | Yes | Saved report ID |

**Response**:
```json
{
  "computed_at": "2024-01-15T12:00:00Z",
  "date_range": {
    "from_date": "2024-01-01T00:00:00Z",
    "to_date": "2024-01-14T23:59:59Z"
  },
  "series": {
    "Login": {
      "2024-01-01": 9852,
      "2024-01-08": 10234
    }
  }
}
```

---

### 5.8 Activity Stream

Query user event history.

#### GET /stream/query

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `distinct_ids` | string | Yes | JSON array string of user IDs |
| `from_date` | string | Yes | Start date |
| `to_date` | string | Yes | End date |

**Response**:
```json
{
  "results": [
    {
      "event": "Login",
      "time": 1704067200,
      "properties": {"$browser": "Chrome"}
    },
    {
      "event": "Purchase",
      "time": 1704067260,
      "properties": {"amount": 99.99}
    }
  ]
}
```

---

### 5.9 JQL (JavaScript Query Language)

Execute custom JavaScript queries. **Note**: JQL is in maintenance mode.

#### POST /jql

**Headers**:
- `Content-Type: application/x-www-form-urlencoded`

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `script` | string | Yes | URL-encoded JavaScript code |
| `params` | string | No | JSON-encoded parameters for script |

**Example Script**:
```javascript
function main() {
  return Events({
    from_date: '2024-01-01',
    to_date: '2024-01-31',
    event_selectors: [{event: "Login"}]
  })
  .groupBy(["properties.$browser"], mixpanel.reducer.count())
}
```

**Response**:
```json
[
  ["Chrome", 15000],
  ["Firefox", 8000],
  ["Safari", 6000]
]
```

**Limits**:
- 5GB process limit
- 2GB output limit
- 2 minute timeout

See `jql.md` for complete JQL documentation.

---

## 6. Ingestion API

Track events and manage user/group profiles.

### Base URL

- US: `https://api.mixpanel.com`
- EU: `https://api-eu.mixpanel.com`
- India: `https://api-in.mixpanel.com`

### Rate Limits

- 2GB per minute (~30,000 events/second)
- Max 2,000 events per batch
- Recommended: 10-20 concurrent clients

---

### 6.1 Event Tracking

#### POST /track

Client-side event tracking (project token auth, last 5 days only).

**Content-Type**: `application/x-www-form-urlencoded`

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `data` | string | Yes | Base64-encoded JSON event(s) |
| `verbose` | integer | No | `1` for detailed response |
| `strict` | integer | No | `1` for strict validation |
| `ip` | integer | No | `1` to use IP for geolocation |

**Event Object**:
```json
{
  "event": "Purchase",
  "properties": {
    "token": "PROJECT_TOKEN",
    "distinct_id": "user123",
    "time": 1704067200,
    "$insert_id": "unique-event-id",
    "amount": 99.99,
    "product": "Premium Plan"
  }
}
```

**Reserved Properties**:

| Property | Description |
|----------|-------------|
| `token` | Project token (required) |
| `distinct_id` | User identifier (required) |
| `time` | Unix timestamp (seconds) |
| `$insert_id` | Unique event ID for deduplication |
| `$device_id` | Device identifier |
| `ip` | IP address for geolocation |

**Response**:
```json
// verbose=0 (default)
1

// verbose=1
{"status": 1}

// Error
{"status": 0, "error": "Invalid token"}
```

#### POST /import

Server-side event import (service account auth, historical data).

**Content-Type**: `application/json`

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `strict` | integer | Yes | `1` for per-event error reporting |
| `project_id` | integer | Conditional | Required for service account auth |

**Request Body**: Array of event objects

```json
[
  {
    "event": "Purchase",
    "properties": {
      "distinct_id": "user123",
      "time": 1704067200,
      "$insert_id": "purchase-001",
      "amount": 99.99
    }
  }
]
```

**Response (strict=1)**:
```json
{
  "code": 200,
  "num_records_imported": 2000,
  "status": "OK"
}

// With failures
{
  "code": 400,
  "num_records_imported": 1999,
  "status": "Bad Request",
  "failed_records": [
    {
      "index": 0,
      "insert_id": "purchase-001",
      "field": "properties.time",
      "message": "'properties.time' is invalid"
    }
  ]
}
```

---

### 6.2 User Profiles

#### POST /engage

Update user profiles.

**Content-Type**: `application/x-www-form-urlencoded`

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `data` | string | Yes | Base64-encoded JSON update(s) |
| `verbose` | integer | No | `1` for detailed response |
| `strict` | integer | No | `1` for strict validation |

**Operations**:

```json
// $set - Set properties (overwrites)
{
  "$token": "PROJECT_TOKEN",
  "$distinct_id": "user123",
  "$set": {
    "name": "John Doe",
    "email": "john@example.com",
    "plan": "premium"
  }
}

// $set_once - Set only if not exists
{
  "$token": "PROJECT_TOKEN",
  "$distinct_id": "user123",
  "$set_once": {
    "first_login": "2024-01-01"
  }
}

// $add - Increment numeric properties
{
  "$token": "PROJECT_TOKEN",
  "$distinct_id": "user123",
  "$add": {
    "login_count": 1,
    "total_spent": 99.99
  }
}

// $append - Append to list
{
  "$token": "PROJECT_TOKEN",
  "$distinct_id": "user123",
  "$append": {
    "purchases": "product-123"
  }
}

// $union - Add unique values to list
{
  "$token": "PROJECT_TOKEN",
  "$distinct_id": "user123",
  "$union": {
    "tags": ["premium", "active"]
  }
}

// $remove - Remove from list
{
  "$token": "PROJECT_TOKEN",
  "$distinct_id": "user123",
  "$remove": {
    "tags": "inactive"
  }
}

// $unset - Delete properties
{
  "$token": "PROJECT_TOKEN",
  "$distinct_id": "user123",
  "$unset": ["temp_property"]
}

// $delete - Delete entire profile
{
  "$token": "PROJECT_TOKEN",
  "$distinct_id": "user123",
  "$delete": ""
}
```

---

### 6.3 Group Profiles

#### POST /groups

Update group profiles (same operations as user profiles).

```json
{
  "$token": "PROJECT_TOKEN",
  "$group_key": "company",
  "$group_id": "acme-corp",
  "$set": {
    "name": "Acme Corporation",
    "plan": "enterprise",
    "employees": 500
  }
}
```

---

### 6.4 Lookup Tables

#### GET /lookup-tables

List all lookup tables.

#### PUT /lookup-tables/{id}

Replace a lookup table (CSV format).

**Content-Type**: `text/csv`

**Request Body**:
```csv
id,name,category,price
sku-001,Widget A,Electronics,29.99
sku-002,Widget B,Electronics,49.99
```

---

## 7. Identity API

Link anonymous and known user identities.

### Base URL

Same as Ingestion API

### Authentication

Project Token (public) or Service Account (for merge)

---

### 7.1 Create Identity

Link an anonymous ID to a known user ID.

#### POST /track#create-identity

**Request Body** (`data` parameter, base64-encoded):
```json
{
  "event": "$identify",
  "properties": {
    "$identified_id": "known-user-123",
    "$anon_id": "anonymous-visitor-456",
    "token": "PROJECT_TOKEN"
  }
}
```

---

### 7.2 Create Alias

Create an alias for a user ID.

#### POST /track#identity-create-alias

**Request Body**:
```json
{
  "event": "$create_alias",
  "properties": {
    "distinct_id": "primary-user-id",
    "alias": "secondary-id",
    "token": "PROJECT_TOKEN"
  }
}
```

---

### 7.3 Merge Identities

Merge two user profiles (requires service account auth).

#### POST /import

**Parameters**:
- `strict=1` (required)
- `project_id` (required)

**Request Body**:
```json
[
  {
    "event": "$merge",
    "properties": {
      "$distinct_ids": ["user-id-1", "user-id-2"],
      "token": "PROJECT_TOKEN"
    }
  }
]
```

---

## 8. Lexicon Schemas API

Sync data dictionary schemas with Mixpanel.

### Base URL

- US: `https://mixpanel.com/api/app`
- EU: `https://eu.mixpanel.com/api/app`

### Authentication

Service Account (Basic Auth)

### Rate Limits

- 5 requests per minute
- Max 4,000 events/properties per minute
- Max 3,000 truncations/deletions per request

---

### Endpoints

#### GET /projects/{projectId}/schemas

List all schemas in a project.

**Response**:
```json
{
  "results": [
    {
      "entityType": "event",
      "name": "Purchase",
      "schemaJson": {
        "description": "User completes a purchase",
        "properties": {
          "amount": {"type": "number", "description": "Purchase amount"},
          "product_id": {"type": "string"}
        }
      }
    }
  ],
  "status": "ok"
}
```

#### POST /projects/{projectId}/schemas

Create/replace multiple schemas.

**Request Body**:
```json
{
  "entries": [
    {
      "entityType": "event",
      "name": "Purchase",
      "schemaJson": {
        "description": "User completes a purchase",
        "properties": {
          "amount": {"type": "number"},
          "product_id": {"type": "string"}
        },
        "metadata": {
          "com.mixpanel": {
            "displayName": "Purchase Event",
            "tags": ["core", "revenue"],
            "hidden": false
          }
        }
      }
    }
  ],
  "truncate": false
}
```

**Response**:
```json
{
  "results": {"added": 1, "deleted": 0},
  "status": "ok"
}
```

#### DELETE /projects/{projectId}/schemas

Delete all schemas in a project.

#### GET /projects/{projectId}/schemas/{entityType}

List schemas for entity type (`event` or `profile`).

#### DELETE /projects/{projectId}/schemas/{entityType}

Delete all schemas of entity type.

#### GET /projects/{projectId}/schemas/{entityType}/{name}

Get schema for specific entity.

#### POST /projects/{projectId}/schemas/{entityType}/{name}

Create/replace single schema.

#### DELETE /projects/{projectId}/schemas/{entityType}/{name}

Delete specific schema.

### Schema Structure

```json
{
  "description": "Event description",
  "properties": {
    "property_name": {
      "type": "string|number|boolean|array|object|integer|null",
      "description": "Property description",
      "metadata": {
        "com.mixpanel": {
          "displayName": "Display Name",
          "hidden": false,
          "dropped": false
        }
      }
    }
  },
  "metadata": {
    "com.mixpanel": {
      "$source": "api",
      "displayName": "Event Display Name",
      "tags": ["tag1", "tag2"],
      "hidden": false,
      "dropped": false,
      "contacts": ["owner@company.com"],
      "teamContacts": ["Analytics Team"]
    }
  }
}
```

---

## 9. GDPR Compliance API

Handle GDPR and CCPA data requests.

### Base URL

- US: `https://mixpanel.com/api/app`
- EU: `https://eu.mixpanel.com/api/app`

### Authentication

OAuth Token (Bearer)

### Rate Limits

- 1 request per second
- Max 2,000 distinct_ids per request
- Max 5 years of data scans

---

### 9.1 Data Retrieval

#### POST /data-retrievals/v3.0

Create a data retrieval job.

**Parameters**:
- `token` (query): Project token

**Request Body**:
```json
{
  "distinct_ids": ["user123", "user456"],
  "compliance_type": "GDPR",
  "disclosure_type": "Data"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `distinct_ids` | string[] | Yes | User IDs (max 2,000) |
| `compliance_type` | string | Yes | `GDPR` or `CCPA` |
| `disclosure_type` | string | CCPA only | `Data`, `Categories`, or `Sources` |

**Response**:
```json
{
  "status": "ok",
  "results": {
    "task_id": "retrieval-job-123"
  }
}
```

#### GET /data-retrievals/v3.0/{tracking_id}

Check retrieval status.

**Parameters**:
- `token` (query): Project token
- `tracking_id` (path): Job ID

**Response**:
```json
{
  "status": "ok",
  "results": {
    "status": "SUCCESS",
    "results": "https://download-url...",
    "distinct_ids": ["user123", "user456"]
  }
}
```

**Status Values**: `PENDING`, `STAGING`, `STARTED`, `SUCCESS`, `FAILURE`, `REVOKED`, `NOT_FOUND`, `UNKNOWN`

---

### 9.2 Data Deletion

#### POST /data-deletions/v3.0

Create a deletion job.

**Request Body**:
```json
{
  "distinct_ids": ["user123"],
  "compliance_type": "GDPR"
}
```

**Note**: Deletions can take up to 30 days to complete.

#### GET /data-deletions/v3.0/{tracking_id}

Check deletion status.

**Response**:
```json
{
  "status": "ok",
  "results": {
    "tracking_id": "deletion-job-123",
    "status": "STARTED",
    "requesting_user": "admin@company.com",
    "compliance_type": "GDPR",
    "project_id": 12345,
    "date_requested": "2024-01-15T10:00:00Z",
    "distinct_ids": ["user123"]
  }
}
```

#### DELETE /data-deletions/v3.0/{tracking_id}

Cancel a deletion job (only before `STARTED` status).

---

## 10. Annotations API

Add annotations to mark events on charts.

### Base URL

- US: `https://mixpanel.com/api/app`
- EU: `https://eu.mixpanel.com/api/app`

### Authentication

Service Account (Basic Auth)

### Permission

Requires Analyst role or higher.

---

### Endpoints

#### GET /projects/{projectId}/annotations

List all annotations.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `fromDate` | string | No | Filter start date |
| `toDate` | string | No | Filter end date |

**Response**:
```json
{
  "status": "ok",
  "results": [
    {
      "id": 123,
      "date": "2024-01-15 12:00:00",
      "description": "New feature launched",
      "user": {"id": 456, "first_name": "John", "last_name": "Doe"},
      "tags": [{"id": 1, "name": "release"}]
    }
  ]
}
```

#### POST /projects/{projectId}/annotations

Create an annotation.

**Request Body**:
```json
{
  "date": "2024-01-15 12:00:00",
  "description": "New feature launched",
  "tags": [1, 2]
}
```

#### GET /projects/{projectId}/annotations/{annotationId}

Get a specific annotation.

#### PATCH /projects/{projectId}/annotations/{annotationId}

Update an annotation.

**Request Body**:
```json
{
  "description": "Updated description",
  "tags": [1, 2, 3]
}
```

#### DELETE /projects/{projectId}/annotations/{annotationId}

Delete an annotation.

---

### Annotation Tags

#### GET /projects/{projectId}/annotations/tags

List all annotation tags.

**Response**:
```json
[
  {"id": 1, "name": "release", "project_id": 12345, "has_annotations": true},
  {"id": 2, "name": "incident", "project_id": 12345, "has_annotations": false}
]
```

#### POST /projects/{projectId}/annotations/tags

Create an annotation tag.

**Request Body**:
```json
{"name": "marketing"}
```

---

## 11. Feature Flags API

Evaluate feature flags and retrieve definitions.

### Base URL

- US: `https://api.mixpanel.com/flags`
- EU: `https://api-eu.mixpanel.com/flags`
- India: `https://api-in.mixpanel.com/flags`

### Authentication

Project Secret (Basic Auth)

---

### Endpoints

#### GET /flags

Evaluate feature flags for a user.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `token` | string | Yes | Project token |
| `context` | string | Yes | URL-encoded JSON evaluation context |

**Context Object** (before URL encoding):
```json
{
  "distinct_id": "user123",
  "device_id": "device456",
  "custom_properties": {
    "plan": "premium",
    "country": "US"
  }
}
```

**Response**:
```json
{
  "flags": {
    "new_checkout_flow": {
      "variant_key": "treatment",
      "variant_value": true,
      "experiment_id": "exp_123",
      "is_experiment_active": true
    },
    "dark_mode": {
      "variant_key": "control",
      "variant_value": false
    }
  }
}
```

#### GET /flags/definitions

Get all feature flag definitions.

**Parameters**:

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `token` | string | Yes | Project token |

**Response**:
```json
{
  "flags": [
    {
      "id": "flag_abc123",
      "name": "New Checkout Flow",
      "key": "new_checkout_flow",
      "status": "enabled",
      "project_id": 12345,
      "workspace_id": 67890,
      "context": "device_id",
      "ruleset": {
        "variants": [
          {"key": "control", "value": false, "is_control": true, "split": 0.5},
          {"key": "treatment", "value": true, "is_control": false, "split": 0.5}
        ],
        "rollout": [
          {
            "rollout_percentage": 1.0,
            "variant_splits": {"control": 0.5, "treatment": 0.5}
          }
        ],
        "test": {
          "users": {"qa_user_1": "treatment"}
        }
      }
    }
  ]
}
```

---

## 12. Service Accounts API

Manage service account credentials programmatically.

### Base URL

- US: `https://mixpanel.com/api/app`
- EU: `https://eu.mixpanel.com/api/app`

### Authentication

Service Account (Basic Auth) - requires organization admin role

---

### Endpoints

#### GET /organizations/{organizationId}/service-accounts

List all service accounts.

**Response**:
```json
{
  "results": [
    {
      "id": 123,
      "username": "api-integration",
      "last_used": "2024-01-15T10:00:00Z",
      "expires": "2025-01-15T00:00:00Z",
      "creator": 456,
      "created": "2024-01-01T00:00:00Z"
    }
  ],
  "status": "ok"
}
```

#### POST /organizations/{organizationId}/service-accounts

Create a service account.

**Request Body**:
```json
{
  "username": "new-api-integration",
  "role": "analyst",
  "expires": "2025-01-15T00:00:00Z",
  "projects": [
    {"id": 12345, "role": "analyst"},
    {"id": 67890, "role": "consumer"}
  ]
}
```

**Roles**: `owner`, `admin`, `analyst`, `consumer`

**Response**:
```json
{
  "results": {
    "id": 124,
    "username": "new-api-integration",
    "token": "sa_secret_xyz...",
    "created": "2024-01-15T10:00:00Z"
  },
  "status": "ok"
}
```

**Note**: The `token` (secret) is only shown once at creation time.

#### GET /organizations/{organizationId}/service-accounts/{serviceAccountId}

Get service account details.

#### DELETE /organizations/{organizationId}/service-accounts/{serviceAccountId}

Delete a service account.

---

### Project Membership

#### GET /projects/{projectId}/service-accounts

List service accounts for a project.

#### POST /organizations/{organizationId}/service-accounts/add-to-project

Add service accounts to projects.

**Request Body**:
```json
{
  "service_account_ids": [123, 124],
  "projects": [
    {"id": 12345, "role": "analyst"},
    {"id": 67890, "role": "consumer"}
  ]
}
```

#### POST /organizations/{organizationId}/service-accounts/remove-from-project

Remove service accounts from projects.

**Request Body**:
```json
{
  "projects": [
    {
      "id": 12345,
      "service_account_ids": [123, 124]
    }
  ]
}
```

---

## 13. Data Pipelines API (Deprecated)

**Note**: This API is deprecated. Use the Mixpanel UI for creating and managing data pipelines.

### Base URL

- US: `https://data.mixpanel.com/api/2.0`
- EU: `https://data-eu.mixpanel.com/api/2.0`

### Authentication

Service Account or Project Secret (Basic Auth)

---

### Pipeline Types

| Type | Destination | Format |
|------|-------------|--------|
| `gcs-raw` | Google Cloud Storage | JSON |
| `s3-raw` | Amazon S3 | JSON |
| `azure-raw` | Azure Blob Storage | JSON |
| `bigquery` | BigQuery | Schematized |
| `snowflake` | Snowflake | Schematized |
| `aws` | AWS (S3 + Glue) | JSON/Parquet |
| `azure-blob` | Azure Blob | JSON/Parquet |
| `gcs-schema` | GCS | JSON/Parquet |

---

### Endpoints

#### GET /nessie/pipeline/jobs

List all pipelines for a project.

**Parameters**:
- `project_id` (query): Project ID

#### POST /nessie/pipeline/create

Create a new pipeline.

**Common Parameters**:

| Name | Type | Description |
|------|------|-------------|
| `project_id` | integer | Project ID |
| `type` | string | Pipeline type |
| `data_source` | string | `events` or `people` |
| `from_date` | string | Start date (YYYY-MM-DD) |
| `to_date` | string | End date (optional, continuous if empty) |
| `frequency` | string | `hourly` or `daily` |
| `events` | string[] | Event filter (optional) |
| `where` | string | Filter expression (optional) |
| `schema_type` | string | `monoschema` or `multischema` |
| `sync` | boolean | Enable sync for updates/deletions |

#### POST /nessie/pipeline/edit

Edit pipeline parameters.

#### POST /nessie/pipeline/pause

Pause a running pipeline.

#### POST /nessie/pipeline/resume

Resume a paused pipeline.

#### POST /nessie/pipeline/cancel

Delete a pipeline (cannot be undone).

#### GET /nessie/pipeline/status

Get pipeline status and job history.

**Parameters**:
- `project_id` (query): Project ID
- `name` (query): Pipeline name
- `status` (query): Filter by status (`pending`, `running`, `retried`, `failed`, `canceled`, `timed_out`)
- `summary` (query): `true` for counts only

#### GET /nessie/pipeline/timeline

Get sync history by date.

---

## 14. Warehouse Connectors API

Trigger warehouse imports.

### Base URL

- US: `https://mixpanel.com/api/app`
- EU: `https://eu.mixpanel.com/api/app`

### Authentication

Service Account (Basic Auth)

---

### Endpoints

#### PUT /projects/{projectId}/warehouse-sources/imports/{importId}/manual-sync

Trigger an immediate sync for a warehouse import.

**Parameters**:
- `projectId` (path): Project ID
- `importId` (path): Import configuration ID

**Response**:
```json
{"status": "ok"}
```

---

## 15. Rate Limits Summary

| API | Requests | Concurrent | Notes |
|-----|----------|------------|-------|
| **Query API** | 60/hour | 5 max | 10s timeout |
| **Export API** | 60/hour | 100 max | 3/second, max 100 days |
| **Ingestion API** | 2GB/min | 10-20 recommended | 2000 events/batch |
| **JQL API** | 60/hour | - | 2 min timeout, 5GB process |
| **GDPR API** | 1/second | - | Max 5 years data |
| **Lexicon API** | 5/min | - | 4000 items/min |

### Handling Rate Limits

When you receive a `429 Too Many Requests`:

1. Check `Retry-After` header for wait time
2. Implement exponential backoff with jitter
3. Reduce concurrent requests
4. Consider batching operations

```python
import time
import random

def backoff_retry(func, max_retries=5):
    for attempt in range(max_retries):
        try:
            return func()
        except RateLimitError:
            wait = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(wait)
    raise Exception("Max retries exceeded")
```

---

## 16. HTTP Response Codes

| Code | Name | Description | Action |
|------|------|-------------|--------|
| `200` | OK | Request succeeded | Process response |
| `201` | Created | Resource created | Process response |
| `204` | No Content | Success, no body | Operation completed |
| `400` | Bad Request | Invalid parameters | Check request format |
| `401` | Unauthorized | Invalid credentials | Check auth credentials |
| `402` | Payment Required | Quota exceeded | Upgrade plan or wait |
| `403` | Forbidden | Permission denied | Check access rights |
| `404` | Not Found | Resource not found | Check ID/path |
| `413` | Payload Too Large | Request body too big | Reduce batch size |
| `429` | Too Many Requests | Rate limit exceeded | Retry with backoff |
| `500` | Internal Server Error | Server error | Retry later |
| `502` | Bad Gateway | Upstream error | Retry later |
| `503` | Service Unavailable | Service down | Retry later |

### Error Response Format

```json
{
  "status": "error",
  "error": "Invalid parameter",
  "error_code": "INVALID_PARAM",
  "details": {
    "parameter": "from_date",
    "message": "Must be in YYYY-MM-DD format"
  }
}
```

---

## 17. Common Pitfalls

### Authentication

1. **Wrong auth method**: Each API uses different authentication. Check the API section for the correct method.
2. **Missing project_id**: Service account auth requires `project_id` parameter.
3. **Colon after secret**: Basic auth with API secret requires trailing colon: `base64(secret:)`

### Data Residency

4. **Wrong region**: Always use endpoints matching your project's data residency (US/EU/India).
5. **Mixing endpoints**: Don't mix regional endpoints in the same integration.

### Date Handling

6. **Wrong date format**: All dates must be `YYYY-MM-DD`.
7. **Timezone confusion**: Query API uses project timezone; Export API uses UTC.
8. **Future dates**: `/track` only accepts events from last 5 days; use `/import` for historical data.

### Request Formatting

9. **Missing URL encoding**: JQL scripts and context parameters must be URL-encoded.
10. **Wrong Content-Type**:
    - `/track`, `/engage`: `application/x-www-form-urlencoded`
    - `/import`: `application/json`
    - Lookup tables: `text/csv`

### Rate Limits

11. **Ignoring 429s**: Always implement exponential backoff.
12. **Too many concurrent requests**: Respect concurrent query limits.
13. **Batch size**: Max 2000 events per batch, 2000 IDs for GDPR.

### Data Quality

14. **Missing $insert_id**: Without it, retried events may create duplicates.
15. **Large events**: Events must be <1MB uncompressed.
16. **Deep nesting**: Max 3 levels of nested objects, max 255 array elements.
17. **Property limits**: Max 255 properties per event.

### Export

18. **Large date ranges**: Export API limits to 100 days per request.
19. **Not streaming**: Always stream JSONL responses; don't buffer entirely.
20. **Missing gzip**: Use `Accept-Encoding: gzip` for large exports.

---

*Document generated from Mixpanel OpenAPI specifications and reference documentation.*
