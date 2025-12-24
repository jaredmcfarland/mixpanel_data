# Copilot Instructions for mixpanel_data

## Project Overview

**mixpanel_data** is a Python library and CLI for working with Mixpanel analytics data, designed for AI coding agents. The project is in **early implementation phase** with foundation layer complete (~1,100 lines of code, 93 tests, 97% coverage).

**Core Concept**: Fetch Mixpanel data once into a local DuckDB database, then query repeatedly with SQL—preserving context window for reasoning rather than consuming it with raw API responses.

**Technology Stack**: Python 3.11+, Pydantic v2, DuckDB (future), httpx (future), Typer CLI (future), pandas, pytest, ruff, mypy

**Current Status**: Foundation layer complete (ConfigManager, exceptions, result types). Next phases: API client, storage engine, services, CLI.

## Build & Test Setup

### Prerequisites
- Python 3.12.3 (or Python 3.11+)
- [uv](https://docs.astral.sh/uv/) - Python package manager

### Development Commands

This project uses `uv` for dependency management and running tools.

| Command | Description |
|---------|-------------|
| `uv sync --all-extras` | Sync all dependencies |
| `uv run pytest` | Run tests |
| `uv run pytest --cov=src/mixpanel_data` | Run tests with coverage |
| `uv run ruff check src/ tests/` | Lint code with ruff |
| `uv run ruff check --fix src/ tests/` | Auto-fix lint errors |
| `uv run ruff format src/ tests/` | Format code with ruff |
| `uv run mypy src/` | Type check with mypy |
| `uv build` | Build package |

### Installation & Setup
**ALWAYS sync dependencies before any development work:**
```bash
uv sync --all-extras
```

This installs all dependencies including dev extras (pytest, ruff, mypy, pytest-cov, pandas-stubs).

### Testing
**Run all tests:**
```bash
uv run pytest
```

**Run tests with coverage (target: 95%+):**
```bash
uv run pytest --cov=src/mixpanel_data --cov-report=term-missing
```

**Run specific tests:**
```bash
uv run pytest -k test_name
uv run pytest tests/unit/test_config.py
```

Tests are organized:
- `tests/unit/` - Unit tests for individual components
- `tests/integration/` - Integration tests for workflows
- `tests/conftest.py` - Shared fixtures (temp_dir, config_path, config_manager, sample_credentials)

### Linting & Type Checking

**ALWAYS run all checks before committing:**
```bash
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest
```

**Auto-fix linting issues:**
```bash
uv run ruff check --fix src/ tests/
```

**Type checking only (must pass with zero errors):**
```bash
uv run mypy src/
```
Note: Tests are excluded from strict type checking (see pyproject.toml `tool.mypy.overrides`)

### Building the Package
**To build distribution packages:**
```bash
uv build
```
Creates wheel and sdist in `dist/`

## Project Structure

```
/home/runner/work/mixpanel_data/mixpanel_data/
├── src/mixpanel_data/          # Main source code
│   ├── __init__.py             # Public API exports (exceptions, result types)
│   ├── auth.py                 # Auth module (placeholder)
│   ├── exceptions.py           # All exception classes (85 lines, 100% coverage)
│   ├── types.py                # Result types: FetchResult, SegmentationResult, etc. (158 lines)
│   ├── py.typed                # PEP 561 marker for type checking
│   └── _internal/              # Private implementation (not in public API)
│       ├── config.py           # ConfigManager, Credentials, AccountInfo (153 lines, 96% coverage)
│       └── __init__.py
├── tests/                      # Test suite (93 tests)
│   ├── conftest.py             # Shared pytest fixtures
│   ├── unit/                   # Unit tests
│   │   ├── test_config.py      # ConfigManager tests
│   │   ├── test_exceptions.py  # Exception tests
│   │   └── test_types.py       # Result type tests
│   └── integration/            # Integration tests
│       ├── test_foundation.py  # Foundation layer workflow tests
│       └── test_config_file.py # Config file persistence tests
├── context/                    # Design documentation
│   ├── mixpanel_data-design.md              # Architecture & component specs
│   ├── mixpanel_data-project-brief.md       # Vision and goals
│   ├── mp-cli-project-spec.md               # CLI specification
│   ├── MIXPANEL_DATA_MODEL_REFERENCE.md     # Mixpanel data model
│   └── mixpanel-http-api-specification.md   # Mixpanel HTTP API (all 11 APIs)
├── specs/                      # Implementation specifications
│   └── 001-foundation-layer/   # Foundation layer spec (current phase)
├── pyproject.toml              # Project configuration (build, deps, tools)
├── README.md                   # User-facing documentation
├── CLAUDE.md                   # Claude Code specific guidance
└── .gitignore                  # Git ignore patterns
```

## Architecture

**Layered Design:**
```
CLI Layer (Typer)           → [NOT IMPLEMENTED] Argument parsing, output formatting
    ↓
Public API Layer            → [PARTIAL] Workspace class (future), auth module (stub)
    ↓
Service Layer               → [NOT IMPLEMENTED] DiscoveryService, FetcherService, LiveQueryService
    ↓
Infrastructure Layer        → [PARTIAL] ConfigManager (✓), MixpanelAPIClient (future), StorageEngine (future)
```

**Key Design Principles:**
- **Explicit table management**: Tables never implicitly overwritten; raise `TableExistsError` if exists
- **Immutable credentials**: Resolved once at Workspace construction
- **Frozen dataclasses**: All result types are frozen (immutable)
- **Dependency injection**: Services accept dependencies as constructor arguments

## Development Workflow

### Configuration System
Config file: `~/.mp/config.toml` (TOML format)
- Multiple named accounts supported
- One account marked as default
- Environment variables override config file: `MP_USERNAME`, `MP_SECRET`, `MP_PROJECT_ID`, `MP_REGION`, `MP_CONFIG_PATH`

### Adding New Code
1. **Check design docs first**: `docs/mixpanel_data-design.md` and `specs/001-foundation-layer/` contain detailed specifications
2. **Follow existing patterns**: Look at `config.py`, `exceptions.py`, `types.py` for style
3. **Use Pydantic v2**: For validation and data models (frozen dataclasses with `model_config`)
4. **Type annotations**: Use `from __future__ import annotations` and full type hints
5. **Docstrings**: Google-style docstrings for classes and public methods

### Writing Tests
1. **Use fixtures**: Import from `conftest.py` (`temp_dir`, `config_path`, `config_manager`, `sample_credentials`)
2. **Test organization**: Group tests in classes by component (e.g., `TestConfigManager`)
3. **Naming**: `test_<what_is_being_tested>` (e.g., `test_add_account_stores_correctly`)
4. **Coverage target**: 95%+ (currently 97%)
5. **Frozen models**: Use `pytest.raises(dataclasses.FrozenInstanceError)` for immutability tests

### Code Style
- **Line length**: 88 characters (Black-compatible)
- **Imports**: Sorted with isort (included in ruff)
- **String quotes**: No preference (project uses both single and double)
- **Type hints**: Always use (mypy strict mode enabled)

## Known Issues & Workarounds

### Test Execution
- **All tests pass**: 93/93 tests pass in ~1 second
- **No flaky tests**: Tests are deterministic
- **No timing issues**: All tests complete quickly

### Python Version
- **Required**: Python 3.11+ (specified in pyproject.toml)
- **Tested**: Python 3.12.3
- **tomli**: For Python <3.11 TOML parsing (not needed with 3.11+, which has tomllib built-in)

## File Locations Quick Reference

**Main Source Files:**
- Public API: `src/mixpanel_data/__init__.py`
- Exceptions: `src/mixpanel_data/exceptions.py`
- Result types: `src/mixpanel_data/types.py`
- Config management: `src/mixpanel_data/_internal/config.py`

**Test Files:**
- Unit tests: `tests/unit/test_*.py`
- Integration tests: `tests/integration/test_*.py`
- Shared fixtures: `tests/conftest.py`

**Configuration:**
- Package config: `pyproject.toml` (dependencies, tool configs)
- Ruff config: `[tool.ruff]` section in pyproject.toml
- Mypy config: `[tool.mypy]` section in pyproject.toml
- Pytest config: `[tool.pytest.ini_options]` section in pyproject.toml
- Git ignore: `.gitignore`

**Documentation:**
- User docs: `README.md`
- Design specs: `context/*.md`
- Mixpanel API: `context/mixpanel-http-api-specification.md`
- Implementation specs: `specs/001-foundation-layer/`
- AI guidance: `CLAUDE.md`

## Trust These Instructions

**These instructions have been validated** by running all commands in the actual environment. If you encounter issues:
1. First verify you're in the correct directory: `/home/runner/work/mixpanel_data/mixpanel_data`
2. Check if dependencies are synced: `uv sync --all-extras`
3. Only then search for additional information or report the issue

**Command execution times** (for timeout planning):
- `uv sync --all-extras`: 30-60 seconds (first run), <5 seconds (subsequent)
- `uv run pytest`: ~1 second
- `uv run pytest --cov`: ~1 second
- `uv run ruff check`: <1 second
- `uv run mypy src/`: 2-3 seconds
- `uv build`: ~30 seconds

---

## Code Review Guidelines

When performing code reviews, apply the following project-specific checks:

### Architecture Enforcement

**Layer Boundaries**: This project uses a layered architecture (CLI → Public API → Service → Infrastructure). Flag any code that:
- Imports from `_internal/` in public modules (only `auth.py` is allowed to re-export)
- Has CLI code directly accessing storage or API clients (should go through Workspace facade)
- Has services calling other services horizontally (they should only call infrastructure)

**Private API Leakage**: The `src/mixpanel_data/_internal/` directory is private implementation. Flag any:
- Direct imports of `_internal` modules in user-facing code
- Types from `_internal/` appearing in public function signatures
- `__all__` exports that include `_internal` symbols

### Exception Handling

Use the library's exception hierarchy—never bare exceptions. Flag:
- `except Exception:` or `except BaseException:` (should be `except MixpanelDataError:`)
- `raise Exception(...)` (should use a specific subclass like `ConfigError`, `QueryError`, etc.)
- Missing exception chaining (`raise X from e`)

**Valid exception classes**: `MixpanelDataError`, `ConfigError`, `AccountNotFoundError`, `AccountExistsError`, `AuthenticationError`, `RateLimitError`, `QueryError`, `TableExistsError`, `TableNotFoundError`

### Security: Credential Handling

Flag any code that could expose secrets:
- Logging or printing `Credentials` objects without going through `__repr__` (which redacts)
- Using `str(secret)` instead of `secret.get_secret_value()` for SecretStr
- f-strings or `.format()` that interpolate secret values
- Secrets in error messages or exception details dicts

### Immutability Patterns

All result types and credentials must be immutable. Flag:
- Dataclasses without `frozen=True`
- Pydantic models without `model_config = ConfigDict(frozen=True)`
- Code that mutates frozen objects (should use `object.__setattr__` for internal caching only)
- Mutable default arguments (`list` instead of `field(default_factory=list)`)

### Explicit Table Management

This project uses explicit table lifecycle—never implicit overwrites. Flag:
- Storage methods that silently overwrite existing tables
- Missing `TableExistsError` checks before table creation
- Missing `TableNotFoundError` checks when accessing tables

### Streaming and Memory Efficiency

Data should flow through iterators, not be loaded entirely into memory. Flag:
- Functions returning `list[dict]` when they should return `Iterator[dict]`
- Collecting all results with `list()` when streaming is possible
- Large data structures stored in variables when they could be yielded

### Dependency Injection

Services must accept dependencies via constructor for testability. Flag:
- Services that instantiate their own `MixpanelAPIClient` or `StorageEngine`
- Direct `ConfigManager()` calls instead of accepting injected config
- Hardcoded paths or URLs that should be parameters

### Type Annotations

This is a PEP 561 typed package (`py.typed`). Flag:
- Missing return type annotations
- `Any` used when a specific type is known
- Missing type annotations on public function parameters
- Use of `Optional[X]` instead of `X | None` (project uses modern union syntax)
