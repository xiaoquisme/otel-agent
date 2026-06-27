# Tasks: Web Dashboard for Request Logs

**Input**: Design documents from `/specs/004-web-dashboard/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/api.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, etc.)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Create dashboard package structure.

- [x] T001 Create dashboard package directory at `src/otel_agent/dashboard/__init__.py`
- [x] T002 Verify current test suite passes: `uv run pytest tests/ -v -m "not integration"`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: HTTP server and JSON API infrastructure. All dashboard features depend on this.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Create `src/otel_agent/dashboard/server.py` with `DashboardServer` class that wraps `http.server.HTTPServer`, handles routing (`/` → HTML, `/api/*` → JSON), and accepts a database path parameter
- [x] T004 Create `src/otel_agent/dashboard/api.py` with `DashboardAPI` class that reads from SQLite using the existing `requests` table schema, supports pagination (`page`, `per_page` params) and filtering (`search`, `method`, `status` params)
- [x] T005 Create `src/otel_agent/commands/dashboard.py` with `handle_dashboard(args)` function that starts the dashboard server with `--port` and `--db` flags
- [x] T006 Register `dashboard` subcommand in `src/otel_agent/cli.py` with `-p`, `-d`, `-c` flags
- [x] T007 [P] Add tests for API pagination and filtering in `tests/test_dashboard.py`: verify `/api/requests` returns correct page, total, and filtered results
- [x] T008 Run `uv run pytest tests/test_dashboard.py -v` — all pass

**Checkpoint**: Dashboard server starts, API returns paginated JSON ✅

---

## Phase 3: User Story 1 — Browse Request Logs (P1) 🎯 MVP

**Goal**: Dashboard shows a table of recent requests with timestamp, method, URL, status, latency. Auto-refreshes via SSE.

**Independent Test**: Start proxy, send requests, open `http://localhost:9090`, verify table shows requests.

### Implementation

- [x] T009 [US1] Create `src/otel_agent/dashboard/index.html` with a table displaying request rows (timestamp, method, URL, status, latency), a "No requests logged yet" empty state, and a basic layout with header and table
- [x] T010 [US1] Add SSE endpoint `GET /api/events` in `src/otel_agent/dashboard/api.py` that watches the database for new rows and pushes them to connected clients
- [x] T011 [US1] Add JavaScript in `index.html` to subscribe to `/api/events` and append new rows to the table automatically (no page refresh)
- [x] T012 [US1] Serve `index.html` from `GET /` in `src/otel_agent/dashboard/server.py`
- [x] T013 [P] [US1] Add test for SSE endpoint: verify new request triggers an event in `tests/test_dashboard.py`
- [x] T014 [US1] Run `uv run pytest tests/test_dashboard.py -v` — all pass

**Checkpoint**: Dashboard shows request table, auto-refreshes ✅

---

## Phase 4: User Story 2 — Search and Filter (P1)

**Goal**: Dashboard supports text search and method/status filters.

**Independent Test**: Send requests to different providers, filter by provider, verify only matching rows shown.

### Implementation

- [x] T015 [US2] Add search input and filter dropdowns (method, status) to `index.html` with JavaScript that calls `/api/requests` with query params and updates the table
- [x] T016 [US2] Implement search/filter query params in `DashboardAPI.get_requests()` in `src/otel_agent/dashboard/api.py`: `search` (case-insensitive URL/upstream match), `method`, `status`
- [x] T017 [P] [US2] Add test for search and filter: verify `/api/requests?search=openai&method=POST` returns filtered results in `tests/test_dashboard.py`

**Checkpoint**: Search and filters work, table updates on input ✅

---

## Phase 5: User Story 3 — View Request Details (P2)

**Goal**: Click a row to see full request/response headers and body.

**Independent Test**: Click a row, verify detail panel shows full headers and body.

### Implementation

- [x] T018 [US3] Add `GET /api/requests/:id` endpoint in `src/otel_agent/dashboard/api.py` that returns full request details (headers, body, response)
- [x] T019 [US3] Add detail panel in `index.html` that shows when a row is clicked: full request headers, request body, response headers, response body, with a "Copy as curl" button
- [x] T020 [P] [US3] Add test for detail endpoint: verify `/api/requests/1` returns full details in `tests/test_dashboard.py`

**Checkpoint**: Click row → full details displayed ✅

---

## Phase 6: User Story 4 — Latency Chart (P2)

**Goal**: Line chart showing latency over time.

**Independent Test**: Send requests with varying latency, verify chart shows data points.

### Implementation

- [x] T021 [US4] Add Chart.js CDN `<script>` tag to `index.html` and create a line chart element below the table
- [x] T022 [US4] Add JavaScript in `index.html` to fetch `/api/requests` data and render latency over time on the chart, with hover tooltips showing URL and latency
- [x] T023 [US4] Update SSE handler in `index.html` to append new data points to the chart in real-time

**Checkpoint**: Latency chart shows data, updates on new requests ✅

---

## Phase 7: User Story 5 — Export Data (P3)

**Goal**: Export filtered requests as CSV or JSON.

**Independent Test**: Apply filter, click export, verify downloaded file contains filtered data.

### Implementation

- [x] T024 [US5] Add `GET /api/export` endpoint in `src/otel_agent/dashboard/api.py` that supports `format=csv` and `format=json` with `Content-Disposition: attachment` header
- [x] T025 [US5] Add "Export CSV" and "Export JSON" buttons in `index.html` that link to `/api/export?format=csv` with current filter params
- [x] T026 [P] [US5] Add test for export: verify `/api/export?format=csv` returns CSV content in `tests/test_dashboard.py`

**Checkpoint**: Export buttons download filtered data ✅

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [x] T027 Update `README.md` with dashboard documentation: `otel-agent dashboard` command, screenshots description, API endpoints
- [x] T028 Run full test suite `uv run pytest tests/ -v -m "not integration"` — all pass
- [x] T029 Run quickstart validation from `specs/004-web-dashboard/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 Browse (Phase 3)**: Depends on Foundational
- **US2 Search/Filter (Phase 4)**: Depends on US1 (needs table to filter)
- **US3 Details (Phase 5)**: Depends on US1 (needs rows to click)
- **US4 Chart (Phase 6)**: Depends on US1 (needs data to chart)
- **US5 Export (Phase 7)**: Depends on US2 (needs filtered data)
- **Polish (Phase 8)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational
- **US2 (P1)**: Depends on US1
- **US3 (P2)**: Depends on US1
- **US4 (P2)**: Depends on US1
- **US5 (P3)**: Depends on US2

### Parallel Opportunities

- T003-T006 are sequential (server.py → api.py → dashboard.py → cli.py)
- T009-T012 are sequential (same file: index.html + api.py)
- T018-T019 can run in parallel (different files: api.py vs index.html)
- T021-T023 are sequential (same file: index.html)
- T024-T025 can run in parallel (different files)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (server + API + CLI)
3. Complete Phase 3: US1 — Request table with auto-refresh
4. **STOP and VALIDATE**: `otel-agent dashboard` → open browser → see requests
5. Continue with remaining stories

### Incremental Delivery

1. Setup + Foundational → Dashboard starts, API returns JSON
2. Add US1 → Request table with auto-refresh (core value!)
3. Add US2 → Search and filter work
4. Add US3 → Click row → full details
5. Add US4 → Latency chart
6. Add US5 → Export data
7. Polish → README updated, tests green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
