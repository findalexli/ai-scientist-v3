#!/usr/bin/env python3
"""Monitor a running Harbor task on Modal.

Usage:
    python monitor.py              # Show agent trajectory (text + tool calls)
    python monitor.py --ps         # Show running processes + GPU usage
    python monitor.py --files      # Show experiment files and figures
    python monitor.py --tail N     # Show last N lines of claude-code.txt raw
"""
import sys
import json
import modal


def get_sandbox():
    sandboxes = list(modal.Sandbox.list())
    if not sandboxes:
        print("No active sandboxes found.")
        sys.exit(1)
    if len(sandboxes) > 1:
        print(f"Found {len(sandboxes)} sandboxes, using first one.")
    return sandboxes[0]


def show_trajectory(sb):
    proc = sb.exec("cat", "/logs/agent/claude-code.txt")
    raw = proc.stdout.read()
    for line in raw.strip().split("\n"):
        try:
            event = json.loads(line)
            if event.get("type") == "assistant":
                msg = event.get("message", {})
                for block in msg.get("content", []):
                    if block.get("type") == "text" and block.get("text", "").strip():
                        text = block["text"][:300]
                        print(f"\n[AGENT] {text}")
                    elif block.get("type") == "tool_use":
                        name = block.get("name", "")
                        inp = block.get("input", {})
                        if name == "Bash":
                            print(f"  > {name}: {inp.get('command', '')[:150]}")
                        elif name in ("Read", "Write", "Edit", "Glob", "Grep"):
                            path = inp.get("file_path", inp.get("pattern", ""))
                            print(f"  > {name}: {path[:150]}")
                        elif name == "Task":
                            print(
                                f"  > {name}: {inp.get('description', '')[:150]}"
                            )
                        else:
                            print(f"  > {name}")
        except (json.JSONDecodeError, KeyError):
            pass


def show_ps(sb):
    proc = sb.exec(
        "bash",
        "-c",
        'echo "=== Processes ===" && ps aux | grep -E "python|torch|claude" | grep -v grep && echo "" && echo "=== GPU ===" && nvidia-smi 2>/dev/null || echo "No GPU"',
    )
    print(proc.stdout.read())


def show_files(sb):
    proc = sb.exec(
        "bash",
        "-c",
        'echo "=== Experiments ===" && ls -lah /app/experiment_results/ 2>/dev/null && echo "" && echo "=== Figures ===" && ls -lah /app/figures/ 2>/dev/null && echo "" && echo "=== Latex ===" && ls -lah /app/latex/*.tex /app/latex/*.pdf 2>/dev/null && echo "" && echo "=== Review ===" && ls -lah /app/review.json 2>/dev/null || echo "not yet"',
    )
    print(proc.stdout.read())


def show_tail(sb, n=50):
    proc = sb.exec("tail", f"-{n}", "/logs/agent/claude-code.txt")
    print(proc.stdout.read())


if __name__ == "__main__":
    sb = get_sandbox()
    if "--ps" in sys.argv:
        show_ps(sb)
    elif "--files" in sys.argv:
        show_files(sb)
    elif "--tail" in sys.argv:
        n = 50
        idx = sys.argv.index("--tail")
        if idx + 1 < len(sys.argv):
            n = int(sys.argv[idx + 1])
        show_tail(sb, n)
    else:
        show_trajectory(sb)
