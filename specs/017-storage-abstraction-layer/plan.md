# Implementation Plan: Storage Abstraction Layer

**Branch**: `017-storage-abstraction-layer` | **Date**: 2026-07-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/017-storage-abstraction-layer/spec.md`

## Summary

Extract all database operations behind a storage interface (ABC), refactor the existing DuckDB code into a backend implementation, add a SQLite backend, and enable backend switching via configuration. The refactor is purely internal — all callers (logger, viewer, dashboard API, CLI) remain unchanged.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**:
- `duckdb` — current production storage (existing)
- `sqlite3` — stdlib fallback (existing)
- `abc` — Python stdlib for abstract base classes

**Storage**: This feature IS the storage abstraction — DuckDB (primary) + SQLite (fallback)

**Testing**: `pytest` — all 127 existing tests must pass without modification

**Target Platform**: Same as current — macOS/Linux CLI tool

**Project Type**: CLI tool with embedded web dashboard

**Performance Goals**: No regression — logging overhead stays under 5ms

**Constraints**: Zero test changes allowed. Callers must not know which backend is active.

**Scale/Scope**: ~400 lines added (interface + 2 backends + factory), ~200 lines moved (from logger/viewer/api into backends)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | ✅ PASS | Interface enforces single responsibility. Each backend is one module. |
| II. Testing Standards | ✅ PASS | 127 existing tests serve as regression suite. No new tests needed for refactor. |
| III. UX Consistency | ✅ PASS | No CLI behavior changes. Backend selection via config is transparent. |
| IV. Performance | ✅ PASS | Same DuckDB code path, just behind an interface. No added overhead. |

## Project Structure

### Documentation (this feature)

```text
specs/017-storage-abstraction-layer/
├── plan.md
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (new/modified files)

```text
src/otel_agent/
├── storage/
│   ├── __init__.py        # StorageFactory + import
│   ├── base.py            # StorageBackend ABC
│   ├── duckdb.py          # DuckDB backend
│   └── sqlite.py          # SQLite backend
├── logger.py              # MODIFY: use StorageFactory
├── viewer.py              # MODIFY: use StorageFactory
├── dashboard/
│   └── api.py             # MODIFY: use StorageFactory
├── db_compat.py           # KEEP (used by migration.py)
└── config.py              # MODIFY: add storage field
```
