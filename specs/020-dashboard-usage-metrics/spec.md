# Feature Specification: Dashboard Usage Metrics

**Feature Branch**: `020-dashboard-usage-metrics`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Add Langfuse-like dashboard metrics, including today's total token consumption and consumption by model. Consider available frontend-design skills."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Today's Token Consumption (Priority: P1)

As a developer using the gateway, I want to see today's total token consumption immediately when opening the dashboard so that I can understand the current day's LLM usage without exporting or manually calculating request data.

**Why this priority**: A single daily total is the fastest and most valuable signal for monitoring current usage.

**Independent Test**: Create telemetry records for the current dashboard day with known input and output token values, open the dashboard, and verify that the overview total equals their sum.

**Acceptance Scenarios**:

1. **Given** one or more completed requests with token-usage data exist for the current dashboard day, **When** I open or refresh the dashboard, **Then** I see the day's total token count prominently in the usage overview.
2. **Given** the dashboard is open and a completed request with token-usage data is recorded today, **When** the dashboard receives its next refresh, **Then** the displayed total includes that request.
3. **Given** no completed requests with token-usage data exist today, **When** I open the dashboard, **Then** I see a clear zero-usage state rather than an error or stale value.

---

### User Story 2 - Compare Usage by Model (Priority: P1)

As a developer, I want to see token consumption broken down by model so that I can identify which models account for the day's usage.

**Why this priority**: The daily total alone cannot support model-level usage decisions or troubleshooting.

**Independent Test**: Create today's telemetry records for at least two models with different known token totals, then verify that the model breakdown lists each model and its correct aggregate total.

**Acceptance Scenarios**:

1. **Given** requests for multiple models have token-usage data today, **When** I view the usage overview, **Then** each model is shown separately with its total tokens and request count.
2. **Given** model usage totals differ, **When** I view the model breakdown, **Then** models are ordered from highest to lowest total token consumption.
3. **Given** the same model is used through multiple requests today, **When** I view its entry, **Then** its displayed total combines all eligible requests for that model.

---

### User Story 3 - Understand Metric Coverage and Token Composition (Priority: P2)

As a developer, I want the overview to distinguish input and output token totals and identify records whose usage cannot be determined, so that I can interpret the metrics correctly.

**Why this priority**: Input/output composition adds diagnostic value, while transparent handling of incomplete provider responses prevents misleading totals.

**Independent Test**: Create a mix of records with input tokens, output tokens, and no usable token data; verify that the overview separates available input/output counts and communicates the number of excluded records.

**Acceptance Scenarios**:

1. **Given** token-usage data includes input and output values, **When** I view the overview, **Then** I can see the input-token total, output-token total, and their combined total.
2. **Given** one or more completed requests lack usable token-usage data, **When** I view the overview, **Then** the dashboard identifies how many records were excluded from token totals.
3. **Given** a request reports only one token component, **When** I view the overview, **Then** the reported component contributes to its corresponding total and the dashboard does not invent the missing component.

### Edge Cases

- Requests outside the current dashboard day must not contribute to today's overview or model breakdown.
- Requests with malformed, non-numeric, negative, or missing usage values must be excluded from token totals without preventing the rest of the dashboard from loading.
- Requests whose model cannot be identified must not be merged into a named model; they should be represented as an explicitly unnamed or unknown group when they contain usable token data.
- Multiple model spellings must remain distinct unless the recorded model identifier is exactly the same.
- The metrics view must remain understandable on narrow desktop and mobile-sized browser widths; summary cards and the model breakdown may reflow but must not overlap or hide values.
- If historical telemetry predates token-usage capture, the dashboard must show available totals and clearly communicate incomplete coverage rather than reporting an error.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The dashboard MUST provide a visually distinct usage overview above or adjacent to the existing request list without removing existing request browsing, filtering, export, or detail capabilities.
- **FR-002**: The usage overview MUST display the total tokens for completed requests recorded during the current dashboard-local calendar day.
- **FR-003**: The usage overview MUST display separate input-token and output-token totals whenever those values are available.
- **FR-004**: The dashboard MUST display a per-model breakdown for the current dashboard-local calendar day, including each model's total tokens and completed-request count.
- **FR-005**: The per-model breakdown MUST order models by descending total tokens and use clear numeric formatting so that relative consumption can be scanned quickly.
- **FR-006**: The dashboard MUST derive token metrics only from recorded provider usage data and MUST NOT estimate token counts from request or response text.
- **FR-007**: The dashboard MUST exclude malformed, negative, or unavailable token values from totals and MUST show the count of completed requests excluded because usable token data was unavailable.
- **FR-008**: The dashboard MUST update displayed usage metrics after newly completed, token-bearing requests are recorded, without requiring the user to restart the dashboard.
- **FR-009**: The dashboard MUST preserve the existing dark-theme visual language while using compact, data-dense summary cards and a legible model comparison presentation inspired by observability dashboards.
- **FR-010**: The dashboard MUST provide an accessible text label for each metric and MUST not rely on color alone to communicate token type, model rank, or missing-usage state.
- **FR-011**: The feature MUST not cause dashboard metric reads to interrupt, delay, or make unavailable the active proxy's telemetry recording.

### Key Entities

- **Usage Record**: The provider-reported input, output, and total token values associated with a completed request, when supplied by the upstream response.
- **Daily Usage Overview**: The aggregate token and coverage metrics for requests recorded on the current dashboard-local calendar day.
- **Model Usage Summary**: A daily aggregate for one recorded model identifier, including total tokens and completed-request count.
- **Excluded Usage Record**: A completed request that cannot safely contribute to token totals because its usage information is absent or invalid.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a representative data set of 100,000 recorded requests, a user sees the current-day usage overview and model breakdown within 2 seconds of opening or refreshing the dashboard.
- **SC-002**: For a controlled data set with known valid usage values, all displayed daily and per-model token totals match the sum of the eligible records exactly.
- **SC-003**: Newly completed requests with usage data appear in the displayed daily aggregate within 2 seconds of being recorded.
- **SC-004**: In usability validation, at least 90% of participants can identify today's total token consumption and the highest-consuming model within 10 seconds of opening the dashboard.
- **SC-005**: Existing request-list filtering, request detail viewing, and data export remain usable while the usage overview is displayed.

## Assumptions

- "Today" means the calendar day in the dashboard viewer's local time zone.
- Version one covers token consumption counts only; monetary cost estimation, quotas, budgets, alerts, and custom date ranges are out of scope.
- Upstream providers may return token-usage data in more than one common response shape; records without reliable usage data are transparently excluded rather than estimated.
- The model identifier used for aggregation is the one recorded with the request; provider and model prefixes are retained when present to avoid merging distinct models.
- The existing dashboard is the primary surface for this feature. A separate analytics product or external telemetry integration is out of scope.
- The current dashboard's dark visual language will be extended with a compact observability-dashboard layout; detailed visual token choices belong in the implementation planning and design phase.
