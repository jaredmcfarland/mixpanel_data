#!/usr/bin/env bash
# Install mixpanel_data and pandas for CodeMode analytics
set -euo pipefail

echo "=== Mixpanel Data — CodeMode Setup ==="
echo ""

# Find Python 3.10+
python_cmd=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
    minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
    if [ "$major" -gt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -ge 10 ]); then
      version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
      python_cmd="$cmd"
      echo "✓ Python $version ($cmd)"
      break
    fi
  fi
done

if [ -z "$python_cmd" ]; then
  echo "✗ Python 3.10+ required but not found."
  echo "  Install from https://python.org or via your package manager."
  exit 1
fi

# Install packages
# mixpanel_data is not on PyPI — install from GitHub
MIXPANEL_DATA_PKG="git+https://github.com/jaredmcfarland/mixpanel_data.git"
DEPS=(pandas numpy matplotlib seaborn 'networkx>=3.0' 'anytree>=2.8.0' scipy)

# pyarrow is only needed on Python 3.11+ (for pandas 3.x Arrow-backed dtypes)
if [ "$minor" -ge 11 ]; then
  DEPS+=('pyarrow>=17.0')
fi

echo ""
echo "Installing mixpanel_data (from GitHub) and dependencies..."
if command -v uv &>/dev/null; then
  echo "  (using uv)"
  uv pip install --python "$python_cmd" "$MIXPANEL_DATA_PKG" "${DEPS[@]}" || { echo "  ⚠ Virtualenv install failed, trying system install..."; uv pip install --system --python "$python_cmd" "$MIXPANEL_DATA_PKG" "${DEPS[@]}"; }
elif "$python_cmd" -m pip --version &>/dev/null; then
  echo "  (using pip via $python_cmd)"
  "$python_cmd" -m pip install "$MIXPANEL_DATA_PKG" "${DEPS[@]}"
else
  echo "✗ No package manager found. Install pip or uv."
  echo "  Recommended: https://docs.astral.sh/uv/"
  exit 1
fi

# Verify imports
echo ""
echo "Verifying installation..."
"$python_cmd" -c "
import sys
import mixpanel_data as mp
import pandas as pd
import numpy as np
import matplotlib
import seaborn as sns
import networkx as nx
import anytree
import scipy
print(f'✓ mixpanel_data installed')
print(f'✓ pandas {pd.__version__}')
if sys.version_info >= (3, 11):
    import pyarrow as pa
    print(f'✓ pyarrow {pa.__version__}')
print(f'✓ numpy {np.__version__}')
print(f'✓ matplotlib {matplotlib.__version__}')
print(f'✓ seaborn {sns.__version__}')
print(f'✓ networkx {nx.__version__}')
print(f'✓ anytree {anytree.__version__}')
print(f'✓ scipy {scipy.__version__}')
" || { echo "✗ Import verification failed"; exit 1; }

# Check credentials
echo ""
echo "Checking Mixpanel credentials..."
"$python_cmd" -c "
import os, sys
# Check environment variables first
env_vars = ['MP_USERNAME', 'MP_SECRET', 'MP_PROJECT_ID', 'MP_REGION']
env_set = [v for v in env_vars if os.environ.get(v)]
if len(env_set) == len(env_vars):
    print(f'✓ All environment variables set')
    sys.exit(0)
elif env_set:
    missing = [v for v in env_vars if not os.environ.get(v)]
    print(f'⚠ Partial environment config — missing: {\", \".join(missing)}')

# Check config file
try:
    from mixpanel_data._internal.config import ConfigManager
    cm = ConfigManager()
    version = 1  # config schema version is fixed under the 0.4.0 layout

    if version >= 2:
        # v2 config: credential + project context
        credentials = cm.list_credentials()
        if credentials:
            active = [c for c in credentials if c.is_active]
            print(f'✓ Config v2: {len(credentials)} credential(s)')
            if active:
                print(f'  Active: {active[0].name} ({active[0].type}, {active[0].region})')
            aliases = cm.list_project_aliases()
            if aliases:
                print(f'  {len(aliases)} project alias(es) configured')
        else:
            print('⚠ Config v2 but no credentials configured.')
            print('  Run /mixpanel-data:auth add (service account) or /mixpanel-data:auth login (OAuth)')
    else:
        # v1 config: account-based
        accounts = cm.list_accounts()
        if accounts:
            names = [a.name for a in accounts]
            print(f'✓ Config v1: {len(accounts)} account(s): {\", \".join(names)}')
            default = next((a.name for a in accounts if a.is_default), None)
            if default:
                print(f'  Default: {default}')
            print(f'  Tip: Run /mixpanel-data:auth migrate to upgrade to v2 for project switching')
        else:
            print('⚠ No accounts configured yet.')
            print('  Run /mixpanel-data:auth add (service account) or /mixpanel-data:auth login (OAuth)')
except Exception as e:
    print(f'⚠ Could not check config file credentials: {e}')
    print('  Set environment variables: MP_USERNAME, MP_SECRET, MP_PROJECT_ID')
"

# Cowork detection: check for bridge file
if [ -d "/sessions" ] || [ -n "${CLAUDE_COWORK:-}" ]; then
  echo ""
  echo "Cowork environment detected."
  BRIDGE_FOUND=""
  for f in "$HOME/.claude/mixpanel/auth.json"; do
    if [ -f "$f" ]; then
      echo "✓ Auth bridge file found: $f"
      "$python_cmd" -c "
import json, sys
try:
    with open(sys.argv[1]) as fh:
        bridge = json.load(fh)
    print(f'  Auth method: {bridge.get(\"auth_method\", \"unknown\")}')
    print(f'  Region: {bridge.get(\"region\", \"unknown\")}')
    print(f'  Project: {bridge.get(\"project_id\", \"unknown\")}')
    ch = bridge.get('custom_header')
    if ch:
        print(f'  Custom header: {ch.get(\"name\", \"?\")} ✓')
    oauth = bridge.get('oauth')
    if oauth and oauth.get('expires_at'):
        print(f'  Token expires: {oauth[\"expires_at\"]}')
except Exception as e:
    print(f'  Error reading bridge file: {e}')
" "$f"
      BRIDGE_FOUND=1
      break
    fi
  done
  if [ -z "$BRIDGE_FOUND" ]; then
    echo "⚠ No auth bridge file found."
    echo "  On your HOST machine, run:"
    echo "    mp auth cowork-setup"
    echo "  Then start a new Cowork session."
  fi
fi

echo ""
echo "=== Setup complete ==="
