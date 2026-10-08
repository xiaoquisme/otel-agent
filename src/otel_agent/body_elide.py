"""Structured elision for oversized telemetry bodies.

Blind ``body[:limit]`` truncation cut JSON mid-string: the stored record
became unparseable, the dashboard needed bracket-repair to render anything,
and the tail — for requests, the *newest* messages — was simply gone.

Structured elision keeps the record honest and complete around the cut. It
understands the body's JSON structure and applies a loss ladder, least lossy
first, and only to bodies that are already over the limit:

1. **Media redaction** — base64 payloads (``data:`` URLs and image-source
   ``data`` fields) become explicit placeholders that declare the omitted
   size. The lowest-value bulk goes first so everything else survives.
2. **Message elision** — whole elements of ``messages`` / ``input`` arrays
   are dropped at element boundaries: the first turn(s) and the newest
   turn(s) stay byte-identical, the middle is replaced by one marker element
   that declares how many messages and bytes are missing.
3. **String shrinking** — any remaining oversized string keeps its head and
   tail around a marker, so a single huge message cannot blow the row.
4. **Text elision** — non-JSON bodies keep head and tail around a marker
   instead of a head-only cut.

Every step is deterministic and declares its own loss, so a stored body never
silently claims to be complete: whatever is missing is stated in place.
"""

from __future__ import annotations

import json
import re
from typing import Any

#: Inline base64 media inside strings (``data:image/png;base64,...``).
_DATA_URL = re.compile(
    r"(data:[a-z0-9+.-]+/[a-z0-9.+-]+;base64,)([A-Za-z0-9+/]{1024,}={0,2})"
)

#: Bare base64 blobs under media ``data`` keys (Anthropic/Responses images).
_BARE_BASE64 = re.compile(r"^[A-Za-z0-9+/]{1024,}={0,2}$")

#: Marker budget for text elision (must exceed the marker string).
_TEXT_MARKER_RESERVE = 64

_MEDIA_KEYS = frozenset({"data"})


def elide_body(body: str, limit: int) -> str:
    """Fit *body* into *limit* chars with explicit, structured loss.

    Bodies within the limit are returned byte-identical. Oversized JSON has
    media redacted and message arrays elided at boundaries; only if that is
    not enough are strings shrunk, and only a non-JSON body ends up as a
    head+tail text elision.
    """
    if len(body) <= limit:
        return body
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return _elide_text(body, limit)
    if not isinstance(parsed, dict):
        return _elide_text(body, limit)

    parsed = _redact_media(parsed)
    parsed = _elide_message_arrays(parsed, limit)

    out = json.dumps(parsed, ensure_ascii=False)
    if len(out) <= limit:
        return out

    shrunk = _shrink_strings(parsed, limit)
    out = json.dumps(shrunk, ensure_ascii=False)
    if len(out) <= limit:
        return out
    return _elide_text(out, limit)


# ------------------------------------------------------------------
# Step 1: media redaction
# ------------------------------------------------------------------

def _redact_media(value: Any) -> Any:
    """Replace base64 media payloads with size-declaring placeholders."""
    if isinstance(value, str):
        return _DATA_URL.sub(
            lambda m: f"{m.group(1)}[otel-agent elided {len(m.group(2))} bytes of media]",
            value,
        )
    if isinstance(value, list):
        return [_redact_media(v) for v in value]
    if isinstance(value, dict):
        return {
            k: (
                f"[otel-agent elided {len(v)} bytes of media]"
                if k in _MEDIA_KEYS and isinstance(v, str) and _BARE_BASE64.match(v)
                else _redact_media(v)
            )
            for k, v in value.items()
        }
    return value


# ------------------------------------------------------------------
# Step 2: message elision
# ------------------------------------------------------------------

def _elide_message_arrays(parsed: dict[str, Any], limit: int) -> dict[str, Any]:
    for key in ("messages", "input"):
        values = parsed.get(key)
        if not isinstance(values, list) or len(values) < 3:
            continue
        overhead = len(json.dumps({**parsed, key: []}, ensure_ascii=False))
        budget = limit - overhead - _TEXT_MARKER_RESERVE
        if budget <= 0:
            continue
        elided = _elide_list(values, budget)
        if elided is not values:
            parsed = {**parsed, key: elided}
    return parsed


def _elide_list(values: list[Any], budget: int) -> list[Any]:
    """Keep the first and last elements that fit, mark the dropped middle."""
    sizes = [len(json.dumps(v, ensure_ascii=False)) + 1 for v in values]

    head_budget = budget // 3
    head: list[Any] = []
    head_used = 0
    for value, size in zip(values, sizes):
        if head and head_used + size > head_budget:
            break
        head.append(value)
        head_used += size
        if head_used >= head_budget:
            break

    tail_budget = budget - head_used
    tail: list[Any] = []
    tail_used = 0
    end = len(values)  # omitted range is [len(head), end)
    while end > len(head):
        size = sizes[end - 1]
        if tail and tail_used + size > tail_budget:
            break
        tail.append(values[end - 1])
        tail_used += size
        end -= 1
        if tail_used >= tail_budget:
            break
    tail.reverse()

    omitted = values[len(head):end]
    if not omitted:
        return values
    omitted_bytes = sum(sizes[len(head):end])
    marker = {
        "role": "omitted",
        "content": f"[otel-agent elided {len(omitted)} messages / {omitted_bytes // 1024} KB]",
        "_elided": {"omitted_messages": len(omitted), "omitted_bytes": omitted_bytes},
    }
    return head + [marker] + tail


# ------------------------------------------------------------------
# Step 3: string shrinking
# ------------------------------------------------------------------

def _shrink_strings(value: Any, limit: int) -> Any:
    """Shrink the largest strings head+tail until the body fits the limit."""
    cap = limit
    candidate = value
    for _ in range(24):
        candidate = _rebuild_with_cap(value, cap)
        if len(json.dumps(candidate, ensure_ascii=False)) <= limit:
            return candidate
        cap = max(256, cap * 2 // 3)
    return candidate


def _rebuild_with_cap(value: Any, cap: int) -> Any:
    if isinstance(value, str):
        return _elide_text(value, cap) if len(value) > cap else value
    if isinstance(value, list):
        return [_rebuild_with_cap(v, cap) for v in value]
    if isinstance(value, dict):
        return {k: _rebuild_with_cap(v, cap) for k, v in value.items()}
    return value


# ------------------------------------------------------------------
# Step 4: text elision
# ------------------------------------------------------------------

def _elide_text(text: str, limit: int) -> str:
    """Keep head and tail of *text* around a loss-declaring marker."""
    if len(text) <= limit:
        return text
    head_len = (limit - _TEXT_MARKER_RESERVE) * 2 // 3
    tail_len = limit - _TEXT_MARKER_RESERVE - head_len
    omitted = len(text) - head_len - tail_len
    marker = f"\n[otel-agent elided {omitted} bytes]\n"
    return text[:head_len] + marker + text[-tail_len:]
