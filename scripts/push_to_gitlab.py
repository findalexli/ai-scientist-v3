#!/usr/bin/env python3
"""Push sanitized job artifacts to the per-idea GitLab repo after job completion.

Usage:
    python3 scripts/push_to_gitlab.py --job-dir jobs/some_idea__2026-02-25__13-29-32
    python3 scripts/push_to_gitlab.py --job-dir jobs/some_idea__2026-02-25__13-29-32 --dry-run
    python3 scripts/push_to_gitlab.py --backfill          # push all completed, unpushed jobs
    python3 scripts/push_to_gitlab.py --backfill --dry-run

Requires GITLAB_KEY env var (personal access token with api scope).
"""

from __future__ import annotations

import argparse
import glob as globmod
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

# Import sibling modules.
sys.path.insert(0, str(SCRIPT_DIR))
from gitlab_setup import get_username, ensure_repo, list_branches  # noqa: E402
from sanitize_secrets import SecretSanitizer  # noqa: E402

# Import viewer's parse_trajectory for summary generation.
sys.path.insert(0, str(REPO_ROOT / "viewer"))
from parse_trajectory import (  # noqa: E402
    detect_and_parse,
    estimate_cost,
    compute_cumulative_tokens,
    compute_tool_breakdown,
    compute_event_type_breakdown,
    find_trajectory_path,
)


# ---------------------------------------------------------------------------
# Job directory parsing
# ---------------------------------------------------------------------------

JOB_NAME_RE = re.compile(r"^(.+?)__(\d{4}-\d{2}-\d{2})__(\d{2}-\d{2}-\d{2})$")


def parse_job_id(job_dir: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract (idea_stem, timestamp) from job directory name.

    Returns (None, None) for legacy date-only job names.
    """
    name = os.path.basename(os.path.normpath(job_dir))
    m = JOB_NAME_RE.match(name)
    if not m:
        return None, None
    stem = m.group(1).strip("_")
    # Legacy date-only names.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stem):
        return None, None
    ts = f"{m.group(2)}-{m.group(3).replace('-', '-')}"  # YYYY-MM-DD-HH-MM-SS
    return stem, ts


def detect_agent_type(config: dict) -> str:
    """Detect agent type from config.json."""
    agents = config.get("agents", [{}])
    if not agents:
        return "unknown"
    import_path = agents[0].get("import_path", "")
    model = agents[0].get("model_name", "")
    if "gemini" in import_path.lower() or "gemini" in model.lower():
        return "gemini-cli"
    if "claude" in import_path.lower() or "claude" in model.lower():
        return "claude-code"
    return "unknown"


def find_harbor_task_dir(job_dir: str) -> Optional[str]:
    """Find the harbor-task-* directory inside a job."""
    try:
        for entry in os.listdir(job_dir):
            if entry.startswith("harbor-task"):
                full = os.path.join(job_dir, entry)
                if os.path.isdir(full):
                    return full
    except OSError:
        pass
    return None


def read_json(path: str) -> dict:
    """Read a JSON file, returning {} on error."""
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


# ---------------------------------------------------------------------------
# Metadata and summary generation
# ---------------------------------------------------------------------------

def generate_metadata(
    job_dir: str,
    config: dict,
    result: dict,
    idea_stem: str,
    agent_type: str,
    branch: str,
    figures: List[str],
    has_paper: bool,
    submission_count: int,
    cost_data: Optional[dict] = None,
) -> dict:
    """Generate metadata.json content."""
    agents = config.get("agents", [{}])
    model = agents[0].get("model_name", "") if agents else ""
    job_name = os.path.basename(os.path.normpath(job_dir))

    started_at = result.get("started_at", "")
    finished_at = result.get("finished_at", "")
    duration = None
    if started_at and finished_at:
        try:
            t0 = datetime.fromisoformat(started_at)
            t1 = datetime.fromisoformat(finished_at)
            duration = int((t1 - t0).total_seconds())
        except (ValueError, TypeError):
            pass

    # Determine status.
    status = "completed"
    if not finished_at:
        status = "running"
    trials = result.get("stats", {})
    if isinstance(trials, dict) and trials.get("n_errors", 0) > 0:
        status = "error"

    return {
        "job_id": job_name,
        "idea_name": idea_stem,
        "agent_type": agent_type,
        "model": model,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration,
        "status": status,
        "branch": branch,
        "submission_count": submission_count,
        "has_paper_pdf": has_paper,
        "figures": figures,
        "token_summary": cost_data,
    }


def generate_trajectory_summary(
    job_dir: str, config: dict, model: str
) -> Optional[dict]:
    """Parse trajectory and generate pre-computed summary for the viewer."""
    try:
        parsed = detect_and_parse(job_dir)
    except Exception:
        return None

    if not parsed.events:
        return None

    cost = estimate_cost(parsed.events, model=model)
    cumulative = compute_cumulative_tokens(parsed.events)
    tool_bkd = compute_tool_breakdown(parsed.events)
    event_bkd = compute_event_type_breakdown(parsed.events)

    return {
        "total_events": len(parsed.events),
        "total_lines": parsed.total_lines,
        "model": parsed.model or model,
        "session_id": parsed.session_id,
        "agent_name": parsed.agent_name,
        "cost": cost,
        "tool_breakdown": tool_bkd,
        "event_type_breakdown": event_bkd,
        "cumulative_tokens": cumulative,
    }


# ---------------------------------------------------------------------------
# File staging
# ---------------------------------------------------------------------------

def stage_artifacts(
    job_dir: str,
    task_dir: str,
    staging: str,
    sanitizer: SecretSanitizer,
) -> Tuple[List[str], bool, int]:
    """Copy and sanitize artifacts into staging directory.

    Layout:
        agent_trace/           — sanitized trajectory + summary + metadata
        reviewer_trace/        — version_log, response.md, reviewer JSONL traces per version
        config.json            — task config (sanitized)
        result.json            — task result (sanitized)
        paper.pdf              — latest paper
        figures/               — latest figures

    Returns (figure_names, has_paper, submission_count).
    """
    agent_dir = os.path.join(task_dir, "agent")
    artifacts_dir = None
    for sub in ["agent", "verifier"]:
        candidate = os.path.join(task_dir, sub, "artifacts")
        if os.path.isdir(candidate):
            artifacts_dir = candidate
            break

    # config.json and result.json from task dir (top-level).
    for fname in ["config.json", "result.json"]:
        src = os.path.join(task_dir, fname)
        if os.path.isfile(src):
            data = read_json(src)
            sanitized = sanitizer.sanitize_json(data)
            with open(os.path.join(staging, fname), "w") as f:
                json.dump(sanitized, f, indent=2)

    # exception.txt (top-level).
    exc_path = os.path.join(task_dir, "exception.txt")
    if os.path.isfile(exc_path):
        sanitizer.sanitize_file(exc_path, os.path.join(staging, "exception.txt"))

    # --- agent_trace/ ---
    trace_dir = os.path.join(staging, "agent_trace")
    os.makedirs(trace_dir, exist_ok=True)

    # Sanitized trajectory.
    traj_path = find_trajectory_path(job_dir)
    if traj_path and os.path.isfile(traj_path):
        sanitizer.sanitize_file(traj_path, os.path.join(trace_dir, "trajectory.json"))

    # Paper PDF (top-level).
    has_paper = False
    if artifacts_dir:
        pdf_path = os.path.join(artifacts_dir, "paper.pdf")
        if os.path.isfile(pdf_path):
            shutil.copy2(pdf_path, os.path.join(staging, "paper.pdf"))
            has_paper = True

    # Figures (top-level figures/).
    figures = []
    if artifacts_dir:
        fig_src = os.path.join(artifacts_dir, "figures")
        if os.path.isdir(fig_src):
            fig_dst = os.path.join(staging, "figures")
            os.makedirs(fig_dst, exist_ok=True)
            for fname in sorted(os.listdir(fig_src)):
                if fname.lower().endswith((".png", ".jpg", ".jpeg", ".svg", ".pdf")):
                    shutil.copy2(os.path.join(fig_src, fname), os.path.join(fig_dst, fname))
                    figures.append(fname)

    # --- reviewer_trace/ ---
    submission_count = 0
    if artifacts_dir:
        sub_root = os.path.join(artifacts_dir, "submissions")
        vlog_path = os.path.join(sub_root, "version_log.json")
        if os.path.isfile(vlog_path):
            rt_dir = os.path.join(staging, "reviewer_trace")
            os.makedirs(rt_dir, exist_ok=True)
            vlog = read_json(vlog_path)
            sanitized_vlog = sanitizer.sanitize_json(vlog)
            with open(os.path.join(rt_dir, "version_log.json"), "w") as f:
                json.dump(sanitized_vlog, f, indent=2)

            versions = vlog.get("versions", [])
            submission_count = len(versions)
            for v in versions:
                vdir = v.get("directory", "")
                if not vdir:
                    continue
                comms_src = os.path.join(sub_root, vdir, "reviewer_communications")
                if not os.path.isdir(comms_src):
                    continue

                v_staging = os.path.join(rt_dir, vdir)
                os.makedirs(v_staging, exist_ok=True)

                # response.md (sanitized).
                resp_md = os.path.join(comms_src, "response.md")
                if os.path.isfile(resp_md):
                    sanitizer.sanitize_file(resp_md, os.path.join(v_staging, "response.md"))

                # raw_response.txt or raw_response.json (sanitized).
                for raw_name in ["raw_response.txt", "raw_response.json"]:
                    raw_path = os.path.join(comms_src, raw_name)
                    if os.path.isfile(raw_path):
                        sanitizer.sanitize_file(raw_path, os.path.join(v_staging, raw_name))

                # Reviewer trace JSONL files (sanitized).
                trace_src = os.path.join(comms_src, "trace")
                if os.path.isdir(trace_src):
                    trace_dst = os.path.join(v_staging, "trace")
                    os.makedirs(trace_dst, exist_ok=True)
                    for tf in os.listdir(trace_src):
                        if tf.endswith(".jsonl"):
                            sanitizer.sanitize_file(
                                os.path.join(trace_src, tf),
                                os.path.join(trace_dst, tf),
                            )

    return figures, has_paper, submission_count


# ---------------------------------------------------------------------------
# Git push
# ---------------------------------------------------------------------------

def git_push(staging: str, repo_url: str, branch: str, job_name: str) -> bool:
    """Clone existing branch (if any), add staged artifacts, commit, and push.

    Merges new files alongside existing agent workspace data on the branch.
    If the branch doesn't exist yet, creates an orphan branch.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    work_dir = tempfile.mkdtemp(prefix="gitlab-git-")

    try:
        return _git_push_inner(work_dir, staging, repo_url, branch, job_name, env)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _git_push_inner(
    work_dir: str, staging: str, repo_url: str, branch: str, job_name: str, env: dict
) -> bool:
    """Inner git push logic with guaranteed work_dir cleanup via caller."""

    def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + list(args),
            cwd=work_dir,
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
            check=check,
        )

    # Try to clone the existing branch (shallow, single-branch for speed).
    clone_result = subprocess.run(
        ["git", "clone", "--depth=1", "--single-branch", "--branch", branch, repo_url, work_dir],
        capture_output=True, text=True, env=env, timeout=180,
    )

    if clone_result.returncode != 0:
        # Branch doesn't exist yet — init an orphan branch in the (empty) work_dir.
        # work_dir was created by mkdtemp but clone may have partially populated it.
        run_git("init", check=False)
        run_git("checkout", "-b", branch, check=False)
        run_git("remote", "add", "origin", repo_url, check=False)
        print(f"  New branch: {branch}")
    else:
        # Remove any existing blobs >90MB to avoid GitLab 100MB limit on re-push.
        _remove_oversized_blobs(work_dir)
        print(f"  Merging into existing branch: {branch}")

    run_git("config", "user.email", "ai-scientist@noreply.local")
    run_git("config", "user.name", "AI Scientist")

    # Copy staged artifacts into the working directory.
    for root, dirs, files in os.walk(staging):
        for fname in files:
            src = os.path.join(root, fname)
            rel = os.path.relpath(src, staging)
            dst = os.path.join(work_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    run_git("add", "-A")

    # Check if there's anything to commit.
    status = run_git("status", "--porcelain")
    if not status.stdout.strip():
        print(f"  No new changes for {job_name}")
        return True  # Not an error — just nothing new.

    run_git("commit", "-m", f"Add agent_trace + reviewer_trace for {job_name}")

    result = run_git("push", "-u", "origin", branch, check=False)
    if result.returncode != 0:
        print(f"  Push failed: {result.stderr}", file=sys.stderr)
        return False

    return True


def _remove_oversized_blobs(work_dir: str, max_mb: int = 90) -> None:
    """Remove files larger than max_mb from the working directory to avoid push limits."""
    max_bytes = max_mb * 1024 * 1024
    for root, dirs, files in os.walk(work_dir):
        # Skip .git directory.
        if ".git" in root.split(os.sep):
            continue
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                if os.path.getsize(fpath) > max_bytes:
                    rel = os.path.relpath(fpath, work_dir)
                    print(f"  Removing oversized file ({os.path.getsize(fpath) // (1024*1024)}MB): {rel}")
                    os.remove(fpath)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Main push logic
# ---------------------------------------------------------------------------

def push_job(job_dir: str, dry_run: bool = False) -> dict:
    """Push a single job's artifacts to GitLab.

    Returns a dict with push status info.
    """
    job_dir = os.path.abspath(job_dir)
    job_name = os.path.basename(os.path.normpath(job_dir))
    idea_stem, ts_raw = parse_job_id(job_dir)

    if not idea_stem:
        return {"job": job_name, "status": "skipped", "reason": "no idea stem in name"}

    # Read configs.
    task_dir = find_harbor_task_dir(job_dir)
    if not task_dir:
        return {"job": job_name, "status": "skipped", "reason": "no harbor-task dir"}

    config = read_json(os.path.join(job_dir, "config.json"))
    result_data = read_json(os.path.join(job_dir, "result.json"))
    agent_type = detect_agent_type(config)
    agent_short = agent_type.replace("-cli", "").replace("-code", "")

    # Format timestamp for branch name: YYYY-MM-DD-HH-MM.
    ts_formatted = ts_raw  # Already YYYY-MM-DD-HH-MM-SS from parse_job_id
    if ts_formatted:
        # Convert to the gitlab_setup format: YYYY-MM-DD-HH-MM
        parts = ts_formatted.split("-")
        if len(parts) >= 5:
            ts_formatted = "-".join(parts[:5])  # Drop seconds

    branch = f"{agent_short}-{ts_formatted}"
    repo_name = idea_stem.replace("_", "-")

    token = os.environ.get("GITLAB_KEY", "")
    if not token:
        return {"job": job_name, "status": "error", "reason": "GITLAB_KEY not set"}

    print(f"Processing {job_name}...")
    print(f"  Repo: {repo_name}, Branch: {branch}")

    if dry_run:
        # Stage to temp dir but don't push.
        sanitizer = SecretSanitizer()
        with tempfile.TemporaryDirectory(prefix="gitlab-push-") as staging:
            figures, has_paper, sub_count = stage_artifacts(
                job_dir, task_dir, staging, sanitizer
            )

            # Generate summary and metadata in agent_trace/.
            agents = config.get("agents", [{}])
            model = agents[0].get("model_name", "") if agents else ""
            summary = generate_trajectory_summary(job_dir, config, model)
            at_dir = os.path.join(staging, "agent_trace")
            os.makedirs(at_dir, exist_ok=True)
            if summary:
                with open(os.path.join(at_dir, "trajectory_summary.json"), "w") as f:
                    json.dump(summary, f)
                with open(os.path.join(at_dir, "metadata.json"), "w") as f:
                    json.dump({}, f)  # Placeholder for listing

            # List staged files.
            staged = []
            for root, dirs, files in os.walk(staging):
                for fname in files:
                    rel = os.path.relpath(os.path.join(root, fname), staging)
                    staged.append(rel)

            print(f"  [DRY RUN] Would push {len(staged)} files:")
            for fname in sorted(staged):
                print(f"    {fname}")
            print(f"  Figures: {figures}")
            print(f"  Has paper: {has_paper}")
            print(f"  Submissions: {sub_count}")
            if summary:
                print(f"  Events: {summary['total_events']}, Cost: ${summary['cost'].get('estimated_cost_usd', '?')}")

        return {"job": job_name, "status": "dry_run", "branch": branch, "files": staged}

    # Real push.
    try:
        username = get_username(token)
    except Exception as e:
        return {"job": job_name, "status": "error", "reason": f"GitLab auth failed: {e}"}

    try:
        project = ensure_repo(token, username, repo_name)
    except Exception as e:
        return {"job": job_name, "status": "error", "reason": f"Repo creation failed: {e}"}

    repo_url = f"https://oauth2:{token}@gitlab.com/{username}/{repo_name}.git"
    web_url = project.get("web_url", f"https://gitlab.com/{username}/{repo_name}")

    sanitizer = SecretSanitizer()

    with tempfile.TemporaryDirectory(prefix="gitlab-push-") as staging:
        figures, has_paper, sub_count = stage_artifacts(
            job_dir, task_dir, staging, sanitizer
        )

        # Generate trajectory summary.
        agents = config.get("agents", [{}])
        model = agents[0].get("model_name", "") if agents else ""
        summary = generate_trajectory_summary(job_dir, config, model)

        # Generate metadata.json inside agent_trace/.
        at_dir = os.path.join(staging, "agent_trace")
        os.makedirs(at_dir, exist_ok=True)
        metadata = generate_metadata(
            job_dir, config, result_data, idea_stem, agent_type,
            branch, figures, has_paper, sub_count,
            cost_data=summary["cost"] if summary else None,
        )
        with open(os.path.join(at_dir, "metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2)

        # Write trajectory summary inside agent_trace/.
        if summary:
            with open(os.path.join(at_dir, "trajectory_summary.json"), "w") as f:
                json.dump(summary, f, indent=2)

        # Push.
        success = git_push(staging, repo_url, branch, job_name)

    if success:
        print(f"  Pushed to {web_url}/-/tree/{branch}")
        return {
            "job": job_name,
            "status": "pushed",
            "branch": branch,
            "web_url": f"{web_url}/-/tree/{branch}",
        }
    else:
        return {"job": job_name, "status": "error", "reason": "git push failed"}


def backfill(jobs_dir: str, dry_run: bool = False) -> List[dict]:
    """Push all completed jobs that haven't been pushed yet."""
    results = []
    if not os.path.isdir(jobs_dir):
        print(f"Jobs directory not found: {jobs_dir}", file=sys.stderr)
        return results

    for entry in sorted(os.listdir(jobs_dir)):
        job_dir = os.path.join(jobs_dir, entry)
        if not os.path.isdir(job_dir):
            continue

        idea_stem, _ = parse_job_id(job_dir)
        if not idea_stem:
            print(f"Skipping {entry}: no idea stem")
            continue

        # Check if job has finished (result.json with finished_at).
        result_data = read_json(os.path.join(job_dir, "result.json"))
        if not result_data.get("finished_at"):
            print(f"Skipping {entry}: not finished")
            continue

        result = push_job(job_dir, dry_run=dry_run)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Push sanitized job artifacts to GitLab"
    )
    parser.add_argument("--job-dir", help="Path to a single job directory")
    parser.add_argument("--backfill", action="store_true", help="Push all completed, unpushed jobs")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be pushed without actually pushing")
    parser.add_argument("--jobs-dir", default=str(REPO_ROOT / "jobs"), help="Jobs root directory (for --backfill)")
    args = parser.parse_args()

    if not args.job_dir and not args.backfill:
        parser.error("Either --job-dir or --backfill is required")

    if args.job_dir:
        if not os.path.isdir(args.job_dir):
            print(f"Error: {args.job_dir} not found", file=sys.stderr)
            sys.exit(1)
        result = push_job(args.job_dir, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] in ("pushed", "dry_run") else 1)

    if args.backfill:
        results = backfill(args.jobs_dir, dry_run=args.dry_run)
        print(f"\n{'='*60}")
        print(f"Backfill complete: {len(results)} jobs processed")
        for r in results:
            print(f"  {r['job']}: {r['status']}")


if __name__ == "__main__":
    main()
