"""Tests for Anthropic ↔ OpenAI format conversion."""

from otel_agent.converter import (
    anthropic_to_openai_request,
    anthropic_to_openai_response,
    convert_anthropic_chunk_to_openai,
    convert_openai_chunk_to_anthropic,
    openai_to_anthropic_request,
    openai_to_anthropic_response,
)


# --- Request conversion ---


def test_openai_to_anthropic_basic():
    openai = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ],
        "max_tokens": 100,
        "temperature": 0.7,
    }
    result = openai_to_anthropic_request(openai)
    assert result["model"] == "gpt-4"
    assert result["system"] == "You are helpful."
    assert len(result["messages"]) == 3
    assert result["messages"][0] == {"role": "user", "content": "Hello"}
    assert result["messages"][1] == {"role": "assistant", "content": "Hi there!"}
    assert result["messages"][2] == {"role": "user", "content": "How are you?"}
    assert result["max_tokens"] == 100
    assert result["temperature"] == 0.7


def test_openai_to_anthropic_stop():
    openai = {"model": "gpt-4", "messages": [], "stop": ["END", "STOP"]}
    result = openai_to_anthropic_request(openai)
    assert result["stop_sequences"] == ["END", "STOP"]


def test_openai_to_anthropic_stop_string():
    openai = {"model": "gpt-4", "messages": [], "stop": "END"}
    result = openai_to_anthropic_request(openai)
    assert result["stop_sequences"] == ["END"]


def test_anthropic_to_openai_basic():
    anthropic = {
        "model": "claude-3",
        "system": "Be helpful",
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "Bye"},
        ],
        "max_tokens": 200,
    }
    result = anthropic_to_openai_request(anthropic)
    assert result["model"] == "claude-3"
    assert result["messages"][0] == {"role": "system", "content": "Be helpful"}
    assert result["messages"][1] == {"role": "user", "content": "Hello"}
    assert result["messages"][2] == {"role": "assistant", "content": "Hi!"}
    assert result["messages"][3] == {"role": "user", "content": "Bye"}
    assert result["max_tokens"] == 200


def test_anthropic_to_openai_stop_sequences():
    anthropic = {"model": "claude-3", "messages": [], "stop_sequences": ["END"]}
    result = anthropic_to_openai_request(anthropic)
    assert result["stop"] == ["END"]


# --- Response conversion ---


def test_openai_to_anthropic_response():
    openai = {
        "id": "chatcmpl-123",
        "model": "gpt-4",
        "choices": [
            {
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    result = openai_to_anthropic_response(openai)
    assert result["type"] == "message"
    assert result["role"] == "assistant"
    assert result["content"][0]["text"] == "Hello!"
    assert result["stop_reason"] == "end_turn"
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["output_tokens"] == 5


def test_openai_to_anthropic_response_length():
    openai = {
        "id": "chatcmpl-123",
        "model": "gpt-4",
        "choices": [{"message": {"content": "partial"}, "finish_reason": "length"}],
        "usage": {},
    }
    result = openai_to_anthropic_response(openai)
    assert result["stop_reason"] == "max_tokens"


def test_anthropic_to_openai_response():
    anthropic = {
        "id": "msg-123",
        "type": "message",
        "model": "claude-3",
        "content": [{"type": "text", "text": "Hello!"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    result = anthropic_to_openai_response(anthropic)
    assert result["object"] == "chat.completion"
    assert result["choices"][0]["message"]["content"] == "Hello!"
    assert result["choices"][0]["finish_reason"] == "stop"
    assert result["usage"]["prompt_tokens"] == 10
    assert result["usage"]["completion_tokens"] == 5
    assert result["usage"]["total_tokens"] == 15


# --- Streaming chunk conversion ---


def test_openai_chunk_to_anthropic_content():
    chunk = {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]}
    result = convert_openai_chunk_to_anthropic(chunk)
    assert result is not None
    assert result["type"] == "content_block_delta"
    assert result["delta"]["text"] == "Hello"


def test_openai_chunk_to_anthropic_finish():
    chunk = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
    result = convert_openai_chunk_to_anthropic(chunk)
    assert result is not None
    assert result["type"] == "message_delta"
    assert result["delta"]["stop_reason"] == "end_turn"


def test_openai_chunk_to_anthropic_empty():
    chunk = {"choices": [{"delta": {}, "finish_reason": None}]}
    result = convert_openai_chunk_to_anthropic(chunk)
    assert result is None


def test_anthropic_chunk_to_openai_content():
    chunk = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi"}}
    result = convert_anthropic_chunk_to_openai(chunk)
    assert result is not None
    assert result["choices"][0]["delta"]["content"] == "Hi"


def test_anthropic_chunk_to_openai_finish():
    chunk = {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}
    result = convert_anthropic_chunk_to_openai(chunk)
    assert result is not None
    assert result["choices"][0]["finish_reason"] == "stop"


def test_anthropic_chunk_to_openai_other():
    chunk = {"type": "message_start"}
    result = convert_anthropic_chunk_to_openai(chunk)
    assert result is None
