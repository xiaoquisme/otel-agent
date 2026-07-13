---
title: Guard non-string url in LatencyChart
date: 2026-07-14
category: ui-bugs
module: frontend
problem_type: ui_bug
component: frontend_stimulus
severity: low
symptoms:
  - "Potential runtime error when last.url is not a string"
root_cause: logic_error
resolution_type: code_fix
tags:
  - typescript
  - type-safety
  - latency-chart
  - frontend
---

# Guard non-string url in LatencyChart

## Problem

LatencyChart.tsx called `.split('?')` on `last.url` without verifying it was a string, risking a runtime error if url was undefined, null, or another type.

The original code relied on optional chaining (`last.url?.split('?')`) as a safety net, but optional chaining only guards against `null` and `undefined` — it does not protect against non-string values that happen to be present on the object. If `last.url` were ever a number, object, or any other non-string type, the `.split('?')` call would throw a `TypeError` at runtime, breaking the chart component.

## Symptoms

- Potential `TypeError` if `last.url` is not a string
- Chart could fail to render labels correctly

The failure would surface as a runtime exception during component rendering. Because this code path executes on every data point when building chart labels, a single malformed record in the telemetry dataset would crash the entire LatencyChart view — preventing users from visualizing any latency data.

## What Didn't Work

N/A — this was a straightforward type-safety fix. The optional chaining (`?.`) approach was the right instinct but insufficient, since it only covers nullish cases. No alternative approaches were attempted or needed.

## Solution

Added a `typeof` guard before the `.split` call. The `urlStr` variable ensures `.split('?')` is only called on a string value.

**Before:**

```typescript
const label = last.method + ' ' + (last.url?.split('?')[0] || '')
```

**After:**

```typescript
const urlStr = typeof last.url === 'string' ? last.url : ''
const label = last.method + ' ' + (urlStr.split('?')[0] || '')
```

The intermediate `urlStr` variable guarantees that the subsequent `.split('?')` call operates exclusively on a string. Non-string values (including `undefined`, `null`, numbers, objects) are safely coerced to an empty string.

## Why This Works

TypeScript's optional chaining (`?.`) only guards against `null` and `undefined`, not against non-string types. The explicit `typeof` check handles all non-string cases.

When `last.url` is a string, the ternary passes it through unchanged. When it is anything else — `undefined`, `null`, a number, an object — the ternary resolves to `''`, and `''split('?')[0]` evaluates to `''`, which the `|| ''` fallback already handles. This makes the label construction robust against every possible value of `last.url`, not just the nullish ones.

## Prevention

- Always verify type before calling string methods on potentially dynamic data
- Use TypeScript strict mode and consider adding explicit type annotations
- When data comes from API responses, treat fields as potentially unexpected types
