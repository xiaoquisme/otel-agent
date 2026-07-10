# Implementation Plan: LLM-Aware Body Viewer

**Branch**: `016-llm-body-viewer` | **Date**: 2026-07-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/016-llm-body-viewer/spec.md`

## Summary

Enhance the dashboard body viewer to be LLM-format-aware: detect OpenAI/Anthropic request/response formats, render message content as formatted markdown (via marked.js + DOMPurify), display messages in a chat-like conversation flow with role labels, and show response metadata prominently. A "Show Raw" toggle preserves access to syntax-highlighted JSON. Single-file change to `index.html` (~452 → ~800 lines).

## Technical Context

**Language/Version**: JavaScript (ES6+), HTML, CSS — single-file dashboard

**Primary Dependencies**:
- `marked.js` ~25KB via CDN — markdown rendering
- `DOMPurify` ~7KB via CDN — XSS sanitization
- `chart.js` ~4.4.0 via CDN — already present (unaffected)

**Storage**: N/A — UI-only change

**Testing**: Manual dashboard verification + existing `tests/test_dashboard.py`

**Target Platform**: Web browser (dashboard served by Python http.server)

**Project Type**: CLI tool with embedded web dashboard

**Performance Goals**: Markdown rendering within 500ms of clicking a request

**Constraints**: Single file `index.html` — no backend changes, no build step

**Scale/Scope**: ~350 lines added, single file modification

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Code Quality | ✅ PASS | Functions under 50 lines. Docstrings on new functions. No dead code. |
| II. Testing Standards | ✅ PASS | Existing tests must pass. No new backend functions need unit tests. |
| III. UX Consistency | ✅ PASS | LLM view is an enhancement, not a breaking change. Fallback preserved. |
| IV. Performance | ✅ PASS | CDN-loaded libs cached by browser. No backend overhead. |

**Quality Gates**:
- ✅ Linting: No new Python code
- ✅ Tests: `uv run pytest tests/ -v` must pass
- ✅ No new public APIs or config changes
- ✅ No README changes needed

## Project Structure

### Documentation (this feature)

```text
specs/016-llm-body-viewer/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (minimal — client-side parsing)
├── quickstart.md        # Phase 1 output
├── checklists/
│   └── requirements.md  # Quality checklist
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (affected files)

```text
src/otel_agent/dashboard/
└── index.html           # ONLY file modified — CSS + JS additions

tests/
└── test_dashboard.py    # Existing tests — verify no regressions
```

## Complexity Tracking

No constitution violations.
