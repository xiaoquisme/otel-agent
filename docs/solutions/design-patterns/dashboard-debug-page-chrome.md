---
title: "Match new dashboard pages to the shared chrome and form controls"
date: 2026-11-10
category: design-patterns
module: dashboard
problem_type: design_pattern
component: frontend_stimulus
severity: medium
applies_when:
  - Adding a dashboard route that is not the request ledger
  - Showing provider or discovery warnings above a form
tags:
  - dashboard
  - debug-page
  - layout
  - alerts
---

# Match new dashboard pages to the shared chrome and form controls

## Context

`/debug` shipped with its own buttons, select, and full-width notice bars. On the live page those bars stacked above the prompt, and the model refresh control sat in the page title instead of with the model field. The rest of the dashboard (Sessions, Requests, Usage) already uses the shared header, tokenized cards, `Button`, and `Select`.

## Guidance

- Keep the page in `DashboardLayout` and use the same left padding and title scale as Sessions (`text-lg` / `font-semibold`, lede in `text-xs` secondary). Do not center a max-width column under the full-width header.
- Build forms from `Card`, `Button`, and `Select`. Put refresh next to the model select, not in the page title.
- Keep credential and discovery copy, but make a long provider list a collapsed `<details>` with a one-line summary and a scrollable list. Use the same muted info, warning, and error wells as the request table (`accent-*-muted` background, accent border).
- Rebuild `src/otel_agent/dashboard/frontend_dist/` from `frontend/dist` after the UI change. The packaged assets are what `otel-agent dashboard` serves.

## Why This Matters

A second visual language makes Debug look unfinished next to Sessions and Requests, and an expanded discovery list pushes the actual prompt below the fold. Collapsing that list keeps every warning available without changing discovery or the gateway request.

## Related

- `docs/solutions/design-patterns/light-theme-token-roles.md`
- `docs/plans/2026-10-29-dashboard-debug-plan.md`
