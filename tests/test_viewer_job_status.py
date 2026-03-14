"""
Tests for viewer job status detection and filtering.

Tests the get_job_status() logic (artifact sync mtime detection, result.json
completion signal) and the short-lived job filter in _discover_jobs_local().
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "viewer"))

from app import get_job_status, _newest_mtime_in_dir


class TestNewestMtimeInDir(unittest.TestCase):
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_newest_mtime_in_dir(d), 0.0)

    def test_single_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "file.txt")
            with open(p, "w") as f:
                f.write("test")
            result = _newest_mtime_in_dir(d)
            self.assertGreater(result, 0.0)
            self.assertAlmostEqual(result, os.path.getmtime(p), places=1)

    def test_picks_newest(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.path.join(d, "old.txt")
            with open(old, "w") as f:
                f.write("old")
            # Backdate
            os.utime(old, (time.time() - 3600, time.time() - 3600))

            new = os.path.join(d, "new.txt")
            with open(new, "w") as f:
                f.write("new")

            result = _newest_mtime_in_dir(d)
            self.assertAlmostEqual(result, os.path.getmtime(new), places=1)

    def test_respects_max_depth(self):
        with tempfile.TemporaryDirectory() as d:
            # Create a file at depth 3 (should be ignored with max_depth=2)
            deep = os.path.join(d, "a", "b", "c")
            os.makedirs(deep)
            with open(os.path.join(deep, "deep.txt"), "w") as f:
                f.write("deep")

            # Create a file at depth 1 (should be found)
            shallow = os.path.join(d, "a")
            old_time = time.time() - 7200
            shallow_file = os.path.join(shallow, "shallow.txt")
            with open(shallow_file, "w") as f:
                f.write("shallow")
            os.utime(shallow_file, (old_time, old_time))

            result = _newest_mtime_in_dir(d, max_depth=2)
            # Should find shallow.txt but not deep.txt
            self.assertAlmostEqual(result, old_time, places=0)

    def test_nonexistent_dir(self):
        self.assertEqual(_newest_mtime_in_dir("/nonexistent/path"), 0.0)


class TestGetJobStatus(unittest.TestCase):
    """Test get_job_status() with synthetic job directories."""

    def _make_job_dir(self):
        """Create a temporary job directory with harbor-task structure."""
        d = tempfile.mkdtemp()
        task_dir = os.path.join(d, "harbor-task-test__abc")
        os.makedirs(os.path.join(task_dir, "agent", "artifacts"))
        os.makedirs(os.path.join(task_dir, "verifier"))
        return d, task_dir

    def test_completed_with_result_json(self):
        job_dir, task_dir = self._make_job_dir()
        # Write top-level result.json with finished_at
        with open(os.path.join(job_dir, "result.json"), "w") as f:
            json.dump({"started_at": "2026-01-01T00:00:00", "finished_at": "2026-01-01T01:00:00"}, f)
        # Also write a recent artifact (should not override completed)
        with open(os.path.join(task_dir, "agent", "artifacts", "recent.txt"), "w") as f:
            f.write("recent")
        self.assertEqual(get_job_status(job_dir), "completed")

    def test_running_with_recent_artifact(self):
        job_dir, task_dir = self._make_job_dir()
        # No result.json — job hasn't finished
        # Write a recent artifact file (simulating artifact sync)
        with open(os.path.join(task_dir, "agent", "artifacts", "paper.tex"), "w") as f:
            f.write("\\documentclass{article}")
        # Also need an activity file for the fallback
        traj = os.path.join(task_dir, "agent", "trajectory.json")
        with open(traj, "w") as f:
            json.dump({"steps": []}, f)
        self.assertEqual(get_job_status(job_dir), "running")

    def test_running_with_recent_trajectory(self):
        job_dir, task_dir = self._make_job_dir()
        # Backdate artifacts so they don't trigger the 6-min check
        art_file = os.path.join(task_dir, "agent", "artifacts", "old.txt")
        with open(art_file, "w") as f:
            f.write("old")
        os.utime(art_file, (time.time() - 600, time.time() - 600))
        # But trajectory is recent
        traj = os.path.join(task_dir, "agent", "trajectory.json")
        with open(traj, "w") as f:
            json.dump({"steps": []}, f)
        # trajectory is just-written → mtime < 5 min → running
        self.assertEqual(get_job_status(job_dir), "running")

    def test_idle_with_old_artifacts(self):
        job_dir, task_dir = self._make_job_dir()
        # No result.json, old artifacts, old trajectory
        art_file = os.path.join(task_dir, "agent", "artifacts", "old.txt")
        with open(art_file, "w") as f:
            f.write("old")
        os.utime(art_file, (time.time() - 7200, time.time() - 7200))
        traj = os.path.join(task_dir, "agent", "trajectory.json")
        with open(traj, "w") as f:
            json.dump({"steps": []}, f)
        os.utime(traj, (time.time() - 7200, time.time() - 7200))
        self.assertEqual(get_job_status(job_dir), "idle")

    def test_completed_via_verifier_result(self):
        job_dir, task_dir = self._make_job_dir()
        # No top-level result.json, but verifier has one
        os.makedirs(os.path.join(task_dir, "verifier", "artifacts"), exist_ok=True)
        with open(os.path.join(task_dir, "verifier", "artifacts", "result.json"), "w") as f:
            json.dump({"reward": 1}, f)
        # Need an activity file and backdate everything
        traj = os.path.join(task_dir, "agent", "trajectory.json")
        with open(traj, "w") as f:
            json.dump({"steps": []}, f)
        os.utime(traj, (time.time() - 7200, time.time() - 7200))
        art_file = os.path.join(task_dir, "agent", "artifacts", "old.txt")
        with open(art_file, "w") as f:
            f.write("old")
        os.utime(art_file, (time.time() - 7200, time.time() - 7200))
        self.assertEqual(get_job_status(job_dir), "completed")

    def test_result_json_without_finished_at_not_completed(self):
        job_dir, task_dir = self._make_job_dir()
        # result.json exists but no finished_at (job started but still running)
        with open(os.path.join(job_dir, "result.json"), "w") as f:
            json.dump({"started_at": "2026-01-01T00:00:00"}, f)
        traj = os.path.join(task_dir, "agent", "trajectory.json")
        with open(traj, "w") as f:
            json.dump({"steps": []}, f)
        os.utime(traj, (time.time() - 7200, time.time() - 7200))
        art_file = os.path.join(task_dir, "agent", "artifacts", "old.txt")
        with open(art_file, "w") as f:
            f.write("old")
        os.utime(art_file, (time.time() - 7200, time.time() - 7200))
        # Should NOT be completed — no finished_at
        self.assertNotEqual(get_job_status(job_dir), "completed")

    def test_unknown_without_activity_file(self):
        with tempfile.TemporaryDirectory() as job_dir:
            # Empty job dir, no harbor-task subdir
            self.assertEqual(get_job_status(job_dir), "unknown")


class TestJobDurationFilter(unittest.TestCase):
    """Test that the 40-minute filter in _discover_jobs_local works correctly."""

    def test_filter_threshold_value(self):
        """Verify the MIN_DURATION_DISPLAY_SEC constant is 40 minutes."""
        # Read the source to verify the constant
        with open(os.path.join(REPO_ROOT, "viewer", "app.py")) as f:
            source = f.read()
        self.assertIn("MIN_DURATION_DISPLAY_SEC = 2400", source)

    def test_filter_skips_running_jobs(self):
        """Verify the filter has a 'running' exemption."""
        with open(os.path.join(REPO_ROOT, "viewer", "app.py")) as f:
            source = f.read()
        # The filter should check status is not "running" before filtering
        self.assertIn('status not in ("running",)', source)


if __name__ == "__main__":
    unittest.main()
