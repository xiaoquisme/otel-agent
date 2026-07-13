# Dashboard Usage API Contract

## Purpose

Provide the current dashboard with one compact, server-aggregated usage summary for a viewer-local day without exposing direct concurrent reads of the active telemetry database.

## Public dashboard endpoint

### `GET /api/usage`

Returns usage for an explicitly supplied UTC interval.

#### Query parameters

| Name | Required | Format | Rules |
|---|---:|---|---|
| `start` | yes | ISO-8601 UTC instant | Inclusive start of the interval. |
| `end` | yes | ISO-8601 UTC instant | Exclusive end of the interval; must be after `start` and no more than 48 hours later. |

Invalid, missing, reversed, or oversized ranges return HTTP 400 with a JSON error message.

#### Success response: HTTP 200

```json
{
  "start": "2026-07-11T00:00:00.000Z",
  "end": "2026-07-12T00:00:00.000Z",
  "total_tokens": 1800,
  "input_tokens": 1200,
  "output_tokens": 600,
  "eligible_request_count": 3,
  "excluded_request_count": 1,
  "models": [
    {
      "model_name": "openai/gpt-4o",
      "total_tokens": 1300,
      "input_tokens": 900,
      "output_tokens": 400,
      "request_count": 2
    },
    {
      "model_name": "anthropic/claude-sonnet",
      "total_tokens": 500,
      "input_tokens": 300,
      "output_tokens": 200,
      "request_count": 1
    }
  ]
}
```

#### Empty response semantics

If no completed records exist in the interval, return HTTP 200 with zero totals, zero counts, and an empty `models` list. This is not an error.

## Internal proxy endpoint

### `GET /internal/dashboard/usage`

Uses the same `start` and `end` query parameters and response schema as `/api/usage`.

The standalone dashboard server calls this endpoint when its configured proxy is available. It must preserve the existing fallback behavior for offline dashboard use, while avoiding direct concurrent DuckDB access when the proxy is active.

## Browser behavior contract

1. On initial dashboard load and each live-refresh event, calculate the viewer's local start of day and next local start of day, convert both to UTC ISO-8601 strings, and request `/api/usage`.
2. Render a loading, success, and non-blocking error state independently from the request list.
3. Render totals with text labels and numeric values. The model table must preserve the API ordering.
4. Display `excluded_request_count` only when non-zero, with copy that explains usage was unavailable rather than presenting an error.
5. Escape model labels and all dynamic text before insertion into the document.

## Compatibility

- Existing dashboard endpoints retain their request and response shapes.
- Usage fields are additive telemetry data; historical records may produce a non-zero excluded count.
- This contract intentionally excludes cost, quotas, alerts, and arbitrary date-range UI controls.
