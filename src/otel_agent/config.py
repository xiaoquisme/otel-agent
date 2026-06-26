from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


DEFAULT_CONFIG = """\
# otel-agent configuration
# Docs: https://github.com/xiaoquisme/otel-agent

# Default provider for requests to localhost (reverse proxy mode)
# When a client sends requests directly to http://127.0.0.1:8080,
# the proxy forwards them to this provider's base_url.
# If not set and only one provider exists, it's used automatically.
# default_provider: openai

providers:
  openai:
    type: openai
    prefix: /openai
    base_url: https://api.openai.com/v1
    keys:
      - key: YOUR_OPENAI_API_KEY
        active: true
      # Add more keys to rotate:
      # - key: YOUR_SECOND_KEY
      #   active: true

  anthropic:
    type: anthropic
    prefix: /anthropic
    base_url: https://api.anthropic.com
    keys:
      - key: YOUR_ANTHROPIC_API_KEY
        active: true
"""

VALID_TYPES = ("openai", "anthropic")


@dataclass
class KeyEntry:
    key: str
    active: bool = True


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    type: str = "openai"
    prefix: str = ""
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
        self._route_table: dict[str, str] = {}  # prefix -> provider_name
        self._reload()

    def _reload(self):
        if not self.path.exists():
            self._providers = {}
            self._route_table = {}
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

            # Infer type from name if not set
            ptype = pconf.get("type", "")
            if not ptype:
                ptype = "anthropic" if "anthropic" in name else "openai"

            # Default prefix from name if not set
            prefix = pconf.get("prefix", f"/{name}")

            providers[name] = ProviderConfig(
                name=name,
                base_url=pconf.get("base_url", ""),
                type=ptype,
                prefix=prefix,
                keys=keys,
            )

        self._providers = providers
        self._route_table = self._build_route_table()
        self._validate_routes()

    def _build_route_table(self) -> dict[str, str]:
        """Build {prefix: provider_name} dict from providers."""
        table = {}
        for name, provider in self._providers.items():
            if provider.prefix:
                table[provider.prefix] = name
        return table

    def _validate_routes(self):
        """Validate route configuration. Raises ValueError on conflicts."""
        seen_prefixes: dict[str, str] = {}
        for name, provider in self._providers.items():
            prefix = provider.prefix
            if not prefix:
                continue
            if not prefix.startswith("/"):
                raise ValueError(
                    f"Provider '{name}' prefix must start with '/', got '{prefix}'"
                )
            if prefix.endswith("/") and prefix != "/":
                raise ValueError(
                    f"Provider '{name}' prefix must not end with '/', got '{prefix}'"
                )
            if provider.type not in VALID_TYPES:
                raise ValueError(
                    f"Provider '{name}' type must be one of {VALID_TYPES}, got '{provider.type}'"
                )
            if not provider.base_url:
                raise ValueError(
                    f"Provider '{name}' must have a base_url"
                )
            if prefix in seen_prefixes:
                other = seen_prefixes[prefix]
                raise ValueError(
                    f"Duplicate prefix '{prefix}' on providers '{other}' and '{name}'"
                )
            seen_prefixes[prefix] = name

    @property
    def default_provider_name(self) -> str:
        """Return the default provider name (explicit or auto-detected)."""
        self._reload()
        if self._default_provider and self._default_provider in self._providers:
            return self._default_provider
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
        if host in ("127.0.0.1", "localhost"):
            default_name = self.default_provider_name
            if default_name:
                return self._providers.get(default_name)
        return None

    def get_provider_by_prefix(self, path: str) -> Optional[ProviderConfig]:
        """Find a provider by longest prefix match on the request path.

        /openai/v1/chat/completions matches /openai.
        /anthropic/v1/messages matches /anthropic.
        """
        self._reload()
        best_prefix = ""
        best_name = ""
        for prefix, name in self._route_table.items():
            if path == prefix or path.startswith(prefix + "/"):
                if len(prefix) > len(best_prefix):
                    best_prefix = prefix
                    best_name = name
        if best_name:
            return self._providers.get(best_name)
        return None

    def get_active_keys(self, host: str) -> list[str]:
        self._reload()
        provider = self.get_provider(host)
        if provider:
            return provider.active_keys()
        return []

    @property
    def routes(self) -> list[dict[str, str]]:
        """Return route table as list of dicts for display."""
        self._reload()
        result = []
        for prefix, name in sorted(self._route_table.items()):
            provider = self._providers.get(name)
            if provider:
                result.append({
                    "prefix": prefix,
                    "provider": name,
                    "type": provider.type,
                    "base_url": provider.base_url,
                })
        return result
