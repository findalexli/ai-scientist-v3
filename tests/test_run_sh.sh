#!/bin/bash
# Tests for run.sh argument parsing — especially the --agent flag.
#
# Usage: bash tests/test_run_sh.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_SH="$REPO_ROOT/run.sh"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

section() { echo ""; echo "=== $1 ==="; }

# Create a dummy idea.json for tests that need one
DUMMY_IDEA=$(mktemp /tmp/test_idea_XXXXXX.json)
echo '{"Name": "test", "Title": "Test"}' > "$DUMMY_IDEA"
cleanup() { rm -f "$DUMMY_IDEA"; }
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Helper: run run.sh with args, capturing its output (stops before harbor runs
# by mocking the harbor command and docker).
# Returns the stdout which contains the "Starting Harbor run..." block.
# ---------------------------------------------------------------------------
capture_run_output() {
    # Create a mock harbor binary that just exits
    local MOCK_DIR
    MOCK_DIR=$(mktemp -d)
    cat > "$MOCK_DIR/harbor" <<'MOCK'
#!/bin/bash
exit 0
MOCK
    chmod +x "$MOCK_DIR/harbor"

    # Also mock docker so GPU check doesn't fail
    cat > "$MOCK_DIR/docker" <<'MOCK'
#!/bin/bash
echo "nvidia"
exit 0
MOCK
    chmod +x "$MOCK_DIR/docker"

    # Run with mocked PATH (harbor exits immediately so we capture the echo output)
    PATH="$MOCK_DIR:$PATH" bash "$RUN_SH" "$@" 2>&1 || true
    rm -rf "$MOCK_DIR"
}

# ---------------------------------------------------------------------------
section "1. Default agent type is claude-code"
# ---------------------------------------------------------------------------

OUTPUT=$(capture_run_output "$DUMMY_IDEA")
if echo "$OUTPUT" | grep -q "Agent:.*claude-code"; then
    pass "Default agent is claude-code"
else
    fail "Default agent is not claude-code. Output: $(echo "$OUTPUT" | grep Agent || echo 'no Agent line')"
fi

# ---------------------------------------------------------------------------
section "2. Default model for claude-code"
# ---------------------------------------------------------------------------

if echo "$OUTPUT" | grep -q "Model:.*anthropic/claude-opus-4-6"; then
    pass "Default claude-code model is anthropic/claude-opus-4-6"
else
    fail "Wrong default model. Output: $(echo "$OUTPUT" | grep Model || echo 'no Model line')"
fi

# ---------------------------------------------------------------------------
section "3. --agent gemini-cli sets correct model"
# ---------------------------------------------------------------------------

OUTPUT=$(capture_run_output "$DUMMY_IDEA" --agent gemini-cli)
if echo "$OUTPUT" | grep -q "Model:.*google/gemini-3.1-pro-preview"; then
    pass "Gemini CLI default model is google/gemini-3.1-pro-preview"
else
    fail "Wrong Gemini model. Output: $(echo "$OUTPUT" | grep Model || echo 'no Model line')"
fi

# ---------------------------------------------------------------------------
section "4. --agent gemini-cli shows correct agent type"
# ---------------------------------------------------------------------------

if echo "$OUTPUT" | grep -q "Agent:.*gemini-cli"; then
    pass "Agent output shows gemini-cli"
else
    fail "Agent output missing gemini-cli. Output: $(echo "$OUTPUT" | grep Agent || echo 'no Agent line')"
fi

# ---------------------------------------------------------------------------
section "5. --agent gemini-cli --model overrides default"
# ---------------------------------------------------------------------------

OUTPUT=$(capture_run_output "$DUMMY_IDEA" --agent gemini-cli --model "custom/my-model")
if echo "$OUTPUT" | grep -q "Model:.*custom/my-model"; then
    pass "Explicit --model overrides gemini-cli default"
else
    fail "Model override failed. Output: $(echo "$OUTPUT" | grep Model || echo 'no Model line')"
fi

# ---------------------------------------------------------------------------
section "6. --agent unknown exits with error"
# ---------------------------------------------------------------------------

ERR_OUTPUT=$(capture_run_output "$DUMMY_IDEA" --agent unknown-agent 2>&1)
if echo "$ERR_OUTPUT" | grep -q "unknown agent type"; then
    pass "Unknown agent type produces error"
else
    fail "No error for unknown agent. Output: $ERR_OUTPUT"
fi

# ---------------------------------------------------------------------------
section "7. --help shows --agent flag"
# ---------------------------------------------------------------------------

HELP_OUTPUT=$(bash "$RUN_SH" --help 2>&1 || true)
if echo "$HELP_OUTPUT" | grep -q "\-\-agent"; then
    pass "--agent appears in help output"
else
    fail "--agent missing from help output"
fi

# ---------------------------------------------------------------------------
section "8. --help shows both agent types"
# ---------------------------------------------------------------------------

if echo "$HELP_OUTPUT" | grep -q "claude-code.*gemini-cli\|gemini-cli.*claude-code"; then
    pass "Help mentions both claude-code and gemini-cli"
else
    fail "Help does not mention both agent types"
fi

# ---------------------------------------------------------------------------
section "9. --model without --agent defaults to claude-code model"
# ---------------------------------------------------------------------------

OUTPUT=$(capture_run_output "$DUMMY_IDEA" --model "anthropic/claude-sonnet-4-5-20250929")
if echo "$OUTPUT" | grep -q "Agent:.*claude-code"; then
    pass "Explicit --model without --agent keeps claude-code agent"
else
    fail "Agent changed unexpectedly. Output: $(echo "$OUTPUT" | grep Agent || echo 'no Agent line')"
fi
if echo "$OUTPUT" | grep -q "Model:.*anthropic/claude-sonnet-4-5-20250929"; then
    pass "Explicit --model is used"
else
    fail "Model not applied. Output: $(echo "$OUTPUT" | grep Model || echo 'no Model line')"
fi

# ---------------------------------------------------------------------------
section "10. Patched agent import path differs per agent type"
# ---------------------------------------------------------------------------

# We can't directly read the variable, but we can check the harbor command args
# by making our mock print them
MOCK_DIR=$(mktemp -d)
cat > "$MOCK_DIR/harbor" <<'MOCK'
#!/bin/bash
echo "HARBOR_ARGS: $@"
exit 0
MOCK
chmod +x "$MOCK_DIR/harbor"
cat > "$MOCK_DIR/docker" <<'MOCK'
#!/bin/bash
echo "nvidia"
exit 0
MOCK
chmod +x "$MOCK_DIR/docker"

CC_OUTPUT=$(PATH="$MOCK_DIR:$PATH" bash "$RUN_SH" "$DUMMY_IDEA" 2>&1 || true)
GC_OUTPUT=$(PATH="$MOCK_DIR:$PATH" bash "$RUN_SH" "$DUMMY_IDEA" --agent gemini-cli 2>&1 || true)
rm -rf "$MOCK_DIR"

if echo "$CC_OUTPUT" | grep -q "patched_claude_code:PatchedClaudeCode"; then
    pass "claude-code uses PatchedClaudeCode import path"
else
    fail "claude-code import path wrong. Harbor args: $(echo "$CC_OUTPUT" | grep HARBOR_ARGS || echo 'none')"
fi

if echo "$GC_OUTPUT" | grep -q "patched_gemini_cli:PatchedGeminiCli"; then
    pass "gemini-cli uses PatchedGeminiCli import path"
else
    fail "gemini-cli import path wrong. Harbor args: $(echo "$GC_OUTPUT" | grep HARBOR_ARGS || echo 'none')"
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
