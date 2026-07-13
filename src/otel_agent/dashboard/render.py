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
    """Safely parse a JSON body string; return None on failure."""
    if not body:
        return None
    try:
        return json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None


def detect_format(body: str, format_tag: str | None = None) -> str:
    """Detect the LLM format of a body string.

    Returns one of: ``"openai"``, ``"anthropic"``, ``"streaming"``, ``"unknown"``.
    Uses *format_tag* from storage when available; otherwise applies the same
    heuristic as the JS ``detectFormat`` function.
    """
    if format_tag:
        tag = format_tag.lower().strip()
        if "stream" in tag:
            return "streaming"
        if "anthropic" in tag or "claude" in tag:
            return "anthropic"
        if "openai" in tag or "gpt" in tag:
            return "openai"

    parsed = _parse_body(body)
    if not parsed or not isinstance(parsed, dict):
        return "unknown"

    # Streaming preview
    if parsed.get("streamed") and parsed.get("preview"):
        return "streaming"
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
    """Parse concatenated JSON chunks (mirrors JS parseStreamingChunks)."""
    chunks: list[dict[str, Any]] = []
    depth = 0
    start = -1
    for i, ch in enumerate(preview_str):
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
