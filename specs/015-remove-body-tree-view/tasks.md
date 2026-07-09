# Tasks: Remove Body Tree View

**Input**: Design documents from `/specs/015-remove-body-tree-view/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Not explicitly requested — verification via existing dashboard tests and manual scenarios.

**Organization**: Single user story — all tasks target one file: `src/otel_agent/dashboard/index.html`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1)
- Exact file paths included in descriptions

---

## Phase 1: Setup (No-op)

No project setup needed — this is a change to an existing single-file dashboard. Skip to Phase 2.

---

## Phase 2: User Story 1 - View Response Body in Raw Format Only (Priority: P1) 🎯 MVP

**Goal**: Remove the Tree/Raw toggle and all Tree view code, showing response bodies in raw (syntax-highlighted JSON) format directly.

**Independent Test**: Open dashboard, click a request with JSON body → body appears as highlighted JSON with no toggle buttons. Run `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/test_dashboard.py -v` → all pass.

### Implementation for User Story 1

- [X] T001 [US1] Remove Tree-only CSS classes in `src/otel_agent/dashboard/index.html`: delete `.json-toggle`, `.json-toggle:hover`, `.json-node`, `.body-viewer-toolbar`, `.body-toggle`, `.body-toggle.active`, `.json-badge`, `.json-badge-*` (model, messages, stream, usage, tool, system), `.json-children`, `.json-summary` (lines 81-86, 88-91, 97-103)

- [X] T002 [US1] Remove Tree-only JS functions in `src/otel_agent/dashboard/index.html`: delete `countJsonLines` (lines 344-346), `AUTO_COLLAPSE_THRESHOLD` constant (line 350), `renderJsonNode` (lines 352-477), `toggleJsonNode` (lines 479-486), `LLM_REQUEST_ANNOTATIONS` (lines 490-501), `LLM_RESPONSE_ANNOTATIONS` (lines 503-511), `getAnnotation` (lines 513-527)

- [X] T003 [US1] Remove `initBodyViewers` function in `src/otel_agent/dashboard/index.html` (lines 587-601)

- [X] T004 [US1] Remove Tree event delegation in `src/otel_agent/dashboard/index.html`: in the click handler (lines 605-635), delete the `.json-toggle` handler block (lines 606-612) and the `.body-toggle` handler block (lines 614-634). Keep the click handler structure but empty (or remove the handler entirely if no other click delegation remains).

- [X] T005 [US1] Remove `initBodyViewers()` call from `showDetail` in `src/otel_agent/dashboard/index.html` (line 297-298: remove comment and call)

- [X] T006 [US1] Simplify `formatBody` function in `src/otel_agent/dashboard/index.html`: replace the entire valid-JSON branch (lines 564-584) — remove `bodyId` generation, `countJsonLines`/`AUTO_COLLAPSE_THRESHOLD` usage, tree container HTML, toggle toolbar HTML, and `body-view-raw` with `display:none`. Replace with direct raw output: `<div class="body-raw">${rawHtml}</div>`. Update the function comment (line 547) to reflect raw-only rendering.

- [X] T007 [US1] Verify: run `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/test_dashboard.py -v` in project root — all tests must pass with zero failures

- [X] T008 [US1] Verify: run quickstart.md scenarios 1-5 manually — confirm no Tree/Raw toggle, raw JSON displays directly, no regressions

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: Skipped (no setup needed)
- **Phase 2 (User Story 1)**: Can start immediately — single file, all tasks sequential

### Within User Story 1

Tasks T001-T006 modify the same file (`index.html`) and must run sequentially to avoid conflicts:

```
T001 (CSS removal) → T002 (JS function removal) → T003 (initBodyViewers removal)
→ T004 (event delegation cleanup) → T005 (showDetail cleanup) → T006 (formatBody simplification)
→ T007 (test verification) → T008 (manual verification)
```

### Parallel Opportunities

None — all tasks target the same file. This is intentional for a single-file simplification.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

This feature has a single user story. The entire implementation is the MVP.

1. Execute T001-T006 (code changes, sequential)
2. Execute T007 (automated test verification)
3. Execute T008 (manual verification)
4. **STOP and VALIDATE**: Dashboard shows raw bodies only, no tree toggle, all tests pass
5. Commit and push

### Commit Strategy

Single commit after all changes verified:

```
refactor: remove tree view from dashboard body viewer, keep raw only

- Remove Tree/Raw toggle toolbar and Tree view rendering
- Simplify formatBody to show syntax-highlighted JSON directly
- Remove dead code: renderJsonNode, toggleJsonNode, initBodyViewers,
  getAnnotation, annotation constants, auto-collapse logic
- Remove Tree-only CSS classes (json-toggle, json-node, json-badge-*, etc.)
```

---

## Notes

- All 8 tasks target one file: `src/otel_agent/dashboard/index.html`
- No new code is written — this is pure removal/simplification
- CSS classes `.json-key`, `.json-string`, `.json-number`, `.json-boolean`, `.json-null` are SHARED with `highlightJsonString` (raw view) — must NOT be removed
- CSS classes `.body-empty`, `.body-raw` are raw-view — must NOT be removed
- `escapeHtml`, `highlightJsonString` are shared — must NOT be removed
- `formatBody` signature unchanged (still accepts `b, context`) — callers unaffected
