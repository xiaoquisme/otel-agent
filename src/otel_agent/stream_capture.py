"""Reassemble streamed upstream chunks into a compact telemetry body.

A streamed response used to be stored as the concatenated raw chunk JSON
(``{"streamed": true, "preview": "<chunk><chunk>…"}``). That representation is
five to ten times the size of the answer it carries — every chunk repeats
``id``/``object``/``created``/``model`` and empty deltas — so it hit the
telemetry body limit constantly, the cut landed mid-chunk, and the usage the
providers report in the *tail* chunk was lost. The dashboard was then left
parsing chunk soup out of a truncated string.

Reassembling while forwarding fixes the representation instead of raising the
limit: the stored body is the answer itself (content, reasoning, tool calls,
finish reason) plus the provider's full usage object — cache fields included —
so nothing is truncated in practice and analytics survive.

The accumulator is bounded: text stops collecting at ``text_limit`` characters
(total across content, reasoning and tool arguments) and the snapshot is
flagged ``content_truncated``. That keeps the original memory guarantee — a
minutes-long stream never buffers unbounded data — while storing one copy of
the answer text instead of a copy of every chunk envelope.
"""

from __future__ import annotations

from typing import Any

#: Safety bound on reassembled text, shared across content, reasoning and
#: tool arguments. Far above any real completion (4M chars ≈ 1M tokens) so it
#: only binds on pathological streams.
TEXT_LIMIT = 4_000_000

#: Anthropic SSE event names (the ``type`` field of each event's data object).
_ANTHROPIC_EVENTS = frozenset({
    "message_start", "message_delta", "message_stop", "ping", "error",
    "content_block_start", "content_block_delta", "content_block_stop",
})


class StreamCapture:
    """Accumulate upstream streaming chunks into a compact body snapshot.

    Understands the three upstream wire formats the gateway routes to:
    OpenAI chat completion chunks, Anthropic message events, and OpenAI
    Responses API events. Usage objects are merged raw (later non-None values
    win) so provider-specific fields — cache tokens included — survive into
    the stored body.
    """

    def __init__(self, text_limit: int = TEXT_LIMIT) -> None:
        self._text_limit = text_limit
        self._content: list[str] = []
        self._reasoning: list[str] = []
        self._text_len = 0
        self._truncated = False
        # key: stream-local index (openai tool index / anthropic block index /
        # responses output_index) — one stream speaks one format, so the key
        # spaces cannot collide.
        self._tool_calls: dict[Any, dict[str, Any]] = {}
        self._finish_reason: str | None = None
        self._model: str | None = None
        self._usage: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def feed(self, chunk: Any) -> None:
        """Incorporate one decoded upstream chunk (any supported format)."""
        if not isinstance(chunk, dict):
            return
        self._absorb_model(chunk)
        self._absorb_usage(chunk)

        kind = chunk.get("type")
        if isinstance(kind, str):
            if kind.startswith("response."):
                self._feed_responses(chunk)
            elif kind in _ANTHROPIC_EVENTS:
                self._feed_anthropic(chunk)
        elif "choices" in chunk:
            self._feed_openai(chunk)

    def _absorb_model(self, chunk: dict[str, Any]) -> None:
        if self._model is not None:
            return
        for source in _nestings(chunk, "model"):
            if isinstance(source, str) and source:
                self._model = source
                return

    def _absorb_usage(self, chunk: dict[str, Any]) -> None:
        for source in _nestings(chunk, "usage"):
            if not isinstance(source, dict):
                continue
            merged = dict(self._usage) if self._usage else {}
            for key, value in source.items():
                if value is not None:
                    merged[key] = value
            self._usage = merged

    def _feed_openai(self, chunk: dict[str, Any]) -> None:
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            return
        choice = choices[0] if isinstance(choices[0], dict) else {}
        if choice.get("finish_reason"):
            self._finish_reason = choice["finish_reason"]
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            return
        self._append(delta.get("content"), self._content)
        self._append(delta.get("reasoning_content"), self._reasoning)
        calls = delta.get("tool_calls")
        if isinstance(calls, list):
            for call in calls:
                if not isinstance(call, dict):
                    continue
                slot = self._tool_slot(call.get("index"))
                fn = call.get("function")
                self._set_call_identity(slot, call.get("id"), fn)
                if isinstance(fn, dict):
                    self._append(fn.get("arguments"), slot["args"])

    def _feed_anthropic(self, chunk: dict[str, Any]) -> None:
        kind = chunk["type"]
        if kind == "content_block_delta":
            delta = chunk.get("delta")
            if not isinstance(delta, dict):
                return
            dtype = delta.get("type")
            if dtype == "text_delta":
                self._append(delta.get("text"), self._content)
            elif dtype == "thinking_delta":
                self._append(delta.get("thinking"), self._reasoning)
            elif dtype == "input_json_delta":
                slot = self._tool_slot(chunk.get("index"))
                self._append(delta.get("partial_json"), slot["args"])
        elif kind == "content_block_start":
            block = chunk.get("content_block")
            if isinstance(block, dict) and block.get("type") == "tool_use":
                slot = self._tool_slot(chunk.get("index"))
                self._set_call_identity(slot, block.get("id"), block)
        elif kind == "message_delta":
            delta = chunk.get("delta")
            if isinstance(delta, dict) and delta.get("stop_reason"):
                self._finish_reason = delta["stop_reason"]

    def _feed_responses(self, chunk: dict[str, Any]) -> None:
        kind = chunk["type"]
        if kind == "response.output_text.delta":
            self._append(chunk.get("delta"), self._content)
        elif kind in ("response.reasoning_text.delta", "response.reasoning_summary_text.delta"):
            self._append(chunk.get("delta"), self._reasoning)
        elif kind == "response.output_item.added":
            item = chunk.get("item")
            if isinstance(item, dict) and item.get("type") == "function_call":
                slot = self._tool_slot(_responses_index(chunk))
                self._set_call_identity(slot, item.get("call_id") or item.get("id"), item)
        elif kind == "response.function_call_arguments.delta":
            slot = self._tool_slot(_responses_index(chunk))
            self._append(chunk.get("delta"), slot["args"])
        elif kind in ("response.completed", "response.incomplete", "response.failed"):
            response = chunk.get("response")
            if not isinstance(response, dict):
                return
            status = response.get("status")
            if status == "completed":
                self._finish_reason = "stop"
            else:
                details = response.get("incomplete_details")
                reason = details.get("reason") if isinstance(details, dict) else None
                self._finish_reason = reason or status or self._finish_reason

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _tool_slot(self, index: Any) -> dict[str, Any]:
        key = index if isinstance(index, int) else 0
        slot = self._tool_calls.get(key)
        if slot is None:
            slot = {"id": None, "name": "", "args": []}
            self._tool_calls[key] = slot
        return slot

    @staticmethod
    def _set_call_identity(slot: dict[str, Any], call_id: Any, fn: Any) -> None:
        if call_id:
            slot["id"] = call_id
        if isinstance(fn, dict) and fn.get("name"):
            slot["name"] = fn["name"]

    def _append(self, text: Any, target: list[str]) -> None:
        if not isinstance(text, str) or not text:
            return
        if self._truncated:
            return
        remaining = self._text_limit - self._text_len
        if remaining <= 0:
            self._truncated = True
            return
        if len(text) > remaining:
            text = text[:remaining]
            self._truncated = True
        target.append(text)
        self._text_len += len(text)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return the compact telemetry body for the stream seen so far."""
        body: dict[str, Any] = {"streamed": True}
        # Usage first: if some downstream ever size-cuts the serialized body,
        # the analytics tail is what must survive the cut.
        if self._usage:
            body["usage"] = self._usage
        if self._model is not None:
            body["model"] = self._model
        if self._finish_reason is not None:
            body["finish_reason"] = self._finish_reason
        body["content"] = "".join(self._content)
        reasoning = "".join(self._reasoning)
        if reasoning:
            body["reasoning_content"] = reasoning
        if self._tool_calls:
            body["tool_calls"] = [
                {
                    "id": slot["id"],
                    "name": slot["name"],
                    "arguments": "".join(slot["args"]),
                }
                for slot in self._tool_calls.values()
            ]
        if self._truncated:
            body["content_truncated"] = True
        return body


def _nestings(chunk: dict[str, Any], field: str) -> list[Any]:
    """The places a format nests ``usage`` (or ``model``) in a chunk."""
    sources = [chunk.get(field)]
    for nested_key in ("message", "response"):
        nested = chunk.get(nested_key)
        if isinstance(nested, dict):
            sources.append(nested.get(field))
    return sources


def _responses_index(chunk: dict[str, Any]) -> Any:
    index = chunk.get("output_index")
    return index if index is not None else chunk.get("item_id")
