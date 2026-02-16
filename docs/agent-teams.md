# Claude Code Agent Teams

> Experimental - enable with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`

Agent teams let you coordinate multiple Claude Code instances working together. One session acts as the team lead, coordinating work, assigning tasks, and synthesizing results.

## When to Use Agent Teams

Best for:
- **Research and review**: Multiple teammates investigate different aspects simultaneously
- **New modules or features**: Teammates each own a separate piece
- **Debugging with competing hypotheses**: Test different theories in parallel
- **Cross-layer coordination**: Changes spanning frontend, backend, tests

### Agent Teams vs Subagents

| | Subagents | Agent Teams |
|---|---|---|
| **Context** | Own context; results return to caller | Own context; fully independent |
| **Communication** | Report back to main agent only | Teammates message each other directly |
| **Coordination** | Main agent manages all work | Shared task list with self-coordination |
| **Best for** | Focused tasks where only result matters | Complex work requiring discussion |
| **Token cost** | Lower | Higher |

## Architecture

| Component | Role |
|---|---|
| **Team lead** | Main session that creates team, spawns teammates, coordinates |
| **Teammates** | Separate Claude Code instances working on assigned tasks |
| **Task list** | Shared list of work items |
| **Mailbox** | Messaging system for inter-agent communication |

## Display Modes
- **In-process**: All teammates run inside main terminal. Use Shift+Up/Down to select.
- **Split panes**: Each teammate gets own pane. Requires tmux or iTerm2.

## Delegate Mode
Restricts lead to coordination-only tools. Enable with Shift+Tab.

## Quality Gates with Hooks
- `TeammateIdle`: Runs when teammate about to go idle. Exit code 2 keeps them working.
- `TaskCompleted`: Runs when task being marked complete. Exit code 2 prevents completion.

## Best Practices
- Give teammates enough context in spawn prompt
- Size tasks appropriately (not too small, not too large)
- Wait for teammates to finish before proceeding
- Avoid file conflicts (each teammate owns different files)
- Monitor and steer progress
