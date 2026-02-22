#!/bin/bash
# Run an AI Scientist experiment in Harbor
#
# Usage: ./run.sh <idea.json> [OPTIONS]
#
# Examples:
#   ./run.sh idea.json                                                # Local Docker, CPU
#   ./run.sh idea.json --gpus 1                                       # Local Docker, GPU
#   ./run.sh idea.json --model anthropic/claude-sonnet-4-5-20250929   # Use Sonnet
#   ./run.sh idea.json --env modal                                    # Modal cloud, CPU
#   ./run.sh idea.json --env modal --gpus 1                           # Modal cloud, GPU
#   ./run.sh idea.json --env modal --gpus 1 --timeout 7200            # Modal, GPU, 2hr
#   ./run.sh idea.json --resume-from jobs/2026-02-14__12-10-51/       # Resume previous
#   ./run.sh idea.json --agent gemini-cli                             # Gemini CLI agent
#   ./run.sh idea.json --agent gemini-cli --model google/gemini-3.1-pro-preview  # Gemini + custom model

set -euo pipefail

IDEA_JSON=""
MODEL=""           # empty = auto-select based on agent type
TIMEOUT="7200"
RESUME_FROM=""
ENV_TYPE=""        # empty = docker (default)
GPUS="0"
MODAL_SECRET="harbor-env"
USE_UPSTREAM_AGENT="0"
ARTIFACT_SYNC_INTERVAL="180"
AGENT_TYPE="claude-code"
PATCHED_AGENT_IMPORT_PATH=""  # set after arg parsing based on AGENT_TYPE
FEEDBACK=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --model)
            MODEL="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --resume-from)
            RESUME_FROM="$2"
            shift 2
            ;;
        --env)
            ENV_TYPE="$2"
            shift 2
            ;;
        --gpus)
            GPUS="$2"
            shift 2
            ;;
        --modal-secret)
            MODAL_SECRET="$2"
            shift 2
            ;;
        --use-upstream-agent)
            USE_UPSTREAM_AGENT="1"
            shift
            ;;
        --artifact-sync-interval)
            ARTIFACT_SYNC_INTERVAL="$2"
            shift 2
            ;;
        --agent)
            AGENT_TYPE="$2"
            shift 2
            ;;
        --feedback)
            FEEDBACK="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: ./run.sh <idea.json> [OPTIONS]"
            echo ""
            echo "Arguments:"
            echo "  idea.json                  Path to research idea JSON file"
            echo ""
            echo "Options:"
            echo "  --agent TYPE               Agent: claude-code (default) or gemini-cli"
            echo "  --model MODEL              LLM model (auto-selected per agent if omitted)"
            echo "  --timeout SECS             Agent timeout in seconds (default: 7200)"
            echo "  --resume-from JOB_PATH     Resume from a previous run's artifacts"
            echo "  --env ENV                  Environment: docker (default) or modal"
            echo "  --gpus N                   Number of GPUs (default: 0, works with local Docker and Modal)"
            echo "  --modal-secret NAME        Modal secret name (default: harbor-env)"
            echo "  --use-upstream-agent       Use Harbor's built-in agent (no artifact sync)"
            echo "  --artifact-sync-interval S Artifact sync interval in seconds (default: 180)"
            echo "  --feedback TEXT            Feedback/notes to include in the instruction"
            exit 0
            ;;
        *)
            if [[ -z "$IDEA_JSON" ]]; then
                IDEA_JSON="$1"
            else
                echo "Error: unexpected argument '$1'" >&2
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$IDEA_JSON" ]]; then
    echo "Error: idea.json path required" >&2
    echo "Usage: ./run.sh <idea.json> [OPTIONS]" >&2
    exit 1
fi

if [[ ! -f "$IDEA_JSON" ]]; then
    echo "Error: $IDEA_JSON not found" >&2
    exit 1
fi

# --- Resolve agent type defaults ---
case "$AGENT_TYPE" in
    claude-code)
        [[ -z "$MODEL" ]] && MODEL="anthropic/claude-opus-4-6"
        PATCHED_AGENT_IMPORT_PATH="local_harbor_agents.patched_claude_code:PatchedClaudeCode"
        UPSTREAM_AGENT_FLAG="claude-code"
        ;;
    gemini-cli)
        [[ -z "$MODEL" ]] && MODEL="google/gemini-3.1-pro-preview"
        PATCHED_AGENT_IMPORT_PATH="local_harbor_agents.patched_gemini_cli:PatchedGeminiCli"
        UPSTREAM_AGENT_FLAG="gemini-cli"
        ;;
    *)
        echo "Error: unknown agent type '$AGENT_TYPE' (use claude-code or gemini-cli)" >&2
        exit 1
        ;;
esac

# Validate and setup local GPU support
if [[ "$GPUS" != "0" && "$ENV_TYPE" != "modal" ]]; then
    # Check if nvidia runtime is available for local Docker
    if ! docker info 2>/dev/null | grep -q "nvidia"; then
        echo "Error: --gpus requires NVIDIA Container Toolkit (nvidia-docker)" >&2
        echo "Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html" >&2
        exit 1
    fi
    # Patch Harbor for local GPU support (idempotent)
    python3 -c "from local_harbor_agents import ensure_gpu_support; ensure_gpu_support(quiet=True)" 2>/dev/null || \
        PYTHONPATH="$SCRIPT_DIR" python3 -c "from local_harbor_agents import ensure_gpu_support; ensure_gpu_support(quiet=True)"
fi

if ! [[ "$ARTIFACT_SYNC_INTERVAL" =~ ^[0-9]+$ ]] || [[ "$ARTIFACT_SYNC_INTERVAL" -lt 30 ]]; then
    echo "Error: --artifact-sync-interval must be an integer >= 30" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Load .env into the current shell so harbor/agent can read them (optional) ---
for env_file in "$SCRIPT_DIR/.env" "$SCRIPT_DIR/../.env"; do
    if [[ -f "$env_file" ]]; then
        # Only source if file has valid bash syntax (VAR=value, no spaces around =)
        if bash -n "$env_file" 2>/dev/null; then
            echo "Loading env from $env_file"
            set -a
            source "$env_file"
            set +a
            break
        fi
    fi
done

# Persistent data directory (datasets, models, etc.) — mounted into container at /data
# Must come AFTER .env sourcing so DATA_DIR from .env takes priority
DATA_DIR="${DATA_DIR:-$SCRIPT_DIR/data}"
export DATA_DIR
mkdir -p "$DATA_DIR"

# Create per-job temp copy of harbor-task so concurrent jobs don't share staging dirs
TASK_DIR_TEMPLATE="$SCRIPT_DIR/harbor-task"
# mktemp generates mixed-case suffixes but Docker requires lowercase image names,
# and Harbor derives image names from the task directory name.
TASK_DIR=$(mktemp -d "/tmp/harbor-task-XXXXXX")
TASK_DIR_LC=$(echo "$TASK_DIR" | tr '[:upper:]' '[:lower:]')
[ "$TASK_DIR" != "$TASK_DIR_LC" ] && mv "$TASK_DIR" "$TASK_DIR_LC"
TASK_DIR="$TASK_DIR_LC"
cp -r "$TASK_DIR_TEMPLATE"/* "$TASK_DIR/"

ENV_DIR="$TASK_DIR/environment"
INSTRUCTION_TEMPLATE="$TASK_DIR/instruction.md.template"
INSTRUCTION_OUT="$TASK_DIR/instruction.md"

# --- Resolve previous artifacts if resuming ---
PREV_ARTIFACTS=""
if [[ -n "$RESUME_FROM" ]]; then
    # Find the artifacts directory (support both job dir and trial dir)
    # Check all possible artifact locations (agent/, verifier/ are Harbor-mounted paths)
    for artifacts_subdir in "agent/artifacts" "verifier/artifacts" "artifacts"; do
        if [[ -d "$RESUME_FROM/$artifacts_subdir" ]]; then
            PREV_ARTIFACTS="$RESUME_FROM/$artifacts_subdir"
            break
        fi
    done

    # If not found directly, look inside trial subdirectory (job dir case)
    if [[ -z "$PREV_ARTIFACTS" ]]; then
        TRIAL_DIR=$(find "$RESUME_FROM" -maxdepth 1 -type d -name "harbor-task__*" | head -1)
        if [[ -n "$TRIAL_DIR" ]]; then
            for artifacts_subdir in "agent/artifacts" "verifier/artifacts" "artifacts"; do
                if [[ -d "$TRIAL_DIR/$artifacts_subdir" ]]; then
                    PREV_ARTIFACTS="$TRIAL_DIR/$artifacts_subdir"
                    break
                fi
            done
        fi
    fi

    if [[ -z "$PREV_ARTIFACTS" || ! -d "$PREV_ARTIFACTS" ]]; then
        echo "Error: no artifacts found in $RESUME_FROM" >&2
        echo "Expected artifacts/ directory with previous run outputs" >&2
        exit 1
    fi

    echo "Resuming from: $PREV_ARTIFACTS"
    ls "$PREV_ARTIFACTS/" 2>/dev/null | sed 's/^/  /'
    echo ""
fi

# --- Copy .env into the build context so docker-compose env_file picks it up ---
# Uses same order as shell sourcing: project dir first, then parent dir
# For Modal: env vars come from Modal secrets, not .env file
for env_file in "$SCRIPT_DIR/.env" "$SCRIPT_DIR/../.env"; do
    if [[ -f "$env_file" ]]; then
        cp "$env_file" "$ENV_DIR/.env"
        break
    fi
done

# --- Stage repo files into the Docker build context ---
echo "Staging build context..."
cp -rL "$SCRIPT_DIR/blank_icbinb_latex" "$ENV_DIR/blank_icbinb_latex"
cp -rL "$SCRIPT_DIR/scripts"            "$ENV_DIR/scripts"
cp -rL "$SCRIPT_DIR/.claude"            "$ENV_DIR/.claude"

# Always create a fresh prev_artifacts dir with a placeholder file.
# Modal's builder omits empty directories from the build context, which causes
# COPY prev_artifacts/ to fail. The placeholder ensures the dir is non-empty.
mkdir -p "$ENV_DIR/prev_artifacts"
touch "$ENV_DIR/prev_artifacts/.keep"
if [[ -n "$PREV_ARTIFACTS" ]]; then
    cp -r "$PREV_ARTIFACTS"/* "$ENV_DIR/prev_artifacts/" 2>/dev/null || true
fi

# --- Generate Dockerfile from CPU or GPU source ---
if [[ "$GPUS" != "0" ]]; then
    echo "Using GPU image (pytorch + CUDA)"
    cp "$ENV_DIR/Dockerfile.gpu" "$ENV_DIR/Dockerfile"
else
    cp "$ENV_DIR/Dockerfile.cpu" "$ENV_DIR/Dockerfile"
fi

cleanup() {
    rm -rf "$TASK_DIR"
}
trap cleanup EXIT

# --- Generate instruction.md from template ---
RESUME_NOTE=""
if [[ -n "$PREV_ARTIFACTS" ]]; then
    # Build a summary of what already exists
    EXISTING=""
    [[ -d "$PREV_ARTIFACTS/experiment_codebase" ]] && \
        EXISTING="$EXISTING\n- experiment_codebase/ ($(ls "$PREV_ARTIFACTS/experiment_codebase/" 2>/dev/null | wc -l | tr -d ' ') files)"
    [[ -d "$PREV_ARTIFACTS/figures" ]] && \
        EXISTING="$EXISTING\n- figures/ ($(ls "$PREV_ARTIFACTS/figures/" 2>/dev/null | wc -l | tr -d ' ') files)"
    [[ -d "$PREV_ARTIFACTS/literature" ]] && \
        EXISTING="$EXISTING\n- literature/ ($(ls "$PREV_ARTIFACTS/literature/" 2>/dev/null | wc -l | tr -d ' ') files)"
    [[ -f "$PREV_ARTIFACTS/paper.pdf" ]] && EXISTING="$EXISTING\n- paper.pdf"
    [[ -f "$PREV_ARTIFACTS/paper.tex" ]] && EXISTING="$EXISTING\n- paper.tex"
    [[ -f "$PREV_ARTIFACTS/review.json" ]] && EXISTING="$EXISTING\n- review.json"
    [[ -d "$PREV_ARTIFACTS/submissions" ]] && \
        EXISTING="$EXISTING\n- submissions/ ($(ls "$PREV_ARTIFACTS/submissions/" 2>/dev/null | grep -c '^v') versions)"

    RESUME_NOTE="
## Resumed Session

This run continues from a previous session that timed out. Previous artifacts
have been pre-loaded into your workspace:
$(echo -e "$EXISTING")

Review what's already done before continuing. Focus on completing the missing
pieces rather than redoing work. Check the quality of existing artifacts and
improve them if needed.
"
fi

if [[ -n "$FEEDBACK" ]]; then
    RESUME_NOTE="$RESUME_NOTE
## Feedback from Previous Run

$FEEDBACK
"
fi

python3 -c "
import sys
template = open(sys.argv[1]).read()
idea = open(sys.argv[2]).read()
resume = sys.argv[3] if len(sys.argv) > 3 else ''
result = template.replace('{{IDEA_CONTENT}}', idea).replace('{{RESUME_CONTEXT}}', resume)
open(sys.argv[4], 'w').write(result)
" "$INSTRUCTION_TEMPLATE" "$IDEA_JSON" "$RESUME_NOTE" "$INSTRUCTION_OUT"

# --- Build harbor run command ---
# Harbor enforces timeout from task.toml [agent] timeout_sec * --timeout-multiplier.
# Compute multiplier so the user's --timeout value is actually enforced.
TASK_TOML_TIMEOUT=7200  # must match harbor-task/task.toml [agent] timeout_sec
TIMEOUT_MULTIPLIER=$(python3 -c "print($TIMEOUT / $TASK_TOML_TIMEOUT)")

HARBOR_ARGS=(
    harbor run
    -p "$TASK_DIR/"
    -m "$MODEL"
    --timeout-multiplier "$TIMEOUT_MULTIPLIER"
    --ak "timeout_sec=$TIMEOUT"
    -n 1
)

if [[ "$USE_UPSTREAM_AGENT" == "1" ]]; then
    HARBOR_ARGS+=(-a "$UPSTREAM_AGENT_FLAG")
else
    HARBOR_ARGS+=(--agent-import-path "$PATCHED_AGENT_IMPORT_PATH")
    HARBOR_ARGS+=(--ak "artifact_sync_interval_sec=$ARTIFACT_SYNC_INTERVAL")
fi

# Environment type
if [[ -n "$ENV_TYPE" ]]; then
    HARBOR_ARGS+=(--env "$ENV_TYPE")
fi

# Modal-specific options
if [[ "$ENV_TYPE" == "modal" ]]; then
    HARBOR_ARGS+=(--ek "secrets=[\"$MODAL_SECRET\"]")
fi

# GPU support (works for both local Docker and Modal)
if [[ "$GPUS" != "0" ]]; then
    HARBOR_ARGS+=(--override-gpus "$GPUS")
fi

echo "Starting Harbor run..."
echo "  Idea:    $IDEA_JSON"
echo "  Model:   $MODEL"
echo "  Timeout: ${TIMEOUT}s"
echo "  Env:     ${ENV_TYPE:-docker}"
if [[ "$USE_UPSTREAM_AGENT" == "1" ]]; then
    echo "  Agent:   $AGENT_TYPE (upstream)"
else
    echo "  Agent:   $AGENT_TYPE (patched, local import)"
    echo "  Sync:    ${ARTIFACT_SYNC_INTERVAL}s"
fi
if [[ "$GPUS" != "0" ]]; then
    echo "  GPUs:    $GPUS"
fi
if [[ -n "$PREV_ARTIFACTS" ]]; then
    echo "  Resume:  $PREV_ARTIFACTS"
fi
if [[ -n "$FEEDBACK" ]]; then
    echo "  Feedback: (included)"
fi
echo ""

PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}" "${HARBOR_ARGS[@]}"