# Feature Specification: Storage Abstraction Layer

**Feature Branch**: `017-storage-abstraction-layer`

**Created**: 2026-07-09

**Status**: Draft

**Input**: User description: "将数据库的相关操作提升一个抽象层，然后可以随便替换"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Define a Storage Interface (Priority: P1)

As a developer maintaining otel-agent, I want a clearly defined storage interface (abstract base class) that all database operations go through, so that I can swap the underlying storage engine (DuckDB, SQLite, PostgreSQL, etc.) without changing any business logic code.

**Why this priority**: This is the foundational work — the interface must exist before any backend can implement it. Without this, every storage change requires modifying multiple files.

**Independent Test**: Implement a mock storage backend that satisfies the interface, verify it works with the existing logger, viewer, and dashboard API without any DuckDB dependency.

**Acceptance Scenarios**:

1. **Given** the storage interface is defined, **When** a developer creates a new backend class that implements the interface, **Then** the new backend works with `TelemetryLogger`, `viewer.query_requests()`, and `DashboardAPI` without code changes in those modules.
2. **Given** the storage interface is defined, **When** a developer reads the interface, **Then** all methods have clear docstrings describing parameters, return types, and expected behavior.
3. **Given** the storage interface is defined, **When** the existing DuckDB backend is refactored to implement it, **Then** all existing tests pass without modification.

---

### User Story 2 - Refactor Existing DuckDB Backend (Priority: P2)

As a developer, I want the current DuckDB-specific code to be moved into a backend class that implements the storage interface, so that the abstraction is proven to work with the real production code path.

**Why this priority**: The interface alone is theoretical — implementing it against the real DuckDB backend validates the design and ensures zero regressions.

**Independent Test**: Run the full test suite after refactoring — all tests must pass with no changes to test code.

**Acceptance Scenarios**:

1. **Given** the DuckDB backend implements the storage interface, **When** the proxy starts and logs requests, **Then** all requests are stored and retrievable exactly as before.
2. **Given** the DuckDB backend implements the storage interface, **When** the dashboard queries requests, **Then** all API responses are identical to before the refactor.
3. **Given** the DuckDB backend implements the storage interface, **When** the CLI `view` command runs, **Then** output is identical to before.

---

### User Story 3 - Enable Backend Switching via Configuration (Priority: P3)

As a user of otel-agent, I want to configure which storage backend to use (e.g., duckdb, sqlite, or a custom backend), so that I can choose the storage engine that fits my deployment environment.

**Why this priority**: Backend switching is the payoff of the abstraction — but it requires the interface and DuckDB backend to be solid first.

**Independent Test**: Set `storage: sqlite` in config, verify the system uses SQLite instead of DuckDB. Set `storage: duckdb`, verify DuckDB is used.

**Acceptance Scenarios**:

1. **Given** the config file has `storage: duckdb` (or no storage setting), **When** the system starts, **Then** DuckDB is used as the storage backend (default behavior preserved).
2. **Given** the config file has `storage: sqlite`, **When** the system starts, **Then** SQLite is used as the storage backend.
3. **Given** an invalid or unknown storage backend name, **When** the system starts, **Then** a clear error message is shown explaining the valid options.

---

### Edge Cases

- What happens when the storage backend is unavailable at startup (e.g., DuckDB not installed)? The system should fall back to the next available backend with a warning.
- What happens when switching backends with existing data? The system should NOT attempt automatic migration between arbitrary backends — that is a separate concern.
- What happens with concurrent access? The storage interface should document that concurrent write access depends on the backend implementation (DuckDB: single-writer, SQLite: WAL mode).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST define an abstract storage interface with methods for: `initialize()` (create tables/schema), `log_request()` (insert a request record), `get_requests()` (paginated query with filters), `get_request()` (single record by ID), `get_requests_since()` (new records since ID), `get_max_id()` (maximum record ID), `get_all_filtered()` (all matching records for export), `close()` (cleanup).
- **FR-002**: System MUST implement a DuckDB backend that satisfies the storage interface using the existing DuckDB code from `logger.py`, `viewer.py`, and `dashboard/api.py`.
- **FR-003**: System MUST implement a SQLite backend that satisfies the storage interface using the existing SQLite fallback code from `db_compat.py`.
- **FR-004**: System MUST select the storage backend based on configuration, defaulting to DuckDB when no storage setting is specified.
- **FR-005**: System MUST provide a factory function that instantiates the correct backend based on configuration.
- **FR-006**: System MUST preserve all existing behavior — the refactor must be invisible to callers (logger, viewer, dashboard API, CLI).
- **FR-007**: System MUST NOT require changes to any test files — the refactoring is purely internal.
- **FR-008**: System MUST handle the case where the preferred backend is unavailable (e.g., DuckDB not installed) by falling back to the next available backend with a deprecation warning.

### Key Entities

- **Storage Interface**: Abstract base class defining all database operations
- **DuckDB Backend**: Concrete implementation using DuckDB
- **SQLite Backend**: Concrete implementation using sqlite3
- **Storage Factory**: Function that creates the appropriate backend based on config
- **Request Record**: The data entity stored/retrieved (id, timestamp, method, url, upstream, headers, body, status, latency)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing tests (127/127) pass without modification after the refactor.
- **SC-002**: A new storage backend can be implemented by implementing only the storage interface — no changes to logger, viewer, or dashboard API code.
- **SC-003**: The storage interface has complete docstrings covering all methods, parameters, and return types.
- **SC-004**: Switching between DuckDB and SQLite backends via configuration works without code changes.
- **SC-005**: No performance regression — request logging latency remains under 5ms overhead.

## Assumptions

- The storage interface will be a Python abstract base class (`abc.ABC`) with `@abstractmethod` decorators.
- The existing `db_compat.py` module will be refactored or replaced by the storage interface + backends.
- The `migration.py` module (SQLite → DuckDB) is independent and remains unchanged.
- The proxy's internal API routing (BUG-001/BUG-002) is a separate concern and not affected by this refactor.
- Configuration for storage backend selection will use the existing `config.yaml` format, adding an optional `storage` field.
- Backends will be implemented as separate modules under a `storage/` package.
