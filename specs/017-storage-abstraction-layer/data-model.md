# Data Model: Storage Abstraction Layer

**Date**: 2026-07-09
**Feature**: 017-storage-abstraction-layer

## Summary

No schema changes. The `requests` table schema remains identical. This feature adds an abstraction layer over existing storage — it does not change what is stored or how.

## Storage Interface (ABC)

**Module**: `src/otel_agent/storage/base.py`

```
StorageBackend (ABC)
├── initialize() → None
│     Create tables and indexes if they don't exist
├── log_request(method, url, request_headers, request_body,
│               response_status, response_headers, response_body,
│               latency_ms, upstream) → None
│     Insert a request record
├── get_requests(search, method, status, cursor, limit) → dict
│     Paginated query with filters. Returns {data, total, cursor, next_cursor, has_more}
├── get_request(request_id) → dict | None
│     Single record by ID
├── get_requests_since(last_id) → list[dict]
│     Records with id > last_id (for SSE)
├── get_max_id() → int
│     Maximum record ID
├── get_all_filtered(search, method, status) → list[dict]
│     All matching records (for export, no pagination)
└── close() → None
      Cleanup connections
```

## Backend Implementations

### DuckDB Backend (`storage/duckdb.py`)

- Wraps existing DuckDB code from `logger.py`, `viewer.py`, `dashboard/api.py`
- Uses `duckdb.connect()` with optional `read_only` parameter
- Supports `CREATE SEQUENCE` and `CREATE TABLE IF NOT EXISTS`
- SQL syntax: DuckDB dialect

### SQLite Backend (`storage/sqlite.py`)

- Uses `sqlite3` from stdlib
- Uses `INTEGER PRIMARY KEY AUTOINCREMENT` instead of sequences
- Sets `PRAGMA journal_mode=WAL` for concurrent reads
- SQL syntax: SQLite dialect

## Request Record (unchanged)

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER | Primary key, auto-increment |
| timestamp | TEXT | ISO 8601 UTC |
| method | TEXT | HTTP method |
| url | TEXT | Request URL |
| upstream | TEXT | Upstream provider |
| request_headers | TEXT | JSON string |
| request_body | TEXT | Raw body |
| response_status | INTEGER | HTTP status code |
| response_headers | TEXT | JSON string |
| response_body | TEXT | Raw body |
| latency_ms | DOUBLE | Request latency |

## Storage Factory

**Module**: `src/otel_agent/storage/__init__.py`

```python
def create_storage(backend: str = "duckdb", db_path: Path, read_only: bool = False) -> StorageBackend
```

Backend selection logic:
1. Look up `backend` string in `BACKENDS` dict
2. If not found → raise `ValueError` with valid options
3. If found but import fails (e.g., duckdb not installed) → fall back to next available with warning
4. Return instantiated backend
