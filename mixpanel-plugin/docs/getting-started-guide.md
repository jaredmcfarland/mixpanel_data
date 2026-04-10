# Getting Started with mixpanel_data

A step-by-step guide to installing, configuring, and using `mixpanel_data` — the Python library, CLI, and Claude Code plugin for Mixpanel analytics.

This guide is for anyone who wants to explore their Mixpanel data programmatically, whether through the command line, Python scripts, or conversational analytics with Claude.

---

## Table of Contents

- [What You'll Need](#what-youll-need)
- [Part 1: Install the Package](#part-1-install-the-package)
- [Part 2: Authenticate with Mixpanel](#part-2-authenticate-with-mixpanel)
- [Part 3: Explore Your Data with the CLI](#part-3-explore-your-data-with-the-cli)
- [Part 4: Run Analytics Queries](#part-4-run-analytics-queries)
- [Part 5: Use the Python API](#part-5-use-the-python-api)
- [Part 6: Set Up the Claude Code Plugin](#part-6-set-up-the-claude-code-plugin)
- [Part 7: Set Up Claude Cowork](#part-7-set-up-claude-cowork)
- [Quick Reference](#quick-reference)
- [Troubleshooting](#troubleshooting)
- [Next Steps](#next-steps)

---

## What You'll Need

Before you begin, make sure you have:

- **Python 3.10 or later** — Check with `python3 --version`
- **pip or uv** — A Python package installer (`pip` comes with Python; [uv](https://docs.astral.sh/uv/) is faster)
- **A Mixpanel account** with access to a project
- **One of the following** for authentication:
  - A **service account** (username + secret) from your Mixpanel project settings, OR
  - A browser for **OAuth login** (interactive — your project is auto-discovered)

For service accounts, you'll also need your **Mixpanel Project ID**, which you can find in your Mixpanel project settings under "Project Details." For OAuth login, your projects are discovered automatically.

---

## Part 1: Install the Package

The `mixpanel_data` package installs both the Python library and the `mp` command-line tool.

### Option A: Install with pip

```bash
pip install git+https://github.com/jaredmcfarland/mixpanel_data.git
```

### Option B: Install with uv (faster)

```bash
uv pip install git+https://github.com/jaredmcfarland/mixpanel_data.git
```

### Verify the Installation

```bash
mp --version
```

You should see a version number printed. If you get "command not found," make sure your Python scripts directory is on your `PATH`. You can also run the CLI with:

```bash
python3 -m mixpanel_data --version
```

---

## Part 2: Authenticate with Mixpanel

You need to connect `mixpanel_data` to your Mixpanel project. There are two ways to do this: **OAuth login** (interactive, opens your browser) or **service account** (for scripts and automation).

### Option A: OAuth Login (Recommended for Personal Use)

This opens your browser so you can log in with your Mixpanel credentials:

```bash
mp auth login --region us
```

After logging in, `mixpanel_data` automatically discovers your accessible projects. If you have exactly one project, it is selected for you. If you have multiple projects, you'll be prompted to choose one:

```bash
mp projects list                  # See all your projects
mp projects switch YOUR_PROJECT_ID  # Select a project
```

You can also specify a project ID upfront if you already know it:

```bash
mp auth login --region us --project-id YOUR_PROJECT_ID
```

**Region options:**

| Region | Flag | When to use |
|--------|------|-------------|
| United States | `--region us` | Most projects (default) |
| Europe | `--region eu` | EU data residency |
| India | `--region in` | India data residency |

Verify the connection:

```bash
mp auth status
```

### Option B: Service Account (Recommended for Scripts & CI/CD)

Service accounts are ideal for automation. You'll need a **service account username** and **secret** from your Mixpanel project settings (Settings > Service Accounts).

Add the credentials (you'll be prompted for the secret securely):

```bash
mp auth add my-project --username YOUR_SA_USERNAME --project YOUR_PROJECT_ID --region us
```

You'll see a hidden input prompt for the secret — paste it and press Enter.

Then verify the connection:

```bash
mp auth test
```

You should see a success message confirming the credentials work.

### Option C: Environment Variables (Quick Setup)

For a quick, temporary setup (useful for trying things out), you can export environment variables:

```bash
export MP_USERNAME="your-service-account-username"
export MP_SECRET="your-service-account-secret"
export MP_PROJECT_ID="12345"
export MP_REGION="us"
```

These take effect immediately for any `mp` command or Python script in the same terminal session.

### Where Credentials Are Stored

Credentials are saved to `~/.mp/config.toml`. This file is created automatically when you run `mp auth add` or `mp auth login`. You should never need to edit it by hand.

---

## Part 3: Explore Your Data with the CLI

Now that you're authenticated, explore what's in your Mixpanel project.

### List All Events

```bash
mp inspect events
```

This shows every event type being tracked in your project.

### View Properties for a Specific Event

```bash
mp inspect properties --event "Signup"
```

Replace `"Signup"` with any event name from the previous command.

### See Saved Funnels and Cohorts

```bash
mp inspect funnels
mp inspect cohorts
```

### Change the Output Format

All commands support `--format` to control how results are displayed:

```bash
mp inspect events --format table    # Human-readable table
mp inspect events --format json     # Machine-readable JSON
mp inspect events --format csv      # Spreadsheet-friendly CSV
```

---

## Part 4: Run Analytics Queries

### Segmentation Query (Event Trends)

See how often an event occurred over a date range:

```bash
mp query segmentation --event "Signup" --from 2025-01-01 --to 2025-01-31
```

### Break Down by Property

Add `--on` to break results down by a property:

```bash
mp query segmentation --event "Purchase" --from 2025-01-01 --to 2025-01-31 --on country
```

### Funnel Conversion

Query a saved funnel by its ID (find IDs with `mp inspect funnels`):

```bash
mp query funnel 12345 --from 2025-01-01 --to 2025-01-31
```

### Filter JSON Output with --jq

Commands that return JSON support `--jq` for inline filtering:

```bash
# Get only the first 5 events
mp inspect events --format json --jq '.[:5]'

# Extract just event names
mp inspect events --format json --jq '.[].name'
```

### Format as a Table

```bash
mp query segmentation --event "Login" --from 2025-01-01 --to 2025-01-31 --format table
```

---

## Part 5: Use the Python API

The Python library gives you the full power of `mixpanel_data` with pandas DataFrames for analysis.

### Basic Setup

```python
import mixpanel_data as mp

# Creates a Workspace using your saved credentials
ws = mp.Workspace()
```

### Discover Your Data

```python
# List all events in your project
events = ws.events()
print(events)

# List properties for a specific event
props = ws.properties("Purchase")
print(props)
```

### Run an Insights Query

```python
# Simple event count over the last 30 days
result = ws.query("Signup", last=30, unit="day")
print(result.df)  # pandas DataFrame
```

### Insights with Breakdown and Filter

```python
from mixpanel_data import Filter, GroupBy

# Purchase revenue by country, filtered to US
result = ws.query(
    "Purchase",
    math="total",
    math_property="amount",
    where=Filter.equals("country", "US"),
    group_by="plan_type",
    last=30,
)
print(result.df)
```

### Funnel Query

```python
# Define funnel steps inline — no saved funnel needed
funnel = ws.query_funnel(
    ["Signup", "Onboarding Complete", "First Purchase"],
    conversion_window=7,
    last=90,
)
print(f"Overall conversion: {funnel.overall_conversion_rate:.1%}")
print(funnel.df)
```

### Retention Query

```python
# How many users who signed up came back to log in?
retention = ws.query_retention(
    "Signup",
    "Login",
    retention_unit="week",
    last=90,
)
print(retention.df.head())  # cohort_date | bucket | count | rate
```

### Flow Query (User Paths)

```python
# What do users do after signing up?
flow = ws.query_flow("Signup", forward=4)
print(flow.top_transitions(5))     # Top 5 most common paths
print(flow.drop_off_summary())     # Where users drop off
```

### Stream Events

For processing large datasets without loading everything into memory:

```python
for event in ws.stream_events(from_date="2025-01-01", to_date="2025-01-31"):
    print(event["event"], event["properties"]["distinct_id"])
```

---

## Part 6: Set Up the Claude Code Plugin

The Claude Code plugin turns Claude into a Mixpanel data analyst. Instead of writing queries yourself, you ask questions in plain English and Claude writes and runs the Python code for you.

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed (CLI, desktop app, or web app)
- Plugins enabled in Claude Code

### Install the Plugin

In your Claude Code session, run:

```
/plugin marketplace add jaredmcfarland/mixpanel_data
/plugin install mixpanel-data@mixpanel-data-marketplace
```

### Run the Setup Skill

After installing, run the setup skill to install dependencies and verify authentication:

```
/mixpanel-data:setup
```

This will:

1. Check that Python 3.10+ is available
2. Install the `mixpanel_data` package and its dependencies (pandas, numpy, matplotlib, networkx, etc.)
3. Verify that your Mixpanel credentials are configured
4. Report the status of your connection

### Configure Credentials (If Not Already Done)

If the setup skill reports that no credentials are found, use the `/mp-auth` command:

```
/mp-auth add my-project
```

Claude will guide you through entering your service account username, project ID, and region. You'll be prompted to run a shell command that securely collects your secret.

### Ask Analytics Questions

Once authenticated, just ask Claude questions in natural language:

```
"How many signups did we get last week?"

"Where do users drop off in the checkout funnel?"

"Do users who complete onboarding retain better than those who don't?"

"What's the most common path after a user signs up?"

"Build me a weekly KPI dashboard for the product team."
```

Claude will choose the right query engine (Insights, Funnels, Retention, or Flows), write and execute the Python code, and explain the results.

### Specialist Agents

The plugin includes five specialist agents that Claude can invoke automatically based on your question:

| Agent | What It Does | Example Question |
|-------|-------------|-----------------|
| **analyst** | General-purpose orchestrator | "Show me revenue trends by plan type" |
| **explorer** | Discovers your data schema | "What events and properties do we track?" |
| **diagnostician** | Root cause analysis | "Why did signups drop last Tuesday?" |
| **synthesizer** | Multi-engine cross-analysis | "Compare funnel conversion for retained vs. churned users" |
| **narrator** | Executive summaries | "Write a weekly product report for leadership" |

You don't need to invoke these manually — Claude routes to the right agent based on your question.

---

## Part 7: Set Up Claude Cowork

[Claude Cowork](https://docs.anthropic.com/en/docs/claude-code/cowork) lets multiple Claude agents collaborate on tasks in sandboxed virtual machines. To use `mixpanel_data` in Cowork, you need to export your credentials from your local machine so the Cowork VM can access them.

### Step 1: Set Up the Credential Bridge (On Your Local Machine)

Run this command on your **local machine** (not inside Cowork):

```bash
mp auth cowork-setup
```

This creates a credential bridge file at `~/.claude/mixpanel/auth.json` that Cowork VMs can read.

**Options:**

```bash
# Use a specific credential (if you have multiple accounts)
mp auth cowork-setup --credential production

# Override the project ID
mp auth cowork-setup --project-id 12345

# Include a workspace ID (needed for dashboard and entity management)
mp auth cowork-setup --workspace-id 3448413

# Write to a specific directory (e.g., a shared Cowork workspace folder)
mp auth cowork-setup --dir /path/to/workspace
```

### Step 2: Verify the Bridge (Anywhere)

Check that the bridge file exists and is valid:

```bash
mp auth cowork-status
```

This shows you the auth method, region, project ID, and whether OAuth tokens are still valid.

### Step 3: Use mixpanel_data in Cowork

Inside a Cowork session, run the setup skill:

```
/mixpanel-data:setup
```

The setup script automatically detects the Cowork environment and reads credentials from the bridge file. No additional configuration is needed.

### Step 4: Clean Up (When Done)

When you no longer need Cowork access, remove the bridge file from your local machine:

```bash
mp auth cowork-teardown
```

If you used `--dir` during setup, include it during teardown:

```bash
mp auth cowork-teardown --dir /path/to/workspace
```

### OAuth Token Refresh

If you authenticated with OAuth, the bridge file includes a refresh token. The library automatically refreshes expired tokens inside Cowork — no browser interaction needed. If the refresh token itself expires, you'll need to re-authenticate on your local machine (`mp auth login`) and re-run `mp auth cowork-setup`.

---

## Quick Reference

### CLI Commands at a Glance

| Command | What It Does |
|---------|-------------|
| `mp auth login` | Log in with OAuth (opens browser) |
| `mp auth add <name>` | Add a service account |
| `mp auth test` | Test your credentials |
| `mp auth status` | Show current auth status |
| `mp inspect events` | List all tracked events |
| `mp inspect properties --event <name>` | List properties for an event |
| `mp query segmentation --event <name> --from <date> --to <date>` | Run a segmentation query |
| `mp query funnel <id> --from <date> --to <date>` | Query a saved funnel |
| `mp projects list` | List accessible projects |
| `mp projects switch <id>` | Switch active project |
| `mp auth migrate` | Migrate v1 config to v2 format |
| `mp --help` | Show all available commands |
| `mp <command> --help` | Show help for a specific command |

### Python API at a Glance

```python
import mixpanel_data as mp

ws = mp.Workspace()

ws.events()                              # List events
ws.properties("EventName")              # List properties
ws.query("Event", last=30)              # Insights query
ws.query_funnel(["A", "B", "C"])        # Funnel query
ws.query_retention("A", "B")            # Retention query
ws.query_flow("Event", forward=3)       # Flow query
ws.stream_events(from_date="...", to_date="...")  # Stream events
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `MP_USERNAME` | Service account username |
| `MP_SECRET` | Service account secret |
| `MP_PROJECT_ID` | Your Mixpanel project ID |
| `MP_REGION` | Data residency region (`us`, `eu`, or `in`) |
| `MP_WORKSPACE_ID` | Workspace ID (for dashboard and entity management) |

### Output Formats

Every CLI command supports `--format`:

| Format | Flag | Best For |
|--------|------|----------|
| JSON | `--format json` | Scripting, piping to other tools |
| JSON Lines | `--format jsonl` | Streaming, log processing |
| Table | `--format table` | Human-readable terminal output |
| CSV | `--format csv` | Spreadsheets, data import |
| Plain | `--format plain` | Minimal text output |

---

## Troubleshooting

### "command not found: mp"

Your Python scripts directory isn't on your `PATH`. Try running with the full path:

```bash
python3 -m mixpanel_data --version
```

Or find where pip installed it:

```bash
pip show mixpanel_data
```

If using `uv`, make sure the virtual environment is activated.

### "Authentication failed" or "401 Unauthorized"

- Double-check your service account username and secret in Mixpanel (Settings > Service Accounts)
- Verify your project ID matches the project the service account has access to
- Make sure the region flag matches your project's data residency
- Run `mp auth test` to see the specific error message

### "No credentials configured"

Run one of:

```bash
# OAuth (interactive — auto-discovers your projects)
mp auth login --region us

# Service account
mp auth add my-project --username YOUR_USERNAME --project YOUR_PROJECT_ID --region us
```

### OAuth Token Expired

```bash
# Re-authenticate
mp auth login --region us
```

### Plugin Not Working in Claude Code

1. Make sure plugins are enabled in your Claude Code settings
2. Run `/mixpanel-data:setup` to install dependencies
3. Check auth with `/mp-auth status`
4. If the plugin doesn't appear, try restarting Claude Code

### Cowork VM Can't Find Credentials

1. On your **local machine**, run: `mp auth cowork-setup`
2. Verify with: `mp auth cowork-status`
3. Inside the Cowork session, run: `/mixpanel-data:setup`

---

## Next Steps

Now that you're set up, here's where to go next:

- **Full documentation**: [jaredmcfarland.github.io/mixpanel_data](https://jaredmcfarland.github.io/mixpanel_data/)
- **Insights query guide**: [Query documentation](https://jaredmcfarland.github.io/mixpanel_data/guide/query/)
- **Funnel queries**: [Funnel documentation](https://jaredmcfarland.github.io/mixpanel_data/guide/query-funnels/)
- **Retention queries**: [Retention documentation](https://jaredmcfarland.github.io/mixpanel_data/guide/query-retention/)
- **Flow queries**: [Flow documentation](https://jaredmcfarland.github.io/mixpanel_data/guide/query-flows/)
- **CLI reference**: [CLI documentation](https://jaredmcfarland.github.io/mixpanel_data/cli/)
- **Python API reference**: [API documentation](https://jaredmcfarland.github.io/mixpanel_data/api/)
- **DeepWiki**: [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/jaredmcfarland/mixpanel_data)

For every CLI command, `--help` shows complete usage information:

```bash
mp query --help
mp query segmentation --help
mp inspect events --help
```

In the Python API, all return values are typed dataclasses — your IDE will show you every available field and method.
