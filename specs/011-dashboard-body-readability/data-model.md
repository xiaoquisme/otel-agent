# Data Model: Dashboard Body Readability

## Overview

This feature is purely client-side — no database schema changes. The data model describes the in-memory structures used by the JSON body viewer component.

## In-Memory Structures

### JsonNode (DOM Tree Representation)

Represents a parsed JSON value rendered as a collapsible DOM tree.

| Field | Type | Description |
|-------|------|-------------|
| `type` | enum | One of: `object`, `array`, `string`, `number`, `boolean`, `null` |
| `key` | string \| null | The JSON key (property name) if inside an object, null for array items and root |
| `value` | any | The raw JSON value (object, array, string, number, boolean, null) |
| `depth` | integer | Nesting depth (0 = root) |
| `element` | HTMLElement | The DOM element representing this node |
| `collapsed` | boolean | Whether the node's children are currently hidden |
| `children` | JsonNode[] | Child nodes (empty for primitives) |

### SemanticAnnotation

Maps known LLM API field names to visual badges.

| Field | Type | Description |
|-------|------|-------------|
| `fieldName` | string | The JSON key name (e.g., "model", "messages") |
| `badge` | string | Display text for the badge (e.g., "🎯 Target model") |
| `badgeClass` | string | CSS class for badge styling |
| `context` | enum | `request` \| `response` \| `both` — which body type this applies to |
| `formatValue` | function \| null | Optional formatter for the value (e.g., token count summary) |

### LLM_FIELD_ANNOTATIONS (Constant Map)

Static mapping of known LLM API fields to their annotations:

**Request-only annotations**:
- `model` → 🎯 Target model
- `stream` → ⚡ Streaming / ⏹ Sync
- `temperature` → 🌡️ Temperature
- `max_tokens` → 📏 Max tokens
- `max_completion_tokens` → 📏 Max completion tokens
- `tools` → 🔧 Tools (N)
- `tool_choice` → 🔧 Tool choice
- `system` → 📋 System prompt

**Response-only annotations**:
- `id` → Request ID
- `model` → Model used
- `choices` → 📝 Choices (N)
- `usage` → Token usage summary
- `finish_reason` → Finish reason

**Both**:
- `messages` → 💬 Messages (N)

## Body Size Thresholds

| Threshold | Behavior |
|-----------|----------|
| 0 bytes | Show "(empty)" |
| 1-10,000 chars | Full tree view, all nodes expanded |
| 10,001-100,000 chars | Full tree view, auto-collapse depth ≥ 1 |
| Non-JSON | Plain text, no highlighting, "Raw content" note |

## State Transitions

### Detail Panel Open Flow

```
User clicks row
  → fetch /api/requests/:id
  → parse response
  → determine body type:
      → JSON valid? → JsonNode tree → renderJsonNode() → highlight + annotate
      → JSON invalid? → plain text display
  → if tree > 50 lines → auto-collapse depth ≥ 1
  → render in detail panel
```

### Toggle Collapse Flow

```
User clicks toggle icon
  → event delegation catches click
  → find parent JsonNode
  → toggle collapsed state
  → update children display (none/block)
  → update icon (▶/▼)
  → update summary label ({...}/[N items])
```

### Raw/Tree Toggle Flow

```
User clicks "Raw" / "Tree" toggle button
  → swap visibility of tree-container / raw-container
  → no re-parsing — both views pre-rendered
```
