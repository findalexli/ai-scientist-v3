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

git_push() {{
    cd /app
    if git remote get-url origin &>/dev/null; then
        git add -A 2>/dev/null
        git commit -m "Auto-sync $(date -u +%H:%M)" --allow-empty-message 2>/dev/null || true
        git push origin "$(git branch --show-current)" 2>/dev/null || true
    fi
}}

trap 'sync_artifacts; git_push' EXIT TERM INT

# --- Git remote + branch setup (if GITLAB_REPO_URL is set) ---
if [ -z "${{GITLAB_REPO_URL:-}}" ] && [ -f /app/scripts/.gitlab_env ]; then
    set -a; source /app/scripts/.gitlab_env; set +a
fi
if [ -n "${{GITLAB_REPO_URL:-}}" ]; then
    cd /app
    git remote add origin "$GITLAB_REPO_URL" 2>/dev/null || git remote set-url origin "$GITLAB_REPO_URL"
    git fetch origin --no-tags 2>/dev/null || true

    if [ -n "${{GITLAB_RESUME_BRANCH:-}}" ] && git rev-parse "origin/${{GITLAB_RESUME_BRANCH}}" &>/dev/null; then
        # Resume: branch off the previous run's branch
        git checkout -b "${{GITLAB_BRANCH:-main}}" "origin/${{GITLAB_RESUME_BRANCH}}"
        # Install any previously-saved pip deps
        if [ -f /app/requirements.txt ]; then
            uv pip install --system --no-cache -r /app/requirements.txt 2>/dev/null || true
        fi
        echo "GitLab: branched ${{GITLAB_BRANCH}} off ${{GITLAB_RESUME_BRANCH}}"
    else
        # Fresh run (or fallback): commit current workspace as-is
        git add -A && git commit -m "Initial workspace" --allow-empty 2>/dev/null || true
        git checkout -b "${{GITLAB_BRANCH:-main}}" 2>/dev/null || true
        echo "GitLab: created fresh branch ${{GITLAB_BRANCH:-main}}"
    fi

    git push -u origin "${{GITLAB_BRANCH:-main}}" 2>/dev/null || true
fi

SYNC_CYCLE=0
(
    while true; do
        sleep {self._artifact_sync_interval_sec}
        sync_artifacts
        SYNC_CYCLE=$((SYNC_CYCLE + 1))
        if [ $((SYNC_CYCLE % 5)) -eq 0 ]; then
            git_push
        fi
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
