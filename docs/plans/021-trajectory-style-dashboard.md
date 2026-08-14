# Trajectory-Style Dashboard Redesign

## Metadata

- **artifact_contract**: ce-unified-plan/v1
- **artifact_readiness**: implementation-ready
- **execution**: code
- **created**: 2026-08-14
- **branch**: feat/trajectory-style-dashboard

## Problem

The current otel-agent dashboard has a basic table layout with a separate detail page. It lacks the sophisticated visualization patterns seen in the deepseek-harness Trajectory UI, which provides a much richer experience for inspecting LLM request/response logs. The user wants to redesign the dashboard to adopt these patterns.

## Design Reference: deepseek-harness Trajectory UI

The Trajectory UI from deepseek-harness provides these key patterns:
1. **Timeline visualization** — Horizontal bar chart showing operations over time with three lanes (system/context, message, tool)
2. **Turn-based organization** — Messages grouped by "turns" with collapsible groups
3. **Cell-based records** — Each event is a compact row with index, kind tag, text preview, metrics, and elapsed time
4. **Split-pane layout** — Table on left, detail panel on right (resizable)
5. **Request boundaries** — Visual dots/markers between requests
6. **Turn rails** — Vertical accent lines showing turn scope
7. **Duration modes** — Sequence, duration, time, actual
8. **Usage metrics** — Input/output/cache/reasoning tokens per request
9. **Timing info** — TTFT, throughput, generation time
10. **Collapsible turns** — Fold/unfold turn groups
11. **Search** — Full-text search across all records
12. **Virtual scrolling** — For performance with large logs

## Scope

Redesign the otel-agent dashboard frontend to adopt Trajectory UI patterns while adapting them for the proxy logging context. The backend API remains unchanged — this is a pure frontend redesign.

### In Scope

1. **Layout redesign** — Split-pane layout (table + detail panel)
2. **Timeline overview** — Horizontal timeline bar showing request distribution and latency
3. **Request ledger** — Turn-based table with kind tags, metrics, and elapsed time
4. **Detail panel** — Right-side panel showing conversation, raw data, headers
5. **Collapsible turns** — Group requests by time window and allow fold/unfold
6. **Request boundaries** — Visual markers between request groups
7. **Turn rails** — Vertical accent lines
8. **Search and filters** — Enhanced search with filter bar
9. **Virtual scrolling** — For performance (if needed for large logs)
10. **Duration display** — Show elapsed time per request
11. **Usage metrics display** — Show tokens in each request row
12. **Keyboard navigation** — Arrow keys, Enter, Escape

### Out of Scope

- Backend API changes (existing API is sufficient)
- Real-time streaming (proxy logs are historical)
- Authentication/authorization
- Data export (already exists)

## Architecture

### Current Structure
```
frontend/src/
├── App.tsx                    # Router
├── main.tsx                   # Entry
├── router.tsx                 # Routes
├── index.css                  # Global styles
├── layouts/
│   └── DashboardLayout.tsx    # Header + Outlet
├── pages/
│   ├── ListPage.tsx           # UsageOverview + LatencyChart + RequestTable
│   └── DetailPage.tsx         # Full detail view
├── components/
│   ├── RequestTable.tsx       # Table with filters
│   ├── RequestRow.tsx         # Single row (unused)
│   ├── MessageDisplay.tsx     # Conversation messages
│   ├── ToolCallBlock.tsx      # Tool call display
│   ├── UsageOverview.tsx      # Usage cards
│   ├── LatencyChart.tsx       # Latency chart
│   ├── DetailPanel.tsx        # Side panel (unused)
│   ├── ui/                    # UI primitives
│   └── ...
├── hooks/
│   ├── useRequests.ts         # Request data
│   ├── useUsage.ts            # Usage data
│   └── useKeyboard.ts         # Keyboard shortcuts
└── api/
    ├── client.ts              # API calls
    └── types.ts               # TypeScript types
```

### New Structure
```
frontend/src/
├── App.tsx                    # (unchanged)
├── main.tsx                   # (unchanged)
├── router.tsx                 # (unchanged — single page app)
├── index.css                  # (unchanged)
├── layouts/
│   └── DashboardLayout.tsx    # (redesigned — split-pane layout)
├── pages/
│   └── ListPage.tsx           # (redesigned — timeline + ledger + detail)
├── components/
│   ├── timeline/
│   │   ├── TimelineOverview.tsx    # Horizontal timeline bar
│   │   └── TimelineOverview.css    # Timeline styles
│   ├── ledger/
│   │   ├── RequestLedger.tsx       # Turn-based request table
│   │   ├── RequestLedgerRow.tsx    # Single ledger row
│   │   ├── TurnGroup.tsx           # Collapsible turn group
│   │   ├── RequestBoundary.tsx     # Boundary marker
│   │   └── ledger.css              # Ledger styles
│   ├── detail/
│   │   ├── DetailPanel.tsx         # Right-side detail panel
│   │   ├── ConversationView.tsx    # Message display
│   │   ├── RawView.tsx             # Raw JSON view
│   │   └── detail.css              # Detail styles
│   ├── filters/
│   │   ├── FilterBar.tsx           # Search + method + status filters
│   │   └── filters.css             # Filter styles
│   └── ui/                         # (existing, unchanged)
├── hooks/
│   ├── useRequests.ts              # (unchanged)
│   ├── useUsage.ts                 # (unchanged)
│   ├── useKeyboard.ts              # (enhanced)
│   └── useTimeline.ts              # NEW — timeline data derivation
└── api/
    ├── client.ts                   # (unchanged)
    └── types.ts                    # (unchanged)
```

## Implementation Plan

### Task 1: DashboardLayout — Split-Pane Shell

**Goal:** Create the split-pane layout with a table area (left) and detail panel (right).

**Files:**
- `frontend/src/layouts/DashboardLayout.tsx` — Redesign to split-pane
- `frontend/src/layouts/split-pane.css` — Split-pane styles

**Changes:**
- Replace the full-width layout with a flex container
- Left pane: scrollable table area (flex: 1)
- Right pane: detail panel (resizable, default 40%, min 300px)
- Add a resize handle between panes
- Keep the header but make it part of the left pane

**Verification:**
- Layout renders with two panes
- Resize handle works
- Responsive: collapses to stacked on narrow screens

### Task 2: FilterBar — Search and Filters

**Goal:** Replace the inline filters in RequestTable with a dedicated filter bar.

**Files:**
- `frontend/src/components/filters/FilterBar.tsx` — New component
- `frontend/src/components/filters/filters.css` — Styles

**Changes:**
- Search input with debounce
- Method dropdown (GET/POST/PUT/DELETE)
- Status dropdown (200/400/404/500)
- Keyboard shortcut: `/` to focus search
- Compact design matching Trajectory UI toolbar

**Verification:**
- Filters work as before
- Keyboard shortcut works
- Visual style matches Trajectory UI

### Task 3: TimelineOverview — Horizontal Timeline

**Goal:** Add a horizontal timeline bar showing request distribution over time.

**Files:**
- `frontend/src/components/timeline/TimelineOverview.tsx` — New component
- `frontend/src/components/timeline/TimelineOverview.css` — Styles
- `frontend/src/hooks/useTimeline.ts` — Timeline data derivation

**Changes:**
- Horizontal bar showing requests as colored spans
- Color by method (GET=green, POST=purple, etc.)
- Height proportional to latency
- Click to scroll to request
- Hover to show tooltip with details

**Verification:**
- Timeline renders with correct proportions
- Click navigates to request
- Hover shows tooltip

### Task 4: RequestLedger — Turn-Based Table

**Goal:** Replace the basic table with a turn-based ledger matching Trajectory UI patterns.

**Files:**
- `frontend/src/components/ledger/RequestLedger.tsx` — New component
- `frontend/src/components/ledger/RequestLedgerRow.tsx` — Row component
- `frontend/src/components/ledger/TurnGroup.tsx` — Collapsible group
- `frontend/src/components/ledger/RequestBoundary.tsx` — Boundary marker
- `frontend/src/components/ledger/ledger.css` — Styles

**Changes:**
- Compact rows (30px height) with:
  - Index (#N)
  - Kind tag (REQUEST, RESPONSE, TOOL)
  - Text preview (method + URL path)
  - Metrics (input/output tokens)
  - Elapsed time
- Turn groups with collapsible headers
- Request boundary dots between groups
- Vertical accent rails
- Hover highlighting
- Selected row state

**Verification:**
- Rows render with correct data
- Collapse/expand works
- Boundaries visible
- Selection works

### Task 5: DetailPanel — Right-Side Inspector

**Goal:** Implement the detail panel showing full request/response data.

**Files:**
- `frontend/src/components/detail/DetailPanel.tsx` — Main panel
- `frontend/src/components/detail/ConversationView.tsx` — Messages
- `frontend/src/components/detail/RawView.tsx` — Raw JSON
- `frontend/src/components/detail/detail.css` — Styles

**Changes:**
- Tabs: Conversation | Raw | Headers
- Conversation view: message bubbles with role tags
- Raw view: formatted JSON with syntax highlighting
- Headers view: key-value pairs
- Metadata grid at top
- Copy as curl button
- Keyboard: Escape to close

**Verification:**
- Panel opens when row is selected
- Tabs work
- Content displays correctly
- Escape closes panel

### Task 6: ListPage Integration

**Goal:** Integrate all new components into the ListPage.

**Files:**
- `frontend/src/pages/ListPage.tsx` — Redesign

**Changes:**
- Replace UsageOverview + LatencyChart + RequestTable with:
  - FilterBar at top
  - TimelineOverview below filter bar
  - RequestLedger in left pane
  - DetailPanel in right pane
- Wire up state: selected request → detail panel
- Keyboard navigation: ↑↓ to navigate, Enter to select

**Verification:**
- All components render together
- State flows correctly
- Keyboard navigation works

### Task 7: Build and Test

**Goal:** Ensure the frontend builds and the dashboard works end-to-end.

**Files:**
- `frontend/dist/` — Build output

**Changes:**
- Run `npm run build` in frontend/
- Copy dist to src/otel_agent/dashboard/frontend_dist/
- Test with `otel-agent dashboard`

**Verification:**
- Build succeeds with no errors
- Dashboard serves correctly
- All features work

## Key Design Decisions

1. **Single-page app** — Keep the existing router structure. The detail panel opens as a split-pane overlay, not a separate route.
2. **No virtual scrolling yet** — The current data volume doesn't require it. Add later if needed.
3. **No timeline modes** — Start with sequence mode only. Duration/time modes can be added later.
4. **Inline metrics** — Show input/output tokens directly in the row, not in a separate column.
5. **Dark theme** — Keep the existing dark theme tokens.
6. **Responsive** — Stack panes on narrow screens (< 768px).

## Success Criteria

1. Dashboard loads and displays requests in the new layout
2. Timeline overview shows request distribution
3. Ledger rows show kind tags, metrics, and elapsed time
4. Detail panel opens with full request data
5. Search and filters work
6. Keyboard navigation works
7. Build succeeds
8. No regressions in existing API functionality
