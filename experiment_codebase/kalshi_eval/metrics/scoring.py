"""
Scoring metrics for probabilistic forecasts.

All functions accept numpy arrays or lists of:
  y_pred  — predicted probabilities in [0, 1]
  y_true  — binary outcomes in {0, 1}

Metrics
-------
  brier_score   — mean((p - y)²), lower is better, baseline=0.25
  log_loss      — cross-entropy, lower is better
  ece           — Expected Calibration Error, lower is better
  reliability   — returns (bin_centers, bin_acc, bin_conf, bin_counts)
"""
import numpy as np


def brier_score(y_pred: np.ndarray, y_true: np.ndarray) -> float:
    """Mean squared error between forecast and outcome. Range [0, 1]."""
    y_pred = np.asarray(y_pred, dtype=float)
    y_true = np.asarray(y_true, dtype=float)
    return float(np.mean((y_pred - y_true) ** 2))


def brier_skill_score(y_pred: np.ndarray, y_true: np.ndarray) -> float:
    """
    BSS = 1 - BS / BS_ref, where BS_ref is the climatological (uniform) forecast.
    BSS > 0 means better than climatology; BSS = 1 is perfect.
    """
    bs = brier_score(y_pred, y_true)
    prevalence = float(np.mean(y_true))
    bs_ref = prevalence * (1 - prevalence)   # Brier score of the base rate
    if bs_ref == 0:
        return 0.0
    return 1.0 - bs / bs_ref


def log_loss(y_pred: np.ndarray, y_true: np.ndarray, clip: float = 1e-7) -> float:
    """Cross-entropy loss. Lower is better."""
    y_pred = np.clip(np.asarray(y_pred, dtype=float), clip, 1 - clip)
    y_true = np.asarray(y_true, dtype=float)
    return float(-np.mean(y_true * np.log(y_pred) + (1 - y_true) * np.log(1 - y_pred)))


def ece(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    n_bins: int = 10,
) -> float:
    """
    Expected Calibration Error.
    Partitions predictions into equal-width bins; for each bin measures
    |mean_prediction - empirical_accuracy|, weighted by bin size.
    """
    y_pred = np.asarray(y_pred, dtype=float)
    y_true = np.asarray(y_true, dtype=float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_pred, bins) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    weighted_error = 0.0
    n = len(y_pred)
    for b in range(n_bins):
        mask = bin_indices == b
        if mask.sum() == 0:
            continue
        conf = y_pred[mask].mean()
        acc  = y_true[mask].mean()
        weighted_error += mask.sum() * abs(conf - acc)

    return weighted_error / n


def reliability_diagram_data(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    n_bins: int = 10,
) -> dict:
    """
    Returns data needed to plot a reliability diagram.

    Returns
    -------
    dict with keys:
      bin_centers  — midpoint of each confidence bin
      bin_acc      — empirical accuracy in each bin
      bin_conf     — mean predicted confidence in each bin
      bin_counts   — number of samples in each bin
      ece          — ECE scalar
    """
    y_pred = np.asarray(y_pred, dtype=float)
    y_true = np.asarray(y_true, dtype=float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_pred, bins) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    centers, accs, confs, counts = [], [], [], []
    for b in range(n_bins):
        mask = bin_indices == b
        centers.append((bins[b] + bins[b + 1]) / 2)
        if mask.sum() == 0:
            accs.append(np.nan)
            confs.append(np.nan)
            counts.append(0)
        else:
            accs.append(float(y_true[mask].mean()))
            confs.append(float(y_pred[mask].mean()))
            counts.append(int(mask.sum()))

    return {
        "bin_centers": np.array(centers),
        "bin_acc":     np.array(accs),
        "bin_conf":    np.array(confs),
        "bin_counts":  np.array(counts),
        "ece":         ece(y_pred, y_true, n_bins=n_bins),
    }


def summary_table(
    y_pred: np.ndarray,
    y_true: np.ndarray,
    label: str = "model",
) -> dict:
    """Return a dict of all core metrics for one forecaster."""
    y_pred = np.asarray(y_pred, dtype=float)
    y_true = np.asarray(y_true, dtype=float)
    return {
        "label":       label,
        "n":           len(y_true),
        "prevalence":  float(np.mean(y_true)),
        "brier":       brier_score(y_pred, y_true),
        "brier_skill": brier_skill_score(y_pred, y_true),
        "log_loss":    log_loss(y_pred, y_true),
        "ece":         ece(y_pred, y_true),
        "mean_pred":   float(np.mean(y_pred)),
    }
