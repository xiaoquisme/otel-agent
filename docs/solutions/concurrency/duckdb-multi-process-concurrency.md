---
title: "DuckDB Multi-Process Concurrency"
date: "2026-08-02"
category: "concurrency"
module: "storage"
problem_type: "architecture_pattern"
component: "database"
severity: "high"
symptoms:
  - "DuckDB lock conflict when proxy and dashboard run simultaneously"
  - "Connection Error: Can't open a connection to same database file with a different configuration"
  - "IO Error: Could not set lock on file: Conflicting lock is held"
root_cause: "duckdb_limitation"
resolution_type: "architecture_pattern"
tags:
  - "duckdb"
  - "concurrency"
  - "multi-process"
  - "file-locking"
  - "dashboard"
  - "proxy"
---

# DuckDB Multi-Process Concurrency

## Problem

The otel-agent proxy and dashboard are separate processes that both need to access the same DuckDB database file. DuckDB uses OS-level file locking that prevents concurrent access from multiple processes:

```
_duckdb.IOException: IO Error: Could not set lock on file "test.duckdb":
Conflicting lock is held in python3.13 (PID 26669) by user xiaoqu.
```

Even opening a read-only connection fails when another process has an open write connection:

```
_duckdb.ConnectionException: Connection Error: Can't open a connection to
same database file with a different configuration than existing connections
```

## Root Cause

DuckDB's concurrency model (per https://duckdb.org/docs/current/connect/concurrency):

1. **File-level locking**: DuckDB uses OS-level file locks to prevent concurrent access
2. **Single process access**: Only ONE process can have an open connection at a time
3. **No multi-process read support**: Unlike PostgreSQL, DuckDB does not support multiple processes reading simultaneously
4. **Configuration mismatch**: Mixing `read_only=True` and `read_only=False` connections to the same file causes a configuration error

This is a fundamental limitation of DuckDB's architecture. The `read_only=True` parameter only prevents writes within the same process; it does not bypass file-level locking.

## Solution

Since DuckDB cannot support true multi-process concurrent access, the solution is a **single-writer architecture**:

1. **Proxy is the sole DuckDB owner**: Only the proxy process opens a write connection
2. **Dashboard queries through proxy HTTP API**: The dashboard routes all queries through the proxy's internal HTTP API
3. **No fallback to direct DuckDB**: When `proxy_port` is specified, the dashboard does NOT fall back to direct DuckDB access (which would cause lock conflicts)
4. **Shared storage in proxy**: The proxy's internal DashboardAPI shares the TelemetryLogger's storage connection (no second connection)

### Implementation

**DashboardAPI** (`src/otel_agent/dashboard/api.py`):
- When `proxy_port` is set: routes queries through proxy HTTP API
- When `proxy_port` is None: falls back to direct DuckDB access (single-process mode)
- When `storage` is provided: uses the shared storage directly (proxy internal use)
- Uses `trust_env=False` to bypass system proxy (Surge) on macOS

**Proxy Server** (`src/otel_agent/server.py`):
- Creates DashboardAPI with `storage=telemetry.storage` to share the connection
- Dashboard routes (`/api/*`) use the shared storage

**Dashboard Command** (`src/otel_agent/commands/dashboard.py`):
- `--proxy` option specifies the proxy port for HTTP API routing
- Without `--proxy`: uses direct DuckDB access (standalone mode, no proxy running)

## Why This Works

1. **No lock conflicts**: Only one process (proxy) accesses DuckDB directly
2. **No configuration mismatches**: No attempt to open read-only connections alongside write connections
3. **Clean separation**: Proxy owns the database; dashboard is a read-only consumer via HTTP
4. **Graceful degradation**: Standalone dashboard works when proxy is not running

## Prevention

- **Never open multiple DuckDB connections to the same file from different processes**
- **Use a single-writer architecture**: One process owns the database, others query via IPC (HTTP, Unix socket, etc.)
- **Document the limitation**: New developers should understand DuckDB's concurrency model
- **Test concurrency scenarios**: Integration tests should verify multi-process access works

## Related

- `docs/solutions/performance-issues/remove-sse-polling-db-pressure.md` — related performance issue with DuckDB
- `docs/solutions/architecture-patterns/dashboard-render-delegation-pattern.md` — dashboard architecture decision
