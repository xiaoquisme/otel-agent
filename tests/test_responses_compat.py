"""Responses-to-chat-completions translation. No I/O."""

import json

import pytest

from otel_agent.responses_compat import (
    ChatToResponsesStreamConverter,
    UnsupportedResponsesFeature,
    chat_completion_to_response,
    responses_to_chat_request,
)


def test_instructions_and_string_input_become_messages():
    chat = responses_to_chat_request(
        {"model": "deepseek/deepseek-v4-pro", "instructions": "Be brief.", "input": "Reply with exactly: OK"},
        upstream_model="deepseek-v4-pro",
    )
    assert chat["model"] == "deepseek-v4-pro"
    assert chat["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Reply with exactly: OK"},
    ]
    assert "stream" not in chat


def test_message_items_keep_order_and_text_parts():
    chat = responses_to_chat_request(
        {
            "input": [
                {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]},
                {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hello"}]},
                {"type": "message", "role": "user", "content": "again"},
            ]
        },
        upstream_model="m",
    )
    assert chat["messages"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "again"},
    ]


def test_function_tool_round_trip_request():
    chat = responses_to_chat_request(
        {
            "input": [
                {"type": "message", "role": "user", "content": "run it"},
                {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "{\"cmd\":\"ls\"}",
                    "call_id": "call_1",
                },
                {"type": "function_call_output", "call_id": "call_1", "output": "file.txt"},
            ],
            "tools": [
                {
                    "type": "function",
                    "name": "shell",
                    "description": "Run a command",
                    "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}},
                }
            ],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
        },
        upstream_model="m",
    )
    assert chat["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "shell",
                "description": "Run a command",
                "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}},
            },
        }
    ]
    assert chat["tool_choice"] == "auto"
    assert chat["parallel_tool_calls"] is False
    assert chat["messages"][1] == {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "shell", "arguments": "{\"cmd\":\"ls\"}"},
            }
        ],
    }
    assert chat["messages"][2] == {"role": "tool", "tool_call_id": "call_1", "content": "file.txt"}


def test_custom_tool_is_recorded_as_a_string_function():
    chat = responses_to_chat_request(
        {
            "tools": [{"type": "custom", "name": "apply_patch", "description": "Patch files"}],
            "input": "go",
        },
        upstream_model="m",
    )
    assert chat["custom_tool_names"] == ["apply_patch"]
    assert chat["tools"][0]["function"]["name"] == "apply_patch"
    assert "input" in chat["tools"][0]["function"]["parameters"]["properties"]


def test_max_output_tokens_and_temperature_map():
    chat = responses_to_chat_request(
        {"input": "hi", "max_output_tokens": 16, "temperature": 0.2},
        upstream_model="m",
    )
    assert chat["max_tokens"] == 16
    assert chat["temperature"] == 0.2
    assert "max_output_tokens" not in chat


@pytest.mark.parametrize(
    "body,field",
    [
        ({"input": "hi", "previous_response_id": "resp_abc"}, "previous_response_id"),
        ({"input": "hi", "store": True}, "store"),
        ({"input": "hi", "tools": [{"type": "web_search"}]}, "web_search"),
        ({"input": "hi", "tools": [{"type": "namespace", "name": "fn"}]}, "namespace"),
        ({"input": [{"type": "message", "role": "user", "content": [{"type": "input_audio", "audio_url": "x"}]}]}, "input_audio"),
        ({"input": [{"type": "local_shell_call", "call_id": "c"}]}, "local_shell_call"),
    ],
)
def test_unsafe_fields_are_named_and_refused(body, field):
    with pytest.raises(UnsupportedResponsesFeature) as exc:
        responses_to_chat_request(body, upstream_model="m")
    assert field in str(exc.value)
    assert exc.value.field == field


def test_codex_always_sent_fields_are_dropped():
    chat = responses_to_chat_request(
        {
            "input": "hi",
            "reasoning": {"effort": "high"},
            "include": ["reasoning.encrypted_content"],
            "store": False,
            "stream_options": {"reasoning_summary_delivery": "sequential_cutoff"},
            "service_tier": "priority",
            "prompt_cache_key": "k",
            "client_metadata": {"a": "b"},
        },
        upstream_model="m",
    )
    for key in ("reasoning", "include", "store", "stream_options", "service_tier", "prompt_cache_key", "client_metadata"):
        assert key not in chat


def test_reasoning_items_in_input_are_omitted():
    chat = responses_to_chat_request(
        {
            "input": [
                {"type": "message", "role": "user", "content": "before"},
                {"type": "reasoning", "summary": [], "encrypted_content": "secret"},
                {"type": "message", "role": "user", "content": "after"},
            ]
        },
        upstream_model="m",
    )
    assert [m["content"] for m in chat["messages"]] == ["before", "after"]


def test_chat_completion_text_and_usage_become_a_responses_object():
    response = chat_completion_to_response(
        {
            "id": "chatcmpl_1",
            "choices": [{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
        },
        model="deepseek-v4-pro",
        custom_tool_names=set(),
    )
    assert response["id"]
    assert response["object"] == "response"
    assert response["status"] == "completed"
    assert response["model"] == "deepseek-v4-pro"
    assert response["output"] == [
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "OK"}],
        }
    ]
    assert response["usage"] == {"input_tokens": 3, "output_tokens": 1, "total_tokens": 4}


def test_missing_usage_is_omitted():
    response = chat_completion_to_response(
        {"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]},
        model="m",
        custom_tool_names=set(),
    )
    assert "usage" not in response
    assert isinstance(response["id"], str) and response["id"]


def test_length_finish_is_incomplete():
    response = chat_completion_to_response(
        {"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]},
        model="m",
        custom_tool_names=set(),
    )
    assert response["status"] == "incomplete"
    assert response["incomplete_details"]["reason"] == "max_output_tokens"


def test_function_and_custom_tool_calls_keep_their_item_types():
    response = chat_completion_to_response(
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_fn",
                                "type": "function",
                                "function": {"name": "shell", "arguments": "{\"cmd\":\"ls\"}"},
                            },
                            {
                                "id": "call_custom",
                                "type": "function",
                                "function": {"name": "apply_patch", "arguments": "*** Begin Patch"},
                            },
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        },
        model="m",
        custom_tool_names={"apply_patch"},
    )
    assert response["output"][0] == {
        "type": "function_call",
        "name": "shell",
        "arguments": "{\"cmd\":\"ls\"}",
        "call_id": "call_fn",
    }
    assert response["output"][1] == {
        "type": "custom_tool_call",
        "name": "apply_patch",
        "input": "*** Begin Patch",
        "call_id": "call_custom",
    }


def _events(frames: list[str]) -> list[tuple[str, dict]]:
    parsed = []
    for frame in frames:
        event = None
        data = None
        for line in frame.splitlines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        assert event and data and data["type"] == event
        parsed.append((event, data))
    return parsed


def test_stream_text_and_usage_match_codex_event_order():
    converter = ChatToResponsesStreamConverter(model="m", custom_tool_names=set())
    frames = []
    frames.extend(converter.feed({"choices": [{"index": 0, "delta": {"role": "assistant", "content": "O"}}]}))
    frames.extend(converter.feed({"choices": [{"index": 0, "delta": {"content": "K"}}]}))
    frames.extend(
        converter.feed(
            {
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            }
        )
    )
    frames.extend(converter.finish())
    events = _events(frames)
    names = [name for name, _ in events]
    assert names == [
        "response.created",
        "response.output_item.added",
        "response.content_part.added",
        "response.output_text.delta",
        "response.output_text.delta",
        "response.output_text.done",
        "response.content_part.done",
        "response.output_item.done",
        "response.completed",
    ]
    assert "data: [DONE]" not in "".join(frames)
    completed = events[-1][1]["response"]
    assert isinstance(completed["id"], str) and completed["id"]
    assert completed["usage"] == {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3}
    item = next(data["item"] for name, data in events if name == "response.output_item.done")
    assert item["content"] == [{"type": "output_text", "text": "OK"}]


def test_split_tool_call_arguments_are_one_function_item():
    converter = ChatToResponsesStreamConverter(model="m", custom_tool_names=set())
    frames = []
    frames.extend(
        converter.feed(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "id": "call_1", "function": {"name": "shell", "arguments": "{\"c"}}
                            ]
                        },
                    }
                ]
            }
        )
    )
    frames.extend(
        converter.feed(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"tool_calls": [{"index": 0, "function": {"arguments": "md\":\"ls\"}"}}]},
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        )
    )
    frames.extend(converter.finish())
    events = _events(frames)
    items = [data["item"] for name, data in events if name == "response.output_item.done"]
    assert items == [
        {
            "type": "function_call",
            "name": "shell",
            "arguments": "{\"cmd\":\"ls\"}",
            "call_id": "call_1",
        }
    ]
    assert events[-1][0] == "response.completed"


def test_custom_tool_stream_item():
    converter = ChatToResponsesStreamConverter(model="m", custom_tool_names={"apply_patch"})
    frames = list(
        converter.feed(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "id": "c1", "function": {"name": "apply_patch", "arguments": "patch"}}
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        )
    )
    frames.extend(converter.finish())
    items = [data["item"] for name, data in _events(frames) if name == "response.output_item.done"]
    assert items == [{"type": "custom_tool_call", "name": "apply_patch", "input": "patch", "call_id": "c1"}]


def test_upstream_failure_is_response_failed_without_completed():
    frame = ChatToResponsesStreamConverter.failure_frame("model rejected the parameter")
    events = _events([frame])
    assert events[0][0] == "response.failed"
    assert events[0][1]["response"]["error"]["message"] == "model rejected the parameter"
    assert "response.completed" not in frame
