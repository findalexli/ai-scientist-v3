# Claude Code Skills

Skills extend what Claude can do. Create a `SKILL.md` file with instructions, and Claude adds it to its toolkit. Claude uses skills when relevant, or you can invoke one directly with `/skill-name`.

Custom slash commands have been merged into skills. A file at `.claude/commands/review.md` and a skill at `.claude/skills/review/SKILL.md` both create `/review` and work the same way.

Claude Code skills follow the [Agent Skills](https://agentskills.io) open standard.

## Getting Started

### Create Your First Skill

```bash
mkdir -p ~/.claude/skills/explain-code
```

Create `~/.claude/skills/explain-code/SKILL.md`:

```yaml
---
name: explain-code
description: Explains code with visual diagrams and analogies. Use when explaining how code works, teaching about a codebase, or when the user asks "how does this work?"
---

When explaining code, always include:

1. **Start with an analogy**: Compare the code to something from everyday life
2. **Draw a diagram**: Use ASCII art to show the flow, structure, or relationships
3. **Walk through the code**: Explain step-by-step what happens
4. **Highlight a gotcha**: What's a common mistake or misconception?

Keep explanations conversational. For complex concepts, use multiple analogies.
```

### Where Skills Live

| Location | Path | Applies to |
|---|---|---|
| Enterprise | Managed settings | All users in organization |
| Personal | `~/.claude/skills/<skill-name>/SKILL.md` | All your projects |
| Project | `.claude/skills/<skill-name>/SKILL.md` | This project only |
| Plugin | `<plugin>/skills/<skill-name>/SKILL.md` | Where plugin is enabled |

Higher-priority locations win: enterprise > personal > project.

### Skill Directory Structure

```
my-skill/
├── SKILL.md           # Main instructions (required)
├── template.md        # Template for Claude to fill in
├── examples/
│   └── sample.md      # Example output showing expected format
└── scripts/
    └── validate.sh    # Script Claude can execute
```

## Frontmatter Reference

```yaml
---
name: my-skill
description: What this skill does
disable-model-invocation: true
allowed-tools: Read, Grep
context: fork
agent: Explore
model: sonnet
---
```

| Field | Required | Description |
|---|---|---|
| `name` | No | Display name. If omitted, uses directory name. Lowercase letters, numbers, hyphens (max 64 chars) |
| `description` | Recommended | What the skill does and when to use it. Claude uses this to decide when to apply automatically |
| `argument-hint` | No | Hint shown during autocomplete (e.g., `[issue-number]`) |
| `disable-model-invocation` | No | `true` prevents Claude from auto-loading. Default: `false` |
| `user-invocable` | No | `false` hides from `/` menu. Default: `true` |
| `allowed-tools` | No | Tools Claude can use without asking permission when skill is active |
| `model` | No | Model to use when skill is active |
| `context` | No | Set to `fork` to run in a forked subagent context |
| `agent` | No | Which subagent type when `context: fork` is set |
| `hooks` | No | Hooks scoped to this skill's lifecycle |

### String Substitutions

| Variable | Description |
|---|---|
| `$ARGUMENTS` | All arguments passed when invoking |
| `$ARGUMENTS[N]` | Specific argument by 0-based index |
| `$N` | Shorthand for `$ARGUMENTS[N]` |
| `${CLAUDE_SESSION_ID}` | Current session ID |

## Control Who Invokes a Skill

| Frontmatter | You can invoke | Claude can invoke | When loaded |
|---|---|---|---|
| (default) | Yes | Yes | Description always in context, full skill loads when invoked |
| `disable-model-invocation: true` | Yes | No | Description not in context, full skill loads when you invoke |
| `user-invocable: false` | No | Yes | Description always in context, full skill loads when invoked |

## Advanced Patterns

### Inject Dynamic Context

The `` !`command` `` syntax runs shell commands before skill content is sent to Claude:

```yaml
---
name: pr-summary
description: Summarize changes in a pull request
context: fork
agent: Explore
allowed-tools: Bash(gh *)
---

## Pull request context
- PR diff: !`gh pr diff`
- PR comments: !`gh pr view --comments`
- Changed files: !`gh pr diff --name-only`

## Your task
Summarize this pull request...
```

### Run Skills in a Subagent

Add `context: fork` to run in isolation. The skill content becomes the prompt driving the subagent.

| Approach | System prompt | Task | Also loads |
|---|---|---|---|
| Skill with `context: fork` | From agent type (Explore, Plan, etc.) | SKILL.md content | CLAUDE.md |
| Subagent with `skills` field | Subagent's markdown body | Claude's delegation message | Preloaded skills + CLAUDE.md |

### Generate Visual Output

Skills can bundle and run scripts in any language. Pattern: generate interactive HTML files that open in the browser for exploring data, debugging, or creating reports.
