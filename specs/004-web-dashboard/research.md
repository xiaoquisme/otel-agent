# Research: Web Dashboard for Request Logs

**Feature**: 004-web-dashboard
**Date**: 2026-06-26

## Decision 1: Web Framework

**Decision**: Plain Python `http.server` (stdlib) with a JSON API endpoint. No Flask/FastAPI dependency.

**Rationale**: FR-010 requires no JS frameworks. A stdlib HTTP server keeps dependencies minimal. The dashboard is a single-user local tool — no need for routing, middleware, or templating engines.

**Alternatives considered**:
- Flask: Adds a dependency for a single-page app with one API endpoint. Overkill.
- FastAPI: Same as Flask, plus async complexity.
- aiohttp: Already a transitive dependency via mitmproxy, but mixing async servers is fragile.

## Decision 2: Auto-Refresh Mechanism

**Decision**: Server-Sent Events (SSE) for push updates. Client subscribes to `/api/events` and receives new requests as they're logged.

**Rationale**: SSE is simpler than WebSocket, works with stdlib HTTP server, and is unidirectional (server → client) which is exactly what auto-refresh needs.

**Alternatives considered**:
- Polling (setInterval + fetch): Simpler but adds latency and wastes requests.
- WebSocket: Full-duplex, overkill for one-way updates. Requires more complex server code.

## Decision 3: Frontend Architecture

**Decision**: Single HTML file with inline CSS and JS. No build step, no bundler, no npm.

**Rationale**: FR-010 says "no JS frameworks." A single file is easy to serve, debug, and modify. The dashboard is simple enough (table + search + chart).

**Alternatives considered**:
- Separate HTML/CSS/JS files: More organization but adds serving complexity.
- Jinja2 templates: Adds dependency for minimal benefit.

## Decision 4: Chart Library

**Decision**: Chart.js loaded from CDN for the latency chart.

**Rationale**: Lightweight (~200KB), well-documented, no build step needed. One `<script>` tag.

**Alternatives considered**:
- D3.js: Too complex for a single line chart.
- Custom canvas drawing: Reinventing the wheel.
- No chart (table only): Loses the visual analysis value.

## Decision 5: Database Query Strategy

**Decision**: Direct SQLite reads from the dashboard server process. Use WAL mode for concurrent access with the proxy.

**Rationale**: WAL mode allows multiple readers while the proxy writes. No need for a separate database service.

**Alternatives considered**:
- Read replica: Overkill for a local tool.
- In-memory cache: Stale data risk, complexity.

## Decision 6: Pagination

**Decision**: Server-side pagination with `LIMIT/OFFSET`. Client sends `?page=1&per_page=50`.

**Rationale**: Keeps memory usage constant regardless of database size. Simple SQL.

**Alternatives considered**:
- Cursor-based pagination: More efficient for very large datasets but more complex.
- Load all + client-side pagination: Breaks at 10,000+ requests.
