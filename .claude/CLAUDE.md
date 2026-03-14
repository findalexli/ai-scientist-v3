# AI Scientist v3

Autonomous AI research platform. The agent conducts ML research end-to-end: literature review, experimentation, plotting, paper writing, and review.

## Workspace

- `experiment_codebase/` — Experiment code, cloned repos, and results
- `figures/` — Publication-quality plots
- `latex/` — ICLR 2025 workshop template (fill in `template.tex`)
- `literature/` — Downloaded papers and reading notes (see `literature/README.md` for index)
- `submissions/` — Versioned snapshots (created by `submit_for_review.sh`)
- `scripts/compile_latex.sh` — Compile paper: `bash scripts/compile_latex.sh latex/`
- `scripts/submit_for_review.sh` — Submit for external review + create versioned snapshot
- `blank_icbinb_latex/` — Clean LaTeX template (copy to `latex/` to start)
- `/search-papers` — Skill for finding related work, getting BibTeX, checking novelty

Package installation: `uv pip install --system` (preferred — faster), `pip install`, `apt-get install`
Datasets: HuggingFace (`huggingface-cli download` or `datasets` library), Kaggle, UCI ML repo, OpenML, or any public source

API keys (via environment variables, if configured):
- `S2_API_KEY` — Semantic Scholar (higher rate limits)
- `OPENALEX_API_KEY` — OpenAlex (PDF downloads, expanded searc for papers that Arxiv could not directly download)
- `HF_TOKEN` — HuggingFace (gated models/datasets)
- `KAGGLE_USERNAME` / `KAGGLE_KEY` — Kaggle API
- `OPENAI_API_KEY` — Codex CLI (ensemble reviewer mode)
- `GEMINI_API_KEY` / `GOOGLE_API_KEY` — Gemini CLI (ensemble reviewer mode)

Reviewer configuration:
- `REVIEWER_MODE` — `ensemble` (default, 3 parallel reviewers), `subagent` (single reviewer), or `api` (external API)
- `REVIEWER_TIMEOUT` — Per-reviewer timeout in seconds (default: `1800` = 30 min)
- `CLAUDE_REVIEWER_MODEL` — Model for Claude reviewer in ensemble mode (default: agent .md setting, currently `opus`). Example: `claude-sonnet-4-5-20250929`
- `CODEX_MODEL` — Model for Codex CLI in ensemble mode (default: Codex CLI's own default)
- `GEMINI_MODEL` — Model for Gemini CLI in ensemble mode (default: `auto`)

## Research Process

1. **Literature Review** — Use `/search-papers` to find related work. Read the full text of the most relevant papers (not just abstracts). Clone public code into `experiment_codebase/cloned_repos/`. Revisit literature throughout the research process, not just at the start.
2. **Experiment Design** — Build on existing code whenever possible. Search GitHub and Papers With Code for implementations before writing from scratch.
3. **Run Experiments** — Use your best judgment on methodology: baselines, ablations, rigor appropriate to the claims.
4. **Plot Results** — Create publication-quality figures in `figures/`. Visually inspect each PNG with the `Read` tool before finalizing.
5. **Write Paper** — Fill in `latex/template.tex`. Compile with `bash scripts/compile_latex.sh latex/`. Must be 4 pages of main text (excluding references and appendix). After compilation, visually inspect the PDF with the `Read` tool to catch formatting issues.
6. **Submit for Review** — Run the reviewer (ensemble mode, 3 parallel reviewers):
   ```bash
   bash scripts/submit_for_review.sh latex/template.tex
   ```
   This generates 3 reviews (comprehensive, idea/literature, code quality), saves them, and creates a versioned snapshot in `submissions/v{N}_{timestamp}/`. Use `timeout: 600000` (10 minutes) for the Bash tool call. Do NOT override `REVIEWER_MODE` — the default ensemble mode is correct.
7. **Read Reviewer Feedback** — Read the reviewer's feedback from `submissions/v{N}_{timestamp}/reviewer_communications/response.md` (path printed by the script). The file contains three `## Review (...)` sections — one per reviewer.
8. **Continue Iterate, autonomously** — Address the reviewer's questions and weaknesses:
   - Run additional experiments if needed
   - Search for additional literature with `/search-papers` to contextualize new results or address gaps
   - Improve the paper, recompile, and visually inspect the PDF again, including the appendix
   - **Write your rebuttal** by appending a `## Rebuttal` section to the same `response.md` file, explaining what you changed and why. This creates a record of the conversation with the reviewer.
   - Resubmit with `bash scripts/submit_for_review.sh latex/template.tex`
   - Repeat until the reviewer's questions are satisfactorily addressed


## Version Management

- **Version numbers are managed automatically** by `submit_for_review.sh` — never create version numbers manually
- Each call creates `submissions/v{N}_{timestamp}/` with a frozen copy of the paper, experiments, figures, and reviewer feedback
- The working directories (`latex/`, `experiment_codebase/`, `figures/`) remain mutable — always edit there, never in `submissions/`
- To see version history: read `submissions/version_log.json`
- To compare with previous versions: read `submissions/v{N}_{timestamp}/paper.tex`

## Research Conventions

### Scientific Method
1. Observe → Hypothesize → Experiment → Analyze → Iterate
2. Always search literature before claiming novelty
3. Include baselines for comparison
4. Use multiple runs/seeds when appropriate
5. Report results truthfully — negative results are valuable

### Experiment Codebase Organization

Keep `experiment_codebase/` organized however makes sense for your project. A common layout:

```
experiment_codebase/
    README.md               # Experiment log — what you ran, what you found
    cloned_repos/           # Third-party code (git-cloned repos, reference implementations)
```

Keep code next to its results. Put third-party code in `cloned_repos/`. Maintain a `README.md` as a running log of what you ran and what you found.

### File Conventions
- Research ideas: `idea.json`
- Plots: `figures/*.png` — visually inspect each PNG with `Read` tool before finalizing
- Paper: `latex/template.tex` → compiled to PDF
- Versioned snapshots: `submissions/v{N}_{timestamp}/` (created by `submit_for_review.sh`)

### Experiment Guidelines
- Use `uv pip install --system` (preferred over pip)
- Clone existing implementations before writing from scratch
- Prefer faster iterations over one long run

### Paper Writing
- Copy `blank_icbinb_latex/` to `latex/` to start
- Template has `%%%%%%%%%TITLE%%%%%%%%%` markers with placeholder text — replace ALL of them
- Compile with: `bash scripts/compile_latex.sh latex/`
- **CRITICAL**: BibTeX entries go inside `\begin{filecontents}{references.bib}...\end{filecontents}` in `template.tex`. The `\bibliography{}` argument MUST match `references` — if it says `iclr2025`, change it to `references`. Mismatched names cause all citations to render as **?**.
- Use `/search-papers` to find papers, get BibTeX from S2 `citationStyles` field or CrossRef `dx.doi.org`.
- Clean citation keys: lowercase, no accents, no special characters

### Quality Standards
- Papers must compile without errors
- All figures referenced in text must exist
- Citations must have valid BibTeX entries
- Results must be real — never hallucinate numbers
- Publication-quality plots (labeled axes, legends, readable fonts)
- At least one submission through `scripts/submit_for_review.sh` with reviewer feedback addressed
- Experimental rigor appropriate to the claims (proper baselines, controls, statistical tests as needed)
