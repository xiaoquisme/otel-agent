# Feature Specification: Streaming Telemetry Logging Bug

**Feature Branch**: `019-streaming-telemetry-bug`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Bug: streaming responses are not being recorded to telemetry. When `response streamed: true`, subsequent responses are not recorded."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Streaming Requests Logged to Dashboard (Priority: P1)

As a developer using the otel-agent gateway, I want ALL streaming requests (SSE responses) to be recorded to the telemetry database so that they appear in the dashboard alongside non-streaming requests.

**Why this priority**: This is a core telemetry requirement — the gateway's primary value is logging all LLM API calls. If streaming requests are missing from the dashboard, the tool loses its core functionality for a significant portion of API traffic (most LLM calls are streaming).

**Independent Test**: Send a streaming request (`"stream": true`), then check the dashboard — the request should appear with status, latency, and a preview of the streamed response.

**Acceptance Scenarios**:

1. **Given** the gateway is running, **When** a streaming request is sent and completes successfully, **Then** the request appears in the dashboard with `{"streamed": true, "preview": "..."}` in the response body.
2. **Given** the gateway is running, **When** a streaming request is sent and the client disconnects mid-stream, **Then** the partial request is still logged to the dashboard (with whatever chunks were collected before disconnect).
3. **Given** the gateway is running, **When** a streaming request is followed by a non-streaming request, **Then** both requests appear in the dashboard in correct order.

---

### User Story 2 - Non-Streaming Requests Still Work After Streaming (Priority: P1)

As a developer, I want non-streaming requests to continue being logged normally even after streaming requests have been processed, ensuring no cross-contamination between request types.

**Why this priority**: If streaming breaks non-streaming logging, the entire telemetry system is unreliable.

**Independent Test**: Send a mix of streaming and non-streaming requests, verify all are logged.

**Acceptance Scenarios**:

1. **Given** the gateway has processed streaming requests, **When** a non-streaming request is sent, **Then** it is logged to the dashboard with the full response body.
2. **Given** the gateway has processed multiple streaming requests, **When** a non-streaming request is sent, **Then** the DuckDB connection is healthy and the INSERT succeeds.

---

### Edge Cases

- What happens when the client disconnects before the first chunk is sent?
- What happens when the upstream provider returns an error during streaming?
- What happens when the gateway shuts down while a stream is in progress?
- What happens when two streaming requests are concurrent?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST log every streaming request to the telemetry database, including partial streams where the client disconnects early.
- **FR-002**: System MUST log the request even if the streaming generator is abandoned (e.g., `StreamingResponse` garbage-collected before generator completes).
- **FR-003**: System MUST NOT allow streaming request logging failures to affect subsequent request logging.
- **FR-004**: System MUST store streaming response bodies in the format `{"streamed": true, "preview": "<concatenated chunks>"}` with a preview limit of 5,000 characters.
- **FR-005**: System MUST log the upstream response headers for streaming requests (to capture provider-specific metadata like request IDs).

### Key Entities

- **Streaming Request**: An LLM API request where `"stream": true` is set, resulting in an SSE (Server-Sent Events) response.
- **Telemetry Record**: A row in the `requests` table capturing method, URL, headers, bodies, status, and latency for each request.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of streaming requests that complete successfully are logged to the dashboard.
- **SC-002**: Streaming requests that fail or are interrupted are still logged (with partial data).
- **SC-003**: Non-streaming requests after streaming requests are logged without issue.
- **SC-004**: Dashboard correctly renders streaming response bodies with the `{"streamed": true, "preview": "..."}` format.

## Assumptions

- The DuckDB storage backend is functional and not locked by another process.
- The bug is in the telemetry logging path for streaming responses, not in the streaming proxy logic itself.
- The `_log_telemetry()` call inside `stream_generator()` may not execute if the generator is abandoned before completion.
- The `StreamingResponse` lifecycle in FastAPI may not guarantee generator completion on client disconnect.
