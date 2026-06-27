# Data Model: Dashboard Performance Optimization

**Feature**: 005-dashboard-performance
**Date**: 2026-06-26

## Schema Changes

### requests table — Add Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp);
CREATE INDEX IF NOT EXISTS idx_requests_method ON requests(method);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(response_status);
```

The `id` column already has a PRIMARY KEY index.

### CountCache (in-memory)

| Field     | Type    | Description                    |
| --------- | ------- | ------------------------------ |
| value     | int     | Cached COUNT result            |
| updated_at| float   | time.monotonic() when cached   |
| ttl       | float   | Cache lifetime in seconds (5.0)|

### Cursor (pagination parameter)

| Field  | Type    | Description                          |
| ------ | ------- | ------------------------------------ |
| last_id| int     | Last seen request ID (page cursor)   |
| limit  | int     | Max rows per page (default 50)       |

## Query Changes

### Before (slow)
```sql
SELECT COUNT(*) FROM requests WHERE ...
SELECT ... FROM requests WHERE ... ORDER BY id DESC LIMIT 50 OFFSET 100
```

### After (fast)
```sql
-- Count: cached, not queried every time
-- Pagination: cursor-based
SELECT id, timestamp, method, url, upstream, response_status, latency_ms
FROM requests
WHERE id < ? AND ...
ORDER BY id DESC
LIMIT 50
```

## Connection Strategy

- Single `sqlite3.Connection` per `DashboardAPI` instance
- WAL mode enabled on connection creation
- Connection reused across all API methods
- No connection pool needed (single-threaded server)
