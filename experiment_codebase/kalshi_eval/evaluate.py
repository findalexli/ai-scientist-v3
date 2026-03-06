"""
Main evaluation loop.

Reads questions from a JSONL file, runs the LLM forecaster on each, and
writes results (original question + LLM prediction) to an output JSONL.

Usage
-----
    # Full run against ForecastBench questions
    python evaluate.py \
        --questions data/questions.jsonl \
        --model claude-sonnet-4-6 \
        --output results/run_20260306.jsonl

    # Quick smoke-test on 10 questions
    python evaluate.py \
        --questions data/questions.jsonl \
        --model claude-haiku-4-5-20251001 \
        --output results/smoke.jsonl \
        --limit 10

    # Score and print a table without re-running LLM
    python evaluate.py --score-only --results results/run_20260306.jsonl
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Allow running from the kalshi_eval/ root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from models.llm_forecaster import LLMForecaster
from metrics.scoring import summary_table


def load_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def save_jsonl(records: list[dict], path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def run_eval(
    questions: list[dict],
    model: str,
    output_path: str,
    resume: bool = True,
) -> list[dict]:
    """
    Forecast each question and save incrementally (so crashes don't lose work).
    If `resume=True`, skip questions that already have results in output_path.
    """
    # Load previously completed results
    done = {}
    if resume and Path(output_path).exists():
        for r in load_jsonl(output_path):
            key = r.get("question", "")
            if r.get("llm_probability") is not None:
                done[key] = r
        print(f"Resuming: {len(done)} questions already done.")

    forecaster = LLMForecaster(model=model)
    results = list(done.values())

    # Open output file in append mode for incremental saving
    out_file = open(output_path, "a")

    pending = [q for q in questions if q.get("question", "") not in done]
    print(f"Running LLM on {len(pending)} questions (model={model}) …")

    for i, q in enumerate(pending):
        print(f"  [{i+1}/{len(pending)}] {q['question'][:80]} …")
        out = forecaster.forecast(
            question=q["question"],
            resolution_date=q.get("resolution_date", ""),
        )
        record = {
            **q,
            "llm_probability": out["probability"],
            "llm_reasoning":   out["reasoning"],
            "llm_model":       out["model"],
        }
        results.append(record)
        out_file.write(json.dumps(record) + "\n")
        out_file.flush()

    out_file.close()
    print(f"Saved {len(results)} results → {output_path}")
    return results


def score_results(results: list[dict]) -> list[dict]:
    """
    Score LLM and (if available) market baseline forecasts.
    Prints a summary table and returns list of summary dicts.
    """
    # Filter to questions with known outcomes AND LLM predictions
    scorable = [
        r for r in results
        if r.get("resolved") and r.get("resolution") is not None
        and r.get("llm_probability") is not None
        and 0.0 <= r["resolution"] <= 1.0
    ]

    if not scorable:
        print("No scorable results (need resolved=True + llm_probability).")
        return []

    y_true = np.array([r["resolution"] for r in scorable])
    y_llm  = np.array([r["llm_probability"] for r in scorable])

    summaries = [summary_table(y_llm, y_true, label="LLM")]

    # Crowd / market baseline (if available)
    has_crowd = [r for r in scorable if r.get("crowd_forecast") is not None]
    if has_crowd:
        y_true_c   = np.array([r["resolution"]    for r in has_crowd])
        y_crowd    = np.array([r["crowd_forecast"] for r in has_crowd])
        summaries.append(summary_table(y_crowd, y_true_c, label="Market/Crowd"))

    # Uniform baseline (always 0.5)
    summaries.append(summary_table(np.full_like(y_true, 0.5), y_true, label="Uniform(0.5)"))

    # Pretty-print
    print("\n=== Evaluation Results ===")
    header = f"{'Forecaster':<22} {'N':>6} {'Brier':>8} {'BSS':>8} {'ECE':>8} {'LogLoss':>9}"
    print(header)
    print("-" * len(header))
    for s in summaries:
        print(f"{s['label']:<22} {s['n']:>6} {s['brier']:>8.4f} {s['brier_skill']:>8.4f} "
              f"{s['ece']:>8.4f} {s['log_loss']:>9.4f}")

    return summaries


def main():
    p = argparse.ArgumentParser(description="Kalshi forecasting evaluator")
    p.add_argument("--questions", help="JSONL with questions (fetch with data/ scripts)")
    p.add_argument("--model",    default="claude-sonnet-4-6", help="Claude model ID")
    p.add_argument("--output",   default="results/run.jsonl", help="Output JSONL path")
    p.add_argument("--limit",    type=int, default=None, help="Max questions to evaluate")
    p.add_argument("--no-resume", action="store_true", help="Overwrite existing output")
    p.add_argument("--score-only", action="store_true",
                   help="Skip LLM, just score existing --output file")
    args = p.parse_args()

    if args.score_only:
        if not args.output or not Path(args.output).exists():
            print("--score-only requires --output pointing to an existing results file.")
            sys.exit(1)
        results = load_jsonl(args.output)
        score_results(results)
        return

    if not args.questions:
        print("Provide --questions <path.jsonl>  (or use --score-only)")
        sys.exit(1)

    questions = load_jsonl(args.questions)
    if args.limit:
        questions = questions[: args.limit]

    # Only score questions with known outcomes (for fair evaluation)
    resolved = [q for q in questions if q.get("resolved") and q.get("resolution") is not None]
    unresolved_count = len(questions) - len(resolved)
    print(f"Questions total: {len(questions)}  |  resolved: {len(resolved)}  |  skipped (unresolved): {unresolved_count}")

    results = run_eval(
        resolved,
        model=args.model,
        output_path=args.output,
        resume=not args.no_resume,
    )

    score_results(results)


if __name__ == "__main__":
    main()
