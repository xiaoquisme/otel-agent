# Contract: Storage API (SQLite → DuckDB)

**Date**: 2026-07-09
**Feature**: 013-sqlite-to-duckdb-migration

## TelemetryLogger Interface

The `TelemetryLogger` class provides the write path for telemetry data.

### Constructor

```python
TelemetryLogger(db_path: Path) -> None
```

- Creates the database file if it does not exist
- Creates the `requests` table if it does not exist
- Creates indexes on `timestamp`, `method`, `response_status`
- If `db_path` has `.db` extension and a DuckDB file doesn't already exist, triggers migration

### log_request()

```python
log_request(
    method: str,
    url: str,
    request_headers: dict,
    request_body: str,
    response_status: int,
    response_headers: dict,
    response_body: str,
    latency_ms: float,
    upstream: str = "",
) -> None
```

- Inserts a single row into the `requests` table
- Timestamp is auto-generated (UTC ISO 8601)
- Headers are JSON-encoded before storage
- Commits immediately (no batching)

### close()

```python
close() -> None
```

- Closes the database connection

## DashboardAPI Interface

The `DashboardAPI` class provides the read path for the web dashboard.

### Constructor

```python
DashboardAPI(db_path: Path) -> None
```

- Opens a persistent connection to the database
- Uses read-only mode when possible

### get_requests()

```python
get_requests(
    search: str = "",
    method: str = "",
    status: int = 0,
    cursor: int = 0,
    limit: int = 50,
) -> dict
```

Returns:
```json
{
  "data": [{"id": 1, "timestamp": "...", ...}],
  "total": 100,
  "cursor": 0,
  "next_cursor": 50,
  "has_more": true
}
```

### get_request()

```python
get_request(request_id: int) -> dict | None
```

Returns full request details including headers and body.

### get_requests_since()

```python
get_requests_since(last_id: int) -> list[dict]
```

Returns requests with `id > last_id` (for SSE real-time updates).

### get_max_id()

```python
get_max_id() -> int
```

Returns the current maximum request ID.

### get_all_filtered()

```python
get_all_filtered(
    search: str = "",
    method: str = "",
    status: int = 0,
) -> list[dict]
```

Returns all matching requests (for export, no pagination).

## Migration Manager Interface

### migrate_sqlite_to_duckdb()

```python
migrate_sqlite_to_duckdb(sqlite_path: Path, duckdb_path: Path) -> bool
```

- Reads all rows from SQLite `requests` table
- Creates DuckDB database and `requests` table
- Inserts all rows
- Creates indexes
- Verifies row count matches
- Renames `.db` to `.db.bak`
- Returns `True` on success, `False` on failure

### needs_migration()

```python
needs_migration(db_path: Path) -> bool
```

- Returns `True` if `db_path` has `.db` extension and `.duckdb` equivalent doesn't exist
- Returns `False` otherwise

## SQL Compatibility

All queries used by the system are standard SQL that DuckDB supports:

| Query Pattern | sqlite3 | duckdb |
|---------------|---------|--------|
| `INSERT INTO ... VALUES (?)` | ✅ | ✅ |
| `SELECT ... WHERE method = ?` | ✅ | ✅ |
| `SELECT ... WHERE url LIKE ?` | ✅ | ✅ |
| `SELECT ... ORDER BY id DESC LIMIT ?` | ✅ | ✅ |
| `SELECT COUNT(*) FROM ...` | ✅ | ✅ |
| `SELECT MAX(id) FROM ...` | ✅ | ✅ |
| `CREATE TABLE IF NOT EXISTS ...` | ✅ | ✅ |
| `CREATE INDEX IF NOT EXISTS ...` | ✅ | ✅ |
