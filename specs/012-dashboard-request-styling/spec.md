# Feature Specification: Dashboard Request Section Styling

**Feature Branch**: `012-dashboard-request-styling`

**Created**: 2026-07-09

**Status**: Draft

**Input**: User description: "dashboard 为啥没有加request 的样式" — The request section in the dashboard detail overlay lacks visual styling and distinction from the response section.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Visual Distinction Between Request and Response (Priority: P1)

As a developer debugging LLM API calls, I want to immediately distinguish the request section from the response section in the detail overlay, so I can quickly locate the information I need without reading every section header.

**Why this priority**: The primary value of the detail overlay is快速定位请求/响应信息。没有视觉区分，用户需要逐个阅读 section headers，降低了调试效率。

**Independent Test**: Can be fully tested by opening the dashboard, clicking a request row, and verifying that the request and response sections have distinct visual treatments (borders, colors, icons).

**Acceptance Scenarios**:

1. **Given** the detail overlay is open, **When** I look at the Request Headers section, **Then** it has a distinct visual border/background color (e.g., blue accent) different from the Response Headers section.
2. **Given** the detail overlay is open, **When** I look at the Request Body section, **Then** it has a visual indicator (icon or color) that distinguishes it from the Response Body section.
3. **Given** the detail overlay is open, **When** I look at the General section, **Then** the request method and URL are visually prominent.

---

### User Story 2 - Request Section Icons and Labels (Priority: P2)

As a developer, I want clear icons and labels for each section in the detail overlay, so I can scan the layout and understand the structure at a glance.

**Why this priority**: Icons and labels improve scannability, which is secondary to basic visual distinction but still important for usability.

**Independent Test**: Can be tested by opening the detail overlay and verifying that each section (Request Headers, Request Body, Response Headers, Response Body) has an appropriate icon and clear label.

**Acceptance Scenarios**:

1. **Given** the detail overlay is open, **When** I look at each section header, **Then** it has an icon (e.g., 📤 for request, 📥 for response) and a clear text label.
2. **Given** the detail overlay is open, **When** I look at the Request Body section, **Then** the Tree/Raw toggle toolbar is visually styled to match the request theme.

---

### User Story 3 - Consistent Color Theme (Priority: P3)

As a developer, I want the request-related sections to follow a consistent color theme (e.g., cool blues/purples) and response-related sections to follow a different theme (e.g., warm greens/oranges), so the visual language is consistent across the dashboard.

**Why this priority**: Color consistency is a polish feature that enhances the overall experience but doesn't block core functionality.

**Independent Test**: Can be tested by opening the detail overlay and verifying that all request sections share one color palette and all response sections share another.

**Acceptance Scenarios**:

1. **Given** the detail overlay is open, **When** I examine the request sections, **Then** they use a consistent cool color palette (blues/purples).
2. **Given** the detail overlay is open, **When** I examine the response sections, **Then** they use a consistent warm color palette (greens/oranges or neutral).
3. **Given** the detail overlay is open, **When** I look at the JSON badges in the request body, **Then** they use the request color theme consistently.

---

### Edge Cases

- What happens when the request body is empty? The section should still show the styled border/background with "(empty)" text.
- What happens when the request body is not valid JSON? The raw view should still respect the request color theme.
- What happens when the detail overlay is narrow (mobile)? The sections should stack vertically and maintain visual distinction.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST apply a distinct visual style (border, background color, or accent) to the Request Headers section in the detail overlay.
- **FR-002**: System MUST apply a distinct visual style to the Request Body section in the detail overlay.
- **FR-003**: System MUST apply a distinct visual style to the Response Headers section in the detail overlay.
- **FR-004**: System MUST apply a distinct visual style to the Response Body section in the detail overlay.
- **FR-005**: System MUST add icons to section headers (e.g., 📤 for request sections, 📥 for response sections).
- **FR-006**: System MUST ensure the Request Body toolbar (Tree/Raw toggle) visually matches the request color theme.
- **FR-007**: System MUST maintain visual distinction when the detail overlay is resized or on narrow screens.
- **FR-008**: System MUST NOT change the underlying JSON viewer functionality (syntax highlighting, collapsible tree, annotations).

### Key Entities

- **Detail Section**: A section in the detail overlay (General, Request Headers, Request Body, Response Headers, Response Body). Each section has a header, content area, and optional actions.
- **Section Style**: Visual properties applied to a section (border color, background tint, icon, label text).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can distinguish request from response sections in under 2 seconds (visual scan test).
- **SC-002**: All 5 sections in the detail overlay have distinct visual treatments with no two adjacent sections sharing the same border/background color.
- **SC-003**: The JSON viewer functionality (tree view, raw view, syntax highlighting, collapsible nodes, annotations) remains fully functional after styling changes.
- **SC-004**: The detail overlay renders correctly at viewport widths from 400px to 1920px without visual overlap or broken layout.

## Assumptions

- The current JSON viewer functionality (syntax highlighting, collapsible tree, semantic annotations) will be preserved without modification.
- The existing color palette (dark theme with #0f1117 background) will be extended, not replaced.
- Mobile responsiveness is a secondary concern; the primary target is desktop browsers.
- The request/response distinction is based on the section type (Request Headers/Body vs Response Headers/Body), not on the data content.
