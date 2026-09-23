---
title: Translate Responses clients onto chat-completions providers
date: 2026-09-23
category: architecture-patterns
module: otel_agent.server
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - A Responses-only client such as Codex posts to /v1/responses for a provider that only speaks chat completions
  - Extending the Responses route without changing the Responses-only pass-through
tags:
  - responses
  - chat-completions
  - codex
  - streaming
---

# Translate Responses clients onto chat-completions providers

## Context

Current Codex releases only speak the Responses API. `POST /v1/responses` used to refuse every provider that was not declared Responses-only, with `Provider '{name}' does not serve the Responses API`. That refusal is correct for a route with no translator. It blocks DeepSeek and any other OpenAI-format provider once the client cannot fall back to `/v1/chat/completions`.

The Responses-only pass-through (Codex Grant) must stay a pass-through. Its forced `stream`, `store: false`, `include`, and stripped `temperature` are accommodations of that one upstream.

## Guidance

Put the translator in `src/otel_agent/responses_compat.py`. The route selects it only when the provider is OpenAI-format and not `responses_only`. Anthropic-format providers stay a 400 that names the format. Do not reuse `_handle_streaming`'s same-format path: it emits bare `data:` frames and `data: [DONE]`, which Codex does not treat as a completed response.

Codex HTTP (`supports_websockets = false`) always sends `stream: true`, `store: false`, and `include: ["reasoning.encrypted_content"]`, and sends the whole conversation in `input`. Those fields do not carry conversation state. Drop them. Error, before any upstream call, on `previous_response_id`, `store: true`, and hosted tools (`web_search`, `tool_search`, `namespace`).

The stream Codex parses is `event:` plus `data:` whose JSON `type` matches. Text deltas are `response.output_text.delta`. Items, including function and custom tool calls, are read from `response.output_item.done`, not from `response.function_call_arguments.delta` (Codex ignores that event). The stream must end with `response.completed` whose `response.id` is a string. If `usage` is present it must include `input_tokens`, `output_tokens`, and `total_tokens` as integers; omit it rather than send a partial object. Upstream failures are `response.failed`, then the stream ends, with no `response.completed`.

Custom tools must come back as `custom_tool_call` with `input`, not as `function_call`. Codex dispatches on item type.

## Why This Matters

Sharing the pass-through normalizations with DeepSeek would strip `temperature` and force Responses fields that chat completions rejects. Emitting chat SSE, or ending without `response.completed`, makes Codex report `stream closed before response.completed` even when the model answered.

## When to Apply

Any change to `POST /v1/responses` for a provider that is not Responses-only. Leave `serves_only_responses` on the existing handler.

## Examples

A chat completion `{"choices": [{"message": {"content": "OK"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}}` becomes a Responses object whose output text is `OK` and whose usage uses `input_tokens` / `output_tokens` / `total_tokens`. The upstream URL is `{base}/chat/completions`, from `build_upstream_url`, not `build_responses_upstream_url`.

## Related

- GitHub issue #35
- `docs/solutions/architecture-patterns/import-supergrok-oauth-sidecar-vault.md` — xAI did not need this adapter; that decision does not apply to a client that cannot speak chat completions
- `docs/solutions/runtime-errors/streaming-format-detection-priority.md` — telemetry `format` is the client dialect (`responses`), not whether the upstream streamed
