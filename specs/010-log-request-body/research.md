# Research: Log Request Bodies and Response Headers to Database

**Date**: 2026-07-08
**Feature**: 010-log-request-body

## Decisions

### D1: Request body capture point

**Decision**: Capture the request body from the `body` variable already parsed by `request.json()` in the endpoint handlers, and pass it through to `_log_telemetry`.

**Rationale**: FastAPI already reads and parses the request body via `await request.json()`. The parsed dict is available as `body` in both `chat_completions()` and `messages()`. Serializing it back to JSON for storage is negligible overhead. Re-reading from `request` would require consuming the body stream again (not possible with FastAPI).

**Alternatives considered**:
- Re-reading from `request.body()` — rejected because FastAPI consumes the body stream; calling it again raises an error or returns empty.
- Wrapping `request.json()` — rejected because it adds complexity with no benefit; the body is already in scope.

### D2: Response header capture point

**Decision**: Capture response headers from the `httpx.Response` object returned by `client.post()` (non-streaming) or `client.stream()` (streaming).

**Rationale**: Both `_handle_non_streaming` and `_handle_streaming` have direct access to the `httpx.Response` object. The response headers are available as `resp.headers` (a `httpx.Headers` object that behaves like a dict). Converting to a plain dict for JSON serialization is trivial.

**Alternatives considered**:
- Reading headers from the converted response body — rejected because conversion only transforms the body, not headers.

### D3: Sensitive header redaction approach

**Decision**: Redact a hardcoded set of known sensitive headers (`authorization`, `x-api-key`, `set-cookie`) by replacing their values with `[REDACTED]` before JSON serialization.

**Rationale**: The set of sensitive headers is small and well-known for LLM API providers. A hardcoded list is sufficient for a single-user developer tool. The redaction happens at the serialization boundary, just before writing to the database.

**Alternatives considered**:
- Configurable redaction list — rejected as over-engineering for a developer tool; can be added later if needed.
- Pattern-based redaction (e.g., redact any header containing "key" or "token") — rejected because it could redact useful headers like `x-ratelimit-reset-tokens`.

### D4: Config option placement

**Decision**: Add `log_request_body` as a top-level boolean in `config.yaml` (not nested under a `logging` section), defaulting to `true` when absent.

**Rationale**: Consistent with existing flat config structure. The Config class already supports hot-reload via mtime check, so no additional work needed for hot-reload support.

**Alternatives considered**:
- Nested under `logging:` section — rejected because it breaks the flat provider-list pattern established in the existing config.
- CLI flag `--log-body` — rejected because it would require threading through multiple commands; config is simpler.

### D5: Streaming response header capture

**Decision**: In the streaming path, response headers are available from `resp.headers` within the `async with client.stream(...)` context, before iterating lines.

**Rationale**: `httpx.AsyncClient.stream()` returns a context manager that yields an `httpx.Response` with headers populated before the body stream begins. Headers can be captured immediately on entry.

**Alternatives considered**:
- Collecting headers from SSE lines — rejected because SSE lines don't contain HTTP response headers.

### D6: Viewer display of response headers

**Decision**: Append response headers (truncated to 200 chars) to the `format_request()` output, on a new line after the request body.

**Rationale**: Consistent with the existing display pattern. Response headers are useful for debugging rate limits, request IDs, and content type.

**Alternatives considered**:
- Separate `view --headers` flag — rejected because it adds CLI complexity; showing both in one view is more useful for debugging.
