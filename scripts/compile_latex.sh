#!/usr/bin/env bash
# compile_latex.sh — Compile LaTeX paper and run linter
#
# Usage:
#   ./compile_latex.sh                    # compile template.tex in current dir
#   ./compile_latex.sh /path/to/latex/    # compile template.tex in given dir
#
# Output: Compilation status, errors if any, chktex warnings

set -uo pipefail

LATEX_DIR="${1:-.}"
TEX_FILE="template.tex"

# Find pdflatex (macOS TeX Live is often not on PATH)
PDFLATEX=$(command -v pdflatex 2>/dev/null || echo "/Library/TeX/texbin/pdflatex")
BIBTEX=$(command -v bibtex 2>/dev/null || echo "/Library/TeX/texbin/bibtex")
CHKTEX=$(command -v chktex 2>/dev/null || echo "/Library/TeX/texbin/chktex")

if [[ ! -x "$PDFLATEX" ]]; then
  echo "ERROR: pdflatex not found. Install TeX Live or MacTeX." >&2
  exit 1
fi

cd "$LATEX_DIR"

if [[ ! -f "$TEX_FILE" ]]; then
  echo "ERROR: $TEX_FILE not found in $LATEX_DIR" >&2
  exit 1
fi

echo "=== Compiling $TEX_FILE ==="

# First pass (generates .aux)
echo "--- Pass 1/3: pdflatex ---"
"$PDFLATEX" -interaction=nonstopmode "$TEX_FILE" > /dev/null 2>&1
PASS1=$?

# BibTeX (resolves citations)
echo "--- BibTeX ---"
"$BIBTEX" "${TEX_FILE%.tex}" 2>&1 | grep -E "^(Warning|Error|I found)" || true

# Second pass (includes bibliography)
echo "--- Pass 2/3: pdflatex ---"
"$PDFLATEX" -interaction=nonstopmode "$TEX_FILE" > /dev/null 2>&1

# Third pass (resolves cross-references)
echo "--- Pass 3/3: pdflatex ---"
"$PDFLATEX" -interaction=nonstopmode "$TEX_FILE" > /dev/null 2>&1
PASS3=$?

# Check compilation result
PDF_FILE="${TEX_FILE%.tex}.pdf"
if [[ -f "$PDF_FILE" ]]; then
  PDF_SIZE=$(wc -c < "$PDF_FILE" | tr -d ' ')
  PDF_PAGES=$(python3 -c "
try:
    import subprocess
    result = subprocess.run(['pdfinfo', '$PDF_FILE'], capture_output=True, text=True)
    for line in result.stdout.split('\n'):
        if line.startswith('Pages:'):
            print(line.split(':')[1].strip())
            break
    else:
        print('?')
except:
    print('?')
" 2>/dev/null || echo "?")
  echo ""
  echo "=== SUCCESS ==="
  echo "Output: $PDF_FILE ($PDF_SIZE bytes, $PDF_PAGES pages)"
else
  echo ""
  echo "=== FAILED ==="
  echo "No PDF generated. Check LaTeX errors below:"
  # Show relevant errors from log
  if [[ -f "${TEX_FILE%.tex}.log" ]]; then
    grep -A2 "^!" "${TEX_FILE%.tex}.log" | head -30
  fi
  exit 1
fi

# Run chktex linter
if [[ -x "$CHKTEX" ]]; then
  echo ""
  echo "=== Lint warnings (chktex) ==="
  "$CHKTEX" -q "$TEX_FILE" 2>/dev/null | head -20 || echo "No warnings."
else
  echo ""
  echo "(chktex not found, skipping lint)"
fi
