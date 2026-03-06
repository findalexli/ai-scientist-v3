"""
Download and filter the ForecastBench dataset.

ForecastBench (forecastingresearch/forecastbench on HuggingFace) contains
binary and multiple-choice questions sourced from:
  - Metaculus, Manifold, Polymarket, Kalshi, INFER, …

Each row has:
  question          str   — natural-language question text
  resolution_date   str   — ISO date
  resolved          bool  — True if the question has a known outcome
  resolution        float — ground-truth probability (0.0 or 1.0 for binary)
  source            str   — "kalshi", "metaculus", …
  crowd_forecast    float — aggregated human crowd probability (where available)

Usage
-----
    python data/fetch_forecastbench.py --output data/questions.jsonl
    python data/fetch_forecastbench.py --output data/questions.jsonl --source kalshi
    python data/fetch_forecastbench.py --output data/questions.jsonl --resolved-only
"""
import argparse
import json
import sys
from pathlib import Path

try:
    from datasets import load_dataset
except ImportError:
    print("Install: uv pip install --system datasets", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import FORECASTBENCH_HF_REPO


REQUIRED_FIELDS = {"question", "resolution_date", "resolved", "resolution", "source"}


def fetch(output_path: str, source_filter: str | None = None, resolved_only: bool = False):
    print(f"Loading ForecastBench from HuggingFace ({FORECASTBENCH_HF_REPO}) …")
    try:
        ds = load_dataset(FORECASTBENCH_HF_REPO, split="test", trust_remote_code=True)
    except Exception:
        # Fall back to the 'questions' config if default split fails
        ds = load_dataset(FORECASTBENCH_HF_REPO, "questions", split="train", trust_remote_code=True)

    print(f"  Total rows: {len(ds)}")
    records = []

    for row in ds:
        # Normalise field names (dataset schema can vary across releases)
        rec = {
            "question":        row.get("question") or row.get("question_text", ""),
            "resolution_date": str(row.get("resolution_date") or row.get("close_date", "")),
            "resolved":        bool(row.get("resolved", False)),
            "resolution":      float(row.get("resolution") if row.get("resolution") is not None else -1),
            "source":          str(row.get("source") or row.get("platform", "unknown")).lower(),
            "crowd_forecast":  row.get("crowd_forecast") or row.get("community_prediction"),
            "metadata":        {k: v for k, v in row.items() if k not in REQUIRED_FIELDS},
        }

        if not rec["question"]:
            continue
        if source_filter and rec["source"] != source_filter.lower():
            continue
        if resolved_only and not rec["resolved"]:
            continue
        # Skip rows with missing outcome (resolution == -1)
        if resolved_only and rec["resolution"] < 0:
            continue

        records.append(rec)

    print(f"  After filters: {len(records)} questions")
    if source_filter:
        print(f"  Source filter: {source_filter}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    print(f"Saved to {output_path}")
    return records


def main():
    p = argparse.ArgumentParser(description="Download ForecastBench dataset")
    p.add_argument("--output", default="data/questions.jsonl")
    p.add_argument("--source", default=None, help="Filter by source, e.g. 'kalshi'")
    p.add_argument("--resolved-only", action="store_true",
                   help="Keep only questions with known outcomes")
    args = p.parse_args()
    fetch(args.output, source_filter=args.source, resolved_only=args.resolved_only)


if __name__ == "__main__":
    main()
