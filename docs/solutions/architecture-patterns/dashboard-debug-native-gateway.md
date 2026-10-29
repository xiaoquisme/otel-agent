---
title: Dashboard Debug delegates execution to native gateway routes
date: 2026-10-29
module: dashboard
problem_type: architecture_pattern
tags: [dashboard, debug, responses, anthropic, model-discovery, telemetry]
---

# Dashboard Debug delegates execution to native gateway routes

## Problem

A text-model debugger must cover Chat Completions, Anthropic and Responses-only subscriptions without copying credential resolution, upstream HTTP, protocol conversion or telemetry. A universal `/v1/responses` caller cannot reach Anthropic; a universal Chat caller cannot reach Responses-only subscriptions. Wrapping every outcome in HTTP 200 would also obscure real gateway errors.

## Solution

`GET /api/debug/models` in `server.create_app` projects the existing `/v1/models` discovery/cache into:

```json
{
  "data": [{"id": "provider/model", "owned_by": "provider", "endpoint": "/v1/messages"}],
  "errors": [],
  "log_request_body": true
}
```

The endpoint is chosen using `serves_only_responses(provider)` first, `api_format == "anthropic"` second, otherwise Chat Completions. Names never decide protocol. Explicit output modalities excluding text hide a model from Debug only; absent capability metadata does not hide it from either catalog.

The browser posts a fixed single-turn body straight to that same-origin native `/v1/*` endpoint. It never receives provider URLs, keys or authorization headers, and it cannot select an arbitrary endpoint. Native Anthropic avoids an unnecessary response conversion and preserves its native errors and usage. Raw JSON is the gateway's client-facing response, not necessarily upstream bytes (Responses-only streams are folded by the existing gateway).

Chat omits optional generation parameters: forcing legacy `max_tokens` would exclude models that require a newer parameter. Anthropic requires `max_tokens`, so Debug supplies 1,024 there. Responses-only uses the gateway's existing stream-folding and parameter accommodations. The page warns about quota/charges, prompt logging and retained response telemetry.

Discovery now distinguishes safe `model_discovery_error` summaries from existing `credential_error` failures. Neither is cached as an empty successful list. Aggregation keeps successful providers. A provider-specific failed catalog is HTTP 502; a credential failure retains HTTP 503. Catalog requests reuse `build_request_headers`; Anthropic also reuses the `/v1` URL normalization. GET removes the body-only Content-Type header to preserve the established header contract.

## Verification

- `tests/test_dashboard_debug.py`: mocked native upstream HTTP/SSE, misleading model names, partial HTTP/transport/malformed/credential failures, native Anthropic discovery, modality filtering, native success/HTTP errors/unknown models, SSE failures, real telemetry and both logging settings.
- `frontend/tests/debug.test.mjs`: Node built-in test runner (Node 22 with type stripping), mocked fetch, fixed native bodies, status/raw errors, non-JSON/network errors, Responses incomplete/failed status and endpoint allowlist. Run `cd frontend && npm test`.
- Local browser fixture exercised all three protocols, HTTP 429, partial-discovery warning, HTML-like text rendered without script elements, double-click prevention (one POST), and a 375px narrow layout probe without horizontal content overflow. No real model requests.
- Build and synchronize `src/otel_agent/dashboard/frontend_dist/`; installation/restart remains a separate authorized shipping step.

## Boundaries

This is not a new execution API, a conversation editor, arbitrary JSON/URL tooling, a credential UI or a multimodal client. It inherits the gateway's access control, model catalog TTL and upstream timeout behavior. Providers without a working catalog still need their existing `models` / `models_from` configuration. Successful HTTP 200 responses carrying an error or an unfinished Responses status are displayed as failed/not completed, without falsifying their actual HTTP status.
