"""LLM body renderer — detects OpenAI/Anthropic/streaming formats and renders
request/response bodies to safe HTML for the dashboard."""

from __future__ import annotations

import json
from html import escape as _html_escape
from typing import Any

import bleach
import markdown as md

# ---------------------------------------------------------------------------
# Constants (mirrors JS MAX_BODY_LENGTH / MAX_TOOL_CONTENT_LENGTH)
# ---------------------------------------------------------------------------
MAX_TOOL_CONTENT_LENGTH = 8000

# Allowed bleach tags/attrs for rendered markdown (matches JS DOMPurify defaults)
_BLEACH_TAGS = {
    "p", "br", "strong", "em", "b", "i", "u", "s", "code", "pre",
    "a", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "table", "thead", "tbody", "tr", "th", "td",
    "hr", "img", "div", "span", "dl", "dt", "dd",
}
_BLEACH_ATTRS = {"a": ["href", "title", "target", "rel"], "img": ["src", "alt"], "div": ["class"], "span": ["class"]}

_md_ext = ["fenced_code", "tables", "nl2br"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape(s: Any) -> str:
    """HTML-escape a value (mirrors JS escapeHtml)."""
    return _html_escape(str(s))


def _highlight_json(value: Any, indent: int = 0) -> str:
    """Recursively render a Python object as syntax-highlighted HTML
    (mirrors JS highlightJsonString)."""
    pad = "  " * indent
    if value is None:
        return f'{pad}<span class="json-null">null</span>'
    if isinstance(value, bool):
        return f'{pad}<span class="json-boolean">{str(value).lower()}</span>'
    if isinstance(value, (int, float)):
        return f'{pad}<span class="json-number">{value}</span>'
    if isinstance(value, str):
        return f'{pad}<span class="json-string">"{_escape(value)}"</span>'

    if isinstance(value, list):
        if len(value) == 0:
            return f"{pad}[]"
        items = [_highlight_json(v, indent + 1) for v in value]
        return f"{pad}[\n" + ",\n".join(items) + f"\n{pad}]"

    if isinstance(value, dict):
        if len(value) == 0:
            return f"{pad}{{}}"
        entries = [
            f'{pad}  <span class="json-key">"{_escape(k)}"</span>: '
            + _highlight_json(v, indent + 1).strip()
            for k, v in value.items()
        ]
        return f"{pad}{{\n" + ",\n".join(entries) + f"\n{pad}}}"

    return pad + str(value)


def _is_truncated(body: str, max_len: int) -> dict[str, Any]:
    """Check if a body string is truncated (mirrors JS isTruncated)."""
    if not body:
        return {"truncated": False}
    if len(body) < max_len:
        return {"truncated": False}
    try:
        json.loads(body)
        return {"truncated": False}
    except json.JSONDecodeError:
        pass
    kb = round(max_len / 1000)
    return {"truncated": True, "reason": f"Body truncated (original exceeded {kb}KB)"}


# ---------------------------------------------------------------------------
# Public: Markdown
# ---------------------------------------------------------------------------

def render_markdown(text: str) -> str:
    """Convert markdown *text* to sanitized HTML."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    try:
        html = md.markdown(text, extensions=_md_ext)
        return bleach.clean(html, tags=_BLEACH_TAGS, attributes=_BLEACH_ATTRS)
    except Exception:
        return f"<pre>{_escape(text)}</pre>"


# ---------------------------------------------------------------------------
# Public: Tool calls
# ---------------------------------------------------------------------------

def render_tool_calls(tool_calls: list[dict[str, Any]]) -> str:
    """Render a list of tool-call dicts as HTML blocks.

    Each dict is expected to have ``function.name`` and ``function.arguments``
    (OpenAI format) or ``name`` / ``input`` (Anthropic-style).
    """
    parts: list[str] = []
    for tc in tool_calls:
        # Support both OpenAI (function.*) and flat name/input shapes
        fn = tc.get("function", tc)
        name = fn.get("name") or "tool"
        raw_args = fn.get("arguments") or fn.get("input") or ""
        if isinstance(raw_args, dict):
            args_text = json.dumps(raw_args, indent=2)
        elif isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
                args_text = json.dumps(parsed, indent=2)
            except (json.JSONDecodeError, TypeError):
                args_text = raw_args
        else:
            args_text = str(raw_args)
        parts.append(
            '<div class="tool-call">'
            f'<span class="tool-call-name">{_escape(name)}</span>'
            f'<div class="tool-call-args">{_escape(args_text)}</div>'
            "</div>"
        )
    return "".join(parts)


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def _parse_body(body: str) -> Any:
    """Safely parse a JSON body string; return None on failure."""
    if not body:
        return None
    try:
        return json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None


def detect_format(body: str, format_tag: str | None = None) -> str:
    """Detect the LLM format of a body string.

    Returns one of: ``"openai"``, ``"anthropic"``, ``"streaming"``, ``"unknown"``.
    Uses *format_tag* from storage when available; otherwise applies the same
    heuristic as the JS ``detectFormat`` function.
    """
    if format_tag:
        tag = format_tag.lower().strip()
        if "stream" in tag:
            return "streaming"
        if "anthropic" in tag or "claude" in tag:
            return "anthropic"
        if "openai" in tag or "gpt" in tag:
            return "openai"

    parsed = _parse_body(body)
    if not parsed or not isinstance(parsed, dict):
        return "unknown"

    # Streaming preview
    if parsed.get("streamed") and parsed.get("preview"):
        return "streaming"
    # OpenAI response
    if isinstance(parsed.get("choices"), list):
        return "openai"
    # Anthropic response
    if (
        isinstance(parsed.get("content"), list)
        and parsed.get("type") == "message"
    ):
        return "anthropic"
    # OpenAI request (has messages + model but NO max_tokens)
    if (
        isinstance(parsed.get("messages"), list)
        and parsed.get("model")
        and parsed.get("max_tokens") is None
    ):
        return "openai"
    # Anthropic request (has messages + max_tokens)
    if isinstance(parsed.get("messages"), list) and parsed.get("max_tokens") is not None:
        return "anthropic"

    return "unknown"


# ---------------------------------------------------------------------------
# Internal: streaming chunk parser
# ---------------------------------------------------------------------------

def _parse_streaming_chunks(preview_str: str) -> list[dict[str, Any]]:
    """Parse concatenated JSON chunks (mirrors JS parseStreamingChunks)."""
    chunks: list[dict[str, Any]] = []
    depth = 0
    start = -1
    for i, ch in enumerate(preview_str):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    chunk = json.loads(preview_str[start : i + 1])
                    if isinstance(chunk, dict):
                        chunks.append(chunk)
                except json.JSONDecodeError:
                    pass
                start = -1

    # Handle incomplete trailing chunk
    if depth > 0 and start >= 0:
        tail = preview_str[start:]
        try:
            chunk = json.loads(tail)
            if isinstance(chunk, dict):
                chunks.append(chunk)
        except json.JSONDecodeError:
            for close in range(1, depth + 1):
                try:
                    chunk = json.loads(tail + "}" * close)
                    if isinstance(chunk, dict):
                        chunks.append(chunk)
                    break
                except json.JSONDecodeError:
                    pass
    return chunks


# ---------------------------------------------------------------------------
# Internal: content extractors
# ---------------------------------------------------------------------------

def _extract_openai_request(parsed: dict[str, Any]) -> list[dict[str, str]] | None:
    """Extract chat messages from an OpenAI-style request body."""
    messages = parsed.get("messages")
    if not messages or not isinstance(messages, list):
        return None

    result: list[dict[str, str]] = []
    for m in messages:
        role = m.get("role", "unknown")
        # Assistant messages with tool_calls
        if role == "assistant" and m.get("tool_calls"):
            content_parts: list[str] = []
            if m.get("content"):
                content_parts.append(render_markdown(m["content"]))
            tc_html = render_tool_calls(m["tool_calls"])
            content_parts.append(tc_html)
            result.append({"role": role, "content": "".join(content_parts)})
            continue
        # Tool messages
        if role == "tool":
            raw = m.get("content", "")
            try:
                parsed_content = json.loads(raw) if isinstance(raw, str) else raw
                content = json.dumps(parsed_content, indent=2) if isinstance(parsed_content, (dict, list)) else str(raw)
            except (json.JSONDecodeError, TypeError):
                content = str(raw)
            result.append({"role": role, "content": content})
            continue

        result.append({"role": role, "content": m.get("content", "")})
    return result


def _extract_anthropic_request(parsed: dict[str, Any]) -> list[dict[str, str]] | None:
    """Extract chat messages from an Anthropic-style request body."""
    messages = parsed.get("messages")
    if not messages or not isinstance(messages, list):
        return None

    result: list[dict[str, str]] = []

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


def _extract_streaming_content(parsed: dict[str, Any]) -> dict[str, Any] | None:
    """Extract concatenated content from a streaming preview object."""
    preview = parsed.get("preview")
    if not preview:
        return None
    chunks = _parse_streaming_chunks(preview)
    if not chunks:
        return None

    content = ""
    reasoning_content = ""
    model = ""
    finish_reason = ""
    tool_calls: dict[int, dict[str, str]] = {}

    for chunk in chunks:
        if chunk.get("model"):
            model = chunk["model"]
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
                    tool_calls[idx] = {"id": "", "name": "", "args": ""}
                if tc.get("id"):
                    tool_calls[idx]["id"] = tc["id"]
                if tc.get("function"):
                    if tc["function"].get("name"):
                        tool_calls[idx]["name"] = tc["function"]["name"]
                    if tc["function"].get("arguments"):
                        tool_calls[idx]["args"] += tc["function"]["arguments"]

    tc_list = list(tool_calls.values())
    incomplete = not content and not reasoning_content and len(tc_list) == 0

    full_content = content
    if reasoning_content:
        full_content = content + "\n\n---\n**Reasoning:** " + reasoning_content

    is_html = False
    if tc_list:
        tc_html = render_tool_calls(tc_list)
        if full_content:
            full_content = render_markdown(full_content) + tc_html
        else:
            full_content = tc_html
        is_html = True

    return {
        "content": full_content,
        "model": model,
        "finish_reason": finish_reason or "streaming",
        "incomplete": incomplete,
        "is_html": is_html,
    }


def _extract_openai_response(parsed: dict[str, Any]) -> dict[str, Any] | None:
    """Extract content from an OpenAI-style response body."""
    choices = parsed.get("choices")
    if not choices or not isinstance(choices, list) or len(choices) == 0:
        return None
    choice = choices[0]
    msg = choice.get("message") or choice.get("delta") or {}
    return {
        "content": msg.get("content", ""),
        "model": parsed.get("model", ""),
        "finish_reason": choice.get("finish_reason", ""),
    }


def _extract_anthropic_response(parsed: dict[str, Any]) -> dict[str, Any] | None:
    """Extract content from an Anthropic-style response body."""
    content = parsed.get("content")
    if not content or not isinstance(content, list):
        return None
    text_blocks = [b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return {
        "content": "\n\n".join(text_blocks),
        "model": parsed.get("model", ""),
        "stop_reason": parsed.get("stop_reason", ""),
    }


# ---------------------------------------------------------------------------
# Internal: chat message renderer
# ---------------------------------------------------------------------------

def _render_chat_message(role: str, content: str, is_html: bool = False) -> str:
    """Render a single chat message as an HTML bubble."""
    role_class = f"chat-{role or 'unknown'}"
    if role == "tool":
        # Tool messages: render as monospace preformatted text
        truncated = content
        is_long = len(content) > MAX_TOOL_CONTENT_LENGTH
        if is_long:
            truncated = content[:MAX_TOOL_CONTENT_LENGTH]
        try:
            parsed = json.loads(truncated)
            rendered = _highlight_json(parsed, 0)
        except (json.JSONDecodeError, TypeError):
            rendered = _escape(truncated)
        return (
            f'<div class="chat-message {role_class}">'
            f'<span class="chat-role">tool</span>'
            f'<div class="chat-content"><pre>{rendered}</pre></div>'
            f"</div>"
        )

    # Callers set is_html=True when content was assembled by render_tool_calls().
    # No heuristic string-matching — that created an injection vector where
    # user content containing "tool-call" bypassed bleach sanitization.

    if is_html:
        rendered_content = content
    else:
        rendered_content = render_markdown(content) if content else ""
    return (
        f'<div class="chat-message {role_class}">'
        f'<span class="chat-role">{_escape(role)}</span>'
        f'<div class="chat-content">{rendered_content}</div>'
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Public: render_request_body / render_response_body
# ---------------------------------------------------------------------------

def render_request_body(body: str, format_tag: str | None = None) -> str | None:
    """Render an LLM request body to HTML chat bubbles.

    Returns the HTML string, or ``None`` if the body is not a recognised LLM
    request format.
    """
    fmt = detect_format(body, format_tag)
    parsed = _parse_body(body)

    messages: list[dict[str, str]] | None = None
    if fmt == "openai" and isinstance(parsed, dict):
        messages = _extract_openai_request(parsed)
    elif fmt == "anthropic" and isinstance(parsed, dict):
        messages = _extract_anthropic_request(parsed)

    if not messages:
        return None

    return "".join(_render_chat_message(m["role"], m["content"]) for m in messages)


def render_response_body(body: str, format_tag: str | None = None) -> str | None:
    """Render an LLM response body to HTML with metadata badges.

    Returns the HTML string, or ``None`` if the body is not a recognised LLM
    response format.
    """
    fmt = detect_format(body, format_tag)
    parsed = _parse_body(body)

    data: dict[str, Any] | None = None
    if fmt == "streaming" and isinstance(parsed, dict):
        data = _extract_streaming_content(parsed)
    elif fmt == "openai" and isinstance(parsed, dict):
        data = _extract_openai_response(parsed)
    elif fmt == "anthropic" and isinstance(parsed, dict):
        data = _extract_anthropic_response(parsed)

    if not data:
        return None

    # Metadata badges
    meta_html = '<div class="response-meta">'
    if data.get("model"):
        meta_html += f'<span class="response-meta-badge model">{_escape(data["model"])}</span>'
    finish = data.get("finish_reason") or data.get("stop_reason")
    if finish:
        meta_html += f'<span class="response-meta-badge finish">{_escape(finish)}</span>'
    meta_html += "</div>"

    # Content
    content_raw = data.get("content", "")
    if data.get("is_html"):
        content_html = content_raw
    else:
        content_html = render_markdown(content_raw)

    incomplete_note = ""
    if data.get("incomplete"):
        incomplete_note = (
            '<div class="streaming-incomplete">'
            "Streaming preview may be incomplete \u2014 limited chunks captured"
            "</div>"
        )

    return (
        f"{meta_html}"
        f'<div class="chat-message chat-assistant">'
        f'<div class="chat-content">{content_html}</div>'
        f"</div>"
        f"{incomplete_note}"
    )


def render_body(body: str | None, context: str = "request", format_tag: str | None = None) -> str:
    """Top-level body renderer (mirrors JS formatBody).

    Returns a full HTML string with an LLM-formatted view when the body is a
    recognised LLM format, or a raw JSON view otherwise.  Handles empty bodies
    and truncation.
    """
    if not body:
        return '<div class="body-empty">(empty)</div>'

    parsed = _parse_body(body)
    if parsed is None:
        # Not valid JSON
        t = _is_truncated(body, 100_000)
        notice = (
            f'<div class="body-truncated">{_escape(t["reason"])}</div>'
            if t["truncated"]
            else '<div style="color:#8b949e;font-size:12px;margin-top:4px;">Content is not valid JSON</div>'
        )
        return f'<div class="body-raw">{notice}<pre>{_escape(body)}</pre></div>'

    fmt = detect_format(body, format_tag)
    if fmt != "unknown":
        llm_html: str | None = None
        if fmt in ("openai", "anthropic"):
            llm_html = render_request_body(body, format_tag) or render_response_body(body, format_tag)
        elif fmt == "streaming":
            llm_html = render_response_body(body, format_tag)

        if llm_html:
            raw_html = f"<pre>{_highlight_json(parsed, 0)}</pre>"
            return (
                '<div class="body-viewer">'
                '<div class="body-toggle-bar">'
                '<button class="body-toggle-btn active">Formatted</button>'
                '<button class="body-toggle-btn">Raw</button>'
                "</div>"
                f'<div class="body-llm-view">{llm_html}</div>'
                f'<div class="body-raw-view" style="display:none">{raw_html}</div>'
                "</div>"
            )

    return f'<div class="body-raw"><pre>{_highlight_json(parsed, 0)}</pre></div>'
