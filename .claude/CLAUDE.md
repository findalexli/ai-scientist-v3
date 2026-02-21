# AI Scientist v3

This is an autonomous AI research platform. The agent conducts ML research end-to-end: ideation, experimentation, plotting, paper writing, and review.

## Runtime: Harbor

Each experiment runs in an isolated Docker container via [Harbor](https://github.com/ai-dock/harbor). This gives full filesystem isolation, reproducible environments, and built-in artifact collection.

### How It Works

1. `run.sh <idea.json>` generates `harbor-task/instruction.md` from the `.template` with the idea injected
2. Harbor builds a Docker image from `harbor-task/environment/Dockerfile` (Python + LaTeX + ML deps)
3. The agent (Claude Code) runs inside the container at `/app/`
4. On completion, `harbor-task/tests/test.sh` verifies all artifacts were produced
5. Results are collected in `jobs/<job-id>/` on the host

### Running an Experiment

```bash
./run.sh idea.json                                                # Default: Opus 4.6, 2hr timeout
./run.sh idea.json --model anthropic/claude-sonnet-4-5-20250929   # Use Sonnet
./run.sh idea.json --timeout 7200                                 # 2hr timeout
```

### Resuming a Timed-Out Run

If a run times out or you want to continue from previous artifacts:

```bash
./run.sh idea.json --resume-from jobs/2026-02-14__12-10-51/ --timeout 7200
```

This bakes the previous run's artifacts (experiments, plots, paper, review) into the new container and injects a "Resumed Session" section into the instruction so the agent knows to continue rather than start over. You can pass either a job directory or a trial directory.

### Interactive Mode (No Docker)

You can also run Claude Code directly without Harbor for interactive research:

```bash
cd ai_scientist_v3
claude
```

The `/search-papers` skill and `scripts/submit_for_review.sh` work against the local filesystem. No isolation — artifacts write directly to the repo directory.

## Project Structure

- `blank_icbinb_latex/` — LaTeX template for ICBINB workshop papers (ICLR 2025 format)
- `fewshot_examples/` — Example paper reviews for calibrating the review skill
- `scripts/` — Helper scripts:
  - `compile_latex.sh` — LaTeX compilation (pdflatex + bibtex + chktex)
  - `submit_for_review.sh` — Submit paper to external reviewer model + create versioned snapshot
- `harbor-task/` — Harbor task definition:
  - `instruction.md.template` — Research prompt template (`{{IDEA_CONTENT}}` placeholder)
  - `instruction.md` — Generated at runtime by `run.sh` (not checked in)
  - `task.toml` — Container config (CPU, memory, timeout, artifacts)
  - `environment/Dockerfile.cpu` — `python:3.12-slim` + LaTeX + scikit-learn (local Docker)
  - `environment/Dockerfile.gpu` — `pytorch/pytorch` + CUDA + LaTeX + scikit-learn (Modal GPU)
  - `environment/Dockerfile` — Generated at runtime from .cpu or .gpu (not checked in)
  - `tests/test.sh` — Completeness verifier (checks for experiments, plots, paper, review)
- `run.sh` — Convenience wrapper for `harbor run`

## Environment

Inside the Harbor container, the workspace is at `/app/`:
- `/app/experiment_results/` — Experiment scripts and .npy results
- `/app/figures/` — Publication-quality plots
- `/app/latex/` — Pre-filled ICLR 2025 template
- `/app/scripts/` — compile_latex.sh
- `/app/fewshot_examples/` — Review calibration examples
- `/app/submissions/` — Versioned snapshots (created by `submit_for_review.sh`)

For local development outside Harbor:
- Load API keys from `.env` in the project root: `source .env` (or `set -a; source .env; set +a`)
- `S2_API_KEY` — Semantic Scholar API key (optional, for higher rate limits)
- pdflatex available at `/Library/TeX/texbin/pdflatex` if not on PATH

## Artifact Collection

Harbor only mounts two paths from the container to the host:
- `/logs/agent/` → `<trial>/agent/` (bind-mounted in Docker, synced in Modal)
- `/logs/verifier/` → `<trial>/verifier/` (bind-mounted in Docker, synced in Modal)

**Do NOT write to `/logs/artifacts/` or any other `/logs/` subpath** — they are ephemeral.

The agent is instructed to save incrementally after each milestone (experiments, plots, paper, review) — not just at the end. On timeout, the verifier also copies whatever exists. Run the following to save:
```bash
mkdir -p /logs/agent/artifacts
cp -r experiment_results/ /logs/agent/artifacts/
cp -r figures/ /logs/agent/artifacts/
cp latex/template.pdf /logs/agent/artifacts/paper.pdf
cp latex/template.tex /logs/agent/artifacts/paper.tex
cp latex/references.bib /logs/agent/artifacts/references.bib 2>/dev/null
cp review.json /logs/agent/artifacts/
cp -r submissions/ /logs/agent/artifacts/submissions/ 2>/dev/null
```

These persist to `jobs/<job-id>/<trial>/agent/artifacts/` on the host. The verifier (`test.sh`) also copies artifacts to both `agent/artifacts/` and `verifier/artifacts/` as a safety net.

## Research Conventions

### Scientific Method
1. Observe → Hypothesize → Experiment → Analyze → Iterate
2. Always search literature before claiming novelty
3. Test on multiple datasets (2-3 minimum, prefer HuggingFace)
4. Include baselines for comparison
5. Run multiple random seeds for error bars
6. Do ablation studies to understand component contributions
7. Report results truthfully — negative results are valuable

### File Conventions
- Research ideas: `idea.json` (structured JSON with Name, Title, Hypothesis, etc.)
- Experiment code: `experiment_results/experiment_*.py` (self-contained, set random seeds, print key metrics during execution so logs capture them)
- Metrics: `experiment_results/*_results.npy` (or `.csv`, `.json`, `.pt` — any standard format)
- Plots: `figures/*.png` (publication quality, max 12, 150+ DPI, `bbox_inches='tight'`, colorblind-friendly palettes, no underscores in labels, error bars when multiple runs exist, visually inspect each PNG with `Read` tool before finalizing)
- Paper: `latex/template.tex` → compiled to PDF
- Review: `review.json` (structured NeurIPS format)
- Versioned snapshots: `submissions/v{N}_{timestamp}/` (created by `submit_for_review.sh`)
- Version history: `submissions/version_log.json`

### Experiment Guidelines
- Use `uv pip install --system` (preferred over pip — faster)
- `git clone` existing implementations for baselines rather than writing from scratch
- Check GPU/RAM availability and design experiments accordingly
- The container has a finite runtime — prefer faster iterations over one long run

### Paper Writing
- Copy `blank_icbinb_latex/` to `latex/` to start
- Template has `%%%%%%%%%TITLE%%%%%%%%%` markers with placeholder text — replace ALL of them
- Compile with: `bash scripts/compile_latex.sh latex/`
- **CRITICAL**: BibTeX entries go inside `\begin{filecontents}{references.bib}...\end{filecontents}` in `template.tex`. The `\bibliography{}` argument MUST match `references` — if it says `iclr2025`, change it to `references`. Mismatched names cause all citations to render as **?**.
- Use `/search-papers` to find papers, get BibTeX from S2 `citationStyles` field or CrossRef `dx.doi.org`. Aim for 15-30 citations.
- Clean citation keys: lowercase, no accents, no special characters

### Quality Standards
- Papers must compile without errors
- 4-page limit for main text (excluding references and appendix)
- All figures referenced in text must exist
- Citations must have valid BibTeX entries
- Results must be real — never hallucinate numbers
