# Quickstart: Validate Fix Body Rendering

**Date**: 2026-07-10
**Feature**: 018-fix-body-rendering

## Prerequisites

- otel-agent proxy running: `uv run otel-agent proxy`
- Dashboard accessible at `http://127.0.0.1:8080/dashboard/`
- At least one request with a large body (>100KB) in the database

## Validation Scenarios

### Scenario 1: Large Request Body Renders as LLM Chat

1. Start the proxy and send a request with a large system prompt (>200KB body):
   ```bash
   python -c "
   import httpx, json
   body = {'model': 'test', 'messages': [{'role': 'system', 'content': 'x' * 300000}, {'role': 'user', 'content': 'hello'}]}
   httpx.post('http://localhost:8080/v1/chat/completions', json=body, timeout=30)
   "
   ```
2. Open dashboard, click the request
3. **Expected**: Request body shows formatted LLM chat with "system" and "user" role labels
4. **Expected**: No "Content is not valid JSON" error

### Scenario 2: Truncated Body Shows Indicator

1. Find a request where the body was stored at exactly 500KB (or mock one)
2. Open dashboard, click the request
3. **Expected**: If body is truncated, a "Body truncated" banner appears above the raw content
4. **Expected**: Toggle to raw view shows the partial JSON with truncation notice

### Scenario 3: Streaming Response Shows Content

1. Send a streaming request:
   ```bash
   python -c "
   import httpx
   body = {'model': 'test', 'messages': [{'role': 'user', 'content': 'Say hello'}], 'stream': True}
   with httpx.stream('POST', 'http://localhost:8080/v1/chat/completions', json=body, timeout=30) as r:
       for line in r.iter_lines():
           if line.startswith('data: '):
               print(line)
   "
   ```
2. Open dashboard, click the request
3. **Expected**: Response shows reassembled assistant content as formatted markdown
4. **Expected**: Model name and finish reason appear as metadata badges

### Scenario 4: Existing Non-LLM Bodies Unchanged

1. Send a non-LLM request (e.g., GET to a non-existent endpoint)
2. Open dashboard, click the request
3. **Expected**: Body renders as syntax-highlighted JSON (existing behavior preserved)

### Scenario 5: Dashboard Performance

1. Open dashboard with a 500KB body request
2. Click to view details
3. **Expected**: Body renders within 2 seconds, no browser freeze
4. **Expected**: Scrolling through the body is smooth

## Run Commands

```bash
# Run existing tests (no regression)
PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/ -v -m "not integration"

# Manual dashboard test
uv run otel-agent proxy  # start proxy
# open http://127.0.0.1:8080/dashboard/
```
