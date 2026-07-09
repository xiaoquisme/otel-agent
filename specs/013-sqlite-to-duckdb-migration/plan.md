# Implementation Plan: SQLite to DuckDB Migration

**Branch**: `013-sqlite-to-duckdb-migration` | **Date**: 2026-07-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-sqlite-to-duckdb-migration/spec.md`

## Summary

Migrate telemetry storage from SQLite to DuckDB across 3 source files (logger.py, dashboard/api.py, viewer.py). Add automatic migration of existing `.db` files, DuckDB fallback to SQLite, and maintain identical query behavior. The `duckdb` Python package replaces the `sqlite3` standard library module.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: `duckdb` (new — replaces `sqlite3` stdlib), `fastapi`, `uvicorn`, `httpx`, `pyyaml` (existing)

**Storage**: DuckDB file (`.duckdb`) replacing SQLite file (`.db`)

**Testing**: pytest (existing test suite), manual dashboard/CLI verification

**Target Platform**: macOS/Linux/Windows (DuckDB provides native binaries for all)

**Project Type**: CLI tool + web dashboard (Python package)

**Performance Goals**: Logging latency ≤ 2ms overhead vs SQLite; dashboard queries < 500ms for 100K rows; migration < 10s for 10K rows

**Constraints**: Must not break existing CLI/dashboard behavior; must auto-migrate existing `.db` files; must fall back to SQLite if DuckDB unavailable

**Scale/Scope**: 3 source files modified, 1 new module (migration), ~200 lines changed

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | ✅ PASS | DuckDB API is clean and Pythonic; migration module has single responsibility; all public functions will have docstrings |
| II. Testing Standards | ✅ PASS | Existing pytest suite covers logger/dashboard/viewer; new migration tests will be added; no network dependency |
| III. User Experience Consistency | ✅ PASS | CLI flags unchanged; dashboard behavior identical; migration is transparent to users |
| IV. Performance Requirements | ✅ PASS | DuckDB is faster than SQLite for analytical queries; WAL-mode equivalent via DuckDB's MVCC; no unbounded buffers |

**Gate Result**: PASS — no violations. Proceeding to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/013-sqlite-to-duckdb-migration/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── storage-api.md
└── tasks.md             # Phase 2 output (NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/otel_agent/
├── logger.py            # MODIFY: TelemetryLogger — sqlite3 → duckdb
├── migration.py         # NEW: SQLite → DuckDB migration manager
├── viewer.py            # MODIFY: CLI viewer — sqlite3 → duckdb
├── config.py            # MODIFY: Default db path extension .db → .duckdb
├── dashboard/
│   ├── api.py           # MODIFY: DashboardAPI — sqlite3 → duckdb
│   └── server.py        # No changes needed
└── commands/
    ├── proxy.py         # MODIFY: Import migration module, run on startup
    ├── dashboard.py     # No changes needed (passes db_path)
    └── view.py          # No changes needed (passes db_path)

tests/
├── test_logger.py       # MODIFY: Update for duckdb
├── test_migration.py    # NEW: Migration tests
├── test_dashboard_api.py # MODIFY: Update for duckdb
└── test_viewer.py       # MODIFY: Update for duckdb
```

**Structure Decision**: Single-project layout. New `migration.py` module handles SQLite→DuckDB conversion. Existing modules updated to use `duckdb` API.

## Complexity Tracking

> No Constitution Check violations — no complexity tracking needed.
