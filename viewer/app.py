"""AI Scientist v3 — Live Job Viewer. FastAPI backend + serves HTML templates."""

import argparse
import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from parse_trajectory import (
    ParseResult,
    compute_cumulative_tokens,
    compute_event_type_breakdown,
    compute_tool_breakdown,
    detect_and_parse,
    estimate_cost,
    find_artifacts_dir,
    find_claude_code_path,
)

app = FastAPI(title="AI Scientist v3 — Job Viewer")

# Global config — set by CLI args
JOBS_DIR = "./jobs"
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
HARBOR_PYTHON = "/home/alex/.local/share/uv/tools/harbor/bin/python3"
GENERATE_ATIF_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "backfill_trajectory.py")


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


def get_job_status(job_dir: str) -> str:
    """Determine if a job is running, completed, or failed."""
    cc_path = find_claude_code_path(job_dir)
    if not cc_path:
        return "unknown"

    # Check mtime — if modified < 5 min ago → running
    try:
        mtime = os.path.getmtime(cc_path)
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
    arts = find_artifacts_dir(job_dir)
    if not arts:
        return 0
    vlog = os.path.join(arts, "submissions", "version_log.json")
    if os.path.exists(vlog):
        try:
            with open(vlog) as f:
                data = json.load(f)
            return data.get("current_version", len(data.get("versions", [])))
        except (json.JSONDecodeError, OSError):
            pass
    return 0


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


def discover_jobs() -> list:
    """Scan jobs directory and return job metadata."""
    jobs = []
    if not os.path.isdir(JOBS_DIR):
        return jobs

    for name in sorted(os.listdir(JOBS_DIR), reverse=True):
        job_dir = os.path.join(JOBS_DIR, name)
        if not os.path.isdir(job_dir):
            continue

        config = read_config(job_dir)
        status = get_job_status(job_dir)
        cc_path = find_claude_code_path(job_dir)

        # Quick line count
        line_count = 0
        file_size = 0
        if cc_path:
            try:
                file_size = os.path.getsize(cc_path)
                with open(cc_path, "r", errors="replace") as f:
                    line_count = sum(1 for _ in f)
            except OSError:
                pass

        # Quick token estimate from parsing (cached in practice)
        token_summary = None
        if cc_path:
            result = detect_and_parse(job_dir)
            cost = estimate_cost(result.events, model=config.get("agents", [{}])[0].get("model_name", "claude-opus-4-6"))
            token_summary = cost

        # Extract task name: try config job_name, then first assistant text
        task_name = config.get("job_name", name)
        # Try to get a more descriptive name from early assistant messages
        if cc_path and result.events:
            for ev in result.events[:10]:
                if ev.source == "agent" and ev.event_type == "text" and len(ev.summary) > 20:
                    task_name = ev.summary[:80]
                    break

        jobs.append({
            "id": name,
            "dir": job_dir,
            "status": status,
            "model": get_model_name(config),
            "line_count": line_count,
            "file_size_mb": round(file_size / 1_000_000, 1),
            "submissions": get_submission_count(job_dir),
            "tokens": token_summary,
            "task_name": task_name,
        })

    return jobs


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
    return JSONResponse(discover_jobs())


@app.get("/api/jobs/{job_id}/events")
async def api_events(job_id: str, after: int = 0):
    """Return JSON events, optionally starting from line N."""
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

    result = detect_and_parse(job_dir, after_line=after)
    return JSONResponse({
        "events": [e.to_dict() for e in result.events],
        "total_lines": result.total_lines,
        "session_id": result.session_id,
        "model": result.model,
    })


@app.get("/api/jobs/{job_id}/stream")
async def stream_events(job_id: str, after: int = 0):
    """SSE stream: polls claude-code.txt every 2 seconds, yields new events."""
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

    cc_path = find_claude_code_path(job_dir)
    if not cc_path:
        return JSONResponse({"error": "No transcript found"}, status_code=404)

    async def event_generator():
        last_line = after
        config = read_config(job_dir)
        model = config.get("agents", [{}])[0].get("model_name", "claude-opus-4-6")
        tick = 0

        while True:
            result = detect_and_parse(job_dir, after_line=last_line)
            for event in result.events:
                yield {
                    "event": "new_event",
                    "data": json.dumps(event.to_dict()),
                }
            if result.events:
                last_line = result.total_lines

            # Also parse full for cumulative stats
            full_result = detect_and_parse(job_dir)
            cost = estimate_cost(full_result.events, model=model)
            cumulative = compute_cumulative_tokens(full_result.events)
            tool_bk = compute_tool_breakdown(full_result.events)
            event_bk = compute_event_type_breakdown(full_result.events)

            yield {
                "event": "metrics",
                "data": json.dumps({
                    "cost": cost,
                    "cumulative_tokens": cumulative[-5:] if cumulative else [],  # last 5 for chart update
                    "tool_breakdown": tool_bk,
                    "event_type_breakdown": event_bk,
                    "total_lines": full_result.total_lines,
                }),
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
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

    config = read_config(job_dir)
    model = config.get("agents", [{}])[0].get("model_name", "claude-opus-4-6")

    result = detect_and_parse(job_dir)
    cost = estimate_cost(result.events, model=model)
    cumulative = compute_cumulative_tokens(result.events)
    tool_bk = compute_tool_breakdown(result.events)
    event_bk = compute_event_type_breakdown(result.events)

    return JSONResponse({
        "cost": cost,
        "cumulative_tokens": cumulative,
        "tool_breakdown": tool_bk,
        "event_type_breakdown": event_bk,
    })


@app.get("/api/jobs/{job_id}/submissions")
async def api_submissions(job_id: str):
    """Read version_log.json + each version's reviewer feedback (response.md or response.json)."""
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

    # Find artifacts in both agent and verifier
    submissions = []
    for entry in os.listdir(job_dir):
        if not entry.startswith("harbor-task"):
            continue
        for sub in ["verifier", "agent"]:
            sub_dir = os.path.join(job_dir, entry, sub, "artifacts", "submissions")
            if not os.path.isdir(sub_dir):
                continue

            vlog_path = os.path.join(sub_dir, "version_log.json")
            if not os.path.exists(vlog_path):
                continue

            try:
                with open(vlog_path) as f:
                    vlog = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            for ver in vlog.get("versions", []):
                v_dir = os.path.join(sub_dir, ver["directory"])
                review = ver.get("reviewer_preview", ver.get("reviewer_question_preview", ""))
                rebuttal = None

                # Try response.md first (new format), then response.json (legacy)
                resp_md = os.path.join(v_dir, "reviewer_communications", "response.md")
                resp_json = os.path.join(v_dir, "reviewer_communications", "response.json")

                if os.path.exists(resp_md):
                    try:
                        with open(resp_md) as f:
                            text = f.read()
                        # Split on ## Review / ## Rebuttal sections
                        parts = text.split("## Rebuttal", 1)
                        review_part = parts[0]
                        # Strip the ## Review header
                        review = review_part.replace("## Review", "", 1).strip()
                        if len(parts) > 1:
                            rebuttal = parts[1].strip()
                    except OSError:
                        pass
                elif os.path.exists(resp_json):
                    try:
                        with open(resp_json) as f:
                            resp = json.load(f)
                        review = resp.get("question", review)
                        rebuttal = resp.get("rebuttal")
                    except (json.JSONDecodeError, OSError):
                        pass

                has_pdf = os.path.exists(os.path.join(v_dir, "paper.pdf"))
                figures_count = 0
                fig_dir = os.path.join(v_dir, "figures")
                if os.path.isdir(fig_dir):
                    figures_count = len([f for f in os.listdir(fig_dir) if f.endswith(".png")])

                submissions.append({
                    "version": ver.get("version"),
                    "timestamp": ver.get("timestamp"),
                    "review": review,
                    "rebuttal": rebuttal,
                    "has_pdf": has_pdf,
                    "has_tex": ver.get("paper_tex", False),
                    "has_experiments": ver.get("has_experiments", False),
                    "has_figures": ver.get("has_figures", False),
                    "figures_count": figures_count,
                    "reviewer_mode": ver.get("reviewer_mode", "api"),
                })

            # Found submissions, stop looking
            if submissions:
                break
        if submissions:
            break

    return JSONResponse({"submissions": submissions, "total": len(submissions)})


@app.get("/api/jobs/{job_id}/artifacts")
async def api_artifacts(job_id: str):
    """List figures, papers, and other artifacts."""
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

    return JSONResponse({"figures": figures, "papers": papers})


@app.get("/api/jobs/{job_id}/trajectory")
async def api_trajectory(job_id: str, regenerate: bool = False):
    """Return ATIF trajectory JSON, generating it if needed."""
    job_dir = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(job_dir):
        return JSONResponse({"error": "Job not found"}, status_code=404)

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

    if not os.path.exists(traj_path):
        return JSONResponse({"error": "No trajectory available"}, status_code=404)

    try:
        with open(traj_path) as f:
            data = json.load(f)
        return JSONResponse(data)
    except (json.JSONDecodeError, OSError) as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
    print(f"  Serving on http://{args.host}:{args.port}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
