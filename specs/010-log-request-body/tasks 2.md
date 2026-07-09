# Tasks: Log Request Bodies and Response Headers to Database

**Input**: Design documents from `specs/010-log-request-body/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/telemetry-logging.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Sensitive header redaction helper — needed by both user stories

^- [x] T001 [P] Add `redact_sensitive_headers(headers: dict[str, str]) -> dict[str, str]` helper function in src/otel_agent/logger.py that replaces values of `authorization`, `x-api-key`, and `set-cookie` keys (case-insensitive) with `[REDACTED]`
^- [x] T002 [P] Add unit test for `redact_sensitive_headers` in tests/test_logger.py — verify known headers redacted, other headers pass through, case-insensitive matching works

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core changes that ALL user stories depend on

^- [x] T003 Update `_log_telemetry` signature in src/otel_agent/server.py to accept `request_body: str = ""`, `resp_headers: dict | None = None`, and `log_body: bool = True`; store request_body (truncated to 100,000 chars) and redacted response_headers via `telemetry.log_request()`
^- [x] T004 [P] Add unit test for `_log_telemetry` with request_body and resp_headers in tests/test_server.py — verify both fields are stored in DB, sensitive headers redacted, empty body when log_body=False

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Complete Telemetry Data Persisted in DB (Priority: P1) 🎯 MVP

**Goal**: Request bodies and response headers are stored in the SQLite telemetry database for every request

**Independent Test**: Send a request through the gateway, query the SQLite DB, confirm `request_body` is non-empty and `response_headers` contains upstream headers with sensitive values redacted

### Implementation for User Story 1

^- [x] T005 [US1] In `_handle_non_streaming` in src/otel_agent/server.py: capture `resp.headers` as a plain dict, pass the original `body` dict (serialized to JSON) and captured headers to `_log_telemetry`
^- [x] T006 [US1] In `_handle_streaming` in src/otel_agent/server.py: capture `resp.headers` from the `async with client.stream(...)` context as a plain dict, pass the original `body` dict (serialized to JSON) and captured headers to `_log_telemetry`
^- [x] T007 [US1] In both endpoint handlers (`chat_completions` and `messages`) in src/otel_agent/server.py: pass the original client request body (before format conversion) to the handler functions so it can be forwarded to `_log_telemetry`
^- [x] T008 [US1] Update `format_request` in src/otel_agent/viewer.py to display `response_headers` (truncated to 200 chars) on a new line after the request body
^- [x] T009 [US1] Add test in tests/test_viewer.py for `format_request` showing response_headers in output
^- [x] T010 [US1] Add integration test in tests/test_integration.py: send a request through FastAPI test client, verify `request_body` and `response_headers` are stored correctly in the DB, verify sensitive headers are redacted

**Checkpoint**: User Story 1 complete — request bodies and response headers are logged

---

## Phase 4: User Story 2 - Configurable Logging (Priority: P2)

**Goal**: Users can disable request body logging via `log_request_body: false` in config

**Independent Test**: Set `log_request_body: false` in config, send requests, verify `request_body` is empty string while `response_headers` are still populated

### Implementation for User Story 2

^- [x] T011 [US2] Add `log_request_body` property to the `Config` class in src/otel_agent/config.py — reads top-level boolean from config YAML, defaults to `True` when absent
^- [x] T012 [US2] Thread `log_request_body` config value from `create_app` through to `_log_telemetry` calls in src/otel_agent/server.py (pass to endpoint handlers, then to handler functions, then to `_log_telemetry`)
^- [x] T013 [US2] Add unit test for `Config.log_request_body` in tests/test_config.py — verify default is True, explicit false is respected, hot-reload works
^- [x] T014 [US2] Add integration test in tests/test_integration.py: configure `log_request_body: false`, send request, verify `request_body` is empty string and `response_headers` still populated

**Checkpoint**: User Story 2 complete — configurable body logging works

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

^- [x] T015 Run quickstart.md validation scenarios end-to-end in tests/test_integration.py — all 5 scenarios pass
^- [x] T016 Run full test suite: `uv run pytest tests/ -v -m "not integration"` — all pass, zero failures
^- [x] T017 Run linter: `uv run ruff check src/ tests/` — zero warnings, zero errors

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — can start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 (T001 redaction helper needed by T003)
- **Phase 3 (US1)**: Depends on Phase 2 (T003/T004 must be complete)
- **Phase 4 (US2)**: Depends on Phase 2 and Phase 3 (T003 config threading, T005-T007 body passing)
- **Phase 5 (Polish)**: Depends on all prior phases

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Phase 2. No dependencies on other stories.
- **User Story 2 (P2)**: Starts after Phase 2. Depends on US1 body/header passing being in place.

### Parallel Opportunities

- T001 and T002 can run in parallel (different concerns: helper vs test)
- T003 and T004 can run in parallel (implementation vs test)
- Within US1: T005, T006, T007 can be done together as a single server.py edit; T008 and T009 are independent of T005-T007
- Within US2: T011 and T013 can run in parallel (config implementation vs test)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Add redact_sensitive_headers helper
2. Complete Phase 2: Update _log_telemetry signature
3. Complete Phase 3: Wire up request body and response header capture
4. **STOP and VALIDATE**: Send request, verify DB has data
5. Deploy if ready

### Incremental Delivery

1. Phase 1+2 → Foundation ready
2. Phase 3 (US1) → Bodies and headers logged → Deploy (MVP!)
3. Phase 4 (US2) → Configurable opt-out → Deploy
4. Phase 5 → Polish and validation
