# Feature Specification: Dashboard Shows Historical Requests

**Feature Branch**: `006-dashboard-history`

**Created**: 2026-06-27

**Status**: Draft

**Input**: When starting the dashboard with `otel-agent dashboard`, all historical requests already stored in the database should be visible immediately. The dashboard should not only show requests that arrive after the dashboard starts.

## User Scenarios & Testing

### User Story 1 - Historical Data on Load (Priority: P1)

A user starts the dashboard and immediately sees all requests that were logged before the dashboard was started.

**Why this priority**: This is the core expectation — the dashboard is a viewer for the database, not a live-only monitor.

**Independent Test**: Start proxy, send 10 requests, stop proxy, start dashboard, verify all 10 requests are visible.

**Acceptance Scenarios**:

1. **Given** the proxy has logged 100 requests, **When** the user starts the dashboard, **Then** the dashboard shows all 100 requests in the table.
2. **Given** the dashboard is showing historical requests, **When** a new request arrives through the proxy, **Then** the new request appears in the table without losing the historical view.
3. **Given** the database has requests from yesterday, **When** the user starts the dashboard today, **Then** yesterday's requests are visible.

---

### User Story 2 - Consistent Database Path (Priority: P1)

The dashboard reads from the same database file as the proxy, regardless of which directory the commands are run from.

**Why this priority**: If proxy and dashboard use different database files, historical data is invisible.

**Independent Test**: Start proxy from directory A, start dashboard from directory B, verify dashboard shows proxy's requests.

**Acceptance Scenarios**:

1. **Given** the proxy is running and logging to `~/.otel-agent/telemetry.db`, **When** the user runs `otel-agent dashboard` from any directory, **Then** the dashboard reads from `~/.otel-agent/telemetry.db`.
2. **Given** the user specifies a custom database path, **When** they start both proxy and dashboard with the same `-d` flag, **Then** both use the same database.

---

### Edge Cases

- What happens if the database is very large (50,000+ requests)? The dashboard MUST still load the first page quickly.
- What happens if the database doesn't exist yet? The dashboard MUST show "No requests logged yet" and not crash.
- What happens if the proxy and dashboard are started simultaneously? The dashboard MUST handle concurrent writes gracefully (WAL mode).

## Requirements

### Functional Requirements

- **FR-001**: The dashboard MUST display all requests stored in the database, not just requests that arrive after the dashboard starts.
- **FR-002**: The default database path MUST be `~/.otel-agent/telemetry.db` (absolute path), consistent across all commands.
- **FR-003**: The dashboard MUST work regardless of the current working directory.
- **FR-004**: New requests arriving while the dashboard is open MUST appear without losing historical data.
- **FR-005**: The dashboard MUST handle an empty database gracefully with a "No requests logged yet" message.

### Key Entities

- **Request Log**: The `requests` table in SQLite — the dashboard reads all rows, not just new ones.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Dashboard shows all historical requests within 2 seconds of opening, regardless of when the proxy was started.
- **SC-002**: Dashboard works identically when started from any directory on the system.
- **SC-003**: New requests appear in the dashboard within 5 seconds without losing historical data.

## Assumptions

- The proxy and dashboard use the same default database path (`~/.otel-agent/telemetry.db`).
- SQLite WAL mode allows concurrent reads while the proxy writes.
- The database file persists between proxy restarts.
