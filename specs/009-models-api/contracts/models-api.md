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
      "owned_by": "openai"
    },
    {
      "id": "openai/gpt-4o-mini",
      "object": "model",
      "created": 1234567890,
      "owned_by": "openai"
    },
    {
      "id": "xiaomi/mimo-v-2.5",
      "object": "model",
      "created": 1234567890,
      "owned_by": "xiaomi"
    }
  ]
}
```

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
