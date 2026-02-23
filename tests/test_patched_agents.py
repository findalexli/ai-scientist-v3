"""
Unit tests for PatchedClaudeCode and PatchedGeminiCli.

These tests mock the Harbor dependency so they can run outside a Harbor
container. Run with:  python3 tests/test_patched_agents.py
"""

import os
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock Harbor modules before importing our patched agents
# ---------------------------------------------------------------------------

# ExecInput — lightweight stand-in
class ExecInput:
    def __init__(self, command="", cwd=None, env=None, timeout_sec=None):
        self.command = command
        self.cwd = cwd
        self.env = env
        self.timeout_sec = timeout_sec

    def __repr__(self):
        return f"ExecInput(command={self.command!r})"


# Base class mock
class BaseInstalledAgent:
    def __init__(self, *args, **kwargs):
        pass


# ClaudeCode mock — returns 2 commands (install + run)
class MockClaudeCode(BaseInstalledAgent):
    INSTALL_CMD = "npm install -g @anthropic-ai/claude-code"
    RUN_CMD = "claude -p 'hello' --model opus"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logs_dir = Path(tempfile.mkdtemp())

    def create_run_agent_commands(self, instruction):
        return [
            ExecInput(command=self.INSTALL_CMD),
            ExecInput(command=self.RUN_CMD, cwd="/app", env={"FOO": "bar"}, timeout_sec=3600),
        ]


# GeminiCli mock — returns 1 command
class MockGeminiCli(BaseInstalledAgent):
    RUN_CMD = "gemini -p 'hello' -y -m gemini-3.1-pro-preview 2>&1 </dev/null | tee /logs/agent/gemini-cli.txt"

    def create_run_agent_commands(self, instruction):
        return [
            ExecInput(command=self.RUN_CMD, cwd="/app", env={"GEMINI_API_KEY": "key"}, timeout_sec=3600),
        ]


# Inject mock modules into sys.modules
def _install_harbor_mocks():
    harbor = types.ModuleType("harbor")
    harbor_agents = types.ModuleType("harbor.agents")
    harbor_agents_installed = types.ModuleType("harbor.agents.installed")
    harbor_agents_installed_base = types.ModuleType("harbor.agents.installed.base")
    harbor_agents_installed_claude_code = types.ModuleType("harbor.agents.installed.claude_code")
    harbor_agents_installed_gemini_cli = types.ModuleType("harbor.agents.installed.gemini_cli")

    harbor_agents_installed_base.ExecInput = ExecInput
    harbor_agents_installed_base.BaseInstalledAgent = BaseInstalledAgent
    harbor_agents_installed_claude_code.ClaudeCode = MockClaudeCode
    harbor_agents_installed_gemini_cli.GeminiCli = MockGeminiCli

    sys.modules["harbor"] = harbor
    sys.modules["harbor.agents"] = harbor_agents
    sys.modules["harbor.agents.installed"] = harbor_agents_installed
    sys.modules["harbor.agents.installed.base"] = harbor_agents_installed_base
    sys.modules["harbor.agents.installed.claude_code"] = harbor_agents_installed_claude_code
    sys.modules["harbor.agents.installed.gemini_cli"] = harbor_agents_installed_gemini_cli


_install_harbor_mocks()

# Now we can import the real patched agents
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from local_harbor_agents.patched_claude_code import PatchedClaudeCode
from local_harbor_agents.patched_gemini_cli import PatchedGeminiCli


# ===========================================================================
# PatchedClaudeCode tests
# ===========================================================================

class TestPatchedClaudeCodeInit(unittest.TestCase):
    def test_default_interval(self):
        agent = PatchedClaudeCode()
        self.assertEqual(agent._artifact_sync_interval_sec, 180)

    def test_custom_interval(self):
        agent = PatchedClaudeCode(artifact_sync_interval_sec=300)
        self.assertEqual(agent._artifact_sync_interval_sec, 300)

    def test_interval_clamped_to_minimum(self):
        agent = PatchedClaudeCode(artifact_sync_interval_sec=10)
        self.assertEqual(agent._artifact_sync_interval_sec, 30)

    def test_invalid_interval_string(self):
        agent = PatchedClaudeCode(artifact_sync_interval_sec="not_a_number")
        self.assertEqual(agent._artifact_sync_interval_sec, 180)

    def test_invalid_interval_none(self):
        agent = PatchedClaudeCode(artifact_sync_interval_sec=None)
        self.assertEqual(agent._artifact_sync_interval_sec, 180)


class TestPatchedClaudeCodeWrap(unittest.TestCase):
    def setUp(self):
        self.agent = PatchedClaudeCode(artifact_sync_interval_sec=60)
        self.wrapped = self.agent._wrap_with_artifact_sync("echo test_command")

    def test_contains_base_command(self):
        self.assertIn("echo test_command", self.wrapped)

    def test_contains_sync_functions(self):
        self.assertIn("copy_tree()", self.wrapped)
        self.assertIn("copy_file()", self.wrapped)
        self.assertIn("sync_artifacts()", self.wrapped)

    def test_contains_trap(self):
        self.assertIn("trap", self.wrapped)

    def test_contains_sleep_interval(self):
        self.assertIn("sleep 60", self.wrapped)

    def test_syncs_experiment_codebase(self):
        self.assertIn("experiment_codebase", self.wrapped)

    def test_syncs_figures(self):
        self.assertIn("figures", self.wrapped)

    def test_syncs_literature(self):
        self.assertIn("literature", self.wrapped)

    def test_syncs_paper_pdf(self):
        self.assertIn("paper.pdf", self.wrapped)

    def test_syncs_paper_tex(self):
        self.assertIn("paper.tex", self.wrapped)

    def test_syncs_submissions(self):
        self.assertIn("submissions", self.wrapped)

    def test_syncs_claude_sessions(self):
        self.assertIn("claude_sessions", self.wrapped)

    def test_captures_exit_code(self):
        self.assertIn("AGENT_EXIT=$?", self.wrapped)
        self.assertIn('exit "$AGENT_EXIT"', self.wrapped)

    def test_kills_sync_process(self):
        self.assertIn("SYNC_PID", self.wrapped)
        self.assertIn('kill "$SYNC_PID"', self.wrapped)

    def test_fixes_permissions(self):
        # Claude-specific: chmod session files for host readability
        self.assertIn("chmod", self.wrapped)

    def test_wrapped_in_bash(self):
        self.assertTrue(self.wrapped.startswith("bash -c "))


class TestPatchedClaudeCodeCommands(unittest.TestCase):
    def test_wraps_second_command(self):
        agent = PatchedClaudeCode()
        commands = agent.create_run_agent_commands("do stuff")
        # Should have 2 commands: install (unchanged) + run (wrapped)
        self.assertEqual(len(commands), 2)
        # First command (install) should be untouched
        self.assertEqual(commands[0].command, MockClaudeCode.INSTALL_CMD)
        # Second command (run) should be wrapped with sync logic
        self.assertIn("sync_artifacts", commands[1].command)
        # The base command is embedded (quotes get shell-escaped by shlex.quote)
        self.assertIn("--model opus", commands[1].command)
        self.assertIn("claude -p", commands[1].command)

    def test_preserves_env(self):
        agent = PatchedClaudeCode()
        commands = agent.create_run_agent_commands("do stuff")
        self.assertEqual(commands[1].env, {"FOO": "bar"})

    def test_preserves_cwd(self):
        agent = PatchedClaudeCode()
        commands = agent.create_run_agent_commands("do stuff")
        self.assertEqual(commands[1].cwd, "/app")

    def test_preserves_timeout(self):
        agent = PatchedClaudeCode()
        commands = agent.create_run_agent_commands("do stuff")
        self.assertEqual(commands[1].timeout_sec, 3600)


class TestPatchedClaudeCodeSessionDir(unittest.TestCase):
    def setUp(self):
        self.agent = PatchedClaudeCode()
        self.sessions_root = self.agent.logs_dir / "sessions"

    def test_returns_none_when_no_sessions(self):
        self.assertIsNone(self.agent._get_session_dir())

    def test_returns_none_when_empty_projects(self):
        (self.sessions_root / "projects").mkdir(parents=True)
        self.assertIsNone(self.agent._get_session_dir())

    def test_finds_uuid_jsonl(self):
        workspace = self.sessions_root / "projects" / "workspace1"
        workspace.mkdir(parents=True)
        session_file = workspace / "a1b2c3d4-e5f6-7890-abcd-ef1234567890.jsonl"
        session_file.write_text("test")
        result = self.agent._get_session_dir()
        self.assertEqual(result, workspace)

    def test_prefers_top_level_over_nested(self):
        workspace = self.sessions_root / "projects" / "workspace1"
        workspace.mkdir(parents=True)
        nested = workspace / "subagent" / "nested"
        nested.mkdir(parents=True)

        # Create top-level (older)
        top_file = workspace / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl"
        top_file.write_text("top")

        # Create nested (newer — should still be ignored because top-level exists)
        nested_file = nested / "11111111-2222-3333-4444-555555555555.jsonl"
        nested_file.write_text("nested")

        result = self.agent._get_session_dir()
        self.assertEqual(result, workspace)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.agent.logs_dir, ignore_errors=True)


# ===========================================================================
# PatchedGeminiCli tests
# ===========================================================================

class TestPatchedGeminiCliInit(unittest.TestCase):
    def test_default_interval(self):
        agent = PatchedGeminiCli()
        self.assertEqual(agent._artifact_sync_interval_sec, 180)

    def test_custom_interval(self):
        agent = PatchedGeminiCli(artifact_sync_interval_sec=300)
        self.assertEqual(agent._artifact_sync_interval_sec, 300)

    def test_interval_clamped_to_minimum(self):
        agent = PatchedGeminiCli(artifact_sync_interval_sec=10)
        self.assertEqual(agent._artifact_sync_interval_sec, 30)

    def test_invalid_interval_string(self):
        agent = PatchedGeminiCli(artifact_sync_interval_sec="not_a_number")
        self.assertEqual(agent._artifact_sync_interval_sec, 180)

    def test_invalid_interval_none(self):
        agent = PatchedGeminiCli(artifact_sync_interval_sec=None)
        self.assertEqual(agent._artifact_sync_interval_sec, 180)


class TestPatchedGeminiCliWrap(unittest.TestCase):
    def setUp(self):
        self.agent = PatchedGeminiCli(artifact_sync_interval_sec=90)
        self.wrapped = self.agent._wrap_with_artifact_sync("echo gemini_cmd")

    def test_contains_base_command(self):
        self.assertIn("echo gemini_cmd", self.wrapped)

    def test_contains_sync_functions(self):
        self.assertIn("copy_tree()", self.wrapped)
        self.assertIn("copy_file()", self.wrapped)
        self.assertIn("sync_artifacts()", self.wrapped)

    def test_contains_trap(self):
        self.assertIn("trap", self.wrapped)

    def test_contains_sleep_interval(self):
        self.assertIn("sleep 90", self.wrapped)

    def test_syncs_experiment_codebase(self):
        self.assertIn("experiment_codebase", self.wrapped)

    def test_syncs_figures(self):
        self.assertIn("figures", self.wrapped)

    def test_syncs_literature(self):
        self.assertIn("literature", self.wrapped)

    def test_syncs_paper_pdf(self):
        self.assertIn("paper.pdf", self.wrapped)

    def test_syncs_paper_tex(self):
        self.assertIn("paper.tex", self.wrapped)

    def test_syncs_submissions(self):
        self.assertIn("submissions", self.wrapped)

    def test_syncs_gemini_sessions(self):
        self.assertIn("gemini_sessions", self.wrapped)

    def test_does_not_sync_claude_sessions(self):
        self.assertNotIn("claude_sessions", self.wrapped)

    def test_captures_exit_code(self):
        self.assertIn("AGENT_EXIT=$?", self.wrapped)
        self.assertIn('exit "$AGENT_EXIT"', self.wrapped)

    def test_kills_sync_process(self):
        self.assertIn("SYNC_PID", self.wrapped)
        self.assertIn('kill "$SYNC_PID"', self.wrapped)

    def test_no_chmod(self):
        # Gemini doesn't need the chmod fix that Claude needs
        self.assertNotIn("chmod", self.wrapped)

    def test_wrapped_in_bash(self):
        self.assertTrue(self.wrapped.startswith("bash -c "))


class TestPatchedGeminiCliCommands(unittest.TestCase):
    def test_wraps_first_command(self):
        agent = PatchedGeminiCli()
        commands = agent.create_run_agent_commands("do stuff")
        # Gemini returns 1 command
        self.assertEqual(len(commands), 1)
        # It should be wrapped with sync logic
        self.assertIn("sync_artifacts", commands[0].command)
        # The base command is embedded (quotes get shell-escaped by shlex.quote)
        self.assertIn("gemini -p", commands[0].command)
        self.assertIn("-y -m gemini-3.1-pro-preview", commands[0].command)

    def test_preserves_env(self):
        agent = PatchedGeminiCli()
        commands = agent.create_run_agent_commands("do stuff")
        self.assertEqual(commands[0].env, {"GEMINI_API_KEY": "key"})

    def test_preserves_cwd(self):
        agent = PatchedGeminiCli()
        commands = agent.create_run_agent_commands("do stuff")
        self.assertEqual(commands[0].cwd, "/app")

    def test_preserves_timeout(self):
        agent = PatchedGeminiCli()
        commands = agent.create_run_agent_commands("do stuff")
        self.assertEqual(commands[0].timeout_sec, 3600)


# ===========================================================================
# Parity tests — both agents sync the same artifact directories
# ===========================================================================

class TestArtifactSyncParity(unittest.TestCase):
    """Ensure both patched agents sync the same core workspace directories."""

    REQUIRED_ARTIFACTS = [
        "experiment_codebase",
        "figures",
        "literature",
        "paper.pdf",
        "paper.tex",
        "references.bib",
        "review.json",
        "submissions",
        "requirements.txt",
    ]

    def setUp(self):
        self.cc_wrapped = PatchedClaudeCode()._wrap_with_artifact_sync("true")
        self.gc_wrapped = PatchedGeminiCli()._wrap_with_artifact_sync("true")

    def test_all_artifacts_in_claude(self):
        for artifact in self.REQUIRED_ARTIFACTS:
            with self.subTest(artifact=artifact):
                self.assertIn(artifact, self.cc_wrapped)

    def test_all_artifacts_in_gemini(self):
        for artifact in self.REQUIRED_ARTIFACTS:
            with self.subTest(artifact=artifact):
                self.assertIn(artifact, self.gc_wrapped)

    def test_both_write_to_agent_artifacts(self):
        self.assertIn("/logs/agent/artifacts", self.cc_wrapped)
        self.assertIn("/logs/agent/artifacts", self.gc_wrapped)

    def test_both_write_to_verifier_artifacts(self):
        self.assertIn("/logs/verifier/artifacts", self.cc_wrapped)
        self.assertIn("/logs/verifier/artifacts", self.gc_wrapped)


# ===========================================================================
# Claude chmod-in-sync test
# ===========================================================================

class TestClaudeChmodInSync(unittest.TestCase):
    """Verify chmod runs inside sync_artifacts, not just post-agent."""

    def test_chmod_inside_sync_artifacts(self):
        agent = PatchedClaudeCode(artifact_sync_interval_sec=60)
        wrapped = agent._wrap_with_artifact_sync("echo test")
        # Extract the sync_artifacts function body
        sync_start = wrapped.index("sync_artifacts() {")
        # Find the closing brace by counting braces
        depth = 0
        sync_end = sync_start
        for i, ch in enumerate(wrapped[sync_start:], sync_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    sync_end = i
                    break
        sync_body = wrapped[sync_start:sync_end]
        self.assertIn("chmod -R a+rX", sync_body)

    def test_chmod_runs_before_copy_in_sync(self):
        """chmod should appear before the copy calls inside sync_artifacts body."""
        agent = PatchedClaudeCode()
        wrapped = agent._wrap_with_artifact_sync("echo test")
        # Extract just the sync_artifacts body
        sync_start = wrapped.index("sync_artifacts() {")
        sync_body = wrapped[sync_start:]
        chmod_pos = sync_body.index("chmod -R a+rX")
        # First copy_tree call inside sync_artifacts (not the function definition)
        copy_pos = sync_body.index('copy_tree "/app')
        self.assertLess(chmod_pos, copy_pos, "chmod should run before copying artifacts")


if __name__ == "__main__":
    unittest.main()
