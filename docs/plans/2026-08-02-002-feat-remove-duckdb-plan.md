---
title: "feat: Remove DuckDB backend and all related code"
date: "2026-08-02"
type: "feat"
depth: "lightweight"
product_contract_source: "ce-plan-bootstrap"
artifact_contract: "ce-unified-plan/v1"
artifact_readiness: "implementation-ready"
execution: "code"
---

## Goal Capsule

- **Objective:** Remove the DuckDB storage backend, migration code, and all related dependencies/tests after switching to SQLite as default.
- **Stop condition:** No DuckDB imports or references remain in source code; `duckdb` removed from dependencies; all tests pass with SQLite only.

---

## Problem Frame

With SQLite as the default storage backend (previous commit), DuckDB code is now dead weight. Removing it eliminates a heavy dependency, simplifies the codebase, and prevents confusion about which backend to use.

---

## Requirements

- R1. Delete `src/otel_agent/storage/duckdb.py`
- R2. Remove `duckdb` from `pyproject.toml` dependencies
- R3. Remove DuckDB from `BACKENDS` dict in `storage/__init__.py`
- R4. Remove migration logic from `logger.py` and `migration.py`
- R5. Remove/update `db_compat.py` (DuckDB fallback logic)
- R6. Update all tests to use SQLite instead of DuckDB
- R7. Update `viewer.py` and `dashboard/api.py` to use SQLite

---

## Implementation Units

### U1: Remove DuckDB source files

**Files:**
- DELETE `src/otel_agent/storage/duckdb.py`
- DELETE `src/otel_agent/migration.py`
- MODIFY `src/otel_agent/db_compat.py` — remove DuckDB fallback
- MODIFY `src/otel_agent/storage/__init__.py` — remove "duckdb" from BACKENDS, change default to "sqlite"

### U2: Update dependent source files

**Files:**
- MODIFY `src/otel_agent/logger.py` — remove migration import/logic, change default backend to "sqlite"
- MODIFY `src/otel_agent/viewer.py` — change "duckdb" to "sqlite"
- MODIFY `src/otel_agent/dashboard/api.py` — change fallback from "duckdb" to "sqlite"
- MODIFY `pyproject.toml` — remove `duckdb>=1.5.4` dependency

### U3: Update tests

**Files:**
- MODIFY `tests/test_logger.py` — rewrite DuckDB-specific tests to use SQLite
- DELETE `tests/test_migration.py` — migration tests no longer needed
- MODIFY `tests/test_server.py` — change .duckdb to .sqlite, remove duckdb imports
- MODIFY `tests/test_integration.py` — change .duckdb to .sqlite, remove duckdb imports
- MODIFY `tests/test_usage_metrics.py` — change .duckdb to .sqlite
- MODIFY `tests/test_viewer.py` — change .duckdb to .sqlite
- MODIFY `tests/test_cli.py` — change .duckdb to .sqlite (if not already done)

---

## Verification Contract

- `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest -m 'not integration'` — all pass
- `grep -r "duckdb\|DuckDB" src/` — returns nothing
- `grep "duckdb" pyproject.toml` — returns nothing
