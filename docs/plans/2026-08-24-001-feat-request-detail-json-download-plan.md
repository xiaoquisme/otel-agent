---
title: "feat: Download current request as JSON from detail page"
type: "feat"
date: "2026-08-24"
artifact_contract: "ce-unified-plan/v1"
artifact_readiness: "implementation-ready"
product_contract_source: "ce-plan-bootstrap"
execution: "code"
---

## Goal Capsule

- **Objective:** On `/request/:id`, the operator can download the currently viewed request as a pretty-printed JSON file (e.g. `request-18788.json`).
- **Product authority:** User request via ce-auto: add a detail-page action to save the current request as JSON. Example URL: `http://localhost:45638/request/18788`.
- **Open blockers:** None.
- **Stop conditions:** Detail header has a working Download JSON control; the file contains the request's stored fields with JSON bodies parsed when possible; missing request still 404s without a download; packaged `frontend_dist` includes the control.
- **Execution profile:** Small UI + one attachment endpoint. Test-first on the route; frontend follows existing export/copy patterns.
- **Tail ownership:** ce-work executes this plan.

---

## Product Contract

### Summary

The request detail window (`DetailPage` at `/request/:id`) already loads the full structured record via `GET /api/requests/{id}` but only lets operators copy fragments (CodeBlock, tool args, curl). There is no way to save that one request as a file. List-level `GET /api/export` dumps a filtered collection, not the current detail. Operators inspecting a single call (replay, share, offline debug) need a one-click JSON download of that request.

Product Contract created by ce-plan-bootstrap.

### Problem Frame

`DetailPage` header shows method, URL, status, latency, and model. Trajectory cells and Event details are inspection-only. `ExportButtons` live on the list and hit `/api/export` for many rows. `CodeBlock` copies body text to the clipboard, which is awkward for large LLM payloads and is not a file. The user wants the page they already have open (`/request/18788`) to emit a `.json` file of that request.

### Requirements

**Download action**

- R1. When a request detail is loaded, the page offers a Download JSON control in the header.
- R2. Activating the control saves a file named `request-{id}.json` (example: `request-18788.json`).
- R3. The file is `application/json`, UTF-8, pretty-printed (indent 2).
- R4. The file represents the current request: identity/timing/status fields, headers, request and response bodies, plus structured `messages` and `metadata` when present.

**Payload quality**

- R5. If `request_body` or `response_body` is valid JSON text, the downloaded file embeds the parsed value (object/array), not an escaped string.
- R6. If a body is missing, empty, or not valid JSON, the downloaded file keeps the original string or `null` rather than failing the download.

**Failure behavior**

- R7. The Download JSON control is not offered on the not-found / loading states.
- R8. `GET /api/requests/{id}` for a missing id remains 404; a dedicated download URL for a missing id also returns 404 JSON, not an empty attachment.

### Success Criteria

- Opening `/request/18788` and clicking Download JSON yields `request-18788.json` that `json.loads` can parse.
- The file's `id` matches the page; request/response bodies are objects when the stored text was JSON.
- List export (`/api/export`) is unchanged.

### Actors

- A1. Dashboard operator inspecting a logged request in a detail window.

### Key Flows

- F1. Operator opens `/request/:id` and clicks Download JSON.
  - **Outcome:** Browser saves `request-{id}.json` containing that request.
- F2. Operator opens a non-existent id.
  - **Outcome:** "Request not found"; no download control.

### Acceptance Examples

- AE1. Covers R1, R2, R3, R4. Given request 18788 is loaded, when the operator clicks Download JSON, then a file named `request-18788.json` downloads and contains `id: 18788` plus method/url/status/bodies.
- AE2. Covers R5. Given `request_body` is the string `'{"model":"gpt-4"}'`, when the file is parsed, then `request_body` is an object with `model` equal to `gpt-4`.
- AE3. Covers R6, R8. Given a missing id, when the download URL is requested, then the response is 404 and not a `.json` attachment.

### Scope Boundaries

**In scope**

- Header control on `DetailPage`
- Server attachment endpoint for a single request (same record as detail API)
- Tests for the endpoint and payload parsing
- Rebuild `src/otel_agent/dashboard/frontend_dist/` so `otel-agent dashboard` / proxy serve the button

**Deferred for later**

- Downloading only one cell / one body
- YAML or HAR export
- List-row per-request download

**Outside this product's identity**

- Changing list bulk `/api/export`
- Changing Trajectory layout or message parsing

### Sources

- User request (ce-auto): download current request as JSON from `/request/:id`
- `frontend/src/pages/DetailPage.tsx`
- `src/otel_agent/dashboard/routes.py` (`GET /api/requests/{id}`, `GET /api/export`)
- `src/otel_agent/dashboard/api.py` (`get_structured_request`)
- `frontend/src/api/client.ts` (`exportData`, `fetchRequestDetail`)

---

## Planning Contract

### Key Technical Decisions

KTD-1. Server attachment endpoint, not only a client Blob.
Decision: Add `GET /api/requests/{request_id}/download` that returns pretty-printed JSON with `Content-Disposition: attachment; filename="request-{id}.json"`.
Rationale: Matches existing `/api/export` attachment style, works via curl, avoids re-serializing in the browser for large bodies, and gives a single source of truth for filename and payload. The UI is a link/button to that URL (same pattern as `exportData`).

KTD-2. Payload is structured detail with JSON bodies decoded.
Decision: Start from `get_structured_request` and replace `request_body` / `response_body` (and header fields that are JSON strings) with `json.loads` when that succeeds.
Rationale: Operators want a usable file, not a double-encoded string dump of bodies they already see parsed in the UI. Non-JSON bodies stay strings (R6).

KTD-3. Place the new path before FastAPI cannot confuse it with `{request_id}`.
Decision: Register `/requests/{request_id}/download` as its own route. Integer `request_id` already used by `/requests/{request_id}`; the extra path segment is unambiguous.
Rationale: Avoid query-flag downloads (`?download=1`) that are easy to miss in tests and clients.

KTD-4. Ship via rebuilt `frontend_dist`.
Decision: After the React change, run the frontend production build and replace `src/otel_agent/dashboard/frontend_dist/` the same way `hatch_build.py` copies `frontend/dist`.
Rationale: The live process on `:45638` serves packaged assets, not Vite source.

KTD-5. Header control styling follows the detail header, not list `ExportButtons`.
Decision: Add a compact text button in the existing `DetailPage` header using current CSS tokens (`--color-border-default`, `--color-text-secondary`, etc.), not the hardcoded dark `ExportButtons` classes.
Rationale: Detail page already uses token-based inline styles; list export buttons are leftover dark hardcodes.

### Assumptions

- Single-request download does not need list filters (search/method/status).
- Pretty-print indent 2 is acceptable for multi-megabyte bodies (same as `/api/export` JSON).
- No auth change: dashboard APIs stay as they are today.
- Worktree frontend may need `npm install` before `npm run build`.

### Sequencing

```
U1 (download route + payload helper + tests) → U2 (DetailPage control + frontend_dist rebuild)
```

U2 depends on U1 for the URL contract.

### Risks

- Large request/response bodies can make `json.dumps(..., indent=2)` heavy. Acceptable: detail page already loaded that payload; no extra fetch if the operator uses the same process. Mitigation: stream is not required for this scope.
- FastAPI route order is not a real risk because `/download` is a distinct path.
- `frontend_dist` hash filenames change on rebuild; SPA fallback tests already cover `/request/:id` serving `index.html`.

---

## Implementation Units

### U1. Single-request JSON download endpoint

- **Goal:** `GET /api/requests/{id}/download` returns a pretty-printed JSON attachment of the structured request, with JSON bodies decoded when possible.
- **Requirements:** R2, R3, R4, R5, R6, R8
- **Dependencies:** None
- **Files:**
  - Modify: `src/otel_agent/dashboard/routes.py`
  - Modify: `src/otel_agent/dashboard/api.py` (optional helper if decoding should live next to `get_structured_request`)
  - Modify: `tests/test_dashboard.py`
- **Approach:**
  1. Add a small helper (module-level in `routes.py` or method on `DashboardAPI`) that takes the structured request dict and returns a downloadable dict: copy fields; `json.loads` `request_body` / `response_body` when they are non-empty strings; leave non-JSON strings as-is; leave already-parsed objects as-is.
  2. Add `GET /requests/{request_id}/download`. 404 JSON when `get_structured_request` returns None. Otherwise `Response` with `media_type="application/json"`, `Content-Disposition: attachment; filename="request-{id}.json"`, body `json.dumps(payload, indent=2, ensure_ascii=False)`.
  3. Update the module docstring endpoint list.
  4. Tests: happy path filename + parsed body object; non-JSON body remains a string; missing id is 404 without attachment disposition.
- **Patterns to follow:** `export_data` in `routes.py`; `test_route_export_json` / `test_route_request_detail` / `test_route_request_not_found` in `tests/test_dashboard.py`.
- **Test scenarios:**
  - Happy path: existing id returns 200, `content-type` includes `application/json`, `content-disposition` contains `attachment` and `request-{id}.json`, JSON `id` matches.
  - Happy path: stored `request_body` is a JSON object string; downloaded `request_body` is a dict.
  - Edge case: stored `request_body` is plain text; downloaded `request_body` is that string.
  - Edge case: unknown id returns 404; no `attachment` disposition.
  - Regression: `GET /api/requests/{id}` and `GET /api/export` still behave as today.
- **Verification:** `uv run pytest tests/test_dashboard.py -k "download or export or request_detail or request_not_found" -v`

### U2. Detail page Download JSON control

- **Goal:** Loaded detail pages expose Download JSON in the header, targeting the U1 URL.
- **Requirements:** R1, R2, R7
- **Dependencies:** U1
- **Files:**
  - Modify: `frontend/src/pages/DetailPage.tsx`
  - Modify: `frontend/src/api/client.ts` (optional `downloadRequestJson(id)` helper)
  - Modify: `src/otel_agent/dashboard/frontend_dist/` (regenerated)
- **Approach:**
  1. Add `downloadRequestJson(id: number)` next to `exportData`: navigate or assign `window.location` / open `${API_BASE}/requests/${id}/download`. Prefer assigning via a temporary `<a download>` or `window.location.href` like `exportData` so the browser uses Content-Disposition. Do not fetch-and-blob unless the attachment header is ignored (not expected on same origin).
  2. In `DetailPage` header, after the status/latency/model span, render a button "Download JSON" only when `detail` is loaded. Click calls the helper with `detail.id`.
  3. Style with existing header tokens; keep it compact so URL text still wraps.
  4. `npm run build` in `frontend/` and replace `src/otel_agent/dashboard/frontend_dist/` with `frontend/dist/` (rmtree + copytree, same as `hatch_build.py`).
- **Patterns to follow:** `exportData` in `frontend/src/api/client.ts`; header layout in `frontend/src/pages/DetailPage.tsx`; `hatch_build.py` for dist copy; `docs/solutions/design-patterns/light-theme-token-roles.md` for token usage.
- **Test scenarios:**
  - Happy path: loaded detail header contains a Download JSON control whose target is `/api/requests/{id}/download`.
  - Edge case: loading skeleton and not-found view have no download control.
  - Integration: packaged `frontend_dist` JS/HTML includes the new label or download path.
- **Verification:** `npm run build` in `frontend/` succeeds. `rg -n "Download JSON|/requests/.*/download" src/otel_agent/dashboard/frontend_dist frontend/src/pages/DetailPage.tsx`. No frontend unit test runner exists; rely on build + string presence in dist.

---

## Verification Contract

| Gate | Command | Pass criteria |
|------|---------|---------------|
| Download route | `uv run pytest tests/test_dashboard.py -k "download or export or request_detail" -v` | New download tests pass; existing detail/export tests pass |
| Dashboard suite | `uv run pytest tests/test_dashboard.py -v` | Full dashboard file green |
| Frontend typecheck/build | `npm run build` in `frontend/` | `tsc -b && vite build` exit 0 |
| Packaged UI | Inspect `src/otel_agent/dashboard/frontend_dist/` | Assets refreshed; download control present in bundle |
| Smoke | `curl -D- http://localhost:<port>/api/requests/<id>/download` | 200, attachment filename `request-<id>.json`, valid JSON |

Worktree note: if pytest is missing, install with `uv pip install -e ".[dev]"` first (see skillhub/otel-agent worktree pitfall).

---

## Definition of Done

**Global**

- Detail page header can download the current request as `request-{id}.json`
- Download endpoint 404s for unknown ids without an attachment
- JSON bodies are objects in the file when the stored text was JSON
- `tests/test_dashboard.py` passes
- `frontend_dist` rebuilt from current `frontend/` source
- This plan's decisions remain accurate; update only if implementation diverges

**Per unit**

- U1: `GET /api/requests/{id}/download` covered by tests for 200/404 and body parsing
- U2: `DetailPage` shows Download JSON only when loaded; packaged assets include the control

**Cleanup**

- No unused client Blob helper if the server attachment is used
- Do not restyle list `ExportButtons` in this change
