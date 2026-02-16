# Running Claude Code Programmatically (Agent SDK)

The Agent SDK gives you the same tools, agent loop, and context management that power Claude Code. Available as CLI for scripts/CI/CD, or as Python and TypeScript packages.

## Basic Usage

```bash
claude -p "Find and fix the bug in auth.py" --allowedTools "Read,Edit,Bash"
```

## Key Patterns

### Structured Output
```bash
claude -p "Summarize this project" --output-format json
```

With JSON Schema:
```bash
claude -p "Extract function names from auth.py" \
  --output-format json \
  --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}},"required":["functions"]}'
```

### Stream Responses
```bash
claude -p "Explain recursion" --output-format stream-json --verbose --include-partial-messages
```

### Auto-Approve Tools
```bash
claude -p "Run tests and fix failures" --allowedTools "Bash,Read,Edit"
```

### Continue Conversations
```bash
# First request
claude -p "Review this codebase for performance issues"

# Continue most recent conversation
claude -p "Now focus on database queries" --continue

# Resume specific session
session_id=$(claude -p "Start a review" --output-format json | jq -r '.session_id')
claude -p "Continue that review" --resume "$session_id"
```

### Custom System Prompt
```bash
gh pr diff "$1" | claude -p \
  --append-system-prompt "You are a security engineer. Review for vulnerabilities." \
  --output-format json
```

## System Prompt Flags

| Flag | Behavior | Modes |
|---|---|---|
| `--system-prompt` | Replaces entire default prompt | Interactive + Print |
| `--system-prompt-file` | Replaces with file contents | Print only |
| `--append-system-prompt` | Appends to default prompt | Interactive + Print |
| `--append-system-prompt-file` | Appends file contents | Print only |
