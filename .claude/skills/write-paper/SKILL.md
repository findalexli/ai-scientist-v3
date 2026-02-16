---
name: write-paper
description: Write a complete research paper by filling the LaTeX template with experiment results. Use after experiments and plots are complete.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Paper Writing

Write a complete research paper using the ICBINB (I Can't Believe It's Not Better) workshop LaTeX template.

## Process

1. **Setup**: Copy `blank_icbinb_latex/` to `latex/`
2. **Gather citations**: Use `/search-papers` to find relevant papers, collect BibTeX entries
3. **Add citations**: Insert BibTeX entries into `\begin{filecontents}{references.bib}` in `template.tex`
4. **Write content**: Replace all section placeholders with actual content
5. **Include figures**: Reference plots from `figures/` using `\includegraphics`
6. **Compile**: Run `scripts/compile_latex.sh latex/`
7. **Fix errors**: Read compilation output, fix LaTeX issues
8. **Review quality**: Read the compiled PDF, check for issues
9. **Iterate**: Refine writing, fix formatting, re-compile

## Template Structure

The template has section markers like `%%%%%%%%%TITLE%%%%%%%%%` with placeholder text. Replace ALL placeholders:

| Section | Content |
|---------|---------|
| Title | Catchy, informative (<2 lines) |
| Abstract | 1 paragraph: challenge explored, motivation, key findings |
| Introduction | Problem overview, why it matters, contributions |
| Related Work | Literature with citations |
| Background | Technical background (optional) |
| Method | Problem discussion or methodology |
| Experimental Setup | Configuration for reproducibility |
| Experiments | Results with figures and analysis |
| Conclusion | Key lessons, future directions |
| Appendix | Supplementary material, additional plots |

## Writing Guidelines

- **4-page limit** for main text (excluding references and appendix)
- **Truthful reporting**: Never hallucinate results. Use actual numbers from experiments.
- **Cite properly**: Use `\citep{}` for parenthetical and `\citet{}` for textual citations
- **Figure references**: Use `\ref{fig:label}` — make sure labels match
- **Minimize lists**: Use flowing prose, not bullet points
- **LaTeX quality**: Avoid common errors (unescaped %, &, missing $, etc.)
- Refer to @examples/section-guide.md for detailed section guidance

## Citation Workflow

1. Think about what citations you need (background, related work, methods, datasets)
2. For each: run `/search-papers "query"` to find papers
3. Copy BibTeX entries from results
4. Add to the `\begin{filecontents}{references.bib}` block in `template.tex`
5. Clean citation keys: lowercase, no accents, no special characters
6. Aim for 15-30 citations total

**CRITICAL**: The template uses `\bibliography{references}` to read from `references.bib`. All BibTeX entries MUST go inside the `\begin{filecontents}{references.bib}...\end{filecontents}` block. If `\bibliography{}` points to a different file (e.g., `iclr2025`), change it to `\bibliography{references}`. Mismatched filenames cause all citations to render as **?**.

## Compilation

```bash
bash scripts/compile_latex.sh latex/
```

If compilation fails, read the error output and fix the LaTeX source. Common fixes:
- Escape special characters: `%`, `&`, `#`, `$`
- Fix unmatched braces
- Remove invalid `\ref{}` to non-existent labels
- Ensure all `\includegraphics` files exist in `figures/`
