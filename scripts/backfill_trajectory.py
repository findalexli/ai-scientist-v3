#!/usr/bin/env python3
"""Backfill ATIF trajectory.json for old jobs that lack one.

New jobs generate trajectory.json automatically via Harbor's
populate_context_post_run.  This script exists only to retroactively
create trajectories for jobs produced before that upstream feature
landed (harbor commit 5a3a6db, 2026-02-12).

Usage (requires Harbor's Python, not the project venv):
    /home/alex/.local/share/uv/tools/harbor/bin/python3 scripts/backfill_trajectory.py --job-dir jobs/<job-id>
"""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path


def find_agent_dir(job_dir: Path) -> Path | None:
    """Find the agent directory inside a job."""
    for entry in job_dir.iterdir():
        if entry.name.startswith("harbor-task") and entry.is_dir():
            agent_dir = entry / "agent"
            if agent_dir.is_dir():
                return agent_dir
    return None


def generate_claude_atif(agent_dir: Path) -> int:
    """Generate ATIF from claude-code.txt."""
    from harbor.agents.installed.claude_code import ClaudeCode

    cc_path = agent_dir / "claude-code.txt"
    if not cc_path.exists():
        print(f"No claude-code.txt in {agent_dir}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Converter expects *.jsonl files in session_dir
        shutil.copy2(cc_path, tmp_path / "session.jsonl")

        # Minimal instance — just needs logs_dir and model_name
        agent = ClaudeCode.__new__(ClaudeCode)
        agent.logs_dir = agent_dir
        agent.model_name = None

        traj = agent._convert_events_to_trajectory(tmp_path)

    if not traj:
        print("Conversion returned None", file=sys.stderr)
        return 1

    out = agent_dir / "trajectory.json"
    out.write_text(json.dumps(traj.to_json_dict(), indent=2, ensure_ascii=False))
    print(f"Wrote {len(traj.steps)} steps → {out}")
    return 0


def generate_gemini_atif(agent_dir: Path) -> int:
    """Generate ATIF from gemini-cli.trajectory.json."""
    from harbor.agents.installed.gemini_cli import GeminiCli

    traj_path = agent_dir / "gemini-cli.trajectory.json"
    if not traj_path.exists():
        print(f"No gemini-cli.trajectory.json in {agent_dir}", file=sys.stderr)
        return 1

    data = json.loads(traj_path.read_text())

    # Minimal instance — needs logs_dir, model_name, _version
    agent = GeminiCli.__new__(GeminiCli)
    agent.logs_dir = agent_dir
    agent.model_name = None
    agent._version = None

    traj = agent._convert_gemini_to_atif(data)
    if not traj:
        print("Conversion returned None", file=sys.stderr)
        return 1

    out = agent_dir / "trajectory.json"
    out.write_text(json.dumps(traj.to_json_dict(), indent=2, ensure_ascii=False))
    print(f"Wrote {len(traj.steps)} steps → {out}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Generate ATIF trajectory from agent logs")
    parser.add_argument("--job-dir", required=True, help="Path to job directory")
    args = parser.parse_args()

    job_dir = Path(args.job_dir).resolve()
    if not job_dir.is_dir():
        print(f"Not a directory: {job_dir}", file=sys.stderr)
        sys.exit(1)

    agent_dir = find_agent_dir(job_dir)
    if not agent_dir:
        print(f"No agent directory found in {job_dir}", file=sys.stderr)
        sys.exit(1)

    # Detect agent type
    if (agent_dir / "claude-code.txt").exists():
        sys.exit(generate_claude_atif(agent_dir))
    elif (agent_dir / "gemini-cli.trajectory.json").exists():
        sys.exit(generate_gemini_atif(agent_dir))
    else:
        print(f"No recognized agent logs in {agent_dir}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
