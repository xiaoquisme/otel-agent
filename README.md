# otel-agent — LLM Telemetry Proxy

Intercept, log, and redirect LLM API calls. Config-driven multi-key rotation.

## Quick Start

```bash
uv sync
uv run otel-agent init       # creates ~/.otel-agent/config.yaml
# edit config to add your API keys
uv run otel-proxy proxy      # start proxy on :8080
```

## Config File

`~/.otel-agent/config.yaml`:

```yaml
providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-proj-key1
        active: true
      - key: sk-proj-key2
        active: true
      - key: sk-proj-key3
        active: false   # disabled

  anthropic:
    base_url: https://api.anthropic.com
    keys:
      - key: sk-ant-key1
        active: true
      - key: sk-ant-key2
        active: true

  deepseek:
    base_url: https://api.deepseek.com/v1
    keys:
      - key: sk-ds-key1
        active: true
```

- **Round-robin** among active keys per provider
- **Hot-reload**: edit the file, changes take effect on next request (no restart)
- Toggle `active: true/false` to enable/disable keys
- Provider matched by host substring: request to `api.openai.com` uses `openai` provider

## Usage

```bash
# Start proxy
uv run otel-proxy proxy

# Custom port and DB
uv run otel-proxy proxy -p 9090 -d /tmp/logs.db

# Override upstream (ignores config base_url)
uv run otel-proxy proxy -u https://custom-endpoint.com

# Use different config file
uv run otel-proxy proxy -c ./project-config.yaml

# View logged requests
uv run otel-proxy view
uv run otel-proxy view --filter openai --limit 50
```

## Client Usage

### Hermes Agent

```bash
hermes config set model.base_url http://127.0.0.1:8080
hermes config set model.api_key dummy
```

Or in `~/.hermes/config.yaml`:
```yaml
model:
  default: claude-sonnet-4-20250514
  provider: anthropic
  base_url: http://127.0.0.1:8080
  api_key: dummy
```

### Claude Code

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8080
export ANTHROPIC_API_KEY=dummy
claude -p "your task"
```

### OpenAI SDK

```python
import httpx
from openai import OpenAI

client = OpenAI(
    api_key="dummy",
    http_client=httpx.Client(proxies="http://127.0.0.1:8080", verify=False),
)
```

### curl

```bash
export https_proxy=http://127.0.0.1:8080
curl -k https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}'
```

## Schema

Each logged request includes:
- `timestamp`, `method`, `url`, `upstream`
- `request_headers`, `request_body` (full JSON)
- `response_status`, `response_headers`, `response_body`
- `latency_ms`

## Testing

```bash
uv run pytest tests/ -v -m "not integration"
```

## License

MIT
