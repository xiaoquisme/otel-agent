# otel-agent — LLM Telemetry Proxy

Intercept, log, and redirect LLM API calls. Config-driven key rotation with path-based routing.

## Install

```bash
# Run without installing
uvx --from git+https://github.com/xiaoquisme/otel-agent.git otel-agent --version

# Install globally
uv tool install git+https://github.com/xiaoquisme/otel-agent.git

# pip fallback
pip install git+https://github.com/xiaoquisme/otel-agent.git
```

## Quick Start

```bash
# 1. Create config
otel-agent init

# 2. Edit config to add your API keys
otel-agent config edit

# 3. View routing table
otel-agent routes

# 4. Start proxy
otel-agent proxy

# 5. Send requests with path prefix
curl http://localhost:8080/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}'
```

## Commands

```
otel-agent --version          Print version
otel-agent init               Create default config file
otel-agent proxy              Start the MITM proxy
otel-agent routes             Display routing table
otel-agent view               View logged requests
otel-agent config path|show|edit  Manage configuration
otel-agent doctor             Check installation health
```

## Path-Based Routing

Requests are routed by URL path prefix. The prefix is stripped before forwarding to the upstream.

```
/openai/v1/chat/completions    → https://api.openai.com/v1/chat/completions
/anthropic/v1/messages         → https://api.anthropic.com/v1/messages
/deepseek/v1/chat/completions  → https://api.deepseek.com/v1/chat/completions
```

### View Routes

```bash
otel-agent routes
```

Output:
```
Path Prefix      Provider         Type         Upstream
/anthropic       anthropic        anthropic    https://api.anthropic.com
/openai          openai           openai       https://api.openai.com/v1
```

## Config File

`~/.otel-agent/config.yaml`:

```yaml
# Default provider for requests without a matching prefix
default_provider: openai

providers:
  openai:
    type: openai              # API style: openai or anthropic
    prefix: /openai           # URL path prefix for routing
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-proj-key1
        active: true
      - key: sk-proj-key2
        active: true

  anthropic:
    type: anthropic
    prefix: /anthropic
    base_url: https://api.anthropic.com
    keys:
      - key: ***
        active: true

  # OpenAI-compatible provider with custom prefix
  deepseek:
    type: openai
    prefix: /deepseek
    base_url: https://api.deepseek.com/v1
    keys:
      - key: ***
        active: true
```

### Config Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `type` | No | Inferred from name | API style: `openai` or `anthropic` |
| `prefix` | No | `/<provider_name>` | URL path prefix for routing |
| `base_url` | Yes | — | Upstream API base URL |
| `keys` | Yes | — | API keys with `active` flag |

### Auth Headers by Type

- `openai` → `Authorization: Bearer <key>`
- `anthropic` → `x-api-key: <key>`

### Validation

The proxy rejects configs with:
- Duplicate prefixes
- Invalid prefix format (must start with `/`)
- Unknown `type` values
- Empty `base_url`

## Client Usage

### OpenAI SDK (path-based)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/openai/v1",
    api_key="dummy",  # proxy injects real key
)
```

### Anthropic SDK (path-based)

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8080/anthropic",
    api_key="dummy",  # proxy injects real key
)
```

### curl

```bash
# OpenAI
curl http://localhost:8080/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}'

# Anthropic
curl http://localhost:8080/anthropic/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":100,"messages":[{"role":"user","content":"hi"}]}'
```

## Other Commands

```bash
otel-agent proxy -p 9090              # Custom port
otel-agent proxy -c ./config.yaml     # Custom config
otel-agent view --filter openai       # Filter logs
otel-agent config show                # Show config (keys masked)
otel-agent doctor                     # Health check
```

## Testing

```bash
uv run pytest tests/ -v -m "not integration"
```

## License

MIT
