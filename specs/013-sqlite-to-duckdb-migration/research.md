# Research: SQLite to DuckDB Migration

**Date**: 2026-07-09
**Feature**: 013-sqlite-to-duckdb-migration

## Design Decisions

### Decision 1: DuckDB Python API Usage

**Decision**: Use `duckdb.connect()` with file-based database, `conn.execute()` for queries, `conn.fetchall()`/`conn.fetchone()` for results.

**Rationale**: DuckDB's Python API is nearly identical to `sqlite3` in usage pattern. The main differences:
- No `row_factory = sqlite3.Row` — must manually create dicts from `cursor.description` + row tuples
- `conn.execute(sql, params)` accepts `?` placeholders (same as sqlite3)
- DuckDB has automatic MVCC — no need for `PRAGMA journal_mode=WAL`
- `duckdb` package installs native binaries — no system dependency

**Alternatives considered**:
- SQLAlchemy abstraction layer: Rejected — adds unnecessary complexity for 3 files with simple queries.
- pandas + DuckDB: Rejected — overkill for a telemetry logger; adds heavy dependency.

### Decision 2: Migration Strategy

**Decision**: Auto-detect existing `.db` files, read all rows via `sqlite3` (stdlib), insert into DuckDB, rename `.db` to `.db.bak`.

**Rationale**: DuckDB can read SQLite files directly via `duckdb.read_sqlite()`, but using stdlib `sqlite3` for reading is more portable and avoids circular dependency issues. The migration is a one-time operation per database file.

**Alternatives considered**:
- DuckDB's `ATTACH` SQLite: Viable but requires DuckDB to be installed first (circular for fallback case).
- Manual CSV export/import: Rejected — lossy for JSON fields, slower.

### Decision 3: Fallback to SQLite

**Decision**: Wrap `import duckdb` in try/except. If import fails, fall back to `sqlite3` with a `warnings.warn()` deprecation message.

**Rationale**: The `duckdb` package may fail to install on some platforms (missing native libs). Graceful degradation preserves backward compatibility while encouraging migration.

**Alternatives considered**:
- Hard dependency (require duckdb): Rejected — breaks installation on unsupported platforms.
- Optional dependency with extras (`pip install otel-agent[duckdb]`): Viable but adds packaging complexity.

### Decision 4: Default File Extension

**Decision**: Change default from `.db` to `.duckdb` in `config.py`. The `--db` flag accepts both extensions.

**Rationale**: Clear distinction between storage engines. Users can manually specify `.db` to force SQLite (for fallback or debugging).

### Decision 5: Row Factory Pattern

**Decision**: Create a helper function `rows_to_dicts(cursor)` that converts DuckDB result tuples to dictionaries using `cursor.description`.

**Rationale**: DuckDB doesn't have `sqlite3.Row`. The helper function provides the same dict-like access pattern used throughout the codebase (e.g., `dict(row)` in dashboard/api.py).

## DuckDB vs SQLite: Key API Differences

| Feature | sqlite3 | duckdb |
|---------|---------|--------|
| Import | `import sqlite3` | `import duckdb` |
| Connect | `sqlite3.connect(path)` | `duckdb.connect(path)` |
| Execute | `conn.execute(sql, params)` | `conn.execute(sql, params)` |
| Fetch all | `conn.fetchall()` | `conn.fetchall()` |
| Fetch one | `conn.fetchone()` | `conn.fetchone()` |
| Row as dict | `conn.row_factory = sqlite3.Row` | Manual: `dict(zip([d[0] for d in cursor.description], row))` |
| Parameter style | `?` | `?` (also supports `$1, :name`) |
| WAL mode | `PRAGMA journal_mode=WAL` | Automatic (MVCC) |
| Concurrent reads | WAL mode | In-process only (MVCC); multi-process NOT supported (exclusive file lock) (BUG-001) |
| Autoincrement | `INTEGER PRIMARY KEY AUTOINCREMENT` | `INTEGER PRIMARY KEY DEFAULT nextval('seq')` or `INTEGER` (DuckDB auto-increments INTEGER PK) |

## Summary

All NEEDS CLARIFICATION items resolved. The migration is straightforward due to DuckDB's sqlite-like API. The main implementation effort is in the row factory helper and migration module.

**Bugfix**: 2026-07-09 — BUG-001 Corrected "Concurrent reads: Automatic" to note multi-process is NOT supported.
