"""Key rotation / bearer resolution for provider credentials."""
from __future__ import annotations

from otel_agent.auth_vault import resolve_bearer
from otel_agent.config import Config


class KeyRotator:
    """Returns the live credential for a given provider name."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def get_key(self, provider_name: str) -> str | None:
        """Return the resolved bearer for the named provider, or None."""
        provider = self.config.get_provider(provider_name)
        if not provider:
            return None
        try:
            return resolve_bearer(provider)
        except Exception:
            return provider.api_key or None
