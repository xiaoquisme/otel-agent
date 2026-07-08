# Tasks: Models API Endpoint

**Input**: Design documents from `specs/009-models-api/`

**Prerequisites**: plan.md (required), spec.md (required), data-model.md, contracts/models-api.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new models module and test file

- [X] T001 Create `src/otel_agent/models.py` with empty module and imports

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: ModelCache class and fetch logic — blocks all user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 Implement `ModelCache` class in `src/otel_agent/models.py` with TTL-based caching
- [X] T003 Implement `fetch_provider_models()` async function in `src/otel_agent/models.py` — queries provider's GET /v1/models via httpx, returns list of model dicts
- [X] T004 Implement `aggregate_models()` function in `src/otel_agent/models.py` — merges results from all providers, prefixes model IDs with provider name

**Checkpoint**: ModelCache stores and retrieves cached model lists, fetch function queries upstream

---

## Phase 3: User Story 1 — List All Available Models (Priority: P1) 🎯 MVP

**Goal**: GET `/v1/models` returns all models from all providers with provider-name prefixes

**Independent Test**: `curl http://localhost:8080/v1/models` returns JSON with models prefixed by provider name

### Tests for User Story 1 ⚠️

- [X] T005 [P] [US1] Unit tests for `ModelCache` (store, retrieve, TTL expiry) in `tests/test_models.py`
- [X] T006 [P] [US1] Unit tests for `aggregate_models()` (prefix logic, empty providers, unreachable providers) in `tests/test_models.py`

### Implementation for User Story 1

- [X] T007 [US1] Add `GET /v1/models` endpoint to `src/otel_agent/server.py` — calls aggregate, returns OpenAI-format response
- [X] T008 [US1] Implement graceful degradation: unreachable providers return empty list, not error

**Checkpoint**: GET `/v1/models` returns models from all providers in OpenAI format

---

## Phase 4: User Story 2 — Filter by Provider (Priority: P2)

**Goal**: `GET /v1/models?provider=openai` returns only that provider's models

**Independent Test**: `curl "http://localhost:8080/v1/models?provider=openai"` returns only openai models

### Tests for User Story 2 ⚠️

- [X] T009 [P] [US2] Unit tests for provider filter (valid provider, unknown provider, empty filter) in `tests/test_models.py`

### Implementation for User Story 2

- [X] T010 [US2] Add `provider` query parameter to `/v1/models` endpoint in `src/otel_agent/server.py`
- [X] T011 [US2] Implement provider filter logic in `src/otel_agent/models.py`

**Checkpoint**: Provider filter works, unknown provider returns empty list

---

## Phase 5: User Story 3 — Cached Model Discovery (Priority: P2)

**Goal**: Repeated `/v1/models` requests served from cache, config reload invalidates cache

**Independent Test**: Two rapid requests, second is faster (cached). Config change triggers refresh.

### Tests for User Story 3 ⚠️

- [X] T012 [P] [US3] Unit tests for cache TTL (hit within window, miss after expiry) in `tests/test_models.py`
- [X] T013 [P] [US3] Unit tests for cache invalidation on config mtime change in `tests/test_models.py`

### Implementation for User Story 3

- [X] T014 [US3] Wire cache into `/v1/models` endpoint — check cache before fetching upstream
- [X] T015 [US3] Add config mtime tracking to ModelCache — invalidate when config changes

**Checkpoint**: Cached responses <500ms, config changes trigger refresh

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Integration with existing system

- [X] T016 [P] Add `/v1/models` to startup banner in `src/otel_agent/commands/proxy.py`
- [X] T017 Update `README.md` with `/v1/models` endpoint documentation and curl examples
- [X] T018 Run full test suite: `uv run pytest tests/ -v -m "not integration"`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1
- **US1 (Phase 3)**: Depends on Phase 2 — core endpoint
- **US2 (Phase 4)**: Depends on Phase 3 (endpoint must exist to add filter)
- **US3 (Phase 5)**: Depends on Phase 3 (endpoint must exist to add caching)
- **Polish (Phase 6)**: Depends on all user stories

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no dependencies on other stories
- **US2 (P2)**: Can start after US1 — adds query parameter to existing endpoint
- **US3 (P2)**: Can start after US1 — adds caching layer to existing endpoint

### Parallel Opportunities

- T005, T006 can run in parallel (different test functions)
- T009 can run in parallel with T012, T013 (different test functions)
- T016 can run in parallel with T017 (different files)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: US1 — GET `/v1/models` returns all models
4. **STOP and VALIDATE**: Test the endpoint
5. Deploy if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → Test `/v1/models` → Deploy (MVP!)
3. Add US2 → Test provider filter → Deploy
4. Add US3 → Test caching → Deploy

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Use `uv run pytest tests/ -v -m "not integration"` for verification
