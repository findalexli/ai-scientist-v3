#!/usr/bin/env python3
"""Create a GitLab repo for an idea (idempotent) and return run metadata.

Usage:
    python3 scripts/gitlab_setup.py --idea-name NAME --agent AGENT_TYPE [--timestamp TS]

Requires GITLAB_KEY env var (personal access token with api scope).

Outputs JSON to stdout:
    {
        "repo_url": "https://oauth2:TOKEN@gitlab.com/USER/NAME.git",
        "web_url": "https://gitlab.com/USER/NAME",
        "branch": "gemini-2026-02-24-22-30",
        "sibling_branches": ["gemini-2026-02-23-10-00", "claude-2026-02-22-18-30"]
    }
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone


GITLAB_API = "https://gitlab.com/api/v4"


def _api(method: str, path: str, token: str, data: dict | None = None) -> dict:
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


def main():
    parser = argparse.ArgumentParser(description="Setup GitLab repo for AI Scientist idea")
    parser.add_argument("--idea-name", required=True, help="Idea name (used as repo name)")
    parser.add_argument("--agent", required=True, help="Agent type: claude-code or gemini-cli")
    parser.add_argument("--timestamp", default=None, help="Override timestamp (default: now)")
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

    # List existing branches (sibling runs)
    all_branches = list_branches(token, project_id)
    sibling_branches = [b for b in all_branches if b != branch_name and b != "main"]

    # Build authenticated repo URL for push
    repo_url = f"https://oauth2:{token}@gitlab.com/{username}/{repo_name}.git"
    web_url = project.get("web_url", f"https://gitlab.com/{username}/{repo_name}")

    result = {
        "repo_url": repo_url,
        "web_url": web_url,
        "branch": branch_name,
        "sibling_branches": sibling_branches,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    main()
