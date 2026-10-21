---
title: "Scope DSH Trajectory chrome to the request detail page"
date: 2026-10-19
category: design-patterns
module: dashboard
problem_type: design_pattern
component: frontend_stimulus
severity: medium
applies_when:
  - Restyling /request/:id toward deepseek-harness Trajectory
  - Adding kind-tag, overview, or selection treatment on trajectory cells
tags:
  - trajectory
  - dsh
  - css-tokens
  - dashboard
---

# Scope DSH Trajectory chrome to the request detail page

## Context

`/request/:id` is a static projection of one logged request: kind-tagged cells plus an Event details pane. DeepSeek Harness Trajectory is the visual reference (38px cells, inset brand ring, complementary inspector). The harness packages are a live conversation runtime and must not be vendored. The rest of the dashboard still uses the GitHub-light tokens in `frontend/src/styles/tokens.css`.

## Guidance

- Keep DSH aliases under `.dsh-trajectory` in `frontend/src/components/trajectory/trajectory.css`. Do not copy them onto `:root`.
- Cells: height 38px, padding `0 8px 0 20px`, gap 24px, 8px radius, `border-l2` (`rgba(0, 0, 0, 0.1)`), layer-3 fill on a layer-1 page.
- Selected cell: `border-color: transparent` and `box-shadow: inset 0 0 0 2px` brand primary. An outer 2px border reads as a GitHub focus ring and shifts the row.
- Kind tags stay shrink-wrapped in an 80px slot (height 22px, radius 6px): SYSTEM secondary/platform, USER success, ASSISTANT brand mix, TOOL warn, REASONING a separate purple.
- Do not paint request-level latency or token totals onto every cell. Those numbers belong in the request header and the Timing / Summary inspector. Per-step elapsed time is not on `RequestDetail`.
- Leave the shared `Tabs` primitive alone. The inspector draws its own 34px tab strip so other pages keep their chrome.
- Arrow keys move the listbox selection. A 50px overview sits under the request header: three lanes (User / Msg / Tool), DSH span colors, click selects that cell. Segment width is the square root of the step's text length, capped at 2000 characters. The request has one `latency_ms`, so the strip is not a duration axis. Do not port the live toolbar, viewport brush, virtualization, or turn collapse.

## Why This Matters

A global token swap would restyle the ledger, sessions, and usage pages. An outer blue border keeps the page looking like the previous GitHub-light detail view even when the tags are recolored.

## When to Apply

- Changing how a trajectory cell or the event inspector is drawn
- Adding a metric to a cell row

## Examples

- Selected cell uses an inset 2px ring; the 1px border becomes transparent so the row does not grow.
- `502 · 1605ms · model` stays in the 32px request header. Cells show index, kind, and preview only.

## Related

- `docs/plans/2026-08-17-002-feat-request-detail-trajectory-plan.md`
- `docs/solutions/design-patterns/request-detail-trajectory-window.md`
- `docs/solutions/design-patterns/request-detail-split-resize.md`
- `docs/solutions/design-patterns/light-theme-token-roles.md`
