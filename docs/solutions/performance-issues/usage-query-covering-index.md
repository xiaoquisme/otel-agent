---
title: Cover usage aggregates so they do not read request bodies
date: 2026-10-19
category: performance-issues
module: storage
problem_type: performance_issue
component: sqlite
severity: high
symptoms:
  - "GET /api/usage for a 30-day window takes tens of seconds on first call and still about two seconds once the file is cached"
  - "All-time /api/usage is as slow or slower; /api/usage/series over the same wide range does not return before a client timeout"
  - "Today's window stays well under a second"
root_cause: sqlite_status_index_table_lookup
resolution_type: covering_index
tags:
  - usage
  - sqlite
  - covering-index
  - dashboard
---

# Cover usage aggregates so they do not read request bodies

## Problem

`get_usage_summary` and `get_usage_series` only need token columns, model name, status, and timestamp. On a telemetry DB whose rows also store request and response bodies, those queries were still reading the bodies.

## Symptoms

Measured against a live gateway DB (about 904 million tokens across 15 models in the summary payload, ~3.7KB of JSON):

| Query | Cold | Warm |
| --- | --- | --- |
| `/api/usage` 30-day | 40.2s | 1.88s |
| `/api/usage/series` 30-day | 0.70s | 2.50s |
| `/api/usage` today | 0.12s | |
| `/api/usage/series` today | 0.06s | |
| `/api/usage` from 2020-01-01 | 54s | |
| `/api/usage/series` from 2020-01-01 | client gave up at ~46s with an empty body | |

The cold-to-warm drop is the OS page cache, not a result cache. Warm was still reading the same pages.

## What Didn't Work

A partial index on the token columns (`WHERE response_status >= 200 AND response_status <= 299`, status itself not indexed) was selected but not covering, so it still looked up table rows. Adding `response_status` to that partial index made `BETWEEN 200 AND 299` covering, but the equivalent `>= 200 AND < 300` predicate ignored the partial index and used `idx_requests_status` again. A result cache would not fix the first page load. The non-partial covering index is the plan both for a 30-day window and for all-time, with or without `ANALYZE`.

## Solution

`EXPLAIN QUERY PLAN` on the summary and series statements, with only the original indexes, was:

```text
SEARCH requests USING INDEX idx_requests_status (response_status>? AND response_status<?)
```

The bytecode is a status-index scan plus `DeferredSeek` into the table. `timestamp` is an early column, so rows outside the window are rejected before SQLite touches the payload. `input_tokens` and the other sums are stored *after* `request_body` and `response_body`, so every row that passes the timestamp check loads those overflow pages. Today stays under a second because almost every 2xx row fails that check. A 30-day or all-time window accepts most of a busy history, and the cold read of those bodies is the 40–54s. The warm call is the same read from the page cache (~2s), not a result cache.

`idx_requests_usage` is a non-partial covering index led by `timestamp`, then `response_status`, `model_name`, and the token columns. The same statements become:

```text
SEARCH requests USING COVERING INDEX idx_requests_usage (timestamp>? AND timestamp<?)
```

The range is a seek, the 2xx filter and the sums are answered from index leaves, and body overflow pages are not read. Minute grouping for the series stays in SQL; Python still folds those minutes into the viewer's timezone. No default period change.

`SQLiteStorage.initialize()` creates the index after the analytics columns exist, including on a legacy database. The first proxy start after upgrade builds it once (that build does scan the table). Later starts no-op on `IF NOT EXISTS`. Read-only dashboard connections do not create it; the proxy writer does.

## Local timing

Synthetic SQLite 3.45, 3,000 rows, 40KB request body and 40KB response body (~246MB), no `ANALYZE`. `posix_fadvise(DONTNEED)` ran between samples; the file had just been written, so this is not a cold multi-GB disk. Same plans as the live queries.

| Plan | 30-day summary | 30-day series | All-time summary | All-time series |
| --- | --- | --- | --- | --- |
| `idx_requests_status` | 131ms | 23ms | 212ms | 37ms |
| `idx_requests_usage` covering | 1.8ms | 1.8ms | 2.1ms | 2.6ms |

On that file the covering index added about 0.2MB and built in 0.04s while the table was hot. The first proxy start on a real database reads the table once to build it, then `IF NOT EXISTS` is a no-op. The regression test asserts `COVERING INDEX idx_requests_usage` for the 30-day and all-time summary and series statements.

## Why This Matters

Dropping or reordering this index, or adding a second status filter the planner likes better, sends the usage page back to scanning bodies. The status index is still right for status-only request lists. Usage queries need the timestamp-led covering index.

## When to Apply

- Changing `get_usage_summary` or `get_usage_series` SQL
- Adding a storage backend that keeps payloads in the same row as token columns
- A usage query regresses to multi-second while `EXPLAIN` no longer says `COVERING INDEX idx_requests_usage`
