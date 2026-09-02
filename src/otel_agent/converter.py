"""Format conversion between OpenAI and Anthropic API formats."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


def openai_to_anthropic_request(openai_body: dict[str, Any]) -> dict[str, Any]:
    """Convert an OpenAI chat completion request to Anthropic messages format.

    Handles: messages, model, max_tokens, temperature, top_p, stream, stop.
    System messages are extracted to the top-level 'system' field.
    """
    messages = openai_body.get("messages", [])
    system_parts: list[str] = []
    converted_messages: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            if isinstance(content, str):
                system_parts.append(content)
            elif isinstance(content, list):
                text = " ".join(
                    p.get("text", "") for p in content if p.get("type") == "text"
                )
                system_parts.append(text)
            continue

        if role == "assistant":
            converted_messages.append({"role": "assistant", "content": content})
        else:
            # user or any other role -> user
            converted_messages.append({"role": "user", "content": content})

    result: dict[str, Any] = {
        "model": openai_body.get("model", ""),
        "messages": converted_messages,
        "max_tokens": openai_body.get("max_tokens", 4096),
    }

    if system_parts:
        result["system"] = "\n\n".join(system_parts)

    if "temperature" in openai_body:
        result["temperature"] = openai_body["temperature"]
    if "top_p" in openai_body:
        result["top_p"] = openai_body["top_p"]
    if "stream" in openai_body:
        result["stream"] = openai_body["stream"]
    if "stop" in openai_body:
        stop = openai_body["stop"]
        if isinstance(stop, str):
            result["stop_sequences"] = [stop]
        elif isinstance(stop, list):
            result["stop_sequences"] = stop

    return result


def _flatten_anthropic_content(content: Any) -> tuple[str | list[Any], str]:
    """Turn Anthropic content blocks into OpenAI string content + reasoning.

    Claude Code history uses ``thinking`` / ``text`` blocks. OpenAI-format
    providers (xAI) reject those objects as invalid arguments.
    """
    if isinstance(content, str):
        return content, ""
    if not isinstance(content, list):
        return str(content) if content else "", ""

    texts: list[str] = []
    reasoning_parts: list[str] = []
    leftover: list[Any] = []
    for part in content:
        if not isinstance(part, dict):
            leftover.append(part)
            continue
        kind = part.get("type")
        if kind == "text":
            texts.append(str(part.get("text") or ""))
        elif kind in ("thinking", "redacted_thinking"):
            thinking = part.get("thinking") or part.get("data") or ""
            if thinking:
                reasoning_parts.append(str(thinking))
        else:
            leftover.append(part)

    reasoning = "".join(reasoning_parts)
    if leftover:
        combined: list[Any] = []
        if texts:
            combined.append({"type": "text", "text": "".join(texts)})
        combined.extend(leftover)
        return combined, reasoning
    return "".join(texts), reasoning


def anthropic_to_openai_request(anthropic_body: dict[str, Any]) -> dict[str, Any]:
    """Convert an Anthropic messages request to OpenAI chat completion format.

    The top-level 'system' field is prepended as a system message.
    Content-block arrays (text/thinking) are flattened for OpenAI providers.
    """
    messages = anthropic_body.get("messages", [])
    system = anthropic_body.get("system", "")

    converted_messages: list[dict[str, Any]] = []

    if system:
        if isinstance(system, list):
            text = " ".join(
                p.get("text", "") for p in system if p.get("type") == "text"
            )
            converted_messages.append({"role": "system", "content": text})
        else:
            converted_messages.append({"role": "system", "content": str(system)})

    for msg in messages:
        role = msg.get("role", "user")
        content, reasoning = _flatten_anthropic_content(msg.get("content", ""))
        out_role = "assistant" if role == "assistant" else "user"
        converted: dict[str, Any] = {"role": out_role, "content": content}
        if reasoning and out_role == "assistant":
            converted["reasoning_content"] = reasoning
        converted_messages.append(converted)

    result: dict[str, Any] = {
        "model": anthropic_body.get("model", ""),
        "messages": converted_messages,
    }

    if "max_tokens" in anthropic_body:
        result["max_tokens"] = anthropic_body["max_tokens"]
    if "temperature" in anthropic_body:
        result["temperature"] = anthropic_body["temperature"]
    if "top_p" in anthropic_body:
        result["top_p"] = anthropic_body["top_p"]
    if "stream" in anthropic_body:
        result["stream"] = anthropic_body["stream"]
    if "stop_sequences" in anthropic_body:
        result["stop"] = anthropic_body["stop_sequences"]

    return result


def openai_to_anthropic_response(openai_resp: dict[str, Any]) -> dict[str, Any]:
    """Convert an OpenAI chat completion response to Anthropic messages format."""
    if "choices" not in openai_resp:
        return openai_resp

    choices = openai_resp.get("choices", [])
    content_blocks: list[dict[str, Any]] = []
    stop_reason = None

    for choice in choices:
        message = choice.get("message", {})
        text = message.get("content", "")
        if text:
            content_blocks.append({"type": "text", "text": text})

        finish = choice.get("finish_reason")
        if finish == "stop":
            stop_reason = "end_turn"
        elif finish == "length":
            stop_reason = "max_tokens"
        elif finish == "tool_calls":
            stop_reason = "tool_use"

    usage = openai_resp.get("usage", {})

    return {
        "id": openai_resp.get("id", ""),
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": openai_resp.get("model", ""),
        "stop_reason": stop_reason,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


def anthropic_to_openai_response(anthropic_resp: dict[str, Any]) -> dict[str, Any]:
    """Convert an Anthropic messages response to OpenAI chat completion format."""
    content = anthropic_resp.get("content", [])
    text_parts = [block.get("text", "") for block in content if block.get("type") == "text"]
    combined_text = "".join(text_parts)

    stop_reason = anthropic_resp.get("stop_reason")
    if stop_reason == "end_turn":
        finish_reason = "stop"
    elif stop_reason == "max_tokens":
        finish_reason = "length"
    else:
        finish_reason = "stop"

    usage = anthropic_resp.get("usage", {})

    return {
        "id": anthropic_resp.get("id", ""),
        "object": "chat.completion",
        "model": anthropic_resp.get("model", ""),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": combined_text},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
    }


def convert_openai_chunk_to_anthropic(chunk: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a single OpenAI streaming chunk to Anthropic streaming event.

    Returns None for chunks with no meaningful content.
    """
    choices = chunk.get("choices", [])
    if not choices:
        return None

    choice = choices[0]
    delta = choice.get("delta", {})
    finish = choice.get("finish_reason")

    events: list[dict[str, Any]] = []

    if "content" in delta and delta["content"]:
        events.append({
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": delta["content"]},
        })

    if finish:
        stop_reason = "end_turn" if finish == "stop" else "max_tokens"
        return {"type": "message_delta", "delta": {"stop_reason": stop_reason}}

    if events:
        return events[0]
    return None


@dataclass(frozen=True)
class AnthropicSSEEvent:
    """One Anthropic SSE frame (event: + data:)."""

    event: str
    data: dict[str, Any]

    def encode(self) -> bytes:
        return f"event: {self.event}\ndata: {json.dumps(self.data)}\n\n".encode()


class OpenAIToAnthropicStreamConverter:
    """Turn OpenAI chat.completion.chunk SSE into a full Anthropic event stream.

    Claude Code (and the Anthropic SDK) require ``message_start`` /
    ``content_block_start`` / ``message_stop``. Emitting only
    ``content_block_delta`` looks like an empty stream.

    xAI Grok often streams ``reasoning_content`` with no ``content`` until
    the end; those deltas become Anthropic thinking blocks so the client
    still receives complete events.
    """

    def __init__(self) -> None:
        self._started = False
        self._closed = False
        self._current_block: str | None = None
        self._current_index = -1
        self._next_index = 0

    def feed(self, chunk: dict[str, Any]) -> list[AnthropicSSEEvent]:
        if self._closed:
            return []

        events: list[AnthropicSSEEvent] = []
        if not self._started:
            events.extend(self._start(chunk))

        choices = chunk.get("choices") or []
        choice = choices[0] if choices else {}
        delta = choice.get("delta") or {}
        finish = choice.get("finish_reason")
        reasoning = delta.get("reasoning_content")
        content = delta.get("content")

        if reasoning:
            events.extend(self._ensure_block("thinking"))
            events.append(AnthropicSSEEvent(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": self._current_index,
                    "delta": {"type": "thinking_delta", "thinking": reasoning},
                },
            ))

        if content:
            events.extend(self._ensure_block("text"))
            events.append(AnthropicSSEEvent(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": self._current_index,
                    "delta": {"type": "text_delta", "text": content},
                },
            ))

        if finish:
            events.extend(self._finish(finish, chunk.get("usage") or {}))
        return events

    def flush(self) -> list[AnthropicSSEEvent]:
        if self._closed or not self._started:
            return []
        return self._finish("stop", {})

    def _start(self, chunk: dict[str, Any]) -> list[AnthropicSSEEvent]:
        self._started = True
        message = {
            "id": chunk.get("id") or "msg_proxy",
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": chunk.get("model") or "",
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        return [AnthropicSSEEvent("message_start", {"type": "message_start", "message": message})]

    def _ensure_block(self, kind: str) -> list[AnthropicSSEEvent]:
        if self._current_block == kind:
            return []
        events = self._close_block()
        index = self._next_index
        self._next_index += 1
        self._current_index = index
        self._current_block = kind
        if kind == "thinking":
            content_block: dict[str, Any] = {"type": "thinking", "thinking": ""}
        else:
            content_block = {"type": "text", "text": ""}
        events.append(AnthropicSSEEvent(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": index,
                "content_block": content_block,
            },
        ))
        return events

    def _close_block(self) -> list[AnthropicSSEEvent]:
        if self._current_block is None:
            return []
        index = self._current_index
        self._current_block = None
        return [AnthropicSSEEvent("content_block_stop", {"type": "content_block_stop", "index": index})]

    def _finish(self, finish: str, usage: dict[str, Any]) -> list[AnthropicSSEEvent]:
        events = self._close_block()
        stop_reason = "end_turn" if finish == "stop" else "max_tokens"
        if finish == "tool_calls":
            stop_reason = "tool_use"
        delta: dict[str, Any] = {"stop_reason": stop_reason, "stop_sequence": None}
        payload: dict[str, Any] = {"type": "message_delta", "delta": delta}
        output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
        if isinstance(output_tokens, int) and not isinstance(output_tokens, bool) and output_tokens >= 0:
            payload["usage"] = {"output_tokens": output_tokens}
        events.append(AnthropicSSEEvent("message_delta", payload))
        events.append(AnthropicSSEEvent("message_stop", {"type": "message_stop"}))
        self._closed = True
        return events


def convert_anthropic_chunk_to_openai(chunk: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a single Anthropic streaming event to OpenAI streaming chunk.

    Returns None for events with no meaningful content.
    """
    event_type = chunk.get("type", "")

    if event_type == "content_block_delta":
        delta = chunk.get("delta", {})
        text = delta.get("text", "")
        if text:
            return {
                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]
            }

    if event_type == "message_delta":
        delta = chunk.get("delta", {})
        stop = delta.get("stop_reason")
        if stop:
            finish = "stop" if stop == "end_turn" else "length"
            return {
                "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]
            }

    return None
