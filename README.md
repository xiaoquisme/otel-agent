# otel-agent — LLM Telemetry Proxy

Intercept, log, and redirect LLM API calls. Config-driven multi-key rotation.

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

# 3. Start proxy
otel-agent proxy

# 4. View logged requests
otel-agent view
```

## Commands

```
otel-agent --version          Print version
otel-agent init               Create default config file
otel-agent proxy              Start the MITM proxy
otel-agent view               View logged requests
otel-agent config path|show|edit  Manage configuration
otel-agent doctor             Check installation health
```

### `otel-agent init`

Creates `~/.otel-agent/config.yaml` with a documented template. Won't overwrite existing config.

```bash
otel-agent init
otel-agent init -c ./custom-config.yaml
```

### `otel-agent proxy`

Start the MITM proxy with config-driven key rotation.

```bash
otel-agent proxy                    # port 8080, default config
otel-agent proxy -p 9090            # custom port
otel-agent proxy -u https://api.anthropic.com  # override upstream
otel-agent proxy -c ./config.yaml   # custom config
```

### `otel-agent view`

Display logged requests.

```bash
otel-agent view                     # last 20 requests
otel-agent view --filter openai     # filter by upstream
otel-agent view --limit 50          # show more rows
```

### `otel-agent config`

Manage configuration without remembering the file path.

```bash
otel-agent config path              # print config file path
otel-agent config show              # display config (keys masked)
otel-agent config edit              # open in $EDITOR
```

### `otel-agent doctor`

Check installation health.

```bash
otel-agent doctor                   # check Python, mitmproxy, config, port
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
```

- **Round-robin** among active keys per provider
- **Hot-reload**: edit the file, changes take effect on next request (no restart)
- Toggle `active: true/false` to enable/disable keys

## Client Usage

### Hermes Agent

```bash
hermes config set model.base_url http://127.0.0.1:8080
hermes config set model.api_key dummy
```

### Claude Code

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8080
export ANTHROPIC_API_KEY=*** -p "your task"
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

## Testing

```bash
uv run pytest tests/ -v -m "not integration"
```

## License

MIT
