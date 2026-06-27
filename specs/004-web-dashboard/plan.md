# Implementation Plan: Web Dashboard for Request Logs

**Branch**: `004-web-dashboard` | **Date**: 2026-06-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-web-dashboard/spec.md`

## Summary

Add a web dashboard to otel-agent for browsing, searching, and analyzing proxy request logs. The dashboard is a single-page app served by a Python stdlib HTTP server with a JSON API and SSE for auto-refresh. No new dependencies — uses stdlib `http.server` and Chart.js from CDN.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: stdlib `http.server`, `sqlite3`. Chart.js from CDN (frontend only).

**Storage**: SQLite (existing telemetry.db — read-only)

**Testing**: pytest

**Target Platform**: Linux, macOS, WSL (browser-based)

**Project Type**: CLI tool with embedded web server

**Performance Goals**: Dashboard loads <2s with 1000 requests. Search <500ms.

**Constraints**: No JS frameworks. No new Python dependencies. Single HTML file.

**Scale/Scope**: Single-user local tool, typically <10,000 requests.

## Constitution Check

| Principle | Gate | Status |
| --------- | ---- | ------ |
| I. Code Quality | Single responsibility, type hints | ✅ PASS — server, API, and HTML separated |
| II. Testing Standards | Unit tests for each change | ✅ PASS — tests for API endpoints and query logic |
| III. UX Consistency | --help, clear errors | ✅ PASS — `otel-agent dashboard --help`, missing DB message |
| IV. Performance | <5ms overhead | ✅ PASS — dashboard is separate process, no proxy overhead |

No violations.

## Project Structure

### Documentation (this feature)

```text
specs/004-web-dashboard/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api.md
└── tasks.md
```

### Source Code (files to change)

```text
src/otel_agent/
├── commands/
│   └── dashboard.py     # NEW: dashboard server + API handlers
├── dashboard/
│   ├── __init__.py
│   ├── server.py        # HTTP server with routing
│   ├── api.py           # JSON API handlers
│   └── index.html       # Single-page dashboard (inline CSS/JS)
└── cli.py               # Register dashboard subcommand

tests/
├── test_dashboard.py    # NEW: API endpoint tests
└── test_cli.py          # Update for dashboard subcommand
```

**Structure Decision**: New `dashboard/` package for server logic. `commands/dashboard.py` for CLI handler. Single `index.html` file with inline assets.
