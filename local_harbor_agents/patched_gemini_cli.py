import shlex

from harbor.agents.installed.base import ExecInput
from harbor.agents.installed.gemini_cli import GeminiCli


class PatchedGeminiCli(GeminiCli):
    """Drop-in GeminiCli replacement with artifact syncing during execution.

    Upstream GeminiCli handles ATIF trajectory conversion and content-format
    fixing natively (since harbor commit 5a3a6db).  This subclass only adds
    periodic artifact syncing so partial work is preserved if the run times out.
    """

    def __init__(self, artifact_sync_interval_sec: int = 180, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            interval = int(artifact_sync_interval_sec)
        except (TypeError, ValueError):
            interval = 180
        self._artifact_sync_interval_sec = max(interval, 30)

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
    GEMINI_TMP_DIR="${{HOME:-/root}}/.gemini/tmp"
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
        copy_tree "$GEMINI_TMP_DIR" "gemini_sessions"
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

kill "$SYNC_PID" 2>/dev/null || true
wait "$SYNC_PID" 2>/dev/null || true

sync_artifacts
exit "$AGENT_EXIT"
"""
        return f"bash -c {shlex.quote(sync_script)}"

    def create_run_agent_commands(self, instruction: str) -> list[ExecInput]:
        commands = super().create_run_agent_commands(instruction)
        if not commands:
            return commands

        # Wrap the last command (the actual agent run) with artifact sync.
        # Upstream may prepend optional setup commands (e.g. MCP registration).
        idx = len(commands) - 1
        run_command = commands[idx]
        commands[idx] = ExecInput(
            command=self._wrap_with_artifact_sync(run_command.command),
            cwd=run_command.cwd,
            env=run_command.env,
            timeout_sec=run_command.timeout_sec,
        )
        return commands
