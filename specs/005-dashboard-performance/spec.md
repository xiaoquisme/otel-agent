# Feature Specification: Dashboard Performance Optimization

**Feature Branch**: `005-dashboard-performance`

**Created**: 2026-06-26

**Status**: Draft

**Input**: The dashboard requests are too slow to respond. API calls take several seconds even with moderate data. Need to optimize database queries and connection handling.

## User Scenarios & Testing

### User Story 1 - Fast Initial Load (Priority: P1)

A user opens the dashboard and sees the request table immediately, not after a long delay.

**Why this priority**: First impression. If the dashboard takes 5+ seconds to load, users won't use it.

**Independent Test**: Open dashboard with 1000 requests in database. Verify page loads in under 1 second.

**Acceptance Scenarios**:

1. **Given** the database has 1000 requests, **When** the user opens the dashboard, **Then** the table appears within 1 second.
2. **Given** the database has 5000 requests, **When** the user opens the dashboard, **Then** the table appears within 2 seconds.
3. **Given** the database is empty, **When** the user opens the dashboard, **Then** the page loads instantly.

---

### User Story 2 - Fast Search (Priority: P1)

A user types in the search box and results update quickly.

**Why this priority**: Search is the primary way to find specific requests. Slow search makes the dashboard unusable.

**Independent Test**: Type "openai" in search box. Verify results appear within 500ms.

**Acceptance Scenarios**:

1. **Given** the database has 1000 requests, **When** the user types "openai" in search, **Then** filtered results appear within 500ms.
2. **Given** search results are shown, **When** the user clears the search, **Then** all results appear within 500ms.

---

### User Story 3 - Real-Time Updates Without Lag (Priority: P2)

New requests appear in the dashboard without causing the entire page to slow down.

**Why this priority**: Auto-refresh should not degrade performance.

**Independent Test**: Send 10 requests rapidly. Verify dashboard updates without lag.

**Acceptance Scenarios**:

1. **Given** the dashboard is open, **When** 10 new requests arrive in quick succession, **Then** the dashboard updates smoothly without freezing.
2. **Given** the SSE connection is active, **When** the user is browsing the table, **Then** new requests don't interrupt the current view.

---

### Edge Cases

- What happens if the database has 50,000+ requests? The dashboard MUST still load the first page in under 3 seconds.
- What happens if the database is being written to heavily? The dashboard MUST not block on WAL locks.
- What happens if the user pagates to page 100? Pagination MUST not slow down with high page numbers (no OFFSET-based pagination).

## Requirements

### Functional Requirements

- **FR-001**: The `requests` table MUST have indexes on `id`, `timestamp`, `method`, and `response_status` columns.
- **FR-002**: The dashboard API MUST use a persistent connection pool instead of creating a new connection per request.
- **FR-003**: The `get_requests` endpoint MUST use cursor-based pagination instead of OFFSET for consistent performance.
- **FR-004**: The COUNT query MUST be optimized (cached or approximate) to avoid full table scans on every request.
- **FR-005**: The SSE endpoint MUST reuse a single connection instead of opening/closing per poll cycle.
- **FR-006**: Search queries MUST use indexes where possible (exact matches on method, status) before applying LIKE filters.
- **FR-007**: The dashboard MUST load the first page of results within 1 second for databases with up to 10,000 requests.

### Key Entities

- **Request Log**: The existing `requests` table — needs indexes added.
- **Connection Pool**: A shared SQLite connection for read queries.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Dashboard initial load (first page) completes in under 1 second with 1000 requests.
- **SC-002**: Dashboard initial load completes in under 2 seconds with 10,000 requests.
- **SC-003**: Search results appear within 500ms with 1000 requests.
- **SC-004**: Pagination to any page completes in under 500ms.
- **SC-005**: SSE updates don't cause visible UI lag.

## Assumptions

- The SQLite database is on a local SSD (not network storage).
- The proxy and dashboard run on the same machine.
- WAL mode is already enabled (from existing proxy code).
- The performance issues are query-level, not network-level.
