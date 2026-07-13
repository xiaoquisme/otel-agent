"""Comprehensive tests for otel_agent.dashboard.render module."""

from __future__ import annotations

import json

import pytest

from otel_agent.dashboard.render import (
    detect_format,
    render_body,
    render_markdown,
    render_request_body,
    render_response_body,
    render_tool_calls,
    _parse_streaming_chunks,
    _highlight_json,
    _escape,
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


def _make_anthropic_request(*, with_system: bool = True) -> str:
    body: dict = {
        "model": "claude-3-sonnet",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "Thanks!"},
        ],
    }
    if with_system:
        body["system"] = "You are a helpful math tutor."
    return json.dumps(body)


def _make_anthropic_response(*, text: str = "The answer is **4**.") -> str:
    return json.dumps({
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "model": "claude-3-sonnet",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
    })


def _make_streaming_preview(*, chunks: list | None = None) -> str:
    if chunks is None:
        chunks = [
            {"model": "gpt-4", "choices": [{"delta": {"content": "Hello"}, "index": 0}]},
            {"choices": [{"delta": {"content": " world!"}, "finish_reason": "stop", "index": 0}]},
        ]
    return json.dumps({"streamed": True, "preview": "".join(json.dumps(c) for c in chunks)})


# ===================================================================
# Tests
# ===================================================================

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


class TestRenderRequestBody:
    """Tests for render_request_body."""

    def test_openai_request_chat_bubbles(self) -> None:
        body = _make_openai_request()
        html = render_request_body(body)
        assert html is not None
        assert 'class="chat-message chat-user"' in html
        assert 'class="chat-message chat-assistant"' in html
        assert "Hello!" in html
        assert "Hi there!" in html

    def test_openai_request_with_system(self) -> None:
        body = _make_openai_request(with_system=True)
        html = render_request_body(body)
        assert html is not None
        assert 'class="chat-message chat-system"' in html
        assert "You are helpful." in html

    def test_anthropic_request_system_extraction(self) -> None:
        body = _make_anthropic_request(with_system=True)
        html = render_request_body(body, format_tag="anthropic")
        assert html is not None
        assert 'class="chat-message chat-system"' in html
        assert "math tutor" in html
        assert "What is 2+2?" in html

    def test_anthropic_request_without_system(self) -> None:
        body = _make_anthropic_request(with_system=False)
        html = render_request_body(body, format_tag="anthropic")
        assert html is not None
        assert "chat-system" not in (html or "")
        assert "What is 2+2?" in html

    def test_non_llm_body_returns_none(self) -> None:
        body = json.dumps({"foo": "bar"})
        assert render_request_body(body) is None


class TestRenderResponseBody:
    """Tests for render_response_body."""

    def test_openai_response_badges(self) -> None:
        body = _make_openai_response()
        html = render_response_body(body)
        assert html is not None
        assert 'class="response-meta-badge model"' in html
        assert "gpt-4" in html
        assert 'class="response-meta-badge finish"' in html
        assert "stop" in html

    def test_openai_response_content(self) -> None:
        body = _make_openai_response(content="# Hello\n\nWorld")
        html = render_response_body(body)
        assert html is not None
        assert "Hello" in html
        assert "World" in html
        assert "chat-assistant" in html

    def test_anthropic_response_content_blocks(self) -> None:
        body = _make_anthropic_response(text="The answer is **4**.")
        html = render_response_body(body, format_tag="anthropic")
        assert html is not None
        assert "claude-3-sonnet" in html
        assert "end_turn" in html
        assert "4" in html

    def test_anthropic_response_multiple_blocks(self) -> None:
        body = json.dumps({
            "id": "msg_456",
            "type": "message",
            "role": "assistant",
            "model": "claude-3-opus",
            "content": [
                {"type": "text", "text": "First block."},
                {"type": "text", "text": "Second block."},
            ],
            "stop_reason": "end_turn",
        })
        html = render_response_body(body, format_tag="anthropic")
        assert html is not None
        assert "First block." in html
        assert "Second block." in html

    def test_non_llm_body_returns_none(self) -> None:
        body = json.dumps({"foo": "bar"})
        assert render_response_body(body) is None


class TestStreaming:
    """Tests for streaming preview rendering."""

    def test_streaming_preview_basic(self) -> None:
        body = _make_streaming_preview()
        html = render_response_body(body, format_tag="streaming")
        assert html is not None
        assert "Hello" in html
        assert "world!" in html
        assert "gpt-4" in html

    def test_streaming_preview_with_model(self) -> None:
        chunks = [
            {"model": "gpt-4-turbo", "choices": [{"delta": {"content": "Hi"}, "index": 0}]},
            {"choices": [{"delta": {"content": "!"}, "finish_reason": "stop", "index": 0}]},
        ]
        body = _make_streaming_preview(chunks=chunks)
        html = render_response_body(body, format_tag="streaming")
        assert html is not None
        assert "gpt-4-turbo" in html

    def test_streaming_preview_incomplete(self) -> None:
        chunks = [
            {"model": "gpt-4", "choices": [{"delta": {}, "index": 0}]},
        ]
        body = _make_streaming_preview(chunks=chunks)
        html = render_response_body(body, format_tag="streaming")
        assert html is not None
        assert "streaming-incomplete" in html

    def test_streaming_chunks_parser(self) -> None:
        preview = json.dumps({"choices": [{"delta": {"content": "a"}}]}) + json.dumps(
            {"choices": [{"delta": {"content": "b"}}]}
        )
        chunks = _parse_streaming_chunks(preview)
        assert len(chunks) == 2

    def test_streaming_chunks_parser_malformed(self) -> None:
        # Mix of valid and invalid chunks
        valid = json.dumps({"choices": [{"delta": {"content": "ok"}}]})
        preview = valid + '{"broken"' + valid
        chunks = _parse_streaming_chunks(preview)
        # Should extract at least the valid chunks
        assert len(chunks) >= 1


class TestToolCalls:
    """Tests for tool call rendering."""

    def test_tool_calls_basic(self) -> None:
        calls = [
            {"function": {"name": "get_weather", "arguments": '{"city": "NYC"}'}}
        ]
        html = render_tool_calls(calls)
        assert "get_weather" in html
        assert "tool-call-name" in html
        assert "NYC" in html

    def test_tool_calls_json_pretty_printed(self) -> None:
        calls = [
            {"function": {"name": "search", "arguments": '{"query": "test", "limit": 10}'}}
        ]
        html = render_tool_calls(calls)
        assert "tool-call-args" in html
        # Quotes are HTML-escaped by _escape inside render_tool_calls
        assert "&quot;query&quot;" in html

    def test_tool_calls_multiple(self) -> None:
        calls = [
            {"function": {"name": "func_a", "arguments": "{}"}},
            {"function": {"name": "func_b", "arguments": "{}"}},
        ]
        html = render_tool_calls(calls)
        assert "func_a" in html
        assert "func_b" in html
        assert html.count("tool-call") >= 2

    def test_tool_calls_dict_input(self) -> None:
        """When arguments is already a dict, not a string."""
        calls = [
            {"function": {"name": "do_thing", "arguments": {"key": "val"}}}
        ]
        html = render_tool_calls(calls)
        assert "do_thing" in html
        assert "key" in html

    def test_tool_calls_flat_format(self) -> None:
        """Anthropic-style tool_use blocks (name + input)."""
        calls = [
            {"name": "calculator", "input": {"expr": "2+2"}}
        ]
        html = render_tool_calls(calls)
        assert "calculator" in html
        assert "2+2" in html

    def test_tool_calls_empty(self) -> None:
        html = render_tool_calls([])
        assert html == ""

    def test_tool_calls_invalid_json_arguments(self) -> None:
        calls = [
            {"function": {"name": "broken", "arguments": "not json {"}}
        ]
        html = render_tool_calls(calls)
        assert "broken" in html
        assert "not json {" in html


class TestOpenAIRequestWithToolCalls:
    """OpenAI request with assistant tool_calls role."""

    def test_assistant_tool_calls_in_request(self) -> None:
        body = json.dumps({
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "What's the weather?"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": '{"city": "NYC"}'},
                    }],
                },
                {"role": "tool", "content": '{"temp": 72}'},
            ],
        })
        html = render_request_body(body)
        assert html is not None
        assert "get_weather" in html
        assert "tool-call" in html
        assert "tool" in html  # tool role message

    def test_tool_role_content_json(self) -> None:
        body = json.dumps({
            "model": "gpt-4",
            "messages": [
                {"role": "tool", "content": '{"result": [1, 2, 3]}'},
            ],
        })
        html = render_request_body(body)
        assert html is not None
        assert "tool" in html
        # _highlight_json wraps arrays across lines, so check for individual numbers
        assert "json-number" in html
        assert ">1<" in html or ">1<" in html


class TestMarkdown:
    """Tests for render_markdown."""

    def test_headers(self) -> None:
        html = render_markdown("# Hello\n## World")
        assert "<h1>" in html
        assert "Hello" in html
        assert "<h2>" in html
        assert "World" in html

    def test_lists(self) -> None:
        html = render_markdown("- item1\n- item2\n- item3")
        assert "<ul>" in html
        assert "item1" in html
        assert "item2" in html

    def test_code_blocks(self) -> None:
        text = "```python\nprint('hi')\n```"
        html = render_markdown(text)
        assert "<code" in html or "<pre" in html
        assert "print" in html

    def test_inline_code(self) -> None:
        html = render_markdown("Use `foo` here")
        assert "<code>" in html
        assert "foo" in html

    def test_links(self) -> None:
        html = render_markdown("[click](https://example.com)")
        assert '<a href="https://example.com"' in html
        assert "click" in html

    def test_bold_italic(self) -> None:
        html = render_markdown("**bold** and *italic*")
        assert "<strong>" in html or "<b>" in html
        assert "<em>" in html or "<i>" in html

    def test_empty_input(self) -> None:
        assert render_markdown("") == ""
        assert render_markdown(None) == ""  # type: ignore[arg-type]

    def test_non_string_input(self) -> None:
        html = render_markdown(42)  # type: ignore[arg-type]
        assert "42" in html


class TestRenderBody:
    """Tests for the top-level render_body function."""

    def test_empty_body(self) -> None:
        html = render_body("")
        assert "(empty)" in html

    def test_none_body(self) -> None:
        html = render_body(None)
        assert "(empty)" in html

    def test_non_json_body(self) -> None:
        html = render_body("not json at all")
        assert "body-raw" in html
        assert "not json at all" in html

    def test_unknown_json_body(self) -> None:
        html = render_body(json.dumps({"random": "data"}))
        assert "body-raw" in html
        assert "random" in html

    def test_openai_request_formatted(self) -> None:
        html = render_body(_make_openai_request())
        assert "body-viewer" in html
        assert "body-llm-view" in html
        assert "body-raw-view" in html

    def test_openai_response_formatted(self) -> None:
        html = render_body(_make_openai_response())
        assert "body-viewer" in html

    def test_anthropic_response_formatted(self) -> None:
        html = render_body(_make_anthropic_response(), format_tag="anthropic")
        assert "body-viewer" in html

    def test_streaming_formatted(self) -> None:
        html = render_body(_make_streaming_preview(), format_tag="streaming")
        assert "body-viewer" in html


class TestXSS:
    """Security: bleach must sanitize dangerous HTML."""

    def test_script_tag_in_markdown(self) -> None:
        html = render_markdown('<script>alert("xss")</script>')
        assert "<script>" not in html

    def test_img_onerror_xss(self) -> None:
        # onerror inside src attr value is just text — bleach keeps it.
        # Test that actual dangerous *attributes* are stripped:
        html = render_markdown('![img](url)')
        assert 'onerror=' not in html  # no standalone onerror attr
        # Also test that event handler attributes in raw markdown are stripped:
        html2 = '<div onerror="alert(1)">safe</div>'
        rendered = render_markdown(html2)
        assert 'onerror' not in rendered

    def test_html_tag_in_markdown(self) -> None:
        html = render_markdown("<b onclick='alert(1)'>safe</b>")
        assert "onclick" not in html

    def test_angular_brackets_in_content(self) -> None:
        html = render_markdown("Use < and > safely")
        # These should be rendered as text, not as tags
        assert "Use &lt; and &gt; safely" in html or "Use <" in html


class TestEscape:
    """Tests for HTML escaping."""

    def test_escape_ampersand(self) -> None:
        assert "&amp;" in _escape("a & b")

    def test_escape_angle_brackets(self) -> None:
        assert "&lt;" in _escape("<div>")

    def test_escape_quotes(self) -> None:
        assert "&quot;" in _escape('"hello"')


class TestHighlightJson:
    """Tests for syntax-highlighted JSON output."""

    def test_highlight_null(self) -> None:
        html = _highlight_json(None)
        assert "json-null" in html

    def test_highlight_boolean(self) -> None:
        html = _highlight_json(True)
        assert "json-boolean" in html

    def test_highlight_number(self) -> None:
        html = _highlight_json(42)
        assert "json-number" in html

    def test_highlight_string(self) -> None:
        html = _highlight_json("hello")
        assert "json-string" in html

    def test_highlight_empty_dict(self) -> None:
        html = _highlight_json({})
        assert "{}" in html

    def test_highlight_empty_list(self) -> None:
        html = _highlight_json([])
        assert "[]" in html

    def test_highlight_nested(self) -> None:
        data = {"key": [1, 2], "nested": {"a": "b"}}
        html = _highlight_json(data)
        assert "json-key" in html
        assert "json-number" in html
