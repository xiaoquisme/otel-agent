# Dashboard Debug implementation plan

## Confirmed scope and constraints

Add `/debug` for a single-turn text prompt against configured models, including Responses-only subscriptions. Work directly in the current checkout as the sole writer. No agents, commits, push, installs, deployment, service restart, or changes to the pre-existing untracked `deploy/`.

## Evidence and decisions

- `server.create_app` already owns `/v1/models`, the model cache, credentials, gateway handlers and telemetry. Reuse these; do not introduce a second upstream client or credential path.
- `serves_only_responses(provider)` is configuration/auth-source based. Select `/v1/responses` for those providers, `/v1/messages` for Anthropic, otherwise `/v1/chat/completions`. Never infer protocol from model names.
- Add only a read-only `/api/debug/models` projection over existing discovery: model IDs, fixed gateway endpoint, partial failures, and request-body logging setting. Browser execution calls the selected real `/v1/*` endpoint directly with a fixed text-only body; no arbitrary URL/JSON editor or execution wrapper.
- Preserve gateway HTTP/error semantics and raw response JSON. Display actual client protocol, answer, status, elapsed time, usage and structured errors. Native Anthropic avoids unnecessary conversion and keeps native error bodies intact.
- Discovery failures (HTTP, connection, malformed catalog, credentials) must be visible without dropping successful providers or caching failures. Do not return upstream headers, keys, tokens or raw discovery error bodies.
- Exclude models only when explicit output-modality metadata rules out text; unknown capability metadata must not hide text models.

## Implementation units and acceptance

1. **Discovery + route contract:** add mock-first tests for configuration-based selection (including misleading model IDs), partial discovery failures, no secret disclosure, and logging metadata. Implement the narrow projection and observable failures; keep existing `/v1/models` compatible.
2. **Debug UI:** add nav/route and accessible responsive form, model loading/empty/error/retry states, pending duplicate-submit prevention, logging warning, native fixed bodies, and result/error/raw output. Proxy `/v1` in Vite as well as `/api`. Test frontend request construction/result handling with mocked fetch without adding dependencies.
3. **Gateway verification:** mock upstream HTTP/SSE for Chat, Anthropic and Responses-only success/failure/unknown model; assert genuine endpoints, provider-only authorization, real HTTP statuses and telemetry logging configuration. No paid/network requests.
4. **Artifacts + gates:** run frontend tests, `npm run lint`, `npm run build`, synchronize `frontend/dist/` to `src/otel_agent/dashboard/frontend_dist/`, run `bash harness/checks.sh`. Inspect final diff and confirm `deploy/` untouched. Report failures honestly, without installing tools or restarting services.

## Definition of done

All above acceptance checks pass, shipped frontend bundle is synchronized, and parent receives changed paths, verification evidence, implementation trade-offs and residual risks. Parent owns review/commit/install/restart. Browser checks, if available, use mock-only local fixtures and do not contact configured paid models.
