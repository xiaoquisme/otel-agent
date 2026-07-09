# Research: Remove Body Tree View

**Date**: 2026-07-09
**Feature**: 015-remove-body-tree-view

## Dead Code Audit

The dashboard is a single-file application (`src/otel_agent/dashboard/index.html`). The Tree view was introduced in specs 011 (body readability) and 012 (request styling). Analysis of all Tree-related symbols:

### JavaScript Functions & Constants

| Symbol | Lines | Used By | Verdict |
|--------|-------|---------|---------|
| `renderJsonNode(value, key, depth, autoCollapse, context)` | 353-477 | `initBodyViewers` only | REMOVE |
| `toggleJsonNode(nodeEl)` | 480-486 | Click event delegation (`.json-toggle`) | REMOVE |
| `initBodyViewers()` | 588-601 | `showDetail` post-DOM-insertion | REMOVE |
| `countJsonLines(value)` | 344-346 | `formatBody` for auto-collapse | REMOVE |
| `AUTO_COLLAPSE_THRESHOLD` | 350 | `formatBody` | REMOVE |
| `getAnnotation(fieldName, context, value)` | 514-527 | `renderJsonNode` only | REMOVE |
| `LLM_REQUEST_ANNOTATIONS` | 491-501 | `getAnnotation` only | REMOVE |
| `LLM_RESPONSE_ANNOTATIONS` | 504-511 | `getAnnotation` only | REMOVE |

### JavaScript Functions (Shared — KEEP)

| Symbol | Used By Tree? | Used By Raw? | Verdict |
|--------|--------------|--------------|---------|
| `escapeHtml(s)` | Yes | Yes (highlightJsonString) | KEEP |
| `highlightJsonString(value, indent)` | No (tree uses DOM) | Yes (raw view) | KEEP |
| `formatBody(b, context)` | Yes (generates tree container) | Yes (generates raw) | SIMPLIFY |

### CSS Classes

| Class | Tree-only? | Verdict |
|-------|-----------|---------|
| `.json-toggle`, `.json-toggle:hover` | Yes | REMOVE |
| `.json-node` | Yes | REMOVE |
| `.json-badge`, `.json-badge-*` | Yes (renderJsonNode) | REMOVE |
| `.json-children` | Yes (renderJsonNode) | REMOVE |
| `.json-summary` | Yes (renderJsonNode) | REMOVE |
| `.body-viewer-toolbar` | Yes | REMOVE |
| `.body-toggle`, `.body-toggle.active` | Yes | REMOVE |
| `.json-key`, `.json-string`, `.json-number`, `.json-boolean`, `.json-null` | Shared | KEEP |
| `.body-empty`, `.body-raw` | No (raw view) | KEEP |

## Decision: Annotation System

**Decision**: Remove entirely.

**Rationale**: `LLM_REQUEST_ANNOTATIONS`, `LLM_RESPONSE_ANNOTATIONS`, and `getAnnotation()` are exclusively consumed by `renderJsonNode()` to attach semantic badges (e.g., "Target model", "Messages (3)") to tree nodes. Since the Raw view uses `highlightJsonString()` (a pure HTML string renderer), it never calls `getAnnotation()`. Removing the tree removes the only consumer.

**Alternatives considered**:
- Keep annotations for future use: Rejected — YAGNI. Annotations can be re-added if a tree view is ever reintroduced.

## Decision: formatBody Simplification

**Decision**: Replace the entire body-viewer div (with toggle toolbar + dual containers) with a single raw container.

**Before** (pseudocode):
```
body-viewer
  ├── body-viewer-toolbar (Tree | Raw buttons)
  ├── body-view-tree (placeholder, filled by initBodyViewers)
  └── body-view-raw (display:none, shown on toggle)
```

**After** (pseudocode):
```
body-raw
  └── pre (highlighted JSON)
```

The `formatBody` function simplifies to:
1. Empty body → `(empty)` placeholder (unchanged)
2. Non-JSON → raw text + hint (unchanged)
3. Valid JSON → `highlightJsonString(parsed, 0)` wrapped in `<pre>` (no toggle, no tree)

## Impact Assessment

- **Lines removed**: ~200 (JS functions, CSS rules, toggle HTML)
- **Lines modified**: ~5 (formatBody simplified, initBodyViewers call removed, event delegation trimmed)
- **Lines added**: 0
- **Risk**: Very low — removing unused UI path, existing functionality preserved
- **Dependencies**: None — single-file change, no backend/API impact
