---
title: "Streaming response bodies not parsed due to format_tag priority"
module: "otel_agent.dashboard.render"
component: "dashboard"
problem_type: "runtime-error"
tags:
  - "streaming"
  - "format-detection"
  - "dashboard"
  - "rendering"
symptoms:
  - "Dashboard shows 'No parsed messages available' for streaming requests"
  - "Messages array is empty despite raw data existing"
  - "Metadata shows format: 'openai' for streaming responses"
root_cause: "detect_format() prioritized format_tag from DB over body content heuristics"
resolution_type: "code-fix"
date: "2026-07-13"
---

# Streaming response bodies not parsed due to format_tag priority

## Problem

Streaming LLM responses (with `{"streamed": true, "preview": "..."}` body format) were not being parsed by the dashboard. The detail view showed "No parsed messages available" despite raw request/response bodies existing in the database.

## Symptoms

- Dashboard shows empty messages array for streaming requests
- `metadata.format` shows `"openai"` instead of `"streaming"`
- Raw body tab shows the streaming preview JSON correctly
- Formatted tab shows nothing

## Root Cause

`detect_format()` in `render.py` checked the `format_tag` from the database first and returned immediately when it matched `"openai"`. The format tag stores the **client API format** (e.g., "openai" for all OpenAI requests), not whether the response was streamed.

```python
# BEFORE (buggy)
def detect_format(body: str, format_tag: str | None = None) -> str:
    if format_tag:
        tag = format_tag.lower().strip()
        if "openai" in tag or "gpt" in tag:
            return "openai"  # Returns here without checking body content!
    
    # Body content heuristics never reached for format_tag="openai"
    parsed = _parse_body(body)
    if parsed.get("streamed") and parsed.get("preview"):
        return "streaming"  # Never reached
```

The response body was `{"streamed": true, "preview": "...chunks..."}`, but `detect_format()` returned `"openai"` because the format_tag said so. The `"openai"` parser expected a `choices` array, which streaming previews don't have at the top level.

## Solution

Move the streaming preview body-content check **before** the format_tag fallback. Body content is ground truth; the tag is just metadata about the client API format.

```python
# AFTER (fixed)
def detect_format(body: str, format_tag: str | None = None) -> str:
    parsed = _parse_body(body)
    
    # Streaming preview — body content takes priority over format_tag
    if parsed and isinstance(parsed, dict) and parsed.get("streamed") and parsed.get("preview"):
        return "streaming"

    if format_tag:
        tag = format_tag.lower().strip()
        if "stream" in tag:
            return "streaming"
        if "anthropic" in tag or "claude" in tag:
            return "anthropic"
        if "openai" in tag or "gpt" in tag:
            return "openai"

    # ... rest of heuristics
```

## Why This Works

The `format` column in the database stores the **client API format** (what the user sent), not the **response format** (how the upstream responded). For streaming requests:
- Client sends `POST /v1/chat/completions` with `stream: true` → format tag = `"openai"`
- Upstream responds with SSE chunks → response body = `{"streamed": true, "preview": "..."}`

By checking body content first, we correctly detect streaming regardless of what the format tag says.

## Prevention

1. **Body content is ground truth for format detection.** When the body has `{"streamed": true, "preview": "..."}`, it's streaming — regardless of any metadata tag.

2. **Format tags record client intent, not response reality.** The tag tells you what API the client used, not how the upstream responded. Don't use it to decide response parsing strategy.

3. **Test with streaming responses.** Existing tests only tested streaming detection with no format_tag. Always test format detection with conflicting signals (body says streaming, tag says openai).

## Files Changed

- `src/otel_agent/dashboard/render.py` — reordered `detect_format()` to check body first
- `tests/test_render.py` — added 2 regression tests

## Commit

`9e77ddb fix(dashboard): detect streaming preview body before format_tag`
