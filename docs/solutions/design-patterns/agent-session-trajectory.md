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

- Read the run id in `_log_telemetry`, the single write used by chat completions, messages, responses, and streaming. Header order is `X-Otel-Session`, then `X-Session-ID`, then the Pi affinity headers `session_id`, `x-session-affinity`, and `x-client-request-id`. The first non-blank value wins, including over any body fingerprint. `X-Otel-Session-Step` is an optional label. Do not invent a step.
- When every session header is missing or blank, store `inferred-` plus the first 16 hex chars of a SHA-256 of the conversation root. The root is the leading system / developer text plus the first user text (Anthropic top-level `system`, Responses `instructions` + `input`, and chat `messages` share one canonical form). Do not hash the growing tail, the model, or the wall clock. The function is pure, so the same root survives a process restart. Cap stays `MAX_SESSION_ID_LEN` (256); the inferred form is well under that.
- Leave `session_id` null when there is nothing stable to key on: empty or missing messages, image prompts, multipart image edits, and a chat whose user turns have no text. Do not mint a random id per request.
- Unrelated chats that truly share the same system text and first user text share an inferred id. That collision is accepted. A system prompt that changes between turns, or a client that sends only the latest turn, will not stay one session — the body no longer contains the same root.
- Store nullable `session_id` and `session_step` with the existing `ALTER TABLE` upgrade, plus partial index `idx_requests_session_time` on `(session_id, timestamp, id)`. Cap the id at 256 characters and the step at 128. Inferred ids use the same column.
- List sessions with `GET /api/sessions` and one trajectory with `GET /api/sessions/{id}`. Steps are chronological and carry cumulative tokens (unknown usage does not move the total), a short body preview, and `failed` / `slow` flags (status outside 2xx–3xx, latency ≥ 10s). The detail also includes deterministic waste `findings` (see `session-waste-rules.md`). Full bodies stay on `GET /api/requests/{id}`.
- A turn is one user round, matching the harness session model (a turn holds one or more model-call steps). Group consecutive requests whose latest human user text is the same. OpenAI `role=tool` messages, Anthropic `tool_result` blocks, and Responses `function_call_output` items do not start a turn. A request with no textual user message is its own turn. `session_step` stays a label on the step and does not merge or split turns. Each step gets `turn_index` and a short `turn_label`. The trajectory page shows those turns, and folds a turn only when it has more than one step. The body is read to find that text and is not copied onto the step.
- `GET /api/requests/{id}` returns the stored `session_id` and `session_step` (null when absent). The request page shows that id and links to `/sessions/{id}`. The sessions list keeps the full id and marks ids that start with `inferred-`. Do not remap different ids into one row after the fact.
- A database that has not been upgraded yet returns an empty session list instead of failing the dashboard read. The proxy's `initialize()` adds the columns.

## Why This Matters

The session id has to be captured on the request that was actually logged. Parsing it later from stored headers would miss the index and the list query. A random id per request never forms a trajectory, and a hash of the whole growing transcript splits one conversation every turn. The fingerprint is only the root that stays put. Clients that already send a session header are unchanged.

## When to Apply

- Extending telemetry that should survive across the chat, messages, responses, and streaming handlers
- Adding another storage backend: implement `list_sessions` and `get_session` next to `log_request`
