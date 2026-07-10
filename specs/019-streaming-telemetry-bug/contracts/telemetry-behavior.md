# Contract: Streaming Telemetry Logging

**Feature**: 019-streaming-telemetry-bug

## Interface: `_handle_streaming()` Behavior Contract

The `_handle_streaming()` function in `server.py` MUST satisfy these invariants:

### INV-001: Telemetry Always Logged

For every invocation of `_handle_streaming()`:
- A telemetry record MUST be inserted into the `requests` table
- The record MUST include `response_body` containing `{"streamed": true, "preview": "..."}`
- This holds regardless of: client disconnect, upstream error, timeout, or server shutdown

### INV-002: Telemetry Data Completeness

The telemetry record for a streaming request MUST include:
- `method`: HTTP method from the original request
- `url`: Full request URL
- `request_body`: Original request body (truncated to 500KB if `log_body=True`)
- `response_status`: 200 (success), 502 (connection error), or 504 (timeout)
- `response_headers`: Upstream response headers (sensitive values redacted)
- `response_body`: `{"streamed": true, "preview": "<concatenated chunks, max 5000 chars>"}`
- `latency_ms`: Time from request start to stream completion/error

### INV-003: No Side Effects on Subsequent Requests

Streaming request logging MUST NOT:
- Leave DuckDB transactions uncommitted
- Leave the DuckDB connection in a locked state
- Affect the ability to log subsequent requests (streaming or non-streaming)

### INV-004: Error Resilience

If `_log_telemetry()` fails (e.g., DuckDB write error):
- The error MUST be caught and logged (via `logger.exception()`)
- The streaming response to the client MUST NOT be affected
- Subsequent requests MUST still be loggable
