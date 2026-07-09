# Quickstart: Remove Body Tree View

**Date**: 2026-07-09
**Feature**: 015-remove-body-tree-view

## Prerequisites

- otel-agent installed in dev mode: `uv sync --group dev`
- Dashboard running with some logged requests

## Validation Scenarios

### Scenario 1: JSON body displays as raw (syntax-highlighted)

1. Start the dashboard: `uv run otel-agent dashboard`
2. Send a few requests through the proxy (e.g., `curl http://localhost:8080/v1/chat/completions ...`)
3. Open the dashboard in browser
4. Click any request with a JSON response body
5. **Expected**: Response Body section shows syntax-highlighted JSON immediately
6. **Expected**: No "Tree" or "Raw" toggle buttons visible

### Scenario 2: Non-JSON body

1. Trigger a request that returns non-JSON body (e.g., plain text error)
2. Click the request in dashboard
3. **Expected**: Raw text displayed with "Content is not valid JSON" hint below

### Scenario 3: Empty body

1. Click a request with empty response body
2. **Expected**: "(empty)" placeholder displayed in italics

### Scenario 4: No tree DOM elements

1. Open browser DevTools (F12) → Elements tab
2. Click any request with JSON body
3. Inspect the Response Body section
4. **Expected**: No `.body-view-tree`, `.json-node`, `.json-toggle`, or `.body-viewer-toolbar` elements in DOM

### Scenario 5: Existing tests pass

```bash
PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/test_dashboard.py -v
```

**Expected**: All tests pass with zero failures

### Scenario 6: Linting passes

```bash
uv run ruff check src/otel_agent/dashboard/
```

**Expected**: No errors (note: HTML files are not Python-linted, but verify no Python-side changes broke anything)

```bash
uv run ruff check src/
```

**Expected**: Zero errors
