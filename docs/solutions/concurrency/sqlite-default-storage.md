---
title: "SQLite as Default Storage for Multi-Process Concurrency"
date: "2026-08-02"
category: "concurrency"
module: "storage"
problem_type: "architecture_pattern"
component: "database"
severity: "medium"
symptoms:
  - "DuckDB file locking prevents dashboard from reading while proxy writes"
  - "Dashboard requires proxy HTTP API workaround for database access"
root_cause: "duckdb_file_locking"
resolution_type: "backend_switch"
tags:
  - "sqlite"
  - "duckdb"
  - "concurrency"
  - "wal-mode"
  - "storage-backend"
---

# SQLite as Default Storage for Multi-Process Concurrency

## Problem

DuckDB uses OS-level file locking that prevents multi-process concurrent access. The proxy process writes telemetry data while the dashboard process needs to read it. With DuckDB, this requires a workaround where the dashboard routes queries through the proxy's HTTP API.

## Solution

Switch the default storage backend from DuckDB to SQLite with WAL (Write-Ahead Logging) mode. SQLite WAL supports multi-process concurrent reads with a single writer — exactly matching the project's architecture (proxy writes, dashboard reads).

### Key Changes

1. **Default backend**: Changed from `"duckdb"` to `"sqlite"` in `config.py` and CLI defaults
2. **WAL PRAGMAs optimized**:
   - `busy_timeout=5000` — wait 5 seconds on write conflicts before erroring
   - `synchronous=NORMAL` — faster writes in WAL mode (safe because WAL provides crash recovery)
   - `wal_autocheckpoint=1000` — automatic WAL checkpoint every 1000 pages
   - `cache_size=-64000` — 64MB page cache for better read performance
3. **CLI default DB path**: Changed from `telemetry.duckdb` to `telemetry.sqlite`

### Why SQLite WAL Works Here

- **Concurrent reads**: Multiple processes can read simultaneously without blocking
- **Single writer**: Only the proxy writes telemetry — matches SQLite's model
- **No lock conflicts**: Dashboard can open its own read connection directly
- **No proxy HTTP workaround needed**: Dashboard reads SQLite directly

### Migration Path

DuckDB remains available as an opt-in backend via `storage: duckdb` in config.yaml. The existing `migrate_sqlite_to_duckdb()` function in `migration.py` can be reversed to migrate data from DuckDB to SQLite if needed.

## Trade-offs

| Aspect | DuckDB | SQLite WAL |
|--------|--------|------------|
| Multi-process read | ❌ File lock | ✅ Concurrent reads |
| Write blocks readers | ❌ Yes | ✅ No |
| Analytical query speed | ⚡ Columnar, vectorized | 🟡 Row-based, standard SQL |
| Data volume sweet spot | 1M+ rows | <1M rows |
| Deployment | Zero-config (embedded) | Zero-config (stdlib) |
| Extra dependency | `duckdb` package | None (Python built-in) |

For typical LLM telemetry volumes (thousands to tens of thousands of requests per day), SQLite performance is more than adequate.

## Related

- `docs/solutions/concurrency/duckdb-multi-process-concurrency.md` — original DuckDB concurrency problem and single-writer workaround
- `docs/ideation/2026-08-02-lightweight-db-concurrent-rw-ideation.html` — full ideation analysis of database options
