---
title: "feat: Add model name to homepage request list"
date: "2026-07-15"
type: "feat"
depth: "lightweight"
product_contract_source: "ce-plan-bootstrap"
---

## Goal Capsule

- **Objective:** Display the model name (e.g. `deepseek-v4-flash`, `MiMo-v2-5-Pro`) on each row of the homepage request list so users can see which model handled each request without opening the detail view.
- **Stop condition:** Model name visible on every request row in the list; `null` model names render gracefully.

---

## Problem Frame

The dashboard's request list shows ID, timestamp, method, URL, status, and latency — but not which model served the request. The `model_name` column already exists in the database (written by `TelemetryLogger.log_request`) but is not returned by the list query or displayed in the frontend. Users must click into each request's detail view to see the model, which is slow for triage.

---

## Requirements

- R1. The list query returns `model_name` alongside existing columns.
- R2. The frontend `RequestItem` type includes `model_name`.
- R3. Each request row displays the model name (or a fallback for `null`).

---

## Implementation Units

### U1. Add `model_name` to storage list queries

**Goal:** Return `model_name` from the paginated list endpoint.

**Files:**
- `src/otel_agent/storage/duckdb.py`
- `src/otel_agent/storage/sqlite.py`

**Approach:** Add `model_name` to the SELECT column list and the `_COLUMNS` tuple in both storage backends. The column already exists in the `requests` table — no schema change needed.

**Test scenarios:**
- Happy path: request with `model_name="deepseek-v4-flash"` appears in list with that value.
- Null model: request with `model_name=None` returns `null` (not an error).

**Test expectation:** none — storage layer is exercised via integration tests already; the column addition is mechanical.

---

### U2. Display model name in frontend request list

**Goal:** Show model name on each request row.

**Files:**
- `frontend/src/api/types.ts`
- `frontend/src/components/RequestRow.tsx`

**Approach:** Add `model_name: string | null` to `RequestItem`. In `RequestRow`, render it as a subtle badge after the URL column. When `null`, show `—` (em dash) as fallback.

**Test scenarios:**
- Happy path: row with `model_name="deepseek-v4-flash"` shows the model name.
- Null model: row with `model_name=null` shows `—`.
- Long model name: text truncates gracefully (already handled by parent `max-w` + `overflow-hidden`).

**Verification:** Open dashboard, confirm model name visible on request rows. Filter/search still works.

---

## Verification Contract

| Gate | Command | Pass criteria |
|------|---------|---------------|
| Type check | `cd frontend && npx tsc --noEmit` | No errors |
| Lint | `cd frontend && npx eslint src/` | No new warnings |
| Tests | `uv run pytest tests/ -x -q --ignore=tests/test_integration.py` | 253+ passed |

---

## Definition of Done

- [ ] `model_name` returned by list API for both duckdb and sqlite backends
- [ ] Model name visible on every request row in the dashboard list
- [ ] Null model names render as `—`
- [ ] No regressions in existing tests
