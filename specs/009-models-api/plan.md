# Implementation Plan: Models API Endpoint

**Branch**: `main` | **Date**: 2026-07-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/009-models-api/spec.md`

## Summary

Add a GET `/v1/models` endpoint to the FastAPI gateway that queries each configured provider's model list endpoint, aggregates results with provider-name prefixes, caches them with a configurable TTL, and returns them in OpenAI-compatible format. Supports filtering by provider via query parameter.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: FastAPI, uvicorn, httpx (already installed), pyyaml

**Storage**: In-memory TTL cache (dict + timestamps), SQLite (telemetry, unchanged)

**Testing**: pytest

**Target Platform**: macOS / Linux (local dev tool)

**Project Type**: CLI + web service (FastAPI gateway)

**Performance Goals**: <500ms cached response, <5s uncached

**Constraints**: Providers may not expose model list endpoints; must handle gracefully

**Scale/Scope**: Single-process gateway, typically <20 providers configured

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Code Quality**: New module `models.py` has single responsibility. Functions under 50 lines. Type hints on all signatures. Docstrings on public functions.
- **Testing**: Unit tests for cache logic, model aggregation, provider filtering. Tests deterministic (mock httpx). Tests run in <30s.
- **UX Consistency**: GET `/v1/models` follows OpenAI response format. Error messages include what went wrong + what to do.
- **Performance**: Cache avoids per-request upstream calls. Config mtime check triggers cache invalidation.

**Post-design re-check**: All gates pass. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/009-models-api/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── models-api.md    # Phase 1 output
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
src/otel_agent/
├── server.py            # Modified: add /v1/models endpoint
├── models.py            # NEW: ModelCache, fetch_models, aggregate logic
├── config.py            # Unchanged
├── router.py            # Unchanged
└── ...

tests/
├── test_models.py       # NEW: tests for models.py
└── ...
```

**Structure Decision**: Single project. New module `models.py` for model discovery and caching logic. Endpoint registered in existing `server.py`.
