# Quickstart: Background Proxy Management

**Feature**: 003-background-proxy
**Date**: 2026-06-26

## Prerequisites

- otel-agent installed (`uv tool install git+https://github.com/xiaoquisme/otel-agent.git`)
- Valid config at `~/.otel-agent/config.yaml`

## Start Proxy in Background

```bash
otel-agent proxy
```

Expected output:
```
Proxy started on :8080 (PID 12345)
Logging to ~/.otel-agent/proxy.log
```

Terminal is immediately available for other commands.

## Check Status

```bash
otel-agent proxy status
```

Expected output:
```
Proxy running on :8080 (PID 12345)
```

## View Logs

```bash
otel-agent proxy logs
```

Stream logs in real-time:
```bash
otel-agent proxy logs --follow
```

## Stop Proxy

```bash
otel-agent proxy stop
```

Expected output:
```
Proxy stopped.
```

## Restart Proxy

```bash
otel-agent proxy restart
```

Expected output:
```
Proxy stopped.
Proxy started on :8080 (PID 12346)
```

## Foreground Mode (Debugging)

```bash
otel-agent proxy --foreground
```

Runs in terminal (blocking). Ctrl+C to stop.

## Verify

```bash
# Start proxy
otel-agent proxy

# Send a request
curl http://localhost:8080/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}'

# Check logs
otel-agent proxy logs

# Stop
otel-agent proxy stop
```
