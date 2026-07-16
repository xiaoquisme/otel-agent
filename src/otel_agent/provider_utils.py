"""Shared provider utilities — URL building, auth headers, model name prefixing."""
from __future__ import annotations

from otel_agent.config import Provider

# Auth header patterns per provider API format
AUTH_HEADERS = {
    "openai": lambda key: {"Authorization": f"Bearer {key}"},
    "anthropic": lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01"},
}


def build_upstream_url(provider: Provider) -> str:
    """Build the upstream URL for a provider."""
    base = provider.base_url.rstrip("/")
    path = "messages" if provider.api_format == "anthropic" else "chat/completions"
    return f"{base}/{path}"


def build_request_headers(provider: Provider) -> dict[str, str]:
    """Build auth + content-type headers for a provider."""
    headers = AUTH_HEADERS[provider.api_format](provider.api_key)
    headers["Content-Type"] = "application/json"
    return headers


def prefix_model_name(model_name: str | None, provider_name: str) -> str | None:
    """Prefix model name with provider config name for dashboard display."""
    return f"{provider_name}/{model_name}" if model_name else None
