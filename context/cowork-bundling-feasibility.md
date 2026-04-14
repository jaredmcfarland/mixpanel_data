# Feasibility Report: Bundling mixpanel_data into the Claude Cowork Plugin

**Date**: 2026-04-13
**Author**: Claude (at Jared's request)
**Status**: Analysis complete

---

## Executive Summary

**Can we package the entire `mixpanel_data` Python library into a ZIP with the existing plugin so it works in Cowork without `pip install`?**

**Verdict: Not fully, but close.** The library source code (1.8 MB) can be bundled easily. However, four of its nine runtime dependencies contain **native C/Rust extensions** that are platform-specific binaries — they cannot be pre-compiled into a universal ZIP. A hybrid approach (bundled source + SessionStart hook for native deps) is the recommended path.

---

## Current State

### Plugin (mixpanel-plugin/)
| Metric | Value |
|--------|-------|
| Size | 740 KB |
| Components | 5 agents, 3 skills, 1 command, 2 scripts |
| Cowork support | Full (auth bridge, auto-detection, token refresh) |
| Distribution | Not yet packaged as ZIP |

### Library (src/mixpanel_data/)
| Metric | Value |
|--------|-------|
| Source files | 66 Python files |
| Lines of code | 55,334 |
| Source size (no cache) | 1.8 MB |
| Python version | 3.10+ |
| Version | 0.2.0 |

### Current Install Flow
1. User runs `/mixpanel-data:setup`
2. `setup.sh` executes `pip install git+https://github.com/jaredmcfarland/mixpanel_data.git`
3. Also installs pandas, numpy, matplotlib, seaborn, networkx, anytree, scipy
4. Total download + install: **~103 MB** of site-packages

---

## The Blocker: Native Extensions

Four runtime dependencies ship **compiled C/Rust binaries** (`.so`/`.dylib` files):

| Package | Size | Extension Type | Why Native |
|---------|------|---------------|------------|
| **numpy** | 21.7 MB | C + Fortran | Linear algebra, array operations |
| **pandas** | 45.5 MB | Cython → C | DataFrame internals, parsers |
| **pydantic-core** | 4.4 MB | Rust (PyO3) | Validation engine |
| **jq** | < 0.1 MB | C (libjq) | JSON query processing |

These `.so` files are compiled for a specific platform + Python version combination (e.g., `cpython-312-darwin-arm64`). **Cowork VMs run Linux x86_64** — macOS binaries won't load there.

### Pure-Python Dependencies (safe to bundle)

| Package | Size | Notes |
|---------|------|-------|
| networkx | 10.9 MB | Graph algorithms |
| rich | 1.9 MB | Terminal formatting |
| httpx + httpcore | 1.2 MB | HTTP client |
| click | 0.8 MB | CLI framework |
| typer | 0.4 MB | CLI framework (wraps click) |
| anyio | 1.3 MB | Async I/O |
| pygments | 4.7 MB | Syntax highlighting |
| anytree | 0.3 MB | Tree structures |
| certifi, idna, h11, etc. | ~1.5 MB | HTTP internals |

**Total pure-Python deps**: ~23 MB (uncompressed)

---

## Cowork Plugin Constraints

| Constraint | Value | Source |
|------------|-------|--------|
| Max ZIP size | **50 MB** | Cowork admin plugin upload |
| Plugin root | `${CLAUDE_PLUGIN_ROOT}` | Read-only after install, changes on update |
| Persistent data | `${CLAUDE_PLUGIN_DATA}` | Survives updates, at `~/.claude/plugins/data/{id}/` |
| VM platform | **Linux x86_64** | Sandboxed Cowork VM |
| VM Python | Typically 3.12+ | Pre-installed in sandbox |
| Network access | **Yes** (public internet) | pip/uv can reach PyPI |
| Local filesystem | Sandboxed per session | No host access except workspace dir |

---

## Options Evaluated

### Option A: Bundle Everything (Source + All Deps) in ZIP

**Verdict: NOT FEASIBLE**

- Uncompressed size: 1.8 MB (source) + 103 MB (deps) = **~105 MB** — exceeds 50 MB ZIP limit even with compression
- Native extensions are platform-specific — macOS `.so` files won't load on Linux Cowork VMs
- Would need separate ZIPs per platform (macOS arm64, macOS x86, Linux x86_64) per Python version (3.10, 3.11, 3.12, 3.13) = **8+ variants**
- Maintenance nightmare for updates

### Option B: Bundle Source Only, pip Install Deps at Runtime

**Verdict: FEASIBLE — Marginal Improvement**

- Bundle: plugin (740 KB) + library source (1.8 MB) = **~2.5 MB ZIP**
- SessionStart hook installs deps from PyPI: `pip install pandas numpy pydantic httpx ...`
- Eliminates: GitHub clone of `mixpanel_data` (~10s)
- Still requires: ~60s for pip install of native deps on first session
- Complexity: need `sys.path` manipulation so bundled source is importable

### Option C: Bundle Source + Pure-Python Deps, pip Install Native Deps Only

**Verdict: FEASIBLE — Moderate Improvement, High Complexity**

- Bundle: plugin (740 KB) + source (1.8 MB) + pure deps (~23 MB) = **~12 MB ZIP** (compressed ~8 MB)
- SessionStart hook installs only: `numpy pandas pydantic-core jq` (~72 MB)
- Saves: ~30% of install time (pure deps already present)
- Risk: version conflicts between bundled pure deps and pip-resolved native deps
- Complexity: vendoring with `sys.path` manipulation, namespace isolation

### Option D: SessionStart Hook + CLAUDE_PLUGIN_DATA Venv (Recommended Pattern)

**Verdict: RECOMMENDED — Best Practice**

- Bundle: plugin (740 KB) + source (1.8 MB) + `requirements.txt` = **~2.5 MB ZIP**
- SessionStart hook creates/reuses a Python venv in `${CLAUDE_PLUGIN_DATA}/venv/`
- Diffs `requirements.txt` against cached copy — only reinstalls when deps change
- First session: ~60-90s for venv creation + pip install
- Subsequent sessions: **< 1s** (diff check passes, venv already exists)
- No platform concerns — pip resolves correct wheels for the VM
- Official Anthropic-recommended pattern for plugin dependencies

### Option E: Thin Plugin, Full PyPI Publish

**Verdict: BEST LONG-TERM — Requires PyPI Presence**

- Publish `mixpanel_data` to PyPI (currently GitHub-only)
- SessionStart hook: `pip install mixpanel_data[analytics]`
- Single command installs everything, pip handles caching
- Fastest install (PyPI CDN + wheel caching), simplest maintenance
- Blocked by: package not yet on PyPI

---

## Recommendation: Option D (with path to E)

### Phase 1: Hybrid Bundle (Option D)

Package structure:

```
mixpanel-data-plugin.zip
├── .claude-plugin/
│   └── plugin.json          # Add hooks section
├── agents/                   # Existing 5 agents
├── commands/                 # Existing auth command
├── skills/                   # Existing 3 skills
├── docs/                     # Existing docs
├── lib/                      # NEW: bundled library source
│   └── mixpanel_data/        # Copy of src/mixpanel_data/
├── requirements.txt          # NEW: pinned runtime deps
├── bin/
│   └── ensure-deps.sh        # NEW: venv bootstrap script
└── README.md
```

**plugin.json additions**:
```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/bin/ensure-deps.sh"
          }
        ]
      }
    ]
  }
}
```

**ensure-deps.sh** logic:
1. Check if `${CLAUDE_PLUGIN_DATA}/venv/` exists
2. Diff `${CLAUDE_PLUGIN_ROOT}/requirements.txt` against `${CLAUDE_PLUGIN_DATA}/requirements.txt`
3. If diff or no venv: create venv, `pip install -r requirements.txt`, install bundled source via `pip install -e ${CLAUDE_PLUGIN_ROOT}/lib/`
4. Copy requirements.txt to data dir for next session's diff
5. Export `PYTHONPATH` or activate venv for subsequent Bash tool calls

**Estimated ZIP size**: ~2.5 MB (well under 50 MB limit)

**First-session install time**: ~60-90s (venv creation + pip from PyPI)

**Repeat-session time**: < 1s (requirements diff passes)

### Phase 2: PyPI Publish (Option E)

Once `mixpanel_data` is on PyPI:
- Remove `lib/` from plugin ZIP
- `requirements.txt` becomes just `mixpanel_data[analytics]>=0.2.0`
- Install time drops (PyPI wheel caching, CDN)
- Plugin ZIP shrinks to ~800 KB

---

## What "Zero Install" Actually Means in Cowork

True zero-install (no network, no pip) is **not achievable** for this project because of native extensions. However, the **user experience** can feel like zero-install:

| Scenario | User Experience | What Happens Behind the Scenes |
|----------|----------------|-------------------------------|
| First session ever | ~60s wait at session start | SessionStart hook builds venv |
| Repeat session | Instant | Hook diffs requirements, skips install |
| Plugin update (same deps) | Instant | requirements.txt unchanged, venv reused |
| Plugin update (new deps) | ~30s | Hook detects diff, updates venv |

The user never runs `/mixpanel-data:setup` manually — the hook handles everything.

---

## Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Cowork VM lacks Python 3.10+ | Low | High | Check in hook, fail with clear message |
| pip/uv not available in VM | Low | High | Fall back to `python -m ensurepip` |
| PyPI unreachable from VM | Very Low | High | Cowork VMs have public internet |
| Venv corrupted between sessions | Low | Medium | Hook detects import failure, rebuilds venv |
| requirements.txt drift vs library | Medium | Medium | Pin exact versions from uv.lock |
| Native extension build fails (no compiler) | Low | High | Use `--only-binary :all:` to force wheel-only install |
| 50 MB ZIP limit exceeded | Very Low | High | Current estimate: ~2.5 MB |

---

## Appendix A: Dependency Size Breakdown

### Uncompressed Runtime Dependencies (103.4 MB total)

```
 pandas          45.5 MB  ██████████████████████████████████████████  (native)
 numpy           21.7 MB  ████████████████████                       (native)
 networkx        10.9 MB  ██████████                                 (pure)
 pydantic         7.1 MB  ███████                                    (pure model)
 pygments         4.7 MB  █████                                      (pure)
 pydantic-core    4.4 MB  ████                                       (native)
 rich             1.9 MB  ██                                         (pure)
 anyio            1.3 MB  █                                          (pure)
 pytz             1.0 MB  █                                          (pure)
 click            0.8 MB  █                                          (pure)
 httpx            0.6 MB  █                                          (pure)
 httpcore         0.6 MB  █                                          (pure)
 tzdata           0.6 MB  █                                          (pure)
 idna             0.5 MB  ▌                                          (pure)
 typer            0.4 MB  ▌                                          (pure)
 anytree          0.3 MB  ▌                                          (pure)
 certifi          0.3 MB  ▌                                          (pure)
 h11              0.2 MB  ▌                                          (pure)
 others           1.1 MB  █                                          (pure)
```

### Packages with Native Extensions
- `numpy`: 21.7 MB — C/Fortran (LAPACK, BLAS bindings)
- `pandas`: 45.5 MB — Cython-compiled (parsers, indexing, groupby)
- `pydantic-core`: 4.4 MB — Rust via PyO3 (validation engine)
- `jq`: < 0.1 MB — C (wraps libjq)

**Total native**: ~71.6 MB (69% of deps)
**Total pure-Python**: ~31.8 MB (31% of deps)

---

## Appendix B: Files to Bundle from Source

```
src/mixpanel_data/
├── __init__.py              # Public API
├── workspace.py             # Main facade (9,408 lines)
├── types.py                 # Result types (10,869 lines)
├── auth.py                  # Public auth module
├── exceptions.py            # Exception hierarchy
├── _literal_types.py        # Type aliases
├── py.typed                 # PEP 561 marker
├── _internal/               # Private implementation
│   ├── api_client.py        # HTTP client (7,577 lines)
│   ├── config.py            # Credential management
│   ├── validation.py        # Input validation
│   ├── pagination.py        # Cursor pagination
│   ├── bookmark_builders.py # Query building
│   ├── segfilter.py         # Segmentation filters
│   ├── transforms.py        # Data transforms
│   ├── auth/                # OAuth (6 modules)
│   ├── services/            # Discovery + LiveQuery
│   └── query/               # User query builders
└── cli/                     # CLI (25 command modules)
    ├── main.py
    ├── commands/             # 24 command files
    ├── formatters.py
    └── utils.py

66 files, 55,334 lines, 1.8 MB
```

---

## Appendix C: Cowork Plugin Path Variables

| Variable | Path | Lifecycle | Use For |
|----------|------|-----------|---------|
| `${CLAUDE_PLUGIN_ROOT}` | Plugin install dir | Changes on update | Read-only assets: scripts, source, configs |
| `${CLAUDE_PLUGIN_DATA}` | `~/.claude/plugins/data/{id}/` | Persists across updates | venv, caches, state files |
