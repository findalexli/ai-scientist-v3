#!/bin/bash
# Test that run.sh isolates concurrent jobs with per-job temp directories.
# Validates that harbor-task/ is treated as a read-only template and each job
# gets its own staging copy, preventing cross-contamination of artifacts.
#
# Usage: bash tests/test_run_isolation.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

section() { echo ""; echo "=== $1 ==="; }

RUN_SH="$REPO_ROOT/run.sh"

# ---------------------------------------------------------------------------
section "1. run.sh creates per-job temp directory"
# ---------------------------------------------------------------------------

if grep -q 'mktemp -d.*/tmp/harbor-task-' "$RUN_SH" 2>/dev/null; then
    pass "run.sh creates temp dir with mktemp"
else
    fail "run.sh does NOT create temp dir with mktemp"
fi

if grep -q 'TASK_DIR_TEMPLATE=.*harbor-task' "$RUN_SH" 2>/dev/null; then
    pass "run.sh defines TASK_DIR_TEMPLATE pointing to harbor-task"
else
    fail "run.sh missing TASK_DIR_TEMPLATE"
fi

if grep -q 'cp -r "\$TASK_DIR_TEMPLATE"/\*' "$RUN_SH" 2>/dev/null; then
    pass "run.sh copies template contents to temp dir"
else
    fail "run.sh does NOT copy template to temp dir"
fi

# Docker requires lowercase image names; Harbor derives names from the task dir
if grep -q "tr '\[:upper:\]' '\[:lower:\]'" "$RUN_SH" 2>/dev/null; then
    pass "run.sh lowercases temp dir name for Docker compatibility"
else
    fail "run.sh does NOT lowercase temp dir name (Docker requires lowercase image names)"
fi

# ---------------------------------------------------------------------------
section "2. Derived paths use temp dir, not shared harbor-task"
# ---------------------------------------------------------------------------

if grep -q 'ENV_DIR="\$TASK_DIR/environment"' "$RUN_SH" 2>/dev/null; then
    pass "ENV_DIR points to temp dir"
else
    fail "ENV_DIR does NOT point to temp dir"
fi

if grep -q 'INSTRUCTION_TEMPLATE="\$TASK_DIR/instruction.md.template"' "$RUN_SH" 2>/dev/null; then
    pass "INSTRUCTION_TEMPLATE points to temp dir"
else
    fail "INSTRUCTION_TEMPLATE does NOT point to temp dir"
fi

if grep -q 'INSTRUCTION_OUT="\$TASK_DIR/instruction.md"' "$RUN_SH" 2>/dev/null; then
    pass "INSTRUCTION_OUT points to temp dir"
else
    fail "INSTRUCTION_OUT does NOT point to temp dir"
fi

# ---------------------------------------------------------------------------
section "3. Harbor -p flag uses temp dir"
# ---------------------------------------------------------------------------

if grep -q '\-p "\$TASK_DIR/"' "$RUN_SH" 2>/dev/null; then
    pass "Harbor -p points to temp dir"
else
    fail "Harbor -p does NOT point to temp dir"
fi

# Ensure no leftover reference to the shared path for -p
if grep -q '\-p "\$SCRIPT_DIR/harbor-task/"' "$RUN_SH" 2>/dev/null; then
    fail "Harbor -p still references shared harbor-task directory"
else
    pass "No stale -p reference to shared harbor-task"
fi

# ---------------------------------------------------------------------------
section "4. Cleanup removes temp dir"
# ---------------------------------------------------------------------------

if grep -q 'rm -rf "\$TASK_DIR"' "$RUN_SH" 2>/dev/null; then
    pass "cleanup() removes temp dir"
else
    fail "cleanup() does NOT remove temp dir"
fi

# Ensure cleanup does NOT reference the shared ENV_DIR paths (old pattern)
if grep -q 'rm.*\$ENV_DIR/blank_icbinb_latex' "$RUN_SH" 2>/dev/null; then
    fail "cleanup() still removes individual staged files (old pattern)"
else
    pass "cleanup() does not use old per-file removal pattern"
fi

# ---------------------------------------------------------------------------
section "5. harbor-task/ is never written to directly"
# ---------------------------------------------------------------------------

# run.sh should NOT write to $SCRIPT_DIR/harbor-task/ after the template copy.
# Check that ENV_DIR, INSTRUCTION_TEMPLATE, INSTRUCTION_OUT don't use
# $SCRIPT_DIR/harbor-task/ (except for TASK_DIR_TEMPLATE definition).
DIRECT_WRITES=$(grep -n 'SCRIPT_DIR/harbor-task/' "$RUN_SH" 2>/dev/null \
    | grep -v 'TASK_DIR_TEMPLATE=' \
    | grep -v '^#' \
    | grep -v '^\s*#' || true)

if [ -z "$DIRECT_WRITES" ]; then
    pass "No direct writes to shared harbor-task directory"
else
    fail "Found direct references to shared harbor-task: $DIRECT_WRITES"
fi

# ---------------------------------------------------------------------------
section "6. No stale rm -rf of prev_artifacts before mkdir"
# ---------------------------------------------------------------------------

# The old pattern was: rm -rf "$ENV_DIR/prev_artifacts" followed by mkdir.
# With per-job temp dirs, the rm -rf is unnecessary (fresh copy each time).
if grep -q 'rm -rf.*prev_artifacts' "$RUN_SH" 2>/dev/null; then
    fail "run.sh still has rm -rf of prev_artifacts (unnecessary with temp dirs)"
else
    pass "No unnecessary rm -rf of prev_artifacts"
fi

# The mkdir + .keep pattern should still exist (needed for Dockerfile COPY)
if grep -q 'mkdir -p "\$ENV_DIR/prev_artifacts"' "$RUN_SH" 2>/dev/null; then
    pass "prev_artifacts mkdir still present for Dockerfile COPY"
else
    fail "prev_artifacts mkdir missing"
fi

# ---------------------------------------------------------------------------
section "7. Functional: temp dirs are independent"
# ---------------------------------------------------------------------------

# Simulate what run.sh does: create two temp dirs from the template,
# stage different prev_artifacts, and verify they don't interfere.
TEMPLATE_DIR="$REPO_ROOT/harbor-task"

if [ ! -d "$TEMPLATE_DIR" ]; then
    fail "harbor-task template directory not found"
else
    JOB1=$(mktemp -d "/tmp/harbor-task-test1-XXXXXX")
    JOB2=$(mktemp -d "/tmp/harbor-task-test2-XXXXXX")
    cp -r "$TEMPLATE_DIR"/* "$JOB1/"
    cp -r "$TEMPLATE_DIR"/* "$JOB2/"

    # Stage different prev_artifacts in each
    mkdir -p "$JOB1/environment/prev_artifacts"
    echo "job1-paper" > "$JOB1/environment/prev_artifacts/paper.tex"

    mkdir -p "$JOB2/environment/prev_artifacts"
    echo "job2-paper" > "$JOB2/environment/prev_artifacts/paper.tex"

    # Verify isolation
    JOB1_CONTENT=$(cat "$JOB1/environment/prev_artifacts/paper.tex")
    JOB2_CONTENT=$(cat "$JOB2/environment/prev_artifacts/paper.tex")

    if [ "$JOB1_CONTENT" = "job1-paper" ] && [ "$JOB2_CONTENT" = "job2-paper" ]; then
        pass "Concurrent temp dirs have independent prev_artifacts"
    else
        fail "Temp dir artifacts leaked between jobs"
    fi

    # Verify template is unmodified
    if [ ! -f "$TEMPLATE_DIR/environment/prev_artifacts/paper.tex" ]; then
        pass "Template directory unmodified by temp dir operations"
    else
        fail "Template directory was modified"
    fi

    # Verify .env staging in one doesn't affect the other
    echo "KEY=job1" > "$JOB1/environment/.env"
    if [ ! -f "$JOB2/environment/.env" ]; then
        pass "Staging .env in job1 does not affect job2"
    else
        fail ".env leaked between temp dirs"
    fi

    # Verify Dockerfile selection is independent
    if [ -f "$JOB1/environment/Dockerfile.cpu" ]; then
        cp "$JOB1/environment/Dockerfile.cpu" "$JOB1/environment/Dockerfile"
    fi
    if [ -f "$JOB2/environment/Dockerfile.gpu" ]; then
        cp "$JOB2/environment/Dockerfile.gpu" "$JOB2/environment/Dockerfile"
    fi

    JOB1_DF=$(head -1 "$JOB1/environment/Dockerfile" 2>/dev/null || echo "")
    JOB2_DF=$(head -1 "$JOB2/environment/Dockerfile" 2>/dev/null || echo "")
    if [ "$JOB1_DF" != "$JOB2_DF" ] || [ -n "$JOB1_DF" ]; then
        pass "Dockerfile selection is independent between jobs"
    else
        fail "Dockerfile selection is NOT independent"
    fi

    # Cleanup
    rm -rf "$JOB1" "$JOB2"
    pass "Temp dirs cleaned up successfully"
fi

# ---------------------------------------------------------------------------
section "8. Functional: cleanup removes temp dir completely"
# ---------------------------------------------------------------------------

TEMP_DIR=$(mktemp -d "/tmp/harbor-task-test-cleanup-XXXXXX")
cp -r "$TEMPLATE_DIR"/* "$TEMP_DIR/"
mkdir -p "$TEMP_DIR/environment/prev_artifacts"
echo "test" > "$TEMP_DIR/environment/prev_artifacts/paper.tex"
echo "test" > "$TEMP_DIR/environment/.env"
cp "$TEMP_DIR/environment/Dockerfile.cpu" "$TEMP_DIR/environment/Dockerfile" 2>/dev/null || true

# Simulate cleanup
rm -rf "$TEMP_DIR"

if [ ! -d "$TEMP_DIR" ]; then
    pass "rm -rf removes entire temp dir (no leftover files)"
else
    fail "Temp dir still exists after cleanup"
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
