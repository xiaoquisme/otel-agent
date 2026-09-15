# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

### Sidecar Auth Vault
File at `~/.otel-agent/auth.json` that stores imported OAuth grants (access + rotating refresh). Distinct from `config.yaml`, which only declares provider identity (`auth: xai-oauth`). Refresh writes only this file.

### SuperGrok Grant
A personal xAI OAuth token pair minted by Hermes (`xai-oauth`) or `grok login`. Usable as a Bearer on `api.x.ai` chat/completions. Not the same as `XAI_API_KEY` pay-as-you-go, and not included with X Premium+ alone.

### Codex Grant
A personal ChatGPT Plus / Codex OAuth token pair, adopted once from a sibling CLI's credential store and thereafter owned by the adopter: the sibling's copy is a duplicate of the same rotating chain, not an independent one, so the adopter's first refresh consumes it and the sibling has to re-login. Usable as a Bearer on `chatgpt.com/backend-api/codex`, an endpoint that accepts only streaming Responses requests. Unlike a SuperGrok Grant, its refresh token is single-use and rotates on every refresh, and presenting a consumed one revokes the whole grant family — so it tolerates exactly one writer.
