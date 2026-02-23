"""
Tests for ATIF trajectory generation pipeline.

Covers:
  - scripts/generate_atif.py: find_agent_dir, generate_claude_atif, generate_gemini_atif
  - viewer/app.py: find_agent_dir, generate_trajectory, /api/jobs/{job_id}/trajectory

Run with:  python3 tests/test_trajectory_management.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent


# ===========================================================================
# generate_atif.py unit tests (import functions directly)
# ===========================================================================

# We can test find_agent_dir without Harbor since it's pure path logic
sys.path.insert(0, str(REPO_ROOT / "scripts"))
# Can't import generate_atif directly because it imports harbor at module level.
# Instead, extract the find_agent_dir function via exec.
_generate_atif_source = (REPO_ROOT / "scripts" / "generate_atif.py").read_text()

# Extract just the find_agent_dir function
_namespace = {}
exec(
    "from pathlib import Path\n"
    + "\n".join(
        line
        for line in _generate_atif_source.split("\n")
        if not line.startswith("from harbor") and not line.startswith("import harbor")
    ),
    _namespace,
)
_find_agent_dir = _namespace["find_agent_dir"]


class TestGenerateAtifFindAgentDir(unittest.TestCase):
    """Test find_agent_dir from generate_atif.py."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_finds_agent_dir(self):
        agent_dir = self.tmpdir / "harbor-task-abc123" / "agent"
        agent_dir.mkdir(parents=True)
        result = _find_agent_dir(self.tmpdir)
        self.assertEqual(result, agent_dir)

    def test_returns_none_when_no_harbor_task(self):
        (self.tmpdir / "some-other-dir").mkdir()
        result = _find_agent_dir(self.tmpdir)
        self.assertIsNone(result)

    def test_returns_none_when_no_agent_subdir(self):
        (self.tmpdir / "harbor-task-abc123").mkdir()
        # No 'agent' subdirectory
        result = _find_agent_dir(self.tmpdir)
        self.assertIsNone(result)

    def test_finds_with_double_underscore_naming(self):
        agent_dir = self.tmpdir / "harbor-task__XyZ123" / "agent"
        agent_dir.mkdir(parents=True)
        result = _find_agent_dir(self.tmpdir)
        self.assertEqual(result, agent_dir)

    def test_finds_with_complex_naming(self):
        agent_dir = self.tmpdir / "harbor-task-cs3muz__nYznQyt" / "agent"
        agent_dir.mkdir(parents=True)
        result = _find_agent_dir(self.tmpdir)
        self.assertEqual(result, agent_dir)


# ===========================================================================
# viewer/app.py trajectory tests
# ===========================================================================

sys.path.insert(0, str(REPO_ROOT / "viewer"))


class TestViewerFindAgentDir(unittest.TestCase):
    """Test find_agent_dir from viewer/app.py."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_finds_agent_dir(self):
        from app import find_agent_dir
        agent_dir = os.path.join(self.tmpdir, "harbor-task-abc", "agent")
        os.makedirs(agent_dir)
        result = find_agent_dir(self.tmpdir)
        self.assertEqual(result, agent_dir)

    def test_returns_none_for_nonexistent_dir(self):
        from app import find_agent_dir
        result = find_agent_dir("/nonexistent/path/12345")
        self.assertIsNone(result)

    def test_returns_none_when_empty(self):
        from app import find_agent_dir
        result = find_agent_dir(self.tmpdir)
        self.assertIsNone(result)


class TestViewerGenerateTrajectory(unittest.TestCase):
    """Test generate_trajectory from viewer/app.py."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.agent_dir = os.path.join(self.tmpdir, "harbor-task-test", "agent")
        os.makedirs(self.agent_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_none_when_no_agent_dir(self):
        from app import generate_trajectory
        empty = tempfile.mkdtemp()
        result = generate_trajectory(empty)
        self.assertIsNone(result)
        import shutil
        shutil.rmtree(empty, ignore_errors=True)

    def test_returns_existing_fresh_trajectory(self):
        from app import generate_trajectory
        traj_path = os.path.join(self.agent_dir, "trajectory.json")
        with open(traj_path, "w") as f:
            json.dump({"schema_version": "test"}, f)
        result = generate_trajectory(self.tmpdir)
        self.assertEqual(result, traj_path)

    @patch("app.HARBOR_PYTHON", "/nonexistent/python")
    def test_returns_none_when_no_harbor_python(self):
        from app import generate_trajectory
        result = generate_trajectory(self.tmpdir)
        self.assertIsNone(result)

    def test_skips_generation_if_fresh(self):
        """Should not call subprocess if trajectory is < 60s old."""
        from app import generate_trajectory
        traj_path = os.path.join(self.agent_dir, "trajectory.json")
        with open(traj_path, "w") as f:
            json.dump({"fresh": True}, f)

        with patch("subprocess.run") as mock_run:
            result = generate_trajectory(self.tmpdir)
            mock_run.assert_not_called()
        self.assertEqual(result, traj_path)


class TestTrajectoryEndpoint(unittest.TestCase):
    """Test the /api/jobs/{job_id}/trajectory FastAPI endpoint."""

    def setUp(self):
        from app import app
        self.tmpdir = tempfile.mkdtemp()
        self.job_id = "test-job-2026"
        self.job_dir = os.path.join(self.tmpdir, self.job_id)
        self.agent_dir = os.path.join(self.job_dir, "harbor-task-test", "agent")
        os.makedirs(self.agent_dir)

        # Write a trajectory file
        self.traj_data = {
            "schema_version": "ATIF-v1.2",
            "session_id": "test",
            "agent": {"name": "test-agent"},
            "steps": [{"step_id": 1, "source": "user", "message": "hello"}],
        }
        with open(os.path.join(self.agent_dir, "trajectory.json"), "w") as f:
            json.dump(self.traj_data, f)

        # Also need a transcript file so get_job_status works
        with open(os.path.join(self.agent_dir, "claude-code.txt"), "w") as f:
            f.write("{}\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_returns_trajectory_json(self):
        from starlette.testclient import TestClient
        import app as app_module

        original_jobs_dir = app_module.JOBS_DIR
        app_module.JOBS_DIR = self.tmpdir
        try:
            client = TestClient(app_module.app)
            resp = client.get(f"/api/jobs/{self.job_id}/trajectory")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["schema_version"], "ATIF-v1.2")
            self.assertEqual(len(data["steps"]), 1)
        finally:
            app_module.JOBS_DIR = original_jobs_dir

    def test_returns_404_for_missing_job(self):
        from starlette.testclient import TestClient
        import app as app_module

        original_jobs_dir = app_module.JOBS_DIR
        app_module.JOBS_DIR = self.tmpdir
        try:
            client = TestClient(app_module.app)
            resp = client.get("/api/jobs/nonexistent-job/trajectory")
            self.assertEqual(resp.status_code, 404)
        finally:
            app_module.JOBS_DIR = original_jobs_dir

    def test_returns_404_when_no_agent_dir(self):
        from starlette.testclient import TestClient
        import app as app_module

        empty_job = os.path.join(self.tmpdir, "empty-job")
        os.makedirs(empty_job)

        original_jobs_dir = app_module.JOBS_DIR
        app_module.JOBS_DIR = self.tmpdir
        try:
            client = TestClient(app_module.app)
            resp = client.get("/api/jobs/empty-job/trajectory")
            self.assertEqual(resp.status_code, 404)
        finally:
            app_module.JOBS_DIR = original_jobs_dir


# ===========================================================================
# Integration test: generate_atif.py CLI (requires Harbor Python 3.13)
# ===========================================================================

HARBOR_PYTHON = "/home/alex/.local/share/uv/tools/harbor/bin/python3"
GENERATE_ATIF = str(REPO_ROOT / "scripts" / "generate_atif.py")


@unittest.skipUnless(
    os.path.isfile(HARBOR_PYTHON),
    "Harbor Python 3.13 not available"
)
class TestGenerateAtifCLI(unittest.TestCase):
    """Integration tests that run generate_atif.py as a subprocess."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.agent_dir = self.tmpdir / "harbor-task-test" / "agent"
        self.agent_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_exits_1_when_no_agent_logs(self):
        result = subprocess.run(
            [HARBOR_PYTHON, GENERATE_ATIF, "--job-dir", str(self.tmpdir)],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("No recognized agent logs", result.stderr)

    def test_exits_1_when_no_agent_dir(self):
        empty = Path(tempfile.mkdtemp())
        try:
            result = subprocess.run(
                [HARBOR_PYTHON, GENERATE_ATIF, "--job-dir", str(empty)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("No agent directory", result.stderr)
        finally:
            import shutil
            shutil.rmtree(empty, ignore_errors=True)

    def test_claude_generates_trajectory(self):
        """Write a minimal claude-code.txt and verify trajectory is generated."""
        # A minimal valid JSONL that the converter can parse
        events = [
            {"type": "system", "subtype": "init", "cwd": "/app",
             "session_id": "test-123", "model": "claude-opus-4-6",
             "version": "1.0"},
            {"type": "assistant", "message": {"id": "msg_1", "role": "assistant",
             "model": "claude-opus-4-6", "content": [{"type": "text", "text": "Hello"}],
             "usage": {"input_tokens": 10, "output_tokens": 5,
                       "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}},
             "duration_ms": 100, "duration_api_ms": 80},
        ]
        with open(self.agent_dir / "claude-code.txt", "w") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        result = subprocess.run(
            [HARBOR_PYTHON, GENERATE_ATIF, "--job-dir", str(self.tmpdir)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("steps", result.stdout)

        # Validate the generated trajectory
        traj_path = self.agent_dir / "trajectory.json"
        self.assertTrue(traj_path.exists())
        data = json.loads(traj_path.read_text())
        self.assertIn("schema_version", data)
        self.assertIn("steps", data)

    def test_gemini_generates_trajectory(self):
        """Write a Gemini trajectory with list content and verify fix + conversion."""
        gemini_data = {
            "sessionId": "gemini-test-123",
            "messages": [
                {"type": "user", "content": [{"text": "Fix this bug"}],
                 "timestamp": "2026-02-21T20:00:00Z"},
                {"type": "gemini", "content": "I'll fix it now",
                 "thoughts": [], "toolCalls": [],
                 "tokens": {"input": 50, "output": 20, "cached": 0, "tool": 0, "thoughts": 0},
                 "model": "gemini-3.1-pro-preview",
                 "timestamp": "2026-02-21T20:00:01Z"},
            ],
        }
        with open(self.agent_dir / "gemini-cli.trajectory.json", "w") as f:
            json.dump(gemini_data, f)

        result = subprocess.run(
            [HARBOR_PYTHON, GENERATE_ATIF, "--job-dir", str(self.tmpdir)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("2 steps", result.stdout)

        # Validate
        traj_path = self.agent_dir / "trajectory.json"
        self.assertTrue(traj_path.exists())
        data = json.loads(traj_path.read_text())
        self.assertEqual(data["schema_version"], "ATIF-v1.6")
        self.assertEqual(len(data["steps"]), 2)
        # User message content should be a string (fixed), not a list
        self.assertIsInstance(data["steps"][0]["message"], str)
        self.assertEqual(data["steps"][0]["message"], "Fix this bug")

    def test_gemini_content_fix_applied(self):
        """Specifically test that list-of-dicts content is converted to string."""
        gemini_data = {
            "sessionId": "content-fix-test",
            "messages": [
                {"type": "user",
                 "content": [{"text": "Part 1"}, {"text": "Part 2"}],
                 "timestamp": "2026-02-21T20:00:00Z"},
            ],
        }
        with open(self.agent_dir / "gemini-cli.trajectory.json", "w") as f:
            json.dump(gemini_data, f)

        result = subprocess.run(
            [HARBOR_PYTHON, GENERATE_ATIF, "--job-dir", str(self.tmpdir)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

        data = json.loads((self.agent_dir / "trajectory.json").read_text())
        # Should be concatenated with newline
        self.assertEqual(data["steps"][0]["message"], "Part 1\nPart 2")


# ===========================================================================
# Integration test: validate real job trajectories (if available)
# ===========================================================================

JOBS_DIR = REPO_ROOT / "jobs"


@unittest.skipUnless(
    os.path.isfile(HARBOR_PYTHON) and JOBS_DIR.is_dir(),
    "Harbor Python or jobs directory not available"
)
class TestRealJobTrajectories(unittest.TestCase):
    """Validate generate_atif.py against real job data."""

    def _run_and_validate(self, job_dir: Path):
        result = subprocess.run(
            [HARBOR_PYTHON, GENERATE_ATIF, "--job-dir", str(job_dir)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            self.skipTest(f"No agent logs in {job_dir.name}: {result.stderr.strip()}")

        # Find the generated trajectory
        for entry in job_dir.iterdir():
            if entry.name.startswith("harbor-task"):
                traj = entry / "agent" / "trajectory.json"
                if traj.exists():
                    data = json.loads(traj.read_text())
                    self.assertIn("schema_version", data)
                    self.assertIn("steps", data)
                    self.assertGreater(len(data["steps"]), 0)
                    return data
        self.fail("No trajectory.json found after generation")

    def test_latest_claude_job(self):
        """Find the most recent Claude job and validate trajectory."""
        for name in sorted(os.listdir(JOBS_DIR), reverse=True):
            job_dir = JOBS_DIR / name
            if not job_dir.is_dir():
                continue
            for entry in job_dir.iterdir():
                if entry.name.startswith("harbor-task"):
                    if (entry / "agent" / "claude-code.txt").exists():
                        data = self._run_and_validate(job_dir)
                        self.assertEqual(data["schema_version"], "ATIF-v1.2")
                        return
        self.skipTest("No Claude jobs found")

    def test_latest_gemini_job(self):
        """Find the most recent Gemini job and validate trajectory."""
        for name in sorted(os.listdir(JOBS_DIR), reverse=True):
            job_dir = JOBS_DIR / name
            if not job_dir.is_dir():
                continue
            for entry in job_dir.iterdir():
                if entry.name.startswith("harbor-task"):
                    if (entry / "agent" / "gemini-cli.trajectory.json").exists():
                        data = self._run_and_validate(job_dir)
                        self.assertEqual(data["schema_version"], "ATIF-v1.6")
                        # Verify user messages have string content (not lists)
                        for step in data["steps"]:
                            if step["source"] == "user":
                                self.assertIsInstance(step["message"], str)
                        return
        self.skipTest("No Gemini jobs found")


if __name__ == "__main__":
    unittest.main()
