"""AI Scientist v3 — Live Job Viewer. FastAPI backend + serves HTML templates."""

import argparse
import asyncio
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from parse_trajectory import (
    ParseResult,
    compute_cumulative_tokens,
    compute_event_type_breakdown,
    compute_tool_breakdown,
    detect_and_parse,
    estimate_cost,
    find_agent_activity_path,
    find_artifacts_dir,
    find_trajectory_path,
    mask_secrets,
    mask_secrets_in_text,
)
from gitlab_client import GitLabClient

app = FastAPI(title="AI Scientist v3 — Job Viewer")

# Global config — set by CLI args
JOBS_DIR = "./jobs"
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
HARBOR_PYTHON = "/home/alex/.local/share/uv/tools/harbor/bin/python3"
GENERATE_ATIF_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "backfill_trajectory.py")
# Parsed event/cache metadata per job to keep /api/jobs fast across refreshes.
JOB_PARSE_CACHE: Dict[str, dict] = {}
JOB_METRICS_CACHE: Dict[str, dict] = {}
JOBS_LIST_CACHE: Dict[str, Any] = {
    "jobs_dir": None,
    "expires_at": 0.0,
    "payload": None,
}
JOBS_LIST_CACHE_TTL_SEC = 15.0

# GitLab client — initialized if GITLAB_KEY is set.
GITLAB_CLIENT: Optional[GitLabClient] = None
# Maps job_id -> (project_id, branch) for GitLab-backed jobs.
GITLAB_JOB_MAP: Dict[str, Tuple[int, str]] = {}
IDEA_NAME_PATTERNS = [
    re.compile(r'"Name"\s*:\s*"([^"]+)"'),
    re.compile(r'\\"Name\\"\s*:\s*\\"([^"\\]+)\\"'),
]


# ---------------------------------------------------------------------------
# ATIF trajectory generation
# ---------------------------------------------------------------------------

def find_agent_dir(job_dir: str) -> Optional[str]:
    """Find the agent directory inside a job."""
    if not os.path.isdir(job_dir):
        return None
    for entry in os.listdir(job_dir):
        if entry.startswith("harbor-task"):
            agent_dir = os.path.join(job_dir, entry, "agent")
            if os.path.isdir(agent_dir):
                return agent_dir
    return None


def generate_trajectory(job_dir: str) -> Optional[str]:
    """Generate ATIF trajectory.json via the wrapper script. Returns path or None."""
    agent_dir = find_agent_dir(job_dir)
    if not agent_dir:
        return None

    traj_path = os.path.join(agent_dir, "trajectory.json")

    # Skip if trajectory is fresh (< 60s old)
    if os.path.exists(traj_path):
        try:
            age = time.time() - os.path.getmtime(traj_path)
            if age < 60:
                return traj_path
        except OSError:
            pass

    if not os.path.isfile(HARBOR_PYTHON) or not os.path.isfile(GENERATE_ATIF_SCRIPT):
        return traj_path if os.path.exists(traj_path) else None

    try:
        subprocess.run(
            [HARBOR_PYTHON, GENERATE_ATIF_SCRIPT, "--job-dir", job_dir],
            capture_output=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass

    return traj_path if os.path.exists(traj_path) else None


# ---------------------------------------------------------------------------
# Job discovery
# ---------------------------------------------------------------------------

def read_config(job_dir: str) -> dict:
    """Read config.json from a job directory."""
    cfg_path = os.path.join(job_dir, "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _extract_idea_stem(job_name: str) -> Optional[str]:
    """Extract idea stem from '<stem>__YYYY-MM-DD__HH-MM-SS' naming."""
    if not job_name:
        return None
    m = re.match(r"^(.+?)__\d{4}-\d{2}-\d{2}__\d{2}-\d{2}-\d{2}$", job_name)
    if not m:
        return None
    stem = m.group(1).strip("_")
    # Legacy names like '2026-02-21__20-39-12' should not map to idea_2026-02-21.json.
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stem):
        return None
    return stem or None


def _idea_path_candidates(stem: str) -> List[str]:
    return [
        os.path.join(REPO_ROOT, f"idea_{stem}.json"),
        os.path.join(REPO_ROOT, "ideas", f"idea_{stem}.json"),
        os.path.join(REPO_ROOT, f"{stem}.json"),
        os.path.join(REPO_ROOT, "ideas", f"{stem}.json"),
    ]


def _iter_idea_files() -> List[str]:
    base = Path(REPO_ROOT)
    files = list(base.glob("idea_*.json")) + list((base / "ideas").glob("idea_*.json"))
    return [str(p) for p in sorted(files)]


def _extract_idea_name_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    for pat in IDEA_NAME_PATTERNS:
        m = pat.search(text)
        if m:
            name = (m.group(1) or "").strip()
            if name:
                return name
    return None


def _read_head(path: str, limit: int = 600_000) -> str:
    try:
        with open(path, "r", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return ""


def _extract_idea_name_from_job_artifacts(job_dir: str) -> Optional[str]:
    """Best-effort inference for legacy jobs lacking idea stem in job_id."""
    if not job_dir or not os.path.isdir(job_dir):
        return None

    # Prefer command input snapshots if available (smaller and direct).
    for entry in sorted(os.listdir(job_dir)):
        if not entry.startswith("harbor-task"):
            continue
        cmd_root = Path(job_dir) / entry / "agent"
        for cmd_txt in sorted(cmd_root.glob("command-*/command.txt")):
            name = _extract_idea_name_from_text(_read_head(str(cmd_txt), limit=250_000))
            if name:
                return name

    # Fallback to trajectory content.
    traj_path = find_trajectory_path(job_dir)
    if traj_path:
        name = _extract_idea_name_from_text(_read_head(traj_path))
        if name:
            return name
    return None


def resolve_idea_file(job_id: str, config: dict, job_dir: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Resolve idea JSON by job-name stem, then legacy artifact inference."""
    stems: List[str] = []
    for candidate in [job_id, str(config.get("job_name", ""))]:
        stem = _extract_idea_stem(candidate)
        if stem and stem not in stems:
            stems.append(stem)

    for stem in stems:
        for path in _idea_path_candidates(stem):
            if os.path.isfile(path):
                return stem, path

    inferred_name = _extract_idea_name_from_job_artifacts(job_dir or "")
    if inferred_name:
        for path in _idea_path_candidates(inferred_name):
            if os.path.isfile(path):
                return inferred_name, path

        # Fallback: match by JSON `Name` field in idea files.
        for path in _iter_idea_files():
            try:
                with open(path) as f:
                    data = json.load(f)
                if str(data.get("Name", "")).strip() == inferred_name:
                    return inferred_name, path
            except (json.JSONDecodeError, OSError):
                continue

    return inferred_name or (stems[0] if stems else None), None


def load_idea_payload(job_id: str, config: dict, job_dir: Optional[str] = None) -> dict:
    """Load pretty JSON text for the job's original idea input."""
    stem, path = resolve_idea_file(job_id, config, job_dir=job_dir)
    if not stem or not path:
        return {"found": False, "stem": stem, "source": None, "content": None, "format": None}

    source = os.path.relpath(path, REPO_ROOT)
    try:
        with open(path) as f:
            parsed = json.load(f)
        text = json.dumps(parsed, indent=2)
        return {
            "found": True,
            "stem": stem,
            "source": source,
            "content": mask_secrets_in_text(text),
            "format": "json",
        }
    except (json.JSONDecodeError, OSError):
        try:
            with open(path, "r", errors="replace") as f:
                text = f.read()
            return {
                "found": True,
                "stem": stem,
                "source": source,
                "content": mask_secrets_in_text(text),
                "format": "text",
            }
        except OSError:
            return {"found": False, "stem": stem, "source": source, "content": None, "format": None}


def get_job_status(job_dir: str) -> str:
    """Determine if a job is running, completed, or failed."""
    activity_path = find_agent_activity_path(job_dir)
    if not activity_path:
        return "unknown"

    # Check mtime — if modified < 5 min ago → running
    try:
        mtime = os.path.getmtime(activity_path)
        age = time.time() - mtime
        if age < 300:  # 5 minutes
            return "running"
    except OSError:
        return "unknown"

    # Check for result.json in verifier
    for entry in os.listdir(job_dir):
        if entry.startswith("harbor-task"):
            result_path = os.path.join(job_dir, entry, "verifier", "artifacts", "result.json")
            if os.path.exists(result_path):
                return "completed"
            # Check for any verifier output indicating completion
            verifier_dir = os.path.join(job_dir, entry, "verifier")
            if os.path.isdir(verifier_dir):
                return "completed"

    return "idle"


def get_submission_count(job_dir: str) -> int:
    """Count submissions from version_log.json."""
    best = 0
    for root in iter_submission_roots(job_dir):
        vlog = os.path.join(root, "version_log.json")
        try:
            with open(vlog) as f:
                data = json.load(f)
            count = data.get("current_version", len(data.get("versions", [])))
            if isinstance(count, int):
                best = max(best, count)
        except (json.JSONDecodeError, OSError):
            continue
    if best:
        return best
    return 0


def _parse_iso8601(ts: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp used in Harbor artifacts."""
    if not ts or not isinstance(ts, str):
        return None
    normalized = ts.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_job_duration_seconds(job_dir: str, status: str) -> Optional[int]:
    """Best-effort wall-clock duration based on result timestamps."""
    candidates = [os.path.join(job_dir, "result.json")]
    try:
        for entry in os.listdir(job_dir):
            if entry.startswith("harbor-task"):
                candidates.append(os.path.join(job_dir, entry, "verifier", "artifacts", "result.json"))
    except OSError:
        pass

    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                payload = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        started = _parse_iso8601(payload.get("started_at"))
        finished = _parse_iso8601(payload.get("finished_at"))
        if not started:
            continue

        if finished and finished >= started:
            return int((finished - started).total_seconds())
        if status == "running":
            now = datetime.now(timezone.utc)
            if now >= started:
                return int((now - started).total_seconds())

    return None


def get_model_name(config: dict) -> str:
    """Extract model name from config."""
    agents = config.get("agents", [])
    if agents:
        model = agents[0].get("model_name", "")
        # Shorten: "anthropic/claude-opus-4-6" → "opus-4-6"
        if "/" in model:
            model = model.split("/")[-1]
        return model.replace("claude-", "")
    return "unknown"


def resolve_cost_model(config: dict, parsed_model: Optional[str]) -> str:
    """Pick the most reliable model identifier for pricing."""
    cfg_model = config.get("agents", [{}])[0].get("model_name")
    return cfg_model or parsed_model or "claude-opus-4-6"


def load_job_events(job_dir: str, after_line: int = 0, allow_backfill: bool = False) -> ParseResult:
    """Load parsed events, preferring Harbor trajectory and backfilling if needed."""
    result = detect_and_parse(job_dir, after_line=after_line)
    if result.events or result.total_lines > 0 or not allow_backfill:
        return result

    # Fallback: if trajectory is missing or stale for a new job, try generating it once.
    generate_trajectory(job_dir)
    return detect_and_parse(job_dir, after_line=after_line)


def _build_activity_cache_key(job_dir: str) -> Optional[tuple]:
    """Stable cache key for a job's active transcript/trajectory."""
    activity_path = find_agent_activity_path(job_dir)
    if not activity_path:
        return None
    try:
        st = os.stat(activity_path)
        return (activity_path, st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def get_job_metrics(
    job_dir: str,
    config: dict,
    allow_backfill: bool = True,
    parsed: Optional[ParseResult] = None,
) -> dict:
    """Return cached per-job token/cost/breakdown metrics."""
    cache_key = _build_activity_cache_key(job_dir)
    cached = JOB_METRICS_CACHE.get(job_dir)
    if cached and cached.get("cache_key") == cache_key:
        return cached.get("data", {})

    result = parsed or load_job_events(job_dir, allow_backfill=allow_backfill)
    model_for_cost = resolve_cost_model(config, result.model)
    data = {
        "cost": estimate_cost(result.events, model=model_for_cost),
        "cumulative_tokens": compute_cumulative_tokens(result.events),
        "tool_breakdown": compute_tool_breakdown(result.events),
        "event_type_breakdown": compute_event_type_breakdown(result.events),
        "total_lines": result.total_lines,
        "model": result.model,
    }
    JOB_METRICS_CACHE[job_dir] = {"cache_key": cache_key, "data": data}
    return data


def iter_submission_roots(job_dir: str) -> List[str]:
    """Return all submissions roots found under verifier/agent artifacts."""
    roots: List[str] = []
    if not os.path.isdir(job_dir):
        return roots

    try:
        for entry in os.listdir(job_dir):
            if not entry.startswith("harbor-task"):
                continue
            for sub in ["verifier", "agent"]:
                root = os.path.join(job_dir, entry, sub, "artifacts", "submissions")
                vlog = os.path.join(root, "version_log.json")
                if os.path.isdir(root) and os.path.exists(vlog):
                    roots.append(root)
    except OSError:
        return roots
    return roots


def _split_review_rebuttal(md: str) -> Tuple[str, Optional[str]]:
    """Extract review/rebuttal markdown sections from response.md."""
    text = md or ""
    if not text.strip():
        return "", None

    # Normalize line endings and split on headings if present.
    normalized = text.replace("\r\n", "\n")
    parts = re.split(r"(?im)^\s*##\s*Rebuttal\s*$", normalized, maxsplit=1)
    review_part = parts[0]
    review_part = re.sub(r"(?im)^\s*##\s*Review\s*$", "", review_part, count=1).strip()
    rebuttal_part = parts[1].strip() if len(parts) > 1 else None
    return review_part, rebuttal_part


def _safe_submission_dir_name(name: str) -> bool:
    if not name or "/" in name or "\\" in name:
        return False
    if name in {".", ".."} or ".." in name:
        return False
    return True


def build_submission_records(job_dir: str, job_id: str) -> List[dict]:
    """Collect submission versions across all artifacts roots."""
    records: Dict[str, dict] = {}

    for root in iter_submission_roots(job_dir):
        vlog_path = os.path.join(root, "version_log.json")
        try:
            with open(vlog_path) as f:
                vlog = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        for ver in vlog.get("versions", []):
            directory = str(ver.get("directory", "")).strip()
            if not _safe_submission_dir_name(directory):
                continue
            v_dir = os.path.join(root, directory)
            review_md = ver.get("reviewer_preview", ver.get("reviewer_question_preview", "")) or ""
            rebuttal_md = None

            resp_md = os.path.join(v_dir, "reviewer_communications", "response.md")
            resp_json = os.path.join(v_dir, "reviewer_communications", "response.json")

            if os.path.exists(resp_md):
                try:
                    with open(resp_md) as f:
                        review_md, rebuttal_md = _split_review_rebuttal(f.read())
                except OSError:
                    pass
            elif os.path.exists(resp_json):
                try:
                    with open(resp_json) as f:
                        resp = json.load(f)
                    review_md = resp.get("question", review_md) or review_md
                    rebuttal_md = resp.get("rebuttal")
                except (json.JSONDecodeError, OSError):
                    pass

            has_pdf = os.path.exists(os.path.join(v_dir, "paper.pdf"))
            has_tex = bool(ver.get("paper_tex", False) or os.path.exists(os.path.join(v_dir, "paper.tex")))
            figures_count = 0
            fig_dir = os.path.join(v_dir, "figures")
            if os.path.isdir(fig_dir):
                figures_count = len([f for f in os.listdir(fig_dir) if f.endswith(".png")])

            record = {
                "version": ver.get("version"),
                "timestamp": ver.get("timestamp"),
                "directory": directory,
                "review": mask_secrets_in_text(review_md or ""),
                "review_markdown": mask_secrets_in_text(review_md or ""),
                "rebuttal": mask_secrets_in_text(rebuttal_md or "") if rebuttal_md else None,
                "rebuttal_markdown": mask_secrets_in_text(rebuttal_md or "") if rebuttal_md else None,
                "has_pdf": has_pdf,
                "paper_url": f"/api/jobs/{job_id}/submissions/{directory}/paper" if has_pdf else None,
                "has_tex": has_tex,
                "has_experiments": bool(ver.get("has_experiments", False)),
                "has_figures": bool(ver.get("has_figures", False) or figures_count > 0),
                "figures_count": figures_count,
                "reviewer_mode": ver.get("reviewer_mode", "api"),
            }

            prev = records.get(directory)
            if not prev:
                records[directory] = record
            else:
                prev_score = (
                    (1 if prev.get("has_pdf") else 0)
                    + len(prev.get("review_markdown", "") or "")
                    + len(prev.get("rebuttal_markdown", "") or "")
                )
                new_score = (
                    (1 if record.get("has_pdf") else 0)
                    + len(record.get("review_markdown", "") or "")
                    + len(record.get("rebuttal_markdown", "") or "")
                )
                if new_score >= prev_score:
                    records[directory] = record

    submissions = list(records.values())
    # Show newest first where possible.
    submissions.sort(
        key=lambda r: (
            r.get("version") if isinstance(r.get("version"), int) else -1,
            r.get("timestamp") or "",
        ),
        reverse=True,
    )
    return submissions


def _is_gitlab_backed(job_id: str) -> bool:
    """Check if a job has pre-computed data on GitLab."""
    return GITLAB_CLIENT is not None and job_id in GITLAB_JOB_MAP


def _gitlab_lookup(job_id: str) -> Optional[Tuple[int, str]]:
    """Return (project_id, branch) for a GitLab-backed job, or None."""
    if not _is_gitlab_backed(job_id):
        return None
    return GITLAB_JOB_MAP.get(job_id)


def discover_jobs() -> list:
    """Scan jobs directory and return job metadata.

    If a GitLab client is configured, also includes completed jobs from GitLab.
    GitLab jobs that also exist locally are merged (local data takes priority for
    running jobs; GitLab data used for completed jobs to avoid re-parsing).
    """
    jobs = []
    if not os.path.isdir(JOBS_DIR):
        return jobs

    job_entries = []
    for name in os.listdir(JOBS_DIR):
        job_dir = os.path.join(JOBS_DIR, name)
        if not os.path.isdir(job_dir):
            continue
        try:
            mtime = os.path.getmtime(job_dir)
        except OSError:
            mtime = 0
        job_entries.append((name, job_dir, mtime))
    job_entries.sort(key=lambda x: x[2], reverse=True)

    # Pre-fetch all GitLab metadata in parallel to avoid sequential API calls.
    gl_entries = [(name, job_dir) for name, job_dir, _ in job_entries if _is_gitlab_backed(name)]
    gl_data: Dict[str, Tuple[Optional[dict], Optional[dict]]] = {}
    if gl_entries and GITLAB_CLIENT:
        from concurrent.futures import ThreadPoolExecutor

        def _fetch_gl(name):
            pid, branch = GITLAB_JOB_MAP[name]
            meta = GITLAB_CLIENT.get_metadata(pid, branch)
            summary = GITLAB_CLIENT.get_trajectory_summary(pid, branch)
            return name, meta, summary

        with ThreadPoolExecutor(max_workers=min(10, len(gl_entries))) as pool:
            for result_name, meta, summary in pool.map(_fetch_gl, [n for n, _ in gl_entries]):
                gl_data[result_name] = (meta, summary)

    for idx, (name, job_dir, _) in enumerate(job_entries):

        # Fast path: for GitLab-backed completed jobs, skip ALL local disk I/O.
        if name in gl_data:
            gl_meta, gl_summary = gl_data[name]
            if gl_meta and gl_meta.get("job_id"):
                gl_model = gl_meta.get("model", "unknown")
                if "/" in gl_model:
                    gl_model = gl_model.split("/")[-1]
                gl_model = gl_model.replace("claude-", "")
                jobs.append({
                    "id": name,
                    "dir": job_dir,
                    "status": gl_meta.get("status", "completed"),
                    "duration_seconds": gl_meta.get("duration_seconds"),
                    "model": gl_model,
                    "line_count": gl_summary.get("total_lines", 0) if gl_summary else 0,
                    "file_size_mb": 0,
                    "submissions": gl_meta.get("submission_count", 0),
                    "tokens": gl_summary.get("cost") if gl_summary else None,
                    "task_name": gl_meta.get("idea_name", name).replace("_", " ").title(),
                })
                continue  # Skip all local disk I/O for this job.

        # Slow path: local disk I/O for jobs not on GitLab (running, legacy, etc.)
        config = read_config(job_dir)
        status = get_job_status(job_dir)
        duration_seconds = get_job_duration_seconds(job_dir, status)
        activity_path = find_agent_activity_path(job_dir)

        line_count = 0
        file_size = 0
        task_name = config.get("job_name", name)
        token_summary = None
        parsed_model = None
        cache_key = _build_activity_cache_key(job_dir)

        if cache_key:
            file_size = cache_key[2]

        cached = JOB_PARSE_CACHE.get(job_dir)
        if cached and cached.get("cache_key") == cache_key:
            line_count = cached.get("line_count", 0)
            token_summary = cached.get("token_summary")
            task_name = cached.get("task_name", task_name)
            parsed_model = cached.get("parsed_model")
        else:
            # Only parse trajectories for running jobs on the dashboard.
            # Completed jobs get their metrics from the job detail page or GitLab.
            # The old heuristic (idx < 8) parsed massive files (100MB+) for
            # completed jobs that happened to be recent, causing multi-second loads.
            should_parse_detail = status == "running"
            if should_parse_detail:
                result = load_job_events(job_dir)
                if result.events:
                    metrics = get_job_metrics(job_dir, config, allow_backfill=False, parsed=result)
                    token_summary = metrics.get("cost")
                    line_count = result.total_lines or line_count
                    parsed_model = result.model
                    for ev in result.events[:10]:
                        if ev.source in {"agent", "user"} and ev.event_type in {"text", "user_message"} and len(ev.summary) > 20:
                            task_name = ev.summary[:80]
                            break

            if activity_path and not line_count and not activity_path.endswith("trajectory.json"):
                # Approximate line count from file size instead of reading the
                # entire file (claude-code.txt can be 150MB+).
                try:
                    line_count = max(1, os.path.getsize(activity_path) // 500)
                except OSError:
                    pass

            JOB_PARSE_CACHE[job_dir] = {
                "cache_key": cache_key,
                "line_count": line_count,
                "token_summary": token_summary,
                "task_name": task_name,
                "parsed_model": parsed_model,
            }

        model_name = get_model_name(config)
        if model_name == "unknown" and parsed_model:
            model_name = str(parsed_model).split("/")[-1].replace("claude-", "")

        # Defer submission count for non-running jobs (disk I/O per job).
        sub_count = get_submission_count(job_dir) if status == "running" else 0

        jobs.append({
            "id": name,
            "dir": job_dir,
            "status": status,
            "duration_seconds": duration_seconds,
            "model": model_name,
            "line_count": line_count,
            "file_size_mb": round(file_size / 1_000_000, 1),
            "submissions": sub_count,
            "tokens": token_summary,
            "task_name": mask_secrets_in_text(task_name),
        })

    # Note: GitLab-only jobs (no local dir) are rare in practice.  The job map
    # is populated at startup by _init_gitlab_client; we don't re-discover here
    # to avoid a 3-4s API round-trip on every dashboard refresh.

    return jobs


def discover_job_meta(job_id: str) -> Optional[dict]:
    """Load lightweight metadata for a single job detail page."""
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return None

    config = read_config(job_dir)
    status = get_job_status(job_dir)
    duration_seconds = get_job_duration_seconds(job_dir, status)
    submissions = get_submission_count(job_dir)
    model_name = get_model_name(config)

    if model_name == "unknown":
        metrics = get_job_metrics(job_dir, config, allow_backfill=True)
        parsed_model = metrics.get("model")
        if parsed_model:
            model_name = str(parsed_model).split("/")[-1].replace("claude-", "")

    return {
        "id": job_id,
        "status": status,
        "duration_seconds": duration_seconds,
        "model": model_name,
        "submissions": submissions,
    }


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard HTML."""
    template_path = os.path.join(TEMPLATES_DIR, "index.html")
    with open(template_path) as f:
        return HTMLResponse(f.read())


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_detail(job_id: str):
    """Serve the job detail HTML."""
    template_path = os.path.join(TEMPLATES_DIR, "job.html")
    with open(template_path) as f:
        html = f.read()
    # Inject job_id into the template
    html = html.replace("{{JOB_ID}}", job_id)
    return HTMLResponse(html)


@app.get("/api/jobs")
async def api_jobs():
    """Return JSON list of all jobs with summary stats."""
    now = time.time()
    cached = JOBS_LIST_CACHE
    if (
        cached.get("jobs_dir") == JOBS_DIR
        and cached.get("payload") is not None
        and now < float(cached.get("expires_at", 0.0))
    ):
        return JSONResponse(mask_secrets(cached["payload"]))

    payload = discover_jobs()
    JOBS_LIST_CACHE.update({
        "jobs_dir": JOBS_DIR,
        "payload": payload,
        "expires_at": now + JOBS_LIST_CACHE_TTL_SEC,
    })
    return JSONResponse(mask_secrets(payload))


@app.get("/api/jobs/{job_id}/meta")
async def api_job_meta(job_id: str):
    """Return lightweight metadata for one job."""
    # Try GitLab first.
    gl = _gitlab_lookup(job_id)
    if gl:
        project_id, branch = gl
        gl_meta = GITLAB_CLIENT.get_metadata(project_id, branch)
        if gl_meta:
            model = gl_meta.get("model", "unknown")
            if "/" in model:
                model = model.split("/")[-1]
            model = model.replace("claude-", "")
            return JSONResponse({
                "id": job_id,
                "status": gl_meta.get("status", "completed"),
                "duration_seconds": gl_meta.get("duration_seconds"),
                "model": model,
                "submissions": gl_meta.get("submission_count", 0),
            })

    # Fallback to local disk.
    meta = discover_job_meta(job_id)
    if not meta:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return JSONResponse(mask_secrets(meta))


@app.get("/api/jobs/{job_id}/events")
async def api_events(job_id: str, after: int = 0):
    """Return JSON events, optionally starting from line N."""
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

    result = load_job_events(job_dir, after_line=after, allow_backfill=True)
    return JSONResponse({
        "events": mask_secrets([e.to_dict() for e in result.events]),
        "total_lines": result.total_lines,
        "session_id": result.session_id,
        "model": result.model,
    })


@app.get("/api/jobs/{job_id}/stream")
async def stream_events(job_id: str, after: int = 0):
    """SSE stream: polls parsed trajectory/events every 2 seconds, yields new events."""
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

    activity_path = find_agent_activity_path(job_dir)
    if not activity_path:
        generate_trajectory(job_dir)
        activity_path = find_agent_activity_path(job_dir)
    if not activity_path:
        return JSONResponse({"error": "No trajectory or transcript found"}, status_code=404)

    async def event_generator():
        last_line = after
        config = read_config(job_dir)
        tick = 0

        while True:
            result = load_job_events(job_dir, after_line=last_line, allow_backfill=True)
            for event in result.events:
                yield {
                    "event": "new_event",
                    "data": json.dumps(mask_secrets(event.to_dict())),
                }
            if result.events:
                last_line = result.total_lines

            # Full metrics are expensive on large trajectories; refresh less frequently.
            if tick == 0 or result.events or tick % 3 == 0:
                metrics = get_job_metrics(job_dir, config, allow_backfill=True)
                cumulative = metrics.get("cumulative_tokens") or []
                yield {
                    "event": "metrics",
                    "data": json.dumps(mask_secrets({
                        "cost": metrics.get("cost"),
                        "cumulative_tokens": cumulative[-5:] if cumulative else [],  # last 5 for chart update
                        "tool_breakdown": metrics.get("tool_breakdown") or [],
                        "event_type_breakdown": metrics.get("event_type_breakdown") or [],
                        "total_lines": metrics.get("total_lines", result.total_lines),
                    })),
                }

            # Regenerate ATIF trajectory every ~60s for running jobs
            tick += 1
            if tick % 30 == 0:
                generate_trajectory(job_dir)

            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())


@app.get("/api/jobs/{job_id}/tokens")
async def api_tokens(job_id: str):
    """Token usage summary and per-step breakdown."""
    # Try GitLab first for completed jobs (pre-computed, instant).
    gl = _gitlab_lookup(job_id)
    if gl:
        project_id, branch = gl
        summary = GITLAB_CLIENT.get_trajectory_summary(project_id, branch)
        if summary:
            return JSONResponse({
                "cost": summary.get("cost"),
                "cumulative_tokens": summary.get("cumulative_tokens") or [],
                "tool_breakdown": summary.get("tool_breakdown") or [],
                "event_type_breakdown": summary.get("event_type_breakdown") or [],
            })

    # Fallback to local disk.
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

    config = read_config(job_dir)
    metrics = get_job_metrics(job_dir, config, allow_backfill=True)

    return JSONResponse(mask_secrets({
        "cost": metrics.get("cost"),
        "cumulative_tokens": metrics.get("cumulative_tokens") or [],
        "tool_breakdown": metrics.get("tool_breakdown") or [],
        "event_type_breakdown": metrics.get("event_type_breakdown") or [],
    }))


@app.get("/api/jobs/{job_id}/idea")
async def api_job_idea(job_id: str):
    """Return original idea JSON matched by job stem."""
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

    config = read_config(job_dir)
    return JSONResponse(load_idea_payload(job_id, config, job_dir=job_dir))


@app.get("/api/jobs/{job_id}/submissions")
async def api_submissions(job_id: str):
    """Read submission versions with markdown review/rebuttal and paper links."""
    # Try GitLab for completed jobs (version_log + response.md per version).
    gl = _gitlab_lookup(job_id)
    if gl:
        project_id, branch = gl
        vlog = GITLAB_CLIENT.get_file_json(project_id, branch, "reviewer_trace/version_log.json")
        if vlog and vlog.get("versions"):
            versions = vlog["versions"]

            # Fetch all response.md files in parallel to avoid N sequential API calls.
            from concurrent.futures import ThreadPoolExecutor
            def _fetch_response(vdir):
                if not vdir:
                    return None
                data = GITLAB_CLIENT.get_file_raw(project_id, branch, f"reviewer_trace/{vdir}/response.md")
                return data.decode("utf-8", errors="replace") if data else None

            with ThreadPoolExecutor(max_workers=min(8, len(versions))) as pool:
                resp_texts = list(pool.map(_fetch_response, [v.get("directory", "") for v in versions]))

            submissions = []
            for v, resp_text in zip(versions, resp_texts):
                vdir = v.get("directory", "")
                review_md = ""
                rebuttal_md = None
                if resp_text:
                    review_md, rebuttal_md = _split_review_rebuttal(resp_text)
                submissions.append({
                    "version": v.get("version"),
                    "timestamp": v.get("timestamp"),
                    "directory": vdir,
                    "reviewer_mode": v.get("reviewer_mode"),
                    "review_markdown": review_md,
                    "rebuttal_markdown": rebuttal_md,
                    "paper_url": f"/api/jobs/{job_id}/submissions/{vdir}/paper" if vdir else None,
                })
            submissions.sort(key=lambda r: (r.get("version") or -1, r.get("timestamp") or ""), reverse=True)
            return JSONResponse({"submissions": submissions, "total": len(submissions)})

    # Fallback to local disk.
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

    submissions = build_submission_records(job_dir, job_id)
    return JSONResponse({"submissions": submissions, "total": len(submissions)})


@app.get("/api/jobs/{job_id}/submissions/{submission_dir}/paper")
async def api_submission_pdf(job_id: str, submission_dir: str):
    """Serve paper.pdf for a specific submission version directory."""
    if not _safe_submission_dir_name(submission_dir):
        return JSONResponse({"error": "Invalid submission directory"}, status_code=400)

    # Try GitLab for the main paper.pdf (pushed as paper.pdf at repo root).
    gl = _gitlab_lookup(job_id)
    if gl:
        project_id, branch = gl
        pdf_bytes = GITLAB_CLIENT.get_file_raw(project_id, branch, "paper.pdf")
        if pdf_bytes:
            from starlette.responses import Response
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": "inline; filename=paper.pdf",
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    # Fallback to local disk.
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

    for root in iter_submission_roots(job_dir):
        pdf_path = os.path.join(root, submission_dir, "paper.pdf")
        if os.path.exists(pdf_path):
            return FileResponse(
                pdf_path,
                media_type="application/pdf",
                filename="paper.pdf",
                content_disposition_type="inline",
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
    return JSONResponse({"error": "PDF not found"}, status_code=404)


@app.get("/api/jobs/{job_id}/artifacts")
async def api_artifacts(job_id: str):
    """List figures, papers, and other artifacts."""
    # Try GitLab for completed jobs.
    gl = _gitlab_lookup(job_id)
    if gl:
        project_id, branch = gl
        gl_meta = GITLAB_CLIENT.get_metadata(project_id, branch)
        if gl_meta:
            figures = gl_meta.get("figures", [])
            papers = ["paper.pdf"] if gl_meta.get("has_paper_pdf") else []
            return JSONResponse({"figures": figures, "papers": papers})

    # Fallback to local disk.
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

    arts_dir = find_artifacts_dir(job_dir)
    if not arts_dir:
        return JSONResponse({"figures": [], "papers": []})

    figures = []
    fig_dir = os.path.join(arts_dir, "figures")
    if os.path.isdir(fig_dir):
        figures = sorted(os.listdir(fig_dir))

    papers = []
    latex_dir = os.path.join(arts_dir, "latex")
    if os.path.isdir(latex_dir):
        papers = [f for f in os.listdir(latex_dir) if f.endswith((".tex", ".pdf"))]

    return JSONResponse(mask_secrets({"figures": figures, "papers": papers}))


@app.get("/api/jobs/{job_id}/trajectory")
async def api_trajectory(job_id: str, regenerate: bool = False):
    """Return ATIF trajectory JSON, generating it if needed."""
    # Try GitLab for completed jobs (sanitized trajectory in agent_trace/).
    gl = _gitlab_lookup(job_id)
    if gl and not regenerate:
        project_id, branch = gl
        traj = GITLAB_CLIENT.get_file_json(project_id, branch, "agent_trace/trajectory.json")
        if traj:
            return JSONResponse(traj)

    # Fallback to local disk.
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

    traj_path = find_trajectory_path(job_dir)
    if not traj_path:
        agent_dir = find_agent_dir(job_dir)
        if not agent_dir:
            return JSONResponse({"error": "No agent directory"}, status_code=404)
        traj_path = os.path.join(agent_dir, "trajectory.json")

    # Generate if missing, stale, or forced
    need_gen = regenerate or not os.path.exists(traj_path)
    if not need_gen and os.path.exists(traj_path):
        try:
            age = time.time() - os.path.getmtime(traj_path)
            status = get_job_status(job_dir)
            if status == "running" and age > 60:
                need_gen = True
        except OSError:
            need_gen = True

    if need_gen:
        generate_trajectory(job_dir)
        traj_path = find_trajectory_path(job_dir) or traj_path

    if not os.path.exists(traj_path):
        return JSONResponse({"error": "No trajectory available"}, status_code=404)

    try:
        with open(traj_path) as f:
            data = json.load(f)
        return JSONResponse(mask_secrets(data))
    except (json.JSONDecodeError, OSError) as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _init_gitlab_client():
    """Initialize GitLab client if GITLAB_KEY is set.

    Pre-warms all caches so the first page load is fast.
    """
    global GITLAB_CLIENT
    token = os.environ.get("GITLAB_KEY", "")
    if not token:
        return
    try:
        client = GitLabClient(token)
        if client.username:
            GITLAB_CLIENT = client
            print(f"  GitLab: connected as {client.username}")
            # Pre-populate job map from GitLab repos.
            try:
                gl_jobs = client.discover_gitlab_jobs()
                for gj in gl_jobs:
                    if gj.get("_project_id") and gj.get("_branch"):
                        GITLAB_JOB_MAP[gj["id"]] = (gj["_project_id"], gj["_branch"])
                print(f"  GitLab: {len(GITLAB_JOB_MAP)} jobs indexed")
            except Exception as e:
                print(f"  GitLab: job discovery failed: {e}")

            # Pre-warm trajectory summary cache in parallel so first page
            # load doesn't block on N sequential GitLab API calls.
            if GITLAB_JOB_MAP:
                from concurrent.futures import ThreadPoolExecutor
                def _warm(item):
                    pid, branch = item
                    client.get_trajectory_summary(pid, branch)
                with ThreadPoolExecutor(max_workers=10) as pool:
                    pool.map(_warm, GITLAB_JOB_MAP.values())
                print(f"  GitLab: caches pre-warmed")
    except Exception as e:
        print(f"  GitLab: init failed: {e}")


def main():
    global JOBS_DIR
    parser = argparse.ArgumentParser(description="AI Scientist v3 — Job Viewer")
    parser.add_argument("--jobs-dir", default="./jobs", help="Path to jobs directory")
    parser.add_argument("--port", type=int, default=8501, help="Port to serve on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()

    JOBS_DIR = os.path.abspath(args.jobs_dir)
    print(f"AI Scientist v3 — Job Viewer")
    print(f"  Jobs dir: {JOBS_DIR}")

    _init_gitlab_client()

    print(f"  Serving on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
