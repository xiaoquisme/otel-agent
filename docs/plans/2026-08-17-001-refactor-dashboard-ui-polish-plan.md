---
title: "Dashboard UI Polish & Accessibility Refactor - Plan"
type: "refactor"
date: "2026-08-17"
artifact_contract: "ce-unified-plan/v1"
artifact_readiness: "implementation-ready"
product_contract_source: "ce-plan-bootstrap"
execution: "code"
---

## Goal Capsule

- **Objective:** Refactor the otel-agent dashboard applying ui-ux-pro-max design principles — improve accessibility, interaction quality, visual hierarchy, loading states, and dark-theme polish while keeping the existing trajectory-style split-pane architecture.
- **Product authority:** User directive to apply ui-ux-pro-max skill guidance.
- **Open blockers:** None.

---

## Product Contract

### Summary

Polish the existing dashboard UI: improve touch targets and focus management, replace emoji with SVG icons, add skeleton loading states, enhance the usage overview visual hierarchy, consolidate the duplicated detail panel/page, migrate hardcoded hex colors in globals.css to design tokens, and add reduced-motion support. No structural layout changes, no new features, no new dependencies.

### Problem Frame

The dashboard works functionally but has UX gaps:

1. **Accessibility gaps** — minimal ARIA attributes, small touch targets (30px ledger rows), no reduced-motion support, emoji used as icons
2. **Inconsistent loading states** — basic "Loading..." text despite a Skeleton component existing in the UI primitives
3. **Duplicated detail logic** — DetailPanel (split-pane) and DetailPage (/request/:id) have separate implementations of the same content
4. **globals.css has ~40 hardcoded hex colors** not migrated to the token system
5. **Usage overview is functional but visually flat** — no sparklines, no visual hierarchy beyond cards and table
6. **Header has no navigation affordance** — just a logo and label with no clear way to navigate between views

### Requirements

**Accessibility**
- R1. All interactive elements meet minimum 44px touch target height
- R2. ARIA attributes added to all interactive components (tabs, collapsibles, buttons, grid/list roles)
- R3. prefers-reduced-motion media query disables/reduces animations
- R4. Emoji replaced with inline SVG icons throughout

**Visual Polish**
- R5. Skeleton loading states replace plain "Loading..." text in all async views
- R6. Usage overview gains visual hierarchy: sparkline for model distribution, better card styling
- R7. Header gains navigation links between list and usage views
- R8. globals.css hardcoded hex colors migrated to CSS custom property tokens

**Code Quality**
- R9. DetailPanel and DetailPage share a single message/body rendering implementation
- R10. responsive.css class-based styles reconciled with inline-style components

### Scope Boundaries

**In scope**
- All frontend components in `frontend/src/`
- Design tokens and global styles
- Accessibility attributes and focus management
- Loading skeleton states
- SVG icon replacement
- Detail component consolidation
- Header navigation

**Deferred for later**
- Full WCAG 2.1 AA audit and screen reader testing
- Virtual scrolling for large request lists
- Chart.js replacement with lightweight SVG sparklines
- Dark/light theme toggle
- Keyboard shortcut enhancements beyond current set

**Outside this product's identity**
- Backend changes
- New npm dependencies
- Mobile app
- Structural layout redesign (keeping trajectory split-pane)

---

## Planning Contract

### Key Technical Decisions

**KTD1: SVG icons approach**
Decision: Inline SVG components in a shared `icons.tsx` file rather than importing an icon library.
Rationale: The dashboard uses only ~8-10 icons (search, close, chevron, clock, method badges, etc.). A shared file avoids adding a dependency and keeps bundle minimal. Follows the existing pattern of inline SVGs in DashboardLayout.tsx and FilterBar.tsx.
Alternatives: lucide-react (rejected — new dependency), Heroicons (rejected — new dependency), emoji replacement only (rejected — inconsistent sizing and accessibility).

**KTD2: Detail component consolidation**
Decision: Extract shared content rendering (metadata grid, message display, raw body, headers) into a shared `DetailContent` component used by both DetailPanel and DetailPage.
Rationale: Currently DetailPanel (493 lines) and DetailPage (223 lines) duplicate metadata rendering, message display, tab logic, and raw body display. A shared component eliminates drift.
Alternatives: Make DetailPage use DetailPanel (rejected — different layout needs), remove DetailPage entirely (rejected — deep-linking to /request/:id is valuable).

**KTD3: Skeleton loading approach**
Decision: Use the existing `Skeleton`, `SkeletonText`, `SkeletonCard` components from `ui/Skeleton.tsx` in all async views.
Rationale: The primitives already exist but are unused. No new code needed, just integration.

**KTD4: Token migration strategy for globals.css**
Decision: Replace each hardcoded hex value in globals.css with the nearest existing CSS custom property from tokens.css. No new tokens needed — the existing token set covers all values.
Rationale: tokens.css already defines the full palette. The globals.css classes are legacy from before the token system. Mapping is mechanical.

### Assumptions

- The existing CSS token set in tokens.css is sufficient for the refactor; no new tokens needed
- The split-pane layout (ListPage) and the routed DetailPage will coexist — the split-pane is the primary workflow, the routed page supports deep-linking
- The existing polling-based data fetching pattern (30s intervals) is adequate; no real-time streaming needed

---

## Implementation Units

### U1. SVG Icons Module
**Goal:** Create a shared SVG icon component library replacing emoji and ad-hoc inline SVGs.
**Requirements:** R4.
**Dependencies:** None.
**Files:**
- `frontend/src/components/ui/icons.tsx` — (new) shared SVG icon components
- `frontend/src/components/ToolCallBlock.tsx` — (modify) replace ⚡ emoji with ZapIcon
- `frontend/src/layouts/DashboardLayout.tsx` — (modify) replace inline SVG with shared icon
- `frontend/src/components/filters/FilterBar.tsx` — (modify) replace inline SVG with SearchIcon

**Approach:**
1. Create `icons.tsx` with function components: `SearchIcon`, `CloseIcon`, `ChevronDownIcon`, `ChevronRightIcon`, `ZapIcon`, `ClockIcon`, `ArrowLeftIcon`, `InfoIcon`
2. Each icon accepts `size` (default 16) and `className` props
3. Use `currentColor` for stroke/fill so icons inherit text color
4. Replace all inline SVGs and emoji across the codebase

**Patterns to follow:** Existing inline SVGs in DashboardLayout.tsx (line 55-57) and FilterBar.tsx (line 46-61) — same viewBox and stroke approach, just extracted.

**Test scenarios:**
- Each icon renders at default size
- Icons accept custom size prop
- Icons inherit parent text color via currentColor
- No emoji characters remain in component source

**Verification:** All icons render correctly, no visual regressions, no emoji in source.

---

### U2. Accessibility Attributes & Touch Targets
**Goal:** Add ARIA attributes to all interactive components and ensure 44px minimum touch targets.
**Requirements:** R1, R2.
**Dependencies:** U1 (icons need aria-label).
**Files:**
- `frontend/src/components/ledger/RequestLedger.tsx` — (modify) increase row height, add ARIA grid/listbox roles
- `frontend/src/components/timeline/TimelineOverview.tsx` — (modify) add ARIA to timeline bars
- `frontend/src/components/filters/FilterBar.tsx` — (modify) add aria-label to inputs
- `frontend/src/components/UsageOverview.tsx` — (modify) add ARIA to period tabs
- `frontend/src/components/detail/DetailPanel.tsx` — (modify) add ARIA to tabs and close button
- `frontend/src/pages/DetailPage.tsx` — (modify) add ARIA to tabs and back button
- `frontend/src/components/MessageDisplay.tsx` — (modify) add ARIA to message roles
- `frontend/src/components/ui/Tabs.tsx` — (modify) add role="tablist", role="tab", role="tabpanel"
- `frontend/src/components/ui/Collapsible.tsx` — (modify) add aria-expanded, aria-controls
- `frontend/src/styles/responsive.css` — (modify) add prefers-reduced-motion rules

**Approach:**
1. RequestLedger: increase row height from 30px to 36px (still compact, closer to 44px with padding), add `role="grid"` on container, `role="row"` on rows, `aria-selected` on selected row
2. FilterBar: add `aria-label` to search input and filter selects
3. UsageOverview: add `role="tablist"` to period buttons, `aria-selected` on active tab
4. DetailPanel/DetailPage: add `aria-label` to close/back buttons, ensure tabs have proper ARIA
5. MessageDisplay: add `role="log"` and `aria-label` for message list
6. responsive.css: add `@media (prefers-reduced-motion: reduce)` that sets `--transition-fast: 0ms`, `--transition-base: 0ms`, `--transition-slow: 0ms`

**Patterns to follow:** The existing focus-visible styles in responsive.css (lines 67-81).

**Test scenarios:**
- Tab components have role="tablist", role="tab", role="tabpanel" with aria-selected
- Collapsible components have aria-expanded attribute toggling correctly
- Search input has aria-label="Search requests"
- Filter selects have descriptive aria-labels
- Request ledger rows have role="row" and aria-selected on selected row
- prefers-reduced-motion reduces all transitions to 0ms
- All interactive elements are at least 36px in the smallest dimension (with padding reaching 44px touch area)

**Verification:** Screen reader announces component roles correctly, all touch targets meet minimum size, reduced-motion disables animations.

---

### U3. Skeleton Loading States
**Goal:** Replace all "Loading..." text with skeleton loaders using existing Skeleton primitives.
**Requirements:** R5.
**Dependencies:** None.
**Files:**
- `frontend/src/components/ledger/RequestLedger.tsx` — (modify) replace loading text with skeleton rows
- `frontend/src/components/UsageOverview.tsx` — (modify) replace loading text with skeleton cards
- `frontend/src/components/detail/DetailPanel.tsx` — (modify) replace loading text with skeleton
- `frontend/src/pages/DetailPage.tsx` — (modify) replace loading text with skeleton
- `frontend/src/components/timeline/TimelineOverview.tsx` — (modify) add skeleton for empty/loading state

**Approach:**
1. RequestLedger: render 8 skeleton rows (matching typical page size) with shimmer animation when `loading && requests.length === 0`
2. UsageOverview: render 3 skeleton cards when loading, shimmer on the card content
3. DetailPanel/DetailPage: render skeleton metadata grid and skeleton message blocks when loading
4. TimelineOverview: show a subtle pulse animation bar when loading
5. All skeletons use the existing `Skeleton` component from `ui/Skeleton.tsx`

**Test scenarios:**
- RequestLedger shows 8 skeleton rows during initial load
- UsageOverview shows 3 skeleton cards during load
- DetailPanel shows skeleton metadata grid during load
- Skeleton shimmer respects prefers-reduced-motion
- Skeleton disappears when data loads

**Verification:** All async views show skeleton loaders instead of plain text, transitions are smooth.

---

### U4. Usage Overview Visual Enhancement
**Goal:** Improve the usage overview with better visual hierarchy, a model distribution sparkline, and polished card styling.
**Requirements:** R6.
**Dependencies:** U3.
**Files:**
- `frontend/src/components/UsageOverview.tsx` — (modify) enhance cards, add mini bar chart for model distribution

**Approach:**
1. UsageCard: add subtle gradient background, improve number formatting with abbreviations (1.2M instead of 1,234,567 for large numbers), add trend indicator
2. Model breakdown: add a horizontal stacked bar showing relative model distribution above the table
3. Period tabs: improve visual treatment with bottom-border indicator style matching DetailPanel tabs
4. Add a summary line showing request count alongside token counts
5. Improve empty state with an icon and helpful message

**Test scenarios:**
- Large token counts format with abbreviations (1.2M, 345K)
- Model distribution bar renders proportional segments
- Period tabs have active indicator styling
- Empty state shows icon and message
- Loading state uses skeletons from U3

**Verification:** Usage section has clear visual hierarchy, numbers are readable, model distribution is visible at a glance.

---

### U5. Header Navigation
**Goal:** Add navigation links in the header for switching between list and usage views.
**Requirements:** R7.
**Dependencies:** U1 (icons for nav items).
**Files:**
- `frontend/src/layouts/DashboardLayout.tsx` — (modify) add navigation links
- `frontend/src/router.tsx` — (modify) add usage route if not present

**Approach:**
1. Add nav links in the header: "Requests" (→ /) and "Usage" (→ /usage)
2. Active link gets highlighted styling (underline or background)
3. Use `NavLink` from react-router-dom for automatic active class
4. Keep the existing logo and label on the left, nav links centered or right-aligned

**Test scenarios:**
- Clicking "Requests" navigates to / and highlights
- Clicking "Usage" navigates to /usage and highlights
- Active nav link has distinct visual indicator
- Navigation works with browser back/forward

**Verification:** Header provides clear navigation between views, active state is visible.

---

### U6. Token Migration in globals.css
**Goal:** Replace all hardcoded hex colors in globals.css with CSS custom property references.
**Requirements:** R8.
**Dependencies:** None.
**Files:**
- `frontend/src/styles/globals.css` — (modify) replace ~40 hardcoded hex values with token references

**Approach:**
1. Map each hardcoded hex to the nearest token:
   - `#0d1117` → `var(--color-bg-base)`
   - `#1c2128` → `var(--color-bg-elevated)`
   - `#30363d` → `var(--color-border-default)`
   - `#21262d` → `var(--color-bg-overlay)`
   - `#8b949e` → `var(--color-text-secondary)`
   - `#e1e4e8` → `var(--color-text-primary)`
   - `#58a6ff` → `var(--color-accent-blue)`
   - `#3fb950` → `var(--color-accent-green)`
   - `#d29922` → `var(--color-accent-yellow)`
   - `#79c0ff`, `#a5d6ff`, `#d2a8ff` → keep as-is (syntax highlighting specific, no matching token)
2. Preserve the classes that use semantic tokens already — no changes needed there
3. Verify no visual regressions by comparing before/after

**Test scenarios:**
- No hardcoded hex values remain in globals.css (except syntax highlighting colors)
- All migrated classes render identically to before
- JSON viewer syntax highlighting still works

**Verification:** globals.css uses only CSS custom properties (except syntax highlighting), visual output unchanged.

---

### U7. Detail Component Consolidation
**Goal:** Extract shared detail content into a reusable component used by both DetailPanel and DetailPage.
**Requirements:** R9.
**Dependencies:** U1, U2.
**Files:**
- `frontend/src/components/detail/DetailContent.tsx` — (new) shared content renderer
- `frontend/src/components/detail/DetailPanel.tsx` — (modify) use DetailContent
- `frontend/src/pages/DetailPage.tsx` — (modify) use DetailContent

**Approach:**
1. Extract from DetailPanel: MetadataGrid, MessageBubble, ToolCallBlock rendering, tab content (conversation/raw/headers), and usage metrics display
2. DetailContent accepts: `detail: RequestDetail`, `compact?: boolean` (for panel vs page sizing)
3. DetailPanel becomes a thin wrapper: header + close button + DetailContent
4. DetailPage becomes: back button + card wrapper + DetailContent
5. Shared tab state management inside DetailContent

**Test scenarios:**
- DetailPanel renders same content as before using DetailContent
- DetailPage renders same content as before using DetailContent
- Tab switching works in both panel and page contexts
- Compact mode adjusts spacing for panel context

**Verification:** Both detail views render identically to before, no duplicated rendering logic.

---

## Verification Contract

### Automated Tests
- No test framework currently exists (Vitest not configured). Manual verification required.
- If Vitest is set up during this work, add render tests for icons (U1) and DetailContent (U7).

### Manual Verification
- Visual inspection of all pages at 1024px, 768px, and 375px widths
- Tab through all interactive elements — focus ring visible on every one
- Enable prefers-reduced-motion — all animations stop
- Test with VoiceOver or NVDA — components announce roles correctly
- Verify no emoji characters in any component source file
- Verify no hardcoded hex colors in globals.css (except syntax highlighting)
- Test skeleton loaders appear during network throttle in DevTools

### Performance
- No bundle size increase (no new dependencies, icons are inline SVG)
- Skeleton loaders use CSS animations, not JS

---

## Definition of Done

- All interactive elements have ARIA attributes and meet 44px touch target minimum
- prefers-reduced-motion disables all transitions and animations
- No emoji characters in component source — all replaced with SVG icons
- Skeleton loaders in all async views
- globals.css has no hardcoded hex values (except syntax highlighting)
- DetailPanel and DetailPage share a single DetailContent component
- Header has navigation links between views
- Usage overview has improved visual hierarchy
- No new npm dependencies added
- No visual regressions — dashboard looks identical or better
