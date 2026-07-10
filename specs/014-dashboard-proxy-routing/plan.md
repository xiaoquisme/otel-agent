# Implementation Plan: Dashboard Proxy Routing

**Branch**: `014-dashboard-proxy-routing` | **Date**: 2026-07-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/014-dashboard-proxy-routing/spec.md`

**Note**: This feature was already implemented as BUG-001 and BUG-002 fixes. The plan documents the existing architecture for traceability.

## Summary

Route dashboard database queries through the proxy's internal HTTP API instead of opening a separate DuckDB connection. This avoids DuckDB's exclusive file lock conflict (BUG-001) and handles health-check timeout race conditions (BUG-002).

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**: duckdb, fastapi, uvicorn, httpx, pyyaml (existing)
**Storage**: DuckDB file (`.duckdb`) — exclusive lock per process
**Testing**: pytest (existing test suite)
**Target Platform**: macOS/Linux/Windows
**Project Type**: CLI tool + web dashboard (Python package)
**Performance Goals**: Dashboard queries < 500ms for 100K rows; proxy health check cached for 30s
**Constraints**: Must not break existing CLI/dashboard behavior; must handle proxy startup/shutdown gracefully
**Scale/Scope**: 2 source files modified, 1 source file extended, ~200 lines changed

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | ✅ PASS | Single responsibility; docstrings on all public functions; type hints present |
| II. Testing Standards | ✅ PASS | 3 new unit tests for caching; 2 integration tests for internal API; regression test for lock conflict |
| III. User Experience Consistency | ✅ PASS | Dashboard behavior identical; proxy routing is transparent to users |
| IV. Performance Requirements | ✅ PASS | Proxy health check cached (30s TTL); no unbounded buffers; DuckDB concurrency handled architecturally |

**Gate Result**: PASS — all principles satisfied.

## Project Structure

### Documentation (this feature)

```text
specs/014-dashboard-proxy-routing/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── internal-api.md  # Internal dashboard API contract
└── tasks.md             # Phase 2 output (NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/otel_agent/
├── server.py            # EXTENDED: Internal dashboard API endpoints + query helpers
├── dashboard/
│   ├── api.py           # MODIFIED: Proxy routing with DuckDB fallback + URL caching
│   └── server.py        # MODIFIED: Pass proxy_port to DashboardAPI
├── commands/
│   └── dashboard.py     # MODIFIED: Detect proxy port on startup
└── process.py           # EXISTING: get_proxy_status() for proxy detection

tests/
├── test_dashboard.py    # MODIFIED: 3 new caching tests
└── test_integration.py  # MODIFIED: 2 new internal API tests
```

**Structure Decision**: Minimal changes to existing architecture. Internal API endpoints added to proxy's FastAPI app. DashboardAPI gains proxy routing with TTL-based caching.

## Complexity Tracking

> No Constitution Check violations — no complexity tracking needed.
