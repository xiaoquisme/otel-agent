# Data Model: SQLite to DuckDB Migration

**Date**: 2026-07-09
**Feature**: 013-sqlite-to-duckdb-migration

## Overview

The migration preserves the existing `requests` table schema. DuckDB uses the same column types with minor differences in auto-increment behavior.

## Entity: requests

| Column | SQLite Type | DuckDB Type | Notes |
|--------|-------------|-------------|-------|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | INTEGER PRIMARY KEY | DuckDB auto-increments INTEGER PK |
| timestamp | TEXT NOT NULL | TEXT NOT NULL | ISO 8601 format |
| method | TEXT NOT NULL | TEXT NOT NULL | GET, POST, PUT, DELETE |
| url | TEXT NOT NULL | TEXT NOT NULL | Full request URL |
| upstream | TEXT | TEXT | Upstream provider URL |
| request_headers | TEXT | TEXT | JSON-encoded headers |
| request_body | TEXT | TEXT | Raw request body |
| response_status | INTEGER | INTEGER | HTTP status code |
| response_headers | TEXT | TEXT | JSON-encoded headers |
| response_body | TEXT | TEXT | Raw response body |
| latency_ms | REAL | DOUBLE | Request latency in milliseconds |

## Indexes

| Index | Columns | Purpose |
|-------|---------|---------|
| idx_requests_timestamp | timestamp | Time-based queries |
| idx_requests_method | method | Method filtering |
| idx_requests_status | response_status | Status filtering |

## Migration Rules

1. Read all rows from SQLite `requests` table
2. Insert all rows into DuckDB `requests` table
3. Verify row count matches (source vs destination)
4. Rename SQLite `.db` file to `.db.bak`
5. Create indexes in DuckDB

## Validation Rules

- Row count in DuckDB MUST equal row count in original SQLite
- All columns MUST be transferred without data loss
- JSON-encoded fields (headers) MUST remain valid JSON
- Timestamps MUST preserve ISO 8601 format
- Latency values MUST preserve decimal precision
