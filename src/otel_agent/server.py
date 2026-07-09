"""FastAPI-based LLM API gateway with model-name-based routing."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from otel_agent.config import Config, Provider
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

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await client.aclose()
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

    # ------------------------------------------------------------------
    # Internal dashboard API (avoids DuckDB multi-process lock conflict)
    # ------------------------------------------------------------------
    @app.get("/internal/dashboard/requests")
    async def internal_requests(
        search: str = "",
        method: str = "",
        status: int = 0,
        cursor: int = 0,
        limit: int = 50,
    ):
        """Paginated request list for the dashboard (internal)."""
        return _query_requests(telemetry, search, method, status, cursor, limit)

    @app.get("/internal/dashboard/requests/{request_id}")
    async def internal_request_detail(request_id: int):
        """Single request detail for the dashboard (internal)."""
        return _query_request_detail(telemetry, request_id)

    @app.get("/internal/dashboard/max-id")
    async def internal_max_id():
        """Current max request ID for SSE (internal)."""
        return _query_max_id(telemetry)

    @app.get("/internal/dashboard/requests-since/{last_id}")
    async def internal_requests_since(last_id: int):
        """New requests since last_id for SSE (internal)."""
        return _query_requests_since(telemetry, last_id)

    @app.get("/internal/dashboard/export")
    async def internal_export(
        search: str = "",
        method: str = "",
        status: int = 0,
    ):
        """All filtered requests for export (internal)."""
        return _query_all_filtered(telemetry, search, method, status)

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
            request_body=request_body, log_body=log_body,
        )
        return JSONResponse(error_body, status_code=502)
    except httpx.TimeoutException:
        latency_ms = (time.monotonic() - start_time) * 1000
        error_body = {"error": {"message": f"Timeout connecting to provider '{provider.name}'", "type": "server_error"}}
        _log_telemetry(
            telemetry, request, 504, error_body, latency_ms, provider,
            request_body=request_body, log_body=log_body,
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
        try:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                resp_headers = dict(resp.headers)
                async for line in resp.aiter_lines():
                    if not line:
                        yield b"\n"
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            if source_format == "openai":
                                yield b"data: [DONE]\n\n"
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
                    else:
                        # Pass through non-data lines (event:, id:, etc.)
                        yield f"{line}\n".encode()

        except httpx.ConnectError as e:
            stream_status = 502
            error_msg = json.dumps({"error": {"message": f"Connection failed: {e}", "type": "server_error"}})
            yield f"data: {error_msg}\n\n".encode()
        except httpx.TimeoutException:
            stream_status = 504
            error_msg = json.dumps({"error": {"message": "Timeout", "type": "server_error"}})
            yield f"data: {error_msg}\n\n".encode()

        latency_ms = (time.monotonic() - start_time) * 1000
        _log_telemetry(
            telemetry, request, stream_status, {"streamed": True, "preview": collected_text[:500]}, latency_ms, provider,
            request_body=request_body, resp_headers=resp_headers, log_body=log_body,
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
) -> None:
    """Log request/response to telemetry database."""
    try:
        body_str = json.dumps(resp_body) if isinstance(resp_body, dict) else str(resp_body)
        stored_body = request_body[:100_000] if log_body else ""
        stored_headers = redact_sensitive_headers(resp_headers) if resp_headers else {}
        telemetry.log_request(
            method=request.method,
            url=str(request.url),
            request_headers=dict(request.headers),
            request_body=stored_body,
            response_status=status_code,
            response_headers=stored_headers,
            response_body=body_str[:100_000],
            latency_ms=latency_ms,
            upstream=provider.base_url,
        )
    except Exception:
        logger.exception("Failed to log telemetry")


# ------------------------------------------------------------------
# Internal dashboard query helpers (use TelemetryLogger's DuckDB conn)
# ------------------------------------------------------------------

def _build_where(search: str = "", method: str = "", status: int = 0) -> tuple[str, list]:
    """Build WHERE clause for request queries."""
    conditions: list[str] = []
    params: list = []
    if method:
        conditions.append("method = ?")
        params.append(method)
    if status:
        conditions.append("response_status = ?")
        params.append(status)
    if search:
        conditions.append("(url LIKE ? OR upstream LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = " AND ".join(conditions) if conditions else "1=1"
    return where, params


def _rows_to_dicts(cursor, rows: list) -> list[dict]:
    """Convert DuckDB result rows to dicts using cursor.description."""
    if not rows:
        return []
    if cursor is not None and hasattr(cursor, "description") and cursor.description:
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    return [dict(r) if hasattr(r, "keys") else r for r in rows]


def _query_requests(telemetry, search: str, method: str, status: int,
                    cursor: int, limit: int) -> dict:
    """Paginated request list — mirrors DashboardAPI.get_requests()."""
    conn = telemetry.conn
    where, params = _build_where(search, method, status)

    count_query = f"SELECT COUNT(*) FROM requests WHERE {where}"
    total = conn.execute(count_query, params).fetchone()[0]

    if cursor > 0:
        cursor_where = f"({where}) AND id < ?"
        cursor_params = params + [cursor]
    else:
        cursor_where = where
        cursor_params = params

    result = conn.execute(
        f"SELECT id, timestamp, method, url, upstream, response_status, latency_ms "
        f"FROM requests WHERE {cursor_where} ORDER BY id DESC LIMIT ?",
        cursor_params + [limit + 1],
    )
    rows = result.fetchall()
    columns = [desc[0] for desc in result.description] if result.description else []
    data = [dict(zip(columns, r)) for r in rows[:limit]]
    has_more = len(rows) > limit
    next_cursor = data[-1]["id"] if data and has_more else 0

    return {
        "data": data,
        "total": total,
        "cursor": cursor,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


def _query_request_detail(telemetry, request_id: int) -> dict | None:
    """Single request detail — mirrors DashboardAPI.get_request()."""
    conn = telemetry.conn
    result = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,))
    row = result.fetchone()
    if row is None:
        return None
    columns = [desc[0] for desc in result.description] if result.description else []
    result_dict = dict(zip(columns, row))
    for field in ("request_headers", "response_headers"):
        if result_dict.get(field):
            try:
                result_dict[field] = json.loads(result_dict[field])
            except json.JSONDecodeError:
                pass
    return result_dict


def _query_max_id(telemetry) -> int:
    """Current max request ID — mirrors DashboardAPI.get_max_id()."""
    conn = telemetry.conn
    row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM requests").fetchone()
    return row[0]


def _query_requests_since(telemetry, last_id: int) -> list[dict]:
    """New requests since last_id — mirrors DashboardAPI.get_requests_since()."""
    conn = telemetry.conn
    result = conn.execute(
        "SELECT id, timestamp, method, url, upstream, response_status, latency_ms "
        "FROM requests WHERE id > ? ORDER BY id ASC",
        (last_id,),
    )
    rows = result.fetchall()
    columns = [desc[0] for desc in result.description] if result.description else []
    return [dict(zip(columns, r)) for r in rows]


def _query_all_filtered(telemetry, search: str, method: str, status: int) -> list[dict]:
    """All filtered requests — mirrors DashboardAPI.get_all_filtered()."""
    conn = telemetry.conn
    where, params = _build_where(search, method, status)
    result = conn.execute(
        f"SELECT * FROM requests WHERE {where} ORDER BY id DESC", params
    )
    rows = result.fetchall()
    columns = [desc[0] for desc in result.description] if result.description else []
    return [dict(zip(columns, r)) for r in rows]
