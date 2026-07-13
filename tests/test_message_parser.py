"""Tests for otel_agent.dashboard.message_parser module."""

from __future__ import annotations

import json
import pytest
from otel_agent.dashboard.message_parser import parse_messages


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_openai_request(*, with_system: bool = False, with_tool_calls: bool = False) -> str:
    msgs = []
    if with_system:
        msgs.append({"role": "system", "content": "You are helpful."})
    msgs.append({"role": "user", "content": "Hello!"})
    if with_tool_calls:
        msgs.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location":"NYC"}'},
            }],
        })
        msgs.append({"role": "tool", "content": '{"temp": 72}'})
    else:
        msgs.append({"role": "assistant", "content": "Hi there!"})
    msgs.append({"role": "user", "content": "How are you?"})
    return json.dumps({"model": "gpt-4", "messages": msgs})


def _make_openai_response(*, content: str = "Hello, world!", with_tool_calls: bool = False) -> str:
    message: dict = {"role": "assistant", "content": content}
    if with_tool_calls:
        message["content"] = None
        message["tool_calls"] = [{
            "id": "call_1",
            "type": "function",
            "function": {"name": "get_weather", "arguments": '{"location":"NYC"}'},
        }]
    return json.dumps({
        "id": "chatcmpl-123",
        "model": "gpt-4",
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": "stop" if not with_tool_calls else "tool_calls",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    })


def _make_anthropic_request(*, with_system: bool = False) -> str:
    msgs = [{"role": "user", "content": "Hello!"}]
    body: dict = {"model": "claude-3", "messages": msgs, "max_tokens": 100}
    if with_system:
        body["system"] = "You are helpful."
    return json.dumps(body)


def _make_anthropic_response(*, text: str = "Hello from Claude") -> str:
    return json.dumps({
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "model": "claude-3-opus",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    })


def _make_streaming_preview() -> str:
    chunks = [
        json.dumps({"model": "gpt-4", "choices": [{"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}]}),
        json.dumps({"choices": [{"index": 0, "delta": {"content": " world"}, "finish_reason": None}]}),
        json.dumps({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}),
    ]
    return json.dumps({"streamed": True, "preview": "".join(chunks)})


# ---------------------------------------------------------------------------
# Tests: OpenAI request parsing
# ---------------------------------------------------------------------------

class TestOpenAIRequest:
    def test_basic_messages(self) -> None:
        body = _make_openai_request()
        result = parse_messages(request_body=body, response_body=None)
        messages = result["messages"]
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello!"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hi there!"
        assert messages[2]["role"] == "user"

    def test_with_system_message(self) -> None:
        body = _make_openai_request(with_system=True)
        result = parse_messages(request_body=body, response_body=None)
        messages = result["messages"]
        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful."

    def test_with_tool_calls(self) -> None:
        body = _make_openai_request(with_tool_calls=True)
        result = parse_messages(request_body=body, response_body=None)
        messages = result["messages"]
        # user, assistant(tool_calls), tool, user = 4 messages
        assert len(messages) == 4
        assistant_msg = messages[1]
        assert assistant_msg["role"] == "assistant"
        assert "tool_calls" in assistant_msg
        assert len(assistant_msg["tool_calls"]) == 1
        assert assistant_msg["tool_calls"][0]["name"] == "get_weather"
        assert messages[2]["role"] == "tool"


# ---------------------------------------------------------------------------
# Tests: OpenAI response parsing
# ---------------------------------------------------------------------------

class TestOpenAIResponse:
    def test_basic_response(self) -> None:
        body = _make_openai_response()
        result = parse_messages(request_body=None, response_body=body)
        messages = result["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "Hello, world!"
        assert result["metadata"]["model"] == "gpt-4"
        assert result["metadata"]["finish_reason"] == "stop"

    def test_response_with_usage(self) -> None:
        body = _make_openai_response()
        result = parse_messages(request_body=None, response_body=body)
        usage = result["metadata"]["usage"]
        assert usage is not None
        assert usage["prompt_tokens"] == 10
        assert usage["completion_tokens"] == 5

    def test_response_with_tool_calls(self) -> None:
        body = _make_openai_response(with_tool_calls=True)
        result = parse_messages(request_body=None, response_body=body)
        messages = result["messages"]
        assert len(messages) == 1
        msg = messages[0]
        assert "tool_calls" in msg
        assert msg["tool_calls"][0]["name"] == "get_weather"


# ---------------------------------------------------------------------------
# Tests: Anthropic request parsing
# ---------------------------------------------------------------------------

class TestAnthropicRequest:
    def test_basic_messages(self) -> None:
        body = _make_anthropic_request()
        result = parse_messages(request_body=body, response_body=None)
        messages = result["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello!"

    def test_with_system_message(self) -> None:
        body = _make_anthropic_request(with_system=True)
        result = parse_messages(request_body=body, response_body=None)
        messages = result["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful."


# ---------------------------------------------------------------------------
# Tests: Anthropic response parsing
# ---------------------------------------------------------------------------

class TestAnthropicResponse:
    def test_basic_response(self) -> None:
        body = _make_anthropic_response()
        result = parse_messages(request_body=None, response_body=body)
        messages = result["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "Hello from Claude"
        assert result["metadata"]["model"] == "claude-3-opus"
        assert result["metadata"]["finish_reason"] == "end_turn"

    def test_response_with_usage(self) -> None:
        body = _make_anthropic_response()
        result = parse_messages(request_body=None, response_body=body)
        usage = result["metadata"]["usage"]
        assert usage is not None
        assert usage["input_tokens"] == 10
        assert usage["output_tokens"] == 5


# ---------------------------------------------------------------------------
# Tests: Streaming preview parsing
# ---------------------------------------------------------------------------

class TestStreamingPreview:
    def test_basic_streaming(self) -> None:
        body = _make_streaming_preview()
        result = parse_messages(request_body=None, response_body=body)
        messages = result["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "Hello world"
        assert result["metadata"]["model"] == "gpt-4"
        assert result["metadata"]["finish_reason"] == "stop"

    def test_streaming_with_reasoning(self) -> None:
        chunks = [
            json.dumps({"choices": [{"index": 0, "delta": {"reasoning_content": "Thinking..."}, "finish_reason": None}]}),
            json.dumps({"choices": [{"index": 0, "delta": {"content": "Answer"}, "finish_reason": "stop"}]}),
        ]
        body = json.dumps({"streamed": True, "preview": "".join(chunks)})
        result = parse_messages(request_body=None, response_body=body)
        messages = result["messages"]
        assert len(messages) == 1
        assert messages[0]["reasoning_content"] == "Thinking..."
        assert messages[0]["content"] == "Answer"


# ---------------------------------------------------------------------------
# Tests: Combined request + response
# ---------------------------------------------------------------------------

class TestCombinedParsing:
    def test_openai_request_and_response(self) -> None:
        req = _make_openai_request()
        resp = _make_openai_response()
        result = parse_messages(request_body=req, response_body=resp)
        messages = result["messages"]
        # 3 request messages + 1 response message
        assert len(messages) == 4
        assert messages[0]["role"] == "user"
        assert messages[-1]["role"] == "assistant"
        assert messages[-1]["content"] == "Hello, world!"
        assert result["metadata"]["format"] == "openai"


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_bodies(self) -> None:
        result = parse_messages(request_body=None, response_body=None)
        assert result["messages"] == []
        assert result["metadata"]["format"] == "unknown"

    def test_empty_string_bodies(self) -> None:
        result = parse_messages(request_body="", response_body="")
        assert result["messages"] == []

    def test_invalid_json(self) -> None:
        result = parse_messages(request_body="not json", response_body="also not json")
        assert result["messages"] == []

    def test_unknown_format(self) -> None:
        body = json.dumps({"foo": "bar"})
        result = parse_messages(request_body=body, response_body=None)
        assert result["messages"] == []
        assert result["metadata"]["format"] == "unknown"

    def test_empty_openai_request(self) -> None:
        body = json.dumps({"model": "gpt-4", "messages": []})
        result = parse_messages(request_body=body, response_body=None)
        assert result["messages"] == []

    def test_format_tag_override(self) -> None:
        body = json.dumps({"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]})
        result = parse_messages(request_body=body, response_body=None, format_tag="openai")
        assert result["metadata"]["format"] == "openai"
