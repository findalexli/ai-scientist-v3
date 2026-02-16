# AI Scientist v2 Analysis — What to Keep, What to Rethink

## Assets Carried Forward (unchanged)

### `blank_icbinb_latex/` — LaTeX Boilerplate
- 7 files: `template.tex`, `iclr2025.sty/.bst`, `natbib.sty`, `fancyhdr.sty`, `math_commands.tex`, `iclr2025.bib`
- `template.tex` is 150 lines with section markers like `%%%%%%%%%TITLE%%%%%%%%%` that get replaced
- Sections: Abstract, Introduction, Related Work, Background, Method, Experimental Setup, Experiments, Conclusion, Appendix
- `math_commands.tex` has 500+ notation shortcuts (vectors, matrices, probability, norms)
- Compilation: 3x `pdflatex` + `bibtex`, then `chktex` linting, then VLM review of compiled PDF
- **v3 note**: This template is fine as-is. The agent can work with it directly via Bash.

### `fewshot_examples/` — Review Few-Shot Examples
- 3 papers x 3 files each (PDF, JSON review, TXT extracted text)
- Papers: "Automated Relational" (Accept, 7/10), "Carpe Diem" (Reject, 4/10), "Attention Is All You Need" (Accept, 8/10)
- JSON format: 16 fields (Summary, Strengths, Weaknesses, Originality, Quality, Clarity, Significance, Questions, Limitations, Ethical Concerns, Soundness, Presentation, Contribution, Overall, Confidence, Decision)
- Used only in review phase via `get_review_fewshot_examples(num_fs_examples=1)`
- **v3 note**: These become part of a review skill's supporting files directory.

---

## Semantic Scholar API — Current Implementation & Gaps

### What Exists (v2)

Two duplicate implementations in `ai_scientist/tools/semantic_scholar.py`:

1. **`SemanticScholarSearchTool` class** (lines 19-98) — Used by IdeationAgent
   - Inherits from BaseTool, has `json_schema()`, `to_function_spec()`, `execute()`
   - Fields fetched: `title,authors,venue,year,abstract,citationCount`
   - Returns formatted string via `use_tool()`
   - **BUG**: Missing `citationStyles` field — incompatible with citation pipeline

2. **`search_for_papers()` function** (lines 101-138) — Used by writeup pipeline
   - Fields fetched: `title,authors,venue,year,abstract,citationStyles,citationCount`
   - Returns raw JSON list
   - Has `citationStyles` for BibTeX extraction
   - Manual `time.sleep(1.0)` rate limiting

### API Endpoint
```
https://api.semanticscholar.org/graph/v1/paper/search
```

### API Key
- Env var: `S2_API_KEY`
- With key: ~100 req/5 min
- Without: ~10 req/5 min (warning printed)
- Uses `@backoff.on_exception` for retry

### Citation Pipeline Workflow
1. LLM generates search query + description of what it needs
2. `search_for_papers()` hits API with `max_results=10`, sorted by `citationCount:desc`
3. LLM selects relevant papers from results
4. BibTeX extracted via `papers[i]["citationStyles"]["bibtex"]`
5. Citation keys cleaned (accents removed, lowercase)
6. Inserted into `\begin{filecontents}{references.bib}` in template
7. Up to 20 citation rounds per paper

### What's Wrong / Missing

**Bugs:**
- `SemanticScholarSearchTool` omits `citationStyles` — would crash if used for citations
- No validation that returned papers have required fields before accessing them

**Naive Search Strategy:**
- Simple keyword matching only
- No filtering by: publication date, venue quality, citation threshold, field of study
- Single query per round — no refinement if results are poor
- No deduplication across citation rounds

**Unused API Features:**
```
/paper/{paperId}                  # Full metadata, references, citations
/paper/batch                      # Batch lookup by paper IDs
/paper/{paperId}/references       # Papers this one cites
/paper/{paperId}/citations        # Papers citing this one
/paper/search/match-title         # AI-powered title matching (better than keyword)
```

**Missing Fields (available but not fetched):**
- `fieldsOfStudy` — topic classification for domain filtering
- `influentialCitationCount` — weighted by downstream impact
- `tldr` — AI-generated summaries (could replace manual abstract parsing)
- `publicationTypes` — Conference/Journal/Preprint distinction
- `openAccessPdf` — direct PDF URLs for verification

**Performance:**
- Potential 200-400 API calls per paper (20 rounds x 10-20 searches)
- No caching of search results
- No deduplication of previously seen papers

---

## v3 Improvement Opportunities

### Semantic Scholar — What We Can Do Better

**1. Unified, smarter search function:**
```python
# Instead of naive keyword search, compose better queries:
# - Add year range filter: &year=2020-2025
# - Add field filter: &fieldsOfStudy=Computer Science
# - Fetch richer fields: fieldsOfStudy,tldr,openAccessPdf,influentialCitationCount
# - Post-filter by citationCount > 10 for quality
```

**2. Result caching within a session:**
- Cache by query string to avoid duplicate API calls
- Cache by paperId to avoid re-fetching the same paper
- Deduplicate across citation rounds by title

**3. Use title-matching endpoint:**
- `/paper/search/match-title` for more precise lookups when we know what we're looking for
- Better than keyword search for finding specific papers

**4. In v3, the agent decides its own search strategy:**
- Instead of hardcoding "do 20 citation rounds with 10 results each"
- The agent can adaptively search: start broad, then narrow
- Can follow citation chains: find a key paper, then get its references
- Can search by author when a specific research group is relevant

**5. MCP server option:**
- Could wrap Semantic Scholar API as an MCP server for cleaner tool integration
- But direct `curl`/`python` via Bash is simpler and the agent can do it natively
- Recommendation: keep it as a helper script the agent can call, not a Python class

### LaTeX Pipeline — Let the Agent Own It

**Current v2 approach (hardcoded):**
```
copy template → gather citations → generate VLM descriptions →
LLM fills template → compile → chktex → VLM review →
reflection loop (3x) → figure optimization → page limit check
```

**v3 approach (agent-driven):**
- Agent gets the template, experiment results, and figures
- Agent decides how to structure the paper
- Agent compiles with `pdflatex`/`bibtex` via Bash
- Agent runs `chktex` and fixes issues itself
- Agent can view the compiled PDF (VLM capability built into Claude)
- Agent decides when it's done (no hardcoded reflection count)
- Hooks can enforce quality gates (page limit, compilation success)

### Review — Simplify with Skills

**Current v2:** Complex Python with `perform_review()`, fewshot loading, multi-round reflection
**v3:** A review skill that:
- Has fewshot examples as supporting files in the skill directory
- Reads the paper PDF directly (Claude's multimodal capability)
- Outputs structured JSON review
- No Python wrapper needed

---

## File Inventory — What Matters for v3

### Keep As-Is
- `blank_icbinb_latex/` — LaTeX template and style files
- `fewshot_examples/` — Review few-shot examples (move into review skill directory)

### Rethink for v3
- `tools/semantic_scholar.py` — Rewrite as a clean helper script or let agent use `curl` directly
- `perform_writeup.py` / `perform_icbinb_writeup.py` — Replace with writeup skill + agent autonomy
- `perform_llm_review.py` — Replace with review skill
- `perform_ideation_temp_free.py` — Replace with ideation skill
- `perform_plotting.py` — Replace with plotting skill

### Don't Need in v3
- `llm_gateway.py` — Claude Code handles model selection natively
- `llm.py`, `vlm.py` — Claude Code has built-in multimodal + LLM calling
- `backend/` — No need for API routing shims
- `token_tracker.py` — Use `--max-budget-usd` flag instead
- `agents/*.py` — These become Skills (SKILL.md files)
- `prompts/*.yaml` — Instructions move into SKILL.md files and CLAUDE.md
