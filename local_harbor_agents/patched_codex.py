import os
import shlex
from pathlib import Path

from harbor.agents.installed.base import ExecInput
from harbor.agents.installed.codex import Codex
from harbor.models.trial.paths import EnvironmentPaths


class PatchedCodex(Codex):
    """Drop-in Codex replacement with OAuth auth.json injection and artifact syncing.

    The upstream Codex agent creates auth.json from OPENAI_API_KEY, which doesn't
    work for ChatGPT subscription users who authenticate via OAuth tokens.  This
    subclass copies a pre-staged auth.json (placed in /app/.codex_auth/ by the
    Dockerfile) into $CODEX_HOME so the CLI picks up the OAuth tokens.

    It also wraps the main command with the same artifact-sync loop used by
    PatchedClaudeCode/PatchedGeminiCli so partial work survives timeouts.
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
    CODEX_SESSIONS_DIR="${{CODEX_HOME:-$HOME/.codex}}/sessions"
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
        copy_tree "$CODEX_SESSIONS_DIR" "codex_sessions"
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

# --- Git remote + branch setup ---
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
        escaped_instruction = shlex.quote(instruction)

        if not self.model_name:
            raise ValueError("Model name is required")

        model = self.model_name.split("/")[-1]

        codex_home = EnvironmentPaths.agent_dir.as_posix()

        env = {
            "CODEX_HOME": codex_home,
        }

        # Pass through API key if available (for non-OAuth setups)
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            env["OPENAI_API_KEY"] = api_key

        if openai_base_url := os.environ.get("OPENAI_BASE_URL"):
            env["OPENAI_BASE_URL"] = openai_base_url

        # Setup: inject auth.json from pre-staged location (OAuth tokens)
        # or fall back to generating from OPENAI_API_KEY (standard flow).
        setup_command = f"""
mkdir -p "{codex_home}"

# Prefer pre-staged OAuth auth.json (copied from host by Dockerfile)
if [ -f /app/.codex_auth/auth.json ]; then
    cp /app/.codex_auth/auth.json "{codex_home}/auth.json"
    echo "Codex auth: using pre-staged OAuth auth.json"
elif [ -n "${{OPENAI_API_KEY:-}}" ]; then
    cat >"{codex_home}/auth.json" <<AUTHEOF
{{
  "OPENAI_API_KEY": "${{OPENAI_API_KEY}}"
}}
AUTHEOF
    echo "Codex auth: using OPENAI_API_KEY"
else
    echo "WARNING: No Codex auth available (no auth.json and no OPENAI_API_KEY)"
fi

# Copy config.toml if pre-staged
if [ -f /app/.codex_auth/config.toml ]; then
    cp /app/.codex_auth/config.toml "{codex_home}/config.toml"
    echo "Codex config: using pre-staged config.toml"
fi
"""

        # Register skills if available (method may not exist in older Harbor versions)
        if hasattr(self, '_build_register_skills_command'):
            skills_command = self._build_register_skills_command()
            if skills_command:
                setup_command += f"\n{skills_command}"

        # Register MCP servers if configured
        if hasattr(self, '_build_register_mcp_servers_command'):
            mcp_command = self._build_register_mcp_servers_command()
            if mcp_command:
                setup_command += f"\n{mcp_command}"

        # Build reasoning effort flag
        reasoning_effort = getattr(self, '_reasoning_effort', None)
        reasoning_flag = (
            f"-c model_reasoning_effort={reasoning_effort} " if reasoning_effort else ""
        )

        # Main codex exec command
        run_command = (
            "trap 'rm -f \"$CODEX_HOME/auth.json\"' EXIT TERM INT; "
            ". ~/.nvm/nvm.sh; "
            "codex exec "
            "--dangerously-bypass-approvals-and-sandbox "
            "--skip-git-repo-check "
            f"--model {model} "
            "--json "
            f"{reasoning_flag}"
            "-- "
            f"{escaped_instruction} "
            f"2>&1 </dev/null | stdbuf -oL tee {EnvironmentPaths.agent_dir / Codex._OUTPUT_FILENAME}"
        )

        return [
            ExecInput(
                command=setup_command,
                env=env,
            ),
            ExecInput(
                command=self._wrap_with_artifact_sync(run_command),
                cwd="/app",
                env=env,
            ),
        ]
