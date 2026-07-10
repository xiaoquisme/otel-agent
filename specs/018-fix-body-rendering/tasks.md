# Tasks: Fix Body Rendering for Truncated Data

**Input**: Design documents from `/specs/018-fix-body-rendering/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not requested — dashboard is client-side JS with no test harness (established pattern).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup

**Purpose**: No project setup needed — this is an incremental change to existing files.

*(Skipped — no setup tasks required)*

---

## Phase 2: Foundational — Increase Storage Limits

**Purpose**: Backend constant changes that enable all user stories. MUST complete before dashboard work.

- [X] T001 [P] Increase request body storage limit from 100KB to 500KB in `src/otel_agent/server.py:383` — change `request_body[:100_000]` to `request_body[:500_000]`
- [X] T002 [P] Increase response body storage limit from 100KB to 500KB in `src/otel_agent/server.py:392` — change `body_str[:100_000]` to `body_str[:500_000]`
- [X] T003 [P] Increase streaming preview limit from 500 to 5000 chars in `src/otel_agent/server.py:361` — change `collected_text[:500]` to `collected_text[:5_000]`

**Checkpoint**: Backend now stores larger bodies. Dashboard can receive up to 500KB payloads.

---

## Phase 3: User Story 1 — Request Body Renders as Formatted LLM Chat (P1) 🎯 MVP

**Goal**: Request bodies render as formatted LLM chat even when truncated, with a clear indicator when data is incomplete.

**Independent Test**: Open dashboard, find a request with a large body (>100KB originally), verify formatted chat renders OR truncation indicator appears.

### Implementation for User Story 1

- [X] T004 [US1] Add `MAX_BODY_LENGTH = 500000` constant at top of `<script>` in `src/otel_agent/dashboard/index.html`
- [X] T005 [US1] Add truncation detection helper `isTruncated(body, maxLen)` in `src/otel_agent/dashboard/index.html` — returns `{ truncated: bool, reason: string }` by checking body length against maxLen and JSON parse success
- [X] T006 [US1] Update `formatBody()` in `src/otel_agent/dashboard/index.html:519` to detect truncated bodies — if `b.length >= MAX_BODY_LENGTH && !isValidJson`, show truncation banner before raw content
- [X] T007 [US1] Add CSS class `.body-truncated` in `src/otel_agent/dashboard/index.html` `<style>` block — yellow/amber warning banner styling
- [X] T008 [US1] Render truncation indicator: `<div class="body-truncated">⚠ Body truncated (original exceeded 500KB)</div>` above the raw content in `formatBody()`

**Checkpoint**: Large request bodies either render as LLM chat or show truncation indicator with raw fallback.

---

## Phase 4: User Story 2 — Streaming Response Shows Reassembled Content (P1)

**Goal**: Streaming responses display reassembled assistant content even with limited preview data.

**Independent Test**: Open dashboard, find a streaming response, verify content is visible or "incomplete preview" indicator is shown.

### Implementation for User Story 2

- [X] T009 [US2] Update `extractStreamingContent()` in `src/otel_agent/dashboard/index.html:404` — when no content deltas found in chunks, return `{ content: '', model, finishReason, incomplete: true }` instead of null
- [X] T010 [US2] Update `renderLlmResponseBody()` in `src/otel_agent/dashboard/index.html:499` — when `data.incomplete` is true, show "Streaming preview may be incomplete — limited chunks captured" note below the metadata badges
- [X] T011 [US2] Add CSS class `.streaming-incomplete` in `src/otel_agent/dashboard/index.html` `<style>` block — muted info note styling

**Checkpoint**: Streaming responses show content when available, or a clear "incomplete preview" note when not.

---

## Phase 5: User Story 3 — Dashboard Handles Large Bodies Without Freezing (P2)

**Goal**: Dashboard remains responsive for 500KB bodies.

**Independent Test**: Open dashboard, click a request with 500KB body, verify page renders within 2 seconds.

### Implementation for User Story 3

- [X] T012 [US3] Verify `highlightJsonString()` in `src/otel_agent/dashboard/index.html:341` handles 500KB JSON without performance issues — test with a large mock object, confirm < 2s render
- [X] T013 [US3] If needed, add `max-height: 600px; overflow-y: auto;` to `.body-raw pre` in `src/otel_agent/dashboard/index.html` `<style>` block to prevent massive pre elements from causing layout thrash

**Checkpoint**: 500KB bodies render smoothly.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [X] T014 Run existing tests: `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/ -v -m "not integration"` — verify zero regressions
- [X] T015 Run quickstart.md validation scenarios 1-5 manually against running proxy
- [X] T016 Verify dashboard HTML file size increase is under 2KB (FR-008): `wc -c src/otel_agent/dashboard/index.html` before and after


---

## Bugfix: FR-004 Partial LLM Rendering from Truncated JSON

**Bugfix**: 2026-07-10 — BUG-002 Updated from bugfix patch

- [X] T017 [US1] Implement partial LLM rendering from truncated request bodies in `src/otel_agent/dashboard/index.html` — in `formatBody()`, after detecting truncation but before returning raw view, attempt to extract complete `{"role": "...", "content": "..."}` message objects from the truncated string using a regex or brace-depth parser. If any complete messages are found, render them as formatted LLM chat (using `renderChatMessage()`) above the raw view with truncation indicator. If no complete messages are found, fall back to current raw view with indicator. This implements FR-004 which was defined in spec.md but never scoped into tasks.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 2 (Foundational)**: No dependencies — start immediately
- **Phase 3 (US1)**: Depends on Phase 2 (limits must be increased first)
- **Phase 4 (US2)**: Depends on Phase 2, independent of US1
- **Phase 5 (US3)**: Depends on Phase 2, independent of US1/US2
- **Phase 6 (Polish)**: Depends on all phases complete

### User Story Dependencies

- **US1 (P1)**: Depends on Phase 2 only
- **US2 (P1)**: Depends on Phase 2 only, can run parallel with US1
- **US3 (P2)**: Depends on Phase 2 only, can run parallel with US1/US2

### Parallel Opportunities

- T001, T002, T003: All parallel (different lines in same file, no conflicts)
- US1 and US2: Can be implemented in parallel (different functions in index.html)
- T014, T015, T016: All parallel (validation tasks)

---

## Implementation Strategy

### MVP First (US1 + US2 Combined)

1. Complete Phase 2: Increase limits (3 constant changes)
2. Complete Phase 3: Truncation detection for request bodies
3. Complete Phase 4: Incomplete streaming preview indicator
4. **STOP and VALIDATE**: Test with data ID 864 and other large requests
5. Commit and deploy

### Why MVP includes both US1 and US2

US1 and US2 are both P1 and address the same root cause (truncation). They share the truncation detection pattern and should be implemented together for consistency.

---

## Notes

- Total tasks: 16 (3 foundational + 5 US1 + 3 US2 + 2 US3 + 3 polish)
- No test tasks — dashboard has no JS test harness (established pattern from 016-llm-body-viewer)
- Estimated effort: ~2 hours total (mostly JS changes in index.html)
- Files modified: 2 (`server.py` constants + `index.html` JS/CSS)