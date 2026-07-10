# Implementation Plan: Streaming Telemetry Logging Bug

**Branch**: `019-streaming-telemetry-bug` | **Date**: 2026-07-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/019-streaming-telemetry-bug/spec.md`

## Summary

Streaming responses (SSE) are not being recorded to telemetry because `_log_telemetry()` is called inside the `stream_generator()` async generator. If the generator is abandoned (client disconnect, garbage collection, server shutdown), the logging code never executes. The fix moves telemetry logging out of the generator into a reliable lifecycle pattern that guarantees logging regardless of generator completion.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: FastAPI (0.115+), Starlette (StreamingResponse), httpx (0.28+), DuckDB (1.5.4+)

**Storage**: DuckDB (single-file, single-connection per TelemetryLogger instance)

**Testing**: pytest (unit + integration tests marked with `@pytest.mark.integration`)

**Target Platform**: Linux/macOS server (CLI tool running as local proxy)

**Project Type**: CLI tool / web-service (FastAPI-based LLM API gateway)

**Performance Goals**: <5ms proxy overhead per request, <30s total test suite

**Constraints**: DuckDB single-process access only; concurrent reads/writes from same process OK but multi-process NOT supported; memory must remain constant regardless of request volume

**Scale/Scope**: Single-user local proxy; handles streaming LLM API calls (SSE responses)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | ✅ PASS | Fix is surgical — moves logging call, no new modules |
| II. Testing Standards | ⚠️ REQUIRED | Must add regression test that fails before fix and passes after |
| III. User Experience | ✅ PASS | No CLI/behavior change — streaming requests just get logged correctly |
| IV. Performance | ✅ PASS | No new overhead — logging already happens, just needs to be reliable |

**Required for merge**: Regression test per Principle II (bug fix MUST include a regression test).

## Project Structure

### Documentation (this feature)

```text
specs/019-streaming-telemetry-bug/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/otel_agent/
├── server.py            # BUG LOCATION: _handle_streaming() and stream_generator()
├── logger.py            # TelemetryLogger.log_request() — logging interface
├── storage/
│   ├── base.py          # StorageBackend abstract class
│   ├── duckdb.py        # DuckDBStorage.log_request() — INSERT + commit
│   └── sqlite.py        # SQLiteStorage.log_request() — fallback backend
└── ...

tests/
├── test_server.py       # Existing telemetry tests — needs new regression test
├── test_integration.py  # Integration tests — may need streaming test
└── ...
```

**Structure Decision**: Single project, src-layout. Fix is confined to `server.py` with a new test in `tests/test_server.py`.

## Complexity Tracking

No constitution violations — this is a surgical bug fix.
