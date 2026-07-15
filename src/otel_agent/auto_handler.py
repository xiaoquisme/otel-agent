"""Auto-mode handler — orchestrates the auto-routing pipeline.

Intercepts model="auto" requests and routes them through:
1. Task classification (classifier.py)
2. Session cache lookup (session_cache.py)
3. Provider selection via Thompson Sampling (auto_router.py)
4. Fallback with circuit breaking (circuit_breaker.py)
5. Response headers and telemetry logging
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any


import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from otel_agent.auto_router import AutoRouter
from otel_agent.circuit_breaker import CircuitBreaker
from otel_agent.classifier import classify_task
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
from otel_agent.server import normalize_usage
from otel_agent.session_cache import SessionCache

logger = logging.getLogger(__name__)

# Module-level singletons (initialized once per process)
_auto_router = AutoRouter()
_circuit_breaker = CircuitBreaker()
_session_cache = SessionCache()

# Tier ordering: simple is cheapest, reasoning is most expensive
TIER_ORDER = ["simple", "medium", "complex", "reasoning"]
TIER_INDEX = {t: i for i, t in enumerate(TIER_ORDER)}

# Auth header patterns per provider API format
AUTH_HEADERS = {
    "openai": lambda key: {"Authorization": f"Bearer {key}"},
    "anthropic": lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01"},
}


def _build_upstream_url(provider: Provider) -> str:
    """Build the upstream URL for a provider."""
    base = provider.base_url.rstrip("/")
    path = "messages" if provider.api_format == "anthropic" else "chat/completions"
    return f"{base}/{path}"


def _build_request_headers(provider: Provider) -> dict[str, str]:
    """Build auth + content-type headers for a provider."""
    headers = AUTH_HEADERS[provider.api_format](provider.api_key)
    headers["Content-Type"] = "application/json"
    return headers


def _build_routing_decision(
    tier: str, provider_name: str, reason: str, fallback_depth: int, error: str | None = None,
) -> dict:
    """Build a routing_decision dict for telemetry and response headers."""
    d = {"tier": tier, "provider": provider_name, "reason": reason, "fallback_depth": fallback_depth}
    if error:
        d["error"] = error
    return d


def _select_provider_for_tier(
    tier: str,
    config: Config,
    session_id: str | None,
    messages: list[dict],
) -> tuple[Provider, str, str] | None:
    """Select a provider for the given tier.

    Returns (provider, tier_used, reason) or None if no providers available.
    """
    # Check session cache first
    cached = _session_cache.get(session_id, messages)
    if cached:
        provider = config.get_provider(cached.provider_name)
        if provider and _circuit_breaker.is_available(cached.provider_name):
            return provider, cached.tier, "session_sticky"

    # Get available providers for this tier
    available = config.get_providers_for_tier(tier)
    available = [p for p in available if _circuit_breaker.is_available(p.name)]

    if not available:
        # Fallback: try cheaper tiers first (simple < medium < complex < reasoning)
        idx = TIER_INDEX.get(tier, len(TIER_ORDER))
        for fallback_tier in reversed(TIER_ORDER[:idx]):
            available = config.get_providers_for_tier(fallback_tier)
            available = [p for p in available if _circuit_breaker.is_available(p.name)]
            if available:
                tier = fallback_tier
                break

    if not available:
        return None

    # Seed router (only seeds once per provider per tier)
    _auto_router.seed_from_costs(tier, available)

    # Select via Thompson Sampling
    provider = _auto_router.select_provider(tier, available)
    if provider is None:
        return None

    return provider, tier, "cost_optimized"


def _prepare_request_body(
    body: dict,
    provider: Provider,
    client_format: str,
) -> dict:
    """Prepare the upstream request body for a provider.

    Handles format conversion between client format and provider format.
    """
    upstream_body = dict(body)

    # Use provider's default model (client sent "auto", provider needs a real model)
    # If no default_model configured, remove the "auto" so the provider uses its own default
    if provider.default_model:
        upstream_body["model"] = provider.default_model
    else:
        upstream_body.pop("model", None)

    # Convert between formats if needed
    if client_format == "openai" and provider.api_format == "anthropic":
        upstream_body = openai_to_anthropic_request(upstream_body)
    elif client_format == "anthropic" and provider.api_format == "openai":
        upstream_body = anthropic_to_openai_request(upstream_body)

    return upstream_body


def _log_routing_telemetry(
    telemetry: TelemetryLogger,
    request: Request,
    status_code: int,
    resp_body: dict | str,
    latency_ms: float,
    provider: Provider,
    routing_decision: dict,
    request_body: str = "",
    resp_headers: dict[str, str] | None = None,
    log_body: bool = True,
    client_format: str = "openai",
) -> None:
    """Log request with routing metadata to telemetry database."""
    try:
        body_str = json.dumps(resp_body) if isinstance(resp_body, dict) else str(resp_body)
        usage = normalize_usage(resp_body)
        model_name = None
        if isinstance(resp_body, dict):
            model_name = resp_body.get("model") if resp_body.get("model") else None
        stored_body = request_body[:500_000] if log_body else ""
        stored_headers = redact_sensitive_headers(resp_headers) if resp_headers else {}

        # Inject routing_decision into request_headers for persistence
        enriched_headers = dict(request.headers)
        enriched_headers["x-routing-decision"] = json.dumps(routing_decision)

        telemetry.log_request(
            method=request.method,
            url=str(request.url),
            request_headers=enriched_headers,
            request_body=stored_body,
            response_status=status_code,
            response_headers=stored_headers,
            response_body=body_str[:500_000],
            latency_ms=latency_ms,
            upstream=provider.base_url,
            model_name=model_name,
            input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"], timestamp=None,
            format=client_format,
        )
    except Exception:
        logger.exception("Failed to log auto-routing telemetry")




async def handle_auto_mode(
    body: dict,
    config: Config,
    client: httpx.AsyncClient,
    telemetry: TelemetryLogger,
    request: Request,
    is_stream: bool,
    client_format: str = "openai",
) -> Any:
    """Handle a model='auto' request through the auto-routing pipeline.

    Args:
        body: The parsed request body (already JSON).
        config: The gateway config.
        client: The httpx async client.
        telemetry: The telemetry logger.
        request: The FastAPI Request object.
        is_stream: Whether the client requested streaming.
        client_format: The client's expected format ("openai" or "anthropic").
    """
    messages = body.get("messages", [])
    session_id = request.headers.get("X-Session-ID")

    tier = classify_task(messages)
    result = _select_provider_for_tier(tier, config, session_id, messages)

    if result is None:
        return JSONResponse(
            {"error": {"message": "No providers available for auto-routing", "type": "server_error"}},
            status_code=503,
        )

    provider, tier_used, reason = result

    # Cache session decision (skip if already cached with same provider/tier)
    cached = _session_cache.get(session_id, messages)
    if cached is None or cached.provider_name != provider.name or cached.tier != tier_used:
        _session_cache.set(session_id, messages, provider.name, tier_used)

    upstream_body = _prepare_request_body(body, provider, client_format)
    url = _build_upstream_url(provider)
    headers = _build_request_headers(provider)

    start_time = time.monotonic()
    original_body = json.dumps(body)

    fallback_depth = 0
    max_fallbacks = 5
    current_provider = provider
    current_tier = tier_used

    while fallback_depth < max_fallbacks:
        try:
            routing_decision = _build_routing_decision(
                tier_used, current_provider.name, reason, fallback_depth,
            )
            handler = _handle_streaming_auto if is_stream else _handle_non_streaming_auto
            return await handler(
                client, url, headers, upstream_body,
                current_provider, telemetry, request, start_time,
                source_format=client_format, target_format=current_provider.api_format,
                request_body=original_body, log_body=config.log_request_body,
                routing_decision=routing_decision,
            )

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            _auto_router.record_outcome(current_provider.name, current_tier, success=False)
            _circuit_breaker.record_failure(current_provider.name)

            fallback_depth += 1
            available = config.get_providers_for_tier(current_tier)
            available = [
                p for p in available
                if p.name != current_provider.name and _circuit_breaker.is_available(p.name)
            ]

            if not available:
                latency_ms = (time.monotonic() - start_time) * 1000
                error_body = {"error": {"message": f"All providers failed. Last error: {e}", "type": "server_error"}}
                _log_routing_telemetry(
                    telemetry, request, 502, error_body, latency_ms,
                    current_provider, routing_decision=_build_routing_decision(
                        tier_used, current_provider.name, reason, fallback_depth, error=str(e),
                    ),
                    request_body=original_body, log_body=config.log_request_body,
                    client_format=client_format,
                )
                return JSONResponse(error_body, status_code=502)

            current_provider = available[0]
            reason = f"fallback_from_{current_provider.name}"
            url = _build_upstream_url(current_provider)
            headers = _build_request_headers(current_provider)
            upstream_body = _prepare_request_body(body, current_provider, client_format)

    latency_ms = (time.monotonic() - start_time) * 1000
    error_body = {"error": {"message": "Max fallback depth exceeded", "type": "server_error"}}
    _log_routing_telemetry(
        telemetry, request, 502, error_body, latency_ms,
        current_provider, routing_decision=_build_routing_decision(
            tier_used, current_provider.name, reason, fallback_depth, error="max_fallbacks_exceeded",
        ),
        request_body=original_body, log_body=config.log_request_body,
        client_format=client_format,
    )
    return JSONResponse(error_body, status_code=502)


async def _handle_non_streaming_auto(
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
    routing_decision: dict | None = None,
) -> JSONResponse:
    """Handle a non-streaming auto-mode request. Raises on connection errors."""
    # Make the request — let ConnectError/TimeoutException propagate
    resp = await client.post(url, headers=headers, json=body)

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

    # Build routing headers
    routing_headers = {}
    if routing_decision:
        routing_headers = {
            "X-Routed-Provider": routing_decision["provider"],
            "X-Routed-Tier": routing_decision["tier"],
            "X-Routed-Reason": routing_decision.get("reason", ""),
        }
        if routing_decision.get("fallback_depth", 0) > 0:
            routing_headers["X-Routed-Fallback-Depth"] = str(routing_decision["fallback_depth"])

    # Log telemetry with routing metadata
    _log_routing_telemetry(
        telemetry, request, resp.status_code, resp_body, latency_ms,
        provider, routing_decision=routing_decision or {},
        request_body=request_body, resp_headers=dict(resp.headers),
        log_body=log_body, client_format=source_format,
    )

    # Add routing headers to response
    response = JSONResponse(resp_body, status_code=resp.status_code)
    for k, v in routing_headers.items():
        response.headers[k] = v

    return response


async def _handle_streaming_auto(
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
    routing_decision: dict | None = None,
) -> StreamingResponse:
    """Handle a streaming auto-mode request. Raises on connection errors."""

    async def stream_generator():
        collected_text = ""
        resp_headers: dict[str, str] = {}
        stream_status = 200
        last_valid_usage: dict | None = None
        sent_done = False

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
                                sent_done = True
                            break

                        try:
                            chunk_data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        if source_format == target_format:
                            yield f"data: {json.dumps(chunk_data)}\n\n".encode()
                        elif source_format == "openai" and target_format == "anthropic":
                            converted = convert_anthropic_chunk_to_openai(chunk_data)
                            if converted:
                                yield f"data: {json.dumps(converted)}\n\n".encode()
                        elif source_format == "anthropic" and target_format == "openai":
                            converted = convert_openai_chunk_to_anthropic(chunk_data)
                            if converted:
                                yield f"data: {json.dumps(converted)}\n\n".encode()

                        collected_text += json.dumps(chunk_data)
                        chunk_usage = normalize_usage(chunk_data)
                        if chunk_usage["total_tokens"] is not None:
                            last_valid_usage = chunk_usage
                    else:
                        yield f"{line}\n".encode()

                if not sent_done and source_format == "openai":
                    yield b"data: [DONE]\n\n"

        except httpx.ConnectError:
            stream_status = 502
            error_msg = json.dumps({"error": {"message": "Connection failed", "type": "server_error"}})
            yield f"data: {error_msg}\n\n".encode()
        except httpx.TimeoutException:
            stream_status = 504
            error_msg = json.dumps({"error": {"message": "Timeout", "type": "server_error"}})
            yield f"data: {error_msg}\n\n".encode()
        finally:
            latency_ms = (time.monotonic() - start_time) * 1000
            resp_body: dict = {"streamed": True, "preview": collected_text}
            if last_valid_usage is not None:
                resp_body["usage"] = {
                    "input_tokens": last_valid_usage["input_tokens"],
                    "output_tokens": last_valid_usage["output_tokens"],
                    "total_tokens": last_valid_usage["total_tokens"],
                }
            _log_routing_telemetry(
                telemetry, request, stream_status, resp_body, latency_ms,
                provider, routing_decision=routing_decision or {},
                request_body=request_body, resp_headers=resp_headers,
                log_body=log_body, client_format=source_format,
            )

    return StreamingResponse(stream_generator(), media_type="text/event-stream")
