# Data Model: Web Dashboard for Request Logs

**Feature**: 004-web-dashboard
**Date**: 2026-06-26

## Entities

### Request Log (existing — read-only)

| Field            | Type    | Description                       |
| ---------------- | ------- | --------------------------------- |
| id               | integer | Auto-increment primary key        |
| timestamp        | string  | ISO 8601 UTC timestamp            |
| method           | string  | HTTP method (POST, GET, etc.)     |
| url              | string  | Full request URL                  |
| upstream         | string  | Resolved upstream URL             |
| request_headers  | string  | JSON-encoded request headers      |
| request_body     | string  | Full request body                 |
| response_status  | integer | HTTP response status code         |
| response_headers | string  | JSON-encoded response headers     |
| response_body    | string  | Full response body                |
| latency_ms       | float   | Request latency in milliseconds   |

**No schema changes needed.** The dashboard reads from the existing table.

### Dashboard API Response (derived)

| Field     | Type         | Description                    |
| --------- | ------------ | ------------------------------ |
| data      | list[Request] | Paginated request list        |
| total     | integer      | Total matching rows            |
| page      | integer      | Current page number            |
| per_page  | integer      | Rows per page                  |

### Filter Parameters (query string)

| Field    | Type    | Default | Description                    |
| -------- | ------- | ------- | ------------------------------ |
| search   | string  | ""      | Text search on URL/upstream    |
| method   | string  | ""      | Filter by HTTP method          |
| status   | integer | 0       | Filter by status code (0=all)  |
| page     | integer | 1       | Page number                    |
| per_page | integer | 50      | Rows per page                  |

## Validation Rules

1. `page` must be >= 1
2. `per_page` must be between 1 and 500
3. `method` must be a valid HTTP verb or empty
4. `status` must be a valid HTTP status code or 0
5. `search` is case-insensitive substring match
