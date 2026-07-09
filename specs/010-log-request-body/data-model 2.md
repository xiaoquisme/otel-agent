# Data Model: Log Request Bodies and Response Headers to Database

**Date**: 2026-07-08
**Feature**: 010-log-request-body

## Entity: Telemetry Record (requests table)

No schema migration required. Existing columns `request_body TEXT` and `response_headers TEXT` are already present but currently store empty values.

### Field Transitions

| Field | Before | After |
|-------|--------|-------|
| `request_body` | Always `""` (empty string) | Original client JSON body (up to 100,000 chars) or `""` when `log_request_body: false` |
| `response_headers` | Always `{}` (empty JSON object) | Upstream provider response headers as JSON, with sensitive values redacted to `[REDACTED]` |

### Field: request_body

- **Type**: TEXT (JSON string)
- **Source**: Original client request body (before format conversion)
- **Max size**: 100,000 characters (truncated if exceeded)
- **When disabled**: Empty string `""` when `log_request_body: false`
- **Content**: Full JSON of the client's request (e.g., `{"model":"openai/gpt-5.4","messages":[...]}`)

### Field: response_headers

- **Type**: TEXT (JSON object string)
- **Source**: Upstream HTTP response headers (`resp.headers` from httpx)
- **Redaction**: Sensitive header values replaced with `[REDACTED]`
- **Sensitive headers list**: `authorization`, `x-api-key`, `set-cookie`
- **Content**: JSON object like `{"content-type":"application/json","x-request-id":"abc123","authorization":"[REDACTED]"}`

## Entity: Configuration (config.yaml)

### New Field: log_request_body

- **Type**: boolean
- **Default**: `true` (when absent from config)
- **Location**: Top-level key in `config.yaml`
- **Hot-reload**: Yes (inherits existing mtime-based reload mechanism)
- **Effect on request_body**: When `false`, `request_body` is stored as `""`
- **Effect on response_headers**: None — response headers are always logged regardless of this setting

### Example config additions

```yaml
# Existing
providers:
  - name: openai
    ...

# New (optional)
log_request_body: true
```

## No Relationships Changes

The existing single-table `requests` schema is sufficient. No new tables, indexes, or foreign keys needed.
