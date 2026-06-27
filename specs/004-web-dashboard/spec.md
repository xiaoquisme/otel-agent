# Feature Specification: Web Dashboard for Request Logs

**Feature Branch**: `004-web-dashboard`

**Created**: 2026-06-26

**Status**: Draft

**Input**: Build a web dashboard for the logs in the SQLite database so users can browse, search, and analyze proxy requests in a browser instead of the CLI.

## User Scenarios & Testing

### User Story 1 - Browse Request Logs (Priority: P1)

A user opens the dashboard in a browser and sees a table of recent requests with key details.

**Why this priority**: This is the core value — visual browsing of requests.

**Independent Test**: Start proxy, send requests, open dashboard in browser, verify table shows requests.

**Acceptance Scenarios**:

1. **Given** the proxy has logged requests, **When** the user opens `http://localhost:9090`, **Then** a table shows recent requests with timestamp, method, URL, status, and latency.
2. **Given** the dashboard is open, **When** new requests arrive through the proxy, **Then** the table updates automatically without page refresh.
3. **Given** no requests have been logged, **When** the user opens the dashboard, **Then** a message says "No requests logged yet."

---

### User Story 2 - Search and Filter (Priority: P1)

A user filters requests by URL, method, status code, or provider to find specific traffic.

**Why this priority**: Without filtering, the dashboard is useless once there are hundreds of requests.

**Independent Test**: Send requests to different providers, filter by provider name, verify only matching rows shown.

**Acceptance Scenarios**:

1. **Given** the dashboard shows requests, **When** the user types in the search box, **Then** only requests matching the URL or upstream (provider) are shown.
2. **Given** the dashboard is open, **When** the user selects a method filter (GET/POST), **Then** only requests with that method are shown.
3. **Given** the dashboard is open, **When** the user selects a status filter (200/400/500), **Then** only requests with that status code are shown.
4. **Given** filters are active, **When** the user clears filters, **Then** all requests are shown again.

---

### User Story 3 - View Request Details (Priority: P2)

A user clicks a request row to see full request/response headers and body.

**Why this priority**: Debugging requires seeing the full payload, not just summary columns.

**Independent Test**: Click a request row, verify a detail panel shows full headers and body.

**Acceptance Scenarios**:

1. **Given** the dashboard shows a list of requests, **When** the user clicks a row, **Then** a detail panel shows full request headers, request body, response headers, and response body.
2. **Given** the detail panel is open, **When** the user clicks "Copy as curl", **Then** a curl command is copied to clipboard.
3. **Given** the detail panel is open, **When** the user clicks "Close" or clicks another row, **Then** the panel updates or closes.

---

### User Story 4 - Latency Chart (Priority: P2)

A user sees a chart of request latency over time to spot slow requests.

**Why this priority**: Visual patterns reveal performance issues that tables miss.

**Independent Test**: Send requests with varying latency, verify chart shows data points.

**Acceptance Scenarios**:

1. **Given** the dashboard has request data, **When** the user views the dashboard, **Then** a line chart shows latency over time for recent requests.
2. **Given** the chart is displayed, **When** the user hovers over a point, **Then** a tooltip shows the request URL and exact latency.

---

### User Story 5 - Export Data (Priority: P3)

A user exports filtered request data as CSV or JSON for external analysis.

**Why this priority**: Power users need to analyze data in spreadsheets or scripts.

**Independent Test**: Apply a filter, click export, verify downloaded file contains filtered data.

**Acceptance Scenarios**:

1. **Given** the dashboard shows filtered requests, **When** the user clicks "Export CSV", **Then** a CSV file downloads with the filtered data.
2. **Given** the dashboard shows filtered requests, **When** the user clicks "Export JSON", **Then** a JSON file downloads with the filtered data.

---

### Edge Cases

- What happens if the database file is missing? The dashboard MUST show "No database found. Start the proxy first."
- What happens if the database is locked by the proxy? The dashboard MUST use WAL mode reads and not block the proxy.
- What happens if there are 10,000+ requests? The dashboard MUST paginate or virtual-scroll, not load all rows at once.
- What happens if the dashboard port conflicts with the proxy port? The tool MUST use a different default port (9090) and allow configuration.

## Requirements

### Functional Requirements

- **FR-001**: The dashboard MUST be accessible at `http://localhost:9090` by default.
- **FR-002**: The dashboard MUST display a table of requests with timestamp, method, URL, status, and latency.
- **FR-003**: The dashboard MUST auto-refresh when new requests arrive via SSE (Server-Sent Events).
- **FR-004**: The dashboard MUST support text search across URL and upstream fields (upstream substring match serves as provider filter).
- **FR-005**: The dashboard MUST support filtering by HTTP method and status code.
- **FR-006**: The dashboard MUST show full request/response details when a row is clicked.
- **FR-007**: The dashboard MUST display a latency chart over time.
- **FR-008**: The dashboard MUST support CSV and JSON export of filtered data.
- **FR-009**: The dashboard MUST paginate results (50 per page by default).
- **FR-010**: The dashboard MUST work without JavaScript frameworks — plain HTML/CSS/JS served from the proxy process.
- **FR-011**: A new `otel-agent dashboard` command MUST start the dashboard server.
- **FR-012**: The dashboard MUST accept `--port` and `--db` flags.

### Key Entities

- **Request Log**: The existing `requests` table in SQLite — the dashboard reads from it.
- **Dashboard Server**: A lightweight HTTP server serving the dashboard UI and a JSON API.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Dashboard loads in under 2 seconds with 1000 requests in the database.
- **SC-002**: Search results update within 500ms of typing.
- **SC-003**: Auto-refresh latency is under 5 seconds (new requests appear within 5s).
- **SC-004**: Export of 1000 requests completes in under 3 seconds.
- **SC-005**: Dashboard works in Chrome, Firefox, and Safari without additional setup.

## Assumptions

- The dashboard runs on the same machine as the proxy.
- The SQLite database is readable by the dashboard process (WAL mode allows concurrent reads).
- Users have a modern web browser.
- The dashboard is for local development use, not production deployment.
- No authentication is required (local-only tool).
- The dashboard reuses the existing `requests` table schema — no new tables needed.
