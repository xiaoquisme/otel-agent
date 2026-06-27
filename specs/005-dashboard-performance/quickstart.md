# Quickstart: Dashboard Performance Optimization

**Feature**: 005-dashboard-performance
**Date**: 2026-06-26

## Prerequisites

- otel-agent installed
- Database with at least 100 requests

## Verify Performance

### 1. Start proxy and send requests

```bash
otel-agent proxy
# Send 100+ requests to generate data
for i in $(seq 1 100); do
  curl -s http://localhost:8080/openai/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"gpt-4","messages":[{"role":"user","content":"test '$i'"}]}' > /dev/null &
done
wait
```

### 2. Start dashboard

```bash
otel-agent dashboard
```

### 3. Test initial load

Open `http://localhost:9090` in browser. Verify:
- Page loads in under 1 second
- Table shows requests

### 4. Test search

Type "openai" in search box. Verify:
- Results appear in under 500ms

### 5. Test detail view

Click a request row. Verify:
- Detail panel appears in under 1 second

### 6. Test pagination

Click "Next" page. Verify:
- Page loads in under 500ms
- No visible delay

### 7. Test with large dataset

```bash
# Generate 1000+ requests
for i in $(seq 1 1000); do
  curl -s http://localhost:8080/openai/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"gpt-4","messages":[{"role":"user","content":"bulk '$i'"}]}' > /dev/null &
done
wait
```

Refresh dashboard. Verify initial load still under 2 seconds.

## Benchmark (optional)

```bash
# Time the API directly
time curl -s 'http://localhost:9090/api/requests?limit=50' > /dev/null
time curl -s 'http://localhost:9090/api/requests?limit=50&cursor=500' > /dev/null
time curl -s 'http://localhost:9090/api/requests/1' > /dev/null
```

All should complete in under 100ms.
