# Concepts

Shared domain vocabulary for this project — entities, named processes, and status concepts with project-specific meaning. Seeded with core domain vocabulary, then accretes as ce-compound and ce-compound-refresh process learnings; direct edits are fine. Glossary only, not a spec or catch-all.

## Auto-Routing

### Thompson Sampling
A Bayesian bandit algorithm used to select the best provider within a complexity tier. Each provider maintains a Beta distribution (via `ProviderScore`) parameterized by success and failure counts. On each request, a sample is drawn from each provider's distribution, and the provider with the highest sample is selected. This balances exploration (trying less-used providers) with exploitation (picking known-good providers).

### Provider Score
Beta distribution parameters (`successes`, `failures`) for a provider within a tier. Starts at (1.0, 1.0) to avoid degenerate distributions. A `seeded` flag tracks whether cost-based initial bias has been applied — cheaper providers get a higher initial success prior, but only once per provider per tier.

### Tier
A complexity classification for routing requests. Tiers are ordered from cheapest to most expensive: `simple`, `medium`, `complex`, `reasoning`. Each tier maps to a set of providers that support that complexity level. Fallback on circuit-breaker failure tries cheaper tiers first.

### Circuit Breaker
Tracks consecutive failures per provider and excludes providers that exceed a failure threshold. States: `CLOSED` (normal), `OPEN` (excluded, cooldown period), `HALF_OPEN` (probe allowed after cooldown). After `threshold` consecutive failures, the circuit opens. After `cooldown` seconds in OPEN state, transitions to HALF_OPEN to allow a probe request.

### Session Cache
TTL cache that pins multi-turn conversations to the same provider. Keyed on session ID (or a hash of message content for stateless requests). Prevents provider churn within a conversation, which could break context continuity.

### Seed From Costs
Initialization method that gives cheaper providers a higher initial success prior in their Beta distribution. Computes each provider's cost relative to the tier average, then adds a bonus proportional to how much cheaper it is. Only applied once per provider per tier (guarded by the `seeded` flag).

### Sidecar Auth Vault
File at `~/.otel-agent/auth.json` that stores imported OAuth grants (access + rotating refresh). Distinct from `config.yaml`, which only declares provider identity (`auth: xai-oauth`). Refresh writes only this file.

### SuperGrok Grant
A personal xAI OAuth token pair minted by Hermes (`xai-oauth`) or `grok login`. Usable as a Bearer on `api.x.ai` chat/completions. Not the same as `XAI_API_KEY` pay-as-you-go, and not included with X Premium+ alone.
