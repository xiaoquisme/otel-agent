# Feature Specification: LLM-Aware Body Viewer

**Feature Branch**: `016-llm-body-viewer`

**Created**: 2026-07-09

**Status**: Draft

**Input**: User description: "request body 和 response body 都是按照 openai/anthropic 的格式，在 dashboard 渲染数据的时候，看有没有开源的框架可以使用，将这些数据变得更加易读"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Render Message Content as Formatted Markdown (Priority: P1)

As a developer using the otel-agent dashboard, I want the message content inside request and response bodies to be rendered as formatted markdown (bold, code blocks, lists, etc.) instead of raw escaped JSON text, so that I can quickly read and understand the actual conversation content without squinting at JSON strings.

**Why this priority**: This is the highest-value improvement — LLM outputs are markdown, but currently they're buried inside JSON as escaped strings. Seeing formatted text immediately makes the dashboard far more useful for debugging and monitoring.

**Independent Test**: Open dashboard, click a request where the response body contains a chat completion with markdown content (e.g., code blocks, bullet points), verify the content renders as formatted text rather than escaped JSON strings.

**Acceptance Scenarios**:

1. **Given** a request with an OpenAI chat completion response body containing markdown content in `choices[0].message.content`, **When** the user views the response body, **Then** the message content is rendered as formatted markdown (headings, code blocks, lists, bold/italic are visually distinct).
2. **Given** a request with an Anthropic messages response body containing content blocks, **When** the user views the response body, **Then** text content blocks are rendered as formatted markdown.
3. **Given** a request body with a `messages` array (OpenAI or Anthropic format), **When** the user views the request body, **Then** each message's `content` field is rendered as formatted markdown, with the `role` label (system/user/assistant) visually distinct.
4. **Given** a body that is not OpenAI or Anthropic format, **When** the user views it, **Then** it falls back to syntax-highlighted JSON (current behavior preserved).

---

### User Story 2 - Display Messages in Conversation Flow (Priority: P2)

As a developer, I want the messages array to be displayed as a sequential conversation (system → user → assistant → user → ...) with role labels and timestamps, so that I can follow the conversation flow without mentally parsing JSON array indices.

**Why this priority**: Understanding the conversation flow is the second most valuable improvement after readable content. It helps developers see the full context of an API call at a glance.

**Independent Test**: Open dashboard, click a request with multi-turn messages, verify messages appear in order with role labels (system, user, assistant) visually distinguished.

**Acceptance Scenarios**:

1. **Given** a request with 5 messages in the `messages` array, **When** the user views the request body, **Then** all 5 messages are displayed sequentially with role labels.
2. **Given** a message with role "system", **When** rendered, **Then** it has a distinct visual style (e.g., muted color, different background) from user/assistant messages.
3. **Given** a message with role "user", **When** rendered, **Then** it is visually distinct from assistant messages (e.g., different alignment or background color).
4. **Given** a message with role "assistant", **When** rendered, **Then** it is visually distinct and its content is rendered as markdown.

---

### User Story 3 - Show Response Choices and Usage Visually (Priority: P3)

As a developer, I want the response body to visually highlight key fields like model, finish reason, and token usage, so that I can quickly assess the response quality and cost without reading the entire JSON.

**Why this priority**: Token usage and model info are already partially shown (usage summary bar), but finish reason and other metadata could be more prominent.

**Independent Test**: Open dashboard, click a request with a complete response, verify model name, finish reason, and token counts are displayed as prominent labels above the content.

**Acceptance Scenarios**:

1. **Given** a response body with `model` field, **When** the user views the response, **Then** the model name is displayed as a prominent label.
2. **Given** a response body with `choices[0].finish_reason` (or Anthropic `stop_reason`), **When** the user views the response, **Then** the stop reason is displayed (e.g., "stop", "length", "tool_calls").
3. **Given** a response body with token usage data, **When** the user views the response, **Then** prompt/completion/total tokens are displayed in a compact summary bar (existing behavior, but ensure it works with both OpenAI and Anthropic formats).

---

### Edge Cases

- What happens when message content is an array of content blocks (Anthropic format: `[{type: "text", text: "..."}, {type: "image", ...}]`)? Only text blocks should be rendered as markdown; non-text blocks should show a placeholder.
- What happens when content contains HTML/XSS? Markdown rendering MUST be sanitized to prevent script injection.
- What happens when content is very long (>10,000 characters)? The rendered content should be scrollable within its container.
- What happens when the JSON body is malformed? Fall back to raw text display.
- What happens with streaming response chunks (delta format)? Show delta content as-is (no accumulation).
- When the user toggles to raw view, the full original JSON is shown with syntax highlighting (preserving the existing `highlightJsonString` rendering).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST detect OpenAI and Anthropic request/response body formats by checking for characteristic fields (`messages` array for requests, `choices` or `content` array for responses).
- **FR-002**: System MUST render message `content` fields as formatted markdown using a lightweight open-source markdown rendering library loaded via CDN.
- **FR-003**: System MUST sanitize all rendered markdown HTML to prevent XSS attacks (script injection, event handlers, etc.).
- **FR-004**: System MUST display request messages in sequential order with visually distinct role labels (system, user, assistant).
- **FR-005**: System MUST visually distinguish different message roles through color, background, or alignment differences.
- **FR-006**: System MUST render Anthropic content block arrays by extracting and rendering only text-type blocks as markdown.
- **FR-007**: System MUST display the LLM-aware formatted view by default when an OpenAI or Anthropic body is detected. A "Show Raw" toggle button MUST be provided in the body viewer toolbar, allowing users to switch to the existing syntax-highlighted JSON view at any time. For non-LLM-format bodies, the raw JSON view is shown directly (no toggle needed).
- **FR-007a**: System MUST persist the toggle state per body viewer — switching to raw for one request does not affect other requests.
- **FR-008**: System MUST display response metadata (model name, finish/stop reason) as prominent labels.
- **FR-009**: System MUST preserve the existing token usage summary bar for both OpenAI and Anthropic response formats.
- **FR-010**: System MUST handle large content (10,000+ characters) without freezing the browser — rendered content must be scrollable.
- **FR-011**: System MUST NOT introduce new backend dependencies — all rendering is client-side in the dashboard HTML.

### Key Entities

- **LLM Request Body**: OpenAI format (`{model, messages, stream, temperature, tools, ...}`) or Anthropic format (`{model, messages, max_tokens, stream, ...}`)
- **LLM Response Body**: OpenAI format (`{id, model, choices: [{message, finish_reason}], usage}`) or Anthropic format (`{id, type, content: [{type, text}], usage, stop_reason}`)
- **Message**: `{role: "system"|"user"|"assistant", content: string | content_block_array}`
- **Content Block** (Anthropic): `{type: "text", text: string}` or `{type: "image", ...}`

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: LLM message content renders as formatted markdown (headings, code blocks, lists, bold are visually distinct) within 500ms of clicking a request.
- **SC-002**: Developers can read a multi-turn conversation in the request body in under 10 seconds (vs. 30+ seconds parsing raw JSON).
- **SC-003**: 100% of existing dashboard functionality is preserved — no regressions in non-LLM body display, empty bodies, or error states.
- **SC-004**: Zero XSS vulnerabilities — markdown rendering uses sanitized output.
- **SC-005**: The dashboard HTML file size increase is under 50KB (markdown library via CDN does not count toward this limit).

## Assumptions

- The markdown rendering library will be loaded via CDN (e.g., `marked.js` ~25KB) — consistent with the existing pattern of loading `chart.js` via CDN.
- HTML sanitization will use DOMPurify (CDN, ~7KB) or a built-in sanitization approach to prevent XSS.
- The existing `highlightJsonString` function will be retained for non-LLM bodies and raw JSON view.
- Message content that is not valid markdown will still render as readable text (markdown renderers handle plain text gracefully).
- The feature targets the single-file dashboard (`index.html`) — no backend changes needed. File will grow from ~452 to ~800 lines, which is acceptable for a debugging tool dashboard. No architecture split planned at this stage.
- OpenAI format is detected by presence of `messages` array + `model` field; Anthropic format by `messages` array + `max_tokens` or `content` array in response.
## Clarifications

### Session 2026-07-09

- Q: How should users switch between LLM-aware view and raw JSON for LLM-format bodies? → A: LLM view shown by default with a "Show Raw" toggle button to switch to syntax-highlighted JSON.
- Q: Is the single-file architecture still suitable after adding LLM viewer? → A: Yes, keep single file. ~800 lines is acceptable for a debugging tool dashboard.
