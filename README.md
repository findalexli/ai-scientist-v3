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

```bash
cd ai_scientist_v3

# Interactive mode
claude --agent ai-scientist
> Here's my research idea: [paste idea.json contents]

# Headless mode
claude --agent ai-scientist -p "Run experiments for this idea: $(cat idea.json)" \
  --max-budget-usd 10
```

## Architecture

```
ai_scientist_v3/
├── .claude/
│   ├── CLAUDE.md                           # Project context + conventions
│   ├── settings.json                       # Stop hook (completeness check)
│   ├── agents/
│   │   └── ai-scientist.md                # Main agent (--agent ai-scientist)
│   └── skills/
│       ├── ideation/SKILL.md              # /ideation — generate research ideas
│       ├── run-experiment/SKILL.md        # /run-experiment — write & execute code
│       ├── plot-results/SKILL.md          # /plot-results — publication plots
│       ├── write-paper/SKILL.md           # /write-paper — fill LaTeX template
│       ├── review-paper/SKILL.md          # /review-paper — structured review
│       └── search-papers/SKILL.md         # /search-papers — Semantic Scholar API
├── scripts/
│   └── compile_latex.sh                    # pdflatex + bibtex + chktex
├── blank_icbinb_latex/                     # ICLR 2025 workshop LaTeX template
├── fewshot_examples/                       # Example reviews for calibration
└── docs/                                   # Claude Code documentation reference
```

## Harbor Runtime

Each experiment runs in an isolated Docker container via Harbor:

1. `run.sh <idea.json>` generates `instruction.md` from the `.template` with the idea injected
2. Harbor builds a Docker image from `Dockerfile.cpu` (slim) or `Dockerfile.gpu` (CUDA + PyTorch)
3. The agent (Claude Code) runs inside the container at `/app/`
4. For GPU runs, `--override-gpus` attaches GPUs via Modal
5. Results are collected in `jobs/<job-id>/` on the host

Source templates are never modified — `run.sh` generates `instruction.md` and `Dockerfile` at runtime and cleans them up on exit.

## How It Works

The agent receives a research idea and autonomously:

1. Searches literature for related work
2. Writes experiment code and runs it
3. Debugs failures, iterates on approach
4. Tests on multiple datasets with error bars
5. Runs ablation studies
6. Generates publication-quality plots
7. Writes a complete paper using the LaTeX template
8. Reviews its own paper
9. A Stop hook prevents quitting before all steps are done

No hardcoded stages. No tree data structure. No Python orchestration. The agent decides what to do and when, using its own scientific judgment.

## Environment

- `S2_API_KEY` (optional) — Semantic Scholar API key for higher rate limits
- `pdflatex` — Required for paper compilation (MacTeX: `/Library/TeX/texbin/pdflatex`)

## Documentation

`docs/` contains downloaded Claude Code reference docs:
- Skills, Subagents, Agent Teams, Hooks
- Memory/CLAUDE.md, CLI Reference, Agent SDK
- v2 analysis and migration notes
