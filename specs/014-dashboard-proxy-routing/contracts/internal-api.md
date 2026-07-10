# Internal Dashboard API Contract

**Date**: 2026-07-09
**Feature**: 014-dashboard-proxy-routing

## Overview

The proxy exposes internal HTTP endpoints that mirror the DashboardAPI methods. These endpoints are used by the dashboard process to query data through the proxy, avoiding DuckDB's exclusive file lock.

**Base URL**: `http://127.0.0.1:{proxy_port}`

**Authentication**: None (localhost only).

## Endpoints

### GET /internal/dashboard/requests

Paginated request list with filters.

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| search | string | "" | Filter by URL or upstream (LIKE match) |
| method | string | "" | Filter by HTTP method |
| status | int | 0 | Filter by response status code |
| cursor | int | 0 | Cursor for pagination (0 = first page) |
| limit | int | 50 | Max items per page (capped at 500) |

**Response** (200 OK):
```json
{
  "data": [{"id": 1, "timestamp": "...", "method": "POST", "url": "...", "upstream": "...", "response_status": 200, "latency_ms": 123.4}],
  "total": 393,
  "cursor": 0,
  "next_cursor": 391,
  "has_more": true
}
```

### GET /internal/dashboard/requests/{request_id}

Single request detail.

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| request_id | int | Request ID |

**Response** (200 OK):
```json
{
  "id": 1,
  "timestamp": "...",
  "method": "POST",
  "url": "...",
  "upstream": "...",
  "request_headers": {"content-type": "application/json"},
  "request_body": "...",
  "response_status": 200,
  "response_headers": {"content-type": "application/json"},
  "response_body": "...",
  "latency_ms": 123.4
}
```

**Response** (404 Not Found): `{"error": "Request not found"}`

### GET /internal/dashboard/max-id

Current maximum request ID (for SSE initialization).

**Response** (200 OK): `393` (integer)

### GET /internal/dashboard/requests-since/{last_id}

New requests since the given ID (for SSE polling).

**Path Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| last_id | int | Last known request ID |

**Response** (200 OK):
```json
[
  {"id": 394, "timestamp": "...", "method": "POST", "url": "...", "upstream": "...", "response_status": 200, "latency_ms": 456.7}
]
```

### GET /internal/dashboard/export

All filtered requests (for CSV/JSON export).

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| search | string | "" | Filter by URL or upstream |
| method | string | "" | Filter by HTTP method |
| status | int | 0 | Filter by response status code |

**Response** (200 OK): Array of full request records.

## Error Handling

All endpoints return JSON error responses:
```json
{"error": "Error description"}
```

Internal server errors return 500 with the error message.
