# Data Model: Remove Body Tree View

**Date**: 2026-07-09
**Feature**: 015-remove-body-tree-view

## Summary

No data model changes. This feature is a pure UI simplification.

The change affects only the dashboard frontend (`index.html`) — specifically the rendering of response/request body content. No database schema, API contracts, data structures, or storage formats are modified.

## Existing Data Flow (unchanged)

```
Proxy logs request → DuckDB storage → API returns JSON → Dashboard renders body
                                                            ↓
                                                    formatBody(body, context)
                                                            ↓
                                                    highlightJsonString(parsed, 0)
```

The data flow from storage to display is unaffected. Only the final rendering step changes (tree toggle removed, raw view shown directly).
