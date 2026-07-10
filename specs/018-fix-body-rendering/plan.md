# Implementation Plan: Fix Body Rendering for Truncated Data

**Branch**: `018-fix-body-rendering` | **Date**: 2026-07-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/018-fix-body-rendering/spec.md`

## Summary

Request bodies truncated at 100KB break JSON validity, causing the dashboard to show raw text instead of formatted LLM chat. Streaming response previews truncated at 500 chars capture only 1-2 chunks with no content. Fix: increase storage limits (100KB→500KB request, 500→5000 char preview) and add dashboard-level truncation detection with graceful fallback rendering.

## Technical Context

**Language/Version**: Python 3.13, JavaScript (ES2020+)
**Primary Dependencies**: FastAPI (proxy), DuckDB (storage), marked.js + DOMPurify (CDN, dashboard)
**Storage**: DuckDB TEXT columns — no schema change needed, only limit constants
**Testing**: pytest (Python), manual dashboard verification (HTML/JS)
**Target Platform**: macOS/Linux server, browser (dashboard)
**Project Type**: web-service (LLM API proxy + dashboard)
**Performance Goals**: Dashboard render < 2s for 500KB bodies; proxy overhead < 5ms
**Constraints**: DuckDB single-process lock; single-file dashboard HTML; CDN-only frontend deps
**Scale/Scope**: Single-file change in `server.py` (2 constants), single-file change in `index.html` (truncation detection + rendering)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | ✅ PASS | Changes are minimal — 2 constant updates + JS helper functions. No new modules. |
| II. Testing Standards | ⚠️ NEEDS ATTENTION | Dashboard is client-side JS — no automated tests. Python constants need no new tests. Regression test needed for truncation detection logic. |
| III. User Experience | ✅ PASS | Truncation indicator is user-facing improvement. No CLI changes. |
| IV. Performance | ✅ PASS | 500KB limit is within "up to 10MB" rule. Dashboard rendering time target is < 2s. |

**Gate Verdict**: PASS with note — test coverage gap for JS truncation detection is acceptable since dashboard has no test harness (established pattern from 016-llm-body-viewer).

## Project Structure

### Documentation (this feature)

```text
specs/018-fix-body-rendering/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── checklists/
│   └── requirements.md  # (created by speckit-specify)
└── spec.md              # Feature specification
```

### Source Code (repository root)

```text
src/otel_agent/
├── server.py            # Update: increase body truncation limits (2 constants)
├── dashboard/
│   └── index.html       # Update: truncation detection + graceful rendering
tests/
└── test_server.py       # Existing: verify no regression
```

**Structure Decision**: Minimal change — 2 files modified (server.py constants + index.html JS). No new modules, no schema changes.

## Complexity Tracking

> No constitution violations requiring justification.

## Phase Status

- [x] Phase 0: Research — `research.md` complete, all unknowns resolved
- [x] Phase 1: Design — `data-model.md`, `contracts/internal-api.md`, `quickstart.md` complete
- [ ] Phase 2: Tasks — not created by `/speckit-plan` (use `/speckit-tasks`)

**Bugfix**: 2026-07-10 — BUG-002 Updated from bugfix patch. FR-004 (partial LLM rendering from truncated JSON) was not scoped into Phase 3 tasks. Added T017 to cover this gap.

**Bugfix**: 2026-07-10 — BUG-003 Updated from bugfix patch. Tool message rendering needs <pre> path, not markdown.
