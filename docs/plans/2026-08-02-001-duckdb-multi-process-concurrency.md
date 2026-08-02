---
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
date: "2026-08-02"
---

# DuckDB Multi-Process Concurrency Support

## Problem Statement

The otel-agent proxy and dashboard are separate processes that both access the same DuckDB database file. DuckDB uses file-level locking that prevents concurrent access from multiple processes:

- **Proxy process**: Opens a write connection to log requests
- **Dashboard process**: Tries to open a read-only connection to query data

When both are running simultaneously, the dashboard's direct DuckDB access fails with:
```
IO Error: Could not set lock on file: Conflicting lock is held in python3.13
```

The current `DashboardAPI` has a workaround: route queries through the proxy's HTTP API when possible, falling back to direct DuckDB access. This fallback causes the lock conflict.

## Root Cause Analysis

DuckDB's concurrency model (per https://duckdb.org/docs/current/connect/concurrency):

1. **File-level locking**: DuckDB uses OS-level file locks to prevent concurrent access
2. **Single process access**: Only ONE process can have an open connection at a time
3. **No multi-process read support**: Unlike PostgreSQL, DuckDB does not support multiple processes reading simultaneously

This is a fundamental limitation of DuckDB's architecture. The `read_only=True` parameter only prevents writes within the same process; it does not bypass file-level locking.

## Solution

Since DuckDB cannot support true multi-process concurrent access, the solution is to:

1. **Make the proxy HTTP API the primary data access path**
2. **Remove the direct DuckDB access fallback from DashboardAPI**
3. **Ensure the proxy HTTP API handles all query types**
4. **Make `--proxy` option required for dashboard command**

This eliminates the lock conflict by ensuring only ONE process (the proxy) ever opens the DuckDB file.

## Implementation Plan

### Task 1: Simplify DashboardAPI
**File**: `src/otel_agent/dashboard/api.py`

- Remove `_proxy_url()` and `_http_get()` methods (no longer needed for fallback)
- Remove `proxy_port` parameter from `__init__`
- Add `proxy_url` parameter (required) that points to the proxy's HTTP API
- Update all query methods to ONLY use HTTP API calls
- Raise error if proxy is unreachable (no fallback)

### Task 2: Update Dashboard Command
**File**: `src/otel_agent/commands/dashboard.py`

- Make `--proxy` option required
- Update help text to explain that proxy must be running
- Remove fallback logic

### Task 3: Update CLI Arguments
**File**: `src/otel_agent/cli.py`

- Make `--proxy` a required argument for dashboard command
- Update help text

### Task 4: Add Error Handling
**File**: `src/otel_agent/dashboard/api.py`

- Add proper error handling for proxy unavailability
- Add retry logic with exponential backoff
- Add clear error messages when proxy is down

### Task 5: Add Tests
**File**: `tests/test_duckdb_concurrency.py`

- Add tests for dashboard requiring proxy
- Add tests for proxy HTTP API routing
- Add tests for error handling when proxy is down

### Task 6: Update Documentation
**File**: `docs/solutions/`

- Document the DuckDB concurrency limitation
- Document the proxy HTTP API architecture
- Update existing solution docs if needed

## Verification

1. Run existing tests: `pytest tests/`
2. Start proxy: `otel-agent proxy`
3. Start dashboard without proxy: `otel-agent dashboard` → should fail with clear error
4. Start dashboard with proxy: `otel-agent dashboard --proxy 45638` → should work
5. Verify dashboard can query data while proxy is writing
6. Check no lock conflict errors in logs

## Success Criteria

- Dashboard requires `--proxy` option to start
- Dashboard fails with clear error when proxy is not running
- Dashboard works correctly when proxy is running
- No "database is locked" or "lock conflict" errors
- All existing tests pass
- Documentation updated to explain the architecture
