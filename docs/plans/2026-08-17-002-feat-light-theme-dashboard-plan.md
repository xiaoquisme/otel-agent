---
title: "feat: Bright light theme for dashboard"
type: "feat"
date: "2026-08-17"
artifact_contract: "ce-unified-plan/v1"
artifact_readiness: "implementation-ready"
product_contract_source: "ce-plan-bootstrap"
execution: "code"
---

## Goal Capsule

- **Objective:** Change the otel-agent dashboard from its current dark palette to a bright light theme for backgrounds and theme colors, without changing layout or adding a theme toggle.
- **Product authority:** User request via ce-auto: 项目的背景和主题颜色改成明亮的风格.
- **Execution profile:** Lightweight styling change through the existing CSS token system.
- **Open blockers:** None.
- **Stop conditions:** Live routed dashboard (list, detail, usage) reads as light surfaces with dark text and readable accents; shipped `frontend_dist` matches source.

## Product Contract

### Summary

The dashboard currently ships a dark GitHub-like palette defined in `frontend/src/styles/tokens.css`. Recalibrate those tokens (and the few live-path leftovers that do not use them) so the default look is bright: light backgrounds, dark text, softer shadows, and accents that still contrast on white.

Product Contract created by ce-plan-bootstrap.

### Problem Frame

Operators want a bright workspace. The live UI already consumes CSS custom properties, so a token flip is the correct lever. Dark-tuned muted accents are also used as syntax colors (`globals.css` `.json-string` uses `--color-accent-blue-muted`); those must be decoupled or the light theme will lose JSON contrast.

### Requirements

**Theme**

- R1. Default page background and surfaces are light (near-white / light gray), not dark charcoal.
- R2. Primary text is dark on those surfaces; secondary/muted text remains readable.
- R3. Accent, semantic, and muted-accent tokens stay usable: accents readable as text on light surfaces; `*-muted` tokens remain pale surface tints, not dark wells.
- R4. Shadows and overlays lighten so cards and popovers do not look like dark-theme remnants.
- R5. The browser UI (`color-scheme`) matches the light page so native controls and scrollbars do not stay dark.

**Delivery**

- R6. The packaged dashboard in `src/otel_agent/dashboard/frontend_dist/` is rebuilt from the updated frontend so `otel-agent dashboard` serves the light theme.

### Success Criteria

- Opening the dashboard shows a bright page immediately, with no dark full-page chrome.
- Conversation, ledger, usage cards, and code/JSON blocks remain readable.
- Spacing, typography, and split-pane layout are unchanged.

### Actors

- A1. Dashboard operator viewing requests and usage locally.

### Key Flows

- F1. Operator opens the dashboard home (request list + optional detail pane).
  - **Outcome:** Light chrome, dark text, existing navigation still works.
- F2. Operator opens a request detail and usage view.
  - **Outcome:** Same light theme; syntax and charts remain visible.

### Acceptance Examples

- AE1. Covers R1, R2. Given a running dashboard, when the operator loads `/`, then `body` / layout background is a light token value and primary text is a dark token value.
- AE2. Covers R3. Given a chat/JSON body, when highlighted, then keys/strings/numbers are not pale-on-white.
- AE3. Covers R6. Given the repo as served by the Python package, when `frontend_dist` assets are inspected, then they contain the new light token values.

### Scope Boundaries

**In scope**

- Recalibrate color and shadow tokens in `frontend/src/styles/tokens.css`.
- Fix token consumers that would break contrast after muted accents become light tints.
- Set `color-scheme: light`.
- Rebuild and copy frontend assets into `frontend_dist`.

**Deferred for later**

- Dark/light theme toggle (already deferred in `docs/plans/2026-08-17-001-refactor-dashboard-ui-polish-plan.md`).
- Migrating unused legacy components that still hardcode GitHub-dark hex (`Header.tsx`, `RequestList.tsx`, `RequestRow.tsx`, `components/DetailPanel.tsx`, `LLMBody.tsx`, `ExportButtons.tsx` — not imported by the router).
- Full WCAG AA audit.

**Outside this product's identity**

- Backend, routing, or layout redesign.
- New npm dependencies or a second theme stylesheet.

## Planning Contract

### Key Technical Decisions

KTD1. Flip `:root` tokens in place rather than adding `[data-theme]` or a second stylesheet.
Decision: Replace the dark values on the existing custom properties.
Rationale: Live layout/components already read `var(--color-*)`. A dual-theme system is explicitly deferred.
Alternatives: Theme toggle (out of scope); Tailwind `@theme` rewrite (unnecessary churn).

KTD2. Keep muted accents as surface tints; stop using them as syntax text.
Decision: Recalibrate `--color-accent-*-muted` to pale tints. Point `.json-string` (and any similar text use) at a readable accent or a small `--color-syntax-*` token, not the muted surface token.
Rationale: On dark theme, `#1f3a5c` worked as both a well and (poorly) as text. On light theme those roles conflict.
Alternatives: Keep muted tokens dark (would punch dark holes in a light UI).

KTD3. Directional light palette, not a named third-party kit.
Decision: Neutral cool gray surfaces (`#f6f8fa` / `#ffffff` family), ink text (`#1f2328` family), slightly deeper accents than the current neon-on-dark set so they meet contrast on white.
Rationale: Matches the dashboard's existing GitHub-adjacent language without importing a design system.
Execution note: Treat exact hex as implementation judgment as long as R1–R4 hold.

KTD4. Ship via rebuilt `frontend_dist`.
Decision: Run the frontend production build and refresh `src/otel_agent/dashboard/frontend_dist/` the same way hatch copies `frontend/dist`.
Rationale: `otel-agent dashboard` serves the packaged assets, not Vite source.

### Assumptions

- The user wants the default (only) theme to become light, not a toggle.
- Layout, typography, and spacing tokens stay as they are.
- Unused GitHub-dark leftover components can remain until a later cleanup.

### Sequencing

U1 then U2. Token contrast must be correct before the production bundle is copied.

## Implementation Units

### U1. Light design tokens and contrast-safe consumers

**Goal:** Make the live dashboard render as a bright theme from CSS tokens.
**Requirements:** R1, R2, R3, R4, R5.
**Dependencies:** None.
**Files:**
- `frontend/src/styles/tokens.css` — (modify) light backgrounds, dark text, pale muted accents, lighter shadows
- `frontend/src/styles/globals.css` — (modify) stop using muted tokens as syntax text
- `frontend/src/index.css` — (modify) `color-scheme: light` on `html`/`body`
- `frontend/index.html` — (modify) optional `color-scheme` meta if needed for first paint
- `frontend/src/components/LatencyChart.tsx` — (modify) chart fill that hardcodes a dark-theme blue alpha

**Approach:**
1. Recalibrate only color and shadow custom properties; leave spacing, type, radius, z-index untouched.
2. Invert the stack: base light, surface white, elevated slightly brighter/whiter, muted a light gray, inverse text now light-on-dark for the rare inverse chip.
3. Deepen accent/semantic hues enough for body text on white.
4. Retarget `.json-string` (and scan `globals.css` for other muted-as-text uses).
5. Set `color-scheme: light`.
6. Replace the LatencyChart hardcoded `rgba(88, 166, 255, 0.1)` with a token-derived or light-appropriate fill.

**Patterns to follow:** Existing token names and consumption in `frontend/src/index.css` and `frontend/src/layouts/DashboardLayout.tsx`. Prior token migration intent in `docs/plans/2026-08-17-001-refactor-dashboard-ui-polish-plan.md` KTD4.

**Execution note:** This is styling; prefer visual/smoke verification over new unit tests.

**Test scenarios:**
Test expectation: none -- token and stylesheet recalibration with no behavioral logic.

**Verification:**
- `--color-bg-base` is a light value; `--color-text-primary` is a dark value.
- Chat user/assistant wells use pale muted tints, not dark rectangles.
- JSON string color remains readable on `--color-bg-base`.

### U2. Rebuild packaged dashboard assets

**Goal:** The Python-served dashboard shows the light theme without running Vite separately.
**Requirements:** R6.
**Dependencies:** U1.
**Files:**
- `src/otel_agent/dashboard/frontend_dist/` — (modify) regenerated production assets
- `frontend/dist/` — (modify) Vite build output if present in the worktree

**Approach:**
1. Run the frontend production build from `frontend/`.
2. Replace `src/otel_agent/dashboard/frontend_dist/` with the new `frontend/dist/` contents, matching `hatch_build.py`.
3. Confirm the bundled CSS contains the new light token values.

**Patterns to follow:** `hatch_build.py` copy from `frontend/dist` to `src/otel_agent/dashboard/frontend_dist`.

**Execution note:** Packaging/smoke; no new pytest module required.

**Test scenarios:**
Test expectation: none -- asset copy only.

**Verification:**
- `frontend_dist` `index.html` and hashed CSS exist.
- Packaged CSS includes the new `--color-bg-base` light value, not `#1a1d24`.

## Verification Contract

| Gate | Command / check | Applies to | Done signal |
|---|---|---|---|
| Frontend typecheck/build | `npm run build` in `frontend/` | U1, U2 | Build succeeds |
| Packaged tokens | Inspect bundled CSS under `frontend_dist/assets/` | U2 | Light `--color-bg-base`, dark `--color-text-primary` |
| Python tests | `pytest` | regression | Existing suite still passes |
| Visual smoke | Load list, detail, usage | U1 | Bright chrome, readable text and JSON |

## Definition of Done

- R1–R6 are met on the live routed pages.
- U1 and U2 verification signals above are true.
- No theme toggle or layout rewrite landed.
- Abandoned experiment files are not left in the diff.
- Packaged `frontend_dist` matches the source token change.
