# DataClaw Benchmark — Experiment Codebase

## Overview

Research into building a user-first coding agent benchmark from real Claude Code sessions
uploaded via the [DataClaw](https://github.com/peteromallet/dataclaw) tool.

## Data

All DataClaw datasets downloaded from HuggingFace into `dataclaw_datasets/`.

### Download Stats (March 2026)

| Dataset | Sessions | Notes |
|---|---|---|
| `peteromallet/dataclaw-peteromallet` | 549 | Primary; 14 projects; claude-opus-4-6 |
| `woctordho/dataclaw` | 208 | |
| `woctordho/dataclaw-windows` | 348 | Windows environment |
| `akenove/my-personal-codex-data` | 203 | Codex sessions |
| `GazTrab/dataclaw-GazTrab` | 97 | |
| `tillg/dataclaw-tillg` | 123 | |
| `zhiyaowang/dataclaw-zhiyaowang` | 73 | |
| `peteromallet/my-personal-codex-data` | 108 | Codex sessions |
| `Batman787/dataclaw-Batman787` | 6 | |
| `sunsun123new/dataclaw-sunsun123new` | 9 | |
| `vaynelee/dataclaw-vaynelee` | 21 | |
| `parani01/dataclaw-parani01` | 5 | |
| `GolienHzmsr/dataclaw-GolienHzmsr` | 1 | |
| `DJTRIXUK/dataclaw-DJTRIXUK` | 2 | |
| `xuechengjiang/my-personal-codex-data` | 19 | |
| **Total (deduplicated)** | **~1,880** | After deduping identical forks |

26 datasets downloaded total; 8 are exact forks of peteromallet canonical (same 549 sessions).
3 codex datasets share identical content (108 sessions each, counted once).

### Session Format

Each session in `conversations.jsonl`:
```json
{
  "session_id": "...",
  "model": "claude-opus-4-5-20251101",
  "git_branch": "...",
  "start_time": "2026-01-19T10:19:51.792Z",
  "end_time": "...",
  "project": "...",
  "stats": {
    "user_messages": 2,
    "assistant_messages": 8,
    "tool_uses": 2,
    "input_tokens": 153370,
    "output_tokens": 32
  },
  "messages": [
    {"role": "user", "content": "...", "timestamp": "..."},
    {"role": "assistant", "content": "...", "timestamp": "..."}
  ]
}
```

## Research Goal

Build a **user-first** coding agent benchmark that captures:
1. Multi-turn correction loops (not single-shot pass/fail)
2. User satisfaction signals (follow-ups, rephrasing, abandonment)
3. Realistic task distribution from real sessions
4. Turn efficiency as the core metric (turns-to-acceptance)

## Scripts

- `download_dataclaw.py` — Download all DataClaw datasets from HuggingFace
