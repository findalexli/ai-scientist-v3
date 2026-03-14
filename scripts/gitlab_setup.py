#!/usr/bin/env python3
"""Create a GitLab repo for an idea (idempotent) and return run metadata.

Usage:
    python3 scripts/gitlab_setup.py --idea-name NAME --agent AGENT_TYPE [--timestamp TS]
    python3 scripts/gitlab_setup.py --idea-name NAME --agent AGENT_TYPE --resume-branch claude-2026-03-10-19-04

Requires GITLAB_KEY env var (personal access token with api scope).

Outputs JSON to stdout:
    {
        "repo_url": "https://oauth2:TOKEN@gitlab.com/USER/NAME.git",
        "web_url": "https://gitlab.com/USER/NAME",
        "branch": "gemini-2026-02-24-22-30",
        "resume_branch": "claude-2026-03-10-19-04",
        "sibling_branches": ["gemini-2026-02-23-10-00", "claude-2026-02-22-18-30"]
    }

Auto-prunes stale branches (<30 min duration) on every invocation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional


GITLAB_API = "https://gitlab.com/api/v4"
MIN_BRANCH_DURATION_MIN = 30


def _api(method: str, path: str, token: str, data: Optional[dict] = None) -> dict:
    """Make a GitLab API request."""
    url = f"{GITLAB_API}{path}"
    body = json.dumps(data).encode() if data else None
    headers = {
        "PRIVATE-TOKEN": token,
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"GitLab API {method} {path}: {e.code} {error_body}") from e


def get_username(token: str) -> str:
    user = _api("GET", "/user", token)
    return user["username"]


def ensure_repo(token: str, username: str, repo_name: str) -> dict:
    """Create repo if it doesn't exist. Returns project dict."""
    encoded = urllib.parse.quote(f"{username}/{repo_name}", safe="")
    try:
        return _api("GET", f"/projects/{encoded}", token)
    except RuntimeError as e:
        if "404" not in str(e):
            raise

    # Create it
    return _api("POST", "/projects", token, {
        "name": repo_name,
        "visibility": "private",
        "initialize_with_readme": True,
        "description": f"AI Scientist research: {repo_name}",
    })


def list_branches(token: str, project_id: int) -> list[str]:
    """List all branch names for a project."""
    try:
        branches = _api("GET", f"/projects/{project_id}/repository/branches?per_page=100", token)
        return [b["name"] for b in branches]
    except RuntimeError:
        return []


def _list_branches_with_commits(token: str, project_id: int) -> list[dict]:
    """List branches with their last commit date."""
    try:
        return _api("GET", f"/projects/{project_id}/repository/branches?per_page=100", token)
    except RuntimeError:
        return []


def _parse_branch_start(name: str) -> Optional[datetime]:
    """Parse start time from branch name like 'claude-2026-03-10-19-04'."""
    m = re.match(r"(?:claude|codex|gemini)-(\d{4}-\d{2}-\d{2}-\d{2}-\d{2})$", name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d-%H-%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _branch_duration_min(branch: dict) -> Optional[float]:
    """Compute duration in minutes from branch name timestamp to last commit."""
    start = _parse_branch_start(branch["name"])
    if start is None:
        return None
    commit_date_str = branch["commit"]["committed_date"]
    commit_date = datetime.fromisoformat(commit_date_str).astimezone(timezone.utc)
    return (commit_date - start).total_seconds() / 60.0


def prune_stale_branches(
    token: str,
    project_id: int,
    branches: list[dict],
    protected_names: set[str],
    min_duration_min: float = MIN_BRANCH_DURATION_MIN,
) -> list[str]:
    """Delete branches that lasted less than min_duration_min. Returns list of pruned names."""
    pruned = []
    for b in branches:
        name = b["name"]
        if name in protected_names:
            continue
        duration = _branch_duration_min(b)
        if duration is not None and duration < min_duration_min:
            encoded = urllib.parse.quote(name, safe="")
            try:
                urllib.request.urlopen(
                    urllib.request.Request(
                        f"{GITLAB_API}/projects/{project_id}/repository/branches/{encoded}",
                        headers={"PRIVATE-TOKEN": token},
                        method="DELETE",
                    ),
                    timeout=15,
                )
                pruned.append(name)
                print(f"  pruned stale branch: {name} ({duration:.0f} min)", file=sys.stderr)
            except (urllib.error.HTTPError, urllib.error.URLError) as e:
                print(f"  failed to prune {name}: {e}", file=sys.stderr)
    return pruned


def main():
    parser = argparse.ArgumentParser(description="Setup GitLab repo for AI Scientist idea")
    parser.add_argument("--idea-name", required=True, help="Idea name (used as repo name)")
    parser.add_argument("--agent", required=True, help="Agent type: claude-code, gemini-cli, or codex")
    parser.add_argument("--timestamp", default=None, help="Override timestamp (default: now)")
    parser.add_argument("--resume-branch", default=None, help="Branch to resume from (branch off)")
    args = parser.parse_args()

    token = os.environ.get("GITLAB_KEY", "")
    if not token:
        print('{"error": "GITLAB_KEY not set"}', file=sys.stderr)
        sys.exit(1)

    # Normalize names: underscores → hyphens for GitLab
    repo_name = args.idea_name.replace("_", "-")
    agent_short = args.agent.replace("-cli", "").replace("-code", "")  # "gemini" or "claude"

    if args.timestamp:
        ts = args.timestamp
    else:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M")

    branch_name = f"{agent_short}-{ts}"

    username = get_username(token)
    project = ensure_repo(token, username, repo_name)
    project_id = project["id"]

    # List existing branches with commit info (for pruning + sibling list)
    all_branches_info = _list_branches_with_commits(token, project_id)
    all_branch_names = [b["name"] for b in all_branches_info]

    # Validate resume branch if provided
    resume_branch = None
    if args.resume_branch:
        if args.resume_branch in all_branch_names:
            resume_branch = args.resume_branch
        else:
            print(f"Warning: resume branch '{args.resume_branch}' not found on GitLab, ignoring", file=sys.stderr)

    # Auto-prune stale branches (<30 min)
    protected = {"main", branch_name}
    if resume_branch:
        protected.add(resume_branch)
    pruned = prune_stale_branches(token, project_id, all_branches_info, protected)

    # Build sibling list (excluding pruned, current, and main)
    pruned_set = set(pruned)
    sibling_branches = [
        b for b in all_branch_names
        if b != branch_name and b != "main" and b not in pruned_set
    ]

    # Build authenticated repo URL for push
    repo_url = f"https://oauth2:{token}@gitlab.com/{username}/{repo_name}.git"
    web_url = project.get("web_url", f"https://gitlab.com/{username}/{repo_name}")

    result = {
        "repo_url": repo_url,
        "web_url": web_url,
        "project_id": project_id,
        "branch": branch_name,
        "sibling_branches": sibling_branches,
    }
    if resume_branch:
        result["resume_branch"] = resume_branch
    print(json.dumps(result))


if __name__ == "__main__":
    main()
