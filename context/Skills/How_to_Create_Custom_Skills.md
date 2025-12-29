# How to create custom Skills | Claude Help Center

Custom Skills let you enhance Claude with specialized knowledge and workflows specific to your organization or personal work style. This article explains how to create, structure, and test your own Skills.

Skills can be as simple as a few lines of instructions or as complex as multi-file packages with executable code. The best Skills:

## Creating a Skill.md File

Every Skill consists of a directory containing at minimum a Skill.md file, which is the core of the Skill. This file must start with a YAML frontmatter to hold name and description fields, which are required metadata. It can also contain additional metadata, instructions for Claude or reference files, executable scripts, or tools.

### Required metadata fields

**name:** A human-friendly name for your Skill (64 characters maximum)

**description:** A clear description of what the Skill does and when to use it.

### Optional Metadata Fields

**version:** Track versions of your Skill as you iterate.

**dependencies:** Software packages required by your Skill.

The metadata in the Skill.md file serves as the first level of a progressive disclosure system, providing just enough information for Claude to know when the Skill should be used without having to load all of the content.

### Markdown Body

The Markdown body is the second level of detail after the metadata, so Claude will access this if needed after reading the metadata. Depending on your task, Claude can access the Skill.md file and use the Skill.

### Example Skill.md

**Brand Guidelines Skill**

## Adding Resources

If you have too much information to add to a single [Skill.md](http://skill.md/) file (e.g., sections that only apply to specific scenarios), you can add more content by adding files within your Skill directory. For example, add a REFERENCE.md file containing supplemental and reference information to your Skill directory. Referencing it in [Skill.md](http://skill.md/) will help Claude decide if it needs to access that resource when executing the Skill.

## Adding Scripts

For more advanced Skills, attach executable code files to [Skill.md](http://skill.md/), allowing Claude to run code. For example, our document skills use the following programming languages and packages:

## Packaging Your Skill

Once your Skill folder is complete:

**Correct structure:**

my-Skill.zip

└── my-Skill/

├── Skill.md

└── resources/

**Incorrect structure:**

my-Skill.zip

└── (files directly in ZIP root)

## Testing Your Skill

### Before Uploading

1\. Review your Skill.md for clarity

2\. Check that the description accurately reflects when Claude should use the Skill

3\. Verify all referenced files exist in the correct locations

4\. Test with example prompts to ensure Claude invokes it appropriately

### After Uploading to Claude

2\. Try several different prompts that should trigger it

3\. Review Claude's thinking to confirm it's loading the Skill

4\. Iterate on the description if Claude isn't using it when expected

## Best Practices

**Keep it focused:** Create separate Skills for different workflows. Multiple focused Skills compose better than one large Skill.

**Write clear descriptions:** Claude uses descriptions to decide when to invoke your Skill. Be specific about when it applies.

**Start simple:** Begin with basic instructions in Markdown before adding complex scripts. You can always expand on the Skill later.

**Use examples:** Include example inputs and outputs in your Skill.md file to help Claude understand what success looks like.

**Version your Skills:** Track versions as you iterate. This helps when troubleshooting or rolling back changes.

**Test incrementally:** Test after each significant change rather than building a complex Skill all at once.

**Skills can build on each other:** While Skills can't explicitly reference other Skills, Claude can use multiple Skills together automatically. This composability is one of the most powerful parts of the Skills feature.

## Security Considerations

## Example Skills to Reference

---

Related Articles

[

What are Skills?

](https://support.claude.com/en/articles/12512176-what-are-skills)[

Using Skills in Claude

](https://support.claude.com/en/articles/12512180-using-skills-in-claude)[

Teach Claude your way of working using skills

](https://support.claude.com/en/articles/12580051-teach-claude-your-way-of-working-using-skills)[

How to create a skill with Claude through conversation

](https://support.claude.com/en/articles/12599426-how-to-create-a-skill-with-claude-through-conversation)[

Claude for Financial Services Skills

](https://support.claude.com/en/articles/12663107-claude-for-financial-services-skills)

---
Source: [How to create custom Skills | Claude Help Center](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills)