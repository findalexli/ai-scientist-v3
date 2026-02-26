"""
Viewer redaction tests: verify .env secret values never appear in rendered output.

Run with:
  ./.venv/bin/python -m unittest tests.test_viewer_secret_redaction -v
"""

import json
import os
import sys
import tempfile
import unittest
import asyncio
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
VIEWER_DIR = REPO_ROOT / "viewer"
sys.path.insert(0, str(VIEWER_DIR))

import app as app_module  # noqa: E402


def _load_env_secret_values() -> list[tuple[str, str]]:
    """Load .env values to guard against accidental raw leakage in UI/API output."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return []

    secret_pairs: list[tuple[str, str]] = []
    try:
        lines = env_path.read_text(errors="replace").splitlines()
    except OSError:
        return []

    non_sensitive_names = {"DATA_DIR", "REVIEWER_MODE"}

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip().upper()
        if name in non_sensitive_names:
            continue
        value = value.strip()
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if not value:
            continue
        is_secret_name = any(tok in name for tok in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
        # Include all substantial values (>=8 chars) plus explicit secret-like names.
        # Very short values (e.g. "api") are excluded to avoid noisy false positives.
        if not is_secret_name and len(value) < 8:
            continue
        secret_pairs.append((name, value))

    # Longest first so collision checks are deterministic.
    return sorted(set(secret_pairs), key=lambda kv: len(kv[1]), reverse=True)


def _clear_viewer_caches() -> None:
    app_module.JOB_PARSE_CACHE.clear()
    if hasattr(app_module, "JOB_METRICS_CACHE"):
        app_module.JOB_METRICS_CACHE.clear()
    if hasattr(app_module, "JOBS_LIST_CACHE"):
        app_module.JOBS_LIST_CACHE.update({"jobs_dir": None, "expires_at": 0.0, "payload": None})


class _RedactionAssertionsMixin:
    env_secret_pairs: list[tuple[str, str]]

    def assert_no_env_secret_leak(self, payload_text: str, context: str) -> None:
        leaked = [name for name, value in self.env_secret_pairs if value in payload_text]
        self.assertFalse(
            leaked,
            f"{context}: found unmasked .env secret values for keys: {', '.join(leaked)}",
        )

    def run_async(self, coro):
        return asyncio.run(coro)

    def response_text(self, resp) -> str:
        body = getattr(resp, "body", b"")
        if isinstance(body, bytes):
            return body.decode("utf-8", errors="replace")
        return str(body)


class TestViewerRedactionAgainstRealJobs(unittest.TestCase, _RedactionAssertionsMixin):
    @classmethod
    def setUpClass(cls):
        cls.env_secret_pairs = _load_env_secret_values()
        if not cls.env_secret_pairs:
            raise unittest.SkipTest("No secret-like values found in .env")
        cls.real_jobs_dir = str(REPO_ROOT / "jobs")
        if not os.path.isdir(cls.real_jobs_dir):
            raise unittest.SkipTest("jobs/ directory not found")

    def setUp(self):
        self.original_jobs_dir = app_module.JOBS_DIR
        app_module.JOBS_DIR = self.real_jobs_dir
        _clear_viewer_caches()

    def tearDown(self):
        app_module.JOBS_DIR = self.original_jobs_dir
        _clear_viewer_caches()

    def test_dashboard_html_does_not_leak_env_secrets(self):
        resp = self.run_async(app_module.dashboard())
        self.assertEqual(resp.status_code, 200, msg="/")
        self.assert_no_env_secret_leak(self.response_text(resp), context="/")

    def test_jobs_api_cache_does_not_leak_env_secrets(self):
        # Verify both cold and warm-cache responses stay redacted.
        first = self.run_async(app_module.api_jobs())
        self.assertEqual(first.status_code, 200, msg="/api/jobs (cold)")
        self.assert_no_env_secret_leak(self.response_text(first), context="/api/jobs (cold)")

        second = self.run_async(app_module.api_jobs())
        self.assertEqual(second.status_code, 200, msg="/api/jobs (warm)")
        self.assert_no_env_secret_leak(self.response_text(second), context="/api/jobs (warm)")

    def test_selected_real_job_endpoints_do_not_leak_env_secrets(self):
        # Known real traces + one newest fallback.
        preferred = [
            "2026-02-21__20-39-12",
            "videoqa_with_toolw_feedback__2026-02-23__22-25-19",
        ]
        discovered = [
            p.name
            for p in Path(self.real_jobs_dir).iterdir()
            if p.is_dir()
        ]
        discovered.sort(reverse=True)

        sample_job_ids: list[str] = []
        for job_id in preferred + discovered:
            if job_id in discovered and job_id not in sample_job_ids:
                sample_job_ids.append(job_id)
            if len(sample_job_ids) >= 3:
                break

        if not sample_job_ids:
            self.skipTest("No real jobs available to inspect")

        for job_id in sample_job_ids:
            endpoints = [
                (f"/job/{job_id}", lambda: app_module.job_detail(job_id)),
                (f"/api/jobs/{job_id}/meta", lambda: app_module.api_job_meta(job_id)),
                (f"/api/jobs/{job_id}/events", lambda: app_module.api_events(job_id, after=0)),
                (f"/api/jobs/{job_id}/tokens", lambda: app_module.api_tokens(job_id)),
                (f"/api/jobs/{job_id}/submissions", lambda: app_module.api_submissions(job_id)),
                (f"/api/jobs/{job_id}/idea", lambda: app_module.api_job_idea(job_id)),
                (f"/api/jobs/{job_id}/artifacts", lambda: app_module.api_artifacts(job_id)),
                (f"/api/jobs/{job_id}/trajectory", lambda: app_module.api_trajectory(job_id, regenerate=False)),
            ]
            for path, call in endpoints:
                resp = self.run_async(call())
                self.assertIn(resp.status_code, (200, 404), msg=path)
                self.assert_no_env_secret_leak(self.response_text(resp), context=path)


class TestViewerRedactionSyntheticLeak(unittest.TestCase, _RedactionAssertionsMixin):
    @classmethod
    def setUpClass(cls):
        cls.env_secret_pairs = _load_env_secret_values()
        if not cls.env_secret_pairs:
            raise unittest.SkipTest("No secret-like values found in .env")

    def setUp(self):
        self.secret_name, self.secret_value = self.env_secret_pairs[0]

        self.tmpdir = tempfile.mkdtemp(prefix="viewer-redact-")
        self.job_id = "redaction_probe__2026-02-25__12-00-00"
        self.job_dir = os.path.join(self.tmpdir, self.job_id)
        self.agent_dir = os.path.join(self.job_dir, "harbor-task-probe", "agent")
        os.makedirs(self.agent_dir, exist_ok=True)

        # Minimal config to satisfy job discovery.
        with open(os.path.join(self.job_dir, "config.json"), "w") as f:
            json.dump(
                {
                    "job_name": self.job_id,
                    "agents": [{"model_name": "anthropic/claude-opus-4-6"}],
                },
                f,
            )

        # Inject raw secret into trajectory payload.
        with open(os.path.join(self.agent_dir, "trajectory.json"), "w") as f:
            json.dump(
                {
                    "schema_version": "ATIF-v1.2",
                    "session_id": "probe-session",
                    "agent": {"name": "probe-agent"},
                    "steps": [
                        {
                            "step_id": 1,
                            "source": "user",
                            "message": f"secret probe value: {self.secret_value}",
                        }
                    ],
                },
                f,
            )

        # Inject raw secret into submissions review/rebuttal content.
        sub_root = os.path.join(
            self.job_dir, "harbor-task-probe", "verifier", "artifacts", "submissions"
        )
        sub_ver = os.path.join(sub_root, "v1_20260225_120000")
        comms = os.path.join(sub_ver, "reviewer_communications")
        os.makedirs(comms, exist_ok=True)
        with open(os.path.join(sub_root, "version_log.json"), "w") as f:
            json.dump(
                {
                    "current_version": 1,
                    "versions": [
                        {
                            "version": 1,
                            "timestamp": "2026-02-25T12:00:00",
                            "directory": "v1_20260225_120000",
                            "reviewer_mode": "api",
                        }
                    ],
                },
                f,
            )
        with open(os.path.join(comms, "response.json"), "w") as f:
            json.dump(
                {
                    "question": f"Review includes {self.secret_value}",
                    "rebuttal": f"Rebuttal includes {self.secret_value}",
                },
                f,
            )

        self.original_jobs_dir = app_module.JOBS_DIR
        app_module.JOBS_DIR = self.tmpdir
        _clear_viewer_caches()

    def tearDown(self):
        import shutil

        app_module.JOBS_DIR = self.original_jobs_dir
        _clear_viewer_caches()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_synthetic_secret_is_masked_in_events_submissions_and_trajectory(self):
        targets = [
            {
                "path": "/api/jobs (cold)",
                "call": lambda: app_module.api_jobs(),
                "expect_redacted_marker": True,
            },
            {
                "path": "/api/jobs (warm)",
                "call": lambda: app_module.api_jobs(),
                "expect_redacted_marker": True,
            },
            {
                "path": f"/job/{self.job_id}",
                "call": lambda: app_module.job_detail(self.job_id),
                "expect_redacted_marker": False,
            },
            {
                "path": f"/api/jobs/{self.job_id}/meta",
                "call": lambda: app_module.api_job_meta(self.job_id),
                "expect_redacted_marker": False,
            },
            {
                "path": f"/api/jobs/{self.job_id}/events",
                "call": lambda: app_module.api_events(self.job_id, after=0),
                "expect_redacted_marker": True,
            },
            {
                "path": f"/api/jobs/{self.job_id}/tokens",
                "call": lambda: app_module.api_tokens(self.job_id),
                "expect_redacted_marker": False,
            },
            {
                "path": f"/api/jobs/{self.job_id}/submissions",
                "call": lambda: app_module.api_submissions(self.job_id),
                "expect_redacted_marker": True,
            },
            {
                "path": f"/api/jobs/{self.job_id}/idea",
                "call": lambda: app_module.api_job_idea(self.job_id),
                "expect_redacted_marker": False,
            },
            {
                "path": f"/api/jobs/{self.job_id}/artifacts",
                "call": lambda: app_module.api_artifacts(self.job_id),
                "expect_redacted_marker": False,
            },
            {
                "path": f"/api/jobs/{self.job_id}/trajectory",
                "call": lambda: app_module.api_trajectory(self.job_id, regenerate=False),
                "expect_redacted_marker": True,
            },
        ]
        for target in targets:
            path = target["path"]
            resp = self.run_async(target["call"]())
            self.assertEqual(resp.status_code, 200, msg=path)
            resp_text = self.response_text(resp)
            self.assert_no_env_secret_leak(resp_text, context=path)
            if target["expect_redacted_marker"]:
                self.assertIn("[REDACTED]", resp_text, msg=path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
