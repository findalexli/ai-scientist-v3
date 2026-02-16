# Claude Code CLI Reference

## CLI Commands

| Command | Description |
|---|---|
| `claude` | Start interactive REPL |
| `claude "query"` | Start REPL with initial prompt |
| `claude -p "query"` | Query via SDK, then exit |
| `cat file \| claude -p "query"` | Process piped content |
| `claude -c` | Continue most recent conversation |
| `claude -r "<session>" "query"` | Resume session by ID or name |
| `claude update` | Update to latest version |
| `claude mcp` | Configure MCP servers |

## Key CLI Flags

| Flag | Description |
|---|---|
| `--add-dir` | Add additional working directories |
| `--agent` | Specify an agent for the session |
| `--agents` | Define custom subagents via JSON |
| `--allowedTools` | Tools that execute without permission prompting |
| `--append-system-prompt` | Append custom text to system prompt |
| `--continue`, `-c` | Continue most recent conversation |
| `--dangerously-skip-permissions` | Skip all permission prompts |
| `--debug` | Enable debug mode |
| `--disallowedTools` | Tools removed from model's context |
| `--fallback-model` | Automatic fallback model when overloaded |
| `--max-budget-usd` | Maximum dollar spend on API calls |
| `--max-turns` | Limit agentic turns (print mode only) |
| `--mcp-config` | Load MCP servers from JSON files |
| `--model` | Set model for session (sonnet, opus, haiku, or full name) |
| `--output-format` | Output format: text, json, stream-json |
| `--permission-mode` | Begin in specified permission mode |
| `--print`, `-p` | Print response without interactive mode |
| `--remote` | Create web session on claude.ai |
| `--resume`, `-r` | Resume specific session |
| `--system-prompt` | Replace entire system prompt |
| `--tools` | Restrict which tools Claude can use |
| `--verbose` | Enable verbose logging |

## --agents Flag Format

```bash
claude --agents '{
  "code-reviewer": {
    "description": "Expert code reviewer.",
    "prompt": "You are a senior code reviewer.",
    "tools": ["Read", "Grep", "Glob", "Bash"],
    "model": "sonnet"
  }
}'
```

Fields: `description` (required), `prompt` (required), `tools`, `disallowedTools`, `model`, `skills`, `mcpServers`, `maxTurns`, `permissionMode`, `hooks`, `memory`.

## System Prompt Flags

| Flag | Behavior | Modes |
|---|---|---|
| `--system-prompt` | Replaces entire default prompt | Interactive + Print |
| `--system-prompt-file` | Replaces with file contents | Print only |
| `--append-system-prompt` | Appends to default prompt | Interactive + Print |
| `--append-system-prompt-file` | Appends file contents | Print only |
