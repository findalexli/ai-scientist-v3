# AI Scientist v3 - Documentation Index

Reference documentation for Claude Code features used in the AI Scientist v3 architecture.

## Documents

| Document | Description |
|---|---|
| [Claude Code Overview](claude-code-overview.md) | High-level overview of Claude Code capabilities, environments, architecture, and installation |
| [Skills](skills.md) | Creating and using skills (SKILL.md files) to extend Claude's capabilities with reusable instructions |
| [Hooks](hooks.md) | Lifecycle hooks for automating actions at specific points (PreToolUse, PostToolUse, Stop, etc.) |
| [Subagents](subagents.md) | Specialized AI assistants with custom system prompts, tool access, and independent context windows |
| [Agent Teams](agent-teams.md) | Coordinating multiple Claude Code instances working together on complex tasks |
| [Headless / Agent SDK](headless-agent-sdk.md) | Running Claude Code programmatically via CLI, Python, or TypeScript for scripts and CI/CD |
| [Memory / CLAUDE.md](memory-claude-md.md) | Persistent memory system including CLAUDE.md files, auto memory, and modular rules |
| [CLI Reference](cli-reference.md) | Complete CLI commands, flags, and configuration options |

## How These Map to AI Scientist v3

| v2 Component | v3 Replacement | Docs |
|---|---|---|
| `agents/*.py` (Python wrappers) | Skills (`.claude/skills/`) | [Skills](skills.md) |
| `treesearch/` (BFS orchestration) | Agent Teams | [Agent Teams](agent-teams.md) |
| `prompts/*.yaml` (prompt templates) | CLAUDE.md + Skill instructions | [Memory](memory-claude-md.md), [Skills](skills.md) |
| `llm_gateway.py` (API routing) | Claude Code's native model selection | [CLI Reference](cli-reference.md) |
| `token_tracker.py` (usage tracking) | `--max-budget-usd` flag | [CLI Reference](cli-reference.md) |
| Quality gates in Python | Hooks | [Hooks](hooks.md) |
| Headless execution scripts | Agent SDK (`claude -p`) | [Headless / Agent SDK](headless-agent-sdk.md) |
