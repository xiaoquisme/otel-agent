---
title: "Auto-routing seed bias and fallback tier order bugs"
date: "2026-07-14"
category: "logic-errors"
module: "auto_routing"
problem_type: "logic_error"
component: "service_object"
symptoms:
  - "Thompson Sampling provider selection skews toward frequently-called providers regardless of actual success rate"
  - "Circuit-breaker fallback tries more expensive provider tiers before cheaper ones"
  - "Auto-router accumulates arbitrarily high success priors on popular providers"
  - "Fallback tier ordering inverts cost preferences under circuit-breaker pressure"
root_cause: "logic_error"
resolution_type: "code_fix"
severity: "medium"
tags:
  - "thompson-sampling"
  - "auto-routing"
  - "circuit-breaker"
  - "seed-bias"
  - "fallback-tiers"
  - "provider-selection"
  - "session-cache"
  - "compounding-priors"
related_components:
  - "circuit_breaker"
  - "session_cache"
---

# Auto-routing seed bias and fallback tier order bugs

## Problem

The auto-model routing system — the pipeline that intercepts `model="auto"` requests, classifies task complexity into tiers, and selects the cheapest suitable provider via Thompson Sampling — had two logic bugs that caused incorrect routing decisions, plus significant dead code accumulated from iterative development.

The routing system lives across four modules:

- **`auto_handler.py`** — orchestrates the full pipeline: classify → session lookup → provider select → fallback → forward → log.
- **`auto_router.py`** — Thompson Sampling bandit algorithm that picks the best provider within a complexity tier.
- **`circuit_breaker.py`** — tracks consecutive failures per provider and excludes providers that exceed a failure threshold.
- **`session_cache.py`** — pins multi-turn conversations to the same provider via a TTL cache.

Bug 1 made the Thompson Sampling algorithm converge prematurely on a single provider regardless of actual performance. Bug 2 made tier fallback redundant and prevent cost optimization from working as intended during partial outages. Together, they meant the auto-routing system was not behaving as a cost-optimized router — it was effectively a static selector that would lock onto one provider and stay there.

---

## Symptoms

**Thompson Sampling lock-in (Bug 1).** In production, the auto-router would quickly converge on a single provider and never explore alternatives, even when cheaper or more capable providers were available. Metrics showed one provider accumulating thousands of "success" counts while competitors stayed near their prior values. The Bayesian bandit should have been exploring; instead it was deterministic.

**Redundant fallback (Bug 2).** When all providers in the "reasoning" tier were circuit-broken (e.g., during an upstream outage), the fallback loop would re-try "reasoning" tier providers that had already been excluded, wasting time before eventually returning a 503. Cheaper tiers like "simple" or "medium" — which often had healthy providers — were never reached.

**Dead code smell.** Multiple getter functions (`get_auto_router()`, `get_circuit_breaker()`, `get_session_cache()`) were defined but never called. Fields like `failure_count` on `SessionEntry` and `last_probe_time` on `ProviderCircuit` were stored but never read. The `CircuitBreaker.get_state()` getter had a hidden side effect (transitioning OPEN→HALF_OPEN) that made it unsuitable for read-only inspection. This made the codebase harder to reason about and introduced subtle coupling.

---

## What Didn't Work

**The original `seed_from_costs()` call site.** The function was designed to give cheaper providers a higher initial success prior in the Beta distribution, seeding the Thompson Sampling exploration. This was a sound idea — cheaper providers should get a head start. However, it was called inside `_select_provider_for_tier()` on every incoming request, not just on first contact. Each invocation recomputed the cost ratio and added a bonus to `ProviderScore.successes`. After N requests, a provider's success count was inflated by N × bonus, completely dominating the Beta distribution. The sampling variance collapsed and the bandit stopped exploring.

**The original fallback loop.** The fallback was written as `TIER_ORDER[idx:]` — a forward slice starting at the current tier index. When the current tier was `"reasoning"` (index 3), this produced `["reasoning"]`, which tried the same broken tier again. The intent was to try *cheaper* tiers on failure, but the slice direction was wrong.

**Getter functions and unused fields.** The singleton getters (`get_auto_router()`, `get_circuit_breaker()`, `get_session_cache()`) were created early in development for debugging access, but the module-level singletons (`_auto_router`, `_circuit_breaker`, `_session_cache`) were imported directly instead. `SessionEntry.failure_count` was added to track how many times a session had been routed to a failing provider, but the logic was never implemented — the field was set to 0 and never incremented. `ProviderCircuit.last_probe_time` and `record_probe_result()` were part of a more sophisticated probe mechanism that was never wired up.

---

## Solution

### Bug 1 Fix: One-Time Cost Seeding

Added a `seeded: bool = False` field to the `ProviderScore` dataclass in `auto_router.py`. In `seed_from_costs()`, each provider's score is checked before seeding:

```python
score = self.scores[tier].setdefault(name, ProviderScore())
if score.seeded:
    continue  # Already seeded — skip
score.seeded = True
cost_ratio = cost / avg_cost if avg_cost > 0 else 1.0
bonus = max(0, (1.0 - cost_ratio) * 4)
score.successes += bonus
```

The `seeded` flag is set before the bonus is computed, guarding the entire seeding block. Subsequent calls to `seed_from_costs()` for the same provider in the same tier are no-ops. This preserves the original design intent — cheaper providers start with a higher prior — without allowing the bonus to compound across requests.

### Bug 2 Fix: Cheaper-First Fallback

Changed the fallback loop in `_select_provider_for_tier()` from:

```python
for fallback_tier in TIER_ORDER[idx:]:      # forward: tries same tier again
```

to:

```python
for fallback_tier in reversed(TIER_ORDER[:idx]):  # reverse: tries cheaper tiers first
```

Now when "reasoning" providers are all circuit-broken, the fallback walks backward through "complex", "medium", "simple" — trying tiers in reverse-expensive order, all of which are cheaper than reasoning.

### Dead Code Removal

Removed the following across the four modules:

| Item | Module | Why removed |
|------|--------|-------------|
| `get_auto_router()` | auto_handler.py | Unused — module-level singleton imported directly |
| `get_circuit_breaker()` | auto_handler.py | Unused — same reason |
| `get_session_cache()` | auto_handler.py | Unused — same reason |
| `record_failure()` | session_cache.py | Never called |
| `failure_count` field | session_cache.py | Set to 0, never incremented or read |
| `get_state()` side effect | circuit_breaker.py | Was calling `should_allow_request()` as a side effect of a getter, causing OPEN→HALF_OPEN transitions on read. Now a pure read of `.state` |
| `last_probe_time` field | circuit_breaker.py | Unused — part of unimplemented probe mechanism |
| `record_probe_result()` method | circuit_breaker.py | Unused — same reason |
| Set model then pop pattern | auto_handler.py | Was setting `upstream_body["model"]` then immediately removing it; replaced with a clean assignment in `_prepare_request_body()` |

Additionally, moved the `JSONResponse` import to the top of `auto_handler.py` (was previously a late import in one code path) and extracted a `_build_upstream_url()` helper to deduplicate URL construction that was repeated in both the initial request and the fallback loop.

### Code Simplification

- **`defaultdict` for shared state:** `CircuitBreaker.circuits` and `AutoRouter.scores` now use `defaultdict(ProviderCircuit)` and `defaultdict(dict)` respectively, eliminating manual key-existence checks.
- **`setdefault()` replaces `_get_or_create_score()`:** All score lookups now use `dict.setdefault()` in a single line, removing the helper method entirely.
- **Dict comprehension simplification:** `get_provider_stats()` uses a clean dict comprehension instead of building the result dict in a loop.
- **Comment cleanup:** Removed verbose comments that restated what the code already expressed clearly.

---

## Why This Works

**Bug 1 — compounding bias eliminated.** The `seeded` flag is a simple guard that converts a per-request side effect into a one-time initialization. The Thompson Sampling Beta distribution now starts with a slight bias toward cheaper providers (the design intent) but is driven by actual success/failure outcomes thereafter. The bandit can explore freely and will naturally converge on the best-performing provider over time, not the cheapest one by default.

**Bug 2 — fallback explores cheaper tiers.** `reversed(TIER_ORDER[:idx])` produces a list ordered from most expensive to cheapest within the fallback range. When reasoning-tier providers are all down, the system tries complex → medium → simple in order. This maximizes the chance of finding a healthy provider while minimizing the jump down in capability — a complex-tier response is preferred over simple when both are available. If no cheaper tiers have healthy providers either, it correctly returns 503.

**Dead code removal — reduced surface area.** Removing unused getters, fields, and methods eliminates the cognitive overhead of tracking state that doesn't matter. The `get_state()` side effect removal is particularly important: a getter that mutates state is a correctness hazard — any code that reads circuit state could accidentally trigger a HALF_OPEN transition. Now `get_state()` is a pure accessor.

**Simplifications — lower maintenance cost.** `defaultdict` and `setdefault()` are idiomatic Python that express "create if missing" in one line, replacing boilerplate that scattered the same logic across multiple locations. The extracted `_build_upstream_url()` helper means URL construction logic lives in one place — a future change to URL format (e.g., adding API version paths) only needs one edit.

---

## Prevention

1. **Guard one-time initialization with explicit flags.** Whenever a function is designed to run once (seed priors, initialize state, register hooks), use a boolean guard like `seeded` rather than relying on the caller to know not to call it repeatedly. This makes the function safe to call from any context without coordination.

2. **Test fallback paths with circuit-broken providers.** Add integration tests that trip the circuit breaker on all providers in a tier and verify that fallback reaches cheaper tiers. A simple test: configure two tiers, break all providers in the expensive tier, and assert the router selects from the cheaper tier.

3. **Prefer side-effect-free getters.** Getters and query methods should never mutate state. If a state transition is needed (e.g., OPEN→HALF_OPEN after cooldown), make it an explicit method call (`try_probe()` or `check_cooldown()`), not a side effect of reading state.

4. **Remove dead code promptly.** Fields, methods, and functions that are added speculatively should be removed when the planned use case doesn't materialize. Dead code creates the illusion of functionality and makes it harder to reason about what the system actually does.

5. **Prefer `defaultdict`/`setdefault` over manual key-existence patterns.** When a data structure requires "get or create" semantics, use Python built-ins that express this idiomatically. This avoids the common pattern of checking `if key not in dict` followed by `dict[key] = default`, which is verbose and error-prone when the creation logic is repeated in multiple places.
