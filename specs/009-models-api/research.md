# Research: Models API Endpoint

**Date**: 2026-07-07

## Decision 1: Model Discovery Approach

**Decision**: Query each provider's `GET /v1/models` endpoint using httpx, aggregate results.

**Rationale**: Most OpenAI-compatible providers expose `GET /v1/models`. This is the standard discovery mechanism. For providers that don't expose it, return an empty list for that provider (graceful degradation).

**Alternatives considered**:
- Static model list in config: Rejected — requires manual maintenance, goes stale.
- Parsing model names from request history: Rejected — incomplete, only shows models already used.

## Decision 2: Caching Strategy

**Decision**: In-memory dict with per-provider TTL (default 5 minutes). Cache keyed by provider name.

**Rationale**: Simple, no external dependencies. Single-process gateway doesn't need distributed cache. Per-provider TTL allows different refresh rates if needed later.

**Alternatives considered**:
- No caching: Rejected — N upstream requests per `/v1/models` call is too slow.
- SQLite cache: Rejected — overkill for ephemeral data, adds disk I/O.
- Redis/memcached: Rejected — external dependency for a single-process tool.

## Decision 3: Response Format

**Decision**: Follow OpenAI `/v1/models` response structure exactly.

```json
{
  "object": "list",
  "data": [
    {
      "id": "openai/gpt-4o",
      "object": "model",
      "created": 1234567890,
      "owned_by": "openai"
    }
  ]
}
```

**Rationale**: OpenAI SDK `client.models.list()` expects this format. Full compatibility enables drop-in usage.

**Alternatives considered**:
- Custom format with more metadata: Rejected — breaks SDK compatibility.

## Decision 4: Cache Invalidation

**Decision**: Invalidate cache when config file mtime changes (already tracked by `Config._reload()`).

**Rationale**: Reuses existing hot-reload mechanism. Simple and consistent.

**Alternatives considered**:
- Manual invalidation via API endpoint: Rejected — adds complexity, config reload is sufficient.
- Time-only invalidation: Rejected — config changes should take effect immediately.
