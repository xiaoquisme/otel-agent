# Data Model: Streaming Telemetry Logging Bug

**Feature**: 019-streaming-telemetry-bug

## Entities

No new entities. This bug fix operates on existing entities:

### Request Record (existing)

| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER (PK) | Auto-incrementing request ID |
| timestamp | TEXT | ISO 8601 UTC timestamp |
| method | TEXT | HTTP method (POST) |
| url | TEXT | Request URL |
| upstream | TEXT | Upstream provider base URL |
| request_headers | TEXT | JSON-encoded request headers |
| request_body | TEXT | Original request body (up to 500KB) |
| response_status | INTEGER | HTTP status code |
| response_headers | TEXT | JSON-encoded upstream response headers |
| response_body | TEXT | Response body — for streaming: `{"streamed": true, "preview": "..."}` |
| latency_ms | DOUBLE | End-to-end latency in milliseconds |

### State Transition (bug fix impact)

**Before fix**:
- Streaming request → generator runs → `_log_telemetry()` at end of generator → IF generator completes: logged; IF generator abandoned: NOT logged

**After fix**:
- Streaming request → generator runs → `finally` block ensures `_log_telemetry()` always runs → logged regardless of generator completion

## Validation Rules

- `response_body` for streaming MUST contain `{"streamed": true, "preview": "<chunks>"}` (FR-004)
- `preview` field MUST be truncated to 5,000 characters max
- `response_status` MUST be set to actual upstream status (200 on success, 502 on connection error, 504 on timeout)
- `latency_ms` MUST reflect total time from request start to stream completion
