"""Key rotation for provider API keys."""

from __future__ import annotations

from otel_agent.config import Config


class KeyRotator:
    """Returns the API key for a given provider name."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def get_key(self, provider_name: str) -> str | None:
        """Return the api_key for the named provider, or None."""
        provider = self.config.get_provider(provider_name)
        if not provider:
            return None
        return provider.api_key or None
