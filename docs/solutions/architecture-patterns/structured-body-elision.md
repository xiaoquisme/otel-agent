---
title: Structured elision for oversized telemetry bodies
date: 2026-10-04
category: architecture-patterns
module: otel_agent.body_elide
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - A request or response body exceeds the telemetry row limit (500 KB)
  - Preserving debugging value of a record that cannot be stored whole
tags:
  - telemetry
  - truncation
  - request-body
  - storage
---

# Structured elision for oversized telemetry bodies

## Problem

Telemetry rows cap stored request/response bodies at 500 KB. The original
implementation was a blind `body[:500_000]` cut, which on real traffic (42% of
request rows hit the cap, all of them long `messages` histories) meant:

- JSON cut mid-string → stored record unparseable without bracket repair
- the cut removed the **tail** of requests — the newest, most relevant turns
- no indication of what was lost

## Approach

`otel_agent/body_elide.py` replaces the cut with a deterministic loss ladder,
applied only to bodies already over the limit. Bodies within the limit are
returned byte-identical.

1. **Media redaction** — base64 payloads (`data:` URLs, Anthropic/Responses
   image-source `data` fields) become placeholders that declare the omitted
   byte count. The lowest-value bulk goes first so everything else survives.
2. **Message elision** — elements of `messages` / `input` arrays are dropped
   at element boundaries: the first turn(s) and newest turn(s) stay
   byte-identical, the middle is replaced by one marker element
   (`{"role": "omitted", "_elided": {"omitted_messages": N, "omitted_bytes": B}}`).
3. **String shrinking** — remaining oversized strings keep head + tail around
   a marker (a single huge message cannot blow the row).
4. **Text elision** — non-JSON bodies keep head + tail around a marker.

Every step declares its own loss in place, so a stored body never silently
claims to be complete. This is deliberately **not** context compression: no
summarization, no semantic rewriting — the stored record stays evidence, and
whatever is missing is stated explicitly.

## Consequences

- Elided bodies are always valid JSON (validated against reconstructed real
  traffic: 18/18 parse vs 0/18 for blind truncation) at ~77% retained bulk.
- The `render.py` `_parse_body` bracket-repair stays for historical rows only.
- Elision runs only when the limit is exceeded, so the common write path is
  untouched.

## Related

- `stream_capture.py` — streamed responses are reassembled at answer size and
  lead with usage, so their rows rarely reach the limit at all.
