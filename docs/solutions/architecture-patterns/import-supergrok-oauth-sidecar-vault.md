---
title: "Import SuperGrok OAuth grants into a sidecar vault"
date: "2026-08-17"
category: "architecture-patterns"
module: "auth"
problem_type: "architecture_pattern"
component: "authentication"
severity: "medium"
applies_when:
  - "A consumer LLM subscription (SuperGrok / xai-oauth) must be used from the gateway"
  - "Tokens rotate on refresh and cannot live in mtime-watched config.yaml"
  - "Hermes or Grok CLI already holds a working grant on the same machine"
tags:
  - "xai-oauth"
  - "supergrok"
  - "credential-vault"
  - "token-refresh"
  - "hermes"
---

# Import SuperGrok OAuth grants into a sidecar vault

## Context

otel-agent providers required a static YAML `api_key`. SuperGrok access tokens last about 6 hours and refresh tokens rotate on every refresh. Putting those secrets in `~/.otel-agent/config.yaml` would thrash the mtime hot-reload and, if the same refresh token were shared with Hermes, produce `invalid_grant` for one of the two writers.

A 2026-08-17 live probe showed the Hermes xai-oauth Bearer already works on `POST https://api.x.ai/v1/chat/completions` (including SSE). The gateway did not need a Responses adapter — it needed a place to keep a *copy* of the grant warm.

## Guidance

1. Allow `auth: xai-oauth` with an empty `api_key` (`config.py` validation).
2. Import with `otel-agent auth import-xai` — copy tokens from `~/.hermes/auth.json` (or `~/.grok/auth.json`) into `~/.otel-agent/auth.json` (mode 0600). Do **not** refresh-write Hermes afterward.
3. Resolve Bearers on the hot path (`provider_utils.build_request_headers`, `models.fetch_provider_models`) via `auth_vault.resolve_bearer`.
4. Keep the client model prefix `xai/…`. OAuth is an auth mode, not a second provider name.
5. Rewrite SuperGrok entitlement 403s for humans; do not treat them as circuit-breaker failures (today only connect/timeout trip the breaker).

## Why This Matters

A gateway is a multi-client process. Consumer subscriptions are personal grants. Copy-on-import plus a single vault writer is the only combination that (a) reuses an existing login and (b) does not steal Hermes' rotating refresh chain.

## When to Apply

Adding any short-lived OAuth / subscription credential to a provider that today only has `api_key`. Do not invent a new device-code client until import-from-sibling-CLI is insufficient.

## Examples

```yaml
# config.yaml — no secret
providers:
  - name: xai
    base_url: https://api.x.ai/v1
    auth: xai-oauth
    api_format: openai
```

```bash
otel-agent auth import-xai
# clients: model xai/grok-4.6
```
