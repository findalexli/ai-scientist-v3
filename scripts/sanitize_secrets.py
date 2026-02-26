#!/usr/bin/env python3
"""Sanitize secrets from text, JSON, and files before pushing to external services.

Reusable module + CLI. Loads exact secret values from .env and applies regex
patterns for known credential formats (API keys, tokens, OAuth URLs, etc.).

Usage:
    python3 scripts/sanitize_secrets.py --input trajectory.json --output sanitized.json
    python3 scripts/sanitize_secrets.py --input trajectory.json --in-place
    python3 scripts/sanitize_secrets.py --check trajectory.json   # exit 1 if secrets found
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, List, Optional


REDACTION = "[REDACTED]"

# ---------------------------------------------------------------------------
# Regex patterns for known credential formats
# ---------------------------------------------------------------------------

SECRET_TOKEN_PATTERNS = [
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}\b"),                  # Anthropic
    re.compile(r"\bsk-(?:live|proj|test)?[A-Za-z0-9_\-]{16,}\b"),   # OpenAI-style
    re.compile(r"\bsk-kimi-[A-Za-z0-9_\-]{8,}\b"),                  # Kimi
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"),                     # Google/Gemini
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),                  # GitHub PAT
    re.compile(r"\bglpat-[A-Za-z0-9._\-]{20,}\b"),                  # GitLab PAT
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),                         # HuggingFace
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                            # AWS access key
    re.compile(r"\bKGAT_[A-Za-z0-9]{20,}\b"),                       # Kaggle
]

ENV_SECRET_PATTERN = re.compile(
    r'(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|ACCESS[_-]?KEY|SECRET|TOKEN|PRIVATE[_-]?KEY)[A-Z0-9_]*)(\s*=\s*)("|\')?([^\s"\'`;,\}]+)(?(3)\3)'
)
JSON_SECRET_PATTERN = re.compile(
    r'(?i)("?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|authorization|auth[_-]?token)"?\s*[:=]\s*)("|\')([^"\']+)\2'
)
JSON_SECRET_UNQUOTED_PATTERN = re.compile(
    r'(?i)("?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password|authorization|auth[_-]?token)"?\s*[:=]\s*)(?!["\'])([^\n,}]+)'
)
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]{12,}")
OAUTH_URL_PATTERN = re.compile(r"oauth2:[^@\s]{8,}@")


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

def load_env_secrets(env_path: Optional[str] = None) -> List[str]:
    """Load exact secret values from a .env file. Returns longest-first."""
    if env_path is None:
        env_path = str(Path(__file__).resolve().parent.parent / ".env")

    if not os.path.exists(env_path):
        return []

    secrets: List[str] = []
    try:
        with open(env_path, "r", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                name, value = line.split("=", 1)
                name = name.strip().upper()
                value = value.strip()
                if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                if not any(tok in name for tok in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                    continue
                if value and len(value) >= 8:
                    secrets.append(value)
    except OSError:
        return []

    return sorted(set(secrets), key=len, reverse=True)


# ---------------------------------------------------------------------------
# SecretSanitizer
# ---------------------------------------------------------------------------

class SecretSanitizer:
    """Reusable secret sanitizer. Loads .env values + applies regex patterns."""

    def __init__(
        self,
        env_path: Optional[str] = None,
        extra_patterns: Optional[List[re.Pattern]] = None,
        extra_exact: Optional[List[str]] = None,
    ):
        self.exact_secrets = load_env_secrets(env_path)
        if extra_exact:
            combined = set(self.exact_secrets) | set(extra_exact)
            self.exact_secrets = sorted(combined, key=len, reverse=True)

        self.token_patterns = list(SECRET_TOKEN_PATTERNS)
        if extra_patterns:
            self.token_patterns.extend(extra_patterns)

    def sanitize_text(self, text: str) -> str:
        """Strip all recognized secrets from a string."""
        if not text:
            return text

        masked = text

        # Exact value replacement (longest first).
        for secret in self.exact_secrets:
            if secret and secret in masked:
                masked = masked.replace(secret, REDACTION)

        # OAuth URLs: oauth2:TOKEN@host
        masked = OAUTH_URL_PATTERN.sub(f"oauth2:{REDACTION}@", masked)

        # Bearer tokens.
        masked = BEARER_PATTERN.sub("Bearer [REDACTED]", masked)

        # KEY=value assignments.
        masked = ENV_SECRET_PATTERN.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{m.group(3) or ''}{REDACTION}{m.group(3) or ''}",
            masked,
        )
        # JSON-style "key": "value" patterns.
        masked = JSON_SECRET_PATTERN.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{REDACTION}{m.group(2)}",
            masked,
        )
        masked = JSON_SECRET_UNQUOTED_PATTERN.sub(
            lambda m: f"{m.group(1)}{REDACTION}",
            masked,
        )

        # Known token formats.
        for pat in self.token_patterns:
            masked = pat.sub(REDACTION, masked)

        return masked

    def sanitize_json(self, data: Any) -> Any:
        """Recursively sanitize a JSON-serializable structure."""
        if isinstance(data, str):
            return self.sanitize_text(data)
        if isinstance(data, dict):
            return {k: self.sanitize_json(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self.sanitize_json(v) for v in data]
        return data

    def sanitize_file(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        in_place: bool = False,
    ) -> str:
        """Read a file, sanitize its contents, write to output_path or in-place.

        Returns the sanitized content.
        """
        with open(input_path, "r", errors="replace") as f:
            raw = f.read()

        # Try JSON first for structured sanitization.
        try:
            data = json.loads(raw)
            sanitized_data = self.sanitize_json(data)
            sanitized = json.dumps(sanitized_data, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, ValueError):
            sanitized = self.sanitize_text(raw)

        dest = output_path if output_path else (input_path if in_place else None)
        if dest:
            with open(dest, "w") as f:
                f.write(sanitized)

        return sanitized

    def check_file(self, input_path: str) -> List[str]:
        """Check a file for secrets without modifying it. Returns list of findings."""
        with open(input_path, "r", errors="replace") as f:
            raw = f.read()

        findings = []

        for secret in self.exact_secrets:
            if secret and secret in raw:
                # Show a safe prefix for identification.
                safe_prefix = secret[:4] + "..." if len(secret) > 4 else "***"
                findings.append(f"Exact .env value found: {safe_prefix}")

        for pat in self.token_patterns:
            matches = pat.findall(raw)
            if matches:
                for m in matches:
                    safe = m[:6] + "..." if len(m) > 6 else "***"
                    findings.append(f"Token pattern {pat.pattern[:30]}: {safe}")

        if OAUTH_URL_PATTERN.search(raw):
            findings.append("OAuth URL with embedded token found")

        if BEARER_PATTERN.search(raw):
            findings.append("Bearer token found")

        return findings


# ---------------------------------------------------------------------------
# Default singleton (lazy init, same pattern as parse_trajectory.py)
# ---------------------------------------------------------------------------

_default_sanitizer: Optional[SecretSanitizer] = None


def get_default_sanitizer() -> SecretSanitizer:
    """Get or create the default sanitizer (loads .env from repo root)."""
    global _default_sanitizer
    if _default_sanitizer is None:
        _default_sanitizer = SecretSanitizer()
    return _default_sanitizer


def sanitize_text(text: str) -> str:
    """Convenience: sanitize text using the default sanitizer."""
    return get_default_sanitizer().sanitize_text(text)


def sanitize_json(data: Any) -> Any:
    """Convenience: sanitize JSON using the default sanitizer."""
    return get_default_sanitizer().sanitize_json(data)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sanitize secrets from files before pushing to external services"
    )
    parser.add_argument("--input", required=True, help="Input file path")
    parser.add_argument("--output", default=None, help="Output file path (default: stdout)")
    parser.add_argument("--in-place", action="store_true", help="Modify input file in place")
    parser.add_argument("--check", action="store_true", help="Check for secrets without modifying (exit 1 if found)")
    parser.add_argument("--env", default=None, help="Path to .env file (default: auto-detect)")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    sanitizer = SecretSanitizer(env_path=args.env)

    if args.check:
        findings = sanitizer.check_file(args.input)
        if findings:
            print(f"Found {len(findings)} secret(s) in {args.input}:")
            for f in findings:
                print(f"  - {f}")
            sys.exit(1)
        else:
            print(f"No secrets found in {args.input}")
            sys.exit(0)

    if args.in_place:
        sanitizer.sanitize_file(args.input, in_place=True)
        print(f"Sanitized {args.input} in place", file=sys.stderr)
    elif args.output:
        sanitizer.sanitize_file(args.input, output_path=args.output)
        print(f"Sanitized {args.input} -> {args.output}", file=sys.stderr)
    else:
        result = sanitizer.sanitize_file(args.input)
        sys.stdout.write(result)


if __name__ == "__main__":
    main()
