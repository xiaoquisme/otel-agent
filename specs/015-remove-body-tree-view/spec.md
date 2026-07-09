# Feature Specification: Remove Body Tree View

**Feature Branch**: `015-remove-body-tree-view`

**Created**: 2026-07-09

**Status**: Draft

**Input**: User description: "dashboard 的 response body 的 tree 模式删了吧，只要 raw"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Response Body in Raw Format Only (Priority: P1)

As a developer using the otel-agent dashboard, I want the response body detail view to display content directly in raw (formatted JSON) format without a Tree/Raw toggle, so that I can see the full response body immediately without extra clicks.

**Why this priority**: This is the only user-facing change — removing the toggle and showing raw content directly simplifies the interface and removes an unnecessary interaction step.

**Independent Test**: Can be fully tested by opening the dashboard, clicking a logged request, and verifying the response body appears as syntax-highlighted JSON with no Tree/Raw toggle buttons visible.

**Acceptance Scenarios**:

1. **Given** a request with a valid JSON response body has been logged, **When** the user clicks that request in the dashboard and scrolls to the Response Body section, **Then** the body is displayed as syntax-highlighted JSON in raw format immediately, with no toggle buttons.
2. **Given** a request with non-JSON response body has been logged, **When** the user views the response body, **Then** the raw text content is displayed as before (no behavior change for non-JSON bodies).
3. **Given** the dashboard is open, **When** the user views any request's response body, **Then** the Tree view toggle button and Tree view container are completely absent from the DOM.

---

### Edge Cases

- What happens when the response body is very large (>1000 lines of JSON)? The raw view should still render and remain scrollable.
- What happens when the response body is empty? The "(empty)" placeholder should still appear as before.
- What happens when the response body is not valid JSON? The raw text display with "Content is not valid JSON" hint should still work.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display response bodies in raw (syntax-highlighted JSON) format by default, without requiring any user interaction to switch views.
- **FR-002**: System MUST remove the Tree/Raw toggle toolbar from the response body viewer UI.
- **FR-003**: System MUST remove the Tree view container (`body-view-tree`) and its associated DOM tree rendering logic.
- **FR-004**: System MUST remove all dead code related to the Tree view: `renderJsonNode` function, `toggleJsonNode` function, `json-toggle` CSS styles, `json-node` CSS styles, `AUTO_COLLAPSE_THRESHOLD` constant, `countJsonLines` function, and Tree view event delegation handlers.
- **FR-005**: System MUST preserve the raw view rendering behavior exactly as it works today (syntax-highlighted JSON via `highlightJsonString`).
- **FR-006**: System MUST preserve the non-JSON body display behavior (raw text with "Content is not valid JSON" hint).
- **FR-007**: System MUST preserve the empty body placeholder display ("(empty)").

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Response bodies appear as formatted JSON immediately upon clicking a request, with zero additional clicks needed.
- **SC-002**: The dashboard HTML file is reduced by approximately 100+ lines of removed Tree view code.
- **SC-003**: All existing tests continue to pass with no regressions.
- **SC-004**: No Tree-related DOM elements (`.body-view-tree`, `.json-node`, `.json-toggle`, `.body-viewer-toolbar`) exist in the rendered response body section.

## Assumptions

- The Raw view (syntax-highlighted JSON via `highlightJsonString`) is the only view users need for response body inspection.
- The Tree view was an optional convenience feature with low usage that adds maintenance complexity without sufficient value.
- The `highlightJsonString` function and its raw HTML output are sufficient for all JSON body inspection needs.
- Non-JSON bodies and empty bodies are unaffected by this change.
- The `body-viewer-toolbar` CSS class and its styles can be removed entirely since no toolbar is needed.
