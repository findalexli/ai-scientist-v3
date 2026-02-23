import re
import shlex
from pathlib import Path

from harbor.agents.installed.base import ExecInput
from harbor.agents.installed.claude_code import ClaudeCode

_UUID_JSONL_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.jsonl$"
)


class PatchedClaudeCode(ClaudeCode):
    """Drop-in ClaudeCode replacement with safer session selection and log syncing."""

    def __init__(self, artifact_sync_interval_sec: int = 180, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            interval = int(artifact_sync_interval_sec)
        except (TypeError, ValueError):
            interval = 180
        self._artifact_sync_interval_sec = max(interval, 30)

    @staticmethod
    def _path_sort_key(path: Path) -> tuple[float, int, str]:
        try:
            stat = path.stat()
            return (stat.st_mtime, stat.st_size, path.as_posix())
        except OSError:
            return (0.0, 0, path.as_posix())

    def _get_session_dir(self) -> Path | None:
        """Choose the newest primary Claude session log, ignoring subagent logs."""
        sessions_root = self.logs_dir / "sessions"
        project_root = sessions_root / "projects"
        if not project_root.exists():
            return None

        candidate_files = [f for f in project_root.glob("**/*.jsonl") if f.is_file()]
        if not candidate_files:
            return None

        # Primary session files are top-level under projects/<workspace>/*.jsonl.
        top_level_files = [f for f in candidate_files if f.parent.parent == project_root]
        if top_level_files:
            candidate_files = top_level_files

        uuid_named_files = [f for f in candidate_files if _UUID_JSONL_RE.match(f.name)]
        if uuid_named_files:
            candidate_files = uuid_named_files

        candidate_files.sort(key=self._path_sort_key, reverse=True)
        selected_file = candidate_files[0]
        if len(candidate_files) > 1:
            print(f"Multiple Claude Code session logs found; using newest: {selected_file.name}")
        return selected_file.parent

    def _wrap_with_artifact_sync(self, base_command: str) -> str:
        sync_script = f"""
set -o pipefail

copy_tree() {{
    SRC="$1"
    REL="$2"
    if [ -d "$SRC" ]; then
        rm -rf "$DEST/$REL" 2>/dev/null || true
        mkdir -p "$(dirname "$DEST/$REL")" 2>/dev/null || true
        cp -r "$SRC" "$DEST/$REL" 2>/dev/null || true
    fi
}}

copy_file() {{
    SRC="$1"
    TARGET_NAME="$2"
    if [ -f "$SRC" ]; then
        mkdir -p "$(dirname "$DEST/$TARGET_NAME")" 2>/dev/null || true
        cp "$SRC" "$DEST/$TARGET_NAME" 2>/dev/null || true
    fi
}}

sync_artifacts() {{
    SESSIONS_DIR="${{CLAUDE_CONFIG_DIR:-/logs/agent/sessions}}"
    chmod -R a+rX "$SESSIONS_DIR" 2>/dev/null || true
    for DEST in /logs/agent/artifacts /logs/verifier/artifacts; do
        mkdir -p "$DEST" 2>/dev/null || true
        copy_tree "/app/experiment_codebase" "experiment_codebase"
        copy_tree "/app/figures" "figures"
        copy_tree "/app/literature" "literature"
        copy_file "/app/latex/template.pdf" "paper.pdf"
        copy_file "/app/latex/template.tex" "paper.tex"
        copy_file "/app/latex/references.bib" "references.bib"
        copy_file "/app/review.json" "review.json"
        copy_tree "/app/submissions" "submissions"
        copy_file "/app/requirements.txt" "requirements.txt"
        copy_tree "$SESSIONS_DIR/projects" "claude_sessions/projects"
        copy_tree "$SESSIONS_DIR/todos" "claude_sessions/todos"
        copy_tree "$SESSIONS_DIR/debug" "claude_sessions/debug"
        copy_file "$SESSIONS_DIR/.claude.json" "claude_sessions/.claude.json"
    done
}}

trap 'sync_artifacts' EXIT TERM INT

(
    while true; do
        sleep {self._artifact_sync_interval_sec}
        sync_artifacts
    done
) &
SYNC_PID=$!

{base_command}
AGENT_EXIT=$?

# Fix permissions on session files so the host process can read them for
# trajectory conversion.  Claude Code runs as root inside the container and
# creates files with 0600 — the host user needs at least read access.
SESSIONS_DIR="${{CLAUDE_CONFIG_DIR:-/logs/agent/sessions}}"
chmod -R a+rX "$SESSIONS_DIR" 2>/dev/null || true

kill "$SYNC_PID" 2>/dev/null || true
wait "$SYNC_PID" 2>/dev/null || true

sync_artifacts
exit "$AGENT_EXIT"
"""
        return f"bash -c {shlex.quote(sync_script)}"

    def create_run_agent_commands(self, instruction: str) -> list[ExecInput]:
        commands = super().create_run_agent_commands(instruction)
        if len(commands) < 2:
            return commands

        # Wrap the last command (the actual agent run) with artifact sync.
        # commands[0] is setup; commands[-1] is the agent invocation.
        idx = len(commands) - 1
        run_command = commands[idx]
        commands[idx] = ExecInput(
            command=self._wrap_with_artifact_sync(run_command.command),
            cwd=run_command.cwd,
            env=run_command.env,
            timeout_sec=run_command.timeout_sec,
        )
        return commands
