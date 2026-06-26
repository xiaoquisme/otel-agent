# otel-agent — LLM Telemetry Proxy

Intercept, log, and redirect LLM API calls (OpenAI, Anthropic, etc.).
Inject API keys in the proxy so clients don't need to know them.

## Install

```bash
uv sync
```

## Usage

### Start proxy (default port 8080)

```bash
uv run otel-proxy proxy
```

### Inject API keys (3 ways)

**CLI args (repeatable):**
```bash
uv run otel-proxy proxy \
  -k openai.com:sk-proj-xxx \
  -k anthropic.com:sk-ant-xxx
```

**Environment variable:**
```bash
export OTEL_API_KEYS="openai.com:sk-proj-xxx,anthropic.com:sk-ant-xxx"
uv run otel-proxy proxy
```

**Key file (one HOST:KEY per line):**
```bash
cat > keys.txt << 'EOF'
# comment
openai.com:sk-proj-xxx
anthropic.com:sk-ant-xxx
EOF
uv run otel-proxy proxy --key-file keys.txt
```

Priority: `--api-key` CLI > `--key-file` > `OTEL_API_KEYS` env var.

The proxy auto-detects the auth header:
- `openai.com` → `Authorization: Bearer <key>`
- `anthropic.com` → `x-api-key: <key>`
- Everything else → `Authorization: Bearer <key>`

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

## Client Usage

When API keys are configured in the proxy, clients send **no auth header** — the proxy injects it:

### Python requests
```python
import requests

resp = requests.post(
    "https://api.openai.com/v1/chat/completions",
    json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
    proxies={"https": "http://127.0.0.1:8080", "http": "http://127.0.0.1:8080"},
    verify=False,
)
```

### OpenAI SDK
```python
import httpx
from openai import OpenAI

client = OpenAI(
    api_key="dummy",  # proxy overrides this
    http_client=httpx.Client(proxies="http://127.0.0.1:8080", verify=False),
)
```

### Anthropic SDK
```python
import httpx
import anthropic

client = anthropic.Anthropic(
    api_key="dummy",  # proxy overrides this
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
