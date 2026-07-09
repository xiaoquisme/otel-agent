# Feature Specification: SQLite to DuckDB Migration

**Feature Branch**: `013-sqlite-to-duckdb-migration`

**Created**: 2026-07-09

**Status**: Draft

**Input**: User description: "change sqlite to duckdb" — Migrate the telemetry storage backend from SQLite to DuckDB for better analytical query performance and columnar storage.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Transparent Storage Migration (Priority: P1)

As a developer using otel-agent, I want the proxy to store telemetry data in DuckDB instead of SQLite, so I benefit from faster analytical queries on my request logs without changing how I use the tool.

**Why this priority**: This is the core migration — without it, no other story delivers value. The storage engine is foundational to all telemetry operations (logging, querying, exporting).

**Independent Test**: Start the proxy, send requests through it, verify they are stored in a DuckDB file. Open the dashboard and confirm requests appear correctly. Run the CLI viewer and confirm output matches previous behavior.

**Acceptance Scenarios**:

1. **Given** a fresh otel-agent installation, **When** I start the proxy and send requests, **Then** a `.duckdb` file is created (not `.db`) and contains all logged requests with the same schema.
2. **Given** an existing SQLite database from a previous installation, **When** I start the proxy with the new version, **Then** the data is automatically migrated to DuckDB and the old SQLite file is preserved as a backup.
3. **Given** the proxy is running with DuckDB storage, **When** I send requests through the proxy, **Then** the logging latency overhead does not increase by more than 2ms compared to SQLite.

---

### User Story 2 - Dashboard Query Compatibility (Priority: P2)

As a developer using the otel-agent dashboard, I want all dashboard features (request list, detail view, search, filtering, export) to work identically with DuckDB as they did with SQLite.

**Why this priority**: The dashboard is the primary interface for inspecting telemetry. If queries break, the feature is unusable regardless of storage performance gains.

**Independent Test**: Open the dashboard, verify request list loads, click a request to view details, use search/filter, export CSV/JSON, and confirm real-time SSE updates work.

**Acceptance Scenarios**:

1. **Given** the dashboard is open with DuckDB storage, **When** I view the request list, **Then** all columns (ID, Timestamp, Method, URL, Status, Latency) display correctly with proper formatting.
2. **Given** the dashboard is open, **When** I use the search box or method/status filters, **Then** results are filtered correctly and pagination works.
3. **Given** the dashboard is open, **When** I click Export CSV or Export JSON, **Then** the exported data matches the filtered view.

---

### User Story 3 - CLI Viewer Compatibility (Priority: P3)

As a developer using the `otel-agent view` command, I want the CLI viewer to read from DuckDB and display request logs in the same format as before.

**Why this priority**: The CLI viewer is a secondary interface; the dashboard is primary. CLI compatibility is important but less critical.

**Independent Test**: Run `otel-agent view --db ./data/requests.duckdb` and confirm output format matches the previous SQLite-based output.

**Acceptance Scenarios**:

1. **Given** a DuckDB database with logged requests, **When** I run `otel-agent view`, **Then** the output shows request entries in the same tabular format.
2. **Given** a DuckDB database, **When** I run `otel-agent view --upstream <filter>`, **Then** results are filtered by upstream correctly.

---

### Edge Cases
- **Concurrent process access**: DuckDB uses exclusive file locks — the proxy and dashboard cannot both open the same `.duckdb` file simultaneously. Architectural solution required (see FR-010 note).

- What happens if both a `.db` (SQLite) and `.duckdb` file exist in the same directory? The system should use DuckDB and not attempt re-migration.
- What happens if the DuckDB file is corrupted? The system should report a clear error and not crash the proxy.
- What happens if the old SQLite file is very large (100MB+)? Migration should complete within 30 seconds without blocking the proxy startup.
- What happens if DuckDB is not installed (missing native library)? The system should fall back to SQLite with a deprecation warning.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST use DuckDB as the default storage engine for new installations.
- **FR-002**: System MUST automatically migrate existing SQLite databases to DuckDB on first run, preserving the original `.db` file as `.db.bak`.
- **FR-003**: System MUST NOT lose any data during migration — all rows from the `requests` table must be transferred.
- **FR-004**: System MUST maintain the same `requests` table schema in DuckDB (id, timestamp, method, url, upstream, request_headers, request_body, response_status, response_headers, response_body, latency_ms).
- **FR-005**: System MUST support the same query patterns used by the dashboard API (cursor-based pagination, filtering by method/status/search, COUNT queries).
- **FR-006**: System MUST support the same query patterns used by the CLI viewer (ORDER BY id DESC, LIMIT, WHERE upstream LIKE).
- **FR-007**: System MUST preserve the `--db` CLI flag behavior, accepting both `.db` and `.duckdb` file paths.
- **FR-008**: System MUST fall back to SQLite if DuckDB is unavailable, with a visible deprecation warning.
- **FR-009**: System MUST NOT increase proxy logging latency by more than 2ms per request compared to SQLite baseline.
- **FR-010**: System MUST handle concurrent reads (dashboard) and writes (proxy logging) without deadlocks or data corruption. ~~Note: DuckDB does not support multi-process concurrent access to a single file. This requirement must be solved architecturally (e.g., routing dashboard reads through the proxy process) rather than relying on the database engine's concurrency model.~~ (BUG-001)

### Key Entities

- **TelemetryLogger**: Writes request records to the database. Currently uses `sqlite3` module; will use `duckdb` module.
- **DashboardAPI**: Reads request records for the web dashboard. Currently uses `sqlite3` module; will use `duckdb` module.
- **CLI Viewer**: Reads request records for terminal display. Currently uses `sqlite3` module; will use `duckdb` module.
- **Migration Manager**: New component that detects existing SQLite databases and migrates data to DuckDB.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can start the proxy, send requests, and see them in the dashboard within 2 seconds of the request completing.
- **SC-002**: Migration of a 10,000-row SQLite database completes in under 10 seconds.
- **SC-003**: Dashboard search and filter operations return results in under 500ms for databases with up to 100,000 rows.
- **SC-004**: Zero data loss during migration — row count in DuckDB matches row count in original SQLite.
- **SC-005**: The `otel-agent view` command produces identical output format for DuckDB databases as it did for SQLite.

## Assumptions

**Bugfix**: 2026-07-09 — BUG-001 Updated FR-010, corrected concurrent access assumption, added edge case.

- DuckDB Python package (`duckdb`) is available via pip and installs native binaries for macOS/Linux/Windows.
- DuckDB supports the same SQL syntax used by the current queries (SELECT, INSERT, WHERE, LIKE, ORDER BY, LIMIT, COUNT, MAX).
- ~~DuckDB supports WAL-like concurrent read/write access for the proxy+dashboard use case.~~ **CORRECTED**: DuckDB does NOT support multi-process concurrent access. Only one process can hold a connection to a `.duckdb` file at a time (exclusive file lock). In-process (multi-threaded) MVCC works, but multi-process access requires architectural solutions. (BUG-001)
- The default file extension changes from `.db` to `.duckdb`, but the `--db` flag accepts either.
- Existing users with `.db` files will have them migrated automatically on first run.
- The `sqlite3` standard library module will be replaced by `duckdb` in all source files.
