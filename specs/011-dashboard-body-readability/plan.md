# Implementation Plan: Dashboard Body Readability

**Branch**: `011-dashboard-body-readability` | **Date**: 2026-07-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/011-dashboard-body-readability/spec.md`

## Summary

Enhance the otel-agent dashboard's request/response body viewer from plain `<pre>` text to an interactive JSON tree with syntax highlighting, collapsible nodes, and LLM-API-specific semantic annotations. The implementation is purely client-side (vanilla JS in `index.html`) — no backend API changes required.

## Technical Context

**Language/Version**: JavaScript (ES2022+, vanilla, no framework), HTML5, CSS3

**Primary Dependencies**: None new — existing dashboard uses vanilla JS with Chart.js (CDN). JSON viewer implemented as pure DOM manipulation. No build step.

**Storage**: SQLite (existing `requests` table, TEXT columns for `request_body` and `response_body`). No schema changes needed.

**Testing**: Manual browser testing + pytest for any backend changes. Dashboard tests are visual/interactive — no automated JS test framework currently in place.

**Target Platform**: Modern browsers (Chrome 90+, Firefox 90+, Safari 15+, Edge 90+)

**Project Type**: Web application (embedded HTTP server in Python package)

**Performance Goals**: Body rendering <500ms for payloads up to 100KB. Smooth scrolling with large payloads.

**Constraints**: Single HTML file architecture (all CSS/JS inline). No npm/build step. External CDN acceptable for lightweight libraries but vanilla JS preferred.

**Scale/Scope**: Single-file change to `src/otel_agent/dashboard/index.html`. 3 UI enhancements (syntax highlighting, collapsible tree, semantic annotations). No backend API changes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | ✅ PASS | Single HTML file with inline JS — functions kept small and well-named. Docstrings via comments on key functions. |
| II. Testing Standards | ⚠️ PARTIAL | Dashboard is visual/interactive — automated JS testing not currently in project. Manual verification via quickstart scenarios. Constitution allows visual testing for UI components. |
| III. UX Consistency | ✅ PASS | Dark theme colors extended consistently. Error states (empty, non-JSON) handled gracefully. |
| IV. Performance | ✅ PASS | Collapsible tree avoids DOM-heavy full renders. Large payloads handled with auto-collapse. |

**Gate Verdict**: PASS (no violations requiring justification)

## Constitution Re-Check (Post-Phase 1 Design)

*Re-evaluated after design artifacts are complete.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | ✅ PASS | JS functions kept small and focused: `renderJsonNode()`, `toggleNode()`, `switchView()`. Color constants defined as CSS, not magic strings in JS. |
| II. Testing Standards | ⚠️ PARTIAL | 8 manual validation scenarios in quickstart.md. No automated JS tests (consistent with existing dashboard — no JS test framework in project). |
| III. UX Consistency | ✅ PASS | Dark theme colors tested for WCAG AA contrast. Error states (empty, non-JSON, huge body) all handled gracefully. Existing copy-as-curl preserved. |
| IV. Performance | ✅ PASS | Auto-collapse for large payloads (>50 lines). No new network requests. Event delegation avoids O(n) handler binding. Single file change keeps overhead minimal. |

**Gate Verdict**: PASS

## Project Structure

### Documentation (this feature)

```text
specs/011-dashboard-body-readability/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── body-viewer-ui.md
├── spec.md              # Feature specification
├── checklists/
│   └── requirements.md  # Quality checklist
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/otel_agent/
├── dashboard/
│   ├── index.html       # Main dashboard HTML + CSS + JS (PRIMARY CHANGE)
│   ├── server.py        # HTTP server (no changes)
│   └── api.py           # JSON API (no changes)
├── logger.py            # Telemetry logger (no changes)
└── ...
```

**Structure Decision**: Single-file change to `index.html`. All enhancements are client-side JavaScript and CSS additions within the existing dashboard HTML file. No new files or backend modifications required.
