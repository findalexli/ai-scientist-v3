"""
Download all DataClaw datasets from HuggingFace.
Deduplicates forks of peteromallet/dataclaw-peteromallet (same 549 rows).
"""

import os
import json
from pathlib import Path
from huggingface_hub import snapshot_download
from huggingface_hub.utils import RepositoryNotFoundError, GatedRepoError

# All unique dataclaw datasets (excluding pure forks with identical peteromallet data)
# Forks identified: AbraZero, nathanstvnsn, Vigneshwaran, hitlabstudios, introvoyz041,
#                   arefmikati, 0010Grent, amine-khelif, louyu, Noah-12 (all 549 rows = same data)
# Keeping the canonical peteromallet/dataclaw-peteromallet

DATASETS = [
    # Original / canonical
    "peteromallet/dataclaw-peteromallet",       # 549 rows, primary
    # Unique user sessions
    "woctordho/dataclaw",                        # 260 rows
    "woctordho/dataclaw-windows",                # 105 rows
    "Batman787/dataclaw-Batman787",              # 146 rows
    "leoikin/dataclaw-peteromallet",             # 120 rows (may have user's own sessions)
    "Codingxx/dataclaw-peteromallet",            # 108 rows
    "emperorfutures/dataclaw-code2",             # 152 rows
    "Edmon02/dataclaw-peteromallet",             # 116 rows
    "ajdriscod/dataclaw-peteromallet",           # 105 rows
    "sunsun123new/dataclaw-sunsun123new",        # 176 rows
    "GazTrab/dataclaw-GazTrab",                  # 97 rows
    "GolienHzmsr/dataclaw-GolienHzmsr",          # 118 rows
    "tillg/dataclaw-tillg",                      # 146 rows
    "DJTRIXUK/dataclaw-DJTRIXUK",                # 104 rows
    "parani01/dataclaw-parani01",                # 105 rows
    "zhiyaowang/dataclaw-zhiyaowang",            # 73 rows
    "vaynelee/dataclaw-vaynelee",                # 71 rows
    "jiaweili2001/claw-data",                    # 3 rows
    # Personal claude-code data (tagged dataclaw)
    "misterkerns/my-personal-claude-code-data",
    "REXX-NEW/my-personal-claude-code-data",
    "REXX-NEW/my-personal-codex-data",
    "peteromallet/my-personal-claude-code-data",
    "peteromallet/my-personal-codex-data",
    "introvoyz041/my-personal-codex-data",
    "xuechengjiang/my-personal-codex-data",
    "akenove/my-personal-codex-data",
]

OUTPUT_DIR = Path("/home/user/ai-scientist-v3/experiment_codebase/dataclaw_datasets")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

results = {"success": [], "failed": [], "skipped": []}

for dataset_id in DATASETS:
    safe_name = dataset_id.replace("/", "__")
    out_path = OUTPUT_DIR / safe_name

    if out_path.exists() and any(out_path.iterdir()):
        print(f"[SKIP] {dataset_id} already downloaded")
        results["skipped"].append(dataset_id)
        continue

    print(f"\n[DOWNLOADING] {dataset_id} → {out_path}")
    try:
        snapshot_download(
            repo_id=dataset_id,
            repo_type="dataset",
            local_dir=str(out_path),
        )
        print(f"  ✓ Success")
        results["success"].append(dataset_id)
    except RepositoryNotFoundError:
        print(f"  ✗ Not found (private or deleted)")
        results["failed"].append({"dataset": dataset_id, "error": "not found"})
    except GatedRepoError:
        print(f"  ✗ Gated repo (requires token)")
        results["failed"].append({"dataset": dataset_id, "error": "gated"})
    except Exception as e:
        print(f"  ✗ Error: {e}")
        results["failed"].append({"dataset": dataset_id, "error": str(e)})

# Save summary
summary_path = OUTPUT_DIR / "download_summary.json"
with open(summary_path, "w") as f:
    json.dump(results, f, indent=2)

print(f"\n{'='*60}")
print(f"SUCCESS: {len(results['success'])}")
print(f"SKIPPED: {len(results['skipped'])}")
print(f"FAILED:  {len(results['failed'])}")
print(f"Summary saved to {summary_path}")

if results["failed"]:
    print("\nFailed datasets:")
    for f in results["failed"]:
        print(f"  - {f['dataset']}: {f['error'][:100]}")
