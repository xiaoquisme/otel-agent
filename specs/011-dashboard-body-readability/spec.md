# Feature Specification: Dashboard Body Readability

**Feature Branch**: `011-dashboard-body-readability`

**Created**: 2026-07-08

**Status**: Draft

**Input**: User description: "看下数据库的数据结构，我想让dashboard 里的request body 和response body 更加的易懂"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pretty-printed JSON with Syntax Highlighting (Priority: P1)

As an API developer debugging LLM requests through the otel-agent dashboard, I want request and response bodies displayed with JSON syntax highlighting (colored keys, strings, numbers, booleans, and nulls) so that I can quickly scan and understand the payload structure without mentally parsing raw text.

**Why this priority**: The current dashboard renders bodies in plain `<pre>` blocks with no visual distinction between JSON element types. Syntax highlighting is the single highest-impact improvement for readability and is the foundation for all other enhancements.

**Independent Test**: Can be fully tested by opening the dashboard, clicking any logged request, and verifying that JSON keys are visually distinct from string values, numbers, booleans, and null literals. Delivers immediate value by making every body inspection easier.

**Acceptance Scenarios**:

1. **Given** a request with a JSON request body, **When** the user clicks the request row in the dashboard, **Then** the request body section displays with distinct colors for JSON keys, string values, number values, boolean values, and null values.
2. **Given** a request with a JSON response body, **When** the user expands the response body section, **Then** the response body displays with the same syntax highlighting as the request body.
3. **Given** a request with a non-JSON body (e.g., plain text or binary), **When** the user views the body, **Then** the body is displayed as-is without syntax highlighting but with appropriate plain-text formatting.
4. **Given** a request with nested JSON objects and arrays, **When** the user views the body, **Then** nested structures are indented consistently with 2-space indentation.

---

### User Story 2 - Collapsible JSON Structure (Priority: P2)

As an API developer inspecting large LLM payloads in the dashboard, I want nested JSON objects and arrays to be collapsible (foldable) so that I can focus on the top-level structure first and expand only the sections I need to inspect.

**Why this priority**: LLM request/response payloads often contain deeply nested structures (e.g., messages arrays with content blocks, tool calls with arguments). Collapsible sections let users navigate large payloads efficiently without scrolling through hundreds of lines.

**Independent Test**: Can be fully tested by loading a request with a large nested body (e.g., a chat completions request with multiple messages) and verifying that clicking a collapse indicator hides/shows the child nodes. Delivers standalone value for payload navigation.

**Acceptance Scenarios**:

1. **Given** a request body with nested JSON objects, **When** the user views the body, **Then** each object and array has a clickable collapse/expand indicator (e.g., a triangle icon or +/- button).
2. **Given** a collapsed JSON node, **When** the user clicks the expand indicator, **Then** the child content becomes visible and the indicator changes to indicate "expanded" state.
3. **Given** an expanded JSON node, **When** the user clicks the collapse indicator, **Then** the child content is hidden and only a summary is shown (e.g., `{...}` or `[3 items]`).
4. **Given** a body larger than 50 lines, **When** the body section is displayed, **Then** top-level objects and arrays start in a collapsed state to reduce initial scroll burden.

---

### User Story 3 - LLM Payload Semantic Awareness (Priority: P3)

As an API developer debugging LLM API calls through the dashboard, I want the body viewer to recognize and annotate common LLM API fields (like "model", "messages", "content", "role", "temperature", "stream") with semantic labels so that I can understand the payload's intent at a glance without deep-diving into the raw JSON.

**Why this priority**: The dashboard specifically monitors LLM API traffic. Semantic awareness transforms raw JSON inspection into meaningful API debugging. This is a differentiating feature that makes otel-agent uniquely useful for LLM developers.

**Independent Test**: Can be fully tested by sending a known OpenAI chat completions request through the proxy and verifying that key fields like "model", "messages", and "stream" are visually annotated in the dashboard. Delivers targeted value for LLM-specific debugging.

**Acceptance Scenarios**:

1. **Given** an OpenAI chat completions request body, **When** the user views the body, **Then** fields like "model", "messages", "stream", "temperature", and "max_tokens" are displayed with inline annotations indicating their purpose (e.g., next to "model": the value is highlighted or a tooltip shows "Target model").
2. **Given** a request body with a "messages" array, **When** the user views the body, **Then** each message object is visually grouped with its "role" (system/user/assistant) shown as a badge or label.
3. **Given** a response body with "choices" and "usage" fields, **When** the user views the body, **Then** token usage information (prompt_tokens, completion_tokens, total_tokens) is displayed as a compact summary line near the top of the response section.

---

### Edge Cases

- What happens when the body is empty (e.g., GET requests with no payload)? The body section displays "(empty)" — no change from current behavior.
- What happens when the body is extremely large (near the 100KB storage limit)? The body section renders but performance remains smooth — consider virtualizing or truncating with a "show all" button for bodies exceeding 10,000 characters.
- What happens when the body is not valid JSON (e.g., raw text, HTML, binary)? The body section displays the raw content without syntax highlighting, with a note indicating the content type.
- What happens when the body contains unicode/emoji or escaped characters? These render correctly without breaking syntax highlighting.
- What happens when streaming response bodies are displayed (currently stored as `{"streamed": true, "preview": "..."}`)? The JSON structure is highlighted, and the "preview" field value is rendered as a readable text block.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display request and response bodies with JSON syntax highlighting that visually distinguishes keys, string values, numeric values, boolean values, and null literals using distinct colors.
- **FR-002**: System MUST render JSON with consistent 2-space indentation for nested structures.
- **FR-003**: System MUST provide collapsible (foldable) sections for each JSON object and array in the body viewer.
- **FR-004**: System MUST collapse top-level nested structures by default when the body exceeds 50 lines to reduce initial scroll burden.
- **FR-005**: System MUST display a summary indicator for collapsed nodes (e.g., showing the count of child items or a compact preview).
- **FR-006**: System MUST preserve a "raw view" toggle that allows users to see the original unformatted body text.
- **FR-007**: System MUST visually annotate common LLM API fields (model, messages, content, role, stream, temperature, max_tokens, usage) with semantic labels or badges.
- **FR-008**: System MUST handle non-JSON bodies gracefully — display as plain text with no highlighting.
- **FR-009**: System MUST handle bodies up to 100KB without rendering performance degradation.
- **FR-010**: System MUST maintain the existing copy-as-curl functionality alongside the new body display.

### Key Entities

- **Request Body**: The original request payload sent by the client to the otel-agent proxy, stored as a JSON string in the `requests` table. Contains OpenAI or Anthropic compatible chat completion parameters.
- **Response Body**: The upstream provider's response payload (or converted format), stored as a JSON string. For streaming requests, stored as a summary object with a text preview.
- **Body Viewer**: The dashboard UI component that renders request/response bodies with syntax highlighting, collapsible structure, and semantic annotations.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can identify the model name, message count, and streaming status of a request within 2 seconds of opening the detail panel (currently requires reading through raw JSON).
- **SC-002**: Users can navigate a large nested payload (>100 lines) by collapsing irrelevant sections, reducing the visible content to the specific section of interest within 3 clicks.
- **SC-003**: Non-technical stakeholders viewing the dashboard can understand the basic intent of an LLM request (which model, how many messages, streaming or not) without developer assistance.
- **SC-004**: Body rendering completes within 500ms for payloads up to 100KB with no visible UI lag or jank.

## Assumptions

- The existing SQLite database schema (TEXT fields for request_body and response_body) is sufficient — no schema changes needed since the bodies are already stored as JSON strings.
- The dashboard currently loads bodies via the `/api/requests/:id` detail endpoint which returns the full row including request_body and response_body fields.
- The existing dark theme color scheme should be extended with syntax highlighting colors that are consistent with the current palette.
- The dashboard is a single-page application using vanilla JavaScript (no framework), so any syntax highlighting or collapsible tree implementation must work without external dependencies beyond the already-loaded Chart.js.
- Users viewing the dashboard are primarily API developers who are familiar with JSON structure and LLM API conventions.
- Collapsing behavior is a UI-only concern; no backend API changes are required.
