"""
Fetch resolved markets directly from the Kalshi public API.

Kalshi exposes two endpoint families:
  /markets         — live and recently closed markets
  /series          — series/category listings

No API key is needed for public market data. The API returns:
  ticker, title, status, result, close_time, last_price, …

The last_price before close is our market-implied probability baseline.

Usage
-----
    # Fetch the most recent 200 resolved binary markets
    python data/fetch_kalshi.py --output data/kalshi_markets.jsonl --limit 200

    # Fetch markets in a specific series
    python data/fetch_kalshi.py --series INAU --output data/kalshi_markets.jsonl
"""
import argparse
import json
import time
from pathlib import Path

import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
HEADERS = {"Accept": "application/json"}


def get_markets(
    limit: int = 200,
    series_ticker: str | None = None,
    status: str = "settled",
) -> list[dict]:
    """
    Page through /markets until we have `limit` resolved markets.
    Returns a list of dicts with normalised fields.

    Valid status values: "open", "closed", "settled"
    "settled" = resolved with a known outcome (yes/no).

    Note on crowd_forecast: Kalshi's last_price at settlement is 0 or 100 (cents),
    so it's not a useful pre-resolution probability baseline. Use
    get_candlestick_history() to fetch the price at a fixed horizon before close.
    For a quick baseline, we use (yes_bid + yes_ask) / 2 from the last candle
    before settlement. This field is left None here; enrich with candlestick data
    if you need a proper market-implied probability baseline.
    """
    collected = []
    cursor = None

    while len(collected) < limit:
        params: dict = {
            "limit": min(200, limit - len(collected)),
            "status": status,
        }
        if cursor:
            params["cursor"] = cursor
        if series_ticker:
            params["series_ticker"] = series_ticker

        resp = requests.get(f"{BASE}/markets", headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        markets = data.get("markets", [])
        if not markets:
            break

        for m in markets:
            # Only keep binary yes/no markets with a clear resolution
            if m.get("market_type") != "binary":
                continue
            result = m.get("result", "")
            if result not in ("yes", "no"):
                continue

            # crowd_forecast: use mid-price if available, else None (see docstring)
            yes_bid = m.get("yes_bid")
            yes_ask = m.get("yes_ask")
            if yes_bid is not None and yes_ask is not None and yes_bid + yes_ask > 0:
                market_prob = (yes_bid + yes_ask) / 2.0 / 100.0
            else:
                market_prob = None  # will need candlestick data for a real baseline

            collected.append({
                "ticker":          m.get("ticker", ""),
                "question":        m.get("title", ""),
                "series":          m.get("series_ticker", ""),
                "category":        m.get("category", ""),
                "close_time":      m.get("close_time", ""),
                "resolution":      1.0 if result == "yes" else 0.0,
                "resolved":        True,
                "source":          "kalshi",
                "crowd_forecast":  market_prob,
                "metadata": {
                    "open_time":    m.get("open_time"),
                    "volume":       m.get("volume"),
                    "open_interest":m.get("open_interest"),
                    "yes_bid":      yes_bid,
                    "yes_ask":      yes_ask,
                },
            })

        cursor = data.get("cursor")
        if not cursor:
            break
        time.sleep(0.1)   # be polite to the API

    return collected


def get_candlestick_history(ticker: str, horizon_days: int = 7) -> list[dict]:
    """
    Fetch hourly candlestick data for a market.
    Returns list of {ts, open, close, high, low} in probability space (0-1).
    """
    resp = requests.get(
        f"{BASE}/markets/{ticker}/candlesticks",
        headers=HEADERS,
        params={"period_interval": 60},   # 60-minute candles
        timeout=30,
    )
    if resp.status_code != 200:
        return []
    candles = resp.json().get("candlesticks", [])
    return [
        {
            "ts":    c.get("end_period_ts"),
            "open":  c.get("yes_open", 50) / 100.0,
            "close": c.get("yes_close", 50) / 100.0,
            "high":  c.get("yes_high", 50) / 100.0,
            "low":   c.get("yes_low", 50) / 100.0,
        }
        for c in candles
    ]


def main():
    p = argparse.ArgumentParser(description="Fetch resolved Kalshi markets")
    p.add_argument("--output", default="data/kalshi_markets.jsonl")
    p.add_argument("--limit", type=int, default=200,
                   help="Max number of markets to fetch")
    p.add_argument("--series", default=None,
                   help="Filter by series ticker, e.g. INAU")
    args = p.parse_args()

    print(f"Fetching up to {args.limit} resolved Kalshi markets …")
    markets = get_markets(limit=args.limit, series_ticker=args.series)
    print(f"  Fetched: {len(markets)}")

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        for m in markets:
            f.write(json.dumps(m) + "\n")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
