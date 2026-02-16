# Section Writing Guide

## Title
- Should be catchy and informative
- Keep under 2 lines
- Should convey the core insight or finding

## Abstract (~250 words)
- Start with the challenge or pitfall being explored
- Motivate why this matters for real-world deployment
- Summarize key findings (even if negative/inconclusive)
- Must be continuous prose (no bullet points)

## Introduction
- Set up the problem and why it matters
- Provide context from the broader field
- Clearly state your research question
- Summarize contributions and findings
- Negative results are valuable — frame them as learning

## Related Work
- Group by theme, not chronologically
- Compare and contrast with your approach
- Use `\citep{}` for parenthetical citations: "... has been studied \citep{smith2023}"
- Use `\citet{}` for textual: "\citet{smith2023} showed that..."
- Don't just list papers — explain relationships

## Method / Problem Discussion
- Describe your approach clearly enough to reproduce
- Use math notation from `math_commands.tex` when appropriate
- Include algorithm pseudocode if helpful
- Be honest about simplifications and assumptions

## Experimental Setup
- Datasets: name, size, source, preprocessing
- Baselines: what you compare against and why
- Metrics: what you measure and why it's the right metric
- Hyperparameters: learning rate, batch size, epochs, etc.
- Hardware: GPU type, training time

## Experiments
- Present results truthfully — negative results are OK
- Reference ALL figures: "As shown in Figure \ref{fig:main}"
- Include error bars from multiple seeds
- Discuss what the results mean, not just what they are
- If something didn't work, explain why

## Conclusion
- Summarize the key takeaway
- Acknowledge limitations honestly
- Suggest concrete future directions
- Don't overstate findings

## Common LaTeX Mistakes to Avoid
- Missing `$` around math: `$\alpha$` not `\alpha`
- Unescaped special chars: `\%`, `\&`, `\#`
- Figure not found: ensure path matches `\graphicspath`
- Bibliography not compiling: run bibtex between pdflatex passes
- Orphaned references: every `\ref{}` needs a matching `\label{}`
