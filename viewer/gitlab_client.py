"""GitLab API client for the AI Scientist viewer.

Reads pre-computed job metadata and trajectory summaries from per-idea GitLab
repos. Caches aggressively since completed jobs are immutable.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

GITLAB_API = "https://gitlab.com/api/v4"
REPO_DESCRIPTION_PREFIX = "AI Scientist research:"


class CacheEntry:
    __slots__ = ("data", "expires_at")

    def __init__(self, data: Any, ttl: float):
        self.data = data
        self.expires_at = time.time() + ttl

    def is_valid(self) -> bool:
        return time.time() < self.expires_at


class GitLabClient:
    """Read-only GitLab API client with per-request caching."""

    # Cache TTLs (seconds).
    REPOS_TTL = 60.0
    BRANCHES_TTL = 300.0
    METADATA_TTL = 86400.0  # 24h — completed jobs don't change.
    FILE_TTL = 600.0

    def __init__(self, token: str, username: Optional[str] = None):
        self.token = token
        self._username = username
        self._cache: Dict[str, CacheEntry] = {}

    # ------------------------------------------------------------------
    # Low-level API
    # ------------------------------------------------------------------

    def _api(self, path: str, raw: bool = False) -> Any:
        """Make a GET request to the GitLab API."""
        url = f"{GITLAB_API}{path}"
        headers = {"PRIVATE-TOKEN": self.token}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read()
                if raw:
                    return body
                return json.loads(body.decode())
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            return None

    def _cached(self, key: str, ttl: float, fetcher) -> Any:
        """Return cached value or call fetcher."""
        entry = self._cache.get(key)
        if entry and entry.is_valid():
            return entry.data
        data = fetcher()
        if data is not None:
            self._cache[key] = CacheEntry(data, ttl)
        return data

    @property
    def username(self) -> Optional[str]:
        if self._username:
            return self._username
        user = self._api("/user")
        if user:
            self._username = user.get("username")
        return self._username

    # ------------------------------------------------------------------
    # Repo and branch discovery
    # ------------------------------------------------------------------

    def list_repos(self) -> List[dict]:
        """List all AI Scientist research repos (cached)."""
        def fetch():
            repos = self._api(f"/users/{self.username}/projects?per_page=100&order_by=updated_at")
            if not repos:
                return []
            return [
                {"id": r["id"], "name": r["path"], "web_url": r["web_url"]}
                for r in repos
                if isinstance(r, dict) and REPO_DESCRIPTION_PREFIX in (r.get("description") or "")
            ]
        return self._cached("repos", self.REPOS_TTL, fetch) or []

    def list_branches(self, project_id: int) -> List[dict]:
        """List branches (runs) for a repo (cached)."""
        def fetch():
            branches = self._api(f"/projects/{project_id}/repository/branches?per_page=100")
            if not branches:
                return []
            return [
                {"name": b["name"], "committed_date": b.get("commit", {}).get("committed_date")}
                for b in branches
                if isinstance(b, dict) and b.get("name") != "main"
            ]
        return self._cached(f"branches:{project_id}", self.BRANCHES_TTL, fetch) or []

    # ------------------------------------------------------------------
    # File access
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_lfs_pointer(data: bytes) -> Optional[dict]:
        """Parse a Git LFS pointer file. Returns {oid, size} or None."""
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            return None
        if not text.startswith("version https://git-lfs.github.com/"):
            return None
        info: Dict[str, str] = {}
        for line in text.strip().splitlines():
            if " " in line:
                key, val = line.split(" ", 1)
                info[key] = val
        oid = info.get("oid", "")
        if oid.startswith("sha256:"):
            oid = oid[7:]
        size_str = info.get("size", "0")
        if oid:
            return {"oid": oid, "size": int(size_str)}
        return None

    def _get_project_http_url(self, project_id: int) -> Optional[str]:
        """Get the HTTP clone URL for a project (cached)."""
        cache_key = f"http_url:{project_id}"
        entry = self._cache.get(cache_key)
        if entry and entry.is_valid():
            return entry.data
        proj = self._api(f"/projects/{project_id}")
        if not proj:
            return None
        url = proj.get("http_url_to_repo")
        if url:
            self._cache[cache_key] = CacheEntry(url, self.METADATA_TTL)
        return url

    def _fetch_lfs_blob(self, project_id: int, oid: str, size: int) -> Optional[bytes]:
        """Download an LFS blob via the Git LFS batch API."""
        import base64
        http_url = self._get_project_http_url(project_id)
        if not http_url:
            return None
        lfs_url = f"{http_url}/info/lfs/objects/batch"
        payload = json.dumps({
            "operation": "download",
            "objects": [{"oid": oid, "size": size}],
        }).encode()
        auth = base64.b64encode(f"oauth2:{self.token}".encode()).decode()
        headers = {
            "Content-Type": "application/vnd.git-lfs+json",
            "Accept": "application/vnd.git-lfs+json",
            "Authorization": f"Basic {auth}",
        }
        req = urllib.request.Request(lfs_url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                batch = json.loads(resp.read().decode())
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            return None

        objects = batch.get("objects", [])
        if not objects:
            return None
        actions = objects[0].get("actions", {})
        download = actions.get("download", {})
        href = download.get("href")
        if not href:
            return None

        # Download the actual blob.
        dl_headers = download.get("header", {})
        dl_req = urllib.request.Request(href, headers=dl_headers)
        try:
            with urllib.request.urlopen(dl_req, timeout=120) as resp:
                return resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            return None

    def _fetch_file_raw(self, project_id: int, branch: str, path: str) -> Optional[bytes]:
        """Fetch raw file content, resolving LFS pointers transparently."""
        encoded_path = urllib.parse.quote(path, safe="")
        data = self._api(
            f"/projects/{project_id}/repository/files/{encoded_path}/raw?ref={branch}",
            raw=True,
        )
        if data is None:
            return None
        # Check if this is an LFS pointer and resolve it.
        lfs = self._parse_lfs_pointer(data)
        if lfs:
            resolved = self._fetch_lfs_blob(project_id, lfs["oid"], lfs["size"])
            return resolved if resolved else None
        return data

    def get_file_json(self, project_id: int, branch: str, path: str, ttl: Optional[float] = None) -> Optional[dict]:
        """Fetch and parse a JSON file from a branch (resolves LFS pointers)."""
        cache_key = f"file:{project_id}:{branch}:{path}"
        effective_ttl = ttl if ttl is not None else self.FILE_TTL

        def fetch():
            data = self._fetch_file_raw(project_id, branch, path)
            if data is None:
                return None
            try:
                return json.loads(data.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None

        return self._cached(cache_key, effective_ttl, fetch)

    def get_file_raw(self, project_id: int, branch: str, path: str) -> Optional[bytes]:
        """Fetch raw file bytes, resolving LFS pointers transparently."""
        cache_key = f"raw:{project_id}:{branch}:{path}"

        def fetch():
            return self._fetch_file_raw(project_id, branch, path)

        return self._cached(cache_key, self.FILE_TTL, fetch)

    def list_tree(self, project_id: int, branch: str, path: str = "") -> List[dict]:
        """List files in a directory on a branch."""
        cache_key = f"tree:{project_id}:{branch}:{path}"

        def fetch():
            encoded_path = urllib.parse.quote(path, safe="")
            url = f"/projects/{project_id}/repository/tree?ref={branch}&per_page=100"
            if path:
                url += f"&path={encoded_path}"
            return self._api(url) or []

        return self._cached(cache_key, self.BRANCHES_TTL, fetch) or []

    # ------------------------------------------------------------------
    # High-level accessors (pre-computed data)
    # ------------------------------------------------------------------

    def get_metadata(self, project_id: int, branch: str) -> Optional[dict]:
        """Fetch pre-computed metadata.json from agent_trace/ (cached for 24h)."""
        return self.get_file_json(project_id, branch, "agent_trace/metadata.json", ttl=self.METADATA_TTL)

    def get_trajectory_summary(self, project_id: int, branch: str) -> Optional[dict]:
        """Fetch pre-computed trajectory_summary.json from agent_trace/ (cached for 24h)."""
        return self.get_file_json(project_id, branch, "agent_trace/trajectory_summary.json", ttl=self.METADATA_TTL)

    # ------------------------------------------------------------------
    # Job discovery: build job list from GitLab data
    # ------------------------------------------------------------------

    def discover_gitlab_jobs(self) -> List[dict]:
        """Build a job list from all repos and branches.

        Returns list of dicts compatible with the viewer's discover_jobs() format.
        """
        jobs = []
        repos = self.list_repos()

        for repo in repos:
            project_id = repo["id"]
            branches = self.list_branches(project_id)

            for branch_info in branches:
                branch = branch_info["name"]
                meta = self.get_metadata(project_id, branch)
                if not meta or not meta.get("job_id"):
                    continue  # Skip branches without valid metadata.

                job_id = meta.get("job_id", "")
                model = meta.get("model", "unknown")
                if "/" in model:
                    model = model.split("/")[-1]
                model = model.replace("claude-", "")

                jobs.append({
                    "id": job_id,
                    "status": meta.get("status", "completed"),
                    "duration_seconds": meta.get("duration_seconds"),
                    "model": model,
                    "line_count": 0,
                    "file_size_mb": 0,
                    "submissions": meta.get("submission_count", 0),
                    "tokens": meta.get("token_summary"),
                    "task_name": meta.get("idea_name", job_id).replace("_", " ").title(),
                    # GitLab-specific fields for routing.
                    "_gitlab": True,
                    "_project_id": project_id,
                    "_branch": branch,
                    "_repo_name": repo["name"],
                    "_web_url": repo["web_url"],
                })

        return jobs
