---
title: "Image API Support - Plan"
type: feat
date: 2026-08-26
topic: image-api-support
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
execution: code
---

# Image API Support - Plan

## Goal Capsule

**Objective:** Add OpenAI-compatible image API support to otel-agent — image generation proxy and vision/multimodal content passthrough.

**Product authority:** The gateway already proxies OpenAI/Anthropic chat completions. Image support extends this to cover image generation endpoints and multimodal content parts in chat messages.

**Open blockers:** None — scope is clear, only OpenAI format supported.

## Product Contract

### Summary

Add two image capabilities to the otel-agent LLM API gateway: (1) a `/v1/images/generations` endpoint that proxies image generation requests to OpenAI-format providers, and (2) support for `image_url` content parts in `/v1/chat/completions` so vision/multimodal requests pass through correctly to OpenAI-format providers.

### Problem Frame

The gateway currently has no image-related API support. Users who need image generation or vision/multimodal capabilities must call provider APIs directly, bypassing all gateway value: logging, auto-routing, rate limiting, and cost tracking. Additionally, the converter pipeline silently drops `image_url` content parts during cross-format conversion, but this is not an issue for the OpenAI→OpenAI passthrough path which is the only path we're supporting.

### Key Decisions

- **OpenAI format only.** No Anthropic image format conversion. If the upstream provider is Anthropic and the request contains image content, the gateway returns an error. This avoids the complexity of format conversion while covering the primary use case.
- **Passthrough, not transformation.** Image content passes through the gateway unchanged. The gateway does not inspect, resize, or transform image data — it preserves the payload exactly as received.
- **Reuse existing patterns.** The image generation endpoint follows the same pattern as `/v1/chat/completions`: model name parsing → provider resolution → upstream forwarding.

### Requirements

**Image Generation**

- R1. The gateway exposes a `POST /v1/images/generations` endpoint that accepts OpenAI-format image generation requests.
- R2. The endpoint parses the `model` field using the existing `provider/model` routing convention.
- R3. The request is forwarded to the upstream provider's `/images/generations` endpoint with the same request body.
- R4. If the upstream provider uses Anthropic API format, the endpoint returns a 400 error with a message indicating image generation is not supported for that provider.
- R5. Request and response telemetry is logged using the existing `_log_telemetry` function.

**Vision/Multimodal in Chat**

- R6. When a client sends a `/v1/chat/completions` request containing `image_url` content parts and the upstream provider uses OpenAI API format, the content parts are passed through to the upstream unchanged.
- R7. The existing `openai_to_anthropic_request` converter does not need modification — it only fires when the upstream is Anthropic, and we are not supporting image content for Anthropic providers in this version.

**Telemetry**

- R8. Image generation requests appear in the dashboard request log with the same fields as chat completion requests (method, URL, status, latency, model).
- R9. The `model` field in telemetry reflects the provider-prefixed model name (e.g., `openai/dall-e-3`).

### Scope Boundaries

**In scope:**
- `/v1/images/generations` endpoint
- `image_url` content part passthrough for OpenAI-format providers
- Telemetry logging for image requests

**Deferred (not in this version):**
- Anthropic image format conversion
- Image generation for non-OpenAI providers
- `/v1/images/edits` and `/v1/images/variations` endpoints
- Vision content in streaming responses
- Dashboard image rendering (displaying images in the UI)
- Image-specific telemetry fields (content_type, image_count)

### Acceptance Examples

- AE1. `POST /v1/images/generations` with `model: "openai/dall-e-3"` → request forwarded to `https://api.openai.com/v1/images/generations`, response returned to client, telemetry logged.
- AE2. `POST /v1/images/generations` with `model: "anthropic/claude-3"` → 400 error: "Provider 'anthropic' uses Anthropic API format which does not support image generation."
- AE3. `POST /v1/chat/completions` with `image_url` content part and `model: "openai/gpt-4o"` → request forwarded with image_url intact, response returned normally.
- AE4. All existing tests continue to pass (295 tests, no regressions).

---

## Planning Contract

### Key Technical Decisions

**KTD1: Reuse `_handle_non_streaming` for image generation.**
Image generation is a synchronous request-response pattern, same as non-streaming chat completions. The existing `_handle_non_streaming` function handles URL construction, upstream forwarding, telemetry logging, and error handling. No new handler needed.

**KTD2: `build_image_upstream_url` as a separate function.**
The image generation path (`/images/generations`) differs from chat completions (`/chat/completions`). A dedicated URL builder keeps the routing logic clean and avoids conditional branching in `build_upstream_url`.

**KTD3: Vision passthrough requires no code changes.**
When `source_format == target_format` (OpenAI→OpenAI), the request body passes through unchanged. The `needs_conversion` flag in `chat_completions` is `False` for OpenAI-format providers, so `openai_to_anthropic_request` is never called. Image content parts survive the passthrough path naturally.

### Assumptions

- OpenAI-format providers expose `/images/generations` at the same base URL as `/chat/completions`.
- The `parse_model` / `resolve_provider` pipeline works for image generation models (e.g., `openai/dall-e-3`).
- The existing `_log_telemetry` function handles image generation responses without modification (the response body is a JSON dict, same as chat completions).

---

## Implementation Units

### U1. Image Generation Endpoint

**Goal:** Add `POST /v1/images/generations` endpoint to server.py.

**Requirements:** R1, R2, R3, R4, R5

**Dependencies:** None (standalone)

**Files:**
- `src/otel_agent/server.py` (modify — add endpoint)
- `src/otel_agent/provider_utils.py` (modify — add `build_image_upstream_url`)
- `tests/test_server.py` (modify — add image generation tests)

**Approach:**
1. Add `build_image_upstream_url` to `provider_utils.py` — builds `{base_url}/images/generations`.
2. Import it in `server.py`.
3. Add the `/v1/images/generations` endpoint between the messages endpoint and the models endpoint.
4. Follow the same pattern as `chat_completions`: parse model → resolve provider → check api_format → build URL → forward → log telemetry.
5. Return 400 for Anthropic providers with a clear error message.

**Patterns to follow:**
- `src/otel_agent/server.py:82-136` — the `chat_completions` endpoint pattern.
- `src/otel_agent/server.py:196-242` — the image generation endpoint (already implemented).

**Test scenarios:**
- Happy path: valid OpenAI model → request forwarded, response returned, telemetry logged.
- Anthropic provider → 400 error with descriptive message.
- Invalid model format → 400 error from `parse_model`.
- Unknown provider → 400 error from `resolve_provider`.
- Connection error → 502 error body logged to telemetry.
- Timeout → 504 error body logged to telemetry.

**Verification:** Run `uv run pytest tests/test_server.py -x -q` — all existing tests pass, new image generation tests pass.

### U2. Vision Passthrough Verification

**Goal:** Verify that `image_url` content parts survive the OpenAI→OpenAI passthrough path.

**Requirements:** R6, R7

**Dependencies:** U1

**Files:**
- `tests/test_server.py` (modify — add vision passthrough test)

**Approach:**
1. Add a test that sends a `/v1/chat/completions` request with `image_url` content parts to an OpenAI-format provider.
2. Verify the request body is forwarded unchanged (image_url parts intact).
3. This is a verification-only unit — no production code changes needed (the passthrough works by design when `needs_conversion` is False).

**Patterns to follow:**
- `tests/test_server.py` — existing chat completion test patterns.

**Test scenarios:**
- Request with `image_url` content part and OpenAI provider → forwarded with image_url intact.
- Request with mixed content (text + image_url) → all parts forwarded.
- Request with only `image_url` (no text) → forwarded correctly.

**Verification:** Run `uv run pytest tests/test_server.py -x -q` — vision passthrough tests pass.

### U3. Telemetry for Image Requests

**Goal:** Verify image generation requests appear in telemetry with correct fields.

**Requirements:** R8, R9

**Dependencies:** U1

**Files:**
- `tests/test_server.py` (modify — add telemetry verification test)

**Approach:**
1. Add a test that sends an image generation request and verifies the telemetry log entry.
2. Check that `method`, `url`, `status`, `latency_ms`, and `model_name` fields are populated correctly.
3. Verify `model_name` is provider-prefixed (e.g., `openai/dall-e-3`).

**Patterns to follow:**
- `tests/test_telemetry.py` — existing telemetry logging test patterns.

**Test scenarios:**
- Image generation request → telemetry entry has correct method (POST), URL, status (200), latency, and model name.
- Model name is provider-prefixed in telemetry.

**Verification:** Run `uv run pytest tests/test_telemetry.py tests/test_server.py -x -q` — telemetry tests pass.

---

## Verification Contract

- **Test command:** `uv run pytest tests/ -x -q -m "not integration"`
- **Expected result:** 295+ tests pass, no regressions
- **New tests:** U1 adds image generation endpoint tests, U2 adds vision passthrough tests, U3 adds telemetry verification tests
- **Behavioral verification:** Image generation requests are proxied correctly; vision requests pass through unchanged; telemetry logs all image requests

---

## Definition of Done

**Global:**
- All existing 295 tests pass without modification
- New tests cover image generation endpoint, vision passthrough, and telemetry
- No changes to existing converter functions (R7 preserved)
- `build_image_upstream_url` is importable and returns correct URLs

**Per-unit:**
- U1: `/v1/images/generations` endpoint accepts requests, forwards to OpenAI providers, returns 400 for Anthropic providers, logs telemetry
- U2: `image_url` content parts survive the OpenAI→OpenAI passthrough path
- U3: Image generation telemetry entries have correct fields and provider-prefixed model names
