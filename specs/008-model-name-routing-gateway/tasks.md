# Tasks: Model-Name-Based Routing Gateway

**Input**: Design documents from `specs/008-model-name-routing-gateway/`

**Prerequisites**: plan.md (required), spec.md (required)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Remove mitmproxy, add FastAPI/httpx dependencies

- [X] T001 Update `pyproject.toml`: remove `mitmproxy` dependency, add `fastapi`, `uvicorn`, `httpx`
- [X] T002 Run `uv sync --group dev` to install new dependencies
- [X] T003 [P] Remove `src/otel_agent/addon.py` (mitmproxy addon)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: New config schema and model-name router — blocks all user stories

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Rewrite `src/otel_agent/config.py`: new flat provider list schema with `api_format` field, hot-reload, validation
- [X] T005 [P] Create `src/otel_agent/router.py`: `parse_model()` and `resolve_provider()` functions
- [X] T006 Update `src/otel_agent/rotator.py`: simplify to work with new config (or merge into config)
- [X] T007 Update default config template in `src/otel_agent/commands/init.py`

**Checkpoint**: Config loads, model parsing works, provider resolution works

---

## Phase 3: User Story 1 — Model-Name-Based Provider Routing (Priority: P1) 🎯 MVP

**Goal**: Requests with `model: "openai/gpt-5.4"` route to the OpenAI provider

**Independent Test**: Send request with model prefix, verify correct upstream routing

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T008 [P] [US1] Unit tests for `parse_model()` in `tests/test_router.py`
- [X] T009 [P] [US1] Unit tests for `resolve_provider()` in `tests/test_router.py`

### Implementation for User Story 1

- [X] T010 Create `src/otel_agent/server.py`: FastAPI app with `/v1/chat/completions` endpoint
- [X] T011 [US1] Implement upstream forwarding via httpx (non-streaming first)
- [X] T012 [US1] Implement streaming SSE passthrough for `/v1/chat/completions`
- [X] T013 [US1] Update `src/otel_agent/commands/proxy.py`: start uvicorn instead of mitmproxy
- [X] T014 [US1] Update `src/otel_agent/process.py` for uvicorn process management

**Checkpoint**: OpenAI-format requests route correctly by model name prefix

---

## Phase 4: User Story 2 — Dual API Format Endpoints (Priority: P1)

**Goal**: Anthropic-format requests accepted at `/v1/messages`, with format conversion

**Independent Test**: Send Anthropic-format request, verify routing + conversion

### Tests for User Story 2 ⚠️

- [X] T015 [P] [US2] Unit tests for Anthropic→OpenAI conversion in `tests/test_converter.py`
- [X] T016 [P] [US2] Unit tests for OpenAI→Anthropic conversion in `tests/test_converter.py`

### Implementation for User Story 2

- [X] T017 [P] [US2] Create `src/otel_agent/converter.py`: Anthropic ↔ OpenAI message format conversion
- [X] T018 [US2] Add `/v1/messages` endpoint to FastAPI app (Anthropic format)
- [X] T019 [US2] Implement format conversion routing: detect mismatch, convert, forward, convert back
- [X] T020 [US2] Implement streaming format conversion for both directions

**Checkpoint**: Both OpenAI and Anthropic SDK clients work, with cross-format conversion

---

## Phase 5: User Story 3 — Provider Configuration Registry (Priority: P1)

**Goal**: Flat provider list config with hot-reload and validation

**Independent Test**: Edit config, verify hot-reload without restart

### Tests for User Story 3 ⚠️

- [X] T021 [P] [US3] Update `tests/test_config.py` for new flat schema
- [X] T022 [P] [US3] Test config validation (missing fields, duplicate names, invalid api_format)

### Implementation for User Story 3

- [X] T023 [US3] Wire config hot-reload into FastAPI request lifecycle
- [X] T024 [US3] Update `src/otel_agent/commands/routes.py` to show model-name routing table
- [X] T025 [US3] Update `src/otel_agent/commands/doctor.py` health checks for new architecture

**Checkpoint**: Config changes take effect without restart, validation errors are clear

---

## Phase 6: User Story 4 — Telemetry and Request Logging (Priority: P2)

**Goal**: All requests logged with model name and provider info

**Independent Test**: Send request, query SQLite, verify logged

### Implementation for User Story 4

- [X] T026 Update `src/otel_agent/logger.py`: add `model` and `provider` fields to logged data
- [X] T027 Wire telemetry logging into FastAPI response handler
- [X] T028 Update `src/otel_agent/viewer.py` to display model/provider columns

**Checkpoint**: Telemetry works end-to-end with new architecture

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Updates that affect the overall product

- [X] T029 Update `README.md`: new architecture, config format, client usage examples
- [X] T030 Update `src/otel_agent/cli.py` if any CLI flags changed
- [X] T031 Remove dead code: `test_addon.py`, any mitmproxy references
- [X] T032 Run full test suite: `uv run pytest tests/ -v -m "not integration"`
- [X] T033 Update `specs/008-model-name-routing-gateway/tasks.md` — mark all tasks complete

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — core routing
- **US2 (Phase 4)**: Depends on Phase 3 (needs server.py to exist)
- **US3 (Phase 5)**: Depends on Phase 2 (config is foundational)
- **US4 (Phase 6)**: Depends on Phase 3 (needs server to wire logging into)
- **Polish (Phase 7)**: Depends on all user stories

### Parallel Opportunities

- T008, T009 can run in parallel (both in test_router.py but test different functions)
- T015, T016 can run in parallel
- T021, T022 can run in parallel
- US3 config work can run in parallel with US1 server work (different files)

---

## Notes

- Follow RED→GREEN: write tests first, confirm failure, then implement
- Only mark `[X]` after code + tests pass
- Commit after each task or logical group
- Use `uv run pytest tests/ -v -m "not integration"` for verification
