"""Translate the Responses API to Chat Completions and back.

Pure functions. The Responses-only pass-through does not use this module:
its normalizations belong to that upstream, not to Chat Completions providers.
"""

from __future__ import annotations

import json
import uuid
from typing import Any


class UnsupportedResponsesFeature(Exception):
    """A Responses field that cannot be represented without lying."""

    def __init__(self, field: str, message: str | None = None) -> None:
        self.field = field
        self.message = message or (
            f"Responses feature '{field}' cannot be translated to chat completions."
        )
        super().__init__(self.message)


_DROPPED_REQUEST_FIELDS = (
    "reasoning",
    "include",
    "stream_options",
    "service_tier",
    "prompt_cache_key",
    "client_metadata",
    "access_programs",
)

_REFUSED_INPUT_TYPES = {
    "additional_tools",
    "agent_message",
    "local_shell_call",
    "web_search_call",
    "tool_search_call",
    "tool_search_output",
    "image_generation_call",
    "compaction",
    "mcp_call",
    "mcp_tool_call",
    "computer_call",
    "computer_call_output",
}


def responses_to_chat_request(body: dict[str, Any], upstream_model: str) -> dict[str, Any]:
    """Convert a Responses request into a chat-completions body.

    ``custom_tool_names`` is gateway metadata. The caller must pop it before
    the body is sent upstream.
    """
    if not isinstance(body, dict):
        raise UnsupportedResponsesFeature("body", "Responses body must be an object.")
    if body.get("previous_response_id"):
        raise UnsupportedResponsesFeature(
            "previous_response_id",
            "previous_response_id cannot be translated. Send the whole conversation in 'input'.",
        )
    if body.get("store") is True:
        raise UnsupportedResponsesFeature(
            "store",
            "store: true cannot be honored by a chat-completions provider.",
        )
    if body.get("background"):
        raise UnsupportedResponsesFeature("background")
    if body.get("conversation"):
        raise UnsupportedResponsesFeature("conversation")

    custom_names: list[str] = []
    chat: dict[str, Any] = {
        "model": upstream_model,
        "messages": _messages(body, custom_names),
    }
    tools = _tools(body.get("tools"), custom_names)
    if tools:
        chat["tools"] = tools
    if "tool_choice" in body:
        chat["tool_choice"] = _tool_choice(body.get("tool_choice"))
    if "parallel_tool_calls" in body:
        chat["parallel_tool_calls"] = bool(body.get("parallel_tool_calls"))
    if body.get("max_output_tokens") is not None:
        chat["max_tokens"] = body["max_output_tokens"]
    if body.get("temperature") is not None:
        chat["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        chat["top_p"] = body["top_p"]
    response_format = _response_format(body.get("text"))
    if response_format is not None:
        chat["response_format"] = response_format
    if custom_names:
        chat["custom_tool_names"] = custom_names
    return chat


def chat_completion_to_response(
    chat: dict[str, Any],
    *,
    model: str,
    custom_tool_names: set[str],
    response_id: str | None = None,
) -> dict[str, Any]:
    """Build the Responses object a non-streaming client, and response.completed, expect."""
    choice = _first_choice(chat)
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    finish = choice.get("finish_reason")
    output = _output_items(message, custom_tool_names)
    result: dict[str, Any] = {
        "id": response_id or _response_id(chat.get("id")),
        "object": "response",
        "status": "incomplete" if finish == "length" else "completed",
        "model": model,
        "output": output,
    }
    if finish == "length":
        result["incomplete_details"] = {"reason": "max_output_tokens"}
    usage = _responses_usage(chat.get("usage"))
    if usage is not None:
        result["usage"] = usage
    return result


class ChatToResponsesStreamConverter:
    """Turn chat-completions SSE chunks into Responses SSE frames Codex parses."""

    def __init__(self, *, model: str, custom_tool_names: set[str]) -> None:
        self.model = model
        self.custom_tool_names = custom_tool_names
        self.response_id = _new_id("resp")
        self._seq = 0
        self._started = False
        self._text_open = False
        self._closed = False
        self._text = ""
        self._message_id = _new_id("msg")
        self._tools: dict[int, dict[str, str]] = {}
        self._usage: dict[str, Any] | None = None
        self._finish_reason: str | None = None

    def feed(self, chunk: dict[str, Any]) -> list[str]:
        if self._closed or not isinstance(chunk, dict):
            return []
        usage = chunk.get("usage")
        if isinstance(usage, dict):
            self._usage = usage
        frames: list[str] = []
        for choice in chunk.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            if choice.get("finish_reason"):
                self._finish_reason = choice["finish_reason"]
            delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
            text = delta.get("content")
            if isinstance(text, str) and text:
                frames.extend(self._open_text())
                self._text += text
                frames.append(
                    self._frame(
                        "response.output_text.delta",
                        delta=text,
                        item_id=self._message_id,
                        output_index=0,
                        content_index=0,
                    )
                )
            for call in delta.get("tool_calls") or []:
                if isinstance(call, dict):
                    self._accumulate_tool(call)
        return frames

    def finish(self) -> list[str]:
        if self._closed:
            return []
        self._closed = True
        frames: list[str] = []
        if not self._started:
            frames.append(self._created())
        if self._text_open:
            frames.extend(self._close_text())
        for item in self._tool_output_items():
            frames.append(self._frame("response.output_item.done", item=item, output_index=len(frames)))
        completed = chat_completion_to_response(
            self._as_chat(),
            model=self.model,
            custom_tool_names=self.custom_tool_names,
            response_id=self.response_id,
        )
        frames.append(self._frame("response.completed", response=completed))
        return frames

    def terminal_body(self) -> dict[str, Any]:
        """Client-visible object for telemetry, including after a partial stream."""
        return chat_completion_to_response(
            self._as_chat(),
            model=self.model,
            custom_tool_names=self.custom_tool_names,
            response_id=self.response_id,
        )

    @staticmethod
    def failure_frame(message: str) -> str:
        payload = {
            "type": "response.failed",
            "response": {
                "id": _new_id("resp"),
                "object": "response",
                "status": "failed",
                "error": {"message": message, "type": "server_error", "code": None},
            },
        }
        return f"event: response.failed\ndata: {json.dumps(payload)}\n\n"

    def _open_text(self) -> list[str]:
        frames: list[str] = []
        if not self._started:
            frames.append(self._created())
        if self._text_open:
            return frames
        self._text_open = True
        item = {
            "type": "message",
            "id": self._message_id,
            "role": "assistant",
            "content": [],
        }
        frames.append(self._frame("response.output_item.added", item=item, output_index=0))
        frames.append(
            self._frame(
                "response.content_part.added",
                item_id=self._message_id,
                output_index=0,
                content_index=0,
                part={"type": "output_text", "text": ""},
            )
        )
        return frames

    def _close_text(self) -> list[str]:
        item = {
            "type": "message",
            "id": self._message_id,
            "role": "assistant",
            "content": [{"type": "output_text", "text": self._text}],
        }
        return [
            self._frame("response.output_text.done", item_id=self._message_id, output_index=0, content_index=0, text=self._text),
            self._frame("response.content_part.done", item_id=self._message_id, output_index=0, content_index=0, part={"type": "output_text", "text": self._text}),
            self._frame("response.output_item.done", item=item, output_index=0),
        ]

    def _created(self) -> str:
        self._started = True
        return self._frame(
            "response.created",
            response={
                "id": self.response_id,
                "object": "response",
                "status": "in_progress",
                "model": self.model,
                "output": [],
            },
        )

    def _accumulate_tool(self, call: dict[str, Any]) -> None:
        index = call.get("index", 0)
        try:
            index = int(index)
        except (TypeError, ValueError):
            index = 0
        slot = self._tools.setdefault(index, {"id": "", "name": "", "arguments": ""})
        if isinstance(call.get("id"), str) and call["id"]:
            slot["id"] = call["id"]
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = function.get("name")
        if isinstance(name, str) and name:
            slot["name"] += name
        arguments = function.get("arguments")
        if isinstance(arguments, str) and arguments:
            slot["arguments"] += arguments

    def _tool_output_items(self) -> list[dict[str, Any]]:
        items = []
        for index in sorted(self._tools):
            slot = self._tools[index]
            items.append(
                _tool_call_item(
                    {
                        "id": slot["id"] or _new_id("call"),
                        "function": {"name": slot["name"], "arguments": slot["arguments"]},
                    },
                    self.custom_tool_names,
                )
            )
        return items

    def _as_chat(self) -> dict[str, Any]:
        tool_calls = []
        for index in sorted(self._tools):
            slot = self._tools[index]
            tool_calls.append(
                {
                    "id": slot["id"] or _new_id("call"),
                    "type": "function",
                    "function": {"name": slot["name"], "arguments": slot["arguments"]},
                }
            )
        message: dict[str, Any] = {"role": "assistant", "content": self._text or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        finish = self._finish_reason
        if finish is None:
            finish = "tool_calls" if tool_calls else "stop"
        chat: dict[str, Any] = {"choices": [{"message": message, "finish_reason": finish}]}
        if self._usage is not None:
            chat["usage"] = self._usage
        return chat

    def _frame(self, event_type: str, **fields: Any) -> str:
        payload = {"type": event_type, "sequence_number": self._seq, **fields}
        self._seq += 1
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _messages(body: dict[str, Any], custom_names: list[str]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    instructions = body.get("instructions")
    if isinstance(instructions, str) and instructions:
        messages.append({"role": "system", "content": instructions})
    raw = body.get("input")
    if isinstance(raw, str):
        messages.append({"role": "user", "content": raw})
        return messages
    if raw is None:
        raise UnsupportedResponsesFeature("input", "Responses request is missing 'input'.")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise UnsupportedResponsesFeature("input", "Responses 'input' must be a string or an array.")
    pending: list[dict[str, Any]] = []

    def flush() -> None:
        if pending:
            messages.append({"role": "assistant", "content": None, "tool_calls": list(pending)})
            pending.clear()

    for item in raw:
        if isinstance(item, str):
            flush()
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            raise UnsupportedResponsesFeature("input", "Responses input items must be objects.")
        kind = item.get("type")
        if kind == "reasoning":
            continue
        if kind in _REFUSED_INPUT_TYPES:
            raise UnsupportedResponsesFeature(str(kind))
        if kind in (None, "message") and "role" in item:
            flush()
            messages.append(_message_item(item))
            continue
        if kind in ("function_call", "custom_tool_call"):
            pending.append(_input_tool_call(item))
            continue
        if kind in ("function_call_output", "custom_tool_call_output"):
            flush()
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": str(item.get("call_id") or ""),
                    "content": _tool_output_text(item.get("output")),
                }
            )
            continue
        raise UnsupportedResponsesFeature(str(kind or "input"))
    flush()
    return messages


def _message_item(item: dict[str, Any]) -> dict[str, Any]:
    role = item.get("role") or "user"
    if role == "developer":
        role = "system"
    if role not in ("system", "user", "assistant", "tool"):
        role = "user"
    return {"role": role, "content": _content(item.get("content"))}


def _content(content: Any) -> Any:
    if isinstance(content, str) or content is None:
        return content or ""
    if not isinstance(content, list):
        raise UnsupportedResponsesFeature("content")
    parts: list[dict[str, Any]] = []
    for part in content:
        if isinstance(part, str):
            parts.append({"type": "text", "text": part})
            continue
        if not isinstance(part, dict):
            raise UnsupportedResponsesFeature("content")
        kind = part.get("type")
        if kind in ("input_text", "output_text", "text"):
            parts.append({"type": "text", "text": str(part.get("text") or "")})
            continue
        if kind == "input_image":
            if part.get("file_id"):
                raise UnsupportedResponsesFeature("file_id", "Image file_id cannot be translated.")
            url = part.get("image_url")
            if isinstance(url, dict):
                if url.get("file_id"):
                    raise UnsupportedResponsesFeature("file_id", "Image file_id cannot be translated.")
                url = url.get("url")
            if not isinstance(url, str) or not url:
                raise UnsupportedResponsesFeature("input_image")
            image: dict[str, Any] = {"url": url}
            if part.get("detail"):
                image["detail"] = part["detail"]
            parts.append({"type": "image_url", "image_url": image})
            continue
        if kind == "input_audio":
            raise UnsupportedResponsesFeature("input_audio")
        raise UnsupportedResponsesFeature(str(kind or "content"))
    if parts and all(part["type"] == "text" for part in parts):
        return "".join(part["text"] for part in parts)
    return parts


def _input_tool_call(item: dict[str, Any]) -> dict[str, Any]:
    name = str(item.get("name") or "")
    if item.get("type") == "custom_tool_call":
        arguments = item.get("input")
    else:
        arguments = item.get("arguments")
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments if arguments is not None else {})
    return {
        "id": str(item.get("call_id") or item.get("id") or _new_id("call")),
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _tools(raw: Any, custom_names: list[str]) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise UnsupportedResponsesFeature("tools")
    tools: list[dict[str, Any]] = []
    for tool in raw:
        if not isinstance(tool, dict):
            raise UnsupportedResponsesFeature("tools")
        kind = tool.get("type") or "function"
        if kind == "function":
            tools.append(_function_tool(tool))
        elif kind == "custom":
            name = tool.get("name")
            if not isinstance(name, str) or not name:
                raise UnsupportedResponsesFeature("custom", "Custom tool is missing a name.")
            custom_names.append(name)
            spec: dict[str, Any] = {
                "name": name,
                "parameters": {
                    "type": "object",
                    "properties": {"input": {"type": "string"}},
                    "required": ["input"],
                },
            }
            if tool.get("description"):
                spec["description"] = tool["description"]
            tools.append({"type": "function", "function": spec})
        else:
            raise UnsupportedResponsesFeature(str(kind))
    return tools


def _function_tool(tool: dict[str, Any]) -> dict[str, Any]:
    function = tool.get("function") if isinstance(tool.get("function"), dict) else tool
    name = function.get("name")
    if not isinstance(name, str) or not name:
        raise UnsupportedResponsesFeature("function", "Function tool is missing a name.")
    spec: dict[str, Any] = {"name": name}
    if function.get("description"):
        spec["description"] = function["description"]
    if function.get("parameters") is not None:
        spec["parameters"] = function["parameters"]
    return {"type": "function", "function": spec}


def _tool_choice(value: Any) -> Any:
    if value in ("auto", "none", "required"):
        return value
    if isinstance(value, dict) and value.get("type") == "function":
        name = value.get("name")
        nested = value.get("function")
        if not isinstance(name, str) and isinstance(nested, dict):
            name = nested.get("name")
        if isinstance(name, str) and name:
            return {"type": "function", "function": {"name": name}}
    raise UnsupportedResponsesFeature("tool_choice")


def _response_format(text: Any) -> dict[str, Any] | None:
    if not isinstance(text, dict):
        return None
    fmt = text.get("format")
    if not isinstance(fmt, dict) or not fmt:
        return None
    if fmt.get("type") != "json_schema":
        raise UnsupportedResponsesFeature("text.format")
    return {
        "type": "json_schema",
        "json_schema": {
            "name": fmt.get("name") or "response",
            "schema": fmt.get("schema") or {},
            "strict": bool(fmt.get("strict", False)),
        },
    }


def _first_choice(chat: dict[str, Any]) -> dict[str, Any]:
    choices = chat.get("choices") if isinstance(chat, dict) else None
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return choices[0]
    return {}


def _output_items(message: dict[str, Any], custom_tool_names: set[str]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    content = message.get("content")
    text = _assistant_text(content)
    if text:
        output.append(
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        )
    for call in message.get("tool_calls") or []:
        if isinstance(call, dict):
            output.append(_tool_call_item(call, custom_tool_names))
    return output


def _assistant_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") in ("text", "output_text"):
                parts.append(str(part.get("text") or ""))
        return "".join(parts)
    return ""


def _tool_call_item(call: dict[str, Any], custom_tool_names: set[str]) -> dict[str, Any]:
    function = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = str(function.get("name") or call.get("name") or "")
    arguments = function.get("arguments", call.get("arguments"))
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments if arguments is not None else {})
    call_id = call.get("id") or call.get("call_id") or _new_id("call")
    call_id = str(call_id)
    if name in custom_tool_names:
        return {"type": "custom_tool_call", "name": name, "input": arguments, "call_id": call_id}
    return {"type": "function_call", "name": name, "arguments": arguments, "call_id": call_id}


def _tool_output_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        parts = []
        for part in output:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
            else:
                parts.append(json.dumps(part))
        return "".join(parts)
    if output is None:
        return ""
    return json.dumps(output)


def _responses_usage(raw: Any) -> dict[str, int] | None:
    if not isinstance(raw, dict):
        return None

    def integer(value: Any) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    input_tokens = integer(raw.get("input_tokens", raw.get("prompt_tokens")))
    output_tokens = integer(raw.get("output_tokens", raw.get("completion_tokens")))
    total_tokens = integer(raw.get("total_tokens"))
    if input_tokens is None or output_tokens is None:
        return None
    if total_tokens is None:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _response_id(raw: Any) -> str:
    if isinstance(raw, str) and raw:
        return raw if raw.startswith("resp_") else f"resp_{raw}"
    return _new_id("resp")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
