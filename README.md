# otel-agent — LLM API Gateway

OpenAI/Anthropic compatible API gateway with model-name-based provider routing and telemetry logging.

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

# 3. Start gateway (runs in background)
otel-agent proxy

# 4. Send requests with model-name routing
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"openai/gpt-4o","messages":[{"role":"user","content":"hi"}]}'
```

## How It Works

The gateway routes requests based on the **model name prefix**:

| Model String | Routes To |
|---|---|
| `openai/gpt-5.4` | OpenAI provider |
| `openrouter/openai/gpt-5.4` | OpenRouter provider (model: `openai/gpt-5.4`) |
| `xiaomi/mimo-v-2.5` | Xiaomi provider |
| `anthropic/claude-sonnet-4` | Anthropic provider |

The first segment before `/` is always the **provider name** (looked up in config).
Everything after the first `/` is the **upstream model name** forwarded to that provider.

## Commands

```
otel-agent --version          Print version
otel-agent init               Create default config file
otel-agent proxy              Start gateway in background
otel-agent proxy stop         Stop the running gateway
otel-agent proxy restart      Restart the gateway
otel-agent proxy status       Check if gateway is running
otel-agent proxy logs         View gateway log output
otel-agent proxy --foreground Run in foreground (blocking)
otel-agent routes             Display provider routing table
otel-agent dashboard          Start web dashboard
otel-agent view               View logged requests (CLI)
otel-agent config path|show|edit  Manage configuration
otel-agent doctor             Check installation health
```

## Web Dashboard

```bash
otel-agent dashboard              # Start on :9090
otel-agent dashboard -p 3000      # Custom port
otel-agent dashboard -d logs.db   # Custom database
```

Open `http://localhost:9090` in a browser.

Features:
- Request table with timestamp, method, URL, status, latency
- Real-time auto-refresh (SSE)
- Text search and method/status filters
- Click row for full request/response details
- Latency chart over time
- CSV/JSON export

## API Endpoints

The gateway exposes both OpenAI-compatible and Anthropic-compatible endpoints:

| Endpoint | Format | Description |
|---|---|---|
| `POST /v1/chat/completions` | OpenAI | Chat completions (streaming supported) |
| `POST /v1/messages` | Anthropic | Messages (streaming supported) |
| `GET /v1/models` | OpenAI | List all available models |
| `GET /health` | — | Health check |

**Cross-format conversion**: If you send an Anthropic-format request to `/v1/messages` but the target provider uses OpenAI format (or vice versa), the gateway automatically converts the request and response formats.

## Config File

`~/.otel-agent/config.yaml`:

```yaml
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-proj-key1
    api_format: openai

  - name: openrouter
    base_url: https://openrouter.ai/api/v1
    api_key: sk-or-key1
    api_format: openai

  - name: xiaomi
    base_url: https://api.xiaomi.com/v1
    api_key: sk-xiaomi-key1
    api_format: openai

  - name: anthropic
    base_url: https://api.anthropic.com
    api_key: sk-ant-key1
    api_format: anthropic
```

Each provider needs:
- `name`: routing key (used as model name prefix)
- `base_url`: upstream API base URL
- `api_key`: authentication key
- `api_format`: `openai` or `anthropic` (default: `openai`)

## Client Usage

### OpenAI SDK

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8080/v1", api_key="dummy")
response = client.chat.completions.create(
    model="openai/gpt-4o",  # or "xiaomi/mimo-v-2.5"
    messages=[{"role": "user", "content": "Hello!"}],
)
```

### Anthropic SDK

```python
import anthropic
client = anthropic.Anthropic(base_url="http://localhost:8080", api_key="dummy")
response = client.messages.create(
    model="anthropic/claude-sonnet-4",  # or "xiaomi/mimo-v-2.5"
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
```

### curl

```bash
# List available models
curl http://localhost:8080/v1/models

# Filter by provider
curl "http://localhost:8080/v1/models?provider=openai"

# OpenAI format
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-4o",
    "messages": [{"role": "user", "content": "hi"}],
    "stream": true
  }'

# Anthropic format
curl http://localhost:8080/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "anthropic/claude-sonnet-4",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "hi"}]
  }'
```

## Testing

```bash
uv run pytest tests/ -v -m "not integration"
```

## License

MIT
