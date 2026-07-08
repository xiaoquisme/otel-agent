# Quickstart: Dashboard Request Section Styling

**Date**: 2026-07-09
**Feature**: 012-dashboard-request-styling

## Prerequisites

- otel-agent proxy running with some logged requests (or mock data in the SQLite database)
- Modern browser (Chrome, Firefox, or Safari)

## Validation Scenarios

### Scenario 1: Visual Distinction (P1)

**Setup**: Start the dashboard with a database containing at least one logged request.

```bash
cd /path/to/otel-agent
uv run otel-agent dashboard --db ./data/requests.db
```

**Steps**:
1. Open `http://localhost:8080` in browser
2. Click any request row in the table
3. Observe the detail overlay

**Expected outcome**:
- Request Headers section has a blue left border accent
- Request Body section has a blue left border accent
- Response Headers section has a green left border accent
- Response Body section has a green left border accent
- General section has no colored border (default styling)

### Scenario 2: Icons and Labels (P2)

**Steps** (same setup as Scenario 1):
1. Open the detail overlay for any request
2. Inspect each section header

**Expected outcome**:
- Request Headers shows "📤 Request Headers"
- Request Body shows "📤 Request Body"
- Response Headers shows "📥 Response Headers"
- Response Body shows "📥 Response Body"

### Scenario 3: JSON Viewer Preserved (FR-008)

**Steps**:
1. Open detail overlay for a request with a JSON body (e.g., an LLM API call)
2. Click "Tree" and "Raw" toggles in both Request Body and Response Body
3. Click collapsible JSON nodes (▶/▼ toggles)

**Expected outcome**:
- Tree view renders with syntax highlighting
- Raw view shows formatted JSON
- Collapsible nodes expand/collapse correctly
- Semantic annotations (🎯 Model, 💬 Messages, etc.) appear on JSON keys
- All functionality works identically to before the styling change

### Scenario 4: Responsive Layout (FR-007)

**Steps**:
1. Open the detail overlay
2. Resize the browser window to 400px width
3. Observe section layout

**Expected outcome**:
- Sections stack vertically without overlap
- Left border accents remain visible
- Content remains readable (no horizontal overflow)

## References

- [Dashboard Styling Contract](./contracts/dashboard-styling.md) — CSS class specifications
- [Data Model](./data-model.md) — Section type and style mapping
