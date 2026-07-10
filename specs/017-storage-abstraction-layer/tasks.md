# Tasks: Storage Abstraction Layer

**Input**: Design documents from `/specs/017-storage-abstraction-layer/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: No new test tasks — existing 127 tests serve as regression suite.

**Organization**: 3 user stories across 5 phases.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (Storage Package Structure)

**Purpose**: Create the storage package with the ABC interface

- [X] T001 Create storage package directory `src/otel_agent/storage/` with empty `__init__.py`
- [X] T002 Create `src/otel_agent/storage/base.py` — define `StorageBackend` ABC with all 8 abstract methods: `initialize()`, `log_request()`, `get_requests()`, `get_request()`, `get_requests_since()`, `get_max_id()`, `get_all_filtered()`, `close()`. Include complete docstrings per data-model.md signatures.
- [X] T003 [P] Create `src/otel_agent/storage/__init__.py` — implement `create_storage(backend, db_path, read_only)` factory function with `BACKENDS` dict mapping `"duckdb" → DuckDBStorage`, `"sqlite" → SQLiteStorage`. Include fallback logic and error handling per research.md Decision 2.

---

## Phase 2: User Story 2 - Refactor Existing DuckDB Backend (Priority: P2) 🎯 MVP

**Goal**: Move all DuckDB code from logger/viewer/dashboard-api into a backend class that implements StorageBackend.

**Independent Test**: Run `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/ -v -m "not integration"` — all 127 tests pass with no test code changes.

### Implementation for User Story 2

- [X] T004 [US2] Create `src/otel_agent/storage/duckdb.py` — implement `DuckDBStorage(StorageBackend)`. Move table creation SQL from `logger.py:_create_tables()` into `initialize()`. Move INSERT logic from `logger.py:log_request()` into `log_request()`. Move all SELECT logic from `dashboard/api.py` into `get_requests()`, `get_request()`, `get_requests_since()`, `get_max_id()`, `get_all_filtered()`. Use `duckdb.connect()` for connection management.

- [X] T005 [US2] Refactor `src/otel_agent/logger.py` — replace `self.conn = get_connection(...)` and `self._create_tables()` with `self.storage = create_storage('duckdb', db_path)`. Replace `self.conn.execute(...)` in `log_request()` with `self.storage.log_request(...)`. Replace `self.conn.close()` with `self.storage.close()`. Remove `from otel_agent.db_compat import get_connection` import.

- [X] T006 [US2] Refactor `src/otel_agent/viewer.py` — replace `get_connection()` + `conn.execute()` with `create_storage('duckdb', db_path, read_only=True)`. Call `storage.get_all_filtered()` or equivalent. Remove `from otel_agent.db_compat import get_connection` import.

- [X] T007 [US2] Refactor `src/otel_agent/dashboard/api.py` — inject `StorageBackend` instance. Replace all `conn.execute(...)` calls in `get_requests()`, `get_request()`, `get_requests_since()`, `get_max_id()`, `get_all_filtered()` with backend method calls. Keep `CountCache` and proxy routing logic (BUG-001/BUG-002) in the API layer. Remove `from otel_agent.db_compat import get_connection, rows_to_dicts` imports.

- [X] T008 [US2] Run full test suite: `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/ -v -m "not integration"` — verify all 127 tests pass with zero failures.

**Checkpoint**: DuckDB backend works through the abstraction layer. All callers updated. Zero regressions.

---

## Phase 3: User Story 1 - Storage Interface Validation (Priority: P1)

**Goal**: Verify the interface is complete and well-documented. Implement a minimal mock backend to prove the interface works independently.

**Independent Test**: Create a mock backend implementing StorageBackend, instantiate it via factory, call all methods — no DuckDB dependency needed.

### Implementation for User Story 1

- [X] T009 [US1] Review and finalize `src/otel_agent/storage/base.py` — ensure all abstract methods have complete docstrings with parameter types, return types, and behavior descriptions. Add `RequestRecord` TypedDict for the standard record shape.

- [X] T010 [US1] Verify interface completeness — confirm `DuckDBStorage` implements all abstract methods. Run `python -c "from otel_agent.storage.duckdb import DuckDBStorage; print('OK')"` to verify import.

**Checkpoint**: Interface is documented and proven to work with DuckDB backend.

---

## Phase 4: User Story 3 - SQLite Backend + Config Switching (Priority: P3)

**Goal**: Implement SQLite backend and enable backend selection via config.yaml.

**Independent Test**: Set `storage: sqlite` in config, verify SQLite is used. Set `storage: duckdb`, verify DuckDB is used.

### Implementation for User Story 3

- [X] T011 [US3] Create `src/otel_agent/storage/sqlite.py` — implement `SQLiteStorage(StorageBackend)` using stdlib `sqlite3`. Use `INTEGER PRIMARY KEY AUTOINCREMENT` instead of sequences. Set `PRAGMA journal_mode=WAL`. Implement all 8 interface methods with SQLite-compatible SQL.

- [X] T012 [US3] Modify `src/otel_agent/config.py` — add optional `storage` field to the config dataclass (default: `"duckdb"`). Parse from `config.yaml`.

- [X] T013 [US3] Update `src/otel_agent/storage/__init__.py` — read storage backend name from config. Update `create_storage()` default parameter to use config value.

- [X] T014 [US3] Update `src/otel_agent/logger.py` — read storage backend from config instead of hardcoding `"duckdb"`.

- [X] T015 [US3] Run full test suite to verify SQLite backend works and config switching doesn't break DuckDB default.

- [X] T016 [US3] Manual verification: start proxy with `storage: sqlite` config, send requests, verify data stored in SQLite.

**Checkpoint**: Both backends work. Config switching functional.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup, documentation, edge cases

- [X] T017 Verify `db_compat.py` is still needed (used by `migration.py`) — do NOT remove it. Add comment explaining its role alongside the storage abstraction.

- [X] T018 Run `PYTHONPATH="$(pwd):$(pwd)/src" uv run ruff check src/otel_agent/storage/` — verify no lint errors in new code.

- [X] T019 Run quickstart.md scenarios 1-7 — confirm all pass.

- [X] T020 Run `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/ -v -m "not integration"` — final verification, all 127 tests must pass.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (US2 - DuckDB refactor)**: Depends on Phase 1 (interface must exist)
- **Phase 3 (US1 - Interface validation)**: Depends on Phase 2 (needs working backend to validate)
- **Phase 4 (US3 - SQLite + config)**: Depends on Phase 2 (DuckDB refactor must be stable)
- **Phase 5 (Polish)**: Depends on all above

### Parallel Opportunities

- T001 and T002 can run in parallel (different files in same package)
- T003 depends on T002 (needs base.py to import StorageBackend)
- T009 and T010 are review tasks, can run after Phase 2
- T011 (SQLite) and T012-T014 (config) can partially overlap

### Within Each Phase

Phase 2 tasks MUST run sequentially (each modifies files that depend on the previous).

---

## Implementation Strategy

### MVP First (User Story 2 — DuckDB Refactor)

1. Complete Phase 1: Storage package + interface
2. Complete Phase 2: DuckDB backend + caller refactoring
3. **STOP and VALIDATE**: All 127 tests pass, DuckDB works through interface
4. This is the critical milestone — if this fails, the abstraction design needs revision

### Incremental Delivery

1. Phase 1 → Interface defined
2. Phase 2 → MVP! DuckDB works through abstraction (zero regressions)
3. Phase 3 → Interface validated with documentation
4. Phase 4 → SQLite backend + config switching
5. Phase 5 → Polish + verification

### Commit Strategy

- Commit after Phase 2 (biggest change, critical milestone)
- Commit after Phase 4 (new functionality)
- Final commit after Phase 5 (polish)

```
Commit 1: refactor: extract storage abstraction layer with DuckDB backend
- Add StorageBackend ABC with 8 abstract methods
- Implement DuckDBStorage backend (refactored from logger/viewer/api)
- Refactor TelemetryLogger, viewer.query_requests, DashboardAPI to use StorageBackend
- All 127 existing tests pass unchanged

Commit 2: feat: add SQLite backend and config-based storage switching
- Implement SQLiteStorage backend
- Add storage field to config.yaml
- Backend selection via create_storage() factory
```
