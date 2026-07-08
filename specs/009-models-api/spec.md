# Feature Specification: Models API Endpoint

**Feature Branch**: `009-models-api`

**Created**: 2026-07-07

**Status**: Draft

**Input**: User description: "add /models API for retrieve all the models from provider"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - List All Available Models (Priority: P1)

A user sends a GET request to `/v1/models` and receives a unified list of all models available across all configured providers. Each model is prefixed with its provider name (e.g., `openai/gpt-4o`, `xiaomi/mimo-v-2.5`), matching the model names used in chat completion requests.

**Why this priority**: This is the core endpoint. Without it, the feature does not exist. Users need a way to discover what models are available before making requests.

**Independent Test**: Start the gateway with multiple providers configured, send GET `/v1/models`, verify the response includes models from each provider with correct prefixes.

**Acceptance Scenarios**:

1. **Given** the gateway is running with `openai` and `xiaomi` providers configured, **When** the user sends GET `/v1/models`, **Then** the response includes models from both providers prefixed with their provider names.
2. **Given** a provider is configured but unreachable, **When** the user sends GET `/v1/models`, **Then** the gateway returns models from the reachable providers and omits or marks the unreachable provider.
3. **Given** no providers are configured, **When** the user sends GET `/v1/models`, **Then** the gateway returns an empty model list.

---

### User Story 2 - List Models for a Specific Provider (Priority: P2)

A user sends GET `/v1/models?provider=openai` and receives only the models from that specific provider. This allows clients to filter by provider without parsing the full list.

**Why this priority**: Filtering is useful but not required for the basic discovery flow. It improves efficiency for clients that only need one provider's models.

**Independent Test**: Send GET `/v1/models?provider=openai`, verify only OpenAI models are returned.

**Acceptance Scenarios**:

1. **Given** the gateway is running with multiple providers, **When** the user sends GET `/v1/models?provider=xiaomi`, **Then** only Xiaomi models are returned.
2. **Given** the user requests a provider that does not exist, **When** the user sends GET `/v1/models?provider=nonexistent`, **Then** the gateway returns an empty list or a clear error.

---

### User Story 3 - Cached Model Discovery (Priority: P2)

The gateway queries upstream providers for their model lists and caches the results to avoid adding latency to every `/v1/models` request. The cache refreshes periodically or on demand.

**Why this priority**: Without caching, every `/v1/models` call would make N upstream requests, adding significant latency. Caching is important for performance but not strictly required for the endpoint to function.

**Independent Test**: Send multiple `/v1/models` requests in quick succession, verify upstream is only queried once within the cache window.

**Acceptance Scenarios**:

1. **Given** the gateway has fetched models from providers, **When** the user sends a second `/v1/models` request within the cache window, **Then** the response is served from cache without contacting upstream providers.
2. **Given** the cache has expired, **When** the user sends GET `/v1/models`, **Then** the gateway refreshes model lists from upstream providers.

---

### Edge Cases

- What happens when a provider's model list endpoint returns an unexpected format?
- What happens when a provider does not expose a model list endpoint?
- What happens when a provider returns a very large number of models?
- What happens when the gateway loses network connectivity to a provider?
- What happens when the config is hot-reloaded — does the cache invalidate?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose a GET `/v1/models` endpoint returning all available models in OpenAI-compatible format.
- **FR-002**: Each model in the response MUST include the provider name as a prefix (e.g., `openai/gpt-4o`).
- **FR-003**: System MUST query each configured provider's model list endpoint to discover available models.
- **FR-004**: System MUST support filtering models by provider via a `provider` query parameter.
- **FR-005**: System MUST cache model lists from upstream providers to avoid per-request overhead.
- **FR-006**: Cache TTL MUST be configurable or use a sensible default (e.g., 5 minutes).
- **FR-007**: System MUST handle unreachable providers gracefully — returning models from reachable providers without failing the entire request.
- **FR-008**: System MUST invalidate the cache when the configuration is hot-reloaded.
- **FR-009**: System MUST support providers that do not expose a model list endpoint by returning an empty list for that provider.
- **FR-010**: The response format MUST follow the OpenAI `/v1/models` response structure for client compatibility.

### Key Entities

- **Model Entry**: A model available from a provider, with id (prefixed), provider name, and creation timestamp.
- **Model Cache**: An in-memory cache of model lists per provider, with TTL-based expiration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can retrieve all available models via GET `/v1/models` in under 500ms (cached) or 5s (uncached).
- **SC-002**: The response includes models from all reachable providers, prefixed with provider names.
- **SC-003**: Clients using the OpenAI SDK can call `client.models.list()` against the gateway and receive valid results.
- **SC-004**: Unreachable providers do not cause the endpoint to fail — partial results are returned.
- **SC-005**: Repeated `/v1/models` requests within the cache window do not trigger upstream provider queries.

## Assumptions

- Providers that support OpenAI-compatible API expose a `GET /v1/models` endpoint.
- Providers that use Anthropic format do not have a standard models endpoint — the gateway will attempt OpenAI-format discovery for all providers.
- The gateway queries each provider using the provider's `base_url` and `api_key`.
- Model IDs in the response follow the `provider/original-model-id` format.
- The `/v1/models` endpoint is read-only and does not require authentication at the gateway level.
