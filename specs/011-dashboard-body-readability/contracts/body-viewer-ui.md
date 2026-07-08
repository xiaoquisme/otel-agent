# UI Contract: Body Viewer Component

## Component: `renderBodyViewer(container, body, context)`

Renders a request or response body with syntax highlighting, collapsible tree, and semantic annotations into a container DOM element.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `container` | HTMLElement | The DOM element to render into (replaces innerHTML) |
| `body` | string \| null | The raw body string from the API response |
| `context` | `"request"` \| `"response"` | Which body type — controls which semantic annotations apply |

### Behavior

1. **Empty body** (`body` is null, empty, or undefined):
   - Render: `<div class="body-empty">(empty)</div>`
   - No highlighting, no tree

2. **Non-JSON body** (fails `JSON.parse()`):
   - Render: `<div class="body-raw"><pre>{escaped body}</pre></div>`
   - Add note: "Content is not valid JSON"
   - No syntax highlighting applied

3. **JSON body** (valid `JSON.parse()`):
   - Render toggle button: `[Tree] [Raw]`
   - **Tree view**: Nested `<div class="json-tree">` with syntax-highlighted spans
   - **Raw view**: `<pre>{pretty-printed JSON}</pre>`
   - Apply semantic annotations based on `context`
   - If > 50 lines: auto-collapse depth ≥ 1

### DOM Structure (Tree View)

```html
<div class="body-viewer">
  <div class="body-viewer-toolbar">
    <button class="body-toggle active" data-view="tree">Tree</button>
    <button class="body-toggle" data-view="raw">Raw</button>
  </div>
  <div class="body-viewer-tree">
    <div class="json-node json-type-object" data-depth="0">
      <span class="json-toggle">▼</span>
      <span class="json-brace">{</span>
      <div class="json-children">
        <div class="json-node" data-depth="1">
          <span class="json-key">"model"</span>
          <span class="json-colon">:</span>
          <span class="json-string">"gpt-4"</span>
          <span class="json-badge json-badge-model">🎯 Target model</span>
        </div>
        <!-- ... more nodes ... -->
      </div>
      <span class="json-brace">}</span>
    </div>
  </div>
  <div class="body-viewer-raw" style="display:none">
    <pre>{pretty-printed JSON}</pre>
  </div>
</div>
```

### CSS Classes

| Class | Purpose |
|-------|---------|
| `.body-viewer` | Root container |
| `.body-viewer-toolbar` | Toggle button bar |
| `.body-toggle` | View toggle button |
| `.body-toggle.active` | Currently active toggle |
| `.json-node` | A single JSON value container |
| `.json-type-object` | Node containing an object |
| `.json-type-array` | Node containing an array |
| `.json-toggle` | Collapsible toggle icon (▶/▼) |
| `.json-key` | JSON property name |
| `.json-string` | String value |
| `.json-number` | Number value |
| `.json-boolean` | Boolean value |
| `.json-null` | Null value |
| `.json-brace` | Opening/closing braces |
| `.json-colon` | Colon separator |
| `.json-comma` | Comma separator |
| `.json-badge` | Semantic annotation badge |
| `.json-badge-model` | Model-specific badge |
| `.json-badge-messages` | Messages-specific badge |
| `.json-badge-stream` | Stream-specific badge |
| `.json-badge-usage` | Usage summary badge |
| `.body-empty` | Empty body placeholder |
| `.body-raw` | Non-JSON content |
| `.json-children` | Collapsible children container |
| `.json-summary` | Collapsed state summary ("{...}" or "[N items]") |

### Color Constants

```css
.json-key    { color: #79c0ff; }
.json-string { color: #a5d6ff; }
.json-number { color: #d2a8ff; }
.json-boolean { color: #58a6ff; }
.json-null   { color: #8b949e; font-style: italic; }
.json-toggle { color: #8b949e; cursor: pointer; user-select: none; }
.json-badge  { background: #21262d; border: 1px solid #30363d; border-radius: 4px; padding: 1px 6px; font-size: 11px; color: #8b949e; margin-left: 6px; }
```

## Event Delegation

All click handlers are attached to the `.body-viewer` root element (event delegation pattern), not to individual toggle elements. This avoids re-binding handlers when nodes are toggled.

```
body-viewer.addEventListener('click', (e) => {
  const toggle = e.target.closest('.json-toggle');
  if (toggle) → toggleNode(toggle.closest('.json-node'));

  const viewToggle = e.target.closest('.body-toggle');
  if (viewToggle) → switchView(viewToggle.dataset.view);
});
```

## Copy-as-Curl Preservation

The existing `copyCurl()` function operates on the raw request data, not the rendered body. It continues to work unchanged since the body viewer only affects the `<pre>` rendering in the detail panel.
