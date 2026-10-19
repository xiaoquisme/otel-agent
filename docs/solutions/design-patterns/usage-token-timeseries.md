---
title: Bucket dashboard token usage in the viewer's timezone
date: 2026-10-19
category: design-patterns
module: dashboard
problem_type: design_pattern
component: usage_series
severity: medium
applies_when:
  - Adding time-series token charts to the usage page
  - Aggregating ISO-8601 timestamps stored as UTC text
tags:
  - usage
  - sqlite
  - timezone
  - chart
---

# Bucket dashboard token usage in the viewer's timezone

## Context

`/api/usage` returns one total for a half-open UTC range. The Usage page periods (Today, This Week, This Month, All Time) are local calendar ranges, so a chart has to split that range into marks that match the viewer's clock. Request timestamps are UTC ISO-8601 text (`2026-03-02T15:10:00+00:00` or `...Z`).

## Guidance

- Keep the summary endpoint unchanged. Serve marks from `GET /api/usage/series?start&end&bucket&tz`.
- Group in SQLite by UTC minute (`substr(timestamp, 1, 16)`), using the same `200–299` status filter as `get_usage_summary`. Fold minutes into hour, day, week (Monday), or month in Python with `zoneinfo`.
- Those aggregates must stay on `idx_requests_usage` (a covering index led by `timestamp`). The status index cannot seek the range and pulls every 2xx row's request and response body.
- Default `tz` is UTC. The browser sends `Intl.DateTimeFormat().resolvedOptions().timeZone`. `bucket_start` is the UTC instant of the local boundary, so `new Date(bucket_start)` labels correctly.
- Choose the bucket from the span when the client omits it: hour ≤ 36h, day ≤ 45d, week ≤ 180d, else month. Coarsen anything that would draw more than 400 marks. All-time series start at the first bucket that has tokens.
- Do not fill marks after the current instant unless a recorded minute falls there.

## Why This Matters

Shifting with one fixed offset mis-assigns tokens across a DST change, and grouping only by UTC hour splits a `+05:30` local hour in two. Minute groups stay inside a single local hour for every real offset, and the series total still matches `/api/usage` for the same range.

## When to Apply

- Changing usage charts, period tabs, or the timestamp column format
- Adding another storage backend: implement `get_usage_series` next to `get_usage_summary`

## Related

- `src/otel_agent/usage_series.py`
- `docs/solutions/performance-issues/usage-query-covering-index.md`
- `frontend/src/components/UsageChart.tsx`
- `docs/solutions/design-patterns/light-theme-token-roles.md` — chart colors read the same CSS variables as the rest of the dashboard
