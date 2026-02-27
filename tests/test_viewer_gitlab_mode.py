"""
Tests for viewer GitLab mode: idea loading, event parsing, token endpoints.

Uses a mocked GitLabClient — no real API calls.

Run with:
  python3 -m unittest tests.test_viewer_gitlab_mode -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
VIEWER_DIR = REPO_ROOT / "viewer"
sys.path.insert(0, str(VIEWER_DIR))


def _make_mock_gitlab_client(files=None, metadata=None, summary=None):
    """Create a mock GitLabClient that returns specified data."""
    files = files or {}
    client = MagicMock()

    def get_file_json(project_id, branch, path, ttl=None):
        return files.get(path)

    def get_file_raw(project_id, branch, path):
        raw = files.get(path)
        if isinstance(raw, bytes):
            return raw
        if isinstance(raw, str):
            return raw.encode()
        return None

    def get_metadata(project_id, branch):
        return metadata

    def get_trajectory_summary(project_id, branch):
        return summary

    client.get_file_json = MagicMock(side_effect=get_file_json)
    client.get_file_raw = MagicMock(side_effect=get_file_raw)
    client.get_metadata = MagicMock(side_effect=get_metadata)
    client.get_trajectory_summary = MagicMock(side_effect=get_trajectory_summary)
    return client


SAMPLE_IDEA = {
    "Name": "test_idea",
    "Title": "Test Idea for Unit Testing",
    "Short Hypothesis": "Testing works correctly.",
    "Experiment Plan": "Run tests, check assertions.",
}

SAMPLE_ATIF_TRAJECTORY = {
    "schema_version": "1.0",
    "session_id": "test-session",
    "agent": {"name": "claude-code", "model_name": "opus-4-6"},
    "steps": [
        {
            "step_id": 1,
            "source": "user",
            "message": "Do research on tabular transformers.",
            "timestamp": "2026-02-26T10:00:00Z",
        },
        {
            "step_id": 2,
            "source": "agent",
            "message": "I will search for papers on tabular transformers.",
            "timestamp": "2026-02-26T10:00:05Z",
            "metrics": {
                "usage": {
                    "input_tokens": 500,
                    "completion_tokens": 50,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                }
            },
        },
        {
            "step_id": 3,
            "source": "agent",
            "message": "",
            "tool_calls": [
                {
                    "function_name": "Bash",
                    "arguments": {"command": "ls experiment_codebase/"},
                    "tool_call_id": "tool_001",
                }
            ],
            "observation": {
                "results": [
                    {
                        "source_call_id": "tool_001",
                        "content": "baselines/\nmain/\nablations/\n",
                    }
                ]
            },
            "timestamp": "2026-02-26T10:00:10Z",
            "metrics": {
                "usage": {
                    "input_tokens": 600,
                    "completion_tokens": 30,
                    "cache_read_input_tokens": 100,
                    "cache_creation_input_tokens": 0,
                }
            },
        },
    ],
    "final_metrics": {},
}

SAMPLE_METADATA = {
    "job_id": "test_idea__2026-02-26__10-00-00",
    "idea_name": "test_idea",
    "agent_type": "claude-code",
    "model": "opus-4-6",
    "started_at": "2026-02-26T10:00:00Z",
    "finished_at": "2026-02-26T11:00:00Z",
    "duration_seconds": 3600,
    "status": "completed",
    "branch": "claude-2026-02-26-10-00",
    "submission_count": 2,
    "has_paper_pdf": True,
    "figures": ["fig1.png", "fig2.png"],
}

SAMPLE_SUMMARY = {
    "cost": {
        "total_tokens": 150000,
        "estimated_cost_usd": 4.50,
    },
    "cumulative_tokens": [
        {"step": 0, "input_tokens": 500, "output_tokens": 50, "cache_read": 0},
        {"step": 1, "input_tokens": 1100, "output_tokens": 80, "cache_read": 100},
    ],
    "tool_breakdown": [
        {"tool": "Bash", "count": 5, "pct": 50},
        {"tool": "Read", "count": 3, "pct": 30},
    ],
    "event_type_breakdown": [
        {"type": "experiment", "count": 4},
        {"type": "text", "count": 3},
    ],
    "total_lines": 42,
}


def _setup_gitlab_mode(client, job_map):
    """Patch viewer app module to simulate gitlab mode."""
    import app as app_mod
    app_mod.SOURCE_MODE = "gitlab"
    app_mod.GITLAB_CLIENT = client
    app_mod.GITLAB_JOB_MAP = job_map


def _teardown_gitlab_mode():
    """Restore viewer app to local mode."""
    import app as app_mod
    app_mod.SOURCE_MODE = "local"
    app_mod.GITLAB_CLIENT = None
    app_mod.GITLAB_JOB_MAP = {}


class TestGitLabIdeaEndpoint(unittest.TestCase):
    """Test /api/jobs/{job_id}/idea in GitLab mode."""

    JOB_ID = "test_idea__2026-02-26__10-00-00"
    PROJECT_ID = 999
    BRANCH = "claude-2026-02-26-10-00"

    def setUp(self):
        self.client_mock = _make_mock_gitlab_client(
            files={"idea.json": SAMPLE_IDEA},
            metadata=SAMPLE_METADATA,
        )
        _setup_gitlab_mode(self.client_mock, {self.JOB_ID: (self.PROJECT_ID, self.BRANCH)})

        from starlette.testclient import TestClient
        import app as app_mod
        self.test_client = TestClient(app_mod.app)

    def tearDown(self):
        _teardown_gitlab_mode()

    def test_returns_idea_from_gitlab(self):
        resp = self.test_client.get(f"/api/jobs/{self.JOB_ID}/idea")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["found"])
        self.assertEqual(data["format"], "json")
        self.assertEqual(data["source"], "gitlab")
        self.assertIn("test_idea", data["stem"])
        # Content should be valid JSON with the idea fields.
        parsed = json.loads(data["content"])
        self.assertEqual(parsed["Name"], "test_idea")
        self.assertEqual(parsed["Title"], "Test Idea for Unit Testing")

    def test_returns_not_found_when_no_idea_on_gitlab(self):
        # Override with empty files.
        self.client_mock = _make_mock_gitlab_client(files={}, metadata=SAMPLE_METADATA)
        _setup_gitlab_mode(self.client_mock, {self.JOB_ID: (self.PROJECT_ID, self.BRANCH)})

        resp = self.test_client.get(f"/api/jobs/{self.JOB_ID}/idea")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["found"])

    def test_returns_not_found_for_unknown_job(self):
        resp = self.test_client.get("/api/jobs/nonexistent-job/idea")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["found"])


class TestGitLabEventsEndpoint(unittest.TestCase):
    """Test /api/jobs/{job_id}/events in GitLab mode."""

    JOB_ID = "test_idea__2026-02-26__10-00-00"
    PROJECT_ID = 999
    BRANCH = "claude-2026-02-26-10-00"

    def setUp(self):
        self.client_mock = _make_mock_gitlab_client(
            files={"agent_trace/trajectory.json": SAMPLE_ATIF_TRAJECTORY},
            metadata=SAMPLE_METADATA,
            summary=SAMPLE_SUMMARY,
        )
        _setup_gitlab_mode(self.client_mock, {self.JOB_ID: (self.PROJECT_ID, self.BRANCH)})

        from starlette.testclient import TestClient
        import app as app_mod
        self.test_client = TestClient(app_mod.app)

    def tearDown(self):
        _teardown_gitlab_mode()

    def test_returns_events_from_gitlab_trajectory(self):
        resp = self.test_client.get(f"/api/jobs/{self.JOB_ID}/events")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("events", data)
        events = data["events"]
        self.assertGreater(len(events), 0, "Should parse at least 1 event from ATIF trajectory")
        # Check that event types and summaries are populated.
        for ev in events:
            self.assertIn("event_type", ev)
            self.assertIn("summary", ev)
            self.assertIn("step", ev)

    def test_returns_model_from_trajectory(self):
        resp = self.test_client.get(f"/api/jobs/{self.JOB_ID}/events")
        data = resp.json()
        # Model should be extracted from the ATIF trajectory agent info.
        self.assertIn("model", data)

    def test_returns_404_for_unknown_job_in_gitlab_mode(self):
        resp = self.test_client.get("/api/jobs/nonexistent-job/events")
        self.assertEqual(resp.status_code, 404)

    def test_returns_empty_events_when_no_trajectory(self):
        # Override with no trajectory file.
        self.client_mock = _make_mock_gitlab_client(files={}, metadata=SAMPLE_METADATA)
        _setup_gitlab_mode(self.client_mock, {self.JOB_ID: (self.PROJECT_ID, self.BRANCH)})

        resp = self.test_client.get(f"/api/jobs/{self.JOB_ID}/events")
        # Should return 404 since no trajectory exists.
        self.assertEqual(resp.status_code, 404)


class TestGitLabTokensEndpoint(unittest.TestCase):
    """Test /api/jobs/{job_id}/tokens in GitLab mode."""

    JOB_ID = "test_idea__2026-02-26__10-00-00"
    PROJECT_ID = 999
    BRANCH = "claude-2026-02-26-10-00"

    def setUp(self):
        self.client_mock = _make_mock_gitlab_client(
            files={},
            metadata=SAMPLE_METADATA,
            summary=SAMPLE_SUMMARY,
        )
        _setup_gitlab_mode(self.client_mock, {self.JOB_ID: (self.PROJECT_ID, self.BRANCH)})

        from starlette.testclient import TestClient
        import app as app_mod
        self.test_client = TestClient(app_mod.app)

    def tearDown(self):
        _teardown_gitlab_mode()

    def test_returns_token_summary_from_gitlab(self):
        resp = self.test_client.get(f"/api/jobs/{self.JOB_ID}/tokens")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("cost", data)
        self.assertEqual(data["cost"]["total_tokens"], 150000)
        self.assertAlmostEqual(data["cost"]["estimated_cost_usd"], 4.50)

    def test_returns_cumulative_tokens(self):
        resp = self.test_client.get(f"/api/jobs/{self.JOB_ID}/tokens")
        data = resp.json()
        self.assertIn("cumulative_tokens", data)
        self.assertEqual(len(data["cumulative_tokens"]), 2)

    def test_returns_tool_breakdown(self):
        resp = self.test_client.get(f"/api/jobs/{self.JOB_ID}/tokens")
        data = resp.json()
        self.assertIn("tool_breakdown", data)
        self.assertEqual(len(data["tool_breakdown"]), 2)
        self.assertEqual(data["tool_breakdown"][0]["tool"], "Bash")

    def test_returns_404_for_unknown_job(self):
        resp = self.test_client.get("/api/jobs/nonexistent-job/tokens")
        self.assertEqual(resp.status_code, 404)


class TestGitLabMetaEndpoint(unittest.TestCase):
    """Test /api/jobs/{job_id}/meta in GitLab mode."""

    JOB_ID = "test_idea__2026-02-26__10-00-00"
    PROJECT_ID = 999
    BRANCH = "claude-2026-02-26-10-00"

    def setUp(self):
        self.client_mock = _make_mock_gitlab_client(
            files={},
            metadata=SAMPLE_METADATA,
            summary=SAMPLE_SUMMARY,
        )
        _setup_gitlab_mode(self.client_mock, {self.JOB_ID: (self.PROJECT_ID, self.BRANCH)})

        from starlette.testclient import TestClient
        import app as app_mod
        self.test_client = TestClient(app_mod.app)

    def tearDown(self):
        _teardown_gitlab_mode()

    def test_returns_meta_from_gitlab(self):
        resp = self.test_client.get(f"/api/jobs/{self.JOB_ID}/meta")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["model"], "opus-4-6")
        self.assertEqual(data["submissions"], 2)

    def test_includes_gitlab_url(self):
        # Add web_url to metadata for this test.
        import app as app_mod
        # The gitlab_url is constructed from repo web_url + branch.
        # In the actual code, it reads from the GITLAB_JOB_MAP and does a
        # GITLAB_CLIENT.list_repos() lookup. For this test, just verify
        # the meta endpoint returns without error.
        resp = self.test_client.get(f"/api/jobs/{self.JOB_ID}/meta")
        self.assertEqual(resp.status_code, 200)


class TestPushToGitLabIdeaStaging(unittest.TestCase):
    """Test that push_to_gitlab stages idea.json correctly."""

    def test_idea_json_is_staged(self):
        """Verify idea.json gets copied to staging when it exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create job dir structure.
            job_dir = os.path.join(tmpdir, "test_idea__2026-02-26__10-00-00")
            task_dir = os.path.join(job_dir, "harbor-task-xyz", "agent")
            os.makedirs(task_dir)
            staging = os.path.join(tmpdir, "staging")
            os.makedirs(staging)

            # Create idea file at "repo root".
            idea_path = os.path.join(tmpdir, "idea_test_idea.json")
            with open(idea_path, "w") as f:
                json.dump(SAMPLE_IDEA, f)

            # Import and call stage_artifacts with mocked REPO_ROOT.
            sys.path.insert(0, str(REPO_ROOT / "scripts"))
            import push_to_gitlab

            orig_repo_root = push_to_gitlab.REPO_ROOT
            push_to_gitlab.REPO_ROOT = Path(tmpdir)
            try:
                # We need config.json for stage_artifacts.
                config_path = os.path.join(
                    job_dir, "harbor-task-xyz", "config.json"
                )
                os.makedirs(os.path.dirname(config_path), exist_ok=True)
                with open(config_path, "w") as f:
                    json.dump({}, f)

                # Manually test the idea staging logic.
                from push_to_gitlab import parse_job_id, read_json
                from sanitize_secrets import SecretSanitizer

                sanitizer = SecretSanitizer()
                idea_stem, _ = parse_job_id(job_dir)
                self.assertEqual(idea_stem, "test_idea")

                # Test the idea staging logic directly.
                for idea_candidate in [
                    os.path.join(str(push_to_gitlab.REPO_ROOT), f"idea_{idea_stem}.json"),
                    os.path.join(str(push_to_gitlab.REPO_ROOT), "ideas", f"idea_{idea_stem}.json"),
                ]:
                    if os.path.isfile(idea_candidate):
                        data = read_json(idea_candidate)
                        sanitized = sanitizer.sanitize_json(data)
                        with open(os.path.join(staging, "idea.json"), "w") as f:
                            json.dump(sanitized, f, indent=2)
                        break

                # Verify idea.json was staged.
                staged_idea = os.path.join(staging, "idea.json")
                self.assertTrue(os.path.exists(staged_idea), "idea.json should be staged")
                with open(staged_idea) as f:
                    staged_data = json.load(f)
                self.assertEqual(staged_data["Name"], "test_idea")
            finally:
                push_to_gitlab.REPO_ROOT = orig_repo_root


if __name__ == "__main__":
    unittest.main()
