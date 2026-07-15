"""FastAPI-based LLM API gateway with model-name-based routing."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from otel_agent.config import Config, Provider
from otel_agent.dashboard.api import DashboardAPI
from otel_agent.dashboard.routes import router as dashboard_router, set_api as set_dashboard_api
from otel_agent.converter import (
    anthropic_to_openai_request,
    anthropic_to_openai_response,
    convert_anthropic_chunk_to_openai,
    convert_openai_chunk_to_anthropic,
    openai_to_anthropic_request,
    openai_to_anthropic_response,
)
from otel_agent.logger import TelemetryLogger, redact_sensitive_headers
from otel_agent.models import ModelCache, aggregate_models, fetch_provider_models
from otel_agent.router import parse_model, resolve_provider

logger = logging.getLogger(__name__)


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

# Auth header patterns per provider API format
AUTH_HEADERS = {
    "openai": lambda key: {"Authorization": f"Bearer {key}"},
    "anthropic": lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01"},
}


def create_app(config: Config, telemetry: TelemetryLogger) -> FastAPI:
    """Create the FastAPI application with all routes."""
    app = FastAPI(title="otel-agent", version="0.1.0")
    client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))
    model_cache = ModelCache(config)
    # ------------------------------------------------------------------
    # Dashboard (merged into proxy process)
    # ------------------------------------------------------------------
    dashboard_api = DashboardAPI(telemetry.db_path)
    set_dashboard_api(dashboard_api)
    app.include_router(dashboard_router)

    # Serve React dashboard from frontend/dist/
    _frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if (_frontend_dist / "index.html").exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="static")

        @app.get("/", response_class=FileResponse)
        async def serve_dashboard():
            """Serve the React dashboard."""
            return FileResponse(_frontend_dist / "index.html", media_type="text/html")
    else:
        # Fallback: serve old index.html
        html_path = Path(__file__).parent / "dashboard" / "index.html"

        @app.get("/", response_class=FileResponse)
        async def serve_dashboard():
            """Serve the dashboard index.html."""
            if html_path.exists():
                return FileResponse(html_path, media_type="text/html")
            from fastapi.responses import HTMLResponse
            return HTMLResponse("<h1>Dashboard</h1><p>index.html not found</p>")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await client.aclose()
        dashboard_api.close()
        telemetry.close()

    # ------------------------------------------------------------------
    # OpenAI-compatible endpoint
    # ------------------------------------------------------------------
    @app.post("/v1/chat/completions", response_model=None)
    async def chat_completions(request: Request):
        """OpenAI-compatible chat completions endpoint."""
        body = await request.json()
        model = body.get("model", "")
        is_stream = body.get("stream", False)

        # Auto-mode interception
        if model == "auto":
            from otel_agent.auto_handler import handle_auto_mode
            return await handle_auto_mode(
                body, config, client, telemetry, request, is_stream,
            )

        try:
            provider_name, upstream_model = parse_model(model)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        try:
            provider = resolve_provider(provider_name, config)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        # Prepare the upstream request body
        upstream_body = dict(body)
        upstream_body["model"] = upstream_model

        # If provider speaks Anthropic, convert the request
        needs_conversion = provider.api_format == "anthropic"

        if needs_conversion:
            upstream_body = openai_to_anthropic_request(upstream_body)
            url = f"{provider.base_url.rstrip('/')}/messages"
        else:
            url = f"{provider.base_url.rstrip('/')}/chat/completions"

        headers = AUTH_HEADERS[provider.api_format](provider.api_key)
        headers["Content-Type"] = "application/json"

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

        # Auto-mode interception
        if model == "auto":
            from otel_agent.auto_handler import handle_auto_mode
            return await handle_auto_mode(
                body, config, client, telemetry, request, is_stream,
                client_format="anthropic",
            )

        try:
            provider_name, upstream_model = parse_model(model)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        try:
            provider = resolve_provider(provider_name, config)
        except ValueError as e:
            return JSONResponse({"error": {"message": str(e), "type": "invalid_request_error"}}, status_code=400)

        upstream_body = dict(body)
        upstream_body["model"] = upstream_model

        needs_conversion = provider.api_format == "openai"

        if needs_conversion:
            upstream_body = anthropic_to_openai_request(upstream_body)
            url = f"{provider.base_url.rstrip('/')}/chat/completions"
        else:
            url = f"{provider.base_url.rstrip('/')}/messages"

        headers = AUTH_HEADERS[provider.api_format](provider.api_key)
        headers["Content-Type"] = "application/json"

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
        for name, prov in providers.items():
            cached = model_cache.get(name)
            if cached is not None:
                raw_models[name] = cached
            else:
                fetched = await fetch_provider_models(client, prov)
                model_cache.put(name, fetched)
                raw_models[name] = fetched

        return JSONResponse(aggregate_models(raw_models))

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


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
        collected_text = ""
        resp_headers: dict[str, str] = {}
        stream_status = 200
        last_valid_usage: dict | None = None
        try:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                resp_headers = dict(resp.headers)
                sent_done = False
                async for line in resp.aiter_lines():
                    if not line:
                        yield b"\n"
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            if source_format == "openai":
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
                        elif source_format == "anthropic" and target_format == "openai":
                            # Upstream is openai, client expects anthropic
                            converted = convert_openai_chunk_to_anthropic(chunk_data)
                            if converted:
                                yield f"data: {json.dumps(converted)}\n\n".encode()

                        # Collect for telemetry
                        collected_text += json.dumps(chunk_data)
                        # T031: Extract usage from streaming chunks
                        chunk_usage = normalize_usage(chunk_data)
                        if chunk_usage["total_tokens"] is not None:
                            last_valid_usage = chunk_usage
                    else:
                        # Pass through non-data lines (event:, id:, etc.)
                        yield f"{line}\n".encode()

                # If upstream closed the stream without sending [DONE],
                # send it ourselves so the client knows the stream is complete.
                if not sent_done and source_format == "openai":
                    yield b"data: [DONE]\n\n"

        except httpx.ConnectError as e:
            stream_status = 502
            error_msg = json.dumps({"error": {"message": f"Connection failed: {e}", "type": "server_error"}})
            yield f"data: {error_msg}\n\n".encode()
        except httpx.TimeoutException:
            stream_status = 504
            error_msg = json.dumps({"error": {"message": "Timeout", "type": "server_error"}})
            yield f"data: {error_msg}\n\n".encode()
        finally:
            latency_ms = (time.monotonic() - start_time) * 1000
            resp_body: dict = {"streamed": True, "preview": collected_text}
            # T031: If usage was captured from streaming chunks, include it in the
            # response body so _log_telemetry can normalize and persist it.
            if last_valid_usage is not None:
                resp_body["usage"] = {
                    "input_tokens": last_valid_usage["input_tokens"],
                    "output_tokens": last_valid_usage["output_tokens"],
                    "total_tokens": last_valid_usage["total_tokens"],
                }
            _log_telemetry(
                telemetry, request, stream_status, resp_body, latency_ms, provider,
                request_body=request_body, resp_headers=resp_headers, log_body=log_body,
                source_format=source_format,
            )

    media_type = "text/event-stream"
    return StreamingResponse(stream_generator(), media_type=media_type)


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
) -> None:
    """Log request/response to telemetry database."""
    try:
        body_str = json.dumps(resp_body) if isinstance(resp_body, dict) else str(resp_body)
        usage = normalize_usage(resp_body)
        # Extract client-visible model from response body for analytics
        model_name = None
        if isinstance(resp_body, dict):
            model_name = resp_body.get("model") if resp_body.get("model") else None
        stored_body = request_body[:500_000] if log_body else ""
        stored_headers = redact_sensitive_headers(resp_headers) if resp_headers else {}
        telemetry.log_request(
            method=request.method,
            url=str(request.url),
            request_headers=dict(request.headers),
            request_body=stored_body,
            response_status=status_code,
            response_headers=stored_headers,
            response_body=body_str[:500_000],
            latency_ms=latency_ms,
            upstream=provider.base_url,
            model_name=model_name,
            input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
            format=source_format,
        )
    except Exception:
        logger.exception("Failed to log telemetry")



