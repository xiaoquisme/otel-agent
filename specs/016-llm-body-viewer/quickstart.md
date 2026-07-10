# Quickstart: LLM-Aware Body Viewer

**Date**: 2026-07-09
**Feature**: 016-llm-body-viewer

## Prerequisites

- otel-agent installed in dev mode: `uv sync --group dev`
- Dashboard running with logged LLM API requests (both OpenAI and Anthropic formats)

## Validation Scenarios

### Scenario 1: OpenAI request body renders as chat

1. Start the dashboard: `uv run otel-agent dashboard`
2. Send an OpenAI chat completion request through the proxy
3. Open dashboard, click the request
4. **Expected**: Request Body section shows messages in chat format:
   - "system" label with muted style, content rendered as text
   - "user" label, content rendered as text
   - "assistant" label (if present), content rendered as markdown
5. **Expected**: "Show Raw" toggle button visible

### Scenario 2: OpenAI response body renders markdown

1. Send a request that returns a response with markdown content (code blocks, lists, bold)
2. Click the request in dashboard
3. **Expected**: Response body shows:
   - Model name as prominent label
   - Finish reason displayed (e.g., "stop")
   - Token usage summary bar (existing)
   - Message content rendered as formatted markdown (code blocks have dark background, lists are bulleted, bold is bold)

### Scenario 3: Anthropic request body renders

1. Send an Anthropic messages API request through the proxy
2. Click the request in dashboard
3. **Expected**: Messages displayed in chat format with role labels
4. **Expected**: `system` field (if present) shown as system message

### Scenario 4: Anthropic response body renders

1. Send a request that returns Anthropic response format
2. Click the request in dashboard
3. **Expected**: Content blocks rendered as markdown
4. **Expected**: Model name and stop_reason displayed

### Scenario 5: Raw JSON toggle works

1. Click any request with LLM-format body
2. Click "Show Raw" button
3. **Expected**: Body switches to syntax-highlighted JSON view
4. Click "Show Formatted" button
5. **Expected**: Body switches back to LLM chat/markdown view

### Scenario 6: Non-LLM body fallback

1. Send a non-LLM request (e.g., plain REST API)
2. Click the request in dashboard
3. **Expected**: Body shows as syntax-highlighted JSON (no chat UI, no toggle)

### Scenario 7: Empty and non-JSON bodies

1. Click a request with empty body → "(empty)" placeholder
2. Click a request with non-JSON body → raw text with "Content is not valid JSON" hint

### Scenario 8: XSS protection

1. Craft a request where message content contains `<script>alert(1)</script>`
2. View the request in dashboard
3. **Expected**: Script tag is sanitized, not executed. Content shows as text.

### Scenario 9: Large content handling

1. Send a request with very long message content (>10,000 characters)
2. View the request in dashboard
3. **Expected**: Content renders without browser freeze, scrollable within container

### Scenario 10: Existing tests pass

```bash
PYTHONPATH="$(pwd):$(pwd)/src" uv run pytest tests/test_dashboard.py -v
```

**Expected**: All 20 tests pass with zero failures
