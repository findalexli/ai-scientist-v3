#!/bin/bash
# Test that infrastructure files are consistent.
# Validates the experiment_codebase rename and Code References schema.
#
# Usage: bash tests/test_infrastructure.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

section() { echo ""; echo "=== $1 ==="; }

# ---------------------------------------------------------------------------
section "1. No stale experiment_results references in tracked files"
# ---------------------------------------------------------------------------

# Get list of tracked files that still reference experiment_results
STALE=$(git -C "$REPO_ROOT" grep -l "experiment_results" -- ':!interactive_run/' ':!jobs/' ':!*.md.template.bak' 2>/dev/null || true)
if [ -z "$STALE" ]; then
    pass "No tracked files reference experiment_results"
else
    fail "These tracked files still reference experiment_results: $STALE"
fi

# ---------------------------------------------------------------------------
section "2. All infrastructure files reference experiment_codebase"
# ---------------------------------------------------------------------------

REQUIRED_FILES=(
    ".claude/CLAUDE.md"
    "harbor-task/instruction.md.template"
    "harbor-task/environment/Dockerfile.cpu"
    "harbor-task/environment/Dockerfile.gpu"
    "harbor-task/tests/test.sh"
    "local_harbor_agents/patched_claude_code.py"
    "run.sh"
    "scripts/submit_for_review.sh"
    "monitor.py"
    ".gitignore"
)

for f in "${REQUIRED_FILES[@]}"; do
    FULL="$REPO_ROOT/$f"
    if [ ! -f "$FULL" ]; then
        fail "$f does not exist"
        continue
    fi
    if grep -q "experiment_codebase" "$FULL" 2>/dev/null; then
        pass "$f references experiment_codebase"
    else
        fail "$f does NOT reference experiment_codebase"
    fi
done

# ---------------------------------------------------------------------------
section "3. CLAUDE.md has code-cloning guidance"
# ---------------------------------------------------------------------------

CLAUDE_MD="$REPO_ROOT/.claude/CLAUDE.md"

if grep -q "clone it into.*experiment_codebase" "$CLAUDE_MD" 2>/dev/null; then
    pass "Literature review mentions cloning code into experiment_codebase"
else
    fail "Literature review missing clone guidance"
fi

if grep -q '"Code References"' "$CLAUDE_MD" 2>/dev/null; then
    pass "CLAUDE.md documents Code References field"
else
    fail "CLAUDE.md missing Code References documentation"
fi

if grep -q "curl -L" "$CLAUDE_MD" 2>/dev/null; then
    pass "Experiment guidelines include curl download pattern"
else
    fail "Experiment guidelines missing curl download pattern"
fi

if grep -q "Explore cloned repos" "$CLAUDE_MD" 2>/dev/null; then
    pass "Experiment guidelines include repo exploration guidance"
else
    fail "Experiment guidelines missing repo exploration guidance"
fi

# ---------------------------------------------------------------------------
section "4. Instruction template has Code References note"
# ---------------------------------------------------------------------------

TEMPLATE="$REPO_ROOT/harbor-task/instruction.md.template"

if grep -q "Code References" "$TEMPLATE" 2>/dev/null; then
    pass "Instruction template mentions Code References"
else
    fail "Instruction template missing Code References note"
fi

# ---------------------------------------------------------------------------
section "5. Idea JSON files are valid"
# ---------------------------------------------------------------------------

for f in "$REPO_ROOT"/idea*.json; do
    [ -f "$f" ] || continue
    BASENAME=$(basename "$f")
    if python3 -c "import json; json.load(open('$f'))" 2>/dev/null; then
        pass "$BASENAME is valid JSON"
    else
        fail "$BASENAME is INVALID JSON"
    fi
done

# ---------------------------------------------------------------------------
section "6. idea_videoqa_with_tool.json has Code References"
# ---------------------------------------------------------------------------

IDEA_VQA="$REPO_ROOT/idea_videoqa_with_tool.json"

if [ -f "$IDEA_VQA" ]; then
    HAS_CODE_REFS=$(python3 -c "
import json
with open('$IDEA_VQA') as f:
    data = json.load(f)
refs = data.get('Code References', [])
if refs and isinstance(refs, list) and len(refs) > 0:
    ref = refs[0]
    if 'url' in ref:
        print('ok')
    else:
        print('missing_url')
else:
    print('missing')
" 2>/dev/null)

    if [ "$HAS_CODE_REFS" = "ok" ]; then
        pass "idea_videoqa_with_tool.json has valid Code References"
    else
        fail "idea_videoqa_with_tool.json Code References: $HAS_CODE_REFS"
    fi
else
    fail "idea_videoqa_with_tool.json not found"
fi

# ---------------------------------------------------------------------------
section "7. Dockerfile consistency"
# ---------------------------------------------------------------------------

for DF in Dockerfile.cpu Dockerfile.gpu; do
    FULL="$REPO_ROOT/harbor-task/environment/$DF"
    if grep -q "mkdir -p /app/experiment_codebase" "$FULL" 2>/dev/null; then
        pass "$DF creates experiment_codebase directory"
    else
        fail "$DF does NOT create experiment_codebase directory"
    fi
    if grep -q "prev_artifacts/experiment_codebase" "$FULL" 2>/dev/null; then
        pass "$DF copies previous experiment_codebase artifacts"
    else
        fail "$DF does NOT copy previous experiment_codebase artifacts"
    fi
done

# ---------------------------------------------------------------------------
section "8. Artifact sync consistency"
# ---------------------------------------------------------------------------

PATCHED="$REPO_ROOT/local_harbor_agents/patched_claude_code.py"
if grep -q '"experiment_codebase"' "$PATCHED" 2>/dev/null; then
    pass "patched_claude_code.py syncs experiment_codebase"
else
    fail "patched_claude_code.py does NOT sync experiment_codebase"
fi

TEST_SH="$REPO_ROOT/harbor-task/tests/test.sh"
if grep -q "experiment_codebase" "$TEST_SH" 2>/dev/null; then
    pass "test.sh checks experiment_codebase"
else
    fail "test.sh does NOT check experiment_codebase"
fi

SUBMIT="$REPO_ROOT/scripts/submit_for_review.sh"
if grep -q 'experiment_codebase' "$SUBMIT" 2>/dev/null; then
    pass "submit_for_review.sh copies experiment_codebase"
else
    fail "submit_for_review.sh does NOT copy experiment_codebase"
fi

# ---------------------------------------------------------------------------
section "9. Gemini CLI support"
# ---------------------------------------------------------------------------

PATCHED_GEMINI="$REPO_ROOT/local_harbor_agents/patched_gemini_cli.py"

if [ -f "$PATCHED_GEMINI" ]; then
    pass "patched_gemini_cli.py exists"
else
    fail "patched_gemini_cli.py does not exist"
fi

if grep -q '"experiment_codebase"' "$PATCHED_GEMINI" 2>/dev/null; then
    pass "patched_gemini_cli.py syncs experiment_codebase"
else
    fail "patched_gemini_cli.py does NOT sync experiment_codebase"
fi

if grep -q 'gemini_sessions' "$PATCHED_GEMINI" 2>/dev/null; then
    pass "patched_gemini_cli.py syncs gemini_sessions"
else
    fail "patched_gemini_cli.py does NOT sync gemini_sessions"
fi

INIT_PY="$REPO_ROOT/local_harbor_agents/__init__.py"
if grep -q "PatchedClaudeCode" "$INIT_PY" && grep -q "PatchedGeminiCli" "$INIT_PY"; then
    pass "__init__.py exports both PatchedClaudeCode and PatchedGeminiCli"
else
    fail "__init__.py does not export both patched agents"
fi

if grep -q "\-\-agent" "$REPO_ROOT/run.sh" 2>/dev/null; then
    pass "run.sh supports --agent flag"
else
    fail "run.sh does NOT support --agent flag"
fi

TEMPLATE="$REPO_ROOT/harbor-task/instruction.md.template"
if grep -q "(CLAUDE.md)" "$TEMPLATE" 2>/dev/null; then
    fail "instruction.md.template still has agent-specific (CLAUDE.md) reference"
else
    pass "instruction.md.template is agent-agnostic (no CLAUDE.md parenthetical)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "==========================================="
echo "  RESULTS: $PASS passed, $FAIL failed"
echo "==========================================="

if [ "$FAIL" -gt 0 ]; then
    exit 1
else
    exit 0
fi
