"""Shared provider utilities — URL building, auth headers, model name prefixing."""
from __future__ import annotations

import asyncio

from otel_agent.config import Provider

# Auth header patterns per provider API format
AUTH_HEADERS = {
    "openai": lambda key: {"Authorization": f"Bearer {key}"},
    "anthropic": lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01"},
}


def build_upstream_url(provider: Provider) -> str:
    """Build the upstream URL for a provider."""
    base = provider.base_url.rstrip("/")
    if provider.api_format == "anthropic":
        # Anthropic API lives at /v1/messages; auto-append /v1 when missing
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return f"{base}/messages"
    return f"{base}/chat/completions"


def build_image_upstream_url(provider: Provider) -> str:
    """Build the upstream URL for image generation (OpenAI /v1/images/generations)."""
    base = provider.base_url.rstrip("/")
    return f"{base}/images/generations"


def build_image_edit_upstream_url(provider: Provider) -> str:
    """Build the upstream URL for image editing (OpenAI /v1/images/edits)."""
    base = provider.base_url.rstrip("/")
    return f"{base}/images/edits"


async def resolve_bearer_async(provider: Provider) -> str:
    """Resolve a provider's bearer without blocking the event loop (KTD1).

    Resolution may refresh a subscription credential over the network, and the
    vault's read-modify-write is deliberately blocking — it holds a
    cross-process file lock across the exchange — so it runs in a worker
    thread rather than on the loop.
    """
    from otel_agent.auth_vault import resolve_bearer

    return await asyncio.to_thread(resolve_bearer, provider)


async def build_request_headers(provider: Provider) -> dict[str, str]:
    """Build auth + content-type headers for a provider."""
    key = await resolve_bearer_async(provider)
    headers = AUTH_HEADERS[provider.api_format](key)
    headers["Content-Type"] = "application/json"
    return headers


def prefix_model_name(model_name: str | None, provider_name: str) -> str | None:
    """Prefix model name with provider config name for dashboard display."""
    return f"{provider_name}/{model_name}" if model_name else None


def rewrite_upstream_model(provider: Provider, upstream_model: str) -> str:
    """Adjust the stripped model id before sending it upstream."""
    from urllib.parse import urlparse

    from otel_agent.cursor_sidecar import cursor_cli_model_for_sidecar

    host = (urlparse(provider.base_url).hostname or "").lower()
    if provider.name == "cursor" and host in ("127.0.0.1", "localhost"):
        return cursor_cli_model_for_sidecar(upstream_model)
    return upstream_model
