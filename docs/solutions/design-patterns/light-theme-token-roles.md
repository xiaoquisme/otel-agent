---
title: "Separate muted surfaces from hover and syntax colors"
date: 2026-08-17
category: design-patterns
module: dashboard
problem_type: design_pattern
component: frontend_stimulus
severity: medium
applies_when:
  - Recalibrating dashboard CSS custom properties between light and dark palettes
  - Using accent-muted tokens as both a well and as text
tags:
  - css-tokens
  - light-theme
  - contrast
  - dashboard
---

# Separate muted surfaces from hover and syntax colors

## Context

The dashboard theme lives in `frontend/src/styles/tokens.css` as `:root` custom properties. Live layout and components already consume those tokens, so flipping the default look is a palette change, not a layout rewrite.

On the previous dark palette, `--color-accent-*-muted` was a dark well. That same token was also used as JSON string text (`.json-string`) and as primary/danger button hover fills. Those three jobs only coincided while the muted value was a dark saturated color. A light theme needs muted tokens to be pale tints for chips, selected rows, and chat wells.

## Guidance

Keep one token name per job:

- `*-muted` — pale surface tint behind dark or accent text
- accent / semantic hues — body-readable color on `--color-bg-base`
- `*-hover` — a darker (or otherwise still contrasting) fill for inverse-text buttons
- syntax text — a readable accent, never a muted surface token

After changing tokens, rebuild and commit `src/otel_agent/dashboard/frontend_dist/` from a fresh `frontend/dist`. The Python dashboard serves those packaged assets, not Vite source. `uv tool install` keeps the committed `frontend_dist` and will not overwrite it with a leftover `frontend/dist`.

## Why This Matters

If muted tokens become light tints while still used as text or as a hover fill under `--color-text-inverse`, JSON strings vanish and primary buttons flash white-on-white. The token flip looks done, but contrast regressions hide in consumers that overloaded the muted name.

## When to Apply

- Changing `--color-*` values in `tokens.css`
- Adding a new accent that will be used both as a chip background and as text
- Shipping a dashboard visual change that must appear in `otel-agent dashboard`

## Examples

Before (dark-only coincidence):

- `--color-accent-blue-muted` used as chat well, selected row, JSON string color, and primary hover
- `--color-text-inverse` dark, because accents were light-on-dark

After (light default):

- muted tokens are pale tints (`#ddf4ff` family)
- `.json-string` uses `--color-accent-green`
- `Button` primary/danger hover uses `--color-accent-blue-hover` / `--color-accent-red-hover`
- `--color-text-inverse` is white so filled buttons stay readable

## Related

- `docs/solutions/trajectory-style-dashboard.md` — still describes the dashboard as a dark theme; refresh that note when convenient
- `docs/plans/2026-08-17-002-feat-light-theme-dashboard-plan.md`
