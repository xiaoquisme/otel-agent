from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


DEFAULT_CONFIG = """\
# otel-agent configuration
# Docs: https://github.com/your-org/otel-agent

# Default provider for requests to localhost (reverse proxy mode)
# When a client sends requests directly to http://127.0.0.1:8080,
# the proxy forwards them to this provider's base_url.
# If not set and only one provider exists, it's used automatically.
# default_provider: openai

providers:
  openai:
    base_url: https://api.openai.com/v1
    keys:
      - key: YOUR_OPENAI_API_KEY
        active: true
      # Add more keys to rotate:
      # - key: YOUR_SECOND_KEY
      #   active: true

  anthropic:
    base_url: https://api.anthropic.com
    keys:
      - key: YOUR_ANTHROPIC_API_KEY
        active: true
"""


@dataclass
class KeyEntry:
    key: str
    active: bool = True


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    keys: list[KeyEntry] = field(default_factory=list)

    def active_keys(self) -> list[str]:
        return [k.key for k in self.keys if k.active]


class Config:
    """Loads and hot-reloads ~/.otel-agent/config.yaml."""

    def __init__(self, path: Path):
        self.path = path
        self._mtime: float = 0
        self._providers: dict[str, ProviderConfig] = {}
        self._default_provider: str = ""
        self._reload()

    def _reload(self):
        if not self.path.exists():
            self._providers = {}
            return

        stat = self.path.stat().st_mtime
        if stat == self._mtime:
            return
        self._mtime = stat

        with open(self.path) as f:
            data = yaml.safe_load(f) or {}

        self._default_provider = data.get("default_provider", "")

        providers = {}
        for name, pconf in (data.get("providers") or {}).items():
            keys = []
            for entry in (pconf.get("keys") or []):
                if isinstance(entry, dict):
                    keys.append(KeyEntry(
                        key=entry.get("key", ""),
                        active=bool(entry.get("active", True)),
                    ))
                elif isinstance(entry, str):
                    keys.append(KeyEntry(key=entry, active=True))
            providers[name] = ProviderConfig(
                name=name,
                base_url=pconf.get("base_url", ""),
                keys=keys,
            )
        self._providers = providers

    @property
    def default_provider_name(self) -> str:
        """Return the default provider name (explicit or auto-detected)."""
        self._reload()
        if self._default_provider and self._default_provider in self._providers:
            return self._default_provider
        # Auto-detect: if only one provider, use it
        if len(self._providers) == 1:
            return next(iter(self._providers))
        return ""

    def get_provider(self, host: str) -> Optional[ProviderConfig]:
        """Find a provider whose name is a substring of host.

        Falls back to default_provider for localhost requests.
        """
        self._reload()
        for name, provider in self._providers.items():
            if name in host:
                return provider
        # Fallback: use default provider for localhost/127.0.0.1
        if host in ("127.0.0.1", "localhost"):
            default_name = self.default_provider_name
            if default_name:
                return self._providers.get(default_name)
        return None

    def get_active_keys(self, host: str) -> list[str]:
        self._reload()
        provider = self.get_provider(host)
        if provider:
            return provider.active_keys()
        return []
