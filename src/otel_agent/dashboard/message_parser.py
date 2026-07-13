"""Structured message parser — extracts message arrays from raw LLM request/response JSON.

Returns parsed message dicts suitable for frontend rendering via @assistant-ui/react,
instead of pre-rendered HTML strings.
"""

from __future__ import annotations

import json
from typing import Any

from otel_agent.dashboard.render import (
    _parse_body,
    _parse_streaming_chunks,
    detect_format,
)


def _extract_openai_request_messages(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract chat messages from an OpenAI-style request body."""
    messages = parsed.get("messages")
    if not messages or not isinstance(messages, list):
        return []

    result: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "unknown")
        msg: dict[str, Any] = {"role": role}

        if role == "assistant" and m.get("tool_calls"):
            content = m.get("content", "") or ""
            tool_calls = []
            for tc in m["tool_calls"]:
                fn = tc.get("function", tc)
                tool_calls.append({
                    "name": fn.get("name", "tool"),
                    "arguments": fn.get("arguments", ""),
                })
            msg["content"] = content
            msg["tool_calls"] = tool_calls
        elif role == "tool":
            msg["content"] = m.get("content", "")
        else:
            msg["content"] = m.get("content", "")

        result.append(msg)
    return result


def _extract_anthropic_request_messages(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract chat messages from an Anthropic-style request body."""
    messages = parsed.get("messages")
    if not messages or not isinstance(messages, list):
        return []

    result: list[dict[str, Any]] = []

    # System message
    system = parsed.get("system")
    if system:
        if isinstance(system, str):
            sys_content = system
        elif isinstance(system, list):
            sys_content = "\n".join(
                b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text"
            )
        else:
            sys_content = str(system)
        if sys_content:
            result.append({"role": "system", "content": sys_content})

    for m in messages:
        role = m.get("role", "unknown")
        content_raw = m.get("content", "")
        if isinstance(content_raw, str):
            content = content_raw
        elif isinstance(content_raw, list):
            content = "\n".join(
                b.get("text", "") for b in content_raw if isinstance(b, dict) and b.get("type") == "text"
            )
        else:
            content = str(content_raw) if content_raw else ""
        result.append({"role": role, "content": content})
    return result


def _extract_streaming_messages(parsed: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract messages and metadata from a streaming preview object."""
    preview = parsed.get("preview")
    if not preview:
        return [], {}

    chunks = _parse_streaming_chunks(preview)
    if not chunks:
        return [], {}

    content = ""
    reasoning_content = ""
    model = ""
    finish_reason = ""
    tool_calls: dict[int, dict[str, str]] = {}
    usage: dict[str, Any] = {}

    for chunk in chunks:
        if chunk.get("model"):
            model = chunk["model"]
        # Extract usage from chunks
        chunk_usage = chunk.get("usage")
        if isinstance(chunk_usage, dict):
            usage = {
                "input_tokens": chunk_usage.get("input_tokens") or chunk_usage.get("prompt_tokens"),
                "output_tokens": chunk_usage.get("output_tokens") or chunk_usage.get("completion_tokens"),
                "total_tokens": chunk_usage.get("total_tokens"),
            }
        choices = chunk.get("choices")
        if not choices or not isinstance(choices, list):
            continue
        choice = choices[0]
        if choice.get("finish_reason"):
            finish_reason = choice["finish_reason"]
        delta = choice.get("delta", {})
        if delta.get("content"):
            content += delta["content"]
        if delta.get("reasoning_content"):
            reasoning_content += delta["reasoning_content"]
        if delta.get("tool_calls"):
            for tc in delta["tool_calls"]:
                idx = tc.get("index", 0)
                if idx not in tool_calls:
                    tool_calls[idx] = {"name": "", "arguments": ""}
                if tc.get("function"):
                    if tc["function"].get("name"):
                        tool_calls[idx]["name"] = tc["function"]["name"]
                    if tc["function"].get("arguments"):
                        tool_calls[idx]["arguments"] += tc["function"]["arguments"]

    messages: list[dict[str, Any]] = []
    if content or reasoning_content or tool_calls:
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        tc_list = list(tool_calls.values())
        if tc_list:
            msg["tool_calls"] = tc_list
        messages.append(msg)

    metadata: dict[str, Any] = {
        "model": model,
        "finish_reason": finish_reason or "streaming",
        "usage": usage if usage else None,
    }
    return messages, metadata


def _extract_openai_response_messages(parsed: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract messages and metadata from an OpenAI-style response body."""
    choices = parsed.get("choices")
    if not choices or not isinstance(choices, list) or len(choices) == 0:
        return [], {}

    choice = choices[0]
    msg = choice.get("message") or choice.get("delta") or {}

    messages: list[dict[str, Any]] = []
    assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.get("content", "") or ""}

    tool_calls = msg.get("tool_calls")
    if tool_calls:
        assistant_msg["tool_calls"] = [
            {"name": tc.get("function", {}).get("name", "tool"), "arguments": tc.get("function", {}).get("arguments", "")}
            for tc in tool_calls
        ]

    messages.append(assistant_msg)

    usage = parsed.get("usage")
    metadata: dict[str, Any] = {
        "model": parsed.get("model", ""),
        "finish_reason": choice.get("finish_reason", ""),
        "usage": usage if isinstance(usage, dict) else None,
    }
    return messages, metadata


def _extract_anthropic_response_messages(parsed: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract messages and metadata from an Anthropic-style response body."""
    content = parsed.get("content")
    if not content or not isinstance(content, list):
        return [], {}

    text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    combined_text = "\n\n".join(text_parts)

    # Extract tool_use blocks
    tool_calls = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            tool_calls.append({"name": b.get("name", "tool"), "arguments": json.dumps(b.get("input", {}))})

    messages: list[dict[str, Any]] = []
    assistant_msg: dict[str, Any] = {"role": "assistant", "content": combined_text}
    if tool_calls:
        assistant_msg["tool_calls"] = tool_calls
    messages.append(assistant_msg)

    usage = parsed.get("usage")
    metadata: dict[str, Any] = {
        "model": parsed.get("model", ""),
        "finish_reason": parsed.get("stop_reason", ""),
        "usage": usage if isinstance(usage, dict) else None,
    }
    return messages, metadata


def parse_messages(
    request_body: str | None,
    response_body: str | None,
    format_tag: str | None = None,
) -> dict[str, Any]:
    """Parse raw LLM request/response bodies into structured messages + metadata.

    Returns::

        {
            "messages": [ {"role": ..., "content": ..., "tool_calls": ...}, ... ],
            "metadata": { "model": ..., "finish_reason": ..., "usage": ..., "format": ... }
        }

    The ``messages`` array contains request messages followed by the response
    assistant message (if present). The ``metadata`` object carries response-level
    information extracted from the response body.
    """
    req_fmt = detect_format(request_body or "", format_tag)
    resp_fmt = detect_format(response_body or "", format_tag)
    fmt = resp_fmt if resp_fmt != "unknown" else req_fmt

    messages: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {"model": None, "finish_reason": None, "usage": None, "format": fmt}

    # Parse request messages
    if request_body:
        req_parsed = _parse_body(request_body)
        if req_parsed and isinstance(req_parsed, dict):
            if req_fmt == "openai":
                messages.extend(_extract_openai_request_messages(req_parsed))
            elif req_fmt == "anthropic":
                messages.extend(_extract_anthropic_request_messages(req_parsed))

    # Parse response messages
    if response_body:
        resp_parsed = _parse_body(response_body)
        if resp_parsed and isinstance(resp_parsed, dict):
            if resp_fmt == "streaming":
                resp_msgs, resp_meta = _extract_streaming_messages(resp_parsed)
            elif resp_fmt == "openai":
                resp_msgs, resp_meta = _extract_openai_response_messages(resp_parsed)
            elif resp_fmt == "anthropic":
                resp_msgs, resp_meta = _extract_anthropic_response_messages(resp_parsed)
            else:
                resp_msgs, resp_meta = [], {}

            messages.extend(resp_msgs)
            if resp_meta.get("model"):
                metadata["model"] = resp_meta["model"]
            if resp_meta.get("finish_reason"):
                metadata["finish_reason"] = resp_meta["finish_reason"]
            if resp_meta.get("usage"):
                metadata["usage"] = resp_meta["usage"]

    return {"messages": messages, "metadata": metadata}
