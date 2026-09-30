# API Contract: Models Endpoint

**Date**: 2026-07-07

## GET /v1/models

List all available models across all configured providers.

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| provider | string | No | Filter by provider name (e.g., `openai`) |

### Response (200 OK)

```json
{
  "object": "list",
  "data": [
    {
      "id": "openai/gpt-4o",
      "object": "model",
      "created": 1234567890,
      "owned_by": "openai",
      "context_length": 128000,
      "max_output_tokens": 16384,
      "input_modalities": ["text", "image"],
      "output_modalities": ["text"]
    },
    {
      "id": "xiaomi/mimo-v-2.5",
      "object": "model",
      "created": 1234567890,
      "owned_by": "xiaomi",
      "context_length": 200000,
      "input_modalities": ["text", "image", "video", "audio"],
      "output_modalities": ["text"]
    },
    {
      "id": "cursor/composer-2.5",
      "object": "model",
      "created": 1234567890,
      "owned_by": "cursor"
    }
  ]
}
```

`context_length`, `max_output_tokens`, `input_modalities` and `output_modalities`
are optional, additive fields (added 2026-09): the core four fields
(`id`, `object`, `created`, `owned_by`) keep their names and semantics. In the
example, `xiaomi/mimo-v-2.5` has no `max_output_tokens` (value unknown — the
field is omitted, not zeroed or nulled) and `cursor/composer-2.5` has no
capability fields at all.

### Capability metadata fields

| Field | Type | Description |
|-------|------|-------------|
| context_length | integer | Total context window length in tokens |
| max_output_tokens | integer | Maximum output tokens per response |
| input_modalities | string[] | Accepted input modalities (`text`, `image`, `file`, `video`, `audio`; unknown values pass through untouched) |
| output_modalities | string[] | Produced output modalities (`text`, `image`, `audio`; unknown values pass through untouched) |

### Response with provider filter

```
GET /v1/models?provider=openai
```

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

### Error Responses

**400 Bad Request** — invalid provider filter:
```json
{
  "error": {
    "message": "Unknown provider 'nonexistent'. Configured providers: openai, xiaomi.",
    "type": "invalid_request_error"
  }
}
```

### Behavior Notes

- Models from unreachable providers are silently omitted (partial results returned)
- Providers that don't expose a model list endpoint contribute zero models
- Results are cached for 5 minutes (configurable)
- Cache invalidates on config hot-reload
- Response format matches OpenAI `/v1/models` for SDK compatibility
- Capability metadata is sourced per field: upstream catalog value (same name,
  right type) passes through → otherwise backfilled from the OpenRouter public
  catalog → otherwise the field is omitted as a whole (never `0`, never `null`)
- The backfill is zero-config: there is no config knob for capability metadata
  and no source label in the response. The whole OpenRouter catalog is fetched
  at most once per day in the background; when OpenRouter is unreachable the
  previous values keep serving (up to 7 days) and a request never fails or
  slows down because of it
