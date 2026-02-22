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

set -euo pipefail

IDEA_JSON=""
MODEL="anthropic/claude-opus-4-6"
TIMEOUT="7200"
RESUME_FROM=""
ENV_TYPE=""        # empty = docker (default)
GPUS="0"
MODAL_SECRET="harbor-env"
USE_UPSTREAM_AGENT="0"
ARTIFACT_SYNC_INTERVAL="180"
PATCHED_AGENT_IMPORT_PATH="local_harbor_agents.patched_claude_code:PatchedClaudeCode"

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
        -h|--help)
            echo "Usage: ./run.sh <idea.json> [OPTIONS]"
            echo ""
            echo "Arguments:"
            echo "  idea.json                  Path to research idea JSON file"
            echo ""
            echo "Options:"
            echo "  --model MODEL              LLM model (default: anthropic/claude-opus-4-6)"
            echo "  --timeout SECS             Agent timeout in seconds (default: 7200)"
            echo "  --resume-from JOB_PATH     Resume from a previous run's artifacts"
            echo "  --env ENV                  Environment: docker (default) or modal"
            echo "  --gpus N                   Number of GPUs (default: 0, works with local Docker and Modal)"
            echo "  --modal-secret NAME        Modal secret name (default: harbor-env)"
            echo "  --use-upstream-agent       Use Harbor's built-in claude-code agent"
            echo "  --artifact-sync-interval S Artifact sync interval in seconds (default: 180)"
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
ENV_DIR="$SCRIPT_DIR/harbor-task/environment"
INSTRUCTION_TEMPLATE="$SCRIPT_DIR/harbor-task/instruction.md.template"
INSTRUCTION_OUT="$SCRIPT_DIR/harbor-task/instruction.md"

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
cp -rL "$SCRIPT_DIR/fewshot_examples"   "$ENV_DIR/fewshot_examples"
cp -rL "$SCRIPT_DIR/scripts"            "$ENV_DIR/scripts"
cp -rL "$SCRIPT_DIR/.claude"            "$ENV_DIR/.claude"

# Always create prev_artifacts dir with a placeholder file.
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
    rm -rf "$ENV_DIR/blank_icbinb_latex" "$ENV_DIR/fewshot_examples" \
           "$ENV_DIR/scripts" "$ENV_DIR/.claude" "$ENV_DIR/.env" \
           "$ENV_DIR/prev_artifacts"
    # Remove generated files (sources are never modified)
    rm -f "$ENV_DIR/Dockerfile"
    rm -f "$INSTRUCTION_OUT"
}
trap cleanup EXIT

# --- Generate instruction.md from template ---
RESUME_NOTE=""
if [[ -n "$PREV_ARTIFACTS" ]]; then
    # Build a summary of what already exists
    EXISTING=""
    [[ -d "$PREV_ARTIFACTS/experiment_results" ]] && \
        EXISTING="$EXISTING\n- experiment_results/ ($(ls "$PREV_ARTIFACTS/experiment_results/" 2>/dev/null | wc -l | tr -d ' ') files)"
    [[ -d "$PREV_ARTIFACTS/figures" ]] && \
        EXISTING="$EXISTING\n- figures/ ($(ls "$PREV_ARTIFACTS/figures/" 2>/dev/null | wc -l | tr -d ' ') files)"
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
    -p "$SCRIPT_DIR/harbor-task/"
    -m "$MODEL"
    --timeout-multiplier "$TIMEOUT_MULTIPLIER"
    --ak "timeout_sec=$TIMEOUT"
    -n 1
)

if [[ "$USE_UPSTREAM_AGENT" == "1" ]]; then
    HARBOR_ARGS+=(-a claude-code)
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
    echo "  Agent:   claude-code (upstream)"
else
    echo "  Agent:   PatchedClaudeCode (local import)"
    echo "  Sync:    ${ARTIFACT_SYNC_INTERVAL}s"
fi
if [[ "$GPUS" != "0" ]]; then
    echo "  GPUs:    $GPUS"
fi
if [[ -n "$PREV_ARTIFACTS" ]]; then
    echo "  Resume:  $PREV_ARTIFACTS"
fi
echo ""

PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}" "${HARBOR_ARGS[@]}"