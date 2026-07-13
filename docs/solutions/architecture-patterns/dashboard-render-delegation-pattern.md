---
title: "Dashboard Render Delegation Pattern: Move LLM Response Rendering to Backend"
date: "2026-07-13"
category: "architecture-patterns"
module: "dashboard"
problem_type: "architecture_pattern"
component: "tooling"
severity: "medium"
applies_when:
  - "Dashboard renders complex data that duplicates backend format knowledge"
  - "Frontend has hand-rolled rendering logic that must stay in sync with backend converters"
  - "Separate dashboard process causes database lock conflicts with the main application"
tags:
  - "dashboard"
  - "fastapi"
  - "frontend-backend-separation"
  - "llm-response-rendering"
  - "backend-renderer"
  - "single-process-merge"
---

# Dashboard Render Delegation Pattern: Move LLM Response Rendering to Backend

## Context

The otel-agent project is a Python FastAPI LLM API gateway with DuckDB storage. It has a dashboard UI that lets users browse captured LLM requests and responses. The dashboard originally ran as a **separate process**: a `BaseHTTPRequestHandler` serving static HTML on port 9090, while the FastAPI proxy ran on port 8080. The dashboard's `index.html` contained ~500 lines of hand-rolled JavaScript that manually detected LLM response formats (OpenAI, Anthropic, streaming), extracted content from deeply nested JSON, rendered markdown client-side (via `marked.js` and `DOMPurify`), and built chat bubble UI — all duplicated from knowledge that already existed in Python's `converter.py`.

This architecture caused recurring dashboard rendering bugs (specs 011, 012, 018, 020) because every new LLM format required coordinated changes in both Python (storage/conversion) and JavaScript (rendering). The DuckDB multi-process lock conflicts (BUG-001, BUG-02) compounded the pain, since two Python processes competed for the same database file.

The problem was not a bug in either layer — it was an **architecture gap**: format knowledge was duplicated across language boundaries, with no single source of truth for how to detect and render LLM responses.

## Guidance

**Consolidate frontend rendering into the backend process when format knowledge already exists server-side, using FastAPI sub-mounts to preserve separation of concerns.**

The pattern has five concrete steps:

### 1. Merge the dashboard into the FastAPI process

Mount the dashboard as a FastAPI sub-application on the same port as the proxy. Use `app.include_router()` for the dashboard routes, not route merging — this preserves clean separation between proxy logic and dashboard logic while sharing a single process and database connection.

```python
# src/otel_agent/server.py
from fastapi import FastAPI
from src.otel_agent.dashboard.routes import router as dashboard_router

app = FastAPI()
app.include_router(dashboard_router, prefix="/api")
```

This eliminates the DuckDB multi-process lock problem immediately.

### 2. Store format metadata at write time

Add a `format` tag (`openai`, `anthropic`, `streaming`) to the request storage schema at capture time, when the proxy already knows the format. This inverts the frontend's heuristic detection — instead of the dashboard guessing the format from raw JSON, the storage layer stamps it definitively.

```python
# src/otel_agent/storage/base.py
class RequestRecord(TypedDict, total=False):
    format: str | None  # "openai" | "anthropic" | "streaming"
```

### 3. Create a server-side rendering module

Build a Python module (`render.py`) that owns all format detection, markdown rendering, and chat bubble generation. Use the `markdown` library with `bleach` for safe HTML output. This module replaces the 12 JS functions in `index.html` with a single, testable Python module.

```python
# src/otel_agent/dashboard/render.py
import markdown
import bleach

def render_response_body(body: str, format_tag: str | None) -> str:
    """Render LLM response body to HTML based on format tag."""
    content = extract_content(body, format_tag)
    html = markdown.markdown(content, extensions=["fenced_code", "tables"])
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)
```

### 4. Expose rendering via API endpoint

Add a `/api/render/{id}` endpoint that returns pre-rendered HTML for a stored request. Also include `rendered_request` / `rendered_response` fields in the existing detail endpoint. Render at API response time, not at storage time, to avoid schema migrations.

```python
# src/otel_agent/dashboard/routes.py
@router.get("/render/{request_id}")
def render_request(request_id: int) -> JSONResponse:
    result = api.get_rendered_request(request_id)
    return JSONResponse({
        "rendered_request": result["rendered_request"],
        "rendered_response": result["rendered_response"],
    })
```

### 5. Simplify the frontend

Replace the 500+ lines of JS format detection, extraction, and rendering with calls to the API. The `index.html` shrinks from 995 to 684 lines. The 12 JS functions and CDN imports for `marked.js` and `DOMPurify` are removed entirely.

```javascript
// Before: 12 functions, 2 CDN imports, format guessing logic
// After:
const res = await fetch(`/api/requests/${id}`);
const { rendered_response } = await res.json();
document.getElementById("response").innerHTML = rendered_response;
```

## Why This Matters

The original architecture had a fundamental flaw: **format knowledge was duplicated across language boundaries**. Every new LLM format (or format variation) required:

1. Python changes in `converter.py` to detect and convert the format
2. JavaScript changes in `index.html` to detect and render the format

These changes had to stay in sync manually. When they drifted, dashboard rendering bugs appeared — and they did, repeatedly (specs 011, 012, 018, 020). The root cause was not carelessness; it was an architecture that made drift inevitable.

The consolidated architecture eliminates this duplication. Format knowledge lives in one place (Python's `render.py`). The frontend becomes a thin consumer of pre-rendered HTML. New formats require changes in one file, not two languages.

The secondary benefit — eliminating DuckDB lock conflicts — was a free win from process consolidation. But the primary value is **single source of truth for format handling**.

## When to Apply

- The frontend contains significant rendering logic that duplicates knowledge already present in the backend
- Format detection or content extraction logic exists in both Python/JS and has drifted
- Multiple processes share a database and cause lock contention
- Dashboard rendering bugs recur whenever the backend adds new formats
- The single-file HTML constraint means all rendering logic lives in one place anyway (no React/Vue to abstract it)

This pattern is especially relevant for API gateways, log viewers, and monitoring dashboards where the data format is complex and already known at capture time.

## Examples

### Before: Separate process with duplicated format knowledge

```python
# server.py — two processes, two ports
def start_proxy():
    uvicorn.run(app, host="0.0.0.0", port=8080)

def start_dashboard():
    server = HTTPServer(("0.0.0.0", 9090), DashboardHandler)
    server.serve_forever()
```

```javascript
// index.html — 500+ lines of JS format detection
function detectFormat(body) {
  if (body.choices) return "openai";
  if (body.content) return "anthropic";
  if (body.delta) return "streaming";
  // ... more heuristic checks
}

function extractContent(body, format) {
  if (format === "openai") return body.choices[0].message.content;
  if (format === "anthropic") return body.content[0].text;
  // ... more extraction per format
}

// 12 more functions for markdown rendering, bubble generation, etc.
```

### After: Single process with server-side rendering

```python
# server.py — one process, one port
app = FastAPI()
app.include_router(dashboard_router, prefix="/api")
uvicorn.run(app, host="0.0.0.0", port=8080)
```

```python
# render.py — single source of truth
def render_response_body(body: str, format_tag: str | None) -> str:
    content = extract_content(body, format_tag)
    html = markdown.markdown(content, extensions=["fenced_code", "tables"])
    return bleach.clean(html)
```

```javascript
// index.html — thin consumer
const res = await fetch(`/api/requests/${id}`);
const { rendered_response } = await res.json();
document.getElementById("response").innerHTML = rendered_response;
```

### Files changed in the otel-agent implementation

| File | Change |
|------|--------|
| `src/otel_agent/dashboard/render.py` | Created — 573 lines, format detection + markdown rendering |
| `src/otel_agent/dashboard/routes.py` | Created — FastAPI router with `/api/render/{id}` endpoint |
| `tests/test_render.py` | Created — 68 tests for render module |
| `src/otel_agent/server.py` | Modified — sub-mount dashboard router |
| `src/otel_agent/dashboard/api.py` | Modified — integrate render module |
| `src/otel_agent/storage/*.py` | Modified — add format tag to storage schema |
| `src/otel_agent/logger.py` | Modified — stamp format at capture time |
| `src/otel_agent/dashboard/index.html` | Simplified — 995 → 684 lines |

## Related

- Specs: 004 (web dashboard), 011 (body readability), 014 (dashboard-proxy routing), 016 (LLM body viewer) — all had high overlap with this pattern; this refactor supersedes their architectural assumptions
- Bugs: BUG-001, BUG-02 (DuckDB multi-process lock conflicts resolved by process merge)
- Implementation plan: `docs/plans/2026-07-13-001-refactor-dashboard-fastapi-merge-plan.md`
