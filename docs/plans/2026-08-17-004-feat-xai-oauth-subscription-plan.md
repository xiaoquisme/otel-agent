---
title: "xAI SuperGrok OAuth subscription as a gateway provider"
type: "feat"
date: "2026-08-17"
topic: "xai-oauth-subscription"
artifact_contract: "ce-unified-plan/v1"
artifact_readiness: "implementation-ready"
product_contract_source: "ce-ideate"
execution: "code"
---

## Goal Capsule

- **Objective:** Let otel-agent spend a SuperGrok / xAI OAuth grant the same way Hermes does — import the existing `~/.hermes/auth.json` (or `~/.grok/auth.json`) grant, keep it warm in a sidecar vault, and serve `xai/grok-4.6` over the existing OpenAI `chat/completions` path. No new OAuth app, no Responses adapter.
- **Product authority:** Ideation `docs/ideation/2026-08-17-grok-subscription-oauth-ideation.html` (ideas 2, 3, 5, 6). Live probe 2026-08-17: Hermes xai-oauth Bearer returned HTTP 200 on `GET /v1/models`, `POST /v1/chat/completions` (incl. SSE), and `POST /v1/responses`.
- **Open blockers:** None. Probe removed the Responses-only uncertainty.

## Product Contract

### Problem Frame

otel-agent can only load providers with a static YAML `api_key`. SuperGrok users already have a working OAuth grant in Hermes (`~/.hermes/auth.json`, provider `xai-oauth`). That Bearer is a valid `api.x.ai` credential for chat/completions, but:

1. Config validation rejects an empty `api_key`.
2. Headers read `provider.api_key` at request time with no refresh hook.
3. Writing a rotating refresh token into mtime-watched YAML would thrash config and race Hermes.

### Actors

- **Operator** — already logged into Hermes (or Grok CLI); runs `otel-agent auth import-xai` once.
- **Gateway** — long-lived proxy; resolves a live Bearer per request; refreshes ~1h before 6h expiry into its own vault.
- **Client** — any OpenAI-compatible caller using `model: "xai/grok-4.6"` (prefix unchanged).
- **Hermes** — source of the original grant; must not share a rotating refresh writer after import.

### Key Flows

#### F1. Import existing grant
Operator runs `otel-agent auth import-xai` → gateway copies access+refresh from `~/.hermes/auth.json` (fallback `~/.grok/auth.json`) into `~/.otel-agent/auth.json` → writes/updates a YAML provider named `xai` with `auth: xai-oauth` and no secret → doctor reports logged-in.

#### F2. Warm request
Client `POST /v1/chat/completions` `{model:"xai/grok-4.6",...}` → resolver returns current access token (refresh if within 3600s of expiry or missing exp) → existing OpenAI header/path used → upstream 200.

#### F3. Entitlement 403
Upstream returns the overloaded SuperGrok 403 body → gateway forwards 403 but rewrites `error.message` with Hermes-style hint (Premium+ ≠ API, quota URL) → does **not** call `CircuitBreaker.record_failure` (today only connect/timeout trip the breaker).

#### F4. Explicit API key still works
A provider with a real `api_key` and no `auth:` is unchanged.

### Requirements

- **R1.** A provider may omit `api_key` when `auth` is `xai-oauth`. Empty key without `auth` still fails validation.
- **R2.** Model prefix stays `xai/…`. Do not introduce `xai-oauth/` as a required client string.
- **R3.** Live tokens live in `~/.otel-agent/auth.json` (mode 0600), never in `config.yaml`.
- **R4.** Import is copy-on-first-use. After import, refresh writes only the otel-agent vault. Do not write back to `~/.hermes/auth.json`.
- **R5.** All outbound Bearer construction (`provider_utils.build_request_headers`, `models.fetch_provider_models`) goes through a resolver, not `provider.api_key` baked at YAML parse.
- **R6.** Refresh uses xAI token endpoint + the public Hermes/Grok client_id already on the grant (`aud` of the access JWT). Skew 3600s. Rotating refresh token is persisted atomically.
- **R7.** `otel-agent auth import-xai` and `otel-agent auth status`. `doctor` shows xAI OAuth logged-in / missing / refresh-failed without printing tokens.
- **R8.** SuperGrok entitlement 403s get a rewritten message pointing at `https://grok.com/?_s=usage` and stating X Premium+ does not include API access.
- **R9.** Default config / README documents the import path and that subscription tokens are personal (proxy binds `0.0.0.0` today — warn, do not change bind in this slice).

### Acceptance Examples

#### AE1. Import then chat prefix
```
Given ~/.hermes/auth.json has providers.xai-oauth tokens
When otel-agent auth import-xai
Then ~/.otel-agent/auth.json exists mode 0600 and config has name:xai auth:xai-oauth
And POST {model:"xai/grok-4.6"} uses a Bearer from the vault, not YAML
```

#### AE2. Empty key without auth still rejected
```
Given a provider with api_key: "" and no auth field
When Config loads
Then ValueError must have an api_key
```

#### AE3. Refresh does not touch Hermes file
```
Given import completed
When resolver refreshes
Then ~/.otel-agent/auth.json refresh_token changes
And ~/.hermes/auth.json mtime/bytes are unchanged
```

#### AE4. Entitlement rewrite
```
Given upstream 403 body contains "do not have an active grok subscription"
When gateway returns to client
Then status is 403 and message mentions SuperGrok / grok.com/?_s=usage
```

### Scope Boundaries

**In scope:** import, vault, resolver, refresh, prefix `xai`, doctor/auth CLI, 403 rewrite, docs.

**Out of scope:** device-code login UI; new xAI OAuth client_id; Responses/`codex_responses` adapter; `billing_mode` / auto-routing cost model; dashboard login; changing proxy bind from `0.0.0.0`; writing tokens into YAML as a “quick” path.

**Deferred:** generic `auth_type` registry for Codex/Qwen; loopback-only bind for consumer OAuth; live entitlement probe hiding models from `/v1/models`.

## Planning Contract

### Assumptions

- Operator already has a Hermes (or Grok CLI) SuperGrok login. This slice does not implement device-code.
- Live probe (2026-08-17) is still valid: chat/completions accepts the OAuth Bearer.
- Reusing Hermes’ public client_id for *refresh of a grant we copied* is acceptable; we will not start a new device-code against that client as “otel-agent”.
- External web research was blocked in the ideation environment; Hermes source + live probe are the evidence.

### Key Technical Decisions

**KTD1. Token-consumer, not OAuth-client.** Import existing grant; do not register or run device-code. Rationale: probe + existing files; avoids allowlist (#26847) and dual-login.

**KTD2. Copy-on-import into `~/.otel-agent/auth.json`.** Never refresh-write Hermes’ rotating token. Rationale: Hermes `auth.py` documents invalid_grant when two writers share a refresh chain.

**KTD3. `auth: xai-oauth` on a provider named `xai`.** Keep the routing contract. Optional static `api_key` on the same name is a fallback if vault is missing (prefer vault when both exist).

**KTD4. Resolver on the hot path.** Expand `KeyRotator.get_key` (or replace with `resolve_bearer(provider)`) and use it from `build_request_headers` and `fetch_provider_models`. Refresh is synchronous in the request (with a lock) for v1; a background warmer is deferred.

**KTD5. 403 rewrite is presentation only.** Do not change circuit-breaker wiring. Today only `ConnectError`/`TimeoutException` call `record_failure` (`auto_handler.py:197-199`).

### Technical Design

```
config.yaml:  {name: xai, base_url: https://api.x.ai/v1, auth: xai-oauth}
                     │
                     ▼
              resolve_bearer(provider)
                     │
          ┌──────────┴──────────┐
          │ vault hit + fresh   │ → return access_token
          │ vault stale/missing │ → refresh_token grant → atomic rewrite vault
          │ no vault, api_key   │ → return api_key (legacy)
          └─────────────────────┘
                     │
                     ▼
         Authorization: Bearer <token>
         POST {base}/chat/completions
```

Refresh POST: `grant_type=refresh_token`, `client_id=b1a00492-073a-47ea-816f-4c329264a828` (or `aud` from stored JWT), token_endpoint from vault `discovery` or OIDC `https://auth.x.ai/.well-known/openid-configuration`.

Vault schema (minimal):

```json
{
  "providers": {
    "xai": {
      "auth": "xai-oauth",
      "tokens": {"access_token": "...", "refresh_token": "...", "expires_at": 0},
      "discovery": {"token_endpoint": "https://auth.x.ai/oauth2/token"},
      "imported_from": "hermes"
    }
  }
}
```

### Risks

- **Refresh token rotation / invalid_grant** — mitigated by copy-on-import and single writer.
- **Token theft via 0.0.0.0 bind** — documented warning only (R9).
- **xAI allowlist 403 after successful import** — rewrite message; do not loop re-import.

## Implementation Units

### U1. Config: optional api_key when auth is xai-oauth

**Goal:** Load a provider with `auth: xai-oauth` and empty/missing `api_key`.
**Files:** `src/otel_agent/config.py`, `tests/test_config.py`
**Approach:** Add `auth: str = ""` on `Provider`. Validation: require `api_key` XOR (`auth == "xai-oauth"`). Unknown `auth` values error. Update `test_empty_api_key_rejected` to keep the no-auth case; add `test_xai_oauth_allows_empty_api_key`.
**Depends:** none

### U2. Sidecar vault + resolver

**Goal:** `resolve_bearer(provider)` reads/writes `~/.otel-agent/auth.json` (0600), refreshes with 3600s skew, never touches Hermes files.
**Files:** new `src/otel_agent/auth_vault.py`, `src/otel_agent/rotator.py` (or replace), `tests/test_auth_vault.py`
**Approach:** Atomic write (temp + replace). File lock around refresh. Derive `expires_at` from JWT `exp` when present, else `now + expires_in`. Vault path is `~/.otel-agent/auth.json` in production and injected via constructor/env in tests. Unit-test refresh with httpx mock; assert the Hermes path is never opened on refresh.
**Depends:** U1

### U3. Hot path uses resolver

**Goal:** Every upstream Bearer comes from `resolve_bearer`.
**Files:** `src/otel_agent/provider_utils.py`, `src/otel_agent/models.py`, `tests/test_rotator.py`, `tests/test_models.py` as needed
**Approach:** `build_request_headers(provider, bearer=None)` — if bearer omitted, resolve. Tests inject a fake vault.
**Depends:** U2

### U4. Import CLI + doctor status

**Goal:** `otel-agent auth import-xai` and `auth status`; doctor line for xAI OAuth.
**Files:** `src/otel_agent/cli.py`, new `src/otel_agent/commands/auth_cmd.py`, `src/otel_agent/commands/doctor.py`, `tests/test_cli.py`
**Approach:** Parse Hermes `providers.xai-oauth.tokens` and pool fallback; same for `~/.grok/auth.json` if present. Upsert YAML provider `xai` via a small config helper (do not clobber unrelated providers). Never print token values.
**Depends:** U2

### U5. Entitlement 403 rewrite

**Goal:** Match Hermes entitlement strings; append hint + usage URL.
**Files:** new `src/otel_agent/xai_errors.py`, `src/otel_agent/server.py` (and auto_handler non-stream/stream error path if they forward raw JSON), `tests/test_xai_errors.py`
**Approach:** Pure function `rewrite_xai_error(status, body) -> body`. Apply when provider `auth == "xai-oauth"` or base_url host is `api.x.ai`.
**Depends:** none (can land parallel with U1)

### U6. Docs + default config example

**Goal:** README + DEFAULT_CONFIG comment showing `auth: xai-oauth` and import command.
**Files:** `README.md`, `src/otel_agent/config.py` DEFAULT_CONFIG
**Depends:** U4 (command name stable)

## Verification Contract

```
uv run pytest tests/ -v -m "not integration"
```

Must stay green. New unit tests listed on U1–U5. No live xAI calls in CI.

Optional local smoke (not CI): after import, `curl` `xai/grok-4.6` against a foreground proxy.

## Definition of Done

- R1–R9 have a unit test or a doc sentence (R9).
- `test_empty_api_key_rejected` still passes for non-oauth providers.
- Refresh tests never open `~/.hermes/auth.json`.
- CLI `--help` shows `auth`.
- Existing prefix routing tests unchanged.

## Appendix

- Hermes client_id: `b1a00492-073a-47ea-816f-4c329264a828`
- Issuer: `https://auth.x.ai`
- Probe: chat/completions 200, stream SSE + `[DONE]`, models list includes `grok-4.6`
- Circuit breaker does **not** currently count HTTP 403 as failure
