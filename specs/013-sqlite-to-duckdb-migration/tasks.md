# Tasks: SQLite to DuckDB Migration

**Input**: Design documents from `/specs/013-sqlite-to-duckdb-migration/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in spec. Tests are included for migration correctness (FR-003: zero data loss) as they are critical for this feature.

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

**Purpose**: Add DuckDB dependency and create foundational utilities

- [x] T001 Add `duckdb>=1.1.0` to `[project.dependencies]` in `pyproject.toml` and run `uv sync`
- [x] T002 [P] Create `src/otel_agent/migration.py` with `needs_migration(db_path: Path) -> bool` function that checks if `.db` extension exists and `.duckdb` equivalent doesn't
- [x] T003 [P] Create `src/otel_agent/db_compat.py` with `rows_to_dicts(cursor, rows) -> list[dict]` helper that converts DuckDB result tuples to dictionaries using cursor.description, and `get_connection(db_path, read_only=False)` that wraps `duckdb.connect()` with fallback to `sqlite3`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration module that ALL user stories depend on

- [x] T004 [US1] Implement `migrate_sqlite_to_duckdb(sqlite_path: Path, duckdb_path: Path) -> bool` in `src/otel_agent/migration.py` — reads all rows from SQLite via stdlib `sqlite3`, creates DuckDB database with same schema, inserts all rows, creates indexes, verifies row count, renames `.db` to `.db.bak`
- [x] T005 [US1] Add migration test in `tests/test_migration.py` — create SQLite DB with 100 rows, migrate to DuckDB, verify row count matches and data integrity

**Checkpoint**: Migration module ready — can convert existing SQLite databases to DuckDB

---

## Phase 3: User Story 1 - Transparent Storage Migration (Priority: P1) 🎯 MVP

**Goal**: TelemetryLogger writes to DuckDB instead of SQLite, with automatic migration of existing `.db` files.

**Independent Test**: Start proxy, send requests, verify they appear in `.duckdb` file. Verify existing `.db` files are migrated.

### Implementation for User Story 1

- [x] T006 [US1] Modify `src/otel_agent/logger.py` — replace `import sqlite3` with `from otel_agent.db_compat import get_connection, rows_to_dicts`, update `TelemetryLogger.__init__()` to call `needs_migration()` and `migrate_sqlite_to_duckdb()` if needed, then connect via `get_connection()`, remove `PRAGMA journal_mode=WAL` (DuckDB uses MVCC)
- [x] T007 [US1] Update `_create_tables()` in `src/otel_agent/logger.py` — change `INTEGER PRIMARY KEY AUTOINCREMENT` to `INTEGER PRIMARY KEY` (DuckDB auto-increments INTEGER PK), keep `CREATE INDEX IF NOT EXISTS` statements
- [x] T008 [US1] Update `log_request()` in `src/otel_agent/logger.py` — ensure `conn.execute()` and `conn.commit()` work with DuckDB connection (API is identical to sqlite3)
- [x] T009 [US1] Update `close()` in `src/otel_agent/logger.py` — ensure `conn.close()` works with DuckDB connection
- [x] T010 [US1] Update `tests/test_logger.py` — change any sqlite3-specific assertions to work with DuckDB (e.g., `tmp_path / "test.duckdb"` instead of `test.db`)

**Checkpoint**: Proxy logs to DuckDB, existing `.db` files auto-migrated

---

## Phase 4: User Story 2 - Dashboard Query Compatibility (Priority: P2)

**Goal**: DashboardAPI reads from DuckDB with identical query behavior.

**Independent Test**: Open dashboard, verify request list, detail view, search/filter, export all work.

### Implementation for User Story 2

- [x] T011 [P] [US2] Modify `src/otel_agent/dashboard/api.py` — replace `import sqlite3` with `from otel_agent.db_compat import get_connection, rows_to_dicts`, update `DashboardAPI.__init__()` to use `get_connection()`, remove `PRAGMA journal_mode=WAL`, remove `conn.row_factory = sqlite3.Row`
- [ ] T012 [US2] ⚠️ Reopened (BUG-001) Update `_get_conn()` in `src/otel_agent/dashboard/api.py` — use `get_connection(db_path, read_only=True)` for dashboard reads. **BLOCKED**: DuckDB does not support multi-process concurrent access. `read_only=True` does not bypass the exclusive file lock. Requires architectural fix (see T021).
- [x] T013 [US2] Update all query methods in `src/otel_agent/dashboard/api.py` — replace `dict(r)` with `rows_to_dicts(conn.description, [r])` pattern for converting DuckDB tuples to dicts, update `CountCache.get()` to work with DuckDB cursor
- [x] T014 [US2] Update `tests/test_dashboard_api.py` — change sqlite3-specific setup to DuckDB, verify all query methods return correct results

**Checkpoint**: Dashboard works identically with DuckDB backend

---

## Phase 5: User Story 3 - CLI Viewer Compatibility (Priority: P3)

**Goal**: CLI viewer reads from DuckDB with identical output format.

**Independent Test**: Run `otel-agent view --db ./data/requests.duckdb` and verify output format.

### Implementation for User Story 3

- [x] T015 [P] [US3] Modify `src/otel_agent/viewer.py` — replace `import sqlite3` with `from otel_agent.db_compat import get_connection, rows_to_dicts`, update `query_requests()` to use `get_connection()` and `rows_to_dicts()`
- [x] T016 [US3] Update `tests/test_viewer.py` — change sqlite3-specific setup to DuckDB, verify output format matches expected

**Checkpoint**: CLI viewer works with DuckDB

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Config defaults, startup integration, and final verification

- [x] T017 Update default db path in `src/otel_agent/config.py` — change default extension from `.db` to `.duckdb`, ensure `--db` flag accepts both extensions
- [x] T018 Update `src/otel_agent/commands/proxy.py` — import migration module, call `needs_migration()` + `migrate_sqlite_to_duckdb()` on startup before creating TelemetryLogger
- [x] T019 Run `uv run pytest tests/ -v` to verify all tests pass with DuckDB backend
- [x] T020 Run quickstart.md validation scenarios (fresh install, migration, dashboard, CLI, fallback) to confirm end-to-end functionality

---

## Phase 7: Concurrency Fix (BUG-001)

**Purpose**: Solve multi-process concurrent access — DuckDB exclusive file lock prevents proxy (writer) + dashboard (reader) from sharing a `.duckdb` file.

- [ ] T021 [US2] Design and implement architectural fix for concurrent access: route dashboard reads through the proxy process via internal HTTP API (proxy exposes `/internal/dashboard/requests` etc.), dashboard server calls proxy's internal API instead of opening its own DuckDB connection. Update `src/otel_agent/dashboard/server.py` to proxy API calls to the running proxy instance.
- [ ] T022 [US2] Update `src/otel_agent/dashboard/api.py` — modify `DashboardAPI` to use HTTP calls to the proxy's internal API when proxy is running, fall back to direct DuckDB connection for offline/CLI use. Handle proxy-not-running gracefully.
- [ ] T023 [US2] Add concurrency integration test in `tests/test_integration.py` — start proxy, start dashboard, send requests, verify dashboard receives them via SSE without lock errors. Verify no `IOException` on concurrent access.

## Dependencies & Execution Order

**Bugfix**: 2026-07-09 — BUG-001 Updated from bugfix patch. T012 reopened; new tasks T021-T023 added.

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on T001 (duckdb installed) — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Phase 2 (migration module + db_compat)
- **User Story 2 (Phase 4)**: Depends on Phase 2 (db_compat helper) — can run parallel with US1
- **User Story 3 (Phase 5)**: Depends on Phase 2 (db_compat helper) — can run parallel with US1/US2
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Phase 2 — core storage migration
- **User Story 2 (P2)**: Depends on Phase 2 — can start after db_compat exists, independent of US1
- **User Story 3 (P3)**: Depends on Phase 2 — can start after db_compat exists, independent of US1/US2

### Within Each User Story

- db_compat helper before module changes
- Module changes before test updates
- Tests should pass after each story

### Parallel Opportunities

- T002 + T003 (Setup: migration + db_compat) — different files, no dependencies
- T011 (US2 dashboard api) can start as soon as T003 (db_compat) is done, parallel with US1
- T015 (US3 viewer) can start as soon as T003 (db_compat) is done, parallel with US1/US2

---

## Parallel Example: Setup Phase

```bash
# Launch both foundational tasks together:
Task: "Create migration.py with needs_migration() in src/otel_agent/migration.py"
Task: "Create db_compat.py with rows_to_dicts() and get_connection() in src/otel_agent/db_compat.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T005)
3. Complete Phase 3: User Story 1 (T006-T010)
4. **STOP and VALIDATE**: Start proxy, send requests, verify DuckDB storage + migration
5. Deploy if ready — core storage migration works

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test: proxy logs to DuckDB → Deploy (MVP!)
3. Add User Story 2 → Test: dashboard works → Deploy
4. Add User Story 3 → Test: CLI viewer works → Deploy
5. Polish phase → Config defaults, startup migration → Done

### Parallel Team Strategy

With multiple developers:
1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (logger + migration)
   - Developer B: User Story 2 (dashboard api)
   - Developer C: User Story 3 (viewer)
3. Stories complete and integrate independently
