# Implementation Plan: Model-Name-Based Routing Gateway

**Branch**: `008-model-name-routing-gateway` | **Date**: 2026-07-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/008-model-name-routing-gateway/spec.md`

## Summary

Replace the mitmproxy-based telemetry proxy with a FastAPI-based LLM API gateway. The gateway exposes both OpenAI-compatible (`/v1/chat/completions`) and Anthropic-compatible (`/v1/messages`) endpoints. Requests are routed to upstream providers based on the model name prefix (e.g., `openai/gpt-5.4` → OpenAI, `xiaomi/mimo-v-2.5` → Xiaomi). Format conversion is performed when the client endpoint format differs from the provider's declared `api_format`.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: FastAPI, uvicorn, httpx (async HTTP client), pyyaml

**Removed Dependencies**: mitmproxy (completely removed)

**Storage**: SQLite (existing telemetry logger, kept as-is)

**Testing**: pytest

**Target Platform**: macOS / Linux (local dev tool)

**Project Type**: CLI + web service

**Performance Goals**: <5ms proxy overhead per request (excluding upstream latency)

**Constraints**: Must maintain backward-compatible config migration where possible

## Constitution Check

- **Code Quality**: Each module has single responsibility. Functions under 50 lines. Type hints on all signatures. Docstrings on public functions.
- **Testing**: Every new function gets a unit test. Tests are deterministic (no network). Tests run in <30s.
- **UX Consistency**: CLI commands retain `--help`. Error messages include what went wrong + what to do. Hot-reload preserved.
- **Performance**: <5ms overhead. SQLite WAL mode. Config mtime check before re-parse.

## Project Structure

### Documentation (this feature)

```text
specs/008-model-name-routing-gateway/
├── spec.md
├── plan.md
└── tasks.md
```

### Source Code (repository root)

```text
src/otel_agent/
├── __init__.py
├── __main__.py
├── cli.py                    # CLI entry point (modified)
├── config.py                 # New config schema: provider registry
├── server.py                 # NEW: FastAPI app + uvicorn runner
├── router.py                 # NEW: model-name parser + provider resolver
├── converter.py              # NEW: Anthropic ↔ OpenAI format conversion
├── logger.py                 # Telemetry logger (kept, minor updates)
├── rotator.py                # Key rotator (simplified, may merge into config)
├── viewer.py                 # CLI viewer (kept as-is)
├── process.py                # Process management (updated for uvicorn)
├── commands/
│   ├── __init__.py
│   ├── proxy.py              # Modified: start uvicorn instead of mitmproxy
│   ├── init.py               # Updated default config template
│   ├── config_cmd.py         # Kept as-is
│   ├── dashboard.py          # Kept as-is
│   ├── doctor.py             # Updated health checks
│   ├── routes.py             # Updated for model-name routing
│   └── view.py               # Kept as-is
└── dashboard/
    ├── __init__.py
    ├── server.py             # Kept as-is
    └── api.py                # Kept as-is

tests/
├── test_config.py            # Updated for new config schema
├── test_router.py            # NEW: model-name parsing tests
├── test_converter.py         # NEW: format conversion tests
├── test_server.py            # NEW: FastAPI endpoint tests
├── test_addon.py             # REMOVED (mitmproxy addon no longer exists)
├── test_rotator.py           # Updated or removed
├── test_logger.py            # Kept
├── test_cli.py               # Updated
├── test_proxy.py             # Updated for uvicorn
├── test_process.py           # Updated
├── test_viewer.py            # Kept
├── test_dashboard.py         # Kept
└── test_integration.py       # Updated
```

**Structure Decision**: Single project layout. Core routing logic in `router.py` and `converter.py`. FastAPI app in `server.py`. Existing modules (logger, viewer, dashboard, process) kept with necessary updates.

## New Config Schema

```yaml
# ~/.otel-agent/config.yaml
providers:
  - name: openai
    base_url: https://api.openai.com/v1
    api_key: sk-...
    api_format: openai          # openai | anthropic

  - name: xiaomi
    base_url: https://api.xiaomi.com/v1
    api_key: sk-...
    api_format: openai

  - name: openrouter
    base_url: https://openrouter.ai/api/v1
    api_key: sk-...
    api_format: openai

  - name: anthropic
    base_url: https://api.anthropic.com
    api_key: sk-ant-...
    api_format: anthropic
```

**Key changes from v1 config**:
- Flat list of providers (no more `providers.openai[]` / `providers.anthropic[]` nesting)
- Each provider has an `api_format` field instead of being grouped by type
- No more `active` flag — routing is model-name-driven, all providers are always active
- Provider `name` is the routing key used in model name prefix

## Routing Logic

```python
def parse_model(model: str) -> tuple[str, str]:
    """Parse 'openrouter/openai/gpt-5.4' → ('openrouter', 'openai/gpt-5.4')."""
    parts = model.split("/", 1)
    if len(parts) < 2:
        raise ValueError(f"Model must include provider prefix: '{model}'")
    return parts[0], parts[1]

def resolve_provider(provider_name: str, config: Config) -> Provider:
    """Look up provider by name from config."""
    ...
```

## Format Conversion

When a client sends an Anthropic-format request to `/v1/messages` but the target provider uses `api_format: openai`:
1. Convert Anthropic messages format → OpenAI messages format
2. Convert Anthropic parameters (max_tokens, system, etc.) → OpenAI parameters
3. Forward to provider
4. Convert response back to Anthropic format

When a client sends an OpenAI-format request to `/v1/chat/completions` but the target provider uses `api_format: anthropic`:
1. Convert OpenAI messages format → Anthropic messages format
2. Forward to provider
3. Convert response back to OpenAI format

Streaming responses must be converted chunk-by-chunk preserving SSE semantics.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|-----------|--------------------------------------|
| Format conversion module | Two API formats (OpenAI + Anthropic) with cross-routing | Single format would require all providers to support same API, limiting flexibility |
| Async httpx client | Streaming SSE passthrough requires async | Sync requests would block on long-running LLM calls |
