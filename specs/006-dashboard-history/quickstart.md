# Quickstart: Dashboard Historical Data

**Feature**: 006-dashboard-history
**Date**: 2026-06-27

## Prerequisites

- otel-agent installed with BUG-001/002/003 fixes

## Verify Historical Data

### 1. Start proxy and send requests

```bash
otel-agent proxy

# Send some requests
curl -s http://localhost:8080/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"test 1"}]}'
curl -s http://localhost:8080/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"test 2"}]}'
```

### 2. Start dashboard (after requests are logged)

```bash
otel-agent dashboard
```

### 3. Open browser

```bash
open http://localhost:9090
```

### 4. Verify

- Dashboard shows both "test 1" and "test 2" requests
- Requests are visible even though they were sent BEFORE the dashboard started

### 5. Verify new requests appear

```bash
# Send another request while dashboard is open
curl -s http://localhost:8080/openai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"test 3"}]}'
```

- "test 3" appears in the dashboard within 5 seconds
- "test 1" and "test 2" are still visible

### 6. Verify from different directory

```bash
cd /tmp
otel-agent dashboard
# Open http://localhost:9090 — same data shown
```
