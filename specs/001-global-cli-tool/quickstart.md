# Quickstart: Global CLI Tool

**Feature**: 001-global-cli-tool
**Date**: 2026-06-26

## Prerequisites

- Python 3.10+
- `uv` installed (https://docs.astral.sh/uv/)

## Install

```bash
# Option 1: Run without installing
uvx otel-agent --version

# Option 2: Install globally
uv tool install otel-agent

# Option 3: pip fallback
pip install otel-agent
```

## First-Time Setup

```bash
# Create config
otel-agent init

# Edit config to add your API keys
otel-agent config edit
```

Verify config:
```bash
otel-agent config show
```

## Start Proxy

```bash
otel-agent proxy
```

Expected output:
```
otel-proxy listening on :8080
logging to telemetry.db
config: ~/.otel-agent/config.yaml
  provider: openai (1/1 keys active)
Ctrl+C to stop
```

## Send a Request Through

```bash
export https_proxy=http://127.0.0.1:8080
curl -k https://api.openai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}'
```

## View Logs

```bash
otel-agent view
otel-agent view --filter openai --limit 5
```

## Health Check

```bash
otel-agent doctor
```

## Custom Port

```bash
otel-agent proxy -p 9090
```

## Custom Config

```bash
otel-agent proxy -c ./my-config.yaml
```
