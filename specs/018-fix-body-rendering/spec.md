# Feature Specification: Fix Body Rendering for Truncated Data

**Feature Branch**: `018-fix-body-rendering`

**Created**: 2026-07-10

**Status**: Draft

**Input**: User description: "for this data id :864 the request body and response body not render as expected"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Request Body Renders as Formatted LLM Chat (Priority: P1)

As a developer using the otel-agent dashboard, I want the request body to render as formatted LLM chat messages (with role labels and markdown content) even when the stored body is truncated due to size limits, so that I can still understand what was sent in the request without seeing a "Content is not valid JSON" error.

**Why this priority**: This is the most visible and frustrating issue — users see a raw text dump instead of the formatted chat view they expect. The truncation at 100KB breaks JSON validity for large requests (e.g., long system prompts with tool schemas).

**Independent Test**: Open dashboard, find a request with a large request body (>100KB stored), verify the body is either rendered as formatted LLM chat (if truncation is handled gracefully) or shows a clear "truncated" indicator with whatever partial content is available.

**Acceptance Scenarios**:

1. **Given** a request with a valid OpenAI-format body that fits within the storage limit, **When** the user views the request body, **Then** the body renders as formatted LLM chat with role labels and markdown content.
2. **Given** a request with a truncated request body (originally >100KB, stored body ends mid-JSON), **When** the user views the request body, **Then** the dashboard attempts to parse the truncated JSON and either: (a) renders whatever messages could be extracted, or (b) falls back to raw view with a clear "Body truncated (original size >100KB)" indicator.
3. **Given** a request with a truncated body, **When** the user toggles to raw view, **Then** the raw JSON is shown (even if partial/malformed) with a truncation notice.

---

### User Story 2 - Streaming Response Shows Reassembled Content (Priority: P1)

As a developer, I want the streaming response body to display the reassembled conversation content (the actual assistant message) instead of showing nothing, so that I can see what the LLM actually responded with.

**Why this priority**: Streaming responses currently store only a 500-character preview of concatenated JSON chunks. This is too small to contain meaningful content — often just 1-2 chunks with no assistant message content. The dashboard renders this as empty or near-empty.

**Independent Test**: Open dashboard, find a streaming response, verify the assistant's content is visible and rendered as markdown.

**Acceptance Scenarios**:

1. **Given** a streaming response with a 500-character preview that contains only the first 1-2 chunks (no content delta), **When** the user views the response body, **Then** the dashboard shows a clear indicator that the streaming preview is incomplete, along with any partial content that was captured.
2. **Given** a streaming response with a larger preview that contains actual content deltas, **When** the user views the response body, **Then** the reassembled content is rendered as formatted markdown with model and finish reason metadata.

---

### User Story 3 - Dashboard Handles Large Bodies Without Freezing (Priority: P2)

As a developer, I want the dashboard to handle very large request/response bodies (up to 500KB) without freezing the browser, so that I can inspect requests with large tool schemas or long system prompts.

**Why this priority**: Increasing the storage limit to handle more complete bodies is important, but the dashboard must also handle the increased data gracefully.

**Independent Test**: Open dashboard, click a request with a 500KB body, verify the page remains responsive and the body renders within 2 seconds.

**Acceptance Scenarios**:

1. **Given** a request body of 500KB, **When** the user clicks to view details, **Then** the body renders within 2 seconds without browser freeze.
2. **Given** a response body of 500KB, **When** the user clicks to view details, **Then** the body renders within 2 seconds without browser freeze.

---

### Edge Cases

- What happens when the stored body is exactly at the truncation boundary (e.g., 100,000 bytes) and the JSON is cut mid-string? The dashboard should detect the truncation and show a fallback.
- What happens when the streaming preview contains only SSE preamble (model info, role delta) with no actual content? The dashboard should show "Streaming preview captured early — no content available."
- What happens when the body is valid JSON but the LLM format detection fails on a partial/truncated body? Fall back to raw JSON view with a truncation notice.
- What happens with concurrent requests to the dashboard while the proxy is writing large bodies? No change to existing DuckDB locking behavior.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST store request bodies up to 500KB (increased from 100KB) to preserve JSON validity for most LLM requests with large system prompts or tool schemas.
- **FR-002**: System MUST store streaming response previews up to 5,000 characters (increased from 500) to capture meaningful content deltas and finish reasons.
- **FR-003**: System MUST detect truncated JSON bodies by checking if the stored string is the maximum size and fails JSON parsing, then display a "Body truncated" indicator.
- **FR-004**: System MUST attempt to render truncated request bodies as LLM chat by extracting whatever complete message objects exist in the partial JSON.
- **FR-005**: System MUST display a truncation notice in the raw JSON view when the body is truncated, showing the approximate original size.
- **FR-006**: System MUST render streaming preview content as reassembled markdown when enough chunks are captured (content deltas present).
- **FR-007**: System MUST show an "Incomplete streaming preview" indicator when the preview is too short to contain meaningful content.
- **FR-008**: System MUST NOT increase the dashboard HTML file size by more than 2KB for this feature.
- **FR-009**: System MUST render tool message (role=tool) content as formatted JSON in a `<pre>` code block, not through the markdown renderer, since tool responses contain structured data not prose.
- **FR-010**: System MUST handle tool messages where content is not valid JSON by rendering as monospace preformatted text. System SHOULD truncate long tool content (>$maxToolContentLen) with a collapsible 'show more' toggle to prevent overwhelming the chat view.

### Key Entities

- **Request Body**: The JSON body sent by the client to the proxy, stored in the database. May be truncated if original exceeds the storage limit.
- **Streaming Preview**: A concatenated string of JSON chunks from an SSE stream, stored as `{"streamed": true, "preview": "..."}`. May be truncated if the preview limit is too small.
- **Truncation Indicator**: A visual element shown when the body is detected as truncated, providing context about the original size and content availability.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 95% of LLM-format request bodies (with model + messages fields) render as formatted chat in the dashboard, including those up to 500KB.
- **SC-002**: Streaming responses with content deltas show the reassembled assistant message in formatted markdown (when preview captures ≥3 chunks with content).
- **SC-003**: Truncated bodies display a clear "Body truncated" indicator within 1 second of clicking the request.
- **SC-004**: Dashboard remains responsive (< 2 second render time) for bodies up to 500KB.
- **SC-005**: Zero regressions in existing body rendering for non-truncated, non-LLM-format bodies.

## Assumptions

- The 100KB request body limit was set conservatively and can be increased to 500KB without significant storage impact (DuckDB handles large TEXT columns efficiently).
- The 500-character streaming preview limit was set during initial implementation and can be increased to 5,000 characters without performance concerns.
- Existing tests cover non-truncated body rendering and will catch regressions.
- The dashboard's `highlightJsonString` function already handles large objects without freezing (up to ~500KB).
- The `marked.js` and `DOMPurify` CDN libraries are already loaded and handle large markdown inputs.

**Bugfix**: 2026-07-10 — BUG-002 FR-004 (partial LLM rendering from truncated JSON) identified as unimplemented spec gap. Patch adds task T017.

**Bugfix**: 2026-07-10 — BUG-003 Added FR-009 for tool message JSON rendering. Tool content was routed through renderMarkdown() which mangles JSON.

**Bugfix**: 2026-07-10 — BUG-004 Added FR-010 for non-JSON tool content handling and truncation.
