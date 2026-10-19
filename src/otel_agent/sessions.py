"""Agent session ids carried on gateway requests.

A session is one agent run. ``X-Otel-Session`` wins, then ``X-Session-ID``,
then the Pi affinity headers (``session_id``, ``x-session-affinity``,
``x-client-request-id``). When every session header is missing or blank, a
deterministic ``inferred-`` id is taken from the conversation root in the
request body (leading system text plus the first user text). A payload with
no textual root stays null. ``X-Otel-Session-Step`` is only a label.
"""

from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)

SESSION_HEADER = "x-otel-session"
SESSION_HEADER_ALIAS = "x-session-id"
SESSION_STEP_HEADER = "x-otel-session-step"
# Lower priority than the two headers above. Pi sets all three to the same
# session id when ``sendSessionAffinityHeaders`` is on. ``x-client-request-id``
# is last because other clients use it as a per-request id.
SESSION_AFFINITY_HEADERS = (
    "session_id",
    "x-session-affinity",
    "x-client-request-id",
)

MAX_SESSION_ID_LEN = 256
MAX_SESSION_STEP_LEN = 128
SLOW_STEP_MS = 10_000
PREVIEW_CHARS = 160

INFERRED_SESSION_PREFIX = "inferred-"
_INFERRED_DIGEST_HEX = 16
_ROOT_VERSION = "v1"
_TEXT_PART_TYPES = frozenset({"text", "input_text", "output_text"})


def _header_value(headers: dict, name: str) -> str | None:
    """Return the first header value whose name matches, case-insensitively."""
    target = name.lower()
    for key, value in headers.items():
        if str(key).lower() != target:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        if value is None:
            return None
        return str(value)
    return None


def clean_session_label(value: str | None, limit: int) -> str | None:
    """Strip control characters and cap length. Blank becomes None."""
    if value is None:
        return None
    text = "".join(ch for ch in str(value) if ch >= " " and ch != "\x7f")
    text = text.strip()
    if not text:
        return None
    return text[:limit]


def session_fields_from_headers(headers: dict | None) -> tuple[str | None, str | None]:
    """Read ``(session_id, session_step)`` from a request header mapping.

    ``X-Otel-Session`` wins, then ``X-Session-ID``, then the Pi affinity
    headers in ``SESSION_AFFINITY_HEADERS``. The first non-blank value wins.
    ``X-Otel-Session-Step`` is an optional turn label and does not create a
    session by itself.
    """
    headers = headers or {}
    session_id = None
    for name in (SESSION_HEADER, SESSION_HEADER_ALIAS, *SESSION_AFFINITY_HEADERS):
        session_id = clean_session_label(_header_value(headers, name), MAX_SESSION_ID_LEN)
        if session_id is not None:
            break
    step = clean_session_label(
        _header_value(headers, SESSION_STEP_HEADER), MAX_SESSION_STEP_LEN
    )
    return session_id, step


def session_fields_from_request(
    headers: dict | None,
    body: str | bytes | dict | None = None,
) -> tuple[str | None, str | None]:
    """Header session id wins. Otherwise fingerprint the conversation root.

    ``session_step`` still comes only from ``X-Otel-Session-Step``.
    """
    session_id, step = session_fields_from_headers(headers)
    if session_id is None:
        session_id = infer_session_id(body)
    return session_id, step


def infer_session_id(body: str | bytes | dict | None) -> str | None:
    """Return ``inferred-<hex>`` for a stable conversation root, or None.

    The root is the leading system / developer text plus the first user text.
    Later turns are ignored, so a growing ``messages`` or Responses ``input``
    array keeps the same id. Empty bodies, image prompts, and chats with no
    textual user turn stay None. The id is a pure function of that root.
    """
    parsed = _coerce_json_object(body)
    if parsed is None:
        return None
    try:
        root = _conversation_root(parsed)
    except Exception:
        logger.debug("session inference failed", exc_info=True)
        return None
    if not root:
        return None
    return _fingerprint(root)


def _coerce_json_object(body: str | bytes | dict | None) -> dict | None:
    if isinstance(body, dict):
        return body
    if isinstance(body, bytes):
        try:
            body = body.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(body, str) or not body.strip():
        return None
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _conversation_root(body: dict) -> list[tuple[str, str]] | None:
    """Leading system text and the first textual user turn, or None."""
    messages = body.get("messages")
    if isinstance(messages, list) and messages:
        return _root_from_messages([*_system_messages(body.get("system")), *messages])
    if "input" in body:
        prefix = _system_messages(body.get("instructions"))
        if not prefix:
            prefix = _system_messages(body.get("system"))
        return _root_from_messages([*prefix, *_input_items(body.get("input"))])
    return None


def _system_messages(value: Any) -> list[dict[str, str]]:
    text = _message_text(value)
    if not text:
        return []
    return [{"role": "system", "content": text}]


def _input_items(raw: Any) -> list[Any]:
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return raw
    return []


def _root_from_messages(messages: list[Any]) -> list[tuple[str, str]] | None:
    root: list[tuple[str, str]] = []
    for message in messages:
        role, text = _role_and_text(message)
        if role == "system":
            if text:
                root.append(("system", text))
            continue
        if role == "user":
            if not text:
                continue
            root.append(("user", text))
            return root
    return None


def _role_and_text(message: Any) -> tuple[str | None, str]:
    if isinstance(message, str):
        return "user", _normalize_text(message)
    if not isinstance(message, dict):
        return None, ""
    role = message.get("role")
    if not isinstance(role, str) or not role.strip():
        return None, ""
    role = role.strip().lower()
    if role == "developer":
        role = "system"
    return role, _message_text(message.get("content"))


def _message_text(content: Any) -> str:
    """Flatten chat / Anthropic / Responses content to edge-stripped text."""
    if isinstance(content, str):
        return _normalize_text(content)
    if isinstance(content, dict):
        return _content_piece_text(content)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                piece = _normalize_text(block)
            elif isinstance(block, dict):
                piece = _content_piece_text(block)
            else:
                piece = ""
            if piece:
                parts.append(piece)
        return "\n".join(parts)
    return ""


def _content_piece_text(block: dict) -> str:
    kind = block.get("type")
    if kind is not None and kind not in _TEXT_PART_TYPES:
        return ""
    text = block.get("text")
    if isinstance(text, str):
        return _normalize_text(text)
    return ""


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip()


def _fingerprint(root: list[tuple[str, str]]) -> str:
    payload = _ROOT_VERSION + "\x1e" + "\x1e".join(f"{role}\x1f{text}" for role, text in root)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_INFERRED_DIGEST_HEX]
    return f"{INFERRED_SESSION_PREFIX}{digest}"


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def preview_body(body: str | None, limit: int = PREVIEW_CHARS) -> str:
    """Collapse whitespace and truncate a stored body for a trajectory row."""
    if not body:
        return ""
    text = " ".join(str(body).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def step_flags(status: int | None, latency_ms: float | None) -> list[str]:
    """Light markers for a step that failed or ran long. No model judgment."""
    flags: list[str] = []
    if status is None or status < 200 or status >= 400:
        flags.append("failed")
    if latency_ms is not None and latency_ms >= SLOW_STEP_MS:
        flags.append("slow")
    return flags


def _split_agg(value: str | None) -> list[str]:
    if not value:
        return []
    seen: set[str] = set()
    items: list[str] = []
    for part in str(value).split(","):
        text = part.strip()
        if text and text not in seen:
            seen.add(text)
            items.append(text)
    return items


def session_summary_from_row(row: dict) -> dict:
    """Normalize one grouped session row from SQL."""
    return {
        "session_id": row["session_id"],
        "request_count": int(row["request_count"] or 0),
        "total_tokens": int(row["total_tokens"] or 0),
        "input_tokens": int(row["input_tokens"] or 0),
        "output_tokens": int(row["output_tokens"] or 0),
        "token_request_count": int(row["token_request_count"] or 0),
        "first_timestamp": row["first_timestamp"],
        "last_timestamp": row["last_timestamp"],
        "error_count": int(row["error_count"] or 0),
        "total_latency_ms": float(row["total_latency_ms"] or 0),
        "models": _split_agg(row.get("models")),
        "upstreams": _split_agg(row.get("upstreams")),
    }


def assemble_session(session_id: str, rows: list[dict]) -> dict:
    """Turn chronological request rows into one trajectory with running totals.

    Token totals add only steps that reported a count. A step with no usage
    keeps its own fields null and does not move the running total. Waste
    findings are attached from the same rows; body rules use length and a
    bounded suffix when those fields or ``request_body`` are present.
    """
    steps: list[dict] = []
    cum_in = 0
    cum_out = 0
    cum_total = 0
    cum_latency = 0.0
    models: list[str] = []
    upstreams: list[str] = []
    seen_models: set[str] = set()
    seen_upstreams: set[str] = set()
    token_request_count = 0

    for row in rows:
        inp = _as_int(row.get("input_tokens"))
        out = _as_int(row.get("output_tokens"))
        total = _as_int(row.get("total_tokens"))
        latency = _as_float(row.get("latency_ms"))
        status = _as_int(row.get("response_status"))
        if inp is not None:
            cum_in += inp
        if out is not None:
            cum_out += out
        if total is not None:
            cum_total += total
            token_request_count += 1
        if latency is not None:
            cum_latency += latency
        model_name = row.get("model_name") or None
        upstream = row.get("upstream") or None
        if model_name and model_name not in seen_models:
            seen_models.add(model_name)
            models.append(model_name)
        if upstream and upstream not in seen_upstreams:
            seen_upstreams.add(upstream)
            upstreams.append(upstream)
        raw_preview = row.get("request_preview")
        if raw_preview is None:
            raw_preview = row.get("request_body")
        steps.append({
            "id": row["id"],
            "timestamp": row["timestamp"],
            "method": row.get("method") or "",
            "url": row.get("url") or "",
            "upstream": upstream,
            "response_status": status,
            "latency_ms": latency,
            "model_name": model_name,
            "input_tokens": inp,
            "output_tokens": out,
            "total_tokens": total,
            "cache_read_tokens": _as_int(row.get("cache_read_tokens")),
            "cache_creation_tokens": _as_int(row.get("cache_creation_tokens")),
            "format": row.get("format"),
            "session_step": row.get("session_step") or None,
            "cumulative_input_tokens": cum_in,
            "cumulative_output_tokens": cum_out,
            "cumulative_total_tokens": cum_total,
            "cumulative_latency_ms": cum_latency,
            "flags": step_flags(status, latency),
            "request_preview": preview_body(raw_preview),
        })

    error_count = sum(1 for step in steps if "failed" in step["flags"])
    detail = {
        "session_id": session_id,
        "request_count": len(steps),
        "total_tokens": cum_total,
        "input_tokens": cum_in,
        "output_tokens": cum_out,
        "token_request_count": token_request_count,
        "total_latency_ms": cum_latency,
        "first_timestamp": rows[0]["timestamp"] if rows else None,
        "last_timestamp": rows[-1]["timestamp"] if rows else None,
        "error_count": error_count,
        "models": models,
        "upstreams": upstreams,
        "slow_latency_ms": SLOW_STEP_MS,
        "steps": steps,
    }
    from otel_agent.waste import apply_waste_findings

    return apply_waste_findings(detail, rows)
