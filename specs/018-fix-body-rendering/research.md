# Research: Fix Body Rendering for Truncated Data

**Date**: 2026-07-10
**Feature**: 018-fix-body-rendering

## Findings

### 1. Request Body Truncation — Root Cause

**Location**: `src/otel_agent/server.py:383`
```python
stored_body = request_body[:100_000] if log_body else ""
```

**Problem**: Request bodies >100KB are truncated mid-JSON, producing invalid JSON. The dashboard's `formatBody()` (index.html:519) tries `JSON.parse()` and falls back to raw text with "Content is not valid JSON".

**Also at**: `src/otel_agent/server.py:392` — response bodies truncated at same 100KB limit.

**Decision**: Increase both limits to 500KB (`[:500_000]`).
**Rationale**: DuckDB TEXT columns handle this efficiently. Most LLM requests with large tool schemas are 200-400KB. 500KB covers 99%+ of real requests while staying well under the 10MB constitution limit.
**Alternatives considered**:
- Store full body without limit → rejected (memory risk for pathological payloads)
- Compress before storage → rejected (adds complexity, minimal benefit at 500KB)
- Lazy-load full body from a sidecar file → rejected (breaks single-DB architecture)

### 2. Streaming Preview Truncation — Root Cause

**Location**: `src/otel_agent/server.py:361`
```python
{"streamed": True, "preview": collected_text[:500]}
```

**Problem**: Only 500 chars of concatenated JSON chunks are stored. For mimo-v2.5, the first chunk is just model info + role delta (no content). A 500-char window captures 1-2 chunks — never enough for actual content.

**Decision**: Increase to 5,000 characters (`[:5_000]`).
**Rationale**: Typical SSE chunks are 200-400 chars each. 5,000 chars captures ~12-25 chunks, enough for the first meaningful content deltas and finish reason. Still compact for storage.
**Alternatives considered**:
- Store all chunks → rejected (could be MBs for long outputs)
- Store only the last N chunks → rejected (need early chunks for model/finish_reason metadata)
- Store reassembled content instead of raw chunks → rejected (loses streaming metadata, breaks existing rendering)

### 3. Dashboard Truncation Detection

**Current behavior**: `JSON.parse()` fails on truncated body → raw text fallback with no explanation.

**Decision**: Add truncation detection in `formatBody()` by checking if body length equals the max stored size AND JSON parsing fails. Show a truncation indicator banner.

**Implementation approach**:
1. Pass `maxLength` hint to `formatBody()` (500000 for request/response bodies)
2. If `b.length >= maxLength && !isValidJson` → show "Body truncated (original exceeded 500KB)" banner + raw content
3. If `b.length >= maxLength && isValidJson` → render normally (body happened to fit exactly)
4. For streaming: if `preview.length >= 5000 && no content chunks` → show "Streaming preview may be incomplete"

### 4. Dashboard Performance with 500KB Bodies

**Current**: `highlightJsonString()` recursively renders JSON as HTML. For 500KB JSON, this produces ~2-3MB of HTML.

**Assessment**: The function is already used for all body rendering. Chrome handles 3MB DOM nodes fine (< 1s). The `marked.js` markdown rendering for LLM chat view is much more compact. No special optimization needed — the existing rendering path handles this scale.

### 5. Constitution Compliance

- **Principle I (Code Quality)**: 2 constant changes + ~30 lines of JS. No new modules. ✅
- **Principle II (Testing)**: No new Python functions to test (just constant changes). JS truncation detection has no test harness (established pattern). Regression risk is minimal. ✅
- **Principle III (UX)**: Truncation indicator is a clear UX improvement. ✅
- **Principle IV (Performance)**: 500KB << 10MB limit. Dashboard render < 2s for this size. ✅
