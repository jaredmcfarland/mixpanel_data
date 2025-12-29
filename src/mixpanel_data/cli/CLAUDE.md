# CLI Package

The `mp` command-line interface for `mixpanel_data`—a complete programmable interface to Mixpanel analytics. Built with Typer.

## Command Groups

| Group | Purpose |
|-------|---------|
| `auth` | Account management (login, logout, list, switch) |
| `fetch` | Data retrieval into local DuckDB (events, profiles) |
| `query` | Live Mixpanel API queries (segmentation, funnels, retention, JQL) |
| `inspect` | Local database introspection (tables, schema, sample, stats) |

## Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point, global options, command registration |
| `formatters.py` | Output formatters (JSON, JSONL, table, CSV, plain) |
| `utils.py` | Error handling, workspace helpers, output routing |
| `options.py` | Shared option type aliases (`FormatOption`) |
| `validators.py` | Literal type validators for CLI parameters |
| `commands/` | Command group implementations |

## Global Options

Defined in `main.py`:
- `--account, -a`: Named account to use
- `--quiet, -q`: Suppress progress output
- `--verbose, -v`: Enable debug output
- `--version`: Show version and exit

## Architecture

```
mp command → main.py callback → command handler
                   ↓
              ctx.obj = {account, quiet, verbose, workspace, config}
                   ↓
              get_workspace(ctx) / get_config(ctx)
                   ↓
              Workspace or ConfigManager
```

## Output Flow

1. Command calls `output_result(ctx, data, format=format)`
2. `output_result()` routes to appropriate formatter
3. Formatter converts data to string or Rich Table
4. Output printed to stdout via `console`

Errors go to stderr via `err_console`.

## Error Handling

`@handle_errors` decorator maps exceptions to exit codes:

| Exception | Exit Code |
|-----------|-----------|
| `AuthenticationError` | 2 |
| `AccountNotFoundError` | 4 |
| `TableNotFoundError` | 4 |
| `RateLimitError` | 5 |
| `QueryError` | 3 |
| `ConfigError` | 1 |
| `MixpanelDataError` | 1 |

## Adding New Commands

1. Create or extend file in `commands/`
2. Use Typer decorators and Annotated types
3. Apply `@handle_errors` decorator
4. Use helpers: `get_workspace()`, `get_config()`, `output_result()`
5. Register command group in `main.py:_register_commands()`
