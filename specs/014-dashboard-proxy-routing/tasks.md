# Tasks: Dashboard Proxy Routing

**Input**: Design documents from `/specs/014-dashboard-proxy-routing/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included — test tasks for internal API endpoints and proxy URL caching.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Source: `src/otel_agent/`
- Tests: `tests/`
- Config: `pyproject.toml`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add internal API endpoints to the proxy's FastAPI app

- [x] T001 Add internal dashboard API endpoints to `src/otel_agent/server.py` — GET /internal/dashboard/requests, /requests/{id}, /max-id, /requests-since/{id}, /export
- [x] T002 Add query helper functions to `src/otel_agent/server.py` — _build_where(), _rows_to_dicts(), _query_requests(), _query_request_detail(), _query_max_id(), _query_requests_since(), _query_all_filtered() using TelemetryLogger's DuckDB connection

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: DashboardAPI proxy routing with DuckDB fallback

- [x] T003 [P] Modify `src/otel_agent/dashboard/api.py` — add proxy_port parameter to DashboardAPI.__init__(), add _proxy_url() health check, add _http_get() helper, modify all query methods to try proxy first then fall back to direct DuckDB
- [x] T004 [P] Modify `src/otel_agent/dashboard/server.py` — add proxy_port parameter to DashboardServer.__init__(), pass to DashboardAPI
- [x] T005 Modify `src/otel_agent/commands/dashboard.py` — detect proxy port via get_proxy_status(), pass to DashboardServer

**Checkpoint**: Dashboard routes through proxy when available, falls back to direct DuckDB when not

---

## Phase 3: User Story 1 - Dashboard Reads Through Proxy (Priority: P1) 🎯 MVP

**Goal**: Dashboard displays telemetry data without DuckDB lock errors while proxy is running.

**Independent Test**: Start proxy, start dashboard, verify dashboard loads and displays request data without errors.

### Implementation for User Story 1

- [x] T006 [US1] Add concurrency integration test in `tests/test_integration.py` — test_proxy_internal_dashboard_api(): verify all internal endpoints return correct data
- [x] T007 [US1] Add concurrency integration test in `tests/test_integration.py` — test_dashboard_api_routes_through_proxy(): verify DashboardAPI routes through proxy with real uvicorn server

**Checkpoint**: Dashboard works through proxy, no lock errors

---

## Phase 4: User Story 2 - Dashboard Works Without Proxy (Priority: P2)

**Goal**: Dashboard falls back to direct DuckDB when proxy is not running.

**Independent Test**: Stop proxy, start dashboard with existing DuckDB file, verify historical data loads.

### Implementation for User Story 2

- [x] T008 [US2] Verify existing dashboard tests pass with proxy_port=None (direct DuckDB fallback) — `tests/test_dashboard.py` all existing tests already cover this path

**Checkpoint**: Dashboard works offline without proxy

---

## Phase 5: User Story 3 - Graceful Degradation Under Load (Priority: P3)

**Goal**: Dashboard uses cached proxy URL under load, avoids health-check race condition.

**Independent Test**: Send concurrent requests, verify dashboard remains responsive.

### Implementation for User Story 3

- [x] T009 [US3] Fix proxy URL caching in `src/otel_agent/dashboard/api.py` — cache _proxy_url() result with 30s TTL, keep using cached URL for 60s after health check failure, only fall back to direct DuckDB after 60s of unreachable proxy
- [x] T010 [US3] Add caching unit test in `tests/test_dashboard.py` — test_proxy_url_caching_prevents_fallback(): verify cached URL used when health check fails
- [x] T011 [US3] Add caching unit test in `tests/test_dashboard.py` — test_proxy_url_cache_expires_after_60s(): verify fallback after 60s
- [x] T012 [US3] Add caching unit test in `tests/test_dashboard.py` — test_proxy_url_fresh_check_resets_cache(): verify failure timer reset on successful health check

**Checkpoint**: Dashboard handles proxy load gracefully, no lock conflicts

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Spec artifacts, documentation, and final verification

- [x] T013 Create feature specification in `specs/014-dashboard-proxy-routing/spec.md`
- [x] T014 Create implementation plan in `specs/014-dashboard-proxy-routing/plan.md`
- [x] T015 Create research document in `specs/014-dashboard-proxy-routing/research.md`
- [x] T016 Create data model in `specs/014-dashboard-proxy-routing/data-model.md`
- [x] T017 Create internal API contract in `specs/014-dashboard-proxy-routing/contracts/internal-api.md`
- [x] T018 Create quickstart validation guide in `specs/014-dashboard-proxy-routing/quickstart.md`
- [x] T019 Run `uv run pytest tests/ -v` to verify all tests pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on T001-T002 (internal API endpoints)
- **User Story 1 (Phase 3)**: Depends on Phase 2 (proxy routing)
- **User Story 2 (Phase 4)**: Depends on Phase 2 (fallback behavior)
- **User Story 3 (Phase 5)**: Depends on Phase 2 (caching logic)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Phase 2 — core proxy routing
- **User Story 2 (P2)**: Depends on Phase 2 — fallback behavior (independent of US1)
- **User Story 3 (P3)**: Depends on Phase 2 — caching logic (independent of US1/US2)

### Within Each User Story

- Implementation before tests
- Tests should pass after each story

### Parallel Opportunities

- T003 + T004 (api.py + server.py) — different files, no dependencies
- T006 + T007 (integration tests) — can run together
- T010 + T011 + T012 (caching tests) — can run together

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Internal API endpoints (T001-T002)
2. Complete Phase 2: Proxy routing (T003-T005)
3. Complete Phase 3: Integration tests (T006-T007)
4. **STOP and VALIDATE**: Start proxy, start dashboard, verify no lock errors
5. Deploy if ready — dashboard works through proxy

### Incremental Delivery

1. Complete Setup + Foundational → Internal API + proxy routing ready
2. Add User Story 1 → Test: dashboard works through proxy → Deploy (MVP!)
3. Add User Story 2 → Test: dashboard works offline → Deploy
4. Add User Story 3 → Test: graceful degradation → Deploy
5. Polish phase → Documentation → Done

### Parallel Team Strategy

With multiple developers:
1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (integration tests)
   - Developer B: User Story 2 (fallback verification)
   - Developer C: User Story 3 (caching tests)
3. Stories complete and integrate independently
