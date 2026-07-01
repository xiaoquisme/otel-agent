# Feature Specification: Multi-Provider Routing

**Feature Branch**: `007-multi-provider-routing`

**Created**: 2026-06-30

**Status**: Draft

**Input**: User description: "want client connect this client by /openai and /anthropic, for the server side, dependency the config with active field. and the config file like this providers: openai: - name: xiaomi, base_url, api_key, active. anthropic: - name, base_url, api_key, active. only one provider can be active at a time."

## Clarifications

### Session 2026-06-30

- Q: Should the existing routing method remain supported? → A: No. The existing routing method should be removed; only the standardized provider-path routing should be supported.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure Multiple Providers (Priority: P1)

A user edits the configuration file to define multiple named providers under each provider type. The user assigns exactly one provider as active per type so requests are routed predictably. The user does not need to change client code or endpoint addresses to switch providers.

**Why this priority**: Without configurable providers, the feature does not exist. This is the foundational capability that makes all other user journeys possible.

**Independent Test**: User creates a config with two OpenAI-compatible providers, marks one as active, and verifies the startup output shows only that provider as active for the OpenAI type.

**Acceptance Scenarios**:

1. **Given** a config with two OpenAI providers and one marked active, **When** the proxy starts, **Then** the active provider is used and the inactive provider is ignored for OpenAI requests.
2. **Given** a config with zero active providers for a type, **When** the proxy starts, **Then** the proxy reports a configuration error and does not start.
3. **Given** a config with two active providers for the same type, **When** the proxy starts, **Then** the proxy reports a configuration error and does not start.

---

### User Story 2 - Route Requests Through Standardized Paths (Priority: P1)

A user sends requests to `/openai` or `/anthropic` and the proxy forwards them to the corresponding active provider transparently. The user does not need to know provider names, base URLs, or API keys after configuration.

**Why this priority**: This is the core user-facing value of the feature. It abstracts provider selection behind a stable path so client behavior stays consistent across provider swaps.

**Independent Test**: User sends a request to `/openai` and verifies it reaches the active OpenAI provider. User repeats with `/anthropic` and verifies it reaches the active Anthropic provider.

**Acceptance Scenarios**:

1. **Given** an active OpenAI provider is configured, **When** the user sends a request to `/openai`, **Then** the request is forwarded to the active provider's base URL with the active provider's credentials.
2. **Given** an active Anthropic provider is configured, **When** the user sends a request to `/anthropic`, **Then** the request is forwarded to the active provider's base URL with the active provider's credentials.
3. **Given** a provider is switched from inactive to active in config, **When** the config is reloaded, **Then** new requests to that provider type route to the newly active provider without restarting.

---

### User Story 3 - View Active Provider Assignments (Priority: P2)

A user inspects the proxy's current configuration to see which provider is active for each type. This helps the user confirm routing behavior before sending traffic.

**Why this priority**: Visibility reduces debugging time when requests do not behave as expected. It is useful but not required for the basic routing flow.

**Independent Test**: User runs the view/status command and verifies it reports the active provider name and base URL for each provider type.

**Acceptance Scenarios**:

1. **Given** the proxy is running with configured providers, **When** the user requests provider status, **Then** the output shows one active provider per type or reports missing configuration.
2. **Given** multiple providers exist for a type, **When** the user requests provider status, **Then** only the active provider is shown as selected.

---

### User Story 4 - Handle Provider Failures Gracefully (Priority: P3)

A user encounters a clear error message when the active provider is unreachable, instead of a silent failure or confusing timeout. The user knows whether the issue is with their provider selection or network connectivity.

**Why this priority**: Error clarity is important for reliability, but it is secondary to the core routing and configuration behavior.

**Independent Test**: User configures an active provider with an invalid base URL, sends a request, and verifies the error message indicates the provider could not be reached.

**Acceptance Scenarios**:

1. **Given** the active provider URL is unreachable, **When** the user sends a request, **Then** the user receives an actionable error identifying the active provider and the connection failure.
2. **Given** the active provider returns an error response, **When** the user sends a request, **Then** the proxy forwards the upstream response rather than masking or rewriting it into a generic failure.

---

### Edge Cases

- What happens when no provider is marked active for a provider type?
- What happens when multiple providers are marked active for the same provider type?
- What happens when the active provider's base URL is malformed?
- What happens when the config file is edited while requests are in flight?
- What happens when a provider's API key is missing or empty?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose standardized routing paths for OpenAI-compatible and Anthropic-compatible traffic, such as `/openai` and `/anthropic`.
- **FR-002**: System MUST read provider configuration from a config file that defines provider types with named provider entries.
- **FR-003**: Each provider entry MUST include a human-readable name, a base URL, an API key, and an active status.
- **FR-004**: System MUST enforce that exactly one provider is active within each provider type.
- **FR-005**: System MUST reject configuration with zero active providers for a type and report which type is missing an active provider.
- **FR-006**: System MUST reject configuration with multiple active providers for the same type and report the duplicate active entries.
- **FR-007**: System MUST route all requests for a provider type through its currently active provider instance.
- **FR-008**: System MUST load provider credentials and base URLs from the active provider's configuration when forwarding requests.
- **FR-009**: System MUST support reloading provider configuration without requiring a full restart.
- **FR-010**: System MUST provide users with a way to view the currently active provider for each type.
- **FR-011**: System MUST return clear error messages when the active provider is unreachable, malformed, or returns an error.
- **FR-012**: System MUST remove the previous routing method and support only the standardized provider-path routing surface.

### Key Entities *(include if feature involves data)*

- **Provider Entry**: A single named backend AI service definition with a base URL, API key, and active flag.
- **Provider Type**: A category grouping related providers, such as `openai` or `anthropic`, with exactly one active member at runtime.
- **Provider Configuration**: The user-authored config defining all provider entries, their types, and active assignments.
- **Routing Rule**: The runtime mapping from a standardized path to the active provider for that path's provider type.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can complete provider setup in under 1 minute by editing a single config file.
- **SC-002**: Requests sent to `/openai` and `/anthropic` reach the correct active provider without any additional client-side configuration.
- **SC-003**: Switching the active provider requires no code changes, only a config update that takes effect within the reload interval.
- **SC-004**: Users can identify the active provider for each type from the tool's status output.
- **SC-005**: Misconfigured provider files produce actionable error messages that identify missing or duplicate active flags within 1 second of startup.
- **SC-006**: Connection failures produce diagnostic error messages that include the provider name, endpoint URL, specific failure reason, and actionable troubleshooting steps. [BUG-002]

**Bugfix**: 2026-06-30 — BUG-002 Added SC-006 for actionable connection error diagnostics

## Assumptions

- Standardized paths `/openai` and `/anthropic` are the intended routing surface; direct provider URLs remain an internal implementation detail.
- Provider configuration follows the same file format and location conventions used by the existing otel-agent config.
- The proxy removes the previous routing method entirely and uses only the standardized `/openai` and `/anthropic` provider-path routing surface.
- Existing request transformations, logging, and security behavior remain unchanged; this feature replaces provider selection behavior, not downstream handling.
- The proxy continues to validate credentials and headers using existing conventions for API key handling.
- Provider names and types are user-defined strings; they do not need to match external service identifiers.
- Users are responsible for ensuring active provider base URLs and credentials are valid.
