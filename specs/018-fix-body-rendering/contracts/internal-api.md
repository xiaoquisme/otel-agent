# Internal API Contract: Body Storage Limits

**Date**: 2026-07-10
**Feature**: 018-fix-body-rendering

## Contract: Dashboard Response Body Size

The internal dashboard API (`/internal/dashboard/requests/{id}`) returns request/response bodies that may now be up to 500KB (previously 100KB).

### Before

```
GET /internal/dashboard/requests/864
Response: { "request_body": "<up to 100KB>", "response_body": "<up to 100KB>" }
```

### After

```
GET /internal/dashboard/requests/864
Response: { "request_body": "<up to 500KB>", "response_body": "<up to 500KB>" }
```

### Impact

- Dashboard clients must handle larger JSON payloads (up to ~1MB total per request detail)
- No API signature change — just larger payloads
- Streaming preview field (`response_body.streamed.preview`) may now be up to 5,000 chars (was 500)

## Contract: Truncation Indicator (Dashboard Client-Side)

When a body is truncated, the dashboard renders a visual indicator:

```
┌─────────────────────────────────────────────┐
│ ⚠ Body truncated (original exceeded 500KB) │
└─────────────────────────────────────────────┘
```

This is purely client-side — no server-side truncation metadata is added.
