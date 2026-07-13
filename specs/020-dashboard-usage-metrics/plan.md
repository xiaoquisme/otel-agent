# Implementation Plan: Dashboard Usage Metrics

**Branch**: `main` (no feature branch created by configured hooks) | **Date**: 2026-07-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/020-dashboard-usage-metrics/spec.md`

## Summary

Add a Langfuse-like current-day usage overview to the existing dashboard: total, input, and output tokens; transparent coverage for requests without usage; and a ranked per-model breakdown. The gateway will normalize provider-reported usage and the client-visible model while logging, persist nullable analytics fields through additive schema upgrades, and serve date-bounded aggregates through the proxy-safe dashboard query path. The single-file dark dashboard will render compact cards and an accessible, responsive model table without a new visualization dependency.

## Technical Context

**Language/Version**: Python 3.10+; browser HTML, CSS, and vanilla JavaScript

**Primary Dependencies**: FastAPI, httpx, DuckDB, optional SQLite storage backend; existing Chart.js/marked/DOMPurify dashboard assets (no new dependency)

**Storage**: Existing `requests` table in DuckDB (default) and SQLite (fallback), extended with nullable `model_name`, `input_tokens`, `output_tokens`, and `total_tokens` analytics fields

**Testing**: pytest; deterministic unit and API-route tests. Standard gate: `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest -m 'not integration'`

**Target Platform**: macOS/Linux/Windows proxy and browser dashboard

**Project Type**: Python CLI gateway with a standalone web dashboard

**Performance Goals**: Current-day summary and model breakdown visible within 2 seconds for 100,000 recorded requests; newly completed token-bearing requests represented within 2 seconds; no additional proxy request-path delay beyond bounded normalization and one telemetry write

**Constraints**: Never estimate tokens from text; preserve existing dashboard operations; historical telemetry remains readable; proxy owns active DuckDB access and dashboard reads route through its internal API while available; usage endpoint accepts only validated bounded UTC ranges; no unbounded in-memory aggregation

**Scale/Scope**: One extended telemetry table, two storage implementations, SQLite-to-DuckDB migration, telemetry logger/server path, dashboard API/server, one standalone dashboard HTML file, and focused pytest coverage. Version one excludes cost, budgets, alerts, and custom date selectors.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Pre-design status | Post-design status | Notes |
|-----------|-------------------|--------------------|-------|
| I. Code Quality | PASS | PASS | Keep normalization, aggregation, and HTTP boundary helpers small and single-purpose; public storage methods receive type hints and docstrings. |
| II. Testing Standards | PASS | PASS | Add deterministic unit tests for normalizer, schema upgrades, aggregates, and dashboard behavior; avoid external-network dependencies. |
| III. User Experience Consistency | PASS | PASS | Existing commands and dashboard functions remain unchanged; metrics use explicit empty, loading, and unavailable-usage states. |
| IV. Performance Requirements | PASS | PASS | Persisted numeric fields and database aggregation prevent body scans; proxy-routed dashboard reads avoid DuckDB lock conflicts; no unbounded buffers. |

**Gate Result**: PASS. No violations or complexity exceptions require tracking.

## Project Structure

### Documentation (this feature)

```text
specs/020-dashboard-usage-metrics/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── dashboard-usage-api.md
└── tasks.md                 # created by /speckit-tasks
```

### Source Code (repository root)

```text
src/otel_agent/
├── logger.py                 # MODIFY: accept and persist normalized analytics fields
├── migration.py              # MODIFY: preserve analytics fields during SQLite-to-DuckDB migration
├── server.py                 # MODIFY: normalize telemetry usage and expose proxy usage aggregate
├── storage/
│   ├── base.py               # MODIFY: add typed usage-summary storage contract
│   ├── duckdb.py             # MODIFY: additive schema upgrade, indexes, write/query aggregate
│   └── sqlite.py             # MODIFY: equivalent fallback schema and aggregate behavior
└── dashboard/
    ├── api.py                # MODIFY: proxy-first and offline usage-summary access
    ├── server.py             # MODIFY: public usage endpoint and range validation
    └── index.html            # MODIFY: accessible responsive summary cards and model ranking table

tests/
├── test_logger.py            # MODIFY: persisted normalized analytics fields
├── test_migration.py         # MODIFY: legacy and migrated schema compatibility
├── test_dashboard.py         # MODIFY: aggregate, proxy, direct-read, and API behavior
└── test_server.py            # MODIFY: OpenAI/Anthropic normalization and no-usage cases
```

**Structure Decision**: Retain the existing single-project architecture. The storage abstraction remains the aggregation boundary, the FastAPI proxy remains the authoritative active DuckDB reader, and the standalone dashboard continues to own presentation. No new service, client bundle, or database table is needed for the current-day-only scope.

## Implementation Sequence

1. Define typed analytics and usage-summary shapes plus a pure normalization helper with complete valid/invalid/partial cases; retain the latest valid usage while processing streaming chunks so bounded stream previews are never used as an aggregate source.
2. Extend both storage schemas idempotently, including legacy in-place upgrades, analytics write fields, UTC-range aggregation, deterministic model ordering, and indexes.
3. Update telemetry logging and the SQLite-to-DuckDB migration to carry the nullable analytics projection without changing existing raw payload retention.
4. Add proxy internal usage endpoint; add dashboard API and public endpoint with strict time-range validation and established proxy/offline behavior.
5. Add dashboard overview markup, responsive dark-theme styles, escaped rendering helpers, independent loading/error handling, live refresh, and accessible coverage messaging.
6. Add and run deterministic tests, then execute the manual quickstart scenarios.

## Complexity Tracking

> No constitution violations; no complexity tracking required.
