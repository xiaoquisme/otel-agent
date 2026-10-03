"""Unit tests for StreamCapture — reassembled streaming telemetry bodies."""

from __future__ import annotations

import json

from otel_agent.stream_capture import StreamCapture


class TestOpenAIChunks:
    def test_content_reasoning_finish_and_model(self) -> None:
        cap = StreamCapture()
        cap.feed({"model": "gpt-4", "choices": [{"index": 0, "delta": {"content": "Hel"}}]})
        cap.feed({"choices": [{"index": 0, "delta": {"reasoning_content": "think"}}]})
        cap.feed({"choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": "stop"}]})
        body = cap.snapshot()
        assert body["streamed"] is True
        assert body["model"] == "gpt-4"
        assert body["content"] == "Hello"
        assert body["reasoning_content"] == "think"
        assert body["finish_reason"] == "stop"

    def test_tool_calls_accumulate_arguments(self) -> None:
        cap = StreamCapture()
        cap.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "id": "call_1", "function": {"name": "lookup", "arguments": ""}},
        ]}}]})
        cap.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": '{"key": '}},
        ]}}]})
        cap.feed({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": '"v"}'}},
        ]}}]})
        body = cap.snapshot()
        assert body["tool_calls"] == [
            {"id": "call_1", "name": "lookup", "arguments": '{"key": "v"}'},
        ]

    def test_usage_kept_raw_including_cache_details(self) -> None:
        cap = StreamCapture()
        cap.feed({"choices": [{"index": 0, "delta": {"content": "x"}}]})
        cap.feed({"choices": [], "usage": {
            "prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105,
            "prompt_tokens_details": {"cached_tokens": 90, "audio_tokens": 0},
        }})
        body = cap.snapshot()
        assert body["usage"] == {
            "prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105,
            "prompt_tokens_details": {"cached_tokens": 90, "audio_tokens": 0},
        }

    def test_null_usage_chunks_ignored(self) -> None:
        cap = StreamCapture()
        cap.feed({"choices": [{"index": 0, "delta": {"content": "x"}}], "usage": None})
        body = cap.snapshot()
        assert "usage" not in body

    def test_no_usage_key_absent_from_snapshot(self) -> None:
        cap = StreamCapture()
        cap.feed({"choices": [{"index": 0, "delta": {"content": "x"}}]})
        assert "usage" not in cap.snapshot()

    def test_later_usage_wins_partials(self) -> None:
        cap = StreamCapture()
        cap.feed({"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}})
        cap.feed({"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 9, "total_tokens": 19}})
        body = cap.snapshot()
        assert body["usage"]["completion_tokens"] == 9
        assert body["usage"]["total_tokens"] == 19


class TestAnthropicEvents:
    def test_full_message_flow(self) -> None:
        cap = StreamCapture()
        cap.feed({
            "type": "message_start",
            "message": {
                "model": "claude-sonnet-4", "role": "assistant",
                "usage": {"input_tokens": 42, "output_tokens": 0,
                          "cache_read_input_tokens": 1000,
                          "cache_creation_input_tokens": 20},
            },
        })
        cap.feed({"type": "content_block_start", "index": 0,
                  "content_block": {"type": "text", "text": ""}})
        cap.feed({"type": "content_block_delta", "index": 0,
                  "delta": {"type": "thinking_delta", "thinking": "hmm"}})
        cap.feed({"type": "content_block_delta", "index": 0,
                  "delta": {"type": "text_delta", "text": "Hello"}})
        cap.feed({"type": "content_block_start", "index": 1,
                  "content_block": {"type": "tool_use", "id": "toolu_1", "name": "read_file"}})
        cap.feed({"type": "content_block_delta", "index": 1,
                  "delta": {"type": "input_json_delta", "partial_json": '{"path": "/x"}}'}})
        cap.feed({"type": "message_delta", "delta": {"stop_reason": "tool_use"},
                  "usage": {"output_tokens": 8}})
        cap.feed({"type": "message_stop"})

        body = cap.snapshot()
        assert body["model"] == "claude-sonnet-4"
        assert body["content"] == "Hello"
        assert body["reasoning_content"] == "hmm"
        assert body["tool_calls"] == [
            {"id": "toolu_1", "name": "read_file", "arguments": '{"path": "/x"}}'},
        ]
        assert body["finish_reason"] == "tool_use"
        # Raw usage merged across message_start + message_delta, cache fields kept.
        assert body["usage"] == {
            "input_tokens": 42, "output_tokens": 8,
            "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 20,
        }


class TestResponsesEvents:
    def test_full_response_flow(self) -> None:
        cap = StreamCapture()
        cap.feed({"type": "response.created",
                  "response": {"id": "resp_1", "model": "gpt-5-codex", "status": "in_progress"}})
        cap.feed({"type": "response.output_item.added", "output_index": 0,
                  "item": {"type": "message", "id": "msg_1"}})
        cap.feed({"type": "response.output_text.delta", "output_index": 0, "delta": "Hel"})
        cap.feed({"type": "response.output_text.delta", "output_index": 0, "delta": "lo"})
        cap.feed({"type": "response.output_item.added", "output_index": 1,
                  "item": {"type": "function_call", "id": "fc_1", "call_id": "call_1",
                           "name": "shell", "arguments": ""}})
        cap.feed({"type": "response.function_call_arguments.delta", "output_index": 1,
                  "delta": '{"cmd": "ls"}}'})
        cap.feed({"type": "response.completed", "response": {
            "id": "resp_1", "model": "gpt-5-codex", "status": "completed",
            "usage": {"input_tokens": 12, "output_tokens": 1, "total_tokens": 13,
                      "input_tokens_details": {"cached_tokens": 10}},
        }})

        body = cap.snapshot()
        assert body["model"] == "gpt-5-codex"
        assert body["content"] == "Hello"
        assert body["tool_calls"] == [
            {"id": "call_1", "name": "shell", "arguments": '{"cmd": "ls"}}'},
        ]
        assert body["finish_reason"] == "stop"
        assert body["usage"]["input_tokens_details"] == {"cached_tokens": 10}

    def test_incomplete_reason_reported(self) -> None:
        cap = StreamCapture()
        cap.feed({"type": "response.incomplete", "response": {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
        }})
        assert cap.snapshot()["finish_reason"] == "max_output_tokens"

    def test_reasoning_summary_deltas(self) -> None:
        cap = StreamCapture()
        cap.feed({"type": "response.reasoning_summary_text.delta", "delta": "step 1"})
        assert cap.snapshot()["reasoning_content"] == "step 1"


class TestBounds:
    def test_text_limit_marks_truncation(self) -> None:
        cap = StreamCapture(text_limit=5)
        cap.feed({"choices": [{"index": 0, "delta": {"content": "abcdef"}}]})
        cap.feed({"choices": [{"index": 0, "delta": {"content": "more"}}]})
        body = cap.snapshot()
        assert body["content"] == "abcde"
        assert body["content_truncated"] is True

    def test_limit_shared_across_fields(self) -> None:
        cap = StreamCapture(text_limit=6)
        cap.feed({"choices": [{"index": 0, "delta": {"content": "abcd"}}]})
        cap.feed({"choices": [{"index": 0, "delta": {"reasoning_content": "efgh"}}]})
        body = cap.snapshot()
        assert body["content"] == "abcd"
        assert body["reasoning_content"] == "ef"
        assert body["content_truncated"] is True

    def test_not_marked_when_under_limit(self) -> None:
        cap = StreamCapture()
        cap.feed({"choices": [{"index": 0, "delta": {"content": "hi"}}]})
        assert "content_truncated" not in cap.snapshot()

    def test_empty_stream(self) -> None:
        body = StreamCapture().snapshot()
        assert body == {"streamed": True, "content": ""}

    def test_non_dict_chunks_ignored(self) -> None:
        cap = StreamCapture()
        cap.feed(["not", "a", "dict"])  # type: ignore[arg-type]
        cap.feed("stringy")  # type: ignore[arg-type]
        assert cap.snapshot() == {"streamed": True, "content": ""}


class TestSnapshotShape:
    def test_usage_leads_the_snapshot(self) -> None:
        """Usage must survive even if a downstream size-cuts the serialized
        body from the tail."""
        cap = StreamCapture()
        cap.feed({"choices": [{"index": 0, "delta": {"content": "x"}}],
                  "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
        body = cap.snapshot()
        keys = list(body)
        assert keys.index("usage") < keys.index("content")

    def test_snapshot_is_json_serializable(self) -> None:
        cap = StreamCapture()
        cap.feed({"choices": [{"index": 0, "delta": {"content": "x"}, "finish_reason": "stop"}]})
        assert json.loads(json.dumps(cap.snapshot())) == cap.snapshot()
