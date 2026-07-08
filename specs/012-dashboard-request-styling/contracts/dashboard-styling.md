# Contract: Dashboard Styling Classes

**Date**: 2026-07-09
**Feature**: 012-dashboard-request-styling

## CSS Class Contract

The dashboard detail overlay uses the following CSS classes to style sections by type. This contract documents the expected visual behavior for each class.

### `.detail-section-request`

Applies to: Request Headers, Request Body sections.

```css
.detail-section-request {
  border-left: 3px solid #58a6ff;
  background: rgba(88, 166, 255, 0.05);
  padding-left: 12px;
}
```

**Expected behavior**:
- Blue left border accent (3px solid)
- Subtle blue background tint
- Section header shows 📤 icon via `::before` pseudo-element
- Content area inherits existing styles (pre blocks, JSON viewer, etc.)

### `.detail-section-response`

Applies to: Response Headers, Response Body sections.

```css
.detail-section-response {
  border-left: 3px solid #3fb950;
  background: rgba(63, 185, 80, 0.05);
  padding-left: 12px;
}
```

**Expected behavior**:
- Green left border accent (3px solid)
- Subtle green background tint
- Section header shows 📥 icon via `::before` pseudo-element
- Content area inherits existing styles

### `.detail-section` (General)

No changes. The General section retains its current styling.

## HTML Template Contract

The `showDetail()` function must assign the appropriate class to each section div:

```html
<div class="detail-section detail-section-request">
  <h3>📤 Request Headers</h3>
  <pre>...</pre>
</div>

<div class="detail-section detail-section-response">
  <h3>📥 Response Body</h3>
  <div class="body-viewer">...</div>
</div>
```

**Rules**:
- Each section `<div>` must have both `detail-section` and the type-specific class.
- Icons are embedded in the `<h3>` text, not via `::before` (simpler, no CSS specificity issues).
- The `detail-section` base class provides default spacing; the type-specific class adds border and background.

## Backward Compatibility

- The `detail-section` base class is preserved — any code that targets it continues to work.
- No existing CSS selectors are modified or removed.
- The JSON viewer, Tree/Raw toggle, and annotation badges are unaffected.
