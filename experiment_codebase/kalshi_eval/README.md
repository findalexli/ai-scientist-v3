# Kalshi Forecasting Evaluation Framework

A ForecastBench-style evaluation framework for measuring LLM calibration and
accuracy on Kalshi prediction-market questions.

## Structure

```
kalshi_eval/
├── data/
│   ├── fetch_forecastbench.py   # Download ForecastBench dataset (includes Kalshi Qs)
│   └── fetch_kalshi.py          # Fetch directly from Kalshi public API
├── models/
│   └── llm_forecaster.py        # LLM inference → probability estimates
├── metrics/
│   ├── scoring.py               # Brier score, log loss, ECE
│   └── calibration.py           # Reliability diagrams, calibration plots
├── evaluate.py                  # Main eval loop
├── plot_results.py              # Generate publication-quality figures
└── config.py                    # API keys and settings
```

## Quick Start

```bash
# 1. Fetch questions (ForecastBench dataset with Kalshi subset)
python data/fetch_forecastbench.py --output data/questions.jsonl

# 2. Run LLM forecaster
python evaluate.py \
    --questions data/questions.jsonl \
    --model claude-sonnet-4-6 \
    --output results/run_$(date +%Y%m%d).jsonl

# 3. Score + plot
python plot_results.py --results results/run_*.jsonl
```

## Metrics

- **Brier Score** — mean squared error between forecast probability and outcome (lower is better)
- **Log Loss** — cross-entropy (lower is better)
- **ECE** — Expected Calibration Error (lower is better; 0 = perfectly calibrated)
- **Reliability Diagram** — visual calibration check: predicted prob vs empirical freq

## Baselines

- Market-implied probability (Kalshi last-trade price before resolution)
- ForecastBench human/crowd baseline
- Uniform prior (0.5 for binary)

## Experiment Log

| Date | Model | N questions | Brier | ECE | Notes |
|------|-------|-------------|-------|-----|-------|
| (run evaluate.py to populate) | | | | | |
