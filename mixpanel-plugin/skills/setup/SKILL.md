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

## Check Credentials

After installation, check auth status:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanel-analyst/scripts/auth_manager.py status
```

Parse the JSON result. If `active_method` is not `"none"`, credentials are configured — proceed to verification.

## If Credentials Are Missing

If no credentials are configured, guide the user to one of these methods:

### Recommended: Guided Setup

Tell the user to run `/mp-auth add` for a step-by-step walkthrough that securely collects credentials.

### Alternative: OAuth Login

Tell the user to run `/mp-auth login` for browser-based authentication (no service account needed).

### Alternative: Environment Variables (temporary)

For quick testing, set all four variables in the shell:

```bash
export MP_USERNAME="service-account-username"
export MP_SECRET="service-account-secret"
export MP_PROJECT_ID="12345"
export MP_REGION="us"  # or "eu", "in"
```

## Verify Everything Works

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanel-analyst/scripts/auth_manager.py test
```

If the result shows `"success": true`, setup is complete. The user can now ask questions about their Mixpanel data.

If verification fails, suggest `/mp-auth test` for detailed diagnostics.
