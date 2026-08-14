---
module: dashboard
tags: [ui, react, trajectory, design-pattern]
problem_type: ui-redesign
---

# Trajectory-Style Dashboard Redesign

## Problem

The otel-agent dashboard had a basic table layout with a separate detail page, lacking the sophisticated visualization patterns seen in modern LLM debugging tools like deepseek-harness's Trajectory UI.

## Solution

Redesigned the dashboard to adopt Trajectory UI patterns:

1. **Split-pane layout** — Table on left, detail panel on right (resizable)
2. **Timeline overview** — Horizontal bar showing request distribution over time
3. **Compact request ledger** — 30px rows with method tags, status, latency, and model
4. **Detail panel** — Tabs for conversation, raw data, and headers
5. **Keyboard navigation** — Arrow keys, /, Esc, Enter

## Key Patterns from deepseek-harness Trajectory UI

- **Cell-based records** — Each request is a compact row with index, kind tag, text preview, metrics, and elapsed time
- **Turn-based organization** — Messages grouped by request-response cycles
- **Request boundaries** — Visual markers between request groups
- **Timeline visualization** — Horizontal bar chart showing operations over time
- **Split-pane layout** — Table + detail panel with resizable divider

## Implementation Notes

- React + TypeScript + Vite
- CSS custom properties for theming (dark theme)
- No virtual scrolling yet (data volume doesn't require it)
- Backend API unchanged — pure frontend redesign
