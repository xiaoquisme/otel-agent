# Data Model: Fix Body Rendering for Truncated Data

**Date**: 2026-07-10
**Feature**: 018-fix-body-rendering

## Entities

### Request Record (existing — no schema change)

| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER | Primary key, auto-increment |
| timestamp | TIMESTAMP | Request time |
| method | TEXT | HTTP method |
| url | TEXT | Request URL |
| upstream | TEXT | Upstream provider URL |
| request_headers | TEXT/JSON | Redacted headers |
| request_body | TEXT | **Limit: 100KB → 500KB** |
| response_status | INTEGER | HTTP status code |
| response_headers | TEXT/JSON | Response headers |
| response_body | TEXT | **Limit: 100KB → 500KB** |
| latency_ms | FLOAT | Request latency |

**No schema migration needed** — DuckDB TEXT columns have no fixed size limit. Changing the Python slice constant is sufficient.

### Streaming Preview (embedded in response_body)

Stored as: `{"streamed": true, "preview": "<concatenated JSON chunks>"}`

| Field | Old Limit | New Limit | Rationale |
|-------|-----------|-----------|-----------|
| preview | 500 chars | 5,000 chars | Captures ~12-25 SSE chunks |

### Truncation State (new — client-side only)

Not stored. Detected at render time in the dashboard:

| Condition | Detection | Display |
|-----------|-----------|---------|
| Request body truncated | `body.length >= 500000 && JSON.parse()` fails | "Body truncated" banner + raw content |
| Response body truncated | `body.length >= 500000 && JSON.parse()` fails | "Body truncated" banner + raw content |
| Streaming preview incomplete | `preview.length >= 5000 && no content chunks` | "Streaming preview may be incomplete" note |

## State Transitions

None — this is a limit increase + client-side detection. No new states or lifecycle changes.

## Validation Rules

- Request body slice: `[:500_000]` (Python) — must be applied consistently in `_log_telemetry()`
- Response body slice: `[:500_000]` (Python) — same function
- Streaming preview slice: `[:5_000]` (Python) — in `_handle_streaming()`
- Truncation detection: client-side only, no server changes needed
