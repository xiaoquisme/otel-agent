# Feature Specification: Log Request Bodies and Response Headers to Database

**Feature Branch**: `010-log-request-body`

**Created**: 2026-07-08

**Status**: Draft

**Input**: User description: "request body not logged to the db"

## Clarifications

### Session 2026-07-08

- Q: Should response headers also be logged? → A: Yes, expand scope to fix both request body AND response header logging in this feature.
- Q: Should sensitive headers be redacted before storage? → A: Yes, redact known sensitive headers (authorization, x-api-key, etc.) by storing `[REDACTED]` as the value.

## User Scenarios & Testing

### User Story 1 - Complete Telemetry Data Persisted in DB (Priority: P1)

As a developer using the otel-agent gateway, I want incoming request bodies and upstream response headers to be stored in the SQLite telemetry database alongside the existing metadata (timestamp, method, URL, status, latency, response body), so that I can inspect and debug the full request lifecycle when troubleshooting LLM API issues.

**Why this priority**: The `request_body` column already exists in the database schema but is always written as an empty string. The `response_headers` column is similarly always written as `{}`. These are the two core data gaps — populating them is the primary fix.

**Independent Test**: Can be verified by sending a request through the gateway and confirming the stored row in the SQLite database contains the full request body (not empty) and the upstream response headers (not `{}`). Delivers immediate debugging value.

**Acceptance Scenarios**:

1. **Given** the gateway is running, **When** a non-streaming chat completion request is sent with a JSON body, **Then** the stored `request_body` column contains the complete JSON request body, and the `response_headers` column contains the upstream provider's response headers as JSON.
2. **Given** the gateway is running, **When** a streaming request is sent, **Then** the stored `request_body` column contains the complete JSON request body (not the streamed chunks, but the original request), and `response_headers` contains the upstream response headers.
3. **Given** the gateway is running, **When** a request body exceeds 100 KB, **Then** the body is truncated to a reasonable maximum size (e.g., 100,000 characters) and stored without crashing.
4. **Given** the `otel-agent view` command is used, **When** a logged request is displayed, **Then** the request body and response headers are shown alongside other request metadata.

---

### User Story 2 - Configurable Logging (Priority: P2)

As a user concerned about privacy or database size, I want the ability to disable request body logging via configuration, because request bodies may contain sensitive prompts, proprietary content, or very large payloads that bloat the database.

**Why this priority**: Some users route sensitive data through the gateway. Having an opt-out mechanism is important for privacy compliance and storage management, but the feature still works without it (just always logs).

**Independent Test**: Can be tested by setting `log_request_body: false` in config and confirming the `request_body` column remains empty in the database.

**Acceptance Scenarios**:

1. **Given** config has `log_request_body: false`, **When** any request is logged, **Then** the `request_body` column is stored as an empty string; response headers are still logged.
2. **Given** config has `log_request_body: true` or the setting is omitted (default), **When** any request is logged, **Then** the request body is stored in full.
3. **Given** config is hot-reloaded, **When** the `log_request_body` setting is changed, **Then** the new behavior takes effect for subsequent requests without a restart.

---

### Edge Cases

- What happens when the request body is empty (e.g., GET request accidentally hits a POST endpoint)?
- What happens when the request body contains binary or non-JSON data?
- What happens when the body is exactly at the truncation threshold?
- What happens when the database disk is full and the write fails?
- What happens when upstream response headers are missing or malformed?

## Requirements

### Functional Requirements

- **FR-001**: System MUST store the complete incoming request body in the `request_body` column of the `requests` table for every logged POST request.
- **FR-002**: System MUST store the upstream provider's response headers in the `response_headers` column as a JSON object for every logged request.
- **FR-003**: System MUST truncate request bodies that exceed 100,000 characters to prevent excessive database storage.
- **FR-004**: System MUST support a `log_request_body` configuration option (boolean, default: `true`) that controls whether request bodies are stored.
- **FR-005**: System MUST persist the request body from the original client request, not the converted upstream body.
- **FR-006**: System MUST apply the same logging behavior to both streaming and non-streaming requests.
- **FR-007**: System MUST hot-reload the `log_request_body` configuration setting without requiring a restart.
- **FR-008**: System MUST redact known sensitive headers (e.g., `authorization`, `x-api-key`) in response headers before storage, replacing values with `[REDACTED]`.
- **FR-009**: The `view` command MUST display the stored request body and response headers alongside other request metadata.

### Key Entities

- **Telemetry Record**: Represents a single logged request. Key attributes: timestamp, method, URL, upstream provider, request headers, **request body**, response status, **response headers**, response body, latency. Both the `request_body` and `response_headers` fields transition from always-empty/`{}` to conditionally-populated/populated.
- **Configuration**: The gateway config file (`config.yaml`) gains a new optional `log_request_body` boolean field.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of logged POST requests have a non-empty `request_body` column when `log_request_body` is `true` (or omitted).
- **SC-002**: 100% of logged requests have a non-empty `response_headers` column containing the upstream provider's headers.
- **SC-003**: Request bodies up to 100,000 characters are stored completely without truncation.
- **SC-004**: Setting `log_request_body: false` results in zero request body data stored in the database.
- **SC-005**: No measurable increase in proxy latency (logging adds negligible overhead since the body is already parsed in memory).
- **SC-006**: Sensitive headers (authorization, x-api-key) are stored as `[REDACTED]` in the database — never as raw credential values.
- **SC-007**: The `view` command displays the request body and response headers for logged requests, enabling full request inspection from the terminal.

## Assumptions

- The `request_body TEXT` and `response_headers TEXT` columns already exist in the database schema — no migration is needed.
- The request body is already parsed as JSON in memory by the time logging occurs (FastAPI reads it via `request.json()`), so serializing it back to JSON for storage has negligible cost.
- Response headers from the upstream HTTP response are available as a dictionary and can be serialized to JSON.
- Users who want to keep their prompts private can set `log_request_body: false` in config.
- Truncation at 100,000 characters is sufficient for most use cases; extremely large prompts (e.g., long context documents) will be partially stored.
- The gateway is a single-user/developer tool — no multi-tenant access control is needed for body visibility.
