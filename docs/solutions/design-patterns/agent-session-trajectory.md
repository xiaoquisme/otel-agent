---
title: Group gateway calls into an agent session trajectory
date: 2026-10-19
category: design-patterns
module: telemetry
problem_type: design_pattern
component: session_id
severity: medium
applies_when:
  - Logging multi-turn agent traffic through the gateway
  - Adding a dashboard view over more than one request row
tags:
  - session
  - sqlite
  - dashboard
  - trajectory
---

# Group gateway calls into an agent session trajectory

## Context

Each proxy call is one `requests` row. Agent runs issue many calls (tools, retries, follow-ups), and those rows could not be read back as one path.

## Guidance

- Read the run id in `_log_telemetry`, the single write used by chat completions, messages, responses, and streaming. Header `X-Otel-Session` wins; `X-Session-ID` is the alias when the primary header is missing or blank. `X-Otel-Session-Step` is an optional label. Blank means null — do not invent an id.
- Store nullable `session_id` and `session_step` with the existing `ALTER TABLE` upgrade, plus partial index `idx_requests_session_time` on `(session_id, timestamp, id)`. Cap the id at 256 characters and the step at 128.
- List sessions with `GET /api/sessions` and one trajectory with `GET /api/sessions/{id}`. Steps are chronological and carry cumulative tokens (unknown usage does not move the total), a short body preview, and `failed` / `slow` flags (status outside 2xx–3xx, latency ≥ 10s). Full bodies stay on `GET /api/requests/{id}`.
- A database that has not been upgraded yet returns an empty session list instead of failing the dashboard read. The proxy's `initialize()` adds the columns.

## Why This Matters

The session id has to be captured on the request that was actually logged. Parsing it later from stored headers would miss the index and the list query, and a generated id would glue unrelated traffic together.

## When to Apply

- Extending telemetry that should survive across the chat, messages, responses, and streaming handlers
- Adding another storage backend: implement `list_sessions` and `get_session` next to `log_request`
