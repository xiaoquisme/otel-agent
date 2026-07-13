"""Tests for otel_agent.dashboard.render module (format detection and chunk parsing only)."""

from __future__ import annotations

import json
import pytest
from otel_agent.dashboard.render import (
    detect_format,
    _parse_streaming_chunks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openai_request(*, with_system: bool = False) -> str:
    msgs = []
    if with_system:
        msgs.append({"role": "system", "content": "You are helpful."})
    msgs.extend([
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"},
    ])
    return json.dumps({"model": "gpt-4", "messages": msgs})


def _make_openai_response(*, content: str = "Hello, world!") -> str:
    return json.dumps({
        "id": "chatcmpl-123",
        "model": "gpt-4",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    })


def _make_anthropic_request(*, with_system: bool = False) -> str:
    msgs = [{"role": "user", "content": "What is 2+2?"}]
    body: dict = {"model": "claude-3", "messages": msgs, "max_tokens": 100}
    if with_system:
        body["system"] = "You are a math tutor."
    return json.dumps(body)


def _make_anthropic_response() -> str:
    return json.dumps({
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "4"}],
        "model": "claude-3-opus",
        "stop_reason": "end_turn",
    })


def _make_streaming_preview(*, chunks: list | None = None) -> str:
    if chunks is None:
        chunks = [
            {"model": "gpt-4", "choices": [{"delta": {"content": "Hello"}, "index": 0}]},
            {"choices": [{"delta": {"content": " world!"}, "finish_reason": "stop", "index": 0}]},
        ]
    preview = "".join(json.dumps(c) for c in chunks)
    return json.dumps({"streamed": True, "preview": preview})


# ---------------------------------------------------------------------------
# Tests: detect_format
# ---------------------------------------------------------------------------

class TestDetectFormat:
    """Tests for detect_format."""

    def test_openai_request(self) -> None:
        body = _make_openai_request()
        assert detect_format(body) == "openai"

    def test_openai_request_with_system(self) -> None:
        body = _make_openai_request(with_system=True)
        assert detect_format(body) == "openai"

    def test_openai_response(self) -> None:
        body = _make_openai_response()
        assert detect_format(body) == "openai"

    def test_anthropic_request(self) -> None:
        body = _make_anthropic_request()
        assert detect_format(body) == "anthropic"

    def test_anthropic_response(self) -> None:
        body = _make_anthropic_response()
        assert detect_format(body) == "anthropic"

    def test_streaming_preview(self) -> None:
        body = _make_streaming_preview()
        assert detect_format(body) == "streaming"

    def test_unknown_format(self) -> None:
        body = json.dumps({"foo": "bar", "baz": 42})
        assert detect_format(body) == "unknown"

    def test_empty_body(self) -> None:
        assert detect_format("") == "unknown"

    def test_non_json_body(self) -> None:
        assert detect_format("not json at all") == "unknown"

    def test_format_tag_override_openai(self) -> None:
        body = json.dumps({})
        assert detect_format(body, "openai") == "openai"

    def test_format_tag_override_anthropic(self) -> None:
        body = json.dumps({})
        assert detect_format(body, "anthropic-messages") == "anthropic"

    def test_format_tag_override_streaming(self) -> None:
        body = json.dumps({})
        assert detect_format(body, "streaming") == "streaming"

    def test_format_tag_case_insensitive(self) -> None:
        body = json.dumps({})
        assert detect_format(body, "OpenAI") == "openai"
        assert detect_format(body, "ANTHROPIC") == "anthropic"

    def test_format_tag_claude(self) -> None:
        body = json.dumps({})
        assert detect_format(body, "claude-response") == "anthropic"

    def test_streaming_body_overrides_openai_format_tag(self) -> None:
        """Streaming preview body must be detected even when format_tag='openai'.

        Regression: the DB format column stores the client API format (e.g.
        'openai'), not whether the response was streamed. detect_format must
        check body content first so streaming previews are routed to the
        streaming parser.
        """
        body = _make_streaming_preview()
        assert detect_format(body, "openai") == "streaming"

    def test_streaming_body_overrides_anthropic_format_tag(self) -> None:
        body = _make_streaming_preview()
        assert detect_format(body, "anthropic") == "streaming"


# ---------------------------------------------------------------------------
# Tests: streaming chunk parser
# ---------------------------------------------------------------------------

class TestStreamingChunks:
    """Tests for _parse_streaming_chunks."""

    def test_basic_parsing(self) -> None:
        preview = json.dumps({"choices": [{"delta": {"content": "a"}}]}) + json.dumps(
            {"choices": [{"delta": {"content": "b"}}]}
        )
        chunks = _parse_streaming_chunks(preview)
        assert len(chunks) == 2

    def test_malformed_chunks(self) -> None:
        valid = json.dumps({"choices": [{"delta": {"content": "ok"}}]})
        preview = valid + '{"broken"' + valid
        chunks = _parse_streaming_chunks(preview)
        assert len(chunks) >= 1

    def test_empty_preview(self) -> None:
        chunks = _parse_streaming_chunks("")
        assert chunks == []

    def test_single_chunk(self) -> None:
        preview = json.dumps({"model": "gpt-4", "choices": [{"delta": {"content": "hi"}}]})
        chunks = _parse_streaming_chunks(preview)
        assert len(chunks) == 1
        assert chunks[0]["model"] == "gpt-4"
