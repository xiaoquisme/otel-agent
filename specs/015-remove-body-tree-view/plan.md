# Implementation Plan: Remove Body Tree View

**Branch**: `015-remove-body-tree-view` | **Date**: 2026-07-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/015-remove-body-tree-view/spec.md`

## Summary

Remove the Tree/Raw toggle from the dashboard response body viewer, keeping only the raw (syntax-highlighted JSON) view. This simplifies the UI by eliminating an unnecessary toggle and approximately 200 lines of dead code (tree rendering, toggle logic, annotation badges, and associated CSS) from the single-file dashboard.

## Technical Context

**Language/Version**: JavaScript (ES6+), HTML, CSS — single-file dashboard (`index.html`)

**Primary Dependencies**: Chart.js (CDN, unaffected)

**Storage**: N/A — UI-only change

**Testing**: Manual dashboard verification + existing `tests/test_dashboard.py`

**Target Platform**: Web browser (dashboard served by FastAPI)

**Project Type**: CLI tool with embedded web dashboard

**Performance Goals**: N/A — removing code improves load time marginally

**Constraints**: Single file `src/otel_agent/dashboard/index.html` — all changes in this one file

**Scale/Scope**: ~200 lines removed, 0 new lines added

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | ✅ PASS | Removing dead code directly improves quality. No new functions added. |
| II. Testing Standards | ✅ PASS | Existing dashboard tests must pass. No new functions need unit tests (simplification only). |
| III. UX Consistency | ✅ PASS | Removing an unused toggle improves UX simplicity. No CLI behavior changes. |
| IV. Performance | ✅ PASS | Removing tree DOM rendering reduces memory and DOM manipulation on page load. |

**Quality Gates**:
- ✅ Linting: No new code; HTML/JS changes in existing file
- ✅ Tests: Run `uv run pytest tests/ -v` — all must pass
- ✅ No new public APIs or config changes
- ✅ No README changes needed (dashboard UI detail, not user-facing feature)

## Project Structure

### Documentation (this feature)

```text
specs/015-remove-body-tree-view/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (minimal — no data changes)
├── quickstart.md        # Phase 1 output
├── checklists/
│   └── requirements.md  # Quality checklist
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (affected files)

```text
src/otel_agent/dashboard/
└── index.html           # ONLY file modified — CSS + JS removals + formatBody simplification

tests/
└── test_dashboard.py    # Existing tests — verify no regressions
```

## Complexity Tracking

No constitution violations. This is a pure code removal simplification.

## Phase 0: Research

No NEEDS CLARIFICATION items in the spec. Research is minimal:

1. **Dead code audit**: Identify all symbols used exclusively by Tree view
2. **Annotation system dependency**: Verify `getAnnotation`, `LLM_REQUEST_ANNOTATIONS`, `LLM_RESPONSE_ANNOTATIONS` are only called from `renderJsonNode`
3. **CSS dependency check**: Verify which CSS classes are Tree-only vs shared with Raw view

**Research findings** (will be consolidated in research.md):

- `renderJsonNode` (lines 353-477): Tree-only — REMOVE
- `toggleJsonNode` (lines 480-486): Tree-only — REMOVE
- `initBodyViewers` (lines 588-601): Tree-only — REMOVE
- `countJsonLines` (lines 344-346): Tree-only (used for auto-collapse) — REMOVE
- `AUTO_COLLAPSE_THRESHOLD` (line 350): Tree-only — REMOVE
- `getAnnotation` (lines 514-527): Called only by `renderJsonNode` — REMOVE
- `LLM_REQUEST_ANNOTATIONS` (lines 491-501): Used only by `getAnnotation` — REMOVE
- `LLM_RESPONSE_ANNOTATIONS` (lines 504-511): Used only by `getAnnotation` — REMOVE
- Tree toggle event delegation (lines 606-612 in click handler) — REMOVE
- Body toggle event delegation (lines 614-634 in click handler) — REMOVE
- `initBodyViewers()` call in `showDetail` (line 298) — REMOVE
- CSS `.json-toggle`, `.json-toggle:hover`, `.json-node` — Tree-only — REMOVE
- CSS `.body-viewer-toolbar`, `.body-toggle`, `.body-toggle.active` — Tree-only — REMOVE
- CSS `.json-badge`, `.json-badge-*`, `.json-children`, `.json-summary` — Tree-only — REMOVE
- CSS `.json-key`, `.json-string`, `.json-number`, `.json-boolean`, `.json-null` — SHARED (used by `highlightJsonString` in Raw view) — KEEP
- CSS `.body-empty`, `.body-raw` — Raw view — KEEP
- `escapeHtml` — SHARED — KEEP
- `highlightJsonString` — Raw view — KEEP

## Phase 1: Design & Contracts

### data-model.md

No data model changes. This is a pure UI simplification — no entities, no state transitions, no storage changes.

### contracts/

No interface contracts affected. The dashboard is an internal tool, not a public API.

### quickstart.md

Validation scenarios for confirming the feature works:

1. **Prerequisites**: Run `otel-agent dashboard` (or equivalent) to start the dashboard with logged requests
2. **Test Scenario 1 — JSON body displays as raw**: Click any request with a JSON response body → body appears as syntax-highlighted JSON immediately, no Tree/Raw toggle visible
3. **Test Scenario 2 — Non-JSON body**: Click a request with non-JSON body → raw text with "Content is not valid JSON" hint appears
4. **Test Scenario 3 — Empty body**: Click a request with empty body → "(empty)" placeholder appears
5. **Test Scenario 4 — No tree DOM elements**: Open browser DevTools → inspect response body section → no `.body-view-tree`, `.json-node`, `.json-toggle`, or `.body-viewer-toolbar` elements present
6. **Test Scenario 5 — Existing tests pass**: Run `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/test_dashboard.py -v` → all tests pass
