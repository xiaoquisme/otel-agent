# Tasks: Dashboard Request Section Styling

**Input**: Design documents from `/specs/012-dashboard-request-styling/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Not included — this is a visual/CSS feature verified by manual inspection per quickstart.md.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

All changes are in a single file: `src/otel_agent/dashboard/index.html`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No setup needed — existing project with established dashboard structure.

(Skipped — no project initialization required.)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No foundational tasks — this feature modifies existing CSS/HTML in a single file with no new infrastructure.

(Skipped — no blocking prerequisites.)

---

## Phase 3: User Story 1 - Visual Distinction Between Request and Response (Priority: P1) 🎯 MVP

**Goal**: Add colored borders and background tints to distinguish request sections from response sections in the detail overlay.

**Independent Test**: Open dashboard, click a request row, verify request sections have blue left border and response sections have green left border.

### Implementation for User Story 1

- [x] T001 [US1] Add CSS classes `.detail-section-request` and `.detail-section-response` with border-left and background-tint properties in `src/otel_agent/dashboard/index.html` (CSS `<style>` block, after existing `.detail-section` styles)
- [x] T002 [US1] Update `showDetail()` function in `src/otel_agent/dashboard/index.html` to apply `.detail-section-request` class to Request Headers and Request Body section `<div>` elements
- [x] T003 [US1] Update `showDetail()` function in `src/otel_agent/dashboard/index.html` to apply `.detail-section-response` class to Response Headers and Response Body section `<div>` elements

**Checkpoint**: At this point, User Story 1 should be fully functional — request and response sections have distinct visual treatments.

---

## Phase 4: User Story 2 - Request Section Icons and Labels (Priority: P2)

**Goal**: Add icons (📤/📥) to section headers for quick visual scanning.

**Independent Test**: Open detail overlay, verify each section header shows an appropriate icon alongside its text label.

### Implementation for User Story 2

- [x] T004 [P] [US2] Add CSS rule for `.detail-section-request h3::before` with content "📤" and appropriate spacing in `src/otel_agent/dashboard/index.html`
- [x] T005 [P] [US2] Add CSS rule for `.detail-section-response h3::before` with content "📥" and appropriate spacing in `src/otel_agent/dashboard/index.html`

**Checkpoint**: At this point, User Stories 1 AND 2 should both work — sections have colored borders AND icons.

---

## Phase 5: User Story 3 - Consistent Color Theme (Priority: P3)

**Goal**: Ensure request sections use a consistent cool color palette and response sections use a warm palette, including JSON badge accents.

**Independent Test**: Open detail overlay, verify all request-related elements (borders, backgrounds, JSON badges) share one color family and response elements share another.

### Implementation for User Story 3

- [x] T006 [US3] Review existing JSON badge classes (`.json-badge-model`, `.json-badge-messages`, etc.) in `src/otel_agent/dashboard/index.html` and confirm they already use the request color theme (blue/purple) — document findings, adjust if needed
- [x] T007 [US3] Verify response JSON badge classes (`.json-badge-usage`, etc.) use warm colors (amber/green) — document findings, adjust if needed

**Checkpoint**: All user stories should now be independently functional with consistent color theming.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Verification and final polish.

- [ ] T008 Verify JSON viewer functionality preserved: Tree/Raw toggle, collapsible nodes, syntax highlighting, semantic annotations all work in `src/otel_agent/dashboard/index.html`
- [ ] T009 Run quickstart.md validation scenarios (4 scenarios) against live dashboard to confirm all acceptance criteria met
- [ ] T010 Verify responsive layout at 400px and 1920px viewport widths — sections stack correctly, no visual overlap

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Skipped — no setup needed
- **Foundational (Phase 2)**: Skipped — no blocking prerequisites
- **User Story 1 (Phase 3)**: Can start immediately — no dependencies
- **User Story 2 (Phase 4)**: Can start after Phase 3 (needs CSS classes from T001 to exist)
- **User Story 3 (Phase 5)**: Can start after Phase 3 (needs CSS classes to review)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Independent — can start immediately
- **User Story 2 (P2)**: Depends on US1 (uses `.detail-section-request`/`.detail-section-response` classes for `::before` styling)
- **User Story 3 (P3)**: Depends on US1 (reviews and adjusts colors defined in US1)

### Within Each User Story

- CSS classes before HTML template changes
- Implementation before verification

### Parallel Opportunities

- T004 and T005 (US2 icons) can run in parallel (different CSS rules, same file but non-overlapping)
- T006 and T007 (US3 color review) can run in parallel (independent color checks)

---

## Parallel Example: User Story 2

```bash
# Launch both icon tasks together:
Task: "Add CSS rule for .detail-section-request h3::before with content 📤 in index.html"
Task: "Add CSS rule for .detail-section-response h3::before with content 📥 in index.html"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 3: User Story 1 (T001-T003)
2. **STOP and VALIDATE**: Verify blue/green borders and background tints in browser
3. Deploy if ready — core visual distinction is achieved

### Incremental Delivery

1. Complete User Story 1 → Test in browser → Deploy (MVP!)
2. Add User Story 2 (icons) → Test in browser → Deploy
3. Add User Story 3 (color refinement) → Test in browser → Deploy
4. Run Polish phase → Final verification → Done

### Implementation Notes

- All changes are in `src/otel_agent/dashboard/index.html` — single file, no new files
- CSS changes go in the `<style>` block (after line ~88, before `</style>`)
- HTML template changes go in the `showDetail()` function (around lines 253-275)
- No backend changes, no new dependencies, no config changes
