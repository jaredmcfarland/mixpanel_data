# CLI Commands

Typer command groups for the `mp` CLI. Each file defines a subcommand group.

## Files

| File | Command Group | Purpose |
|------|---------------|---------|
| `auth.py` | `mp auth` | Account management (add, remove, list, test, set-default) |
| `inspect.py` | `mp inspect` | Schema discovery (events, properties, funnels, cohorts, bookmarks) |
| `query.py` | `mp query` | Query execution (segmentation, funnel, retention, jql) |
| `dashboards.py` | `mp dashboards` | Dashboard CRUD (list, create, get, update, delete, favorite, pin, blueprints, RCA) |
| `reports.py` | `mp reports` | Report/bookmark CRUD (list, create, get, update, delete, bulk operations, history) |
| `cohorts.py` | `mp cohorts` | Cohort CRUD (list, create, get, update, delete, bulk operations) |

## Command Pattern

All commands follow this pattern:

```python
@app.command()
@handle_errors  # Converts exceptions to exit codes
def command_name(
    ctx: typer.Context,
    # Annotated options...
    format: FormatOption = "json",
) -> None:
    """Docstring becomes --help text."""
    workspace = get_workspace(ctx)  # Lazy workspace from context
    result = workspace.some_method(...)
    output_result(ctx, result.to_dict(), format=format)
```

## Key Helpers

From `cli/utils.py`:
- `@handle_errors`: Decorator converting exceptions to exit codes
- `get_workspace(ctx)`: Get/create workspace from context (respects `--account`)
- `get_config(ctx)`: Get/create ConfigManager from context
- `output_result(ctx, data)`: Format and output data per `--format` option

## Output Formats

All data commands support `--format`:
- `json` (default): Pretty-printed JSON
- `jsonl`: One JSON object per line
- `table`: Rich ASCII table
- `csv`: Comma-separated with headers
- `plain`: Minimal text output

## Exit Codes

From `ExitCode` enum:
- 0: Success
- 1: General error
- 2: Authentication error
- 3: Invalid arguments
- 4: Not found
- 5: Rate limited
- 130: Interrupted (Ctrl+C)

## Adding New Commands

1. Add command to appropriate group file
2. Use `@handle_errors` decorator
3. Accept `format: FormatOption` for data output
4. Call `output_result()` with serializable dict/list
5. Follow existing docstring conventions for --help
