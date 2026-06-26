# Tasks: Path-Based Routing

**Input**: Design documents from `/specs/002-path-based-routing/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/routing.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, etc.)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No new dependencies or project structure changes needed. This feature modifies existing files only.

- [ ] T001 Verify current test suite passes: `uv run pytest tests/ -v -m "not integration"`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Extend config model with type/prefix fields and validation. All routing depends on this.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T002 Add `type` field (str, default inferred) and `prefix` field (str, default `/<name>`) to `ProviderConfig` dataclass in `src/otel_agent/config.py`
- [ ] T003 Add `_build_route_table()` method to `Config` class that builds a `{prefix: provider_name}` dict from providers in `src/otel_agent/config.py`
- [ ] T004 Add `_validate_routes()` method to `Config` that rejects duplicate prefixes, invalid prefix format, unknown types, and empty base_urls in `src/otel_agent/config.py`
- [ ] T005 Add `get_provider_by_prefix(path: str)` method to `Config` that matches by longest prefix in `src/otel_agent/config.py`
- [ ] T006 Update `_reload()` in `Config` to parse `type` and `prefix` fields from YAML, call `_validate_routes()`, and build route table in `src/otel_agent/config.py`
- [ ] T007 [P] Add tests for type/prefix parsing, prefix inference, type inference, duplicate prefix rejection, and invalid prefix rejection in `tests/test_config.py`
- [ ] T008 Run `uv run pytest tests/test_config.py -v` — all pass

**Checkpoint**: Config loads type/prefix fields, validates routes, rejects duplicates ✅

---

## Phase 3: User Story 1 — Path-Based Provider Selection (P1) 🎯 MVP

**Goal**: Requests to `/openai/v1/chat/completions` route to OpenAI, `/anthropic/v1/messages` route to Anthropic. Prefix is stripped before forwarding.

**Independent Test**: Send `POST /openai/v1/chat/completions` through proxy, verify it reaches OpenAI upstream with correct auth header.

### Implementation

- [ ] T009 [US1] Update `request()` method in `TelemetryAddon` to extract first path segment, call `config.get_provider_by_prefix()`, and rewrite host/scheme/port to provider's base_url in `src/otel_agent/addon.py`
- [ ] T010 [US1] Add `_strip_prefix(path: str, prefix: str) -> str` helper to `TelemetryAddon` that removes the matched prefix from the request path in `src/otel_agent/addon.py`
- [ ] T011 [US1] Update `_inject_auth()` in `TelemetryAddon` to use provider's `type` field instead of host substring matching for auth header selection in `src/otel_agent/addon.py`
- [ ] T012 [US1] Update `KeyRotator.next()` to accept an optional `provider_name` parameter for direct lookup (bypass host matching) in `src/otel_agent/rotator.py`
- [ ] T013 [P] [US1] Add tests for prefix matching, prefix stripping, auth header by type, and fallback to default_provider in `tests/test_addon.py`
- [ ] T014 [US1] Run `uv run pytest tests/test_addon.py -v` — all pass

**Checkpoint**: Requests route by path prefix, prefix stripped, correct auth header injected ✅

---

## Phase 4: User Story 2 — Config Organized by API Style (P1)

**Goal**: Config file supports `type` field per provider, grouping by API style.

**Independent Test**: Config with `type: openai` and `type: anthropic` providers loads correctly and routes with correct auth headers.

### Implementation

- [ ] T015 [US2] Update `DEFAULT_CONFIG` template in `config.py` to include `type` and `prefix` fields with comments in `src/otel_agent/config.py`
- [ ] T016 [P] [US2] Add test for DEFAULT_CONFIG template: verify it loads without errors and has correct type/prefix values in `tests/test_config.py`

**Checkpoint**: Config template includes type/prefix, existing configs without type/prefix still work ✅

---

## Phase 5: User Story 3 — Custom Path Prefixes (P2)

**Goal**: Users can define custom prefixes (e.g., `/deepseek` for a DeepSeek provider).

**Independent Test**: Configure provider with `prefix: /deepseek`. Send request to `/deepseek/v1/chat/completions`. Verify it reaches DeepSeek upstream.

### Implementation

- [ ] T017 [P] [US3] Add test for custom prefix: configure provider with `prefix: /local`, verify `get_provider_by_prefix("/local/v1/chat/completions")` returns that provider in `tests/test_config.py`
- [ ] T018 [P] [US3] Add test for prefix priority: when `/open` and `/openai` both exist, `/openai/v1/...` matches the longer prefix in `tests/test_config.py`

**Checkpoint**: Custom prefixes work, longest-prefix matching correct ✅

---

## Phase 6: User Story 4 — View Route Mapping (P2)

**Goal**: `otel-agent routes` displays the routing table.

**Independent Test**: Run `otel-agent routes`. Verify output shows prefix → provider → type → upstream.

### Implementation

- [ ] T019 [US4] Create `src/otel_agent/commands/routes.py` with `handle_routes(args)` function that loads config and prints a formatted table of prefix → provider → type → base_url
- [ ] T020 [US4] Register `routes` subcommand in `src/otel_agent/cli.py`
- [ ] T021 [P] [US4] Add test for routes command: verify output contains expected prefix/provider/type/upstream in `tests/test_cli.py`

**Checkpoint**: `otel-agent routes` shows routing table ✅

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [ ] T022 Update `README.md` with path-based routing documentation: config format, `otel-agent routes` command, example curl commands
- [ ] T023 Run full test suite `uv run pytest tests/ -v -m "not integration"` — all pass
- [ ] T024 Run quickstart validation from `specs/002-path-based-routing/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 Routing (Phase 3)**: Depends on Foundational
- **US2 Config Style (Phase 4)**: Depends on Foundational
- **US3 Custom Prefixes (Phase 5)**: Depends on Foundational
- **US4 Routes Command (Phase 6)**: Depends on Foundational
- **Polish (Phase 7)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — no dependencies on other stories
- **US2 (P1)**: Can start after Foundational — no dependencies on other stories
- **US3 (P2)**: Can start after Foundational — no dependencies on other stories
- **US4 (P2)**: Can start after Foundational — no dependencies on other stories

### Parallel Opportunities

- T002-T006 are sequential (same file: config.py)
- T007 can run in parallel with T008
- T009-T012 are sequential (same file: addon.py)
- T013 can run in parallel with T014
- T015-T016, T017-T018, T019-T021 can all run in parallel after Phase 2
- T022-T024 are sequential (polish)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (config type/prefix support)
3. Complete Phase 3: User Story 1 (routing by path)
4. **STOP and VALIDATE**: `otel-agent proxy` + `curl /openai/v1/chat/completions` works
5. Continue with remaining stories

### Incremental Delivery

1. Setup + Foundational → Config loads type/prefix, validates routes
2. Add US1 → Path-based routing works (core value!)
3. Add US2 → Config template updated
4. Add US3 → Custom prefixes work
5. Add US4 → `otel-agent routes` works
6. Polish → README updated, tests green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
