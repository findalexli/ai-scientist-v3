"""Parse claude-code.txt JSONL transcripts into unified event streams."""

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, List, Optional

# Import shared sanitization module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from sanitize_secrets import (  # noqa: E402
    REDACTION,
    get_default_sanitizer as _get_sanitizer,
    sanitize_text as _sanitize_text,
    sanitize_json as _sanitize_json,
)


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


def mask_secrets_in_text(text: str) -> str:
    """Mask secrets/tokens in a string for safe display."""
    return _sanitize_text(text)


def mask_secrets(value: Any) -> Any:
    """Recursively mask secrets in nested objects."""
    return _sanitize_json(value)


def _mask_events(events: List[Event]) -> None:
    for ev in events:
        ev.summary = mask_secrets_in_text(ev.summary or "")
        if ev.detail:
            ev.detail = mask_secrets_in_text(ev.detail)


def _estimate_tokens_from_chars(char_count: int) -> int:
    """Estimate token count from character count.

    Approximation: ~3.5 chars per token for code-heavy content (Claude tokenizer).
    English prose averages ~4 chars/token, but code, JSON, and tool args are denser.
    """
    if char_count <= 0:
        return 0
    return max(1, int(char_count / 3.5))


def _estimate_output_tokens_from_content(content_blocks: list) -> int:
    """Estimate output tokens from actual content blocks in Claude Code JSONL.

    The usage.output_tokens field is unreliable (per-block streaming deltas).
    This estimates from the real text content the model produced.
    """
    total_chars = 0
    for block in content_blocks:
        block_type = block.get("type", "")
        if block_type == "thinking":
            total_chars += len(block.get("thinking", ""))
        elif block_type == "text":
            total_chars += len(block.get("text", ""))
        elif block_type == "tool_use":
            # Tool name + serialized input arguments.
            total_chars += len(block.get("name", ""))
            inp = block.get("input", {})
            if isinstance(inp, dict):
                total_chars += len(json.dumps(inp, ensure_ascii=False))
            elif isinstance(inp, str):
                total_chars += len(inp)
    return _estimate_tokens_from_chars(total_chars)


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
    lname = (name or "").lower()

    if name == "Skill":
        skill = tool_input.get("skill", "")
        if "search-papers" in skill:
            return "literature_review"
        return "other"

    if name == "Bash" or lname in {"run_shell_command", "run_command", "execute_command", "bash"}:
        cmd = (
            tool_input.get("command")
            or tool_input.get("cmd")
            or tool_input.get("bash_command")
            or ""
        )
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

    if name in ("Read", "Glob", "Grep") or lname in {
        "read_file",
        "grep_search",
        "glob_search",
        "list_directory",
    }:
        return "file_read"

    if name in ("Write", "Edit") or lname in {"write_file", "edit_file", "update_file", "replace_in_file"}:
        # Check if writing to tex/bib or figures
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        if any(ext in path for ext in [".tex", ".bib"]) or "/latex/" in path:
            return "paper_write"
        if "/figures/" in path:
            return "plotting"
        return "file_write"

    if name == "Task":
        return "subagent"

    if name in ("WebFetch", "WebSearch") or lname in {
        "web_fetch",
        "web_search",
        "fetch_url",
        "google_search",
    }:
        return "web"

    if name in ("TodoWrite", "TaskOutput", "TaskStop"):
        return "task_mgmt"

    return "other"


def _summarize_tool(name: str, tool_input: dict, event_type: str) -> str:
    """Create a human-readable summary for a tool call."""
    lname = (name or "").lower()

    if name == "Bash" or lname in {"run_shell_command", "run_command", "execute_command", "bash"}:
        desc = tool_input.get("description", "")
        if desc:
            return f"Bash: {desc}"
        cmd = (
            tool_input.get("command")
            or tool_input.get("cmd")
            or tool_input.get("bash_command")
            or ""
        )
        # Truncate long commands
        first_line = cmd.split("\n")[0][:120]
        return f"Bash: {first_line}"

    if name == "Read" or lname == "read_file":
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        short = os.path.basename(path) if path else "?"
        return f"Read: {short}"

    if name == "Write" or lname == "write_file":
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        short = os.path.basename(path) if path else "?"
        return f"Write: {short}"

    if name == "Edit" or lname in {"edit_file", "update_file", "replace_in_file"}:
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        short = os.path.basename(path) if path else "?"
        return f"Edit: {short}"

    if name == "Glob" or lname == "glob_search":
        pattern = tool_input.get("pattern", "")
        return f"Glob: {pattern}"

    if name == "Grep" or lname == "grep_search":
        pattern = tool_input.get("pattern", "")
        return f"Grep: {pattern[:80]}"

    if name == "WebFetch" or lname in {"web_fetch", "fetch_url"}:
        url = tool_input.get("url", "")
        return f"WebFetch: {url[:80]}"

    if name == "WebSearch" or lname in {"web_search", "google_search"}:
        query = tool_input.get("query") or tool_input.get("search_term") or ""
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
    lname = (name or "").lower()

    if name == "Bash" or lname in {"run_shell_command", "run_command", "execute_command", "bash"}:
        cmd = (
            tool_input.get("command")
            or tool_input.get("cmd")
            or tool_input.get("bash_command")
            or ""
        )
        if len(cmd) > 120:
            return cmd[:500]
        return None

    if name in ("Write", "Edit") or lname in {"write_file", "edit_file", "update_file", "replace_in_file"}:
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        return path

    if name == "Task":
        prompt = tool_input.get("prompt", "")
        return prompt[:300] if prompt else None

    return None


def _extract_tokens_from_metrics(metrics: dict) -> TokenInfo:
    if not metrics:
        return TokenInfo()
    extra = metrics.get("extra", {}) if isinstance(metrics, dict) else {}
    cache_creation = 0
    if isinstance(extra, dict):
        cache_creation = extra.get("cache_creation_input_tokens", 0)
        if isinstance(cache_creation, dict):
            cache_creation = (
                cache_creation.get("ephemeral_5m_input_tokens", 0)
                + cache_creation.get("ephemeral_1h_input_tokens", 0)
            )
    cache_read = metrics.get("cached_tokens", 0) or (
        extra.get("cache_read_input_tokens", 0) if isinstance(extra, dict) else 0
    )
    prompt_tokens = metrics.get("prompt_tokens", 0)
    # Harbor ATIF prompt_tokens can include cache-read tokens.
    # Convert to uncached input tokens so cost accounting doesn't double count cache reads.
    uncached_input = metrics.get("input_tokens")
    if uncached_input is None:
        uncached_input = prompt_tokens
        if cache_read and prompt_tokens >= cache_read:
            uncached_input = prompt_tokens - cache_read

    return TokenInfo(
        input_tokens=uncached_input or 0,
        output_tokens=metrics.get("completion_tokens", 0) or metrics.get("output_tokens", 0),
        cache_read=cache_read,
        cache_creation=cache_creation or 0,
    )


def _stringify_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def parse_atif_trajectory(path: str, after_line: int = 0) -> ParseResult:
    """Parse Harbor ATIF trajectory.json into unified event stream."""
    if not os.path.exists(path):
        return ParseResult(events=[], total_lines=0)

    try:
        with open(path, "r", errors="replace") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return ParseResult(events=[], total_lines=0)

    steps = data.get("steps", [])
    session_id = data.get("session_id")
    agent_info = data.get("agent", {}) if isinstance(data.get("agent"), dict) else {}
    model = agent_info.get("model_name")
    agent_name = agent_info.get("name")

    all_events: List[Event] = []

    def add_event(
        source: str,
        event_type: str,
        summary: str,
        detail: Optional[str] = None,
        tool_name: Optional[str] = None,
        tokens: Optional[dict] = None,
        timestamp: Optional[str] = None,
        tool_id: Optional[str] = None,
    ) -> None:
        idx = len(all_events)
        all_events.append(
            Event(
                step=idx,
                timestamp=timestamp,
                source=source,
                event_type=event_type,
                tool_name=tool_name,
                summary=summary,
                detail=detail,
                tokens=tokens,
                line_num=idx,
                tool_id=tool_id,
            )
        )

    for step in steps:
        source = step.get("source", "agent")
        ts = step.get("timestamp")
        token_info = _extract_tokens_from_metrics(step.get("metrics", {}))

        # Fix output_tokens: ATIF reasoning_content is often empty (thinking
        # text is dropped), so completion_tokens may under-count.
        # However, Gemini's metrics.extra.thoughts_tokens reports thinking
        # tokens accurately, and completion_tokens already includes them.
        # Strategy: estimate from visible content + thoughts_tokens, take max.
        if source == "agent":
            metrics = step.get("metrics", {}) if isinstance(step.get("metrics"), dict) else {}
            extra = metrics.get("extra", {}) if isinstance(metrics.get("extra"), dict) else {}
            thoughts_tokens = extra.get("thoughts_tokens", 0) or 0

            content_chars = 0
            msg_text = step.get("message", "")
            if isinstance(msg_text, str):
                content_chars += len(msg_text)
            reasoning = step.get("reasoning_content", "")
            if isinstance(reasoning, str):
                content_chars += len(reasoning)
            for tc in (step.get("tool_calls") or []):
                if isinstance(tc, dict):
                    args = tc.get("arguments", {})
                    content_chars += len(json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args))
                    content_chars += len(tc.get("function_name", ""))
            visible_estimated = _estimate_tokens_from_chars(content_chars)
            # Best estimate = visible content tokens + thinking tokens.
            estimated = visible_estimated + thoughts_tokens
            if estimated > token_info.output_tokens:
                token_info.output_tokens = estimated

        token_dict = asdict(token_info) if any([
            token_info.input_tokens,
            token_info.output_tokens,
            token_info.cache_read,
            token_info.cache_creation,
        ]) else None
        token_attached = False

        def step_tokens_once() -> Optional[dict]:
            nonlocal token_attached
            if token_attached or token_dict is None:
                return None
            token_attached = True
            return token_dict

        message = _stringify_content(step.get("message", "")).strip()
        reasoning = _stringify_content(step.get("reasoning_content", "")).strip()
        tool_calls = step.get("tool_calls") if isinstance(step.get("tool_calls"), list) else []

        if source == "agent":
            if reasoning and reasoning.lower() not in {"null", "none"}:
                add_event(
                    source="agent",
                    event_type="thinking",
                    summary=f"Thinking: {reasoning[:100]}...",
                    detail=reasoning[:1000] if len(reasoning) > 100 else None,
                    tokens=step_tokens_once(),
                    timestamp=ts,
                )

            if message and not (tool_calls and message.startswith("Executed ")):
                add_event(
                    source="agent",
                    event_type="text",
                    summary=message[:150],
                    detail=message if len(message) > 150 else None,
                    tokens=step_tokens_once(),
                    timestamp=ts,
                )

            for call in tool_calls:
                tool_name = call.get("function_name") or call.get("name") or ""
                tool_input = call.get("arguments") or call.get("input") or {}
                if not isinstance(tool_input, dict):
                    tool_input = {"raw": _stringify_content(tool_input)}
                tool_id = call.get("tool_call_id") or call.get("id")
                event_type = _categorize_tool(tool_name, tool_input)
                add_event(
                    source="agent",
                    event_type=event_type,
                    tool_name=tool_name,
                    summary=_summarize_tool(tool_name, tool_input, event_type),
                    detail=_get_detail(tool_name, tool_input),
                    tokens=step_tokens_once(),
                    timestamp=ts,
                    tool_id=tool_id,
                )

            obs = step.get("observation", {}) if isinstance(step.get("observation"), dict) else {}
            results = obs.get("results", []) if isinstance(obs.get("results"), list) else []
            step_extra = step.get("extra", {}) if isinstance(step.get("extra"), dict) else {}
            is_error = bool(step_extra.get("tool_result_is_error", False))

            for result in results:
                call_id = result.get("source_call_id")
                content = _stringify_content(result.get("content", ""))
                preview = content[:200] if content else "(empty)"
                summary = f"Error: {preview}" if is_error else f"Result: {preview}"
                add_event(
                    source="tool_result",
                    event_type="tool_result",
                    summary=summary,
                    detail=content[:1000] if len(content) > 200 else None,
                    tokens=None,
                    timestamp=ts,
                    tool_id=call_id,
                )

        elif source == "user":
            if message:
                add_event(
                    source="user",
                    event_type="user_message",
                    summary=message[:150],
                    detail=message if len(message) > 150 else None,
                    tokens=step_tokens_once(),
                    timestamp=ts,
                )
        elif source == "system":
            if message:
                add_event(
                    source="system",
                    event_type="system",
                    summary=message[:150],
                    detail=message if len(message) > 150 else None,
                    tokens=step_tokens_once(),
                    timestamp=ts,
                )
        elif message:
            add_event(
                source=source,
                event_type="other",
                summary=message[:150],
                detail=message if len(message) > 150 else None,
                tokens=step_tokens_once(),
                timestamp=ts,
            )

        # Keep accounting accurate even if this step produced no visible event.
        if token_dict is not None and not token_attached:
            add_event(
                source=source if source in {"agent", "user", "system"} else "agent",
                event_type="text" if source == "agent" else "other",
                summary="Model turn (no visible content)",
                detail=None,
                tokens=step_tokens_once(),
                timestamp=ts,
            )

    total_lines = len(all_events)
    filtered = [e for e in all_events if e.line_num >= after_line]
    _mask_events(filtered)

    return ParseResult(
        events=filtered,
        total_lines=total_lines,
        session_id=session_id,
        model=model,
        agent_name=agent_name,
    )


def parse_claude_code_jsonl(path: str, after_line: int = 0) -> ParseResult:
    """Parse claude-code.txt JSONL, optionally starting from line N for incremental reads."""
    events = []
    session_id = None
    model = None
    step = after_line  # step counter continues from where we left off
    seen_msg_ids = set()  # Track message IDs to avoid double-counting tokens
    # Accumulate all content blocks per message ID so we can estimate output
    # tokens from actual content rather than the unreliable usage.output_tokens.
    msg_content_blocks: Dict[str, list] = {}

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

                # Accumulate content blocks for output token estimation.
                msg_id = message.get("id", "")
                if msg_id:
                    if msg_id not in msg_content_blocks:
                        msg_content_blocks[msg_id] = []
                    msg_content_blocks[msg_id].extend(content_blocks)

                # Only count tokens once per unique API call (message ID).
                # Claude Code splits multi-block responses into separate JSONL
                # lines, each carrying the full usage for that API call.
                if msg_id and msg_id in seen_msg_ids:
                    token_info = None  # Already counted for this API call
                else:
                    token_info = _extract_tokens(usage)
                    # Override output_tokens with content-based estimate.
                    # The usage.output_tokens is unreliable (per-block streaming
                    # deltas of 1-19 tokens, not the real total).
                    if token_info and msg_id:
                        all_blocks = msg_content_blocks.get(msg_id, content_blocks)
                        estimated = _estimate_output_tokens_from_content(all_blocks)
                        if estimated > token_info.output_tokens:
                            token_info.output_tokens = estimated
                    if msg_id:
                        seen_msg_ids.add(msg_id)

                token_attached = False

                def msg_tokens_once():
                    nonlocal token_attached
                    if token_info is None or token_attached:
                        return None
                    token_attached = True
                    return asdict(token_info)

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
                            tokens=msg_tokens_once(),
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
                            tokens=msg_tokens_once(),
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
                            tokens=msg_tokens_once(),
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

    _mask_events(events)

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
    """Estimate cost based on token usage and model pricing.

    NOTE on output_tokens:
    - The raw usage.output_tokens from Claude Code JSONL and ATIF completion_tokens
      are unreliable (per-block streaming deltas / dropped thinking content).
    - The parsers now override output_tokens with content-based estimates
      (~3.5 chars/token) when the reported value is suspiciously low.
    - This is an approximation; actual token counts depend on the model's tokenizer.
    """
    # Pricing per million tokens (USD) — updated Feb 2026
    # Cache read = 0.1x input, cache write (5min) = 1.25x input
    pricing = {
        "claude-opus-4-6":   {"input": 5.0,   "output": 25.0,  "cache_read": 0.50,  "cache_creation": 6.25},
        "claude-opus-4-5":   {"input": 5.0,   "output": 25.0,  "cache_read": 0.50,  "cache_creation": 6.25},
        "claude-sonnet-4-6": {"input": 3.0,   "output": 15.0,  "cache_read": 0.30,  "cache_creation": 3.75},
        "claude-sonnet-4-5": {"input": 3.0,   "output": 15.0,  "cache_read": 0.30,  "cache_creation": 3.75},
        "claude-haiku-4-5":  {"input": 1.0,   "output": 5.0,   "cache_read": 0.10,  "cache_creation": 1.25},
        "gemini-3.1-pro-preview": {"input": 2.0, "output": 12.0, "cache_read": 0.20, "cache_creation": 2.0},
        "gemini-3.1-pro":    {"input": 2.0,   "output": 12.0,  "cache_read": 0.20,  "cache_creation": 2.0},
        "gemini-3-pro":      {"input": 2.0,   "output": 12.0,  "cache_read": 0.20,  "cache_creation": 2.0},
        "gemini-2.5-pro":    {"input": 1.25,  "output": 10.0,  "cache_read": 0.125, "cache_creation": 1.25},
    }

    # Normalize model name and resolve best pricing match.
    model_norm = (model or "").lower()
    prices = pricing.get(model_norm)
    if not prices:
        # Prefer most specific key first.
        for key in sorted(pricing.keys(), key=len, reverse=True):
            if key in model_norm:
                prices = pricing[key]
                break
    if not prices:
        # Family-based fallback to avoid silently overcharging non-Claude models.
        if "gemini" in model_norm:
            prices = pricing["gemini-3.1-pro-preview"]
        elif "sonnet" in model_norm:
            prices = pricing["claude-sonnet-4-6"]
        elif "haiku" in model_norm:
            prices = pricing["claude-haiku-4-5"]
        else:
            prices = pricing["claude-opus-4-6"]

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


def find_trajectory_path(job_dir: str) -> Optional[str]:
    """Find Harbor ATIF trajectory.json within a job directory."""
    direct = os.path.join(job_dir, "trajectory.json")
    if os.path.exists(direct):
        return direct

    try:
        for entry in os.listdir(job_dir):
            if entry.startswith("harbor-task"):
                path = os.path.join(job_dir, entry, "agent", "trajectory.json")
                if os.path.exists(path):
                    return path
    except OSError:
        pass
    return None


def find_claude_code_path(job_dir: str) -> Optional[str]:
    """Find the claude-code.txt file within a job directory."""
    direct = os.path.join(job_dir, "claude-code.txt")
    if os.path.exists(direct):
        return direct

    try:
        for entry in os.listdir(job_dir):
            if entry.startswith("harbor-task"):
                path = os.path.join(job_dir, entry, "agent", "claude-code.txt")
                if os.path.exists(path):
                    return path
    except OSError:
        pass
    return None


def find_gemini_raw_path(job_dir: str) -> Optional[str]:
    """Find gemini-cli.trajectory.json within a job directory."""
    direct = os.path.join(job_dir, "gemini-cli.trajectory.json")
    if os.path.exists(direct):
        return direct

    try:
        for entry in os.listdir(job_dir):
            if entry.startswith("harbor-task"):
                path = os.path.join(job_dir, entry, "agent", "gemini-cli.trajectory.json")
                if os.path.exists(path):
                    return path
    except OSError:
        pass
    return None


def find_agent_activity_path(job_dir: str) -> Optional[str]:
    """Find best file that indicates latest agent activity."""
    for finder in (find_trajectory_path, find_claude_code_path, find_gemini_raw_path):
        path = finder(job_dir)
        if path:
            return path
    return None


def detect_and_parse(trial_dir: str, after_line: int = 0) -> ParseResult:
    """Auto-detect and parse with Harbor trajectory as primary source."""
    traj_path = find_trajectory_path(trial_dir)
    if traj_path:
        parsed = parse_atif_trajectory(traj_path, after_line)
        if parsed.events or parsed.total_lines > 0:
            return parsed

    cc_path = find_claude_code_path(trial_dir)
    if cc_path:
        return parse_claude_code_jsonl(cc_path, after_line)

    return ParseResult(events=[], total_lines=0)


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
