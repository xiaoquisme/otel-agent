# Quickstart: Log Request Bodies and Response Headers to Database

**Date**: 2026-07-08
**Feature**: 010-log-request-body

## Prerequisites

- otel-agent installed (`uv sync --group dev`)
- A provider configured in `~/.otel-agent/config.yaml`

## Validation Scenarios

### Scenario 1: Request body and response headers stored (non-streaming)

1. Start the gateway: `uv run otel-agent start`
2. Send a request:
   ```bash
   curl -s http://localhost:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"openai/gpt-5.4","messages":[{"role":"user","content":"hi"}]}'
   ```
3. Query the database:
   ```bash
   uv run otel-agent view -d ~/.otel-agent/telemetry.db
   ```
4. **Expected**: Output shows the request body (the full JSON sent) and response headers (containing `content-type`, `x-request-id`, etc. with `authorization` redacted).

### Scenario 2: Streaming request body stored

1. Send a streaming request:
   ```bash
   curl -s http://localhost:8080/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"openai/gpt-5.4","messages":[{"role":"user","content":"hi"}],"stream":true}'
   ```
2. Query the database.
3. **Expected**: `request_body` contains the full original request JSON; `response_headers` contains the upstream headers.

### Scenario 3: log_request_body disabled

1. Add to `~/.otel-agent/config.yaml`:
   ```yaml
   log_request_body: false
   ```
2. Restart the gateway.
3. Send a request and query the database.
4. **Expected**: `request_body` is empty string; `response_headers` are still populated.

### Scenario 4: Sensitive header redaction

1. Send a request and query the database directly:
   ```bash
   sqlite3 ~/.otel-agent/telemetry.db "SELECT response_headers FROM requests ORDER BY id DESC LIMIT 1"
   ```
2. **Expected**: The `authorization` header value is `[REDACTED]`, not a raw token.

### Scenario 5: Large body truncation

1. Send a request with a body > 100,000 characters.
2. Query the database and check `request_body` length.
3. **Expected**: Body is stored but truncated to 100,000 characters; no crash or error.

## Test Commands

```bash
# Run all unit tests
uv run pytest tests/ -v -m "not integration"

# Run specific test files
uv run pytest tests/test_logger.py tests/test_viewer.py tests/test_config.py -v
```
