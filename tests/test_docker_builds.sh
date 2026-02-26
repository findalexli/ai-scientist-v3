#!/bin/bash
# End-to-end tests for Docker image builds and GPU patch correctness.
#
# Tests that both Dockerfiles actually build, packages import inside the
# containers, and the GPU patch correctly modifies Harbor's docker.py.
#
# Usage: bash tests/test_docker_builds.sh
#
# Note: Docker build tests require Docker. GPU patch tests are pure file I/O.
# First run may be slow (~3-5 min) while layers download; subsequent runs are
# cached and fast.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

section() { echo ""; echo "=== $1 ==="; }

CPU_IMAGE="test-aiscientist-cpu-$$"
GPU_IMAGE="test-aiscientist-gpu-$$"
BUILD_CTX=""

cleanup() {
    # Remove test images
    docker rmi "$CPU_IMAGE" "$GPU_IMAGE" 2>/dev/null || true
    # Remove build context
    if [[ -n "$BUILD_CTX" && -d "$BUILD_CTX" ]]; then
        rm -rf "$BUILD_CTX"
    fi
}
trap cleanup EXIT

# ===========================================================================
section "1. Stage Docker build context"
# ===========================================================================

# Both Dockerfiles COPY these dirs from the build context. Create a minimal
# staging area so `docker build` succeeds without the full run.sh pipeline.
BUILD_CTX=$(mktemp -d)

cp "$REPO_ROOT/harbor-task/environment/Dockerfile.cpu" "$BUILD_CTX/Dockerfile.cpu"
cp "$REPO_ROOT/harbor-task/environment/Dockerfile.gpu" "$BUILD_CTX/Dockerfile.gpu"
cp -r "$REPO_ROOT/blank_icbinb_latex" "$BUILD_CTX/blank_icbinb_latex"
cp -r "$REPO_ROOT/scripts" "$BUILD_CTX/scripts"
cp -r "$REPO_ROOT/.claude" "$BUILD_CTX/.claude"
mkdir -p "$BUILD_CTX/prev_artifacts"
touch "$BUILD_CTX/prev_artifacts/.keep"

# Copy .gitignore.agent (used by Dockerfile COPY .gitignore.agent)
cp "$REPO_ROOT/harbor-task/environment/.gitignore.agent" "$BUILD_CTX/.gitignore.agent"

# Copy docker-compose.yaml so context is complete (not used by build, but
# keeps the directory structure identical to what run.sh stages)
cp "$REPO_ROOT/harbor-task/environment/docker-compose.yaml" "$BUILD_CTX/" 2>/dev/null || true

pass "Build context staged to $BUILD_CTX"

# ===========================================================================
section "2. Build CPU image"
# ===========================================================================

if docker build -q -f "$BUILD_CTX/Dockerfile.cpu" -t "$CPU_IMAGE" "$BUILD_CTX" > /dev/null 2>&1; then
    pass "CPU image builds successfully"
else
    fail "CPU image build failed"
fi

# ===========================================================================
section "3. CPU image: core packages import"
# ===========================================================================

if docker run --rm "$CPU_IMAGE" python3 -c "
import numpy, pandas, sklearn, matplotlib, seaborn, scipy, datasets
print('ok')
" 2>/dev/null | grep -q "ok"; then
    pass "CPU image: numpy, pandas, sklearn, matplotlib, seaborn, scipy, datasets all import"
else
    fail "CPU image: package import failed"
fi

# ===========================================================================
section "4. CPU image: uv installed"
# ===========================================================================

if docker run --rm "$CPU_IMAGE" uv --version 2>/dev/null | grep -q "uv"; then
    pass "CPU image: uv is installed"
else
    fail "CPU image: uv not found"
fi

# ===========================================================================
section "5. CPU image: Claude Code CLI installed"
# ===========================================================================

if docker run --rm "$CPU_IMAGE" claude --version 2>/dev/null | grep -q "."; then
    pass "CPU image: claude CLI is installed ($(docker run --rm "$CPU_IMAGE" claude --version 2>/dev/null | head -1))"
else
    fail "CPU image: claude CLI not found"
fi

# ===========================================================================
section "6. CPU image: git repo pre-initialized"
# ===========================================================================

if docker run --rm "$CPU_IMAGE" bash -c "cd /app && git status && test -f .gitignore" 2>/dev/null | grep -q "On branch"; then
    pass "CPU image: /app is a git repo with .gitignore"
else
    fail "CPU image: git repo not initialized in /app"
fi

# ===========================================================================
section "7. Build GPU image"
# ===========================================================================

if docker build -q -f "$BUILD_CTX/Dockerfile.gpu" -t "$GPU_IMAGE" "$BUILD_CTX" > /dev/null 2>&1; then
    pass "GPU image builds successfully"
else
    fail "GPU image build failed"
fi

# ===========================================================================
section "7. GPU image: PyTorch + core packages import"
# ===========================================================================

if docker run --rm "$GPU_IMAGE" python3 -c "
import torch, numpy, pandas, sklearn, matplotlib, seaborn, scipy, datasets
print('torch', torch.__version__)
print('ok')
" 2>/dev/null | grep -q "ok"; then
    pass "GPU image: torch, numpy, pandas, sklearn, matplotlib, seaborn, scipy, datasets all import"
else
    fail "GPU image: package import failed"
fi

# ===========================================================================
section "8. GPU image: uv installed"
# ===========================================================================

if docker run --rm "$GPU_IMAGE" uv --version 2>/dev/null | grep -q "uv"; then
    pass "GPU image: uv is installed"
else
    fail "GPU image: uv not found"
fi

# ===========================================================================
section "9. GPU image: Claude Code CLI installed"
# ===========================================================================

if docker run --rm "$GPU_IMAGE" claude --version 2>/dev/null | grep -q "."; then
    pass "GPU image: claude CLI is installed ($(docker run --rm "$GPU_IMAGE" claude --version 2>/dev/null | head -1))"
else
    fail "GPU image: claude CLI not found"
fi

# ===========================================================================
section "10. GPU image: git repo pre-initialized"
# ===========================================================================

if docker run --rm "$GPU_IMAGE" bash -c "cd /app && git status && test -f .gitignore" 2>/dev/null | grep -q "On branch"; then
    pass "GPU image: /app is a git repo with .gitignore"
else
    fail "GPU image: git repo not initialized in /app"
fi

# ===========================================================================
section "11. GPU image: uv pip install --system works"
# ===========================================================================

# This catches PEP 668 / EXTERNALLY-MANAGED regressions
if docker run --rm "$GPU_IMAGE" bash -c "uv pip install --system --no-cache requests 2>&1 && python3 -c 'import requests; print(\"ok\")'" 2>/dev/null | grep -q "ok"; then
    pass "GPU image: uv pip install --system works (PEP 668 unblocked)"
else
    fail "GPU image: uv pip install --system failed (PEP 668 EXTERNALLY-MANAGED still present?)"
fi

# ===========================================================================
section "12. GPU patch: patch_docker_py() on new-format Harbor"
# ===========================================================================

# Create a mock docker.py that uses the new Harbor format (imported constants)
MOCK_DIR=$(mktemp -d)
cat > "$MOCK_DIR/docker.py" <<'MOCK_DOCKER_PY'
from pathlib import Path
from harbor.environments.docker import COMPOSE_NO_NETWORK_PATH

class DockerEnvironmentEnvVars:
    memory: str = "1G"

class DockerEnvironment:
    _DOCKER_COMPOSE_NO_NETWORK_PATH = COMPOSE_NO_NETWORK_PATH

    def supports_gpus(self) -> bool:
        return False

    def __init__(self):
        env_vars = DockerEnvironmentEnvVars(
            memory=f"{task_env_config.memory_mb}M",
        )

    def _get_compose_paths(self):
        paths = []
        if not self.task_env_config.allow_internet:
            paths.append(self._DOCKER_COMPOSE_NO_NETWORK_PATH)
        return paths
MOCK_DOCKER_PY

PATCH_OUTPUT=$(cd "$REPO_ROOT" && python3 -c "
from pathlib import Path
from local_harbor_agents.patch_docker_gpu import patch_docker_py, is_patched

docker_py = Path('$MOCK_DIR/docker.py')
patched = patch_docker_py(docker_py)
content = docker_py.read_text()

# Check: class attribute DEFINITION exists (not just usage)
has_def = '_DOCKER_COMPOSE_GPU_PATH =' in content
# Check: is_patched agrees
detected = is_patched(docker_py)
# Check: supports_gpus returns True
has_gpu_true = 'return True' in content
# Check: gpus field added
has_gpus_field = 'gpus: int' in content

print(f'patched={patched} has_def={has_def} detected={detected} has_gpu_true={has_gpu_true} has_gpus_field={has_gpus_field}')
" 2>&1)

if echo "$PATCH_OUTPUT" | grep -q "patched=True has_def=True detected=True has_gpu_true=True has_gpus_field=True"; then
    pass "GPU patch applies correctly to new-format Harbor (imported constants)"
else
    fail "GPU patch failed on new-format Harbor: $PATCH_OUTPUT"
fi

# ===========================================================================
section "13. GPU patch: patch_docker_py() on old-format Harbor"
# ===========================================================================

cat > "$MOCK_DIR/docker.py" <<'MOCK_DOCKER_PY'
from pathlib import Path

class DockerEnvironmentEnvVars:
    memory: str = "1G"

class DockerEnvironment:
    _DOCKER_COMPOSE_NO_NETWORK_PATH = (
        Path(__file__).parent / "docker-compose-no-network.yaml"
    )

    def supports_gpus(self) -> bool:
        return False

    def __init__(self):
        env_vars = DockerEnvironmentEnvVars(
            memory=f"{task_env_config.memory_mb}M",
        )

    def _get_compose_paths(self):
        paths = []
        if not self.task_env_config.allow_internet:
            paths.append(self._DOCKER_COMPOSE_NO_NETWORK_PATH)
        return paths
MOCK_DOCKER_PY

PATCH_OUTPUT=$(cd "$REPO_ROOT" && python3 -c "
from pathlib import Path
from local_harbor_agents.patch_docker_gpu import patch_docker_py, is_patched

docker_py = Path('$MOCK_DIR/docker.py')
patched = patch_docker_py(docker_py)
content = docker_py.read_text()

has_def = '_DOCKER_COMPOSE_GPU_PATH =' in content
detected = is_patched(docker_py)

print(f'patched={patched} has_def={has_def} detected={detected}')
" 2>&1)

if echo "$PATCH_OUTPUT" | grep -q "patched=True has_def=True detected=True"; then
    pass "GPU patch applies correctly to old-format Harbor (inline Path)"
else
    fail "GPU patch failed on old-format Harbor: $PATCH_OUTPUT"
fi

# ===========================================================================
section "14. GPU patch: is_patched() rejects incomplete patch"
# ===========================================================================

# A file that has the USAGE of _DOCKER_COMPOSE_GPU_PATH but not the DEFINITION
cat > "$MOCK_DIR/docker.py" <<'MOCK_DOCKER_PY'
class DockerEnvironmentEnvVars:
    memory: str = "1G"
    gpus: int = 0

class DockerEnvironment:
    def supports_gpus(self) -> bool:
        return True

    def __init__(self):
        env_vars = DockerEnvironmentEnvVars(
            gpus=task_env_config.gpus,
        )

    def _get_compose_paths(self):
        if self.task_env_config.gpus > 0:
            paths.append(self._DOCKER_COMPOSE_GPU_PATH)
MOCK_DOCKER_PY

PATCH_OUTPUT=$(cd "$REPO_ROOT" && python3 -c "
from pathlib import Path
from local_harbor_agents.patch_docker_gpu import is_patched

docker_py = Path('$MOCK_DIR/docker.py')
detected = is_patched(docker_py)
print(f'detected={detected}')
" 2>&1)

if echo "$PATCH_OUTPUT" | grep -q "detected=False"; then
    pass "is_patched() correctly rejects file with usage but no class attribute definition"
else
    fail "is_patched() wrongly accepted incomplete patch: $PATCH_OUTPUT"
fi

# ===========================================================================
section "15. GPU patch: create_gpu_compose() output"
# ===========================================================================

COMPOSE_OUTPUT=$(cd "$REPO_ROOT" && python3 -c "
from pathlib import Path
from local_harbor_agents.patch_docker_gpu import create_gpu_compose

d = Path('$MOCK_DIR')
create_gpu_compose(d)
content = (d / 'docker-compose-gpu.yaml').read_text()

has_nvidia = 'driver: nvidia' in content
has_count = '\${GPUS:-1}' in content
has_caps = 'capabilities: [gpu]' in content

print(f'has_nvidia={has_nvidia} has_count={has_count} has_caps={has_caps}')
" 2>&1)

if echo "$COMPOSE_OUTPUT" | grep -q "has_nvidia=True has_count=True has_caps=True"; then
    pass "GPU compose overlay has nvidia driver, GPU count variable, and gpu capabilities"
else
    fail "GPU compose overlay incorrect: $COMPOSE_OUTPUT"
fi

rm -rf "$MOCK_DIR"

# ===========================================================================
# Summary
# ===========================================================================

echo ""
echo "==========================================="
echo "  RESULTS: $PASS passed, $FAIL failed"
echo "==========================================="

if [ "$FAIL" -gt 0 ]; then
    exit 1
else
    exit 0
fi
