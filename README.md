# otel-agent — LLM Telemetry Proxy

Intercept, log, and redirect LLM API calls (OpenAI, Anthropic, etc.).

## Install

```bash
uv sync
```

## Usage

### Start proxy (default port 8080)

```bash
uv run otel-proxy proxy
```

### Redirect all traffic to a different upstream

```bash
uv run otel-proxy proxy --upstream https://api.anthropic.com
```

### Custom port and DB path

```bash
uv run otel-proxy proxy -p 9090 -d /tmp/llm-logs.db
```

### View logged requests

```bash
uv run otel-proxy view
uv run otel-proxy view --filter openai --limit 50
```

### Use with Python requests

```python
import requests

resp = requests.post(
    "https://api.openai.com/v1/chat/completions",
    json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
    headers={"Authorization": "Bearer sk-..."},
    proxies={"https": "http://127.0.0.1:8080"},
    verify=False,  # mitmproxy self-signed cert
)
```

### Use with OpenAI SDK

```python
import httpx
from openai import OpenAI

client = OpenAI(
    http_client=httpx.Client(
        proxies="http://127.0.0.1:8080",
        verify=False,
    )
)
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
