# JQ Filter Support for CLI Output - TDD Implementation Plan

## Overview

Add `--jq` option to CLI commands for client-side JSON filtering using jq syntax. This enables power users to filter and transform JSON output without piping to external tools, following modern CLI patterns (gh, kubectl).

## Motivation

**Current workflow:**
```bash
mp inspect events --format json | jq '.[] | select(.event == "signup")'
```

**Problems:**
- Requires jq installed on system (platform-specific install)
- Extra shell plumbing
- No consistency across platforms (especially Windows)
- Breaks integration with non-shell environments

**With --jq support:**
```bash
mp inspect events --format json --jq '.[] | select(.event == "signup")'
```

**Benefits:**
- Native jq syntax with zero external dependencies
- Consistent experience across all platforms (Windows, macOS, Linux)
- Better integration with automation tools and AI agents
- Progressive disclosure: simple cases use `--format`, advanced cases use `--jq`

## Research Summary

**Library Selection: jq.py (PyPI: `jq`)**

| Criteria | Status |
|----------|--------|
| Maintenance | ✅ Active (v1.10.0, July 2025) |
| GitHub | ✅ 434 stars, 10 contributors |
| Dependents | ✅ 220 packages depend on it |
| Python support | ✅ 3.8-3.13 |

**Pre-built Wheels (no compilation needed):**
- ✅ Linux (x86, x86-64, arm64)
- ✅ macOS (Intel, Apple Silicon)
- ✅ Windows (x86, x86-64)

**Decision: Required Dependency**

jq.py is added as a **required** dependency, not optional. Rationale:
1. Pre-built wheels exist for all major platforms
2. Package already includes heavy native deps (pandas, duckdb)
3. Better UX - `--jq` works out of the box
4. No "gotcha" moment for users discovering the feature
5. Simpler documentation

## Scope

### In Scope
- `--jq` option on all commands that support `--format json/jsonl`
- Integration with existing formatter pipeline
- Unit tests for jq filtering logic
- Integration tests for CLI commands with --jq
- Property-based tests for jq filter edge cases
- Error messages for jq syntax errors
- Error messages for incompatible format combinations
- Documentation updates

### Out of Scope
- jq support for non-JSON formats (table, csv, plain)
- Custom jq functions or modules

## Design Decisions

### 1. Integration Point: Post-Formatter Pipeline

**Current flow:**
```
data → formatter (json/jsonl/table/csv/plain) → console.print()
```

**New flow:**
```
data → formatter → apply_jq_filter() → console.print()
                        ↑
                  (only for json/jsonl)
```

**Location:** Add `_apply_jq_filter()` helper in `cli/utils.py`

### 2. Format Compatibility

Only allow `--jq` with `--format json` or `--format jsonl`.

```bash
mp inspect events --format table --jq '.[]'  # ERROR: --jq requires json/jsonl
mp inspect events --format json --jq '.[]'   # OK
```

### 3. Error Handling

**Two error cases:**

A. Invalid jq syntax:
```
jq filter error: compile error: syntax error...
```

B. jq runtime error:
```
jq filter error: Cannot index string with number
```

**Exit Code:** `ExitCode.INVALID_ARGS` (3) for all jq errors

### 4. Output Format

Always pretty-print jq results as JSON:
- Single result → pretty-printed value
- Multiple results → pretty-printed array
- No results → `[]`

### 5. Per-Command Option

Add `--jq` to individual commands (not global), mirroring `--format` pattern.

## Architecture Changes

### Files Modified

```
pyproject.toml                    # Add jq>=1.9.0 to dependencies
src/mixpanel_data/cli/
├── options.py                    # Add JqOption type
├── utils.py                      # Add _apply_jq_filter(), update output_result()
└── commands/
    ├── inspect.py                # Add jq_filter param to commands
    ├── query.py                  # Add jq_filter param to commands
    └── fetch.py                  # Add jq_filter param to commands

tests/unit/cli/
├── test_utils.py                 # Tests for _apply_jq_filter()
├── test_jq_integration.py        # NEW: Integration tests
└── test_jq_pbt.py                # NEW: Property-based tests
```

### Type Definitions

**cli/options.py:**
```python
JqOption = Annotated[
    str | None,
    typer.Option(
        "--jq",
        help="Apply jq filter to JSON output.",
    ),
]
```

**cli/utils.py signature:**
```python
def output_result(
    ctx: typer.Context,
    data: dict[str, Any] | list[Any],
    columns: list[str] | None = None,
    *,
    format: str | None = None,
    jq_filter: str | None = None,  # NEW
) -> None:
```

## TDD Implementation Steps

### Phase 1: Add Dependency

**File:** `pyproject.toml`

```toml
dependencies = [
    # ... existing deps ...
    "jq>=1.9.0",
]
```

### Phase 2: Core jq Filtering Logic (TDD)

**Test File:** `tests/unit/cli/test_utils.py`

#### Test 2.1: Simple filter on dict
```python
def test_apply_jq_filter_simple_dict() -> None:
    """Test applying a simple jq filter to a dictionary."""
    json_str = '{"name": "Alice", "age": 30}'
    result = _apply_jq_filter(json_str, ".name")
    assert result == '"Alice"'
```

#### Test 2.2: Filter on list
```python
def test_apply_jq_filter_list() -> None:
    """Test applying jq filter to extract from list."""
    json_str = '[{"event": "Signup"}, {"event": "Purchase"}]'
    result = _apply_jq_filter(json_str, ".[] | .event")
    assert json.loads(result) == ["Signup", "Purchase"]
```

#### Test 2.3: Select filter
```python
def test_apply_jq_filter_select() -> None:
    """Test applying jq select filter."""
    json_str = '[{"event": "Signup", "count": 100}, {"event": "Login", "count": 50}]'
    result = _apply_jq_filter(json_str, '.[] | select(.count > 75)')
    parsed = json.loads(result)
    assert len(parsed) == 1
    assert parsed[0]["event"] == "Signup"
```

#### Test 2.4: Invalid jq syntax
```python
def test_apply_jq_filter_invalid_syntax() -> None:
    """Test error handling for invalid jq syntax."""
    json_str = '{"name": "test"}'
    with pytest.raises(typer.Exit) as exc_info:
        _apply_jq_filter(json_str, ".name |")  # Incomplete
    assert exc_info.value.exit_code == ExitCode.INVALID_ARGS
```

#### Test 2.5: jq runtime error
```python
def test_apply_jq_filter_runtime_error() -> None:
    """Test error handling for jq runtime errors."""
    json_str = '{"name": "test"}'
    with pytest.raises(typer.Exit) as exc_info:
        _apply_jq_filter(json_str, ".[0]")  # Index dict as array
    assert exc_info.value.exit_code == ExitCode.INVALID_ARGS
```

#### Test 2.6: Empty results
```python
def test_apply_jq_filter_empty_results() -> None:
    """Test jq filter that returns no results."""
    json_str = '[{"count": 10}, {"count": 20}]'
    result = _apply_jq_filter(json_str, '.[] | select(.count > 100)')
    assert json.loads(result) == []
```

#### Test 2.7: Single vs multiple results
```python
def test_apply_jq_filter_single_result() -> None:
    """Test jq filter returning a single scalar."""
    json_str = '{"data": [1, 2, 3]}'
    result = _apply_jq_filter(json_str, '.data | length')
    assert result == "3"

def test_apply_jq_filter_multiple_results() -> None:
    """Test jq filter returning multiple results."""
    json_str = '[{"x": 1}, {"x": 2}]'
    result = _apply_jq_filter(json_str, '.[].x')
    assert json.loads(result) == [1, 2]
```

**Implementation:**
```python
def _apply_jq_filter(json_str: str, filter_expr: str) -> str:
    """Apply jq filter to JSON string.

    Args:
        json_str: JSON string to filter.
        filter_expr: jq filter expression.

    Returns:
        Filtered JSON string (pretty-printed).

    Raises:
        typer.Exit: If filter syntax invalid or runtime error occurs.
    """
    import jq

    try:
        data = json.loads(json_str)
        compiled = jq.compile(filter_expr)
        results = list(compiled.input(data).all())

        if len(results) == 0:
            return "[]"
        elif len(results) == 1:
            return json.dumps(results[0], indent=2, default=_json_serializer, ensure_ascii=False)
        else:
            return json.dumps(results, indent=2, default=_json_serializer, ensure_ascii=False)

    except ValueError as e:
        # jq compile/runtime errors
        err_console.print(f"[red]jq filter error:[/red] {e}")
        raise typer.Exit(ExitCode.INVALID_ARGS) from None
    except json.JSONDecodeError as e:
        err_console.print(f"[red]Invalid JSON:[/red] {e}")
        raise typer.Exit(ExitCode.GENERAL_ERROR) from None
```

### Phase 3: Integration with output_result() (TDD)

**Test File:** `tests/unit/cli/test_utils.py`

#### Test 3.1: output_result with jq filter
```python
def test_output_result_with_jq_filter_json(mock_context, capsys) -> None:
    """Test output_result applies jq filter for JSON format."""
    data = [{"event": "Signup", "count": 100}, {"event": "Login", "count": 50}]
    output_result(mock_context, data, format="json", jq_filter=".[] | select(.count > 75)")
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert len(result) == 1
    assert result[0]["event"] == "Signup"
```

#### Test 3.2: Reject jq with table format
```python
def test_output_result_rejects_jq_with_table_format(mock_context) -> None:
    """Test that jq filter is rejected for table format."""
    data = [{"event": "Signup"}]
    with pytest.raises(typer.Exit) as exc_info:
        output_result(mock_context, data, format="table", jq_filter=".[]")
    assert exc_info.value.exit_code == ExitCode.INVALID_ARGS
```

#### Test 3.3: Reject jq with csv format
```python
def test_output_result_rejects_jq_with_csv_format(mock_context) -> None:
    """Test that jq filter is rejected for csv format."""
    data = [{"event": "Signup"}]
    with pytest.raises(typer.Exit) as exc_info:
        output_result(mock_context, data, format="csv", jq_filter=".[]")
    assert exc_info.value.exit_code == ExitCode.INVALID_ARGS
```

#### Test 3.4: Reject jq with plain format
```python
def test_output_result_rejects_jq_with_plain_format(mock_context) -> None:
    """Test that jq filter is rejected for plain format."""
    data = [{"event": "Signup"}]
    with pytest.raises(typer.Exit) as exc_info:
        output_result(mock_context, data, format="plain", jq_filter=".[]")
    assert exc_info.value.exit_code == ExitCode.INVALID_ARGS
```

#### Test 3.5: No jq filter works normally
```python
def test_output_result_without_jq_filter(mock_context, capsys) -> None:
    """Test that output_result works normally without jq filter."""
    data = {"event": "Signup", "count": 100}
    output_result(mock_context, data, format="json")
    captured = capsys.readouterr()
    assert json.loads(captured.out) == data
```

### Phase 4: Add JqOption (TDD)

**Test File:** `tests/unit/cli/test_options.py` (NEW)

```python
def test_jq_option_type() -> None:
    """Test that JqOption has correct type annotation."""
    from mixpanel_data.cli.options import JqOption
    import typing
    actual_type = typing.get_args(JqOption)[0]
    assert actual_type == str | None
```

### Phase 5: Command Integration (TDD)

**Test File:** `tests/unit/cli/test_jq_integration.py` (NEW)

#### Test 5.1: inspect events with --jq
```python
def test_inspect_events_with_jq_filter(cli_runner, mock_workspace) -> None:
    """Test inspect events command with --jq filter."""
    mock_workspace.events.return_value = ["Signup", "Login", "Purchase"]
    with patch("mixpanel_data.cli.commands.inspect.get_workspace", return_value=mock_workspace):
        result = cli_runner.invoke(
            app,
            ["inspect", "events", "--format", "json", "--jq", '.[0]']
        )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == "Signup"
```

#### Test 5.2: inspect events --jq with incompatible format
```python
def test_inspect_events_jq_with_table_fails(cli_runner, mock_workspace) -> None:
    """Test that --jq fails with --format table."""
    mock_workspace.events.return_value = ["Signup"]
    with patch("mixpanel_data.cli.commands.inspect.get_workspace", return_value=mock_workspace):
        result = cli_runner.invoke(
            app,
            ["inspect", "events", "--format", "table", "--jq", ".[]"]
        )
    assert result.exit_code == ExitCode.INVALID_ARGS
```

#### Test 5.3: query sql with --jq
```python
def test_query_sql_with_jq_filter(cli_runner, mock_workspace) -> None:
    """Test query sql command with --jq filter."""
    mock_workspace.sql_rows.return_value = [
        {"event": "Signup", "count": 100},
        {"event": "Login", "count": 50}
    ]
    with patch("mixpanel_data.cli.commands.query.get_workspace", return_value=mock_workspace):
        result = cli_runner.invoke(
            app,
            ["query", "sql", "SELECT * FROM events", "--format", "json", "--jq", ".[] | select(.count > 75)"]
        )
    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert len(output) == 1
    assert output[0]["event"] == "Signup"
```

### Phase 6: Property-Based Tests (TDD)

**Test File:** `tests/unit/cli/test_jq_pbt.py` (NEW)

```python
from hypothesis import given, strategies as st

@given(st.builds(dict, name=st.text(min_size=1), count=st.integers()))
def test_jq_identity_preserves_structure(data: dict) -> None:
    """Test that identity filter '.' preserves JSON structure."""
    json_str = json.dumps(data)
    result = _apply_jq_filter(json_str, ".")
    assert json.loads(result) == data

@given(st.lists(st.builds(dict, x=st.integers()), min_size=1, max_size=20))
def test_jq_length_returns_correct_count(data: list) -> None:
    """Test that 'length' filter returns correct list length."""
    json_str = json.dumps(data)
    result = _apply_jq_filter(json_str, "length")
    assert int(result) == len(data)

@given(st.lists(st.builds(dict, count=st.integers(0, 100)), min_size=1, max_size=20))
def test_jq_select_never_increases_size(data: list) -> None:
    """Test that select filter never increases list size."""
    json_str = json.dumps(data)
    result = _apply_jq_filter(json_str, ".[] | select(.count > 50)")
    parsed = json.loads(result) if result != "[]" else []
    assert len(parsed) <= len(data)
```

### Phase 7: Update Commands

Add `jq_filter: JqOption = None` parameter to all commands with `--format`:

**inspect.py commands:**
- events, properties, values, funnels, cohorts, top_events, bookmarks
- lexicon_schemas, lexicon_schema
- distribution, numeric, daily, engagement, coverage
- info, tables, schema, sample, summarize, breakdown, keys, column

**query.py commands:**
- sql, segmentation, funnel, retention, jql

**fetch.py commands:**
- events, profiles

Example update:
```python
@inspect_app.command("events")
@handle_errors
def inspect_events(
    ctx: typer.Context,
    format: FormatOption = "json",
    jq_filter: JqOption = None,
) -> None:
    """List all event names from Mixpanel project.

    Examples:
        mp inspect events
        mp inspect events --format json --jq '.[0:5]'
    """
    workspace = get_workspace(ctx, read_only=True)
    with status_spinner(ctx, "Fetching events..."):
        events = workspace.events()
    output_result(ctx, events, format=format, jq_filter=jq_filter)
```

### Phase 8: Update Documentation (`docs/`)

Review and update all documentation files to include `--jq` option where relevant.

**Files to review:**

| File | Updates Needed |
|------|----------------|
| `docs/cli/commands.md` | Add `--jq` to command reference, examples |
| `docs/cli/index.md` | Mention `--jq` in CLI overview |
| `docs/getting-started/quickstart.md` | Add `--jq` example in quick start |
| `docs/guide/discovery.md` | Add `--jq` examples for filtering discovery results |
| `docs/guide/live-analytics.md` | Add `--jq` examples for filtering query results |
| `docs/guide/sql-queries.md` | Add `--jq` examples for post-processing SQL output |

**Documentation pattern:**
```markdown
## Filtering Output with jq

All commands that support `--format json` also support `--jq` for client-side filtering:

```bash
# Get first 5 events
mp inspect events --format json --jq '.[:5]'

# Filter segmentation results
mp query segmentation --event Signup --from 2024-01-01 --to 2024-01-31 \
  --format json --jq '.series.total | to_entries | map({date: .key, count: .value})'

# Extract specific fields from SQL results
mp query sql "SELECT * FROM events LIMIT 100" \
  --format json --jq '.[] | {event, time: .properties.time}'
```

See the [jq manual](https://jqlang.org/manual/) for filter syntax.
```

### Phase 9: Update Plugin (`mixpanel-plugin/`)

Review and update all plugin files to include `--jq` option where relevant.

**Files to review:**

| File | Updates Needed |
|------|----------------|
| `mixpanel-plugin/commands/mp-inspect.md` | Add `--jq` examples |
| `mixpanel-plugin/commands/mp-query.md` | Add `--jq` examples |
| `mixpanel-plugin/commands/mp-fetch.md` | Add `--jq` examples |
| `mixpanel-plugin/skills/mixpanel-data/SKILL.md` | Mention `--jq` capability |
| `mixpanel-plugin/skills/mixpanel-data/references/cli-commands.md` | Document `--jq` option |
| `mixpanel-plugin/skills/mixpanel-data/references/patterns.md` | Add `--jq` patterns |
| `mixpanel-plugin/agents/mixpanel-analyst.md` | Include `--jq` in agent context |
| `mixpanel-plugin/agents/jql-expert.md` | Include `--jq` for post-processing |
| `mixpanel-plugin/agents/funnel-optimizer.md` | Include `--jq` for result filtering |
| `mixpanel-plugin/agents/retention-specialist.md` | Include `--jq` for result filtering |

**Plugin documentation pattern:**
```markdown
## Output Filtering

Use `--jq` to filter JSON output without external tools:

```bash
# Filter events by name pattern
mp inspect events --format json --jq '.[] | select(startswith("User"))'

# Extract funnel conversion rates
mp query funnel --funnel-id 12345 --format json \
  --jq '.steps | map({step: .step, rate: .conversion_rate})'
```
```

**Validation:**
After updates, run plugin validation:
```bash
cd mixpanel-plugin && ./scripts/validate.sh
```

## Testing Checklist

- [ ] All unit tests pass for `_apply_jq_filter()`
- [ ] All integration tests pass for commands with `--jq`
- [ ] Property-based tests pass
- [ ] Coverage remains ≥90%
- [ ] `just check` passes (lint, typecheck, test)
- [ ] Manual testing on local machine

## Acceptance Criteria

### Core Implementation
- [ ] `jq>=1.9.0` added to required dependencies
- [ ] All commands with `--format` support `--jq` parameter
- [ ] `--jq` only works with `--format json/jsonl` (clear error otherwise)
- [ ] Invalid jq syntax shows clear error with exit code 3
- [ ] jq runtime errors show clear error with exit code 3
- [ ] All tests pass (unit, integration, property-based)
- [ ] Test coverage remains ≥90%
- [ ] Type checking passes (`mypy --strict`)
- [ ] Linting passes (`ruff check`, `ruff format`)
- [ ] Docstrings updated with `--jq` examples

### Documentation (`docs/`)
- [ ] `docs/cli/commands.md` updated with `--jq` reference
- [ ] `docs/cli/index.md` mentions `--jq` capability
- [ ] `docs/getting-started/quickstart.md` includes `--jq` example
- [ ] `docs/guide/discovery.md` has `--jq` filtering examples
- [ ] `docs/guide/live-analytics.md` has `--jq` filtering examples
- [ ] `docs/guide/sql-queries.md` has `--jq` filtering examples

### Plugin (`mixpanel-plugin/`)
- [ ] `mixpanel-plugin/commands/mp-*.md` files updated with `--jq` examples
- [ ] `mixpanel-plugin/skills/mixpanel-data/SKILL.md` mentions `--jq`
- [ ] `mixpanel-plugin/skills/mixpanel-data/references/cli-commands.md` documents `--jq`
- [ ] `mixpanel-plugin/skills/mixpanel-data/references/patterns.md` has `--jq` patterns
- [ ] `mixpanel-plugin/agents/*.md` files include `--jq` context
- [ ] Plugin validation passes (`./scripts/validate.sh`)

## Implementation Estimate

**Complexity:** Low-Medium
**Lines of Code:** ~50-100 (implementation) + tests + documentation updates
**Estimated Time:** 6-8 hours total
- Phases 1-7 (Core): 4-5 hours
- Phase 8 (docs/): 1 hour
- Phase 9 (mixpanel-plugin/): 1-2 hours

## References

- [jq.py on PyPI](https://pypi.org/project/jq/)
- [jq.py GitHub](https://github.com/mwilliamson/jq.py)
- [jq Manual](https://jqlang.org/manual/)
- [gh CLI --jq reference](https://cli.github.com/manual/gh_help_formatting)
