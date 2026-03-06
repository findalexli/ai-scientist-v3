"""
Central configuration for the Kalshi eval framework.
All API keys are read from environment variables — never hard-code them.
"""
import os

# --- Anthropic / Claude ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# --- Kalshi API ---
# Public endpoints require no key; private order-book endpoints need:
KALSHI_API_KEY_ID    = os.environ.get("KALSHI_API_KEY_ID", "")
KALSHI_API_KEY_PEM   = os.environ.get("KALSHI_API_KEY_PEM", "")   # RSA private-key string or path
KALSHI_BASE_URL      = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_HISTORY_URL   = "https://api.elections.kalshi.com/trade-api/v2"

# --- ForecastBench ---
# Dataset hosted on HuggingFace: forecastingresearch/forecastbench
FORECASTBENCH_HF_REPO = "forecastingresearch/forecastbench"

# --- Scoring ---
N_CALIBRATION_BINS  = 10       # bins for ECE / reliability diagram
BRIER_CLIP          = 1e-6     # clip probabilities away from 0/1 for log-loss stability

# --- LLM defaults ---
DEFAULT_MODEL       = "claude-sonnet-4-6"
MAX_TOKENS          = 512
TEMPERATURE         = 0.0      # deterministic for reproducibility
N_RETRIES           = 3
RETRY_DELAY_SEC     = 2.0
