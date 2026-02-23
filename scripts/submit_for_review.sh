#!/bin/bash
# Submit a paper for external review and create a versioned snapshot.
#
# Usage: bash scripts/submit_for_review.sh <tex_path> [base_dir]
#   tex_path:  Path to the .tex file to submit
#   base_dir:  Workspace root (default: /app, or parent of scripts/ if not in container)
#
# What this does:
#   1. Generates a review (via external API or Claude Code subagent)
#   2. Creates a versioned snapshot in submissions/v{N}_{timestamp}/ containing:
#      - paper.tex, paper.pdf
#      - experiment_codebase/
#      - figures/
#      - reviewer_communications/response.md
#   3. Updates submissions/version_log.json
#
# Environment variables:
#   REVIEWER_MODE  — "api" (default) uses external reviewer API (works with any runtime)
#                    "subagent" uses Claude Code reviewer agent (.claude/agents/reviewer.md)
#                    NOTE: "subagent" requires the Claude Code CLI (`claude` command).
#                    It will NOT work with Gemini CLI or other agent runtimes.
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

REVIEWER_MODE="${REVIEWER_MODE:-api}"

# --- Step 1: Generate review ---
echo "=== Submitting paper for review ==="
echo "Paper: $TEX_PATH"
echo "Reviewer mode: $REVIEWER_MODE"

RAW_RESPONSE="$BASE_DIR/reviewer_raw_response.json"

if [ "$REVIEWER_MODE" = "subagent" ]; then
    # Requires Claude Code CLI. Will not work with Gemini or other runtimes.
    if ! command -v claude &>/dev/null; then
        echo "Error: REVIEWER_MODE=subagent requires the Claude Code CLI." >&2
        exit 1
    fi

    echo "Invoking reviewer subagent (this may take several minutes)..."

    # Snapshot existing session files so we can identify the reviewer's trace afterward.
    SESSIONS_PROJECT_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/-app"
    PRE_SESSIONS=""
    if [ -d "$SESSIONS_PROJECT_DIR" ]; then
        PRE_SESSIONS=$(find "$SESSIONS_PROJECT_DIR" -name "*.jsonl" 2>/dev/null | sort)
    fi

    # CLAUDECODE="" clears the nesting guard so claude can launch from within a running session.
    # --output-format text gives us the review directly on stdout — no parsing needed.
    if ! CLAUDECODE="" claude -p \
        --agent reviewer \
        --model opus \
        --output-format text \
        --dangerously-skip-permissions \
        "Review the research submission. The paper is at $TEX_PATH. Inspect the full workspace: experiment_codebase/, figures/, literature/, and latex/. Follow your review procedure and produce your review." \
        > "$RAW_RESPONSE" 2>"$BASE_DIR/reviewer_subagent_stderr.log"; then
        echo "Warning: Reviewer subagent returned non-zero exit code." >&2
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
                # Flatten into trace dir: replace / with __ to keep filenames unique
                FLAT_NAME=$(echo "$f" | sed "s|$SESSIONS_PROJECT_DIR/||; s|/|__|g")
                cp "$f" "$REVIEWER_TRACE_DIR/$FLAT_NAME"
            done
            echo "Reviewer trace: $(echo "$NEW_SESSIONS" | wc -l) session file(s) saved to $REVIEWER_TRACE_DIR/"
        fi
    fi

    echo "Reviewer subagent complete."

else
    # --- External API reviewer (original behavior) ---
    if [ ! -f "$EXTRACT_SCRIPT" ]; then
        echo "Error: extract_and_generate_questions.sh not found at $EXTRACT_SCRIPT" >&2
        exit 1
    fi

    echo "Calling external reviewer model (this takes ~30 seconds)..."
    bash "$EXTRACT_SCRIPT" "$TEX_PATH" > "$RAW_RESPONSE"
    echo "External reviewer response received."
fi

# --- Step 2: Determine next version number ---
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

# --- Step 3: Create versioned snapshot ---
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

if [ "$REVIEWER_MODE" = "subagent" ]; then
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

# --- Step 4: Update version log ---
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

# --- Step 5: Report ---
echo ""
echo "=== Version v${NEXT_VERSION} snapshot complete ==="
echo "  Directory: $VERSION_DIR"
echo "  Paper:     $([ -f "$VERSION_DIR/paper.tex" ] && echo 'yes' || echo 'no')"
echo "  PDF:       $([ -f "$VERSION_DIR/paper.pdf" ] && echo 'yes' || echo 'no')"
echo "  Experiments: $([ -d "$VERSION_DIR/experiment_codebase" ] && echo 'yes' || echo 'no')"
echo "  Figures:   $([ -d "$VERSION_DIR/figures" ] && echo 'yes' || echo 'no')"
echo "  Reviewer:  $VERSION_DIR/reviewer_communications/response.md"
if [ -d "$VERSION_DIR/reviewer_communications/trace" ]; then
    echo "  Trace:     $VERSION_DIR/reviewer_communications/trace/ ($(ls "$VERSION_DIR/reviewer_communications/trace/" | wc -l) file(s))"
fi
echo ""
echo "Read the reviewer's feedback at:"
echo "  $VERSION_DIR/reviewer_communications/response.md"
