# Tasks: Streaming Telemetry Logging Bug

**Input**: Design documents from `specs/019-streaming-telemetry-bug/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Required — constitution Principle II mandates regression tests for all bug fixes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Verify current state — confirm the bug exists before fixing

- [ ] T001 Run existing unit tests to establish baseline: `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/ -x -q -m "not integration"`
- [ ] T002 Manually verify the bug: read `src/otel_agent/server.py:306-363` and confirm `_log_telemetry()` is inside the generator but outside the `try/except` block

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Write regression tests that FAIL before the fix (per constitution Principle II)

**⚠️ CRITICAL**: Tests must be written and confirmed failing before any implementation

### Regression Tests for Streaming Telemetry

- [ ] T003 [US1] Add regression test `test_streaming_telemetry_logged` in `tests/test_server.py` — sends a streaming request through the FastAPI test client with a mock upstream, asserts telemetry record exists with `{"streamed": true, "preview": "..."}` format. **Expected: FAILS before fix.**
- [ ] T004 [US1] Add regression test `test_streaming_client_disconnect` in `tests/test_server.py` — sends a streaming request, closes the client mid-stream, asserts partial telemetry is still logged. **Expected: FAILS before fix.**
- [ ] T005 [US2] Add regression test `test_nonstreaming_after_streaming` in `tests/test_server.py` — sends a streaming request followed by a non-streaming request, asserts BOTH are logged. **Expected: FAILS before fix (if the bug blocks subsequent requests).**

**Checkpoint**: All 3 tests FAIL. Bug is confirmed reproducible. Proceed to implementation.

---

## Phase 3: User Story 1 — Streaming Requests Logged to Dashboard (Priority: P1) 🎯 MVP

**Goal**: Every streaming request is recorded to telemetry, regardless of client disconnect or generator lifecycle.

**Independent Test**: Run `test_streaming_telemetry_logged` and `test_streaming_client_disconnect` — both PASS.

### Implementation for User Story 1

- [ ] T006 [US1] Fix `src/otel_agent/server.py`: move `_log_telemetry()` call from line 360 (after `try/except`) into a `finally` block inside `stream_generator()`, ensuring it executes on both normal completion and `GeneratorExit`/`ClientDisconnect`

**Checkpoint**: `test_streaming_telemetry_logged` and `test_streaming_client_disconnect` now PASS.

---

## Phase 4: User Story 2 — Non-Streaming Requests Still Work After Streaming (Priority: P1)

**Goal**: Non-streaming requests continue to be logged normally after streaming requests.

**Independent Test**: Run `test_nonstreaming_after_streaming` — PASS.

### Implementation for User Story 2

- [ ] T007 [US2] Run `test_nonstreaming_after_streaming` — verify it now passes with the fix from T006 (no additional code change needed if the fix is correct)
- [ ] T008 [US2] Run full test suite: `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest -x -q -m "not integration"` — confirm all existing tests still pass (no regressions)

**Checkpoint**: All tests pass. Both user stories complete.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [ ] T009 Run quickstart.md validation scenarios to confirm end-to-end behavior
- [ ] T010 Code review: verify the `finally` block in `stream_generator()` follows constitution Principle I (functions <50 lines, type hints, docstrings)
- [ ] T011 Run `ruff check src/otel_agent/server.py` — confirm zero linting errors (constitution quality gate)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational — implements the core fix
- **US2 (Phase 4)**: Depends on US1 — validates fix doesn't break non-streaming
- **Polish (Phase 5)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Core fix — must complete first
- **US2 (P1)**: Validation — depends on US1 fix being in place

### Within Each User Story

- Tests written FIRST, confirmed FAILING
- Implementation applied
- Tests confirmed PASSING
- Full test suite run to check for regressions

---

## Parallel Example: Phase 2 Tests

```bash
# All 3 regression tests can be written in parallel (same file but independent test functions):
Task: "T003 test_streaming_telemetry_logged in tests/test_server.py"
Task: "T004 test_streaming_client_disconnect in tests/test_server.py"
Task: "T005 test_nonstreaming_after_streaming in tests/test_server.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Verify baseline
2. Complete Phase 2: Write failing regression tests
3. Complete Phase 3: Apply the `finally` block fix
4. **STOP and VALIDATE**: US1 tests pass
5. Commit: `fix: ensure streaming telemetry always logged via finally block`

### Full Delivery

1. Phase 1-2: Setup + failing tests
2. Phase 3: Core fix (US1)
3. Phase 4: Validation (US2)
4. Phase 5: Polish + lint
5. Commit: single fix commit with regression tests

---

## Notes

- This is a surgical bug fix — single file change (`server.py`), single test file addition (`test_server.py`)
- The `finally` block approach is the simplest reliable pattern (research.md R1)
- Constitution Principle II requires regression test — non-negotiable for merge
- No new modules, no new dependencies, no schema changes
