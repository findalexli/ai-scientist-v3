"""Lightweight index generation for ATIF trajectory files.

Generates a compact index with step summaries and byte offsets for O(1) random
access to any step in a 200MB+ trajectory file.  The index is cached to disk as
``trajectory_index.json`` alongside the trajectory so it only needs to be built
once.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Step classification  (simplified 8-type taxonomy)
# ---------------------------------------------------------------------------

# Priority order: higher-priority types win when a step has multiple tool calls.
_TYPE_PRIORITY = {
    "literature": 7,
    "experiment": 6,
    "paper": 5,
    "submission": 4,
    "plotting": 3,
    "web": 2,
    "system": 1,
    "thinking": 0,
}


def _classify_tool_call(name: str, tool_input: dict) -> str:
    """Classify a single tool call into one of 8 event types."""
    lname = (name or "").lower()

    # -- Skill tool --
    if name == "Skill":
        skill = tool_input.get("skill", "")
        if "search-papers" in skill:
            return "literature"
        return "system"

    # -- Bash / shell commands --
    if name == "Bash" or lname in {
        "run_shell_command", "run_command", "execute_command", "bash",
    }:
        cmd = (
            tool_input.get("command")
            or tool_input.get("cmd")
            or tool_input.get("bash_command")
            or ""
        )
        # Submission
        if "submit_for_review" in cmd or "extract_and_generate_questions" in cmd:
            return "submission"

        # Literature (check BEFORE experiment to avoid false positives from
        # S2 API URLs containing "eval" substring)
        _lit_kw = (
            "semantic_scholar", "openalex",
            "crossref", "doi.org/10.",
            "api.semanticscholar", "api.openalex.org", "api.openreview.net",
        )
        if any(kw in cmd for kw in _lit_kw):
            return "literature"
        if (
            "literature/" in cmd
            and any(dl in cmd for dl in ("curl ", "wget ", "mkdir -p"))
            and "/logs/agent/artifacts" not in cmd
        ):
            return "literature"
        if any(d in cmd for d in ("arxiv.org/pdf", "arxiv.org/abs", "ar5iv.labs.arxiv.org")):
            return "literature"

        # Paper (LaTeX compilation + file access)
        if "compile_latex" in cmd or "scripts/compile_latex.sh" in cmd:
            return "paper"
        if re.search(r"bibtex\s", cmd):
            return "paper"
        if re.search(r"/latex[/\s]", cmd) and any(ext in cmd for ext in (".tex", ".bib", ".bbl", ".aux")):
            return "paper"

        # Plotting (check BEFORE experiment to avoid experiment regex stealing plotting scripts)
        if re.search(r"python3?\s+.*plotting/", cmd) or "create_figures" in cmd:
            return "plotting"
        if "matplotlib" in cmd and "pip " not in cmd and "install" not in cmd:
            return "plotting"

        # Experiment (match both trailing slash and space/&& after dir name)
        if re.search(r"(baselines|main|ablations)[/\s&]", cmd):
            if re.search(r"python3?\s", cmd):
                return "experiment"
        if re.search(r"python3?\s+\S*experiment\S*\.py\b", cmd):
            return "experiment"
        if re.search(r"\b(train|eval|evaluate)\b", cmd):
            if re.search(r"python3?\s", cmd):
                return "experiment"

        # pip/git → system
        return "system"

    # -- File read tools --
    if name in ("Read", "Glob", "Grep") or lname in {
        "read_file", "grep_search", "glob_search", "list_directory",
    }:
        path = (
            tool_input.get("file_path")
            or tool_input.get("path")
            or tool_input.get("pattern")
            or ""
        )
        if "/literature/" in path:
            return "literature"
        if any(ext in path for ext in (".tex", ".bib")) or "/latex/" in path:
            return "paper"
        if "/figures/" in path or "/plotting/" in path:
            return "plotting"
        if "/submissions/" in path:
            return "submission"
        return "system"

    # -- File write tools --
    if name in ("Write", "Edit") or lname in {
        "write_file", "edit_file", "update_file", "replace_in_file",
    }:
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        if "/literature/" in path:
            return "literature"
        if any(ext in path for ext in (".tex", ".bib")) or "/latex/" in path:
            return "paper"
        if "/figures/" in path or "/plotting/" in path:
            return "plotting"
        if "/submissions/" in path:
            return "submission"
        return "system"

    # -- Web tools --
    if name in ("WebFetch", "WebSearch") or lname in {
        "web_fetch", "web_search", "fetch_url", "google_search",
    }:
        url = tool_input.get("url", "")
        query = tool_input.get("query", "")
        prompt_text = tool_input.get("prompt", "")
        combined = f"{url} {query} {prompt_text}".lower()
        _academic = (
            "arxiv.org", "ar5iv.labs.", "semanticscholar.org",
            "openalex.org", "openreview.net", "scholar.google",
            "doi.org/10.", "aclanthology.org",
            "proceedings.neurips", "proceedings.mlr.press",
        )
        if any(sig in combined for sig in _academic):
            return "literature"
        return "web"

    # -- Task/Agent tool (inspect description for literature) --
    if name in ("Task", "Agent"):
        desc = (tool_input.get("description") or "").lower()
        prompt = (tool_input.get("prompt") or "").lower()
        combined = f"{desc} {prompt}"
        _lit_task_kw = (
            "literature", "search-papers", "citation", "bibtex",
            "semantic scholar", "find paper", "missing citation",
            "novelty", "related work",
        )
        if any(kw in combined for kw in _lit_task_kw):
            return "literature"
        # Word-boundary check for "search paper" to avoid matching "research paper"
        if re.search(r"\bsearch\s+paper", combined):
            return "literature"
        return "system"

    if name in ("TodoWrite", "TaskCreate", "TaskUpdate",
                 "TaskGet", "TaskList", "TaskOutput", "TaskStop"):
        return "system"

    return "system"


def classify_step(step: dict) -> str:
    """Classify an ATIF step into one of 8 event types.

    Examines all tool calls and picks the most significant type by priority.
    Steps with no tool calls are classified as ``thinking``.
    """
    source = step.get("source", "agent")
    tool_calls = step.get("tool_calls") if isinstance(step.get("tool_calls"), list) else []

    if not tool_calls:
        # No tools — it is a thinking/message step.
        if source in ("system", "user"):
            return "system"
        return "thinking"

    best_type = "system"
    best_priority = -1
    for tc in tool_calls:
        fname = tc.get("function_name") or tc.get("name") or ""
        fargs = tc.get("arguments") or tc.get("input") or {}
        if not isinstance(fargs, dict):
            fargs = {}
        t = _classify_tool_call(fname, fargs)
        p = _TYPE_PRIORITY.get(t, 0)
        if p > best_priority:
            best_priority = p
            best_type = t

    return best_type


# ---------------------------------------------------------------------------
# Step summarization
# ---------------------------------------------------------------------------

def summarize_step(step: dict) -> str:
    """Extract a short human-readable summary from an ATIF step."""
    source = step.get("source", "agent")
    tool_calls = step.get("tool_calls") if isinstance(step.get("tool_calls"), list) else []

    # System / user messages
    if source in ("system", "user"):
        msg = step.get("message", "")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()[:120]
        return f"{source} message"

    # Agent with tool calls — summarize the first tool
    if tool_calls:
        parts = []
        for tc in tool_calls[:3]:  # first 3 tools
            fname = tc.get("function_name") or tc.get("name") or "?"
            fargs = tc.get("arguments") or tc.get("input") or {}
            if not isinstance(fargs, dict):
                fargs = {}
            parts.append(_summarize_single_tool(fname, fargs))
        summary = "; ".join(parts)
        if len(tool_calls) > 3:
            summary += f" (+{len(tool_calls) - 3} more)"
        return summary

    # Agent text / thinking
    msg = step.get("message", "")
    if isinstance(msg, str) and msg.strip():
        first_line = msg.strip().split("\n")[0][:120]
        return first_line

    reasoning = step.get("reasoning_content", "")
    if isinstance(reasoning, str) and reasoning.strip() and reasoning.strip().lower() not in ("null", "none"):
        return f"Thinking: {reasoning.strip()[:100]}"

    return "Agent turn"


def _summarize_single_tool(name: str, tool_input: dict) -> str:
    """Summarize a single tool call compactly."""
    lname = (name or "").lower()

    if name == "Bash" or lname in {"run_shell_command", "run_command", "execute_command", "bash"}:
        desc = tool_input.get("description", "")
        if desc:
            return f"Bash: {desc[:80]}"
        cmd = (
            tool_input.get("command")
            or tool_input.get("cmd")
            or tool_input.get("bash_command")
            or ""
        )
        first_line = cmd.split("\n")[0][:80]
        return f"Bash: {first_line}"

    if name == "Read" or lname == "read_file":
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        return f"Read: {os.path.basename(path) if path else '?'}"

    if name == "Write" or lname == "write_file":
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        return f"Write: {os.path.basename(path) if path else '?'}"

    if name == "Edit" or lname in {"edit_file", "update_file", "replace_in_file"}:
        path = tool_input.get("file_path") or tool_input.get("path") or ""
        return f"Edit: {os.path.basename(path) if path else '?'}"

    if name == "Glob" or lname == "glob_search":
        return f"Glob: {tool_input.get('pattern', '')[:60]}"

    if name == "Grep" or lname == "grep_search":
        return f"Grep: {tool_input.get('pattern', '')[:60]}"

    if name == "WebFetch" or lname in {"web_fetch", "fetch_url"}:
        return f"WebFetch: {tool_input.get('url', '')[:60]}"

    if name == "WebSearch" or lname in {"web_search", "google_search"}:
        return f"WebSearch: {tool_input.get('query', '')[:60]}"

    if name == "Skill":
        return f"Skill: {tool_input.get('skill', '')}"

    if name == "Task":
        desc = tool_input.get("description", "")
        return f"Subagent: {desc[:60]}" if desc else "Subagent"

    return name


# ---------------------------------------------------------------------------
# Token extraction (mirrors parse_trajectory.py logic)
# ---------------------------------------------------------------------------

def _extract_step_tokens(step: dict) -> dict:
    """Extract token counts from an ATIF step's metrics."""
    metrics = step.get("metrics", {})
    if not isinstance(metrics, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}

    extra = metrics.get("extra", {}) if isinstance(metrics.get("extra"), dict) else {}

    # Cache tokens
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
    # Uncached input tokens
    uncached_input = metrics.get("input_tokens")
    if uncached_input is None:
        uncached_input = prompt_tokens
        if cache_read and prompt_tokens >= cache_read:
            uncached_input = prompt_tokens - cache_read

    completion_tokens = metrics.get("completion_tokens", 0) or metrics.get("output_tokens", 0)

    return {
        "prompt_tokens": uncached_input or 0,
        "completion_tokens": completion_tokens or 0,
        "cache_read": cache_read or 0,
        "cache_creation": cache_creation or 0,
    }


# ---------------------------------------------------------------------------
# Index generation
# ---------------------------------------------------------------------------

def generate_index(trajectory_path: str) -> dict:
    """Generate a lightweight index for an ATIF trajectory file.

    Strategy:
    1. Read raw bytes and find step boundaries using a fast brace-counting
       scanner (no JSON parsing needed for offsets).
    2. Parse each step individually from its byte span to extract metadata.
    3. Extract top-level fields (agent, session_id, final_metrics) from the
       preamble before the steps array.
    """
    try:
        with open(trajectory_path, "rb") as f:
            raw_bytes = f.read()
    except OSError as exc:
        return {"error": str(exc), "total_steps": 0, "steps": []}

    # --- Find step byte boundaries with fast brace scanner ---
    step_spans = _find_step_byte_spans(raw_bytes)

    # --- Extract top-level metadata ---
    # Parse just the preamble (everything before the steps array) for metadata.
    agent_info, session_id, final_metrics = _extract_metadata(raw_bytes, step_spans)

    # --- Build index entries by parsing each step from its byte span ---
    index_steps: List[dict] = []
    for i, (byte_offset, byte_length) in enumerate(step_spans):
        try:
            step_bytes = raw_bytes[byte_offset:byte_offset + byte_length]
            step = json.loads(step_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            index_steps.append({
                "step_id": i,
                "source": "unknown",
                "timestamp": None,
                "event_type": "system",
                "summary": "(parse error)",
                "tool_names": [],
                "has_reasoning": False,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cache_read": 0,
                "cache_creation": 0,
                "byte_offset": byte_offset,
                "byte_length": byte_length,
            })
            continue

        source = step.get("source", "agent")
        timestamp = step.get("timestamp")
        event_type = classify_step(step)
        summary = summarize_step(step)

        # Tool names
        tool_calls = step.get("tool_calls") if isinstance(step.get("tool_calls"), list) else []
        tool_names = []
        for tc in tool_calls:
            fn = tc.get("function_name") or tc.get("name") or ""
            if fn and fn not in tool_names:
                tool_names.append(fn)

        # Reasoning flag
        reasoning = step.get("reasoning_content", "")
        has_reasoning = bool(
            isinstance(reasoning, str)
            and reasoning.strip()
            and reasoning.strip().lower() not in ("null", "none")
        )

        # Tokens
        tokens = _extract_step_tokens(step)

        index_steps.append({
            "step_id": i,
            "source": source,
            "timestamp": timestamp,
            "event_type": event_type,
            "summary": summary,
            "tool_names": tool_names,
            "has_reasoning": has_reasoning,
            "prompt_tokens": tokens["prompt_tokens"],
            "completion_tokens": tokens["completion_tokens"],
            "cache_read": tokens.get("cache_read", 0),
            "cache_creation": tokens.get("cache_creation", 0),
            "byte_offset": byte_offset,
            "byte_length": byte_length,
        })

    return {
        "total_steps": len(step_spans),
        "agent": {
            "name": agent_info.get("name") if agent_info else None,
            "model_name": agent_info.get("model_name") if agent_info else None,
        },
        "session_id": session_id,
        "final_metrics": final_metrics,
        "steps": index_steps,
    }


def _find_step_byte_spans(raw_bytes: bytes) -> List[Tuple[int, int]]:
    """Find (byte_offset, byte_length) for each step in the steps array.

    Uses a fast brace-counting scanner on the raw bytes.  Handles nested
    braces, JSON string escapes (including ``\\\"``) so it correctly finds
    top-level object boundaries within the array.  This runs in a single
    O(n) pass over the relevant portion of the file.
    """
    # Locate the "steps" array opening bracket.
    # Search for b'"steps"' followed by ':' then '['.
    marker = b'"steps"'
    idx = raw_bytes.find(marker)
    if idx < 0:
        return []

    # Skip past "steps" : [
    pos = idx + len(marker)
    length = len(raw_bytes)
    # Skip whitespace and colon
    while pos < length and raw_bytes[pos:pos + 1] in (b' ', b'\t', b'\n', b'\r', b':'):
        pos += 1
    if pos >= length or raw_bytes[pos:pos + 1] != b'[':
        return []
    pos += 1  # skip '['

    spans: List[Tuple[int, int]] = []

    # Scan through the array looking for top-level '{' ... '}' objects.
    while pos < length:
        # Skip whitespace and commas.
        b = raw_bytes[pos:pos + 1]
        if b in (b' ', b'\t', b'\n', b'\r', b','):
            pos += 1
            continue
        if b == b']':
            break  # end of steps array
        if b != b'{':
            pos += 1
            continue

        # Found start of an object.
        obj_start = pos
        depth = 0
        in_string = False
        escape_next = False

        while pos < length:
            ch = raw_bytes[pos]
            if escape_next:
                escape_next = False
                pos += 1
                continue
            if in_string:
                if ch == 0x5C:  # backslash
                    escape_next = True
                elif ch == 0x22:  # double quote
                    in_string = False
                pos += 1
                continue
            # Not in string
            if ch == 0x22:  # "
                in_string = True
            elif ch == 0x7B:  # {
                depth += 1
            elif ch == 0x7D:  # }
                depth -= 1
                if depth == 0:
                    pos += 1
                    spans.append((obj_start, pos - obj_start))
                    break
            pos += 1

    return spans


def _extract_metadata(
    raw_bytes: bytes,
    step_spans: List[Tuple[int, int]],
) -> Tuple[Optional[dict], Optional[str], Optional[dict]]:
    """Extract agent, session_id, and final_metrics from the trajectory.

    Parses only the portion of the file before the first step (for agent/
    session_id) and after the last step (for final_metrics), avoiding
    full-file JSON parsing.
    """
    agent_info: Optional[dict] = None
    session_id: Optional[str] = None
    final_metrics: Optional[dict] = None

    if not raw_bytes:
        return agent_info, session_id, final_metrics

    # Try to extract from the preamble (before steps array, typically < 1KB).
    # Find "steps" marker to bound the preamble.
    steps_marker = raw_bytes.find(b'"steps"')
    preamble_end = steps_marker if steps_marker > 0 else min(4096, len(raw_bytes))

    # Build a valid JSON object from the preamble by closing it.
    preamble = raw_bytes[:preamble_end]
    # Quick extraction using regex on the preamble bytes.
    try:
        # Try parsing as a truncated JSON: add closing brackets.
        # Remove trailing comma if present.
        preamble_str = preamble.decode("utf-8", errors="replace").rstrip().rstrip(",")
        # Close the object.
        test_json = preamble_str + "}"
        try:
            meta = json.loads(test_json)
            agent_info = meta.get("agent") if isinstance(meta.get("agent"), dict) else None
            session_id = meta.get("session_id")
        except json.JSONDecodeError:
            pass
    except Exception:
        pass

    # If preamble parsing failed, try a minimal regex approach.
    if session_id is None:
        import re as _re
        m = _re.search(rb'"session_id"\s*:\s*"([^"]*)"', raw_bytes[:preamble_end + 200])
        if m:
            session_id = m.group(1).decode("utf-8", errors="replace")

    if agent_info is None:
        # Try to find agent block.
        agent_marker = raw_bytes.find(b'"agent"', 0, preamble_end + 200)
        if agent_marker >= 0:
            # Find the opening brace of the agent object.
            brace_start = raw_bytes.find(b'{', agent_marker + 7)
            if brace_start >= 0 and brace_start < preamble_end + 500:
                # Find matching close brace (agent object is small).
                depth = 0
                pos = brace_start
                while pos < min(len(raw_bytes), brace_start + 500):
                    ch = raw_bytes[pos]
                    if ch == 0x7B:
                        depth += 1
                    elif ch == 0x7D:
                        depth -= 1
                        if depth == 0:
                            try:
                                agent_info = json.loads(raw_bytes[brace_start:pos + 1])
                            except json.JSONDecodeError:
                                pass
                            break
                    pos += 1

    # Extract final_metrics from the tail of the file (after all steps).
    if step_spans:
        last_end = step_spans[-1][0] + step_spans[-1][1]
        tail = raw_bytes[last_end:]
        fm_marker = tail.find(b'"final_metrics"')
        if fm_marker >= 0:
            # Find the object after the key.
            colon = tail.find(b':', fm_marker + 15)
            if colon >= 0:
                brace_start = tail.find(b'{', colon)
                if brace_start >= 0:
                    depth = 0
                    pos = brace_start
                    while pos < len(tail):
                        ch = tail[pos]
                        if ch == 0x7B:
                            depth += 1
                        elif ch == 0x7D:
                            depth -= 1
                            if depth == 0:
                                try:
                                    final_metrics = json.loads(tail[brace_start:pos + 1])
                                except json.JSONDecodeError:
                                    pass
                                break
                        pos += 1

    return agent_info, session_id, final_metrics


# ---------------------------------------------------------------------------
# Single-step random access
# ---------------------------------------------------------------------------

def read_single_step(trajectory_path: str, byte_offset: int, byte_length: int) -> Optional[dict]:
    """Read and parse a single ATIF step using byte offset seeking.

    Returns the parsed step dict, or ``None`` on failure.
    """
    if byte_offset <= 0 and byte_length <= 0:
        return None

    try:
        with open(trajectory_path, "rb") as f:
            f.seek(byte_offset)
            chunk = f.read(byte_length)
        return json.loads(chunk.decode("utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# Index caching helpers
# ---------------------------------------------------------------------------

def get_index_cache_path(trajectory_path: str) -> str:
    """Return the path where the index JSON will be cached on disk."""
    directory = os.path.dirname(trajectory_path)
    return os.path.join(directory, "trajectory_index.json")


def load_cached_index(trajectory_path: str) -> Optional[dict]:
    """Load the cached index from disk if it exists and is fresh.

    The index is considered fresh if it is newer than the trajectory file.
    """
    index_path = get_index_cache_path(trajectory_path)
    if not os.path.exists(index_path):
        return None

    try:
        traj_mtime = os.path.getmtime(trajectory_path)
        idx_mtime = os.path.getmtime(index_path)
        if idx_mtime < traj_mtime:
            # Index is stale.
            return None
    except OSError:
        return None

    try:
        with open(index_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_index_to_disk(trajectory_path: str, index: dict) -> bool:
    """Save the index to disk alongside the trajectory file.

    Returns True on success.
    """
    index_path = get_index_cache_path(trajectory_path)
    try:
        with open(index_path, "w") as f:
            json.dump(index, f, separators=(",", ":"))
        return True
    except OSError:
        return False


def get_or_generate_index(trajectory_path: str) -> dict:
    """Load cached index or generate and cache a fresh one."""
    cached = load_cached_index(trajectory_path)
    if cached is not None:
        return cached

    index = generate_index(trajectory_path)
    if index.get("total_steps", 0) > 0:
        save_index_to_disk(trajectory_path, index)
    return index
