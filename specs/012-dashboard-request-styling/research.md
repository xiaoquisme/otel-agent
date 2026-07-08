# Research: Dashboard Request Section Styling

**Date**: 2026-07-09
**Feature**: 012-dashboard-request-styling

## Design Decisions

### Decision 1: Color Theme Assignment

**Decision**: Request sections use cool blue/purple accents; response sections use warm green/amber accents.

**Rationale**: Blue/purple is culturally associated with "outgoing" (sending data), while green/amber is associated with "incoming" (receiving data). This aligns with the request/response semantic meaning. The existing dashboard already uses blue for latency charts and green for success status, so these colors are visually consistent with the project's palette.

**Alternatives considered**:
- Red for request / green for response: Rejected — red implies error/danger, which is misleading for normal requests.
- Same color for both: Rejected — defeats the purpose of visual distinction.
- Purple for both with different saturation: Rejected — insufficient contrast for quick scanning.

### Decision 2: CSS Approach

**Decision**: Add new CSS classes (`.detail-section-request`, `.detail-section-response`) and apply them to existing `<div class="detail-section">` elements via a wrapper or class swap in the `showDetail()` JS function.

**Rationale**: The existing `showDetail()` function dynamically builds the detail overlay HTML. Adding section-type classes at this point is the minimal-change approach. No new DOM structure needed — just class assignments on existing elements.

**Alternatives considered**:
- CSS `:nth-child` selectors: Rejected — fragile, breaks if section order changes.
- Data attributes + CSS: Viable but adds unnecessary complexity for a 2-class solution.
- Inline styles: Rejected — violates Code Quality principle (no inline styles in committed code).

### Decision 3: Icon Strategy

**Decision**: Use Unicode emoji characters (📤 for request, 📥 for response) in section headers via CSS `::before` pseudo-elements.

**Rationale**: Emoji icons are universally supported in modern browsers, require no external dependencies, and render consistently across platforms. They also match the existing annotation badge style (which already uses emoji like 🎯, 💬, 🔧).

**Alternatives considered**:
- SVG icons: Rejected — requires external files or inline SVG, adds complexity.
- Icon font (Font Awesome): Rejected — external dependency, overkill for 2 icons.
- Text-only labels: Rejected — doesn't meet FR-005 requirement for icons.

### Decision 4: Border vs Background Styling

**Decision**: Use left border accent (3px solid) plus subtle background tint for each section type.

**Rationale**: Left border is a common UI pattern for indicating section type without overwhelming the content. The subtle background tint provides additional visual separation. This approach is lightweight and doesn't interfere with the existing JSON viewer styling.

**Alternatives considered**:
- Full background color: Rejected — too heavy, reduces readability of JSON content.
- Top border only: Rejected — less visually prominent than left border.
- Box shadow: Rejected — inconsistent rendering across browsers.

## Color Palette

| Element | Request (cool) | Response (warm) |
|---------|---------------|-----------------|
| Left border | `#58a6ff` (blue) | `#3fb950` (green) |
| Background tint | `rgba(88,166,255,0.05)` | `rgba(63,185,80,0.05)` |
| Header icon | 📤 | 📥 |
| Badge accent | `#a371f7` (purple) | `#d29922` (amber) |

## Summary

All NEEDS CLARIFICATION items resolved. No unresolved dependencies. The feature is a pure CSS/HTML change confined to `index.html` with no backend impact.
