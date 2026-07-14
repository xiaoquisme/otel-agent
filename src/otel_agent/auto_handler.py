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
from fastapi.responses import JSONResponse

from otel_agent.auto_router import AutoRouter
from otel_agent.circuit_breaker import CircuitBreaker
from otel_agent.classifier import classify_task
from otel_agent.config import Config, Provider
from otel_agent.session_cache import SessionCache

logger = logging.getLogger(__name__)

# Module-level singletons (initialized once per process)
_auto_router = AutoRouter()
_circuit_breaker = CircuitBreaker()
_session_cache = SessionCache()

# Tier ordering: simple is cheapest, reasoning is most expensive
TIER_ORDER = ["simple", "medium", "complex", "reasoning"]


def _build_upstream_url(provider: Provider) -> str:
    """Build the upstream URL for a provider."""
    base = provider.base_url.rstrip("/")
    path = "messages" if provider.api_format == "anthropic" else "chat/completions"
    return f"{base}/{path}"


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
        idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else len(TIER_ORDER)
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


async def handle_auto_mode(
    body: dict,
    config: Config,
    client: httpx.AsyncClient,
    telemetry: Any,
    request: Any,
    is_stream: bool,
) -> Any:
    """Handle a model='auto' request through the auto-routing pipeline."""
    from otel_agent.server import _handle_non_streaming, _handle_streaming, AUTH_HEADERS

    messages = body.get("messages", [])
    session_id = request.headers.get("X-Session-ID")

    # Step 1: Classify the task
    tier = classify_task(messages)

    # Step 2: Select provider (with session stickiness + circuit breaking)
    result = _select_provider_for_tier(tier, config, session_id, messages)

    if result is None:
        return JSONResponse(
            {"error": {"message": "No providers available for auto-routing", "type": "server_error"}},
            status_code=503,
        )

    provider, tier_used, reason = result

    # Step 3: Cache session decision
    _session_cache.set(session_id, messages, provider.name, tier_used)

    # Step 4: Prepare upstream request
    upstream_body = dict(body)
    upstream_body.pop("model", None)  # Remove model — provider uses its default

    needs_conversion = provider.api_format == "anthropic"
    if needs_conversion:
        from otel_agent.converter import openai_to_anthropic_request
        upstream_body = openai_to_anthropic_request(upstream_body)

    url = _build_upstream_url(provider)
    headers = AUTH_HEADERS[provider.api_format](provider.api_key)
    headers["Content-Type"] = "application/json"

    start_time = time.monotonic()
    original_body = json.dumps(body)

    # Step 5: Forward request with fallback
    fallback_depth = 0
    max_fallbacks = 5
    current_provider = provider
    current_tier = tier_used

    while fallback_depth < max_fallbacks:
        try:
            if is_stream:
                response = await _handle_streaming(
                    client, url, headers, upstream_body,
                    current_provider, telemetry, request, start_time,
                    source_format="openai", target_format=current_provider.api_format,
                    request_body=original_body, log_body=config.log_request_body,
                )
            else:
                response = await _handle_non_streaming(
                    client, url, headers, upstream_body,
                    current_provider, telemetry, request, start_time,
                    source_format="openai", target_format=current_provider.api_format,
                    request_body=original_body, log_body=config.log_request_body,
                )

            # Step 6: Record success and add routing headers
            _auto_router.record_outcome(current_provider.name, current_tier, success=True)
            _circuit_breaker.record_success(current_provider.name)

            if hasattr(response, 'headers'):
                response.headers["X-Routed-Provider"] = current_provider.name
                response.headers["X-Routed-Tier"] = current_tier
                response.headers["X-Routed-Reason"] = reason
                if fallback_depth > 0:
                    response.headers["X-Routed-Fallback-Depth"] = str(fallback_depth)

            return response

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
                return JSONResponse(
                    {"error": {"message": f"All providers failed. Last error: {e}", "type": "server_error"}},
                    status_code=502,
                )

            current_provider = available[0]
            reason = f"fallback_from_{current_provider.name}"
            url = _build_upstream_url(current_provider)
            headers = AUTH_HEADERS[current_provider.api_format](current_provider.api_key)
            headers["Content-Type"] = "application/json"

    return JSONResponse(
        {"error": {"message": "Max fallback depth exceeded", "type": "server_error"}},
        status_code=502,
    )
