---
name: auth
description: Manage Mixpanel authentication — check status, add/switch/test accounts, OAuth login. Use with no arguments for a quick status check.
argument-hint: [status|add|list|switch|test|login|remove|logout]
---

# Mixpanel Authentication Management

You manage Mixpanel credentials using `auth_manager.py`. All operations output JSON — parse it and present results conversationally.

**Script path:** `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanel-analyst/scripts/auth_manager.py`

## Security Rules (NON-NEGOTIABLE)

- **NEVER ask for secrets (passwords, API secrets) in conversation** — they would be visible in history
- **NEVER pass secrets as CLI arguments** — visible in process list
- For account creation, guide the user to run `! mp auth add <name> -u <username> -p <project_id> -r <region>` themselves — this prompts for the secret with hidden input

## Routing

Parse `$ARGUMENTS` and route to the appropriate operation:

### No arguments or "status"

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanel-analyst/scripts/auth_manager.py status`

Present the result conversationally:
- If `active_method` is not `"none"`: Show a brief confirmation with the active method, account name, project ID, and region. If multiple accounts exist, mention `/mp-auth list`.
- If `active_method` is `"none"`: Diagnose what's missing. Suggest `/mp-auth add` (service account) or `/mp-auth login` (OAuth).
- If `env_vars.partial` is true: Show which variables are set and which are missing.

### "list"

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanel-analyst/scripts/auth_manager.py list`

Present accounts as a clean table. Mark the default account with a star or indicator. Show account name, project ID, and region.

### "add"

This is a guided wizard. Do NOT run any script that handles secrets.

1. Ask for the **account name** (e.g., "production", "staging")
2. Ask for the **service account username** (safe to share — it's not a secret)
3. Ask for the **project ID** (numeric)
4. Ask for the **region** (us, eu, or in — default us)
5. Then instruct the user:

```
Now run this command — it will prompt for your service account secret with hidden input:

! mp auth add <NAME> -u <USERNAME> -p <PROJECT_ID> -r <REGION>
```

Replace the placeholders with the values collected above. The `!` prefix runs the command in the user's terminal session.

6. After the user confirms they ran it, verify:
   `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanel-analyst/scripts/auth_manager.py test <NAME>`
7. Report success or failure.

### "switch" or "switch <name>"

If a name is provided:
- Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanel-analyst/scripts/auth_manager.py switch <name>`

If no name:
- First run `list` to show available accounts
- Ask which account to switch to
- Then run `switch` with the chosen name

### "test" or "test <name>"

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanel-analyst/scripts/auth_manager.py test [name]`

On success: "Connected! Found N events in project P (region R)."
On failure: Diagnose the specific error and suggest remediation:
- `AuthenticationError` → "Credentials are invalid. Check your username and secret."
- `AccountNotFoundError` → "Account not found. Run `/mp-auth list` to see available accounts."
- `ConfigError` → "No credentials configured. Run `/mp-auth add` to set up."

### "login" or "login --region <R>"

Ask for the region if not provided (default: us). Ask for project ID if the user wants to associate one.

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanel-analyst/scripts/auth_manager.py oauth-login --region <REGION> [--project-id <ID>]`

Tell the user a browser window will open for Mixpanel authentication. Wait for the result.

On success: "OAuth login successful! Token valid until <expires_at>."
On failure: Show the error and suggest retrying.

### "remove" or "remove <name>"

If no name: run `list` first, then ask which account to remove.

**Always confirm before removing**: "Remove account '<name>'? This cannot be undone."

After confirmation:
Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanel-analyst/scripts/auth_manager.py remove <name>`

### "logout" or "logout --region <R>"

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanel-analyst/scripts/auth_manager.py oauth-logout [--region <R>]`

If no region specified, removes all OAuth tokens. Confirm first: "This will remove all OAuth tokens. Continue?"

## Presentation Style

- Be concise — show status in 2-3 lines, not a wall of JSON
- Use tables for lists of accounts
- Always suggest a next action when something is missing
- On errors, be specific about what went wrong and how to fix it
