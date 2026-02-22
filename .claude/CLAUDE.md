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

## Research Process

1. **Literature Review** — Use `/search-papers` to find related work. Understand the state of the art. **For the 3-5 most relevant papers, read the full text** — don't rely solely on abstracts. Download PDFs to `literature/` and read them with the `Read` tool (use `pages` parameter for long papers), or use `WebFetch` on HTML versions. Record key takeaways in `literature/README.md`. The `/search-papers` skill documents how to obtain full text for any paper. **When a paper has public code** (GitHub link in the paper, or search GitHub/Papers With Code), **clone it into `experiment_codebase/`** to study the implementation — don't just read the PDF. Literature search is not a one-time step — revisit it throughout the research process. Search again after getting experiment results (to contextualize findings), when the reviewer raises gaps, when you discover unexpected behavior, or when you need to strengthen a claim. Aim for 15-30 citations in the final paper.
2. **Experiment Design** — Set up experiments by building on existing code whenever possible. If the idea has a `"Code References"` field, clone those repos or download those files first. Check repos cloned during literature review for reusable baselines. Search GitHub for existing implementations of methods in the idea. Clone repos and download files into `experiment_codebase/`. Only write code from scratch when no suitable existing implementation is available. Install packages, download datasets.
3. **Run Experiments** — Use your best judgment on methodology: baselines, ablations, statistical rigor appropriate to the claims. Run multiple random seeds for error bars.
4. **Plot Results** — Create publication-quality figures in `figures/`. Visually inspect each PNG with the `Read` tool before finalizing.
5. **Write Paper** — Fill in `latex/template.tex`. Compile with `bash scripts/compile_latex.sh latex/`. Must be 4 pages of main text (excluding references and appendix). After compilation, visually inspect the PDF with the `Read` tool to catch formatting issues.
6. **Submit for Review** — Run the external reviewer:
   ```bash
   bash scripts/submit_for_review.sh latex/template.tex
   ```
   This calls the external reviewer API, saves the response, and creates a versioned snapshot in `submissions/v{N}_{timestamp}/`. Use `timeout: 180000` (3 minutes) for the Bash tool call since the API takes ~30 seconds.
7. **Read Reviewer Feedback** — Read the reviewer's questions from `submissions/v{N}_{timestamp}/reviewer_communications/response.json` (path printed by the script). The response contains a `question` field.
8. **Continue Iterate, autonomously** — Address the reviewer's questions and weaknesses:
   - Run additional experiments if needed
   - Search for additional literature with `/search-papers` to contextualize new results or address gaps
   - Improve the paper, recompile, and visually inspect the PDF again, including the appendix
   - **Write your rebuttal** back into the same `response.json` by adding a `"rebuttal"` field explaining what you changed and why. This creates a record of the conversation with the reviewer.
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
3. Test on multiple datasets (2-3 minimum, prefer HuggingFace)
4. Include baselines for comparison
5. Run multiple random seeds for error bars
6. Do ablation studies to understand component contributions
7. Report results truthfully — negative results are valuable

### File Conventions
- Research ideas: `idea.json` (structured JSON with Name, Title, Hypothesis, etc.). May include optional `"Code References"`: list of `{url, files?, notes}` for repos/files to clone or download.
- Experiment code: `experiment_codebase/experiment_*.py` (self-contained, set random seeds, print key metrics during execution so logs capture them)
- Metrics: `experiment_codebase/*_results.npy` (or `.csv`, `.json`, `.pt` — any standard format)
- Plots: `figures/*.png` (publication quality, max 12, 150+ DPI, `bbox_inches='tight'`, colorblind-friendly palettes, no underscores in labels, error bars when multiple runs exist, visually inspect each PNG with `Read` tool before finalizing)
- Paper: `latex/template.tex` → compiled to PDF
- Review: `review.json` (structured NeurIPS format)
- Versioned snapshots: `submissions/v{N}_{timestamp}/` (created by `submit_for_review.sh`)
- Version history: `submissions/version_log.json`

### Experiment Guidelines
- Use `uv pip install --system` (preferred over pip — faster)
- `git clone` existing implementations for baselines rather than writing from scratch. For specific files, use `curl -L https://raw.githubusercontent.com/Owner/Repo/main/path/file.py -o experiment_codebase/file.py`
- Explore cloned repos before writing code — read their README and key scripts, then build on them
- Check GPU/RAM availability and design experiments accordingly
- Prefer faster iterations over one long run
- Self-contained scripts: each experiment file should run independently

### Paper Writing
- Copy `blank_icbinb_latex/` to `latex/` to start
- Template has `%%%%%%%%%TITLE%%%%%%%%%` markers with placeholder text — replace ALL of them
- Compile with: `bash scripts/compile_latex.sh latex/`
- **CRITICAL**: BibTeX entries go inside `\begin{filecontents}{references.bib}...\end{filecontents}` in `template.tex`. The `\bibliography{}` argument MUST match `references` — if it says `iclr2025`, change it to `references`. Mismatched names cause all citations to render as **?**.
- Use `/search-papers` to find papers, get BibTeX from S2 `citationStyles` field or CrossRef `dx.doi.org`.
- Clean citation keys: lowercase, no accents, no special characters

### Quality Standards
- Papers must compile without errors
- 4-page limit for main text (excluding references and appendix)
- All figures referenced in text must exist
- Citations must have valid BibTeX entries
- Results must be real — never hallucinate numbers
- Publication-quality plots (labeled axes, legends, readable fonts)
- At least one submission through `scripts/submit_for_review.sh` with reviewer feedback addressed
- Experimental rigor appropriate to the claims (proper baselines, controls, statistical tests as needed)
