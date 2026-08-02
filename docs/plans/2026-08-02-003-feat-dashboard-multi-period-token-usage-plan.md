# Implementation Plan: Dashboard Multi-Period Token Usage Display

**Branch**: `feat/dashboard-token-usage-display` | **Date**: 2026-08-02 | **Input**: User request: "Add today/this week/this month token usage display by model and also show total on dashboard"

## Summary

Extend the existing dashboard usage overview to display token consumption across four time periods — Today, This Week, This Month, and All Time — with per-model breakdowns for each period. The backend `/api/usage` endpoint currently caps ranges at 48 hours; this plan relaxes that constraint and adds a lightweight aggregation endpoint for wider ranges. The frontend adds tab navigation to switch between periods, each fetching its own usage summary.

## Technical Context

**Language/Version**: Python 3.10+; React 18 + TypeScript  
**Primary Dependencies**: FastAPI, httpx, SQLite (stdlib), React  
**Storage**: Existing `requests` table with `model_name`, `input_tokens`, `output_tokens`, `total_tokens` columns  
**Testing**: pytest (backend), existing test patterns  
**Target Platform**: macOS/Linux/Windows proxy and browser dashboard

## Key Changes

### 1. Backend: Remove 48-hour range limit on `/api/usage`

**File**: `src/otel_agent/dashboard/routes.py`  
**Change**: Remove the `(end_dt - start_dt).total_seconds() > 48 * 3600` guard. The existing `get_usage_summary` query in SQLite already handles arbitrary date ranges via `timestamp >= ? AND timestamp < ?`. The 48h limit was a DuckDB-era safeguard; with SQLite + WAL, wide-range aggregations are safe.

**File**: `src/otel_agent/dashboard/api.py`  
**Change**: No changes needed — `get_usage_summary` already delegates to storage with arbitrary start/end.

### 2. Frontend: Add time period tabs to UsageOverview

**File**: `frontend/src/components/UsageOverview.tsx`  
**Change**: Replace the single "Usage Today" section with a tabbed interface. Tabs: Today | This Week | This Month | All Time. Each tab fetches its own usage data for the corresponding UTC range. Active tab defaults to "Today".

**Tab ranges** (computed client-side in local time, converted to UTC):
- **Today**: `start = today 00:00 local` → `end = tomorrow 00:00 local`
- **This Week**: `start = this Monday 00:00 local` → `end = next Monday 00:00 local`
- **This Month**: `start = this month 1st 00:00 local` → `end = next month 1st 00:00 local`
- **All Time**: `start = 2000-01-01T00:00:00Z` → `end = now`

### 3. Frontend: Extend useUsage hook

**File**: `frontend/src/hooks/useUsage.ts`  
**Change**: The hook currently only fetches "Today". Extend it to accept a `period` parameter and fetch the corresponding date range. Or create separate hook instances per tab. The simplest approach: one `useUsage(period)` hook that recomputes the range when `period` changes.

### 4. Frontend: Add tabs UI component

**File**: `frontend/src/components/UsageOverview.tsx`  
**Change**: Add a simple tab bar at the top of the usage section. Use existing `Tabs` component if available, or inline styled tabs matching the dark theme.

### 5. Tests

**File**: `tests/test_dashboard.py`  
**Change**: Add test that `/api/usage` accepts ranges wider than 48 hours and returns correct aggregates.

## Implementation Steps

1. **Backend**: Remove the 48-hour range limit from `routes.py` (1 line change)
2. **Backend**: Add test for wide-range usage queries
3. **Frontend**: Update `useUsage` hook to accept a period parameter and compute date ranges
4. **Frontend**: Update `UsageOverview` to add tab navigation and render per-period data
5. **Frontend**: Build and verify the frontend compiles
6. **Run tests**: `pytest -m 'not integration'`

## File Summary

| File | Action | Description |
|------|--------|-------------|
| `src/otel_agent/dashboard/routes.py` | MODIFY | Remove 48h range limit |
| `frontend/src/hooks/useUsage.ts` | MODIFY | Accept period param, compute ranges |
| `frontend/src/components/UsageOverview.tsx` | MODIFY | Add tabs, render per-period data |
| `tests/test_dashboard.py` | MODIFY | Add wide-range usage test |

## Risks

- **Wide-range queries on large databases**: With 100k+ records, a full-time-range GROUP BY could be slow. Mitigation: SQLite handles this well with the existing `idx_requests_timestamp` index; can add index on `model_name` if needed.
- **Frontend bundle size**: No new dependencies — tabs are inline styled components.
