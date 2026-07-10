# Quickstart: Dashboard Proxy Routing

**Date**: 2026-07-09
**Feature**: 014-dashboard-proxy-routing

## Prerequisites

- Python 3.10+
- `uv` package manager
- `duckdb` Python package (installed via `uv sync`)

## Validation Scenarios

### Scenario 1: Dashboard Reads Through Proxy (P1)

**Setup**: Proxy running with telemetry data.

```bash
# Start proxy
uv run otel-agent proxy --port 8080

# Send some requests through the proxy
curl http://localhost:8080/v1/models

# Start dashboard
uv run otel-agent dashboard --port 9090
```

**Steps**:
1. Open `http://localhost:9090` in browser
2. Verify request list loads without errors
3. Click a request row to view details

**Expected outcome**:
- Dashboard displays request data
- No DuckDB lock errors in proxy logs
- Dashboard output shows "Proxy detected on :8080 — routing queries through proxy"

### Scenario 2: Dashboard Works Without Proxy (P2)

**Setup**: Existing DuckDB file, no proxy running.

```bash
# Stop proxy if running
uv run otel-agent proxy stop

# Start dashboard with existing data
uv run otel-agent dashboard --port 9090 --db ~/.otel-agent/telemetry.duckdb
```

**Steps**:
1. Open `http://localhost:9090`
2. Verify historical data loads

**Expected outcome**:
- Dashboard displays historical request data
- No proxy detection message (direct DuckDB access)

### Scenario 3: Graceful Degradation Under Load (P3)

**Setup**: Proxy running, dashboard running.

```bash
# Start proxy and dashboard
uv run otel-agent proxy --port 8080 &
uv run otel-agent dashboard --port 9090 &

# Send many requests concurrently
for i in $(seq 1 20); do
  curl -s http://localhost:8080/v1/models > /dev/null &
done
wait
```

**Steps**:
1. Open dashboard during load
2. Verify dashboard remains responsive

**Expected outcome**:
- Dashboard loads data without errors
- No lock conflicts in proxy logs
- Dashboard uses cached proxy URL (no repeated health checks)

### Scenario 4: Proxy Crash Recovery (P1)

**Setup**: Proxy running, dashboard running.

```bash
# Start proxy and dashboard
uv run otel-agent proxy --port 8080 &
uv run otel-agent dashboard --port 9090 &

# Kill proxy
kill $(cat ~/.otel-agent/proxy.pid)

# Wait 60+ seconds, then check dashboard
sleep 65
curl http://localhost:9090/api/requests?limit=1
```

**Expected outcome**:
- Dashboard continues working (falls back to direct DuckDB after 60s)
- No crash or hang

## References

- [Internal API Contract](./contracts/internal-api.md) — endpoint specifications
- [Data Model](./data-model.md) — entity relationships
