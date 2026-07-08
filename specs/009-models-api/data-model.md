# Data Model: Models API

**Date**: 2026-07-07

## Entities

### ModelEntry

A single model available from a provider.

| Field | Type | Description |
|-------|------|-------------|
| id | string | Prefixed model ID (e.g., `openai/gpt-4o`) |
| object | string | Always `"model"` |
| created | int | Unix timestamp (from upstream or current time) |
| owned_by | string | Provider name (e.g., `openai`) |

### ModelCache

In-memory cache for model discovery results.

| Field | Type | Description |
|-------|------|-------------|
| _cache | dict[str, list[ModelEntry]] | Provider name → model list |
| _timestamps | dict[str, float] | Provider name → last fetch time (monotonic) |
| _config_mtime | float | Config file mtime at last fetch |
| ttl | float | Cache TTL in seconds (default: 300) |

**State transitions**:
- `EMPTY` → `FRESH` (after successful fetch)
- `FRESH` → `STALE` (after TTL expires or config mtime changes)
- `STALE` → `FRESH` (after re-fetch)
- Any → `EMPTY` (config reload with no providers)

## Relationships

- `ModelEntry.owned_by` → `Provider.name` (from config)
- `ModelCache._cache` keys → `Config.providers` keys
