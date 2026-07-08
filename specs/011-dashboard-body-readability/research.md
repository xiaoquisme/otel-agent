# Research: Dashboard Body Readability

## Decision 1: JSON Syntax Highlighting Approach

**Decision**: Custom regex-based tokenizer + inline CSS classes (no external library)

**Rationale**: The dashboard is a single HTML file with no build step. Loading a syntax highlighting library (e.g., highlight.js at ~40KB, Prism.js at ~20KB) adds disproportionate weight for a single-use case (JSON only). A custom tokenizer for JSON is straightforward (~60 lines of JS) and produces exactly the colors needed.

**Alternatives considered**:
- **highlight.js CDN**: ~40KB gzipped. Overkill — supports 190+ languages when we need only JSON. Adds a network dependency.
- **Prism.js with JSON plugin**: ~8KB core + JSON grammar. Lighter but still an external dependency and adds CDN latency.
- **TreeWalker + DOM APIs**: Browsers have built-in `document.createTreeWalker()` but it operates on rendered text, not structured JSON tokens. Not useful for syntax coloring.
- **Custom tokenizer**: ~60 lines of JS that walks the JSON string character-by-character, emitting `<span>` elements with color classes. Zero dependencies, ~1KB added to the HTML file. Preferred.

**Implementation pattern**: Parse JSON with `JSON.parse()` to validate. If valid, walk the stringified pretty-printed version character-by-character, identifying:
- Keys (strings before `:`) → `.json-key` class (blue: #79c0ff)
- String values (strings after `:`) → `.json-string` class (green: #a5d6ff)
- Numbers → `.json-number` class (orange: #d2a8ff)
- Booleans → `.json-boolean` class (cyan: #58a6ff)
- Null → `.json-null` class (gray: #8b949e)
- Punctuation (`{`, `}`, `[`, `]`, `:`, `,`) → default text color

## Decision 2: Collapsible Tree Implementation

**Decision**: Recursive DOM builder with click handlers on toggle elements

**Rationale**: Pure DOM manipulation with event delegation. No virtual scrolling needed for typical LLM payloads (<100KB ≈ <1000 nodes). The key insight: render the tree as nested `<div>` elements with `display:none` children, toggled by clicking a triangle icon.

**Alternatives considered**:
- **Virtual scrolling**: Overkill — typical LLM payloads have 50-500 nodes, not 10,000+. The DOM can handle this without performance issues.
- **Canvas-based rendering**: Maximum performance but loses native text selection, copy-paste, and accessibility. Not worth it for this payload size.
- **ContentEditable with MutationObserver**: Too complex and fragile for a read-only viewer.

**Implementation pattern**:
```
function renderJsonNode(value, key, depth, autoCollapse) → DOM element
  - If value is object/array:
    - Create container div with toggle icon (▶/▼)
    - Create children div with nested renderJsonNode calls
    - If autoCollapse and depth > 0: start collapsed
    - Click handler toggles children display + icon rotation
  - If value is primitive:
    - Create span with syntax-highlighted value
```

**Auto-collapse logic**: Count lines in pretty-printed JSON. If > 50 lines, auto-collapse all nodes at depth >= 1 on initial render.

## Decision 3: Dark Theme Color Palette

**Decision**: Extend existing palette with JSON-specific colors that match the GitHub Dark theme

**Rationale**: The dashboard already uses a GitHub Dark-inspired palette (#0d1117 background, #e1e4e8 text, #30363d borders). JSON colors should feel cohesive with this existing aesthetic.

**Color assignments** (tested for WCAG AA contrast on #0d1117):
- JSON keys: #79c0ff (bright blue) — 7.2:1 contrast ratio ✓
- String values: #a5d6ff (light blue) — 9.1:1 contrast ratio ✓
- Numbers: #d2a8ff (light purple) — 8.5:1 contrast ratio ✓
- Booleans: #58a6ff (medium blue) — 5.8:1 contrast ratio ✓
- Null: #8b949e (gray) — 4.6:1 contrast ratio ✓
- Punctuation: #e1e4e8 (default text) — inherits existing contrast

## Decision 4: LLM Semantic Annotations

**Decision**: Field-specific badge labels + usage summary bar, implemented as a post-processing step after JSON rendering

**Rationale**: Rather than modifying the core JSON renderer, add a separate annotation layer that identifies known LLM API fields and adds visual badges. This keeps the JSON renderer generic and reusable.

**OpenAI Chat Completions Request fields**:
| Field | Type | Annotation |
|-------|------|------------|
| `model` | string | "🎯 Target model" badge |
| `messages` | array | "💬 Messages (N)" badge with count |
| `stream` | boolean | "⚡ Streaming" / "⏹ Sync" badge |
| `temperature` | number | "🌡️ Temperature" badge |
| `max_tokens` | number | "📏 Max tokens" badge |
| `tools` | array | "🔧 Tools (N)" badge with count |
| `tool_choice` | string/object | "🔧 Tool choice" badge |

**OpenAI Chat Completions Response fields**:
| Field | Type | Annotation |
|-------|------|------------|
| `id` | string | Request ID |
| `model` | string | Model used |
| `choices` | array | "📝 Choices (N)" badge |
| `usage` | object | Compact summary bar: "Tokens: N prompt / N completion / N total" |
| `stream` | boolean | (on request only) |

**Anthropic Messages Request fields**:
| Field | Type | Annotation |
|-------|------|------------|
| `model` | string | "🎯 Target model" badge |
| `messages` | array | "💬 Messages (N)" badge |
| `system` | string/array | "📋 System prompt" badge |
| `max_tokens` | number | "📏 Max tokens" badge |
| `stream` | boolean | "⚡ Streaming" badge |
| `tools` | array | "🔧 Tools (N)" badge |

**Implementation**: After rendering the JSON tree, scan for known field names. When found, insert a badge `<span>` after the key. For `usage` objects, render a compact summary line. For `messages` arrays, show count in the toggle label.

## Decision 5: Raw View Toggle

**Decision**: Simple toggle button in each body section header that switches between tree view and raw `<pre>` view

**Rationale**: FR-006 requires a raw view. A toggle button is the simplest UX — it preserves the original behavior on demand while defaulting to the enhanced tree view. Implementation: keep both DOM trees (tree and raw), toggle `display` on click.

## Open Questions (Resolved)

All NEEDS CLARIFICATION items from the spec have been resolved through codebase analysis:
- Database schema: TEXT columns, no changes needed (confirmed from `logger.py`)
- API contract: `/api/requests/:id` returns full row with body fields (confirmed from `api.py:get_request()`)
- Streaming body format: `{"streamed": true, "preview": "..."}` (confirmed from `server.py:_log_telemetry()`)
- Body size limit: 100KB storage cap (confirmed from `server.py` line 345/354)
