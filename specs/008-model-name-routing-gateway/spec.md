# Feature Specification: Model-Name-Based Routing Gateway

**Feature Branch**: `008-model-name-routing-gateway`

**Created**: 2026-07-07

**Status**: Implemented

**Input**: User description: "Change project positioning to provide OpenAI and Anthropic format API endpoints. Route internally based on model name: `openai/gpt-5.4` goes to OpenAI provider, `openrouter/openai/gpt-5.4` goes to OpenRouter, `xiaomi/mimo-v-2.5` goes to Xiaomi. Remove mitmproxy, rewrite with FastAPI."

## Clarifications

### Session 2026-07-07

- Q: Remove mitmproxy entirely? → A: Yes, replace with FastAPI/uvicorn.
- Q: Both OpenAI and Anthropic format endpoints? → A: Yes, expose both formats.
- Q: Model name format is `provider/model` or `provider/sub-provider/model`? → A: Yes, slash-separated, first segment is always the provider name.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Model-Name-Based Provider Routing (Priority: P1)

A user sends an OpenAI-format request with `model: "openai/gpt-5.4"` and the gateway routes it to the configured OpenAI provider, stripping the `openai/` prefix and forwarding `model: "gpt-5.4"`. Similarly, `model: "xiaomi/mimo-v-2.5"` routes to the Xiaomi provider.

**Why this priority**: This is the core routing mechanism that replaces the old path-based routing. Without this, the feature does not exist.

**Independent Test**: Send a request with `model: "openai/gpt-4o"` to `/v1/chat/completions` and verify it reaches the correct upstream provider with the correct model name.

**Acceptance Scenarios**:

1. **Given** a config with `openai` provider configured, **When** user sends `model: "openai/gpt-5.4"` to `/v1/chat/completions`, **Then** the request is forwarded to the OpenAI provider with `model: "gpt-5.4"`.
2. **Given** a config with `xiaomi` provider configured, **When** user sends `model: "xiaomi/mimo-v-2.5"` to `/v1/chat/completions`, **Then** the request is forwarded to the Xiaomi provider with `model: "mimo-v-2.5"`.
3. **Given** a config with `openrouter` provider configured, **When** user sends `model: "openrouter/openai/gpt-5.4"` to `/v1/chat/completions`, **Then** the request is forwarded to OpenRouter with `model: "openai/gpt-5.4"`.
4. **Given** a model string with an unregistered provider prefix, **When** user sends the request, **Then** the gateway returns a clear error identifying the unknown provider.

---

### User Story 2 - Dual API Format Endpoints (Priority: P1)

A user can send requests in either OpenAI format (`/v1/chat/completions`) or Anthropic format (`/v1/messages`). The gateway accepts both and routes based on the model name regardless of which endpoint is used.

**Why this priority**: Supporting both formats is a core positioning requirement. Users with Anthropic SDK clients must be able to use the gateway without switching to OpenAI format.

**Independent Test**: Send an Anthropic-format request to `/v1/messages` with `model: "xiaomi/mimo-v-2.5"` and verify it routes correctly.

**Acceptance Scenarios**:

1. **Given** the gateway is running, **When** user sends an OpenAI-format request to `/v1/chat/completions`, **Then** the gateway accepts and routes it.
2. **Given** the gateway is running, **When** user sends an Anthropic-format request to `/v1/messages`, **Then** the gateway accepts and routes it.
3. **Given** a provider configured with `api_format: openai`, **When** user sends an Anthropic-format request to `/v1/messages` targeting that provider, **Then** the gateway converts the request to OpenAI format before forwarding.
4. **Given** a provider configured with `api_format: anthropic`, **When** user sends an OpenAI-format request to `/v1/chat/completions` targeting that provider, **Then** the gateway converts the request to Anthropic format before forwarding.

---

### User Story 3 - Provider Configuration Registry (Priority: P1)

A user configures all providers in a single config file with name, base URL, API key, and API format. The gateway reads this config and hot-reloads on changes.

**Why this priority**: Configuration is the foundation that makes routing possible. Users must be able to define providers before any requests can be routed.

**Independent Test**: Create a config with multiple providers, start the gateway, verify startup output shows all registered providers.

**Acceptance Scenarios**:

1. **Given** a config file with providers defined, **When** the gateway starts, **Then** all providers are registered and visible in startup output.
2. **Given** the config file is modified while the gateway is running, **When** the next request arrives, **Then** the updated config is used.
3. **Given** a provider with missing required fields, **When** the gateway starts, **Then** a clear validation error is reported.

---

### User Story 4 - Telemetry and Request Logging (Priority: P2)

All requests passing through the gateway are logged to SQLite with method, URL, model, provider, request/response bodies, latency, and status code.

**Why this priority**: Telemetry is a core value proposition of the project. It should continue working after the architecture change.

**Independent Test**: Send a request through the gateway, then query the SQLite database to verify the request was logged.

**Acceptance Scenarios**:

1. **Given** the gateway is running, **When** a request completes, **Then** the request details are logged to the telemetry database.
2. **Given** logged requests exist, **When** user runs `otel-agent view`, **Then** the logged requests are displayed.

---

### Edge Cases

- What happens when the model string has no `/` (e.g., `gpt-4`)? → Return error: model must include provider prefix.
- What happens when the provider name in the model string is not in the config? → Return 400 with clear error.
- What happens when a streaming request needs format conversion? → Must preserve SSE streaming behavior.
- What happens when the config file is malformed YAML? → Report parse error at startup.
- What happens when two providers have the same name? → Config validation rejects duplicates.
- What happens when the upstream provider returns an error? → Forward the error response transparently.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose OpenAI-compatible API endpoints (`/v1/chat/completions`, `/v1/models`, etc.).
- **FR-002**: System MUST expose Anthropic-compatible API endpoints (`/v1/messages`).
- **FR-003**: System MUST route requests based on the model name prefix (e.g., `openai/gpt-5.4` → OpenAI provider).
- **FR-004**: System MUST support nested provider paths in model names (e.g., `openrouter/openai/gpt-5.4`).
- **FR-005**: System MUST strip the provider prefix from the model name before forwarding to the upstream provider.
- **FR-006**: Each provider MUST declare its `api_format` (openai or anthropic).
- **FR-007**: System MUST convert request/response formats when the client endpoint format differs from the provider's `api_format`.
- **FR-008**: System MUST read provider configuration from `~/.otel-agent/config.yaml`.
- **FR-009**: System MUST hot-reload configuration without restart.
- **FR-010**: System MUST log all requests to SQLite telemetry database.
- **FR-011**: System MUST remove all mitmproxy dependencies and use FastAPI/uvicorn.
- **FR-012**: System MUST validate config at startup and report clear errors for invalid configuration.
- **FR-013**: System MUST support streaming responses (SSE) for both OpenAI and Anthropic formats.
- **FR-014**: System MUST return clear error messages when a model string has no provider prefix.

### Key Entities

- **Provider**: A named backend service with base_url, api_key, and api_format (openai or anthropic).
- **Model Router**: Parses the model name string, identifies the provider, and determines the upstream model name.
- **Format Converter**: Translates requests/responses between OpenAI and Anthropic formats when needed.
- **Telemetry Logger**: Records all request/response pairs with metadata.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can configure providers and start the gateway in under 1 minute.
- **SC-002**: Requests with `model: "openai/gpt-5.4"` correctly reach the OpenAI provider within 5ms overhead.
- **SC-003**: Requests with `model: "openrouter/openai/gpt-5.4"` correctly reach OpenRouter with model `openai/gpt-5.4`.
- **SC-004**: Both OpenAI SDK and Anthropic SDK clients can connect to the gateway without code changes beyond base_url.
- **SC-005**: Format conversion between OpenAI and Anthropic request/response formats works for chat/messages endpoints.
- **SC-006**: All existing tests pass after migration (or are replaced with equivalent tests).
- **SC-007**: No mitmproxy dependency remains in the project.

## Assumptions

- The gateway runs as a single process (no horizontal scaling needed for v1).
- Format conversion covers the basic chat/messages endpoint; other endpoints (embeddings, completions) are out of scope for v1.
- Streaming (SSE) is the primary response mode for LLM requests.
- Provider API keys are stored in the config file (same as current behavior).
- The gateway listens on a single port and serves both OpenAI and Anthropic endpoints.
- Model names follow the `provider/model` or `provider/sub-provider/model` convention.
