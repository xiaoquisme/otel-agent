---
title: "fix: Remove SSE from Dashboard"
type: fix
date: 2026-07-13
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
---

# fix: Remove SSE from Dashboard

## Goal Capsule

**Objective:** Remove the SSE (Server-Sent Events) live-feed from the dashboard to eliminate constant DB polling pressure. The `GET /api/events` endpoint polls the database every 1 second per connected client — with multiple browser tabs open, this creates multiplicative load on DuckDB/SQLite for minimal value (users can refresh manually).

**Stop conditions:**
- No code path polls the DB on an interval for live updates
- `GET /api/events` returns 404
- Frontend has no EventSource or SSE connection code
- All remaining tests pass

---

## Problem Frame

The SSE endpoint in `routes.py:95-114` runs an infinite loop: every 1 second, it queries `get_requests_since(last_id)` + `get_max_id()`. Each connected browser tab opens its own SSE connection, so N tabs = N×2 queries/second hitting the DB continuously. DuckDB in particular is not optimized for high-concurrency polling workloads.

---

## Requirements

- R1. Remove the `GET /api/events` SSE endpoint from FastAPI routes
- R2. Remove the `_serve_sse()` handler from the legacy HTTP server
- R3. Remove `get_requests_since()` and `get_max_id()` from storage backends (DuckDB + SQLite) and the abstract base
- R4. Remove `get_requests_since()` and `get_max_id()` from `DashboardAPI`
- R5. Remove all SSE-related frontend code (inline SSE in `App.tsx`, `useSSE.ts` hook)
- R6. Remove SSE-related tests
- R7. Update dashboard migration plan to remove SSE references

---

## Key Technical Decision

**No live-reload replacement.** Users refresh the page or click the existing pagination controls to see new data. A manual refresh button could be added later as a follow-up if needed — this plan only removes the pressure source.

---

## Implementation Units

### U1. Remove SSE backend endpoint and storage methods

**Goal:** Eliminate all server-side SSE code and the DB methods that only exist to support it.

**Files:**
- `src/otel_agent/dashboard/routes.py` — remove `sse_events()` handler (lines 95-114)
- `src/otel_agent/dashboard/server.py` — remove `_serve_sse()` method and the `/api/events` branch in `do_GET`
- `src/otel_agent/dashboard/api.py` — remove `get_requests_since()` and `get_max_id()` methods
- `src/otel_agent/storage/base.py` — remove `get_requests_since()` and `get_max_id()` abstract methods
- `src/otel_agent/storage/duckdb.py` — remove `get_requests_since()` and `get_max_id()` implementations
- `src/otel_agent/storage/sqlite.py` — remove `get_requests_since()` and `get_max_id()` implementations

**Approach:** Delete the methods and the route handler. The `StreamingResponse` and `asyncio` imports in `routes.py` can be removed if no other route uses them.

**Test scenarios:**
- `GET /api/events` returns 404 (no matching route)
- All other `/api/*` endpoints still work correctly (regression check)

---

### U2. Remove SSE frontend code

**Goal:** Remove all client-side SSE connection code.

**Files:**
- `frontend/src/App.tsx` — remove `EventSource` setup, `connectSSE` callback, `eventSourceRef`, and the `useEffect` that connects SSE
- `frontend/src/hooks/useSSE.ts` — delete the file entirely

**Approach:** In `App.tsx`, remove the `useRef<EventSource>` import, `eventSourceRef`, `connectSSE`, and the SSE `useEffect`. The `useCallback` and `useRef` imports can be cleaned up if no longer used.

**Test expectation:** none — no component tests exist yet for the React dashboard.

---

### U3. Remove SSE tests

**Goal:** Remove tests that exercise the deleted SSE methods.

**Files:**
- `tests/test_dashboard.py` — remove `test_get_requests_since`, `test_get_max_id`, `test_get_max_id_empty`, and the SSE-related assertions in the nonexistent-DB test (`assert api.get_requests_since(0) == []` and `assert api.get_max_id() == 0`)

**Approach:** Delete the three test functions. Edit the nonexistent-DB test to remove the two SSE assertions while keeping the others.

---

### U4. Update dashboard migration plan

**Goal:** Remove SSE references from the existing plan so it stays accurate.

**Files:**
- `docs/plans/2026-07-13-002-feat-react-dashboard-migration-plan.md` — remove R8 (SSE), SSE from scope boundaries, SSE from feature parity section, and any `useSSE` references in implementation units

---

## Verification Contract

1. `uv run pytest -m "not integration" -q` — all tests pass
2. `npm run build` in `frontend/` — TypeScript compiles with no errors
3. Start dashboard with `otel-agent dashboard` — `GET /api/events` returns 404, all other endpoints work

## Definition of Done

- No SSE endpoint exists on the server
- No EventSource or SSE code exists in the frontend
- No DB polling methods (`get_requests_since`, `get_max_id`) exist in storage layer
- All tests pass
- Dashboard migration plan updated
