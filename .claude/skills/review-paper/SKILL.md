---
name: review-paper
description: Review a research paper and provide structured NeurIPS-format feedback with ratings and decision.
argument-hint: "[path/to/template.tex]"
disable-model-invocation: true
allowed-tools: Bash, Read
---

# Paper Review

You are an AI researcher acting as a reviewer for a prestigious ML conference. Provide a thorough, structured review.

## Process

1. **Extract text and generate questions**: Extract paper text and generate review questions using a specialty-trained model
   - Run with **timeout: 180000** (3 minutes): `bash .claude/skills/review-paper/scripts/extract_and_generate_questions.sh <tex_path>`
   - Reads LaTeX source directly — no OCR needed (~30s total)
   - Generates context-aware review questions using specialty-trained model
   - Returns JSON with both extracted text and generated question
   - **Use `timeout: 180000`** in the Bash tool call (question generation takes ~20-30s)
   - Save the output to use in your review

2. **Read the paper**: Read the LaTeX source carefully, end to end
   - Use the extracted text as reference, but also read the original LaTeX for full context

3. **Study fewshot examples**: Reference the example reviews in `examples/` directory to calibrate your ratings

4. **Evaluate**: Assess across all dimensions below, incorporating insights from the generated questions

5. **Write review**: Produce structured JSON output, including the generated questions in the "Questions" field

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
- **Use the extraction script** (Step 1): The script provides:
  - Accurate text extracted directly from the LaTeX source
  - Context-aware questions that highlight important aspects to consider
  - Incorporate the generated question into your review's "Questions" field, but also add your own questions based on your analysis
- **Calibrate** against the fewshot examples in `examples/`:
  - "Attention Is All You Need" → Accept (8/10): groundbreaking contribution
  - "Automated Relational" → Accept (7/10): solid work
  - "Carpe Diem" → Reject (4/10): insufficient evidence
- Overall ≥ 6 → Accept, < 6 → Reject
- For workshop papers (ICBINB), negative results are acceptable if well-analyzed

## Environment Variables

- `QUESTIONS_API_URL` — URL for questions generation endpoint (defaults to `http://31.97.61.220/api/generate`)
