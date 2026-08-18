---
title: "xAI SuperGrok device-code login without Hermes or Grok CLI"
type: "feat"
date: "2026-08-17"
topic: "xai-oauth-device-code-login"
artifact_contract: "ce-unified-plan/v1"
artifact_readiness: "implementation-ready"
product_contract_source: "user-requirement"
execution: "code"
supersedes_ktd: "docs/plans/2026-08-17-004-feat-xai-oauth-subscription-plan.md KTD1"
---

## Goal Capsule

- **Objective:** Let an operator who has SuperGrok (and no Hermes / Grok CLI) mint a grant into `~/.otel-agent/auth.json` via RFC 8628 device-code, then keep using `xai/grok-4.6` through the existing vault + resolver.
- **Product authority:** User requirement after PR #16: other otel-agent users do not install Hermes or Grok CLI, so `auth import-xai` is insufficient. Prior slice (plan 004 / PR #16) remains the vault, resolver, import, and 403 rewrite.
- **Open blockers:** None. Reuse the public Grok/Hermes `client_id` already used for refresh. Do not register a new xAI application in this slice.

## Product Contract

### Problem Frame

PR #16 made otel-agent a token consumer: copy a grant from Hermes/Grok, refresh only the sidecar vault. That path is empty when the operator never installed those CLIs. Those users still need a first-party way to authorize SuperGrok.

The gateway is a daemon (`0.0.0.0` bind). Device-code must be an explicit TTY command, not something that blocks `otel-agent proxy` startup.

### Actors

- **Standalone operator** — SuperGrok subscriber, no Hermes/Grok CLI; runs `otel-agent auth login` in a terminal, completes xAI's verification page in a browser.
- **Hermes operator** — still can `otel-agent auth import-xai` (unchanged).
- **Gateway** — unchanged after the grant lands: `resolve_bearer` + 3600s refresh, single vault writer.
- **Client** — still `model: "xai/grok-4.6"`.

### Key Flows

#### F1. Device-code login (primary for standalone users)

Operator runs `otel-agent auth login` → CLI fetches OIDC discovery → POST device-code with public client_id + SuperGrok scopes → prints verification URL and user code, optionally opens the browser → polls token endpoint until authorized / denied / timeout → `save_grant(..., imported_from="device-code")` → upsert YAML `name: xai`, `auth: xai-oauth`. Never writes `~/.hermes/auth.json` or `~/.grok/auth.json`.

#### F2. Import remains a shortcut

`otel-agent auth import-xai` unchanged. If both are possible, operator chooses; login overwrites the vault entry for `xai` (new grant, new refresh chain).

#### F3. Status / doctor

`auth status` and `doctor` distinguish `device-code` vs `hermes` / `grok-cli`. Missing grant tells standalone users to run `auth login` first, and mentions `import-xai` as the Hermes shortcut.

#### F4. Existing proxy traffic

After login, F2/F3 from plan 004 apply unchanged (warm request, entitlement 403 rewrite).

### Requirements

- R1. `otel-agent auth login` runs RFC 8628 against `https://auth.x.ai` using the same public client_id and scopes Hermes uses. No new xAI app registration.
- R2. Tokens land only in `~/.otel-agent/auth.json` (0600) via existing `save_grant`. `imported_from` is `device-code`.
- R3. CLI prints URL + user code. Open the system browser when a graphical session is available; `--no-browser` skips that. Remote/SSH/no-DISPLAY never auto-opens.
- R4. Poll handles `authorization_pending`, `slow_down` (bump interval, cap 30s), success (require access + refresh), explicit errors, and expiry timeout. Never print token values.
- R5. Login upserts the `xai` provider the same way import does (`auth: xai-oauth`, `base_url: https://api.x.ai/v1`).
- R6. `import-xai` stays. Help/status/doctor present login as the default path for users without those CLIs.
- R7. Refresh / missing-grant error strings point at `otel-agent auth login` (import remains documented in README).
- R8. No device-code during `proxy` / dashboard startup. No dashboard login UI in this slice.
- R9. README documents both paths: login (no extra CLI) and import (Hermes/Grok already signed in).

### Acceptance Examples

#### AE1. Login without Hermes files

```
Given no ~/.hermes/auth.json and no ~/.grok/auth.json
When otel-agent auth login completes device-code
Then ~/.otel-agent/auth.json exists mode 0600 with imported_from=device-code
And config has name:xai auth:xai-oauth
And ~/.hermes/auth.json was not created
```

#### AE2. Pending then success

```
Given the token endpoint returns authorization_pending then 200 with access+refresh
When login polls
Then the grant is saved and the process exits 0
```

#### AE3. Denied / timeout

```
Given access_denied or poll deadline
When login finishes
Then exit non-zero, vault is unchanged, no tokens printed
```

#### AE4. Import still works

```
Given ~/.hermes/auth.json has xai-oauth tokens
When otel-agent auth import-xai
Then behavior matches plan 004 AE1
```

### Scope Boundaries

**In scope:** TTY `auth login`, device-code request/poll, browser open + `--no-browser`, vault `imported_from=device-code`, status/doctor/README copy, tests with mocked httpx.

**Out of scope:** Registering a new xAI `client_id`; dashboard / web login; embedding login in `proxy` startup; writing Hermes or Grok auth stores; PKCE loopback; Responses adapter; changing `0.0.0.0` bind.

**Deferred:** Official first-party client_id if xAI later allowlists by client; dashboard device-code (print URL in UI, poll server-side).

## Planning Contract

### Assumptions

- The public Grok CLI client_id (`b1a00492-073a-47ea-816f-4c329264a828`) still issues device codes for SuperGrok. Hermes `hermes_cli/auth.py` is the reference implementation (`_xai_oauth_request_device_code`, `_xai_oauth_poll_device_token`, `_xai_oauth_device_code_login`).
- Starting a *new* device-code session as otel-agent against that client_id is acceptable for this product. Plan 004 KTD1 ("token-consumer only") is revised for operators who have no grant to import. We still do not register a new app.
- Live probe from 2026-08-17 still holds: the resulting Bearer works on `POST /v1/chat/completions`.
- Login is interactive and not run in CI.

### Key Technical Decisions

**KTD1. Reuse Hermes/Grok public client_id and scopes.** Do not open an xAI developer app. Rationale: same grant shape the vault already refreshes; registering a client is a product/legal step and would block this slice.

**KTD2. New grant, own refresh chain.** Device-code mint is written only to the sidecar vault. Never seed or refresh-write Hermes. If the operator later runs Hermes login on the same machine, the two grants are independent (same as import-then-copy).

**KTD3. Protocol lives next to the vault, CLI only prints and upserts.** Put request/poll in `auth_vault.py` (or a thin `xai_oauth.py` if `auth_vault.py` would exceed one responsibility). `commands/auth_cmd.py` owns TTY, browser, `--no-browser`, exit codes. Tests mock HTTP, not the terminal, except a small CLI parser test.

**KTD4. Browser is best-effort.** Match Hermes: skip auto-open on SSH / missing DISPLAY / `--no-browser`. Always print the complete verification URL and user code so headless operators can finish on another device.

**KTD5. Login overwrites provider `xai`.** One SuperGrok grant per gateway. Re-login replaces tokens; do not keep a pool in this slice.

### Technical Design

```
otel-agent auth login [--no-browser] [-c config]
        │
        ├─ GET  https://auth.x.ai/.well-known/openid-configuration
        ├─ POST https://auth.x.ai/oauth2/device/code
        │     client_id=b1a00492-…  scope=openid profile email offline_access grok-cli:access api:access
        ├─ print verification_uri_complete + user_code
        ├─ optional webbrowser.open
        └─ POST token_endpoint  grant_type=urn:ietf:params:oauth:grant-type:device_code
              pending → sleep(interval)
              slow_down → interval = min(interval+1, 30)
              200 + access + refresh → save_grant(imported_from="device-code") + upsert_provider
              error / timeout → AuthError, exit 1
```

Constants (already used for refresh, add the two device-code ones):

- client_id: `b1a00492-073a-47ea-816f-4c329264a828`
- device code URL: `https://auth.x.ai/oauth2/device/code`
- scope: `openid profile email offline_access grok-cli:access api:access`
- token URL: discovery `token_endpoint`, fallback `https://auth.x.ai/oauth2/token`

`save_grant` already requires access + refresh and derives `expires_at` from JWT `exp` or `expires_in`. Login should pass through discovery so later refresh skips a discovery GET when possible.

Partial tree note: a previous turn started adding device-code constants and relogin hint strings to `auth_vault.py`; that diff was reverted. Implement from this plan, not from leftover WIP.

### Risks

- **xAI allowlist / client misuse.** Same public client Hermes uses. If device-code starts failing for non-Grok-CLI user-agents, surface the HTTP body and stop; do not silently retry import.
- **Interactive timeout.** Device `expires_in` is the poll deadline; do not invent a shorter default that cuts off the user.
- **Two writers if user also runs Hermes on the same grant.** Login creates a *new* grant, so this is safe. Warning: do not document "log in here then import back to Hermes."

## Implementation Units

### U1. Device-code request + poll (no TTY)

**Goal:** Pure functions that request a device code and poll until tokens or a typed error.
**Files:** `src/otel_agent/auth_vault.py` (or new `src/otel_agent/xai_oauth.py` imported by the vault/CLI), `tests/test_auth_vault.py`
**Approach:** Mirror Hermes field checks (`device_code`, `user_code`, `verification_uri`, `verification_uri_complete`, `expires_in`, `interval`). Inject `httpx.Client` (or monkeypatch) in tests. Cover pending→success, slow_down interval bump, missing refresh_token, access_denied, timeout. Sleep must be patchable.
**Depends:** none (vault `save_grant` already exists)

### U2. `otel-agent auth login` TTY command

**Goal:** Operator-facing login: print instructions, optional browser, save grant, upsert `xai` provider.
**Files:** `src/otel_agent/commands/auth_cmd.py`, `src/otel_agent/cli.py`, `tests/test_cli.py`, `tests/test_auth_login.py` (or extend `test_auth_vault.py`)
**Approach:** Add `login` to `auth_action` choices. `--no-browser` on the auth parser. Detect remote session conservatively (SSH_CONNECTION / SSH_TTY / no DISPLAY on Linux). Open `verification_uri_complete`. On success call existing `save_grant` + `upsert_provider`. Exit 1 on `AuthError` with the message only.
**Depends:** U1

### U3. Status, doctor, refresh hints

**Goal:** Standalone users are told to `auth login`; Hermes users still see import.
**Files:** `src/otel_agent/commands/auth_cmd.py`, `src/otel_agent/commands/doctor.py`, `src/otel_agent/auth_vault.py` (error strings from `resolve_bearer` / `_refresh`)
**Approach:** Status: if logged in, print `imported_from`; if not, print login as primary and import as optional. Doctor line matches. Refresh/missing-grant errors say `otel-agent auth login`.
**Depends:** U2 for command name stability

### U4. Docs

**Goal:** README + DEFAULT_CONFIG comment list login first, import second.
**Files:** `README.md`, `src/otel_agent/config.py` DEFAULT_CONFIG
**Depends:** U2

## Verification Contract

```
uv run pytest tests/test_auth_vault.py tests/test_cli.py tests/test_config.py -q
uv run pytest tests/ -q -m "not integration"
```

No live xAI calls in CI. Device-code tests are fully mocked.

Optional local smoke (not CI): on a machine without using the existing Hermes grant, `otel-agent auth login` then `xai/grok-4.6` through the proxy. Do not commit the resulting vault.

## Definition of Done

- R1–R9 covered by tests (R3 browser skip + R8 no proxy hook + R9 README).
- `import-xai` tests still pass.
- Login success test asserts Hermes/Grok paths are not written.
- `otel-agent auth --help` lists `login`.
- Plan 004 behavior (empty api_key, resolver, 403 rewrite) unchanged.

## Appendix

- Hermes reference: `~/.hermes/hermes-agent/hermes_cli/auth.py` around `_xai_oauth_request_device_code` / `_xai_oauth_poll_device_token` / `_xai_oauth_device_code_login` (approx. lines 7974–8120).
- Prior plan: `docs/plans/2026-08-17-004-feat-xai-oauth-subscription-plan.md` — this slice revises KTD1 only for minting; KTD2–KTD5 (copy vault, `auth: xai-oauth` on `xai`, resolver, 403 presentation) stay.
- PR in flight: https://github.com/xiaoquisme/otel-agent/pull/16 — land this as a follow-up commit on `feat/xai-oauth-subscription` unless that PR merges first.
