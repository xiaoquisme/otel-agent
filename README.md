# otel-agent — LLM Telemetry Proxy

Intercept, log, and redirect LLM API calls. Config-driven key rotation with path-based routing and a web dashboard.

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

# 3. Start proxy (runs in background)
otel-agent proxy

# 4. Open web dashboard
otel-agent dashboard

# 5. Send requests
curl http://localhost:8080/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}'
```

## Commands

```
otel-agent --version          Print version
otel-agent init               Create default config file
otel-agent proxy              Start proxy in background
otel-agent proxy stop         Stop the running proxy
otel-agent proxy restart      Restart the proxy
otel-agent proxy status       Check if proxy is running
otel-agent proxy logs         View proxy log output
otel-agent proxy --foreground Run in foreground (blocking)
otel-agent routes             Display routing table
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

## Path-Based Routing

Requests are routed by provider type path prefix to the active provider:

```
/openai/v1/chat/completions    → active OpenAI provider's base_url
/anthropic/v1/messages         → active Anthropic provider's base_url
```

```bash
otel-agent routes  # View active provider assignments
```

## Config File

`~/.otel-agent/config.yaml`:

```yaml
providers:
  openai:
    - name: primary
      base_url: https://api.openai.com/v1
      api_key: sk-proj-key1
      active: true
    - name: backup
      base_url: https://api.deepseek.com
      api_key: sk-backup-key
      active: false

  anthropic:
    - name: primary
      base_url: https://api.anthropic.com
      api_key: sk-ant-key1
      active: true
```

Exactly one provider per type must be marked `active: true`. Requests to
`/openai` are forwarded to the active OpenAI provider; `/anthropic` to
the active Anthropic provider.

## Proxy Management

```bash
otel-agent proxy              # Start in background
otel-agent proxy --foreground # Run in terminal (blocking)
otel-agent proxy stop         # Stop
otel-agent proxy restart      # Restart
otel-agent proxy status       # Check status
otel-agent proxy logs         # View logs
otel-agent proxy logs -F      # Stream logs (tail -f)
```

## Client Usage

### OpenAI SDK

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8080/openai/v1", api_key="dummy")
```

### Anthropic SDK

```python
import anthropic
client = anthropic.Anthropic(base_url="http://localhost:8080/anthropic", api_key="dummy")
```

## Testing

```bash
uv run pytest tests/ -v -m "not integration"
```

## License

MIT
