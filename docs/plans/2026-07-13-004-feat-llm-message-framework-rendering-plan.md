---
title: "LLM Message Framework Rendering - Plan"
type: "feat"
date: "2026-07-13"
topic: "llm-message-framework-rendering"
artifact_contract: "ce-unified-plan/v1"
artifact_readiness: "implementation-ready"
product_contract_source: "ce-brainstorm"
execution: "code"
---

## Goal Capsule

- **Objective:** Replace the current backend-rendered HTML pipeline with @assistant-ui/react on the frontend for LLM message display in the otel-agent dashboard.
- **Product authority:** User confirmed approach, scope, and trade-offs in brainstorm dialogue 2026-07-13.
- **Open blockers:** None.

---

## Product Contract

### Summary

Introduce @assistant-ui/react as the rendering layer for LLM request/response messages in the otel-agent dashboard. Backend returns structured JSON (parsed messages array + metadata); frontend uses the framework's markdown, Shiki code highlighting, and tool call components for ChatGPT/Claude-like static display. Old backend rendering pipeline (render.py, rendered HTML API) is removed.

### Problem Frame

The otel-agent dashboard currently renders LLM request/response bodies through a server-side pipeline: Python's `render.py` detects OpenAI/Anthropic/streaming formats, extracts content from nested JSON, renders markdown to sanitized HTML via the `markdown` + `bleach` libraries, and returns pre-rendered HTML strings to the React frontend. The frontend displays these via `dangerouslySetInnerHTML`.

This architecture has three problems:
- The rendering quality is limited by hand-rolled HTML generation — no syntax-highlighted code blocks, no structured tool call display, no reasoning content visualization
- Format detection and content extraction logic is duplicated between Python (`render.py`) and the conceptual model the frontend needs
- The `dangerouslySetInnerHTML` approach is a security concern and makes the rendering code hard to maintain

### Requirements

**Backend API Contract**

- R1. The backend `/api/requests/{id}` endpoint returns a structured `messages` array instead of pre-rendered HTML strings (`rendered_request` / `rendered_response` fields removed)
- R2. Each message in the array contains `role`, `content`, and optional `tool_calls` fields — matching the structure the frontend framework expects
- R3. The API response includes metadata: `model`, `finish_reason`, `usage` (input/output/total tokens), and `format` tag
- R4. The backend retains format detection logic (OpenAI, Anthropic, streaming) and content extraction, but returns parsed structured data instead of HTML
- R5. The `/api/render/{request_id}` endpoint is removed

**Frontend Rendering**

- R6. The frontend uses @assistant-ui/react components for message display: chat bubbles with role labels, markdown rendering with syntax highlighting (Shiki), and structured tool call visualization
- R7. Markdown content is rendered with full GFM support (tables, fenced code blocks with language detection, strikethrough, task lists)
- R8. Code blocks display with Shiki syntax highlighting and a copy-to-clipboard button
- R9. Tool calls are rendered as expandable blocks showing function name and formatted arguments
- R10. Reasoning content (when present in responses) is displayed in a collapsible section, visually distinct from main content
- R11. The Formatted/Raw toggle is preserved — "Formatted" shows the framework-rendered view, "Raw" shows syntax-highlighted JSON

**Quality and Compatibility**

- R12. The rendering handles all formats currently supported by render.py: OpenAI chat completions, Anthropic messages, and streaming preview objects
- R13. Empty or missing bodies display gracefully (no crashes, clear empty state)
- R14. Large bodies (truncated at storage time) display with a truncation notice

### Scope Boundaries

**Deferred for later:**
- Live streaming / SSE support for real-time chat
- Chat input / composer component
- Interactive conversation features (multi-turn, context management)
- LaTeX / KaTeX math rendering

**Outside this product's identity:**
- Cost tracking, budget management, or alerting (separate feature)
- Prompt management or versioning
- Model benchmarking or evaluation

### Key Decisions

- **@assistant-ui/react as the framework.** Selected over @llamaindex/chat-ui (simpler but fewer primitives) and react-markdown + custom components (lighter but requires building chat bubbles and tool call display from scratch). @assistant-ui/react has the best markdown rendering (Shiki), most mature component primitives, and strongest community (14k+ GitHub stars, MIT license).
- **Backend returns structured JSON, not HTML.** Inverts the current rendering ownership: backend parses and structures, frontend renders. This eliminates format-rendering duplication and lets the frontend use its framework's full capabilities.
- **Remove old rendering pipeline entirely.** render.py, the `/api/render/{id}` endpoint, and the `rendered_request`/`rendered_response` fields are removed. Dashboard is the sole consumer, so backward compatibility is unnecessary.
- **Static display only, no streaming.** The framework's streaming, input, and transport features are unused. Only the rendering layer (markdown, code highlighting, chat bubbles, tool calls) is consumed. Bundle size impact is mitigated by tree-shaking.

### Dependencies / Assumptions

- @assistant-ui/react and its peer dependencies (@assistant-ui/react-markdown, react-markdown, shiki) are compatible with the project's React 19 / Vite 8 / Tailwind 4 stack
- The backend's existing format detection and content extraction logic in `render.py` is reliable and can be adapted to return structured data
- The dashboard's storage layer already provides raw request/response bodies and format tags that the backend can parse into structured messages

### Sources / Research

- @assistant-ui/react: https://github.com/assistant-ui/assistant-ui — MIT, 14k+ stars, Radix-based primitives, Shiki code highlighting, ExternalStoreRuntime for static messages
- @assistant-ui/react-markdown: npm package, uses react-markdown v10 with rehype integration
- Existing architecture pattern: `docs/solutions/architecture-patterns/dashboard-render-delegation-pattern.md` — documents the current render delegation approach being replaced
- Existing render.py: `src/otel_agent/dashboard/render.py` — 571 lines of format detection, content extraction, markdown rendering, and chat bubble generation

---

## Planning Contract

### Key Technical Decisions

- **Structured message extraction lives in a new module** (`src/otel_agent/dashboard/message_parser.py`) that reuses format detection from `render.py` but returns a list of message dicts instead of HTML. This keeps the parsing logic testable and independent of both the HTML renderer and the frontend framework.
- **Backend API returns messages + metadata as a flat JSON response.** The `/api/requests/{id}` response shape becomes `{ id, method, url, status, latency_ms, messages: [...], metadata: { model, finish_reason, usage, format } }`. This matches what @assistant-ui/react's `ExternalStoreRuntime` consumes.
- **Frontend uses @assistant-ui/react's primitive components** (MessagePrimitive, MarkdownText) rather than the full Thread/Composer stack. The static display only needs the rendering layer, not the chat interaction layer.
- **Shiki for code highlighting** (bundled with @assistant-ui/react-markdown) replaces the current `highlight.js`-free approach. Shiki produces highlighted HTML at build time, which is higher quality than runtime highlighting.

### Assumptions

- @assistant-ui/react works with React 19 — the library's peer dependency is `react >=18`, so React 19 should be compatible
- Tree-shaking will eliminate unused streaming/input/transport code from the final bundle
- The existing `render.py` extraction logic (OpenAI, Anthropic, streaming chunk parsing) is correct and can be adapted to return structured data without behavioral changes

---

## Implementation Units

### U1. Structured message parser module

**Goal:** Create a new module that extracts structured message data from raw LLM request/response JSON, reusing format detection logic from render.py.

**Requirements:** R1, R2, R3, R4

**Dependencies:** None

**Files:**
- Create: `src/otel_agent/dashboard/message_parser.py`
- Create: `tests/test_message_parser.py`

**Approach:**
- Extract format detection from `render.py`'s `detect_format()` into a shared utility (or import it directly)
- Create `parse_messages(request_body, response_body, format_tag)` that returns `{ messages: [...], metadata: { model, finish_reason, usage, format } }`
- Each message dict has `role`, `content` (string), and optional `tool_calls` (list of `{ name, arguments }`)
- For request bodies: extract chat messages (OpenAI/Anthropic format) — same extraction logic as `_extract_openai_request` / `_extract_anthropic_request` in render.py but returning raw dicts
- For response bodies: extract the assistant message with content, tool_calls, and reasoning_content — same extraction as `_extract_openai_response` / `_extract_anthropic_response` / `_extract_streaming_content`
- Streaming responses: parse concatenated chunks into a single reconstructed assistant message (reuse `_parse_streaming_chunks` logic)
- Include `model`, `finish_reason`/`stop_reason`, and `usage` in metadata

**Test scenarios:**
- Happy path: OpenAI request with system/user/assistant messages → correct message array
- Happy path: Anthropic request with system block → system message + user/assistant messages
- Happy path: OpenAI response → single assistant message with content
- Happy path: Anthropic response → single assistant message with content
- Happy path: Streaming preview → reconstructed assistant message from concatenated chunks
- Edge case: Request with tool_calls in assistant message → tool_calls extracted
- Edge case: Response with reasoning_content → reasoning included in message
- Edge case: Empty body → empty messages array, null metadata
- Edge case: Invalid JSON → empty messages array
- Edge case: Unknown format → empty messages array, format="unknown"

**Verification:** `uv run pytest tests/test_message_parser.py -v` passes with all scenarios covered.

---

### U2. Backend API contract change

**Goal:** Update the `/api/requests/{id}` endpoint to return structured messages instead of pre-rendered HTML.

**Requirements:** R1, R2, R3, R5

**Dependencies:** U1

**Files:**
- Modify: `src/otel_agent/dashboard/api.py`
- Modify: `src/otel_agent/dashboard/routes.py`
- Modify: `tests/test_dashboard.py`

**Approach:**
- Replace `get_rendered_request()` in `DashboardAPI` with `get_structured_request()` that calls `parse_messages()` from U1
- Update `/api/requests/{id}` route to return the new shape
- Remove the `/api/render/{request_id}` endpoint entirely
- Remove the `rendered_request` / `rendered_response` fields from the response
- The response shape becomes: `{ id, timestamp, method, url, upstream, response_status, latency_ms, request_headers, response_headers, messages: [...], metadata: { model, finish_reason, usage, format } }`

**Test scenarios:**
- Happy path: `/api/requests/{id}` returns `messages` array and `metadata` object
- Happy path: response does NOT contain `rendered_request` or `rendered_response` fields
- Happy path: `/api/render/{id}` returns 404 (endpoint removed)
- Edge case: Request not found → 404
- Edge case: Request with empty body → empty messages array

**Verification:** `uv run pytest tests/test_dashboard.py -v` passes. Old render-related test cases are removed or updated.

---

### U3. Frontend: install @assistant-ui/react and create message display component

**Goal:** Install the framework and build a React component that renders structured LLM messages using @assistant-ui/react primitives.

**Requirements:** R6, R7, R8, R9, R10

**Dependencies:** U2

**Files:**
- Modify: `frontend/package.json` (add dependencies)
- Create: `frontend/src/components/MessageDisplay.tsx`
- Create: `frontend/src/components/ToolCallBlock.tsx`
- Create: `frontend/src/components/ReasoningBlock.tsx`
- Modify: `frontend/src/api/types.ts` (update RequestDetail type)

**Approach:**
- Install `@assistant-ui/react`, `@assistant-ui/react-markdown`, `react-markdown` (peer dep)
- Define TypeScript types matching the new API response shape: `StructuredMessage { role, content, tool_calls? }`, `MessageMetadata { model, finish_reason, usage, format }`
- Create `MessageDisplay` component that:
  - Takes `messages` array and `metadata` as props
  - Renders each message as a styled chat bubble with role label
  - Uses @assistant-ui/react's markdown rendering for content
  - Delegates tool calls to `ToolCallBlock` (expandable, shows name + formatted args)
  - Delegates reasoning content to `ReasoningBlock` (collapsible, visually distinct)
- Style with Tailwind CSS (existing project convention) — dark theme matching the current dashboard

**Test scenarios:**
- Happy path: Component renders messages with correct role labels
- Happy path: Markdown content renders with code highlighting
- Happy path: Tool calls render as expandable blocks
- Happy path: Reasoning content renders in collapsible section
- Edge case: Empty messages array → empty state message
- Edge case: Message with no content → minimal display

**Verification:** `cd frontend && npm run build` succeeds. Component renders correctly in browser with sample data.

---

### U4. Frontend: integrate MessageDisplay into DetailPanel

**Goal:** Replace the current LLMBody-based rendering in DetailPanel with the new MessageDisplay component.

**Requirements:** R11, R12, R13, R14

**Dependencies:** U3

**Files:**
- Modify: `frontend/src/components/DetailPanel.tsx`
- Modify: `frontend/src/components/LLMBody.tsx` (keep for Raw view, remove Formatted path)
- Modify: `frontend/src/api/client.ts` (update fetch to use new API shape)

**Approach:**
- Update `DetailPanel` to fetch the new structured API response
- Replace the two `LLMBody` instances (request body / response body) with `MessageDisplay` components
- Keep the Formatted/Raw toggle: "Formatted" shows `MessageDisplay`, "Raw" shows the existing JSON highlighting (from LLMBody or a simplified raw view)
- Pass `messages` and `metadata` from the API response to `MessageDisplay`
- Handle the "General" section (method, URL, status, latency) — this stays unchanged
- Handle headers sections — these stay unchanged

**Test scenarios:**
- Happy path: Clicking a request shows formatted messages with markdown rendering
- Happy path: Toggle to Raw shows syntax-highlighted JSON
- Happy path: Request and response both render correctly
- Edge case: Request with no body → empty messages, no crash
- Edge case: Very large response → truncation notice displayed

**Verification:** Manual browser test: open dashboard, click a request, verify formatted and raw views work. `cd frontend && npm run build` succeeds.

---

### U5. Remove old rendering pipeline

**Goal:** Clean up deprecated code: render.py HTML generation, old API endpoint, and old tests.

**Requirements:** R5

**Dependencies:** U4

**Files:**
- Modify: `src/otel_agent/dashboard/render.py` (remove HTML generation functions, keep format detection as shared utility)
- Modify: `src/otel_agent/dashboard/routes.py` (remove `/api/render/{id}`)
- Modify: `src/otel_agent/dashboard/api.py` (remove `get_rendered_request`)
- Modify: `tests/test_render.py` (remove HTML rendering tests, keep format detection tests)
- Modify: `tests/test_dashboard.py` (remove render-related test cases)

**Approach:**
- In `render.py`: remove `render_body()`, `render_request_body()`, `render_response_body()`, `_render_chat_message()`, and related HTML generation. Keep `detect_format()`, `_parse_body()`, `_parse_streaming_chunks()` as shared utilities used by `message_parser.py`
- In `routes.py`: remove the `@router.get("/render/{request_id}")` endpoint
- In `api.py`: remove `get_rendered_request()` method
- In `test_render.py`: remove all HTML rendering tests; keep format detection and chunk parsing tests
- In `test_dashboard.py`: remove test cases that assert on `rendered_request` / `rendered_response` fields

**Test scenarios:**
- `uv run pytest tests/test_render.py -v` passes (format detection tests only)
- `uv run pytest tests/test_dashboard.py -v` passes (no references to removed API)
- `uv run pytest -m 'not integration' -v` full suite passes

**Verification:** `uv run pytest -m 'not integration' -v` passes. No references to `rendered_request`, `rendered_response`, or `/api/render/` remain in source code.

---

### U6. Frontend rebuild and integration test

**Goal:** Rebuild the frontend, verify the full integration works end-to-end.

**Requirements:** R6, R7, R8, R9, R10, R11, R12, R13, R14

**Dependencies:** U5

**Files:**
- Modify: `frontend/dist/` (rebuilt output)

**Approach:**
- Run `cd frontend && npm run build` to produce the production bundle
- Start the backend server and verify:
  - Dashboard loads at `http://localhost:8080/`
  - Request list populates
  - Clicking a request shows formatted messages with markdown, code highlighting, tool calls
  - Raw view shows syntax-highlighted JSON
  - Empty/missing bodies display gracefully
- Run full test suite: `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest -m 'not integration' -v`

**Test scenarios:**
- Integration: Dashboard loads and displays request list
- Integration: Clicking request shows formatted LLM messages
- Integration: Formatted/Raw toggle works
- Integration: Code blocks have syntax highlighting
- Integration: Tool calls render as expandable blocks

**Verification:** `cd frontend && npm run build` succeeds. `uv run pytest -m 'not integration' -v` passes. Manual browser verification of rendering quality.

---

## Verification Contract

| Gate | Command | Applies to |
|------|---------|------------|
| Unit tests | `uv run pytest tests/test_message_parser.py -v` | U1 |
| API tests | `uv run pytest tests/test_dashboard.py -v` | U2 |
| Render tests | `uv run pytest tests/test_render.py -v` | U5 |
| Full suite | `PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest -m 'not integration' -v` | All |
| Frontend build | `cd frontend && npm run build` | U3, U4, U6 |
| Manual QA | Browser: dashboard loads, messages render, toggle works | U6 |

---

## Definition of Done

- All unit and API tests pass
- Frontend builds without errors
- Dashboard displays LLM messages with markdown rendering, code highlighting, tool calls, and reasoning
- Formatted/Raw toggle works
- Old render.py HTML generation and `/api/render/{id}` endpoint are removed
- No references to `rendered_request` or `rendered_response` remain in source code
