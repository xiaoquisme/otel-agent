# Feature Specification: Dashboard Proxy Routing

**Feature Branch**: `014-dashboard-proxy-routing`

**Created**: 2026-07-09

**Status**: Draft

**Input**: User description: "DuckDB lock conflict when running otel-agent dashboard — dashboard process cannot open DuckDB file because proxy process holds exclusive lock"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dashboard Reads Through Proxy (Priority: P1)

As a developer using otel-agent, I want the dashboard to display my telemetry data without crashing, even while the proxy is running and logging requests.

**Why this priority**: The dashboard is completely unusable without this fix — it crashes on every data request due to DuckDB's exclusive file lock. This blocks all dashboard functionality.

**Independent Test**: Start the proxy, start the dashboard, verify the dashboard loads and displays request data without errors.

**Acceptance Scenarios**:

1. **Given** the proxy is running and logging requests, **When** I open the dashboard, **Then** the dashboard displays the request list without any lock errors.
2. **Given** the proxy is busy handling upstream requests, **When** the dashboard queries for data, **Then** the dashboard receives the data through the proxy's internal API without opening a direct DuckDB connection.
3. **Given** the dashboard is displaying data, **When** new requests are logged by the proxy, **Then** the dashboard updates to show the new requests.

---

### User Story 2 - Dashboard Works Without Proxy (Priority: P2)

As a developer reviewing offline telemetry data, I want the dashboard to work even when the proxy is not running, so I can analyze past request logs.

**Why this priority**: Offline analysis is a secondary use case — the primary use case is live monitoring while the proxy runs. But developers should be able to review historical data without starting the proxy.

**Independent Test**: Stop the proxy, start the dashboard with an existing DuckDB file, verify the dashboard displays historical data.

**Acceptance Scenarios**:

1. **Given** the proxy is not running, **When** I start the dashboard with an existing DuckDB file, **Then** the dashboard displays historical request data.
2. **Given** the proxy is not running, **When** I use search/filter in the dashboard, **Then** the filters work correctly on the historical data.

---

### User Story 3 - Graceful Degradation Under Load (Priority: P3)

As a developer using otel-agent, I want the dashboard to remain responsive even when the proxy is under heavy load, so I can monitor system health during peak usage.

**Why this priority**: Under normal load the dashboard should work perfectly. Under extreme load, graceful degradation (cached responses) is better than crashing.

**Independent Test**: Send many concurrent requests through the proxy, verify the dashboard remains responsive and does not crash.

**Acceptance Scenarios**:

1. **Given** the proxy is under heavy load, **When** the dashboard queries for data, **Then** the dashboard uses cached proxy connection info instead of re-checking health on every query.
2. **Given** the proxy was reachable but becomes temporarily slow, **When** the dashboard queries for data, **Then** the dashboard continues using the cached proxy URL for at least 60 seconds before falling back to direct access.

---

### Edge Cases

- What happens if the proxy crashes while the dashboard is running? The dashboard should fall back to direct DuckDB access after the proxy has been unreachable for more than 60 seconds.
- What happens if both the proxy and dashboard start simultaneously? The dashboard should detect the proxy within a few seconds and route through it.
- What happens if the DuckDB file is corrupted? The system should report a clear error and not crash the proxy.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The dashboard MUST route all database queries through the proxy's internal HTTP API when the proxy is running, instead of opening a direct DuckDB connection.
- **FR-002**: The proxy MUST expose internal API endpoints that provide the same data the dashboard needs (request list, detail, max ID, requests since ID, filtered export).
- **FR-003**: The dashboard MUST detect the proxy's port automatically by reading the proxy's process status file.
- **FR-004**: The dashboard MUST fall back to direct DuckDB connection only when the proxy is not running or has been unreachable for more than 60 seconds.
- **FR-005**: The proxy connection check MUST be cached with a TTL of at least 30 seconds to avoid health-check race conditions under load.
- **FR-006**: All existing dashboard features (request list, detail view, search, filter, export, SSE) MUST work identically whether queries route through the proxy or directly to DuckDB.

### Key Entities

- **Proxy Internal API**: HTTP endpoints exposed by the proxy process that provide dashboard data from the DuckDB connection it already holds.
- **Dashboard API Client**: The dashboard's data access layer that decides whether to route through the proxy or use direct DuckDB access.
- **Proxy Connection Cache**: A TTL-based cache that stores the proxy URL and prevents re-checking health on every query.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Dashboard loads and displays request data without errors in 100% of cases when the proxy is running.
- **SC-002**: Dashboard remains responsive (queries complete in under 2 seconds) even when the proxy is handling concurrent requests.
- **SC-003**: Dashboard falls back to direct DuckDB access within 60 seconds of the proxy becoming unreachable.
- **SC-004**: Dashboard works offline (without proxy) for historical data analysis.
- **SC-005**: No DuckDB lock conflicts occur in any scenario (proxy running, proxy busy, proxy crashed, proxy restarted).

## Assumptions

- DuckDB does not support multi-process concurrent access to a single database file (exclusive file lock).
- The proxy process is the primary owner of the DuckDB file — it holds the lock for the lifetime of the process.
- The proxy and dashboard typically run as separate OS processes on the same machine.
- The dashboard's internal API calls add negligible latency compared to direct DuckDB queries.
- The proxy's process status file (PID file, port file) is reliable for detecting whether the proxy is running.
