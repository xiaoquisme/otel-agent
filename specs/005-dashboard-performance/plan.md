# Implementation Plan: Dashboard Performance Optimization

**Branch**: `005-dashboard-performance` | **Date**: 2026-06-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-dashboard-performance/spec.md`

## Summary

Optimize the dashboard API for fast load times: add database indexes, cache COUNT queries (5s TTL), use persistent connection, switch to cursor-based pagination, and fix default database path. No new dependencies.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: stdlib `sqlite3`, `http.server` (no new deps)

**Storage**: SQLite with WAL mode

**Testing**: pytest

**Target Platform**: Linux, macOS, WSL

**Project Type**: CLI tool with embedded web server

**Performance Goals**: <1s initial load (10k requests), <500ms search, <1s detail page

**Constraints**: No new dependencies. Backward-compatible API (frontend JS needs update for cursor pagination).

**Scale/Scope**: Up to 50,000 requests in database

## Constitution Check

| Principle | Gate | Status |
| --------- | ---- | ------ |
| I. Code Quality | Single responsibility, type hints | ✅ PASS — changes isolated to api.py and logger.py |
| II. Testing Standards | Unit tests for each change | ✅ PASS — tests for indexes, caching, cursor pagination |
| III. UX Consistency | --help, clear errors | ✅ PASS — no CLI changes |
| IV. Performance | <5ms overhead | ✅ PASS — this IS the performance fix |

No violations.

## Project Structure

### Documentation (this feature)

```text
specs/005-dashboard-performance/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api.md
└── tasks.md
```

### Source Code (files to change)

```text
src/otel_agent/
├── dashboard/
│   ├── api.py           # Connection pooling, cached COUNT, cursor pagination
│   ├── server.py        # Update API handler for cursor params
│   └── index.html       # Update JS for cursor-based pagination
├── logger.py            # Add index creation
└── commands/
    └── proxy.py         # Fix default DB path to ~/.otel-agent/telemetry.db
    └── dashboard.py     # Fix default DB path

tests/
├── test_dashboard.py    # Add tests for cursor pagination, COUNT cache
└── test_logger.py       # Add test for index creation
```

**Structure Decision**: Changes are minimal and isolated. No new files needed — only modifications to existing modules.
