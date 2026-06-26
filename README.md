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

# 3. Start proxy (runs in background)
otel-agent proxy

# 4. Send requests
curl http://localhost:8080/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}'

# 5. View logs
otel-agent proxy logs

# 6. Stop proxy
otel-agent proxy stop
```

## Commands

```
otel-agent --version          Print version
otel-agent init               Create default config file
otel-agent proxy              Start proxy in background (default)
otel-agent proxy stop         Stop the running proxy
otel-agent proxy restart      Restart the proxy
otel-agent proxy status       Check if proxy is running
otel-agent proxy logs         View proxy log output
otel-agent proxy logs -F      Stream logs in real-time
otel-agent proxy --foreground Run in foreground (blocking)
otel-agent routes             Display routing table
otel-agent view               View logged requests
otel-agent config path|show|edit  Manage configuration
otel-agent doctor             Check installation health
```

## Proxy Management

### Start

```bash
# Background (default)
otel-agent proxy

# Foreground (blocking, for debugging)
otel-agent proxy --foreground

# Custom port
otel-agent proxy -p 9090
```

### Stop / Restart

```bash
otel-agent proxy stop
otel-agent proxy restart
```

### Status

```bash
otel-agent proxy status
```

Output: `Proxy running on :8080 (PID 12345)` or `Proxy is not running.`

### Logs

```bash
otel-agent proxy logs              # Last 50 lines
otel-agent proxy logs -n 100       # Last 100 lines
otel-agent proxy logs -F           # Stream in real-time (Ctrl+C to stop)
```

## Path-Based Routing

Requests are routed by URL path prefix:

```
/openai/v1/chat/completions    → https://api.openai.com/v1/chat/completions
/anthropic/v1/messages         → https://api.anthropic.com/v1/messages
/deepseek/v1/chat/completions  → https://api.deepseek.com/v1/chat/completions
```

### View Routes

```bash
otel-agent routes
```

## Config File

`~/.otel-agent/config.yaml`:

```yaml
default_provider: openai

providers:
  openai:
    type: openai
    prefix: /openai
    base_url: https://api.openai.com/v1
    keys:
      - key: sk-proj-key1
        active: true

  anthropic:
    type: anthropic
    prefix: /anthropic
    base_url: https://api.anthropic.com
    keys:
      - key: ***
        active: true
```

## Client Usage

### OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/openai/v1",
    api_key="dummy",
)
```

### Anthropic SDK

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8080/anthropic",
    api_key="dummy",
)
```

## Testing

```bash
uv run pytest tests/ -v -m "not integration"
```

## License

MIT
