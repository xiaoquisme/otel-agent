---
title: "Resize the request detail inspector without a split-pane library"
date: 2026-10-21
category: design-patterns
module: dashboard
problem_type: design_pattern
component: frontend_stimulus
severity: low
applies_when:
  - Adjusting the event-details pane on /request/:id
  - Keeping the DSH trajectory split usable on a narrow viewport
tags:
  - trajectory
  - dsh
  - split-pane
  - dashboard
---

# Resize the request detail inspector without a split-pane library

## Context

`/request/:id` lays the trajectory ledger and the event inspector side by side in `.dsh-split`. The inspector used a fixed `clamp(320px, 38%, 440px)`, so payload and result tabs stayed narrow on a wide window. The dashboard has no split-pane dependency and does not persist other layout preferences.

Below 860px, including a 390px-wide phone, the same split already stacks: the ledger on top, the inspector full width underneath.

## Guidance

- Put the drag handle in `TrajectorySplit`, between the ledger and `EventDetails`. Keep DSH chrome in `trajectory.css`. Do not add a split-pane package.
- Store the preferred inspector width in `localStorage` under `otel-agent.dsh-details-width`. Apply it with `--dsh-details-width` on `.dsh-split`. Absent or cleared storage keeps `clamp(320px, 38%, 440px)`.
- Clamp with `clampDetailsWidth`: inspector at least 320px, ledger at least 280px. When the split is narrower than both minimums, give the leftover to the inspector. Double-click the handle to clear the preference.
- The handle is a `role="separator"` with pointer capture and arrow keys. Arrow left/up widens the inspector. Hide it inside the existing `@media (max-width: 860px)` stack and force `.dsh-details { width: 100% }` there so a stored pixel width cannot pin the column layout.

## Why This Matters

An unclamped drag collapses the kind-tag column or the tab strip. Applying the stored pixel width inside the stacked media query makes a 390px viewport scroll sideways instead of stacking.

## When to Apply

- Changing the trajectory split or the inspector width
- Adding another persisted dashboard layout preference

## Examples

- Drag the divider left on a 1280px window: the inspector grows and the ledger keeps at least 280px.
- Reload `/request/:id`: the same inspector width comes back from `otel-agent.dsh-details-width`.
- At 390px the handle is gone and the inspector is full width, stored pixels ignored.

## Related

- `docs/solutions/design-patterns/dsh-trajectory-detail-surface.md`
- `frontend/src/components/trajectory/TrajectorySplit.tsx`
