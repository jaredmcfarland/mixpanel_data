# Building Skills for Claude Code | Claude

## **When AI lacks your institutional knowledge**

Your team has built up hard-won knowledge about your data—you know which tables are the source of truth, why certain filters must always apply, and how revenue can be calculated differently, depending on the context. But Claude doesn't retain context from previous sessions.

Without a way to share your team's data playbook, you end up re-explaining the same details through prompting. Skills let you package that expertise into something Claude Code can discover and use automatically.

## **How Skills solve the knowledge gap**

Skills give Claude Code access to your procedural knowledge through progressive disclosure, revealing information in layers only when needed, rather than flooding the context window.

Here's how it works: Claude always sees a lightweight index of available skills (names and descriptions, about 100 words each). When you ask Claude to analyze revenue data, it recognizes that your data warehouse SQL skill applies and loads those instructions. Detailed documentation about specific tables loads only when needed during execution.

This design solves the fundamental tension between comprehensive knowledge and limited context. You can build a skill with dozens of table definitions and pages of business logic documentation, but Claude only loads what's relevant for the current query.

## **The anatomy of a skill**

Every skill follows a specific structure designed for both human maintenance and AI consumption. Let's look at how a data warehouse skill would be structured.

### **SKILL.md: The core instructions**

The SKILL.md file starts with YAML frontmatter containing two critical fields:

```
name: sql-analysis
description: Use when analyzing business data: revenue, ARR, customer segments, product usage, or sales pipeline. Provides table schemas, metric definitions, required filters, and query patterns specific to ACME's data warehouse.
```

That description determines when Claude loads your skill. When someone says "what was our revenue last quarter" or "show me customer churn by segment," Claude recognizes this skill applies.

The markdown body contains your actual instructions, organized for progressive disclosure:

```


# SQL Analysis Skill


## Quick Start Workflow
When a user asks for data analysis:
1. **Clarify the request**
   - What time period? (default to current year if unspecified)
   - Which customer segment? (clarify "customers" - accounts or organizations?)
   - What business decision will this inform?

2. **Check for existing dashboards**
   - Look in `references/dashboards.md` for pre-built reports
   - If a dashboard exists, direct them there first

3. **Identify the data source**
   - Prefer aggregated tables over raw event data
   - Verify table has required columns before querying

4. **Execute the analysis**
   - Apply required filters (exclude test accounts, etc.)
   - Validate results against known benchmarks

### Standard Query Filters
For all revenue queries:
- Always exclude test accounts: `WHERE account != 'Test'`

- Always use complete periods: `WHERE month <= DATE_TRUNC(CURRENT_DATE(), MONTH)`

### ARR Calculations
- Monthly to ARR: `monthly_revenue * 12`

- 7-day run rate: `rolling_7d * 52`

## Knowledge Base
For detailed table schemas and query patterns, see:
- **Revenue & Finance** → `references/finance.md`

- **Product Usage** → `references/product.md`
- **Sales & Pipeline** → `references/sales.md`

- **Customer Success** → `references/customers.md`
```

Notice how the SKILL.md provides high-level workflow guidance and critical business logic, while pointing to reference files for detailed documentation. 

**References: On-demand documentation**

The `references/` directory contains detailed documentation Claude loads only when needed. Here's what ACME's `references/finance.md` might look like:

-   **Table schemas**: Column names, data types, and descriptions for key tables like `monthly_revenue` and `arr_metrics`

-   **Standard filters**: Which WHERE clauses should always apply (e.g., excluding test accounts, using complete periods only)
-   **Metric definitions**: How to calculate ARR, run rates, and other business metrics with exact formulas

-   **Common query patterns**: Ready-to-adapt SQL snippets for frequent requests like "revenue by customer segment and region" or "ARR trends over time"
-   **Edge cases**: Known quirks, like when to use one table over another, or columns are commonly used for JOINs even though the naming convention might not match

Each reference file might be thousands of words, but users only pay the context cost for what they actually need.

A key principle to remember: information should live in either SKILL.md or reference files but not both, so keep SKILL.md lean with high-level instructions while putting detailed specifications in references.

**Skills vs CLAUDE.md**

Skills and CLAUDE.md files both give Claude context, but serve different purposes. CLAUDE.md is always loaded into Claude’s context. It’s for project-specific guidance (coding conventions, local workflows, common commands) that lives in your repo as a single markdown file, and works only in Claude Code. 

Skills use progressive disclosure, loading only when relevant, and work across all Claude platforms (claude.ai, Claude Code, and Claude API). Beyond the context management advantages, Skills can include executable code and reference files—not just markdown. This makes them ideal for substantial, reusable knowledge that spans projects, such as data warehouse schemas, company design standards, or domain expertise.

## **Building your first Skill**

Start by installing Claude Code in your terminal or IDE:

```
curl -fsSL https://claude.ai/install.sh | bash
```

Then add the Claude Code [plugin](https://github.com/anthropics/skills/blob/0f77e501e6506235956d953cd2d7a2a4aa9ba133/.claude-plugin/marketplace.json#L24-L42) which includes the [skill-creator skill](https://support.claude.com/en/articles/12599426-how-to-create-a-skill-with-claude-through-conversation). Now identify your first candidate. The best skills share these characteristics:

-   **Cross-repo relevance**: Knowledge that applies across multiple projects

-   **Multi-audience value**: Both technical and non-technical users benefit
-   **Stable patterns**: Procedures that don't change with every commit

Data warehouse queries, internal platform documentation, and company-wide standards all make excellent skills.

Claude can also serve as your documentation partner here. Start off by describing your workflow conversationally:

```
Help me create a data warehouse skill. I'll walk you through our tables 
and business logic, and you can help me structure it properly.
```

Claude will ask clarifying questions during this process to collect details around your workflow: What are your key tables? What business terms need definition? What filters should always apply? This extraction process surfaces knowledge critical to the skill's effectiveness.

Once you've outlined your domain, Claude will help you structure the SKILL.md and organize reference files. As you use the skill, you can always add in more reference files as you discover what’s missing.

### **Storing and sharing skills**

Skills live locally on your machine, giving you full control over when and how they're updated. When you're ready to share a skill with your team, you have several options depending on your workflow:

-   **Zip file:** Share skills directly with teammates for quick, informal collaboration

-   **Internal versioned repository:** Host skills in a centralized repo where your organization can access approved, maintained versions alongside code
-   **Git repository:** Version your skills alongside code, with full commit history and branch management

-   **Plugin bundle:** Package skills into a Claude Code plugin for easy distribution across your team

Choose the approach that fits how your team already works. Teams with strong Git workflows often prefer repository-based sharing, while organizations with formal tooling standards may benefit from plugin bundles or a centralized skill repository.

## **Real implementation patterns**

Here are examples from the community that show Skills in action:

[Playwright skill](https://github.com/lackeyjb/playwright-skill): Enables Claude to write and run browser automation on the fly using Playwright. Ask Claude to test a webpage, verify forms work correctly, or capture screenshots—Claude writes the code, executes it, and returns results without requiring any manual setup.

[Web assets generator skill:](https://www.reddit.com/r/ClaudeAI/comments/1ocm1if/built_a_claude_code_skill_that_completely/) Creates favicons, app icons, and social media images from logos, text, or emojis. Tell Claude you need a favicon for your startup or Open Graph images for your blog, and it generates properly sized assets ready for your project.

This [Skills marketplace shares even more examples to inspire you.](https://skillsmp.com/) Explore community-built skills that extend what Claude can do—from automated testing and data visualization to code review and domain name brainstorming.

## **Getting started with Claude Code and Skills**

Skills let you encode institutional knowledge that works across teams and platforms. By capturing your procedures, terminology, and business logic into a skill, you create organizational memory that scales. New analysts query data correctly on day one, data scientists stop explaining the same table relationships, and business users can self-serve accurate metrics. Start building your first Skill in [Claude Code](https://www.claude.com/product/claude-code) today.

‍

‍

‍

---
Source: [Building Skills for Claude Code | Claude](https://website.claude.com/blog/building-skills-for-claude-code)