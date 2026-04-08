---
name: setup
description: This skill installs mixpanel_data, pandas, numpy, matplotlib, seaborn, networkx, anytree, and scipy, then verifies Mixpanel credentials. It should be invoked when setting up a new environment for Mixpanel data analysis, when dependencies are missing, or when configuring service account or OAuth credentials for the first time.
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
2. Install `mixpanel_data`, `pandas`, `numpy`, `matplotlib`, `seaborn`, `networkx>=3.0`, `anytree>=2.8.0`, and `scipy` (tries uv, pip in order)
3. Verify all packages import successfully (including networkx, anytree, and scipy)
4. Check for configured Mixpanel credentials (supports both v1 and v2 config schemas)

## Check Credentials

After installation, check auth status:

```bash
python3 ${CLAUDE_SKILL_DIR}/../mixpanel-analyst/scripts/auth_manager.py status
```

Parse the JSON result:
- If `active_method` is not `"none"`, credentials are configured — proceed to verification.
- If `config_version` is `1`, suggest `/mp-auth migrate` to upgrade to v2 for project switching.
- If `config_version` is `2`, show the active credential and project context.

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
python3 ${CLAUDE_SKILL_DIR}/../mixpanel-analyst/scripts/auth_manager.py test
```

If the result shows `"success": true`, setup is complete. The user can now ask questions about their Mixpanel data.

If verification fails, suggest `/mp-auth test` for detailed diagnostics.

## Post-Setup: Explore Your Data

Once authenticated, these commands help orient the user:

- `/mp-auth projects` — discover all accessible projects via the /me API
- `/mp-auth context` — see the active credential + project + workspace
- `/mp-auth switch-project <ID>` — switch to a different project (v2 config only)

The user can also construct a Workspace targeting a specific credential or project:

```python
import mixpanel_data as mp

ws = mp.Workspace()                              # default credentials
ws = mp.Workspace(account="production")           # named account (v1)
ws = mp.Workspace(credential="production")        # named credential (v2)
ws = mp.Workspace(project_id="67890", region="eu") # explicit project
```

_The mixpanel-analyst skill auto-triggers on analytics questions. For the analytical frameworks that guide investigations, see [analytical-frameworks.md](../mixpanel-analyst/references/analytical-frameworks.md). For the complete Python API, see [python-api.md](../mixpanel-analyst/references/python-api.md)._
