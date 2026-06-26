# Quickstart: Path-Based Routing

**Feature**: 002-path-based-routing
**Date**: 2026-06-26

## Prerequisites

- otel-agent installed (`uv tool install git+https://github.com/xiaoquisme/otel-agent.git`)
- API keys for at least one provider

## Setup

```bash
# Create config with path-based routing
otel-agent init
otel-agent config edit
```

Edit config to add `type` and `prefix` fields:

```yaml
default_provider: openai

providers:
  openai:
    type: openai
    prefix: /openai
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-your-key
        active: true

  anthropic:
    type: anthropic
    prefix: /anthropic
    base_url: https://api.anthropic.com
    keys:
      - key: sk-ant-your-key
        active: true
```

## Verify Routes

```bash
otel-agent routes
```

Expected output:
```
Path Prefix    Provider      Type       Upstream
/openai        openai        openai     https://api.openai.com/v1
/anthropic     anthropic     anthropic  https://api.anthropic.com
```

## Start Proxy

```bash
otel-agent proxy
```

## Test Path-Based Routing

```bash
# OpenAI request via path prefix
curl http://localhost:8080/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}'

# Anthropic request via path prefix
curl http://localhost:8080/anthropic/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":100,"messages":[{"role":"user","content":"hi"}]}'
```

## Verify Logs

```bash
otel-agent view --limit 5
```

## Add Custom Provider

```yaml
  deepseek:
    type: openai
    prefix: /deepseek
    base_url: https://api.deepseek.com/v1
    keys:
      - key: sk-ds-your-key
        active: true
```

Then `curl http://localhost:8080/deepseek/v1/chat/completions ...` routes to DeepSeek.
