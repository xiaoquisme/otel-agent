# Tasks: LLM-Aware Body Viewer

**Input**: Design documents from `/specs/016-llm-body-viewer/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Not explicitly requested — verification via existing dashboard tests + manual scenarios.

**Organization**: 3 user stories, all targeting single file `src/otel_agent/dashboard/index.html`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Exact file paths included in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add CDN dependencies and foundational CSS/JS

- [X] T001 Add marked.js and DOMPurify CDN script tags in `src/otel_agent/dashboard/index.html` (after the existing chart.js CDN tag, before the inline `<script>` block)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Format detection and markdown rendering utilities that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [US1] Implement `detectFormat(parsed)` function in `src/otel_agent/dashboard/index.html` — returns `'openai-request'`, `'openai-response'`, `'anthropic-request'`, `'anthropic-response'`, or `null` based on field presence per research.md detection rules

- [X] T003 [US1] Implement `renderMarkdown(text)` function in `src/otel_agent/dashboard/index.html` — wraps `marked.parse(text)` with `DOMPurify.sanitize()` output. Handles null/empty input gracefully.

**Checkpoint**: Format detection and markdown rendering ready — user story implementation can begin

---

## Phase 3: User Story 1 - Render Message Content as Formatted Markdown (Priority: P1) 🎯 MVP

**Goal**: Detect LLM formats and render message content as formatted markdown instead of raw JSON strings.

**Independent Test**: Click a request with OpenAI/Anthropic body → content renders as formatted markdown with no toggle. Non-LLM bodies → unchanged raw JSON.

### Implementation for User Story 1

- [X] T004 [US1] Implement `extractOpenAiRequestContent(parsed)` in `src/otel_agent/dashboard/index.html` — extracts messages array from OpenAI request format, returns `[{role, content}]`

- [X] T005 [US1] Implement `extractOpenAiResponseContent(parsed)` in `src/otel_agent/dashboard/index.html` — extracts message content from `choices[0].message.content`, returns `{content, model, finishReason}`

- [X] T006 [US1] Implement `extractAnthropicRequestContent(parsed)` in `src/otel_agent/dashboard/index.html` — extracts messages array + system field from Anthropic request format, returns `[{role, content}]`

- [X] T007 [US1] Implement `extractAnthropicResponseContent(parsed)` in `src/otel_agent/dashboard/index.html` — extracts text blocks from `content` array, returns `{content, model, stopReason}`

- [X] T008 [US1] Add CSS classes for chat message rendering in `src/otel_agent/dashboard/index.html`: `.chat-message`, `.chat-role`, `.chat-content`, `.chat-content pre` (markdown code blocks), `.chat-content code` (inline code), `.chat-system` (muted style), `.chat-user`, `.chat-assistant`

- [X] T009 [US1] Implement `renderChatMessage(role, content)` in `src/otel_agent/dashboard/index.html` — renders a single message as a chat bubble with role label and markdown-rendered content via `renderMarkdown()`

- [X] T010 [US1] Implement `renderLlmRequestBody(parsed)` in `src/otel_agent/dashboard/index.html` — calls extract functions, renders messages as sequential chat messages using `renderChatMessage()`

- [X] T011 [US1] Implement `renderLlmResponseBody(parsed)` in `src/otel_agent/dashboard/index.html` — calls extract functions, renders response content as markdown with model/finish_reason labels above

- [X] T012 [US1] Update `formatBody(b, context)` in `src/otel_agent/dashboard/index.html` — after JSON parse, call `detectFormat()`. If LLM format detected, render via `renderLlmRequestBody`/`renderLlmResponseBody`. Otherwise fall back to existing `highlightJsonString` raw view.

**Checkpoint**: LLM bodies render as formatted markdown. Non-LLM bodies unchanged. All existing tests pass.

---

## Phase 4: User Story 2 - Display Messages in Conversation Flow (Priority: P2)

**Goal**: Show messages in sequential order with visually distinct role labels (system/user/assistant).

**Independent Test**: Click a request with multi-turn messages → messages appear in order with distinct role styles.

### Implementation for User Story 2

- [X] T013 [US2] Add CSS for role-specific styling in `src/otel_agent/dashboard/index.html`: `.chat-system` (full-width, muted bg `#1c2128`, smaller font), `.chat-user` (slight blue tint bg), `.chat-assistant` (default bg), role label as colored badge above content

- [X] T014 [US2] Update `renderChatMessage(role, content)` in `src/otel_agent/dashboard/index.html` — add role-specific CSS class, render role label as a small badge (e.g., `<span class="chat-role">system</span>`)

- [X] T015 [US2] Handle Anthropic `system` field separately in `renderLlmRequestBody()` in `src/otel_agent/dashboard/index.html` — extract `system` field from parsed body and render as a system message before the messages array

**Checkpoint**: Messages display as a readable conversation with distinct role styles.

---

## Phase 5: User Story 3 - Show Response Choices and Usage Visually (Priority: P3)

**Goal**: Display model name, finish/stop reason, and token usage as prominent metadata.

**Independent Test**: Click a request with complete response → model, finish reason, and tokens displayed prominently.

### Implementation for User Story 3

- [X] T016 [US3] Add CSS for response metadata in `src/otel_agent/dashboard/index.html`: `.response-meta` (flex row with badges), `.response-meta-badge` (pill-shaped badge with icon)

- [X] T017 [US3] Update `renderLlmResponseBody(parsed)` in `src/otel_agent/dashboard/index.html` — add metadata bar above content showing model name badge and finish/stop reason badge

- [X] T018 [US3] Verify existing `renderUsageSummary()` works correctly with both OpenAI (`prompt_tokens/completion_tokens/total_tokens`) and Anthropic (`input_tokens/output_tokens`) formats in `src/otel_agent/dashboard/index.html`

**Checkpoint**: Response metadata prominently displayed. Token usage bar works for both formats.

---

## Phase 6: User Story 1 (continued) - Raw JSON Toggle

**Goal**: "Show Raw" toggle button to switch between LLM view and syntax-highlighted JSON.

**Independent Test**: Click "Show Raw" → switches to JSON view. Click "Show Formatted" → switches back.

### Implementation for Raw Toggle

- [X] T019 [US1] Add CSS for toggle button in `src/otel_agent/dashboard/index.html`: `.body-viewer` (wrapper), `.body-toggle-bar` (toolbar row), `.body-toggle-btn` (active/inactive states)

- [X] T020 [US1] Update `formatBody(b, context)` in `src/otel_agent/dashboard/index.html` — for LLM-format bodies, wrap both views in a `.body-viewer` container with toggle buttons. LLM view shown by default (`display:''`), raw view hidden (`display:none`).

- [X] T021 [US1] Add toggle event delegation in the `detail-body` click handler in `src/otel_agent/dashboard/index.html` — handle `.body-toggle-btn` clicks, swap `display` between `.body-llm-view` and `.body-raw-view`, update active button state.

**Checkpoint**: Toggle works per-request. LLM view default, raw accessible via button.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup, edge cases, verification

- [X] T022 Add markdown content max-height with scroll in `src/otel_agent/dashboard/index.html`: `.chat-content { max-height: 500px; overflow-y: auto; }` to handle large content

- [X] T023 Handle edge cases in `src/otel_agent/dashboard/index.html`: Anthropic content blocks with `type !== "text"` render as placeholder `[Image content]` or `[Tool use: {name}]` based on block type

- [X] T024 Run `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/test_dashboard.py -v` — all tests must pass

- [X] T025 Run quickstart.md scenarios 1-10 manually — confirm all pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 (CDN tags must be present)
- **Phase 3 (US1 - Markdown)**: Depends on Phase 2
- **Phase 4 (US2 - Conversation)**: Depends on Phase 3 (uses renderChatMessage from US1)
- **Phase 5 (US3 - Metadata)**: Depends on Phase 3 (uses renderLlmResponseBody from US1)
- **Phase 6 (Raw Toggle)**: Depends on Phase 3 (modifies formatBody from US1)
- **Phase 7 (Polish)**: Depends on all above

### Parallel Opportunities

- Phase 4 (US2) and Phase 5 (US3) can run in parallel after Phase 3 completes
- T022, T023 can run in parallel (independent edge case fixes)

### Within Each Phase

All tasks in Phases 1-3 are sequential (same file). Phase 4 and 5 tasks can interleave since they modify different functions.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: CDN setup
2. Complete Phase 2: Format detection + markdown utility
3. Complete Phase 3: LLM body rendering
4. **STOP and VALIDATE**: LLM bodies render as markdown, non-LLM unchanged
5. This is already useful — deploy/demo if ready

### Incremental Delivery

1. Phase 1+2 → Foundation ready
2. Phase 3 → MVP! LLM bodies render as markdown
3. Phase 4 → Conversation flow with role labels
4. Phase 5 → Metadata badges
5. Phase 6 → Raw JSON toggle
6. Phase 7 → Edge cases + verification

### Commit Strategy

Single commit after all phases verified:

```
feat: add LLM-aware body viewer to dashboard

- Detect OpenAI/Anthropic request/response formats
- Render message content as formatted markdown (marked.js + DOMPurify)
- Display messages in chat-like conversation flow with role labels
- Show response metadata (model, finish reason, token usage)
- Add "Show Raw" toggle for JSON fallback
- Single-file change to index.html, no backend changes
```
