---
name: mixpanel-data:auth
description: Manage Mixpanel authentication — check status, add/switch/test accounts, OAuth login, migrate config, discover projects. Use with no arguments for a quick status check.
argument-hint: [status|add|list|switch|test|login|remove|logout|migrate|projects|context|switch-project]
---

# Mixpanel Authentication Management

You manage Mixpanel credentials using `auth_manager.py`. All operations output JSON — parse it and present results conversationally.

**Script path:** `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py`

## Security Rules (NON-NEGOTIABLE)

- **NEVER ask for secrets (passwords, API secrets) in conversation** — they would be visible in history
- **NEVER pass secrets as CLI arguments** — visible in process list
- For account creation, guide the user to run `! mp auth add <name> -u <username> -p <project_id> -r <region>` themselves — this prompts for the secret with hidden input

## Routing

Parse `$ARGUMENTS` and route to the appropriate operation:

### No arguments or "status"

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py status`

Present the result conversationally:
- If `active_method` is not `"none"`: Show a brief confirmation with the active method, account name, project ID, and region. If multiple accounts/credentials exist, mention `/mp-auth list`. The possible `active_method` values are:
  - `env_vars` — service-account env vars (`MP_USERNAME`/`MP_SECRET`/`MP_PROJECT_ID`/`MP_REGION`)
  - `oauth_token_env` — raw OAuth bearer-token env vars (`MP_OAUTH_TOKEN`/`MP_PROJECT_ID`/`MP_REGION`)
  - `oauth` — OAuth tokens from PKCE storage or v2 OAuth credentials
  - `service_account` — stored service-account credentials
- If `active_method` is `"none"`: Diagnose what's missing. Suggest `/mp-auth add` (service account), `/mp-auth login` (OAuth PKCE browser flow), or `MP_OAUTH_TOKEN` env var (raw bearer token — best for non-interactive contexts like CI or agents).
- If `env_vars.partial` is true: Show which variables are set and which are missing for the service-account triple. Also check `env_vars.oauth_token` for the raw-bearer triple — if either is `partial`, surface the missing vars.
- If `config_version` is `1`: Mention that `/mp-auth migrate` can upgrade to v2 for project switching.
- If `config_version` is `2`: Show active context (credential + project + workspace) and mention project aliases if any exist.

#### Raw OAuth bearer-token env vars (`MP_OAUTH_TOKEN`)

For non-interactive contexts (CI, agents, ephemeral environments) where the PKCE browser flow isn't viable, set:

```
export MP_OAUTH_TOKEN=<bearer-token>
export MP_PROJECT_ID=<project-id>
export MP_REGION=<us|eu|in>
```

The library builds an `Authorization: Bearer <token>` header for every Mixpanel endpoint. Service-account env vars (`MP_USERNAME`/`MP_SECRET`) take precedence when both triples are set, so this is safe to add to a shell that already exports the service-account vars.

### "list"

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py list`

For **v1 config**: Present accounts as a clean table. Mark the default account with a star. Show account name, project ID, and region.

For **v2 config**: Present two sections:
1. **Credentials** — name, type (service_account/oauth), region, active status
2. **Project aliases** — alias name, project ID, credential, workspace ID

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
   `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py test <NAME>`
7. Report success or failure.

### "switch" or "switch <name>"

If a name is provided:
- Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py switch <name>`

If no name:
- First run `list` to show available accounts/credentials
- Ask which one to switch to
- Then run `switch` with the chosen name

### "test" or "test <name>"

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py test [name]`

On success: "Connected! Found N events in project P (region R)."
On failure: Diagnose the specific error and suggest remediation:
- `AuthenticationError` → "Credentials are invalid. Check your username and secret."
- `AccountNotFoundError` → "Account not found. Run `/mp-auth list` to see available accounts."
- `ConfigError` → "No credentials configured. Run `/mp-auth add` to set up."

### "login" or "login --region <R>"

Ask for the region if not provided (default: us). Ask for project ID if the user wants to associate one.

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py oauth-login --region <REGION> [--project-id <ID>]`

Tell the user a browser window will open for Mixpanel authentication. Wait for the result.

On success: "OAuth login successful! Token valid until <expires_at>."
On failure: Show the error and suggest retrying.

### "remove" or "remove <name>"

If no name: run `list` first, then ask which account/credential to remove.

**Always confirm before removing**: "Remove account '<name>'? This cannot be undone."

After confirmation:
Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py remove <name>`

For v2 config, if the response includes `orphaned_aliases`, warn the user about project aliases that referenced the removed credential.

### "logout" or "logout --region <R>"

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py oauth-logout [--region <R>]`

If no region specified, removes all OAuth tokens. Confirm first: "This will remove all OAuth tokens. Continue?"

### "migrate"

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py migrate --dry-run`

Show the user what will change (credentials created, aliases created). Ask for confirmation.

If confirmed:
Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py migrate`

On success: Report migration results. Explain that accounts are now split into credentials (auth identity) and project aliases (project selection), enabling project switching without reconfiguring auth.

If already v2: Tell the user no migration is needed.

### "projects"

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py projects`

Present accessible projects as a table: organization, project name, project ID, timezone. Suggest `/mp-auth switch-project <ID>` to switch.

### "context"

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py context`

Show the active credential, project ID, and workspace ID. For v1 config, suggest migrating.

### "switch-project" or "switch-project <project_id>"

If no project_id: run `projects` first, then ask which to switch to.

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py switch-project <PROJECT_ID> [--workspace-id <WS_ID>]`

On success: Confirm the active project was changed.
If v1 config: Error suggests running `/mp-auth migrate` first.

### "cowork-setup"

This command is only available on the host machine, not inside Cowork.
Tell the user: "Run `mp auth cowork-setup` on your **host machine** (not inside Cowork) to export credentials for Cowork sessions."

### "cowork-status"

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/mixpanelyst/scripts/auth_manager.py cowork-status`

Parse the JSON and present:
- If `bridge_found` is true: Show auth method, project, region, token expiry, custom header presence
- If `bridge_found` is false: Suggest running `mp auth cowork-setup` on the host machine

### "cowork-teardown"

This command is only available on the host machine, not inside Cowork.
Tell the user: "Run `mp auth cowork-teardown` on your **host machine** to remove Cowork credentials."

## Presentation Style

- Be concise — show status in 2-3 lines, not a wall of JSON
- Use tables for lists of accounts, credentials, or projects
- Always suggest a next action when something is missing
- On errors, be specific about what went wrong and how to fix it
