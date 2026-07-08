# Quickstart: Dashboard Body Readability

## Prerequisites

- Python environment with otel-agent installed (`uv sync --group dev`)
- A running proxy instance that has logged at least one request
- A modern browser (Chrome 90+, Firefox 90+, Safari 15+)

## Validation Scenarios

### Scenario 1: JSON Syntax Highlighting (P1)

**Setup**: Start the proxy and send a chat completions request:
```bash
# Terminal 1: Start proxy
uv run otel-agent proxy --port 18765

# Terminal 2: Send a test request
curl http://localhost:18765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"test/model","messages":[{"role":"user","content":"Hello"}]}'
```

**Steps**:
1. Open `http://localhost:9090` (dashboard)
2. Click the logged request row in the table
3. Verify the detail panel opens with the request body section

**Expected**:
- [ ] JSON keys (e.g., `"model"`, `"messages"`) appear in blue (#79c0ff)
- [ ] String values (e.g., `"test/model"`, `"Hello"`) appear in light blue (#a5d6ff)
- [ ] Numbers appear in purple (#d2a8ff)
- [ ] Booleans appear in medium blue (#58a6ff)
- [ ] Null values appear in gray italic (#8b949e)
- [ ] Indentation is consistent 2-space

### Scenario 2: Collapsible Tree (P2)

**Setup**: Use the same request from Scenario 1, or send a multi-message request:
```bash
curl http://localhost:18765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"test/model","messages":[{"role":"system","content":"You are helpful"},{"role":"user","content":"Hello"},{"role":"assistant","content":"Hi there"},{"role":"user","content":"How are you?"}],"temperature":0.7}'
```

**Steps**:
1. Open the request detail panel
2. Click the ▼ icon next to the `"messages"` array

**Expected**:
- [ ] Clicking ▼ collapses the messages array, showing `[4 items]` summary
- [ ] Clicking ▶ expands it back, showing all 4 message objects
- [ ] Each message object also has its own collapse/expand toggle
- [ ] Toggling does not re-render the entire body

### Scenario 3: Auto-Collapse for Large Bodies (FR-004)

**Setup**: Send a request with a very large messages array (50+ items or long content):
```bash
# Generate a request with many messages
python3 -c "
import json, requests
msgs = [{'role': 'user', 'content': f'Message {i}'} for i in range(60)]
resp = requests.post('http://localhost:18765/v1/chat/completions', json={
    'model': 'test/model',
    'messages': msgs,
    'max_tokens': 100
})
print(resp.status_code)
"
```

**Steps**:
1. Open the request detail panel in the dashboard

**Expected**:
- [ ] Body renders without UI lag
- [ ] Top-level objects/arrays are collapsed by default
- [ ] User can expand specific sections without scrolling through everything

### Scenario 4: LLM Semantic Annotations (P3)

**Setup**: Send a standard chat completions request with common fields:
```bash
curl http://localhost:18765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"Hello"}],"stream":true,"temperature":0.7,"max_tokens":100}'
```

**Steps**:
1. Open the request detail panel
2. Inspect the request body section

**Expected**:
- [ ] `"model"` field has a "🎯 Target model" badge
- [ ] `"messages"` field has a "💬 Messages (1)" badge
- [ ] `"stream"` field shows "⚡ Streaming" or "⏹ Sync" badge based on value
- [ ] `"temperature"` field has a "🌡️ Temperature" badge
- [ ] `"max_tokens"` field has a "📏 Max tokens" badge

### Scenario 5: Raw View Toggle (FR-006)

**Steps**:
1. Open any request detail panel
2. Click the "Raw" toggle button in the body section

**Expected**:
- [ ] Body switches to plain pretty-printed JSON (no highlighting, no tree)
- [ ] Clicking "Tree" switches back to the enhanced view
- [ ] Both views show the same content

### Scenario 6: Non-JSON Body Handling (FR-008)

**Setup**: Send a request that results in a non-JSON response (or use a raw text body):
```bash
curl http://localhost:18765/v1/chat/completions \
  -H "Content-Type: text/plain" \
  -d "plain text body"
```

**Expected**:
- [ ] Body displays as plain text
- [ ] No syntax highlighting applied
- [ ] A note indicates "Content is not valid JSON"
- [ ] No crash or rendering error

### Scenario 7: Empty Body (Edge Case)

**Steps**:
1. Start a GET request to the proxy (e.g., `/v1/models`)
2. Open the request detail panel

**Expected**:
- [ ] Request body section shows "(empty)"
- [ ] Response body section shows the JSON response with highlighting

### Scenario 8: Copy-as-Curl Still Works (FR-010)

**Steps**:
1. Open any request detail panel
2. Click the "Copy as curl" button

**Expected**:
- [ ] Curl command is copied to clipboard
- [ ] The curl command is valid and can be pasted into a terminal
- [ ] This works regardless of whether Tree or Raw view is active
