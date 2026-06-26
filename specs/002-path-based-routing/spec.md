# Feature Specification: Path-Based Routing

**Feature Branch**: `002-path-based-routing`

**Created**: 2026-06-26

**Status**: Draft

**Input**: Update proxy config so requests are routed by URL path prefix (e.g., `/openai/v1` routes to OpenAI, `/anthropic` routes to Anthropic). The proxy decides which upstream to use based on the path. Config file should be organized by API style (OpenAI-compatible vs Anthropic-compatible).

## User Scenarios & Testing

### User Story 1 - Path-Based Provider Selection (Priority: P1)

A user sends requests to the proxy with a path prefix that indicates which provider should handle the request. The proxy strips the prefix and forwards to the correct upstream.

**Why this priority**: This is the core routing feature. Without it, all requests go to a single default provider.

**Independent Test**: Send `POST http://localhost:8080/openai/v1/chat/completions` and verify it reaches the OpenAI upstream. Send `POST http://localhost:8080/anthropic/v1/messages` and verify it reaches the Anthropic upstream.

**Acceptance Scenarios**:

1. **Given** the proxy is running with OpenAI and Anthropic providers configured, **When** a client sends `POST /openai/v1/chat/completions`, **Then** the proxy forwards to `https://api.openai.com/v1/chat/completions` with the OpenAI API key injected.
2. **Given** the proxy is running, **When** a client sends `POST /anthropic/v1/messages`, **Then** the proxy forwards to `https://api.anthropic.com/v1/messages` with the Anthropic API key injected.
3. **Given** the proxy is running, **When** a client sends a request with no recognized path prefix, **Then** the proxy uses the default provider (or returns an error if no default is configured).
4. **Given** the proxy is running, **When** a client sends `POST /openai/v1/chat/completions`, **Then** the `/openai` prefix is stripped before forwarding — the upstream receives `/v1/chat/completions`.

---

### User Story 2 - Config Organized by API Style (Priority: P1)

A user configures providers grouped by their API compatibility style. OpenAI-compatible providers share a common config structure, and Anthropic-compatible providers share theirs.

**Why this priority**: Different API styles have different auth headers, request/response formats, and endpoint paths. Grouping by style makes config clear and prevents misconfiguration.

**Independent Test**: Create a config with `openai_style` and `anthropic_style` sections. Verify the proxy loads both and routes correctly.

**Acceptance Scenarios**:

1. **Given** a config file with `openai_style` providers, **When** the user views the config, **Then** all OpenAI-compatible providers are grouped together with their base URLs and keys.
2. **Given** a config file with `anthropic_style` providers, **When** the user views the config, **Then** all Anthropic-compatible providers are grouped together.
3. **Given** a provider is configured under `openai_style`, **When** the proxy sends a request, **Then** the auth header uses `Authorization: Bearer <key>`.
4. **Given** a provider is configured under `anthropic_style`, **When** the proxy sends a request, **Then** the auth header uses `x-api-key: <key>`.

---

### User Story 3 - Custom Path Prefixes (Priority: P2)

A user wants to define custom path prefixes for providers, not just the default `/openai` or `/anthropic`.

**Why this priority**: Users may have multiple OpenAI-compatible providers (e.g., a local model server) and need distinct prefixes.

**Independent Test**: Configure a provider with `prefix: /local`. Send request to `/local/v1/chat/completions`. Verify it reaches the configured upstream.

**Acceptance Scenarios**:

1. **Given** a provider configured with `prefix: /local`, **When** a client sends `POST /local/v1/chat/completions`, **Then** the proxy forwards to that provider's base_url.
2. **Given** a provider configured with `prefix: /deepseek`, **When** a client sends `POST /deepseek/v1/chat/completions`, **Then** the proxy forwards to the DeepSeek upstream.
3. **Given** two providers with different prefixes, **When** requests arrive with each prefix, **Then** each routes to its correct upstream independently.

---

### User Story 4 - View Route Mapping (Priority: P2)

A user wants to see which path prefixes map to which providers.

**Why this priority**: Debugging routing issues requires visibility into the routing table.

**Independent Test**: Run `otel-agent routes`. Verify it shows all configured prefix-to-provider mappings.

**Acceptance Scenarios**:

1. **Given** the proxy is configured, **When** the user runs `otel-agent routes`, **Then** a table shows each path prefix, the target provider, and the upstream base_url.
2. **Given** a provider has a custom prefix, **When** the user runs `otel-agent routes`, **Then** the custom prefix is shown alongside the default prefix.

---

### Edge Cases

- What happens if two providers have the same path prefix? The tool MUST reject the config at load time with a clear error: "Duplicate prefix '/openai' on providers 'openai' and 'openai-local'."
- What happens if a request path matches a prefix but the provider has no active keys? The proxy MUST return HTTP 503 with a message: "Provider 'openai' has no active keys."
- What happens if the config has no providers? The proxy MUST refuse to start with: "No providers configured. Run: otel-agent init"
- What happens if a request has a prefix match but the remaining path is empty? The proxy MUST forward to the provider's base_url root path.

## Requirements

### Functional Requirements

- **FR-001**: The proxy MUST route requests based on URL path prefix (e.g., `/openai/v1/...` → OpenAI provider).
- **FR-002**: The proxy MUST strip the path prefix before forwarding to the upstream. The upstream receives only the remaining path.
- **FR-003**: The config file MUST support a `routes` section that maps path prefixes to provider names.
- **FR-004**: The config file MUST support grouping providers by API style (`openai_style` and `anthropic_style`).
- **FR-005**: Each provider MUST have a `type` field indicating its API style (`openai` or `anthropic`), which determines the auth header format.
- **FR-006**: Users MUST be able to define custom path prefixes per provider.
- **FR-007**: If no prefix is configured, the provider name MUST be used as the default prefix (e.g., provider `openai` gets prefix `/openai`).
- **FR-008**: The proxy MUST reject configs with duplicate prefixes at startup.
- **FR-009**: A new `otel-agent routes` subcommand MUST display the routing table.
- **FR-010**: The existing `default_provider` behavior MUST continue to work for requests without a recognized prefix.
- **FR-011**: The config hot-reload mechanism MUST apply to route changes without restart.

### Key Entities

- **Route**: A mapping from a path prefix (e.g., `/openai`) to a provider name and its API style.
- **Provider**: An upstream LLM API endpoint with a `type` (openai/anthropic), `base_url`, and one or more API keys.
- **API Style**: Determines auth header format and endpoint conventions. Two styles: `openai` (Bearer token, `/v1/chat/completions`) and `anthropic` (x-api-key header, `/v1/messages`).

## Success Criteria

### Measurable Outcomes

- **SC-001**: A request to `/openai/v1/chat/completions` reaches the OpenAI upstream within 5ms proxy overhead.
- **SC-002**: A request to `/anthropic/v1/messages` reaches the Anthropic upstream with the correct auth header.
- **SC-003**: Users can add a new provider with a custom prefix by editing only the config file — no code changes.
- **SC-004**: `otel-agent routes` displays all configured routes in under 1 second.
- **SC-005**: Config changes to routes take effect on the next request without restarting the proxy.

## Assumptions

- Users understand the difference between OpenAI-compatible and Anthropic-compatible API formats.
- The proxy runs locally and is not exposed to the public internet.
- Path prefixes always start with `/` and do not end with `/`.
- The existing `default_provider` mechanism handles requests that don't match any prefix.
- The config file remains backward-compatible — existing configs without `routes` continue to work using the default provider.
