---
title: "Download request JSON from loaded detail, not a new API path"
date: 2026-08-24
category: design-patterns
module: dashboard
problem_type: design_pattern
component: frontend_stimulus
severity: medium
applies_when:
  - Adding a single-record download on a Vite-proxied dashboard
  - Detail page already has the request payload in memory
  - A new backend download route would 404 against an older proxy
root_cause: incomplete_setup
resolution_type: code_fix
symptoms:
  - "Clicking Download JSON navigates to /api/requests/:id/download and shows Not Found"
  - Vite /api proxy still targets a long-lived otel-agent process without the new route
tags:
  - dashboard
  - download-json
  - vite-proxy
---

# Download request JSON from loaded detail, not a new API path

## Context

Operators on `/request/:id` wanted one-click save of the current request as `request-{id}.json`. A dedicated `GET /api/requests/{id}/download` attachment matches list `/api/export`, but the Vite app in `frontend/vite.config.ts` proxies `/api` to `http://localhost:45638`. That port is a separately installed `otel-agent proxy` that does not reload worktree routes. Navigating the tab to the new path therefore 404s even though `GET /api/requests/{id}` (the existing detail fetch) already succeeded.

## Guidance

When the detail view already holds `RequestDetail`, serialize that object in the browser:

1. Pretty-print with `JSON.stringify(payload, null, 2)`.
2. `json.parse` string bodies/headers only when they are valid JSON text; leave non-JSON strings as-is.
3. Trigger save with a temporary `<a download="request-{id}.json">` and `URL.createObjectURL`, then revoke the object URL.

Keep `GET /api/requests/{id}/download` for curl and same-process dashboards. Do not use `window.location.href` to that path from Vite-dev DetailPage.

## Why This Matters

`window.location.href = '/api/requests/18788/download'` replaces the SPA with the proxy's 404 JSON (`{"detail":"Not Found"}`). The operator already paid for the detail fetch; a second GET is not required for the file they asked for.

## When to Apply

- Adding download/export on a page that already loaded the record
- Frontend `server.proxy['/api']` points at a long-lived process that is not the worktree you just edited
- The control must work before the user restarts `otel-agent proxy`

## Examples

Broken (navigates away, 404 on stale proxy):

```ts
export function downloadRequestJson(id: number): void {
  window.location.href = `${API_BASE}/requests/${id}/download`
}
```

Working (`frontend/src/api/client.ts` `downloadRequestJson`):

```ts
export function downloadRequestJson(detail: RequestDetail): void {
  const payload = {
    ...detail,
    request_body: maybeParseJson(detail.request_body),
    response_body: maybeParseJson(detail.response_body),
    request_headers: maybeParseJson(detail.request_headers),
    response_headers: maybeParseJson(detail.response_headers),
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `request-${detail.id}.json`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
```

## Related

- `docs/solutions/design-patterns/request-detail-trajectory-window.md` — how `/request/:id` is opened
- `frontend/vite.config.ts` — `/api` → `localhost:45638`
- `src/otel_agent/dashboard/routes.py` — optional same-process attachment route
