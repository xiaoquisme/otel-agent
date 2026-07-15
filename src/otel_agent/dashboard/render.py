"""Shared utilities for LLM body format detection and chunk parsing.

These utilities are used by message_parser.py for structured extraction.
HTML rendering functions have been removed — the frontend now handles
rendering via @assistant-ui/react.
"""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _parse_body(body: str) -> Any:
    """Safely parse a JSON body string; return None on failure.

    When the body is truncated (e.g. by the 500 KB storage limit) and
    therefore invalid JSON, attempt a best-effort recovery: close any
    open strings, arrays, and objects so that ``json.loads`` can parse
    the result.  This lets us extract partial ``messages`` arrays from
    large request bodies that were cut off mid-string.
    """
    if not body:
        return None
    try:
        return json.loads(body)
    except (json.JSONDecodeError, TypeError):
        pass

    # --- Best-effort truncation recovery ---
    # Walk the string tracking depth and string state so we can append
    # the minimal closing characters needed for valid JSON.
    in_string = False
    escape_next = False
    stack: list[str] = []  # tracks opening brackets/braces in order

    for ch in body:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()

    # Build a repair suffix
    suffix = ""
    if in_string:
        suffix += '"'  # close unterminated string
    # Close open containers inside-out (matching the nesting order)
    for opener in reversed(stack):
        suffix += "}" if opener == "{" else "]"

    if suffix:
        try:
            return json.loads(body + suffix)
        except (json.JSONDecodeError, TypeError):
            pass

    return None


def detect_format(body: str, format_tag: str | None = None) -> str:
    """Detect the LLM format of a body string.

    Returns one of: ``"openai"``, ``"anthropic"``, ``"streaming"``, ``"unknown"``.
    Body content is checked first — streaming preview is detected regardless of
    *format_tag* because the tag stores the client API format (e.g. "openai"),
    not whether the response was streamed.
    """
    parsed = _parse_body(body)

    # Streaming preview — body content takes priority over format_tag
    if parsed and isinstance(parsed, dict) and parsed.get("streamed") and parsed.get("preview"):
        return "streaming"

    if format_tag:
        tag = format_tag.lower().strip()
        if "stream" in tag:
            return "streaming"
        if "anthropic" in tag or "claude" in tag:
            return "anthropic"
        if "openai" in tag or "gpt" in tag:
            return "openai"

    if not parsed or not isinstance(parsed, dict):
        return "unknown"
    # OpenAI response
    if isinstance(parsed.get("choices"), list):
        return "openai"
    # Anthropic response
    if (
        isinstance(parsed.get("content"), list)
        and parsed.get("type") == "message"
    ):
        return "anthropic"
    # OpenAI request (has messages + model but NO max_tokens)
    if (
        isinstance(parsed.get("messages"), list)
        and parsed.get("model")
        and parsed.get("max_tokens") is None
    ):
        return "openai"
    # Anthropic request (has messages + max_tokens)
    if isinstance(parsed.get("messages"), list) and parsed.get("max_tokens") is not None:
        return "anthropic"

    return "unknown"


# ---------------------------------------------------------------------------
# Internal: streaming chunk parser
# ---------------------------------------------------------------------------

def _parse_streaming_chunks(preview_str: str) -> list[dict[str, Any]]:
    """Parse concatenated JSON chunks (mirrors JS parseStreamingChunks).

    Tracks whether we are inside a JSON string so that ``{`` / ``}``
    characters inside string values do not confuse the depth counter.
    """
    chunks: list[dict[str, Any]] = []
    depth = 0
    start = -1
    in_string = False
    escape_next = False
    for i, ch in enumerate(preview_str):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        # Outside a string — normal depth tracking
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    chunk = json.loads(preview_str[start : i + 1])
                    if isinstance(chunk, dict):
                        chunks.append(chunk)
                except json.JSONDecodeError:
                    pass
                start = -1

    # Handle incomplete trailing chunk
    if depth > 0 and start >= 0:
        tail = preview_str[start:]
        try:
            chunk = json.loads(tail)
            if isinstance(chunk, dict):
                chunks.append(chunk)
        except json.JSONDecodeError:
            for close in range(1, depth + 1):
                try:
                    chunk = json.loads(tail + "}" * close)
                    if isinstance(chunk, dict):
                        chunks.append(chunk)
                    break
                except json.JSONDecodeError:
                    pass
    return chunks
