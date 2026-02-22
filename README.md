# AI Scientist v3

Autonomous AI research agent. No Python orchestration — the agent IS the scientist.

## The Bitter Lesson Applied

v2 used ~5000 lines of Python to orchestrate a 4-stage BFS tree search with hardcoded stages, explicit node selection, LLM-evaluated completion criteria, and manual parallelism. v3 deletes all of that. Claude Code already is a tree search agent — it writes code, sees errors, fixes them, tries alternatives, remembers what worked.

| v2 (5000+ lines of Python) | v3 (markdown files) |
|---|---|
| `agent_manager.py` — orchestrator | Agent decides its own workflow |
| `parallel_agent.py` — BFS tree search | Agent's conversation = the search |
| `journal.py` — solution tree | Agent's memory = the journal |
| `stage_manager.py` — hardcoded 4 stages | No stages — agent uses judgment |
| `stage_evaluator.py` — LLM completion checks | Agent judges its own progress |
| `llm_gateway.py` — API routing | Claude Code handles models natively |
| `token_tracker.py` — usage tracking | `--max-budget-usd` flag |
| `agents/*.py` — Python wrappers | Skills (SKILL.md files) |
| `prompts/*.yaml` — prompt templates | Instructions in SKILL.md + CLAUDE.md |

## Quick Start

### Harbor Mode (Isolated Docker)

```bash
./run.sh idea.json                                                # Default: Opus 4.6, 2hr timeout
./run.sh idea.json --model anthropic/claude-sonnet-4-5-20250929   # Use Sonnet
./run.sh idea.json --timeout 7200                                 # 2hr timeout
./run.sh idea.json --gpus 1                                       # Local Docker with GPU
./run.sh idea.json --env modal --gpus 1                           # Modal cloud with GPU
./run.sh idea.json --env modal --gpus 1 --artifact-sync-interval 120
```

By default, `run.sh` uses a local patched Claude agent (via `--agent-import-path`) to
improve Modal reliability without modifying Harbor source code:
- picks the primary Claude session log even when subagent logs exist
- syncs artifacts to `/logs/agent/artifacts` and `/logs/verifier/artifacts` periodically
  and again on `TERM/EXIT` (critical for timeout cases)
- includes Claude session logs in artifacts (`claude_sessions/`), including subagent traces

Use `--use-upstream-agent` if you want Harbor's built-in `claude-code` agent behavior.

### Interactive Mode (No Docker)

```bash
cd ai_scientist_v3
claude
> Read idea.json and conduct this research
```

The `/search-papers` skill and `scripts/submit_for_review.sh` work against the local filesystem. No isolation — artifacts write directly to the repo directory.

## Architecture

```
ai_scientist_v3/
├── .claude/
│   ├── CLAUDE.md                           # Project context + conventions
│   └── skills/
│       ├── search-papers/                  # /search-papers — 3-API stack (S2, OpenReview, CrossRef)
│       │   ├── SKILL.md
│       │   └── reference.md               # Full API endpoint reference
│       └── review-paper/
│           ├── scripts/                    # LaTeX extraction + questions API
│           └── examples/                   # Fewshot calibration reviews
├── harbor-task/
│   ├── instruction.md.template             # Research prompt ({{IDEA_CONTENT}} placeholder)
│   ├── task.toml                           # Container config (CPU, memory, timeout)
│   ├── environment/
│   │   ├── Dockerfile.cpu                  # python:3.12-slim + LaTeX + scikit-learn
│   │   └── Dockerfile.gpu                  # pytorch + CUDA + LaTeX + scikit-learn
│   └── tests/test.sh                       # Verifier (checks artifacts, produces reward)
├── scripts/
│   ├── compile_latex.sh                   # pdflatex + bibtex + chktex
│   └── submit_for_review.sh              # External review API + versioned snapshot
├── blank_icbinb_latex/                     # ICLR 2025 workshop LaTeX template
└── docs/                                   # Claude Code documentation reference
```

## Harbor Runtime

Each experiment runs in an isolated Docker container via Harbor:

1. `run.sh <idea.json>` generates `instruction.md` from the `.template` with the idea injected
2. Harbor builds a Docker image from `Dockerfile.cpu` (slim) or `Dockerfile.gpu` (CUDA + PyTorch)
3. The agent (Claude Code) runs inside the container at `/app/`
4. On completion, `harbor-task/tests/test.sh` verifies all artifacts were produced
5. Results are collected in `jobs/<job-id>/` on the host

Source templates are never modified — `run.sh` generates `instruction.md` and `Dockerfile` at runtime and cleans them up on exit.

### Resuming a Timed-Out Run

```bash
./run.sh idea.json --resume-from jobs/2026-02-14__12-10-51/ --timeout 7200
```

This bakes the previous run's artifacts into the new container and injects a "Resumed Session" section so the agent continues rather than starts over.

### Sending Feedback

After reviewing a run's output, you can send feedback to steer the next run:

```bash
./run.sh idea.json --resume-from jobs/2026-02-14__12-10-51/ --feedback "The ablation study is missing a comparison without the temporal zoom component. Also add error bars to Figure 3."
```

The `--feedback` text is injected into the instruction as a "Feedback from Previous Run" section. The agent sees it at the start of the session and prioritizes addressing it. Combine with `--resume-from` so the agent builds on existing artifacts rather than starting over.

### GPU Support

`--gpus N` works with both local Docker and Modal:

```bash
# Local Docker — requires NVIDIA Container Toolkit
./run.sh idea.json --gpus 1

# Modal cloud
./run.sh idea.json --env modal --gpus 1
```

When `--gpus` is specified:
- `Dockerfile.gpu` is used instead of `Dockerfile.cpu` (base image: `pytorch/pytorch` with CUDA + PyTorch pre-installed)
- For local Docker, NVIDIA Container Toolkit must be installed ([install guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html))
- For Modal, GPUs are provisioned from the cloud — no local GPU required

The agent auto-detects GPU availability inside the container and adjusts experiments accordingly.

### Viewing Job Results

```bash
harbor view jobs
```

## How It Works

The agent receives a research idea and autonomously:

1. Uses `/search-papers` to find related work (Semantic Scholar, OpenReview, CrossRef)
2. Writes experiment code and runs it
3. Debugs failures, iterates on approach
4. Tests on multiple datasets with error bars
5. Runs ablation studies
6. Generates publication-quality plots
7. Writes a complete paper using the LaTeX template
8. Submits for external review via `scripts/submit_for_review.sh` (calls reviewer API, creates versioned snapshot)
9. Reads reviewer questions, iterates on experiments and paper, resubmits

No hardcoded stages. No tree data structure. No Python orchestration. The agent decides what to do and when, using its own scientific judgment.

## Environment

- `S2_API_KEY` (optional) — Semantic Scholar API key for higher rate limits
- `pdflatex` — Required for paper compilation (MacTeX: `/Library/TeX/texbin/pdflatex`)

## Documentation

`docs/` contains Claude Code reference docs:
- Skills, Subagents, Agent Teams, Hooks
- Memory/CLAUDE.md, CLI Reference, Agent SDK
- v2 analysis and migration notes
