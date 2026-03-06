"""
Publication-quality calibration plots.

Functions
---------
  plot_reliability_diagram   — standard reliability diagram (one or many forecasters)
  plot_calibration_comparison — side-by-side reliability + histogram
  plot_metric_bars            — bar chart comparing Brier/ECE across models
"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

from metrics.scoring import reliability_diagram_data, summary_table


PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]


def plot_reliability_diagram(
    forecasters: list[dict],   # [{"label": str, "y_pred": array, "y_true": array}, …]
    out_path: str = "figures/reliability.png",
    n_bins: int = 10,
    title: str = "Reliability Diagram",
):
    """
    Plot a reliability diagram for one or more forecasters.

    Parameters
    ----------
    forecasters : list of dicts with keys:
        label   — name shown in legend
        y_pred  — predicted probabilities
        y_true  — binary outcomes
    """
    fig, ax = plt.subplots(figsize=(6, 6))

    # Perfect calibration reference line
    ax.plot([0, 1], [0, 1], "k--", lw=1.5, label="Perfect calibration", zorder=0)

    for i, fc in enumerate(forecasters):
        color = PALETTE[i % len(PALETTE)]
        rd = reliability_diagram_data(
            np.asarray(fc["y_pred"]), np.asarray(fc["y_true"]), n_bins=n_bins
        )
        mask = ~np.isnan(rd["bin_acc"])
        label = f"{fc['label']}  (ECE={rd['ece']:.3f})"
        ax.plot(
            rd["bin_conf"][mask], rd["bin_acc"][mask],
            "o-", color=color, label=label, lw=2, ms=6, zorder=2,
        )

    ax.set_xlabel("Mean predicted probability", fontsize=13)
    ax.set_ylabel("Empirical accuracy (fraction YES)", fontsize=13)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(fontsize=10, loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")


def plot_calibration_comparison(
    forecasters: list[dict],
    out_path: str = "figures/calibration_comparison.png",
    n_bins: int = 10,
    title: str = "Calibration Comparison",
):
    """
    Two-panel figure: reliability diagram (left) + forecast distribution histogram (right).
    """
    n = len(forecasters)
    fig = plt.figure(figsize=(12, 5))
    gs = gridspec.GridSpec(1, 2, figure=fig)
    ax_rel  = fig.add_subplot(gs[0])
    ax_hist = fig.add_subplot(gs[1])

    ax_rel.plot([0, 1], [0, 1], "k--", lw=1.5, label="Perfect", zorder=0)

    for i, fc in enumerate(forecasters):
        color = PALETTE[i % len(PALETTE)]
        y_pred = np.asarray(fc["y_pred"])
        y_true = np.asarray(fc["y_true"])
        rd = reliability_diagram_data(y_pred, y_true, n_bins=n_bins)
        mask = ~np.isnan(rd["bin_acc"])

        label = f"{fc['label']}  ECE={rd['ece']:.3f}"
        ax_rel.plot(rd["bin_conf"][mask], rd["bin_acc"][mask],
                    "o-", color=color, label=label, lw=2, ms=6, zorder=2)
        ax_hist.hist(y_pred, bins=n_bins, alpha=0.5, color=color,
                     label=fc["label"], range=(0, 1))

    ax_rel.set_xlabel("Mean predicted probability", fontsize=12)
    ax_rel.set_ylabel("Empirical accuracy", fontsize=12)
    ax_rel.set_xlim(0, 1); ax_rel.set_ylim(0, 1)
    ax_rel.legend(fontsize=9, loc="upper left")
    ax_rel.grid(True, alpha=0.3)
    ax_rel.set_title("Reliability Diagram", fontsize=13, fontweight="bold")

    ax_hist.set_xlabel("Predicted probability", fontsize=12)
    ax_hist.set_ylabel("Count", fontsize=12)
    ax_hist.set_xlim(0, 1)
    ax_hist.legend(fontsize=9)
    ax_hist.set_title("Forecast Distribution", fontsize=13, fontweight="bold")
    ax_hist.grid(True, alpha=0.3)

    fig.suptitle(title, fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")


def plot_metric_bars(
    summaries: list[dict],   # list of dicts from scoring.summary_table()
    out_path: str = "figures/metric_bars.png",
    metrics: list[str] = ("brier", "ece", "log_loss"),
):
    """
    Grouped bar chart comparing metrics across forecasters.
    """
    labels   = [s["label"] for s in summaries]
    n_metrics = len(metrics)
    x = np.arange(len(labels))
    width = 0.7 / n_metrics

    fig, ax = plt.subplots(figsize=(max(6, 2 * len(labels)), 5))

    metric_labels = {
        "brier":       "Brier Score ↓",
        "ece":         "ECE ↓",
        "log_loss":    "Log Loss ↓",
        "brier_skill": "Brier Skill Score ↑",
    }

    for j, m in enumerate(metrics):
        vals = [s[m] for s in summaries]
        offset = (j - n_metrics / 2 + 0.5) * width
        bars = ax.bar(x + offset, vals, width, label=metric_labels.get(m, m),
                      color=PALETTE[j % len(PALETTE)], alpha=0.85)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.002,
                    f"{v:.3f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylabel("Score", fontsize=12)
    ax.set_title("Forecaster Metrics Comparison", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_ylim(0, ax.get_ylim()[1] * 1.15)
    fig.tight_layout()

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")
