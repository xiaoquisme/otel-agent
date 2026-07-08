# Implementation Plan: Log Request Bodies and Response Headers to Database

**Branch**: `010-log-request-body` | **Date**: 2026-07-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/010-log-request-body/spec.md`

## Summary

The gateway's `_log_telemetry` function currently writes `request_body=""` and `response_headers={}` for every logged request, even though both values are available in memory. This plan populates those fields: the original client request body is forwarded to the logger, upstream response headers are captured from the HTTP response, known sensitive headers are redacted, and a `log_request_body` config flag is added for opt-out.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: FastAPI, uvicorn, httpx (async HTTP client), pyyaml

**Storage**: SQLite (existing telemetry logger, kept as-is — no schema migration needed)

**Testing**: pytest

**Target Platform**: macOS / Linux (local dev tool)

**Project Type**: CLI + web service

**Performance Goals**: <5ms proxy overhead per request (existing target — body serialization is negligible since body is already in memory)

**Constraints**: Must maintain backward-compatible config, no schema migration, hot-reload preserved

**Scale/Scope**: Single-user developer tool, low request volume

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| Code Quality | Functions <50 lines, type hints, docstrings | PASS — changes span small helpers; no new long functions |
| Testing | Every new function gets a unit test, deterministic, <30s | PASS — all changes testable with in-memory SQLite |
| UX Consistency | Error messages include what+how, --help preserved | PASS — no CLI flag changes |
| Performance | <5ms overhead, WAL mode, mtime check | PASS — body is already parsed; serialization is O(1) |

No violations. Proceeding.

## Project Structure

### Documentation (this feature)

```text
specs/010-log-request-body/
├── spec.md              # Feature specification
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
├── config.py            # Add log_request_body field to Config
├── logger.py            # Unchanged — already supports request_body + response_headers params
├── server.py            # Main changes — pass body/headers to _log_telemetry, redact sensitive headers
└── viewer.py            # Add response_headers display

tests/
├── test_logger.py       # Add tests for body/header storage
├── test_viewer.py       # Add test for response_headers display
├── test_config.py       # Add test for log_request_body config
└── test_server.py       # Add integration test for end-to-end logging
```

**Structure Decision**: Single project layout (existing). Changes are minimal and localized to 4 source files.

## Complexity Tracking

No constitution violations. No complexity tracking needed.
