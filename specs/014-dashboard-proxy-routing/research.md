# Research: Dashboard Proxy Routing

**Date**: 2026-07-09
**Feature**: 014-dashboard-proxy-routing

## Design Decisions

### Decision 1: Internal API Endpoints

**Decision**: Add internal HTTP endpoints to the proxy's FastAPI app that expose dashboard data.

**Rationale**: The proxy already holds the DuckDB connection via TelemetryLogger. Adding internal endpoints (mirror of DashboardAPI methods) lets the dashboard query data through the proxy without opening its own DuckDB connection. This is the simplest architectural solution to DuckDB's exclusive file lock.

**Alternatives considered**:
- Shared in-memory cache (Redis/Memcached): Rejected — adds external dependency for a single-user tool.
- DuckDB HTTP server mode: Not available in the Python package.
- Separate process with IPC: Overkill for a CLI tool.

### Decision 2: Proxy Detection via PID File

**Decision**: Dashboard detects proxy by reading `~/.otel-agent/proxy.pid` and `~/.otel-agent/proxy.port`.

**Rationale**: The proxy already writes PID and port files when running in background mode. Reusing this existing mechanism avoids new coordination files. The dashboard checks if the PID is alive via `os.kill(pid, 0)`.

**Alternatives considered**:
- Port scanning: Fragile and slow.
- Unix socket: Requires socket path coordination.
- Environment variable: Doesn't work across processes.

### Decision 3: TTL-Based URL Caching

**Decision**: Cache the proxy URL with 30s TTL. If health check fails but proxy was previously reachable, keep using cached URL for up to 60s.

**Rationale**: The health check runs on EVERY dashboard query. Under load, the proxy may be slow to respond to health checks. A 2-second timeout on every query adds latency and can cause intermittent lock conflicts if the check fails. Caching avoids this race condition (BUG-002).

**Alternatives considered**:
- No caching (original BUG-001 implementation): Failed under load — health check timeout caused fallback to direct DuckDB.
- Connection pooling: Unnecessary — the proxy is a single process.
- WebSocket for real-time updates: Overkill for this use case.

### Decision 4: Fallback Strategy

**Decision**: Fall back to direct DuckDB connection only if proxy has been unreachable for > 60 seconds.

**Rationale**: Brief proxy unavailability (restart, slow response) should not cause the dashboard to open a conflicting DuckDB connection. The 60s grace period handles transient issues while still allowing offline use when the proxy is truly down.

**Alternatives considered**:
- Never fall back: Breaks offline/CLI use case.
- Immediate fallback: Causes lock conflicts under load.
- Exponential backoff: Unnecessary complexity for a single-user tool.

## DuckDB Concurrency Model

| Aspect | SQLite WAL | DuckDB |
|--------|-----------|--------|
| Multi-process reads | ✅ Yes (WAL mode) | ❌ No (exclusive lock) |
| Multi-process write+read | ✅ Yes (WAL mode) | ❌ No |
| In-process concurrency | ✅ Yes (threads) | ✅ Yes (MVCC) |
| Lock type | Shared WAL lock | Exclusive file lock |
| Fallback strategy | N/A | Route through single owner process |

## Summary

All design decisions resolved. The architecture is: proxy owns DuckDB connection, dashboard routes queries through proxy's internal HTTP API, with TTL-based caching to avoid health-check race conditions.
