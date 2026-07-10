# Data Model: Dashboard Proxy Routing

**Date**: 2026-07-09
**Feature**: 014-dashboard-proxy-routing

## Entities

### Proxy Process Status

Represents a running proxy instance.

| Field | Type | Description |
|-------|------|-------------|
| pid | int | Process ID of the proxy |
| port | int | HTTP port the proxy listens on |

**Source**: `~/.otel-agent/proxy.pid` and `~/.otel-agent/proxy.port` files.

**State transitions**:
- Created: Proxy starts in background mode
- Active: PID file exists, process is alive
- Stale: PID file exists, process is dead → cleaned up on next check

### DashboardAPI Proxy Cache

In-memory cache of proxy connection state.

| Field | Type | TTL | Description |
|-------|------|-----|-------------|
| _proxy_url_cache | str \| None | 30s | Cached proxy base URL |
| _proxy_url_cache_time | float | 30s | Timestamp of last successful health check |
| _proxy_last_fail_time | float | 60s | Timestamp of first consecutive health check failure |

**State transitions**:
- Uncached: No proxy detected → direct DuckDB access
- Cached (healthy): Health check succeeded → route through proxy
- Cached (unhealthy): Health check failed < 60s → keep using cached proxy URL
- Expired: Health check failed > 60s → fall back to direct DuckDB

### Internal API Request Record

Same schema as the `requests` table in DuckDB.

| Field | Type | Description |
|-------|------|-------------|
| id | int | Auto-incrementing primary key |
| timestamp | text | ISO 8601 timestamp |
| method | text | HTTP method (GET, POST, etc.) |
| url | text | Request URL |
| upstream | text | Upstream provider URL |
| request_headers | text | JSON-encoded request headers |
| request_body | text | Request body (truncated to 100KB) |
| response_status | int | HTTP response status code |
| response_headers | text | JSON-encoded response headers |
| response_body | text | Response body (truncated to 100KB) |
| latency_ms | double | Request latency in milliseconds |

## Relationships

```
Proxy Process (1) ──owns──> DuckDB File (1)
                                │
Dashboard Process (1) ──queries──> Proxy Internal API (N)
                                        │
                                        └──> DuckDB File (via proxy's connection)
```

The proxy process is the sole owner of the DuckDB file. The dashboard process queries data through the proxy's internal API, never touching DuckDB directly (unless proxy is unreachable for > 60s).
