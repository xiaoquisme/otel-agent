"""Model discovery and caching for the /v1/models endpoint."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from otel_agent.config import Config, Provider

logger = logging.getLogger(__name__)

DEFAULT_TTL = 300.0  # 5 minutes


class ModelCache:
    """TTL-based cache for model lists per provider.

    Cache invalidates when TTL expires or config file changes.
    """

    def __init__(self, config: Config, ttl: float = DEFAULT_TTL) -> None:
        self._config = config
        self._ttl = ttl
        self._cache: dict[str, list[dict[str, Any]]] = {}
        self._timestamps: dict[str, float] = {}
        self._config_mtime: float = 0

    def _is_fresh(self, provider_name: str) -> bool:
        """Check if cached data for a provider is still fresh."""
        config_mtime = self._config._mtime
        if config_mtime != self._config_mtime:
            return False
        ts = self._timestamps.get(provider_name)
        if ts is None:
            return False
        return (time.monotonic() - ts) < self._ttl

    def get(self, provider_name: str) -> list[dict[str, Any]] | None:
        """Return cached models for a provider, or None if stale/missing."""
        if self._is_fresh(provider_name):
            return self._cache.get(provider_name)
        return None

    def put(self, provider_name: str, models: list[dict[str, Any]]) -> None:
        """Store models for a provider in the cache."""
        self._cache[provider_name] = models
        self._timestamps[provider_name] = time.monotonic()
        self._config_mtime = self._config._mtime

    def invalidate(self) -> None:
        """Clear the entire cache."""
        self._cache.clear()
        self._timestamps.clear()


async def fetch_provider_models(
    client: httpx.AsyncClient,
    provider: Provider,
    *,
    failures: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch model list from a single provider via GET /v1/models.

    Returns an empty list if the provider doesn't expose a models endpoint
    or is unreachable. Loopback Cursor providers use `agent --list-models`
    so clients never see the sidecar's stale hardcoded catalog.

    *failures* — when given, a credential failure is recorded in it as
    ``{provider_name: message}``. The empty list alone cannot carry that: it is
    exactly what a provider with no models returns, so a caller that has to
    tell the operator which provider is broken needs the distinction (KTD6).
    """
    from urllib.parse import urlparse

    from otel_agent.auth_vault import AuthError
    from otel_agent.provider_utils import resolve_bearer_async

    host = (urlparse(provider.base_url).hostname or "").lower()
    if provider.name == "cursor" and host in ("127.0.0.1", "localhost"):
        from otel_agent.cursor_sidecar import list_cursor_cli_models

        ids = list_cursor_cli_models(api_key=provider.api_key)
        return [
            {"id": model_id, "object": "model", "owned_by": "cursor", "created": 0}
            for model_id in ids
        ]

    url = f"{provider.base_url.rstrip('/')}/models"

    try:
        # Inside the try on purpose: resolving a subscription bearer can fail,
        # and this function is called once per provider by an endpoint that
        # must not lose the other providers' models over it (KTD6).
        headers = {"Authorization": f"Bearer {await resolve_bearer_async(provider)}"}
        resp = await client.get(url, headers=headers, timeout=10.0)
        if resp.status_code != 200:
            logger.warning(
                "Provider '%s' returned status %d from %s",
                provider.name, resp.status_code, url,
            )
            return []

        data = resp.json()
        raw_models = data.get("data", [])
        if not isinstance(raw_models, list):
            return []

        return raw_models
    except AuthError as e:
        logger.warning("Credential unavailable for provider '%s': %s", provider.name, e)
        if failures is not None:
            failures[provider.name] = str(e)
        return []
    except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as e:
        logger.warning("Failed to fetch models from provider '%s': %s", provider.name, e)
        return []
    except Exception as e:
        logger.warning("Unexpected error fetching models from '%s': %s", provider.name, e)
        return []


def aggregate_models(
    raw_models: dict[str, list[dict[str, Any]]],
    failures: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Aggregate model lists from multiple providers into OpenAI /v1/models format.

    Each model ID is prefixed with the provider name (e.g., 'openai/gpt-4o').

    *failures* names the providers that could not be listed at all. They are
    reported in the body rather than dropped: a provider that vanishes from the
    list is indistinguishable from one that was removed from the config, which
    is the silent absence KTD6 rules out. The aggregate itself still succeeds —
    the entries are additive, so a client reading ``data`` is unaffected.
    """
    result: list[dict[str, Any]] = []

    for provider_name, models in sorted(raw_models.items()):
        for model in models:
            original_id = model.get("id", "")
            result.append({
                "id": f"{provider_name}/{original_id}",
                "object": "model",
                "created": model.get("created", 0),
                "owned_by": provider_name,
            })

    body: dict[str, Any] = {"object": "list", "data": result}
    if failures:
        body["errors"] = [
            {"provider": name, "message": message, "type": "credential_error"}
            for name, message in sorted(failures.items())
        ]
    return body
