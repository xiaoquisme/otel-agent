# Quickstart: Web Dashboard for Request Logs

**Feature**: 004-web-dashboard
**Date**: 2026-06-26

## Prerequisites

- otel-agent installed
- Valid config at `~/.otel-agent/config.yaml`

## Start Proxy and Dashboard

```bash
# Start proxy in background
otel-agent proxy

# Start dashboard
otel-agent dashboard
```

Expected output:
```
Dashboard running at http://localhost:9090
Database: telemetry.db
```

## Open Dashboard

Open `http://localhost:9090` in a browser.

## Send Test Requests

```bash
curl http://localhost:8080/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"hi"}]}'
```

## Verify Dashboard

1. Dashboard shows the request in the table
2. Search for "openai" — only matching requests shown
3. Click a row — full request/response details displayed
4. Latency chart shows data points

## Test Auto-Refresh

Send another request. Verify it appears in the dashboard within 5 seconds without page refresh.

## Test Export

1. Apply a filter (e.g., method = POST)
2. Click "Export CSV"
3. Verify downloaded file contains filtered data

## Custom Port

```bash
otel-agent dashboard -p 3000
```

Open `http://localhost:3000`.
