"""
Patch Harbor's DockerEnvironment to support local GPU passthrough.

This module patches Harbor's installed docker.py to enable GPU support for local
Docker runs. The patch:
1. Changes `supports_gpus` to return True
2. Adds GPU count to environment variables
3. Creates a GPU-enabled docker-compose overlay

Run automatically by run.sh when --gpus is specified, or manually:
    python -m local_harbor_agents.patch_docker_gpu
"""

from __future__ import annotations

import glob
import subprocess
import sys
from pathlib import Path
from typing import Optional


def find_harbor_docker_dir() -> Optional[Path]:
    """Find Harbor's docker environment directory."""
    try:
        result = subprocess.run(
            ["uv", "tool", "dir"], capture_output=True, text=True, check=True
        )
        tools_dir = result.stdout.strip()
        matches = glob.glob(
            f"{tools_dir}/harbor/lib/*/site-packages/harbor/environments/docker"
        )
        return Path(matches[0]) if matches else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def is_patched(docker_py: Path) -> bool:
    """Check if docker.py is already patched for GPU support."""
    content = docker_py.read_text()
    return (
        "def supports_gpus(self) -> bool:\n        return True" in content
        and "gpus: int" in content
        and "gpus=task_env_config.gpus" in content
    )


def patch_docker_py(docker_py: Path) -> bool:
    """Patch docker.py to enable GPU support. Returns True if patched."""
    content = docker_py.read_text()
    original = content

    # 1. Add gpus field to DockerEnvironmentEnvVars
    if "gpus: int" not in content:
        content = content.replace(
            'memory: str = "1G"', 'memory: str = "1G"\n    gpus: int = 0'
        )

    # 2. Change supports_gpus to return True
    content = content.replace(
        "def supports_gpus(self) -> bool:\n        return False",
        "def supports_gpus(self) -> bool:\n        return True",
    )

    # 3. Add gpus to __init__ env_vars construction
    if "gpus=task_env_config.gpus" not in content:
        content = content.replace(
            'memory=f"{task_env_config.memory_mb}M",',
            'memory=f"{task_env_config.memory_mb}M",\n            gpus=task_env_config.gpus,',
        )

    # 4. Add GPU compose file path constant
    if "_DOCKER_COMPOSE_GPU_PATH" not in content:
        content = content.replace(
            '_DOCKER_COMPOSE_NO_NETWORK_PATH = (\n        Path(__file__).parent / "docker-compose-no-network.yaml"\n    )',
            '_DOCKER_COMPOSE_NO_NETWORK_PATH = (\n        Path(__file__).parent / "docker-compose-no-network.yaml"\n    )\n    _DOCKER_COMPOSE_GPU_PATH = Path(__file__).parent / "docker-compose-gpu.yaml"',
        )

    # 5. Add GPU compose file to paths when gpus > 0
    if "self._DOCKER_COMPOSE_GPU_PATH" not in content:
        content = content.replace(
            "if not self.task_env_config.allow_internet:",
            "# Add GPU compose overlay if GPUs requested\n        if self.task_env_config.gpus > 0:\n            paths.append(self._DOCKER_COMPOSE_GPU_PATH)\n\n        if not self.task_env_config.allow_internet:",
        )

    if content != original:
        docker_py.write_text(content)
        return True
    return False


def create_gpu_compose(docker_dir: Path) -> bool:
    """Create GPU-enabled docker-compose overlay. Returns True if created."""
    gpu_compose = docker_dir / "docker-compose-gpu.yaml"

    content = """\
# GPU-enabled docker-compose overlay for local NVIDIA GPU passthrough
# Automatically merged when task requests GPUs > 0
services:
  main:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: ${GPUS:-1}
              capabilities: [gpu]
"""

    if gpu_compose.exists() and gpu_compose.read_text() == content:
        return False

    gpu_compose.write_text(content)
    return True


def ensure_gpu_support(quiet: bool = False) -> bool:
    """
    Ensure Harbor Docker environment supports local GPUs.
    Returns True if Harbor is properly configured.
    """
    docker_dir = find_harbor_docker_dir()
    if not docker_dir:
        if not quiet:
            print("Error: Harbor not installed. Run: uv tool install harbor", file=sys.stderr)
        return False

    docker_py = docker_dir / "docker.py"
    if not docker_py.exists():
        if not quiet:
            print(f"Error: {docker_py} not found", file=sys.stderr)
        return False

    # Check if already patched
    if is_patched(docker_py):
        gpu_compose = docker_dir / "docker-compose-gpu.yaml"
        if gpu_compose.exists():
            return True

    # Apply patches
    patched = patch_docker_py(docker_py)
    created = create_gpu_compose(docker_dir)

    if not quiet and (patched or created):
        print(f"Patched Harbor for local GPU support: {docker_dir}")

    return True


def main():
    """CLI entry point."""
    print("Checking Harbor GPU support...\n")

    docker_dir = find_harbor_docker_dir()
    if not docker_dir:
        print("Error: Harbor not installed. Run: uv tool install harbor")
        return 1

    print(f"Harbor location: {docker_dir}")

    docker_py = docker_dir / "docker.py"
    if is_patched(docker_py):
        print("Status: Already patched for GPU support")
        return 0

    if ensure_gpu_support():
        print("Status: Patched successfully")
        print("\nUsage: ./run.sh idea.json --gpus 1")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
