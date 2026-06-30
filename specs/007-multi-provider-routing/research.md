# Research: Multi-Provider Routing

**Feature**: 007-multi-provider-routing
**Date**: 2026-06-30

## Questions

1. Should we retain the existing host/prefix fallback routing during migration?
2. How should provider-level active selection interact with key-level active selection?
3. What should `otel-agent routes` display after removal of old routing?
4. How should startup behave when active-provider rules are violated?
5. What config shape changes are required or backward-compatible?

## Findings

### Decision: Remove host/prefix fallback routing entirely

- **Decision**: The addon/routing path supports only standardized provider paths; no host substring matching or prefix fallback remains.
- **Rationale**: The clarified feature boundary requires one routing surface only. Removing fallback simplifies request flow, validation, and tests.
- **Alternatives considered**:
  - Keep fallback temporarily behind a flag — rejected because it preserves the routing surface the feature is removing.
  - Deprecation warning only — rejected because users still need to migrate client configs.

### Decision: Use provider active flag, not key active selection

- **Decision**: Provider entries include exactly one active provider per type. Key rotation remains, but selection is by provider.
- **Rationale**: The user's config shape models provider-level activity. This matches the requested semantics more directly than key-level active.
- **Alternatives considered**:
  - Keep multiple active keys as selection mechanism — rejected because it doesn't map to the requested config.
  - Hybrid provider+key active flags — rejected as unnecessary complexity for v1.

### Decision: Routes display active provider assignment per type

- **Decision**: `otel-agent routes` shows one active provider per type with type summary/routing table behavior.
- **Rationale**: Provides the visibility needed to confirm routing behavior without exposing old routing entries.
- **Alternatives considered**:
  - Show all provider entries — rejected because it can imply unused entries are valid routing targets.
  - Hide routes entirely — rejected because users need verification before sending traffic.

### Decision: Startup rejects invalid active-provider configs

- **Decision**: Config load raises clear errors for zero or multiple active providers within a type.
- **Rationale**: Prevents silent misrouting and gives users immediate actionable feedback.
- **Alternatives considered**:
  - Warn and pick one automatically — rejected because selection must be explicit.
  - Allow runtime override — rejected because it adds CLI behavior outside the requested scope.

### Decision: Config shape adds `providers[type][name]` active entries

- **Decision**: Provider definitions live under type groups, with name/base_url/api_key/active fields.
- **Rationale**: Matches the requested config shape and makes active assignment explicit per type.
- **Alternatives considered**:
  - Flat provider list with type field — rejected because it doesn't enforce the one-active-per-type rule as directly.
  - Multiple top-level config files — rejected because it increases user burden.

## Open Risks

- Existing docs/tests still describe old routing behavior; replacement requires coordinated cleanup.
- Client migration from host/old path routing to `/openai` and `/anthropic` paths is breaking and must be documented.
