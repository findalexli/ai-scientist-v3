"""
Generate publication-quality evaluation figures from results JSONL files.

Usage
-----
    # Plot from one or more results files
    python plot_results.py --results results/run_20260306.jsonl

    # Compare multiple models
    python plot_results.py \
        --results results/haiku.jsonl results/sonnet.jsonl \
        --labels "Haiku" "Sonnet"

    # Filter to a specific source (e.g., kalshi-only)
    python plot_results.py --results results/run.jsonl --source kalshi
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metrics.scoring import summary_table
from metrics.calibration import (
    plot_reliability_diagram,
    plot_calibration_comparison,
    plot_metric_bars,
)


def load_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def build_forecasters(
    results_files: list[str],
    labels: list[str] | None,
    source_filter: str | None,
) -> tuple[list[dict], list[dict]]:
    """
    Returns (forecasters_list, summaries_list) for all model + baseline combos.
    """
    forecasters = []
    summaries   = []

    for i, path in enumerate(results_files):
        records = load_jsonl(path)

        if source_filter:
            records = [r for r in records if r.get("source", "").lower() == source_filter.lower()]

        scorable = [
            r for r in records
            if r.get("resolved") and r.get("resolution") is not None
            and r.get("llm_probability") is not None
            and 0.0 <= r["resolution"] <= 1.0
        ]
        if not scorable:
            print(f"  WARNING: no scorable records in {path}")
            continue

        label = labels[i] if labels and i < len(labels) else Path(path).stem
        y_true = np.array([r["resolution"]    for r in scorable])
        y_pred = np.array([r["llm_probability"] for r in scorable])

        forecasters.append({"label": label, "y_pred": y_pred, "y_true": y_true})
        summaries.append(summary_table(y_pred, y_true, label=label))

    # Add baselines from the first file (Crowd + Uniform)
    if results_files:
        records = load_jsonl(results_files[0])
        if source_filter:
            records = [r for r in records if r.get("source", "").lower() == source_filter.lower()]
        scorable = [r for r in records
                    if r.get("resolved") and r.get("resolution") is not None
                    and 0.0 <= r["resolution"] <= 1.0]

        if scorable:
            y_true = np.array([r["resolution"] for r in scorable])

            # Crowd / market baseline
            has_crowd = [r for r in scorable if r.get("crowd_forecast") is not None]
            if has_crowd:
                y_true_c = np.array([r["resolution"]    for r in has_crowd])
                y_crowd  = np.array([r["crowd_forecast"] for r in has_crowd])
                forecasters.append({"label": "Market/Crowd", "y_pred": y_crowd, "y_true": y_true_c})
                summaries.append(summary_table(y_crowd, y_true_c, label="Market/Crowd"))

            # Uniform baseline
            y_uniform = np.full_like(y_true, 0.5)
            forecasters.append({"label": "Uniform(0.5)", "y_pred": y_uniform, "y_true": y_true})
            summaries.append(summary_table(y_uniform, y_true, label="Uniform(0.5)"))

    return forecasters, summaries


def main():
    p = argparse.ArgumentParser(description="Plot Kalshi eval results")
    p.add_argument("--results", nargs="+", required=True, help="JSONL result files")
    p.add_argument("--labels",  nargs="+", default=None, help="Labels for each results file")
    p.add_argument("--source",  default=None, help="Filter by source, e.g. 'kalshi'")
    p.add_argument("--out-dir", default="../../figures", help="Output directory for figures")
    args = p.parse_args()

    forecasters, summaries = build_forecasters(args.results, args.labels, args.source)

    if not forecasters:
        print("No forecasters to plot.")
        sys.exit(1)

    out = args.out_dir
    suffix = f"_{args.source}" if args.source else ""

    # 1. Simple reliability diagram
    plot_reliability_diagram(
        forecasters,
        out_path=f"{out}/reliability{suffix}.png",
        title=f"Reliability Diagram{' — ' + args.source.title() if args.source else ''}",
    )

    # 2. Combined reliability + distribution histogram
    plot_calibration_comparison(
        forecasters,
        out_path=f"{out}/calibration_comparison{suffix}.png",
        title=f"Calibration Comparison{' — ' + args.source.title() if args.source else ''}",
    )

    # 3. Metric bar chart
    plot_metric_bars(
        summaries,
        out_path=f"{out}/metric_bars{suffix}.png",
    )

    # Print final table
    print("\n=== Final Metrics ===")
    header = f"{'Forecaster':<22} {'N':>6} {'Brier':>8} {'BSS':>8} {'ECE':>8} {'LogLoss':>9}"
    print(header)
    print("-" * len(header))
    for s in summaries:
        print(f"{s['label']:<22} {s['n']:>6} {s['brier']:>8.4f} {s['brier_skill']:>8.4f} "
              f"{s['ece']:>8.4f} {s['log_loss']:>9.4f}")


if __name__ == "__main__":
    main()
