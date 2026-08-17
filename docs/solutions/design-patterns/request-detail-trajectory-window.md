---
title: "Open request detail in a named Trajectory window"
date: 2026-08-17
category: design-patterns
module: dashboard
problem_type: design_pattern
component: frontend_stimulus
severity: medium
applies_when:
  - Opening request detail from the dashboard ledger
  - Rendering a logged LLM request as harness-like Trajectory steps
tags:
  - trajectory
  - window-open
  - dashboard
---

# Open request detail in a named Trajectory window

## Context

The list used an in-page split pane. Operators wanted the request detail in a separate window, styled like deepseek-harness Trajectory: compact kind-tagged cells plus a complementary Event details pane. Harness Trajectory is bound to a live conversation store; otel-agent only has a static `RequestDetail.messages` list.

## Guidance

- Open `/request/:id` with `window.open(url, \`otel-request-${id}\`)` so the same request reuses one window. If `window.open` returns null, fall back to same-tab navigation.
- Keep ↑↓ as list highlight only. Click and Enter open the window.
- Flatten each `StructuredMessage` into cells: reasoning, text, then each `tool_call`. Do not wrap the harness package.
- Reuse existing `MessageDisplay` / `CodeBlock` inside Event details tabs (Summary, Payload, Result, Timing).

## Why This Matters

A split pane fights the ledger. A named window keeps the list full-width. Flattening tool calls into their own cells is what makes the page read as Trajectory instead of chat bubbles.

## When to Apply

- Changing how a request is opened from the ledger
- Changing how messages are projected into inspectable steps

## Examples

- Click request 42 → window target `otel-request-42` loads `/request/42`
- Assistant text + one tool call → ASSISTANT cell and TOOL cell

## Related

- `docs/plans/2026-08-17-002-feat-request-detail-trajectory-plan.md`
- `docs/solutions/trajectory-style-dashboard.md`
