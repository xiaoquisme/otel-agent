# Data Model: Dashboard Request Section Styling

**Date**: 2026-07-09
**Feature**: 012-dashboard-request-styling

## Overview

This feature is CSS/HTML-only and does not introduce new data entities or modify existing data structures. The data model documents the existing entities affected by the styling changes.

## Existing Entities (Unchanged)

### Detail Section

A section within the detail overlay panel. Each section has a type that determines its visual styling.

| Field | Type | Description |
|-------|------|-------------|
| type | enum | One of: `general`, `request-headers`, `request-body`, `response-headers`, `response-body` |
| header | string | Section title text (e.g., "Request Headers") |
| content | DOM element | The section's content area |
| style | object | Visual properties derived from type |

### Section Style Mapping

| Section Type | CSS Class | Border Color | Background Tint | Icon |
|-------------|-----------|--------------|-----------------|------|
| `general` | `.detail-section` | `#30363d` (default) | none | — |
| `request-headers` | `.detail-section-request` | `#58a6ff` | `rgba(88,166,255,0.05)` | 📤 |
| `request-body` | `.detail-section-request` | `#58a6ff` | `rgba(88,166,255,0.05)` | 📤 |
| `response-headers` | `.detail-section-response` | `#3fb950` | `rgba(63,185,80,0.05)` | 📥 |
| `response-body` | `.detail-section-response` | `#3fb950` | `rgba(63,185,80,0.05)` | 📥 |

## State Transitions

None. Sections are static once rendered; no dynamic state changes apply.

## Validation Rules

- CSS classes must follow the existing naming convention (kebab-case, prefixed with `detail-section-`).
- Colors must be accessible against the `#0f1117` background (WCAG AA contrast ratio ≥ 4.5:1 for text).
- Icons must render correctly in all target browsers (Chrome, Firefox, Safari).
