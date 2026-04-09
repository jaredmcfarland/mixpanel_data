# Quick Start: mixpanel_data + Claude Cowork

Get your Mixpanel credentials working inside [Claude Cowork](https://docs.anthropic.com/en/docs/claude-code/cowork) sessions so Claude agents can query your analytics data autonomously.

Cowork runs Claude agents in sandboxed virtual machines. These VMs don't have access to your local config files or browser, so credentials need to be exported from your machine into a "bridge file" that Cowork can read.

---

## What You'll Need

- **Claude Code** with Cowork access
- **The `mp` CLI installed on your local machine** — this is the tool that exports your credentials
- **Working Mixpanel credentials** already configured on your local machine

If you haven't installed `mixpanel_data` or set up credentials yet, complete the [Claude Code Quick Start](quickstart-claude-code.md) first (Steps 1-3), or install the CLI directly:

```bash
pip install git+https://github.com/jaredmcfarland/mixpanel_data.git
```

---

## Step 1: Verify Your Local Credentials

On your **local machine** (not inside Cowork), confirm you have working credentials:

```bash
mp auth test
```

You should see a success message. If not, set up credentials first:

```bash
# OAuth (opens browser)
mp auth login --region us --project-id YOUR_PROJECT_ID

# OR service account (prompts for secret securely)
mp auth add my-project --username YOUR_SA_USERNAME --project YOUR_PROJECT_ID --region us
```

---

## Step 2: Export Credentials for Cowork

On your **local machine**, run:

```bash
mp auth cowork-setup
```

This creates a bridge file at `~/.claude/mixpanel/auth.json` containing your credentials. Cowork VMs can read this file automatically.

You'll see output confirming what was exported:

```
status: cowork_setup_complete
bridge_path: /home/you/.claude/mixpanel/auth.json
auth_method: service_account
region: us
project_id: 12345
credentials_valid: true
```

### Options

```bash
# Use a specific credential (if you have multiple accounts)
mp auth cowork-setup --credential production

# Override the project ID
mp auth cowork-setup --project-id 12345

# Include a workspace ID (required for dashboard/entity management)
mp auth cowork-setup --workspace-id 3448413

# Write to a specific directory
mp auth cowork-setup --dir /path/to/workspace
```

---

## Step 3: Start a Cowork Session and Run Setup

Open a Cowork session and run the setup skill:

```
/mixpanel-data:setup
```

The setup script automatically detects the Cowork environment and reads credentials from the bridge file. You'll see output like:

```
Cowork environment detected.
✓ Auth bridge file found: ~/.claude/mixpanel/auth.json
  Auth method: service_account
  Region: us
  Project: 12345
```

No additional configuration is needed inside Cowork.

---

## Step 4: Start Asking Questions

You're ready. Ask Claude questions in natural language, just like in regular Claude Code:

```
How many signups did we get last week?

What's our funnel conversion rate from signup to purchase?

Show me weekly retention for users who completed onboarding.
```

---

## Managing the Credential Bridge

All bridge management commands run on your **local machine**, not inside Cowork.

### Check bridge status

Works both locally and inside Cowork:

```bash
mp auth cowork-status
```

Shows whether the bridge file exists, the auth method, region, project ID, and (for OAuth) whether the token is still valid.

### Update credentials

If you change your credentials or switch projects, re-export:

```bash
mp auth cowork-setup
```

Then start a **new Cowork session** for the changes to take effect.

### Remove the bridge

When you no longer need Cowork access to your Mixpanel data:

```bash
mp auth cowork-teardown
```

If you used `--dir` during setup, include it during teardown:

```bash
mp auth cowork-teardown --dir /path/to/workspace
```

---

## OAuth and Token Refresh

If you authenticated with OAuth (rather than a service account), the bridge file includes both an access token and a refresh token.

- **Automatic refresh**: The `mixpanel_data` library refreshes expired OAuth tokens automatically inside Cowork — no browser needed
- **Refresh token expired**: If the refresh token itself expires (rare), you need to re-authenticate on your local machine and re-export:

```bash
# On your local machine
mp auth login --region us --project-id YOUR_PROJECT_ID
mp auth cowork-setup
```

Then start a new Cowork session.

---

## How the Bridge Works

The credential bridge is a JSON file that maps your local credentials into a format Cowork VMs can consume:

```
Your machine                          Cowork VM
┌─────────────────────┐               ┌─────────────────────┐
│ ~/.mp/config.toml   │               │ ~/.claude/mixpanel/  │
│ (your credentials)  │──cowork-setup──▶│ auth.json           │
│                     │               │ (bridge file)        │
└─────────────────────┘               └─────────────────────┘
                                             │
                                      mixpanel_data detects
                                      Cowork + reads bridge
                                             │
                                      ┌──────▼──────────────┐
                                      │ mp.Workspace()      │
                                      │ (authenticated)     │
                                      └─────────────────────┘
```

The bridge file is searched in this priority order:

1. `MP_AUTH_FILE` environment variable (if set)
2. `mixpanel_auth.json` in the current working directory
3. `~/.claude/mixpanel/auth.json` (default location)
4. `~/.claude/mixpanel_auth.json`
5. `~/mnt/{folder}/mixpanel_auth.json` (bindfs mount)

---

## Troubleshooting

### "No auth bridge file found" in Cowork

**Cause**: The bridge file wasn't created or isn't in a location Cowork can see.

**Fix**: On your local machine:
```bash
mp auth cowork-setup
mp auth cowork-status   # verify it was created
```
Then start a **new** Cowork session (existing sessions won't pick up the new file).

### "Authentication failed" inside Cowork

**Cause**: The credentials in the bridge file are invalid or the service account was rotated.

**Fix**: On your local machine:
```bash
mp auth test            # verify local credentials still work
mp auth cowork-setup    # re-export fresh credentials
```

### OAuth token expired and won't refresh

**Cause**: Both the access token and refresh token have expired.

**Fix**: On your local machine:
```bash
mp auth login --region us --project-id YOUR_PROJECT_ID
mp auth cowork-setup
```
Then start a new Cowork session.

### Can't run `mp auth cowork-setup` — "command not found"

**Cause**: The `mixpanel_data` package isn't installed on your local machine.

**Fix**:
```bash
pip install git+https://github.com/jaredmcfarland/mixpanel_data.git
mp --version   # verify
```

### Setup says "Cowork environment detected" but no credentials

**Cause**: You're inside Cowork but the bridge file is missing.

**Fix**: You cannot configure credentials from inside Cowork (no browser, no host terminal). Exit Cowork, run `mp auth cowork-setup` on your local machine, then start a new Cowork session.

### Important: What Doesn't Work Inside Cowork

These commands require a browser or host terminal and **cannot run inside Cowork**:

- `mp auth login` (needs browser)
- `mp auth add` (needs interactive secret input from host)
- `mp auth cowork-setup` (runs on host, exports to bridge)
- `mp auth cowork-teardown` (runs on host, removes bridge)

Always run these on your **local machine** before starting a Cowork session.

---

## Next Steps

- **Claude Code quick start**: [Claude Code Quick Start](quickstart-claude-code.md) — plugin setup and authentication
- **Full getting started guide**: [Getting Started Guide](getting-started-guide.md) — Python library, CLI, and more
- **Full documentation**: [jaredmcfarland.github.io/mixpanel_data](https://jaredmcfarland.github.io/mixpanel_data/)
