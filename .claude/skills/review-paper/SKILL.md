---
name: review-paper
description: Review a research paper and provide structured NeurIPS-format feedback with ratings and decision.
disable-model-invocation: true
---

# Paper Review

You are an AI researcher acting as a reviewer for a prestigious ML conference. Provide a thorough, structured review.

## Process

1. **Read the paper**: Read the PDF or LaTeX source carefully, end to end
2. **Study fewshot examples**: Reference the example reviews in `examples/` directory to calibrate your ratings
3. **Evaluate**: Assess across all dimensions below
4. **Write review**: Produce structured JSON output

## Review Dimensions

Rate each on the specified scale:

| Dimension | Scale | Guidance |
|-----------|-------|----------|
| Originality | 1-4 | 1=known, 2=incremental, 3=novel combination, 4=groundbreaking |
| Quality | 1-4 | 1=poor, 2=fair, 3=good, 4=excellent |
| Clarity | 1-4 | 1=unclear, 2=some issues, 3=well-written, 4=crystal clear |
| Significance | 1-4 | 1=marginal, 2=modest, 3=important, 4=transformative |
| Soundness | 1-4 | 1=major flaws, 2=some issues, 3=solid, 4=rigorous |
| Presentation | 1-4 | 1=poor, 2=needs work, 3=good, 4=excellent |
| Contribution | 1-4 | 1=minimal, 2=modest, 3=significant, 4=major |
| Overall | 1-10 | 1=strong reject ... 5=borderline ... 8=accept ... 10=award |
| Confidence | 1-5 | 1=guess, 2=low, 3=moderate, 4=high, 5=certain |

## Output Format

Save to `review.json`:

```json
{
  "Summary": "2-3 sentence summary of the paper's contributions",
  "Strengths": [
    "Specific strength 1 with evidence",
    "Specific strength 2 with evidence"
  ],
  "Weaknesses": [
    "Specific weakness 1 with evidence",
    "Specific weakness 2 with evidence"
  ],
  "Originality": 3,
  "Quality": 3,
  "Clarity": 3,
  "Significance": 2,
  "Soundness": 3,
  "Presentation": 3,
  "Contribution": 3,
  "Questions": [
    "Question for authors 1",
    "Question for authors 2"
  ],
  "Limitations": [
    "Limitation or negative societal impact 1"
  ],
  "Ethical Concerns": false,
  "Overall": 6,
  "Confidence": 3,
  "Decision": "Accept"
}
```

## Review Guidelines

- Be **critical but fair** — identify both strengths and weaknesses
- Be **specific** — cite sections, figures, equations by reference
- Be **constructive** — suggest how to fix weaknesses
- **Calibrate** against the fewshot examples in `examples/`:
  - "Attention Is All You Need" → Accept (8/10): groundbreaking contribution
  - "Automated Relational" → Accept (7/10): solid work
  - "Carpe Diem" → Reject (4/10): insufficient evidence
- Overall ≥ 6 → Accept, < 6 → Reject
- For workshop papers (ICBINB), negative results are acceptable if well-analyzed
