# Custom Property Formula Reference

Formulas use a SQL-like expression language. Variables (A, B, _A, etc.) map to properties via `composedProperties`.

## Variable Binding

`LET(name, expression, body)` — define intermediate results:
```
LET(raw, A, REGEX_REPLACE(raw, "pattern", "replacement"))
LET(x, A * B, IFS(x < 50, "low", x < 200, "mid", TRUE, "high"))
```

## Conditionals

`IF(cond, then, else)`, `IFS(cond1, val1, cond2, val2, ..., TRUE, default)`

## String Functions

`UPPER(s)`, `LOWER(s)`, `LEN(s)`, `LEFT(s, n)`, `RIGHT(s, n)`, `MID(s, start, count)`, `SPLIT(s, delim, n)`, `HAS_PREFIX(s, p)`, `HAS_SUFFIX(s, p)`, `PARSE_URL(s, "domain")`

## Regex Functions (PCRE2 engine)

- `REGEX_MATCH(haystack, pattern)` — returns true/false
- `REGEX_EXTRACT(haystack, pattern, capture_group)` — returns match or capture group
- `REGEX_REPLACE(haystack, pattern, replacement)` — replaces all matches

## Type Functions

`STRING(x)`, `NUMBER(x)`, `BOOLEAN(x)`, `DEFINED(x)`

## Math

`+`, `-`, `*`, `/`, `%`, `MIN(a,b)`, `MAX(a,b)`, `FLOOR(n)`, `CEIL(n)`, `ROUND(n)`

## Date

`DATEDIF(start, end, unit)` — units: D, M, Y, MD, YM, YD. `TODAY()` for current date.

## List

`SUM(list)`, `ANY(x, list, expr)`, `ALL(x, list, expr)`, `FILTER(x, list, expr)`, `MAP(x, list, expr)`

## Comparison, Logical & Constants

`==`, `!=`, `<`, `>`, `<=`, `>=` (case-insensitive for strings), `IN` for list membership. `AND`, `OR`, `NOT(x)`. Constants: `TRUE`, `FALSE`, `UNDEFINED`.

## Examples

**CamelCase splitting:** `REGEX_REPLACE(text, "(?-i)([a-z])([A-Z])", "$1 $2")` → "ChickenSundaysApril" becomes "Chicken Sundays April"

**Multi-step cleanup** (campaign names from Braze): Chain `LET` + `REGEX_REPLACE` to strip date prefixes, targeting codes, channel suffixes, and underscores in a single formula.
