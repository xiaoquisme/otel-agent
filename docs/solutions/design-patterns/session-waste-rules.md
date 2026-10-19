---
title: Flag wasted work on an agent session with fixed rules
date: 2026-10-19
category: design-patterns
module: telemetry
problem_type: design_pattern
component: session_waste
severity: medium
applies_when:
  - Reading an agent session trajectory for obvious token waste
  - Adding or tuning a deterministic session finding
tags:
  - session
  - waste
  - dashboard
  - trajectory
---

# Flag wasted work on an agent session with fixed rules

## Context

An Agent Session is the time-ordered gateway calls that share `X-Otel-Session`. The trajectory already showed failed and slow steps. It did not say which calls looked like retries, duplicated work, or a token spike, so a person still had to scan the whole run before editing a prompt or skill.

## Guidance

- Keep every threshold in `otel_agent.waste`. The slow cut stays `sessions.SLOW_STEP_MS` (10s) and the waste module imports it.
- Run the rules inside `assemble_session` so `GET /api/sessions/{id}`, the Sessions page, and `otel-agent view --session` share one result. Add fields only: `findings`, `finding_counts`, `flagged_request_ids`, and `waste_rules` on each step.
- Each finding has `rule_id`, `severity` (`info` or `warn`), `request_ids`, an English `message`, and `tokens_involved` (null when the step reported no usage).
- Rules: `failed_step`, `slow_step`, `retry_burst`, `duplicate_call`, `token_spike`, `heavy_context`. A retry is a failure followed, within 45s, by the same body tail or by another failure on the same model and endpoint. A duplicate is a consecutive run with the same model, endpoint, and body tail. Compare the tail (`substr(request_body, -256)` plus `length(request_body)`), not a prefix — agent turns share a long head. Do not parse the body and do not put the tail on the public step.
- A duplicate run whose request ids are already covered by a retry burst is omitted. A later success with a different body is a failed step, not a retry.
- Token spikes need four token samples before the median (3×, floor 1,000) or 90th percentile applies. Shorter runs flag only a step at or above 50,000 tokens that is also 3× the smallest step.

## Why This Matters

Prefix equality marks every turn of a growing transcript as a duplicate. Body parsing on the session read would pull full stored payloads back into the dashboard process. One module for the cuts keeps the API, the page, and the CLI from drifting.

## When to Apply

- Tuning a waste rule or adding one that can be decided from status, latency, tokens, model, endpoint, body length, and a bounded tail
- Implementing `get_session` on another storage backend: select `length(request_body)` and `substr(request_body, -256)` and pass both through `assemble_session`
