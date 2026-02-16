# Claude Code Memory (CLAUDE.md)

Claude Code has two kinds of persistent memory:
- **Auto memory**: Claude automatically saves useful context
- **CLAUDE.md files**: Markdown files you write with instructions for Claude

## Memory Hierarchy

| Memory Type | Location | Purpose | Shared With |
|---|---|---|---|
| **Managed policy** | System-level paths | Organization-wide instructions | All users |
| **Project memory** | `./CLAUDE.md` or `./.claude/CLAUDE.md` | Team-shared project instructions | Team via VCS |
| **Project rules** | `./.claude/rules/*.md` | Modular topic-specific instructions | Team via VCS |
| **User memory** | `~/.claude/CLAUDE.md` | Personal preferences for all projects | Just you |
| **Project memory (local)** | `./CLAUDE.local.md` | Personal project-specific preferences | Just you |
| **Auto memory** | `~/.claude/projects/<project>/memory/` | Claude's automatic notes | Just you (per project) |

## Auto Memory

Directory structure:
```
~/.claude/projects/<project>/memory/
├── MEMORY.md          # Concise index, loaded into every session (first 200 lines)
├── debugging.md       # Detailed notes on debugging patterns
├── api-conventions.md # API design decisions
└── ...
```

- First 200 lines of MEMORY.md loaded into system prompt
- Topic files loaded on demand
- Use `/memory` to open file selector

## CLAUDE.md Imports

Use `@path/to/import` syntax to import additional files:

```
See @README for project overview and @package.json for available npm commands.

# Additional Instructions
- git workflow @docs/git-instructions.md
```

## Modular Rules (.claude/rules/)

```
.claude/rules/
├── frontend/
│   ├── react.md
│   └── styles.md
├── backend/
│   ├── api.md
│   └── database.md
└── general.md
```

### Path-Specific Rules

```markdown
---
paths:
  - "src/api/**/*.ts"
---

# API Development Rules
- All API endpoints must include input validation
- Use the standard error response format
```
