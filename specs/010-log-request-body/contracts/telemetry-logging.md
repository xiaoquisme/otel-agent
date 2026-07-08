# Contract: Telemetry Logger Interface

**Date**: 2026-07-08
**Feature**: 010-log-request-body

## Purpose

Document the interface contract for the `_log_telemetry` helper function and the `TelemetryLogger.log_request` method, which are the boundaries where request body and response header data flow into the database.

## _log_telemetry Function (server.py)

### Current Signature

```python
def _log_telemetry(
    telemetry: TelemetryLogger,
    request: Request,
    status_code: int,
    resp_body: dict | str,
    latency_ms: float,
    provider: Provider,
) -> None:
```

### Updated Signature (proposed)

```python
def _log_telemetry(
    telemetry: TelemetryLogger,
    request: Request,
    status_code: int,
    resp_body: dict | str,
    resp_headers: dict[str, str],   # NEW: upstream response headers
    latency_ms: float,
    provider: Provider,
    request_body: str = "",          # NEW: original client request body
    log_body: bool = True,           # NEW: from config
) -> None:
```

### Behavior Contract

1. When `log_body` is `true`: `request_body` is stored as-is (truncated to 100,000 chars).
2. When `log_body` is `false`: `request_body` is stored as `""`.
3. `resp_headers` is always stored after sensitive header redaction.
4. Sensitive headers (`authorization`, `x-api-key`, `set-cookie`) have values replaced with `[REDACTED]`.
5. All other headers are stored verbatim.

## TelemetryLogger.log_request (logger.py)

**No changes required.** The existing method already accepts `request_body: str` and `response_headers: dict` parameters. The fix is purely at the call site in `server.py`.

## Sensitive Header Redaction

### Input

Raw response headers dict, e.g.:
```json
{
  "content-type": "application/json",
  "x-request-id": "abc-123",
  "authorization": "Bearer sk-..."
}
```

### Output (after redaction)

```json
{
  "content-type": "application/json",
  "x-request-id": "abc-123",
  "authorization": "[REDACTED]"
}
```

### Redacted Headers List

- `authorization`
- `x-api-key`
- `set-cookie`

### Implementation

Case-insensitive matching (HTTP headers are case-insensitive). The redaction function should be a pure function: `dict[str, str] -> dict[str, str]`.

## Config Contract

### New config.yaml field

```yaml
log_request_body: true  # or false to suppress
```

### Config.get behavior

- When key is absent: return `True` (default — log everything)
- When key is present as boolean: return the value
- When key is present as non-boolean: treat as `True` (fail open for logging)
