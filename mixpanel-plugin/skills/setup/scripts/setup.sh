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
echo ""
echo "Installing mixpanel_data and pandas..."
if command -v uv &>/dev/null; then
  echo "  (using uv)"
  uv pip install --python "$python_cmd" mixpanel_data pandas || { echo "  ⚠ Virtualenv install failed, trying system install..."; uv pip install --system --python "$python_cmd" mixpanel_data pandas; }
elif "$python_cmd" -m pip --version &>/dev/null; then
  echo "  (using pip via $python_cmd)"
  "$python_cmd" -m pip install mixpanel_data pandas
else
  echo "✗ No package manager found. Install pip or uv."
  echo "  Recommended: https://docs.astral.sh/uv/"
  exit 1
fi

# Verify imports
echo ""
echo "Verifying installation..."
"$python_cmd" -c "
import mixpanel_data as mp
import pandas as pd
print(f'✓ mixpanel_data installed')
print(f'✓ pandas {pd.__version__}')
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
    from mixpanel_data.auth import ConfigManager
    cm = ConfigManager()
    accounts = cm.list_accounts()
    if accounts:
        names = [a.name for a in accounts]
        print(f'✓ {len(accounts)} configured account(s): {\", \".join(names)}')
        default = next((a.name for a in accounts if a.is_default), None)
        if default:
            print(f'  Default: {default}')
    else:
        print('⚠ No accounts configured yet.')
        print('  Set environment variables: MP_USERNAME, MP_SECRET, MP_PROJECT_ID')
        print('  Or configure an account programmatically (see setup instructions)')
except Exception as e:
    print(f'⚠ Could not check config file credentials: {e}')
    print('  Set environment variables: MP_USERNAME, MP_SECRET, MP_PROJECT_ID')
"

echo ""
echo "=== Setup complete ==="
