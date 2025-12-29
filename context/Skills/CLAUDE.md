# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Directory Purpose

Documentation for Claude Code Agent Skills - specialized instructions that Claude loads dynamically for task-specific workflows.

## File Reference

| File | Purpose |
|------|---------|
| `What_are_Skills.md` | Conceptual overview, comparisons to Projects/MCP |
| `Agent_Skills.md` | Technical overview of skill system |
| `Skills_best_practices.md` | Authoring guidelines, conciseness, degrees of freedom |
| `Building_Skills_for_Claude_Code.md` | Claude Code-specific skill development |
| `How_to_Create_Custom_Skills.md` | Step-by-step creation guide |
| `How_to_create_Skills_for_Claude.md` | General skill creation |
| `Equipping_agents_with_Skills.md` | Loading skills into agents |
| `Skills_explained.md` | Detailed explanation of skill mechanics |
| `Introducing_Agent_Skills_Claude.md` | Introduction and concepts |
| `Anthropic_Example_SKills_README.md` | Example skills from Anthropic |

## Skill Structure

```
.claude/skills/my-skill/
├── SKILL.md                 # Required - main instructions
├── reference.md             # Optional - additional docs
└── scripts/                 # Optional - executable scripts
    └── process.py
```

## SKILL.md Format

```markdown
---
name: my-skill
description: Brief description for discovery
triggers:
  - keyword1
  - keyword2
---

# Skill Name

Instructions Claude follows when this skill is active.

## When to Use
- Specific scenario 1
- Specific scenario 2

## Process
1. Step one
2. Step two
```

## Skill Locations

| Type | Location | Scope |
|------|----------|-------|
| Project | `.claude/skills/` | Current project |
| User | `~/.claude/skills/` | All projects |
| Plugin | `plugins/<name>/skills/` | Via plugin |

## Key Authoring Principles

1. **Conciseness**: Every token competes for context window space
2. **Progressive disclosure**: Metadata loads first, SKILL.md only when relevant
3. **Degrees of freedom**: Match specificity to task fragility
   - High freedom: Text instructions for flexible tasks
   - Medium freedom: Pseudocode with parameters
   - Low freedom: Exact scripts for brittle tasks
4. **Assume Claude's intelligence**: Only add context Claude doesn't already have

## Skills vs Other Features

| Feature | Loading | Scope |
|---------|---------|-------|
| Skills | Dynamic, on-demand | Task-specific procedures |
| Projects | Always loaded | Static background knowledge |
| MCP | Connection-based | External tools/data access |
| Custom Instructions | Always loaded | Broad preferences |
