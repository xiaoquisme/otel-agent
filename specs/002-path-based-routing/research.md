# Research: Path-Based Routing

**Feature**: 002-path-based-routing
**Date**: 2026-06-26

## Decision 1: Route Matching Strategy

**Decision**: Match by longest prefix first. The proxy extracts the first path segment (e.g., `/openai` from `/openai/v1/chat/completions`) and looks up the provider.

**Rationale**: Simple, predictable, and covers all use cases. Longest-prefix prevents ambiguity when one prefix is a substring of another (e.g., `/open` vs `/openai`).

**Alternatives considered**:
- Regex-based matching: Overkill for this use case. Adds complexity without user value.
- Query parameter routing (`?provider=openai`): Non-standard, breaks client libraries.
- Header-based routing: Requires custom client configuration, defeats the purpose.

## Decision 2: API Style Determines Auth Header

**Decision**: Each provider has a `type` field (`openai` or `anthropic`). The type determines the auth header format:
- `openai` → `Authorization: Bearer <key>`
- `anthropic` → `x-api-key: <key>`

**Rationale**: The existing `PROVIDER_AUTH` dict in `addon.py` already does this by host substring. Moving it to a `type` field makes it explicit and config-driven.

**Alternatives considered**:
- Auto-detect from host: Already works but breaks with custom upstreams (e.g., a proxy to a proxy).
- Per-provider `auth_header` config: Too flexible, most users just need the two standard formats.

## Decision 3: Prefix Stripping

**Decision**: Strip the matched prefix from the request path before forwarding. `/openai/v1/chat/completions` → `/v1/chat/completions`.

**Rationale**: The upstream expects its standard paths. Adding a prefix is a proxy concern, not an upstream concern.

**Alternatives considered**:
- Keep prefix and let upstream handle: Breaks all existing LLM APIs.
- Configurable strip/keep: Adds complexity for no practical benefit.

## Decision 4: Config Schema Extension

**Decision**: Add `type` and `prefix` fields to each provider. Keep backward compatibility — if `type` is omitted, infer from provider name. If `prefix` is omitted, use `/<provider_name>`.

**Rationale**: Minimal config change. Existing configs work without modification.

**Alternatives considered**:
- Separate `routes` section: Duplicates provider info, harder to maintain.
- Top-level `api_styles` grouping: Breaks existing flat provider structure.

## Decision 5: Duplicate Prefix Detection

**Decision**: Validate at config load time. Reject config with duplicate prefixes.

**Rationale**: Fail-fast prevents silent routing bugs. Users see the error immediately when they edit the config.

**Alternatives considered**:
- First-match-wins: Silent, confusing when requests go to wrong provider.
- Last-match-wins: Same problem.
