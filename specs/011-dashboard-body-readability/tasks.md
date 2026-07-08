# Tasks: Dashboard Body Readability

**Input**: Design documents from `/specs/011-dashboard-body-readability/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/body-viewer-ui.md, quickstart.md

**Tests**: Not included — spec uses manual browser validation via quickstart.md scenarios. No automated JS test framework in project.

**Organization**: Tasks grouped by user story. All changes in single file: `src/otel_agent/dashboard/index.html`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Single target file: `src/otel_agent/dashboard/index.html`

---

## Phase 1: Setup (CSS Foundation)

**Purpose**: Add all JSON viewer CSS styles to the `<style>` block in index.html. No behavioral changes — just style classes that will be used by later tasks.

- [x] T001 [US1] Add JSON syntax highlighting CSS classes to `src/otel_agent/dashboard/index.html` <style> block: `.json-key` (color: #79c0ff), `.json-string` (color: #a5d6ff), `.json-number` (color: #d2a8ff), `.json-boolean` (color: #58a6ff), `.json-null` (color: #8b949e, font-style: italic), `.json-toggle` (color: #8b949e, cursor: pointer, user-select: none), `.json-badge` (background: #21262d, border: 1px solid #30363d, border-radius: 4px, padding: 1px 6px, font-size: 11px, color: #8b949e, margin-left: 6px), `.json-children` (padding-left: 20px, border-left: 1px solid #21262d), `.json-summary` (color: #8b949e, font-size: 12px), `.body-viewer-toolbar` (display: flex, gap: 4px, margin-bottom: 8px), `.body-toggle` (background: #21262d, border: 1px solid #30363d, color: #8b949e, padding: 2px 8px, border-radius: 4px, cursor: pointer, font-size: 12px), `.body-toggle.active` (background: #30363d, color: #e1e4e8), `.body-empty` (color: #8b949e, font-style: italic), `.json-node` (line-height: 1.6)
- [x] T002 [US1] Add badge-specific CSS variants to `src/otel_agent/dashboard/index.html` <style> block: `.json-badge-model` (border-color: #58a6ff), `.json-badge-messages` (border-color: #a371f7), `.json-badge-stream` (border-color: #3fb950), `.json-badge-usage` (border-color: #d29922), `.json-badge-tool` (border-color: #f0883e), `.json-badge-system` (border-color: #8b949e)

**Checkpoint**: CSS classes exist in the file but are unused. No visual change yet.

---

## Phase 2: Foundational (Core JSON Utilities)

**Purpose**: Add core JavaScript utility functions that ALL user stories depend on. These are pure functions that parse, highlight, and render JSON — no integration with the detail panel yet.

- [x] T003 [US1] Add `escapeHtml(s)` utility function to the `<script>` block in `src/otel_agent/dashboard/index.html`. Function escapes `&`, `<`, `>`, `"` characters for safe HTML insertion.
- [x] T004 [US1] Add `highlightJsonString(json, indent)` function to `<script>` block. This is a recursive function that walks a parsed JSON value and returns an HTML string with syntax-highlighted `<span>` elements. Handles objects (with key highlighting), arrays, strings, numbers, booleans, and null. Uses 2-space indentation. Calls `escapeHtml()` for string values.
- [x] T005 [P] [US1] Add `countJsonLines(json)` utility function to `<script>` block. Counts lines in the pretty-printed representation of a JSON value. Used for auto-collapse threshold (50 lines).

**Checkpoint**: Utility functions exist but are not yet called. Can be tested in browser console.

---

## Phase 3: User Story 1 - Syntax Highlighting (Priority: P1) 🎯 MVP

**Goal**: Request and response bodies display with colored JSON syntax — keys, strings, numbers, booleans, and nulls each have distinct colors.

**Independent Test**: Open dashboard → click any request → body sections show colored JSON. Non-JSON bodies show plain text. Empty bodies show "(empty)".

### Implementation for User Story 1

- [x] T006 [US1] Replace the `formatBody(b)` function in `src/otel_agent/dashboard/index.html` with a version that: (1) returns `(empty)` if body is falsy, (2) tries `JSON.parse(b)` — if valid, calls `highlightJsonString(JSON.parse(b), 0)` and wraps result in a `<pre>` tag, (3) on parse failure, returns escaped plain text in `<pre>` with a note "Content is not valid JSON".
- [x] T007 [US1] Update the `showDetail(id)` function in `src/otel_agent/dashboard/index.html` to replace the inline `${formatBody(r.request_body)}` and `${formatBody(r.response_body)}` calls so they use the updated `formatBody()` function (this should already work if T006 is correct — verify the detail panel renders highlighted JSON).
- [x] T008 [US1] Verify in browser: send a POST /v1/chat/completions request through the proxy, open dashboard, click the request, confirm keys are blue (#79c0ff), strings are light blue (#a5d6ff), numbers are purple (#d2a8ff), booleans are blue (#58a6ff), nulls are gray italic (#8b949e). Verify non-JSON body shows plain text. Verify empty body shows "(empty)".

**Checkpoint**: MVP complete — bodies are syntax-highlighted. User Story 1 is independently functional.

---

## Phase 4: User Story 2 - Collapsible Tree (Priority: P2)

**Goal**: Nested JSON objects and arrays are collapsible/expandable. Large bodies auto-collapse deep nodes.

**Independent Test**: Open a request with nested JSON → click toggle icons to collapse/expand. Large body (>50 lines) shows deep nodes collapsed by default.

### Implementation for User Story 2

- [x] T009 [US2] Add `renderJsonNode(value, key, depth, autoCollapse)` function to `<script>` block in `src/otel_agent/dashboard/index.html`. This is a recursive function that returns a DOM element (`<div class="json-node">`). For primitives: renders syntax-highlighted span. For objects/arrays: renders a toggle icon (▶/▼), a header with key (if present), opening brace, a `<div class="json-children">` containing recursive child nodes, and a closing brace. The toggle icon triggers collapse/expand of children div. Auto-collapse nodes at depth ≥ 1 when `autoCollapse` is true.
- [x] T010 [US2] Add `toggleJsonNode(nodeElement)` function to `<script>` block. Finds the `.json-children` div within the node, toggles its `display` between `none` and `block`. Updates the toggle icon between ▶ and ▼. Updates or creates a `.json-summary` span showing item count when collapsed.
- [x] T011 [US2] Add event delegation click handler on the detail panel body sections. Attach a single `click` listener to the `#detail-body` element that: (1) checks if click target has class `.json-toggle` or is inside a `.json-toggle` → calls `toggleJsonNode()` on the closest `.json-node` ancestor, (2) checks if click target has class `.body-toggle` → switches between tree and raw view.
- [x] T012 [US2] Replace the `formatBody(b)` function (from T006) with a version that returns a full body viewer DOM string: a `<div class="body-viewer">` containing a toolbar with Tree/Raw toggle buttons, a tree-view container with `renderJsonNode()` output (autoCollapse = true if > 50 lines), and a hidden raw-view container with `<pre>` of pretty-printed JSON. Empty body returns `.body-empty`. Non-JSON returns `.body-raw` with plain text.
- [x] T013 [US2] Verify in browser: open a request with nested JSON, confirm toggle icons appear on objects/arrays, clicking collapses/expands, collapsed nodes show summary (e.g., `{3 items}` or `[4 items]`). Send a large-body request (>50 lines), confirm deep nodes start collapsed. Toggle between Tree and Raw views.

**Checkpoint**: User Stories 1 AND 2 are both functional. Bodies have syntax highlighting + collapsible tree.

---

## Phase 5: User Story 3 - LLM Semantic Annotations (Priority: P3)

**Goal**: Common LLM API fields are annotated with badges. Usage data shown as compact summary.

**Independent Test**: Send a chat completions request → body shows badges on model, messages, stream, temperature, max_tokens. Response shows usage summary.

### Implementation for User Story 3

- [x] T014 [US3] Add `LLM_REQUEST_ANNOTATIONS` constant map to `<script>` block in `src/otel_agent/dashboard/index.html`. Maps field names to badge configs: `model` → {badge: "🎯 Target model", cssClass: "json-badge-model"}, `messages` → {badge: "💬 Messages", cssClass: "json-badge-messages", countField: true}, `stream` → {badge: "⚡ Streaming", cssClass: "json-badge-stream", valueMap: {true: "⚡ Streaming", false: "⏹ Sync"}}, `temperature` → {badge: "🌡️ Temperature", cssClass: "json-badge-model"}, `max_tokens` → {badge: "📏 Max tokens", cssClass: "json-badge-model"}, `max_completion_tokens` → {badge: "📏 Max completion tokens", cssClass: "json-badge-model"}, `tools` → {badge: "🔧 Tools", cssClass: "json-badge-tool", countField: true}, `tool_choice` → {badge: "🔧 Tool choice", cssClass: "json-badge-tool"}, `system` → {badge: "📋 System prompt", cssClass: "json-badge-system"}
- [x] T015 [P] [US3] Add `LLM_RESPONSE_ANNOTATIONS` constant map to `<script>` block. Maps field names to badge configs: `id` → {badge: "🏷️ ID"}, `model` → {badge: "🏷️ Model used"}, `choices` → {badge: "📝 Choices", cssClass: "json-badge-messages", countField: true}, `usage` → {badge: "📊 Usage", cssClass: "json-badge-usage"}, `stop_reason` / `finish_reason` → {badge: "⏹ Stop reason"}
- [x] T016 [US3] Add `getAnnotation(fieldName, context, value)` function to `<script>` block. Takes field name, context ("request"/"response"), and value. Looks up in the appropriate annotation map. Returns null if no annotation, or object with badge text and CSS class. For `countField` annotations, appends count (e.g., "💬 Messages (5)"). For `valueMap` annotations, maps value to display text.
- [x] T017 [US3] Update `renderJsonNode()` (from T009) to accept a `context` parameter ("request" or "response"). When rendering an object key, call `getAnnotation(key, context, value)`. If annotation found, append a `<span class="json-badge {cssClass}">{badge text}</span>` after the key's closing quote.
- [x] T018 [US3] Add `renderUsageSummary(usage)` function to `<script>` block. Takes a usage object and returns a compact HTML string: `Tokens: {input_tokens} in / {output_tokens} out` (or `prompt_tokens / completion_tokens / total_tokens` for OpenAI format). Renders as a small bar above the tree view.
- [x] T019 [US3] Update `showDetail(id)` in `src/otel_agent/dashboard/index.html` to pass "request" context when rendering request_body and "response" context when rendering response_body. For response bodies: if `usage` field exists in the parsed JSON, prepend the usage summary bar above the tree.
- [x] T020 [US3] Verify in browser: send a chat completions request with model, messages, stream, temperature, max_tokens → confirm badges appear on each field. Send a request → response shows usage summary bar. Verify Anthropic-format requests also show appropriate badges (system, max_tokens required).

**Checkpoint**: All 3 user stories functional. Syntax highlighting + collapsible tree + semantic annotations.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, performance, and final validation.

- [x] T021 Test edge cases per quickstart.md scenarios 6-8: non-JSON body renders without crash, empty body shows "(empty)", copy-as-curl still works with new body viewer.
- [x] T022 Performance test: send a large request body (>10KB, >100 lines), verify auto-collapse kicks in, UI remains responsive, no jank on expand/collapse.
- [x] T023 Verify keyboard behavior: Escape key still closes the detail panel (existing handler in index.html). Verify no keyboard conflicts with new toggle functionality.
- [x] T024 Run full quickstart.md validation (8 scenarios) and mark all checkboxes pass/fail.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup CSS)**: No dependencies — can start immediately
- **Phase 2 (Foundational utilities)**: Depends on Phase 1 (CSS classes must exist)
- **Phase 3 (US1 — Syntax Highlighting)**: Depends on Phase 2 (uses `highlightJsonString`)
- **Phase 4 (US2 — Collapsible Tree)**: Depends on Phase 2 (uses `renderJsonNode`, `escapeHtml`). Can start after Phase 2 independently of Phase 3.
- **Phase 5 (US3 — Semantic Annotations)**: Depends on Phase 4 (updates `renderJsonNode` with context param) and Phase 2
- **Phase 6 (Polish)**: Depends on all previous phases

### User Story Dependencies

- **User Story 1 (P1)**: Depends on Phase 2. No dependencies on other stories.
- **User Story 2 (P2)**: Depends on Phase 2. Replaces US1's `formatBody` but doesn't depend on US1's `highlightJsonString` — it reuses it.
- **User Story 3 (P3)**: Depends on US2's `renderJsonNode` (adds context param + annotation logic). Should be implemented after US2.

### Parallel Opportunities

- Phase 1 (T001, T002): Can run in parallel — both add CSS classes
- Phase 2 (T003, T004, T005): T003 and T005 can run in parallel; T004 depends on T003
- US1 and US2 share the same `formatBody` function — cannot be developed truly in parallel, but US1 can be validated before US2 starts

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Add CSS classes
2. Complete Phase 2: Add utility functions
3. Complete Phase 3: Syntax highlighting in body viewer
4. **STOP and VALIDATE**: Bodies are colored. Non-JSON works. Empty works.
5. Deploy/demo if ready

### Incremental Delivery

1. Phase 1 + Phase 2 → Foundation ready
2. Phase 3 (US1) → Syntax highlighting MVP! Deploy/demo
3. Phase 4 (US2) → Collapsible tree added. Deploy/demo
4. Phase 5 (US3) → Semantic annotations. Deploy/demo
5. Phase 6 → Polish and validate all edge cases

---

## Notes

- All changes in single file: `src/otel_agent/dashboard/index.html`
- No backend API changes needed — `/api/requests/:id` already returns full body
- No npm/build step — everything is inline CSS and vanilla JS
- Event delegation pattern for click handlers (one listener on `#detail-body`)
- Color palette tested for WCAG AA contrast on #0d1117 background
- Auto-collapse threshold: 50 lines (configurable constant)
- Existing `copyCurl()` function is unaffected — operates on raw request data, not rendered DOM
