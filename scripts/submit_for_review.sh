#!/bin/bash
# Submit a paper for external review and create a versioned snapshot.
#
# Usage: bash scripts/submit_for_review.sh <tex_path> [base_dir]
#   tex_path:  Path to the .tex file to submit
#   base_dir:  Workspace root (default: /app, or parent of scripts/ if not in container)
#
# What this does:
#   1. Generates a review (via external API, Claude Code subagent, or ensemble of 3 reviewers)
#   2. Creates a versioned snapshot in submissions/v{N}_{timestamp}/ containing:
#      - paper.tex, paper.pdf
#      - experiment_codebase/
#      - figures/
#      - reviewer_communications/response.md
#   3. Updates submissions/version_log.json
#
# Environment variables:
#   REVIEWER_MODE  — "subagent" (default) uses a single reviewer subagent
#                    "ensemble" runs 3 diversified reviewers in parallel:
#                      - Comprehensive reviewer (reviewer.md)
#                      - Idea/literature reviewer (idea-reviewer.md)
#                      - Code quality reviewer (code-reviewer.md)
#                    Each reviewer can run on a different CLI backend (claude, codex, gemini).
#                    "api" uses external reviewer API (works with any runtime)
#   AGENT_TYPE     — "claude-code" or "gemini-cli" (optional, for subagent CLI selection)
#   CODEX_MODEL    — Model for Codex CLI (default: gpt-5.2-codex)
#   GEMINI_MODEL   — Model for Gemini CLI (default: auto)
#
# One call = one version. Deterministic, atomic, no LLM in the loop.

set -euo pipefail

TEX_PATH="$1"

if [ -z "$TEX_PATH" ] || [ ! -f "$TEX_PATH" ]; then
    echo "Error: File not found: $TEX_PATH" >&2
    echo "Usage: bash scripts/submit_for_review.sh <tex_path> [base_dir]" >&2
    exit 1
fi

# Determine base directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${2:-}" ]; then
    BASE_DIR="$2"
elif [ -d "/app/latex" ]; then
    BASE_DIR="/app"
else
    BASE_DIR="$(dirname "$SCRIPT_DIR")"
fi

SUBMISSIONS_DIR="$BASE_DIR/submissions"
VERSION_LOG="$SUBMISSIONS_DIR/version_log.json"
EXTRACT_SCRIPT="$BASE_DIR/.claude/skills/review-paper/scripts/extract_and_generate_questions.sh"

mkdir -p "$SUBMISSIONS_DIR"

REVIEWER_MODE="${REVIEWER_MODE:-subagent}"

# =============================================================================
# Helper functions (used by both subagent and ensemble modes)
# =============================================================================

# Cross-platform timeout: use GNU timeout (gtimeout on macOS) or fall back
if command -v timeout &>/dev/null; then
    TIMEOUT_CMD="timeout"
elif command -v gtimeout &>/dev/null; then
    TIMEOUT_CMD="gtimeout"
else
    TIMEOUT_CMD=""
fi

run_with_timeout() {
    local secs="$1"; shift
    if [ -n "$TIMEOUT_CMD" ]; then
        "$TIMEOUT_CMD" "$secs" "$@"
    else
        "$@"
    fi
}

# Ensure PATH includes common CLI install locations
ensure_cli_path() {
    export PATH="$HOME/.local/bin:$PATH"
    # Source nvm if node-based CLIs aren't on PATH (Harbor installs via nvm)
    if ! command -v node &>/dev/null && [ -f "$HOME/.nvm/nvm.sh" ]; then
        . "$HOME/.nvm/nvm.sh"
    fi
}

# Strip YAML frontmatter from an agent .md file, returning only the body text.
strip_frontmatter() {
    local file="$1"
    local second_marker
    second_marker=$(grep -n "^---$" "$file" | sed -n '2p' | cut -d: -f1)
    if [ -n "$second_marker" ]; then
        tail -n +$((second_marker + 1)) "$file"
    else
        cat "$file"
    fi
}

# Detect available CLI backends. Prints space-separated list padded to 3 entries.
# Always includes "claude"; adds "codex" and "gemini" if their keys + binaries exist.
detect_available_clis() {
    local clis=("claude")

    if { [ -n "${CODEX_API_KEY:-}" ] || [ -n "${OPENAI_API_KEY:-}" ]; } && command -v codex &>/dev/null; then
        clis+=("codex")
    fi

    if { [ -n "${GEMINI_API_KEY:-}" ] || [ -n "${GOOGLE_API_KEY:-}" ]; } && command -v gemini &>/dev/null; then
        clis+=("gemini")
    fi

    # Pad to 3 with claude
    while [ ${#clis[@]} -lt 3 ]; do
        clis+=("claude")
    done

    echo "${clis[@]}"
}

# Shuffle an array using $RANDOM (portable, no dependency on shuf).
# Usage: SHUFFLED=($(shuffle_array "${ARRAY[@]}"))
shuffle_array() {
    local arr=("$@")
    local i n temp
    n=${#arr[@]}
    for (( i = n - 1; i > 0; i-- )); do
        local j=$(( RANDOM % (i + 1) ))
        temp="${arr[$i]}"
        arr[$i]="${arr[$j]}"
        arr[$j]="$temp"
    done
    echo "${arr[@]}"
}

# Run a single reviewer.
# Arguments: agent_name cli_type output_file stderr_file
# Agent names: "reviewer", "idea-reviewer", "code-reviewer"
run_single_reviewer() {
    local agent_name="$1"
    local cli_type="$2"
    local output_file="$3"
    local stderr_file="$4"

    local agent_prompt_file="$BASE_DIR/.claude/agents/${agent_name}.md"
    if [ ! -f "$agent_prompt_file" ]; then
        echo "Error: Agent prompt not found: $agent_prompt_file" >"$stderr_file"
        return 1
    fi

    local task_prompt="Review the research submission. The paper is at latex/template.tex (compiled PDF at latex/template.pdf). Inspect the full workspace: experiment_codebase/, figures/, literature/, and latex/. Follow your review procedure and produce your review."

    cd "$BASE_DIR"

    case "$cli_type" in
        claude)
            # CLAUDECODE="" clears nesting guard
            CLAUDECODE="" run_with_timeout 1200 claude -p \
                --agent "$agent_name" \
                --output-format text \
                "$task_prompt" \
                > "$output_file" 2>"$stderr_file" || true
            ;;
        codex)
            local prompt_file
            prompt_file=$(mktemp)
            strip_frontmatter "$agent_prompt_file" > "$prompt_file"
            printf '\n\n%s\n' "$task_prompt" >> "$prompt_file"

            # Codex CLI reads CODEX_API_KEY (not OPENAI_API_KEY); bridge if needed
            if [ -z "${CODEX_API_KEY:-}" ] && [ -n "${OPENAI_API_KEY:-}" ]; then
                export CODEX_API_KEY="$OPENAI_API_KEY"
            fi

            # Use --dangerously-bypass-approvals-and-sandbox inside containers/sandboxes
            # to avoid Landlock double-sandboxing (container already provides isolation).
            # Detects: Docker (/.dockerenv), LXC/containerd (cgroup), Modal (cgroup /ta-*).
            # Fall back to --full-auto on bare metal.
            local codex_sandbox_flag="--full-auto"
            if [ -f "/.dockerenv" ] || grep -qE 'docker|lxc|containerd|/ta-' /proc/1/cgroup 2>/dev/null; then
                codex_sandbox_flag="--dangerously-bypass-approvals-and-sandbox"
            fi

            if [ -n "${CODEX_MODEL:-}" ]; then
                run_with_timeout 1200 codex exec \
                    --model "$CODEX_MODEL" \
                    $codex_sandbox_flag \
                    --output-last-message "$output_file" \
                    - < "$prompt_file" 2>"$stderr_file" || true
            else
                run_with_timeout 1200 codex exec \
                    $codex_sandbox_flag \
                    --output-last-message "$output_file" \
                    - < "$prompt_file" 2>"$stderr_file" || true
            fi
            rm -f "$prompt_file"
            ;;
        gemini)
            local prompt_file raw_json
            prompt_file=$(mktemp)
            raw_json=$(mktemp)
            strip_frontmatter "$agent_prompt_file" > "$prompt_file"
            printf '\n\n%s\n' "$task_prompt" >> "$prompt_file"

            run_with_timeout 1200 gemini \
                --approval-mode=yolo \
                --output-format json \
                --model "${GEMINI_MODEL:-auto}" \
                < "$prompt_file" \
                > "$raw_json" 2>"$stderr_file" || true

            # Parse JSON response
            python3 -c "
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
    if data.get('error'):
        print(f'Gemini error: {data[\"error\"]}', file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[2], 'w') as f:
        f.write(data.get('response', ''))
except Exception as e:
    print(f'Warning: failed to parse Gemini JSON: {e}', file=sys.stderr)
    import shutil
    shutil.copy(sys.argv[1], sys.argv[2])
" "$raw_json" "$output_file" 2>>"$stderr_file" || true
            rm -f "$prompt_file" "$raw_json"
            ;;
        *)
            echo "Error: Unknown CLI type: $cli_type" >"$stderr_file"
            return 1
            ;;
    esac

    # Verify output was produced
    if [ ! -s "$output_file" ]; then
        echo "Error: Reviewer produced empty output" >>"$stderr_file"
        return 1
    fi
    return 0
}

# =============================================================================
# Step 1: Generate review(s)
# =============================================================================
echo "=== Submitting paper for review ==="
echo "Paper: $TEX_PATH"
echo "Reviewer mode: $REVIEWER_MODE"

RAW_RESPONSE="$BASE_DIR/reviewer_raw_response.json"
ENSEMBLE_ASSIGNMENT_JSON=""  # Set by ensemble mode for version log

ensure_cli_path

if [ "$REVIEWER_MODE" = "ensemble" ]; then
    # =========================================================================
    # ENSEMBLE MODE: Run 3 diversified reviewers in parallel
    # =========================================================================
    echo ""
    echo "--- Ensemble mode: launching 3 reviewers in parallel ---"

    # Agent names for the 3 reviewer roles
    AGENT_NAMES=("reviewer" "idea-reviewer" "code-reviewer")
    AGENT_LABELS=("Comprehensive Reviewer" "Idea & Literature Reviewer" "Code Quality Reviewer")

    # Detect and assign CLIs
    AVAILABLE_CLIS=($(detect_available_clis))
    CLIS=($(shuffle_array "${AVAILABLE_CLIS[@]}"))

    echo "Assignments:"
    for i in 0 1 2; do
        echo "  ${AGENT_LABELS[$i]} (${AGENT_NAMES[$i]}) → ${CLIS[$i]}"
    done

    # Save assignment JSON for version log
    ENSEMBLE_ASSIGNMENT_JSON=$(python3 -c "
import json
names = '${AGENT_NAMES[0]},${AGENT_NAMES[1]},${AGENT_NAMES[2]}'.split(',')
clis = '${CLIS[0]},${CLIS[1]},${CLIS[2]}'.split(',')
print(json.dumps(dict(zip(names, clis))))
")

    # Snapshot Claude session files (for trace capture)
    SESSIONS_PROJECT_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/-app"
    PRE_SESSIONS=""
    if [ -d "$SESSIONS_PROJECT_DIR" ]; then
        PRE_SESSIONS=$(find "$SESSIONS_PROJECT_DIR" -name "*.jsonl" 2>/dev/null | sort)
    fi

    # Launch all 3 reviewers in background
    PIDS=()
    REVIEW_FILES=()
    STDERR_FILES=()
    for i in 0 1 2; do
        review_file="$BASE_DIR/reviewer_response_$((i+1)).txt"
        stderr_file="$BASE_DIR/reviewer_stderr_$((i+1)).log"
        REVIEW_FILES+=("$review_file")
        STDERR_FILES+=("$stderr_file")

        echo "  Starting ${AGENT_LABELS[$i]} (${CLIS[$i]})..."
        run_single_reviewer "${AGENT_NAMES[$i]}" "${CLIS[$i]}" "$review_file" "$stderr_file" &
        PIDS+=($!)
    done

    echo ""
    echo "All 3 reviewers launched. Waiting for completion..."

    # Wait and track results (indexed array: RESULT_STATUS[0..2])
    RESULT_STATUS=()
    FAILURES=0
    for i in 0 1 2; do
        if wait "${PIDS[$i]}"; then
            RESULT_STATUS+=("success")
            echo "  ✓ ${AGENT_LABELS[$i]} (${CLIS[$i]}) completed successfully"
        else
            RESULT_STATUS+=("failed")
            FAILURES=$((FAILURES + 1))
            echo "  ✗ ${AGENT_LABELS[$i]} (${CLIS[$i]}) failed"
        fi
    done

    if [ $FAILURES -eq 3 ]; then
        echo "Error: All 3 reviewers failed." >&2
        for i in 0 1 2; do
            echo "--- stderr from ${AGENT_LABELS[$i]} ---" >&2
            cat "${STDERR_FILES[$i]}" 2>/dev/null >&2 || true
        done
        exit 1
    fi

    echo ""
    echo "Ensemble complete: $((3 - FAILURES))/3 reviewers succeeded."

    # Aggregate reviews into RAW_RESPONSE (used as response.md source)
    {
        for i in 0 1 2; do
            echo "## Review (${AGENT_LABELS[$i]} — ${CLIS[$i]})"
            echo ""
            if [ "${RESULT_STATUS[$i]}" = "success" ] && [ -s "${REVIEW_FILES[$i]}" ]; then
                cat "${REVIEW_FILES[$i]}"
            else
                echo "[Review not available — ${CLIS[$i]} reviewer failed]"
                if [ -f "${STDERR_FILES[$i]}" ]; then
                    echo ""
                    echo "Error log:"
                    echo '```'
                    tail -20 "${STDERR_FILES[$i]}" 2>/dev/null || true
                    echo '```'
                fi
            fi
            echo ""
            echo ""
        done
    } > "$RAW_RESPONSE"

    # Capture Claude session trace (if any Claude reviewers ran)
    if [ -d "$SESSIONS_PROJECT_DIR" ]; then
        POST_SESSIONS=$(find "$SESSIONS_PROJECT_DIR" -name "*.jsonl" 2>/dev/null | sort)
        NEW_SESSIONS=$(comm -13 <(echo "$PRE_SESSIONS") <(echo "$POST_SESSIONS"))
        if [ -n "$NEW_SESSIONS" ]; then
            REVIEWER_TRACE_DIR="$BASE_DIR/reviewer_trace"
            rm -rf "$REVIEWER_TRACE_DIR"
            mkdir -p "$REVIEWER_TRACE_DIR"
            echo "$NEW_SESSIONS" | while IFS= read -r f; do
                FLAT_NAME=$(echo "$f" | sed "s|$SESSIONS_PROJECT_DIR/||; s|/|__|g")
                cp "$f" "$REVIEWER_TRACE_DIR/$FLAT_NAME"
            done
            echo "Reviewer trace: $(echo "$NEW_SESSIONS" | wc -l | tr -d ' ') session file(s) saved to $REVIEWER_TRACE_DIR/"
        fi
    fi

    # Build ensemble results JSON for version log
    ENSEMBLE_RESULTS_JSON=$(python3 -c "
import json
names = '${AGENT_NAMES[0]},${AGENT_NAMES[1]},${AGENT_NAMES[2]}'.split(',')
results = '${RESULT_STATUS[0]},${RESULT_STATUS[1]},${RESULT_STATUS[2]}'.split(',')
print(json.dumps(dict(zip(names, results))))
")

    echo "Ensemble reviewers complete."

elif [ "$REVIEWER_MODE" = "subagent" ]; then
    # =========================================================================
    # SUBAGENT MODE: Single reviewer (existing behavior)
    # =========================================================================
    # Detect which CLI to use: AGENT_TYPE env var, or auto-detect from available commands
    SUBAGENT_CLI="${AGENT_TYPE:-auto}"
    if [ "$SUBAGENT_CLI" = "auto" ]; then
        # Check claude first (more common in this environment)
        if command -v claude &>/dev/null || [ -f "$HOME/.local/bin/claude" ]; then
            SUBAGENT_CLI="claude-code"
        elif command -v gemini &>/dev/null; then
            SUBAGENT_CLI="gemini-cli"
        else
            echo "Error: REVIEWER_MODE=subagent requires claude or gemini CLI." >&2
            exit 1
        fi
    fi

    echo "Invoking reviewer subagent via $SUBAGENT_CLI (this may take several minutes)..."

    if [ "$SUBAGENT_CLI" = "gemini-cli" ]; then
        # --- Gemini CLI reviewer ---
        # Read the reviewer prompt from the agent config file
        REVIEWER_PROMPT_FILE="$BASE_DIR/.claude/agents/reviewer.md"
        if [ ! -f "$REVIEWER_PROMPT_FILE" ]; then
            echo "Error: reviewer prompt not found at $REVIEWER_PROMPT_FILE" >&2
            exit 1
        fi
        # Strip the YAML frontmatter (skip everything up to and including the second ---)
        SECOND_MARKER=$(grep -n "^---$" "$REVIEWER_PROMPT_FILE" | sed -n '2p' | cut -d: -f1)
        REVIEWER_SYSTEM_PROMPT=$(tail -n +$((SECOND_MARKER + 1)) "$REVIEWER_PROMPT_FILE")

        # Write the full review prompt to a temp file (too large for shell argument)
        REVIEW_PROMPT_FILE=$(mktemp)
        cat > "$REVIEW_PROMPT_FILE" <<REVIEW_EOF
Review the research submission. The paper is at $TEX_PATH. Inspect the full workspace: experiment_codebase/, figures/, literature/, and latex/. Follow your review procedure and produce your review.

$REVIEWER_SYSTEM_PROMPT
REVIEW_EOF

        # Use --output-format json and extract .response to get clean output
        # without chain-of-thought / tool narration leaking into the review.
        GEMINI_RAW_JSON="$BASE_DIR/reviewer_gemini_raw.json"
        if ! run_with_timeout 1200 cat "$REVIEW_PROMPT_FILE" | gemini --yolo --output-format json \
            > "$GEMINI_RAW_JSON" 2>"$BASE_DIR/reviewer_subagent_stderr.log"; then
            echo "Warning: Gemini reviewer subagent returned non-zero exit code." >&2
        fi
        # Extract just the response field (final answer, no CoT)
        python3 -c "
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
    response = data.get('response', '')
    with open(sys.argv[2], 'w') as f:
        f.write(response)
except Exception as e:
    print(f'Warning: failed to parse Gemini JSON response: {e}', file=sys.stderr)
    # Fallback: copy raw JSON as-is
    import shutil
    shutil.copy(sys.argv[1], sys.argv[2])
" "$GEMINI_RAW_JSON" "$RAW_RESPONSE"
        rm -f "$REVIEW_PROMPT_FILE" "$GEMINI_RAW_JSON"

    else
        # --- Claude Code reviewer ---
        # Snapshot existing session files so we can identify the reviewer's trace afterward.
        SESSIONS_PROJECT_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/-app"
        PRE_SESSIONS=""
        if [ -d "$SESSIONS_PROJECT_DIR" ]; then
            PRE_SESSIONS=$(find "$SESSIONS_PROJECT_DIR" -name "*.jsonl" 2>/dev/null | sort)
        fi

        # CLAUDECODE="" clears the nesting guard so claude can launch from within a running session.
        cd "$BASE_DIR"
        if ! CLAUDECODE="" run_with_timeout 1200 claude -p \
            --agent reviewer \
            --output-format text \
            "Review the research submission. The paper is at latex/template.tex (compiled PDF at latex/template.pdf). Inspect the full workspace: experiment_codebase/, figures/, literature/, and latex/. Follow your review procedure and produce your review." \
            > "$RAW_RESPONSE" 2>"$BASE_DIR/reviewer_subagent_stderr.log"; then
            echo "Warning: Claude reviewer subagent returned non-zero exit code." >&2
        fi

        # Copy the reviewer's session trace (all JSONL files created during the review).
        if [ -d "$SESSIONS_PROJECT_DIR" ]; then
            POST_SESSIONS=$(find "$SESSIONS_PROJECT_DIR" -name "*.jsonl" 2>/dev/null | sort)
            NEW_SESSIONS=$(comm -13 <(echo "$PRE_SESSIONS") <(echo "$POST_SESSIONS"))
            if [ -n "$NEW_SESSIONS" ]; then
                REVIEWER_TRACE_DIR="$BASE_DIR/reviewer_trace"
                rm -rf "$REVIEWER_TRACE_DIR"
                mkdir -p "$REVIEWER_TRACE_DIR"
                echo "$NEW_SESSIONS" | while IFS= read -r f; do
                    FLAT_NAME=$(echo "$f" | sed "s|$SESSIONS_PROJECT_DIR/||; s|/|__|g")
                    cp "$f" "$REVIEWER_TRACE_DIR/$FLAT_NAME"
                done
                echo "Reviewer trace: $(echo "$NEW_SESSIONS" | wc -l) session file(s) saved to $REVIEWER_TRACE_DIR/"
            fi
        fi
    fi

    echo "Reviewer subagent complete."

else
    # =========================================================================
    # API MODE: External reviewer (original behavior)
    # =========================================================================
    if [ ! -f "$EXTRACT_SCRIPT" ]; then
        echo "Error: extract_and_generate_questions.sh not found at $EXTRACT_SCRIPT" >&2
        exit 1
    fi

    echo "Calling external reviewer model (this takes ~30 seconds)..."
    bash "$EXTRACT_SCRIPT" "$TEX_PATH" > "$RAW_RESPONSE"
    echo "External reviewer response received."
fi

# =============================================================================
# Step 2: Determine next version number
# =============================================================================
if [ -f "$VERSION_LOG" ]; then
    CURRENT_VERSION=$(python3 -c "
import json
with open('$VERSION_LOG') as f:
    data = json.load(f)
print(data.get('current_version', 0))
")
else
    CURRENT_VERSION=0
fi

NEXT_VERSION=$((CURRENT_VERSION + 1))
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
VERSION_DIR="$SUBMISSIONS_DIR/v${NEXT_VERSION}_${TIMESTAMP}"

echo ""
echo "=== Creating version snapshot: v${NEXT_VERSION} ==="

# =============================================================================
# Step 3: Create versioned snapshot
# =============================================================================
mkdir -p "$VERSION_DIR/reviewer_communications"

# Copy paper
cp "$TEX_PATH" "$VERSION_DIR/paper.tex" 2>/dev/null || true
# Try to find the PDF next to the tex file
TEX_DIR="$(dirname "$TEX_PATH")"
TEX_BASE="$(basename "$TEX_PATH" .tex)"
if [ -f "$TEX_DIR/$TEX_BASE.pdf" ]; then
    cp "$TEX_DIR/$TEX_BASE.pdf" "$VERSION_DIR/paper.pdf"
elif [ -f "$BASE_DIR/latex/template.pdf" ]; then
    cp "$BASE_DIR/latex/template.pdf" "$VERSION_DIR/paper.pdf"
fi

# Copy experiment results
if [ -d "$BASE_DIR/experiment_codebase" ]; then
    cp -r "$BASE_DIR/experiment_codebase" "$VERSION_DIR/experiment_codebase"
fi

# Copy figures
if [ -d "$BASE_DIR/figures" ]; then
    cp -r "$BASE_DIR/figures" "$VERSION_DIR/figures"
fi

# Save reviewer communications
RESPONSE_FILE="$VERSION_DIR/reviewer_communications/response.md"

if [ "$REVIEWER_MODE" = "ensemble" ]; then
    # Ensemble mode: RAW_RESPONSE is the aggregated markdown with all 3 reviews
    cp "$RAW_RESPONSE" "$RESPONSE_FILE"

    # Copy individual review files
    for i in 0 1 2; do
        local_review="$BASE_DIR/reviewer_response_$((i+1)).txt"
        if [ -f "$local_review" ]; then
            cp "$local_review" "$VERSION_DIR/reviewer_communications/"
        fi
    done
    # Copy stderr logs
    for i in 0 1 2; do
        local_stderr="$BASE_DIR/reviewer_stderr_$((i+1)).log"
        if [ -f "$local_stderr" ]; then
            cp "$local_stderr" "$VERSION_DIR/reviewer_communications/"
        fi
    done

    # Save ensemble assignment
    echo "$ENSEMBLE_ASSIGNMENT_JSON" > "$VERSION_DIR/reviewer_communications/ensemble_assignment.json"

    # Copy reviewer trace into the versioned snapshot
    if [ -d "$BASE_DIR/reviewer_trace" ]; then
        cp -r "$BASE_DIR/reviewer_trace" "$VERSION_DIR/reviewer_communications/trace"
    fi

elif [ "$REVIEWER_MODE" = "subagent" ]; then
    # Subagent mode: RAW_RESPONSE is plain text (the review)
    cp "$RAW_RESPONSE" "$VERSION_DIR/reviewer_communications/raw_response.txt"
    { echo "## Review"; echo ""; cat "$RAW_RESPONSE"; echo ""; } > "$RESPONSE_FILE"
    # Copy reviewer trace into the versioned snapshot
    if [ -d "$BASE_DIR/reviewer_trace" ]; then
        cp -r "$BASE_DIR/reviewer_trace" "$VERSION_DIR/reviewer_communications/trace"
    fi
else
    # API mode: RAW_RESPONSE is JSON, extract the question
    cp "$RAW_RESPONSE" "$VERSION_DIR/reviewer_communications/raw_response.json"
    python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
with open(sys.argv[2], 'w') as f:
    f.write('## Review\n\n')
    f.write(data.get('question', ''))
    f.write('\n')
" "$RAW_RESPONSE" "$RESPONSE_FILE"
fi

# =============================================================================
# Step 4: Update version log
# =============================================================================
python3 -c "
import json, os

log_path = '$VERSION_LOG'
if os.path.exists(log_path):
    with open(log_path) as f:
        data = json.load(f)
else:
    data = {'versions': [], 'current_version': 0}

version_entry = {
    'version': $NEXT_VERSION,
    'timestamp': '$TIMESTAMP',
    'directory': 'v${NEXT_VERSION}_${TIMESTAMP}',
    'reviewer_mode': '$REVIEWER_MODE',
    'paper_tex': os.path.exists('$VERSION_DIR/paper.tex'),
    'paper_pdf': os.path.exists('$VERSION_DIR/paper.pdf'),
    'has_experiments': os.path.isdir('$VERSION_DIR/experiment_codebase'),
    'has_figures': os.path.isdir('$VERSION_DIR/figures'),
}

# Ensemble-specific metadata
ensemble_assignment = '''$ENSEMBLE_ASSIGNMENT_JSON'''
if ensemble_assignment.strip():
    try:
        version_entry['ensemble_assignment'] = json.loads(ensemble_assignment)
    except:
        pass

ensemble_results = '''${ENSEMBLE_RESULTS_JSON:-}'''
if ensemble_results.strip():
    try:
        version_entry['ensemble_results'] = json.loads(ensemble_results)
    except:
        pass

# Try to extract a preview from the response
try:
    with open('$VERSION_DIR/reviewer_communications/response.md') as f:
        text = f.read()
    # Strip the '## Review' header and grab the first 200 chars of content
    preview = text.replace('## Review', '', 1).strip()[:200]
    version_entry['reviewer_preview'] = preview
except:
    pass

data['versions'].append(version_entry)
data['current_version'] = $NEXT_VERSION

with open(log_path, 'w') as f:
    json.dump(data, f, indent=2)
"

# =============================================================================
# Step 5: Report
# =============================================================================
echo ""
echo "=== Version v${NEXT_VERSION} snapshot complete ==="
echo "  Directory: $VERSION_DIR"
echo "  Paper:     $([ -f "$VERSION_DIR/paper.tex" ] && echo 'yes' || echo 'no')"
echo "  PDF:       $([ -f "$VERSION_DIR/paper.pdf" ] && echo 'yes' || echo 'no')"
echo "  Experiments: $([ -d "$VERSION_DIR/experiment_codebase" ] && echo 'yes' || echo 'no')"
echo "  Figures:   $([ -d "$VERSION_DIR/figures" ] && echo 'yes' || echo 'no')"
echo "  Reviewer:  $VERSION_DIR/reviewer_communications/response.md"
if [ "$REVIEWER_MODE" = "ensemble" ]; then
    echo "  Mode:      ensemble (3 reviewers)"
    if [ -f "$VERSION_DIR/reviewer_communications/ensemble_assignment.json" ]; then
        echo "  Assignment: $(cat "$VERSION_DIR/reviewer_communications/ensemble_assignment.json")"
    fi
fi
if [ -d "$VERSION_DIR/reviewer_communications/trace" ]; then
    echo "  Trace:     $VERSION_DIR/reviewer_communications/trace/ ($(ls "$VERSION_DIR/reviewer_communications/trace/" | wc -l) file(s))"
fi
echo ""
echo "Read the reviewer's feedback at:"
echo "  $VERSION_DIR/reviewer_communications/response.md"
