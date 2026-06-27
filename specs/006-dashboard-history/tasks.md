# Tasks: Dashboard Shows Historical Requests

**Input**: Design documents from `/specs/006-dashboard-history/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/api.md, quickstart.md

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, etc.)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Verify existing tests pass.

- [x] T001 Verify current test suite passes: `uv run pytest tests/ -v -m "not integration"`

---

## Phase 2: User Story 1 — Historical Data on Load (P1) 🎯 MVP

**Goal**: Dashboard shows all requests stored in the database, not just new ones.

**Independent Test**: Create database with requests, start dashboard API, verify all requests returned.

### Implementation

- [x] T002 [US1] Add test `test_historical_requests_visible` in `tests/test_dashboard.py`: create a database with 10 requests, initialize DashboardAPI, call `get_requests()`, verify all 10 are returned
- [x] T003 [US1] Add test `test_historical_requests_after_new_data` in `tests/test_dashboard.py`: create a database with 5 requests, call `get_requests()`, add 3 more requests, call `get_requests()` again, verify all 8 are returned
- [x] T004 [US1] Add test `test_empty_database_no_crash` in `tests/test_dashboard.py`: create DashboardAPI with non-existent database path, call `get_requests()`, verify returns empty result without error

**Checkpoint**: Historical data tests pass ✅

---

## Phase 3: User Story 2 — Consistent Database Path (P1)

**Goal**: Dashboard reads from the same database regardless of working directory.

**Independent Test**: Verify default DB path is absolute.

### Implementation

- [x] T005 [US2] Add test `test_default_db_path_is_absolute` in `tests/test_cli.py`: parse `otel-agent dashboard` args, verify `args.db` starts with `/` or `~`
- [x] T006 [US2] Add test `test_default_db_path_consistent_across_commands` in `tests/test_cli.py`: parse proxy, view, and dashboard args, verify all use the same default DB path

**Checkpoint**: Consistent path tests pass ✅

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Final validation

- [x] T007 Run full test suite `uv run pytest tests/ -v -m "not integration"` — all pass

---

## Dependencies & Execution Order

- **Phase 1**: No dependencies
- **Phase 2 (US1)**: Depends on Phase 1
- **Phase 3 (US2)**: Can run in parallel with Phase 2
- **Phase 4**: Depends on Phase 2 + 3

## Implementation Strategy

1. Phase 1: Verify tests pass
2. Phase 2: Add historical data tests (US1)
3. Phase 3: Add consistent path tests (US2)
4. Phase 4: Final validation

---

## Notes

- Test-only feature — no production code changes
- All requirements already satisfied by BUG-001/002/003 fixes
- These tests prevent regression
