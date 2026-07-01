# Tasks: Multi-Provider Routing

**Input**: Design documents from `/specs/007-multi-provider-routing/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/routing.md, quickstart.md
**Tests**: Included where needed to satisfy existing test suite and constitution quality gates
**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Update shared config defaults and documentation to the new provider-type schema.

- [x] T001 [P] Update default config template to provider-type schema in src/otel_agent/config.py
- [x] T002 [P] Update README config examples to provider-type schema in README.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core config/routing changes that MUST complete before ANY user story work.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 Refactor config data model for provider-type lists and provider entries in src/otel_agent/config.py
- [x] T004 Add active-provider validation rules in src/otel_agent/config.py
- [x] T005 Remove host-based routing fallback from Config in src/otel_agent/config.py
- [x] T006 [P] Update existing config tests for schema and validation changes in tests/test_config.py

**Checkpoint**: Foundation ready — config loads new schema, enforces one active provider per type, and old host routing is removed.

---

## Phase 3: User Story 1 - Configure Multiple Providers (Priority: P1) 🎯 MVP

**Goal**: Users can define multiple providers under each type with exactly one active provider per type.

**Independent Test**: Create a config with two OpenAI providers and one marked active, start the proxy, and verify the active provider is used while the inactive provider is ignored.

### Implementation for User Story 1

- [x] T007 [US1] Update init command to emit new provider-type config in src/otel_agent/commands/init.py
- [x] T008 [US1] Update config show/edit masking for new schema in src/otel_agent/commands/config_cmd.py
- [x] T009 [P] [US1] Add provider-type config parsing and validation tests in tests/test_config.py

**Checkpoint**: User Story 1 should be fully functional and testable independently — config parsing, active validation, and init/show/edit all work.

---

## Phase 4: User Story 2 - Route Requests Through Standardized Paths (Priority: P1)

**Goal**: Remove old routing behavior and forward only `/openai` and `/anthropic` paths to the active provider.

**Independent Test**: Send requests to `/openai` and `/anthropic` and verify they reach the correct active provider; verify old host/prefix fallback paths no longer match.

### Implementation for User Story 2

- [x] T010 [US2] Rewrite addon request routing to provider-type lookup only in src/otel_agent/addon.py; also update startup display in src/otel_agent/commands/proxy.py to use new provider-type model
- [x] T011 [US2] Update auth injection to use active provider credentials in src/otel_agent/addon.py
- [x] T012 [US2] Simplify rotator to provider api_key selection in src/otel_agent/rotator.py
- [x] T013 [P] [US2] Add provider-path-only routing tests in tests/test_addon.py

**Checkpoint**: User Story 2 should be fully functional and testable independently — standardized routes work and old routing is removed.

---

## Phase 5: User Story 3 - View Active Provider Assignments (Priority: P2)

**Goal**: Users can view the currently active provider for each type via CLI output.

**Independent Test**: Run routes/status command and verify it reports exactly one active provider per configured type, or reports missing configuration.

### Implementation for User Story 3

- [x] T014 [US3] Update routes command to display active provider per type in src/otel_agent/commands/routes.py
- [x] T015 [US3] Add provider status output behavior in src/otel_agent/commands/routes.py
- [x] T016 [P] [US3] Add routes/status CLI tests in tests/test_cli.py

**Checkpoint**: User Story 3 should be fully functional and testable independently — status output shows active assignments clearly.

---

## Phase 6: User Story 4 - Handle Provider Failures Gracefully (Priority: P3)

**Goal**: Users receive clear error messages when the active provider is unreachable or misconfigured.

**Independent Test**: Configure an invalid active provider and verify error messages identify the provider and failure cause without masking upstream errors.

### Implementation for User Story 4

- [x] T017 [US4] Ensure startup/runtime errors identify invalid active-provider state in src/otel_agent/config.py (reopened — BUG-002)
- [x] T018 [US4] Ensure upstream/provider errors are surfaced clearly in src/otel_agent/addon.py (reopened — BUG-002)
- [x] T019 [P] [US4] Add error-path tests in tests/test_config.py and tests/test_addon.py (reopened — BUG-002)
- [x] T025 [US4] Enhance connection error handling with specific exception types and actionable diagnostics in src/otel_agent/addon.py [BUG-002]

**Checkpoint**: User Story 4 should be fully functional and testable independently — errors are actionable and identify the active provider.

**Bugfix**: 2026-06-30 — BUG-002 Reopened T017-T019 (error messages still generic); added T025 for enhanced connection error diagnostics

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, docs, and quality gates across all stories.

- [x] T020 [P] Update doctor validation for new provider schema in src/otel_agent/commands/doctor.py
- [x] T021 Update README to document provider-type config and removed routing behavior in README.md
- [x] T022 Run quickstart.md validation (N/A — no quickstart.md exists) scenarios
- [x] T023 Lint and pytest pass (92 passed, 2 integration deselected)
- [x] T024 [US2] Fix proxy startup display in src/otel_agent/commands/proxy.py to iterate config.provider_types and display active provider info using new ProviderType/ProviderEntry model (BUG-001)

**Bugfix**: 2026-06-30 — BUG-001 Added T024 for proxy.py startup display; expanded T010 scope to cover proxy.py.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can proceed sequentially in priority order: US1/US2 (P1) → US3 (P2) → US4 (P3)
  - US1 and US2 are both P1 and can be worked in parallel after Foundation if staffed
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Foundational — no dependencies on other stories
- **User Story 2 (P1)**: Depends on Foundational — no dependencies on other stories
- **User Story 3 (P2)**: Depends on Foundational — integrates with US1/US2 data but independently testable
- **User Story 4 (P3)**: Depends on Foundational — builds on US2 error behavior but independently testable

### Within Each User Story

- Models/config before routing/CLI behavior
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel within Phase 2
- After Foundation: US1 and US2 can start in parallel
- All tests marked [P] within a story can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 1

```bash
# Launch in parallel after Foundation:
Task: "Update init command to emit new provider-type config in src/otel_agent/commands/init.py"
Task: "Update config show/edit masking for new schema in src/otel_agent/commands/config_cmd.py"
Task: "Add provider-type config parsing and validation tests in tests/test_config.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Complete Phase 4: User Story 2
5. **STOP and VALIDATE**: Test US1 + US2 independently end-to-end
6. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently
3. Add User Story 2 → Test independently → Deploy/Demo (MVP!)
4. Add User Story 3 → Test independently → Deploy/Demo
5. Add User Story 4 → Test independently → Deploy/Demo

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
3. After P1 stories complete:
   - Developer A: User Story 3
   - Developer B: User Story 4
4. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same-file conflicts, cross-story dependencies that break independence
