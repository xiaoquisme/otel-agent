---
title: "feat: Switch default storage from DuckDB to SQLite"
date: "2026-08-02"
type: "feat"
depth: "lightweight"
product_contract_source: "ce-plan-bootstrap"
artifact_contract: "ce-unified-plan/v1"
artifact_readiness: "implementation-ready"
execution: "code"
---

## Goal Capsule

- **Objective:** Make SQLite the default storage backend instead of DuckDB, enabling true multi-process concurrent read/write without the proxy HTTP API workaround.
- **Stop condition:** Default storage is SQLite; proxy and dashboard can read/write concurrently; all tests pass; DuckDB remains available as an opt-in backend.

---

## Problem Frame

DuckDB uses OS-level file locking that prevents multi-process concurrent access. The current workaround routes dashboard queries through the proxy's HTTP API. SQLite with WAL mode supports multi-process concurrent read + single writer, which matches the project's architecture (proxy writes, dashboard reads). The `SQLiteStorage` backend already exists but is not the default.

---

## Requirements

- R1. Change the default storage backend from `"duckdb"` to `"sqlite"` in config and code.
- R2. Optimize SQLite WAL PRAGMAs for concurrent read/write performance.
- R3. Dashboard API opens SQLite read connections directly (no proxy HTTP workaround needed when proxy is running).
- R4. DuckDB remains available as an opt-in backend via config.
- R5. All existing tests pass with SQLite as default.

---

## Implementation Units

### U1: Change default storage to SQLite

**Goal:** Make SQLite the default backend across all entry points.

**Files:**
- `src/otel_agent/config.py` — Default config YAML: change `storage: duckdb` to `storage: sqlite`
- `src/otel_agent/logger.py` — TelemetryLogger default backend parameter: `"duckdb"` → `"sqlite"`
- `src/otel_agent/cli.py` — CLI default backend if hardcoded

**Approach:**
1. Update `DEFAULT_CONFIG` in `config.py` to set `storage: sqlite`
2. Update `TelemetryLogger.__init__` default `backend` parameter from `"duckdb"` to `"sqlite"`
3. Check CLI for any hardcoded backend defaults
4. The `create_storage()` factory already handles both backends — no factory changes needed

**Test scenarios:**
- Verify default config produces SQLite storage
- Verify DuckDB can still be selected via config
- All existing unit tests pass

---

### U2: Optimize SQLite WAL PRAGMAs

**Goal:** Tune SQLite for concurrent read/write performance.

**Files:**
- `src/otel_agent/storage/sqlite.py` — `_get_conn()` method

**Approach:**
Add performance PRAGMAs after WAL enablement:
```python
self._conn.execute("PRAGMA journal_mode=WAL")
self._conn.execute("PRAGMA busy_timeout=5000")
self._conn.execute("PRAGMA synchronous=NORMAL")
self._conn.execute("PRAGMA wal_autocheckpoint=1000")
self._conn.execute("PRAGMA cache_size=-64000")
```

**Test scenarios:**
- Existing SQLite tests pass with new PRAGMAs
- Concurrent read/write test (if not already covered)

---

### U3: Dashboard direct SQLite access

**Goal:** Allow dashboard to read SQLite directly without proxy HTTP workaround.

**Files:**
- `src/otel_agent/dashboard/api.py` — `_get_storage()` method

**Approach:**
The `DashboardAPI._get_storage()` currently creates DuckDB read-only connections. When storage is SQLite, it can safely open a separate read connection (WAL mode allows concurrent reads). The proxy HTTP routing is still available as a fallback but no longer required for SQLite.

No code change needed here — the existing `create_storage("sqlite", ..., read_only=True)` already works correctly with WAL mode. The change is that SQLite is now the default, so this path is exercised by default.

**Test scenarios:**
- Dashboard can query while proxy is writing
- Standalone dashboard works with SQLite data

---

## Verification Contract

- `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest -m 'not integration'` — all pass
- Manual: start proxy, open dashboard, verify requests appear
- Manual: start standalone dashboard with existing SQLite DB, verify data loads

---

## Definition of Done

- [x] Default storage is SQLite in config and code
- [x] SQLite WAL PRAGMAs optimized
- [x] Dashboard reads SQLite directly
- [x] DuckDB still available via config
- [x] All tests pass
- [x] No regressions in existing functionality
