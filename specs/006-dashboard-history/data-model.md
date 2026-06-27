# Data Model: Dashboard Shows Historical Requests

**Feature**: 006-dashboard-history
**Date**: 2026-06-27

## No Schema Changes

The existing `requests` table and `DashboardAPI` already support all requirements. No new entities or fields needed.

## Key Behavior

- Dashboard reads from `~/.otel-agent/telemetry.db` (absolute path)
- Proxy writes to the same path
- SQLite WAL mode allows concurrent read/write
- Dashboard shows all rows on load, then SSE pushes new rows
