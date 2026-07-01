from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


DEFAULT_CONFIG = """\
# otel-agent configuration
# Docs: https://github.com/xiaoquisme/otel-agent

# Provider selection is configured by type.
# Exactly one provider under each type must be marked active: true.
# Requests are routed through standardized paths:
#   /openai      -> active OpenAI provider
#   /anthropic   -> active Anthropic provider

providers:
  openai:
    - name: xiaomi
      base_url: https://xxx.xxx/xxx
      api_key: YOUR_OPENAI_API_KEY
      active: true
    # - name: deesseek
    #   base_url: https://xxx.xxx/xxx
    #   api_key: YOUR_SECOND_OPENAI_API_KEY
    #   active: false

  anthropic:
    - name: deesseek
      base_url: https://xxx.xxx/xxx
      api_key: YOUR_ANTHROPIC_API_KEY
      active: true
    # - name: xiaomi
    #   base_url: https://xxx.xxx/xxx
    #   api_key: YOUR_SECOND_ANTHROPIC_API_KEY
    #   active: false
"""

VALID_TYPES = ("openai", "anthropic")


@dataclass
class KeyEntry:
    key: str
    active: bool = True


@dataclass
class ProviderEntry:
    name: str
    base_url: str
    api_key: str
    active: bool = False


@dataclass
class ProviderType:
    name: str
    entries: list[ProviderEntry] = field(default_factory=list)

    def active_entry(self) -> ProviderEntry | None:
        for entry in self.entries:
            if entry.active:
                return entry
        return None


class Config:
    """Loads and hot-reloads ~/.otel-agent/config.yaml."""

    def __init__(self, path: Path):
        self.path = path
        self._mtime: float = 0
        self._provider_types: dict[str, ProviderType] = {}
        self._active_lookup: dict[str, ProviderEntry] = {}
        self._reload()

    def _reload(self):
        if not self.path.exists():
            self._provider_types = {}
            self._active_lookup = {}
            return

        stat = self.path.stat().st_mtime
        if stat == self._mtime:
            return
        self._mtime = stat

        with open(self.path) as f:
            data = yaml.safe_load(f) or {}

        provider_types: dict[str, ProviderType] = {}
        active_lookup: dict[str, ProviderEntry] = {}

        raw_providers = data.get("providers") or {}
        for type_name, entries in raw_providers.items():
            provider_entries = []
            if not isinstance(entries, list):
                continue

            for item in entries:
                if not isinstance(item, dict):
                    continue
                provider_entries.append(ProviderEntry(
                    name=str(item.get("name", "")),
                    base_url=str(item.get("base_url", "")),
                    api_key=str(item.get("api_key", "")),
                    active=bool(item.get("active", False)),
                ))

            provider_type = ProviderType(name=str(type_name), entries=provider_entries)
            provider_types[provider_type.name] = provider_type

            active = provider_type.active_entry()
            if active:
                active_lookup[provider_type.name] = active

        self._provider_types = provider_types
        self._active_lookup = active_lookup
        self._validate()

    def _validate(self):
        for type_name, provider_type in self._provider_types.items():
            if type_name not in VALID_TYPES:
                raise ValueError(
                    f"Provider type '{type_name}' is not valid. "
                    f"Must be one of: {', '.join(VALID_TYPES)}"
                )

            active_entries = [entry for entry in provider_type.entries if entry.active]
            if len(active_entries) == 0:
                provider_names = [entry.name for entry in provider_type.entries]
                raise ValueError(
                    f"Provider type '{type_name}' has no active provider. "
                    f"Available providers: {', '.join(provider_names) or 'none'}. "
                    f"Set 'active: true' on exactly one provider in config."
                )
            if len(active_entries) > 1:
                names = ", ".join(entry.name for entry in active_entries)
                raise ValueError(
                    f"Provider type '{type_name}' has multiple active providers: {names}. "
                    f"Only one provider can be active per type. Set 'active: false' on all but one."
                )

            for entry in provider_type.entries:
                if not entry.base_url:
                    raise ValueError(
                        f"Provider '{entry.name}' (type: {type_name}) must have a base_url. "
                        f"Add a valid URL to the provider config."
                    )
                if not entry.api_key:
                    raise ValueError(
                        f"Provider '{entry.name}' (type: {type_name}) must have an api_key. "
                        f"Add a valid API key to the provider config."
                    )

    @property
    def provider_types(self) -> dict[str, ProviderType]:
        self._reload()
        return self._provider_types

    @property
    def active_providers(self) -> dict[str, ProviderEntry]:
        self._reload()
        return dict(self._active_lookup)

    def get_active_provider(self, type_name: str) -> ProviderEntry | None:
        self._reload()
        return self._active_lookup.get(type_name)

    @property
    def routes(self) -> list[dict[str, str]]:
        self._reload()
        result = []
        for type_name, entry in sorted(self._active_lookup.items()):
            result.append({
                "prefix": f"/{type_name}",
                "provider": entry.name,
                "type": type_name,
                "base_url": entry.base_url,
            })
        return result
