---
title: Cover the session list so it does not read request bodies
date: 2026-10-22
category: performance-issues
module: storage
problem_type: performance_issue
component: sqlite
severity: high
symptoms:
  - "GET /api/sessions is slow on the first open of /sessions"
  - "The sessions table groups every tagged request before it can show the first page"
root_cause: sqlite_session_index_table_lookup
resolution_type: covering_index
tags:
  - session
  - sqlite
  - covering-index
  - dashboard
---

# Cover the session list so it does not read request bodies

## Problem

`GET /api/sessions` rollups only need session id, timestamps, status, latency, model, upstream, and token columns. On a telemetry DB whose rows also store request and response bodies, that aggregate was still reading the bodies.

## Symptoms

The Sessions page issues one request, `GET /api/sessions?limit=50&offset=0`. It does not load trajectories, waste findings, or full steps. Those stay on `GET /api/sessions/{id}`.

`EXPLAIN QUERY PLAN` for the list aggregate, with only `idx_requests_session_time`, was:

```text
SEARCH requests USING INDEX idx_requests_session_time (session_id>?)
```

That index groups by `session_id`, then each row is a table lookup. `input_tokens` and the other rollup columns are stored after `request_body` and `response_body`, so every tagged row loads those overflow pages. There is no time window: the first page still aggregates every session so it can sort by last activity. The distinct-session count was already covering on `idx_requests_session_time`.

## What Didn't Work

A loading skeleton would hide the wait and leave the same read in place. Computing waste rules or previews on the list was not the cost — the list SQL never selects a body. Limiting the `GROUP BY` without a covering index still looks up every tagged row that belongs to the sessions being counted, and the total still walks every session id.

## Solution

`idx_requests_session_summary` is a partial covering index on `session_id` (then timestamp, status, latency, model, upstream, and the three token columns) `WHERE session_id IS NOT NULL`. The list aggregate becomes:

```text
SEARCH requests USING COVERING INDEX idx_requests_session_summary (session_id>?)
```

`SQLiteStorage.initialize()` creates it after the session columns exist, including on a legacy database. The first proxy start after upgrade builds it once. Later starts no-op on `IF NOT EXISTS`. Read-only dashboard connections do not create it; the proxy writer does.

`get_session` still uses `idx_requests_session_time`. The trajectory needs the body for turn grouping and a bounded tail for waste rules, and it orders by `(timestamp, id)`.

## Local timing

Synthetic SQLite 3.45.1, 4,000 session-tagged rows across 250 sessions plus 200 untagged rows, 32KB request body and 32KB response body (~278MB). Page cache dropped between samples. Same rows and the same first session either way.

| Plan | Cold | Warm |
| --- | --- | --- |
| `idx_requests_session_time` plus table lookup | 199ms | 56ms |
| `idx_requests_session_summary` covering | 4–7ms | 1.8ms |

The covering index added about 0.3MB and built in 0.05s while the table was hot. The first proxy start on a real database reads the table once to build it. Cold time without the index scales with the bytes of stored bodies, which is the same reason a wide usage aggregate was tens of seconds before `idx_requests_usage`. The sessions list has no date bound, so that read is the whole tagged history.

## Why This Matters

Dropping this index, or selecting a column that is not in it (a body preview, a header, `session_step`), sends `/sessions` back to reading every tagged payload on first paint. `idx_requests_session_time` stays the right index for one session's trajectory.

## When to Apply

- Changing `list_sessions` SQL
- Adding a storage backend that keeps payloads in the same row as the rollup columns
- The sessions list regresses to a multi-second first load while `EXPLAIN` no longer says `COVERING INDEX idx_requests_session_summary`
