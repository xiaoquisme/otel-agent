# Tasks: Dashboard Usage Metrics

**Input**: Design documents from `/specs/020-dashboard-usage-metrics/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [dashboard usage API contract](./contracts/dashboard-usage-api.md), [quickstart.md](./quickstart.md)

**Tests**: Tests are required by the implementation plan and project constitution. Write each listed test first and verify it fails before the associated implementation task.

**Organization**: Tasks are grouped by user story so each increment can be implemented, tested, and demonstrated independently after the foundational telemetry projection is complete.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other marked tasks after their stated prerequisites are complete and when they modify different files.
- **[Story]**: Maps a task to its user story from [spec.md](./spec.md).
- All paths are repository-relative.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare deterministic test data and establish the required local validation command without adding dependencies.

- [x] T001 [P] Add reusable current-day UTC timestamp and usage-record fixture helpers to `tests/test_dashboard.py` for aggregate and endpoint tests.
- [x] T002 [P] Add a focused telemetry usage fixture builder for OpenAI, Anthropic, malformed, and streaming response shapes in `tests/test_server.py`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the nullable telemetry analytics projection, idempotent schema compatibility, and typed storage contract required by every user story.

**⚠️ CRITICAL**: Complete this phase before starting User Story phases.

- [x] T003 Add `model_name`, `input_tokens`, `output_tokens`, and `total_tokens` optional fields plus a typed `get_usage_summary()` abstract method to `src/otel_agent/storage/base.py`.
- [x] T004 [P] Add failing legacy-schema upgrade and analytics-column persistence coverage for DuckDB in `tests/test_logger.py`.
- [x] T005 [P] Add failing legacy-schema upgrade and analytics-column persistence coverage for SQLite fallback behavior in `tests/test_dashboard.py`.
- [x] T006 [P] Add failing migration coverage for old and new SQLite source schemas in `tests/test_migration.py`.
- [x] T007 Implement additive, idempotent analytics columns and date-range supporting indexes in `src/otel_agent/storage/duckdb.py`.
- [x] T008 [P] Implement matching additive analytics columns and indexes in `src/otel_agent/storage/sqlite.py`.
- [x] T009 Extend telemetry write signatures to pass nullable model and token fields through `src/otel_agent/logger.py`.
- [x] T010 Update SQLite-to-DuckDB schema creation and row-copy handling for absent/present analytics columns in `src/otel_agent/migration.py`.
- [x] T011 Run the foundational schema and migration tests in `tests/test_logger.py`, `tests/test_dashboard.py`, and `tests/test_migration.py` using the command documented in `specs/020-dashboard-usage-metrics/quickstart.md`.

**Checkpoint**: Both storage backends accept legacy and new request records without data loss, and all user stories can rely on nullable analytics fields.

---

## Phase 3: User Story 1 - View Today's Token Consumption (Priority: P1) 🎯 MVP

**Goal**: Show a viewer-local daily total on the dashboard using provider-reported usage without parsing stored request/response bodies at read time.

**Independent Test**: Create known current-day and out-of-range successful records, open the dashboard usage endpoint, and verify only eligible current-day total tokens are returned and shown in the total card.

### Tests for User Story 1

- [x] T012 [P] [US1] Add failing unit tests for OpenAI/Anthropic non-stream usage normalization, invalid values, provider totals, one-component usage, and `log_request_body=False` in `tests/test_server.py`.
- [x] T013 [P] [US1] Add failing direct and proxy-routed total-only usage-summary tests, zero-state tests, and UTC range-boundary tests in `tests/test_dashboard.py`.
- [x] T014 [US1] Add failing internal and public `/usage` endpoint parameter-validation tests in `tests/test_dashboard.py`.

### Implementation for User Story 1

- [x] T015 [US1] Implement a pure normalized-usage extractor and original client model propagation through the non-stream telemetry path in `src/otel_agent/server.py`.
- [x] T016 [P] [US1] Implement database-side 2xx-only, `[start, end)` total-token aggregation and zero-state response in `src/otel_agent/storage/duckdb.py`.
- [x] T017 [P] [US1] Implement the same total-token aggregation semantics in `src/otel_agent/storage/sqlite.py`.
- [x] T018 [US1] Add proxy-first/direct-fallback `get_usage_summary(start, end)` behavior in `src/otel_agent/dashboard/api.py`.
- [x] T019 [US1] Add `/internal/dashboard/usage` delegation and range parsing/validation for public `GET /api/usage` in `src/otel_agent/server.py` and `src/otel_agent/dashboard/server.py`.
- [x] T020 [US1] Add the semantic “Usage today” total-token section, independent loading/error state, viewer-local UTC day-bound generation, and safe text rendering in `src/otel_agent/dashboard/index.html`.
- [x] T021 [US1] Run the User Story 1 tests in `tests/test_server.py` and `tests/test_dashboard.py`, then manually verify the daily total scenario in `specs/020-dashboard-usage-metrics/quickstart.md`.

**Checkpoint**: A user can open the dashboard and see an accurate current-day total token count, including a clear zero state, while existing request browsing continues to work.

---

## Phase 4: User Story 2 - Compare Usage by Model (Priority: P1)

**Goal**: Add a ranked current-day model breakdown so users can identify the highest-consuming model without conflating model identifiers.

**Independent Test**: Seed multiple exact model identifiers, including an unknown model, with distinct eligible totals and verify deterministic descending aggregation, request counts, and UI order.

### Tests for User Story 2

- [x] T022 [P] [US2] Add failing storage/API tests for descending per-model totals, request counts, stable ties, and separate unknown-model grouping in `tests/test_dashboard.py`.
- [x] T023 [US2] Add failing dashboard rendering tests for exact model labels and API-order preservation in `tests/test_dashboard.py`.

### Implementation for User Story 2

- [x] T024 [P] [US2] Extend the usage-summary model grouping and deterministic order in `src/otel_agent/storage/duckdb.py`.
- [x] T025 [P] [US2] Extend the same model grouping and order in `src/otel_agent/storage/sqlite.py`.
- [x] T026 [US2] Extend the usage overview with a semantic ranked model table, text rank/request count, escaped model labels, and optional non-semantic proportional bars in `src/otel_agent/dashboard/index.html`.
- [x] T027 [US2] Run the model aggregation/rendering tests in `tests/test_dashboard.py` and manually verify the per-model scenario in `specs/020-dashboard-usage-metrics/quickstart.md`.

**Checkpoint**: The dashboard shows all eligible models in descending token order, preserves exact identifiers, and groups valid unknown-model usage separately.

---

## Phase 5: User Story 3 - Understand Metric Coverage and Token Composition (Priority: P2)

**Goal**: Show input/output composition and incomplete-usage coverage, including streaming usage captured before its preview is truncated.

**Independent Test**: Seed or proxy a mix of input-only, output-only, total-only, missing, malformed, and streaming-terminal-usage responses; verify no token counts are invented and excluded completed requests are reported exactly once.

### Tests for User Story 3

- [x] T028 [P] [US3] Add failing aggregate tests for nullable input/output sums, valid total-only records, malformed/negative values, non-2xx exclusion, and historical null analytics fields in `tests/test_dashboard.py`.
- [x] T029 [P] [US3] Add failing streaming tests for terminal usage capture, interrupted streams without usage, and malformed chunks in `tests/test_server.py`.
- [x] T030 [US3] Add failing dashboard rendering tests for component totals, excluded-count copy, and no fabricated zero/missing components in `tests/test_dashboard.py`.

### Implementation for User Story 3

- [x] T031 [US3] Retain the latest valid normalized usage while iterating streaming chunks and pass it to final telemetry logging in `src/otel_agent/server.py`.
- [x] T032 [P] [US3] Extend usage aggregation with nullable input/output totals and exactly-once excluded completed-request counts in `src/otel_agent/storage/duckdb.py`.
- [x] T033 [P] [US3] Implement matching composition and coverage aggregation semantics in `src/otel_agent/storage/sqlite.py`.
- [x] T034 [US3] Render labeled input/output metric values, non-error incomplete-coverage copy, accessible update status, and zero-usage explanatory text in `src/otel_agent/dashboard/index.html`.
- [x] T035 [US3] Run the composition and streaming tests in `tests/test_dashboard.py` and `tests/test_server.py`, then manually verify the coverage and streaming scenarios in `specs/020-dashboard-usage-metrics/quickstart.md`.

**Checkpoint**: Users can distinguish input/output consumption and understand exactly when completed requests were excluded without estimating any provider usage.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verify performance, responsive accessibility, backward compatibility, and full feature behavior across user stories.

- [x] T036 [P] Add a 100,000-request aggregate performance regression test with a two-second assertion in `tests/test_dashboard.py`.
- [x] T037 Add narrow-viewport, semantic-label, no-color-only, and `aria-live` usage-overview assertions for `src/otel_agent/dashboard/index.html` in `tests/test_dashboard.py`.
- [x] T038 Verify schema migration preserves pre-feature records and the dashboard displays their incomplete coverage without errors using `tests/test_migration.py` and `tests/test_dashboard.py`.
- [x] T039 Run the full deterministic regression gate configured in `pyproject.toml`: `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest -m 'not integration'`.
- [x] T040 Execute every scenario in `specs/020-dashboard-usage-metrics/quickstart.md`, record actual results in the implementation PR/summary, and fix any discovered regression.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Can start immediately; T001 and T002 are parallel.
- **Phase 2 (Foundational)**: Starts after setup fixtures exist. T003 blocks T007–T010; T004–T006 are test-first work that can proceed in parallel. T011 verifies the completed foundation and blocks all user stories.
- **Phase 3 (US1)**: Starts after T011. T012 and T013 may run in parallel; T014 follows the shared dashboard test fixture changes. T015–T020 are ordered by the telemetry-to-storage-to-API-to-UI flow; T021 closes the MVP.
- **Phase 4 (US2)**: Starts after US1’s query and UI foundation is available (T021). T022 precedes T023 because both modify the dashboard test file; T024–T025 may run in parallel, then T026 and T027.
- **Phase 5 (US3)**: Starts after US1’s telemetry and aggregate foundation is available (T021). It may proceed in parallel with US2 after T021; T028 and T029 may run in parallel, T030 follows the dashboard aggregate tests, then T031–T034 and T035.
- **Phase 6 (Polish)**: Starts after US2 and US3 checkpoints are complete.

### User Story Dependencies

- **US1 (P1)**: Depends only on the shared foundational analytics projection. It is the recommended MVP.
- **US2 (P1)**: Depends on US1’s usage endpoint and overview shell, but can be developed in parallel with US3 after US1 is stable.
- **US3 (P2)**: Depends on US1’s normalized telemetry and aggregate endpoint, but does not depend on US2’s model table.

### Parallel Opportunities

- T001/T002; T004/T005/T006; T007/T008 after T003; and T016/T017 after T015 can be executed in parallel.
- US1 test tasks T012 and T013 are independent; T014 follows the dashboard test changes.
- After T021, US2 and US3 can be staffed in parallel; within them, T024/T025, T028/T029, and T032/T033 are independent pairs.
- T036 can run alongside polish work that does not modify `tests/test_dashboard.py`.

---

## Parallel Example: User Story 2

```text
# Storage implementations modify different files and can run together:
Task: "T024 Extend model grouping in src/otel_agent/storage/duckdb.py"
Task: "T025 Extend model grouping in src/otel_agent/storage/sqlite.py"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 and Phase 2 to establish compatible analytics persistence.
2. Complete Phase 3 through T021.
3. Stop and verify the exact daily total, empty state, UTC day boundary, and active-proxy behavior.
4. Demonstrate the dashboard total before expanding it with model and coverage detail.

### Incremental Delivery

1. Foundation → legacy-safe persistence and typed aggregation boundary.
2. US1 → current-day total-token overview (MVP).
3. US2 → ranked model comparison.
4. US3 → composition, streaming usage, and incomplete-coverage transparency.
5. Polish → performance, accessibility, migration, and complete quickstart validation.

## Notes

- Every task follows the required checkbox, sequential ID, optional parallel marker, optional story label, and exact-file-path format.
- Avoid direct dashboard DuckDB aggregates while the proxy is active; route usage reads through the existing proxy-safe path.
- Do not add token estimation, cost, budget, alerting, or custom date-range controls in this feature.