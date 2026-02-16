# Claude Code Subagents

Subagents are specialized AI assistants that handle specific types of tasks. Each runs in its own context window with a custom system prompt, specific tool access, and independent permissions.

## Built-in Subagents

| Agent | Model | Tools | Purpose |
|---|---|---|---|
| **Explore** | Haiku (fast) | Read-only | File discovery, code search, codebase exploration |
| **Plan** | Inherits | Read-only | Codebase research for planning |
| **General-purpose** | Inherits | All tools | Complex research, multi-step operations, code modifications |
| **Bash** | Inherits | Terminal | Running commands in separate context |

## Creating Subagents

Subagent files use YAML frontmatter + markdown system prompt:

```markdown
---
name: code-reviewer
description: Reviews code for quality and best practices
tools: Read, Glob, Grep
model: sonnet
---

You are a code reviewer. When invoked, analyze the code and provide
specific, actionable feedback on quality, security, and best practices.
```

### Subagent Scope

| Location | Scope | Priority |
|---|---|---|
| `--agents` CLI flag | Current session | 1 (highest) |
| `.claude/agents/` | Current project | 2 |
| `~/.claude/agents/` | All your projects | 3 |
| Plugin's `agents/` directory | Where plugin is enabled | 4 (lowest) |

### Frontmatter Fields

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Unique identifier (lowercase + hyphens) |
| `description` | Yes | When Claude should delegate to this subagent |
| `tools` | No | Tools the subagent can use. Inherits all if omitted |
| `disallowedTools` | No | Tools to deny |
| `model` | No | `sonnet`, `opus`, `haiku`, or `inherit`. Default: `inherit` |
| `permissionMode` | No | `default`, `acceptEdits`, `delegate`, `dontAsk`, `bypassPermissions`, `plan` |
| `maxTurns` | No | Maximum agentic turns |
| `skills` | No | Skills to preload into subagent's context |
| `mcpServers` | No | MCP servers available to this subagent |
| `hooks` | No | Lifecycle hooks scoped to this subagent |
| `memory` | No | Persistent memory scope: `user`, `project`, or `local` |

### CLI-Defined Subagents

```bash
claude --agents '{
  "code-reviewer": {
    "description": "Expert code reviewer. Use proactively after code changes.",
    "prompt": "You are a senior code reviewer. Focus on code quality, security, and best practices.",
    "tools": ["Read", "Grep", "Glob", "Bash"],
    "model": "sonnet"
  }
}'
```

## Subagent Capabilities

### Restrict Tool Access
```yaml
---
name: safe-researcher
description: Research agent with restricted capabilities
tools: Read, Grep, Glob, Bash
disallowedTools: Write, Edit
---
```

### Restrict Spawnable Subagents
```yaml
---
name: coordinator
description: Coordinates work across specialized agents
tools: Task(worker, researcher), Read, Bash
---
```

### Preload Skills
```yaml
---
name: api-developer
description: Implement API endpoints following team conventions
skills:
  - api-conventions
  - error-handling-patterns
---
```

### Persistent Memory
```yaml
---
name: code-reviewer
description: Reviews code for quality and best practices
memory: user
---
```

| Scope | Location |
|---|---|
| `user` | `~/.claude/agent-memory/<name>/` |
| `project` | `.claude/agent-memory/<name>/` |
| `local` | `.claude/agent-memory-local/<name>/` |

### Hooks in Subagent Frontmatter

```yaml
---
name: code-reviewer
description: Review code changes with automatic linting
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate-command.sh"
  PostToolUse:
    - matcher: "Edit|Write"
      hooks:
        - type: command
          command: "./scripts/run-linter.sh"
---
```

## Usage Patterns

### Foreground vs Background
- **Foreground**: Blocks main conversation until complete. Permission prompts pass through.
- **Background**: Runs concurrently. Auto-denies anything not pre-approved. MCP tools unavailable.

### Resume Subagents
Each invocation creates fresh context. Ask Claude to resume to continue with full previous history.

### Common Patterns
- **Isolate high-volume operations**: Tests, docs, logs stay in subagent context
- **Run parallel research**: Spawn multiple subagents for independent investigations
- **Chain subagents**: Sequential workflows where each passes results to next

## Example Subagents

### Code Reviewer (Read-only)
```markdown
---
name: code-reviewer
description: Expert code review specialist. Use immediately after writing or modifying code.
tools: Read, Grep, Glob, Bash
model: inherit
---

You are a senior code reviewer ensuring high standards.

Review checklist:
- Code clarity and readability
- Proper error handling
- No exposed secrets
- Good test coverage
- Performance considerations

Provide feedback organized by priority:
- Critical issues (must fix)
- Warnings (should fix)
- Suggestions (consider improving)
```

### Debugger
```markdown
---
name: debugger
description: Debugging specialist for errors, test failures, and unexpected behavior.
tools: Read, Edit, Bash, Grep, Glob
---

You are an expert debugger specializing in root cause analysis.

1. Capture error message and stack trace
2. Identify reproduction steps
3. Isolate the failure location
4. Implement minimal fix
5. Verify solution works
```
