---
title: "feat: Open request detail in a Trajectory-style window"
type: "feat"
date: "2026-08-17"
artifact_contract: "ce-unified-plan/v1"
artifact_readiness: "implementation-ready"
product_contract_source: "ce-plan-bootstrap"
execution: "code"
---

## Goal Capsule

- **Objective:** Opening a request shows its detail in a separate browser window, and that page looks like deepseek-harness Trajectory: compact kind-tagged cells plus a complementary event-details pane.
- **Product authority:** User request via ce-auto. Visual reference: `/Users/xiaoqu/Library/Mobile Documents/com~apple~CloudDocs/personal/deepseek-harness` Trajectory view (toolbar + timeline + cell table + Event details).
- **Open blockers:** None.
- **Stop conditions:** List stays full-width; click/Enter opens `/request/:id` in a new window; that page shows flattened SYSTEM/USER/ASSISTANT/TOOL cells and a details pane.

## Product Contract

### Summary

The list currently opens detail in an in-page split pane (`DetailPanel`). The standalone `DetailPage` is a chat-bubble layout. Operators want the detail in its own window, styled like harness Trajectory rather than chat cards.

Product Contract created by ce-plan-bootstrap.

### Problem Frame

Inspecting a request next to the ledger is cramped. Harness Trajectory is a compact event ledger (index, kind tag, preview) with a right-hand Event details region (Summary / Payload / Result / Timing). otel-agent already has structured `messages` on `RequestDetail`; the work is presentation and windowing, not a new API.

### Requirements

**Windowing**

- R1. Selecting a request from the ledger (click or Enter) opens `/request/:id` in a separate browser window.
- R2. Re-opening the same request reuses that named window instead of spawning duplicates.
- R3. If the browser blocks `window.open`, fall back to same-tab navigation so the request is still reachable.
- R4. The list page no longer uses the in-page split-pane `DetailPanel` as the primary detail surface.

**Trajectory-style detail**

- R5. The detail window shows the request as a compact cell ledger: index, kind tag (SYSTEM / USER / ASSISTANT / TOOL / REASONING), one-line preview.
- R6. Selecting a cell opens a complementary Event details pane with tabs for Summary, Payload, Result, and Timing.
- R7. Message `tool_calls` and `reasoning_content` become their own cells, matching harness step granularity.
- R8. Existing message markdown / tool / reasoning renderers are reused inside the details pane, not discarded.

### Success Criteria

- Clicking a ledger row leaves the list full-width and opens a second window on `/request/:id`.
- That window reads as a Trajectory table + details pane, not chat bubbles.
- Empty or non-LLM bodies still show a useful raw/summary fallback.

### Actors

- A1. Dashboard operator inspecting a logged request.

### Key Flows

- F1. Operator clicks a request in the ledger.
  - **Outcome:** New (or reused) window shows that request's Trajectory view.
- F2. Operator selects a TOOL cell.
  - **Outcome:** Event details shows tool name, arguments (Payload), and result when present.

### Acceptance Examples

- AE1. Covers R1, R4. Given the list, when the operator clicks request 42, then a window loads `/request/42` and the list has no right-hand detail pane.
- AE2. Covers R2. Given a window already open for request 42, when the operator clicks 42 again, then no extra window appears.
- AE3. Covers R5, R7. Given a request with assistant text plus one tool call, when the detail window loads, then the ledger has separate ASSISTANT and TOOL cells.

### Scope Boundaries

**In scope**

- List selection → `window.open`
- Remove split-pane detail as the primary path
- Trajectory-style `DetailPage` built from existing tokens and message data
- Rebuild `frontend_dist`

**Deferred for later**

- Porting harness virtualization, search index, duration-mode toolbar, or turn collapse
- Copying `@deepseek-ai/dsh-client-ui-trajectory` as a dependency
- Dark/light theme toggle

**Outside this product's identity**

- Backend API changes
- Embedding the harness package

## Planning Contract

### Key Technical Decisions

KTD1. New window via `window.open`, not a React portal.
Decision: `window.open(\`/request/${id}\`, \`otel-request-${id}\`)`.
Rationale: The user asked for a separate window. A named target satisfies R2. Same-origin SPA routing loads `DetailPage` in that window.
Alternatives: `target=_blank` without a name (duplicates); in-page modal (not a window).

KTD2. Do not depend on the harness package.
Decision: Reimplement the visual pattern with existing dashboard tokens and components.
Rationale: Harness Trajectory is wired to a live conversation snapshot store. otel-agent has a static `RequestDetail`. Copying the package would pull an unrelated runtime.

KTD3. Flatten `StructuredMessage[]` into cells.
Decision: Emit one cell per system/user/tool message; split assistant into reasoning, text, and each `tool_call`.
Rationale: Matches harness step rows (USER / ASSISTANT / TOOL) rather than one bubble per role.

KTD4. List keeps selection highlight for keyboard nav; Enter/click opens the window.
Decision: `selectedId` stays for ↑↓ highlight; it no longer mounts `DetailPanel`.
Rationale: Keyboard nav still needs a focused row.

### Assumptions

- "单独开个窗口" means a real browser window/tab, not the existing split pane.
- A single request is one Trajectory (not a multi-request session).
- Popup-blocker fallback to same-tab is acceptable.

### Sequencing

U1 (windowing) then U2 (Trajectory page) then U3 (packaged assets). U2 can land without U1 but the product story needs both.

## Implementation Units

### U1. Open request detail in a separate window

**Goal:** Ledger selection opens `/request/:id` in a named window and drops the split-pane detail.
**Requirements:** R1, R2, R3, R4.
**Dependencies:** None.
**Files:**
- `frontend/src/pages/ListPage.tsx` — (modify) open window; remove `DetailPanel` mount
- `frontend/src/lib/openRequestWindow.ts` — (new) named `window.open` + same-tab fallback

**Approach:**
1. Helper opens `/request/${id}` with target `otel-request-${id}`; if the return is null, `window.location.assign`.
2. List `handleSelect` / Enter uses the helper. Arrow keys still change `selectedId`.
3. Remove `DetailPanel`, resize handle, and the flex split that reserved 40% for detail.

**Patterns to follow:** Existing `/request/:id` route in `frontend/src/router.tsx`.

**Test scenarios:**
- Helper uses a named target derived from the request id.
- When `window.open` returns null, navigation falls back in the current window.
- ListPage no longer renders `DetailPanel`.

**Verification:** Clicking a row does not open a right pane; a new window (or same-tab fallback) loads the detail route.

### U2. Trajectory-style detail window

**Goal:** `/request/:id` looks like harness Trajectory: cell ledger + Event details.
**Requirements:** R5, R6, R7, R8.
**Dependencies:** None.
**Files:**
- `frontend/src/pages/DetailPage.tsx` — (modify) full-height trajectory layout
- `frontend/src/components/trajectory/buildTrajectoryCells.ts` — (new) flatten messages to cells
- `frontend/src/components/trajectory/TrajectoryLedger.tsx` — (new) 38px-ish cells
- `frontend/src/components/trajectory/EventDetails.tsx` — (new) complementary pane + tabs
- `frontend/src/components/MessageDisplay.tsx` — (reuse) render selected cell payload/result

**Approach:**
1. Flatten messages into `{ id, index, kind, preview, message, toolCall? }`.
2. Left: scrollable cells (index, kind tag, preview). Selected cell gets an inset accent ring like harness `.selected`.
3. Right: Event details — Summary (role, model, finish, tokens), Payload (tool args or raw), Result (markdown/content), Timing (request latency).
4. Keep a compact request header (method, url, status, latency) above the split, not chat cards.
5. Empty `messages` still shows raw body via existing `CodeBlock`.

**Patterns to follow:** Harness `TrajectoryCell.module.css` (38px row, tag slot, selected ring). otel tokens for colors. Existing `Tabs` primitives.

**Execution note:** Prefer visual/smoke proof; add a focused unit test for the flattener.

**Test scenarios:**
- Assistant with text + one tool_call yields at least two cells (ASSISTANT and TOOL).
- Reasoning-only assistant yields a REASONING cell.
- User/system/tool roles map to USER/SYSTEM/TOOL tags.
- Preview is a single line (newlines collapsed).

**Verification:** Detail window shows kind-tagged rows; selecting a TOOL cell shows arguments in Payload.

### U3. Rebuild packaged dashboard assets

**Goal:** `otel-agent dashboard` serves the new window + Trajectory page.
**Requirements:** R1–R8 delivery.
**Dependencies:** U1, U2.
**Files:**
- `src/otel_agent/dashboard/frontend_dist/` — (modify) regenerated assets

**Approach:** `npm run build` in `frontend/`, copy `frontend/dist` to `frontend_dist` as `hatch_build.py` does.

**Test scenarios:**
Test expectation: none -- asset copy only.

**Verification:** Packaged JS references Trajectory ledger or `openRequestWindow`.

## Verification Contract

| Gate | Command / check | Applies to | Done signal |
|---|---|---|---|
| Flattener tests | frontend unit test or a small Node/ts check | U2 | Cell counts/kinds match fixtures |
| Frontend build | `npm run build` in `frontend/` | U1–U3 | Build succeeds |
| Python tests | `uv run pytest` | regression | No new failures (2 known pre-existing `os` import failures on main) |
| Visual smoke | Open list, click a request | U1, U2 | New window, Trajectory cells + details |

## Definition of Done

- R1–R8 hold on the live routed pages.
- Split-pane `DetailPanel` is not the primary inspect path.
- Packaged `frontend_dist` matches source.
- Abandoned experiment files are not left in the diff.
