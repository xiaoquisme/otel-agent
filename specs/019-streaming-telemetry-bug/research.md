# Research: Streaming Telemetry Logging Bug

**Feature**: 019-streaming-telemetry-bug
**Date**: 2026-07-11

## R1: StreamingResponse Generator Lifecycle

**Decision**: `_log_telemetry()` must be moved into a `finally` block inside the generator.

**Rationale**: Analysis of Starlette's `StreamingResponse.__call__()` source reveals:

```python
# ASGI spec >= 2.4 path:
try:
    await self.stream_response(send)
except OSError:
    raise ClientDisconnect()

# Older ASGI spec path:
async with create_collapsing_task_group() as task_group:
    task_group.start_soon(wrap, partial(self.stream_response, send))
    await wrap(partial(self.listen_for_disconnect, receive))

# Background runs AFTER stream completes (or fails):
if self.background is not None:
    await self.background()
```

Key findings:
1. `stream_response()` iterates the generator via `async for chunk in self.body_iterator`
2. On client disconnect, `OSError` → `ClientDisconnect` is raised, which closes the generator
3. `BackgroundTask` runs AFTER `stream_response()` — it CANNOT access generator-local state
4. If the generator is garbage-collected before iteration starts, no `finally` block runs — but this is an extreme edge case (FastAPI always iterates the generator)

**Current bug**: `_log_telemetry()` is at line 360, AFTER the `try/except` block but INSIDE the generator. When `GeneratorExit` is raised (generator garbage-collected) or the generator is closed by Starlette on client disconnect, code after the `try/except` may not execute reliably.

**Alternatives considered**:
- BackgroundTask: Cannot access generator-local `collected_text` — rejected
- Wrapper class with `__del__`: Handles garbage-collection edge case but adds complexity — deferred to future if needed
- Log before + update after: Requires two-phase storage (INSERT + UPDATE) — adds complexity to storage layer

## R2: DuckDB Connection State After Interrupted Streams

**Decision**: No connection cleanup changes needed — DuckDB handles this correctly.

**Rationale**: DuckDB's Python client uses autocommit by default. Each `conn.execute()` + `conn.commit()` is a self-contained transaction. If the generator is interrupted:
- The INSERT either completes (committed) or doesn't (rolled back)
- No partial transaction state is left behind
- Subsequent `conn.execute()` calls work normally

The single-connection model is sufficient for this use case (single-process async, sequential writes).

## R3: FastAPI BackgroundTask with StreamingResponse

**Decision**: Do NOT use BackgroundTask for streaming telemetry.

**Rationale**: `BackgroundTask` runs after the response is fully sent. It cannot access generator-local variables (`collected_text`, `resp_headers`, `stream_status`). To use it, we would need to:
1. Store collected state in an external data structure (dict, context var)
2. Reference that structure from the background task
3. Clean up the external structure after logging

This adds unnecessary complexity when a `finally` block inside the generator achieves the same reliability with zero additional state management.

## R4: Regression Test Strategy

**Decision**: Use mock upstream server + mock storage to test telemetry logging for streaming.

**Rationale**: The regression test must:
1. Fail BEFORE the fix (prove the bug exists)
2. Pass AFTER the fix (prove the fix works)
3. Be deterministic (no real network calls)

Pattern:
- Mock the upstream HTTP server to return SSE chunks
- Mock or use in-memory storage backend
- Send a streaming request through the FastAPI test client
- Verify the telemetry record exists in storage
- Also test client-disconnect scenario (close client mid-stream)
