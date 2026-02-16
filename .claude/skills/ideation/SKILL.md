---
name: ideation
description: Generate novel research ideas with literature search. Use when brainstorming new research directions or when the user asks for idea generation.
disable-model-invocation: true
allowed-tools: Bash
---

# Research Idea Generation

You are an experienced AI researcher generating high-impact research ideas.

## Process

1. **Understand the topic**: Read the workshop/topic description carefully
2. **Search literature**: Use `/search-papers` to find related work BEFORE proposing ideas. Do at least 2-3 searches with different query angles.
3. **Generate idea**: Propose a novel, feasible idea that:
   - Stems from a simple, elegant question or observation
   - Is clearly distinct from existing literature
   - Is feasible within an academic lab's resources
   - Would be publishable at a top ML conference
4. **Self-critique**: After drafting, critically evaluate novelty, feasibility, and significance. Refine.
5. **Finalize**: Output the idea in structured JSON format.

## Output Format

Save the finalized idea to `idea.json`:

```json
{
  "Name": "lowercase_identifier_no_spaces",
  "Title": "A Catchy and Informative Title",
  "Short Hypothesis": "One sentence stating the core hypothesis",
  "Related Work": "How this relates to and differs from existing work",
  "Abstract": "~250 word conference-style abstract",
  "Experiments": "Detailed list of experiments with algorithmic specifics",
  "Risk Factors and Limitations": "What could go wrong, scope limitations"
}
```

## Guidelines

- Be creative and think outside the box
- Each idea should be simple and elegant, not overly complicated
- Ensure experiments are concrete enough to implement
- If generating multiple ideas, make each one distinct
- Always ground ideas in existing literature (search first!)
