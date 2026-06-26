from __future__ import annotations

from otel_agent.config import Config


class KeyRotator:
    """Round-robin key rotation, re-reads active keys from config each call."""

    def __init__(self, config: Config):
        self.config = config
        self._indices: dict[str, int] = {}  # provider_name -> current index

    def next(self, provider_name: str) -> str | None:
        """Return the next active key for the named provider."""
        self.config._reload()
        provider = self.config._providers.get(provider_name)
        if not provider:
            return None

        active = provider.active_keys()
        if not active:
            return None

        idx = self._indices.get(provider_name, 0) % len(active)
        key = active[idx]
        self._indices[provider_name] = idx + 1
        return key
