---
name: setup
description: This skill installs mixpanel_data and pandas, then verifies Mixpanel credentials. It should be invoked when setting up a new environment for Mixpanel data analysis, when dependencies are missing, or when configuring service account or OAuth credentials for the first time.
disable-model-invocation: true
allowed-tools: Bash
---

# Mixpanel Data — Setup

Install dependencies and verify credentials for CodeMode analytics.

## Run Setup

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/setup.sh
```

This will:
1. Verify Python 3.10+ is available
2. Install `mixpanel_data` and `pandas` (tries uv, pip3, pip in order)
3. Verify both packages import successfully
4. Check for configured Mixpanel credentials

## If Credentials Are Missing

After installation, if no credentials are configured, help the user choose one of these methods:

### Option 1: Environment Variables (simplest)

```bash
export MP_USERNAME="service-account-username"
export MP_SECRET="service-account-secret"
export MP_PROJECT_ID="12345"
export MP_REGION="us"  # or "eu", "in"
```

### Option 2: Config File (persistent)

```python
python3 -c "
from mixpanel_data.auth import ConfigManager
cm = ConfigManager()
cm.add_account(
    name='default',
    username='SERVICE_ACCOUNT_USERNAME',
    secret='SERVICE_ACCOUNT_SECRET',
    project_id=PROJECT_ID,
    region='us'
)
print('Account configured successfully')
"
```

### Option 3: OAuth Login (interactive)

```python
python3 -c "
import mixpanel_data as mp
mp.auth.login(region='us')
print('OAuth login complete')
"
```

## Verify Everything Works

```python
python3 -c "
import mixpanel_data as mp
ws = mp.Workspace()
events = ws.events()
print(f'Connected! Found {len(events)} events')
print('Top 5:', events[:5])
"
```

If this prints events, setup is complete. The user can now ask questions about their Mixpanel data.
