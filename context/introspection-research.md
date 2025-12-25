# Introspection Capabilities Research

> Research document for understanding introspection patterns and capabilities before designing features for mixpanel_data.

## Table of Contents

1. [Current mixpanel_data Capabilities](#current-mixpanel_data-capabilities)
2. [DuckDB Built-in Introspection](#duckdb-built-in-introspection)
3. [Similar Library Patterns](#similar-library-patterns)
4. [Product Analytics Patterns](#product-analytics-patterns)
5. [Common Data Quality Issues](#common-data-quality-issues)

---

## Current mixpanel_data Capabilities

### Existing Introspection Features

The library already provides two categories of introspection:

#### Remote Discovery (Mixpanel API)

| Method | Returns | Cached |
|--------|---------|--------|
| `events()` | List of event names in project | Yes |
| `properties(event)` | Properties for an event | Yes |
| `property_values(prop, event, limit)` | Sample values for a property | Yes |
| `funnels()` | Saved funnel definitions | Yes |
| `cohorts()` | Saved cohort definitions | Yes |
| `top_events(type, limit)` | Today's top events | No |
| `lexicon_schemas(entity_type)` | Documented schemas | Yes |
| `lexicon_schema(entity_type, name)` | Single schema definition | Yes |

#### Local Introspection (DuckDB)

| Method | Returns | Description |
|--------|---------|-------------|
| `info()` | `WorkspaceInfo` | Database path, project_id, region, tables, size_mb |
| `tables()` | `list[TableInfo]` | Name, type, row_count, fetched_at for each table |
| `table_schema(table)` | `TableSchema` | Columns with name, type, nullable, primary_key |

### Data Model

**Events table schema:**
```sql
CREATE TABLE events (
    event_name VARCHAR NOT NULL,
    event_time TIMESTAMP NOT NULL,
    distinct_id VARCHAR NOT NULL,
    insert_id VARCHAR PRIMARY KEY,
    properties JSON
)
```

**Profiles table schema:**
```sql
CREATE TABLE profiles (
    distinct_id VARCHAR PRIMARY KEY,
    properties JSON,
    last_seen TIMESTAMP
)
```

**Metadata table (`_metadata`):**
```sql
CREATE TABLE _metadata (
    table_name VARCHAR PRIMARY KEY,
    type VARCHAR NOT NULL,          -- 'events' or 'profiles'
    fetched_at TIMESTAMP NOT NULL,
    from_date DATE,
    to_date DATE,
    row_count INTEGER NOT NULL
)
```

### Current API Patterns

- **Frozen dataclasses** for all result types with `.df` lazy property
- **Dependency injection** for testing
- **Escape hatches**: `.connection` (DuckDB), `.api` (MixpanelAPIClient)
- **SQL methods**: `sql()`, `sql_scalar()`, `sql_rows()` for arbitrary queries

---

## DuckDB Built-in Introspection

### information_schema Views

SQL-standard views based on PostgreSQL's implementation:

| View | Purpose |
|------|---------|
| `information_schema.tables` | Table names, types (BASE TABLE, VIEW, LOCAL TEMPORARY) |
| `information_schema.columns` | Column metadata (name, type, nullable, ordinal_position) |
| `information_schema.schemata` | Catalog and schema information |
| `information_schema.table_constraints` | Constraint types (PRIMARY KEY, UNIQUE, CHECK, FOREIGN KEY) |
| `information_schema.key_column_usage` | Maps columns to constraints |
| `information_schema.referential_constraints` | Foreign key relationships |
| `information_schema.character_sets` | Character encoding information |

**Example:**
```sql
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'main'
ORDER BY table_name, ordinal_position;
```

### DuckDB Table Functions

Prefixed with `duckdb_`, these provide richer metadata than `information_schema`:

| Function | Key Columns |
|----------|-------------|
| `duckdb_tables()` | table_name, schema_name, temporary, has_primary_key, estimated_size, column_count, sql |
| `duckdb_columns()` | column_name, table_name, data_type, is_nullable, column_default, numeric_precision |
| `duckdb_functions()` | function_name, function_type, parameter_types, return_type, internal |
| `duckdb_views()` | View definitions and metadata |
| `duckdb_indexes()` | Secondary index information |
| `duckdb_constraints()` | Constraint definitions |
| `duckdb_schemas()` | Database schema information |
| `duckdb_databases()` | Available databases and attachments |
| `duckdb_settings()` | Current configuration values |
| `duckdb_extensions()` | Loaded/installed extensions |
| `duckdb_types()` | Available data types |

**Example:**
```sql
SELECT table_name, estimated_size, column_count
FROM duckdb_tables()
WHERE schema_name = 'main' AND NOT internal;
```

### DESCRIBE / SHOW Statements

```sql
-- Describe table structure
DESCRIBE events;
SHOW events;

-- Describe query result structure
DESCRIBE SELECT * FROM events WHERE event_name = 'Page View';
```

### SUMMARIZE Statement

Computes statistical summary for all columns:

```sql
SUMMARIZE events;
SUMMARIZE SELECT * FROM events WHERE event_name = 'Purchase';
```

**Returns for each column:**
- `column_name`, `column_type`
- `min`, `max`
- `approx_unique` (approximate distinct count)
- `avg`, `std` (mean and standard deviation)
- `q25`, `q50`, `q75` (approximate quartiles)
- `count`
- `null_percentage`

**Note:** Quantiles are approximate values using T-Digest algorithm.

### PRAGMA Commands

| Command | Purpose |
|---------|---------|
| `PRAGMA table_info('table_name')` | Column ID, name, type, NOT NULL, default, primary key |
| `PRAGMA storage_info('table_name')` | Row groups, segments, compression, blocks |
| `PRAGMA database_size` | File size, block counts, WAL size, memory usage |
| `PRAGMA show_tables` | List all tables |
| `PRAGMA show_tables_expanded` | Detailed table information |
| `PRAGMA metadata_info` | Metadata store details |

**Example:**
```sql
PRAGMA table_info('events');
-- Returns: cid, name, type, notnull, dflt_value, pk
```

### Aggregate Functions for Profiling

#### Statistical Functions
| Function | Description |
|----------|-------------|
| `avg()`, `sum()` | Central tendency |
| `min()`, `max()` | Range bounds |
| `median()`, `mode()` | Additional central tendency |
| `var_pop()`, `var_samp()` | Variance |
| `stddev_pop()`, `stddev_samp()` | Standard deviation |
| `skewness()`, `kurtosis()` | Distribution shape |
| `entropy()` | Information entropy |
| `sem()` | Standard error of mean |
| `mad()` | Median absolute deviation |

#### Approximate Functions
| Function | Description |
|----------|-------------|
| `approx_count_distinct()` | HyperLogLog cardinality estimation |
| `approx_quantile(col, p)` | T-Digest approximate percentile |
| `approx_top_k(col, k)` | Filtered Space-Saving for frequent values |
| `reservoir_quantile()` | Reservoir sampling quantile |

#### Distribution Functions
| Function | Description |
|----------|-------------|
| `histogram(col)` | MAP of value -> count |
| `histogram_exact(col)` | Precise histogram |
| `histogram_values(col)` | Bin boundaries and frequencies |
| `quantile_cont(p)` | Continuous percentile (exact) |
| `quantile_disc(p)` | Discrete percentile (exact) |

#### List/Array Aggregates
| Function | Description |
|----------|-------------|
| `list(col)` / `array_agg(col)` | Collect values into list |
| `string_agg(col, separator)` | Concatenate strings |
| `bitstring_agg(col)` | Bitstring of value positions |

**Example profiling query:**
```sql
SELECT
    COUNT(*) as total_rows,
    COUNT(DISTINCT event_name) as unique_events,
    COUNT(DISTINCT distinct_id) as unique_users,
    MIN(event_time) as earliest_event,
    MAX(event_time) as latest_event,
    approx_count_distinct(properties->>'$.page') as approx_unique_pages
FROM events;
```

### Query Profiling

```sql
-- Enable profiling
PRAGMA enable_profiling;
SET profiling_mode = 'detailed';

-- Execute query (profile captured)
SELECT * FROM events WHERE event_name = 'Page View';

-- Output to file
SET profiling_output = '/path/to/profile.json';
```

---

## Similar Library Patterns

### ydata-profiling (formerly pandas-profiling)

**Philosophy:** One-line EDA with comprehensive reports.

**Statistics computed per type:**
- **Numeric:** mean, min, max, zeros, negatives, memory size, quantiles, skewness, kurtosis, histogram
- **Categorical:** distinct count, unique %, most common values, frequency distribution
- **DateTime:** min, max, range, histogram
- **Text:** length statistics, character distribution, word patterns
- **Boolean:** true/false counts, imbalance

**Data Quality Alerts:**
| Alert | Trigger |
|-------|---------|
| `CONSTANT` | Single unique value |
| `ZEROS` | High percentage of zeros |
| `MISSING` | Null/missing values |
| `HIGH_CARDINALITY` | Too many unique values |
| `UNIQUE` | All values are unique |
| `UNIFORM` | Uniform distribution (low information) |
| `IMBALANCE` | Skewed categorical distribution |
| `HIGH_CORRELATION` | Strong correlation between columns |
| `DUPLICATES` | Duplicate rows |
| `SKEWED` | Highly skewed distribution |
| `INFINITE` | Infinite values present |

**Correlation Methods:**
- Pearson (numeric)
- Spearman (ranked)
- Kendall (ordinal)
- Phi coefficient (binary)
- Cramér's V (categorical)

**Output Formats:** HTML report, JSON, widgets (Jupyter)

### Great Expectations

**Philosophy:** Data validation through declarative expectations.

**Expectation Categories:**

| Category | Examples |
|----------|----------|
| **Schema** | `expect_column_to_exist`, `expect_table_columns_to_match_ordered_list` |
| **Type** | `expect_column_values_to_be_of_type`, `expect_column_values_to_be_dateutil_parseable` |
| **Null** | `expect_column_values_to_not_be_null`, `expect_column_values_to_be_null` |
| **Uniqueness** | `expect_column_values_to_be_unique`, `expect_compound_columns_to_be_unique` |
| **Range** | `expect_column_values_to_be_between`, `expect_column_max_to_be_between` |
| **Set** | `expect_column_values_to_be_in_set`, `expect_column_distinct_values_to_be_in_set` |
| **Regex** | `expect_column_values_to_match_regex`, `expect_column_values_to_not_match_regex` |
| **Statistical** | `expect_column_mean_to_be_between`, `expect_column_stdev_to_be_between` |
| **Multi-column** | `expect_column_pair_values_to_be_in_set`, `expect_multicolumn_values_to_be_unique` |
| **Row-level** | `expect_table_row_count_to_be_between`, `expect_table_row_count_to_equal` |

**Data Quality Dimensions:**
- **Completeness:** Missing data checks
- **Uniqueness:** Duplicate detection
- **Consistency:** Cross-source validation
- **Validity:** Format and rule compliance
- **Timeliness:** Freshness checks

### Datasette

**Philosophy:** Instant API for SQLite/DuckDB databases.

**Introspection Endpoints:**
| Endpoint | Purpose |
|----------|---------|
| `/-/metadata.json` | Instance, database, table metadata |
| `/-/settings.json` | Configuration settings |
| `/-/config.json` | Instance configuration |
| `/database.json` | Database-level metadata |
| `/database/table.json` | Table data with column info |

**Column Information in Response:**
```json
{
  "columns": ["event_name", "event_time", "distinct_id"],
  "primary_keys": ["insert_id"],
  "count": 45230,
  "truncated": false
}
```

**Query Filtering:**
- Column filters: `?column__exact=`, `?column__contains=`, `?column__gt=`
- Full-text search: `?_search=`
- Custom WHERE: `?_where=`
- Shape control: `?_shape=array` | `objects` | `newline`

---

## Product Analytics Patterns

### Common SQL Patterns for Event Data

#### Event Distribution
```sql
-- Event frequency by name
SELECT
    event_name,
    COUNT(*) as count,
    COUNT(DISTINCT distinct_id) as unique_users,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () as pct
FROM events
GROUP BY event_name
ORDER BY count DESC;
```

#### User Activity
```sql
-- Events per user distribution
SELECT
    distinct_id,
    COUNT(*) as event_count,
    COUNT(DISTINCT event_name) as event_types,
    MIN(event_time) as first_seen,
    MAX(event_time) as last_seen
FROM events
GROUP BY distinct_id;
```

#### Property Analysis (JSON)
```sql
-- Extract and analyze JSON properties
SELECT
    properties->>'$.country' as country,
    COUNT(*) as events,
    COUNT(DISTINCT distinct_id) as users
FROM events
WHERE event_name = 'Page View'
GROUP BY country
ORDER BY events DESC;
```

#### Funnel Analysis (Window Functions)
```sql
-- Basic funnel with window functions
WITH user_events AS (
    SELECT
        distinct_id,
        event_name,
        event_time,
        ROW_NUMBER() OVER (PARTITION BY distinct_id ORDER BY event_time) as event_order
    FROM events
    WHERE event_time >= '2024-01-01'
)
SELECT
    'Step 1: Signup' as step,
    COUNT(DISTINCT distinct_id) as users
FROM user_events
WHERE event_name = 'Signup'

UNION ALL

SELECT
    'Step 2: Activation' as step,
    COUNT(DISTINCT a.distinct_id)
FROM user_events a
JOIN user_events b ON a.distinct_id = b.distinct_id
WHERE a.event_name = 'Signup'
  AND b.event_name = 'First Action'
  AND b.event_time > a.event_time;
```

#### Retention Cohort
```sql
-- Weekly retention by signup cohort
WITH cohorts AS (
    SELECT
        distinct_id,
        DATE_TRUNC('week', MIN(event_time)) as cohort_week
    FROM events
    GROUP BY distinct_id
),
activity AS (
    SELECT DISTINCT
        e.distinct_id,
        c.cohort_week,
        DATE_TRUNC('week', e.event_time) as activity_week
    FROM events e
    JOIN cohorts c ON e.distinct_id = c.distinct_id
)
SELECT
    cohort_week,
    DATEDIFF('week', cohort_week, activity_week) as weeks_since_signup,
    COUNT(DISTINCT distinct_id) as active_users
FROM activity
GROUP BY cohort_week, weeks_since_signup
ORDER BY cohort_week, weeks_since_signup;
```

### Property Extraction Patterns

DuckDB JSON syntax for Mixpanel properties:

```sql
-- String property
properties->>'$.country'

-- Numeric property (must cast)
CAST(properties->>'$.revenue' AS DECIMAL)

-- Nested property
properties->>'$.user.plan_type'

-- Check property exists
properties->>'$.coupon_code' IS NOT NULL

-- Array access
properties->'$.items'->0->>'$.name'
```

---

## Common Data Quality Issues

### Event Tracking Problems

| Issue | Description | Detection Pattern |
|-------|-------------|-------------------|
| **Inconsistent naming** | Same action with different names (`Signup`, `Signed Up`, `user_signup`) | Levenshtein distance on event names |
| **Missing required properties** | Events without expected context (e.g., page view without URL) | NULL checks on key properties |
| **Duplicate events** | Same event fired multiple times for one action | Group by insert_id, count > 1 |
| **Time gaps** | Missing data during certain periods | Date series with OUTER JOIN |
| **Property type drift** | Property changes from string to number | Type analysis over time windows |
| **Cardinality explosion** | Property with too many unique values (likely an ID) | approx_count_distinct thresholds |
| **Stale properties** | Properties that stopped being populated | Last non-null timestamp per property |

### Data Quality Checks for Event Data

#### Schema Validation
```sql
-- Events missing required properties
SELECT
    event_name,
    COUNT(*) as total,
    SUM(CASE WHEN properties->>'$.page' IS NULL THEN 1 ELSE 0 END) as missing_page,
    SUM(CASE WHEN properties->>'$.page' IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as pct_missing
FROM events
WHERE event_name = 'Page View'
GROUP BY event_name;
```

#### Cardinality Analysis
```sql
-- Property cardinality (potential ID fields)
SELECT
    'country' as property,
    approx_count_distinct(properties->>'$.country') as unique_values,
    COUNT(*) as total_events,
    approx_count_distinct(properties->>'$.country') * 100.0 / COUNT(*) as cardinality_pct
FROM events
WHERE properties->>'$.country' IS NOT NULL;
```

#### Temporal Patterns
```sql
-- Events per hour to detect tracking gaps
SELECT
    DATE_TRUNC('hour', event_time) as hour,
    COUNT(*) as events,
    COUNT(DISTINCT distinct_id) as users
FROM events
GROUP BY hour
ORDER BY hour;
```

#### Distinct ID Quality
```sql
-- Distinct ID patterns (potential anonymous/test IDs)
SELECT
    CASE
        WHEN distinct_id LIKE '%test%' THEN 'test'
        WHEN distinct_id LIKE '%anon%' THEN 'anonymous'
        WHEN LENGTH(distinct_id) > 100 THEN 'suspiciously_long'
        ELSE 'normal'
    END as id_type,
    COUNT(DISTINCT distinct_id) as unique_ids,
    COUNT(*) as events
FROM events
GROUP BY id_type;
```

### Mixpanel-Specific Quality Patterns

| Check | Query Pattern | Threshold |
|-------|---------------|-----------|
| Event volume anomaly | Day-over-day count change | > 50% change |
| Property fill rate | Non-null / total for each property | < 80% for required |
| User identity rate | Events with valid distinct_id | > 95% |
| Timestamp validity | Events in future or distant past | 0 violations |
| Insert ID uniqueness | Duplicate insert_ids | 0 duplicates |
| Session continuity | Gap between consecutive events | < 30 min expected |

---

## References

### DuckDB Documentation
- [Information Schema](https://duckdb.org/docs/stable/sql/meta/information_schema.html)
- [DuckDB Table Functions](https://duckdb.org/docs/stable/sql/meta/duckdb_table_functions.html)
- [SUMMARIZE](https://duckdb.org/docs/stable/guides/meta/summarize)
- [Aggregate Functions](https://duckdb.org/docs/stable/sql/functions/aggregates)
- [Pragmas](https://duckdb.org/docs/stable/configuration/pragmas)

### Similar Libraries
- [ydata-profiling GitHub](https://github.com/ydataai/ydata-profiling)
- [ydata-profiling Documentation](https://docs.profiling.ydata.ai/)
- [Great Expectations](https://greatexpectations.io/)
- [Great Expectations Data Quality Use Cases](https://docs.greatexpectations.io/docs/reference/learn/data_quality_use_cases/dq_use_cases_lp/)
- [Datasette JSON API](https://docs.datasette.io/en/stable/json_api.html)

### Product Analytics SQL
- [Funnel Analysis SQL (Optimizely)](https://www.optimizely.com/insights/blog/funnel-analysis-sql/)
- [Cohort Analysis (O'Reilly SQL for Data Analysis)](https://www.oreilly.com/library/view/sql-for-data/9781492088776/ch04.html)
- [Funnel Analysis with SQL and Python (Hex)](https://hex.tech/blog/funnel-analysis/)

### Data Quality
- [Business Impacts of Data Quality Issues (Mixpanel)](https://mixpanel.com/blog/the-business-impacts-of-data-quality-issues/)
- [JSON Schema Validation](https://json-schema.org/draft/2020-12/json-schema-validation)
