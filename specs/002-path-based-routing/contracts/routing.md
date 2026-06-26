# CLI Contract: Path-Based Routing

**Feature**: 002-path-based-routing

## New Command

### `otel-agent routes`

Display the routing table showing path prefix → provider mappings.

**Exit codes**:
- 0: Routes displayed
- 1: No providers configured

**Output**:
```
Path Prefix    Provider      Type       Upstream
/openai        openai        openai     https://api.openai.com/v1
/anthropic     anthropic     anthropic  https://api.anthropic.com
/deepseek      deepseek      openai     https://api.deepseek.com/v1
```

---

## Modified Behavior

### Proxy Request Routing

When a request arrives at the proxy:

1. Extract first path segment (e.g., `/openai` from `/openai/v1/chat/completions`)
2. Look up provider by prefix match
3. If match found:
   - Strip prefix from path
   - Rewrite host/scheme/port to provider's `base_url`
   - Inject auth header based on provider `type`
   - Forward request
4. If no match:
   - Fall back to `default_provider` behavior (existing)
   - If no default, return HTTP 404 with available routes

### Config Validation (startup)

- Reject duplicate prefixes with error message
- Reject invalid prefix format (must start with `/`, not end with `/`)
- Reject unknown `type` values
- Warn if provider has no active keys (still start)
