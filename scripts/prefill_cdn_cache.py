#!/usr/bin/env python3
"""Warm Cloudflare edge cache for all completed AI Scientist jobs.

Usage:
    python3 scripts/prefill_cdn_cache.py                    # Tier 1+2 only (~200 requests)
    python3 scripts/prefill_cdn_cache.py --include-steps    # + all trajectory steps (~10K requests)
    python3 scripts/prefill_cdn_cache.py --base-url http://localhost:8501  # test locally
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request
from urllib.error import URLError

DEFAULT_BASE = "https://aiscientist.lishengzhi.com"
CONCURRENCY = 8

TIER1_ENDPOINTS = [
    "meta",
    "tokens",
    "idea",
    "submissions",
    "trajectory/index",
    "artifacts",
]


def fetch(url: str) -> tuple[str, int, str]:
    """Fetch a URL and return (url, status, cf-cache-status)."""
    try:
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; CDN-Prefill/1.0)",
            "Accept": "application/json",
        })
        resp = urlopen(req, timeout=30)
        cf = dict(resp.headers).get("cf-cache-status", "?")
        return url, resp.status, cf
    except URLError as e:
        return url, getattr(e, "code", 0), "ERROR"
    except Exception as e:
        return url, 0, f"ERROR: {e}"


def main():
    parser = argparse.ArgumentParser(description="Warm Cloudflare CDN cache")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--include-steps", action="store_true",
                        help="Also prefill individual trajectory steps (Tier 3)")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")

    # 1. Get all jobs
    print(f"Fetching job list from {base}/api/jobs ...")
    req = Request(f"{base}/api/jobs", headers={
        "User-Agent": "Mozilla/5.0 (compatible; CDN-Prefill/1.0)",
        "Accept": "application/json",
    })
    resp = urlopen(req, timeout=30)
    jobs = json.loads(resp.read())
    print(f"  {len(jobs)} jobs found")

    # 2. Build Tier 1+2 URLs
    urls = []
    skip_statuses = {"running"}
    for job in jobs:
        jid = job["id"]
        if job.get("status") in skip_statuses:
            continue
        for ep in TIER1_ENDPOINTS:
            urls.append(f"{base}/api/jobs/{jid}/{ep}")
        # Tier 2: events
        urls.append(f"{base}/api/jobs/{jid}/events?after=0")

    print(f"\nTier 1+2: {len(urls)} requests")

    if args.dry_run:
        for u in urls[:20]:
            print(f"  [dry-run] {u}")
        if len(urls) > 20:
            print(f"  ... and {len(urls) - 20} more")
        return

    # 3. Fire Tier 1+2
    t0 = time.time()
    stats = {"HIT": 0, "MISS": 0, "DYNAMIC": 0, "ERROR": 0, "other": 0}
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(fetch, u): u for u in urls}
        for f in as_completed(futures):
            url, status, cf = f.result()
            bucket = cf if cf in stats else "other"
            stats[bucket] = stats.get(bucket, 0) + 1
            if cf == "ERROR" or status >= 400:
                print(f"  {cf:8s} {status} {url}")

    elapsed = time.time() - t0
    print(f"\nTier 1+2 complete in {elapsed:.1f}s:")
    for k, v in sorted(stats.items()):
        if v > 0:
            print(f"  {k}: {v}")

    # 4. Tier 3: individual steps
    if not args.include_steps:
        print(f"\nSkipping Tier 3 (use --include-steps to prefill individual steps)")
        return

    step_urls = []
    for job in jobs:
        if job.get("status") in skip_statuses:
            continue
        jid = job["id"]
        try:
            resp = urlopen(f"{base}/api/jobs/{jid}/trajectory/index", timeout=30)
            idx = json.loads(resp.read())
            total = idx.get("total_steps", 0)
            for s in range(total):
                step_urls.append(f"{base}/api/jobs/{jid}/trajectory/step/{s}")
        except Exception:
            pass

    print(f"\nTier 3: {len(step_urls)} step requests")
    t0 = time.time()
    step_stats = {"HIT": 0, "MISS": 0, "DYNAMIC": 0, "ERROR": 0, "other": 0}
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(fetch, u): u for u in step_urls}
        done = 0
        for f in as_completed(futures):
            url, status, cf = f.result()
            bucket = cf if cf in step_stats else "other"
            step_stats[bucket] = step_stats.get(bucket, 0) + 1
            done += 1
            if done % 500 == 0:
                print(f"  ... {done}/{len(step_urls)}")

    elapsed = time.time() - t0
    print(f"\nTier 3 complete in {elapsed:.1f}s:")
    for k, v in sorted(step_stats.items()):
        if v > 0:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
