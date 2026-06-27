# Tasks: Dashboard Performance Optimization

**Input**: Design documents from `/specs/005-dashboard-performance/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/api.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, etc.)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Fix default database path (BUG-001).

- [x] T001 Change default `--db` from `telemetry.db` to `~/.otel-agent/telemetry.db` in `src/otel_agent/cli.py` (all subcommands: proxy start/restart, view, dashboard)
- [x] T002 Ensure `~/.otel-agent/` directory is created before database write in `src/otel_agent/logger.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database indexes and connection pooling. All performance improvements depend on this.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Add `CREATE INDEX IF NOT EXISTS` statements for `timestamp`, `method`, `response_status` columns in `_create_tables()` in `src/otel_agent/logger.py`
- [x] T004 Refactor `DashboardAPI` to use a single persistent `sqlite3.Connection` instead of creating a new connection per request in `src/otel_agent/dashboard/api.py`
- [x] T005 [P] Add test for index creation: verify indexes exist on `requests` table in `tests/test_logger.py`
- [x] T006 [P] Add test for persistent connection: verify multiple API calls reuse the same connection in `tests/test_dashboard.py`
- [x] T007 Run `uv run pytest tests/test_logger.py tests/test_dashboard.py -v` — all pass

**Checkpoint**: Indexes exist, connection reused ✅

---

## Phase 3: User Story 1 — Fast Initial Load (P1) 🎯 MVP

**Goal**: Dashboard loads first page in under 1 second with 1000 requests.

**Independent Test**: Open dashboard with 1000 requests. Verify load time <1s.

### Implementation

- [x] T008 [US1] Add `CountCache` class to `src/otel_agent/dashboard/api.py` with 5-second TTL: `get_count(where, params)` returns cached value or queries and caches
- [x] T009 [US1] Update `get_requests()` in `src/otel_agent/dashboard/api.py` to use `CountCache` instead of `SELECT COUNT(*)` on every call
- [x] T010 [US1] Update `get_requests()` to use cursor-based pagination: `WHERE id < cursor ORDER BY id DESC LIMIT ?` instead of `LIMIT ? OFFSET ?`
- [x] T011 [US1] Update `DashboardHandler._serve_requests()` in `src/otel_agent/dashboard/server.py` to accept `cursor` and `limit` params instead of `page` and `per_page`
- [x] T012 [US1] Update `index.html` JavaScript to use cursor-based pagination: send `cursor` param, use `next_cursor` from response, update pagination buttons
- [x] T013 [P] [US1] Add tests for COUNT caching and cursor pagination in `tests/test_dashboard.py`
- [x] T014 [US1] Run `uv run pytest tests/test_dashboard.py -v` — all pass

**Checkpoint**: Initial load <1s, cursor pagination works ✅

---

## Phase 4: User Story 2 — Fast Search (P1)

**Goal**: Search results appear within 500ms.

**Independent Test**: Type "openai" in search. Verify results <500ms.

### Implementation

- [x] T015 [US2] Update `_build_where()` in `src/otel_agent/dashboard/api.py` to apply indexed filters (method, status) before LIKE filter for query optimization
- [x] T016 [P] [US2] Add test for search performance: verify search with indexed filter returns quickly in `tests/test_dashboard.py`

**Checkpoint**: Search <500ms ✅

---

## Phase 5: User Story 3 — Fast Detail View (P1)

**Goal**: Detail page loads within 1 second.

**Independent Test**: Click a row with large response body. Verify detail loads <1s.

### Implementation

- [x] T017 [US3] Verify `get_request()` uses the persistent connection (already done in T004). No code change needed — validate via test.
- [x] T018 [P] [US3] Add test for detail page performance: verify single request lookup is fast in `tests/test_dashboard.py`

**Checkpoint**: Detail page <1s ✅

---

## Phase 6: User Story 4 — Real-Time Updates Without Lag (P2)

**Goal**: SSE updates don't cause UI lag.

**Independent Test**: Send 10 requests rapidly. Verify dashboard updates smoothly.

### Implementation

- [x] T019 [US4] Update `get_requests_since()` in `src/otel_agent/dashboard/api.py` to use the persistent connection (already done in T004). Validate via test.
- [x] T020 [US4] Update `index.html` SSE handler to append new rows without re-rendering the entire table (only prepend new rows)

**Checkpoint**: SSE updates smooth ✅

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [x] T021 Update `README.md` with performance notes: cursor pagination, COUNT caching
- [x] T022 Run full test suite `uv run pytest tests/ -v -m "not integration"` — all pass
- [x] T023 Run quickstart validation from `specs/005-dashboard-performance/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 Initial Load (Phase 3)**: Depends on Foundational
- **US2 Search (Phase 4)**: Depends on Foundational
- **US3 Detail View (Phase 5)**: Depends on Foundational
- **US4 Real-Time (Phase 6)**: Depends on Foundational
- **Polish (Phase 7)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational
- **US2 (P1)**: Can start after Foundational (independent of US1)
- **US3 (P1)**: Can start after Foundational (independent of US1/US2)
- **US4 (P2)**: Can start after Foundational (independent of US1-3)

### Parallel Opportunities

- T001-T002 are sequential (same file: cli.py + logger.py)
- T003-T004 are sequential (same file: api.py + logger.py)
- T005-T006 can run in parallel (different test files)
- T008-T012 are sequential (same files: api.py, server.py, index.html)
- T015-T016 can run in parallel
- T017-T018 can run in parallel
- T019-T020 can run in parallel

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (fix DB path)
2. Complete Phase 2: Foundational (indexes + connection pooling)
3. Complete Phase 3: US1 — COUNT cache + cursor pagination
4. **STOP and VALIDATE**: Dashboard loads <1s with 1000 requests
5. Continue with remaining stories

### Incremental Delivery

1. Setup + Foundational → Indexes and connection reuse
2. Add US1 → COUNT cache + cursor pagination (core value!)
3. Add US2 → Search optimized
4. Add US3 → Detail view fast
5. Add US4 → SSE smooth
6. Polish → README updated, tests green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
