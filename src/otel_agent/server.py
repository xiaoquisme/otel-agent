"""FastAPI-based LLM API gateway with model-name-based routing."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from otel_agent.auth_vault import AuthError, get_status
from otel_agent.config import Config, Provider
from otel_agent.dashboard.api import DashboardAPI
from otel_agent.dashboard.routes import router as dashboard_router, set_api as set_dashboard_api
from otel_agent.dashboard.spa import find_frontend_dist, register_frontend, register_legacy_index
from otel_agent.converter import (
    OpenAIToAnthropicStreamConverter,
    anthropic_to_openai_request,
    anthropic_to_openai_response,
    convert_anthropic_chunk_to_openai,
    openai_to_anthropic_request,
    openai_to_anthropic_response,
)
from otel_agent.logger import TelemetryLogger, redact_sensitive_headers
from otel_agent.models import ModelCache, aggregate_models, fetch_provider_models
from otel_agent.router import parse_model, resolve_provider

logger = logging.getLogger(__name__)

#: How much of a request or response body a telemetry row keeps. It is applied
#: when the row is written, which is what lets an accumulator feeding it stop
#: at the same point instead of holding a whole stream in memory for a
#: truncation that would discard it.
_TELEMETRY_BODY_LIMIT = 500_000


def normalize_usage(response: dict | str) -> dict[str, int | None]:
    """Normalize provider usage without estimating token counts."""
    raw = response.get("usage") if isinstance(response, dict) else None
    usage = raw if isinstance(raw, dict) else {}
    def valid(value):
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    input_tokens = valid(usage.get("input_tokens", usage.get("prompt_tokens")))
    output_tokens = valid(usage.get("output_tokens", usage.get("completion_tokens")))
    total_tokens = valid(usage.get("total_tokens"))
    if total_tokens is None:
        values = [value for value in (input_tokens, output_tokens) if value is not None]
        total_tokens = sum(values) if values else None
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}

from otel_agent.provider_utils import (
    build_upstream_url,
    build_image_upstream_url,
    build_image_edit_upstream_url,
    build_request_headers,
    build_responses_upstream_url,
    prefix_model_name,
    rewrite_upstream_model,
    serves_only_responses,
)


def create_app(config: Config, telemetry: TelemetryLogger) -> FastAPI:
    """Create the FastAPI application with all routes."""
    app = FastAPI(title="otel-agent", version="0.1.0")
    client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))
    model_cache = ModelCache(config)
    # ------------------------------------------------------------------
    # Dashboard (merged into proxy process)
    # ------------------------------------------------------------------
    # Pass the TelemetryLogger's storage to DashboardAPI so it shares
    # the same DuckDB connection instead of opening a second one.
    # DuckDB uses file-level locking that prevents concurrent access
    # from multiple processes (see docs/solutions/ for details).
    dashboard_api = DashboardAPI(telemetry.db_path, storage=telemetry.storage)
    set_dashboard_api(dashboard_api)
    app.include_router(dashboard_router)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await client.aclose()
        dashboard_api.close()
        telemetry.close()

    # ------------------------------------------------------------------
    # Credential failures
    # ------------------------------------------------------------------
    @app.exception_handler(AuthError)
    async def credential_error(request: Request, exc: AuthError) -> JSONResponse:
        """Answer a subscription credential failure as what it is (R12).

        The routes resolve a bearer before they forward anything, so an
        AuthError used to leave the operation and reach the client as an
        unclassified 500 — the same answer the client gets from a bug in this
        gateway. It is neither: the gateway is fine and the upstream was never
        asked. 503 with its own error type says which of the two it is, and the
        subscription's status rides along so the diagnosis does not stop at
        "something went wrong" (AE2).
        """
        error: dict[str, Any] = {
            "message": str(exc),
            "type": "credential_error",
            "code": "credential_unavailable",
        }
        body: dict[str, Any] = {"error": error}
        if exc.provider:
            error["provider"] = exc.provider
            body["credential"] = get_status(exc.provider)
        logger.warning("Credential unavailable: %s", exc)
        return JSONResponse(body, status_code=503)

    # ------------------------------------------------------------------
    # OpenAI-compatible endpoint
    # ------------------------------------------------------------------
    @app.post("/v1/chat/completions", response_model=None)
    async def chat_completions(request: Request):
        """OpenAI-compatible chat completions endpoint."""
        body = await request.json()
        model = body.get("model", "")
        is_stream = body.get("stream", False)

        try:
            provider_name, upstream_model = parse_model(model)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        try:
            provider = resolve_provider(provider_name, config)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        # A Responses-only upstream cannot serve this shape at all. Say so at
        # the client's own shape instead of forwarding and passing on a 404.
        if serves_only_responses(provider):
            return _responses_only_refusal(provider, request)

        # Prepare the upstream request body
        upstream_body = dict(body)
        upstream_body["model"] = rewrite_upstream_model(provider, upstream_model)

        # If provider speaks Anthropic, convert the request
        needs_conversion = provider.api_format == "anthropic"

        if needs_conversion:
            upstream_body = openai_to_anthropic_request(upstream_body)

        url = build_upstream_url(provider)
        headers = await build_request_headers(provider)

        start_time = time.monotonic()
        original_body = json.dumps(body)
        log_body = config.log_request_body

        if is_stream:
            return await _handle_streaming(
                client, url, headers, upstream_body,
                provider, telemetry, request, start_time,
                source_format="openai", target_format=provider.api_format,
                request_body=original_body, log_body=log_body,
            )

        return await _handle_non_streaming(
            client, url, headers, upstream_body,
            provider, telemetry, request, start_time,
            source_format="openai", target_format=provider.api_format,
            request_body=original_body, log_body=log_body,
        )

    # ------------------------------------------------------------------
    # Anthropic-compatible endpoint
    # ------------------------------------------------------------------
    @app.post("/v1/messages", response_model=None)
    async def messages(request: Request):
        """Anthropic-compatible messages endpoint."""
        body = await request.json()
        model = body.get("model", "")
        is_stream = body.get("stream", False)

        try:
            provider_name, upstream_model = parse_model(model)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        try:
            provider = resolve_provider(provider_name, config)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        # See the chat-completions route: a Responses-only upstream cannot
        # serve the Anthropic shape either.
        if serves_only_responses(provider):
            return _responses_only_refusal(provider, request)

        upstream_body = dict(body)
        upstream_body["model"] = rewrite_upstream_model(provider, upstream_model)

        needs_conversion = provider.api_format == "openai"

        if needs_conversion:
            upstream_body = anthropic_to_openai_request(upstream_body)

        url = build_upstream_url(provider)
        headers = await build_request_headers(provider)

        start_time = time.monotonic()
        original_body = json.dumps(body)
        log_body = config.log_request_body

        if is_stream:
            return await _handle_streaming(
                client, url, headers, upstream_body,
                provider, telemetry, request, start_time,
                source_format="anthropic", target_format=provider.api_format,
                request_body=original_body, log_body=log_body,
            )

        return await _handle_non_streaming(
            client, url, headers, upstream_body,
            provider, telemetry, request, start_time,
            source_format="anthropic", target_format=provider.api_format,
            request_body=original_body, log_body=log_body,
        )

    # ------------------------------------------------------------------
    # Responses-native endpoint (pass-through, no protocol translation)
    # ------------------------------------------------------------------
    @app.post("/v1/responses", response_model=None)
    async def responses(request: Request):
        """Responses-native endpoint, passed straight through to the upstream.

        No converter is installed, so the dialect's ``event:`` lines and blank
        separators reach the client as they arrive. The gateway's whole
        accommodation of this upstream is the normalization below.
        """
        body = await request.json()
        model = body.get("model", "")

        try:
            provider_name, upstream_model = parse_model(model)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        try:
            provider = resolve_provider(provider_name, config)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        # The normalization below is written for this upstream, so the route is
        # served only for a provider that declares a Responses surface.
        if not serves_only_responses(provider):
            return JSONResponse(
                {"error": {"message": f"Provider '{provider.name}' does not serve the Responses API. Route to a provider that declares one, or use /v1/chat/completions.", "type": "invalid_request_error"}},
                status_code=400,
            )

        # Continuation is deliberately not supported: the upstream rejects
        # previous_response_id and keeps no server-side state. Stripping it
        # would hand a client that depends on continuation a successful but
        # contextless answer, so it is refused distinguishably instead.
        if body.get("previous_response_id"):
            return JSONResponse(
                {"error": {"message": f"Provider '{provider.name}' is stateless: 'previous_response_id' is not supported. Send the whole conversation in 'input' instead.", "type": "invalid_request_error"}},
                status_code=400,
            )

        upstream_body = dict(body)
        upstream_body["model"] = rewrite_upstream_model(provider, upstream_model)
        # store/include are overwritten whatever the client asked for — a
        # default injected only when missing would forward a client's explicit
        # store: true and leave the conversation on the owner's account.
        upstream_body["stream"] = True
        upstream_body["store"] = False
        upstream_body["include"] = ["reasoning.encrypted_content"]
        # Parameters this upstream rejects outright.
        upstream_body.pop("max_output_tokens", None)
        upstream_body.pop("temperature", None)

        # No identity headers ride along: the upstream treats originator,
        # User-Agent and ChatGPT-Account-ID as optional, and forwarding a
        # client's own values would only invite impersonation.
        url = build_responses_upstream_url(provider)
        headers = await build_request_headers(provider)

        start_time = time.monotonic()
        original_body = json.dumps(body)
        log_body = config.log_request_body

        # The upstream accepts only streaming; which form the CLIENT gets is a
        # separate question, and it follows the same convention as the other
        # two routes (body.get("stream", False)) so that an omitted parameter
        # means the same thing across the gateway. It also matches the
        # Responses API itself, whose `stream` defaults to false — a client
        # that omits it expects one JSON object, not SSE. A non-streaming
        # client still gets its answer: the upstream stream is folded back
        # into a single object (see _handle_responses_non_streaming).
        if body.get("stream", False):
            return await _handle_streaming(
                client, url, headers, upstream_body,
                provider, telemetry, request, start_time,
                source_format="responses", target_format="responses",
                request_body=original_body, log_body=log_body,
            )

        return await _handle_responses_non_streaming(
            client, url, headers, upstream_body,
            provider, telemetry, request, start_time,
            request_body=original_body, log_body=log_body,
        )

    # ------------------------------------------------------------------
    # Image generation endpoint (OpenAI-compatible)
    # ------------------------------------------------------------------
    @app.post("/v1/images/generations", response_model=None)
    async def image_generations(request: Request):
        """OpenAI-compatible image generation endpoint.

        Only supported for OpenAI-format providers. Anthropic providers
        return 400 since they don't have an image generation API.
        """
        body = await request.json()
        model = body.get("model", "")

        try:
            provider_name, upstream_model = parse_model(model)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        try:
            provider = resolve_provider(provider_name, config)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        # Anthropic doesn't have an image generation API
        if provider.api_format == "anthropic":
            return JSONResponse(
                {"error": {"message": f"Provider '{provider.name}' uses Anthropic API format which does not support image generation. Route to an OpenAI-format provider instead.", "type": "invalid_request_error"}},
                status_code=400,
            )

        # Prepare upstream body
        upstream_body = dict(body)
        if upstream_model:
            upstream_body["model"] = upstream_model

        url = build_image_upstream_url(provider)
        headers = await build_request_headers(provider)
        start_time = time.monotonic()
        original_body = json.dumps(body)
        log_body = config.log_request_body

        return await _handle_non_streaming(
            client, url, headers, upstream_body,
            provider, telemetry, request, start_time,
            source_format="openai", target_format="openai",
            request_body=original_body, log_body=log_body,
        )

    # ------------------------------------------------------------------
    # Image edit endpoint (OpenAI-compatible)
    # ------------------------------------------------------------------
    @app.post("/v1/images/edits", response_model=None)
    async def image_edits(request: Request):
        """OpenAI-compatible image edit endpoint.

        Accepts multipart form data with an image file, prompt, and optional
        mask. Only supported for OpenAI-format providers.
        """
        form = await request.form()

        # Extract model from form data (may be absent — defaults to dall-e-2)
        model_raw = form.get("model", "dall-e-2")
        model = str(model_raw) if model_raw else "dall-e-2"

        try:
            provider_name, upstream_model = parse_model(model)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        try:
            provider = resolve_provider(provider_name, config)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        if provider.api_format == "anthropic":
            return JSONResponse(
                {"error": {"message": f"Provider '{provider.name}' uses Anthropic API format which does not support image editing. Route to an OpenAI-format provider instead.", "type": "invalid_request_error"}},
                status_code=400,
            )

        # Build upstream multipart form
        import io
        files = {}
        data = {}

        for key in form:
            if key == "model":
                data["model"] = upstream_model or "dall-e-2"
            elif key in ("image", "mask"):
                upload_file = form[key]
                # UploadFile has 'read' method; str does not
                if callable(getattr(upload_file, "read", None)):
                    content = await upload_file.read()
                    fname = getattr(upload_file, "filename", key)
                    ctype = getattr(upload_file, "content_type", "application/octet-stream")
                    files[key] = (fname, io.BytesIO(content), ctype)
            else:
                val = form[key]
                if isinstance(val, str):
                    data[key] = val

        url = build_image_edit_upstream_url(provider)
        headers = await build_request_headers(provider)
        # Remove Content-Type for multipart (httpx sets it with boundary)
        headers.pop("Content-Type", None)
        start_time = time.monotonic()
        original_body = f"multipart form: {list(form.keys())}"
        log_body = config.log_request_body

        try:
            resp = await client.post(url, headers=headers, files=files, data=data)
        except httpx.ConnectError as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            error_body = {"error": {"message": f"Connection failed to provider '{provider.name}': {e}", "type": "server_error"}}
            _log_telemetry(telemetry, request, 502, error_body, latency_ms, provider, request_body=original_body, log_body=log_body, source_format="openai")
            return JSONResponse(error_body, status_code=502)
        except httpx.TimeoutException:
            latency_ms = (time.monotonic() - start_time) * 1000
            error_body = {"error": {"message": f"Timeout connecting to provider '{provider.name}'", "type": "server_error"}}
            _log_telemetry(telemetry, request, 504, error_body, latency_ms, provider, request_body=original_body, log_body=log_body, source_format="openai")
            return JSONResponse(error_body, status_code=504)

        latency_ms = (time.monotonic() - start_time) * 1000

        try:
            resp_body = resp.json()
        except Exception:
            resp_body = {"raw": resp.text}

        _log_telemetry(telemetry, request, resp.status_code, resp_body, latency_ms, provider, request_body=original_body, resp_headers=dict(resp.headers), log_body=log_body, source_format="openai")

        return JSONResponse(resp_body, status_code=resp.status_code)

    # ------------------------------------------------------------------
    # Models endpoint
    # ------------------------------------------------------------------
    @app.get("/v1/models", response_model=None)
    async def list_models(request: Request, provider: str | None = None):
        """List available models from all providers (OpenAI-compatible)."""
        providers = config.providers

        if provider is not None:
            if provider not in providers:
                available = list(providers.keys())
                return JSONResponse(
                    {"error": {"message": f"Unknown provider '{provider}'. Configured: {', '.join(available) or 'none'}.", "type": "invalid_request_error"}},
                    status_code=400,
                )
            providers = {provider: providers[provider]}

        raw_models: dict[str, list] = {}
        failures: dict[str, str] = {}
        for name, prov in providers.items():
            cached = model_cache.get(name)
            if cached is not None:
                raw_models[name] = cached
            else:
                fetched = await fetch_provider_models(client, prov, failures=failures)
                # A credential failure is not cached: it would hold the empty
                # list in place for a whole TTL after the operator re-adopts,
                # which is the same silent absence in slower motion.
                if name not in failures:
                    model_cache.put(name, fetched)
                raw_models[name] = fetched

        if provider is not None and provider in failures:
            # The client asked for exactly this provider, so "no models" would
            # be a wrong answer and a 200 would dress it up as a right one
            # (specs/009-models-api allows a clear error instead).
            return JSONResponse(
                {
                    "error": {
                        "message": failures[provider],
                        "type": "credential_error",
                        "code": "credential_unavailable",
                        "provider": provider,
                    }
                },
                status_code=503,
            )

        return JSONResponse(aggregate_models(raw_models, failures))

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    # SPA catch-all must be last so GET /v1/models and /health stay JSON.
    _pkg_dir = Path(__file__).parent
    frontend_dist = find_frontend_dist(
        _pkg_dir / "dashboard" / "frontend_dist",
        _pkg_dir.parent.parent / "frontend" / "dist",
    )
    register_frontend(app, frontend_dist)
    if frontend_dist is None:
        register_legacy_index(app, Path(__file__).parent / "dashboard" / "index.html")

    return app


def _responses_only_refusal(provider: Provider, request: Request) -> JSONResponse:
    """Refuse a chat-shaped request to an upstream with only one shape.

    A provider that declares the Responses surface alone cannot serve either
    of the chat-shaped dialects. The client is told that at its own shape,
    rather than being forwarded a 404 from the upstream it cannot read.
    """
    return JSONResponse(
        {
            "error": {
                "message": f"Provider '{provider.name}' serves only the Responses API and is not available on {request.url.path}. POST to /v1/responses with model '{provider.name}/<model>' instead.",
                "type": "invalid_request_error",
            }
        },
        status_code=400,
    )


async def _handle_non_streaming(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: dict,
    provider: Provider,
    telemetry: TelemetryLogger,
    request: Request,
    start_time: float,
    source_format: str,
    target_format: str,
    request_body: str = "",
    log_body: bool = True,
) -> JSONResponse:
    """Handle a non-streaming request to an upstream provider."""
    try:
        resp = await client.post(url, headers=headers, json=body)
    except httpx.ConnectError as e:
        latency_ms = (time.monotonic() - start_time) * 1000
        error_body = {"error": {"message": f"Connection failed to provider '{provider.name}': {e}", "type": "server_error"}}
        _log_telemetry(
            telemetry, request, 502, error_body, latency_ms, provider,
            request_body=request_body, log_body=log_body, source_format=source_format,
        )
        return JSONResponse(error_body, status_code=502)
    except httpx.TimeoutException:
        latency_ms = (time.monotonic() - start_time) * 1000
        error_body = {"error": {"message": f"Timeout connecting to provider '{provider.name}'", "type": "server_error"}}
        _log_telemetry(
            telemetry, request, 504, error_body, latency_ms, provider,
            request_body=request_body, log_body=log_body, source_format=source_format,
        )
        return JSONResponse(error_body, status_code=504)

    latency_ms = (time.monotonic() - start_time) * 1000

    try:
        resp_body = resp.json()
    except Exception:
        resp_body = {"raw": resp.text}

    # Convert response back to the client's expected format if needed
    if source_format != target_format:
        if source_format == "openai" and target_format == "anthropic":
            resp_body = anthropic_to_openai_response(resp_body)
        elif source_format == "anthropic" and target_format == "openai":
            resp_body = openai_to_anthropic_response(resp_body)

    # Log telemetry
    _log_telemetry(
        telemetry, request, resp.status_code, resp_body, latency_ms, provider,
        request_body=request_body, resp_headers=dict(resp.headers), log_body=log_body,
        source_format=source_format,
    )

    if isinstance(resp_body, dict):
        from otel_agent.xai_errors import is_xai_provider, rewrite_xai_error
        if is_xai_provider(provider):
            resp_body = rewrite_xai_error(resp.status_code, resp_body)

    return JSONResponse(resp_body, status_code=resp.status_code)


async def _handle_streaming(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: dict,
    provider: Provider,
    telemetry: TelemetryLogger,
    request: Request,
    start_time: float,
    source_format: str,
    target_format: str,
    request_body: str = "",
    log_body: bool = True,
) -> StreamingResponse:
    """Handle a streaming request to an upstream provider."""

    async def stream_generator() -> AsyncIterator[bytes]:
        collected_chunks: list[str] = []
        collected_chars = 0
        resp_headers: dict[str, str] = {}
        stream_status = 200
        last_valid_usage: dict | None = None
        model_name: str | None = None
        try:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                resp_headers = dict(resp.headers)
                stream_status = resp.status_code

                # Detect non-SSE error responses (e.g. 400 JSON from xAI).
                # Without this check the generator silently yields nothing
                # and the client sees an empty stream.
                content_type = resp.headers.get("content-type", "")
                if resp.status_code >= 400 and "text/event-stream" not in content_type:
                    error_body = (await resp.aread()).decode("utf-8", errors="replace")
                    if source_format == "responses":
                        # A Responses client cannot read the bare data frame
                        # below, so it would see an unparsable frame or a dead
                        # stream instead of the upstream's rejection.
                        yield _responses_error_frame(
                            f"Upstream error {resp.status_code}: {_upstream_error_message(error_body)}"
                        )
                        return
                    try:
                        error_data = json.loads(error_body)
                        error_msg = json.dumps(error_data)
                    except (json.JSONDecodeError, ValueError):
                        error_msg = json.dumps({"error": {"message": error_body, "type": "server_error"}})
                    yield f"data: {error_msg}\n\n".encode()
                    if source_format == "openai":
                        yield b"data: [DONE]\n\n"
                    return

                sent_done = False
                openai_to_anthropic: OpenAIToAnthropicStreamConverter | None = None
                if source_format == "anthropic" and target_format == "openai":
                    openai_to_anthropic = OpenAIToAnthropicStreamConverter()
                async for line in resp.aiter_lines():
                    if not line:
                        if openai_to_anthropic is None:
                            yield b"\n"
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            if openai_to_anthropic is not None:
                                for event in openai_to_anthropic.flush():
                                    yield event.encode()
                            elif source_format == "openai":
                                yield b"data: [DONE]\n\n"
                                sent_done = True
                            break

                        try:
                            chunk_data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        if source_format == target_format:
                            # No conversion needed
                            yield f"data: {json.dumps(chunk_data)}\n\n".encode()
                        elif source_format == "openai" and target_format == "anthropic":
                            # Upstream is anthropic, client expects openai
                            converted = convert_anthropic_chunk_to_openai(chunk_data)
                            if converted:
                                yield f"data: {json.dumps(converted)}\n\n".encode()
                        elif openai_to_anthropic is not None:
                            # Upstream is openai, client expects anthropic
                            for event in openai_to_anthropic.feed(chunk_data):
                                yield event.encode()

                        # Extract model name from first chunk. Chat completions
                        # carry it at the top level, Anthropic nests it in
                        # `message`, the Responses API in `response`.
                        if model_name is None:
                            for candidate in (chunk_data, chunk_data.get("message"), chunk_data.get("response")):
                                if isinstance(candidate, dict) and candidate.get("model"):
                                    model_name = candidate["model"]
                                    break

                        # Collect for telemetry, and stop at the point the
                        # row would keep: a stream can run for minutes and
                        # carry the entire response, so accumulating all of it
                        # would hold a second copy of the answer, per in-flight
                        # request, purely to truncate it on the way in.
                        if collected_chars < _TELEMETRY_BODY_LIMIT:
                            chunk_text = json.dumps(chunk_data)
                            collected_chunks.append(chunk_text)
                            collected_chars += len(chunk_text)
                        # T031: Extract usage from streaming chunks. Same three
                        # places as the model name; prefer the first source that
                        # has a value for each field.
                        merged = normalize_usage(chunk_data)
                        for nested in (chunk_data.get("message"), chunk_data.get("response")):
                            if not isinstance(nested, dict):
                                continue
                            nested_usage = normalize_usage(nested)
                            merged = {
                                k: merged[k] if merged[k] is not None else nested_usage[k]
                                for k in merged
                            }
                        if any(v is not None for v in merged.values()):
                            if last_valid_usage is None:
                                last_valid_usage = merged
                            else:
                                # Accumulate: keep existing non-None, overlay new non-None
                                last_valid_usage = {
                                    k: merged[k] if merged[k] is not None else last_valid_usage[k]
                                    for k in last_valid_usage
                                }
                    elif openai_to_anthropic is None:
                        # Pass through non-data lines (event:, id:, etc.)
                        yield f"{line}\n".encode()

                if openai_to_anthropic is not None:
                    for event in openai_to_anthropic.flush():
                        yield event.encode()
                # If upstream closed the stream without sending [DONE],
                # send it ourselves so the client knows the stream is complete.
                elif not sent_done and source_format == "openai":
                    yield b"data: [DONE]\n\n"

        except httpx.ConnectError as e:
            stream_status = 502
            message = f"Connection failed: {e}"
            if source_format == "responses":
                yield _responses_error_frame(message)
            else:
                yield f"data: {json.dumps({'error': {'message': message, 'type': 'server_error'}})}\n\n".encode()
        except httpx.TimeoutException:
            stream_status = 504
            message = "Timeout"
            if source_format == "responses":
                yield _responses_error_frame(message)
            else:
                yield f"data: {json.dumps({'error': {'message': message, 'type': 'server_error'}})}\n\n".encode()
        finally:
            latency_ms = (time.monotonic() - start_time) * 1000
            resp_body: dict = {"streamed": True, "preview": "".join(collected_chunks), "model": model_name}
            # T031: If usage was captured from streaming chunks, include it in the
            # response body so _log_telemetry can normalize and persist it.
            if last_valid_usage is not None:
                # Recompute total from merged input/output to avoid stale
                # auto-computed values from partial chunks (e.g. message_delta
                # only has output_tokens so its total_tokens is wrong).
                inp = last_valid_usage["input_tokens"]
                out = last_valid_usage["output_tokens"]
                recomputed_total = (
                    (inp or 0) + (out or 0) if inp is not None or out is not None
                    else last_valid_usage["total_tokens"]
                )
                resp_body["usage"] = {
                    "input_tokens": inp,
                    "output_tokens": out,
                    "total_tokens": recomputed_total,
                }
            _log_telemetry(
                telemetry, request, stream_status, resp_body, latency_ms, provider,
                request_body=request_body, resp_headers=resp_headers, log_body=log_body,
                source_format=source_format,
            )

    media_type = "text/event-stream"
    return StreamingResponse(stream_generator(), media_type=media_type)


async def _handle_responses_non_streaming(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: dict,
    provider: Provider,
    telemetry: TelemetryLogger,
    request: Request,
    start_time: float,
    request_body: str = "",
    log_body: bool = True,
) -> JSONResponse:
    """Serve a non-streaming Responses client from a streaming-only upstream.

    KTD5: deliberately not ``_handle_non_streaming``. That one posts once and
    forwards whatever comes back, which for this upstream is a 400 reading
    ``Stream must be set to true``. The upstream is asked in the only form it
    accepts, and the stream is folded back into the single object the client
    asked for, which never learns where it came from.

    The body handed back is the envelope the upstream itself put in its
    terminal ``response.completed`` event — taken, not reconstructed. A
    non-streaming client has no ``event: error`` frame to read, so every
    failure below is a non-2xx with a diagnosable body rather than a stream
    that ends early behind an empty 200.
    """
    resp_headers: dict[str, str] = {}
    status_code = 200
    failure: str | None = None
    final_response: dict | None = None

    try:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            resp_headers = dict(resp.headers)
            status_code = resp.status_code

            if resp.status_code >= 400:
                # A rejection that never became a stream (the shape this
                # upstream uses for an unsupported parameter, say).
                raw = (await resp.aread()).decode("utf-8", errors="replace")
                failure = f"Upstream error {resp.status_code}: {_upstream_error_message(raw)}"
            else:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if not isinstance(event, dict):
                        continue
                    if event.get("type") == "error":
                        # Raised mid-answer, after the stream had opened.
                        status_code = 502
                        failure = str(event.get("message") or "upstream error event")
                        break
                    if event.get("type") == "response.completed":
                        envelope = event.get("response")
                        if isinstance(envelope, dict):
                            final_response = envelope
    except httpx.ConnectError as e:
        status_code = 502
        failure = f"Connection failed to provider '{provider.name}': {e}"
    except httpx.TimeoutException:
        status_code = 504
        failure = f"Timeout connecting to provider '{provider.name}'"

    latency_ms = (time.monotonic() - start_time) * 1000

    if failure is None and final_response is None:
        # The stream ended without ever naming the finished response, so the
        # answer it was carrying is truncated or absent. It must not be
        # reported as a complete one.
        status_code = 502
        failure = (
            f"Upstream stream ended without a response.completed event for "
            f"provider '{provider.name}'"
        )

    if failure is not None:
        error_body = {
            "error": {
                "message": failure,
                "type": "server_error" if status_code >= 500 else "invalid_request_error",
            }
        }
        _log_telemetry(
            telemetry, request, status_code, error_body, latency_ms, provider,
            request_body=request_body, resp_headers=resp_headers, log_body=log_body,
            source_format="responses",
        )
        return JSONResponse(error_body, status_code=status_code)

    _log_telemetry(
        telemetry, request, status_code, final_response, latency_ms, provider,
        request_body=request_body, resp_headers=resp_headers, log_body=log_body,
        source_format="responses",
    )
    return JSONResponse(final_response, status_code=status_code)


def _responses_error_frame(message: str) -> bytes:
    """Frame an upstream failure the way a Responses client expects it.

    The shared handler's bare ``data:`` frame carries no ``event:`` line, so a
    Responses-native client cannot read a rejection out of it.
    """
    payload = {
        "type": "error",
        "code": None,
        "message": message,
        "param": None,
        # A single frame, and nothing preceded it in this stream.
        "sequence_number": 0,
    }
    return f"event: error\ndata: {json.dumps(payload)}\n\n".encode()


def _upstream_error_message(body: str) -> str:
    """Pull the human-readable half out of an upstream error body."""
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return body
    if isinstance(parsed, dict):
        detail = parsed.get("detail")
        if isinstance(detail, str) and detail:
            return detail
        error = parsed.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        if isinstance(error, str) and error:
            return error
    return body


def _log_telemetry(
    telemetry: TelemetryLogger,
    request: Request,
    status_code: int,
    resp_body: dict | str,
    latency_ms: float,
    provider: Provider,
    request_body: str = "",
    resp_headers: dict[str, str] | None = None,
    log_body: bool = True,
    source_format: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> None:
    """Log request/response to telemetry database."""
    try:
        body_str = json.dumps(resp_body) if isinstance(resp_body, dict) else str(resp_body)
        usage = normalize_usage(resp_body)
        # Extract client-visible model from response body for analytics.
        # Fall back to the client's request body when the upstream omits the
        # model field (common with OpenRouter and some proxied providers).
        # When falling back, skip prefixing — the request body model is
        # already prefixed (e.g. "openai/gpt-4"), unlike upstream responses
        # which return the bare model name (e.g. "gpt-4").
        from_request_body = False
        model_name = None
        if isinstance(resp_body, dict):
            model_name = resp_body.get("model")
        if not model_name and request_body:
            try:
                model_name = json.loads(request_body).get("model")
                from_request_body = True
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
        if from_request_body:
            model_name = model_name or None
        else:
            model_name = prefix_model_name(model_name or None, provider.name)
        stored_body = request_body[:_TELEMETRY_BODY_LIMIT] if log_body else ""
        stored_headers = redact_sensitive_headers(resp_headers) if resp_headers else {}
        stored_request_headers = dict(request.headers)
        if extra_headers:
            stored_request_headers.update(extra_headers)
        telemetry.log_request(
            method=request.method,
            url=str(request.url),
            request_headers=stored_request_headers,
            request_body=stored_body,
            response_status=status_code,
            response_headers=stored_headers,
            response_body=body_str[:_TELEMETRY_BODY_LIMIT],
            latency_ms=latency_ms,
            upstream=provider.base_url,
            model_name=model_name,
            input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
            format=source_format,
        )
    except Exception:
        logger.exception("Failed to log telemetry")



