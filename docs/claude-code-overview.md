# Claude Code Overview

Claude Code is an agentic coding tool that reads your codebase, edits files, runs commands, and integrates with development tools. Available in terminal, IDE, desktop app, and browser.

## Key Capabilities

- **Automate tedious tasks**: Write tests, fix lint errors, resolve merge conflicts, update dependencies, write release notes
- **Build features and fix bugs**: Describe what you want in plain language. Claude plans, writes code across multiple files, verifies it works
- **Create commits and pull requests**: Works directly with git - stages changes, writes commit messages, creates branches, opens PRs
- **Connect tools with MCP**: Model Context Protocol connects to external data sources (Google Drive, Jira, Slack, custom tooling)
- **Customize with instructions, skills, and hooks**: CLAUDE.md for coding standards, custom slash commands for repeatable workflows, hooks for automation
- **Run agent teams and build custom agents**: Spawn multiple agents working on different parts simultaneously, or build custom agents with the Agent SDK
- **Pipe, script, and automate with CLI**: Composable, follows Unix philosophy - pipe logs, run in CI, chain with other tools

## Environments

| Environment | Description |
|---|---|
| Terminal | Full-featured CLI for working directly in terminal |
| VS Code | Extension with inline diffs, @-mentions, plan review, conversation history |
| JetBrains | Plugin for IntelliJ, PyCharm, WebStorm with interactive diff viewing |
| Desktop App | Standalone app for running outside IDE/terminal |
| Web | Browser-based, no local setup needed |

## Architecture

Claude Code uses the same underlying engine across all surfaces. CLAUDE.md files, settings, and MCP servers work across all environments.

### Key Integrations
- **GitHub Actions / GitLab CI/CD**: Automate PR reviews and issue triage
- **Slack**: Route bug reports to pull requests
- **Chrome**: Debug live web applications
- **Agent SDK**: Build custom agents for your own workflows

## Installation

```bash
# macOS, Linux, WSL
curl -fsSL https://claude.ai/install.sh | bash

# Then start in any project
cd your-project
claude
```

## Next Steps
- Quickstart: Walk through first real task
- Best practices and common workflows
- Settings customization
- Troubleshooting
