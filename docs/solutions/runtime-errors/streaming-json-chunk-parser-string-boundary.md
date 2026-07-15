---
title: "Streaming JSON chunk parser breaks on tool call arguments containing braces"
date: "2026-07-14"
category: "docs/solutions/runtime-errors/"
module: "otel_agent/dashboard"
problem_type: "runtime_error"
component: "tooling"
symptoms:
  - "Tool call arguments rendered as empty strings despite correct upstream data"
  - "Chunks count correct but accumulated arguments missing after concatenation"
  - "No error raised — parser produced valid-but-incomplete JSON chunks silently"
root_cause: "logic_error"
resolution_type: "code_fix"
severity: "medium"
tags:
  - "streaming-json"
  - "chunk-parser"
  - "string-boundary"
  - "tool-call-parsing"
  - "concatenated-json"
---

# Streaming JSON chunk parser breaks on tool call arguments containing braces

## Problem

The streaming JSON chunk parser `_parse_streaming_chunks` in `src/otel_agent/dashboard/render.py` tracked `{` and `}` brace depth to split concatenated JSON objects, but did not track whether the parser was inside a JSON string literal. When tool call arguments contained `{` or `}` characters (e.g., `{"command": "cd /path"}`), the parser incorrectly concluded the JSON object ended mid-string, producing truncated chunks with empty arguments.

## Symptoms

- Tool call arguments displayed as empty strings in the dashboard despite the LLM returning valid argument data upstream
- Chunk count remained correct (25 chunks) but the accumulated `arguments` field was empty
- The bug was silent — no error or exception was raised; the parser produced valid-but-incomplete JSON chunks

## What Didn't Work

- Verifying chunk count alone was insufficient — the parser produced the right number of chunks, so the split appeared correct at a coarse level
- The issue only manifested when tool call arguments contained JSON-like characters (`{`, `}`, `\`), which is common in real tool invocations (shell commands, code snippets, nested JSON arguments)

## Solution

Add `in_string` and `escape_next` boolean state variables to the parser, and skip depth-tracking for `{` and `}` characters encountered inside a JSON string:

```python
def _parse_streaming_chunks(preview_str: str) -> list[dict[str, Any]]:
    """Parse concatenated JSON chunks (mirrors JS parseStreamingChunks).

    Tracks whether we are inside a JSON string so that ``{`` / ``}``
    characters inside string values do not confuse the depth counter.
    """
    chunks: list[dict[str, Any]] = []
    depth = 0
    start = -1
    in_string = False
    escape_next = False
    for i, ch in enumerate(preview_str):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        # Outside a string — normal depth tracking
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
    # ... trailing chunk handling unchanged
```

Key changes from the original:

1. **`in_string` flag** — toggled on every `"` character encountered outside a string. While `True`, `{` and `}` are skipped entirely by the `if in_string: continue` guard.
2. **`escape_next` flag** — when a `\` is encountered inside a string, the next character is skipped (handles `\"` and `\\` inside JSON string values), preventing a false toggle of `in_string` on an escaped quote.

## Why This Works

The original parser used a naive depth counter that treated every `{` and `}` as a structural boundary. In valid JSON, braces inside string values (like `{"command": "cd /path"}`) are data, not structure. By tracking string boundaries via the `"` toggle and respecting escape sequences via `\`, the parser only counts braces that are actual JSON structural elements.

The `escape_next` guard is essential because a literal `\"` inside a JSON string must not toggle `in_string` — the backslash means the quote is escaped data, not the string delimiter. Similarly, `\\` must not start an escape sequence; the first backslash escapes the second.

## Prevention

- When writing JSON parsers that walk character-by-character, always account for string literals and escape sequences. A brace-depth counter alone is not sufficient for JSON.
- Add test cases with tool call arguments containing braces, backslashes, and escaped quotes to exercise the string-tracking path.
- Consider whether a library parser (e.g., `json.JSONDecoder.raw_decode`) could replace the hand-rolled parser for this use case.

## Related

- [Streaming format detection priority](../runtime-errors/streaming-format-detection-priority.md) — different root cause (format_tag priority) but same module area (streaming parsing in render.py)
- [Dashboard render delegation pattern](../architecture-patterns/dashboard-render-delegation-pattern.md) — architectural context for render.py where format detection and response parsing live
