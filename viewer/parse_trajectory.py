"""Parse claude-code.txt JSONL transcripts into unified event streams."""

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class TokenInfo:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_creation: int = 0


@dataclass
class Event:
    step: int
    timestamp: Optional[str]
    source: str  # "system" | "agent" | "user" | "tool_result"
    event_type: str
    tool_name: Optional[str]
    summary: str
    detail: Optional[str]
    tokens: Optional[dict]  # serialized TokenInfo
    line_num: int
    tool_id: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class ParseResult:
    events: list
    total_lines: int
    session_id: Optional[str] = None
    model: Optional[str] = None
    agent_name: Optional[str] = None

    def to_dict(self):
        return {
            "events": [e.to_dict() for e in self.events],
            "total_lines": self.total_lines,
            "session_id": self.session_id,
            "model": self.model,
            "agent_name": self.agent_name,
        }


def _extract_tokens(usage: dict) -> TokenInfo:
    if not usage:
        return TokenInfo()
    return TokenInfo(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read=usage.get("cache_read_input_tokens", 0),
        cache_creation=usage.get("cache_creation_input_tokens", 0),
    )


def _categorize_tool(name: str, tool_input: dict) -> str:
    """Categorize a tool call into an event_type."""
    if name == "Skill":
        skill = tool_input.get("skill", "")
        if "search-papers" in skill:
            return "literature_review"
        return "other"

    if name == "Bash":
        cmd = tool_input.get("command", "")
        if "submit_for_review" in cmd or "extract_and_generate_questions" in cmd:
            return "submission"
        if "git clone" in cmd:
            return "git_clone"
        if re.search(r"python3?\s+[\w/]*experiment", cmd):
            return "experiment"
        if "pip install" in cmd or "uv pip install" in cmd:
            return "pip_install"
        if "compile_latex" in cmd:
            return "paper_write"
        if "matplotlib" in cmd or "create_figures" in cmd:
            return "plotting"
        if any(kw in cmd for kw in ["semantic_scholar", "openalex", "S2_API_KEY"]):
            return "literature_review"
        return "bash"

    if name in ("Read", "Glob", "Grep"):
        return "file_read"

    if name in ("Write", "Edit"):
        # Check if writing to tex/bib or figures
        path = tool_input.get("file_path", "")
        if any(ext in path for ext in [".tex", ".bib"]) or "/latex/" in path:
            return "paper_write"
        if "/figures/" in path:
            return "plotting"
        return "file_write"

    if name == "Task":
        return "subagent"

    if name in ("WebFetch", "WebSearch"):
        return "web"

    if name in ("TodoWrite", "TaskOutput", "TaskStop"):
        return "task_mgmt"

    return "other"


def _summarize_tool(name: str, tool_input: dict, event_type: str) -> str:
    """Create a human-readable summary for a tool call."""
    if name == "Bash":
        desc = tool_input.get("description", "")
        if desc:
            return f"Bash: {desc}"
        cmd = tool_input.get("command", "")
        # Truncate long commands
        first_line = cmd.split("\n")[0][:120]
        return f"Bash: {first_line}"

    if name == "Read":
        path = tool_input.get("file_path", "")
        short = os.path.basename(path) if path else "?"
        return f"Read: {short}"

    if name == "Write":
        path = tool_input.get("file_path", "")
        short = os.path.basename(path) if path else "?"
        return f"Write: {short}"

    if name == "Edit":
        path = tool_input.get("file_path", "")
        short = os.path.basename(path) if path else "?"
        return f"Edit: {short}"

    if name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"Glob: {pattern}"

    if name == "Grep":
        pattern = tool_input.get("pattern", "")
        return f"Grep: {pattern[:80]}"

    if name == "WebFetch":
        url = tool_input.get("url", "")
        return f"WebFetch: {url[:80]}"

    if name == "WebSearch":
        query = tool_input.get("query", "")
        return f"WebSearch: {query[:80]}"

    if name == "Skill":
        skill = tool_input.get("skill", "")
        args = tool_input.get("args", "")
        return f"Skill: {skill} {args[:60]}"

    if name == "Task":
        desc = tool_input.get("description", "")
        return f"Subagent: {desc}"

    if name == "TodoWrite":
        return "TodoWrite"

    if name == "TaskOutput":
        tid = tool_input.get("task_id", "")
        return f"TaskOutput: {tid}"

    return f"{name}"


def _get_detail(name: str, tool_input: dict) -> Optional[str]:
    """Get expanded detail for a tool call."""
    if name == "Bash":
        cmd = tool_input.get("command", "")
        if len(cmd) > 120:
            return cmd[:500]
        return None

    if name in ("Write", "Edit"):
        path = tool_input.get("file_path", "")
        return path

    if name == "Task":
        prompt = tool_input.get("prompt", "")
        return prompt[:300] if prompt else None

    return None


def parse_claude_code_jsonl(path: str, after_line: int = 0) -> ParseResult:
    """Parse claude-code.txt JSONL, optionally starting from line N for incremental reads."""
    events = []
    session_id = None
    model = None
    step = after_line  # step counter continues from where we left off
    seen_msg_ids = set()  # Track message IDs to avoid double-counting tokens

    if not os.path.exists(path):
        return ParseResult(events=[], total_lines=0)

    with open(path, "r", errors="replace") as f:
        for line_num, raw_line in enumerate(f):
            if line_num < after_line:
                continue

            raw_line = raw_line.strip()
            if not raw_line:
                continue

            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            msg_type = entry.get("type", "")

            # System init message
            if msg_type == "system" and entry.get("subtype") == "init":
                session_id = entry.get("session_id")
                model = entry.get("model")
                events.append(Event(
                    step=step,
                    timestamp=None,
                    source="system",
                    event_type="system",
                    tool_name=None,
                    summary=f"Session started — model={model}",
                    detail=None,
                    tokens=None,
                    line_num=line_num,
                    tool_id=None,
                ))
                step += 1
                continue

            # Assistant messages
            if msg_type == "assistant":
                message = entry.get("message", {})
                usage = message.get("usage", {})
                content_blocks = message.get("content", [])

                # Only count tokens once per unique API call (message ID).
                # Claude Code splits multi-block responses into separate JSONL
                # lines, each carrying the full usage for that API call.
                msg_id = message.get("id", "")
                if msg_id and msg_id in seen_msg_ids:
                    token_info = None  # Already counted for this API call
                else:
                    token_info = _extract_tokens(usage)
                    if msg_id:
                        seen_msg_ids.add(msg_id)

                for block in content_blocks:
                    block_type = block.get("type", "")

                    if block_type == "thinking":
                        text = block.get("thinking", "")
                        events.append(Event(
                            step=step,
                            timestamp=None,
                            source="agent",
                            event_type="thinking",
                            tool_name=None,
                            summary=f"Thinking: {text[:100]}...",
                            detail=text[:500] if len(text) > 100 else None,
                            tokens=asdict(token_info) if token_info else None,
                            line_num=line_num,
                            tool_id=None,
                        ))
                        step += 1

                    elif block_type == "text":
                        text = block.get("text", "")
                        events.append(Event(
                            step=step,
                            timestamp=None,
                            source="agent",
                            event_type="text",
                            tool_name=None,
                            summary=text[:150],
                            detail=text if len(text) > 150 else None,
                            tokens=asdict(token_info) if token_info else None,
                            line_num=line_num,
                            tool_id=None,
                        ))
                        step += 1

                    elif block_type == "tool_use":
                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {})
                        tool_id = block.get("id", "")
                        event_type = _categorize_tool(tool_name, tool_input)
                        summary = _summarize_tool(tool_name, tool_input, event_type)
                        detail = _get_detail(tool_name, tool_input)

                        events.append(Event(
                            step=step,
                            timestamp=None,
                            source="agent",
                            event_type=event_type,
                            tool_name=tool_name,
                            summary=summary,
                            detail=detail,
                            tokens=asdict(token_info) if token_info else None,
                            line_num=line_num,
                            tool_id=tool_id,
                        ))
                        step += 1

                continue

            # User messages (tool results)
            if msg_type == "user":
                message = entry.get("message", {})
                content_blocks = message.get("content", [])
                tool_result = entry.get("tool_use_result", {})

                for block in content_blocks:
                    if block.get("type") == "tool_result":
                        is_error = block.get("is_error", False)
                        tool_id = block.get("tool_use_id", "")
                        content = block.get("content", "")
                        if isinstance(content, list):
                            cleaned_content = []
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "image":
                                    cleaned_content.append({"type": "image", "source": "[BASE64_IMAGE_DATA]"})
                                else:
                                    cleaned_content.append(item)
                            content = str(cleaned_content)

                        # Summarize the result
                        result_preview = str(content)[:200] if content else "(empty)"
                        if is_error:
                            summary = f"Error: {result_preview}"
                        else:
                            # Try to get stdout from tool_use_result
                            stdout = tool_result.get("stdout", "")
                            if stdout:
                                result_preview = stdout[:200]
                            summary = f"Result: {result_preview}"

                        events.append(Event(
                            step=step,
                            timestamp=None,
                            source="tool_result",
                            event_type="tool_result",
                            tool_name=None,
                            summary=summary,
                            detail=str(content)[:1000] if len(str(content)) > 200 else None,
                            tokens=None,
                            line_num=line_num,
                            tool_id=tool_id,
                        ))
                        step += 1

                    elif block.get("type") == "text":
                        # User text messages (rare — usually task prompts)
                        text = block.get("text", "")
                        if text.strip():
                            events.append(Event(
                                step=step,
                                timestamp=None,
                                source="user",
                                event_type="user_message",
                                tool_name=None,
                                summary=text[:150],
                                detail=text if len(text) > 150 else None,
                                tokens=None,
                                line_num=line_num,
                                tool_id=None,
                            ))
                            step += 1

                continue

    total_lines = line_num + 1 if 'line_num' in dir() else 0
    # Count total lines properly
    try:
        with open(path, "r", errors="replace") as f:
            total_lines = sum(1 for _ in f)
    except Exception:
        pass

    return ParseResult(
        events=events,
        total_lines=total_lines,
        session_id=session_id,
        model=model,
    )


def compute_cumulative_tokens(events: list) -> list:
    """Compute cumulative token usage across events that have token info."""
    cumulative = []
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_creation = 0

    for e in events:
        if e.tokens:
            total_input += e.tokens.get("input_tokens", 0)
            total_output += e.tokens.get("output_tokens", 0)
            total_cache_read += e.tokens.get("cache_read", 0)
            total_cache_creation += e.tokens.get("cache_creation", 0)
            cumulative.append({
                "step": e.step,
                "input_tokens": total_input,
                "output_tokens": total_output,
                "cache_read": total_cache_read,
                "cache_creation": total_cache_creation,
                "total": total_input + total_output + total_cache_read + total_cache_creation,
            })

    return cumulative


def compute_tool_breakdown(events: list) -> list:
    """Compute tool call distribution."""
    counts = {}
    for e in events:
        if e.tool_name:
            counts[e.tool_name] = counts.get(e.tool_name, 0) + 1
    total = sum(counts.values()) or 1
    breakdown = [
        {"tool": k, "count": v, "pct": round(v / total * 100, 1)}
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    ]
    return breakdown


def compute_event_type_breakdown(events: list) -> list:
    """Compute event type distribution (for agent events only)."""
    counts = {}
    for e in events:
        if e.source == "agent":
            counts[e.event_type] = counts.get(e.event_type, 0) + 1
    total = sum(counts.values()) or 1
    breakdown = [
        {"type": k, "count": v, "pct": round(v / total * 100, 1)}
        for k, v in sorted(counts.items(), key=lambda x: -x[1])
    ]
    return breakdown


def estimate_cost(events: list, model: str = "claude-opus-4-6") -> dict:
    """Estimate cost based on token usage and model pricing."""
    # Pricing per million tokens (USD) — updated Feb 2026
    # Cache read = 0.1x input, cache write (5min) = 1.25x input
    pricing = {
        "claude-opus-4-6":   {"input": 5.0,   "output": 25.0,  "cache_read": 0.50,  "cache_creation": 6.25},
        "claude-opus-4-5":   {"input": 5.0,   "output": 25.0,  "cache_read": 0.50,  "cache_creation": 6.25},
        "claude-sonnet-4-6": {"input": 3.0,   "output": 15.0,  "cache_read": 0.30,  "cache_creation": 3.75},
        "claude-sonnet-4-5": {"input": 3.0,   "output": 15.0,  "cache_read": 0.30,  "cache_creation": 3.75},
        "claude-haiku-4-5":  {"input": 1.0,   "output": 5.0,   "cache_read": 0.10,  "cache_creation": 1.25},
        "gemini-3-pro":      {"input": 2.0,   "output": 12.0,  "cache_read": 0.20,  "cache_creation": 2.0},
        "gemini-2.5-pro":    {"input": 1.25,  "output": 10.0,  "cache_read": 0.125, "cache_creation": 1.25},
    }

    # Normalize model name — match substring
    prices = pricing.get(model, None)
    if not prices:
        for key in pricing:
            if key in (model or ""):
                prices = pricing[key]
                break
    if not prices:
        prices = pricing["claude-opus-4-6"]  # fallback

    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_creation = 0

    for e in events:
        if e.tokens:
            total_input += e.tokens.get("input_tokens", 0)
            total_output += e.tokens.get("output_tokens", 0)
            total_cache_read += e.tokens.get("cache_read", 0)
            total_cache_creation += e.tokens.get("cache_creation", 0)

    cost = (
        total_input / 1_000_000 * prices["input"]
        + total_output / 1_000_000 * prices["output"]
        + total_cache_read / 1_000_000 * prices["cache_read"]
        + total_cache_creation / 1_000_000 * prices["cache_creation"]
    )

    return {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cache_read_tokens": total_cache_read,
        "cache_creation_tokens": total_cache_creation,
        "total_tokens": total_input + total_output + total_cache_read + total_cache_creation,
        "estimated_cost_usd": round(cost, 2),
        "model": model,
    }


def detect_and_parse(trial_dir: str, after_line: int = 0) -> ParseResult:
    """Auto-detect format and parse. Looks for claude-code.txt in trial_dir or subdirectories."""
    # Direct path
    direct = os.path.join(trial_dir, "claude-code.txt")
    if os.path.exists(direct):
        return parse_claude_code_jsonl(direct, after_line)

    # Search in harbor-task*/agent/ pattern
    for entry in os.listdir(trial_dir):
        agent_path = os.path.join(trial_dir, entry, "agent", "claude-code.txt")
        if os.path.exists(agent_path):
            return parse_claude_code_jsonl(agent_path, after_line)

    return ParseResult(events=[], total_lines=0)


def find_claude_code_path(job_dir: str) -> Optional[str]:
    """Find the claude-code.txt file within a job directory."""
    # Direct
    direct = os.path.join(job_dir, "claude-code.txt")
    if os.path.exists(direct):
        return direct

    # harbor-task*/agent/claude-code.txt
    try:
        for entry in os.listdir(job_dir):
            if entry.startswith("harbor-task"):
                agent_path = os.path.join(job_dir, entry, "agent", "claude-code.txt")
                if os.path.exists(agent_path):
                    return agent_path
    except OSError:
        pass

    return None


def find_artifacts_dir(job_dir: str) -> Optional[str]:
    """Find the artifacts directory within a job directory."""
    try:
        for entry in os.listdir(job_dir):
            if entry.startswith("harbor-task"):
                # Check both agent/artifacts and verifier/artifacts
                for sub in ["agent", "verifier"]:
                    art_path = os.path.join(job_dir, entry, sub, "artifacts")
                    if os.path.isdir(art_path):
                        return art_path
    except OSError:
        pass
    return None
