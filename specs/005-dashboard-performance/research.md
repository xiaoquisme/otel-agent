# Research: Dashboard Performance Optimization

**Feature**: 005-dashboard-performance
**Date**: 2026-06-26

## Decision 1: Database Indexes

**Decision**: Add indexes on `id` (already PK), `timestamp`, `method`, and `response_status` columns.

**Rationale**: These are the columns used in WHERE, ORDER BY, and filter clauses. Without indexes, every query is a full table scan.

**Alternatives considered**:
- Composite index on (method, response_status, timestamp): Covers common filter combinations but more complex.
- Full-text index on url/upstream: SQLite FTS5 is powerful but adds complexity. LIKE with leading wildcard can't use B-tree indexes anyway.

## Decision 2: COUNT Caching

**Decision**: Cache the COUNT result in memory with a 5-second TTL. Return stale count if cache is valid.

**Rationale**: COUNT(*) scans the entire table. For a dashboard, the exact count doesn't need to be real-time. 5-second cache reduces query load by ~5x for active users.

**Alternatives considered**:
- SQLite's `max(id)` as approximate count: Instant but inaccurate if rows are deleted.
- Trigger-based counter: More complex, requires schema changes.
- No caching with index: Still slow for large tables.

## Decision 3: Connection Pooling

**Decision**: Use a single persistent `sqlite3.Connection` with WAL mode. Thread-safe via SQLite's built-in threading support.

**Rationale**: Creating a new connection per request adds overhead. SQLite WAL mode allows concurrent reads from a single connection. The dashboard is single-threaded (http.server), so no lock contention.

**Alternatives considered**:
- Connection pool (multiple connections): Overkill for single-threaded server.
- New connection per request: Current approach, too slow.

## Decision 4: Cursor-Based Pagination

**Decision**: Use `WHERE id < ? ORDER BY id DESC LIMIT ?` instead of `OFFSET`. Client sends the last seen `id` as cursor.

**Rationale**: OFFSET scans and discards rows. Cursor-based pagination uses the index directly. Performance is constant regardless of page number.

**Alternatives considered**:
- Keep OFFSET with index: Still O(offset) for high pages.
- Keyset pagination with composite key: More complex, not needed for single-column PK.

## Decision 5: Detail Page Optimization

**Decision**: Use the persistent connection for detail queries. The `SELECT * WHERE id = ?` is already fast with PK index. The issue is likely connection overhead, not query complexity.

**Rationale**: PK lookup is O(log n). If detail page is slow, it's connection creation overhead, not the query itself.

## Decision 6: Default Database Path

**Decision**: Change default DB path from `telemetry.db` (relative) to `~/.otel-agent/telemetry.db` (absolute). Create `~/.otel-agent/` directory if needed.

**Rationale**: BUG-001 identified that relative paths cause proxy and dashboard to use different databases. Absolute path ensures consistency.
