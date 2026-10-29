# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

### Sidecar Auth Vault
File at `~/.otel-agent/auth.json` that stores imported OAuth grants (access + rotating refresh). Distinct from `config.yaml`, which only declares provider identity (`auth: xai-oauth`). Refresh writes only this file.

### SuperGrok Grant
A personal xAI OAuth token pair minted by Hermes (`xai-oauth`) or `grok login`. Usable as a Bearer on `api.x.ai` chat/completions. Not the same as `XAI_API_KEY` pay-as-you-go, and not included with X Premium+ alone.

### Codex Grant
A personal ChatGPT Plus / Codex OAuth token pair, adopted once from a sibling CLI's credential store and thereafter owned by the adopter: the sibling's copy is a duplicate of the same rotating chain, not an independent one, so the adopter's first refresh consumes it and the sibling has to re-login. Usable as a Bearer on `chatgpt.com/backend-api/codex`, an endpoint that accepts only streaming Responses requests. Unlike a SuperGrok Grant, its refresh token is single-use and rotates on every refresh, and presenting a consumed one revokes the whole grant family — so it tolerates exactly one writer.

### Responses Chat Compat
The gateway path that lets a Responses-only client use a Chat Completions provider. Distinct from the Codex Grant pass-through, which forwards to an upstream that already speaks Responses and applies that upstream's accommodations. This path translates, and it must not reuse those accommodations.

### Agent Session
A run id stored on each logged gateway request. `X-Otel-Session` wins. When that header is absent, `X-Session-ID` is accepted, then the Pi affinity headers `session_id`, `x-session-affinity`, and `x-client-request-id`. When every session header is missing or blank, the gateway stores an inferred id (`inferred-` plus a short hash of the leading system text and the first user text) so a multi-turn client that sends no session header still forms one trajectory. The hash ignores later turns and is a pure function of that root. A payload with no textual conversation root leaves `session_id` null. One Agent Session is the time-ordered set of calls that share the id — the unit a trajectory view inspects (steps, failures, cumulative tokens). It is not an auth session and not a provider conversation id. Unrelated chats that share the same system text and first user text share an inferred id.

### Session Step
Optional label from `X-Otel-Session-Step` on a logged request inside an Agent Session. It names that gateway call. It does not create a session, it does not define a Session Turn, and body inference does not invent one.

### Session Turn
One user round inside an Agent Session: the consecutive gateway calls whose latest human user text is the same. A later user message starts the next turn. Tool results do not. A call with no textual user message is its own turn. The trajectory page groups steps under these turns. Different session ids are never folded into one turn.

### Session Waste Finding
A deterministic note attached to an Agent Session trajectory. It has a rule id, a severity (`info` or `warn`), the request ids it touches, and a short English explanation. The rules are failed steps, slow steps, retry bursts, near-duplicate calls, token spikes, and heavy requests with little or failed output. Thresholds live in `otel_agent.waste`. A finding is not a model judgment and does not propose a prompt or skill edit.

### Model Capability Metadata
The four optional fields on each `/v1/models` entry — `context_length`, `max_output_tokens` (numbers), `input_modalities`, `output_modalities` (string arrays) — sourced in order: upstream passthrough, then OpenRouter public-catalog backfill (whole-catalog cache, normalized exact id match, stale-on-error), then omission. Never guessed and never hand-declared in config — a missing value means the field is absent, not zero.
