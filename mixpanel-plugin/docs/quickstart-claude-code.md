# Quick Start: mixpanel_data + Claude Code

Get Claude answering questions about your Mixpanel data in under 5 minutes. No coding required — Claude writes and runs the Python for you.

---

## What You'll Need

- **Claude Code** — [CLI](https://docs.anthropic.com/en/docs/claude-code/overview), [desktop app](https://docs.anthropic.com/en/docs/claude-code/desktop), [web app](https://claude.ai/code), or [IDE extension](https://docs.anthropic.com/en/docs/claude-code/ide-integrations) (VS Code, JetBrains)
- **A Mixpanel account** with access to a project
- **Your Project ID** — find it in Mixpanel under Settings > Project Details
- **A service account** (username + secret) from Mixpanel under Settings > Service Accounts, OR a browser available for OAuth login

---

## Step 1: Install the Plugin

Open Claude Code and run:

```
/plugin marketplace add jaredmcfarland/mixpanel_data
/plugin install mixpanel-data@mixpanel-data-marketplace
```

This installs the `mixpanel-data` plugin, which teaches Claude how to be a Mixpanel analytics expert.

---

## Step 2: Run Setup

```
/mixpanel-data:setup
```

This installs the `mixpanel_data` Python package and all analysis dependencies (pandas, matplotlib, networkx, etc.). It takes about a minute.

At the end, setup checks for Mixpanel credentials. If you see a warning about missing credentials, continue to Step 3.

---

## Step 3: Authenticate

You only need to do this once. Choose the method that works best for you.

### Option A: Service Account (Recommended)

Run the `/mp-auth` command:

```
/mp-auth add my-project
```

Claude will walk you through it step by step:

1. You provide your **account name** (any label you want, like "production")
2. You provide your **service account username** (starts with something like `sa.`)
3. You provide your **project ID** (a number)
4. You provide your **region** (`us`, `eu`, or `in`)
5. Claude gives you a command to run that securely collects your secret with hidden input

Your secret is never visible in the conversation.

### Option B: OAuth Login (Browser-Based)

```
/mp-auth login
```

Claude will ask for your region, then open a browser window where you log in with your Mixpanel credentials. After login, your projects are automatically discovered — if you have exactly one project, it's selected for you. If you have multiple, Claude will help you pick one.

### Verify It Worked

```
/mp-auth test
```

You should see confirmation that Claude connected successfully and found events in your project.

---

## Step 4: Start Asking Questions

That's it — you're ready. Just ask questions in plain English:

```
How many signups did we get last week?
```

```
Where do users drop off in our onboarding flow?
```

```
Show me daily active users for the past 90 days, broken down by platform.
```

```
Do users who complete the tutorial retain better than those who skip it?
```

```
What's the most common path users take after signing up?
```

```
Build me a weekly KPI dashboard showing signups, activation, and revenue.
```

Claude automatically:
- Discovers your events and properties
- Chooses the right query engine (Insights, Funnels, Retention, or Flows)
- Writes and runs Python code using `mixpanel_data` + `pandas`
- Explains the results in plain language

---

## What's Happening Under the Hood

When you ask a question, Claude writes Python like this:

```python
import mixpanel_data as mp

ws = mp.Workspace()

# Insights: "How many signups last week?"
result = ws.query("Signup", last=7, unit="day")
print(result.df)

# Funnels: "Where do users drop off?"
funnel = ws.query_funnel(["Signup", "Onboarding", "Purchase"], last=30)
print(funnel.overall_conversion_rate)

# Retention: "Do users come back?"
retention = ws.query_retention("Signup", "Login", retention_unit="week", last=90)
print(retention.df)

# Flows: "What paths do users take?"
flow = ws.query_flow("Signup", forward=4)
print(flow.top_transitions(5))
```

You never need to write this yourself, but it's helpful to know what's possible. Claude uses four query engines:

| Engine | Method | Answers |
|--------|--------|---------|
| Insights | `ws.query()` | How many? How much? What's trending? |
| Funnels | `ws.query_funnel()` | Do users convert through a sequence? |
| Retention | `ws.query_retention()` | Do users come back after an action? |
| Flows | `ws.query_flow()` | What paths do users take? |

---

## Specialist Agents

For complex questions, the plugin includes specialist agents that Claude invokes automatically:

| Agent | Handles |
|-------|---------|
| **analyst** | General analytics, dashboards, multi-metric queries |
| **explorer** | "What data do we have?" Schema discovery, data landscape |
| **diagnostician** | "Why did X drop?" Root cause analysis across dimensions |
| **synthesizer** | Cross-engine analysis, statistical testing, graph algorithms |
| **narrator** | Executive summaries, stakeholder reports |

You don't need to think about these — Claude picks the right one based on your question.

---

## Managing Accounts

### Check current status

```
/mp-auth status
```

### Switch between accounts

```
/mp-auth list
/mp-auth switch production
```

### Discover accessible projects

```
/mp-auth projects
```

### Switch projects (v2 config)

```
/mp-auth switch-project 67890
```

### Upgrade to v2 config (enables project switching)

```
/mp-auth migrate
```

---

## Troubleshooting

### "No credentials configured"

Run `/mp-auth add my-project` and follow the prompts, or `/mp-auth login` for OAuth.

### "Authentication failed"

- Check that your service account username and secret are correct (Mixpanel Settings > Service Accounts)
- Verify your project ID matches the project the service account has access to
- Make sure the region matches your project's data residency
- Run `/mp-auth test` for detailed error information

### Plugin not appearing

1. Make sure plugins are enabled in your Claude Code settings
2. Restart Claude Code after installing the plugin
3. Run `/mixpanel-data:setup` again

### Setup fails to install packages

If you're behind a corporate proxy or firewall, you may need to configure `pip` or `uv` with your proxy settings before running setup.

---

## Next Steps

- **Full documentation**: [jaredmcfarland.github.io/mixpanel_data](https://jaredmcfarland.github.io/mixpanel_data/)
- **Plugin details**: [Plugin README](https://github.com/jaredmcfarland/mixpanel_data/blob/main/mixpanel-plugin/README.md)
- **Comprehensive getting started guide**: [Getting Started Guide](getting-started-guide.md) — covers the Python library and CLI in depth
- **Using with Cowork**: [Cowork Quick Start](quickstart-claude-cowork.md)
