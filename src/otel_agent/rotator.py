from __future__ import annotations

from otel_agent.config import Config


class KeyRotator:
    """Round-robin key rotation, re-reads active keys from config each call."""

    def __init__(self, config: Config):
        self.config = config
        self._indices: dict[str, int] = {}  # provider_name -> current index

    def next(self, host: str) -> str | None:
        """Return the next active key for the provider matching host."""
        provider = self.config.get_provider(host)
        if not provider:
            return None

        active = provider.active_keys()
        if not active:
            return None

        name = provider.name
        idx = self._indices.get(name, 0) % len(active)
        key = active[idx]
        self._indices[name] = idx + 1
        return key
