# Claude Code Hooks Reference

Hooks are user-defined shell commands or LLM prompts that execute automatically at specific points in Claude Code's lifecycle.

## Hook Lifecycle

| Event | When it fires |
|---|---|
| `SessionStart` | When a session begins or resumes |
| `UserPromptSubmit` | When you submit a prompt, before Claude processes it |
| `PreToolUse` | Before a tool call executes. Can block it |
| `PermissionRequest` | When a permission dialog appears |
| `PostToolUse` | After a tool call succeeds |
| `PostToolUseFailure` | After a tool call fails |
| `Notification` | When Claude Code sends a notification |
| `SubagentStart` | When a subagent is spawned |
| `SubagentStop` | When a subagent finishes |
| `Stop` | When Claude finishes responding |
| `TeammateIdle` | When an agent team teammate is about to go idle |
| `TaskCompleted` | When a task is being marked as completed |
| `PreCompact` | Before context compaction |
| `SessionEnd` | When a session terminates |

## Configuration

Hooks are defined in JSON settings files with three levels of nesting:
1. Choose a hook event
2. Add a matcher group to filter when it fires
3. Define one or more hook handlers to run when matched

### Hook Locations

| Location | Scope | Shareable |
|---|---|---|
| `~/.claude/settings.json` | All your projects | No |
| `.claude/settings.json` | Single project | Yes, commit to repo |
| `.claude/settings.local.json` | Single project | No, gitignored |
| Managed policy settings | Organization-wide | Yes, admin-controlled |
| Plugin `hooks/hooks.json` | When plugin is enabled | Yes |
| Skill or agent frontmatter | While component is active | Yes |

### Matcher Patterns

| Event | What the matcher filters | Example values |
|---|---|---|
| PreToolUse, PostToolUse, etc. | tool name | `Bash`, `Edit\|Write`, `mcp__.*` |
| SessionStart | how session started | `startup`, `resume`, `clear`, `compact` |
| SessionEnd | why session ended | `clear`, `logout`, `other` |

### Hook Handler Types

- **Command hooks** (`type: "command"`): Run a shell command
- **Prompt hooks** (`type: "prompt"`): Send a prompt to a Claude model for evaluation
- **Agent hooks** (`type: "agent"`): Spawn a subagent that can use tools to verify conditions

### Common Fields

| Field | Required | Description |
|---|---|---|
| `type` | yes | `"command"`, `"prompt"`, or `"agent"` |
| `timeout` | no | Seconds before canceling (600 for command, 30 for prompt, 60 for agent) |
| `statusMessage` | no | Custom spinner message |
| `once` | no | If `true`, runs only once per session |

## Exit Codes

- **Exit 0**: Success. Claude Code parses stdout for JSON output
- **Exit 2**: Blocking error. Stderr is fed back to Claude as error
- **Any other**: Non-blocking error. Stderr shown in verbose mode

## Hook Input (Common Fields via stdin JSON)

| Field | Description |
|---|---|
| `session_id` | Current session identifier |
| `transcript_path` | Path to conversation JSON |
| `cwd` | Current working directory |
| `permission_mode` | Current permission mode |
| `hook_event_name` | Name of the event |

## PreToolUse Decision Control

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "My reason here",
    "updatedInput": { "field_to_modify": "new value" },
    "additionalContext": "Extra context for Claude"
  }
}
```

## Async Hooks

Set `"async": true` to run in background without blocking. Only for `type: "command"`. Cannot block or return decisions.

## Example: Block Destructive Commands

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/block-rm.sh"
          }
        ]
      }
    ]
  }
}
```

```bash
#!/bin/bash
COMMAND=$(jq -r '.tool_input.command')
if echo "$COMMAND" | grep -q 'rm -rf'; then
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: "Destructive command blocked"
    }
  }'
else
  exit 0
fi
```
