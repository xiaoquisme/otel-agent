from __future__ import annotations

from otel_agent.config import Config


class KeyRotator:
    """Round-robin key rotation for provider api_key lists."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._indexes: dict[str, int] = {}

    def next_by_api_key(self, provider_type: str) -> str | None:
        """Return the provider api_key for the given type, reloaded from config."""
        provider = self.config.get_active_provider(provider_type)
        if not provider:
            return None
        key = provider.api_key
        if not key:
            return None
        return key
