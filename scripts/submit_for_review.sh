#!/bin/bash
# Submit a paper for external review and create a versioned snapshot.
#
# Usage: bash scripts/submit_for_review.sh <tex_path> [base_dir]
#   tex_path:  Path to the .tex file to submit
#   base_dir:  Workspace root (default: /app, or parent of scripts/ if not in container)
#
# What this does:
#   1. Calls extract_and_generate_questions.sh to get review questions from the
#      external reviewer model API
#   2. Creates a versioned snapshot in submissions/v{N}_{timestamp}/ containing:
#      - paper.tex, paper.pdf
#      - experiment_results/
#      - figures/
#      - reviewer_communications/response.json (raw API response)
#   3. Updates submissions/version_log.json
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

# --- Step 1: Call external reviewer model ---
echo "=== Submitting paper for external review ==="
echo "Paper: $TEX_PATH"

RAW_RESPONSE="$BASE_DIR/reviewer_raw_response.json"

if [ ! -f "$EXTRACT_SCRIPT" ]; then
    echo "Error: extract_and_generate_questions.sh not found at $EXTRACT_SCRIPT" >&2
    exit 1
fi

echo "Calling external reviewer model (this takes ~30 seconds)..."
bash "$EXTRACT_SCRIPT" "$TEX_PATH" > "$RAW_RESPONSE"
echo "External reviewer response received."

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
if [ -d "$BASE_DIR/experiment_results" ]; then
    cp -r "$BASE_DIR/experiment_results" "$VERSION_DIR/experiment_results"
fi

# Copy figures
if [ -d "$BASE_DIR/figures" ]; then
    cp -r "$BASE_DIR/figures" "$VERSION_DIR/figures"
fi

# Copy reviewer communications (the raw API response)
cp "$RAW_RESPONSE" "$VERSION_DIR/reviewer_communications/response.json"

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
    'paper_tex': os.path.exists('$VERSION_DIR/paper.tex'),
    'paper_pdf': os.path.exists('$VERSION_DIR/paper.pdf'),
    'has_experiments': os.path.isdir('$VERSION_DIR/experiment_results'),
    'has_figures': os.path.isdir('$VERSION_DIR/figures'),
}

# Try to extract the reviewer question from the response
try:
    with open('$VERSION_DIR/reviewer_communications/response.json') as f:
        resp = json.load(f)
    version_entry['reviewer_question_preview'] = resp.get('question', '')[:200]
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
echo "  Experiments: $([ -d "$VERSION_DIR/experiment_results" ] && echo 'yes' || echo 'no')"
echo "  Figures:   $([ -d "$VERSION_DIR/figures" ] && echo 'yes' || echo 'no')"
echo "  Reviewer:  $VERSION_DIR/reviewer_communications/response.json"
echo ""
echo "Read the reviewer's questions at:"
echo "  $VERSION_DIR/reviewer_communications/response.json"
