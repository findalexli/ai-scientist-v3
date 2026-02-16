#!/bin/bash
# Extract text from a LaTeX paper and generate review questions in one step
#
# Usage: extract_and_generate_questions.sh <tex_path>
#   tex_path: path to .tex file
#
# Output: JSON with extracted text and generated question
#
# Timing: ~30s (just question generation)
# Caller should use a generous timeout (180s+)

set -e

TEX_PATH="$1"

if [ -z "$TEX_PATH" ] || [ ! -f "$TEX_PATH" ]; then
    echo "Error: File not found: $TEX_PATH" >&2
    exit 1
fi

case "$TEX_PATH" in
    *.tex) ;;
    *)
        echo "Error: Expected a .tex file, got: $TEX_PATH" >&2
        exit 1
        ;;
esac

QUESTIONS_API_URL="${QUESTIONS_API_URL:-http://31.97.61.220/api/generate}"

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

TEXT_FILE="$TMPDIR/paper_text.txt"

# --- Step 1: Extract text from LaTeX source ---
echo "Extracting text from LaTeX source..." >&2

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/extract_latex_body.py" "$TEX_PATH" > "$TEXT_FILE"

echo "LaTeX text extracted." >&2

# --- Step 2: Generate review questions ---
echo "Generating review questions (this may take 20-30 seconds)..." >&2

QUESTION_FILE="$TMPDIR/question_response.json"

python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    text = f.read()
print(json.dumps({'text': text}))
" "$TEXT_FILE" | curl -s -X POST "$QUESTIONS_API_URL" \
    -H "Content-Type: application/json" \
    -d @- --max-time 240 > "$QUESTION_FILE"

# --- Step 3: Combine results ---
python3 -c "
import sys, json

text_file = sys.argv[1]
question_file = sys.argv[2]

try:
    with open(question_file) as f:
        question_data = json.load(f)
    question = question_data.get('question', '')
except:
    question = ''

with open(text_file) as f:
    extracted_text = f.read()

output = {
    'extracted_text': extracted_text.strip(),
    'question': question
}

print(json.dumps(output, indent=2))
" "$TEXT_FILE" "$QUESTION_FILE"

echo "Done." >&2
