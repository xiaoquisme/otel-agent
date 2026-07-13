---
title: "Remove SSE Polling to Eliminate DB Pressure"
date: "2026-07-13"
category: "performance-issues"
module: "dashboard"
problem_type: "performance_issue"
component: "database"
severity: "high"
symptoms:
  - "DuckDB/SQLite under constant query load from dashboard SSE endpoint"
  - "Each browser tab opens a separate SSE connection, each polling the DB every 1 second"
  - "Multiple tabs create multiplicative DB pressure (N tabs = 2N queries/second)"
root_cause: "logic_error"
resolution_type: "code_fix"
tags:
  - "dashboard"
  - "sse"
  - "polling"
  - "duckdb"
  - "database-pressure"
  - "server-sent-events"
---

# Remove SSE Polling to Eliminate DB Pressure

## Problem

The dashboard's `GET /api/events` SSE endpoint polled the database every 1 second per connected client. Each browser tab opening the dashboard created its own SSE connection, so N open tabs meant 2N database queries per second (one `get_requests_since` + one `get_max_id` per poll cycle). DuckDB in particular is not optimized for high-concurrency polling workloads.

## Symptoms

- Constant DB query load even when no user is actively looking at the dashboard
- Load scales linearly with number of open browser tabs
- DuckDB connection contention under multiple concurrent SSE streams

## What Didn't Work

- No alternative was attempted; the feature provided minimal value (auto-refreshing new requests) relative to its cost

## Solution

Remove SSE entirely from all layers:

**Backend** (6 files):
- `src/otel_agent/dashboard/routes.py` — remove `sse_events()` handler, `asyncio` and `StreamingResponse` imports
- `src/otel_agent/dashboard/server.py` — remove `_serve_sse()` method and `/api/events` routing branch
- `src/otel_agent/dashboard/api.py` — remove `get_requests_since()` and `get_max_id()`
- `src/otel_agent/storage/base.py` — remove abstract `get_requests_since()` and `get_max_id()`
- `src/otel_agent/storage/duckdb.py` — remove `get_requests_since()` and `get_max_id()` implementations
- `src/otel_agent/storage/sqlite.py` — remove `get_requests_since()` and `get_max_id()` implementations

**Frontend** (3 files):
- `frontend/src/App.tsx` — remove inline `EventSource` setup, `connectSSE` callback, `eventSourceRef`
- `frontend/src/hooks/useSSE.ts` — delete entirely
- `frontend/src/hooks/useRequests.ts` — remove `prependRequest` (only used by SSE)

**Tests**:
- `tests/test_dashboard.py` — remove `test_get_requests_since`, `test_get_max_id`, `test_get_max_id_empty`; add `test_route_events_removed` verifying 404

## Why This Works

Removing the polling loop eliminates the constant DB query load. The `get_requests_since()` and `get_max_id()` storage methods existed solely to support SSE polling — no other code path used them, so removing them also simplifies the storage interface. Users see new data by refreshing or using pagination controls.

## Prevention

- Avoid polling-based live updates against embedded databases (DuckDB, SQLite) — they are designed for analytical or low-concurrency workloads, not long-lived streaming connections
- If real-time updates are needed in the future, consider: (a) in-memory pub/sub that doesn't touch the DB on each poll, (b) webhook/callback from the request logger, or (c) a lightweight change-notification mechanism (e.g., `sqlite3` update callbacks, or an `asyncio.Event` signaled by the logger)
- When adding any long-lived connection endpoint, calculate the per-client query rate and multiply by expected concurrent clients to estimate DB load
- **When removing a feature, search the entire codebase for all call sites — including integration tests.** The SSE removal missed `tests/test_integration.py`, which still called the deleted `get_max_id()` and `get_requests_since()` methods. Always run `grep -r "method_name" --include="*.py"` across all test directories before merging removal commits.

## Related

- `docs/solutions/architecture-patterns/dashboard-render-delegation-pattern.md` — related dashboard architecture decision (single-process merge)
- `docs/solutions/test-failures/integration-test-broken-after-sse-removal.md` — the test breakage caused by this removal (documents the missed integration test)
