# Quickstart: Models API Endpoint

**Date**: 2026-07-07

## Prerequisites

- otel-agent installed (`uv tool install -e .` or `uv sync`)
- At least one provider configured in `~/.otel-agent/config.yaml`

## Validation Steps

### 1. Start the gateway

```bash
otel-agent proxy --foreground -p 8080
```

### 2. List all models

```bash
curl -s http://localhost:8080/v1/models | python -m json.tool
```

**Expected**: JSON response with `"object": "list"` and `"data"` array containing models from all providers, prefixed with provider names.

### 3. Filter by provider

```bash
curl -s "http://localhost:8080/v1/models?provider=openai" | python -m json.tool
```

**Expected**: Only models from the `openai` provider.

### 4. Test with OpenAI SDK

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8080/v1", api_key="dummy")
models = client.models.list()
for m in models.data:
    print(m.id)
```

**Expected**: Prints model IDs like `openai/gpt-4o`, `xiaomi/mimo-v-2.5`.

### 5. Verify caching

```bash
# Hit the endpoint twice quickly
time curl -s http://localhost:8080/v1/models > /dev/null
time curl -s http://localhost:8080/v1/models > /dev/null
```

**Expected**: Second request is significantly faster (served from cache).

### 6. Verify graceful degradation

Temporarily point one provider to an invalid base_url in config, then call `/v1/models`.

**Expected**: Models from other providers still returned. No error response.

## Verification Command

```bash
uv run pytest tests/test_models.py -v
```
