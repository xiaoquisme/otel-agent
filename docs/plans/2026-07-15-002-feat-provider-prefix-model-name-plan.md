---
title: "feat: Prefix model name with provider config name"
date: "2026-07-15"
type: "feat"
depth: "lightweight"
product_contract_source: "ce-plan-bootstrap"
artifact_contract: "ce-unified-plan/v1"
artifact_readiness: "implementation-ready"
execution: "code"
---

## Goal Capsule

- **Objective:** Display the provider config name as a prefix on model names across the dashboard — request list, usage statistics breakdown, and detail view — so users see e.g. `xiaomi/mimo-v2.5` instead of just `mimo-v2.5`.
- **Stop condition:** Every model name in the dashboard includes the `provider/` prefix; existing data without prefix renders as-is; no regressions.

---

## Problem Frame

The dashboard stores `model_name` from the upstream response body (e.g., `mimo-v2.5`). Users cannot tell which provider served a request without checking routing headers. The provider config name (e.g., `xiaomi`, `openai`) is known at logging time but not persisted alongside the model name. Adding it as a prefix makes the dashboard self-explanatory.

---

## Requirements

- R1. When logging a request, prefix `model_name` with `provider.name + "/"` before storing (e.g., `xiaomi/mimo-v2.5`).
- R2. The request list displays the prefixed model name.
- R3. The usage statistics breakdown groups and displays by prefixed model name.
- R4. The detail view metadata shows the prefixed model name.
- R5. Requests with `null` model name remain `null` (no prefix applied).

---

## Key Technical Decisions

**KTD1: Prefix at storage time, not display time.** The provider name is available in both `server.py` and `auto_handler.py` at logging time. Prefixing at write time means:
- No frontend changes needed for list and usage stats (they already display `model_name`)
- Usage GROUP BY naturally groups by `provider/model`
- No need to pass provider config to the dashboard API

**KTD2: Detail view uses stored `model_name` instead of raw `metadata.model`.** The `MetadataGrid` currently shows `detail.metadata?.model` (raw response body). Switch to `detail.model_name` (stored, prefixed) for consistency.

---

## Implementation Units

### U1. Prefix model_name at telemetry logging

**Goal:** Prepend `provider.name + "/"` to `model_name` before storing in the database.

**Files:**
- `src/otel_agent/server.py`
- `src/otel_agent/auto_handler.py`

**Approach:** In both `_log_telemetry()` (server.py:415) and `_log_routing_telemetry()` (auto_handler.py:152), after extracting `model_name` from the response body, prefix it with `provider.name + "/"` when non-null. The `provider` parameter is already available in both functions.

**Patterns to follow:** Both functions already have identical model extraction logic — `model_name = resp_body.get("model") if resp_body.get("model") else None`. The prefix is a one-line addition after this extraction.

**Test scenarios:**
- Happy path: request through `xiaomi` provider with response model `mimo-v2.5` → stored as `xiaomi/mimo-v2.5`.
- Null model: request with no `model` in response body → stored as `null` (no prefix).
- Non-auto request: request routed to `openai` provider with model `gpt-5.4` → stored as `openai/gpt-5.4`.

**Verification:** Existing tests pass. Check that stored model_name in the database includes the provider prefix.

---

### U2. Update detail view to use stored model_name

**Goal:** Show the prefixed model name in the detail view's metadata grid.

**Files:**
- `frontend/src/pages/DetailPage.tsx`

**Approach:** In `MetadataGrid`, change the Model item's value from `detail.metadata?.model` to `detail.model_name`. This uses the stored (prefixed) model name instead of the raw response body model. The `model_name` field is already part of `RequestDetail` (inherited from `RequestItem`).

**Test scenarios:**
- Happy path: detail view for a request with `model_name="xiaomi/mimo-v2.5"` shows that value in the Model field.
- Null model: detail view for a request with `model_name=null` shows `—`.

**Verification:** Open a request detail in the dashboard. Confirm the Model field shows the prefixed name.

---

## Verification Contract

| Gate | Command | Pass criteria |
|------|---------|---------------|
| Type check | `cd frontend && npx tsc --noEmit` | No errors |
| Tests | `uv run pytest tests/ -x -q --ignore=tests/test_integration.py` | All pass |

---

## Definition of Done

- [ ] `model_name` stored with `provider/` prefix in both server.py and auto_handler.py
- [ ] Request list shows prefixed model name
- [ ] Usage statistics groups by prefixed model name
- [ ] Detail view shows prefixed model name
- [ ] Null model names remain null (no prefix)
- [ ] No regressions in existing tests
