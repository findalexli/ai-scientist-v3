# GPU patching (no harbor dependency)
from .patch_docker_gpu import ensure_gpu_support

# Agent patching (requires harbor - imported lazily to avoid import errors outside Harbor)
try:
    from .patched_claude_code import PatchedClaudeCode
    from .patched_gemini_cli import PatchedGeminiCli
    __all__ = ["PatchedClaudeCode", "PatchedGeminiCli", "ensure_gpu_support"]
except ImportError:
    __all__ = ["ensure_gpu_support"]
