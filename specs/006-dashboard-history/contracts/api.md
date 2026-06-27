# API Contract: Dashboard Historical Data

**Feature**: 006-dashboard-history

## No API Changes

The existing API endpoints already support all requirements:

- `GET /api/requests?limit=50` — returns all requests (historical + new)
- `GET /api/events` — SSE stream for new requests only

The key behavior: the first `GET /api/requests` call returns ALL rows in the database, regardless of when the dashboard was started.
