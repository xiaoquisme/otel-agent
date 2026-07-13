---
title: "UI Redesign — Notion-style Block Layout"
type: "feat"
date: "2026-07-13"
topic: "dashboard-ui-redesign"
artifact_contract: "ce-unified-plan/v1"
artifact_readiness: "implementation-ready"
product_contract_source: "ce-plan-bootstrap"
execution: "code"
---

## Goal Capsule

- **Objective:** Redesign the otel-agent dashboard with a Notion-style block layout, fixing the unreadable long request bodies and creating a cohesive design system.
- **Product authority:** User confirmed full redesign with block-based flexible layout.
- **Open blockers:** None.

---

## Problem Frame

The current dashboard has three core UX problems:
1. **Detail view is unusable for long bodies** — request bodies up to 500K are dumped as raw JSON in a tiny slide-over panel
2. **No design system** — 50+ hardcoded color values, inconsistent spacing, no reusable components
3. **Information architecture is flat** — everything competes for attention on one page

---

## Scope Boundaries

### In scope
- Complete redesign of all frontend components
- New design system (colors, typography, spacing, components)
- Dedicated request detail page with proper code viewer
- Block-based layout for detail views (collapsible sections, tabbed content)
- Responsive design
- Keyboard navigation

### Deferred for later
- Real-time streaming in dashboard (current polling is fine)
- User authentication
- Multi-user support
- Dark/light theme toggle (dark only for now)

### Outside this product's identity
- Mobile app
- CLI dashboard
- Export to PDF

---

## Key Technical Decisions

### KTD1: Router for multi-page layout
**Decision:** Use React Router v6 for client-side routing.
**Rationale:** The detail view needs to be a full page (`/request/:id`) to handle long bodies properly. A slide-over panel cannot provide enough screen real estate for 500K+ JSON bodies.
**Alternatives considered:** Keep slide-over (rejected — not enough space), hash routing (rejected — ugly URLs).

### KTD2: Code viewer for JSON bodies
**Decision:** Use `@codemirror/lang-json` for JSON viewing with syntax highlighting, line numbers, folding, and search.
**Rationale:** CodeMirror is lightweight (~50KB), supports JSON natively, and provides the features needed for large JSON bodies (folding, search, jump-to-line). Alternatives like Monaco are too heavy (~2MB) for this use case.
**Alternatives considered:** Monaco Editor (rejected — too heavy), highlight.js only (rejected — no folding/search), raw `<pre>` (rejected — current problem).

### KTD3: Design tokens approach
**Decision:** Use CSS custom properties (already started in `index.css`) as the single source of truth, with Tailwind referencing them.
**Rationale:** CSS variables are runtime-themeable and work with both Tailwind classes and component styles. This extends the existing pattern in `index.css`.
**Alternatives considered:** Tailwind config only (rejected — can't use in component styles), CSS Modules (rejected — too much overhead).

### KTD4: Component library approach
**Decision:** Build a minimal component library (`src/components/ui/`) with reusable primitives (Button, Card, Badge, Tabs, CodeBlock, etc.).
**Rationale:** Notion-style blocks need consistent building blocks. Building 8-10 primitives gives us the flexibility of Notion without the overhead of a full UI library.
**Alternatives considered:** shadcn/ui (rejected — adds Radix dependency), Radix UI primitives (rejected — overkill for this project), Headless UI (rejected — not needed).

---

## Implementation Units

### Existing Codebase Note
The otel-agent frontend already has significant infrastructure in place. The following components and files exist and should be reused/extended rather than rebuilt from scratch:

- `frontend/src/components/RequestTable.tsx`, `RequestRow.tsx` — existing request list
- `frontend/src/components/MessageDisplay.tsx`, `ToolCallBlock.tsx`, `ReasoningBlock.tsx` — existing message rendering
- `frontend/src/components/LatencyChart.tsx` — existing chart (to be replaced with SVG sparkline)
- `frontend/src/components/FilterBar.tsx`, `Pagination.tsx` — existing filter/pagination
- `frontend/src/components/UsageCards.tsx`, `ModelTable.tsx` — existing usage display
- `frontend/src/hooks/useRequests.ts`, `useUsage.ts` — existing data hooks
- `frontend/src/components/ui/` — existing primitives (Button, Card, Badge, Tabs, CodeBlock, Collapsible, SearchInput, Select)
- `frontend/src/styles/globals.css` — existing global styles (~40 hardcoded hex colors must be migrated to tokens)

Each implementation unit should reference the existing file in its Approach section and specify what changes (extension, replacement, or new build). Units that list existing files in their Files list must note "(extend existing)" or "(replace)" after the path.

### U1. Design System Foundation
**Goal:** Establish the design token system and base UI primitives.
**Dependencies:** None.
**Files:**
- `frontend/src/styles/tokens.css` — design tokens (colors, spacing, typography, shadows)
- `frontend/src/styles/globals.css` — global styles, resets, utilities (migrate ~40 hardcoded hex colors to CSS custom property tokens)
- `frontend/src/components/ui/Button.tsx` — button primitive with variants
- `frontend/src/components/ui/Card.tsx` — card container
- `frontend/src/components/ui/Badge.tsx` — status/method badges
- `frontend/src/components/ui/Tabs.tsx` — tabbed interface
- `frontend/src/components/ui/CodeBlock.tsx` — syntax-highlighted code viewer
- `frontend/src/components/ui/Collapsible.tsx` — collapsible sections
- `frontend/src/components/ui/SearchInput.tsx` — search with debounce
- `frontend/src/components/ui/Select.tsx` — dropdown select
- `frontend/src/components/ui/index.ts` — barrel export
- `tests/ui-primitives.test.tsx` — tests for UI primitives

**Approach:**
1. Define design tokens in CSS custom properties (extend existing `index.css` variables)
2. Build each primitive with consistent API (variant prop, size prop, disabled state)
3. All primitives use the token system, no hardcoded colors
4. Each primitive gets a basic render test

**Test scenarios:**
- Button renders with correct variant styles
- Badge displays method/status colors correctly
- Tabs switch content on click
- CodeBlock renders JSON with syntax highlighting
- Collapsible expands/collapses on click
- All primitives accept className override

**Verification:** All primitives render correctly in isolation, tokens are applied consistently.

---

### U2. Router and Layout Shell
**Goal:** Set up React Router with the new page layout structure.
**Dependencies:** U1.
**Files:**
- `frontend/src/router.tsx` — route definitions (must include `*` catch-all route rendering `NotFoundPage`)
- `frontend/src/layouts/DashboardLayout.tsx` — main layout with sidebar/header
- `frontend/src/pages/ListPage.tsx` — request list (replaces current App)
- `frontend/src/pages/DetailPage.tsx` — request detail (new dedicated page)
- `frontend/src/pages/UsagePage.tsx` — usage overview (optional, can be in sidebar)
- `frontend/src/App.tsx` — updated to use router
- `frontend/src/main.tsx` — updated to wrap with RouterProvider
- `tests/router.test.tsx` — routing tests

**Approach:**
1. Define routes: `/` (list), `/request/:id` (detail), `/usage` (optional)
2. DashboardLayout provides consistent header + optional sidebar
3. ListPage is the default view (current RequestList + UsageOverview)
4. DetailPage gets full screen for request details
5. Responsive: sidebar collapses on mobile

**Test scenarios:**
- `/` renders ListPage
- `/request/123` renders DetailPage with id=123
- Unknown route shows 404
  - Requires a `NotFoundPage.tsx` component with a message and link back to `/`.
- Navigation between pages preserves state (search params)

**Verification:** Can navigate between list and detail, URLs are clean, back button works.

---

### U3. Request List Redesign
**Goal:** Rebuild the request list with the new design system.
**Dependencies:** U1, U2.
**Files:**
- `frontend/src/pages/ListPage.tsx` — main list page
- `frontend/src/components/RequestTable.tsx` — table component
- `frontend/src/components/RequestRow.tsx` — row component (updated)
- `frontend/src/components/FilterBar.tsx` — search + filters
- `frontend/src/components/Pagination.tsx` — pagination controls
- `frontend/src/hooks/useRequests.ts` — updated hook (add URL params sync)
- `tests/list-page.test.tsx` — list page tests

**Approach:**
1. ListPage combines header, usage summary, and request table
2. **States:** Loading (skeleton), empty (no requests / zero search results), error (API failure), and success states must be handled in this unit — do not defer to U7.
2. FilterBar: extend existing `FilterBar.tsx` to use new UI primitives (SearchInput, Select). Extract filter logic into a reusable component.
3. RequestRow: extend existing `RequestRow.tsx` to use Badge for method/status, shows latency as a mini sparkline.
4. Pagination: extend existing `Pagination.tsx` to use Button primitives.
5. URL params sync for search/filter state (shareable links) — use `useSearchParams` from React Router to sync filter state to URL.
6. Click row → navigate to `/request/:id`
7. **States:** Loading (skeleton rows), empty (no requests / zero search results with helpful message), error (API failure with retry), and success states.

**Test scenarios:**
- List renders with requests from API
- Search filters requests by URL
- Method filter works
- Status filter works
- Pagination navigates correctly
- Click row navigates to detail page
- URL params reflect current filters

**Verification:** Full list page works with all filters, pagination, and navigation.

---

### U4. Request Detail Page
**Goal:** Build a dedicated detail page with block-based layout for long bodies.
**Dependencies:** U1, U2.
**Files:**
- `frontend/src/pages/DetailPage.tsx` — main detail page
- `frontend/src/components/detail/RequestHeader.tsx` — method, URL, status, latency
- `frontend/src/components/detail/MetadataBlock.tsx` — model, tokens, timing
- `frontend/src/components/detail/ConversationBlock.tsx` — messages with MessageDisplay
- `frontend/src/components/detail/RawBodyBlock.tsx` — raw JSON with CodeMirror
- `frontend/src/components/detail/HeadersBlock.tsx` — request/response headers
- ``frontend/src/hooks/useRequestDetail.ts` — hook that fetches a single request by ID from the API, handles loading/error/not-found states, and returns `{ data, loading, error }`. Follow the pattern of existing `useRequests.ts`.
- `tests/detail-page.test.tsx` — detail page tests

**Approach:**
1. DetailPage loads request by ID from URL params
2. **States:** Loading (skeleton), not found (invalid ID / 404 with back link), error (API failure), and success states.
2. Layout: full-width with collapsible blocks (Notion-style)
3. RequestHeader: prominent method badge, URL, status, latency
4. MetadataBlock: model, tokens, finish reason in a card grid
5. ConversationBlock: full message history with MessageDisplay (not just last message)
6. RawBodyBlock: CodeMirror JSON viewer (requires `@codemirror/lang-json` — install via `npm install @codemirror/lang-json @codemirror/view @codemirror/state`). Lazy-load via dynamic import to avoid adding ~50KB to initial bundle. Features:
   - Syntax highlighting
   - Line numbers
   - Code folding (collapse nested objects)
   - Search (Cmd+F)
   - Copy button
   - Toggle between request/response body
7. HeadersBlock: collapsible key-value display
8. All blocks are collapsible with smooth animation
9. Keyboard: `Esc` to go back (detail page only). J/K navigation is handled globally by U7.

**Test scenarios:**
- Detail page loads request by ID
- RequestHeader shows correct method, URL, status
- MetadataBlock shows model and token counts
- ConversationBlock renders all messages (not just last)
- RawBodyBlock renders JSON with syntax highlighting
- CodeMirror supports search (Cmd+F)
- CodeMirror supports code folding
- Collapsible blocks expand/collapse
- Esc navigates back to list

**Verification:** Can view any request detail, long bodies are readable, all blocks work.

---

### U5. Message Display Improvements
**Goal:** Enhance MessageDisplay to show full conversation history.
**Dependencies:** U1, U4.
**Files:**
- `frontend/src/components/MessageDisplay.tsx` — updated (show all messages)
- `frontend/src/components/ToolCallBlock.tsx` — updated (collapsible, copy button)
- `frontend/src/components/ReasoningBlock.tsx` — updated (collapsible)
- `frontend/src/components/MessageBubble.tsx` — new, individual message component
- `tests/message-display.test.tsx` — message display tests

**Approach:**
1. MessageDisplay renders ALL messages from the conversation (not just last)
2. **States:** Loading (skeleton), empty (no messages), error, and success states.
2. Each message is a MessageBubble with role indicator
3. ToolCallBlock becomes collapsible with argument preview
4. ReasoningBlock becomes collapsible with content preview
5. Messages have consistent spacing and visual hierarchy
6. Copy button on each message and tool call

**Test scenarios:**
- MessageDisplay renders all messages
- MessageBubble shows role badge
- ToolCallBlock collapses/expands
- ReasoningBlock collapses/expands
- Copy button copies message content
- Empty messages show placeholder

**Verification:** Full conversation is visible and readable, all interactive elements work.

---

### U6. Usage Dashboard
**Goal:** Redesign usage overview as a proper dashboard section.
**Dependencies:** U1, U2.
**Files:**
- `frontend/src/components/UsageCards.tsx` — token usage cards
- `frontend/src/components/ModelTable.tsx` — model breakdown table
- `frontend/src/components/LatencySparkline.tsx` — lightweight sparkline (replace Chart.js)
- `frontend/src/hooks/useUsage.ts` — updated hook
- `tests/usage-components.test.tsx` — usage component tests

**Approach:**
1. UsageCards: clean card grid with token counts
2. **States:** Loading (skeleton), empty (no usage data), error, and success states.
2. ModelTable: sortable table with progress bars
3. LatencySparkline: lightweight SVG sparkline — replace existing `LatencyChart.tsx` (which uses Chart.js) with a simple SVG-based component. No external charting dependency needed.
4. Optional: move usage to sidebar or dedicated section
5. Real-time updates via polling (keep existing pattern)

**Test scenarios:**
- UsageCards displays token counts
- ModelTable sorts by tokens
- LatencySparkline renders SVG path
- Empty state shows appropriate message
- Loading state shows skeleton

**Verification:** Usage data displays correctly, sparkline renders, no Chart.js dependency.

---

### U7. Polish and Responsive Design
**Goal:** Final polish, responsive design, and accessibility.
**Dependencies:** U1-U6.
**Files:**
- `frontend/src/styles/responsive.css` — responsive breakpoints
- `frontend/src/components/ui/Tooltip.tsx` — tooltip primitive
- `frontend/src/components/ui/Skeleton.tsx` — loading skeleton
- `frontend/src/hooks/useKeyboard.ts` — keyboard navigation hook
- `tests/responsive.test.tsx` — responsive tests
- `tests/keyboard.test.tsx` — keyboard navigation tests

**Approach:**
1. Responsive: mobile-first with breakpoints at 640px, 768px, 1024px
2. Mobile: list view with push navigation to detail page (consistent with KTD1 routing decision — no slide-over panels)
3. Desktop: full detail page
4. Keyboard: global shortcuts — J/K navigate next/prev request (from any page), Esc back to list, / focus search. These are the ONLY global keyboard shortcuts; page-specific shortcuts (e.g., detail page Esc) are owned by their respective units.
5. Loading skeletons for all async content
6. Tooltips on hover for truncated content
7. ARIA labels for accessibility
8. Focus management for keyboard navigation

**Test scenarios:**
- Mobile layout renders correctly
- Desktop layout renders correctly
- Keyboard shortcuts work
- Focus management is correct
- Loading skeletons display
- Tooltips appear on hover

**Verification:** App works on mobile and desktop, keyboard navigation works, accessibility is good.

---

## Verification Contract

### Automated Tests
Note: No test infrastructure currently exists. U1 must set up the test framework (Vitest + React Testing Library) before any test files can be written.

- Unit tests for all UI primitives (U1) — `tests/ui-primitives.test.tsx`
- Component tests for all major components (U3-U6) — `tests/list-page.test.tsx`, `tests/detail-page.test.tsx`, `tests/message-display.test.tsx`, `tests/usage-components.test.tsx`
- Integration test for routing and navigation (U2) — `tests/router.test.tsx`
- Responsive layout tests (U7) — `tests/responsive.test.tsx`
- Keyboard navigation tests (U7) — `tests/keyboard.test.tsx`

### Manual Verification
- Visual inspection of all pages
- Test with real production data (1000+ requests)
- Test with large request bodies (500K+)
- Test on mobile devices
- Test keyboard navigation

### Performance
- Initial load < 2s
- Detail page render < 500ms
- CodeMirror handles 500K JSON without lag
- No layout shift on load

---

## Risks & Dependencies

### R1: CodeMirror bundle size
**Risk:** CodeMirror adds ~50KB gzipped to the bundle.
**Mitigation:** Lazy-load CodeMirror only on detail page. Use dynamic import.

### R2: Large JSON rendering performance
**Risk:** 500K JSON bodies may cause lag in CodeMirror.
**Mitigation:** CodeMirror handles large documents well. Use virtualization if needed.

### R3: Breaking changes for existing users
**Risk:** URL structure changes (no more hash routing).
**Mitigation:** Add redirects from old URLs if needed.

---

## Sources & Research

- **CodeMirror 6:** https://codemirror.net/ — lightweight, extensible code editor
- **Notion design language:** Block-based, collapsible, clean spacing
- **Vercel dashboard:** Clean dark theme, good use of cards and tables
- **Linear:** Excellent keyboard navigation, clean typography

---

## Definition of Done

- [ ] All UI primitives built and tested
- [ ] Router setup with clean URLs
- [ ] Request list page works with all filters
- [ ] Request detail page handles 500K+ bodies
- [ ] MessageDisplay shows full conversation
- [ ] Usage dashboard displays correctly
- [ ] Responsive on mobile and desktop
- [ ] Keyboard navigation works
- [ ] No hardcoded colors (all from tokens)
- [ ] Bundle size < 200KB gzipped
