# Research: Dashboard Shows Historical Requests

**Feature**: 006-dashboard-history
**Date**: 2026-06-27

## Decision 1: No New Code Needed

**Decision**: The requirements are already satisfied by existing code + bug fixes (BUG-001, 002, 003). The only deliverable is explicit integration tests.

**Rationale**:
- FR-001 (show all requests): Dashboard reads from SQLite — already works
- FR-002 (absolute DB path): Fixed in BUG-001 (`~/.otel-agent/telemetry.db`)
- FR-003 (works from any directory): Fixed in BUG-001
- FR-004 (new requests appear): Fixed in BUG-002 (ThreadingHTTPServer) and BUG-003 (check_same_thread=False)
- FR-005 (empty database): Already handled in API code

## Decision 2: Test Strategy

**Decision**: Add integration tests that verify the full flow: proxy writes → dashboard reads historical data.

**Rationale**: The existing unit tests verify API logic in isolation. Integration tests verify the end-to-end flow that the user actually experiences.
